"""Team Lead and test sessions: create a session for a group, start it,
monitor it and see the students' results — never take the test themselves
(that is a student's action; only an Admin may check a test that way, on the
same student pages, with the same timer/grading).

Absolute imports only — see the note at the top of apps/academy/tests.py.
"""
from __future__ import annotations

from urllib.parse import urlparse

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from apps.academy.models import Student
from apps.testing.models import AttemptStatus, SessionStatus, SessionType, StudentAttempt, TestSession
from apps.testing.services import analytics, handoff
from apps.testing.services import attempts as attempt_service
from apps.testing.tests.test_student_flow import StudentFlowFixture
from apps.users.models import User

PASSWORD = "Str0ngPassw0rd!"


class TeamLeadSessionFixture(StudentFlowFixture):
    def setUp(self):
        super().setUp()
        self.lead = User.objects.create_user(
            username="lead", email="lead@okurmen.kg", password=PASSWORD, first_name="Нурлан",
            last_name="Lead", role=User.Role.TEAM_LEAD,
        )
        self.student2 = Student.objects.create(first_name="Aida", last_name="Bek", group=self.group)
        self.api = APIClient()
        self.api.force_authenticate(self.lead)
        # The only LMS account that may take a session's test (to check it).
        self.admin = User.objects.create_superuser(username="root", email="root@okurmen.kg", password=PASSWORD, first_name="R")
        self.taker = APIClient()
        self.taker.force_authenticate(self.admin)

    def create_session(self, client=None, **overrides):
        body = {
            "test": str(self.test.pk),
            "group": self.group.pk,
            "date": "2030-10-04",
            "start_time": "14:00",
            "end_time": "15:00",
            **overrides,
        }
        return (client or self.api).post("/api/v1/teacher/sessions/", body, format="json")

    def created_and_started(self) -> TestSession:
        response = self.create_session()
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.content)
        session_id = response.data["id"]
        started = self.api.post(f"/api/v1/teacher/sessions/{session_id}/start/")
        self.assertEqual(started.status_code, status.HTTP_200_OK, started.content)
        return TestSession.objects.get(pk=session_id)

    def open_handoff(self, url: str, web=None):
        """Open the API's signed link like the Team Lead's browser does."""
        web = web or self.client
        parsed = urlparse(url)
        return web.get(f"{parsed.path}?{parsed.query}")


class TeamLeadCreatesAndStartsSessionTests(TeamLeadSessionFixture):
    def test_team_lead_can_create_test_session(self):
        response = self.create_session()
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.content)
        session = TestSession.objects.get(pk=response.data["id"])
        self.assertEqual(session.created_by, self.lead)
        self.assertEqual(session.group, self.group)
        self.assertEqual(session.test, self.test)
        self.assertEqual(session.session_type, SessionType.EXAM)
        self.assertEqual(session.status, SessionStatus.CREATED)
        # The group's students get the session through the existing roster.
        self.assertEqual(set(session.participants.values_list("student_id", flat=True)), {self.student.pk, self.student2.pk})
        self.assertEqual(response.data["counts"]["total"], 2)
        self.assertEqual(response.data["phase"], "scheduled")
        self.assertEqual(response.data["test"]["title"], "Python Basics")
        self.assertEqual(response.data["group"]["name"], self.group.name)
        self.assertTrue(response.data["can_start"])

    def test_end_time_is_optional(self):
        self.test.time_limit_minutes = 40
        self.test.save()
        response = self.create_session(end_time="")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.content)
        session = TestSession.objects.get(pk=response.data["id"])
        self.assertEqual((session.scheduled_end - session.scheduled_start).total_seconds(), 40 * 60)

    def test_test_and_group_are_required(self):
        response = self.create_session(test="", group="")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("test", response.data)
        self.assertIn("group", response.data)

    def test_team_lead_can_start_own_session(self):
        session = self.created_and_started()
        self.assertEqual(session.status, SessionStatus.RUNNING)

    def test_team_lead_cannot_start_someone_elses_session(self):
        other = self.make_session(group=self.group, session_type=SessionType.TRAINING)
        response = self.api.post(f"/api/v1/teacher/sessions/{other.pk}/start/")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        other.refresh_from_db()
        self.assertEqual(other.status, SessionStatus.CREATED)

    def test_team_lead_sees_every_session(self):
        mine = self.created_and_started()
        theirs = self.make_session(group=self.other_group, session_type=SessionType.TRAINING)
        response = self.api.get("/api/v1/teacher/sessions/")
        ids = {row["id"] for row in response.data["results"]}
        self.assertTrue({str(mine.pk), str(theirs.pk)} <= ids)


class TeamLeadCannotTakeTests(TeamLeadSessionFixture):
    def test_team_lead_never_enters_the_student_test_flow(self):
        session = self.created_and_started()
        response = self.api.post(f"/api/v1/teacher/sessions/{session.pk}/take/")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(StudentAttempt.objects.filter(user=self.lead).exists())
        data = self.api.get(f"/api/v1/teacher/sessions/{session.pk}/participants/").data["session"]
        self.assertFalse(data["can_take"])
        self.assertTrue(self.taker.get(f"/api/v1/teacher/sessions/{session.pk}/participants/").data["session"]["can_take"])

    def test_join_url_is_the_real_student_entry_for_this_session(self):
        session = self.created_and_started()
        data = self.api.get(f"/api/v1/teacher/sessions/{session.pk}/participants/").data["session"]
        self.assertEqual(data["join_url"], f"http://testserver{reverse('testing_public_join')}?key={session.key}")
        page = self.client.get(urlparse(data["join_url"]).path, {"key": session.key})
        self.assertContains(page, session.test.title)
        # An id that is not a visible session is a 404 — changing the id gets nothing.
        self.assertEqual(self.api.get("/api/v1/teacher/sessions/00000000-0000-0000-0000-000000000000/participants/").status_code, 404)


class AdminTakesTestTests(TeamLeadSessionFixture):
    def take(self, session) -> dict:
        response = self.taker.post(f"/api/v1/teacher/sessions/{session.pk}/take/")
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.content)
        return response.data

    def test_full_flow_create_start_take_answer_submit_result(self):
        session = self.created_and_started()
        data = self.take(session)
        attempt = StudentAttempt.objects.get(pk=data["id"])
        # The attempt is the admin's own — not a roster student's.
        self.assertEqual(attempt.user, self.admin)
        self.assertIsNone(attempt.student)
        self.assertEqual(attempt.status, AttemptStatus.ACTIVE)
        self.assertEqual(len(attempt.question_ids), 4)

        # Same student test page (questions, Назад/Далее, timer, autosave).
        page = self.open_handoff(data["take_url"])
        self.assertRedirects(page, reverse("testing_public_take", args=[attempt.pk]))
        page = self.client.get(reverse("testing_public_take", args=[attempt.pk]))
        self.assertContains(page, "Вопрос 1 из 4")

        # Answer + submit through the existing grading.
        response = self.client.post(reverse("testing_public_take", args=[attempt.pk]), self.correct_post())
        self.assertRedirects(response, reverse("testing_public_result", args=[attempt.pk]))
        attempt.refresh_from_db()
        self.assertEqual(attempt.status, AttemptStatus.FINISHED)
        self.assertEqual(attempt.score, 80.0)

        # Own result, in the LMS.
        mine = self.taker.get("/api/v1/teacher/my-attempts/")
        self.assertEqual(mine.status_code, status.HTTP_200_OK)
        self.assertEqual(len(mine.data), 1)
        result = mine.data[0]
        self.assertEqual(result["status"], AttemptStatus.FINISHED)
        self.assertEqual(result["score"]["percent"], 80.0)
        self.assertEqual(result["score"]["earned"], 4)
        self.assertEqual(result["score"]["possible"], 5)
        self.assertEqual(result["score"]["correct"], 3)
        self.assertEqual(result["score"]["pending"], 1)  # the code answer waits for review
        self.assertTrue(result["result_url"])
        result_page = self.open_handoff(result["result_url"], web=self.client_class())
        self.assertEqual(result_page.status_code, 302)

    def test_reopening_returns_the_same_active_attempt(self):
        session = self.created_and_started()
        first = self.take(session)
        second = self.take(session)
        self.assertEqual(first["id"], second["id"])
        self.assertEqual(StudentAttempt.objects.filter(user=self.admin).count(), 1)

    def test_cannot_take_a_session_that_has_not_started(self):
        response = self.create_session()
        take = self.taker.post(f"/api/v1/teacher/sessions/{response.data['id']}/take/")
        self.assertEqual(take.status_code, status.HTTP_400_BAD_REQUEST)

    def test_staff_attempt_stays_out_of_student_statistics(self):
        session = self.created_and_started()
        data = self.take(session)
        self.open_handoff(data["take_url"])
        self.client.post(reverse("testing_public_take", args=[data["id"]]), self.correct_post())
        participants = self.api.get(f"/api/v1/teacher/sessions/{session.pk}/participants/")
        self.assertEqual(participants.data["session"]["counts"]["completed"], 0)
        self.assertEqual(participants.data["session"]["counts"]["total"], 2)
        self.assertEqual(analytics.finished_attempts_of(TestSession.objects.filter(pk=session.pk)).count(), 0)

    def test_team_lead_can_view_student_results(self):
        session = self.created_and_started()
        attempt = attempt_service.join(session, student=self.student)
        right = self.q_single.options.get(is_correct=True)
        attempt_service.submit(attempt, {str(self.q_single.pk): attempt_service.SubmittedAnswer(options=[str(right.pk)])}, timed_out=True)
        participants = self.api.get(f"/api/v1/teacher/sessions/{session.pk}/participants/")
        self.assertEqual(participants.status_code, status.HTTP_200_OK)
        row = next(p for p in participants.data["participants"] if p["student"]["id"] == self.student.pk)
        self.assertEqual(row["status"], "completed")
        self.assertTrue(row["result_available"])
        detail = self.api.get(f"/api/v1/teacher/sessions/{session.pk}/participants/{row['id']}/result/")
        self.assertEqual(detail.status_code, status.HTTP_200_OK)
        self.assertEqual(detail.data["questions"][0]["status"], "correct")


class AttemptOwnershipTests(TeamLeadSessionFixture):
    """A Team Lead can only ever reach their own attempt."""

    def test_cannot_submit_answers_to_another_users_attempt(self):
        session = self.created_and_started()
        student_attempt = attempt_service.join(session, student=self.student)
        # No handoff for it, nothing remembered in this browser → 404.
        response = self.client.post(reverse("testing_public_take", args=[student_attempt.pk]), self.correct_post())
        self.assertEqual(response.status_code, 404)
        student_attempt.refresh_from_db()
        self.assertEqual(student_attempt.status, AttemptStatus.ACTIVE)
        self.assertFalse(student_attempt.answers.exists())

    def test_a_token_opens_only_its_own_attempt(self):
        session = self.created_and_started()
        mine = self.taker.post(f"/api/v1/teacher/sessions/{session.pk}/take/").data
        student_attempt = attempt_service.join(session, student=self.student)
        token = urlparse(mine["take_url"]).query.split("t=", 1)[1]
        response = self.client.get(f"{reverse('testing_public_take', args=[student_attempt.pk])}?t={token}")
        self.assertEqual(response.status_code, 404)

    def test_a_student_attempt_can_never_be_handed_off(self):
        session = self.created_and_started()
        student_attempt = attempt_service.join(session, student=self.student)
        with self.assertRaises(ValueError):
            handoff.token_for(student_attempt)

    def test_forged_or_foreign_tokens_are_rejected(self):
        session = self.created_and_started()
        other_lead = User.objects.create_user(
            username="lead2", email="lead2@okurmen.kg", password=PASSWORD, first_name="L2", role=User.Role.TEAM_LEAD,
        )
        theirs = attempt_service.join(session, user=other_lead)
        response = self.client.get(f"{reverse('testing_public_take', args=[theirs.pk])}?t=forged")
        self.assertEqual(response.status_code, 404)
        # And the API lists only the caller's own attempts.
        self.taker.post(f"/api/v1/teacher/sessions/{session.pk}/take/")
        ids = {row["id"] for row in self.taker.get("/api/v1/teacher/my-attempts/").data}
        self.assertNotIn(str(theirs.pk), ids)


class TeamLeadStillReadOnlyTests(TeamLeadSessionFixture):
    def test_cannot_modify_or_delete_tests(self):
        self.assertEqual(self.api.patch(f"/api/v1/tests/{self.test.pk}/", {"title": "X"}, format="json").status_code, 403)
        self.assertEqual(self.api.delete(f"/api/v1/tests/{self.test.pk}/").status_code, 403)
        self.assertEqual(self.api.post("/api/v1/tests/", {"title": "New"}, format="json").status_code, 403)
        self.assertEqual(
            self.api.patch(f"/api/v1/tests/{self.test.pk}/questions/{self.q_single.pk}/", {"text": "X"}, format="json").status_code, 403
        )
        self.test.refresh_from_db()
        self.assertEqual(self.test.title, "Python Basics")

    def test_cannot_modify_or_delete_students(self):
        self.assertEqual(self.api.patch(f"/api/v1/students/{self.student.pk}/", {"first_name": "X"}, format="json").status_code, 403)
        self.assertEqual(self.api.delete(f"/api/v1/students/{self.student.pk}/").status_code, 403)

    def test_cannot_modify_or_delete_groups(self):
        self.assertEqual(self.api.patch(f"/api/v1/groups/{self.group.pk}/", {"name": "X"}, format="json").status_code, 403)
        self.assertEqual(self.api.delete(f"/api/v1/groups/{self.group.pk}/").status_code, 403)

    def test_cannot_modify_trainers(self):
        self.assertEqual(self.api.delete(f"/api/v1/trainers/{self.teacher.pk}/").status_code, 403)
        self.assertEqual(self.api.post("/api/v1/trainers/", {"username": "x"}, format="json").status_code, 403)

    def test_sessions_cannot_be_patched_or_deleted(self):
        session = self.created_and_started()
        self.assertEqual(self.api.patch(f"/api/v1/teacher/sessions/{session.pk}/", {"title": "X"}, format="json").status_code, 405)
        self.assertEqual(self.api.delete(f"/api/v1/teacher/sessions/{session.pk}/").status_code, 405)


class TrainerGetsNoNewRightsTests(TeamLeadSessionFixture):
    def setUp(self):
        super().setUp()
        self.trainer = APIClient()
        self.trainer.force_authenticate(self.teacher.user)

    def test_trainer_cannot_create_start_or_take(self):
        self.assertEqual(self.create_session(client=self.trainer).status_code, status.HTTP_403_FORBIDDEN)
        session = self.created_and_started()
        self.assertEqual(self.trainer.post(f"/api/v1/teacher/sessions/{session.pk}/start/").status_code, 403)
        self.assertEqual(self.trainer.post(f"/api/v1/teacher/sessions/{session.pk}/take/").status_code, 403)
        self.assertEqual(self.trainer.get("/api/v1/teacher/my-attempts/").status_code, 403)
        listing = self.trainer.get("/api/v1/teacher/sessions/")
        self.assertEqual(listing.status_code, 200)
        self.assertTrue(all(not row["can_start"] and not row["can_take"] for row in listing.data["results"]))

    def test_admin_still_can_everything_here(self):
        client = self.taker
        response = self.create_session(client=client)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(client.post(f"/api/v1/teacher/sessions/{response.data['id']}/start/").status_code, 200)


class TeamLeadResultPageTests(TeamLeadSessionFixture):
    def test_result_page_leads_back_to_the_lms_not_to_the_student_join(self):
        session = self.created_and_started()
        data = self.taker.post(f"/api/v1/teacher/sessions/{session.pk}/take/").data
        self.open_handoff(data["take_url"])
        self.client.post(reverse("testing_public_take", args=[data["id"]]), self.correct_post())
        page = self.client.get(reverse("testing_public_result", args=[data["id"]]))
        self.assertContains(page, "Вернуться в LMS")
        self.assertContains(page, f"/app/exams/{session.pk}")
        self.assertNotContains(page, "Пройти ещё раз")

    def test_an_unfinished_attempt_of_an_ended_session_shows_as_expired(self):
        session = self.created_and_started()
        self.taker.post(f"/api/v1/teacher/sessions/{session.pk}/take/")
        session.refresh_from_db()
        session.finish()
        rows = self.taker.get("/api/v1/teacher/my-attempts/").data
        self.assertEqual(rows[0]["status"], AttemptStatus.EXPIRED)


class SessionListGroupFilterTests(TeamLeadSessionFixture):
    def test_filter_by_group(self):
        mine = self.created_and_started()
        other = self.make_session(group=self.other_group, session_type=SessionType.TRAINING)
        ids = {row["id"] for row in self.api.get("/api/v1/teacher/sessions/", {"group": self.group.pk}).data["results"]}
        self.assertIn(str(mine.pk), ids)
        self.assertNotIn(str(other.pk), ids)
