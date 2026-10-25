"""Предоплата за весь курс (сценарий «Бекнур Абдыбеков»): стандартная 60 000,
итоговая 53 000, 4 месяца, платёж 53 000, начисление «Весь курс» оплачено.

«Весь курс» — одно начисление договора, а не стоимость месяца №1: каждый
месяц показывает свою долю курса и закрыт его оплатой; долга, просрочки и
«Скоро оплата» нет; уроки и месяцы не создают новых начислений; деньги
учитываются один раз. Плюс частичная, помесячная оплата, план месяцев,
изменение цены и добровольная доплата."""
from __future__ import annotations

import datetime as dt

from apps.accounting.models import StudentPayment
from apps.billing.models import Invoice, PaymentAllocation, PaymentMode
from apps.billing.services import contracts, payments, profiles, queues
from apps.billing.services.reports import dashboard, reconcile
from apps.billing.tests.base import D
from apps.billing.tests.test_contracts import BASE
from apps.billing.tests.test_periods import OCT24, PeriodFixture

SEP1 = dt.date(2026, 9, 1)


class PrepayFixture(PeriodFixture):
    def setUp(self):
        super().setUp()
        self.at(SEP1)

    def beknur(self, paid="53000", **extra):
        profile = self.contract(start_date=SEP1, payment_mode=PaymentMode.FULL_PREPAY, discount_enabled=True,
                                final_course_price="53000", discount_reason="Скидка", **extra)
        payment = self.pay(profile, paid, on=SEP1) if paid else None
        return profile, payment

    def lessons(self, n):
        self.at(OCT24)
        self.it_lessons(n)

    def fresh(self, profile):
        profile.refresh_from_db()
        return profile

    def queues_of(self, profile) -> set[str]:
        return {q for q in ("to_pay", "soon", "overdue")
                if profile.pk in [r["profile"] for r in queues.queue_rows(q, {})]}


class FullPrepayTests(PrepayFixture):
    def test_paid_course_has_no_debt_and_months_show_course_shares(self):
        profile, payment = self.beknur()
        self.lessons(14)  # месяц 1 пройден, месяц 2 идёт
        profile = self.fresh(profile)
        s = contracts.money_summary(profile)
        self.assertEqual((s["due_now"], s["overdue"], s["outstanding"], s["net_to_pay"], s["credit"]),
                         (0, 0, 0, 0, 0))
        self.assertTrue(s["course_paid_in_full"])
        schedule = contracts.payment_schedule(profile)
        self.assertEqual((schedule["course"]["amount"], schedule["course"]["paid"], schedule["course"]["paid_in_full"]),
                         (D("53000"), D("53000"), True))
        months = schedule["months"]
        self.assertEqual([(m["month_number"], m["state"], m["kind"], m["amount"], m["paid"]) for m in months],
                         [(n, "prepaid", Invoice.Kind.COURSE, D("13250"), D("13250")) for n in range(1, 5)])
        self.assertNotIn(D("53000"), [m["amount"] for m in months])  # не «стоимость месяца №1»
        self.assertTrue(all(m["to_pay"] == 0 and m["balance"] == 0 for m in months))
        self.assertEqual((schedule["invoiced"], schedule["projected"], schedule["total"], schedule["consistent"]),
                         (D("53000"), D("0"), D("53000"), True))
        # Деньги — один раз: один платёж 53 000, одно распределение на «Весь курс».
        payment.refresh_from_db()
        self.assertEqual(payment.amount, D("53000"))
        self.assertEqual(list(PaymentAllocation.objects.filter(profile=profile, status="ACTIVE")
                              .values_list("invoice__kind", "amount")), [(Invoice.Kind.COURSE, D("53000"))])
        self.assertEqual(Invoice.objects.filter(profile=profile).exclude(status="VOID").count(), 1)
        # Очереди и «Скоро оплата»: ученика нет; следующий месяц — доля курса, к оплате 0.
        self.assertEqual(self.queues_of(profile), set())
        nxt = contracts.next_month_cost(profile)
        self.assertEqual((nxt["month_number"], nxt["cost"], nxt["covered"], nxt["to_pay"]),
                         (3, D("13250"), D("13250"), D("0")))
        self.assertEqual(reconcile(), [])

    def test_card_api_and_whole_course_lessons_create_no_new_charges(self):
        profile, _ = self.beknur()
        self.lessons(48)  # весь курс пройден
        profile = self.fresh(profile)
        self.assertEqual(Invoice.objects.filter(profile=profile).exclude(status="VOID").count(), 1)
        self.assertEqual(profile.status, profile.Status.COMPLETED)
        card = self.client_for(self.accountant).get(BASE + f"profiles/{profile.pk}/card/").data
        self.assertIs(card["summary"]["course_paid_in_full"], True)
        self.assertEqual((card["summary"]["due_now"], card["summary"]["overdue"], card["summary"]["net_to_pay"]),
                         ("0.00", "0.00", "0.00"))
        self.assertEqual([m["invoice"] for m in card["months"]], [None] * 4)  # «Весь курс» не на месяце №1
        self.assertEqual([(m["course_share"]["amount"], m["course_share"]["paid_in_full"]) for m in card["months"]],
                         [("13250.00", True)] * 4)
        self.assertEqual([i["kind"] for i in card["invoices"]], [Invoice.Kind.COURSE])
        self.assertEqual(card["schedule"]["course"]["status"], Invoice.Status.PAID)

    def test_partial_course_payment_counts_debt_once(self):
        profile, _ = self.beknur(paid="20000")
        self.lessons(14)
        profile = self.fresh(profile)
        s = contracts.money_summary(profile)
        self.assertEqual((s["outstanding"], s["course_paid_in_full"]), (D("33000"), False))
        schedule = contracts.payment_schedule(profile)
        self.assertEqual(schedule["course"]["balance"], D("33000"))
        self.assertEqual([(m["state"], m["paid"]) for m in schedule["months"]],
                         [("prepaid", D("13250")), ("course_due", D("6750")), ("course_due", D("0")),
                          ("course_due", D("0"))])
        self.assertEqual(sum((m["to_pay"] + m["balance"] for m in schedule["months"]), D("0")), 0)  # долг — у курса
        self.assertEqual(contracts.next_month_cost(profile)["to_pay"], 0)  # не второй раз в «Скоро оплата»
        self.assertNotIn("soon", self.queues_of(profile))
        self.assertTrue({"to_pay", "overdue"} & self.queues_of(profile))

    def test_month_plan_shares_follow_contract_plan(self):
        profile = profiles.create_student_billing_profile(
            student=self.student(), plan=self.kc, actor=self.accountant, start_date=SEP1,
            payment_mode=PaymentMode.FULL_PREPAY, discount_enabled=True, final_course_price="53000",
            discount_reason="Скидка", month_prices=["13000", "15000", "15000", "17000"], month_plan_mode="PROPORTIONAL",
            responsible_accountant=self.accountant,
        )
        self.pay(profile, "53000", on=SEP1)
        plan = [r.amount for r in profile.month_prices.order_by("month_number")]
        shares = [m["amount"] for m in contracts.payment_schedule(self.fresh(profile))["months"]]
        self.assertEqual(shares, plan)
        self.assertEqual(sum(shares, D("0")), D("53000"))

    def test_price_raise_after_full_payment_projects_one_surcharge(self):
        profile, _ = self.beknur()
        profiles.request_course_terms_change(profile, actor=self.accountant, discount_enabled=True,
                                             final_course_price="55000", reason="Доп. занятия")
        profile = self.fresh(profile)
        s = contracts.money_summary(profile)
        self.assertEqual((s["outstanding"], s["due_now"], s["course_paid_in_full"]), (D("2000"), D("0"), False))
        schedule = contracts.payment_schedule(profile)
        surcharge = [m for m in schedule["months"] if m["state"] == "future"]
        self.assertEqual([(m["month_number"], m["amount"]) for m in surcharge], [(2, D("2000"))])
        self.assertEqual((schedule["total"], schedule["consistent"]), (D("55000"), True))


class ExtraPaymentTests(PrepayFixture):
    def test_voluntary_payment_on_paid_course_becomes_advance(self):
        profile, _ = self.beknur()
        before = list(Invoice.objects.filter(profile=profile).values_list("pk", "status", "amount_paid"))
        preview = payments.preview_payment(profile, amount="1000")
        self.assertEqual((preview["course_paid_in_full"], D(preview["to_credit"]), preview["allocations"]),
                         (True, D("1000"), []))
        response = self.client_for(self.accountant).post(BASE + "payments/", {
            "profile": profile.pk, "amount": "1000", "received_date": SEP1.isoformat(), "method": "cash",
            "mode": "auto", "confirmed": True}, format="json", HTTP_IDEMPOTENCY_KEY="extra-1")
        self.assertIn(response.status_code, (200, 201), response.data)
        self.assertEqual(list(Invoice.objects.filter(profile=profile).values_list("pk", "status", "amount_paid")),
                         before)  # «Весь курс» не тронут, новых начислений нет
        s = contracts.money_summary(self.fresh(profile))
        self.assertEqual((s["received"], s["credit"], s["due_now"], s["outstanding"]),
                         (D("54000"), D("1000"), D("0"), D("0")))
        self.assertTrue(s["course_paid_in_full"])
        self.assertEqual(StudentPayment.objects.filter(billing_profile=profile, status="confirmed").count(), 2)

    def test_only_payment_takers_can_add_payment(self):
        profile, _ = self.beknur()
        body = {"profile": profile.pk, "amount": "1000", "received_date": SEP1.isoformat(), "method": "cash",
                "mode": "auto", "confirmed": True}
        for user in (self.director, self.manager):
            response = self.client_for(user).post(BASE + "payments/", body, format="json", HTTP_IDEMPOTENCY_KEY=f"x-{user.pk}")
            self.assertEqual(response.status_code, 403)
        me = {u: self.client_for(u).get(BASE + "me/").data["can_record_payments"] for u in (self.accountant, self.director)}
        self.assertEqual(me, {self.accountant: True, self.director: False})
        self.assertEqual(StudentPayment.objects.filter(billing_profile=profile).count(), 1)


class OtherModesTests(PrepayFixture):
    def test_monthly_schedule_is_unchanged_and_others_not_affected(self):
        monthly = self.contract(start_date=SEP1)
        self.pay(monthly, "15000", on=SEP1)
        other_before = contracts.payment_schedule(self.fresh(monthly))
        self.beknur()
        schedule = contracts.payment_schedule(self.fresh(monthly))
        self.assertEqual(schedule, other_before)
        self.assertIsNone(schedule["course"])
        self.assertEqual([(m["state"], m["amount"]) for m in schedule["months"]],
                         [("invoiced", D("15000")), ("future", D("15000")), ("future", D("15000")),
                          ("future", D("15000"))])
        self.assertFalse(contracts.money_summary(monthly)["course_paid_in_full"])
        self.assertTrue(all(m.get("kind") != Invoice.Kind.COURSE for m in schedule["months"]))

    def test_monthly_paid_in_advance_is_fully_paid_and_discounted_partial_is_not(self):
        upfront = self.contract(start_date=SEP1)
        self.pay(upfront, "60000", on=SEP1)
        self.assertTrue(contracts.money_summary(self.fresh(upfront))["course_paid_in_full"])
        discounted = self.contract(start_date=SEP1, discount_enabled=True, final_course_price="48000",
                                   discount_reason="Скидка")
        self.pay(discounted, "12000", on=SEP1)
        s = contracts.money_summary(self.fresh(discounted))
        self.assertEqual((s["outstanding"], s["course_paid_in_full"]), (D("36000"), False))
        self.assertEqual(D(dashboard({})["total_debt"]), 0)  # месяц 1 оплачен, будущие — не долг
