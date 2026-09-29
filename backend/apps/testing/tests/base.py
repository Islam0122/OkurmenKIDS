"""Shared fixture for the Testing module tests.

Absolute imports only — see the note at the top of apps/academy/tests.py
(full test discovery imports modules under the `backend.` prefix too).
"""
from __future__ import annotations

import datetime as dt

from django.test import TestCase

from apps.academy.models import Course, Group, Lesson, Student
from apps.testing.models import Test, TestSession
from apps.users.models import Subject, Teacher, User


def make_teacher(username: str) -> Teacher:
    user = User.objects.create_user(
        username=username,
        email=f"{username}@okurmen.kg",
        password="Str0ngPassw0rd!",
        first_name=username.capitalize(),
        role=User.Role.TEACHER,
        is_verified=True,
    )
    return Teacher.objects.create(user=user)


class TestingFixture(TestCase):
    def setUp(self):
        self.subject = Subject.objects.get_or_create(name="Python")[0]
        self.teacher = make_teacher("tpython")
        self.course = Course.objects.create(name="Python Beginner", count_lesson=12)
        self.course.subjects.set([self.subject])
        self.group = Group.objects.create(name="Group 12", course=self.course, start_date=dt.date(2026, 9, 1))
        self.other_group = Group.objects.create(name="Group 13", course=self.course, start_date=dt.date(2026, 9, 1))
        self.lesson = self.make_lesson(self.group)
        self.student = Student.objects.create(first_name="Aibek", last_name="Asanov", group=self.group)
        self.test = Test.objects.create(title="Python Basics")

    def make_lesson(self, group, number=1) -> Lesson:
        return Lesson.objects.create(
            group=group, teacher=self.teacher, subject=self.subject, lesson_number=number,
            date=dt.date(2026, 9, 2), start_time=dt.time(10), end_time=dt.time(11),
        )

    def make_session(self, **fields) -> TestSession:
        fields.setdefault("test", self.test)
        return TestSession.objects.create(**fields)
