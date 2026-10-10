"""Общая фикстура тестов бухгалтерии. Только абсолютные импорты — см.
заметку в apps/academy/tests.py про двойной префикс `backend.`."""
from __future__ import annotations

import datetime as dt
import itertools
from decimal import Decimal

from django.test import TestCase
from rest_framework.test import APIClient

from apps.academy.models import Course, Group, GroupTeacher, Lesson, Student, StudentStatusEvent
from apps.accounting.models import (
    CoursePayrollSettings,
    EmployeeSalaryProfile,
    PayrollPeriod,
    SalaryRule,
    SalaryType,
    StudentPayment,
)
from apps.accounting.services.payroll_calculator import calculate_payroll
from apps.accounting.services.periods import get_or_create_period
from apps.users.models import Subject, Teacher, User

D = Decimal
SEP = (2026, 9)
FIRST, SECOND = PayrollPeriod.PeriodType.FIRST_HALF, PayrollPeriod.PeriodType.SECOND_HALF
MONTH = PayrollPeriod.PeriodType.MONTH
_n = itertools.count(1)


def day(month: int, d: int, year: int = 2026) -> dt.date:
    return dt.date(year, month, d)


def make_user(username: str, role=User.Role.TEACHER, **extra) -> User:
    return User.objects.create_user(
        username=username, email=f"{username}@okurmen.kg", password="Str0ngPassw0rd!",
        first_name=username.capitalize(), last_name="Test", role=role, is_verified=True, **extra,
    )


class AccountingFixture(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser(
            username="root", email="root@okurmen.kg", password="Str0ngPassw0rd!", first_name="Root",
        )
        self.accountant = make_user("buh", User.Role.ACCOUNTANT)
        self.director = make_user("boss", User.Role.DIRECTOR)
        self.python = Subject.objects.get_or_create(name="Python")[0]
        self.course = Course.objects.create(name="Prog SOFT", count_lesson=48)
        self.course.subjects.set([self.python])
        self.other_course = Course.objects.create(name="Robotics", count_lesson=24)
        self.trainer_user = make_user("trainer")
        self.trainer = Teacher.objects.create(user=self.trainer_user)
        self.group_a = self.group("Group A")
        self.group_b = self.group("Group B")

    # -- builders -----------------------------------------------------------

    def group(self, name, *, course=None, start=day(1, 10), trainer=None) -> Group:
        group = Group.objects.create(name=name, course=course or self.course, start_date=start)
        if trainer is not False:
            GroupTeacher.objects.create(group=group, teacher=trainer or self.trainer, subject=self.python)
        return group

    def student(self, group=None, *, enrolled=day(8, 1), **extra) -> Student:
        n = next(_n)
        return Student.objects.create(
            first_name=extra.pop("first_name", f"Student{n}"), last_name="Test", group=group or self.group_a,
            enrollment_date=enrolled, **extra,
        )

    def leave(self, student, on: dt.date):
        StudentStatusEvent.objects.create(
            student=student, event_type=StudentStatusEvent.EventType.DEACTIVATED,
            reason=StudentStatusEvent.Reason.RELOCATION, previous_status=Student.Status.ACTIVE,
            group=student.group, event_date=on,
        )
        Student.objects.filter(pk=student.pk).update(status=Student.Status.WITHDRAWN, is_active=False)

    def transfer(self, student, to: Group, on: dt.date):
        StudentStatusEvent.objects.create(
            student=student, event_type=StudentStatusEvent.EventType.TRANSFERRED,
            previous_status=Student.Status.ACTIVE, from_group=student.group, group=to, event_date=on,
        )
        Student.objects.filter(pk=student.pk).update(group=to)

    def profile(self, user=None, salary_type=SalaryType.FIXED, *, start=day(1, 1)) -> EmployeeSalaryProfile:
        return EmployeeSalaryProfile.objects.create(
            employee=user or self.trainer_user, salary_type=salary_type, effective_from=start,
        )

    def rule(self, profile, rule_type, *, start=day(1, 1), end=None, method=None, **fields) -> SalaryRule:
        rule = SalaryRule(
            employee_profile=profile, rule_type=rule_type, effective_from=start, effective_to=end,
            calculation_method=method or SalaryRule.METHODS_BY_TYPE[rule_type][0], **fields,
        )
        rule.full_clean()
        rule.save()
        return rule

    def pay(self, student, amount, on, *, group=None, service=None, kind=StudentPayment.Kind.PAYMENT, refund_of=None):
        group = group or student.group
        start, end = service or (on.replace(day=1), on.replace(day=28))
        return StudentPayment.objects.create(
            student=student, group=group, course=group.course, kind=kind, amount=D(amount), received_date=on,
            service_start=start, service_end=end, refund_of=refund_of, created_by=self.accountant,
        )

    def refund(self, original, amount, on):
        return self.pay(original.student, amount, on, group=original.group,
                        service=(original.service_start, original.service_end),
                        kind=StudentPayment.Kind.REFUND, refund_of=original)

    def course_settings(self, course=None, *, price="10000", lessons=12, start=day(1, 1), **extra):
        return CoursePayrollSettings.objects.create(
            course=course or self.course, price_per_student=D(price), required_lessons=lessons,
            count_lessons_from=start, **extra,
        )

    def lessons(self, group, dates, *, status=Lesson.Status.COMPLETED):
        """Проведённые уроки группы в указанные даты (по одному в день)."""
        program = GroupTeacher.objects.filter(group=group).first()
        for d in dates:
            Lesson.objects.create(
                group=group, group_teacher=program, teacher=program.teacher, subject=self.python,
                lesson_number=next(_n), date=d,
                start_time=dt.time(10), end_time=dt.time(11), status=status,
            )

    def period(self, year_month=SEP, half=FIRST) -> PayrollPeriod:
        return get_or_create_period(*year_month, half, self.accountant)[0]

    def calc(self, half=FIRST, user=None, year_month=SEP):
        return calculate_payroll(self.period(year_month, half), user or self.trainer_user, self.accountant)

    def client_for(self, user) -> APIClient:
        client = APIClient()
        client.force_authenticate(user)
        return client
