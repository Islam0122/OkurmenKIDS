"""Sessions as their own entity: schedule, phases, roster, live participant
state, the admin «Сессии» section and the teacher API (incl. permissions)."""
from __future__ import annotations

import datetime as dt
from unittest import mock

from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.academy.models import Group, GroupTeacher, Student
from apps.testing.forms import SessionForm
from apps.testing.models import (
    AttemptStatus,
    ParticipantStatus,
    QuestionType,
    SessionParticipant,
    SessionPhase,
    SessionStatus,
    StudentAttempt,
    TestSession,
    TestStatus,
)
from apps.testing.services import attempts
from apps.testing.services import questions as svc
from apps.testing.services.question_rules import OptionData, QuestionData
from apps.testing.tests.base import TestingFixture, make_teacher
from apps.users.models import User

NOW = timezone.make_aware(dt.datetime(2026, 10, 2, 13, 0))


def at(hour, minute=0):
    return timezone.make_aware(dt.datetime(2026, 10, 2, hour, minute))


class SessionFixture(TestingFixture):
    def setUp(self):
        super().setUp()
        self.test.status = TestStatus.ACTIVE
        self.test.time_limit_minutes = 40
        self.test.save()
        for i in range(3):
            svc.save_question(self.test, QuestionData(QuestionType.SINGLE_CHOICE, f"Q{i}", options=[
                OptionData("right", True), OptionData("wrong")]))
        self.student2 = Student.objects.create(first_name="Islam", last_name="D", group=self.group)
        self.outsider = Student.objects.create(first_name="Other", last_name="G", group=self.other_group)

    def create_session(self, **data):
        payload = {
            "title": "Python — Итоговый", "test": str(self.test.pk), "group": str(self.group.pk),
            "all_students": "on", "date": "2026-10-02", "start_time": "14:00", "end_time": "15:00",
            "max_attempts": "1", "session_type": "exam",
        }
        payload.update(data)
        form = SessionForm(payload)
        self.assertTrue(form.is_valid(), form.errors)
        with mock.patch("django.utils.timezone.now", return_value=NOW):
            return form.save(teacher=self.teacher)


class ScheduleAndPhaseTests(SessionFixture):
    def test_scheduled_session_starts_and_ends_by_itself(self):
        session = self.create_session()
        self.assertEqual((session.phase_at(NOW), session.status), (SessionPhase.SCHEDULED, SessionStatus.CREATED))
        self.assertEqual(session.duration, dt.timedelta(hours=1))

        with mock.patch("django.utils.timezone.now", return_value=at(14, 5)):
            session.sync_schedule()
            self.assertEqual(session.status, SessionStatus.RUNNING)
            self.assertEqual(session.expires_at, at(15))  # closes at the end time, not 15:05
            self.assertEqual(session.phase, SessionPhase.ACTIVE)
        with mock.patch("django.utils.timezone.now", return_value=at(15, 1)):
            self.assertEqual(session.phase, SessionPhase.FINISHED)

    def test_draft_without_date_and_cancel(self):
        session = self.create_session(date="", start_time="", end_time="")
        self.assertEqual(session.phase, SessionPhase.DRAFT)
        session.cancel()
        self.assertEqual((session.phase, session.is_active), (SessionPhase.CANCELLED, False))
        self.assertIn("отменена", attempts.session_error(session))

    def test_form_validation(self):
        base = {"test": str(self.test.pk), "group": str(self.group.pk), "all_students": "on", "date": "2026-10-02"}
        self.assertIn("end_time", SessionForm({**base, "start_time": "15:00", "end_time": "14:00"}).errors)
        self.assertIn("end_time", SessionForm({**base, "start_time": "08:00", "end_time": "21:00"}).errors)
        self.assertIn("start_time", SessionForm({**base, "end_time": "14:00"}).errors)
        self.assertIn("students", SessionForm({**base, "all_students": "", "start_time": "14:00", "end_time": "15:00"}).errors)
        draft = self.test.__class__.objects.create(title="Draft test")
        self.assertIn("test", SessionForm({**base, "test": str(draft.pk)}).errors)

    def test_roster_all_or_chosen_students(self):
        session = self.create_session()
        self.assertEqual(set(session.participants.values_list("student_id", flat=True)), {self.student.pk, self.student2.pk})
        session = self.create_session(all_students="", students=[str(self.student2.pk)], title="Only Islam")
        self.assertEqual(list(session.participants.values_list("student_id", flat=True)), [self.student2.pk])

    def test_scheduled_join_message(self):
        session = self.create_session()
        with mock.patch("django.utils.timezone.now", return_value=NOW):
            self.assertIn("начнётся 02.10.2026 в 14:00", attempts.session_error(session))


class ParticipationTests(SessionFixture):
    def setUp(self):
        super().setUp()
        self.session = self.create_session(date="", start_time="", end_time="")
        self.session.start()

    def answers_for(self, attempt):
        return {
            str(q.pk): attempts.SubmittedAnswer(options=[str(q.options.get(is_correct=True).pk)])
            for q in attempts.attempt_questions(attempt)
        }

    def test_only_roster_students_can_join(self):
        with self.assertRaises(attempts.AttemptError):
            attempts.join(self.session, student=self.outsider)
        with self.assertRaises(attempts.AttemptError):
            attempts.join(self.session, student_name="Random person")

    def test_lifecycle_started_progress_left_reconnected_completed(self):
        attempt = attempts.join(self.session, student=self.student)
        participant = SessionParticipant.objects.get(student=self.student)
        self.assertEqual((participant.live_status, participant.question_total), (ParticipantStatus.IN_PROGRESS, 3))

        from apps.testing.services.participants import attempt_progress
        attempt_progress(attempt, current=2, answered=1)
        participant.refresh_from_db()
        self.assertEqual((participant.current_question, participant.answered_count), (2, 1))

        attempt_progress(attempt, left=True)
        participant.refresh_from_db()
        self.assertEqual(participant.live_status, ParticipantStatus.DISCONNECTED)
        attempts.join(self.session, student=self.student)  # comes back
        participant.refresh_from_db()
        self.assertEqual(participant.live_status, ParticipantStatus.IN_PROGRESS)

        with mock.patch("django.utils.timezone.now", return_value=timezone.now() + dt.timedelta(minutes=2)):
            self.assertEqual(participant.live_status, ParticipantStatus.DISCONNECTED)  # heartbeat went silent

        attempts.submit(attempt, self.answers_for(attempt))
        participant.refresh_from_db()
        self.assertEqual((participant.live_status, participant.score), (ParticipantStatus.COMPLETED, 100.0))

    def test_paused_session_shows_paused_participants(self):
        attempts.join(self.session, student=self.student)
        self.session.pause()
        participant = SessionParticipant.objects.get(student=self.student)
        self.assertEqual(participant.live_status, ParticipantStatus.PAUSED)

    def test_session_overrides_time_and_attempts(self):
        self.session.time_limit_minutes = 5
        self.session.max_attempts_per_student = 2
        self.session.save()
        attempt = attempts.join(self.session, student=self.student)
        self.assertEqual(attempts.attempt_deadline(attempt), attempt.started_at + dt.timedelta(minutes=5))
        attempts.submit(attempt, self.answers_for(attempt))
        attempts.join(self.session, student=self.student)  # 2nd attempt allowed by the session
        self.assertEqual(StudentAttempt.objects.filter(student=self.student).count(), 2)

    def test_expired_attempt_marks_participant(self):
        attempt = attempts.join(self.session, student=self.student)
        later = timezone.now() + dt.timedelta(minutes=45)
        with mock.patch("django.utils.timezone.now", return_value=later):
            with self.assertRaises(attempts.AttemptError):
                attempts.submit(attempt, {})
        self.assertEqual(SessionParticipant.objects.get(student=self.student).status, ParticipantStatus.EXPIRED)

    def test_progress_endpoint_is_bound_to_the_students_browser(self):
        response = self.client.post(reverse("testing_public_join"), {"key": self.session.key, "student": self.student.pk, "start": "1"})
        attempt = StudentAttempt.objects.get()
        self.assertRedirects(response, reverse("testing_public_take", args=[attempt.pk]))
        url = reverse("testing_public_progress", args=[attempt.pk])
        self.assertEqual(self.client.post(url, {"current": "3", "answered": "2"}).status_code, 200)
        participant = SessionParticipant.objects.get(student=self.student)
        self.assertEqual((participant.current_question, participant.answered_count), (3, 2))
        self.client.post(url, {"left": "1"})
        participant.refresh_from_db()
        self.assertEqual(participant.live_status, ParticipantStatus.DISCONNECTED)
        stranger = self.client_class()
        self.assertEqual(stranger.post(url, {"current": "1"}).status_code, 404)
        self.assertEqual(self.client.get(url).status_code, 405)

    def test_join_page_lists_only_the_roster(self):
        session = self.create_session(all_students="", students=[str(self.student2.pk)], title="Only Islam", date="", start_time="", end_time="")
        session.start()
        page = self.client.get(reverse("testing_public_join"), {"key": session.key})
        self.assertContains(page, "Islam D")
        self.assertNotContains(page, str(self.student))


class AdminSessionsTests(SessionFixture):
    def setUp(self):
        super().setUp()
        self.admin = User.objects.create_superuser(username="root", email="root@okurmen.kg", password="x")
        self.client.force_login(self.admin)

    def test_teacher_staff_has_no_access(self):
        teacher_user = self.teacher.user
        teacher_user.is_staff = True
        teacher_user.save()
        self.client.force_login(teacher_user)
        self.assertIn(self.client.get(reverse("admin:testing_testsession_changelist")).status_code, (302, 403))

    def test_create_page_and_redirect_into_the_session(self):
        self.assertContains(self.client.get(reverse("admin:testing_testsession_add")), "Создание сессии")
        response = self.client.post(reverse("admin:testing_testsession_add"), {
            "title": "", "test": str(self.test.pk), "group": str(self.group.pk), "all_students": "on",
            "date": "2026-10-03", "start_time": "10:00", "end_time": "11:00", "max_attempts": "1", "session_type": "exam",
        })
        session = TestSession.objects.get()
        self.assertRedirects(response, reverse("admin:testing_testsession_change", args=[session.pk]))
        self.assertEqual(session.participants.count(), 2)

    def test_list_filters(self):
        live = self.create_session(date="", start_time="", end_time="", title="Live one")
        live.start()
        self.create_session(title="Planned", date="2026-10-05")
        url = reverse("admin:testing_testsession_changelist")
        titles = lambda **q: [r["title"] for r in self.client.get(url, q).context["rows"]]  # noqa: E731
        self.assertEqual(titles(status="active"), ["Live one"])
        self.assertEqual(titles(status="scheduled"), ["Planned"])
        self.assertEqual(titles(group=str(self.other_group.pk)), [])
        self.assertEqual(titles(created_from="2026-10-02", created_to="2026-10-02", sort="start"), ["Planned", "Live one"])
        self.assertEqual(titles(created_from="2026-10-03"), [])
        self.assertEqual(titles(type="training"), [])
        self.assertEqual(titles(subject="999"), [])
        self.assertEqual(sorted(titles(q="Live")), ["Live one"])
        self.assertEqual(titles(test="not-a-uuid"), titles())

    def test_session_tabs_actions_and_exports(self):
        session = self.create_session(date="", start_time="", end_time="")
        for name in ("participants", "questions", "analytics", "activity", "settings"):
            self.assertEqual(self.client.get(reverse(f"admin:testing_session_{name}", args=[session.pk])).status_code, 200)
        self.assertRedirects(
            self.client.get(reverse("admin:testing_session_results", args=[session.pk])),
            reverse("admin:testing_session_analytics", args=[session.pk]),
        )
        overview = self.client.get(reverse("admin:testing_testsession_change", args=[session.pk]))
        self.assertContains(overview, session.key)
        self.client.post(reverse("admin:testing_session_action", args=[session.pk, "start"]))
        session.refresh_from_db()
        self.assertEqual(session.status, SessionStatus.RUNNING)
        fragment = self.client.get(reverse("admin:testing_session_participants", args=[session.pk]), {"fragment": "1"})
        self.assertNotContains(fragment, "<html")
        self.assertContains(fragment, str(self.student))
        xlsx = self.client.get(reverse("admin:testing_session_export", args=[session.pk, "xlsx"]))
        self.assertEqual(xlsx["Content-Type"], "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        pdf = self.client.get(reverse("admin:testing_session_export", args=[session.pk, "pdf"]))
        self.assertTrue(pdf.content.startswith(b"%PDF"))
        self.client.post(reverse("admin:testing_session_action", args=[session.pk, "finish"]))
        session.refresh_from_db()
        self.assertEqual(session.phase, SessionPhase.FINISHED)

    def test_settings_edit_roster_and_override(self):
        session = self.create_session()
        response = self.client.post(reverse("admin:testing_session_settings", args=[session.pk]), {
            "title": "Renamed", "test": str(self.test.pk), "group": str(self.group.pk),
            "students": [str(self.student.pk)], "date": "2026-10-02", "start_time": "14:00", "end_time": "15:30",
            "max_attempts": "2", "session_type": "exam", "time_limit_minutes": "25",
        })
        self.assertEqual(response.status_code, 302)
        session.refresh_from_db()
        self.assertEqual((session.title, session.time_limit_minutes, session.max_attempts_per_student), ("Renamed", 25, 2))
        self.assertEqual(list(session.participants.values_list("student_id", flat=True)), [self.student.pk])

    def test_tests_section_no_longer_creates_sessions(self):
        page = self.client.get(reverse("admin:testing_test_publish", args=[self.test.pk]))
        self.assertNotContains(page, "Создать сессию</span>")
        self.assertContains(page, "Открыть в разделе «Сессии»")


class TeacherApiTests(SessionFixture):
    def setUp(self):
        super().setUp()
        GroupTeacher.objects.create(group=self.group, teacher=self.teacher, subject=self.subject)
        self.mine = self.create_session(date="", start_time="", end_time="", title="Mine")
        self.mine.start()
        self.other = TestSession.objects.create(test=self.test, group=self.other_group, session_type="training", title="Other")
        self.api = APIClient()
        self.api.force_authenticate(self.teacher.user)

    def test_teacher_sees_only_own_groups(self):
        titles = [s["title"] for s in self.api.get("/api/v1/teacher/sessions/").data["results"]]
        self.assertEqual(titles, ["Mine"])
        self.assertEqual(self.api.get(f"/api/v1/teacher/sessions/{self.other.pk}/").status_code, 404)
        self.assertEqual(self.api.get(f"/api/v1/teacher/sessions/{self.other.pk}/participants/").status_code, 404)
        other_teacher = make_teacher("tother")
        self.api.force_authenticate(other_teacher.user)
        self.assertEqual(self.api.get(f"/api/v1/teacher/sessions/{self.mine.pk}/").status_code, 404)
        self.api.force_authenticate(None)
        self.assertEqual(self.api.get("/api/v1/teacher/sessions/").status_code, 401)

    def test_admin_sees_all(self):
        self.api.force_authenticate(User.objects.create_superuser(username="root", email="r@okurmen.kg", password="x"))
        self.assertEqual(self.api.get("/api/v1/teacher/sessions/").data["count"], 2)

    def test_live_monitoring_shows_progress_not_answers(self):
        attempt = attempts.join(self.mine, student=self.student)
        data = self.api.get(f"/api/v1/teacher/sessions/{self.mine.pk}/participants/").data
        self.assertTrue(data["session"]["is_live"])
        self.assertEqual(data["session"]["counts"]["in_progress"], 1)
        me = next(p for p in data["participants"] if p["student"]["id"] == self.student.pk)
        self.assertEqual((me["status"], me["question_total"], me["score"]), ("in_progress", 3, None))
        self.assertNotIn("answers", me)
        result_url = f"/api/v1/teacher/sessions/{self.mine.pk}/participants/{me['id']}/result/"
        self.assertEqual(self.api.get(result_url).status_code, 404)  # not before finishing

        answers = {
            str(q.pk): attempts.SubmittedAnswer(options=[str(q.options.get(is_correct=True).pk)])
            for q in attempts.attempt_questions(attempt)
        }
        attempts.submit(attempt, answers)
        data = self.api.get(f"/api/v1/teacher/sessions/{self.mine.pk}/participants/").data
        me = next(p for p in data["participants"] if p["student"]["id"] == self.student.pk)
        self.assertEqual((me["status"], me["score"], me["result_available"]), ("completed", 100.0, True))
        result = self.api.get(result_url).data
        self.assertEqual([q["status"] for q in result["questions"]], ["correct"] * 3)

    def test_status_filters(self):
        self.assertEqual(self.api.get("/api/v1/teacher/sessions/", {"status": "live"}).data["count"], 1)
        self.assertEqual(self.api.get("/api/v1/teacher/sessions/", {"status": "finished"}).data["count"], 0)
        self.assertEqual(self.api.get("/api/v1/teacher/sessions/", {"today": "1"}).data["count"], 1)

    def test_attempt_status_constants(self):
        self.assertEqual(AttemptStatus.ACTIVE, "active")
        self.assertIsInstance(Group.objects.for_teacher(self.teacher).first(), Group)
