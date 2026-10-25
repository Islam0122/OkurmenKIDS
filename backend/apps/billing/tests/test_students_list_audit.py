"""«Финансы → Все студенты»: четыре случая аудита (Prog SOFT 2, 4 × 12 уроков,
15 000 в месяц) — строка списка и `billing_progress_audit`.

* «К оплате сейчас» = просрочено + срок сегодня + срок не наступил;
* просрочка — только от начисления после срока, не от перехода в месяц 2;
* аванс не делает начисление оплаченным; повторный платёж помечается;
* отчёт аудита: период и дата создания начислений, платежи с распределениями.
Отображение и отчёт ничего не меняют."""
from __future__ import annotations

import datetime as dt
from decimal import Decimal
from io import StringIO

from django.core.management import call_command

from apps.billing.models import Invoice, PaymentAllocation
from apps.billing.services import lessons, payments, pricing, profiles, queues
from apps.billing.services.progress_audit import profile_progress
from apps.billing.tests.base import D
from apps.billing.tests.test_periods import OCT24, PeriodFixture

SEP1, SEP2 = dt.date(2026, 9, 1), dt.date(2026, 9, 2)


class StudentsListFixture(PeriodFixture):
    def setUp(self):
        super().setUp()
        self.at(SEP1)
        self.soft2 = pricing.create_plan(
            actor=self.accountant, name="Prog SOFT 2", subject=self.it, course=self.course, lessons_per_package=12,
            package_price=D("15000"), effective_from=self.start, duration_months=4, payment_deadline_lessons=3)

    def contract(self, start=SEP1, **kw):
        return profiles.create_student_billing_profile(
            student=self.student(self.group_b), plan=self.soft2, actor=self.accountant, start_date=start,
            responsible_accountant=self.accountant, **kw)

    def held(self, start_index, n):
        for i in range(start_index, start_index + n):
            lessons.sync_lesson(self.lesson(group=self.group_b, day=SEP2 + dt.timedelta(days=i)).pk)

    def row(self, profile):
        return queues.contract_row(queues.base_queryset().get(pk=profile.pk))

    def scenario(self):
        bayel = self.contract()
        self.pay(bayel, "15000", on=SEP1)
        zeynep = self.contract()
        self.pay(zeynep, "44630", on=SEP1)
        edgar = self.contract(discount_enabled=True, final_course_price="58000", discount_reason="Скидка")
        self.pay(edgar, "7500", on=SEP1)
        self.at(OCT24)
        self.held(0, 11)
        umar = self.contract(start=SEP2 + dt.timedelta(days=11))  # договор позже — 2 урока из 13
        self.pay(umar, "15000", on=SEP1)
        self.held(11, 2)
        return umar, bayel, zeynep, edgar


class StudentsListTests(StudentsListFixture):
    def test_four_rows_match_the_audit_and_split_due_by_deadline(self):
        umar, bayel, zeynep, edgar = self.scenario()
        keys = ("month_number", "lessons_used", "course_lessons_counted", "due_now", "overdue_amount",
                "due_today_amount", "not_due_amount", "credit", "stage")
        rows = {name: {k: self.row(p)[k] for k in keys} for name, p in
                (("umar", umar), ("bayel", bayel), ("zeynep", zeynep), ("edgar", edgar))}
        self.assertEqual(rows["umar"], {"month_number": 1, "lessons_used": 2, "course_lessons_counted": 2,
                                        "due_now": "0.00", "overdue_amount": "0.00", "due_today_amount": "0.00",
                                        "not_due_amount": "0.00", "credit": "0.00", "stage": "paid"})
        self.assertEqual(rows["bayel"], {"month_number": 2, "lessons_used": 1, "course_lessons_counted": 13,
                                         "due_now": "15000.00", "overdue_amount": "0.00", "due_today_amount": "0.00",
                                         "not_due_amount": "15000.00", "credit": "0.00", "stage": "awaiting"})
        self.assertEqual(rows["zeynep"], {"month_number": 2, "lessons_used": 1, "course_lessons_counted": 13,
                                          "due_now": "0.00", "overdue_amount": "0.00", "due_today_amount": "0.00",
                                          "not_due_amount": "0.00", "credit": "14630.00", "stage": "paid"})
        self.assertEqual(rows["edgar"], {"month_number": 2, "lessons_used": 1, "course_lessons_counted": 13,
                                         "due_now": "21500.00", "overdue_amount": "7000.00", "due_today_amount": "0.00",
                                         "not_due_amount": "14500.00", "credit": "0.00", "stage": "overdue"})
        # Просрочка ЭДГАРА — от месяца 1 (оплачено 7 500 из 14 500, срок 3-й урок прошёл), не от месяца 2.
        m1, m2 = Invoice.objects.filter(profile=edgar).order_by("package__number")
        self.assertEqual((m1.status, m1.balance, m2.status, m2.balance),
                         (Invoice.Status.OVERDUE, D("7000"), Invoice.Status.OPEN, D("14500")))
        for name, r in rows.items():
            parts = sum(Decimal(r[k]) for k in ("overdue_amount", "due_today_amount", "not_due_amount"))
            self.assertEqual(parts, Decimal(r["due_now"]), name)

    def test_deadline_today_and_credit_reduce_parts_in_order(self):
        profile = self.contract()
        self.pay(profile, "15000", on=SEP1)
        self.at(OCT24)
        self.held(0, 14)  # месяц 2: 2 урока — срок 3-й ещё не наступил
        self.assertEqual(self.row(profile)["not_due_amount"], "15000.00")
        self.held(14, 1)  # 3-й урок месяца 2 — последний срок
        r = self.row(profile)
        self.assertEqual((r["stage"], r["due_today_amount"], r["not_due_amount"]), ("deadline", "15000.00", "0.00"))
        payments.record_payment(profile=profile, amount="5000", received_date=OCT24, actor=self.accountant,
                                auto_allocate=False)  # аванс рядом с начислением — не оплата
        r = self.row(profile)
        self.assertEqual((r["due_now"], r["due_today_amount"], r["credit"], r["stage"]),
                         ("10000.00", "10000.00", "5000.00", "deadline"))

    def test_audit_lists_invoices_with_period_and_payments_with_allocations(self):
        _umar, _bayel, zeynep, edgar = self.scenario()
        r = profile_progress(edgar)
        self.assertEqual([(i["month"], i["amount"], i["paid"], i["balance"], i["status"], i["period_date"])
                          for i in r["money"]["invoices"]],
                         [(1, "14500.00", "7500.00", "7000.00", "OVERDUE", "2026-09-01"),
                          (2, "14500.00", "0.00", "14500.00", "OPEN", "2026-09-13")])  # период — день 12-го урока
        self.assertTrue(all(i["created_at"] for i in r["money"]["invoices"]))
        self.assertEqual((r["money"]["overdue"], r["money"]["not_due"]), ("7000.00", "14500.00"))
        z = profile_progress(zeynep)["money"]
        self.assertEqual([(p["amount"], p["unallocated"], len(p["allocations"])) for p in z["payments"]],
                         [("44630.00", "14630.00", 2)])
        self.assertEqual((z["received"], z["allocated"], z["credit"]), ("44630.00", "30000.00", "14630.00"))

    def test_same_day_duplicate_payment_is_flagged_and_command_is_read_only(self):
        profile = self.contract()
        self.pay(profile, "15000", on=SEP1)
        self.pay(profile, "15000", on=SEP1)
        before = (list(Invoice.objects.values_list("status", "amount_paid")), PaymentAllocation.objects.count())
        self.assertIn("possible_duplicate_payment", {f["code"] for f in profile_progress(profile)["findings"]})
        out = StringIO()
        call_command("billing_progress_audit", profile=profile.pk, stdout=out)
        self.assertIn("платежи:", out.getvalue())
        self.assertIn("период 2026-09-01", out.getvalue())
        self.assertIn("possible_duplicate_payment", out.getvalue())
        self.assertEqual((list(Invoice.objects.values_list("status", "amount_paid")), PaymentAllocation.objects.count()),
                         before)
