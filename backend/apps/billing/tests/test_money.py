"""Платежи, аванс, бронь, скидки, просрочки, деактивация, возвраты."""
from __future__ import annotations

import datetime as dt

from django.db import IntegrityError, transaction
from django.test import override_settings

from apps.academy.models import Student
from apps.academy.services.student_status import deactivate_student, pause_student, continue_student
from apps.accounting.models import StudentPayment
from apps.billing.models import (
    BillingNotification,
    BillingTask,
    BillingTermsChange,
    CreditLedgerEntry,
    DiscountType,
    Invoice,
    LessonConsumption,
    PaymentAllocation,
    StudentBillingProfile,
)
from apps.billing.services import BillingError, invoices, payments, pricing, profiles, reservations
from apps.billing.services.ledger import payment_unallocated
from apps.billing.services.reports import reconcile
from apps.billing.tests.base import D, BillingFixture


class PaymentScenarioTests(BillingFixture):
    def pay(self, profile, amount, **kwargs):
        return payments.record_payment(profile=profile, amount=amount, received_date=self.today, actor=self.accountant,
                                       **kwargs)[0]

    def test_a_full_payment(self):
        profile = self.profile()
        payment = self.pay(profile, "4000")
        invoice = self.invoices(profile)[0]
        self.assertEqual((invoice.balance, invoice.status), (D("0"), Invoice.Status.PAID))
        self.assertEqual(payment.amount, D("4000"))
        self.assertEqual(self.credit(profile), D("0"))
        self.assertFalse(BillingTask.objects.filter(invoice=invoice, status__in=BillingTask.LIVE_STATUSES).exists())
        self.assertEqual(BillingTask.objects.get(invoice=invoice).status, BillingTask.Status.DONE)

    def test_b_partial_payment(self):
        profile = self.profile()
        self.pay(profile, "2500")
        invoice = self.invoices(profile)[0]
        self.assertEqual((invoice.amount_paid, invoice.balance), (D("2500"), D("1500")))
        self.assertEqual(invoice.status, Invoice.Status.PARTIALLY_PAID)
        self.pay(profile, "1500")
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, Invoice.Status.PAID)
        self.assertEqual(PaymentAllocation.objects.filter(invoice=invoice).count(), 2)

    def test_c_prepayment_of_three_packages(self):
        profile = self.profile()
        payment = self.pay(profile, "13000", prepay_packages=2)
        invs = self.invoices(profile)
        self.assertEqual(len(invs), 3)
        self.assertTrue(all(i.status == Invoice.Status.PAID for i in invs))
        self.assertEqual(payment.amount, D("13000"))  # сумма платежа не меняется
        self.assertEqual(self.credit(profile), D("1000"))
        self.assertEqual(payment_unallocated(payment.pk), D("1000"))
        self.assertEqual(PaymentAllocation.objects.filter(payment=payment).count(), 3)
        # Пакеты 1–3 проходят без новых начислений; 4-й — новое начисление,
        # аванс 1000 сразу его частично оплачивает.
        self.hold(36)
        invs = self.invoices(profile)
        self.assertEqual(len(invs), 4)
        # Пакет 3 завершён в прошлом (дата урока) — срок 4-го уже прошёл.
        self.assertEqual((invs[3].amount_paid, invs[3].balance, invs[3].status),
                         (D("1000"), D("3000"), Invoice.Status.OVERDUE))
        self.assertEqual(self.credit(profile), D("0"))
        self.assertEqual(reconcile(), [])

    def test_d_reservation_becomes_credit_and_covers_invoice_on_payment_event(self):
        profile = self.profile(reservation_amount="1500")
        reservation = profile.reservations.get()
        self.assertEqual(reservation.status, "PENDING")
        reservation, payment, _ = reservations.record_reservation_payment(
            reservation, actor=self.accountant, amount="1500", received_date=self.today,
        )
        self.assertEqual(payment.purpose, StudentPayment.Purpose.RESERVATION)
        self.assertEqual(self.credit(profile), D("1500"))
        # Бронь — не оплата пакета: начисление по-прежнему открыто.
        self.assertEqual(self.invoices(profile)[0].status, Invoice.Status.OPEN)
        # Платёжное событие (наступил срок) — аванс покрывает начисление частично.
        from apps.billing.tasks import apply_credit_to_due_invoices

        invoice = self.invoices(profile)[0]
        apply_credit_to_due_invoices(on=invoice.due_date)
        invoice.refresh_from_db()
        self.assertEqual((invoice.amount_paid, invoice.status), (D("1500"), Invoice.Status.PARTIALLY_PAID))
        self.assertEqual(self.credit(profile), D("0"))

    def test_d_reservation_larger_than_package_keeps_rest_for_next(self):
        profile = self.profile(reservation_amount="6000")
        reservations.record_reservation_payment(profile.reservations.get(), actor=self.accountant, amount="6000",
                                                received_date=self.today)
        payments.apply_available_credit(profile, actor=self.accountant)
        self.assertEqual(self.invoices(profile)[0].status, Invoice.Status.PAID)
        self.assertEqual(self.credit(profile), D("2000"))
        self.hold(12)
        second = self.invoices(profile)[1]
        self.assertEqual((second.amount_paid, second.balance), (D("2000"), D("2000")))
        self.assertIn(second.status, (Invoice.Status.PARTIALLY_PAID, Invoice.Status.OVERDUE))

    def test_reservation_cancel_refund_and_retention(self):
        profile = self.profile(reservation_amount="2000")
        reservation, payment, _ = reservations.record_reservation_payment(
            profile.reservations.get(), actor=self.accountant, amount="2000", received_date=self.today,
        )
        with self.assertRaises(BillingError):
            reservations.cancel_reservation(reservation, actor=self.accountant, reason="x", refund_amount="2500")
        with self.assertRaises(BillingError):
            reservations.cancel_reservation(reservation, actor=self.manager, reason="x", refund_amount="100")
        reservation = reservations.cancel_reservation(
            reservation, actor=self.accountant, reason="Родители передумали", refund_amount="1500", retain_amount="500",
        )
        self.assertEqual(reservation.status, "CANCELLED")
        self.assertEqual(self.credit(profile), D("0"))
        refund = StudentPayment.objects.get(kind=StudentPayment.Kind.REFUND)
        self.assertEqual((refund.amount, refund.refund_of), (D("1500"), payment))
        self.assertEqual(CreditLedgerEntry.objects.get(kind="RETENTION").amount, D("-500"))

    def test_idempotency_key_returns_same_payment(self):
        profile = self.profile()
        p1, c1 = payments.record_payment(profile=profile, amount="1000", received_date=self.today,
                                         actor=self.accountant, idempotency_key="abc")
        p2, c2 = payments.record_payment(profile=profile, amount="1000", received_date=self.today,
                                         actor=self.accountant, idempotency_key="abc")
        self.assertTrue(c1)
        self.assertFalse(c2)
        self.assertEqual(p1, p2)
        self.assertEqual(self.invoices(profile)[0].amount_paid, D("1000"))
        with self.assertRaises(BillingError):
            payments.record_payment(profile=profile, amount="2000", received_date=self.today, actor=self.accountant,
                                    idempotency_key="abc")

    def test_duplicate_document_number_rejected(self):
        profile = self.profile()
        self.pay(profile, "100", reference="KASSA-1")
        with self.assertRaises(BillingError):
            self.pay(profile, "100", reference="KASSA-1")

    def test_invalid_amounts(self):
        profile = self.profile()
        for bad in ("0", "-5", "10.005", "abc"):
            with self.assertRaises(BillingError):
                self.pay(profile, bad)
        with self.assertRaises(BillingError):
            payments.record_payment(profile=profile, amount="10", received_date=self.today + dt.timedelta(days=1),
                                    actor=self.accountant)

    def test_manual_allocation_cannot_exceed_balance_or_payment(self):
        profile = self.profile()
        payment = self.pay(profile, "5000", auto_allocate=False)
        invoice = self.invoices(profile)[0]
        with self.assertRaises(BillingError):
            payments.allocate_payment(payment, actor=self.accountant, items=[(invoice, D("4500"))])
        payments.allocate_payment(payment, actor=self.accountant, items=[(invoice, D("4000"))])
        self.assertEqual(payment_unallocated(payment.pk), D("1000"))
        self.assertEqual(self.credit(profile), D("1000"))


class DiscountTests(BillingFixture):
    def test_percent_and_fixed_discount_and_custom_price(self):
        percent = self.profile(discount_type=DiscountType.PERCENT, discount_value="10", discount_reason="Брат учится")
        self.assertEqual(self.invoices(percent)[0].amount, D("3600"))
        fixed = self.profile(discount_type=DiscountType.FIXED, discount_value="300", discount_reason="Акция")
        self.assertEqual(self.invoices(fixed)[0].amount, D("3700"))
        custom = self.profile(custom_price="3800", discount_reason="Старый тариф")
        inv = self.invoices(custom)[0]
        self.assertEqual(inv.amount, D("3800"))
        self.assertEqual(inv.snapshot["base_price"], "4000.00")
        self.assertEqual(custom.discount_assigned_by, self.manager)
        self.assertEqual(BillingTermsChange.objects.filter(profile=custom, status="APPROVED").count(), 1)

    def test_validation(self):
        for kwargs in ({"discount_type": "PERCENT", "discount_value": "101"},
                       {"discount_type": "FIXED", "discount_value": "5000"},
                       {"discount_type": "PERCENT", "discount_value": "-1"},
                       {"custom_price": "-10"},
                       {"discount_type": "PERCENT", "discount_value": "5"}):  # без основания
            with self.subTest(kwargs=kwargs), self.assertRaises(BillingError):
                self.profile(**kwargs)
        # Отклонённая регистрация ничего не оставила.
        self.assertFalse(StudentBillingProfile.objects.exists())

    def test_database_constraints_on_discount(self):
        profile = self.profile()
        with self.assertRaises(IntegrityError), transaction.atomic():
            StudentBillingProfile.objects.filter(pk=profile.pk).update(discount_type="PERCENT", discount_value=150)

    def test_discount_above_manager_limit_needs_admin_approval(self):
        profile = self.profile(discount_type=DiscountType.PERCENT, discount_value="30", discount_reason="Многодетная")
        invoice = self.invoices(profile)[0]
        self.assertEqual((invoice.status, invoice.amount), (Invoice.Status.DRAFT, D("4000")))
        self.assertEqual(profile.discount_type, DiscountType.NONE)
        change = BillingTermsChange.objects.get(profile=profile)
        self.assertEqual(change.status, "PENDING")
        self.assertTrue(BillingNotification.objects.filter(kind="DISCOUNT_APPROVAL").exists())
        with self.assertRaises(BillingError):
            profiles.decide_terms_change(change, actor=self.manager, approve=True)
        with self.assertRaises(BillingError):
            profiles.decide_terms_change(change, actor=self.accountant, approve=True)
        profiles.decide_terms_change(change, actor=self.director, approve=True, comment="Согласовано")
        invoice.refresh_from_db()
        profile.refresh_from_db()
        self.assertEqual((invoice.status, invoice.amount), (Invoice.Status.OPEN, D("2800")))
        self.assertEqual((profile.discount_assigned_by, profile.discount_approved_by), (self.manager, self.director))

    def test_rejected_discount_issues_standard_price(self):
        profile = self.profile(discount_type=DiscountType.PERCENT, discount_value="50", discount_reason="Просьба")
        change = BillingTermsChange.objects.get(profile=profile)
        profiles.decide_terms_change(change, actor=self.director, approve=False, comment="Нет оснований")
        invoice = self.invoices(profile)[0]
        self.assertEqual((invoice.status, invoice.amount), (Invoice.Status.OPEN, D("4000")))

    def test_plan_price_change_does_not_touch_existing_invoices(self):
        profile = self.profile()
        self.hold(12)
        pricing.add_plan_version(self.it_plan, actor=self.director, lessons_per_package=12, package_price="4500",
                                 effective_from=self.today, reason="Индексация")
        invs = self.invoices(profile)
        self.assertEqual([i.amount for i in invs], [D("4000"), D("4000")])
        self.hold(12, start_day=self.today)
        self.assertEqual(self.invoices(profile)[2].amount, D("4500"))
        with self.assertRaises(BillingError):
            pricing.add_plan_version(self.it_plan, actor=self.manager, lessons_per_package=12, package_price="1",
                                     effective_from=self.today + dt.timedelta(days=5), reason="x")

    def test_terms_change_affects_only_future_packages(self):
        profile = self.profile()
        profiles.request_terms_change(profile, actor=self.director, discount_type=DiscountType.FIXED,
                                      discount_value="1000", reason="Олимпиадник")
        self.assertEqual(self.invoices(profile)[0].amount, D("4000"))
        self.hold(12)
        self.assertEqual(self.invoices(profile)[1].amount, D("3000"))


class OverdueTests(BillingFixture):
    def test_overdue_by_due_date_and_balance(self):
        paid, partial, open_ = self.profile(), self.profile(), self.profile()
        payments.record_payment(profile=paid, amount="4000", received_date=self.today, actor=self.accountant)
        payments.record_payment(profile=partial, amount="1000", received_date=self.today, actor=self.accountant)
        due = self.invoices(open_)[0].due_date
        self.assertEqual(invoices.mark_overdue_invoices(on=due), [])
        marked = invoices.mark_overdue_invoices(on=due + dt.timedelta(days=1))
        self.assertEqual(len(marked), 2)
        self.assertEqual(self.invoices(paid)[0].status, Invoice.Status.PAID)
        self.assertEqual(self.invoices(partial)[0].status, Invoice.Status.OVERDUE)
        self.assertEqual(self.invoices(open_)[0].status, Invoice.Status.OVERDUE)
        # Повтор не дублирует уведомления.
        invoices.mark_overdue_invoices(on=due + dt.timedelta(days=2))
        self.assertEqual(BillingNotification.objects.filter(kind="OVERDUE").count(), 2)
        # Оплата просроченного — PAID, задача закрыта.
        payments.record_payment(profile=open_, amount="4000", received_date=self.today, actor=self.accountant)
        self.assertEqual(self.invoices(open_)[0].status, Invoice.Status.PAID)


class DeactivationTests(BillingFixture):
    def test_deactivated_student_stops_future_billing_and_keeps_history(self):
        student = self.student()
        profile = self.profile(student=student)
        payments.record_payment(profile=profile, amount="12000", received_date=self.today, actor=self.accountant,
                                prepay_packages=2)
        self.hold(5)
        with self.captureOnCommitCallbacks(execute=True):
            deactivate_student(student, reason="relocation", performed_by=self.manager, event_date=self.today)
        profile.refresh_from_db()
        self.assertEqual((profile.status, profile.stopped_on), ("INACTIVE", self.today))
        statuses = [i.status for i in self.invoices(profile)]
        # Текущий пакет и его оплата сохранены; не начатые пакеты отменены,
        # их оплата вернулась в аванс.
        self.assertEqual(statuses, [Invoice.Status.PAID, Invoice.Status.VOID, Invoice.Status.VOID])
        self.assertEqual(self.credit(profile), D("8000"))
        self.assertEqual([p.status for p in self.packages(profile)], ["ACTIVE", "CANCELLED", "CANCELLED"])
        # Уроки после ухода не списываются, новых начислений нет.
        lesson = self.lesson(day=self.today + dt.timedelta(days=1))
        from apps.billing.services import lessons

        lessons.sync_lesson(lesson.pk)
        self.assertEqual(self.packages(profile)[0].lessons_used, 5)
        self.assertEqual(Invoice.objects.filter(profile=profile).count(), 3)
        # Возврат аванса бухгалтером.
        payment = StudentPayment.objects.get(billing_profile=profile, kind="payment")
        payments.refund_payment(payment, actor=self.accountant, amount="8000", reason="Уход")
        self.assertEqual(self.credit(profile), D("0"))
        self.assertEqual(reconcile(), [])

    def test_debt_survives_deactivation(self):
        student = self.student()
        profile = self.profile(student=student)
        self.hold(3)
        with self.captureOnCommitCallbacks(execute=True):
            deactivate_student(student, reason="relocation", event_date=self.today)
        invoice = self.invoices(profile)[0]
        self.assertEqual((invoice.status, invoice.balance), (Invoice.Status.OPEN, D("4000")))

    def test_pause_and_continue(self):
        student = self.student()
        profile = self.profile(student=student)
        self.hold(12)
        self.assertEqual(len(self.invoices(profile)), 2)
        with self.captureOnCommitCallbacks(execute=True):
            pause_student(student, reason="health", event_date=self.today)
        profile.refresh_from_db()
        self.assertEqual(profile.status, "PAUSED")
        with self.captureOnCommitCallbacks(execute=True):
            continue_student(Student.objects.get(pk=student.pk), event_date=self.today)
        profile.refresh_from_db()
        self.assertEqual(profile.status, "ACTIVE")

    def test_registration_requires_active_student_and_no_duplicate(self):
        profile = self.profile()
        with self.assertRaises(BillingError):
            self.profile(student=profile.student)
        Student.objects.filter(pk=profile.student_id).update(status=Student.Status.WITHDRAWN, is_active=False)
        with self.assertRaises(BillingError):
            self.profile(student=Student.objects.get(pk=profile.student_id), plan=self.en_plan)


class RefundAndReversalTests(BillingFixture):
    def test_reverse_payment_reopens_invoice_and_keeps_records(self):
        profile = self.profile()
        payment, _ = payments.record_payment(profile=profile, amount="4000", received_date=self.today,
                                             actor=self.accountant)
        payments.reverse_payment(payment, actor=self.accountant, reason="Ошибся студентом")
        payment.refresh_from_db()
        invoice = self.invoices(profile)[0]
        self.assertEqual(payment.status, StudentPayment.Status.VOID)
        self.assertEqual(payment.amount, D("4000"))
        self.assertEqual((invoice.status, invoice.balance), (Invoice.Status.OPEN, D("4000")))
        self.assertEqual(PaymentAllocation.objects.get().status, "REVERSED")
        self.assertEqual(self.credit(profile), D("0"))
        self.assertEqual(BillingTask.objects.filter(invoice=invoice, status="OPEN").count(), 1)
        with self.assertRaises(BillingError):
            payments.reverse_payment(payment, actor=self.accountant, reason="ещё раз")

    def test_refund_only_from_unallocated_and_reverse_refund(self):
        profile = self.profile()
        payment, _ = payments.record_payment(profile=profile, amount="5000", received_date=self.today,
                                             actor=self.accountant)
        with self.assertRaises(BillingError):
            payments.refund_payment(payment, actor=self.accountant, amount="1500", reason="Переплата")
        refund = payments.refund_payment(payment, actor=self.accountant, amount="1000", reason="Переплата")
        self.assertEqual(self.credit(profile), D("0"))
        with self.assertRaises(BillingError):
            payments.reverse_payment(payment, actor=self.accountant, reason="x")
        payments.reverse_refund(refund, actor=self.accountant, reason="Деньги не выдавали")
        self.assertEqual(self.credit(profile), D("1000"))
        self.assertEqual(reconcile(), [])

    def test_reverse_allocation_moves_money_to_credit(self):
        profile = self.profile()
        payments.record_payment(profile=profile, amount="4000", received_date=self.today, actor=self.accountant)
        allocation = PaymentAllocation.objects.get()
        payments.reverse_allocation(allocation, actor=self.accountant, reason="Не тот счёт")
        self.assertEqual(self.credit(profile), D("4000"))
        self.assertEqual(self.invoices(profile)[0].status, Invoice.Status.OPEN)

    @override_settings(BILLING_ACCOUNTANT_REFUND_LIMIT="500")
    def test_refund_limit(self):
        profile = self.profile()
        payment, _ = payments.record_payment(profile=profile, amount="1000", received_date=self.today,
                                             actor=self.accountant, auto_allocate=False)
        with self.assertRaises(BillingError):
            payments.refund_payment(payment, actor=self.accountant, amount="600", reason="x")
        payments.refund_payment(payment, actor=self.accountant, amount="400", reason="x")

    def test_void_invoice_and_adjustment_rules(self):
        profile = self.profile()
        payments.record_payment(profile=profile, amount="1000", received_date=self.today, actor=self.accountant)
        invoice = self.invoices(profile)[0]
        with self.assertRaises(BillingError):
            invoices.adjust_invoice(invoice, actor=self.accountant, amount="100", reason="x")
        invoices.adjust_invoice(invoice, actor=self.director, amount="500", reason="Компенсация пропусков")
        invoice.refresh_from_db()
        self.assertEqual((invoice.amount, invoice.balance), (D("4000"), D("2500")))
        self.hold(1)
        with self.assertRaises(BillingError):
            invoices.void_invoice(invoice, actor=self.director, reason="x")

    def test_financial_records_cannot_be_deleted(self):
        profile = self.profile()
        with self.assertRaises(Exception):
            self.invoices(profile)[0].delete()
        with self.assertRaises(Exception):
            Invoice.objects.all().delete()
        with self.assertRaises(Exception):
            LessonConsumption.objects.all().delete()
        self.assertTrue(Invoice.objects.exists())


class LegacyPaymentEndpointTests(BillingFixture):
    def test_accounting_void_routes_billing_payment_through_reversal(self):
        from apps.accounting.services import AccountingError
        from apps.accounting.services.student_payments import record_payment as legacy_record, void_student_payment

        profile = self.profile()
        payment, _ = payments.record_payment(profile=profile, amount="4000", received_date=self.today,
                                             actor=self.accountant)
        with self.assertRaises(AccountingError):
            legacy_record(student=profile.student, amount="100", received_date=self.today, actor=self.accountant,
                          refund_of=payment)
        void_student_payment(payment, actor=self.accountant, reason="Ошибка")
        invoice = self.invoices(profile)[0]
        self.assertEqual((invoice.status, invoice.amount_paid), (Invoice.Status.OPEN, D("0")))
        self.assertEqual(reconcile(), [])


class EarlyLeaveTests(BillingFixture):
    def test_student_leaving_before_first_lesson_has_no_debt(self):
        from apps.billing.services import profiles as profile_service

        profile = self.profile()
        profile_service.deactivate_billing_profile(profile, actor=self.manager, reason="Не пришёл")
        invoice = self.invoices(profile)[0]
        self.assertEqual(invoice.status, Invoice.Status.VOID)
        self.assertEqual(self.packages(profile)[0].status, "CANCELLED")
        self.assertFalse(BillingTask.objects.filter(status__in=BillingTask.LIVE_STATUSES).exists())

    def test_list_status_filters_do_not_clash(self):
        self.profile()
        api = self.client_for(self.accountant)
        base = "/api/v1/accounting/billing/"
        self.assertEqual(api.get(base + "profiles/", {"status": "ACTIVE"}).data["count"], 1)
        self.assertEqual(api.get(base + "packages/", {"status": "ACTIVE"}).data["count"], 1)
        self.assertEqual(api.get(base + "payments/", {"status": "confirmed"}).status_code, 200)
