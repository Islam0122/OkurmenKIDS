"""Управление платежами бухгалтером: исправление даты, суммы, договора и
распределения, аннулирование, чек, права, аудит, повтор и параллельность."""
from __future__ import annotations

import datetime as dt
from unittest import skipUnless

from django.core.exceptions import ValidationError
from django.db import connection
from django.test import TransactionTestCase
from django.utils import timezone

from apps.accounting.models import PayrollAuditLog, PayrollPeriod, StudentPayment
from apps.billing.models import CreditLedgerEntry, Invoice, PaymentMode, Receipt
from apps.billing.services import BillingError, analytics, contracts, corrections, payments, periods
from apps.billing.services.reports import reconcile
from apps.billing.tests.base import BillingMixin, D
from apps.billing.tests.test_concurrency import run_parallel
from apps.billing.tests.test_contracts import BASE
from apps.billing.tests.test_periods import OCT24, SEP1, PeriodFixture

SEP8 = dt.date(2026, 9, 8)


class CorrectionFixture(PeriodFixture):
    def setUp(self):
        super().setUp()
        self.profile = self.contract(start_date=SEP1, payment_mode=PaymentMode.FULL_PREPAY, discount_enabled=True,
                                     final_course_price="53000", discount_reason="Скидка 7 000")
        # Ошибка ввода: деньги получены 08.09, а платёж записан датой 24.10.
        self.payment = payments.record_payment(profile=self.profile, amount="53000", received_date=OCT24,
                                               actor=self.accountant)[0]
        self.receipt = self.payment.receipt

    def month(self, value):
        first, last = periods.month_bounds(value)
        return periods.period_report({}, date_from=first, date_to=last)

    def correct(self, user=None, **body):
        return self.client_for(user or self.accountant).post(
            BASE + f"payments/{self.payment.pk}/correct/", body, format="json")


class DateCorrectionTests(CorrectionFixture):
    def test_october_to_september_moves_money_not_accrual(self):
        self.assertEqual((self.month("2026-09")["received"]["gross"], self.month("2026-10")["received"]["gross"]),
                         ("0.00", "53000.00"))
        response = self.correct(received_date="2026-09-08", reason="Деньги получены 08.09, внесены 24.10")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual((response.data["changed"], response.data["payment"]["received_date"]),
                         (["received_date"], "2026-09-08"))
        # Тот же платёж и тот же чек (номер не меняется), новых записей нет.
        self.assertEqual((StudentPayment.objects.count(), Receipt.objects.count()), (1, 1))
        receipt = Receipt.objects.get(pk=self.receipt.pk)
        self.assertEqual(receipt.number, self.receipt.number)
        self.assertEqual(receipt.snapshot["received_date"], "2026-09-08")
        self.assertEqual(receipt.snapshot["history"][0]["snapshot"]["received_date"], "2026-10-24")
        # Отчёты по дате поступления пересчитаны, период начисления — прежний.
        sep, oct_ = self.month("2026-09"), self.month("2026-10")
        self.assertEqual((sep["received"]["gross"], sep["received"]["for_current_period"], oct_["received"]["gross"]),
                         ("53000.00", "53000.00", "0.00"))
        self.assertEqual(sep["debt"]["closing"], "0.00")
        self.assertEqual(analytics.finance_analytics({}, date_from=SEP1, date_to=dt.date(2026, 9, 30))
                         ["received"]["gross"], "53000.00")
        (course,) = self.live_invoices(self.profile)
        self.assertEqual((course.period_date, course.status), (SEP1, Invoice.Status.PAID))
        self.payment.refresh_from_db()
        self.assertEqual(timezone.localdate(self.payment.created_at), OCT24)  # дата записи — отдельно

    def test_history_keeps_old_values_and_audit_is_append_only(self):
        self.correct(received_date="2026-09-08", method="bank", reason="Перевод, получен 08.09")
        log = PayrollAuditLog.objects.get(action="billing_payment_correct", entity_id=self.payment.pk)
        self.assertEqual((log.old_values["received_date"], log.new_values["received_date"]), ("2026-10-24", "2026-09-08"))
        self.assertEqual((log.old_values["method"], log.new_values["method"]), ("cash", "bank"))
        self.assertEqual((log.actor_id, log.reason, log.new_values["receipt_id"]),
                         (self.accountant.pk, "Перевод, получен 08.09", self.receipt.pk))
        history = self.client_for(self.director).get(BASE + f"payments/{self.payment.pk}/history/").data
        actions = [h["action"] for h in history]
        self.assertIn("billing_payment_correct", actions)
        self.assertIn("billing_receipt_update", actions)
        self.assertIn("billing_allocate", actions)
        with self.assertRaises(ValidationError):
            log.delete()
        with self.assertRaises(ValidationError):
            PayrollAuditLog.objects.filter(pk=log.pk).delete()

    def test_resubmitting_same_form_changes_nothing(self):
        body = {"received_date": "2026-09-08", "reason": "Двойной клик"}
        first, second = self.correct(**body), self.correct(**body)
        self.assertEqual((first.data["changed"], second.data["changed"]), (["received_date"], []))
        self.assertEqual(PayrollAuditLog.objects.filter(action="billing_payment_correct").count(), 1)

    def test_future_date_and_missing_reason_rejected(self):
        self.assertEqual(self.correct(received_date="2026-10-25", reason="x").status_code, 400)
        self.assertEqual(self.correct(received_date="2026-09-08").status_code, 400)

    def test_closed_payroll_period_requires_confirmation(self):
        PayrollPeriod.objects.create(year=2026, month=9, period_type=PayrollPeriod.PeriodType.MONTH,
                                     status=PayrollPeriod.Status.CLOSED)
        refused = self.correct(received_date="2026-09-08", reason="x")
        self.assertEqual((refused.status_code, refused.data["code"]), (400, "closed_period"))
        ok = self.correct(received_date="2026-09-08", reason="x", confirm_closed_period=True)
        self.assertEqual((ok.status_code, len(ok.data["warnings"])), (200, 1))
        log = PayrollAuditLog.objects.get(action="billing_payment_correct")
        self.assertEqual(log.new_values["closed_period_warnings"][0]["status"], "CLOSED")

    def test_created_at_only_by_separate_audited_correction(self):
        url = BASE + f"payments/{self.payment.pk}/created-at/"
        response = self.client_for(self.accountant).post(
            url, {"created_at": "2026-09-08T10:00:00+06:00", "reason": "Запись внесена в день оплаты"}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.payment.refresh_from_db()
        self.assertEqual(timezone.localdate(self.payment.created_at), SEP8)
        self.assertTrue(PayrollAuditLog.objects.filter(action="billing_payment_created_at").exists())
        self.assertEqual(self.payment.received_date, OCT24)  # дата денег не тронута


class AmountAndAllocationTests(CorrectionFixture):
    def test_amount_decrease_needs_reallocation_and_reissues_receipt(self):
        (course,) = self.live_invoices(self.profile)
        self.assertEqual(self.correct(amount="50000", reason="Опечатка").data["code"], "exceeds_payment")
        response = self.correct(amount="50000", reason="Опечатка: получено 50 000",
                                allocations=[{"invoice": course.pk, "amount": "50000"}])
        self.assertEqual(response.status_code, 200, response.data)
        course.refresh_from_db()
        self.assertEqual((course.status, course.balance), (Invoice.Status.PARTIALLY_PAID, D("3000")))
        s = contracts.money_summary(self.profile)
        self.assertEqual((s["received"], s["allocated"], s["credit"], s["due_now"]),
                         (D("50000"), D("50000"), D("0"), D("3000")))
        receipt = Receipt.objects.get(pk=self.receipt.pk)
        self.assertEqual((receipt.number, receipt.snapshot["amount"]), (f"{self.receipt.number}/1", "50000.00"))
        self.assertEqual(receipt.snapshot["history"][0]["number"], self.receipt.number)
        self.assertTrue(CreditLedgerEntry.objects.filter(kind="PAYMENT_ADJUST", amount=D("-3000")).exists())
        self.assertEqual(reconcile(), [])

    def test_amount_increase_goes_to_open_invoices_then_credit(self):
        self.correct(amount="55000", reason="Получено 55 000")
        s = contracts.money_summary(self.profile)
        self.assertEqual((s["received"], s["allocated"], s["credit"]), (D("55000"), D("53000"), D("2000")))

    def test_transfer_to_correct_student(self):
        other = self.contract(student=self.student(self.group_b), start_date=OCT24)  # месяц 1 = 15 000
        response = self.correct(profile=other.pk, reason="Платёж другого студента")
        self.assertEqual(response.status_code, 200, response.data)
        self.payment.refresh_from_db()
        self.assertEqual((self.payment.billing_profile_id, self.payment.student_id), (other.pk, other.student_id))
        old, new = contracts.money_summary(self.profile), contracts.money_summary(other)
        self.assertEqual((old["received"], old["credit"], old["due_now"]), (D("0"), D("0"), D("53000")))
        self.assertEqual((new["received"], new["allocated"], new["credit"]), (D("53000"), D("15000"), D("38000")))
        receipt = Receipt.objects.get(pk=self.receipt.pk)
        self.assertEqual((receipt.profile_id, receipt.number), (other.pk, f"{self.receipt.number}/1"))
        self.assertEqual(reconcile(), [])


class VoidTests(CorrectionFixture):
    def test_void_restores_debt_and_cannot_repeat(self):
        api = self.client_for(self.accountant)
        url = BASE + f"payments/{self.payment.pk}/reverse/"
        self.assertEqual(api.post(url, {}, format="json").status_code, 400)  # причина обязательна
        self.assertEqual(api.post(url, {"reason": "Ошибочный платёж"}, format="json").status_code, 200)
        self.payment.refresh_from_db()
        self.assertEqual((self.payment.status, Receipt.objects.get(pk=self.receipt.pk).status),
                         ("void", Receipt.Status.CANCELLED))
        (course,) = self.live_invoices(self.profile)
        s = contracts.money_summary(self.profile)
        self.assertEqual((course.status, s["received"], s["credit"], s["due_now"], s["allocated"]),
                         (Invoice.Status.OPEN, D("0"), D("0"), D("53000"), D("0")))
        again = api.post(url, {"reason": "ещё раз"}, format="json")
        self.assertEqual((again.status_code, again.data["code"]), (400, "bad_status"))
        self.assertEqual(self.correct(received_date="2026-09-08", reason="x").status_code, 400)
        self.assertEqual(StudentPayment.objects.count(), 1)  # ничего не удалено
        self.assertEqual(len(self.live_invoices(self.profile)), 1)  # договор и начисления на месте


class PermissionTests(CorrectionFixture):
    def test_manager_and_director_cannot_change_payments(self):
        for user in (self.manager, self.director):
            for url, body in ((f"payments/{self.payment.pk}/correct/", {"received_date": "2026-09-08", "reason": "x"}),
                              (f"payments/{self.payment.pk}/reverse/", {"reason": "x"}),
                              (f"payments/{self.payment.pk}/created-at/",
                               {"created_at": "2026-09-08T10:00:00+06:00", "reason": "x"})):
                self.assertEqual(self.client_for(user).post(BASE + url, body, format="json").status_code, 403, url)
        with self.assertRaises(BillingError):
            corrections.correct_payment(self.payment, actor=self.director, received_date=SEP8, reason="x")
        self.payment.refresh_from_db()
        self.assertEqual((self.payment.received_date, self.payment.status), (OCT24, "confirmed"))
        director = self.client_for(self.director)
        self.assertEqual(director.get(BASE + f"payments/{self.payment.pk}/").status_code, 200)  # просмотр
        self.assertEqual(director.get(BASE + f"payments/{self.payment.pk}/history/").status_code, 200)
        self.assertEqual(self.client_for(self.manager).get(BASE + "payments/").status_code, 403)

    def test_admin_page_actions_respect_service_permissions(self):
        """Django Admin — системное управление: директор (только просмотр, раздел
        «Финансы») и менеджер туда не попадают даже прямым POST."""
        from django.test import Client

        for user in (self.director, self.manager):
            client = Client()
            client.force_login(user)
            url = f"/admin/accounting/studentpayment/{self.payment.pk}/manage/"
            self.assertEqual(client.get(url).status_code, 302)
            client.post(url, {"action": "void", "confirm": "on", "reason": "x"})
            client.post(url, {"action": "correct", "received_date": "2026-09-08", "reason": "x"})
        self.payment.refresh_from_db()
        self.assertEqual((self.payment.status, self.payment.received_date), ("confirmed", OCT24))

    def test_admin_page_for_accountant_with_admin_access(self):
        from django.test import Client

        client = Client()
        client.force_login(self.admin)  # суперпользователь = администратор оплаты
        url = f"/admin/accounting/studentpayment/{self.payment.pk}/manage/"
        self.assertContains(client.get(url), self.receipt.number)
        client.post(url, {"action": "correct", "received_date": "2026-09-08", "amount": "53000.00", "method": "",
                          "reference": "", "comment": "", "purpose": "", "allocations": "", "reason": "Дата 08.09"})
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.received_date, SEP8)
        # Повторная печать: PDF, счётчик +1, ни платежа, ни чека не прибавилось.
        pdf = client.post(url, {"action": "reprint"})
        self.assertEqual((pdf.status_code, pdf["Content-Type"]), (200, "application/pdf"))
        self.assertEqual(Receipt.objects.get(pk=self.receipt.pk).print_count, 1)
        self.assertEqual((StudentPayment.objects.count(), Receipt.objects.count()), (1, 1))
        client.post(url, {"action": "void", "confirm": "on", "reason": "Ошибочный"})
        client.post(url, {"action": "void", "confirm": "on", "reason": "Ещё раз"})  # второй раз — сообщение об ошибке
        self.assertEqual(PayrollAuditLog.objects.filter(action="billing_payment_reverse").count(), 1)
        changelist = client.get("/admin/accounting/studentpayment/", {"q": self.receipt.number})
        self.assertContains(changelist, f"/admin/accounting/studentpayment/{self.payment.pk}/manage/")
        self.assertContains(client.get("/admin/accounting/studentpayment/", {"q": str(self.payment.pk)}),
                            self.receipt.number)
        self.assertEqual(client.get("/admin/accounting/studentpayment/", {"received_month": "2026-09"}).status_code, 200)

    def test_search_by_payment_and_receipt_number_and_month(self):
        api = self.client_for(self.accountant)
        self.assertEqual(api.get(BASE + "payments/", {"number": self.receipt.number}).data["count"], 1)
        self.assertEqual(api.get(BASE + "payments/", {"number": str(self.payment.pk)}).data["count"], 1)
        self.assertEqual(api.get(BASE + "payments/", {"month": "2026-09"}).data["count"], 0)
        self.assertEqual(api.get(BASE + "payments/", {"month": "2026-10"}).data["count"], 1)


@skipUnless(connection.vendor == "postgresql", "needs real concurrent transactions (PostgreSQL)")
class ParallelCorrectionTests(BillingMixin, TransactionTestCase):
    def setUp(self):
        self.build()

    def test_parallel_void_and_correct_stay_consistent(self):
        profile = self.profile()
        payment = payments.record_payment(profile=profile, amount="4000", received_date=self.today,
                                          actor=self.accountant)[0]

        def void():
            return payments.reverse_payment(payment, actor=self.accountant, reason="ошибка")

        def correct():
            return corrections.correct_payment(payment, actor=self.accountant, amount="4500", reason="сумма")

        _results, errors = run_parallel(void, void, correct)
        self.assertTrue(all(isinstance(e, BillingError) for e in errors))
        self.assertEqual(PayrollAuditLog.objects.filter(action="billing_payment_reverse").count(), 1)
        payment.refresh_from_db()
        self.assertEqual(payment.status, "void")
        self.assertEqual(reconcile(), [])
