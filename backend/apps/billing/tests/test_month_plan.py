"""Индивидуальная стоимость учебных месяцев договора: 13 000 + 15 000 +
15 000 + 15 000 = 58 000 стандартная, итоговая со скидкой 50 000."""
from __future__ import annotations

import datetime as dt
import json
from decimal import Decimal
from io import StringIO

from django.core.management import call_command

from apps.accounting.models import PayrollAuditLog
from apps.billing.models import ContractMonthPrice, Invoice, PaymentMode
from apps.billing.services import BillingError, contracts, month_plan, payments, profiles, reservations
from apps.billing.services.reports import reconcile
from apps.billing.tasks import process_completed_packages
from apps.billing.tests.base import D
from apps.billing.tests.test_contracts import BASE
from apps.billing.tests.test_periods import OCT24, PeriodFixture

PRICES = ["13000", "15000", "15000", "15000"]
SEP1 = dt.date(2026, 9, 1)


class PlanFixture(PeriodFixture):
    def setUp(self):
        super().setUp()
        self.at(SEP1)
        self.day = dt.date(2026, 9, 2)

    def planned(self, *, mode="PROPORTIONAL", final="50000", amounts=None, actor=None, **extra):
        return self.contract(start_date=SEP1, discount_enabled=final != "58000", final_course_price=final,
                             discount_reason="Скидка семье", month_prices=PRICES, month_plan_mode=mode,
                             month_amounts=amounts, actor=actor, student=extra.pop("student", None), **extra)

    def plan(self, profile):
        return {r.month_number: r.amount for r in ContractMonthPrice.objects.filter(profile=profile)}


class DistributionTests(PlanFixture):
    def test_proportional_split_is_exact_to_the_tyiyn(self):
        parts = month_plan.distribute([D(p) for p in PRICES], D("50000"))
        self.assertEqual(sum(parts), D("50000"))
        exact = [D("50000") * D(p) / D("58000") for p in PRICES]
        self.assertTrue(all(abs(a - e) < D("0.01") for a, e in zip(parts, exact)))
        self.assertEqual(month_plan.distribute([D("1"), D("1"), D("1")], D("100")), [D("33.34"), D("33.33"), D("33.33")])


class ContractWithPlanTests(PlanFixture):
    def test_standard_58000_final_50000_plan_sums_exactly(self):
        profile = self.planned()
        self.assertEqual((profile.standard_course_price, profile.final_course_price, profile.discount_amount),
                         (D("58000"), D("50000"), D("8000")))
        plan = self.plan(profile)
        self.assertEqual(sum(plan.values()), D("50000"))
        self.assertTrue(plan[1] < min(plan[2], plan[3], plan[4]))  # месяц 1 дешевле
        self.assertLessEqual(max(plan[2], plan[3], plan[4]) - min(plan[2], plan[3], plan[4]), D("0.01"))  # остаток тыйынов
        (m1,) = self.live_invoices(profile)
        self.assertEqual(m1.amount, plan[1])
        schedule = contracts.payment_schedule(profile)
        self.assertEqual((schedule["standard_course_price"], schedule["total"], schedule["consistent"]),
                         (D("58000"), D("50000"), True))
        self.assertEqual([m["standard_price"] for m in schedule["months"]], [D(p) for p in PRICES])
        card = self.client_for(self.accountant).get(BASE + f"profiles/{profile.pk}/card/").data
        self.assertEqual(card["contract"]["month_plan_mode"], "PROPORTIONAL")
        self.assertEqual([r["standard_price"] for r in card["contract"]["month_prices"]],
                         ["13000.00", "15000.00", "15000.00", "15000.00"])

    def test_months_are_charged_by_plan_and_total_equals_final(self):
        profile = self.planned()
        plan = self.plan(profile)
        self.at(OCT24)
        self.it_lessons(48)  # все 4 месяца по 12 уроков IT
        invoices = self.live_invoices(profile)
        self.assertEqual([i.amount for i in invoices], [plan[m] for m in (1, 2, 3, 4)])
        self.assertEqual(sum(i.amount for i in invoices), D("50000"))
        # Повторные запуски сервисов не создают начислений.
        process_completed_packages(on=OCT24)
        self.assertEqual(Invoice.objects.filter(profile=profile).count(), 4)

    def test_manual_amounts_must_match_final(self):
        with self.assertRaises(BillingError) as error:
            self.planned(mode="MANUAL", amounts=["11000", "13000", "13000", "12000"], actor=self.accountant)
        self.assertEqual(error.exception.code, "plan_total_mismatch")
        self.assertIn("разница 1000.00", error.exception.message)
        profile = self.planned(mode="MANUAL", amounts=["11000", "13000", "13000", "13000"], actor=self.accountant,
                               student=self.student())
        self.assertEqual(self.plan(profile), {1: D("11000"), 2: D("13000"), 3: D("13000"), 4: D("13000")})
        self.assertEqual(self.live_invoices(profile)[0].amount, D("11000"))

    def test_manager_cannot_set_manual_plan_or_change_plan(self):
        with self.assertRaises(BillingError):
            self.planned(mode="MANUAL", amounts=["11000", "13000", "13000", "13000"], actor=self.manager)
        profile = self.planned(actor=self.accountant, student=self.student())
        body = {"standard_prices": PRICES, "final_course_price": "48000", "mode": "PROPORTIONAL", "reason": "x"}
        for user in (self.manager, self.director):
            self.assertEqual(self.client_for(user).post(BASE + f"profiles/{profile.pk}/month-plan/", body,
                                                        format="json").status_code, 403)
        self.assertEqual(self.client_for(self.director).get(BASE + f"profiles/{profile.pk}/month-plan/").status_code, 200)

    def test_full_prepay_single_obligation_with_month_breakdown(self):
        profile = self.planned(payment_mode=PaymentMode.FULL_PREPAY)
        (course,) = self.live_invoices(profile)
        self.assertEqual((course.kind, course.amount), (Invoice.Kind.COURSE, D("50000")))
        self.assertEqual(sum(self.plan(profile).values()), D("50000"))
        payments.record_payment(profile=profile, amount="50000", received_date=SEP1, actor=self.accountant)
        self.at(OCT24)
        self.it_lessons(30)
        self.assertEqual(Invoice.objects.filter(profile=profile).exclude(status="VOID").count(), 1)  # без месячных долгов
        s = contracts.money_summary(profile)
        self.assertEqual((s["due_now"], s["credit"], s["outstanding"]), (D("0"), D("0"), D("0")))


class ChangingPlanTests(PlanFixture):
    def test_issued_month_is_not_repriced_rest_is_redistributed(self):
        profile = self.contract(start_date=SEP1, discount_enabled=True, final_course_price="50000",
                                discount_reason="x")  # прежнее правило: месяц 1 = 12 500
        self.at(OCT24)
        self.it_lessons(3)  # месяц 1 начат
        url = BASE + f"profiles/{profile.pk}/month-plan/"
        api = self.client_for(self.accountant)
        body = {"standard_prices": PRICES, "final_course_price": "50000", "mode": "PROPORTIONAL", "reason": "Цены месяцев"}
        preview = api.post(url, {**body, "dry_run": True}, format="json").data
        self.assertEqual([r["amount"] for r in preview["rows"]], ["12500.00", "12500.00", "12500.00", "12500.00"])
        self.assertEqual(ContractMonthPrice.objects.count(), 0)  # предпросмотр ничего не сохраняет
        saved = api.post(url, body, format="json")
        self.assertEqual((saved.status_code, saved.data["changed"]), (200, True))
        self.assertEqual(self.live_invoices(profile)[0].amount, D("12500"))  # выставленный — без изменений
        manual = api.post(url, {**body, "mode": "MANUAL", "manual_amounts": ["11000", "13000", "13000", "13000"]},
                          format="json")
        self.assertEqual((manual.status_code, manual.data["code"]), (400, "issued_mismatch"))
        again = api.post(url, body, format="json")
        self.assertEqual(again.data["changed"], False)  # повторное сохранение — без изменений
        self.assertEqual(PayrollAuditLog.objects.filter(action="billing_month_plan").count(), 1)
        self.assertEqual(Invoice.objects.filter(profile=profile).count(), 1)

    def test_reissue_unstarted_month_keeps_money(self):
        profile = self.contract(start_date=SEP1, discount_enabled=True, final_course_price="50000",
                                discount_reason="x", reservation_amount="3000")
        reservations.record_reservation_payment(profile.reservations.get(), actor=self.accountant, amount="3000",
                                                received_date=SEP1)
        old = self.live_invoices(profile)[0]
        result = month_plan.set_month_plan(profile, actor=self.accountant, standard_prices=PRICES,
                                           final_course_price="50000", mode="PROPORTIONAL", reason="Цены месяцев",
                                           reissue_unstarted=True)
        self.assertEqual(result["reissued"], [old.number])
        old.refresh_from_db()
        (new,) = self.live_invoices(profile)
        self.assertEqual((old.status, new.amount, new.amount_paid, new.period_date),
                         (Invoice.Status.VOID, self.plan(profile)[1], D("3000"), old.period_date))
        s = contracts.money_summary(profile)
        self.assertEqual((s["received"], s["allocated"], s["credit"]), (D("3000"), D("3000"), D("0")))  # бронь один раз
        self.assertEqual(reconcile(), [])

    def test_course_terms_change_redistributes_or_is_blocked(self):
        profile = self.planned(actor=self.accountant)
        profiles.request_course_terms_change(profile, actor=self.accountant, discount_enabled=True,
                                             final_course_price="48000", reason="Ещё скидка")
        profile.refresh_from_db()
        plan = self.plan(profile)
        self.assertEqual(sum(plan.values()), D("48000"))
        self.assertEqual(plan[1], self.live_invoices(profile)[0].amount)  # выставленный месяц 1 — прежний
        manual = self.planned(mode="MANUAL", amounts=["11000", "13000", "13000", "13000"], actor=self.accountant,
                              student=self.student())
        with self.assertRaises(BillingError) as error:
            profiles.request_course_terms_change(manual, actor=self.accountant, discount_enabled=True,
                                                 final_course_price="48000", reason="x")
        self.assertEqual(error.exception.code, "manual_month_plan")


class MoneyPerMonthTests(PlanFixture):
    def test_balances_by_actual_allocations_and_credit_separate(self):
        profile = self.planned(actor=self.accountant)
        plan = self.plan(profile)
        payments.record_payment(profile=profile, amount="20000", received_date=SEP1, actor=self.accountant)
        (m1,) = self.live_invoices(profile)
        self.assertEqual((m1.status, m1.balance), (Invoice.Status.PAID, D("0")))
        s = contracts.money_summary(profile)
        self.assertEqual((s["allocated"], s["credit"]), (plan[1], D("20000") - plan[1]))
        self.at(OCT24)
        self.it_lessons(12)  # месяц 2 выставлен и частично закрыт авансом
        m2 = self.live_invoices(profile)[1]
        self.assertEqual((m2.amount, m2.amount_paid, m2.balance), (plan[2], D("20000") - plan[1], plan[1] + plan[2] - D("20000")))
        s = contracts.money_summary(profile)
        self.assertEqual((s["due_now"], s["credit"]), (m2.balance, D("0")))
        self.assertEqual(s["outstanding"], D("30000"))


class ReportTests(PlanFixture):
    def test_report_flags_mismatching_contracts_only(self):
        good = self.planned(actor=self.accountant)
        bad = self.planned(actor=self.accountant, student=self.student())
        ContractMonthPrice.objects.filter(profile=bad, month_number=4).update(amount=Decimal("1"))
        out = StringIO()
        call_command("billing_month_plan_report", stdout=out)
        report = json.loads(out.getvalue())
        self.assertTrue(report["dry_run"])
        self.assertEqual([r["profile"] for r in report["mismatches"]], [bad.pk])
        self.assertNotIn(good.pk, [r["profile"] for r in report["mismatches"]])
        ContractMonthPrice.objects.filter(profile=bad, month_number=4).update(amount=Decimal("1"))
        self.assertEqual(ContractMonthPrice.objects.get(profile=bad, month_number=4).amount, D("1"))  # отчёт ничего не меняет


class AdminTests(PlanFixture):
    def test_admin_month_plan_page_preview_and_save(self):
        from django.test import Client

        profile = self.contract(start_date=SEP1)
        client = Client()
        client.force_login(self.admin)
        url = f"/admin/billing/studentbillingprofile/{profile.pk}/month-plan/"
        self.assertContains(client.get(url), "План начислений")
        body = {"standard_prices": "13000, 15000, 15000, 15000", "final_course_price": "50000", "mode": "PROPORTIONAL",
                "manual_amounts": "", "reason": "Цены месяцев", "reissue_unstarted": "on"}
        preview = client.post(url, {**body, "action": "preview"})
        self.assertContains(preview, "Предпросмотр (не сохранён)")
        self.assertEqual(ContractMonthPrice.objects.count(), 0)
        client.post(url, {**body, "action": "save"})
        profile.refresh_from_db()
        self.assertEqual((profile.standard_course_price, profile.final_course_price), (D("58000"), D("50000")))
        self.assertEqual(self.live_invoices(profile)[0].amount, self.plan(profile)[1])  # месяц 1 перевыставлен
        changelist = client.get("/admin/billing/studentbillingprofile/")
        self.assertContains(changelist, "58000")
