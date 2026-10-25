"""Остаток предоплаты за обучение: карточка дашборда = Σ детализации; полная /
частичная предоплата, остаток аванса, сторно, возвраты, брони."""
from __future__ import annotations

import datetime as dt
from decimal import Decimal

from apps.billing.models import PaymentMode, ReservationAllocation
from apps.billing.services import payments, prepayments, reservations
from apps.billing.services.reports import dashboard
from apps.billing.tests.base import D
from apps.billing.tests.test_contracts import BASE
from apps.billing.tests.test_periods import OCT24, PeriodFixture

SEP1 = dt.date(2026, 9, 1)


class PrepaymentFixture(PeriodFixture):
    def setUp(self):
        super().setUp()
        self.at(SEP1)
        self.day = dt.date(2026, 9, 2)

    def new(self, **extra):
        return self.contract(student=extra.pop("student", None) or self.student(self.group_b), start_date=SEP1, **extra)

    def row(self, profile):
        profile.refresh_from_db()
        return prepayments.prepayment_row(profile)


class StatusTests(PrepaymentFixture):
    def test_full_prepay_course_counts_future_months_not_only_credit(self):
        profile = self.new(payment_mode=PaymentMode.FULL_PREPAY)
        self.pay(profile, "60000", on=SEP1)
        row = self.row(profile)
        self.assertEqual((row["status"], row["unallocated"], row["allocated_future"], row["prepayment"]),
                         (prepayments.FULL, D("0"), D("60000"), D("60000")))
        self.assertEqual(row["paid_months"], 4)
        self.at(OCT24)
        self.hold(13, start_day=dt.date(2026, 9, 2), group=self.group_b)  # месяц 1 пройден, месяц 2 начат
        row = self.row(profile)
        self.assertEqual((row["allocated_future"], row["applied_to_studied"], row["status"]),
                         (D("30000"), D("30000"), prepayments.FULL))
        self.assertFalse(row["allocated_future_exact"])  # равные доли без плана месяцев — оценка

    def test_partial_and_full_monthly_prepayment(self):
        partial = self.new()
        self.pay(partial, "40000", on=SEP1)  # месяц 1 = 15 000, аванс 25 000 < будущих 45 000
        row = self.row(partial)
        self.assertEqual((row["status"], row["unallocated"], row["applied_to_studied"], row["remaining_obligations"]),
                         (prepayments.PARTIAL, D("25000"), D("15000"), D("45000")))
        self.assertEqual((row["paid_months"], row["next_covered_month"]), (1, 2))
        full = self.new()
        self.pay(full, "60000", on=SEP1)
        self.assertEqual(self.row(full)["status"], prepayments.FULL)

    def test_overpayment_after_all_months_is_advance(self):
        profile = self.new(payment_mode=PaymentMode.FULL_PREPAY)
        self.pay(profile, "60000", on=SEP1)
        self.at(OCT24)
        self.hold(48, start_day=dt.date(2026, 9, 2), group=self.group_b)  # курс пройден
        self.pay(profile, "1000", on=OCT24)
        row = self.row(profile)
        self.assertEqual(row["allocated_future"], D("0"))
        self.assertEqual((row["unallocated"], row["status"]), (D("1000"), prepayments.REVIEW))  # договор завершён
        self.assertIn("Курс завершён", row["review_reasons"][0])

    def test_package_plan_without_total_is_advance(self):
        profile = self.profile(student=self.student(self.group_b), start_date=SEP1)  # тариф без срока
        payments.record_payment(profile=profile, amount="6000", received_date=SEP1, actor=self.accountant)
        row = self.row(profile)
        self.assertEqual((row["status"], row["contract_total"], row["unallocated"]),
                         (prepayments.ADVANCE, None, D("2000")))


class MoneyRulesTests(PrepaymentFixture):
    def test_reversed_payment_is_not_prepayment(self):
        profile = self.new()
        payment = self.pay(profile, "40000", on=SEP1)
        payments.reverse_payment(payment, actor=self.accountant, reason="Ошибка")
        self.assertIsNone(self.row(profile))

    def test_refund_reduces_prepayment(self):
        profile = self.new()
        payment = self.pay(profile, "40000", on=SEP1)
        payments.refund_payment(payment, actor=self.accountant, amount="10000", reason="Вернули часть")
        self.assertEqual(self.row(profile)["unallocated"], D("15000"))

    def test_course_total_reservation_deposit_is_not_tuition_yet(self):
        profile = self.new(reservation_amount="3000", reservation_allocation=ReservationAllocation.COURSE_TOTAL)
        reservations.record_reservation_payment(profile.reservations.get(), actor=self.accountant, amount="3000",
                                                received_date=SEP1)
        row = self.row(profile)
        self.assertIsNone(row)  # депозит брони не зачтён → не предоплата обучения
        first = self.new(reservation_amount="3000")  # бронь в первый месяц — зачтена сразу
        reservations.record_reservation_payment(first.reservations.get(), actor=self.accountant, amount="3000",
                                                received_date=SEP1)
        self.assertIsNone(self.row(first))  # ушла на месяц 1, остатка нет

    def test_unapplied_credit_and_closed_contract_need_review(self):
        profile = self.new()
        payments.record_payment(profile=profile, amount="5000", received_date=SEP1, actor=self.accountant,
                                auto_allocate=False)
        row = self.row(profile)
        self.assertEqual(row["status"], prepayments.REVIEW)
        self.assertIn("не распределён на неоплаченные", row["review_reasons"][0])


class TotalsTests(PrepaymentFixture):
    def test_dashboard_card_equals_sum_of_rows_and_api(self):
        a = self.new(payment_mode=PaymentMode.FULL_PREPAY)
        self.pay(a, "60000", on=SEP1)
        b = self.new()
        self.pay(b, "40000", on=SEP1)
        c = self.new()
        self.pay(c, "15000", on=SEP1)  # ровно месяц 1 — без предоплаты
        data = prepayments.prepayments({})
        total = sum(Decimal(r["prepayment"]) for r in data["results"])
        self.assertEqual(data["summary"]["prepayment"], total)
        self.assertEqual(total, D("85000"))
        self.assertEqual(data["summary"]["allocated_future"] + data["summary"]["unallocated"], total)  # без двойного счёта
        self.assertEqual((data["summary"]["students"], data["summary"]["full"], data["summary"]["partial"]), (2, 1, 1))
        self.assertEqual(dashboard({})["prepayment_total"], str(total))
        api = self.client_for(self.accountant)
        card = api.get(BASE + "dashboard/").data
        self.assertEqual(card["prepayment_total"], "85000.00")
        listing = api.get(BASE + "prepayments/", {"status": "partial"}).data
        self.assertEqual([r["profile"] for r in listing["results"]], [b.pk])
        self.assertEqual(api.get(BASE + "prepayments/", {"search": a.student.first_name}).data["summary"]["students"], 1)
        self.assertEqual(api.get(BASE + "prepayments/", {"program": self.course.pk}).data["summary"]["students"], 2)
        self.assertEqual(api.get(BASE + "prepayments/", {"status": "x"}).status_code, 400)
        self.assertEqual(self.client_for(self.manager).get(BASE + "prepayments/").status_code, 403)
        self.assertEqual(self.client_for(self.director).get(BASE + "prepayments/").status_code, 200)
