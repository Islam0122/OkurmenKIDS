"""«Скоро оплата»: подразделы 1–3 / 4–5 / 6–10 дней, «Следующий месяц»,
«Полностью оплатили курс» (`services.soon`, `queues.soon_page`).

Дата срока — по действующим правилам (дата начисления; урок-срок по
расписанию группы), дни — календарные по Asia/Bishkek. Единица — финансовое
обязательство: одно обязательство — один подраздел; у студента их может быть
несколько. «Курс оплачен» — `contracts.course_paid_in_full`. Только чтение."""
from __future__ import annotations

import datetime as dt

from apps.billing.models import Invoice, InvoiceAdjustment, PaymentAllocation, PaymentMode, StudentBillingProfile
from apps.billing.services import contracts, invoices, payments, pricing, profiles, queues
from apps.billing.services.soon import SECTIONS, TIME_SECTIONS, section_for
from rest_framework.test import APIClient

from apps.billing.tests.base import D, make_user
from apps.billing.tests.test_contracts import BASE
from apps.billing.tests.test_periods import OCT24, PeriodFixture
from apps.users.models import User

OCT25 = dt.date(2026, 10, 25)


class SectionRuleTests(PeriodFixture):
    """Правило подраздела по дате срока (календарные дни, календарный месяц)."""

    def test_exact_day_boundaries(self):
        today = dt.date(2026, 10, 10)
        expected = {0: None, 1: "days_1_3", 3: "days_1_3", 4: "days_4_5", 5: "days_4_5", 6: "days_6_10",
                    10: "days_6_10", 11: None, -1: None}
        for days, section in expected.items():
            self.assertEqual(section_for(today + dt.timedelta(days=days), today), section, days)

    def test_next_calendar_month_not_30_days(self):
        today = dt.date(2026, 10, 24)
        self.assertEqual(section_for(dt.date(2026, 11, 3), today), "days_6_10")  # 10 дней — ранний подраздел
        self.assertEqual(section_for(dt.date(2026, 11, 4), today), "next_month")
        self.assertEqual(section_for(dt.date(2026, 11, 30), today), "next_month")  # 37 дней, но ноябрь
        self.assertEqual(section_for(dt.date(2026, 12, 1), today), None)  # через месяц — не «следующий»
        self.assertEqual(section_for(dt.date(2026, 10, 31), dt.date(2026, 10, 1)), None)  # тот же месяц, > 10 дней
        self.assertEqual(section_for(None, today), None)  # даты нет — нигде

    def test_month_and_year_end(self):
        self.assertEqual(section_for(dt.date(2027, 1, 1), dt.date(2026, 12, 28)), "days_4_5")
        self.assertEqual(section_for(dt.date(2027, 1, 20), dt.date(2026, 12, 15)), "next_month")
        self.assertEqual(section_for(dt.date(2027, 2, 1), dt.date(2026, 12, 15)), None)
        self.assertEqual(section_for(dt.date(2027, 2, 28), dt.date(2027, 1, 31)), "next_month")
        self.assertEqual(section_for(dt.date(2027, 3, 1), dt.date(2027, 1, 31)), None)
        self.assertEqual(section_for(dt.date(2026, 12, 31), dt.date(2026, 11, 30)), "next_month")


class SoonHelpers:
    def page(self, section=None, **f):
        return queues.soon_page({"section": section, **f})

    def sections_of(self, profile) -> set[str]:
        return {s for s in SECTIONS if profile.pk in [r["profile"] for r in self.page(s)["rows"]]}

    def obligations(self, profile) -> list[tuple]:
        rows = [r for r in self.page()["rows"] if r["profile"] == profile.pk]
        return [(o["source"], o["section"], o["days"], o["to_pay"]) for r in rows for o in r["upcoming"]]

    def queue_ids(self, queue) -> set[int]:
        return {r["profile"] for r in queues.queue_rows(queue, {})}

    def payment_state(self, profile) -> dict:
        (row,) = [r for r in queues._rows("soon", {"contract_status": profile.status}) if r["profile"] == profile.pk]
        return row["course_payment"]


class DateDeadlineSoonTests(SoonHelpers, PeriodFixture):
    """Тариф пакетов: срок — дата начисления (выставлено + N дней)."""

    def setUp(self):
        super().setUp()
        self.p30 = pricing.create_plan(
            actor=self.accountant, name="Пакеты 30 дней", subject=self.it, lessons_per_package=12,
            package_price=D("4000"), effective_from=self.start - dt.timedelta(days=200), payment_due_days=30)
        self.p5 = pricing.create_plan(
            actor=self.accountant, name="Пакеты 5 дней", subject=self.it, lessons_per_package=12,
            package_price=D("4000"), effective_from=self.start - dt.timedelta(days=200), payment_due_days=5)

    def date_profile(self, plan=None, on=OCT24):
        self.at(on)
        return self.profile(plan=plan or self.p30, start_date=on)

    def test_exact_days_and_tomorrow(self):
        profile = self.date_profile()
        due = profile.invoices.get().due_date
        self.assertEqual(due, dt.date(2026, 11, 23))
        for days, section in ((1, "days_1_3"), (3, "days_1_3"), (4, "days_4_5"), (5, "days_4_5"),
                              (6, "days_6_10"), (10, "days_6_10")):
            self.at(due - dt.timedelta(days=days))
            self.assertEqual(self.obligations(profile), [("invoice", section, days, "4000.00")], days)
            self.assertEqual(self.sections_of(profile), {section})
        self.at(due - dt.timedelta(days=1))  # завтра — и «К оплате» (выставлено, срок не наступил)
        self.assertIn(profile.pk, self.queue_ids("to_pay"))
        self.at(due - dt.timedelta(days=11))  # 11 дней, тот же месяц — ни в одном подразделе
        self.assertEqual(self.sections_of(profile), set())

    def test_next_calendar_month(self):
        profile = self.date_profile()  # срок 23.11
        self.at(OCT24)  # 30 дней, ноябрь — следующий месяц
        self.assertEqual(self.obligations(profile), [("invoice", "next_month", 30, "4000.00")])
        self.at(dt.date(2026, 11, 1))  # 22 дня, тот же месяц
        self.assertEqual(self.sections_of(profile), set())

    def test_year_end(self):
        profile = self.date_profile(on=dt.date(2026, 12, 2))  # срок 1.01.2027
        self.at(dt.date(2026, 12, 10))
        self.assertEqual(self.obligations(profile), [("invoice", "next_month", 22, "4000.00")])
        self.at(dt.date(2026, 12, 28))
        self.assertEqual(self.obligations(profile), [("invoice", "days_4_5", 4, "4000.00")])

    def test_today_and_overdue_are_not_future(self):
        profile = self.date_profile()
        due = profile.invoices.get().due_date
        self.at(due)  # срок сегодня — «К оплате» по действующему правилу, не будущий платёж
        self.assertEqual((self.sections_of(profile), profile.pk in self.queue_ids("to_pay")), (set(), True))
        self.at(due + dt.timedelta(days=1))  # срок прошёл — «Просроченные»
        self.assertEqual(self.sections_of(profile), set())
        self.assertEqual((self.queue_ids("overdue") & {profile.pk}, self.queue_ids("to_pay") & {profile.pk}),
                         ({profile.pk}, set()))

    def test_bishkek_date_decides_days(self):
        profile = self.date_profile(plan=self.p5)  # срок 29.10
        self.clock.now = lambda: dt.datetime(2026, 10, 24, 17, 0, tzinfo=dt.timezone.utc)  # 23:00 24.10 в Бишкеке
        self.assertEqual(self.obligations(profile), [("invoice", "days_4_5", 5, "4000.00")])
        self.clock.now = lambda: dt.datetime(2026, 10, 24, 19, 0, tzinfo=dt.timezone.utc)  # 01:00 25.10 в Бишкеке
        self.assertEqual(self.obligations(profile), [("invoice", "days_4_5", 4, "4000.00")])
        self.clock.now = lambda: dt.datetime(2026, 10, 25, 19, 0, tzinfo=dt.timezone.utc)  # 01:00 26.10
        self.assertEqual(self.obligations(profile), [("invoice", "days_1_3", 3, "4000.00")])

    def test_fully_paid_invoice_is_not_upcoming(self):
        profile = self.date_profile(plan=self.p5)
        payments.record_payment(profile=profile, amount="4000", received_date=OCT24, actor=self.accountant)
        self.assertEqual((self.sections_of(profile), self.obligations(profile)), (set(), []))
        # Тариф пакетов — без итоговой стоимости курса: «Курс оплачен» не определяется.
        self.assertIsNone(self.payment_state(profile))

    def test_several_invoices_in_different_sections(self):
        profile = self.date_profile(plan=self.p5, on=dt.date(2026, 10, 21))  # пакет 1: срок 26.10
        self.at(OCT24)
        invoices.create_next_package_invoice(profile, actor=None, on_date=OCT24)  # пакет 2 вперёд: срок 29.10
        self.assertEqual(self.obligations(profile), [("invoice", "days_1_3", 2, "4000.00"),
                                                     ("invoice", "days_4_5", 5, "4000.00")])
        self.assertEqual(self.sections_of(profile), {"days_1_3", "days_4_5"})
        sections = self.page()["sections"]
        self.assertEqual((sections["days_1_3"], sections["days_4_5"]),
                         ({"count": 1, "amount": "4000.00"}, {"count": 1, "amount": "4000.00"}))
        (to_pay_row,) = [r for r in queues.queue_rows("to_pay", {}) if r["profile"] == profile.pk]
        self.assertEqual(to_pay_row["due_now"], "8000.00")  # «К оплате» — как прежде, оба начисления
        # Аванс закрывает раньше ближайший срок; разные начисления не объединяются.
        payments.record_payment(profile=profile, amount="5000", received_date=OCT24, actor=self.accountant,
                                auto_allocate=False)
        rows = [r for r in self.page()["rows"] if r["profile"] == profile.pk]
        self.assertEqual([(o["section"], o["credit_applied"], o["to_pay"]) for r in rows for o in r["upcoming"]],
                         [("days_4_5", "1000.00", "3000.00")])
        self.assertEqual(self.sections_of(profile), {"days_4_5"})


class LessonDeadlineSoonTests(SoonHelpers, PeriodFixture):
    """Договор по программе 4 × 15 000 (60 000), срок — 3-й урок IT месяца.
    Сегодня 24.10; расписание IT — каждый день с 25.10."""

    def setUp(self):
        super().setUp()
        self.at(OCT24)
        self.day = dt.date(2026, 9, 2)

    def kc_contract(self, **extra):
        return self.contract(start_date=dt.date(2026, 9, 1), **extra)

    def schedule(self, n=30):
        self.plan_lessons(n, start_day=OCT25)

    def test_without_schedule_date_is_not_confirmed(self):
        profile = self.kc_contract()
        self.pay(profile, "15000", on=OCT24)
        self.it_lessons(9)
        page = self.page()
        self.assertEqual((self.sections_of(profile), page["undated"]), (set(), 1))
        self.schedule()
        self.assertEqual((self.obligations(profile), self.page()["undated"]),
                         ([("forecast", "days_6_10", 6, "15000.00")], 0))

    def test_paused_student_has_no_forecast_date(self):
        profile = self.kc_contract()
        self.pay(profile, "15000", on=OCT24)
        self.it_lessons(9)
        self.schedule()
        StudentBillingProfile.objects.filter(pk=profile.pk).update(status=StudentBillingProfile.Status.PAUSED)
        self.assertEqual(self.sections_of(profile), set())

    def test_current_month_paid_but_not_course(self):
        profile = self.kc_contract()
        self.pay(profile, "15000", on=OCT24)  # оплачен только месяц 1
        self.it_lessons(9)
        self.schedule()
        self.assertEqual(Invoice.objects.get(profile=profile).status, Invoice.Status.PAID)
        state = self.payment_state(profile)
        self.assertEqual((state["paid_in_full"], state["unpaid"]), (False, "45000.00"))
        self.assertEqual(self.sections_of(profile), {"days_6_10"})  # не «Курс оплачен»

    def test_fully_paid_course_only_in_paid_section(self):
        monthly = self.kc_contract()
        self.pay(monthly, "60000", on=OCT24)  # месяц 1 распределён, 45 000 — аванс на будущие месяцы
        upfront = self.kc_contract(payment_mode=PaymentMode.FULL_PREPAY)
        self.pay(upfront, "60000", on=OCT24)
        self.it_lessons(9)
        self.schedule()
        for profile in (monthly, upfront):
            self.assertEqual(self.sections_of(profile), {"paid_course"})
            self.assertEqual(self.obligations(profile), [])  # искусственной суммы к оплате нет
            self.assertTrue(contracts.money_summary(profile)["course_paid_in_full"])  # то же правило, что карточка
        self.assertEqual(self.page("paid_course")["sections"]["paid_course"], {"count": 2, "amount": "0.00"})
        self.assertTrue(self.queue_ids("soon").isdisjoint({monthly.pk, upfront.pk}))  # бейдж «Скоро» — без них

    def test_withdrawn_without_debt_is_not_paid_course(self):
        """Ушёл после оплаченного месяца 1: долга нет (начисления остановлены),
        но курс не оплачен — не «Курс оплачен» (ни в карточке, ни здесь)."""
        profile = self.kc_contract()
        self.pay(profile, "15000", on=OCT24)
        self.it_lessons(5)
        profiles.deactivate_billing_profile(profile, actor=self.accountant, reason="Ушёл")
        profile.refresh_from_db()
        summary = contracts.money_summary(profile)
        self.assertEqual((summary["due_now"], summary["outstanding"], summary["course_paid_in_full"]),
                         (D("0"), D("0"), False))
        self.assertFalse(self.payment_state(profile)["paid_in_full"])
        self.assertEqual(self.page("paid_course", contract_status="INACTIVE")["rows"], [])

    def test_partially_paid_course(self):
        profile = self.kc_contract()
        self.pay(profile, "35000", on=OCT24)  # месяц 1 + 20 000 аванса
        self.it_lessons(9)
        self.schedule()
        state = self.payment_state(profile)
        self.assertEqual((state["paid_in_full"], state["unpaid"], state["credit"]), (False, "25000.00", "20000.00"))
        self.assertEqual(self.sections_of(profile), set())  # месяц 2 закрыт авансом — платежа нет
        self.pay(profile, "0.01", on=OCT24)
        self.assertEqual(self.payment_state(profile)["paid_in_full"], False)
        other = self.kc_contract()
        self.pay(other, "20000", on=OCT24)  # месяц 1 + 5 000 аванса на месяц 2
        self.it_lessons(0)
        rows = [r for r in self.page()["rows"] if r["profile"] == other.pk]
        self.assertEqual([(o["source"], o["credit_applied"], o["to_pay"]) for r in rows for o in r["upcoming"]],
                         [("forecast", "5000.00", "10000.00")])

    def test_confirmed_payment_and_unallocated_credit(self):
        profile = self.kc_contract()
        self.it_lessons(1)
        self.schedule()
        # Платёж подтверждён, но не распределён: месяц 1 ждёт оплаты, аванс его закрывает по правилам договора.
        self.pay(profile, "20000", on=OCT24, auto_allocate=False)
        self.assertEqual(Invoice.objects.get(profile=profile).status, Invoice.Status.OPEN)
        state = self.payment_state(profile)
        self.assertEqual((state["paid_in_full"], state["allocated"], state["credit"]), (False, "0.00", "20000.00"))
        # Месяц 1 покрыт авансом (не предстоящий платёж); остаток аванса 5 000 уменьшает месяц 2
        # (прогноз: 11 уроков до конца месяца 1 + 3 = 14-й урок, 7.11 — следующий месяц).
        self.assertEqual(self.obligations(profile), [("forecast", "next_month", 14, "10000.00")])
        full = self.kc_contract()
        self.pay(full, "60000", on=OCT24, auto_allocate=False)  # аванс покрывает весь курс
        self.assertTrue(self.payment_state(full)["paid_in_full"])

    def test_refund_void_and_adjustment(self):
        refunded = self.kc_contract()
        payment = self.pay(refunded, "60000", on=OCT24)
        self.assertTrue(self.payment_state(refunded)["paid_in_full"])
        payments.refund_payment(payment, actor=self.accountant, amount="15000", reason="Возврат части",
                                refund_date=OCT24)
        state = self.payment_state(refunded)
        self.assertEqual((state["paid_in_full"], state["unpaid"]), (False, "15000.00"))

        voided = self.kc_contract()
        payment = self.pay(voided, "60000", on=OCT24)
        payments.reverse_payment(payment, actor=self.accountant, reason="Ошибочный платёж")
        state = self.payment_state(voided)
        self.assertEqual((state["paid_in_full"], state["allocated"], state["unpaid"]), (False, "0.00", "60000.00"))
        self.assertEqual(PaymentAllocation.objects.filter(profile=voided, status="ACTIVE").count(), 0)

        adjusted = self.kc_contract()
        self.pay(adjusted, "45000", on=OCT24, auto_allocate=False)
        self.assertFalse(self.payment_state(adjusted)["paid_in_full"])
        invoices.adjust_invoice(Invoice.objects.get(profile=adjusted), actor=self.admin, amount="15000",
                                reason="Перерасчёт по решению директора")
        state = self.payment_state(adjusted)
        self.assertEqual((state["adjusted"], state["unpaid"], state["paid_in_full"]), ("15000.00", "0.00", True))
        self.assertEqual(InvoiceAdjustment.objects.filter(invoice__profile=adjusted).count(), 1)

    def test_obligations_in_different_sections(self):
        profile = self.kc_contract()
        self.it_lessons(13)  # месяц 1 просрочен (не в «Скоро»), месяц 2 выставлен, засчитан 1 урок
        self.schedule()
        # Месяц 2: срок — 3-й урок = 2-й запланированный (26.10). Месяц 3 — прогноз: 11 + 3 = 14-й урок, 7.11.
        self.assertEqual(self.obligations(profile), [("invoice", "days_1_3", 2, "15000.00"),
                                                     ("forecast", "next_month", 14, "15000.00")])
        self.assertEqual(self.sections_of(profile), {"days_1_3", "next_month"})
        self.assertIn(profile.pk, self.queue_ids("overdue"))  # просрочка — отдельно, как прежде
        (row,) = [r for r in self.page("days_1_3")["rows"] if r["profile"] == profile.pk]
        self.assertEqual((row["section_days"], row["section_to_pay"], row["overdue_amount"]), (2, "15000.00", "15000.00"))

    def test_counts_lists_and_sums_match(self):
        a = self.kc_contract()
        self.pay(a, "15000", on=OCT24)
        b = self.kc_contract()
        self.pay(b, "60000", on=OCT24)
        c = self.kc_contract()
        self.pay(c, "20000", on=OCT24)
        self.it_lessons(9)
        self.schedule()
        api = self.client_for(self.accountant)
        all_rows = queues._rows("soon", {})
        for section in SECTIONS:
            data = api.get(BASE + "queues/soon/", {"section": section, "page_size": 200}).data
            expected = sum((D(o["to_pay"]) for r in all_rows for o in r["upcoming"] if o["section"] == section),
                           D("0"))
            self.assertEqual((data["count"], len(data["results"])), (data["sections"][section]["count"],) * 2)
            self.assertEqual(D(data["sections"][section]["amount"]), expected, section)
            self.assertEqual(data["section"], section)
        data = api.get(BASE + "queues/soon/").data
        self.assertEqual(data["sections"]["days_6_10"], {"count": 2, "amount": "25000.00"})  # a 15 000 + c 10 000
        self.assertEqual(data["sections"]["paid_course"], {"count": 1, "amount": "0.00"})
        # Бейдж «Скоро оплата» = студенты временных подразделов = список без подраздела.
        time_students = {r["profile"] for s in TIME_SECTIONS for r in self.page(s)["rows"]}
        self.assertEqual(api.get(BASE + "queues/counts/").data["soon"], len(time_students), data["count"])
        self.assertEqual(time_students, {a.pk, c.pk})

    def test_search_filters_and_pagination(self):
        a = self.kc_contract(parent_phone="+996555111222")
        self.pay(a, "15000", on=OCT24)
        b = self.kc_contract()
        self.pay(b, "15000", on=OCT24)
        self.it_lessons(9)
        self.schedule()
        api = self.client_for(self.accountant)
        data = api.get(BASE + "queues/soon/", {"section": "days_6_10", "search": "555111"}).data
        self.assertEqual(([r["profile"] for r in data["results"]], data["sections"]["days_6_10"]["count"]), ([a.pk], 1))
        data = api.get(BASE + "queues/soon/", {"section": "days_6_10", "page_size": 1, "page": 2}).data
        self.assertEqual((data["count"], len(data["results"])), (2, 1))
        data = api.get(BASE + "queues/soon/", {"section": "days_6_10", "group": self.group_b.pk}).data
        self.assertEqual(data["count"], 0)

    def test_access_and_validation(self):
        api = self.client_for(self.accountant)
        self.assertEqual(api.get(BASE + "queues/soon/", {"section": "days_1_3"}).status_code, 200)
        self.assertEqual(api.get(BASE + "queues/soon/", {"section": "week"}).status_code, 400)
        self.assertEqual(self.client_for(self.director).get(BASE + "queues/soon/", {"section": "paid_course"})
                         .status_code, 200)
        self.assertEqual(self.client_for(self.manager).get(BASE + "queues/soon/", {"section": "days_1_3"})
                         .status_code, 403)
        self.assertEqual(self.client_for(self.manager).get(BASE + "queues/counts/").status_code, 403)
        teacher = make_user("plain_teacher", User.Role.TEACHER)
        self.assertEqual(self.client_for(teacher).get(BASE + "queues/soon/").status_code, 403)
        self.assertIn(APIClient().get(BASE + "queues/soon/").status_code, (401, 403))

    def test_reading_changes_no_records(self):
        profile = self.kc_contract()
        self.pay(profile, "20000", on=OCT24, auto_allocate=False)
        self.it_lessons(13)
        self.schedule()
        snapshot = lambda: (list(Invoice.objects.values_list("pk", "status", "amount_paid", "overdue_since")),
                            PaymentAllocation.objects.count(), InvoiceAdjustment.objects.count())
        before = snapshot()
        for section in SECTIONS:
            self.client_for(self.accountant).get(BASE + "queues/soon/", {"section": section})
        queues.counts({})
        self.assertEqual(snapshot(), before)
