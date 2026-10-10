"""A lesson without homework has no homework step for its trainer: no
checklist line, no «ДЗ не требуется», and completion needs attendance only.
A lesson with homework (added, or declared by its plan) is exactly as
before.

Absolute imports only — see the note at the top of apps/academy/tests.py.
"""
from __future__ import annotations

import datetime as dt

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.academy.models import (
    Attendance, Course, CourseLessonPlan, Group, GroupTeacher, GroupTeacherLessonPlan, Homework, Lesson, Student,
)
from apps.academy.services import lesson_lifecycle
from apps.users.models import Subject, Teacher, User


class HomeworkOptionalTests(TestCase):
    def setUp(self):
        self.python, _ = Subject.objects.get_or_create(name="Python")
        self.course = Course.objects.create(name="Prog", count_lesson=10)
        self.course.subjects.set([self.python])
        user = User.objects.create_user(username="t", email="t@okurmen.kg", password="x", role=User.Role.TEACHER, is_verified=True)
        self.teacher = Teacher.objects.create(user=user)
        self.group = Group.objects.create(name="PRO-01", course=self.course, start_date=timezone.localdate() - dt.timedelta(days=10))
        self.program = GroupTeacher.objects.create(group=self.group, teacher=self.teacher, subject=self.python)
        self.student = Student.objects.create(first_name="A", last_name="B", group=self.group)
        self.api = APIClient()
        self.api.force_authenticate(user)

    def lesson(self, *, plan_homework: str = "", individual_homework: str | None = None, number=1):
        plan = CourseLessonPlan.objects.create(course=self.course, subject=self.python, lesson_number=number, topic="Тема",
                                               homework_title=plan_homework)
        individual = None
        if individual_homework is not None:
            individual = GroupTeacherLessonPlan.objects.create(group_teacher=self.program, lesson_number=number,
                                                               topic="Тема", homework_title=individual_homework)
        return Lesson.objects.create(
            group=self.group, group_teacher=self.program, teacher=self.teacher, subject=self.python, plan=plan,
            individual_plan=individual, lesson_number=number, date=timezone.localdate(),
            start_time=dt.time(10), end_time=dt.time(11), status=Lesson.Status.IN_PROGRESS,
        )

    def detail(self, lesson):
        return self.api.get(f"/api/v1/lessons/{lesson.pk}/").data

    def mark_attendance(self, lesson):
        Attendance.objects.create(student=self.student, lesson=lesson, status=Attendance.Status.PRESENT)

    # -- no homework ------------------------------------------------------

    def test_lesson_without_homework_completes_after_attendance(self):
        lesson = self.lesson()
        data = self.detail(lesson)
        self.assertFalse(data["homework_expected"])
        self.assertEqual([r["key"] for r in data["completion_requirements"]], ["attendance"])
        self.assertEqual(data["completion_progress"]["total"], 1)
        self.assertFalse(data["can_complete"])  # attendance is still required

        self.mark_attendance(lesson)
        self.assertTrue(self.detail(lesson)["can_complete"])
        response = self.api.post(f"/api/v1/lessons/{lesson.pk}/complete/")
        self.assertEqual(response.status_code, 200, response.data)
        lesson.refresh_from_db()
        self.assertEqual(lesson.status, Lesson.Status.COMPLETED)
        self.assertFalse(lesson.homework_not_required)  # nothing was marked

    def test_no_homework_still_needs_attendance(self):
        lesson = self.lesson()
        response = self.api.post(f"/api/v1/lessons/{lesson.pk}/complete/")
        self.assertEqual(response.status_code, 400)

    def test_individual_plan_without_homework_wins_over_the_course_plan(self):
        lesson = self.lesson(plan_homework="Курсовое ДЗ", individual_homework="")
        self.assertFalse(lesson_lifecycle.homework_expected(lesson))

    # -- homework exists / declared: unchanged ------------------------------

    def test_lesson_with_homework_works_as_before(self):
        lesson = self.lesson(plan_homework="Задачи 1–5")
        Homework.objects.create(lesson=lesson, title="Задачи 1–5")
        self.mark_attendance(lesson)
        data = self.detail(lesson)
        self.assertTrue(data["homework_expected"])
        self.assertTrue(data["homework_added"])
        self.assertEqual([r["key"] for r in data["completion_requirements"]], ["attendance", "homework"])
        self.assertTrue(data["can_complete"])

    def test_declared_but_missing_homework_still_blocks_completion(self):
        lesson = self.lesson(plan_homework="Задачи 1–5")
        self.mark_attendance(lesson)
        data = self.detail(lesson)
        self.assertTrue(data["homework_expected"])
        self.assertFalse(data["homework_added"])
        self.assertFalse(data["can_complete"])
        self.assertEqual(self.api.post(f"/api/v1/lessons/{lesson.pk}/complete/").status_code, 400)
        # …and «ДЗ не требуется» still unblocks it, as before.
        self.assertEqual(self.api.post(f"/api/v1/lessons/{lesson.pk}/homework-not-required/", {"value": True}, format="json").status_code, 200)
        self.assertEqual(self.api.post(f"/api/v1/lessons/{lesson.pk}/complete/").status_code, 200)

    def test_homework_added_by_hand_to_a_plan_without_homework_counts(self):
        lesson = self.lesson()
        Homework.objects.create(lesson=lesson, title="Дополнительное")
        self.assertTrue(self.detail(lesson)["homework_expected"])
