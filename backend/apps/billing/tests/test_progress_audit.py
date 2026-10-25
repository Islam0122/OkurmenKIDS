"""Сверка учебного прогресса академии и бухгалтерии (`billing_progress_audit`):
правило «12 засчитанных уроков на месяц» на границах, расхождение на границе
месяца, уроки до договора / других предметов / отменённые, нераспределённый
аванс; команда только читает."""
from __future__ import annotations

import datetime as dt
import json
import tempfile
from io import StringIO
from pathlib import Path

from django.core.management import call_command
from django.test import SimpleTestCase

from apps.academy.models import Lesson
from apps.billing.models import Invoice, LessonConsumption
from apps.billing.services import lessons, payments, pricing, profiles
from apps.billing.services.progress_audit import _rule, profile_progress
from apps.billing.tests.base import D
from apps.billing.tests.test_periods import PeriodFixture

SEP1 = dt.date(2026, 9, 1)


class RuleTests(SimpleTestCase):
    def test_month_boundaries(self):
        cases = {0: (1, 0), 1: (1, 1), 11: (1, 11), 12: (1, 12), 13: (2, 1), 14: (2, 2), 24: (2, 12), 25: (3, 1),
                 72: (6, 12)}
        for counted, expected in cases.items():
            rule = _rule(counted, 12, 6)
            self.assertEqual((rule["month"], rule["in_month"]), expected, counted)


class AuditFixture(PeriodFixture):
    def setUp(self):
        super().setUp()
        self.at(SEP1)
        self.next3 = pricing.create_plan(
            actor=self.accountant, name="Next 3", subject=self.it, course=self.course, lessons_per_package=12,
            package_price=D("12000"), effective_from=self.start, duration_months=6, payment_deadline_lessons=3)
        self.day = dt.date(2026, 9, 2)

    def contract(self, *, start=SEP1, paid="12000", **kw):
        profile = profiles.create_student_billing_profile(
            student=self.student(self.group_b), plan=self.next3, actor=self.accountant, start_date=start,
            responsible_accountant=self.accountant, **kw)
        if paid:
            self.pay(profile, paid, on=SEP1)
        return profile

    def held(self, n, subject=None, status=Lesson.Status.COMPLETED):
        out = []
        for _ in range(n):
            lesson = self.lesson(group=self.group_b, day=self.day, subject=subject, status=status)
            lessons.sync_lesson(lesson.pk)
            self.day += dt.timedelta(days=1)
            out.append(lesson)
        return out


class AuditTests(AuditFixture):
    def test_boundary_and_fourteenth_lesson(self):
        profile = self.contract()
        self.held(12)
        r = profile_progress(profile)
        self.assertEqual(r["billing"]["shown"], "месяц 2 из 6, IT 0/12")  # как сейчас в «Все студенты»
        self.assertEqual(r["rule"]["shown"], "месяц 1 из 6, 12 из 12")
        self.assertEqual([f["code"] for f in r["findings"]], ["boundary_month"])
        self.assertEqual([(i["month"], i["status"]) for i in r["money"]["invoices"]],
                         [(1, Invoice.Status.PAID), (2, Invoice.Status.OPEN)])  # начисление месяца 2 — по правилу проекта
        self.held(2)
        r = profile_progress(profile)
        self.assertEqual((r["billing"]["shown"], r["rule"]["shown"], r["rule"]["course_progress"]),
                         ("месяц 2 из 6, IT 2/12", "месяц 2 из 6, 2 из 12", "14 из 72"))
        self.assertEqual(r["academy"]["held_since_contract"], 14)
        self.assertEqual(r["findings"], [])

    def test_other_subjects_cancelled_and_before_contract_are_not_counted(self):
        self.day = dt.date(2026, 9, 2)
        self.held(2)  # до начала договора
        profile = self.contract(start=dt.date(2026, 9, 4))
        self.held(3)
        self.held(2, subject=self.english)
        self.held(1, status=Lesson.Status.CANCELLED)
        r = profile_progress(profile)
        self.assertEqual((r["academy"]["held_all_time"], r["academy"]["held_since_contract"], r["billing"]["counted"]),
                         (5, 3, 3))
        self.assertEqual(r["billing"]["counted_distinct_lessons"], 3)  # урок не засчитан дважды
        self.assertEqual(r["rule"]["shown"], "месяц 1 из 6, 3 из 12")

    def test_unprocessed_lesson_and_unapplied_credit_are_flagged(self):
        profile = self.contract(paid=None)
        payments.record_payment(profile=profile, amount="5000", received_date=SEP1, actor=self.accountant,
                                auto_allocate=False)
        lesson = self.lesson(group=self.group_b, day=self.day)  # проведён, но не синхронизирован
        codes = {f["code"] for f in profile_progress(profile)["findings"]}
        self.assertTrue({"count_mismatch", "credit_unapplied"} <= codes)
        self.assertFalse(LessonConsumption.objects.filter(lesson_ref=lesson.pk).exists())

    def test_command_is_read_only(self):
        profile = self.contract()
        self.held(12)
        before = (LessonConsumption.objects.count(), Invoice.objects.count(),
                  list(Invoice.objects.values_list("status", "amount_paid")))
        out = StringIO()
        call_command("billing_progress_audit", plan="Next 3", stdout=out)
        self.assertIn("boundary_month", out.getvalue())
        self.assertIn("месяц 1 из 6, 12 из 12", out.getvalue())
        self.assertEqual((LessonConsumption.objects.count(), Invoice.objects.count(),
                          list(Invoice.objects.values_list("status", "amount_paid"))), before)
        self.assertEqual(profile.invoices.count(), 2)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "report.json"
            call_command("billing_progress_audit", profile=profile.pk, json=str(path), stdout=StringIO())
            report = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual((report["total"], report["by_finding"]), (1, {"boundary_month": 1}))
