"""Exam attempts in the shared test UI (training.exam_api): one attempt per
student across refreshes, autosave, the server deadline, the violation
policy, submit rules, results — and that only the student's token opens it.

Absolute imports only (see apps/academy/tests.py)."""
from __future__ import annotations

from datetime import timedelta

from django.urls import reverse
from rest_framework.test import APIClient

from apps.testing.models import AttemptStatus, ExamEventType, StudentAttempt
from apps.testing.tests.test_exam_portal import PortalFixture
from apps.training.exam_api import exam_token
from apps.training.models import PortalSettings


class ExamApiFixture(PortalFixture):
    def setUp(self):
        super().setUp()
        self.api = APIClient()
        PortalSettings.objects.update_or_create(pk=1, defaults={"portal_url": "https://train.example.com"})

    def begin(self) -> StudentAttempt:
        """«Начать экзамен» in the student portal → the shared test UI."""
        response = self.client.post(reverse("student_exam_prepare", args=[self.session.pk]), {"rules_accepted": "1"})
        attempt = StudentAttempt.objects.get(session=self.session, student=self.student)
        follow = self.client.get(response["Location"])
        self.assertEqual(follow.status_code, 302)
        self.assertTrue(follow["Location"].startswith(f"https://train.example.com/exam/{attempt.pk}#t="))
        self.token = follow["Location"].split("#t=", 1)[1]
        return attempt

    def call(self, method, attempt, suffix="", token=None, **data):
        url = f"/api/v1/training/exam-attempts/{attempt.pk}/{suffix}"
        return getattr(self.api, method)(url, data, format="json", HTTP_X_ATTEMPT_TOKEN=token if token is not None else self.token)


class ExamFlowTests(ExamApiFixture):
    def test_full_flow_same_attempt_after_refresh(self):
        attempt = self.begin()
        state = self.call("get", attempt).data
        self.assertEqual((state["mode"], state["status"], state["show_explanation"]), ("exam", "active", False))
        self.assertEqual(len(state["questions"]), 3)
        self.assertTrue(all(q["feedback"] is None and not q["checked"] for q in state["questions"]))
        self.assertGreater(state["remaining_seconds"], 29 * 60)

        right = str(self.q_single.options.get(is_correct=True).pk)
        saved = self.call("put", attempt, f"answers/{self.q_single.pk}/", options=[right])
        self.assertEqual(saved.status_code, 200)
        # Refresh: the same attempt, the saved answer, the same deadline.
        again = self.call("get", attempt).data
        self.assertEqual(again["attempt_id"], str(attempt.pk))
        self.assertEqual(next(q for q in again["questions"] if q["id"] == str(self.q_single.pk))["answer"]["options"], [right])
        self.assertEqual(again["expires_at"], state["expires_at"])
        # «Начать» again does not open a second attempt.
        self.client.post(reverse("student_exam_prepare", args=[self.session.pk]), {"rules_accepted": "1"})
        self.assertEqual(StudentAttempt.objects.filter(session=self.session, student=self.student).count(), 1)

        # Required question unanswered → refused with the reason.
        refused = self.call("post", attempt, "submit/")
        self.assertEqual((refused.status_code, refused.data["code"]), (400, "invalid"))
        self.assertIn("2", refused.data["detail"])
        multi = [str(o.pk) for o in self.q_multi.options.filter(is_correct=True)]
        self.call("put", attempt, f"answers/{self.q_multi.pk}/", options=multi)
        result = self.call("post", attempt, "submit/").data
        self.assertEqual((result["mode"], result["status"], result["finish_reason"]), ("exam", "completed", "submitted"))
        self.assertTrue(result["passed"])
        self.assertTrue(result["back_url"].endswith(reverse("student_portal_dashboard")))
        attempt.refresh_from_db()
        self.assertEqual(attempt.status, AttemptStatus.FINISHED)
        self.assertTrue(attempt.events.filter(event_type=ExamEventType.EXAM_SUBMITTED).exists())
        # Closed: no more answers, the result stays readable.
        self.assertEqual(self.call("put", attempt, f"answers/{self.q_single.pk}/", options=[]).status_code, 409)
        self.assertEqual(self.call("get", attempt, "result/").data["percentage"], result["percentage"])

    def test_the_server_deadline_closes_the_exam(self):
        attempt = self.begin()
        right = str(self.q_single.options.get(is_correct=True).pk)
        self.call("put", attempt, f"answers/{self.q_single.pk}/", options=[right])
        StudentAttempt.objects.filter(pk=attempt.pk).update(expires_at=attempt.started_at - timedelta(minutes=1))
        state = self.call("get", attempt).data
        self.assertNotEqual(state["status"], "active")  # closed by the server, not by the page
        attempt.refresh_from_db()
        self.assertEqual(attempt.finish_reason, "time_expired")
        self.assertEqual(self.call("put", attempt, f"answers/{self.q_single.pk}/", options=[]).status_code, 409)

    def test_violation_policy_of_the_test(self):
        self.test.max_tab_switches = 1
        self.test.save()
        attempt = self.begin()
        first = self.call("post", attempt, "events/", event_type="TAB_SWITCH")
        self.assertEqual((first.status_code, first.data["tab_switch_count"]), (200, 1))  # a warning, not the end
        second = self.call("post", attempt, "events/", event_type="TAB_SWITCH")
        self.assertEqual((second.status_code, second.data["code"]), (409, "terminated"))
        attempt.refresh_from_db()
        self.assertEqual(attempt.finish_reason, "violations")


class ExamAccessTests(ExamApiFixture):
    def test_only_the_students_token_opens_the_attempt(self):
        attempt = self.begin()
        self.assertEqual(self.call("get", attempt, token="").status_code, 403)
        self.assertEqual(self.call("get", attempt, token="forged").status_code, 403)
        other = StudentAttempt.objects.create(session=self.session, student_name="X")
        self.assertEqual(self.call("get", other, token=exam_token(attempt)).status_code, 403)  # bound to its id
        self.assertEqual(self.call("get", attempt, "result/", token="").status_code, 403)

    def test_without_a_portal_address_the_student_portal_page_stays(self):
        PortalSettings.objects.filter(pk=1).update(portal_url="")
        response = self.client.post(reverse("student_exam_prepare", args=[self.session.pk]), {"rules_accepted": "1"})
        page = self.client.get(response["Location"])
        self.assertEqual(page.status_code, 200)
