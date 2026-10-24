"""Карточка «Азирет Эсенбаев»: один платёж 38 000 (банковский перевод от
25.08.2026), принятый как «Оплата брони»; договор помесячно, 4 месяца,
итоговая стоимость сначала 40 000 (месяцы 1–2 выставлены по 10 000), затем
снижена до 38 000; бронь засчитывается в первый месяц. Ожидаемые цифры
карточки: получено 38 000, распределено 20 000, аванс 18 000, будущие
периоды 18 000, к оплате 0 — это один платёж, а не бронь плюс платёж."""
from __future__ import annotations

import datetime as dt

from apps.accounting.models import PayrollAuditLog, StudentPayment
from apps.billing.models import Invoice, Receipt, Reservation
from apps.billing.services import contracts, money_audit, profiles, reservations
from apps.billing.services.reports import reconcile
from apps.billing.tests.base import D
from apps.billing.tests.test_contracts import BASE
from apps.billing.tests.test_periods import OCT24, PeriodFixture

AUG25, SEP9 = dt.date(2026, 8, 25), dt.date(2026, 9, 9)


class AzeretFixture(PeriodFixture):
    def setUp(self):
        super().setUp()
        self.at(AUG25)
        self.azeret = self.student()
        self.profile = self.contract(student=self.azeret, start_date=SEP9, discount_enabled=True,
                                     final_course_price="40000", discount_reason="Скидка", reservation_amount="38000")
        self.reservation = self.profile.reservations.get()
        _r, self.payment, _c = reservations.record_reservation_payment(
            self.reservation, actor=self.accountant, amount="38000", received_date=AUG25, method="bank")
        self.at(OCT24)
        self.day = SEP9
        self.it_lessons(19)  # месяц 1 завершён, месяц 2 — 7 из 12
        profiles.request_course_terms_change(self.profile, actor=self.accountant, discount_enabled=True,
                                             final_course_price="38000", reason="Доп. скидка")
        self.profile.refresh_from_db()

    def card(self, user=None):
        return self.client_for(user or self.accountant).get(BASE + f"profiles/{self.profile.pk}/card/").data


class OnePaymentTests(AzeretFixture):
    def test_one_payment_20000_allocated_18000_credit(self):
        self.assertEqual(StudentPayment.objects.filter(billing_profile=self.profile).count(), 1)
        self.assertEqual(Receipt.objects.filter(profile=self.profile).count(), 1)
        m1, m2 = self.live_invoices(self.profile)
        self.assertEqual([(i.amount, i.amount_paid, i.status) for i in (m1, m2)],
                         [(D("10000"), D("10000"), Invoice.Status.PAID)] * 2)
        s = contracts.money_summary(self.profile)
        self.assertEqual((s["received"], s["allocated"], s["credit"], s["reservation_unused"]),
                         (D("38000"), D("20000"), D("18000"), D("18000")))
        self.assertEqual((s["outstanding"], s["future"], s["due_now"], s["overdue"], s["credit_unapplied"]),
                         (D("0"), D("18000"), D("0"), D("0"), D("0")))
        card = self.card()
        (res,) = card["reservations"]
        # Бронь — тот же платёж, не вторые 38 000.
        self.assertEqual((res["payment"], res["paid_amount"], res["paid_used"], res["paid_unused"], res["receipt_number"]),
                         (self.payment.pk, "38000.00", "20000.00", "18000.00", self.payment.receipt.number))
        self.assertEqual(card["summary"]["received"], "38000.00")
        self.assertEqual([p["id"] for p in card["payments"]], [self.payment.pk])  # одна строка
        self.assertEqual(reconcile(), [])

    def test_schedule_matches_contract_price(self):
        schedule = self.card()["schedule"]
        self.assertTrue(schedule["consistent"], schedule["issues"])
        self.assertEqual((schedule["final_course_price"], schedule["invoiced"], schedule["projected"], schedule["total"]),
                         ("38000.00", "20000.00", "18000.00", "38000.00"))
        rows = [(m["month_number"], m["state"], m["amount"], m["covered_by_credit"], m["to_pay"]) for m in schedule["months"]]
        self.assertEqual(rows, [(1, "invoiced", "10000.00", "0.00", "0.00"), (2, "invoiced", "10000.00", "0.00", "0.00"),
                                (3, "future", "9000.00", "9000.00", "0.00"), (4, "future", "9000.00", "9000.00", "0.00")])
        self.assertEqual([(c["from"], c["to"]) for c in schedule["price_changes"]][-1], ("40000.00", "38000.00"))

    def test_future_months_are_paid_from_credit_not_debt(self):
        self.it_lessons(5)  # месяц 2 завершён → месяц 3 (9 000) закрыт авансом
        m3 = self.live_invoices(self.profile)[2]
        self.assertEqual((m3.amount, m3.status), (D("9000"), Invoice.Status.PAID))
        s = contracts.money_summary(self.profile)
        self.assertEqual((s["credit"], s["due_now"], s["outstanding"]), (D("9000"), D("0"), D("0")))

    def test_audit_flags_reservation_paid_over_expected_only_when_it_is(self):
        types = {p["type"] for p in money_audit.profile_money_audit(self.profile)["problems"]}
        self.assertNotIn("reservation_paid_over_expected", types)  # бронь 38 000 = оплачено 38 000
        self.assertNotIn("schedule_mismatch", types)
        Reservation.objects.filter(pk=self.reservation.pk).update(expected_amount=D("3000"))
        problem = next(p for p in money_audit.profile_money_audit(self.profile)["problems"]
                       if p["type"] == "reservation_paid_over_expected")
        self.assertEqual((problem["paid"], problem["expected"], problem["fix"]), ("38000.00", "3000.00", "confirm"))


class ReservationCorrectionTests(AzeretFixture):
    def test_reclassify_reservation_payment_as_tuition(self):
        response = self.client_for(self.accountant).post(BASE + f"payments/{self.payment.pk}/correct/", {
            "purpose": "tuition", "reason": "Весь курс оплачен переводом, а не бронь",
        }, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.reservation.refresh_from_db()
        self.assertEqual((self.reservation.status, self.reservation.refunded_amount, self.reservation.retained_amount),
                         (Reservation.Status.CANCELLED, D("0"), D("0")))
        s = contracts.money_summary(self.profile)
        self.assertEqual((s["received"], s["allocated"], s["credit"], s["reservation_unused"]),
                         (D("38000"), D("20000"), D("18000"), D("0")))  # деньги те же, бронью больше не считаются
        self.assertTrue(PayrollAuditLog.objects.filter(action="billing_reservation_reclassify").exists())
        self.assertEqual(StudentPayment.objects.count(), 1)

    def test_void_reservation_payment_recalculates(self):
        response = self.client_for(self.accountant).post(BASE + f"payments/{self.payment.pk}/reverse/",
                                                         {"reason": "Перевод не поступил"}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.reservation.refresh_from_db()
        self.assertEqual((self.reservation.status, self.reservation.payment_id), (Reservation.Status.PENDING, None))
        s = contracts.money_summary(self.profile)
        self.assertEqual((s["received"], s["allocated"], s["credit"], s["due_now"]),
                         (D("0"), D("0"), D("0"), D("20000")))
        self.assertEqual(Receipt.objects.get(payment=self.payment).status, Receipt.Status.CANCELLED)
        # Теперь ошибочную бронь можно отменить.
        cancelled = self.client_for(self.accountant).post(BASE + f"reservations/{self.reservation.pk}/cancel/",
                                                          {"reason": "Бронь не нужна"}, format="json")
        self.assertEqual(cancelled.status_code, 200, cancelled.data)
        self.assertEqual(cancelled.data["status"], "CANCELLED")

    def test_correct_reservation_payment_date(self):
        response = self.client_for(self.accountant).post(BASE + f"payments/{self.payment.pk}/correct/", {
            "received_date": "2026-08-26", "reason": "Перевод зачислен 26.08",
        }, format="json")
        self.assertEqual((response.status_code, response.data["payment"]["received_date"]), (200, "2026-08-26"))
        self.assertEqual(self.card()["reservations"][0]["paid_date"], "2026-08-26")
        receipt = Receipt.objects.get(payment=self.payment)
        self.assertEqual((receipt.number, receipt.snapshot["received_date"]), (self.payment.receipt.number, "2026-08-26"))

    def test_edit_pending_reservation(self):
        other = self.contract(student=self.student(self.group_b), start_date=OCT24, reservation_amount="3000")
        pending = other.reservations.get()
        url = BASE + f"reservations/{pending.pk}/edit/"
        api = self.client_for(self.accountant)
        self.assertEqual(api.post(url, {"expected_amount": "3500"}, format="json").status_code, 400)  # без причины
        ok = api.post(url, {"expected_amount": "3500", "reserved_until": "2026-11-01", "reason": "Договорились"},
                      format="json")
        self.assertEqual((ok.status_code, ok.data["expected_amount"], ok.data["reserved_until"]),
                         (200, "3500.00", "2026-11-01"))
        log = PayrollAuditLog.objects.get(action="billing_reservation_update")
        self.assertEqual(log.old_values["expected_amount"], "3000.00")
        paid = api.post(BASE + f"reservations/{self.reservation.pk}/edit/", {"expected_amount": "1", "reason": "x"},
                        format="json")
        self.assertEqual((paid.status_code, paid.data["code"]), (400, "bad_status"))  # оплаченная — через платёж

    def test_reprint_and_permissions(self):
        receipt = self.payment.receipt
        api = self.client_for(self.accountant)
        self.assertEqual(api.post(BASE + f"receipts/{receipt.pk}/printed/").status_code, 200)
        self.assertEqual((StudentPayment.objects.count(), Receipt.objects.count()), (1, 1))
        for user in (self.manager, self.director):
            client = self.client_for(user)
            for url, body in ((f"payments/{self.payment.pk}/correct/", {"received_date": "2026-08-26", "reason": "x"}),
                              (f"payments/{self.payment.pk}/reverse/", {"reason": "x"}),
                              (f"reservations/{self.reservation.pk}/edit/", {"expected_amount": "1", "reason": "x"}),
                              (f"reservations/{self.reservation.pk}/cancel/", {"reason": "x"})):
                self.assertEqual(client.post(BASE + url, body, format="json").status_code, 403, (user, url))
        self.payment.refresh_from_db()
        self.assertEqual((self.payment.status, self.payment.received_date), ("confirmed", AUG25))
        self.assertNotIn("payments", self.card(self.manager))  # менеджер денег не видит
        self.assertEqual(len(self.card(self.director)["payments"]), 1)


class ScheduleMismatchTests(AzeretFixture):
    def test_mismatch_is_reported_not_silently_fixed(self):
        Invoice.objects.filter(profile=self.profile).update(amount=D("20000"))  # испорченные данные
        schedule = contracts.payment_schedule(self.profile)
        self.assertFalse(schedule["consistent"])
        self.assertIn("больше итоговой стоимости", schedule["issues"][0])
        self.assertIn("schedule_mismatch", {p["type"] for p in money_audit.profile_money_audit(self.profile)["problems"]})


class AdminPageTests(AzeretFixture):
    def test_admin_page_shows_reservation_as_same_payment(self):
        from django.test import Client

        client = Client()
        client.force_login(self.admin)
        page = client.get(f"/admin/accounting/studentpayment/{self.payment.pk}/manage/")
        self.assertContains(page, "Оплачена этим платежом")
        self.assertContains(page, self.payment.receipt.number)
