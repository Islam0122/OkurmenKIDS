"""Исторические периоды: сентябрь и октябрь 2026.

Сегодня — октябрь, а бухгалтер продолжает работать с сентябрём. Проверяется,
что три даты не смешиваются: период начисления (`Invoice.period_date`),
дата фактического поступления денег (`StudentPayment.received_date`) и
дата записи в системе (`created_at`)."""
from __future__ import annotations

import datetime as dt
from unittest import mock

from django.utils import timezone

from apps.accounting.models import PayrollAuditLog, StudentPayment
from apps.billing.models import Invoice
from apps.billing.services import BillingError, analytics, invoices, lessons, payments, periods, reports
from apps.billing.tests.test_contracts import BASE, ContractFixture
from apps.billing.tests.base import D

SEP1, SEP20, SEP30 = dt.date(2026, 9, 1), dt.date(2026, 9, 20), dt.date(2026, 9, 30)
OCT1, OCT5, OCT24, OCT31 = dt.date(2026, 10, 1), dt.date(2026, 10, 5), dt.date(2026, 10, 24), dt.date(2026, 10, 31)


class Clock:
    """Управляемое «сегодня»: `timezone.now()` (а через него `localdate()` и
    `auto_now_add`) возвращает полдень выбранного дня."""

    def __init__(self, day: dt.date):
        self.day = day

    def now(self):
        return dt.datetime.combine(self.day, dt.time(6), tzinfo=dt.timezone.utc)  # 12:00 в Бишкеке


class PeriodFixture(ContractFixture):
    def setUp(self):
        self.clock = Clock(OCT24)
        patcher = mock.patch("django.utils.timezone.now", side_effect=lambda: self.clock.now())
        patcher.start()
        self.addCleanup(patcher.stop)
        super().setUp()
        self.day = dt.date(2026, 9, 2)

    def at(self, day: dt.date):
        self.clock.day = day

    def september_contract(self, **extra):
        """Договор с 1 сентября и 8 уроков IT в сентябре (учебный месяц 1 не закончен)."""
        self.it_lessons(8)
        return self.contract(start_date=SEP1, **extra)

    def report(self, month: str, **f):
        date_from, date_to = periods.month_bounds(month)
        return periods.period_report(f, date_from=date_from, date_to=date_to)


class BackdatedAccrualTests(PeriodFixture):
    def test_contract_entered_in_october_accrues_september(self):
        """Причина привязки к октябрю: первое начисление получало период «сегодня»."""
        profile = self.september_contract()  # оформлен 24 октября
        (first,) = self.live_invoices(profile)
        self.assertEqual(first.period_date, SEP1)  # учебный период — сентябрь
        self.assertEqual(first.issue_date, OCT24)  # выставлено в день оформления
        self.assertEqual(timezone.localdate(first.created_at), OCT24)  # запись — сегодня (аудит)
        self.assertEqual(self.months(profile)[0].lessons_used, 8)  # сентябрьские уроки засчитаны
        self.assertEqual(self.report("2026-09")["accrued"]["amount"], "15000.00")
        self.assertEqual(self.report("2026-10")["accrued"]["amount"], "0.00")
        self.assertEqual(reports.financial_report({}, date_from=SEP1, date_to=SEP30)["invoiced"]["amount"], "15000.00")

    def test_next_month_follows_it_lessons_not_calendar(self):
        """Учебный месяц 2 начинается, когда проведён 12-й урок IT, — его дата и есть период."""
        profile = self.september_contract()
        self.day = dt.date(2026, 9, 25)
        self.it_lessons(4)  # 12-й урок — 28 сентября, хотя обработан 24 октября
        month1, month2 = self.live_invoices(profile)
        self.assertEqual((month1.period_date, month2.period_date), (SEP1, dt.date(2026, 9, 28)))
        self.assertEqual(self.report("2026-09")["accrued"]["amount"], "30000.00")
        self.day = OCT5
        self.it_lessons(12)  # месяц 2 закончился в октябре — месяц 3 октябрьский
        self.assertEqual(self.live_invoices(profile)[2].period_date, dt.date(2026, 10, 16))

    def test_editing_lessons_in_october_keeps_september_accruals(self):
        profile = self.september_contract()
        before = [(i.pk, i.period_date, i.amount) for i in self.live_invoices(profile)]
        lesson = self.hold(1, start_day=dt.date(2026, 9, 15))[0]
        lesson.status = lesson.Status.CANCELLED
        lesson.save()
        lessons.sync_lesson(lesson.pk)  # отмена урока в октябре — сторно, не перенос периода
        self.transfer(profile.student, self.group_b, OCT5)  # перевод в другую группу
        self.assertEqual([(i.pk, i.period_date, i.amount) for i in self.live_invoices(profile)], before)


class HistoricalPaymentTests(PeriodFixture):
    def test_register_september_payment_in_october(self):
        """Платёж, полученный 20 сентября, внесён 24 октября — сентябрьское поступление."""
        profile = self.september_contract()
        payment = self.pay(profile, "15000", on=SEP20)
        self.assertEqual(payment.received_date, SEP20)
        self.assertEqual(timezone.localdate(payment.created_at), OCT24)
        sep, oct_ = self.report("2026-09"), self.report("2026-10")
        self.assertEqual(sep["received"]["gross"], "15000.00")
        self.assertEqual(sep["received"]["for_current_period"], "15000.00")
        self.assertEqual(sep["received"]["backdated"], {"amount": "15000.00", "count": 1})
        self.assertEqual((sep["accrued"]["paid_in_period"], sep["accrued"]["unpaid_at_end"]), ("15000.00", "0.00"))
        self.assertEqual(sep["debt"]["closing"], "0.00")
        self.assertEqual(oct_["received"]["gross"], "0.00")

    def test_future_received_date_rejected(self):
        profile = self.september_contract()
        with self.assertRaises(BillingError):
            self.pay(profile, "100", on=OCT24 + dt.timedelta(days=1))

    def test_october_money_for_september_debt(self):
        """Сентябрьский долг, оплаченный в октябре: уменьшает сентябрьское
        начисление, но это октябрьское поступление «за прошлые периоды»."""
        self.at(SEP1)
        profile = self.contract(start_date=SEP1)  # оформлен в сентябре
        self.at(SEP30)
        self.it_lessons(8)  # уроки проводятся в свои дни
        self.at(OCT5)
        self.day = OCT1
        self.it_lessons(4)  # месяц 1 закончен 4 октября → месяц 2 — октябрь
        payment = self.pay(profile, "15000", on=OCT5)
        month1, month2 = self.live_invoices(profile)
        self.assertEqual((month1.period_date, month2.period_date), (SEP1, dt.date(2026, 10, 4)))
        self.assertEqual(month1.status, Invoice.Status.PAID)  # деньги ушли на сентябрьский долг
        self.assertEqual(payment.billing_allocations.get().invoice_id, month1.pk)

        sep = self.report("2026-09")
        self.assertEqual(sep["received"]["gross"], "0.00")  # в сентябре денег не было
        self.assertEqual(sep["accrued"]["amount"], "15000.00")
        self.assertEqual(sep["accrued"]["unpaid_at_end"], "15000.00")
        self.assertEqual(sep["debt"]["closing"], "15000.00")  # «как было» на 30 сентября
        self.assertEqual(sep["accrued"]["paid_later"], "15000.00")
        self.assertEqual([(r["month"], r["amount"]) for r in sep["accrued"]["paid_later_by_month"]],
                         [("2026-10", "15000.00")])
        self.assertEqual(sep["accrued"]["unpaid_now"], "0.00")
        self.assertEqual([r["debt"] for r in sep["debtors_at_end"]], ["15000.00"])

        oct_ = self.report("2026-10")
        self.assertEqual(oct_["received"]["gross"], "15000.00")
        self.assertEqual((oct_["received"]["for_previous_periods"], oct_["received"]["for_current_period"]),
                         ("15000.00", "0.00"))
        self.assertEqual([(r["month"], r["amount"]) for r in oct_["received"]["previous_by_period"]],
                         [("2026-09", "15000.00")])
        self.assertEqual(oct_["debt"]["opening"], "15000.00")
        self.assertEqual(oct_["accrued"]["amount"], "15000.00")  # месяц 2
        self.assertEqual(oct_["debt"]["closing"], "15000.00")  # сентябрь погашен, октябрь нет
        # Аналитика «долг на конец» тоже считает по дате денег, а не по записи распределения.
        debt = analytics.debt_as_of(Invoice.objects.filter(pk=month1.pk), SEP30)
        self.assertEqual(debt, D("15000"))
        self.assertEqual(analytics.debt_as_of(Invoice.objects.filter(pk=month1.pk), OCT5), D("0"))

    def test_new_records_do_not_rewrite_september(self):
        self.at(SEP20)
        profile = self.september_contract()
        self.pay(profile, "5000", on=SEP20)
        self.at(SEP30)
        snapshot = self.report("2026-09")
        self.at(OCT24)
        self.day = OCT1
        self.it_lessons(6)
        self.pay(profile, "25000", on=OCT5)
        self.contract(start_date=OCT1)  # новый октябрьский студент
        after = self.report("2026-09")
        self.assertEqual(after["received"]["gross"], snapshot["received"]["gross"])
        self.assertEqual(after["debt"], snapshot["debt"])
        for field in ("amount", "count", "paid_in_period", "unpaid_at_end"):
            self.assertEqual(after["accrued"][field], snapshot["accrued"][field], field)
        self.assertEqual(after["accrued"]["paid_later"], "10000.00")  # октябрьские деньги — «позже», не сентябрь

    def test_reversed_allocation_is_not_counted_in_history(self):
        """Исправленная ошибка (сторно) не считается оплатой ни в какую дату."""
        profile = self.september_contract()
        wrong = self.pay(profile, "15000", on=SEP20)
        payments.reverse_payment(wrong, actor=self.accountant, reason="Внесён не тому студенту")
        self.assertEqual(self.report("2026-09")["debt"]["closing"], "15000.00")
        self.assertEqual(self.report("2026-09")["received"]["gross"], "0.00")

    def test_historical_adjustment_date(self):
        profile = self.september_contract()
        (invoice,) = self.live_invoices(profile)
        invoices.adjust_invoice(invoice, actor=self.admin, amount="15000", reason="Оплачено наличными до учёта",
                                effective_date=SEP20)
        self.assertEqual(self.report("2026-09")["debt"]["closing"], "0.00")
        invoice2 = self.live_invoices(self.contract(student=self.student(self.group_b), start_date=SEP1))[0]
        invoices.adjust_invoice(invoice2, actor=self.admin, amount="1000", reason="Перерасчёт")  # сегодня
        sep = self.report("2026-09")
        self.assertEqual((sep["debt"]["closing"], sep["accrued"]["adjusted_later"]), ("15000.00", "1000.00"))
        with self.assertRaises(BillingError):
            invoices.adjust_invoice(invoice2, actor=self.admin, amount="1", reason="x", effective_date=OCT31)


class PeriodReviewTests(PeriodFixture):
    def legacy(self, profile):
        """Как было до `period_date`: период = дата выставления (день оформления)."""
        Invoice.objects.filter(profile=profile).update(period_date=OCT24)
        return self.live_invoices(profile)[0]

    def test_review_lists_and_fixes_with_audit(self):
        with_lessons = self.september_contract()
        no_lessons = self.contract(student=self.student(self.group_b), start_date=SEP1)
        lessons_inv, empty_inv = self.legacy(with_lessons), self.legacy(no_lessons)
        rows = {r["invoice"]: r for r in periods.period_review()}
        self.assertEqual(rows[lessons_inv.pk]["proposed"], "2026-09-01")
        self.assertTrue(rows[empty_inv.pk]["ambiguous"])
        self.assertIsNone(rows[empty_inv.pk]["proposed"])
        changed = periods.apply_period_review(actor=self.admin)
        self.assertEqual([r["invoice"] for r in changed], [lessons_inv.pk])
        lessons_inv.refresh_from_db()
        empty_inv.refresh_from_db()
        self.assertEqual((lessons_inv.period_date, empty_inv.period_date), (SEP1, OCT24))  # неоднозначное не тронуто
        self.assertEqual((lessons_inv.issue_date, lessons_inv.amount), (OCT24, D("15000")))
        log = PayrollAuditLog.objects.get(action="billing_invoice_period", entity_id=lessons_inv.pk)
        self.assertEqual((log.old_values, log.new_values), ({"period_date": "2026-10-24"}, {"period_date": "2026-09-01"}))
        self.assertEqual(periods.apply_period_review(actor=self.admin), [])  # повтор ничего не меняет

    def test_manual_correction_requires_reason_and_rights(self):
        invoice = self.legacy(self.contract(start_date=SEP1))
        with self.assertRaises(BillingError):
            invoices.correct_invoice_period(invoice, actor=self.admin, period_date=SEP1, reason="")
        with self.assertRaises(BillingError):
            invoices.correct_invoice_period(invoice, actor=self.manager, period_date=SEP1, reason="x")
        invoices.correct_invoice_period(invoice, actor=self.admin, period_date=SEP1, reason="Договор с сентября")
        invoice.refresh_from_db()
        self.assertEqual(invoice.period_date, SEP1)


class PeriodApiTests(PeriodFixture):
    def test_month_switcher_and_period_report(self):
        profile = self.september_contract()
        self.pay(profile, "15000", on=SEP20)
        api = self.client_for(self.accountant)
        data = api.get(BASE + "periods/").data
        labels = {m["value"]: m["label"] for m in data["months"]}
        self.assertEqual((data["current"], labels["2026-09"], labels["2026-10"], labels["2026-11"]),
                         ("2026-10", "Сентябрь 2026", "Октябрь 2026", "Ноябрь 2026"))
        sep = api.get(BASE + "reports/period/", {"month": "2026-09"}).data
        self.assertEqual((sep["label"], sep["received"]["gross"], sep["accrued"]["amount"]),
                         ("Сентябрь 2026", "15000.00", "15000.00"))
        custom = api.get(BASE + "reports/period/", {"date_from": "2026-09-15", "date_to": "2026-10-10"}).data
        self.assertEqual((custom["received"]["gross"], custom["accrued"]["amount"]), ("15000.00", "0.00"))
        self.assertEqual(api.get(BASE + "reports/period/", {"month": "2026-13"}).status_code, 400)
        invoices_sep = api.get(BASE + "invoices/", {"date_from": "2026-09-01", "date_to": "2026-09-30"}).data
        self.assertEqual(invoices_sep["count"], 1)
        self.assertEqual(api.get(BASE + "invoices/", {"date_from": "2026-10-01", "date_to": "2026-10-31"}).data["count"], 0)
        self.assertEqual(api.get(BASE + "payments/", {"date_from": "2026-09-01", "date_to": "2026-09-30"}).data["count"], 1)
        self.assertEqual(self.client_for(self.manager).get(BASE + "reports/period/").status_code, 403)

    def test_add_payment_with_past_date_and_purpose(self):
        profile = self.september_contract()
        api = self.client_for(self.accountant)
        response = api.post(BASE + "payments/", {
            "profile": profile.pk, "amount": "20000", "received_date": "2026-09-20", "mode": "auto",
        }, format="json", HTTP_IDEMPOTENCY_KEY="sep-1")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual((response.data["received_date"], response.data["unallocated"]), ("2026-09-20", "5000.00"))
        self.assertEqual(response.data["allocations"][0]["invoice_period_date"], "2026-09-01")
        advance = api.post(BASE + "payments/", {
            "profile": profile.pk, "amount": "1000", "received_date": "2026-10-01", "mode": "advance",
        }, format="json", HTTP_IDEMPOTENCY_KEY="oct-1")
        self.assertEqual(advance.data["purpose"], StudentPayment.Purpose.PREPAYMENT)

    def test_registration_payment_on_chosen_date(self):
        self.it_lessons(3)
        api = self.client_for(self.accountant)
        response = api.post(BASE + "profiles/", {
            "student": self.student().pk, "plan": self.kc.pk, "start_date": "2026-09-01",
            "initial_payment": "15000", "payment_received_date": "2026-09-01",
        }, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        payment = StudentPayment.objects.get(billing_profile_id=response.data["id"])
        self.assertEqual(payment.received_date, SEP1)
        invoice = Invoice.objects.get(profile_id=response.data["id"])
        self.assertEqual((invoice.period_date, invoice.status), (SEP1, Invoice.Status.PAID))

    def test_invoice_period_correction_endpoint(self):
        invoice = self.live_invoices(self.contract(start_date=SEP1))[0]
        Invoice.objects.filter(pk=invoice.pk).update(period_date=OCT24)
        url = BASE + f"invoices/{invoice.pk}/period/"
        self.assertEqual(self.client_for(self.accountant).post(url, {"period_date": "2026-09-01"}).status_code, 400)
        self.assertEqual(self.client_for(self.director).post(url, {"period_date": "2026-09-01", "reason": "x"}).status_code, 403)
        ok = self.client_for(self.accountant).post(url, {"period_date": "2026-09-01", "reason": "Договор с сентября"})
        self.assertEqual((ok.status_code, ok.data["period_date"]), (200, "2026-09-01"))
        review = self.client_for(self.accountant).get(BASE + "periods/review/").data
        self.assertEqual(review["count"], 0)
