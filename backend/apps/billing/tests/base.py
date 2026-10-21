"""Общая фикстура тестов оплаты обучения. Только абсолютные импорты."""
from __future__ import annotations

import datetime as dt
import itertools
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.academy.models import Attendance, Course, Group, GroupTeacher, Lesson, Student, StudentStatusEvent
from apps.billing.models import BillingPlan, Invoice, LessonPackage, StudentBillingProfile
from apps.billing.services import lessons, pricing, profiles
from apps.billing.services.ledger import credit_balance
from apps.users.models import Subject, Teacher, User

D = Decimal
_n = itertools.count(1000)


def make_user(username: str, role=User.Role.TEACHER, **extra) -> User:
    return User.objects.create_user(
        username=username, email=f"{username}@okurmen.kg", password="Str0ngPassw0rd!",
        first_name=username.capitalize(), last_name="Test", role=role, is_verified=True, **extra,
    )


class BillingMixin:
    """Строители данных; используется и в TestCase, и в TransactionTestCase."""

    def build(self):
        self.today = timezone.localdate()
        self.start = self.today - dt.timedelta(days=60)
        self.admin = User.objects.create_superuser(
            username="root", email="root@okurmen.kg", password="Str0ngPassw0rd!", first_name="Root",
        )
        self.director = make_user("boss", User.Role.DIRECTOR)
        self.manager = make_user("manager", User.Role.ASSISTANT)
        self.accountant = make_user("buh", User.Role.ACCOUNTANT)
        self.it = Subject.objects.get_or_create(name="IT")[0]
        self.english = Subject.objects.get_or_create(name="English")[0]
        self.course = Course.objects.create(name="Okurmen 144", count_lesson=144)
        self.course.subjects.set([self.it, self.english])
        self.trainer = Teacher.objects.create(user=make_user("trainer"))
        self.group = self.make_group("Group A")
        self.group_b = self.make_group("Group B")
        self.it_plan = pricing.create_plan(
            actor=self.director, name="IT 12", subject=self.it, lessons_per_package=12, package_price=D("4000"),
            effective_from=self.start - dt.timedelta(days=30), payment_due_days=5, warn_before_end_lessons=3,
        )
        self.en_plan = pricing.create_plan(
            actor=self.director, name="English 20", subject=self.english, lessons_per_package=20,
            package_price=D("5000"), effective_from=self.start - dt.timedelta(days=30),
        )

    def make_group(self, name) -> Group:
        group = Group.objects.create(name=name, course=self.course, start_date=self.start - dt.timedelta(days=90))
        for subject in (self.it, self.english):
            GroupTeacher.objects.create(group=group, teacher=self.trainer, subject=subject)
        return group

    def student(self, group=None, *, enrolled=None) -> Student:
        n = next(_n)
        return Student.objects.create(
            first_name=f"Student{n}", last_name="Test", group=group or self.group,
            enrollment_date=enrolled or self.start, parent_phone="+996700000000",
        )

    def profile(self, student=None, plan=None, *, actor=None, **extra) -> StudentBillingProfile:
        student = student or self.student()
        return profiles.create_student_billing_profile(
            student=student, plan=plan or self.it_plan, actor=actor or self.manager,
            start_date=extra.pop("start_date", self.start), responsible_accountant=self.accountant, **extra,
        )

    def lesson(self, *, group=None, day=None, subject=None, status=Lesson.Status.COMPLETED) -> Lesson:
        group = group or self.group
        subject = subject or self.it
        program = GroupTeacher.objects.get(group=group, subject=subject)
        return Lesson.objects.create(
            group=group, group_teacher=program, teacher=program.teacher, subject=subject, lesson_number=next(_n),
            date=day or self.today, start_time=dt.time(10), end_time=dt.time(11), status=status,
        )

    def hold(self, count, *, group=None, start_day=None, subject=None) -> list[Lesson]:
        """Провести `count` уроков (по дню) и списать их (как сигнал после коммита)."""
        start_day = start_day or self.start
        held = []
        for i in range(count):
            lesson = self.lesson(group=group, day=start_day + dt.timedelta(days=i), subject=subject)
            lessons.sync_lesson(lesson.pk)
            held.append(lesson)
        return held

    def mark(self, lesson, student, status):
        Attendance.objects.update_or_create(lesson=lesson, student=student, defaults={"status": status})

    def invoices(self, profile) -> list[Invoice]:
        return list(Invoice.objects.filter(profile=profile).order_by("package__number", "pk"))

    def packages(self, profile) -> list[LessonPackage]:
        return list(LessonPackage.objects.filter(profile=profile).order_by("number"))

    def credit(self, profile) -> Decimal:
        return credit_balance(profile.pk)

    def transfer(self, student, to, on):
        StudentStatusEvent.objects.create(
            student=student, event_type=StudentStatusEvent.EventType.TRANSFERRED,
            previous_status=Student.Status.ACTIVE, from_group=student.group, group=to, event_date=on,
        )
        Student.objects.filter(pk=student.pk).update(group=to)
        student.refresh_from_db()

    def client_for(self, user) -> APIClient:
        client = APIClient()
        client.force_authenticate(user)
        return client


class BillingFixture(BillingMixin, TestCase):
    def setUp(self):
        self.build()


__all__ = ["BillingFixture", "BillingMixin", "D", "make_user", "BillingPlan"]
