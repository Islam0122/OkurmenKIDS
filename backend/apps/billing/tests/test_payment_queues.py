"""Очереди «Скоро оплата» → «К оплате» → «Просроченные» — по актуальным
данным (`contracts.payment_stage`: сегодняшняя дата по часовому поясу
проекта, урок-срок, остаток), а не по сохранённому статусу начисления:
переход происходит при следующем запросе, без фоновой задачи и действий
бухгалтера; счётчики = списки; оплаченное — нигде; аванс — по правилам
договора; записи не меняются."""
from __future__ import annotations

import datetime as dt
from decimal import Decimal
from unittest import mock

from apps.billing.models import Invoice, LessonConsumption
from apps.billing.services import lessons, payments, pricing, profiles, queues
from apps.billing.services.contracts import payment_stage
from apps.billing.tests.base import BillingFixture, D
from apps.billing.tests.test_contracts import BASE
from apps.billing.tests.test_periods import OCT24, PeriodFixture

UTC = dt.timezone.utc


def at_utc(*args):
    """Подменить «сейчас» (UTC); `timezone.localdate()` переводит в Asia/Bishkek (UTC+6)."""
    return mock.patch("django.utils.timezone.now", return_value=dt.datetime(*args, tzinfo=UTC))


class QueueHelpers:
    def queues_of(self, profile) -> set[str]:
        return {q for q in ("soon", "to_pay", "overdue") if profile.pk in [r["profile"] for r in queues.queue_rows(q, {})]}

    def assert_counts_match_lists(self):
        counts = queues.counts({})
        self.assertEqual(counts, {q: len(queues.queue_rows(q, {})) for q in ("to_pay", "soon", "overdue")})
        api = self.client_for(self.accountant)
        self.assertEqual(api.get(BASE + "queues/counts/").data, counts)
        for q in ("to_pay", "soon", "overdue"):
            self.assertEqual(api.get(BASE + f"queues/{q}/").data["count"], counts[q], q)

    def row(self, profile):
        return queues.contract_row(queues.base_queryset().get(pk=profile.pk))


class DateDeadlineTests(QueueHelpers, BillingFixture):
    """Тариф пакетов (срок оплаты — дата: выставлено + 5 дней)."""

    def setUp(self):
        super().setUp()
        self.profile_ = self.profile()
        self.invoice = self.profile_.invoices.get()
        self.due = self.invoice.due_date

    def on(self, day: dt.date, hour_utc: int = 6):
        return at_utc(day.year, day.month, day.day, hour_utc)

    def test_not_due_today_due_and_passed_without_background_job(self):
        with self.on(self.due - dt.timedelta(days=1)):
            self.assertEqual((payment_stage(self.invoice), self.queues_of(self.profile_)), ("awaiting", {"to_pay"}))
            self.assert_counts_match_lists()
        with self.on(self.due):  # срок наступил сегодня
            self.assertEqual((payment_stage(self.invoice), self.queues_of(self.profile_)), ("deadline", {"to_pay"}))
            self.assertEqual(self.row(self.profile_)["due_today_amount"], "4000.00")
        with self.on(self.due + dt.timedelta(days=1)):  # срок прошёл — задача mark_overdue не запускалась
            self.invoice.refresh_from_db()
            self.assertEqual(self.invoice.status, Invoice.Status.OPEN)  # сохранённый статус ещё старый
            self.assertEqual((payment_stage(self.invoice), self.queues_of(self.profile_)), ("overdue", {"overdue"}))
            r = self.row(self.profile_)
            self.assertEqual((r["stage"], r["overdue_amount"], r["due_now"]), ("overdue", "4000.00", "4000.00"))
            self.assert_counts_match_lists()
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.status, Invoice.Status.OPEN)  # просмотр очередей записи не меняет

    def test_timezone_boundary_uses_bishkek_date(self):
        # 23:00 в Бишкеке в день срока (17:00 UTC) — ещё «К оплате»;
        # 01:30 следующего дня в Бишкеке (19:30 UTC дня срока) — уже просрочка.
        with self.on(self.due, hour_utc=17):
            self.assertEqual(self.queues_of(self.profile_), {"to_pay"})
        with at_utc(self.due.year, self.due.month, self.due.day, 19, 30):
            self.assertEqual(self.queues_of(self.profile_), {"overdue"})

    def test_fully_paid_is_in_no_queue_even_after_deadline(self):
        payments.record_payment(profile=self.profile_, amount="4000", received_date=self.today, actor=self.accountant)
        with self.on(self.due + dt.timedelta(days=3)):
            self.assertEqual(self.queues_of(self.profile_), set())
            self.assertEqual(self.row(self.profile_)["stage"], "paid")
            self.assert_counts_match_lists()

    def test_partial_payment_stays_with_the_remaining_amount(self):
        payments.record_payment(profile=self.profile_, amount="1500", received_date=self.today, actor=self.accountant)
        with self.on(self.due):
            r = self.row(self.profile_)
            self.assertEqual((self.queues_of(self.profile_), r["due_now"], r["due_today_amount"]),
                             ({"to_pay"}, "2500.00", "2500.00"))
        with self.on(self.due + dt.timedelta(days=1)):
            self.assertEqual((self.queues_of(self.profile_), self.row(self.profile_)["overdue_amount"]),
                             ({"overdue"}, "2500.00"))

    def test_credit_by_contract_rules_no_artificial_debt(self):
        # Аванс рядом с начислением (не распределён): по правилам договора он
        # учитывается в «к оплате», но начисление НЕ становится оплаченным.
        payments.record_payment(profile=self.profile_, amount="4000", received_date=self.today, actor=self.accountant,
                                auto_allocate=False)
        with self.on(self.due + dt.timedelta(days=2)):
            r = self.row(self.profile_)
            self.assertEqual((r["due_now"], r["overdue_amount"], r["credit"]), ("0.00", "0.00", "4000.00"))
            self.assertEqual(self.queues_of(self.profile_), set())  # к оплате 0 — искусственного долга нет
            self.assertNotEqual(payment_stage(self.invoice), "paid")  # но начисление не «Оплачено»
        self.invoice.refresh_from_db()
        self.assertEqual((self.invoice.status, self.invoice.amount_paid), (Invoice.Status.OPEN, D("0")))
        payments.record_payment(profile=self.profile_, amount="1000", received_date=self.today, actor=self.accountant,
                                auto_allocate=False)
        other = self.profile()  # частичный аванс: остаётся долг на разницу
        payments.record_payment(profile=other, amount="1000", received_date=self.today, actor=self.accountant,
                                auto_allocate=False)
        with self.on(self.due + dt.timedelta(days=2)):
            self.assertEqual((self.queues_of(other), self.row(other)["overdue_amount"]), ({"overdue"}, "3000.00"))


class LessonDeadlineTests(QueueHelpers, PeriodFixture):
    """Договор по программе: срок — 3-й урок месяца; «Скоро оплата» — за 3 урока до конца месяца."""

    def setUp(self):
        super().setUp()
        self.at(OCT24)
        self.day = dt.date(2026, 9, 2)

    def test_soon_then_to_pay_then_overdue_by_lessons(self):
        profile = self.contract(start_date=dt.date(2026, 9, 1))
        self.pay(profile, "15000", on=OCT24)  # месяц 1 оплачен
        self.it_lessons(8)
        self.assertEqual(self.queues_of(profile), set())
        self.it_lessons(1)  # 9/12 — осталось 3: следующий месяц приближается, не покрыт
        self.assertEqual(self.queues_of(profile), {"soon"})
        self.assert_counts_match_lists()
        self.it_lessons(3)  # 12-й урок: начисление месяца 2 выставлено — срок оплаты наступил
        self.assertEqual(self.queues_of(profile), {"to_pay"})
        self.it_lessons(2)  # уроки 1–2 месяца 2
        self.assertEqual(self.queues_of(profile), {"to_pay"})
        self.it_lessons(1)  # 3-й урок — последний срок
        self.assertEqual((self.queues_of(profile), self.row(profile)["stage"]), ({"to_pay"}, "deadline"))
        self.it_lessons(1)  # 4-й урок — просрочка
        self.assertEqual((self.queues_of(profile), self.row(profile)["stage"]), ({"overdue"}, "overdue"))
        self.assert_counts_match_lists()

    def test_reversed_lesson_returns_from_overdue_without_manual_action(self):
        profile = self.contract(start_date=dt.date(2026, 9, 1))
        self.it_lessons(4)  # месяц 1 не оплачен, 4-й урок — просрочка
        self.assertEqual(self.queues_of(profile), {"overdue"})
        last = LessonConsumption.objects.filter(profile=profile).order_by("-lesson_date").first()
        lessons.reverse_consumption(last, actor=self.accountant, reason="Урок не состоялся")
        self.assertEqual(Invoice.objects.get(profile=profile).status, Invoice.Status.OVERDUE)  # сохранённый — старый
        self.assertEqual((self.queues_of(profile), self.row(profile)["stage"]), ({"to_pay"}, "deadline"))

    def test_several_invoices_with_different_deadlines(self):
        profile = self.contract(start_date=dt.date(2026, 9, 1))
        self.it_lessons(13)  # месяц 1 не оплачен (просрочен), месяц 2 выставлен, 1-й урок
        r = self.row(profile)
        self.assertEqual((r["overdue_amount"], r["not_due_amount"], r["due_now"]), ("15000.00", "15000.00", "30000.00"))
        self.assertEqual(self.queues_of(profile), {"to_pay", "overdue"})
        payments.record_payment(profile=profile, amount="15000", received_date=OCT24, actor=self.accountant)
        self.assertEqual(self.queues_of(profile), {"to_pay"})  # просроченный месяц 1 закрыт первым
        self.assert_counts_match_lists()

    def test_early_invoice_moves_student_from_soon_to_to_pay(self):
        plan = pricing.create_plan(
            actor=self.accountant, name="Пакеты с ранним счётом", subject=self.it, lessons_per_package=12,
            package_price=D("4000"), effective_from=self.start, payment_due_days=5, early_invoice_enabled=True,
            early_invoice_after_lessons=10)
        start = dt.date(2026, 10, 14)  # уроки 14–23.10: срок раннего счёта (+5 дней) ещё впереди
        profile = profiles.create_student_billing_profile(
            student=self.student(), plan=plan, actor=self.accountant, start_date=start,
            responsible_accountant=self.accountant)
        self.pay(profile, "4000", on=OCT24)
        self.hold(9, start_day=start)
        self.assertEqual(self.queues_of(profile), {"soon"})
        lessons.sync_lesson(self.lesson(day=start + dt.timedelta(days=9)).pk)  # 10-й урок: счёт следующего пакета
        self.assertEqual(Invoice.objects.filter(profile=profile).count(), 2)
        self.assertEqual(self.queues_of(profile), {"to_pay"})  # начисление выставлено — не «Скоро»
        self.assertEqual(Decimal(self.row(profile)["due_now"]), D("4000"))
