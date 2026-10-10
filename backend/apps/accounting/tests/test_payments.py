"""Выплаты, корректировки и жизненный цикл начисления (ТЗ §8, §12)."""
from __future__ import annotations

from apps.accounting.models import Payroll, PayrollAdjustment, PayrollAuditLog, PayrollPayment, SalaryRule
from apps.accounting.services import AccountingError
from apps.accounting.services.approval_service import (
    approve_payroll,
    create_adjustment,
    decide_adjustment,
    reopen_payroll,
    return_payroll,
)
from apps.accounting.services.payment_service import register_payment, void_payment
from apps.accounting.tests.base import MONTH, D, AccountingFixture, day


class PaymentTests(AccountingFixture):
    def setUp(self):
        super().setUp()
        profile = self.profile()
        self.rule(profile, SalaryRule.RuleType.FIXED, amount=D("20000"))  # оклад за месяц
        self.payroll = self.calc(MONTH)

    def approve(self):
        return approve_payroll(self.payroll, self.director)

    def pay(self, amount, **kw):
        return register_payment(self.payroll, amount=D(amount), payment_date=day(9, 20), actor=self.accountant, **kw)

    def test_full_payment(self):
        self.approve()
        self.pay("20000")
        self.payroll.refresh_from_db()
        self.assertEqual(self.payroll.status, Payroll.Status.PAID)
        self.assertEqual(self.payroll.amount_due, D("0"))

    def test_partial_payment(self):
        self.approve()
        self.pay("10000", is_advance=True)
        self.payroll.refresh_from_db()
        self.assertEqual(self.payroll.status, Payroll.Status.PARTIALLY_PAID)
        self.assertEqual(self.payroll.amount_due, D("10000"))

    def test_several_payments(self):
        self.approve()
        self.pay("10000")
        self.pay("10000")
        self.payroll.refresh_from_db()
        self.assertEqual(self.payroll.total_paid, D("20000"))
        self.assertEqual(self.payroll.status, Payroll.Status.PAID)

    def test_cannot_pay_more_than_due(self):
        self.approve()
        self.pay("15000")
        with self.assertRaises(AccountingError) as ctx:
            self.pay("5000.01")
        self.assertEqual(ctx.exception.code, "exceeds_due")
        self.assertEqual(PayrollPayment.objects.count(), 1)

    def test_repeated_request_is_idempotent(self):
        self.approve()
        first, created = self.pay("5000", idempotency_key="abc-1")
        again, created_again = self.pay("5000", idempotency_key="abc-1")
        self.assertTrue(created)
        self.assertFalse(created_again)
        self.assertEqual(first.pk, again.pk)
        self.payroll.refresh_from_db()
        self.assertEqual(self.payroll.total_paid, D("5000"))

    def test_same_document_number_rejected(self):
        self.approve()
        self.pay("5000", reference="PP-17")
        with self.assertRaises(AccountingError):
            self.pay("5000", reference="PP-17")

    def test_void_payment(self):
        self.approve()
        payment, _ = self.pay("20000")
        void_payment(payment, actor=self.accountant, reason="перевод не прошёл")
        self.payroll.refresh_from_db()
        payment.refresh_from_db()
        self.assertEqual(payment.status, PayrollPayment.Status.VOID)
        self.assertEqual(self.payroll.status, Payroll.Status.APPROVED)
        self.assertEqual(self.payroll.amount_due, D("20000"))
        self.assertTrue(PayrollAuditLog.objects.filter(entity_type="payrollpayment", action="void").exists())
        with self.assertRaises(Exception):
            payment.delete()
        with self.assertRaises(AccountingError):
            void_payment(payment, actor=self.accountant, reason="ещё раз")

    def test_void_requires_reason(self):
        self.approve()
        payment, _ = self.pay("100")
        with self.assertRaises(AccountingError):
            void_payment(payment, actor=self.accountant, reason=" ")

    def test_payment_on_unapproved_payroll(self):
        with self.assertRaises(AccountingError) as ctx:
            self.pay("100")
        self.assertEqual(ctx.exception.code, "not_approved")

    def test_zero_or_negative_amount(self):
        self.approve()
        for amount in ("0", "-5"):
            with self.assertRaises(AccountingError):
                self.pay(amount)

    def test_balance_formula_with_adjustments(self):
        create_adjustment(self.payroll, kind="BONUS", amount=D("3000"), reason="премия", actor=self.accountant)
        self.approve()
        self.pay("13000")
        self.payroll.refresh_from_db()
        # Остаток = 20000 начислено + 3000 корректировка − 13000 выплачено (корректировка не удваивается).
        self.assertEqual(self.payroll.amount_due, D("10000"))
        # Корректировка утверждённого начисления ждёт решения директора.
        adj = create_adjustment(self.payroll, kind="DEDUCTION", amount=D("1000"), reason="штраф", actor=self.accountant)
        self.assertEqual(adj.status, PayrollAdjustment.Status.PENDING)
        self.payroll.refresh_from_db()
        self.assertEqual(self.payroll.amount_due, D("10000"))
        decide_adjustment(adj, approve=True, actor=self.director)
        self.payroll.refresh_from_db()
        self.assertEqual(self.payroll.amount_due, D("9000"))

    def test_deduction_cannot_make_due_negative(self):
        self.approve()
        self.pay("20000")
        adj = create_adjustment(self.payroll, kind="DEDUCTION", amount=D("1"), reason="штраф", actor=self.accountant)
        with self.assertRaises(AccountingError):
            decide_adjustment(adj, approve=True, actor=self.director)

    def test_cannot_pay_yourself(self):
        self.approve()
        with self.assertRaises(AccountingError):
            register_payment(self.payroll, amount=D("1"), payment_date=day(9, 20), actor=self.trainer_user)


class LifecycleTests(AccountingFixture):
    def setUp(self):
        super().setUp()
        self.rule(self.profile(), SalaryRule.RuleType.FIXED, amount=D("20000"))
        self.payroll = self.calc(MONTH)

    def test_return_and_recalculate(self):
        return_payroll(self.payroll, self.director, "проверьте ставку")
        self.payroll.refresh_from_db()
        self.assertEqual(self.payroll.status, Payroll.Status.RETURNED)
        with self.assertRaises(AccountingError):
            approve_payroll(self.payroll, self.director)
        self.assertEqual(self.calc(MONTH).status, Payroll.Status.CALCULATED)

    def test_reopen_only_without_payments(self):
        approve_payroll(self.payroll, self.director)
        register_payment(self.payroll, amount=D("1000"), payment_date=day(9, 20), actor=self.accountant)
        with self.assertRaises(AccountingError):
            reopen_payroll(self.payroll, self.director, "ошибка")

    def test_reopen_keeps_history(self):
        approve_payroll(self.payroll, self.director)
        reopen_payroll(self.payroll, self.director, "ошибка в ставке")
        actions = list(PayrollAuditLog.objects.filter(payroll=self.payroll).values_list("action", flat=True))
        self.assertIn("approve", actions)
        self.assertIn("reopen", actions)

    def test_cannot_approve_own_payroll(self):
        with self.assertRaises(AccountingError):
            approve_payroll(self.payroll, self.trainer_user)

    def test_payroll_cannot_be_deleted(self):
        with self.assertRaises(Exception):
            self.payroll.delete()
        with self.assertRaises(Exception):
            Payroll.objects.all().delete()
        self.assertEqual(Payroll.objects.count(), 1)

    def test_audit_entries_are_immutable(self):
        entry = PayrollAuditLog.objects.first()
        entry.action = "forged"
        with self.assertRaises(Exception):
            entry.save()
        with self.assertRaises(Exception):
            entry.delete()
