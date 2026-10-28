"""Ручная корректировка учебного месяца: «Стандарт», «По плану», «Начисление».

Эталонный пример: курс 58 000 = 13 000 + 15 000 + 15 000 + 15 000, бронь
1 000 + платёж 10 000 зачтены в месяц №1, месяц №2 выставлен и не оплачен."""
from __future__ import annotations

from decimal import Decimal

from apps.accounting.models import PayrollAuditLog, StudentPayment
from apps.billing.models import BillingTermsChange, ContractMonthPrice, Invoice, InvoiceAdjustment, PaymentAllocation
from apps.billing.services import BillingError, contracts, invoices, month_edit, payments
from apps.billing.services import reservations as res_service
from apps.billing.tests.base import D, make_user
from apps.billing.tests.test_contracts import BASE, ContractFixture

PRICES = ["13000", "15000", "15000", "15000"]


class MonthEditFixture(ContractFixture):
    def example(self, **extra):
        """Договор 58 000 с бронью 1 000, оплатой 10 000 и выставленным месяцем №2."""
        profile = self.contract(discount_enabled=False,
                                month_prices=PRICES, month_plan_mode="PROPORTIONAL", reservation_amount="1000",
                                **extra)
        reservation = profile.reservations.get(status="PENDING")
        res_service.record_reservation_payment(reservation, actor=self.accountant, amount="1000",
                                               received_date=self.today)
        self.pay(profile, "10000")
        self.it_lessons(12)  # месяц №1 пройден — выставлен месяц №2
        return profile

    def plain(self, profile):
        profile.refresh_from_db()
        return contracts.money_summary(profile)

    def edit(self, profile, *, actor=None, dry_run=False, **fields):
        version = month_edit.schedule_version(profile)
        return month_edit.edit_month(profile, actor=actor or self.accountant, version=version, dry_run=dry_run,
                                     reason=fields.pop("reason", "ошибка расчёта"), **fields)

    def plan(self, profile):
        return {r.month_number: (r.standard_price, r.amount) for r in ContractMonthPrice.objects.filter(profile=profile)}


class ReferenceExampleTests(MonthEditFixture):
    def test_reference_example_totals_are_consistent(self):
        """Пункт 15 задачи: 17 000 долга + 30 000 будущих = 47 000; бронь не дважды."""
        profile = self.example()
        m1, m2 = self.live_invoices(profile)
        self.assertEqual((m1.amount, m1.amount_paid, m1.balance), (D("13000"), D("11000"), D("2000")))
        self.assertEqual((m2.amount, m2.amount_paid, m2.balance), (D("15000"), D("0"), D("15000")))
        s = self.plain(profile)
        self.assertEqual(s["final_course_price"], D("58000"))
        self.assertEqual(s["invoiced"], D("28000"))
        self.assertEqual(s["future"], D("30000"))
        self.assertEqual(s["net_received"], D("11000"))  # бронь 1 000 внутри 11 000
        self.assertEqual(s["reservation_received"], D("1000"))
        self.assertEqual(s["allocated"], D("11000"))
        self.assertEqual(s["credit"], D("0"))
        self.assertEqual(s["due_now"], D("17000"))
        self.assertEqual(s["net_to_pay"], D("47000"))
        self.assertEqual(s["net_received"], s["allocated"] + s["credit"])
        self.assertEqual(s["due_now"], m1.balance + m2.balance)
        self.assertEqual(s["net_to_pay"], s["due_now"] + s["future"])
        self.assertEqual(s["invoiced"] + s["future"], s["final_course_price"])

    def test_card_schedule_shows_three_separate_values(self):
        profile = self.example()
        card = self.client_for(self.accountant).get(BASE + f"profiles/{profile.pk}/card/").data
        rows = card["schedule"]["months"]
        self.assertEqual([r["standard"] for r in rows], ["13000.00", "15000.00", "15000.00", "15000.00"])
        self.assertEqual([r["plan"] for r in rows], ["13000.00", "15000.00", "15000.00", "15000.00"])
        self.assertEqual([r["charge"] for r in rows], ["13000.00", "15000.00", None, None])
        self.assertEqual([r["allocated"] for r in rows], ["11000.00", "0.00", "0.00", "0.00"])
        self.assertEqual([r["ui_status"] for r in rows], ["overdue", "awaiting", "future", "future"])
        self.assertEqual([r["editable"]["plan"] for r in rows], [False, False, True, True])
        self.assertEqual([r["editable"]["charge"] for r in rows], [True, True, False, False])
        self.assertTrue(card["schedule"]["version"])
        self.assertEqual((card["schedule"]["plan_total"], card["schedule"]["plan_difference"]), ("58000.00", "0.00"))
        self.assertEqual(card["debt"]["unpaid_count"], 2)
        self.assertEqual(card["debt"]["overdue_count"], 1)
        self.assertEqual(card["debt"]["next_due"]["month_number"], 2)
        # Будущие месяцы — без номера счёта.
        self.assertTrue(all(r.get("number") is None for r in rows[2:]))


class StandardAndPlanTests(MonthEditFixture):
    def test_standard_change_touches_only_standard_and_discount(self):
        profile = self.example()
        before = self.live_invoices(profile)
        result = self.edit(profile, month_number=3, standard_price="16000")
        profile.refresh_from_db()
        self.assertEqual(self.plan(profile)[3], (D("16000"), D("15000")))  # план не изменён
        self.assertEqual((profile.standard_course_price, profile.final_course_price, profile.discount_amount),
                         (D("59000"), D("58000"), D("1000")))
        self.assertEqual([(i.pk, i.amount) for i in self.live_invoices(profile)], [(i.pk, i.amount) for i in before])
        self.assertEqual(result["other_months"], [])
        self.assertEqual(result["course"]["before"]["net_to_pay"], result["course"]["after"]["net_to_pay"])

    def test_standard_below_final_is_rejected(self):
        profile = self.example()
        with self.assertRaises(BillingError) as error:
            self.edit(profile, month_number=4, standard_price="14000")
        self.assertEqual(error.exception.code, "above_standard")

    def test_future_plan_change_to_course_total(self):
        """Плановая сумма будущего месяца −1 000 → итоговая и «осталось» −1 000, долг тот же."""
        profile = self.example()
        preview = self.edit(profile, month_number=4, plan_amount="14000", dry_run=True)
        self.assertEqual(self.plan(profile)[4], (D("15000"), D("15000")))  # предпросмотр ничего не сохранил
        self.assertFalse(PayrollAuditLog.objects.filter(action="billing_month_edit").exists())
        course = preview["course"]
        self.assertEqual((course["before"]["final_course_price"], course["after"]["final_course_price"]),
                         (D("58000"), D("57000")))
        self.assertEqual((course["before"]["future"], course["after"]["future"]), (D("30000"), D("29000")))
        self.assertEqual(course["before"]["due_now"], course["after"]["due_now"])
        self.assertEqual(course["after"]["net_to_pay"], D("46000"))
        result = self.edit(profile, month_number=4, plan_amount="14000")
        self.assertTrue(result["changed"])
        profile.refresh_from_db()
        self.assertEqual((profile.final_course_price, profile.discount_amount, profile.month_plan_mode),
                         (D("57000"), D("1000"), "MANUAL"))
        self.assertEqual(self.plan(profile)[4], (D("15000"), D("14000")))
        self.assertTrue(BillingTermsChange.objects.filter(profile=profile, final_course_price=D("57000"),
                                                          status="APPROVED").exists())
        self.assertTrue(contracts.payment_schedule(profile)["consistent"])
        # Месяц будет начислен по новому плану.
        self.it_lessons(24)
        self.assertEqual([i.amount for i in self.live_invoices(profile)], [D("13000"), D("15000"), D("15000"), D("14000")])

    def test_future_plan_change_redistributed_keeps_course_price(self):
        profile = self.example()
        result = self.edit(profile, month_number=3, plan_amount="14000", difference="future")
        profile.refresh_from_db()
        self.assertEqual(profile.final_course_price, D("58000"))
        self.assertEqual({m: a for m, (_s, a) in self.plan(profile).items()},
                         {1: D("13000"), 2: D("15000"), 3: D("14000"), 4: D("16000")})
        self.assertEqual(result["other_months"], [{"month_number": 4, "plan_before": D("15000"),
                                                   "plan_after": D("16000")}])
        self.assertEqual(result["course"]["before"]["net_to_pay"], result["course"]["after"]["net_to_pay"])

    def test_plan_of_issued_month_is_not_editable(self):
        profile = self.example()
        with self.assertRaises(BillingError) as error:
            self.edit(profile, month_number=2, plan_amount="14000")
        self.assertEqual(error.exception.code, "month_issued")
        with self.assertRaises(BillingError) as error:
            self.edit(profile, month_number=3, charge="14000")
        self.assertEqual(error.exception.code, "not_issued")

    def test_negative_amount_rejected(self):
        profile = self.example()
        with self.assertRaises(BillingError) as error:
            self.edit(profile, month_number=4, plan_amount="-1")
        self.assertEqual(error.exception.code, "invalid_amount")


class ChargeTests(MonthEditFixture):
    def test_partially_paid_charge_decrease_keeps_payments(self):
        """Месяц №1: 13 000, оплачено 11 000 → 12 000; остаток 1 000, платежи те же."""
        profile = self.example()
        m1 = self.live_invoices(profile)[0]
        received = list(StudentPayment.objects.filter(billing_profile=profile).values_list("pk", "amount", "status"))
        result = self.edit(profile, month_number=1, charge="12000")
        new = self.live_invoices(profile)[0]
        self.assertNotEqual(new.pk, m1.pk)
        self.assertEqual((new.amount, new.amount_paid, new.balance), (D("12000"), D("11000"), D("1000")))
        self.assertEqual(new.snapshot["reissue_of"], m1.number)
        self.assertEqual((new.period_date, new.due_lesson, new.overdue_since),
                         (m1.period_date, m1.due_lesson, m1.overdue_since))
        old = Invoice.objects.get(pk=m1.pk)
        self.assertEqual(old.status, "VOID")
        self.assertEqual(old.allocations.filter(status="REVERSED").count(), 2)  # история распределений сохранена
        self.assertEqual(list(StudentPayment.objects.filter(billing_profile=profile)
                              .values_list("pk", "amount", "status")), received)  # платежи не тронуты
        self.assertEqual(result["reissued"]["from"], m1.number)
        s = self.plain(profile)
        self.assertEqual((s["final_course_price"], s["due_now"], s["future"], s["net_to_pay"], s["credit"]),
                         (D("57000"), D("16000"), D("30000"), D("46000"), D("0")))
        self.assertEqual(s["net_received"], D("11000"))

    def test_charge_below_paid_is_rejected(self):
        profile = self.example()
        with self.assertRaises(BillingError) as error:
            self.edit(profile, month_number=1, charge="10000")
        self.assertEqual(error.exception.code, "below_paid")
        self.assertEqual(self.live_invoices(profile)[0].amount, D("13000"))

    def test_fully_paid_charge_increase_warns_and_leaves_balance(self):
        profile = self.example()
        self.pay(profile, "2000")  # месяц №1 оплачен полностью
        self.assertEqual(self.live_invoices(profile)[0].status, "PAID")
        with self.assertRaises(BillingError):  # стандарт 13 000 — без его увеличения итоговая выше стандартной
            self.edit(profile, month_number=1, charge="14000", dry_run=True)
        preview = self.edit(profile, month_number=1, charge="14000", standard_price="14000", dry_run=True)
        self.assertTrue(any("полностью оплачено" in w for w in preview["warnings"]))
        self.assertEqual(preview["month"]["after"]["balance"], D("1000"))
        self.assertEqual(self.live_invoices(profile)[0].status, "PAID")  # предпросмотр откатан
        self.edit(profile, month_number=1, charge="14000", standard_price="14000")
        new = self.live_invoices(profile)[0]
        self.assertEqual((new.amount, new.amount_paid, new.status), (D("14000"), D("13000"), "OVERDUE"))

    def test_charge_change_to_future_months_keeps_course_price(self):
        profile = self.example()
        self.edit(profile, month_number=2, charge="14000", difference="future")
        profile.refresh_from_db()
        self.assertEqual(profile.final_course_price, D("58000"))
        self.assertEqual({m: a for m, (_s, a) in self.plan(profile).items()},
                         {1: D("13000"), 2: D("14000"), 3: D("15500"), 4: D("15500")})
        self.assertTrue(contracts.payment_schedule(profile)["consistent"])

    def test_adjusted_invoice_is_replaced_by_new_charge(self):
        profile = self.example()
        m2 = self.live_invoices(profile)[1]
        invoices.adjust_invoice(m2, actor=self.accountant, amount="1000", reason="списание")
        self.edit(profile, month_number=2, charge="14500")
        new = self.live_invoices(profile)[1]
        self.assertEqual((new.amount, new.amount_adjusted, new.balance), (D("14500"), D("0"), D("14500")))
        self.assertEqual(InvoiceAdjustment.objects.get(invoice=m2).status, "VOID")
        s = self.plain(profile)
        # Начисление было 15 000 − 1 000 = 14 000 к оплате, стало 14 500: +500 к стоимости курса.
        self.assertEqual(s["final_course_price"], D("57500"))
        self.assertEqual(s["net_to_pay"], D("47000") - D("1000") + D("500"))


class SafetyTests(MonthEditFixture):
    def test_stale_version_is_rejected(self):
        """Два сотрудника открыли форму; второй сохраняет по устаревшей версии."""
        profile = self.example()
        version = month_edit.schedule_version(profile)
        month_edit.edit_month(profile, actor=self.accountant, month_number=4, plan_amount="14000", reason="a",
                              version=version)
        with self.assertRaises(BillingError) as error:
            month_edit.edit_month(profile, actor=self.accountant, month_number=4, plan_amount="13000", reason="b",
                                  version=version)
        self.assertEqual(error.exception.code, "stale")
        response = self.client_for(self.accountant).post(BASE + f"profiles/{profile.pk}/month-edit/", {
            "month_number": 4, "plan_amount": "13000", "reason": "b", "version": version}, format="json")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(self.plan(profile)[4][1], D("14000"))

    def test_payment_between_open_and_save_makes_form_stale(self):
        profile = self.example()
        version = month_edit.schedule_version(profile)
        self.pay(profile, "500")
        with self.assertRaises(BillingError) as error:
            month_edit.edit_month(profile, actor=self.accountant, month_number=1, charge="12000", reason="x",
                                  version=version)
        self.assertEqual(error.exception.code, "stale")

    def test_permissions(self):
        profile = self.example()
        body = {"month_number": 4, "plan_amount": "14000", "reason": "x",
                "version": month_edit.schedule_version(profile)}
        for user in (self.manager, self.director, make_user("teacher1")):
            response = self.client_for(user).post(BASE + f"profiles/{profile.pk}/month-edit/", body, format="json")
            self.assertIn(response.status_code, (403, 404))
        self.assertEqual(self.plan(profile)[4][1], D("15000"))
        ok = self.client_for(self.accountant).post(BASE + f"profiles/{profile.pk}/month-edit/", body, format="json")
        self.assertEqual(ok.status_code, 200, ok.data)
        self.assertEqual(ok.data["course"]["after"]["final_course_price"], "57000.00")

    def test_reason_required_and_no_change_is_noop(self):
        profile = self.example()
        with self.assertRaises(BillingError) as error:
            self.edit(profile, month_number=4, plan_amount="14000", reason="")
        self.assertEqual(error.exception.code, "reason_required")
        result = self.edit(profile, month_number=4, plan_amount="15000")
        self.assertFalse(result["changed"])
        self.assertFalse(PayrollAuditLog.objects.filter(action="billing_month_edit").exists())

    def test_failed_save_leaves_everything_unchanged(self):
        profile = self.example()
        version = month_edit.schedule_version(profile)
        with self.assertRaises(BillingError):
            self.edit(profile, month_number=2, charge="99000")  # выше стандартной стоимости курса
        self.assertEqual(month_edit.schedule_version(profile), version)
        self.assertEqual(Invoice.objects.filter(profile=profile, status="VOID").count(), 0)

    def test_history_records_old_new_reason_and_author(self):
        profile = self.example()
        self.edit(profile, month_number=1, charge="12000", reason="ошибка в сумме")
        history = month_edit.month_history(profile, 1)
        edit = next(h for h in history if h["action"] == "billing_month_edit")
        self.assertEqual((edit["old_values"]["charge"], edit["new_values"]["charge"]), ("13000.00", "12000"))
        self.assertEqual(edit["reason"], "ошибка в сумме")
        self.assertEqual(edit["actor"], str(self.accountant))
        self.assertEqual(edit["new_values"]["reissued"]["from"], self.live_invoices(profile)[0].snapshot["reissue_of"])
        self.assertTrue(any(h["action"] == "billing_invoice_void" for h in history))
        self.assertFalse(any(h["action"] == "billing_month_edit" for h in month_edit.month_history(profile, 3)))
        card = self.client_for(self.accountant).get(BASE + f"profiles/{profile.pk}/card/").data
        self.assertEqual([r["manual"] for r in card["schedule"]["months"]], [True, False, False, False])
        api = self.client_for(self.director).get(BASE + f"profiles/{profile.pk}/month-history/?month=1")
        self.assertEqual(api.status_code, 200)

    def test_contract_without_plan_is_materialized_as_is(self):
        """Договор без плана месяцев (поровну): изменение одного месяца не меняет остальные."""
        profile = self.contract(discount_enabled=True, final_course_price="50000", discount_reason="x")
        before = [r["amount"] for r in contracts.payment_schedule(profile)["months"]]
        self.edit(profile, month_number=2, standard_price="16000")
        profile.refresh_from_db()
        self.assertEqual([a for _m, (_s, a) in sorted(self.plan(profile).items())], before)
        self.assertEqual([s for _m, (s, _a) in sorted(self.plan(profile).items())],
                         [D("15000"), D("16000"), D("15000"), D("15000")])
        self.assertEqual((profile.final_course_price, profile.standard_course_price), (D("50000"), D("61000")))

    def test_full_prepay_contract_is_blocked(self):
        profile = self.contract(payment_mode="FULL_PREPAY")
        with self.assertRaises(BillingError) as error:
            self.edit(profile, month_number=2, standard_price="16000")
        self.assertEqual(error.exception.code, "edit_blocked")


class MoneyScenarioTests(MonthEditFixture):
    """Сценарии пункта 16 на сводке договора (единый backend-расчёт)."""

    def test_new_contract_without_payments(self):
        profile = self.contract()
        s = self.plain(profile)
        self.assertEqual((s["due_now"], s["net_received"], s["credit"], s["invoiced"], s["future"], s["net_to_pay"]),
                         (D("15000"), D("0"), D("0"), D("15000"), D("45000"), D("60000")))

    def test_free_credit_then_applied(self):
        profile = self.contract()
        self.pay(profile, "20000")
        s = self.plain(profile)
        self.assertEqual((s["allocated"], s["credit"], s["due_now"]), (D("15000"), D("5000"), D("0")))
        self.assertEqual(s["net_received"], s["allocated"] + s["credit"])
        self.it_lessons(12)  # месяц №2 выставлен — аванс распределяется на него, не создаёт новых денег
        s = self.plain(profile)
        self.assertEqual((s["net_received"], s["allocated"], s["credit"], s["due_now"]),
                         (D("20000"), D("20000"), D("0"), D("10000")))

    def test_reversal_is_not_refund(self):
        profile = self.contract()
        payment = self.pay(profile, "15000")
        payments.reverse_payment(payment, actor=self.accountant, reason="ошибка")
        s = self.plain(profile)
        self.assertEqual((s["net_received"], s["refunded"], s["voided"], s["voided_count"], s["due_now"]),
                         (D("0"), D("0"), D("15000"), 1, D("15000")))
        self.assertEqual(PaymentAllocation.objects.filter(payment=payment, status="ACTIVE").count(), 0)

    def test_refund_is_separate_from_reversal(self):
        profile = self.contract()
        payment = self.pay(profile, "20000")
        payments.refund_payment(payment, actor=self.accountant, amount="5000", reason="возврат аванса")
        s = self.plain(profile)
        self.assertEqual((s["received"], s["refunded"], s["net_received"], s["voided"], s["credit"]),
                         (D("20000"), D("5000"), D("15000"), D("0"), D("0")))

    def test_contract_plan_mismatch_is_reported_not_fixed(self):
        profile = self.example()
        ContractMonthPrice.objects.filter(profile=profile, month_number=4).update(amount=Decimal("14000"))
        schedule = month_edit.decorate(profile, contracts.payment_schedule(profile))
        self.assertFalse(schedule["consistent"])
        self.assertEqual(schedule["plan_difference"], D("-1000"))
        preview = self.edit(profile, month_number=3, standard_price="15500", dry_run=True)
        self.assertTrue(any("расходилась" in w for w in preview["warnings"]))
        self.assertEqual(preview["course"]["after"]["final_course_price"], D("58000"))  # не подгоняется
