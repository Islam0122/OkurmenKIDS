"""Одновременная обработка — настоящие параллельные транзакции PostgreSQL
(блокировка профиля `select_for_update`, уникальные индексы). На SQLite
пропускается: там нет построчных блокировок."""
from __future__ import annotations

import datetime as dt
import threading
from decimal import Decimal
from unittest import skipUnless

from django.db import close_old_connections, connection
from django.test import TransactionTestCase

from apps.accounting.models import StudentPayment
from apps.billing.models import Invoice, LessonConsumption, LessonPackage, PaymentAllocation
from apps.billing.services import BillingError, invoices, lessons, payments
from apps.billing.services.ledger import credit_balance
from apps.billing.services.reports import reconcile
from apps.billing.tests.base import BillingMixin, D


def run_parallel(*targets):
    barrier = threading.Barrier(len(targets))
    errors, results = [], []

    def wrap(target):
        def worker():
            try:
                barrier.wait(timeout=10)
                results.append(target())
            except Exception as exc:  # noqa: BLE001 — собираем для проверки в тесте
                errors.append(exc)
            finally:
                close_old_connections()
        return worker

    threads = [threading.Thread(target=wrap(t)) for t in targets]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    return results, errors


@skipUnless(connection.vendor == "postgresql", "needs real concurrent transactions (PostgreSQL)")
class ConcurrencyTests(BillingMixin, TransactionTestCase):
    def setUp(self):
        self.build()

    def test_same_idempotency_key_in_parallel_creates_one_payment(self):
        profile = self.profile()

        def pay():
            return payments.record_payment(profile=profile, amount="4000", received_date=self.today,
                                           actor=self.accountant, idempotency_key="same-key")

        results, errors = run_parallel(pay, pay, pay)
        self.assertEqual(errors, [])
        self.assertEqual(StudentPayment.objects.count(), 1)
        self.assertEqual(sum(1 for _p, created in results if created), 1)
        invoice = Invoice.objects.get(profile=profile)
        self.assertEqual((invoice.amount_paid, invoice.status), (D("4000"), "PAID"))

    def test_parallel_payments_never_overpay_invoice(self):
        profile = self.profile()

        def pay():
            return payments.record_payment(profile=profile, amount="3000", received_date=self.today,
                                           actor=self.accountant)

        _results, errors = run_parallel(pay, pay)
        self.assertEqual(errors, [])
        invoice = Invoice.objects.get(profile=profile)
        self.assertEqual((invoice.amount_paid, invoice.status), (D("4000"), "PAID"))
        self.assertEqual(credit_balance(profile.pk), D("2000"))
        self.assertEqual(PaymentAllocation.objects.filter(status="ACTIVE").count(), 2)
        self.assertEqual(reconcile(), [])

    def test_parallel_consumption_of_same_lesson(self):
        profile = self.profile()
        lesson = self.lesson(day=self.start)

        results, errors = run_parallel(*[lambda: lessons.sync_lesson(lesson.pk)] * 4)
        self.assertEqual(errors, [])
        self.assertEqual(LessonConsumption.objects.filter(kind="CONSUME", status="ACTIVE").count(), 1)
        self.assertEqual(LessonPackage.objects.get(profile=profile).lessons_used, 1)

    def test_parallel_completion_creates_single_next_invoice(self):
        profile = self.profile()
        self.hold(11)
        last = self.lesson(day=self.start + dt.timedelta(days=11))

        _r, errors = run_parallel(lambda: lessons.sync_lesson(last.pk), lambda: lessons.sync_lesson(last.pk),
                                  lambda: invoices.create_next_package_invoice(profile, activate=True))
        self.assertEqual([e for e in errors if not isinstance(e, BillingError)], [])
        self.assertEqual(Invoice.objects.filter(profile=profile).count(), 2)
        self.assertEqual(LessonPackage.objects.filter(profile=profile, status="ACTIVE").count(), 1)

    def test_parallel_refund_and_allocation_do_not_spend_credit_twice(self):
        profile = self.profile()
        payment, _ = payments.record_payment(profile=profile, amount="4000", received_date=self.today,
                                             actor=self.accountant, auto_allocate=False)

        _r, errors = run_parallel(
            lambda: payments.refund_payment(payment, actor=self.accountant, amount="4000", reason="Возврат"),
            lambda: payments.apply_available_credit(profile, actor=self.accountant),
        )
        self.assertEqual(credit_balance(profile.pk), Decimal("0.00"))
        refunded = StudentPayment.objects.filter(kind="refund").count()
        allocated = PaymentAllocation.objects.filter(status="ACTIVE").count()
        # Ровно одна операция получила деньги; вторая — либо ошибка, либо пустая.
        self.assertEqual(refunded + allocated, 1, errors)
        self.assertEqual(reconcile(), [])
