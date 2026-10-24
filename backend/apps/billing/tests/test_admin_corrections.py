"""Django Admin → «Неправильные данные»: права, исправление в два шага,
аннулирование, журнал, пересчёт отчётов."""
from __future__ import annotations

import datetime as dt

from django.contrib.auth.models import Permission
from django.core.exceptions import ValidationError
from django.test import Client

from apps.accounting.models import PayrollAuditLog, StudentPayment
from apps.billing.models import Invoice, PaymentMode, Receipt, Reservation, ReservationAllocation
from apps.billing.services import contracts, periods, reservations
from apps.billing.tests.base import D, make_user
from apps.billing.tests.test_periods import OCT24, PeriodFixture
from apps.users.models import User

SEP1, SEP8 = dt.date(2026, 9, 1), dt.date(2026, 9, 8)
HOME = "/admin/billing/financialcorrection/"


class AdminCorrectionFixture(PeriodFixture):
    def setUp(self):
        super().setUp()
        self.profile = self.contract(start_date=SEP1, payment_mode=PaymentMode.FULL_PREPAY, discount_enabled=True,
                                     final_course_price="53000", discount_reason="Скидка")
        self.payment = self.pay(self.profile, "53000", on=OCT24)  # ошибка: деньги получены 08.09
        self.receipt = self.payment.receipt
        self.fixer = make_user("fixer", User.Role.ADMIN, is_staff=True)
        self.fixer.user_permissions.add(Permission.objects.get(codename="correct_financial_records"))
        self.plain_admin = make_user("plainadmin", User.Role.ADMIN, is_staff=True)

    def client_as(self, user) -> Client:
        client = Client()
        client.force_login(user)
        return client

    def month(self, value):
        first, last = periods.month_bounds(value)
        return periods.period_report({}, date_from=first, date_to=last)


class PermissionTests(AdminCorrectionFixture):
    def test_only_users_with_permission_see_and_use_it(self):
        fixer, plain = self.client_as(self.fixer), self.client_as(self.plain_admin)
        self.assertContains(fixer.get("/admin/"), "Неправильные данные")
        self.assertNotContains(plain.get("/admin/"), "Неправильные данные")
        self.assertEqual(fixer.get(HOME).status_code, 200)
        self.assertEqual(self.client_as(self.admin).get(HOME).status_code, 200)  # суперпользователь — все права
        url = f"{HOME}payment/{self.payment.pk}/"
        for path in (HOME, url, f"{url}void/", f"{HOME}journal/"):
            self.assertEqual(plain.get(path).status_code, 403, path)
        # Прямой POST без разрешения не проходит.
        self.assertEqual(plain.post(url, {"received_date": "2026-09-08", "reason": "x", "step": "confirm"}).status_code, 403)
        self.assertEqual(plain.post(f"{url}void/", {"confirm": "on", "reason": "x"}).status_code, 403)
        for user in (self.director, self.manager):  # роли LMS — в Django Admin не входят
            self.assertEqual(self.client_as(user).get(HOME).status_code, 302)
        self.payment.refresh_from_db()
        self.assertEqual((self.payment.received_date, self.payment.status), (OCT24, "confirmed"))


class PaymentCorrectionTests(AdminCorrectionFixture):
    def test_date_fix_shows_review_then_saves_same_payment_and_reports_follow(self):
        client = self.client_as(self.fixer)
        url = f"{HOME}payment/{self.payment.pk}/"
        self.assertContains(client.get(url), "Проверить исправление")
        found = client.get(HOME, {"number": self.receipt.number})
        self.assertContains(found, f"{HOME}payment/{self.payment.pk}/")
        body = {"received_date": "2026-09-08", "amount": "53000.00", "method": "", "reference": "", "comment": "",
                "purpose": "", "allocations": "", "reason": "Деньги получены 08.09"}
        review = client.post(url, {**body, "step": "review"})
        self.assertContains(review, "Сохранить исправление")
        self.assertContains(review, "2026-10-24")
        self.assertContains(review, "2026-09-08")
        self.assertContains(review, "задолженность")
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.received_date, OCT24)  # проверка ничего не меняет
        client.post(url, {**body, "step": "confirm"})
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.received_date, SEP8)
        self.assertEqual((StudentPayment.objects.count(), Receipt.objects.count()), (1, 1))
        self.assertEqual(Receipt.objects.get(pk=self.receipt.pk).number, self.receipt.number)
        self.assertEqual((self.month("2026-09")["received"]["gross"], self.month("2026-10")["received"]["gross"]),
                         ("53000.00", "0.00"))
        entry = PayrollAuditLog.objects.get(action="admin_financial_correction")
        self.assertEqual((entry.actor_id, entry.reason, entry.entity_id), (self.fixer.pk, "Деньги получены 08.09",
                                                                          self.payment.pk))
        self.assertEqual(entry.old_values["Дата поступления"], "2026-10-24")
        self.assertEqual(entry.new_values["related"]["receipt"], self.receipt.number)

    def test_amount_fix_keeps_single_count(self):
        client = self.client_as(self.fixer)
        url = f"{HOME}payment/{self.payment.pk}/"
        body = {"received_date": "2026-10-24", "amount": "55000", "method": "", "reference": "", "comment": "",
                "purpose": "", "allocations": "", "reason": "Получено 55 000", "step": "confirm"}
        client.post(url, body)
        s = contracts.money_summary(self.profile)
        self.assertEqual((s["received"], s["allocated"], s["credit"]), (D("55000"), D("53000"), D("2000")))
        self.assertEqual(StudentPayment.objects.count(), 1)

    def test_void_payment_restores_debt_and_cannot_repeat(self):
        client = self.client_as(self.fixer)
        url = f"{HOME}payment/{self.payment.pk}/void/"
        self.assertContains(client.get(url), "Аннулировать")
        client.post(url, {"reason": "x"})  # без подтверждения — ничего
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, "confirmed")
        client.post(url, {"confirm": "on", "reason": "Внесён ошибочно"})
        self.payment.refresh_from_db()
        (course,) = self.live_invoices(self.profile)
        self.assertEqual((self.payment.status, Receipt.objects.get(pk=self.receipt.pk).status, course.status),
                         ("void", Receipt.Status.CANCELLED, Invoice.Status.OPEN))
        s = contracts.money_summary(self.profile)
        self.assertEqual((s["received"], s["credit"], s["due_now"]), (D("0"), D("0"), D("53000")))
        again = client.post(url, {"confirm": "on", "reason": "Ещё раз"}, follow=True)
        self.assertContains(again, "уже отменён")
        self.assertEqual(PayrollAuditLog.objects.filter(action="billing_payment_reverse").count(), 1)
        self.assertEqual(StudentPayment.objects.count(), 1)  # не удалён


class InvoiceCorrectionTests(AdminCorrectionFixture):
    def setUp(self):
        super().setUp()
        self.other = self.contract(student=self.student(self.group_b), start_date=OCT24)  # помесячно, месяц 1 = 15 000
        self.invoice = self.live_invoices(self.other)[0]

    def test_amount_due_period_and_note(self):
        client = self.client_as(self.fixer)
        url = f"{HOME}invoice/{self.invoice.pk}/"
        client.post(url, {"amount": "14000", "due_lesson": "4", "period_date": "2026-10-01", "note": "Ошибка тарифа",
                          "reason": "Цена по договору 14 000", "step": "confirm"})
        self.invoice.refresh_from_db()
        self.assertEqual((self.invoice.amount, self.invoice.due_lesson, self.invoice.period_date,
                          self.invoice.snapshot["note"]), (D("14000"), 4, dt.date(2026, 10, 1), "Ошибка тарифа"))
        self.assertEqual(contracts.money_summary(self.other)["due_now"], D("14000"))
        self.assertEqual(self.month("2026-10")["accrued"]["amount"], "14000.00")
        # Нельзя опустить сумму ниже оплаченного.
        paid = self.live_invoices(self.profile)[0]
        response = client.post(f"{HOME}invoice/{paid.pk}/", {"amount": "50000", "reason": "x", "step": "confirm"},
                               follow=True)
        self.assertContains(response, "меньше уже оплаченного")
        paid.refresh_from_db()
        self.assertEqual(paid.amount, D("53000"))

    def test_move_unstarted_invoice_to_right_contract_and_void(self):
        client = self.client_as(self.fixer)
        third = self.contract(student=self.student(self.group_b), start_date=OCT24)
        client.post(f"{HOME}invoice/{self.invoice.pk}/", {"profile": str(third.pk), "reason": "Не тот договор",
                                                          "step": "confirm"})
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.status, Invoice.Status.VOID)
        moved = Invoice.objects.filter(profile=third, snapshot__moved_from_invoice=self.invoice.number).get()
        self.assertEqual((moved.amount, moved.period_date), (self.invoice.amount, self.invoice.period_date))
        client.post(f"{HOME}invoice/{moved.pk}/void/", {"confirm": "on", "reason": "Дубль"})
        moved.refresh_from_db()
        self.assertEqual(moved.status, Invoice.Status.VOID)


class ReservationCorrectionTests(AdminCorrectionFixture):
    def test_reservation_amount_transfer_and_allocation_rule(self):
        a = self.contract(student=self.student(self.group_b), start_date=OCT24, reservation_amount="3000")
        b = self.contract(student=self.student(self.group_b), start_date=OCT24)
        reservation = a.reservations.get()
        client = self.client_as(self.fixer)
        url = f"{HOME}reservation/{reservation.pk}/"
        client.post(url, {"expected_amount": "3500", "reason": "Договорились", "step": "confirm"})
        reservation.refresh_from_db()
        self.assertEqual(reservation.expected_amount, D("3500"))
        reservations.record_reservation_payment(reservation, actor=self.accountant, amount="3500", received_date=OCT24)
        client.post(url, {"paid_date": "2026-10-20", "profile": str(b.pk),
                          "allocation": ReservationAllocation.COURSE_TOTAL, "reason": "Бронь другого студента",
                          "step": "confirm"})
        reservation.refresh_from_db()
        payment = reservation.payment
        self.assertEqual((reservation.profile_id, payment.billing_profile_id, payment.received_date),
                         (b.pk, b.pk, dt.date(2026, 10, 20)))
        a.refresh_from_db()
        self.assertEqual(a.reservation_allocation, ReservationAllocation.COURSE_TOTAL)
        sa, sb = contracts.money_summary(a), contracts.money_summary(b)
        self.assertEqual((sa["received"], sb["received"], sb["allocated"]), (D("0"), D("3500"), D("3500")))
        client.post(f"{url}void/", {"confirm": "on", "reason": "Ошибочная бронь"})
        reservation.refresh_from_db()
        self.assertEqual(reservation.status, Reservation.Status.CANCELLED)
        self.assertEqual(contracts.money_summary(b)["received"], D("0"))


class JournalTests(AdminCorrectionFixture):
    def test_journal_is_read_only(self):
        client = self.client_as(self.fixer)
        client.post(f"{HOME}payment/{self.payment.pk}/", {
            "received_date": "2026-09-08", "amount": "53000.00", "method": "", "reference": "", "comment": "",
            "purpose": "", "allocations": "", "reason": "Дата", "step": "confirm"})
        page = client.get(f"{HOME}journal/")
        self.assertContains(page, "admin_financial_correction")
        self.assertContains(page, "billing_payment_correct")
        entry = PayrollAuditLog.objects.filter(action="admin_financial_correction").first()
        admin_page = self.client_as(self.admin).get(f"/admin/accounting/payrollauditlog/{entry.pk}/change/")
        self.assertNotContains(admin_page, 'name="_save"')  # только просмотр
        with self.assertRaises(ValidationError):
            entry.delete()
