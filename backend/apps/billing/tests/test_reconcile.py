"""Согласованность денег договора и учёт уроков IT — сценарий из карточки
«Бекнур Абдыбеков»: предоплата всего курса 53 000 (скидка 7 000 от 60 000),
платёж 53 000 от 08.09.2026, договор оформлен 24.10.2026 с началом «сегодня»,
19 уроков IT до этой даты и 39 уроков других предметов.

Прежнее состояние воспроизводится так, как его создавал API до исправления:
платёж «Предоплата / аванс» записывался без распределения
(`auto_allocate=False`), поэтому одна сумма была и «к оплате», и авансом."""
from __future__ import annotations

import datetime as dt

from django.utils import timezone

from apps.academy.models import Attendance
from apps.accounting.models import PayrollAuditLog, StudentPayment
from apps.billing.models import Invoice, LessonPackage, PaymentMode, Receipt
from apps.billing.services import BillingError, analytics, contracts, lessons, money_audit, payments, periods, profiles
from apps.billing.services.reports import reconcile
from apps.billing.tasks import process_completed_packages
from apps.billing.tests.base import D
from apps.billing.tests.test_contracts import BASE
from apps.billing.tests.test_periods import OCT24, PeriodFixture

SEP8 = dt.date(2026, 9, 8)


class BeknurFixture(PeriodFixture):
    def setUp(self):
        super().setUp()
        self.beknur = self.student()
        day = SEP8
        self.it_held = []
        for i in range(39):  # English и Soft Skills — по очереди
            subject = self.english if i % 2 else self.soft
            for lesson in self.hold(1, start_day=day + dt.timedelta(days=i), subject=subject):
                self.mark(lesson, self.beknur, Attendance.Status.PRESENT)
        for i in range(19):  # IT — 19 проведённых уроков с 8 сентября
            lesson = self.hold(1, start_day=day + dt.timedelta(days=2 * i))[0]
            self.mark(lesson, self.beknur, Attendance.Status.PRESENT)
            self.it_held.append(lesson)

    def contract_53000(self, student=None, **extra):
        return self.contract(student=student or self.beknur, start_date=extra.pop("start_date", OCT24),
                             payment_mode=PaymentMode.FULL_PREPAY, discount_enabled=True,
                             final_course_price="53000", discount_reason="Скидка 7 000", **extra)

    def legacy_advance(self, profile, amount="53000"):
        """Как API записывал «Предоплата / аванс» до исправления."""
        return payments.record_payment(profile=profile, amount=amount, received_date=SEP8, actor=self.accountant,
                                       purpose=StudentPayment.Purpose.PREPAYMENT, auto_allocate=False)[0]


class LegacyCardTests(BeknurFixture):
    def test_card_was_double_counting_and_audit_explains_it(self):
        profile = self.contract_53000()
        payment = self.legacy_advance(profile)
        (course,) = self.live_invoices(profile)
        self.assertEqual((course.kind, course.amount, course.status), (Invoice.Kind.COURSE, D("53000"), Invoice.Status.OPEN))
        s = contracts.money_summary(profile)
        # Одна и та же сумма: поступила, лежит авансом и не распределена на начисление.
        self.assertEqual((s["received"], s["allocated"], s["credit"], s["invoices_balance"]),
                         (D("53000"), D("0"), D("53000"), D("53000")))
        self.assertEqual(s["credit_unapplied"], D("53000"))
        # «К оплате сейчас» больше не показывает долг, который покрыт доступным авансом.
        self.assertEqual((s["due_now"], s["outstanding"]), (D("0"), D("0")))
        report = money_audit.profile_money_audit(profile)
        types = {p["type"] for p in report["problems"]}
        self.assertIn("credit_unapplied", types)
        self.assertIn("priority_lessons_before_start", types)
        self.assertNotIn("possible_duplicate_payment", types)
        (row,) = report["payments"]
        self.assertEqual((row["payment"], row["kind"], row["status"], row["unallocated"]),
                         (payment.pk, "payment", "confirmed", "53000.00"))  # настоящее поступление денег
        self.assertTrue(row["before_contract_start"])
        self.assertIn({"type": "credit_unapplied", "profile": profile.pk, "amount": "53000.00"}, reconcile())

    def test_safe_fix_allocates_once_and_keeps_payment_and_receipt(self):
        profile = self.contract_53000()
        payment = self.legacy_advance(profile)
        receipt = payment.receipt
        applied = money_audit.apply_safe_fixes(profile)
        self.assertEqual([(a["payment"], a["amount"]) for a in applied], [(payment.pk, "53000.00")])
        self.assertEqual(money_audit.apply_safe_fixes(profile), [])  # повтор ничего не делает
        (course,) = self.live_invoices(profile)
        self.assertEqual((course.status, course.balance), (Invoice.Status.PAID, D("0")))
        s = contracts.money_summary(profile)
        self.assertEqual((s["received"], s["allocated"], s["credit"], s["paid_total"]),
                         (D("53000"), D("53000"), D("0"), D("53000")))  # не 106 000
        self.assertEqual((s["due_now"], s["outstanding"], s["overdue"], s["future"]), (D("0"),) * 4)
        payment.refresh_from_db()
        self.assertEqual((payment.amount, payment.received_date, payment.status), (D("53000"), SEP8, "confirmed"))
        self.assertEqual(timezone.localdate(payment.created_at), OCT24)  # дата записи — отдельно
        self.assertEqual(Receipt.objects.get(pk=receipt.pk).payment_id, payment.pk)
        self.assertTrue(PayrollAuditLog.objects.filter(action="billing_allocate", entity_id=applied[0]["allocation"]).exists())
        self.assertFalse([p for p in reconcile() if p.get("profile") == profile.pk])


class PaymentRecordingTests(BeknurFixture):
    def test_advance_payment_pays_issued_course_invoice(self):
        profile = self.contract_53000()
        response = self.client_for(self.accountant).post(BASE + "payments/", {
            "profile": profile.pk, "amount": "53000", "received_date": "2026-09-08", "mode": "advance",
        }, format="json", HTTP_IDEMPOTENCY_KEY="beknur-1")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual((response.data["purpose"], response.data["unallocated"], response.data["received_date"]),
                         ("prepayment", "0.00", "2026-09-08"))
        self.assertEqual(self.live_invoices(profile)[0].status, Invoice.Status.PAID)
        card = self.client_for(self.accountant).get(BASE + f"profiles/{profile.pk}/card/").data["summary"]
        self.assertEqual((card["due_now"], card["credit"], card["allocated"], card["outstanding"]),
                         ("0.00", "0.00", "53000.00", "0.00"))

    def test_partial_prepayment_leaves_only_the_remainder(self):
        profile = self.contract_53000()
        payments.record_payment(profile=profile, amount="20000", received_date=SEP8, actor=self.accountant,
                                purpose=StudentPayment.Purpose.PREPAYMENT)
        (course,) = self.live_invoices(profile)
        self.assertEqual((course.status, course.balance), (Invoice.Status.PARTIALLY_PAID, D("33000")))
        s = contracts.money_summary(profile)
        self.assertEqual((s["due_now"], s["outstanding"], s["credit"], s["allocated"]),
                         (D("33000"), D("33000"), D("0"), D("20000")))

    def test_targeted_payment_remainder_goes_to_other_open_invoices(self):
        profile = self.contract(student=self.student(self.group_b), start_date=OCT24)  # помесячно, месяц 1 = 15 000
        (month1,) = self.live_invoices(profile)
        payments.record_payment(profile=profile, amount="16000", received_date=OCT24, actor=self.accountant,
                                allocations=[(month1, D("1000"))])
        month1.refresh_from_db()
        self.assertEqual(month1.status, Invoice.Status.PAID)  # 1 000 явно + 14 000 по порядку
        self.assertEqual(contracts.money_summary(profile)["credit"], D("1000"))

    def test_reservation_course_total_stays_deposit(self):
        """Бронь «в общую стоимость курса» по правилам договора не гасит месяц 1."""
        from apps.billing.models import ReservationAllocation
        from apps.billing.services import reservations

        profile = self.contract(student=self.student(self.group_b), start_date=OCT24, reservation_amount="3000",
                                reservation_allocation=ReservationAllocation.COURSE_TOTAL)
        reservations.record_reservation_payment(profile.reservations.get(), actor=self.accountant, amount="3000",
                                                received_date=OCT24)
        s = contracts.money_summary(profile)
        self.assertEqual((s["credit"], s["credit_applicable"], s["due_now"], s["credit_unapplied"]),
                         (D("3000"), D("0"), D("15000"), D("0")))


class FullPrepayObligationTests(BeknurFixture):
    def test_prepaid_course_months_create_no_second_obligation(self):
        profile = self.contract_53000(start_date=SEP8)  # дата начала верная — уроки IT засчитываются
        payments.record_payment(profile=profile, amount="53000", received_date=SEP8, actor=self.accountant)
        months = self.months(profile)
        self.assertEqual([(m.month_number, m.lessons_used) for m in months], [(1, 12), (2, 7)])
        self.assertEqual([(i.kind, i.amount) for i in self.live_invoices(profile)], [(Invoice.Kind.COURSE, D("53000"))])
        # Повторные запуски сервисов не создают начислений.
        lessons.sync_profile_history(profile)
        for lesson in self.it_held:
            lessons.sync_lesson(lesson.pk)
        process_completed_packages(on=OCT24)
        self.assertEqual(Invoice.objects.filter(profile=profile).count(), 1)
        self.assertEqual(contracts.invoiced_total(profile), D("53000"))
        self.assertEqual(contracts.money_summary(profile)["due_now"], D("0"))


class LessonCountingTests(BeknurFixture):
    def test_breakdown_explains_every_attendance(self):
        profile = self.contract_53000()
        data = lessons.lesson_breakdown(profile)
        self.assertEqual((data["attended"], data["counted"]), (58, 0))
        self.assertEqual(data["totals"], {"other_subject": 39, "before_contract": 19})
        self.assertEqual(len(data["lessons"]), 58)
        other = next(r for r in data["lessons"] if r["subject"] == "English")
        self.assertEqual((other["reason_display"], other["attendance_display"], other["contract_start"]),
                         ("Другой предмет", "Присутствовал", "2026-10-24"))
        self.assertEqual(data["priority_before_contract"], {"count": 19, "first_date": "2026-09-08"})

    def test_cancelled_and_unconfirmed_lessons_have_own_reason(self):
        profile = self.contract_53000(start_date=SEP8)
        cancelled = self.lesson(day=dt.date(2026, 10, 20), status="cancelled")
        planned = self.lesson(day=dt.date(2026, 10, 21), status="scheduled")
        for lesson in (cancelled, planned):
            self.mark(lesson, self.beknur, Attendance.Status.PRESENT)
        rows = {r["lesson"]: r["reason"] for r in lessons.lesson_breakdown(profile)["lessons"]}
        self.assertEqual((rows[cancelled.pk], rows[planned.pk]), ("cancelled", "not_completed"))

    def test_controlled_start_date_correction(self):
        profile = self.contract_53000()
        self.legacy_advance(profile)
        money_audit.apply_safe_fixes(profile)
        with self.assertRaises(BillingError):
            profiles.change_start_date(profile, actor=self.admin, start_date=SEP8, reason="")
        with self.assertRaises(BillingError):
            profiles.change_start_date(profile, actor=self.manager, start_date=SEP8, reason="x")
        response = self.client_for(self.accountant).post(BASE + f"profiles/{profile.pk}/start-date/", {
            "start_date": "2026-09-08", "reason": "Учится с 8 сентября, договор оформлен 24.10 с датой «сегодня»",
        }, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual((response.data["consumed"], response.data["lessons"]["counted"]), (19, 19))
        self.assertEqual(response.data["lessons"]["totals"], {"other_subject": 39, "counted": 19})
        profile.refresh_from_db()
        self.assertEqual(profile.start_date, SEP8)
        (course,) = self.live_invoices(profile)
        self.assertEqual((course.period_date, course.amount, course.status), (SEP8, D("53000"), Invoice.Status.PAID))
        self.assertEqual(LessonPackage.objects.filter(profile=profile).exclude(status="CANCELLED").count(), 2)
        log = PayrollAuditLog.objects.get(action="billing_profile_start_date", entity_id=profile.pk)
        self.assertEqual(log.old_values, {"start_date": "2026-10-24"})
        # Сдвиг позже уже засчитанных уроков запрещён — только через сторно.
        with self.assertRaises(BillingError):
            profiles.change_start_date(profile, actor=self.admin, start_date=OCT24, reason="ошибка")
        self.assertEqual(Attendance.objects.filter(student=self.beknur).count(), 58)  # посещаемость не тронута


class ConsistencyTests(BeknurFixture):
    def test_card_and_analytics_agree(self):
        profile = self.contract_53000()
        partial = self.contract_53000(student=self.student(self.group_b))
        payments.record_payment(profile=profile, amount="53000", received_date=SEP8, actor=self.accountant)
        payments.record_payment(profile=partial, amount="20000", received_date=OCT24, actor=self.accountant)
        cards = [contracts.money_summary(p) for p in (profile, partial)]
        report = analytics.finance_analytics({}, date_from=SEP8, date_to=OCT24)
        self.assertEqual(D(report["received"]["gross"]), sum(c["received"] for c in cards))
        period = periods.period_report({}, date_from=dt.date(2026, 9, 1), date_to=dt.date(2026, 10, 31))
        self.assertEqual(D(period["received"]["gross"]), sum(c["received"] for c in cards))
        self.assertEqual(D(period["debt"]["closing"]), sum(c["due_now"] for c in cards))  # 33 000
        self.assertEqual(D(period["accrued"]["amount"]), sum(c["invoiced"] for c in cards))
        dashboard = self.client_for(self.accountant).get(BASE + "dashboard/").data
        self.assertEqual(D(dashboard["total_debt"]), sum(c["due_now"] for c in cards))
        for p in (profile, partial):
            receipt = Receipt.objects.get(payment__billing_profile=p)
            self.assertEqual((receipt.profile_id, D(receipt.snapshot["amount"])),
                             (p.pk, StudentPayment.objects.get(billing_profile=p).amount))
        self.assertEqual(reconcile(), [])


class SeptemberReportTests(BeknurFixture):
    """Начисление сентября 53 000, деньги получены только в октябре."""

    def setUp(self):
        super().setUp()
        self.at(dt.date(2026, 9, 1))
        self.profile = self.contract_53000(student=self.student(self.group_b), start_date=dt.date(2026, 9, 1))
        self.at(OCT24)
        self.payment = payments.record_payment(profile=self.profile, amount="53000", received_date=OCT24,
                                               actor=self.accountant)[0]

    def test_october_money_for_september_accrual(self):
        sep = periods.period_report({}, date_from=dt.date(2026, 9, 1), date_to=dt.date(2026, 9, 30))
        self.assertEqual(sep["received"]["gross"], "0.00")          # в сентябре денег не было
        self.assertEqual(sep["accrued"]["amount"], "53000.00")       # начисление — сентябрьское
        self.assertEqual(sep["debt"]["closing"], "53000.00")         # долг на 30.09
        self.assertEqual([(m["month"], m["amount"]) for m in sep["accrued"]["paid_later_by_month"]],
                         [("2026-10", "53000.00")])
        # Долг на конец = на начало + начислено − оплачено до конца − корректировки до конца.
        a = sep["accrued"]
        self.assertEqual(D(sep["debt"]["closing"]), D(sep["debt"]["opening"]) + D(a["amount"])
                         - D(a["paid_in_advance"]) - D(a["paid_in_period"]) - D(a["adjusted_by_end"]))
        oct_ = periods.period_report({}, date_from=dt.date(2026, 10, 1), date_to=dt.date(2026, 10, 31))
        self.assertEqual((oct_["received"]["gross"], oct_["received"]["for_previous_periods"],
                          oct_["accrued"]["amount"]), ("53000.00", "53000.00", "0.00"))
        (course,) = self.live_invoices(self.profile)
        self.assertEqual((course.period_date, course.status), (dt.date(2026, 9, 1), Invoice.Status.PAID))
        s = contracts.money_summary(self.profile)
        self.assertEqual((s["due_now"], s["credit"], s["allocated"]), (D("0"), D("0"), D("53000")))
        dashboard = self.client_for(self.accountant).get(BASE + "dashboard/").data
        self.assertEqual((dashboard["total_debt"], dashboard["credit_total"]), ("0.00", "0.00"))

    def test_same_request_twice_creates_one_payment_and_one_receipt(self):
        api = self.client_for(self.accountant)
        body = {"profile": self.profile.pk, "amount": "100", "received_date": "2026-10-24", "mode": "advance"}
        first = api.post(BASE + "payments/", body, format="json", HTTP_IDEMPOTENCY_KEY="dbl-1")
        second = api.post(BASE + "payments/", body, format="json", HTTP_IDEMPOTENCY_KEY="dbl-1")
        self.assertEqual((first.status_code, second.status_code, first.data["id"]), (201, 200, second.data["id"]))
        self.assertEqual(StudentPayment.objects.filter(billing_profile=self.profile).count(), 2)
        self.assertEqual(Receipt.objects.filter(profile=self.profile).count(), 2)

    def test_reprint_does_not_create_payment_or_receipt(self):
        receipt = self.payment.receipt
        api = self.client_for(self.accountant)
        for _ in range(2):
            self.assertEqual(api.post(BASE + f"payments/{self.payment.pk}/receipt/").data["id"], receipt.pk)
            self.assertEqual(api.post(BASE + f"receipts/{receipt.pk}/printed/").status_code, 200)
            self.assertEqual(api.get(BASE + f"receipts/{receipt.pk}/pdf/").status_code, 200)
        self.assertEqual((StudentPayment.objects.count(), Receipt.objects.count()), (1, 1))
        receipt.refresh_from_db()
        self.assertEqual(receipt.print_count, 4)  # печать и PDF — только счётчик, без новых записей
        self.assertEqual(receipt.snapshot["amount"], "53000.00")
        self.assertEqual(receipt.snapshot["staff"], self.accountant.get_full_name())

    def test_two_real_payments_of_53000_stay_separate(self):
        """Второе реальное поступление не сливается с первым: после оплаты курса
        оно — свободный аванс (видно отдельно), аудит просит сверить с кассой."""
        second = payments.record_payment(profile=self.profile, amount="53000", received_date=OCT24,
                                         actor=self.accountant, reference="касса-2")[0]
        self.assertNotEqual(second.pk, self.payment.pk)
        s = contracts.money_summary(self.profile)
        self.assertEqual((s["received"], s["allocated"], s["credit"], s["due_now"], s["credit_unapplied"]),
                         (D("106000"), D("53000"), D("53000"), D("0"), D("0")))
        report = money_audit.profile_money_audit(self.profile)
        dup = next(p for p in report["problems"] if p["type"] == "possible_duplicate_payment")
        self.assertEqual((dup["payments"], dup["fix"]), ([self.payment.pk, second.pk], "manual"))
        self.assertEqual(money_audit.apply_safe_fixes(self.profile), [])  # ничего не «исправляется» само

    def test_confirmed_duplicate_is_reversed_with_audit(self):
        from io import StringIO
        import json

        from django.core.management import call_command

        dup = payments.record_payment(profile=self.profile, amount="53000", received_date=OCT24, actor=self.accountant)[0]
        out = StringIO()
        call_command("billing_money_audit", reverse_payment=dup.pk, reason="Деньги получены один раз", stdout=out)
        self.assertTrue(json.loads(out.getvalue())["reverse_payment"]["would_reverse"])  # dry-run
        dup.refresh_from_db()
        self.assertEqual(dup.status, "confirmed")
        call_command("billing_money_audit", reverse_payment=dup.pk, reason="Деньги получены один раз", confirm=True,
                     stdout=StringIO())
        dup.refresh_from_db()
        self.assertEqual((dup.status, dup.receipt.status), ("void", Receipt.Status.CANCELLED))
        s = contracts.money_summary(self.profile)
        self.assertEqual((s["received"], s["credit"], s["allocated"]), (D("53000"), D("0"), D("53000")))
        self.assertTrue(PayrollAuditLog.objects.filter(action="billing_payment_reverse", entity_id=dup.pk).exists())

    def test_lookup_by_receipt_and_invoice_numbers(self):
        receipt, (course,) = self.payment.receipt, self.live_invoices(self.profile)
        found = money_audit.lookup_numbers(receipts=[receipt.number, "OK-2026-999999"], invoices=[course.number])
        self.assertEqual(found["not_found"], ["OK-2026-999999"])
        self.assertEqual(found["receipts"][0]["payment"]["id"], self.payment.pk)
        self.assertEqual(found["receipts"][0]["allocations"][0]["invoice"], course.number)
        self.assertEqual(found["invoices"][0]["allocations"][0]["payment"], self.payment.pk)


class RefundAndReservationTests(BeknurFixture):
    def test_refund_and_reversal_reflected_once(self):
        profile = self.contract_53000(student=self.student(self.group_b))
        pay = payments.record_payment(profile=profile, amount="60000", received_date=OCT24, actor=self.accountant)[0]
        payments.refund_payment(pay, actor=self.accountant, amount="7000", reason="Переплата")
        s = contracts.money_summary(profile)
        self.assertEqual((s["received"], s["refunded"], s["net_received"], s["allocated"], s["credit"], s["paid_total"]),
                         (D("60000"), D("7000"), D("53000"), D("53000"), D("0"), D("53000")))

    def test_reservation_counted_once_in_first_month(self):
        from apps.billing.services import reservations

        profile = self.contract(student=self.student(self.group_b), start_date=OCT24, reservation_amount="3000")
        reservations.record_reservation_payment(profile.reservations.get(), actor=self.accountant, amount="3000",
                                                received_date=OCT24)
        payments.record_payment(profile=profile, amount="12000", received_date=OCT24, actor=self.accountant)
        s = contracts.money_summary(profile)
        (month1,) = self.live_invoices(profile)
        self.assertEqual((month1.status, s["received"], s["allocated"], s["credit"], s["outstanding"]),
                         (Invoice.Status.PAID, D("15000"), D("15000"), D("0"), D("45000")))
