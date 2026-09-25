"""Shared fixture for the scholarship tests.

Absolute imports only — see the note at the top of apps/academy/tests.py
(full test discovery imports modules under the `backend.` prefix too).
"""
from __future__ import annotations

import datetime as dt
import itertools
from decimal import Decimal

from django.test import TestCase

from apps.academy.models import Attendance, Course, Group, Homework, HomeworkResult, Lesson, Student
from apps.scholarships.models import ScholarshipConfiguration, TrainerFeedback
from apps.scholarships.services.generation import generate_period, recalculate_period
from apps.users.models import Subject, Teacher, User

SEP_1 = dt.date(2026, 9, 1)
OCT_1 = dt.date(2026, 10, 1)
_counter = itertools.count(1)


def make_user(username: str, role=User.Role.TEACHER) -> User:
    return User.objects.create_user(
        username=username,
        email=f"{username}@okurmen.kg",
        password="Str0ngPassw0rd!",
        first_name=username.capitalize(),
        role=role,
        is_verified=True,
    )


def make_teacher(username: str) -> Teacher:
    return Teacher.objects.create(user=make_user(username))


def make_admin(username: str = "admin") -> User:
    return User.objects.create_superuser(
        username=username, email=f"{username}@okurmen.kg", password="Str0ngPassw0rd!", first_name="Admin",
    )


class ScholarshipFixture(TestCase):
    def setUp(self):
        self.admin = make_admin()
        self.python = Subject.objects.get_or_create(name="Python")[0]
        self.cyber = Subject.objects.get_or_create(name="CyberSecurity")[0]
        self.english = Subject.objects.get_or_create(name="English")[0]
        self.t_python = make_teacher("tpython")
        self.t_cyber = make_teacher("tcyber")
        self.t_english = make_teacher("tenglish")
        self.course = Course.objects.create(name="Prog SOFT", count_lesson=48)
        self.course.subjects.set([self.python, self.cyber, self.english])
        self.group = Group.objects.create(name="Prog SOFT 1", course=self.course, start_date=dt.date(2026, 1, 10))
        self.other_group = Group.objects.create(name="Prog SOFT 2", course=self.course, start_date=dt.date(2026, 1, 10))
        self.config = ScholarshipConfiguration.objects.active()
        self.assertIsNotNone(self.config, "the 0002 data migration creates the default configuration")

    # -- builders ------------------------------------------------------------

    def configure(self, **fields):
        for key, value in fields.items():
            setattr(self.config, key, value)
        self.config.full_clean()
        self.config.save()

    def student(self, first_name="Islam", *, enrolled=dt.date(2026, 8, 1), group=None, **extra) -> Student:
        return Student.objects.create(
            first_name=first_name, last_name=extra.pop("last_name", "Test"), group=group or self.group,
            enrollment_date=enrolled, **extra,
        )

    def lesson(self, subject, teacher, date, *, group=None, status=Lesson.Status.COMPLETED, homework_not_required=False) -> Lesson:
        return Lesson.objects.create(
            group=group or self.group, teacher=teacher, subject=subject, lesson_number=next(_counter),
            date=date, start_time=dt.time(10), end_time=dt.time(11), status=status,
            homework_not_required=homework_not_required,
        )

    def attend(self, student, lesson, status=Attendance.Status.PRESENT) -> Attendance:
        return Attendance.objects.create(student=student, lesson=lesson, status=status)

    def homework(self, lesson) -> Homework:
        return Homework.objects.create(lesson=lesson, title=f"HW {lesson.lesson_number}")

    def hw_result(self, homework, student, status=HomeworkResult.Status.CHECKED) -> HomeworkResult:
        return HomeworkResult.objects.create(homework=homework, student=student, status=status)

    def feedback(self, period, student, subject, teacher, scores=(5, 5, 5, 5)) -> TrainerFeedback:
        progress, participation, discipline, understanding = scores
        return TrainerFeedback.objects.create(
            period=period, student=student, subject=subject, teacher=teacher, progress=progress,
            participation=participation, discipline=discipline, understanding=understanding,
        )

    def study(self, student, subject, teacher, *, attended=4, missed=0, homework_done=None, homework_total=0, group=None):
        """`attended`+`missed` lessons in September, the first `homework_total`
        of them with homework, `homework_done` of which are checked."""
        homework_done = homework_total if homework_done is None else homework_done
        lessons = []
        for index in range(attended + missed):
            lesson = self.lesson(subject, teacher, SEP_1 + dt.timedelta(days=index), group=group)
            status = Attendance.Status.PRESENT if index < attended else Attendance.Status.ABSENT
            self.attend(student, lesson, status)
            if index < homework_total:
                hw = self.homework(lesson)
                result = HomeworkResult.Status.CHECKED if index < homework_done else HomeworkResult.Status.NOT_SUBMITTED
                self.hw_result(hw, student, result)
            lessons.append(lesson)
        return lessons

    # -- actions -------------------------------------------------------------

    def generate(self, award_date=OCT_1, award_day=1, **kwargs):
        kwargs.setdefault("today", award_date)
        return generate_period(award_date, award_day, **kwargs).period

    def generate_with_feedback(self, feedback_rows, **kwargs):
        """Generate, add feedback [(student, subject, teacher, scores)], recalculate."""
        period = self.generate(**kwargs)
        for student, subject, teacher, scores in feedback_rows:
            self.feedback(period, student, subject, teacher, scores)
        return recalculate_period(period)

    def evaluation(self, period, student):
        return period.evaluations.get(student=student)


D = Decimal
