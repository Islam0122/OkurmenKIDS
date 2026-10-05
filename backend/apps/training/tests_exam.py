"""Exam Mode in the exam portal: /exam/?key=… → the attempt → the React
test screen (training.exam_api). One attempt per student across refreshes,
autosave, events and the violation policy, the server deadline, submit
rules, results — and that only the token issued to the browser that started
the attempt opens it.

Absolute imports only (see apps/academy/tests.py)."""
from __future__ import annotations

from datetime import timedelta
from unittest import mock

from django.test import Client
from django.urls import reverse
from rest_framework.test import APIClient

from apps.academy.models import Student
from apps.testing.models import (
    Answer,
    AttemptStatus,
    ExamEventType,
    FinishReason,
    QuestionType,
    SessionParticipant,
    SessionType,
    StudentAttempt,
    TestSession,
    TestStatus,
)
from apps.testing.services import exam_portal as portal
from apps.testing.services import questions as svc
from apps.testing.services.question_rules import OptionData, QuestionData
from apps.testing.tests.base import TestingFixture
from apps.training.exam_api import exam_token
from apps.training.models import PortalSettings
from apps.users.models import User

PORTAL = "https://train.example.com"


class ExamApiFixture(TestingFixture):
    def setUp(self):
        super().setUp()
        self.test.status = TestStatus.ACTIVE
        self.test.passing_score = 50
        self.test.time_limit_minutes = 30
        self.test.save()
        self.q_single = svc.save_question(self.test, QuestionData(QuestionType.SINGLE_CHOICE, "Backend?", options=[
            OptionData("Python", True), OptionData("HTML", False)]), points=2)
        self.q_multi = svc.save_question(self.test, QuestionData(QuestionType.MULTIPLE_CHOICE, "Immutable?", options=[
            OptionData("tuple", True), OptionData("str", True), OptionData("list", False)]))
        self.q_text = svc.save_question(self.test, QuestionData(
            QuestionType.TEXT, "Что такое Python?", correct_answers=["Язык программирования"]), is_required=False)
        self.session = TestSession.objects.create(
            test=self.test, group=self.group, session_type=SessionType.EXAM, duration=timedelta(hours=2),
            title="Итоговый экзамен",
        )
        self.session.start()
        self.api = APIClient()
        PortalSettings.objects.update_or_create(pk=1, defaults={"portal_url": PORTAL})

    def join(self, browser=None, student=None, **extra):
        """The session-key page: key + «pick yourself from the list» → start."""
        data = {"key": self.session.key, "start": "1", "student": str((student or self.student).pk), **extra}
        return (browser or self.client).post(reverse("testing_public_join"), data)

    def begin(self, browser=None, student=None) -> StudentAttempt:
        """/exam/?key=… → the exam portal with the attempt's token."""
        response = self.join(browser, student)
        self.assertEqual(response.status_code, 302, response.content[:300])
        attempt = StudentAttempt.objects.filter(session=self.session, student=student or self.student).latest("started_at")
        self.assertTrue(response["Location"].startswith(f"{PORTAL}/exam/{attempt.pk}#t="))
        self.token = response["Location"].split("#t=", 1)[1]
        return attempt

    def call(self, method, attempt, suffix="", token=None, **data):
        url = f"/api/v1/training/exam-attempts/{attempt.pk}/{suffix}"
        return getattr(self.api, method)(url, data, format="json", HTTP_X_ATTEMPT_TOKEN=token if token is not None else self.token)

    def put_answer(self, attempt, question, value, token=None):
        return self.call("put", attempt, f"answers/{question.pk}/", token=token, **value)

    def right(self):
        return {
            self.q_single: {"options": [str(self.q_single.options.get(is_correct=True).pk)]},
            self.q_multi: {"options": [str(o.pk) for o in self.q_multi.options.filter(is_correct=True)]},
        }

    def answer_right(self, attempt):
        for question, value in self.right().items():
            self.assertEqual(self.put_answer(attempt, question, value).status_code, 200)

    def event(self, attempt, event_type, **metadata):
        return self.call("post", attempt, "events/", event_type=event_type, metadata=metadata)


class ExamFlowTests(ExamApiFixture):
    def test_full_flow_same_attempt_after_refresh(self):
        attempt = self.begin()
        self.assertTrue(attempt.exam_mode)
        self.assertIsNotNone(attempt.expires_at)  # the server timer runs from the start
        state = self.call("get", attempt).data
        self.assertEqual((state["mode"], state["status"], state["show_explanation"]), ("exam", "active", False))
        self.assertEqual(len(state["questions"]), 3)
        self.assertTrue(all(q["feedback"] is None and not q["checked"] for q in state["questions"]))
        self.assertGreater(state["remaining_seconds"], 29 * 60)
        self.assertNotIn("back_url", state)  # no way out to a cabinet

        right = self.right()[self.q_single]
        self.assertEqual(self.put_answer(attempt, self.q_single, right).status_code, 200)
        # Refresh: the same attempt, the saved answer, the same deadline.
        again = self.call("get", attempt).data
        self.assertEqual(again["attempt_id"], str(attempt.pk))
        self.assertEqual(next(q for q in again["questions"] if q["id"] == str(self.q_single.pk))["answer"]["options"], right["options"])
        self.assertEqual(again["expires_at"], state["expires_at"])
        # The key page again (same browser) does not open a second attempt.
        self.assertEqual(self.begin().pk, attempt.pk)
        self.assertEqual(StudentAttempt.objects.filter(session=self.session, student=self.student).count(), 1)

        # Required question unanswered → refused with the reason.
        refused = self.call("post", attempt, "submit/")
        self.assertEqual((refused.status_code, refused.data["code"]), (400, "invalid"))
        self.assertIn("2", refused.data["detail"])
        self.put_answer(attempt, self.q_multi, self.right()[self.q_multi])
        result = self.call("post", attempt, "submit/").data
        self.assertEqual((result["mode"], result["status"], result["finish_reason"]), ("exam", "completed", "submitted"))
        self.assertTrue(result["passed"])
        self.assertNotIn("back_url", result)
        attempt.refresh_from_db()
        self.assertEqual(attempt.status, AttemptStatus.FINISHED)
        self.assertTrue(attempt.events.filter(event_type=ExamEventType.EXAM_SUBMITTED).exists())
        # Closed: no more answers, the result stays readable.
        self.assertEqual(self.put_answer(attempt, self.q_single, {"options": []}).status_code, 409)
        self.assertEqual(self.call("get", attempt, "result/").data["percentage"], result["percentage"])

    def test_a_name_only_session_runs_in_the_exam_portal_too(self):
        session = TestSession.objects.create(test=self.test, session_type=SessionType.EXAM, duration=timedelta(hours=1),
                                             title="Открытый экзамен")
        session.start()
        browser = Client()
        response = browser.post(reverse("testing_public_join"), {"key": session.key, "start": "1", "student_name": "Иван Иванов"})
        attempt = StudentAttempt.objects.get(session=session)
        self.assertTrue(response["Location"].startswith(f"{PORTAL}/exam/{attempt.pk}#t="))
        self.assertEqual((attempt.student_id, attempt.student_name, attempt.exam_mode), (None, "Иван Иванов", True))
        self.token = response["Location"].split("#t=", 1)[1]
        self.assertEqual(self.call("get", attempt).status_code, 200)
        # Refresh in the same browser → the same attempt; the same name elsewhere can't take it over.
        again = browser.post(reverse("testing_public_join"), {"key": session.key, "start": "1", "student_name": "Иван Иванов"})
        self.assertEqual(again["Location"].split("#")[0], response["Location"].split("#")[0])
        intruder = Client().post(reverse("testing_public_join"), {"key": session.key, "start": "1", "student_name": "Иван Иванов"})
        self.assertContains(intruder, "уже начат")
        self.assertEqual(StudentAttempt.objects.filter(session=session).count(), 1)

    def test_the_legacy_attempt_link_sends_an_exam_back_to_the_portal(self):
        attempt = self.begin()
        response = self.client.get(reverse("testing_public_take", args=[attempt.pk]))
        self.assertTrue(response["Location"].startswith(f"{PORTAL}/exam/{attempt.pk}#t="))
        self.assertEqual(Client().get(reverse("testing_public_take", args=[attempt.pk])).status_code, 404)  # not this browser's

    def test_without_a_portal_address_the_legacy_form_is_the_fallback(self):
        PortalSettings.objects.filter(pk=1).update(portal_url="")
        response = self.join()
        attempt = StudentAttempt.objects.get(session=self.session, student=self.student)
        self.assertEqual(response["Location"], reverse("testing_public_take", args=[attempt.pk]))
        self.assertFalse(attempt.exam_mode)
        self.assertEqual(self.client.get(response["Location"]).status_code, 200)


class AutosaveTests(ExamApiFixture):
    def setUp(self):
        super().setUp()
        self.attempt = self.begin()

    def test_saves_drafts_without_grading(self):
        response = self.put_answer(self.attempt, self.q_multi, self.right()[self.q_multi])
        self.assertEqual(response.status_code, 200)
        self.assertGreater(response.data["remaining_seconds"], 0)
        self.attempt.refresh_from_db()
        self.assertEqual(self.attempt.draft_answers[str(self.q_multi.pk)]["options"], self.right()[self.q_multi]["options"])
        self.assertFalse(Answer.objects.exists())  # graded only on submit
        self.assertTrue(self.attempt.events.filter(event_type=ExamEventType.ANSWER_SAVED).exists())
        participant = self.session.participants.get(student=self.student)
        self.assertEqual(participant.answered_count, 1)

    def test_validation(self):
        foreign = svc.save_question(self.test, QuestionData(QuestionType.SINGLE_CHOICE, "Not in attempt?", options=[
            OptionData("a", True), OptionData("b", False)]))
        cases = [
            (foreign, {"options": [str(foreign.options.first().pk)]}),
            (self.q_single, {"options": [str(self.q_multi.options.first().pk)]}),
            (self.q_single, {"options": [str(o.pk) for o in self.q_single.options.all()]}),
            (self.q_text, {"text": "x" * (portal.MAX_TEXT_ANSWER + 1)}),
        ]
        for question, value in cases:
            with self.subTest(question=question.text):
                self.assertEqual(self.put_answer(self.attempt, question, value).status_code, 400)
        self.attempt.refresh_from_db()
        self.assertEqual(self.attempt.draft_answers, {})

    def test_paused_session_rejects_saves(self):
        self.session.pause()
        response = self.put_answer(self.attempt, self.q_single, self.right()[self.q_single])
        self.assertEqual(response.status_code, 400)
        self.assertTrue(self.call("get", self.attempt).data["paused"])


class EventTests(ExamApiFixture):
    def setUp(self):
        super().setUp()
        self.attempt = self.begin()

    def test_tab_switch_is_counted_and_logged_without_extra_data(self):
        response = self.call("post", self.attempt, "events/", event_type="TAB_SWITCH", metadata={"question": 2, "answer": "secret"})
        self.assertEqual((response.status_code, response.data["tab_switch_count"]), (200, 1))
        self.assertEqual(self.attempt.events.get(event_type=ExamEventType.TAB_SWITCH).metadata, {"question": 2})  # "answer" dropped
        self.attempt.refresh_from_db()
        self.assertEqual((self.attempt.tab_switch_count, self.attempt.violation_count), (1, 1))

    def test_violations_are_counted(self):
        for event in ("COPY_ATTEMPT", "PASTE_ATTEMPT", "CUT_ATTEMPT", "CONTEXT_MENU_ATTEMPT", "DEVTOOLS_ATTEMPT"):
            self.assertEqual(self.event(self.attempt, event).status_code, 200)
        self.event(self.attempt, "PAGE_LEAVE")
        self.attempt.refresh_from_db()
        self.assertEqual((self.attempt.violation_count, self.attempt.tab_switch_count), (5, 0))

    def test_fullscreen_exit_counts_only_when_required(self):
        self.event(self.attempt, "FULLSCREEN_EXIT")
        self.attempt.refresh_from_db()
        self.assertEqual(self.attempt.violation_count, 0)
        self.test.require_fullscreen = True
        self.test.save()
        self.event(self.attempt, "FULLSCREEN_EXIT")
        self.attempt.refresh_from_db()
        self.assertEqual(self.attempt.violation_count, 1)

    def test_server_only_and_unknown_events_are_rejected(self):
        for event in ("EXAM_SUBMITTED", "TIME_EXPIRED", "anything"):
            self.assertEqual(self.event(self.attempt, event).status_code, 400)

    def test_exceeding_tab_switch_limit_ends_the_exam_with_saved_answers(self):
        self.test.max_tab_switches = 1
        self.test.save()
        self.answer_right(self.attempt)
        self.assertEqual(self.event(self.attempt, "TAB_SWITCH").status_code, 200)  # a warning, not the end
        second = self.event(self.attempt, "TAB_SWITCH")
        self.assertEqual((second.status_code, second.data["code"]), (409, "terminated"))
        self.attempt.refresh_from_db()
        self.assertEqual((self.attempt.status, self.attempt.finish_reason), (AttemptStatus.FINISHED, FinishReason.VIOLATIONS))
        self.assertEqual(self.attempt.score, 75.0)
        self.assertTrue(self.attempt.events.filter(event_type=ExamEventType.EXAM_TERMINATED).exists())

    def test_no_limit_never_terminates(self):
        self.test.max_tab_switches = None
        self.test.save()
        for _ in range(10):
            self.assertEqual(self.event(self.attempt, "TAB_SWITCH").status_code, 200)


class DeadlineTests(ExamApiFixture):
    def setUp(self):
        super().setUp()
        self.attempt = self.begin()
        self.answer_right(self.attempt)
        self.attempt.refresh_from_db()

    def later(self, seconds_after_deadline=10):
        return mock.patch("django.utils.timezone.now",
                          return_value=self.attempt.expires_at + timedelta(seconds=seconds_after_deadline))

    def test_backend_closes_expired_attempt_with_saved_answers(self):
        with self.later():
            response = self.put_answer(self.attempt, self.q_text, {"text": "Язык программирования"})
            state = self.call("get", self.attempt).data
        self.assertEqual(response.status_code, 409)
        self.assertNotEqual(state["status"], "active")  # closed by the server, not by the page
        self.attempt.refresh_from_db()
        self.assertEqual((self.attempt.status, self.attempt.finish_reason), (AttemptStatus.FINISHED, FinishReason.TIME_EXPIRED))
        self.assertEqual(self.attempt.finished_at, self.attempt.expires_at)
        self.assertEqual(self.attempt.score, 75.0)  # the late text answer was not accepted
        self.assertTrue(self.attempt.events.filter(event_type=ExamEventType.TIME_EXPIRED).exists())

    def test_without_auto_submit_the_attempt_expires_ungraded(self):
        self.test.auto_submit = False
        self.test.save()
        with self.later():
            self.call("get", self.attempt)
        self.attempt.refresh_from_db()
        self.assertEqual(self.attempt.status, AttemptStatus.EXPIRED)
        self.assertFalse(Answer.objects.exists())

    def test_auto_submit_at_zero_is_accepted(self):
        with self.later(seconds_after_deadline=2):
            response = self.call("post", self.attempt, "submit/", timed_out=True)
        self.assertEqual(response.status_code, 200)
        self.attempt.refresh_from_db()
        self.assertEqual((self.attempt.status, self.attempt.finish_reason), (AttemptStatus.FINISHED, FinishReason.TIME_EXPIRED))

    def test_remaining_time_comes_from_the_server(self):
        with mock.patch("django.utils.timezone.now", return_value=self.attempt.expires_at - timedelta(minutes=12)):
            self.assertEqual(self.call("get", self.attempt).data["remaining_seconds"], 12 * 60)


class ResultTests(ExamApiFixture):
    def setUp(self):
        super().setUp()
        self.attempt = self.begin()
        self.answer_right(self.attempt)

    def test_result_payload(self):
        self.put_answer(self.attempt, self.q_text, {"text": "nope"})
        result = self.call("post", self.attempt, "submit/").data
        self.assertEqual((result["percentage"], result["passed"], result["correct"]), (75.0, True, 2))
        self.assertEqual(Answer.objects.filter(attempt=self.attempt).count(), 3)

    def test_hidden_result(self):
        self.test.show_result = False
        self.test.save()
        result = self.call("post", self.attempt, "submit/").data
        self.assertFalse(result["show_result"])
        self.assertIsNone(result.get("percentage"))  # the score is not sent at all


class ExamAccessTests(ExamApiFixture):
    def test_only_the_token_of_this_browser_opens_the_attempt(self):
        attempt = self.begin()
        self.assertEqual(self.call("get", attempt, token="").status_code, 403)
        self.assertEqual(self.call("get", attempt, token="forged").status_code, 403)
        other = StudentAttempt.objects.create(session=self.session, student_name="X")
        self.assertEqual(self.call("get", other, token=exam_token(attempt)).status_code, 403)  # bound to its id
        self.assertEqual(self.call("get", attempt, "result/", token="").status_code, 403)


class StaffViewsTests(ExamApiFixture):
    def setUp(self):
        super().setUp()
        self.attempt = self.begin()
        self.event(self.attempt, "TAB_SWITCH")
        self.event(self.attempt, "COPY_ATTEMPT")
        self.admin = User.objects.create_superuser(username="root", email="root@okurmen.kg", password="x")
        self.admin_client = Client()
        self.admin_client.force_login(self.admin)

    def test_admin_monitoring_and_event_log(self):
        response = self.admin_client.get(reverse("admin:testing_exam_monitoring"))
        self.assertContains(response, "Aibek Asanov")
        response = self.admin_client.get(reverse("admin:testing_attempt_detail", args=[self.attempt.pk]))
        self.assertContains(response, "Журнал событий")
        self.assertContains(response, "Уход со страницы")
        self.assertContains(response, "Попытка копирования")

    def test_admin_settings_has_exam_mode_fields(self):
        response = self.admin_client.get(reverse("admin:testing_test_settings", args=[self.test.pk]))
        for field in ("max_tab_switches", "require_fullscreen", "auto_submit"):
            self.assertContains(response, field)

    def test_teacher_api_reports_violations(self):
        from apps.testing.teacher_api import ParticipantSerializer

        participant = self.session.participants.select_related("student", "attempt").get(student=self.student)
        data = ParticipantSerializer(participant).data
        self.assertEqual((data["tab_switch_count"], data["violation_count"]), (1, 2))


def roster_student(fixture, first_name="Bakyt"):
    """Another student of the session's roster."""
    other = Student.objects.create(first_name=first_name, last_name="Bekov", group=fixture.group)
    SessionParticipant.objects.get_or_create(session=fixture.session, student=other)
    return other
