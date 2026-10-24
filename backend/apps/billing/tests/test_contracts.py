"""Договор по программе: учебные месяцы по приоритетному предмету (IT),
срок оплаты в уроках, скидка итоговой стоимостью, бронь, предоплата, чеки,
очереди бухгалтера, аналитика и роли. Номера в docstring — сценарии ТЗ."""
from __future__ import annotations

import datetime as dt
import importlib

from django.test import TestCase

from apps.academy.models import GroupTeacher
from apps.accounting.models import StudentPayment
from apps.billing.models import (
    BillingSettings,
    BillingTermsChange,
    Invoice,
    LessonPackage,
    PaymentAllocation,
    PaymentMode,
    Receipt,
    ReservationAllocation,
    StudentBillingProfile,
)
from apps.billing.services import BillingError, analytics, contracts, lessons, payments, pricing, profiles, queues
from apps.billing.services import reservations as res_service
from apps.billing.services.ledger import payment_unallocated
from apps.billing.tests.base import BillingMixin, D
from apps.users.models import Subject

BASE = "/api/v1/accounting/billing/"


class ContractFixture(BillingMixin, TestCase):
    def setUp(self):
        self.build()
        self.soft = Subject.objects.get_or_create(name="Soft Skills")[0]
        self.course.subjects.add(self.soft)
        for group in (self.group, self.group_b):
            GroupTeacher.objects.create(group=group, teacher=self.trainer, subject=self.soft)
        # Kid's Club Standard: 4 месяца × 12 уроков IT, 15 000 сом в месяц → 60 000 сом.
        self.kc = pricing.create_plan(
            actor=self.accountant, name="Kid's Club Standard", subject=self.it, course=self.course,
            lessons_per_package=12, package_price=D("15000"), effective_from=self.start - dt.timedelta(days=30),
            duration_months=4, payment_deadline_lessons=3,
        )
        self.day = self.start

    def contract(self, *, actor=None, student=None, **extra) -> StudentBillingProfile:
        return profiles.create_student_billing_profile(
            student=student or self.student(), plan=self.kc, actor=actor or self.accountant,
            start_date=extra.pop("start_date", self.start),
            responsible_accountant=self.accountant, **extra,
        )

    def it_lessons(self, n=1, group=None):
        held = self.hold(n, start_day=self.day, group=group)
        self.day += dt.timedelta(days=n)
        return held

    def other(self, n, subject):
        held = self.hold(n, start_day=self.day, subject=subject)
        self.day += dt.timedelta(days=n)
        return held

    def months(self, profile):
        return list(LessonPackage.objects.filter(profile=profile).exclude(status="CANCELLED").order_by("number"))

    def live_invoices(self, profile):
        return list(Invoice.objects.filter(profile=profile).exclude(status="VOID").order_by("package__number", "pk"))

    def pay(self, profile, amount, **kw):
        return payments.record_payment(profile=profile, amount=amount, received_date=kw.pop("on", self.today),
                                       actor=self.accountant, **kw)[0]


class StudyMonthTests(ContractFixture):
    def test_contract_snapshot_and_first_month(self):
        profile = self.contract()
        self.assertEqual((profile.standard_course_price, profile.final_course_price, profile.month_price),
                         (D("60000"), D("60000"), D("15000")))
        self.assertEqual((profile.duration_months, profile.lessons_per_month, profile.deadline_lessons), (4, 12, 3))
        month = self.months(profile)[0]
        self.assertEqual((month.month_number, month.status, month.lessons_total), (1, "ACTIVE", 12))
        invoice = self.live_invoices(profile)[0]
        self.assertEqual((invoice.kind, invoice.amount, invoice.due_lesson), ("MONTH", D("15000"), 3))

    def test_01_it_12_english_10_completes_month(self):
        """1. IT — 12 уроков, English — 10: месяц завершён."""
        profile = self.contract()
        self.it_lessons(6)
        self.other(10, self.english)
        self.other(8, self.soft)
        self.it_lessons(6)
        first, second = self.months(profile)
        self.assertEqual((first.status, first.lessons_used, first.completed_on is not None), ("COMPLETED", 12, True))
        self.assertEqual((second.month_number, second.status, second.lessons_used), (2, "ACTIVE", 0))
        self.assertEqual([i.package.month_number for i in self.live_invoices(profile)], [1, 2])

    def test_02_english_12_it_9_does_not_complete_month(self):
        """2. English — 12, IT — 9: месяц не завершён, English не списывается."""
        profile = self.contract()
        self.other(12, self.english)
        self.other(10, self.soft)
        self.it_lessons(9)
        months = self.months(profile)
        self.assertEqual(len(months), 1)
        self.assertEqual((months[0].status, months[0].lessons_used), ("ACTIVE", 9))
        self.assertEqual(profile.consumptions.count(), 9)
        self.assertEqual(len(self.live_invoices(profile)), 1)

    def test_03_deadline_on_third_lesson_of_new_month(self):
        """3. Дедлайн — 3-й урок IT нового месяца, с 4-го — просрочка."""
        profile = self.contract()
        self.pay(profile, "15000")
        self.it_lessons(12)
        invoice = self.live_invoices(profile)[1]
        self.assertEqual(contracts.payment_stage(invoice), "awaiting")
        self.assertEqual([r["profile"] for r in queues.queue_rows("to_pay", {})], [profile.pk])
        self.it_lessons(2)
        invoice.refresh_from_db()
        self.assertEqual((invoice.status, contracts.payment_stage(invoice), invoice.due_reached_on), ("OPEN", "awaiting", None))
        self.it_lessons(1)
        invoice.refresh_from_db()
        self.assertEqual((invoice.status, contracts.payment_stage(invoice)), ("OPEN", "deadline"))
        self.assertIsNotNone(invoice.due_reached_on)
        self.assertTrue(profile.notifications.filter(kind="PAYMENT_DEADLINE").exists())
        self.assertEqual(queues.queue_rows("overdue", {}), [])
        self.it_lessons(1)
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, "OVERDUE")
        self.assertIsNotNone(invoice.overdue_since)
        rows = queues.queue_rows("overdue", {})
        self.assertEqual((rows[0]["profile"], rows[0]["overdue_lessons"], rows[0]["overdue_amount"]),
                         (profile.pk, 1, "15000.00"))
        self.assertEqual(queues.queue_rows("to_pay", {}), [])
        self.pay(profile, "15000")
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, "PAID")
        self.assertEqual(queues.queue_rows("overdue", {}), [])

    def test_deadline_is_a_plan_setting(self):
        self.kc = pricing.update_plan_settings(self.kc, actor=self.accountant, payment_deadline_lessons=5)
        profile = self.contract()
        self.assertEqual(self.live_invoices(profile)[0].due_lesson, 5)
        self.it_lessons(5)
        self.assertEqual(self.live_invoices(profile)[0].status, "OPEN")
        self.it_lessons(1)
        self.assertEqual(self.live_invoices(profile)[0].status, "OVERDUE")
        # Договор хранит снимок: изменение программы не меняет оформленный договор.
        pricing.update_plan_settings(self.kc, actor=self.accountant, payment_deadline_lessons=2)
        profile.refresh_from_db()
        self.assertEqual(profile.deadline_lessons, 5)

    def test_course_completes_after_last_month(self):
        profile = self.contract(payment_mode=PaymentMode.FULL_PREPAY)
        self.pay(profile, "60000")
        self.it_lessons(48)
        profile.refresh_from_db()
        self.assertEqual(profile.status, StudentBillingProfile.Status.COMPLETED)
        self.assertEqual([m.status for m in self.months(profile)], ["COMPLETED"] * 4)
        self.it_lessons(1)  # после завершения уроки не списываются
        self.assertEqual(profile.consumptions.count(), 48)
        self.assertEqual(LessonPackage.objects.filter(profile=profile).count(), 4)

    def test_lesson_never_consumed_twice(self):
        profile = self.contract()
        lesson = self.it_lessons(1)[0]
        for _ in range(3):
            lessons.sync_lesson(lesson.pk)
        self.assertEqual(profile.consumptions.count(), 1)
        self.assertEqual(self.months(profile)[0].lessons_used, 1)

    def test_19_transfer_keeps_month_and_payment_history(self):
        """19. Перевод между группами не портит историю платежей."""
        student = self.student()
        profile = self.contract(student=student)
        payment = self.pay(profile, "15000")
        self.it_lessons(5)
        self.transfer(student, self.group_b, self.day)
        self.it_lessons(4, group=self.group_b)
        payment.refresh_from_db()
        month = self.months(profile)[0]
        self.assertEqual((month.lessons_used, payment.group_id), (9, self.group.pk))
        self.assertEqual(self.live_invoices(profile)[0].status, "PAID")
        report = analytics.finance_analytics({"group": self.group.pk}, date_from=self.today, date_to=self.today)
        self.assertEqual(report["received"]["gross"], "15000.00")


class DiscountAndPrepayTests(ContractFixture):
    def test_05_course_60000_discounted_to_45000(self):
        """5. Курс 60 000 со скидкой до 45 000: скидка 15 000 сомами."""
        profile = self.contract(discount_enabled=True, final_course_price="45000", discount_reason="Полная оплата")
        self.assertEqual((profile.final_course_price, profile.discount_amount), (D("45000"), D("15000")))
        self.assertEqual(self.live_invoices(profile)[0].amount, D("11250"))
        self.it_lessons(36)
        self.assertEqual([i.amount for i in self.live_invoices(profile)], [D("11250")] * 4)

    def test_uneven_split_sums_to_final_price(self):
        profile = self.contract(discount_enabled=True, final_course_price="50000", discount_reason="Договорённость")
        self.it_lessons(36)
        amounts = [i.amount for i in self.live_invoices(profile)]
        self.assertEqual(sum(amounts), D("50000"))
        self.assertEqual(amounts, [D("12500")] * 4)
        profile2 = self.contract(discount_enabled=True, final_course_price="49999.99", discount_reason="x")
        self.assertEqual(self.live_invoices(profile2)[0].amount, D("12499.99"))

    def test_discount_validation(self):
        with self.assertRaises(BillingError):  # итоговая без флажка
            self.contract(final_course_price="45000")
        with self.assertRaises(BillingError):  # без причины
            self.contract(discount_enabled=True, final_course_price="45000")
        with self.assertRaises(BillingError):  # отрицательная
            self.contract(discount_enabled=True, final_course_price="-1", discount_reason="x")
        with self.assertRaises(BillingError):  # не меньше стандартной
            self.contract(discount_enabled=True, final_course_price="60000", discount_reason="x")
        with self.assertRaises(BillingError):  # процентов для программы нет
            self.contract(discount_type="PERCENT", discount_value="10", discount_reason="x")
        self.assertEqual(StudentBillingProfile.objects.count(), 0)

    def test_manager_discount_over_limit_waits_for_accountant(self):
        profile = self.contract(actor=self.manager, discount_enabled=True, final_course_price="45000",
                                discount_reason="Многодетная семья")
        invoice = self.live_invoices(profile)[0]
        self.assertEqual((invoice.status, profile.final_course_price), ("DRAFT", D("60000")))
        change = BillingTermsChange.objects.get(profile=profile, status="PENDING")
        with self.assertRaises(BillingError):
            profiles.decide_terms_change(change, actor=self.director, approve=True)
        profiles.decide_terms_change(change, actor=self.accountant, approve=True)
        invoice.refresh_from_db()
        profile.refresh_from_db()
        self.assertEqual((invoice.status, invoice.amount, profile.discount_amount), ("OPEN", D("11250"), D("15000")))

    def test_manager_discount_within_limit_applies(self):
        profile = self.contract(actor=self.manager, discount_enabled=True, final_course_price="57000",
                                discount_reason="Акция")
        self.assertEqual((profile.final_course_price, self.live_invoices(profile)[0].status), (D("57000"), "OPEN"))

    def test_04_full_prepay_no_future_debt(self):
        """4. Предоплата за весь курс: будущие месяцы не отображаются как долг."""
        profile = self.contract(payment_mode=PaymentMode.FULL_PREPAY, discount_enabled=True,
                                final_course_price="45000", discount_reason="Полная предоплата")
        (invoice,) = self.live_invoices(profile)
        self.assertEqual((invoice.kind, invoice.amount, invoice.due_lesson), ("COURSE", D("45000"), 3))
        self.pay(profile, "45000")
        self.it_lessons(10)
        self.assertEqual(queues.queue_rows("soon", {}), [])
        self.it_lessons(2)
        self.it_lessons(30)
        self.assertEqual(len(self.live_invoices(profile)), 1)  # месяцы 2–4 без начислений
        self.assertEqual(len(self.months(profile)), 4)
        summary = contracts.money_summary(profile)
        self.assertEqual((summary["due_now"], summary["outstanding"], summary["future"]), (D("0"), D("0"), D("0")))
        for queue in ("to_pay", "soon", "overdue"):
            self.assertEqual(queues.queue_rows(queue, {}), [])

    def test_monthly_paid_in_advance_is_not_debt(self):
        profile = self.contract()
        self.pay(profile, "60000")
        self.it_lessons(48)
        self.assertTrue(all(i.status == "PAID" for i in self.live_invoices(profile)))
        self.assertEqual(contracts.money_summary(profile)["outstanding"], D("0"))

    def test_price_change_after_enrollment_does_not_touch_contract(self):
        profile = self.contract()
        pricing.add_plan_version(self.kc, actor=self.accountant, lessons_per_package=12, package_price="18000",
                                 effective_from=self.today, reason="Индексация")
        self.it_lessons(12)
        self.assertEqual(self.live_invoices(profile)[1].amount, D("15000"))
        new = self.contract(start_date=self.today)
        self.assertEqual(new.final_course_price, D("72000"))

    def test_mid_course_final_price_changes_only_future_months(self):
        profile = self.contract()
        self.it_lessons(12)
        profiles.request_course_terms_change(profile, actor=self.accountant, discount_enabled=True,
                                             final_course_price="50000", reason="Перешли на предоплату остатка")
        self.it_lessons(24)
        self.assertEqual([i.amount for i in self.live_invoices(profile)],
                         [D("15000"), D("15000"), D("10000"), D("10000")])
        with self.assertRaises(BillingError):
            profiles.request_course_terms_change(profile, actor=self.accountant, discount_enabled=True,
                                                 final_course_price="30000", reason="ниже начисленного")

    def test_payment_mode_change_before_start(self):
        profile = self.contract()
        profiles.change_payment_mode(profile, actor=self.manager, payment_mode=PaymentMode.FULL_PREPAY)
        (invoice,) = self.live_invoices(profile)
        self.assertEqual((invoice.kind, invoice.amount), ("COURSE", D("60000")))
        self.it_lessons(1)
        with self.assertRaises(BillingError):
            profiles.change_payment_mode(profile, actor=self.manager, payment_mode=PaymentMode.MONTHLY)


class ReservationTests(ContractFixture):
    def reserve(self, profile, amount="3000"):
        reservation = profile.reservations.get(status="PENDING")
        return res_service.record_reservation_payment(reservation, actor=self.accountant, amount=amount,
                                                      received_date=self.today)[1]

    def test_07_reservation_goes_to_first_month(self):
        """7. Бронь засчитывается в первый месяц: доплата 12 000."""
        profile = self.contract(reservation_amount="3000")
        res_payment = self.reserve(profile)
        invoice = self.live_invoices(profile)[0]
        self.assertEqual((invoice.amount_paid, invoice.balance), (D("3000"), D("12000")))
        self.assertEqual(contracts.money_summary(profile)["outstanding"], D("57000"))
        self.assertEqual(payment_unallocated(res_payment.pk), D("0"))

    def test_06_reservation_deducted_exactly_once(self):
        """6. Бронь 3 000 вычитается ровно один раз."""
        profile = self.contract(reservation_amount="3000")
        res_payment = self.reserve(profile)
        self.pay(profile, "12000")
        invoice = self.live_invoices(profile)[0]
        self.assertEqual((invoice.status, invoice.amount_paid), ("PAID", D("15000")))
        summary = contracts.money_summary(profile)
        self.assertEqual((summary["paid_total"], summary["outstanding"], summary["credit"]),
                         (D("15000"), D("45000"), D("0")))
        self.it_lessons(12)
        second = self.live_invoices(profile)[1]
        with self.assertRaises(BillingError):  # те же деньги брони второй раз не распределить
            payments.allocate_payment(res_payment, actor=self.accountant, items=[(second, D("3000"))])
        self.assertEqual(sum(a.amount for a in PaymentAllocation.objects.filter(payment=res_payment,
                                                                             status="ACTIVE")), D("3000"))
        with self.assertRaises(BillingError):  # бронь уже оплачена — повторно не принимается
            res_service.record_reservation_payment(profile.reservations.get(), actor=self.accountant, amount="3000",
                                                   received_date=self.today)

    def test_08_reservation_goes_to_course_total(self):
        """8. Бронь засчитывается в общую стоимость курса (закрывает последний месяц)."""
        profile = self.contract(reservation_amount="3000", reservation_allocation=ReservationAllocation.COURSE_TOTAL)
        self.reserve(profile)
        first = self.live_invoices(profile)[0]
        self.assertEqual((first.amount_paid, first.balance), (D("0"), D("15000")))
        summary = contracts.money_summary(profile)
        self.assertEqual((summary["outstanding"], summary["due_now"], summary["reservation_unused"]),
                         (D("57000"), D("15000"), D("3000")))
        for _ in range(3):
            self.pay(profile, "15000")
            self.it_lessons(12)
        last = self.live_invoices(profile)[3]
        self.assertEqual((last.package.month_number, last.amount_paid, last.balance), (4, D("3000"), D("12000")))
        self.assertTrue(all(i.status == "PAID" for i in self.live_invoices(profile)[:3]))
        self.pay(profile, "12000")
        summary = contracts.money_summary(profile)
        self.assertEqual((summary["outstanding"], summary["paid_total"]), (D("0"), D("60000")))

    def test_reservation_alone_is_not_course_debt(self):
        profile = self.contract(reservation_amount="3000")
        self.reserve(profile)
        self.assertEqual(queues.queue_rows("overdue", {}), [])
        self.assertEqual(contracts.money_summary(profile)["due_now"], D("12000"))


class MoneyTests(ContractFixture):
    def test_09_partial_payment_reduces_debt(self):
        """9. Частичный платёж уменьшает долг."""
        profile = self.contract()
        self.pay(profile, "5000")
        invoice = self.live_invoices(profile)[0]
        self.assertEqual((invoice.status, invoice.balance), ("PARTIALLY_PAID", D("10000")))
        row = queues.queue_rows("to_pay", {})[0]
        self.assertEqual((row["focus_invoice"]["paid"], row["focus_invoice"]["balance"]), ("5000.00", "10000.00"))
        self.assertEqual(contracts.money_summary(profile)["outstanding"], D("55000"))

    def test_10_one_payment_covers_several_invoices(self):
        """10. Один платёж покрывает несколько начислений."""
        profile = self.contract()
        self.it_lessons(12)
        payment = self.pay(profile, "35000")
        first, second = self.live_invoices(profile)
        self.assertEqual((first.status, second.status), ("PAID", "PAID"))
        self.assertEqual(PaymentAllocation.objects.filter(payment=payment).count(), 2)
        self.assertEqual(contracts.money_summary(profile)["credit"], D("5000"))

    def test_11_repeated_events_do_not_create_second_invoice(self):
        """11. Повторное событие не создаёт второй счёт."""
        from apps.billing.services.invoices import create_next_package_invoice
        from apps.billing.services.lessons import complete_package
        from apps.billing.tasks import run_daily

        profile = self.contract()
        held = self.it_lessons(12)
        first = self.months(profile)[0]
        complete_package(first, on_date=self.today)
        create_next_package_invoice(profile, activate=True)
        for lesson in held:
            lessons.sync_lesson(lesson.pk)
        run_daily(report=False)
        run_daily(report=False)
        self.assertEqual(len(self.live_invoices(profile)), 2)
        self.assertEqual(len(self.months(profile)), 2)

    def test_preview_shows_effect_without_writing(self):
        profile = self.contract()
        self.pay(profile, "5000")
        before = StudentPayment.objects.count()
        preview = payments.preview_payment(profile, amount="12000")
        self.assertEqual((preview["obligation"], preview["paid_before"], preview["obligation_balance_after"],
                          preview["to_credit"], preview["credit_after"]),
                         ("15000.00", "5000.00", "0.00", "2000.00", "2000.00"))
        self.assertEqual(StudentPayment.objects.count(), before)

    def test_stopped_contract_owes_only_charged_months(self):
        profile = self.contract()
        self.pay(profile, "5000")
        self.it_lessons(12)
        profile = profiles.deactivate_billing_profile(profile, actor=self.manager, reason="Переезд", on_date=self.day)
        # Месяц 2 не начат — его начисление аннулировано; долг — только остаток месяца 1.
        self.assertEqual(self.live_invoices(profile)[-1].package.month_number, 1)
        summary = contracts.money_summary(profile)
        self.assertEqual((summary["due_now"], summary["outstanding"], summary["future"]),
                         (D("10000"), D("10000"), D("0")))

    def test_refund_cannot_exceed_available(self):
        profile = self.contract()
        payment = self.pay(profile, "20000")
        with self.assertRaises(BillingError):
            payments.refund_payment(payment, actor=self.accountant, amount="5000.01", reason="x")
        payments.refund_payment(payment, actor=self.accountant, amount="5000", reason="Переплата")
        self.assertEqual(contracts.money_summary(profile)["credit"], D("0"))


class ReceiptTests(ContractFixture):
    def test_receipt_issued_with_payment(self):
        profile = self.contract(parent_name="Асанова Айгуль")
        payment = self.pay(profile, "5000", payer_name="Асанова Айгуль")
        receipt = payment.receipt
        self.assertTrue(receipt.number.startswith("OK-"))
        snap = receipt.snapshot
        self.assertEqual((snap["amount"], snap["previously_paid"], snap["outstanding"], snap["payer"]),
                         ("5000.00", "0.00", "55000.00", "Асанова Айгуль"))
        self.assertIn("Учебный месяц №1", snap["purpose_lines"][0])
        second = self.pay(profile, "10000")
        self.assertEqual(second.receipt.snapshot["previously_paid"], "5000.00")
        self.assertNotEqual(second.receipt.number, receipt.number)

    def test_13_reprint_does_not_create_payment(self):
        """13. Повторная печать чека не создаёт новый платёж."""
        profile = self.contract()
        payment = self.pay(profile, "15000")
        api = self.client_for(self.accountant)
        for _ in range(2):
            response = api.get(BASE + f"receipts/{payment.receipt.pk}/pdf/")
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.content.startswith(b"%PDF"))
        self.assertEqual(api.get(BASE + f"receipts/{payment.receipt.pk}/pdf/?size=compact").status_code, 200)
        self.assertEqual((StudentPayment.objects.count(), Receipt.objects.count()), (1, 1))
        payment.receipt.refresh_from_db()
        self.assertEqual(payment.receipt.print_count, 3)
        self.assertEqual(api.post(BASE + f"payments/{payment.pk}/receipt/").data["id"], payment.receipt.pk)

    def test_reversed_payment_cancels_receipt(self):
        profile = self.contract()
        payment = self.pay(profile, "15000")
        payments.reverse_payment(payment, actor=self.accountant, reason="Ошибка ввода")
        payment.receipt.refresh_from_db()
        self.assertEqual(payment.receipt.status, "CANCELLED")
        refund_source = self.pay(profile, "16000")
        refund = payments.refund_payment(refund_source, actor=self.accountant, amount="1000", reason="Переплата")
        self.assertEqual(refund.receipt.kind, "REFUND")

    def test_20_backfill_migration_is_idempotent(self):
        """20. Повторное проведение миграции и фоновых задач не дублирует данные."""
        from django.apps import apps as django_apps
        from apps.billing.tasks import run_daily

        profile = self.contract()
        payment = self.pay(profile, "15000")
        Receipt.objects.filter(pk=payment.receipt.pk).update(number=None)
        receipt_count = Receipt.objects.count()
        backfill = importlib.import_module("apps.billing.migrations.0003_backfill_receipts").backfill
        backfill(django_apps, None)
        backfill(django_apps, None)
        self.assertEqual(Receipt.objects.count(), receipt_count)
        legacy = StudentPayment.objects.create(
            student=profile.student, group=self.group, course=self.course, amount=D("700"), received_date=self.today,
            created_by=self.accountant, billing_profile=profile, purpose="tuition",
        )
        backfill(django_apps, None)
        backfill(django_apps, None)
        self.assertEqual(Receipt.objects.filter(payment=legacy).count(), 1)
        self.assertEqual(StudentPayment.objects.count(), 2)
        counts = (Invoice.objects.count(), PaymentAllocation.objects.count(), LessonPackage.objects.count())
        run_daily(report=True)
        run_daily(report=True)
        self.assertEqual((Invoice.objects.count(), PaymentAllocation.objects.count(), LessonPackage.objects.count()),
                         counts)


class QueueTests(ContractFixture):
    def test_soon_queue(self):
        profile = self.contract()
        self.pay(profile, "15000")
        self.it_lessons(8)
        self.assertEqual(queues.queue_rows("soon", {}), [])
        self.it_lessons(1)
        (row,) = queues.queue_rows("soon", {})
        self.assertEqual((row["profile"], row["lessons_used"], row["next_month"]["cost"], row["next_month"]["to_pay"]),
                         (profile.pk, 9, "15000.00", "15000.00"))
        self.pay(profile, "6000")
        (row,) = queues.queue_rows("soon", {})
        self.assertEqual((row["next_month"]["covered"], row["next_month"]["to_pay"]), ("6000.00", "9000.00"))
        self.pay(profile, "9000")
        self.assertEqual(queues.queue_rows("soon", {}), [])  # следующий месяц уже оплачен авансом
        self.assertEqual(queues.counts()["soon"], 0)

    def test_queue_search_and_counts(self):
        a = self.contract(parent_phone="+996555111222")
        self.contract()
        self.assertEqual(queues.counts()["to_pay"], 2)
        rows = queues.queue_rows("to_pay", {"search": "555111"})
        self.assertEqual([r["profile"] for r in rows], [a.pk])


class AnalyticsTests(ContractFixture):
    def test_17_received_vs_expected(self):
        """17. Аналитика различает полученные деньги и ожидаемые поступления."""
        a, b = self.contract(), self.contract(discount_enabled=True, final_course_price="45000", discount_reason="x")
        self.pay(a, "20000", on=self.day)  # 15 000 за месяц + 5 000 аванс
        self.it_lessons(3)  # срок оплаты месяца 1 наступил у обоих
        report = analytics.finance_analytics({}, date_from=self.start, date_to=self.today)
        self.assertEqual(report["received"]["gross"], "20000.00")
        self.assertEqual(report["expected"]["amount"], "26250.00")  # 15 000 + 11 250
        self.assertEqual(report["expected"]["paid"], "15000.00")
        self.assertEqual((report["expected"]["paid_count"], report["expected"]["overdue_count"]), (1, 0))
        self.assertEqual(report["debt_end"], "11250.00")
        self.assertEqual(report["discounts"]["amount"], "15000.00")  # скидка — не поступление
        self.it_lessons(1)
        report = analytics.finance_analytics({}, date_from=self.start, date_to=self.today)
        self.assertEqual(report["expected"]["overdue_count"], 1)
        before = analytics.finance_analytics({}, date_from=self.start, date_to=self.start - dt.timedelta(days=1))
        self.assertEqual((before["expected"]["amount"], before["debt_end"]), ("0.00", "0.00"))
        programs = {r["program_name"]: r for r in report["by_program"]}
        self.assertEqual(programs[self.course.name]["received"], "20000.00")

    def test_18_refunds_and_reversals_in_reports(self):
        """18. Возвраты и сторнирования отражаются в отчётах."""
        profile = self.contract()
        keep = self.pay(profile, "20000")
        wrong = self.pay(profile, "7000")
        payments.reverse_payment(wrong, actor=self.accountant, reason="Внесён дважды")
        payments.refund_payment(keep, actor=self.accountant, amount="2000", reason="Переплата")
        r = analytics.finance_analytics({}, date_from=self.today, date_to=self.today)["received"]
        self.assertEqual((r["gross"], r["refunds"], r["net"], r["reversed"], r["reversed_count"]),
                         ("20000.00", "2000.00", "18000.00", "7000.00", 1))

    def test_reservation_and_prepayment_totals(self):
        profile = self.contract(reservation_amount="3000")
        res_service.record_reservation_payment(profile.reservations.get(), actor=self.accountant, amount="3000",
                                               received_date=self.today)
        prepaid = self.contract(payment_mode=PaymentMode.FULL_PREPAY)
        self.pay(prepaid, "60000")
        report = analytics.finance_analytics({}, date_from=self.today, date_to=self.today)
        self.assertEqual((report["reservations"], report["prepayment"]), ("3000.00", "60000.00"))


class RoleApiTests(ContractFixture):
    def test_14_director_is_read_only(self):
        """14. Директор не может изменять данные через API."""
        profile = self.contract()
        payment = self.pay(profile, "1000")
        api = self.client_for(self.director)
        for url in ("dashboard/", "queues/to_pay/", "queues/counts/", "analytics/", "payments/", "receipts/",
                    "settings/", "audit-log/", f"profiles/{profile.pk}/card/", "plans/"):
            self.assertEqual(api.get(BASE + url).status_code, 200, url)
        writes = [
            ("post", "payments/", {"profile": profile.pk, "amount": "100", "received_date": str(self.today)}),
            ("post", f"payments/{payment.pk}/reverse/", {"reason": "x"}),
            ("post", f"payments/{payment.pk}/refund/", {"amount": "1", "reason": "x"}),
            ("post", "plans/", {"name": "X", "lessons_per_package": 12, "package_price": "1",
                                "effective_from": str(self.today)}),
            ("patch", f"plans/{self.kc.pk}/", {"is_active": False}),
            ("patch", "settings/", {"due_soon_lessons": 5}),
            ("post", "profiles/", {"student": self.student().pk, "plan": self.kc.pk}),
            ("post", f"profiles/{profile.pk}/course-terms/", {"discount_enabled": True,
                                                              "final_course_price": "1", "reason": "x"}),
            ("post", f"invoices/{self.live_invoices(profile)[0].pk}/adjustments/", {"amount": "1", "reason": "x"}),
            ("post", f"receipts/{payment.receipt.pk}/printed/", {}),
            ("post", f"profiles/{profile.pk}/apply-credit/", {}),
        ]
        for method, url, body in writes:
            self.assertEqual(getattr(api, method)(BASE + url, body, format="json").status_code, 403, url)
        self.assertEqual(StudentPayment.objects.count(), 1)
        self.assertFalse(self.director.has_perm("billing.add_paymentallocation"))
        self.assertTrue(self.director.has_perm("billing.view_invoice"))
        me = api.get(BASE + "me/").data
        self.assertEqual((me["role"], me["read_only"], me["can_record_payments"]), ("director", True, False))

    def test_15_manager_cannot_correct_payments(self):
        """15. Менеджер не может корректировать проведённые платежи."""
        profile = self.contract()
        payment = self.pay(profile, "15000")
        api = self.client_for(self.manager)
        allocation = PaymentAllocation.objects.get(payment=payment)
        for url, body in ((f"payments/{payment.pk}/reverse/", {"reason": "x"}),
                          (f"payments/{payment.pk}/refund/", {"amount": "1", "reason": "x"}),
                          (f"allocations/{allocation.pk}/reverse/", {"reason": "x"}),
                          ("payments/", {"profile": profile.pk, "amount": "1", "received_date": str(self.today)})):
            self.assertEqual(api.post(BASE + url, body, format="json").status_code, 403, url)
        for url in ("payments/", "receipts/", "queues/to_pay/", "analytics/"):
            self.assertEqual(api.get(BASE + url).status_code, 403, url)
        self.assertEqual(api.patch(BASE + "settings/", {"due_soon_lessons": 1}, format="json").status_code, 403)
        with self.assertRaises(BillingError):
            payments.reverse_payment(payment, actor=self.manager, reason="x")
        # Менеджер оформляет договор и видит статусы.
        response = api.post(BASE + "profiles/", {
            "student": self.student().pk, "plan": self.kc.pk, "payment_mode": "FULL_PREPAY",
            "reservation_amount": "3000", "discount_enabled": True, "final_course_price": "57000", "reason": "x",
            "discount_reason": "Акция",
        }, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["final_course_price"], "57000.00")
        card = api.get(BASE + f"profiles/{response.data['id']}/card/").data
        self.assertNotIn("payments", card)
        self.assertEqual(api.get(BASE + "queues/all/").status_code, 200)
        # Деньги при зачислении менеджер не проводит.
        self.assertEqual(api.post(BASE + "profiles/", {
            "student": self.student().pk, "plan": self.kc.pk, "initial_payment": "1000",
        }, format="json").status_code, 403)

    def test_16_accountant_records_payment_and_receipt(self):
        """16. Бухгалтер регистрирует платёж и выдаёт чек."""
        profile = self.contract()
        api = self.client_for(self.accountant)
        preview = api.post(BASE + "payments/preview/", {"profile": profile.pk, "amount": "5000"}, format="json")
        self.assertEqual((preview.status_code, preview.data["obligation_balance_after"]), (200, "10000.00"))
        response = api.post(BASE + "payments/", {
            "profile": profile.pk, "amount": "5000", "received_date": str(self.today), "method": "card",
            "payer_name": "Асанов Бакыт",
        }, format="json", HTTP_IDEMPOTENCY_KEY="k-1")
        self.assertEqual(response.status_code, 201, response.data)
        receipt_id = response.data["receipt"]["id"]
        receipt = api.get(BASE + f"receipts/{receipt_id}/").data
        self.assertEqual(receipt["payer_name"], "Асанов Бакыт")
        self.assertTrue(any(r["label"] == "Остаток долга по договору" for r in receipt["rows"]))
        self.assertEqual(api.get(BASE + f"receipts/{receipt_id}/pdf/").status_code, 200)
        advance = api.post(BASE + "payments/", {
            "profile": profile.pk, "amount": "3000", "received_date": str(self.today), "mode": "advance",
        }, format="json")
        # Предоплата не лежит авансом рядом с неоплаченным месяцем 1: сначала
        # закрывает выставленное начисление (остаток 10 000 → 7 000).
        self.assertEqual((advance.data["purpose"], advance.data["unallocated"]), ("prepayment", "0.00"))
        targeted = api.post(BASE + "payments/", {
            "profile": profile.pk, "amount": "20000", "received_date": str(self.today), "mode": "invoice",
            "invoice": self.live_invoices(profile)[0].pk,
        }, format="json")
        self.assertEqual(targeted.data["unallocated"], "13000.00")  # 7 000 на месяц 1, остальное — аванс
        card = api.get(BASE + f"profiles/{profile.pk}/card/").data
        self.assertEqual(card["summary"]["outstanding"], "32000.00")

    def test_12_double_click_creates_one_payment(self):
        """12. Повторное нажатие кнопки не создаёт второй платёж."""
        profile = self.contract()
        api = self.client_for(self.accountant)
        body = {"profile": profile.pk, "amount": "5000", "received_date": str(self.today)}
        first = api.post(BASE + "payments/", body, format="json", HTTP_IDEMPOTENCY_KEY="same-key")
        second = api.post(BASE + "payments/", body, format="json", HTTP_IDEMPOTENCY_KEY="same-key")
        self.assertEqual((first.status_code, second.status_code), (201, 200))
        self.assertEqual(first.data["id"], second.data["id"])
        self.assertEqual((StudentPayment.objects.count(), Receipt.objects.count()), (1, 1))

    def test_enrollment_with_money_by_accountant(self):
        api = self.client_for(self.accountant)
        body = {
            "student": self.student().pk, "plan": self.kc.pk, "reservation_amount": "3000",
            "reservation_received": True, "initial_payment": "12000", "payment_method": "cash",
            "payer_name": "Родитель", "idempotency_key": "enroll-1",
        }
        response = api.post(BASE + "profiles/", body, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        profile = StudentBillingProfile.objects.get(pk=response.data["id"])
        invoice = self.live_invoices(profile)[0]
        self.assertEqual((invoice.status, invoice.amount_paid), ("PAID", D("15000")))
        self.assertEqual(Receipt.objects.filter(profile=profile).count(), 2)
        # Повтор той же формы — договор уже есть, деньги второй раз не проводятся.
        self.assertEqual(api.post(BASE + "profiles/", body, format="json").status_code, 400)
        self.assertEqual(StudentPayment.objects.filter(billing_profile=profile).count(), 2)

    def test_settings_by_accountant(self):
        api = self.client_for(self.accountant)
        response = api.patch(BASE + "settings/", {"due_soon_lessons": 4, "manager_max_discount_percent": "30",
                                                  "academy_details": "Бишкек, +996 555 000 000"}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(BillingSettings.load().due_soon_lessons, 4)
        profile = self.contract(actor=self.manager, discount_enabled=True, final_course_price="45000",
                                discount_reason="в пределах нового лимита 30 %")
        self.assertEqual(profile.final_course_price, D("45000"))
        self.assertTrue(api.get(BASE + "audit-log/", {"action": "billing_settings_update"}).data["count"] >= 1)
