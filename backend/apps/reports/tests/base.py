"""Shared fixture: a group with two students, a trainer and lessons in October.

Absolute imports only — see the note at the top of apps/academy/tests.py.
"""
from __future__ import annotations

import datetime as dt
import functools

from django.test import TestCase
from django.utils import timezone

from apps.academy.models import Attendance, Course, Group, GroupTeacher, Homework, HomeworkResult, Lesson, Student
from apps.reports.services import analytics, periods
from apps.testing.models import AttemptStatus, StudentAttempt, Test, TestSession
from apps.users.models import Subject, Teacher, User

PASSWORD = "Str0ngPassw0rd!"
TODAY = dt.date(2026, 11, 5)  # «last_month» = October 2026, compared with September


def make_user(username, role, **extra):
    return User.objects.create_user(
        username=username, email=f"{username}@okurmen.kg", password=PASSWORD,
        first_name=username.capitalize(), role=role, is_verified=True, **extra,
    )


@functools.lru_cache(maxsize=1)
def chromium_available() -> bool:
    """Image tests run only where a headless Chromium can actually start."""
    try:
        from apps.reports.services.image_generator import ImageGenerationError, render_html_pages

        render_html_pages('<html><body><section class="page" style="width:10px;height:10px"></section></body></html>')
        return True
    except (ImportError, ImageGenerationError, Exception):  # noqa: BLE001 - any launch failure means «no browser»
        return False


class ReportFixture(TestCase):
    def setUp(self):
        self.python, _ = Subject.objects.get_or_create(name="Python")
        self.course = Course.objects.create(name="Python для детей", count_lesson=30)
        self.course.subjects.set([self.python])
        self.trainer = Teacher.objects.create(user=make_user("trainer", User.Role.TEACHER))
        self.group = Group.objects.create(
            name="PY-01", course=self.course, teacher=self.trainer, start_date=dt.date(2026, 8, 1),
        )
        self.program = GroupTeacher.objects.create(group=self.group, teacher=self.trainer, subject=self.python)
        self.anna = self.student("Анна", "Алиева")
        self.bek = self.student("Бек", "Бекова")
        self.number = 0

    def student(self, first, last, group=None, enrolled=dt.date(2026, 8, 1)):
        return Student.objects.create(first_name=first, last_name=last, group=group or self.group, enrollment_date=enrolled)

    def lesson(self, day, status=Lesson.Status.COMPLETED, group=None, teacher=None, program=None):
        self.number += 1
        return Lesson.objects.create(
            group=group or self.group, group_teacher=program or (self.program if group is None else None),
            teacher=teacher or self.trainer, subject=self.python, lesson_number=self.number, date=day,
            start_time=dt.time(10), end_time=dt.time(11), status=status, topic=f"Тема {self.number}",
        )

    def mark(self, lesson, student, status):
        return Attendance.objects.create(lesson=lesson, student=student, status=status)

    def homework(self, lesson, results: dict):
        homework = Homework.objects.create(lesson=lesson, title=f"ДЗ {lesson.lesson_number}")
        for student, (status, score) in results.items():
            HomeworkResult.objects.create(homework=homework, student=student, status=status, score=score)
        return homework

    def attempt(self, student, score, day, *, group=None):
        test = getattr(self, "_test", None) or Test.objects.create(title="Python Basics", passing_score=60)
        self._test = test
        session = TestSession.objects.create(test=test, group=group or self.group, teacher=self.trainer)
        attempt = StudentAttempt.objects.create(
            session=session, student=student, group=group or self.group, teacher=self.trainer,
            student_name=str(student), test_title=test.title,
        )
        StudentAttempt.objects.filter(pk=attempt.pk).update(
            status=AttemptStatus.FINISHED, score=score,
            finished_at=timezone.make_aware(dt.datetime.combine(day, dt.time(12))),
        )
        return attempt

    def period(self, key="last_month", **dates):
        return periods.resolve(key, today=TODAY, **dates)

    def data(self, key="last_month", teacher_id=None, **dates):
        return analytics.build_report_data(self.group, self.period(key, **dates), teacher_id=teacher_id, today=TODAY)

    @staticmethod
    def entry(data, student):
        return next(row for row in data["students"] if row["id"] == student.pk)


class OctoberFixture(ReportFixture):
    """Three conducted October lessons + one cancelled + one still open, and September data for comparison."""

    def setUp(self):
        super().setUp()
        self.l1 = self.lesson(dt.date(2026, 10, 5))
        self.l2 = self.lesson(dt.date(2026, 10, 8))
        self.l3 = self.lesson(dt.date(2026, 10, 12))
        self.cancelled = self.lesson(dt.date(2026, 10, 15), status=Lesson.Status.CANCELLED)
        self.open_past = self.lesson(dt.date(2026, 10, 19), status=Lesson.Status.SCHEDULED)
        for lesson, anna, bek in ((self.l1, "present", "absent"), (self.l2, "late", "excused"), (self.l3, "present", "present")):
            self.mark(lesson, self.anna, anna)
            self.mark(lesson, self.bek, bek)
        self.homework(self.l1, {self.anna: ("checked", 9), self.bek: ("not_submitted", None)})
        self.homework(self.l2, {self.anna: ("submitted", None), self.bek: ("late", 6)})
        # l3: no homework planned — nothing to fail.

        # September: Anna attended 1 of 2, Bek 2 of 2.
        self.s1 = self.lesson(dt.date(2026, 9, 7))
        self.s2 = self.lesson(dt.date(2026, 9, 9))
        self.mark(self.s1, self.anna, "present")
        self.mark(self.s2, self.anna, "absent")
        self.mark(self.s1, self.bek, "present")
        self.mark(self.s2, self.bek, "present")
        self.homework(self.s1, {self.anna: ("checked", 7), self.bek: ("checked", 8)})
