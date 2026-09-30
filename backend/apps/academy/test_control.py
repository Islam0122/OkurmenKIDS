"""Tests for Control (services.control, /api/v1/control/).

Absolute imports only — see the note at the top of apps/academy/tests.py.
"""
from __future__ import annotations

import datetime as dt

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient
from django.test import TestCase

from apps.academy.models import (
    Attendance,
    Course,
    Group,
    GroupTeacher,
    Homework,
    HomeworkResult,
    Lesson,
    Student,
)
from apps.academy.services.control import ControlQuery, ControlService
from apps.academy.services.reports import ReportFilters
from apps.users.models import Subject, Teacher, User

TODAY = dt.date(2026, 9, 30)
NOON = dt.time(12, 0)
SEPT = {"period": "custom", "start_date": "2026-09-01", "end_date": "2026-10-31"}
# API tests run against the real clock, so their lessons live safely in the past.
PAST = {"period": "custom", "start_date": "2025-03-01", "end_date": "2025-03-31"}


def make_teacher(username: str) -> Teacher:
    user = User.objects.create_user(
        username=username, email=f"{username}@okurmen.kg", password="Str0ngPassw0rd!",
        first_name=username.capitalize(), role=User.Role.TEACHER, is_verified=True,
    )
    return Teacher.objects.create(user=user)


class ControlTestBase(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser(
            username="admin", email="admin@okurmen.kg", password="Str0ngPassw0rd!", first_name="Admin"
        )
        self.python, _ = Subject.objects.get_or_create(name="Python")
        self.soft, _ = Subject.objects.get_or_create(name="Soft Skills")
        self.course = Course.objects.create(name="Prog", count_lesson=20)
        self.course.subjects.set([self.python, self.soft])

        self.aizhan = make_teacher("aizhan")
        self.almaz = make_teacher("almaz")

        self.g1 = Group.objects.create(name="Prog Soft 2", course=self.course, start_date=dt.date(2025, 1, 1))
        self.g2 = Group.objects.create(name="Next 3", course=self.course, start_date=dt.date(2025, 1, 1))
        self.gt1 = GroupTeacher.objects.create(group=self.g1, teacher=self.aizhan, subject=self.python)
        self.gt1_soft = GroupTeacher.objects.create(group=self.g1, teacher=self.aizhan, subject=self.soft)
        self.gt2 = GroupTeacher.objects.create(group=self.g2, teacher=self.almaz, subject=self.python)

        self.s1 = Student.objects.create(first_name="Сумая", last_name="Камалидинова", group=self.g1)
        self.s2 = Student.objects.create(first_name="Али", last_name="Азамат уулу", group=self.g1)
        self.s3 = Student.objects.create(first_name="Артём", last_name="Иванов", group=self.g2)

    _n = 0

    def lesson(self, gt, date, lesson_status=Lesson.Status.COMPLETED, **extra) -> Lesson:
        self._n += 1
        extra.setdefault("teacher", gt.teacher)
        extra.setdefault("start_time", dt.time(10))
        extra.setdefault("end_time", dt.time(11))
        return Lesson.objects.create(
            group=gt.group, group_teacher=gt, subject=gt.subject, lesson_number=self._n,
            date=date, status=lesson_status, **extra,
        )

    def fill(self, lesson, *, attendance=True, homework=True, grades=True, deadline=None):
        """Make `lesson` fully filled in (or leave the given parts out)."""
        students = list(lesson.group.students.filter(is_active=True))
        if attendance:
            for s in students:
                Attendance.objects.create(lesson=lesson, student=s, status=Attendance.Status.PRESENT)
        if homework:
            hw = Homework.objects.create(lesson=lesson, title="HW", deadline=deadline)
            if grades:
                for s in students:
                    HomeworkResult.objects.create(homework=hw, student=s, status=HomeworkResult.Status.CHECKED, score=8)
            return hw
        return None

    def build(self, *, status=None, restrict=None, **params):
        filters = ReportFilters.from_query({**SEPT, **params}, today=TODAY)
        service = ControlService(ControlQuery(filters=filters, status=status, now_time=NOON), restrict_teacher=restrict)
        return service.build()

    def row(self, data, teacher, group):
        for item in data["items"]:
            if item["teacher"] and item["teacher"]["id"] == teacher.id and item["group"]["id"] == group.id:
                return item
        self.fail(f"no row for {teacher} / {group}")


class ControlRulesTests(ControlTestBase):
    def test_fully_completed_lesson_is_ok(self):
        self.fill(self.lesson(self.gt1, dt.date(2026, 9, 28)))
        row = self.row(self.build(), self.aizhan, self.g1)
        self.assertEqual(row["status"], "ok")
        self.assertEqual(row["lessons"]["total"], 1)
        self.assertEqual(row["attendance"], {"completed": 1, "total": 1, "percent": 100.0, "level": "ok"})
        self.assertEqual(row["homework"]["completed"], 1)
        self.assertEqual(row["grades"]["completed"], 1)
        self.assertEqual(row["issues"], [])

    def test_missing_attendance_is_attention(self):
        self.fill(self.lesson(self.gt1, dt.date(2026, 9, 28)), attendance=False)
        row = self.row(self.build(), self.aizhan, self.g1)
        self.assertEqual(row["status"], "attention")
        self.assertEqual((row["attendance"]["completed"], row["attendance"]["total"]), (0, 1))
        self.assertEqual(row["homework"]["level"], "ok")

    def test_missing_homework_is_attention(self):
        self.fill(self.lesson(self.gt1, dt.date(2026, 9, 28)), homework=False)
        data = self.build()
        row = self.row(data, self.aizhan, self.g1)
        self.assertEqual(row["status"], "attention")
        self.assertEqual((row["homework"]["completed"], row["homework"]["total"]), (0, 1))
        # No homework means nothing to score — not a second, separate failure.
        self.assertEqual(row["grades"]["total"], 0)
        self.assertIn("ДЗ не выдано: 1 занятие", row["issues"])

    def test_unchecked_homework_is_attention(self):
        lesson = self.lesson(self.gt1, dt.date(2026, 9, 28))
        hw = self.fill(lesson, grades=False)
        HomeworkResult.objects.create(homework=hw, student=self.s1, status=HomeworkResult.Status.SUBMITTED, score=7)
        HomeworkResult.objects.create(homework=hw, student=self.s2, status=HomeworkResult.Status.CHECKED, score=9)
        row = self.row(self.build(), self.aizhan, self.g1)
        self.assertEqual(row["status"], "attention")
        self.assertEqual(row["homework"]["completed"], 0)
        self.assertEqual(row["grades"]["completed"], 1)

    def test_missing_grades_is_attention_and_lists_students(self):
        lesson = self.lesson(self.gt1, dt.date(2026, 9, 28))
        hw = self.fill(lesson, grades=False)
        HomeworkResult.objects.create(homework=hw, student=self.s2, status=HomeworkResult.Status.CHECKED, score=9)
        row = self.row(self.build(), self.aizhan, self.g1)
        self.assertEqual(row["status"], "attention")
        self.assertEqual((row["grades"]["completed"], row["grades"]["total"]), (0, 1))
        self.assertEqual(row["grades"]["students_missing"], 1)

        detail = ControlService(
            ControlQuery(filters=ReportFilters.from_query(SEPT, today=TODAY), now_time=NOON)
        ).build_detail(group_id=self.g1.id, teacher_id=self.aizhan.id)
        grades = detail["lessons"][0]["grades"]
        self.assertEqual((grades["given"], grades["total"], grades["missing"]), (1, 2, 1))
        self.assertEqual([s["name"] for s in grades["missing_students"]], ["Камалидинова Сумая"])

    def test_not_submitted_counts_as_graded(self):
        lesson = self.lesson(self.gt1, dt.date(2026, 9, 28))
        hw = self.fill(lesson, grades=False)
        HomeworkResult.objects.create(homework=hw, student=self.s1, status=HomeworkResult.Status.NOT_SUBMITTED)
        HomeworkResult.objects.create(homework=hw, student=self.s2, status=HomeworkResult.Status.CHECKED, score=9)
        self.assertEqual(self.row(self.build(), self.aizhan, self.g1)["status"], "ok")

    def test_several_missing_components_is_not_filled(self):
        self.lesson(self.gt1, dt.date(2026, 9, 28), Lesson.Status.SCHEDULED)
        row = self.row(self.build(), self.aizhan, self.g1)
        self.assertEqual(row["status"], "not_filled")
        self.assertEqual(row["lessons"]["not_closed"], 1)

    def test_small_gap_is_warning_level(self):
        for day in range(1, 9):
            lesson = self.lesson(self.gt1, dt.date(2026, 9, day))
            self.fill(lesson, attendance=day > 2)
        row = self.row(self.build(), self.aizhan, self.g1)
        self.assertEqual((row["attendance"]["completed"], row["attendance"]["total"]), (6, 8))
        self.assertEqual(row["attendance"]["level"], "warning")
        self.assertEqual(row["status"], "attention")

    def test_future_lesson_is_upcoming_not_unfilled(self):
        self.lesson(self.gt1, dt.date(2026, 10, 2), Lesson.Status.SCHEDULED)
        # Today's lesson whose slot hasn't ended yet is still upcoming.
        self.lesson(self.gt1, TODAY, Lesson.Status.SCHEDULED, start_time=dt.time(15), end_time=dt.time(16))
        data = self.build()
        row = self.row(data, self.aizhan, self.g1)
        self.assertEqual(row["status"], "upcoming")
        self.assertEqual(row["lessons"]["total"], 0)
        self.assertEqual(row["lessons"]["upcoming"], 2)
        self.assertEqual(data["summary"]["attention_count"], 0)

    def test_today_lesson_past_its_slot_is_due(self):
        self.lesson(self.gt1, TODAY, Lesson.Status.SCHEDULED)  # 10:00–11:00, now is 12:00
        row = self.row(self.build(), self.aizhan, self.g1)
        self.assertEqual(row["lessons"]["total"], 1)
        self.assertEqual(row["status"], "not_filled")

    def test_homework_before_deadline_is_waiting(self):
        lesson = self.lesson(self.gt1, dt.date(2026, 9, 28))
        self.fill(lesson, grades=False, deadline=dt.date(2026, 10, 3))
        row = self.row(self.build(), self.aizhan, self.g1)
        self.assertEqual(row["status"], "ok")
        self.assertEqual((row["homework"]["total"], row["grades"]["total"]), (0, 0))

    def test_cancelled_and_not_required(self):
        self.lesson(self.gt1, dt.date(2026, 9, 21), Lesson.Status.CANCELLED)
        lesson = self.lesson(self.gt1, dt.date(2026, 9, 28), homework_not_required=True)
        self.fill(lesson, homework=False)
        row = self.row(self.build(), self.aizhan, self.g1)
        self.assertEqual(row["status"], "ok")
        self.assertEqual(row["lessons"]["cancelled"], 1)
        self.assertEqual(row["homework"]["total"], 0)

    def test_no_lessons_is_no_data(self):
        data = self.build()
        self.assertEqual(data["items"], [])
        self.assertEqual(data["summary"]["total_lessons"], 0)
        self.assertIsNone(data["summary"]["attendance_completion"])
        self.lesson(self.gt1, dt.date(2026, 9, 21), Lesson.Status.CANCELLED)
        self.assertEqual(self.row(self.build(), self.aizhan, self.g1)["status"], "no_data")

    def test_group_without_students(self):
        empty = Group.objects.create(name="Empty", course=self.course, start_date=dt.date(2025, 1, 1))
        gt = GroupTeacher.objects.create(group=empty, teacher=self.aizhan, subject=self.python)
        lesson = self.lesson(gt, dt.date(2026, 9, 28))
        Homework.objects.create(lesson=lesson, title="HW")
        row = self.row(self.build(), self.aizhan, empty)
        self.assertEqual(row["status"], "ok")
        self.assertEqual((row["attendance"]["total"], row["grades"]["total"]), (0, 0))

    def test_inactive_student_not_required(self):
        lesson = self.lesson(self.gt1, dt.date(2026, 9, 28))
        self.fill(lesson)
        Student.objects.create(first_name="Дана", group=self.g1, is_active=False, status=Student.Status.WITHDRAWN)
        row = self.row(self.build(), self.aizhan, self.g1)
        self.assertEqual(row["status"], "ok")
        self.assertEqual(row["grades"]["students_missing"], 0)

    def test_substitute_teacher_is_responsible(self):
        lesson = self.lesson(self.gt1, dt.date(2026, 9, 28), teacher=self.almaz)
        data = self.build()
        row = self.row(data, self.almaz, self.g1)
        self.assertEqual(row["lessons"]["total"], 1)
        self.assertFalse(any(i["teacher"]["id"] == self.aizhan.id for i in data["items"]))
        detail = ControlService(
            ControlQuery(filters=ReportFilters.from_query(SEPT, today=TODAY), now_time=NOON)
        ).build_detail(group_id=self.g1.id, teacher_id=self.almaz.id)
        self.assertEqual(detail["lessons"][0]["id"], lesson.id)
        self.assertEqual(detail["lessons"][0]["planned_teacher"]["id"], self.aizhan.id)

    def test_multiple_groups_and_trainers(self):
        g3 = Group.objects.create(name="Next 2", course=self.course, start_date=dt.date(2025, 1, 1))
        gt3 = GroupTeacher.objects.create(group=g3, teacher=self.aizhan, subject=self.python)
        Student.objects.create(first_name="Нурсултан", group=g3)
        self.fill(self.lesson(self.gt1, dt.date(2026, 9, 28)))
        self.fill(self.lesson(gt3, dt.date(2026, 9, 28)), attendance=False)
        self.lesson(self.gt2, dt.date(2026, 9, 28), Lesson.Status.SCHEDULED)

        data = self.build()
        self.assertEqual(len(data["items"]), 3)
        self.assertEqual(self.row(data, self.aizhan, self.g1)["status"], "ok")
        self.assertEqual(self.row(data, self.aizhan, g3)["status"], "attention")
        self.assertEqual(self.row(data, self.almaz, self.g2)["status"], "not_filled")
        # Problems first.
        self.assertEqual([i["status"] for i in data["items"]], ["not_filled", "attention", "ok"])
        summary = data["summary"]
        self.assertEqual((summary["total_lessons"], summary["completed_lessons"], summary["not_closed_lessons"]), (3, 2, 1))
        self.assertEqual(summary["attention_count"], 2)
        self.assertEqual(summary["attendance_completion"], 33.3)

    def test_filters(self):
        self.fill(self.lesson(self.gt1, dt.date(2026, 9, 28)))
        self.fill(self.lesson(self.gt1_soft, dt.date(2026, 9, 29)), attendance=False)
        self.lesson(self.gt2, dt.date(2026, 9, 28), Lesson.Status.SCHEDULED)
        self.lesson(self.gt2, dt.date(2026, 8, 28), Lesson.Status.SCHEDULED)  # outside the period

        self.assertEqual(len(self.build()["items"]), 2)
        only_almaz = self.build(teacher=str(self.almaz.id))
        self.assertEqual([i["teacher"]["id"] for i in only_almaz["items"]], [self.almaz.id])
        self.assertEqual(only_almaz["items"][0]["lessons"]["total"], 1)
        self.assertEqual([i["group"]["id"] for i in self.build(group=str(self.g1.id))["items"]], [self.g1.id])
        soft = self.build(subject=str(self.soft.id))
        self.assertEqual(soft["items"][0]["lessons"]["total"], 1)
        self.assertEqual(soft["items"][0]["status"], "attention")
        by_status = self.build(status="not_filled")
        self.assertEqual([i["teacher"]["id"] for i in by_status["items"]], [self.almaz.id])
        # The summary still describes the whole scope, not just the filtered rows.
        self.assertEqual(by_status["summary"]["total_lessons"], 3)
        self.assertEqual(self.build(period="custom", start_date="2026-08-01", end_date="2026-08-31")["summary"]["total_lessons"], 1)


class ControlApiTests(ControlTestBase):
    def setUp(self):
        super().setUp()
        self.client = APIClient()
        self.l1 = self.lesson(self.gt1, dt.date(2025, 3, 10))
        self.fill(self.l1, attendance=False)
        self.l2 = self.lesson(self.gt2, dt.date(2025, 3, 11))
        self.fill(self.l2)

    def get(self, name, user, params=None, **kwargs):
        self.client.force_authenticate(user)
        return self.client.get(reverse(name, kwargs=kwargs or None), params or {})

    def test_requires_authentication(self):
        self.assertEqual(self.client.get(reverse("control-overview")).status_code, status.HTTP_401_UNAUTHORIZED)

    def test_admin_sees_everything(self):
        response = self.get("control-overview", self.admin, PAST)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data["items"]), 2)
        self.assertEqual(response.data["summary"]["total_lessons"], 2)
        self.assertEqual(len(response.data["options"]["teachers"]), 2)

    def test_trainer_sees_only_own_lessons(self):
        response = self.get("control-overview", self.aizhan.user, {**PAST, "teacher": self.almaz.id})
        self.assertEqual(response.status_code, 200)
        self.assertEqual([i["teacher"]["id"] for i in response.data["items"]], [self.aizhan.id])
        self.assertEqual([t["id"] for t in response.data["options"]["teachers"]], [self.aizhan.id])

    def test_account_without_role_is_forbidden(self):
        user = User.objects.create_user(username="nobody", email="n@okurmen.kg", password="x", first_name="N")
        self.assertEqual(self.get("control-overview", user, PAST).status_code, status.HTTP_403_FORBIDDEN)

    def test_detail(self):
        params = {**PAST, "group": self.g1.id, "teacher": self.aizhan.id}
        response = self.get("control-detail", self.admin, params)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["row"]["status"], "attention")
        lesson = response.data["lessons"][0]
        self.assertEqual(lesson["id"], self.l1.id)
        self.assertEqual(lesson["attendance"]["marked"], 0)
        self.assertEqual(len(lesson["attendance"]["missing_students"]), 2)
        self.assertIn("Посещаемость не отмечена", lesson["problems"])
        # A trainer can't open a colleague's row — they always get their own.
        other = self.get("control-detail", self.almaz.user, params)
        self.assertEqual(other.status_code, 404)

    def test_lesson_check_and_scoping(self):
        response = self.get("control-lesson", self.admin, pk=self.l1.id)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["teacher"]["id"], self.aizhan.id)
        self.assertEqual(response.data["status"], "attention")
        self.assertEqual(self.get("control-lesson", self.aizhan.user, pk=self.l1.id).status_code, 200)
        self.assertEqual(self.get("control-lesson", self.almaz.user, pk=self.l1.id).status_code, 404)

    def test_invalid_params(self):
        self.assertEqual(self.get("control-overview", self.admin, {"status": "bogus"}).status_code, 400)
        self.assertEqual(self.get("control-overview", self.admin, {"period": "custom"}).status_code, 400)
        self.assertEqual(self.get("control-detail", self.admin, PAST).status_code, 400)
