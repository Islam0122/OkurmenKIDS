"""Счёт уроков учебного месяца против посещений в карточке студента.

Ошибка: уроки, проведённые с даты начала договора до его оформления, не
попадали в учебный месяц (списание шло только по событию урока / посещаемости
и фоновой задачей за 14 дней) — «IT 0 из 12» при 13 посещениях."""
from __future__ import annotations

import datetime as dt
import io
from unittest import mock

from django.core.management import call_command

from apps.academy.models import Attendance, Lesson
from apps.billing.models import Invoice, LessonConsumption
from apps.billing.services import lessons, pricing, profiles
from apps.billing.services.reports import reconcile
from apps.billing.tests.base import BillingFixture, D


class LessonCountTests(BillingFixture):
    def setUp(self):
        super().setUp()
        self.kc = pricing.create_plan(
            actor=self.accountant, name="KC", subject=self.it, course=self.course, lessons_per_package=12,
            package_price=D("15000"), effective_from=self.start - dt.timedelta(days=30), duration_months=4,
        )
        self.day = self.start

    def attend(self, student, n, *, subject=None, status=Lesson.Status.COMPLETED, mark=Attendance.Status.PRESENT):
        held = []
        for _ in range(n):
            lesson = self.lesson(day=self.day, subject=subject, status=status)
            Attendance.objects.create(lesson=lesson, student=student, status=mark)
            self.day += dt.timedelta(days=1)
            held.append(lesson)
        return held

    def contract(self, student, **kw):
        return profiles.create_student_billing_profile(student=student, plan=self.kc, actor=self.accountant, **kw)

    def months(self, profile):
        return [(m.month_number, m.lessons_used, m.status) for m in profile.packages.order_by("number")]

    def test_13_attended_it_lessons_before_contract_are_counted(self):
        student = self.student()
        self.attend(student, 13)
        attendance = list(Attendance.objects.filter(student=student).values_list("pk", "status"))
        profile = self.contract(student)  # дата начала — дата зачисления (в прошлом)
        self.assertEqual(self.months(profile), [(1, 12, "COMPLETED"), (2, 1, "ACTIVE")])
        breakdown = lessons.lesson_breakdown(profile)
        self.assertEqual((breakdown["attended"], breakdown["counted"]), (13, 13))
        self.assertEqual(list(Attendance.objects.filter(student=student).values_list("pk", "status")), attendance)
        # Месяц 2 начался — его начисление выставлено; уроки месяца 1 за его пределами не считаются.
        self.assertEqual(Invoice.objects.filter(profile=profile).count(), 2)
        self.assertEqual(lessons.sync_profile_history(profile)["consumed"], 0)  # повтор ничего не меняет

    def test_other_subjects_are_attendances_but_not_it_lessons(self):
        student = self.student()
        self.attend(student, 10)
        self.attend(student, 3, subject=self.english)
        profile = self.contract(student)
        self.assertEqual(self.months(profile), [(1, 10, "ACTIVE")])
        totals = lessons.lesson_breakdown(profile)["totals"]
        self.assertEqual((totals["counted"], totals["other_subject"]), (10, 3))

    def test_not_completed_and_before_contract_lessons_are_not_counted(self):
        student = self.student()
        self.attend(student, 2)  # до начала договора
        start = self.day
        self.attend(student, 4)
        self.attend(student, 2, status=Lesson.Status.SCHEDULED)  # отметка есть, урок не «Проведён»
        profile = self.contract(student, start_date=start)
        self.assertEqual(self.months(profile), [(1, 4, "ACTIVE")])
        totals = lessons.lesson_breakdown(profile)["totals"]
        self.assertEqual((totals["counted"], totals["before_contract"], totals["not_completed"]), (4, 2, 2))

    def test_contract_starting_today_does_not_take_past_lessons(self):
        student = self.student()
        self.attend(student, 5)
        profile = self.contract(student, start_date=self.today)
        self.assertEqual(self.months(profile), [(1, 0, "ACTIVE")])
        self.assertEqual(lessons.lesson_breakdown(profile)["totals"]["before_contract"], 5)

    def test_legacy_contract_is_detected_and_fixed_by_command(self):
        student = self.student()
        self.attend(student, 13)
        with mock.patch.object(lessons, "sync_profile_history", return_value={"consumed": 0}):
            profile = self.contract(student)  # как до исправления
        self.assertEqual(self.months(profile), [(1, 0, "ACTIVE")])
        self.assertEqual(lessons.lesson_breakdown(profile)["totals"]["not_processed"], 13)
        self.assertIn({"type": "lessons_not_consumed", "profile": profile.pk, "lessons": 13}, reconcile())
        out = io.StringIO()
        call_command("billing_resync_lessons", "--dry-run", stdout=out)
        self.assertIn("не засчитано уроков — 13", out.getvalue())
        self.assertEqual(LessonConsumption.objects.filter(profile=profile).count(), 0)
        call_command("billing_resync_lessons", stdout=io.StringIO())
        self.assertEqual(self.months(profile), [(1, 12, "COMPLETED"), (2, 1, "ACTIVE")])
        self.assertFalse([p for p in reconcile() if p["type"] == "lessons_not_consumed"])
        call_command("billing_resync_lessons", stdout=out)  # повтор — без дублей
        self.assertEqual(LessonConsumption.objects.filter(profile=profile).count(), 13)

    def test_breakdown_api_for_accountant_and_director(self):
        student = self.student()
        self.attend(student, 13)
        profile = self.contract(student)
        for user in (self.accountant, self.director, self.manager):
            response = self.client_for(user).get(f"/api/v1/accounting/billing/profiles/{profile.pk}/lessons/")
            self.assertEqual(response.status_code, 200)
            self.assertEqual((response.data["attended"], response.data["counted"]), (13, 13))
