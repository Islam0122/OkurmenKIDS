"""Monitoring API: who sees what (Teacher / Team Lead / Admin / anonymous),
filters, overview counters, attempt details with the event timeline and
violations, team analytics and difficult questions."""
from __future__ import annotations

from datetime import timedelta

from rest_framework.test import APIClient

from apps.academy.models import GroupTeacher, Student
from apps.testing.models import (
    Answer,
    AttemptStatus,
    ExamAttemptEvent,
    ExamEventType,
    FinishReason,
    GradingStatus,
    QuestionType,
    SessionType,
    StudentAttempt,
    TestSession,
    TestStatus,
)
from apps.testing.services import questions as svc
from apps.testing.services.question_rules import OptionData, QuestionData
from apps.testing.tests.base import TestingFixture, make_teacher
from apps.users.models import User


class MonitoringFixture(TestingFixture):
    def setUp(self):
        super().setUp()
        self.test.status = TestStatus.ACTIVE
        self.test.passing_score = 50
        self.test.save()
        self.q1 = svc.save_question(self.test, QuestionData(QuestionType.SINGLE_CHOICE, "A?", options=[OptionData("x", True), OptionData("y", False)]))
        self.q2 = svc.save_question(self.test, QuestionData(QuestionType.SINGLE_CHOICE, "B?", options=[OptionData("x", True), OptionData("y", False)]))
        GroupTeacher.objects.create(group=self.group, teacher=self.teacher, subject=self.subject)
        self.mine = TestSession.objects.create(test=self.test, group=self.group, session_type=SessionType.EXAM,
                                               duration=timedelta(hours=1), teacher=self.teacher, title="Mine")
        self.mine.start()
        self.other_teacher = make_teacher("tother")
        self.other = TestSession.objects.create(test=self.test, group=self.other_group, session_type=SessionType.TRAINING,
                                                teacher=self.other_teacher, title="Other")
        self.other.start()
        self.other_student = Student.objects.create(first_name="Bakyt", group=self.other_group)

        self.active = self.attempt(self.mine, self.student, status=AttemptStatus.ACTIVE, exam_mode=True, tab_switch_count=2, violation_count=3)
        ExamAttemptEvent.objects.create(attempt=self.active, event_type=ExamEventType.EXAM_STARTED)
        ExamAttemptEvent.objects.create(attempt=self.active, event_type=ExamEventType.TAB_SWITCH, metadata={"question": 1})
        ExamAttemptEvent.objects.create(attempt=self.active, event_type=ExamEventType.FULLSCREEN_EXIT)
        self.passed = self.attempt(self.mine, self.student, status=AttemptStatus.FINISHED, score=100.0)
        Answer.objects.create(attempt=self.passed, question=self.q1, selected_options=[], is_correct=True, grading_status=GradingStatus.AUTO)
        Answer.objects.create(attempt=self.passed, question=self.q2, selected_options=[], is_correct=False, grading_status=GradingStatus.AUTO)
        self.foreign = self.attempt(self.other, self.other_student, status=AttemptStatus.FINISHED, score=20.0)
        self.terminated = self.attempt(self.other, None, name="Anon", status=AttemptStatus.FINISHED, score=0.0,
                                       finish_reason=FinishReason.VIOLATIONS, violation_count=5)
        self.lead = User.objects.create_user(username="lead", email="lead@okurmen.kg", password="x", first_name="L",
                                             role=User.Role.TEAM_LEAD)
        self.api = APIClient()

    def attempt(self, session, student, name="", **fields):
        now = fields.pop("finished_at", None)
        attempt = StudentAttempt.objects.create(session=session, student=student, student_name=name or str(student),
                                                question_ids=[str(self.q1.pk), str(self.q2.pk)], **fields)
        if attempt.status == AttemptStatus.FINISHED:
            attempt.finished_at = now or attempt.started_at + timedelta(minutes=10)
            attempt.save(update_fields=["finished_at"])
        return attempt

    def get(self, user, url, **params):
        self.api.force_authenticate(user)
        return self.api.get(f"/api/v1/monitoring/{url}", params)


class AccessTests(MonitoringFixture):
    def test_anonymous_and_unknown_roles_have_no_access(self):
        self.api.force_authenticate(None)
        self.assertEqual(self.api.get("/api/v1/monitoring/overview/").status_code, 401)
        stranger = User.objects.create_user(username="x", email="x@okurmen.kg", password="x", first_name="X", role=User.Role.TEACHER)
        self.assertEqual(self.get(stranger, "attempts/").status_code, 403)

    def test_teacher_sees_only_own_groups(self):
        ids = {r["id"] for r in self.get(self.teacher.user, "attempts/").data["results"]}
        self.assertEqual(ids, {str(self.active.pk), str(self.passed.pk)})
        self.assertEqual(self.get(self.teacher.user, f"attempts/{self.foreign.pk}/").status_code, 404)
        self.assertEqual(self.get(self.teacher.user, f"groups/{self.other_group.pk}/").status_code, 404)
        self.assertEqual(self.get(self.teacher.user, f"trainers/{self.other.pk}/").status_code, 404)
        self.assertEqual(self.get(self.teacher.user, "teachers/").status_code, 403)
        options = self.get(self.teacher.user, "filters/").data
        self.assertEqual([g["name"] for g in options["groups"]], ["Group 12"])
        self.assertFalse(options["team_view"])

    def test_team_lead_sees_everything_read_only(self):
        ids = {r["id"] for r in self.get(self.lead, "attempts/").data["results"]}
        self.assertEqual(len(ids), 4)
        self.assertEqual(self.get(self.lead, f"attempts/{self.foreign.pk}/").status_code, 200)
        self.api.force_authenticate(self.lead)
        self.assertEqual(self.api.post("/api/v1/monitoring/overview/").status_code, 405)

    def test_staff_self_attempts_are_not_counted(self):
        self.attempt(self.mine, None, name="Lead", user=self.lead, status=AttemptStatus.FINISHED, score=100.0)
        self.assertEqual(self.get(self.lead, "attempts/").data["count"], 4)


class DataTests(MonitoringFixture):
    def test_rows_status_severity_and_progress(self):
        rows = {r["id"]: r for r in self.get(self.lead, "attempts/").data["results"]}
        active = rows[str(self.active.pk)]
        self.assertEqual((active["status"], active["severity"], active["fullscreen_exits"]), ("in_progress", "warning", 1))
        self.assertEqual(active["group"]["name"], "Group 12")
        self.assertEqual(active["question_total"], 2)
        self.assertIsNotNone(active["remaining_seconds"])
        self.assertEqual(rows[str(self.terminated.pk)]["status"], "terminated")
        self.assertEqual(rows[str(self.terminated.pk)]["severity"], "critical")
        self.assertEqual(rows[str(self.passed.pk)]["score"], 100)
        self.assertTrue(rows[str(self.passed.pk)]["passed"])

    def test_filters(self):
        def ids(**params):
            return {r["id"] for r in self.get(self.lead, "attempts/", **params).data["results"]}
        self.assertEqual(ids(status="in_progress"), {str(self.active.pk)})
        self.assertEqual(ids(status="terminated"), {str(self.terminated.pk)})
        self.assertEqual(ids(group=self.other_group.pk), {str(self.foreign.pk), str(self.terminated.pk)})
        self.assertEqual(ids(teacher=self.teacher.pk), {str(self.active.pk), str(self.passed.pk)})
        self.assertEqual(ids(mode="training"), {str(self.foreign.pk), str(self.terminated.pk)})
        self.assertEqual(ids(violations="1"), {str(self.active.pk), str(self.terminated.pk)})
        self.assertEqual(ids(q="bakyt"), {str(self.foreign.pk)})
        self.assertEqual(len(ids(group="nope", date_from="bad")), 4)  # malformed filters are ignored

    def test_overview(self):
        data = self.get(self.lead, "overview/").data
        self.assertEqual((data["active_students"], data["active_exams"], data["completed"]), (1, 1, 3))
        self.assertEqual((data["passed"], data["failed"], data["terminated"]), (1, 2, 1))
        self.assertEqual(data["violations"], 8)
        self.assertEqual(data["average_score"], 40)
        mine = self.get(self.teacher.user, "overview/").data
        self.assertEqual((mine["completed"], mine["violations"]), (1, 3))

    def test_attempt_detail_timeline_and_violations(self):
        data = self.get(self.teacher.user, f"attempts/{self.active.pk}/").data
        self.assertEqual([e["type"] for e in data["events"]], ["EXAM_STARTED", "TAB_SWITCH", "FULLSCREEN_EXIT"])
        self.assertEqual(data["events"][1]["question"], 1)
        self.assertEqual((data["violations"]["TAB_SWITCH"], data["violations"]["FULLSCREEN_EXIT"], data["violations"]["COPY_ATTEMPT"]), (1, 1, 0))
        self.assertEqual(len(data["questions"]), 2)

    def test_overdue_attempts_are_closed_by_monitoring(self):
        self.active.expires_at = self.active.started_at - timedelta(minutes=1)
        self.active.save(update_fields=["expires_at"])
        self.get(self.lead, "overview/")
        self.active.refresh_from_db()
        self.assertNotEqual(self.active.status, AttemptStatus.ACTIVE)

    def test_team_analytics(self):
        teachers = {r["teacher"]["name"]: r for r in self.get(self.lead, "teachers/").data}
        self.assertEqual(teachers["Tpython"]["completed"], 1)
        self.assertEqual(teachers["Tpython"]["pass_rate"], 100)
        self.assertEqual(teachers["Tother"]["pass_rate"], 0)
        groups = {r["group"]["name"]: r for r in self.get(self.lead, "groups/").data}
        self.assertEqual(groups["Group 13"]["violations"], 5)
        group = self.get(self.lead, f"groups/{self.other_group.pk}/").data
        self.assertIn("Bakyt", group["failed_students"])
        self.assertEqual(group["avg_duration_seconds"], 600)
        trainers = {r["session"]["title"]: r for r in self.get(self.lead, "trainers/").data}
        self.assertEqual(trainers["Mine"]["attempts"], 2)

    def test_difficult_questions(self):
        data = self.get(self.teacher.user, f"trainers/{self.mine.pk}/").data
        hardest = data["difficult_questions"][0]
        self.assertEqual((hardest["text"], hardest["correct_rate"], hardest["incorrect_rate"]), ("B?", 0, 100))
        self.assertEqual(self.get(self.teacher.user, "questions/", session=str(self.mine.pk)).status_code, 200)
