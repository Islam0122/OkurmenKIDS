"""Аудит «Остатка предоплаты за обучение» (services/prepayments.py).

Тестовая база, реальные данные не трогаются. Два вида тестов:

* обычные — фиксируют проверенное поведение (инварианты без двойного учёта,
  совпадение карточек и таблицы, сценарии A–E на модели 60 000 / 4 месяца);
* `expectedFailure` — найденные ошибки: в тесте записано ПРАВИЛЬНОЕ поведение,
  сейчас он падает. После исправления тест станет «unexpected success» —
  декоратор нужно будет снять.
"""
from __future__ import annotations

import datetime as dt
import unittest
from decimal import Decimal

from apps.accounting.models import StudentPayment
from apps.billing.models import CreditLedgerEntry, PaymentAllocation, PaymentMode, ReservationAllocation
from apps.billing.services import contracts, invoices, payments, prepayments, pricing, profiles, reservations
from apps.billing.tests.base import D
from apps.billing.tests.test_contracts import BASE
from apps.billing.tests.test_periods import OCT24
from apps.billing.tests.test_prepayments import SEP1, PrepaymentFixture

SEP2 = dt.date(2026, 9, 2)


class AuditFixture(PrepaymentFixture):
    def assert_no_double_count(self, profile, row):
        """Одни и те же деньги — ровно в одном месте."""
        profile.refresh_from_db()
        s = contracts.money_summary(profile)
        retention = -sum((e.amount for e in CreditLedgerEntry.objects.filter(
            profile=profile, kind=CreditLedgerEntry.Kind.RETENTION)), D("0"))
        # Журнал аванса сходится с платежами и распределениями.
        self.assertEqual(s["credit"], s["net_received"] - s["allocated"] - retention)
        if row is None:
            return
        self.assertEqual(row["prepayment"], row["unallocated"] + row["allocated_future"])
        self.assertEqual(row["applied_to_studied"] + row["allocated_future"], s["allocated"])
        self.assertEqual(row["unallocated"] + row["reservation_held"], max(s["credit"], D("0")))

    def started(self, lessons):
        """Провести `lessons` уроков IT группы B начиная со 2 сентября (сегодня — 24 октября)."""
        self.at(OCT24)
        self.hold(lessons, start_day=SEP2, group=self.group_b)


# ---------------------------------------------------------------------------
# Проверенное поведение
# ---------------------------------------------------------------------------

class VerifiedTests(AuditFixture):
    def test_full_course_paid_case_a_shape(self):
        """Случай A: «4 из 4» = оплачены 4 месяца (начисление «Весь курс» PAID),
        а не пройдены; остаток = доля ещё не начатых месяцев."""
        profile = self.new(payment_mode=PaymentMode.FULL_PREPAY)
        self.pay(profile, "60000", on=SEP1)
        self.started(13)  # месяц 1 пройден, месяц 2 начат
        row = self.row(profile)
        self.assertEqual((row["paid_months"], row["duration_months"]), (4, 4))
        self.assertEqual((row["received"], row["applied_to_studied"], row["prepayment"]),
                         (D("60000"), D("30000"), D("30000")))
        self.assertEqual(row["status"], prepayments.FULL)
        self.assertTrue(contracts.money_summary(profile)["course_paid_in_full"])
        self.assert_no_double_count(profile, row)

    def test_monthly_two_paid_rest_in_credit_case_b(self):
        """Случаи B/C: 2 оплаченных месяца + аванс на месяцы 3–4."""
        profile = self.new()
        self.pay(profile, "60000", on=SEP1)
        self.started(12)  # месяц 2 выставлен и оплачен из аванса
        row = self.row(profile)
        self.assertEqual((row["paid_months"], row["applied_to_studied"], row["unallocated"], row["prepayment"]),
                         (2, D("30000"), D("30000"), D("30000")))
        self.assertEqual((row["next_covered_month"], row["status"]), (3, prepayments.FULL))
        self.assert_no_double_count(profile, row)

    def test_price_reduced_after_two_months_case_e(self):
        """Случай E: месяцы не обязаны стоить одинаково. 60 000 → 54 000 после
        выставления месяцев 1–2 (по 15 000): месяцы 3–4 по 12 000, остаток 24 000."""
        profile = self.new()
        self.pay(profile, "30000", on=SEP1)
        self.started(12)
        profiles.request_course_terms_change(profile, actor=self.accountant, discount_enabled=True,
                                             final_course_price="54000", reason="Скидка")
        self.pay(profile, "24000", on=OCT24)
        row = self.row(profile)
        self.assertEqual((row["contract_total"], row["received"], row["applied_to_studied"], row["prepayment"]),
                         (D("54000"), D("54000"), D("30000"), D("24000")))
        self.assertEqual((row["paid_months"], row["status"]), (2, prepayments.FULL))
        schedule = contracts.payment_schedule(profile)
        self.assertEqual([m["amount"] for m in schedule["months"]], [D("15000"), D("15000"), D("12000"), D("12000")])
        self.assertTrue(schedule["consistent"])
        self.assert_no_double_count(profile, row)

    def test_partial_course_payment_is_partial(self):
        profile = self.new(payment_mode=PaymentMode.FULL_PREPAY)
        self.pay(profile, "30000", on=SEP1)
        row = self.row(profile)
        self.assertEqual((row["prepayment"], row["remaining_obligations"], row["status"]),
                         (D("30000"), D("60000"), prepayments.PARTIAL))
        self.assertFalse(contracts.money_summary(profile)["course_paid_in_full"])
        self.assert_no_double_count(profile, row)

    def test_future_months_allocated_by_prepay_packages(self):
        profile = self.new()
        self.pay(profile, "45000", on=SEP1, prepay_packages=2)
        row = self.row(profile)
        self.assertEqual((row["allocated_future"], row["unallocated"], row["applied_to_studied"], row["paid_months"]),
                         (D("30000"), D("0"), D("15000"), 3))
        self.assert_no_double_count(profile, row)

    def test_refund_and_reversal_leave_no_trace(self):
        profile = self.new()
        kept = self.pay(profile, "40000", on=SEP1)
        wrong = self.pay(profile, "20000", on=SEP1)
        payments.reverse_payment(wrong, actor=self.accountant, reason="Повторный ввод")
        payments.refund_payment(kept, actor=self.accountant, amount="5000", reason="Вернули часть")
        row = self.row(profile)
        self.assertEqual((row["received"], row["unallocated"]), (D("35000"), D("20000")))
        self.assert_no_double_count(profile, row)

    def test_price_cut_below_invoiced_is_blocked(self):
        """Смена стоимости после полной оплаты курса: снизить итоговую ниже уже
        начисленного нельзя (нужна корректировка начисления) — переплата не
        возникает «сама»; повысить выше стандартной тоже нельзя без скидки."""
        from apps.billing.services import BillingError

        profile = self.new(payment_mode=PaymentMode.FULL_PREPAY)
        self.pay(profile, "60000", on=SEP1)
        with self.assertRaises(BillingError):
            profiles.request_course_terms_change(profile, actor=self.accountant, discount_enabled=True,
                                                 final_course_price="54000", reason="Скидка после оплаты")
        with self.assertRaises(BillingError):
            profiles.request_course_terms_change(profile, actor=self.accountant, discount_enabled=False,
                                                 final_course_price="64000", reason="Повышение")
        self.assertEqual(self.row(profile)["status"], prepayments.FULL)

    def test_cards_equal_table_with_mixed_rows(self):
        a = self.new(payment_mode=PaymentMode.FULL_PREPAY)
        self.pay(a, "60000", on=SEP1)
        b = self.new()
        self.pay(b, "70000", on=SEP1)  # переплата
        data = prepayments.prepayments({})
        rows = data["results"]
        s = data["summary"]
        for key in ("prepayment", "allocated_future", "unallocated", "reservation_held"):
            self.assertEqual(s[key], sum((Decimal(r[key]) for r in rows), D("0")), key)
        self.assertEqual(s["students"], len(rows))
        self.assertEqual(s["full"] + s["partial"] + s["advance"] + s["review"], len(rows))

    def test_balance_is_current_not_historical(self):
        """Факт: показатель не зависит от выбранного периода — API игнорирует
        даты и показывает текущий баланс даже для периода до платежа."""
        profile = self.new()
        self.pay(profile, "40000", on=SEP1)
        api = self.client_for(self.accountant)
        before = api.get(BASE + "prepayments/", {"date_from": "2026-08-01", "date_to": "2026-08-31"}).data
        now = api.get(BASE + "prepayments/").data
        self.assertEqual(before["summary"]["prepayment"], now["summary"]["prepayment"])
        self.assertEqual(now["summary"]["prepayment"], "25000.00")
        self.assertEqual([r["profile"] for r in before["results"]], [profile.pk])


# ---------------------------------------------------------------------------
# Найденные ошибки (тест описывает правильное поведение и сейчас падает)
# ---------------------------------------------------------------------------

class FoundDefectTests(AuditFixture):
    def deposit_after_full_payment(self):
        """Случай D: курс оплачен полностью, затем оплачена бронь «в общую стоимость»."""
        profile = self.new(payment_mode=PaymentMode.FULL_PREPAY, reservation_amount="38000",
                           reservation_allocation=ReservationAllocation.COURSE_TOTAL)
        self.pay(profile, "60000", on=SEP1)
        reservations.record_reservation_payment(profile.reservations.get(), actor=self.accountant, amount="38000",
                                                received_date=SEP1)
        self.started(13)
        return profile

    def test_case_d_reproduction(self):
        """Воспроизведение D: получено 98 000 при договоре 60 000, в остатке —
        только доля будущих месяцев; 38 000 спрятаны в «депозит брони»."""
        profile = self.deposit_after_full_payment()
        row = self.row(profile)
        self.assertEqual((row["contract_total"], row["received"], row["applied_to_studied"], row["prepayment"]),
                         (D("60000"), D("98000"), D("30000"), D("30000")))
        self.assertEqual((row["reservation_held"], row["paid_months"], row["status"], row["review_reasons"]),
                         (D("38000"), 4, prepayments.FULL, []))
        s = contracts.money_summary(profile)
        self.assertEqual(s["credit_unreserved"], D("38000"))  # сводка договора видит лишние деньги
        self.assert_no_double_count(profile, row)

    @unittest.expectedFailure
    def test_deposit_with_no_target_left_needs_review(self):
        """Депозит брони, который уже нечем зачесть (курс оплачен), — переплата:
        нужна проверка бухгалтера (возврат или перенос), а не «Полная предоплата»."""
        row = self.row(self.deposit_after_full_payment())
        self.assertEqual(row["status"], prepayments.REVIEW)

    @unittest.expectedFailure
    def test_overpayment_beyond_contract_is_flagged(self):
        """70 000 при договоре 60 000: 10 000 сверх стоимости договора не должны
        молча входить в «Полную предоплату»."""
        profile = self.new()
        self.pay(profile, "70000", on=SEP1)
        row = self.row(profile)
        self.assertEqual(contracts.money_summary(profile)["credit_unreserved"], D("10000"))
        self.assertTrue(row["status"] == prepayments.REVIEW or row.get("overpayment") == D("10000"))

    @unittest.expectedFailure
    def test_held_deposit_counted_even_without_other_prepayment(self):
        """Карточка «Депозиты брони, ещё не зачтённые» должна включать депозит,
        даже если у ученика нет другой предоплаты (сейчас строка не создаётся)."""
        profile = self.new(reservation_amount="3000", reservation_allocation=ReservationAllocation.COURSE_TOTAL)
        reservations.record_reservation_payment(profile.reservations.get(), actor=self.accountant, amount="3000",
                                                received_date=SEP1)
        self.pay(profile, "15000", on=SEP1)  # месяц 1 оплачен деньгами
        self.assertEqual(contracts.money_summary(profile)["reservation_unused"], D("3000"))
        self.assertEqual(prepayments.prepayments({})["summary"]["reservation_held"], D("3000"))

    @unittest.expectedFailure
    def test_next_covered_month_for_course_prepayment(self):
        """Случай A: месяцы 3–4 оплачены из предоплаты курса, но «Следующий месяц
        из предоплаты» пуст (учитываются только месяцы из свободного аванса)."""
        profile = self.new(payment_mode=PaymentMode.FULL_PREPAY)
        self.pay(profile, "60000", on=SEP1)
        self.started(13)
        self.assertEqual(self.row(profile)["next_covered_month"], 3)

    @unittest.expectedFailure
    def test_next_covered_month_for_prepaid_planned_months(self):
        profile = self.new()
        self.pay(profile, "45000", on=SEP1, prepay_packages=2)
        self.assertEqual(self.row(profile)["next_covered_month"], 2)

    @unittest.expectedFailure
    def test_paid_months_for_partially_paid_course(self):
        """30 000 из 60 000 «Весь курс» закрывают месяцы 1–2 (график договора),
        а «Оплачено месяцев» показывает 0."""
        profile = self.new(payment_mode=PaymentMode.FULL_PREPAY)
        self.pay(profile, "30000", on=SEP1)
        covered = sum(1 for m in contracts.course_coverage(profile)["months"].values() if m["paid"] == m["share"])
        self.assertEqual(covered, 2)
        self.assertEqual(self.row(profile)["paid_months"], 2)

    @unittest.expectedFailure
    def test_unstarted_first_month_same_in_both_modes(self):
        """Месяц 1 без проведённых уроков: при предоплате курса его доля — в
        «предоплате», при помесячной оплате оплаченный месяц 1 — уже «зачтено в
        обучение». Одно и то же событие считается по-разному."""
        course = self.new(payment_mode=PaymentMode.FULL_PREPAY)
        self.pay(course, "60000", on=SEP1)
        monthly = self.new()
        self.pay(monthly, "60000", on=SEP1)
        self.assertEqual(self.row(course)["prepayment"], self.row(monthly)["prepayment"])

    @unittest.expectedFailure
    def test_adjusted_course_future_share_matches_schedule(self):
        """Корректировка «Весь курс»: остаток предоплаты и график договора делят
        курс по месяцам разными формулами (prepayments — только деньги,
        график — деньги + корректировки) и расходятся."""
        profile = self.new(payment_mode=PaymentMode.FULL_PREPAY)
        course = contracts.course_invoice(profile)
        invoices.adjust_invoice(course, actor=self.accountant, amount="6000", reason="Скидка задним числом")
        self.pay(profile, "54000", on=SEP1)
        self.started(13)  # начато 2 месяца
        row = self.row(profile)
        schedule_future = sum((m["share"] - D("0") for k, m in contracts.course_coverage(profile)["months"].items()
                               if k > 2 and m["paid"] == m["share"]), D("0"))
        self.assertEqual(row["allocated_future"], schedule_future)

    @unittest.expectedFailure
    def test_students_counted_once_with_two_contracts(self):
        """«Учеников с предоплатой» считает договоры, а не учеников."""
        english_plan = pricing.create_plan(
            actor=self.accountant, name="English", subject=self.english, course=self.course, lessons_per_package=12,
            package_price=D("10000"), effective_from=SEP1 - dt.timedelta(days=30), duration_months=4,
            payment_deadline_lessons=3,
        )
        student = self.student(self.group_b)
        it = self.new(student=student)
        en = profiles.create_student_billing_profile(student=student, plan=english_plan, actor=self.accountant,
                                                     start_date=SEP1, responsible_accountant=self.accountant)
        self.pay(it, "40000", on=SEP1)
        self.pay(en, "30000", on=SEP1)
        self.assertEqual(prepayments.prepayments({})["summary"]["students"], 1)


class MultiContractTests(AuditFixture):
    def test_money_stays_in_its_own_contract(self):
        english_plan = pricing.create_plan(
            actor=self.accountant, name="English", subject=self.english, course=self.course, lessons_per_package=12,
            package_price=D("10000"), effective_from=SEP1 - dt.timedelta(days=30), duration_months=4,
            payment_deadline_lessons=3,
        )
        student = self.student(self.group_b)
        it = self.new(student=student)
        en = profiles.create_student_billing_profile(student=student, plan=english_plan, actor=self.accountant,
                                                     start_date=SEP1, responsible_accountant=self.accountant)
        self.pay(it, "40000", on=SEP1)
        self.pay(en, "30000", on=SEP1)
        rows = {r["profile"]: r for r in prepayments.prepayments({})["results"]}
        self.assertEqual((rows[it.pk]["received"], rows[it.pk]["prepayment"]), ("40000.00", "25000.00"))
        self.assertEqual((rows[en.pk]["received"], rows[en.pk]["prepayment"]), ("30000.00", "20000.00"))
        self.assertFalse(PaymentAllocation.objects.filter(profile=it, invoice__profile=en).exists())
        self.assertEqual(StudentPayment.objects.filter(billing_profile=it).count(), 1)


class AuditCommandTests(AuditFixture):
    def test_explain_case_d_and_read_only(self):
        import io
        import json

        from django.core.management import call_command

        from apps.billing.models import Invoice

        profile = FoundDefectTests.deposit_after_full_payment(self)
        counts = (StudentPayment.objects.count(), PaymentAllocation.objects.count(), CreditLedgerEntry.objects.count(),
                  Invoice.objects.count())
        out = io.StringIO()
        call_command("billing_prepayment_audit", profile=profile.pk, stdout=out)
        (data,) = json.loads(out.getvalue())
        self.assertEqual(data["summary"]["credit_unreserved"], "38000.00")
        self.assertEqual([p["purpose"] for p in data["payments"]], ["tuition", "reservation"])
        self.assertEqual(data["payments"][1]["unallocated"], "38000.00")
        self.assertTrue(any("нечем зачесть" in f or "зачесть его не во что" in f for f in data["findings"]))
        self.assertEqual(counts, (StudentPayment.objects.count(), PaymentAllocation.objects.count(),
                                  CreditLedgerEntry.objects.count(), Invoice.objects.count()))
