"""Учебный месяц и прогресс ученика — единый расчёт (`services.progress`):
1–12 засчитанных уроков → месяц 1, 13–24 → месяц 2…; 12/12 остаётся в
завершённом месяце. English и Soft Skills не влияют; проведённые занятия
группы и засчитанные ученику показываются отдельно; правило начислений и
финансовые записи не меняются."""
from __future__ import annotations

import datetime as dt

from django.test import SimpleTestCase

from apps.academy.models import Attendance
from apps.accounting.models import StudentPayment
from apps.billing.models import (
    AbsencePolicy,
    CreditLedgerEntry,
    Invoice,
    PaymentAllocation,
)
from apps.billing.services import lessons, pricing, profiles, queues
from apps.billing.services.progress import study_progress
from apps.billing.tests.base import D
from apps.billing.tests.test_contracts import BASE
from apps.billing.tests.test_periods import PeriodFixture

SEP1 = dt.date(2026, 9, 1)
EXPECTED = {0: (1, 0), 1: (1, 1), 11: (1, 11), 12: (1, 12), 13: (2, 1), 14: (2, 2), 23: (2, 11), 24: (2, 12),
            25: (3, 1), 35: (3, 11), 36: (3, 12), 48: (4, 12), 60: (5, 12), 72: (6, 12)}


class RuleTests(SimpleTestCase):
    def test_boundaries(self):
        for counted, (month, in_month) in EXPECTED.items():
            p = study_progress(counted, 12, 6)
            self.assertEqual((p["month"], p["in_month"], p["counted"], p["total"]), (month, in_month, counted, 72),
                             counted)

    def test_no_month_plan_and_overflow(self):
        self.assertEqual(study_progress(5, None, None)["month"], None)
        self.assertEqual((study_progress(80, 12, 6)["month"], study_progress(80, 12, 6)["in_month"]), (6, 20))


class ProgressFixture(PeriodFixture):
    def setUp(self):
        super().setUp()
        self.at(SEP1)
        self.next3 = pricing.create_plan(
            actor=self.accountant, name="Next 3", subject=self.it, course=self.course, lessons_per_package=12,
            package_price=D("12000"), effective_from=self.start, duration_months=6, payment_deadline_lessons=3)
        self.day = dt.date(2026, 9, 2)

    def contract(self, plan=None, start=SEP1, student=None):
        return profiles.create_student_billing_profile(
            student=student or self.student(self.group_b), plan=plan or self.next3, actor=self.accountant,
            start_date=start, responsible_accountant=self.accountant)

    def held(self, n, subject=None, mark=None, student=None):
        for _ in range(n):
            lesson = self.lesson(group=self.group_b, day=self.day, subject=subject)
            if mark is not None:
                Attendance.objects.update_or_create(lesson=lesson, student=student, defaults={"status": mark})
            lessons.sync_lesson(lesson.pk)
            self.day += dt.timedelta(days=1)

    def row(self, profile):
        return queues.contract_row(queues.base_queryset().get(pk=profile.pk))

    def finance(self, profile):
        return (list(Invoice.objects.filter(profile=profile).order_by("pk").values_list("amount", "status", "amount_paid")),
                StudentPayment.objects.count(), PaymentAllocation.objects.count(),
                list(CreditLedgerEntry.objects.order_by("pk").values_list("amount", flat=True)))


class ListProgressTests(ProgressFixture):
    def test_every_boundary_from_0_to_72_and_billing_cycle_unchanged(self):
        profile = self.contract()
        done = 0
        for counted, (month, in_month) in EXPECTED.items():
            self.held(counted - done)
            self.held(1, subject=self.english)  # English между уроками IT — не влияет
            done = counted
            r = self.row(profile)
            self.assertEqual((r["month_number"], r["lessons_used"], r["lessons_total"]), (month, in_month, 12), counted)
            self.assertEqual((r["course_lessons_counted"], r["course_lessons_total"], r["duration_months"]),
                             (counted, 72, 6), counted)
            invoices = Invoice.objects.filter(profile=profile).exclude(status="VOID").count()
            # Правило начислений прежнее: после 12-го, 24-го… урока выставлен следующий месяц.
            self.assertEqual(invoices, min(counted // 12 + 1, 6), counted)
            boundary = counted in (12, 24, 36, 48, 60)
            self.assertEqual((r["next_month_open"], r["billing_month_number"]),
                             (boundary, month + 1 if boundary else month), counted)

    def test_fourteen_lessons_example_and_card(self):
        profile = self.contract()
        self.held(14)
        r = self.row(profile)
        self.assertEqual(f"месяц {r['month_number']} из {r['duration_months']}, IT {r['lessons_used']}/{r['lessons_total']}, "
                         f"курс {r['course_lessons_counted']}/{r['course_lessons_total']}",
                         "месяц 2 из 6, IT 2/12, курс 14/72")
        card = self.client_for(self.accountant).get(BASE + f"profiles/{profile.pk}/card/").data
        self.assertEqual({k: card["progress"][k] for k in ("month", "in_month", "counted", "total")},
                         {"month": 2, "in_month": 2, "counted": 14, "total": 72})
        self.assertEqual(card["progress"]["group_held"], {"all_time": 14, "since_contract": 14})
        self.assertEqual([(m["month_number"], m["is_current"]) for m in card["months"]], [(1, False), (2, True)])

    def test_boundary_card_keeps_completed_month_current(self):
        profile = self.contract()
        self.held(12)
        card = self.client_for(self.accountant).get(BASE + f"profiles/{profile.pk}/card/").data
        self.assertEqual((card["row"]["month_number"], card["row"]["lessons_used"]), (1, 12))
        self.assertEqual([(m["month_number"], m["status"], m["is_current"]) for m in card["months"]],
                         [(1, "COMPLETED", True), (2, "ACTIVE", False)])
        self.assertTrue(card["progress"]["next_month_open"])
        self.assertEqual(card["progress"]["billing_month"], 2)

    def test_other_subjects_do_not_change_progress(self):
        profile = self.contract()
        self.held(5)
        before = self.row(profile)
        self.held(7, subject=self.english)
        self.held(7, subject=self.soft)  # Soft Skills — программа группы есть (фикстура)
        after = self.row(profile)
        keys = ("month_number", "lessons_used", "course_lessons_counted")
        self.assertEqual({k: after[k] for k in keys}, {k: before[k] for k in keys})
        self.assertEqual(after["course_lessons_counted"], 5)


class GroupVersusStudentTests(ProgressFixture):
    def test_late_contract_and_absence_rule_differ_from_group_count(self):
        self.held(3)  # группа уже провела 3 урока IT до договора
        profile = self.contract(start=self.day)
        self.held(4)
        card = self.client_for(self.accountant).get(BASE + f"profiles/{profile.pk}/card/").data
        self.assertEqual(card["progress"]["group_held"], {"all_time": 7, "since_contract": 4})
        self.assertEqual((card["progress"]["counted"], card["row"]["month_number"], card["row"]["lessons_used"]),
                         (4, 1, 3 + 1))
        # Тариф «только посещённые»: пропуск не засчитан ученику, хотя занятие группы проведено.
        strict = pricing.create_plan(
            actor=self.accountant, name="Next 3 strict", subject=self.it, course=self.course, lessons_per_package=12,
            package_price=D("12000"), effective_from=self.start, duration_months=6, absence_policy=AbsencePolicy.ATTENDED_ONLY)
        student = self.student(self.group_b)
        other = self.contract(plan=strict, start=self.day, student=student)
        self.held(1, mark=Attendance.Status.PRESENT, student=student)
        self.held(1, mark=Attendance.Status.ABSENT, student=student)
        card = self.client_for(self.accountant).get(BASE + f"profiles/{other.pk}/card/").data
        self.assertEqual((card["progress"]["group_held"]["since_contract"], card["progress"]["counted"]), (2, 1))
        self.assertEqual(self.row(other)["course_lessons_counted"], 1)

    def test_display_is_read_only(self):
        profile = self.contract()
        self.held(12)
        before = self.finance(profile)
        api = self.client_for(self.accountant)
        for _ in range(2):
            self.row(profile)
            self.assertEqual(api.get(BASE + f"profiles/{profile.pk}/card/").status_code, 200)
            listing = api.get(BASE + "queues/all/")
            self.assertEqual(listing.status_code, 200)
        row = next(r for r in listing.data["results"] if r["profile"] == profile.pk)
        self.assertEqual((row["month_number"], row["lessons_used"], row["next_month_open"]), (1, 12, True))
        self.assertEqual(self.finance(profile), before)
