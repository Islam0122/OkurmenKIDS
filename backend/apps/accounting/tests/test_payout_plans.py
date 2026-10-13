"""План выплат: суммы, дефицит, выплаты через существующий механизм, защита от
двойного планирования и переплаты, отмена без потери истории, права,
конкурентный доступ, календарь и журнал."""
from __future__ import annotations

import threading
import unittest

from django.db import connection
from django.test import TransactionTestCase

from apps.accounting.models import (
    EmployeeSalaryProfile,
    PayoutPlan,
    PayoutPlanLine,
    Payroll,
    PayrollAuditLog,
    PayrollPayment,
    SalaryRule,
    SalaryType,
)
from apps.accounting.services import AccountingError
from apps.accounting.services import payout_plans as pp
from apps.accounting.services.approval_service import approve_payroll
from apps.accounting.services.payment_service import register_payment, void_payment
from apps.accounting.services.payroll_calculator import calculate_payroll
from apps.accounting.services.periods import get_or_create_period
from apps.accounting.tests.base import MONTH, D, AccountingFixture, day, make_user
from apps.users.models import User

API = "/api/v1/accounting/payout-plans"
R = SalaryRule.RuleType


class PayoutPlanFixture(AccountingFixture):
    """Четыре сотрудника с окладом 250 000 за сентябрь → 1 000 000 к выплате."""

    def setUp(self):
        super().setUp()
        self.staff = [make_user(f"emp{i}", User.Role.ASSISTANT) for i in range(4)]
        self.payrolls = []
        for user in self.staff:
            self.rule(self.profile(user), R.FIXED, amount=D("250000"))
            self.payrolls.append(approve_payroll(self.calc(MONTH, user=user), self.director))

    def plan(self, prepared="0", payrolls=None, approve=True, **extra):
        plan = pp.create_plan(
            actor=self.accountant, title=extra.pop("title", "Зарплата за сентябрь"), year=2026, month=9,
            payout_date=extra.pop("payout_date", day(10, 1)), prepared_amount=D(prepared),
            lines=[{"payroll": p} for p in (self.payrolls if payrolls is None else payrolls)], **extra,
        )
        return pp.approve_plan(plan, actor=self.accountant) if approve else plan

    def line(self, plan, payroll):
        return plan.lines.get(payroll=payroll, is_removed=False)

    def pay(self, plan, payroll, amount, **kw):
        return pp.pay_line(self.line(plan, payroll), actor=self.accountant, amount=D(amount),
                           payment_date=day(10, 1), payment_method=PayrollPayment.Method.BANK, **kw)


class TotalsTests(PayoutPlanFixture):
    def test_plan_for_one_million(self):
        t = pp.totals(self.plan())
        self.assertEqual((t.planned, t.remaining, t.paid, t.employees), (D("1000000"), D("1000000"), D("0"), 4))
        self.assertEqual(t.deficit, D("1000000"))
        self.assertEqual(t.readiness, D("0.0"))
        self.assertEqual(t.status, pp.SCHEDULED)

    def test_deficit_after_partial_payment_uses_planned_minus_prepared(self):
        plan = self.plan("700000")
        self.pay(plan, self.payrolls[0], "250000")
        t = pp.totals(plan)
        self.assertEqual((t.deficit, t.readiness, t.remaining), (D("300000"), D("70.0"), D("750000")))
        # погашено вне плана → потребность плана уменьшается
        register_payment(Payroll.objects.get(pk=self.payrolls[1].pk), amount=D("100000"), payment_date=day(9, 30),
                         actor=self.accountant)
        self.assertEqual(pp.totals(plan).deficit, D("200000"))

    def test_prepared_700k_gives_300k_deficit(self):
        plan = self.plan()
        plan = pp.update_plan(plan, actor=self.accountant, changes={"prepared_amount": D("700000")})
        t = pp.totals(plan)
        self.assertEqual(t.deficit, D("300000"))
        self.assertEqual(t.readiness, D("70.0"))
        self.assertEqual(t.status, pp.PARTIALLY_FUNDED)
        # подготовленный бюджет — не выплата
        self.assertFalse(PayrollPayment.objects.exists())
        self.assertEqual(Payroll.objects.get(pk=self.payrolls[0].pk).total_paid, D("0"))

    def test_prepared_covers_plan_is_ready(self):
        t = pp.totals(self.plan("1000000"))
        self.assertEqual((t.deficit, t.readiness, t.status), (D("0"), D("100.0"), pp.READY))

    def test_draft_status_and_zero_safe_readiness(self):
        empty = pp.create_plan(actor=self.accountant, title="Пустой", year=2026, month=9, payout_date=day(10, 15))
        t = pp.totals(empty)
        self.assertEqual((t.status, t.readiness, t.deficit), (pp.DRAFT, D("0.0"), D("0")))


class PaymentTests(PayoutPlanFixture):
    def test_partial_payment(self):
        plan = self.plan("1000000")
        payment, created = self.pay(plan, self.payrolls[0], "100000")
        self.assertTrue(created)
        self.assertEqual(payment.payout_plan_line, self.line(plan, self.payrolls[0]))
        t = pp.totals(plan)
        self.assertEqual((t.paid, t.remaining, t.status), (D("100000"), D("900000"), pp.PARTIALLY_PAID))
        self.assertEqual((t.deficit, t.readiness), (D("0"), D("100.0")))  # выплата из подготовленных средств
        payroll = Payroll.objects.get(pk=self.payrolls[0].pk)
        self.assertEqual((payroll.status, payroll.amount_due), (Payroll.Status.PARTIALLY_PAID, D("150000")))

    def test_full_payment(self):
        plan = self.plan("1000000")
        for p in self.payrolls:
            self.pay(plan, p, "250000")
        t = pp.totals(plan)
        self.assertEqual((t.paid, t.remaining, t.status), (D("1000000"), D("0"), pp.PAID))
        self.assertTrue(all(p.status == Payroll.Status.PAID for p in Payroll.objects.filter(
            pk__in=[x.pk for x in self.payrolls])))

    def test_overpayment_forbidden(self):
        plan = self.plan()
        with self.assertRaises(AccountingError) as ctx:
            self.pay(plan, self.payrolls[0], "250000.01")
        self.assertEqual(ctx.exception.code, "exceeds_plan")
        self.assertFalse(PayrollPayment.objects.exists())

    def test_line_capped_by_payroll_due_when_paid_outside_plan(self):
        plan = self.plan()
        register_payment(self.payrolls[0], amount=D("200000"), payment_date=day(9, 30), actor=self.accountant)
        line = self.line(plan, self.payrolls[0])
        self.assertEqual(pp.line_remaining(line), D("50000"))
        with self.assertRaises(AccountingError):
            self.pay(plan, self.payrolls[0], "60000")
        self.assertEqual(pp.totals(plan).remaining, D("800000"))
        self.assertNotEqual(pp.totals(plan).status, pp.PAID)

    def test_recalculation_after_payment_and_void(self):
        plan = self.plan("1000000")
        payment, _ = self.pay(plan, self.payrolls[0], "250000")
        line = pp.explain_line(self.line(plan, self.payrolls[0]))
        self.assertEqual((line["paid_by_plan"], line["remaining_in_plan"], line["status"]), (D("250000"), D("0"), "PAID"))
        self.assertEqual(pp.totals(plan).remaining, D("750000"))
        void_payment(payment, actor=self.accountant, reason="ошибка в реквизитах")
        self.assertEqual(pp.totals(plan).remaining, D("1000000"))
        self.assertEqual(pp.totals(plan).status, pp.READY)

    def test_payment_requires_approved_plan(self):
        plan = self.plan(approve=False)
        with self.assertRaises(AccountingError) as ctx:
            self.pay(plan, self.payrolls[0], "1000")
        self.assertEqual(ctx.exception.code, "bad_state")

    def test_idempotent_payment(self):
        plan = self.plan()
        first, c1 = self.pay(plan, self.payrolls[0], "1000", idempotency_key="k-1")
        again, c2 = self.pay(plan, self.payrolls[0], "1000", idempotency_key="k-1")
        self.assertEqual((first.pk, c1, c2), (again.pk, True, False))
        self.assertEqual(PayrollPayment.objects.count(), 1)


class CompositionTests(PayoutPlanFixture):
    def test_same_accrual_cannot_be_planned_twice(self):
        self.plan()
        with self.assertRaises(AccountingError) as ctx:
            self.plan(title="Второй", payrolls=[self.payrolls[0]])
        self.assertEqual(ctx.exception.code, "nothing_due")
        self.assertEqual(PayoutPlan.objects.count(), 1)  # транзакция откатилась

    def test_duplicate_line_in_one_plan(self):
        plan = self.plan(payrolls=[self.payrolls[0]], approve=False)
        with self.assertRaises(AccountingError) as ctx:
            pp.add_lines(plan, actor=self.accountant, items=[{"payroll": self.payrolls[0]}])
        self.assertEqual(ctx.exception.code, "duplicate")

    def test_split_between_two_plans_within_due(self):
        self.plan(payrolls=[self.payrolls[0]], approve=False)  # черновик тоже резервирует
        first = PayoutPlanLine.objects.get()
        pp.update_line(first, actor=self.accountant, amount=D("100000"))
        second = self.plan(title="15 октября", payrolls=[self.payrolls[0]], payout_date=day(10, 15), approve=False)
        self.assertEqual(self.line(second, self.payrolls[0]).planned_amount, D("150000"))
        with self.assertRaises(AccountingError) as ctx:
            pp.update_line(first, actor=self.accountant, amount=D("100000.01"))
        self.assertEqual(ctx.exception.code, "exceeds_due")

    def test_unapproved_payroll_rejected(self):
        draft = calculate_payroll(self.period((2026, 10), MONTH), self.staff[0], self.accountant)
        with self.assertRaises(AccountingError) as ctx:
            self.plan(payrolls=[draft], approve=False)
        self.assertEqual(ctx.exception.code, "not_approved")

    def test_composition_locked_after_approval(self):
        plan = self.plan(payrolls=self.payrolls[:2])
        with self.assertRaises(AccountingError):
            pp.add_lines(plan, actor=self.accountant, items=[{"payroll": self.payrolls[2]}])
        with self.assertRaises(AccountingError):
            pp.update_line(self.line(plan, self.payrolls[0]), actor=self.accountant, remove=True)
        with self.assertRaises(AccountingError):
            pp.update_plan(plan, actor=self.accountant, changes={"title": "Другое"})
        with self.assertRaises(AccountingError) as ctx:
            pp.update_plan(plan, actor=self.accountant, changes={"payout_date": day(10, 2)})
        self.assertEqual(ctx.exception.code, "reason_required")
        plan = pp.update_plan(plan, actor=self.accountant, changes={"payout_date": day(10, 2)}, reason="выходной")
        self.assertEqual(plan.payout_date, day(10, 2))

    def test_removed_line_frees_reservation(self):
        plan = self.plan(approve=False)
        pp.update_line(self.line(plan, self.payrolls[0]), actor=self.accountant, remove=True, reason="позже")
        self.assertEqual(pp.available(self.payrolls[0]), D("250000"))
        self.assertEqual(pp.totals(plan).planned, D("750000"))


class CancelTests(PayoutPlanFixture):
    def test_cancel_keeps_accruals_and_payments(self):
        plan = self.plan("1000000")
        self.pay(plan, self.payrolls[0], "100000")
        with self.assertRaises(AccountingError) as ctx:
            pp.cancel_plan(plan, actor=self.accountant, reason=" ")
        self.assertEqual(ctx.exception.code, "reason_required")
        plan = pp.cancel_plan(plan, actor=self.accountant, reason="перенос на 15-е")
        self.assertEqual((plan.state, plan.cancel_reason, plan.cancelled_by), (PayoutPlan.State.CANCELLED,
                                                                              "перенос на 15-е", self.accountant))
        self.assertEqual(pp.totals(plan).status, pp.CANCELLED)
        self.assertEqual(PayrollPayment.objects.filter(status=PayrollPayment.Status.CONFIRMED).count(), 1)
        self.assertEqual(Payroll.objects.filter(pk__in=[p.pk for p in self.payrolls]).count(), 4)
        self.assertEqual(plan.lines.count(), 4)
        # резерв освобождён: остаток можно запланировать заново
        self.assertEqual(pp.available(Payroll.objects.get(pk=self.payrolls[0].pk)), D("150000"))
        self.plan(title="Новый план", payrolls=[self.payrolls[0]])
        with self.assertRaises(AccountingError):
            pp.update_plan(plan, actor=self.accountant, changes={"prepared_amount": D("1")})

    def test_cannot_delete_plan(self):
        plan = self.plan()
        with self.assertRaises(Exception):
            plan.delete()
        with self.assertRaises(Exception):
            PayoutPlan.objects.all().delete()


class ConcurrencyTests(PayoutPlanFixture):
    def test_stale_version_is_rejected(self):
        plan = self.plan(approve=False)
        stale = plan.version
        pp.update_plan(plan, actor=self.accountant, changes={"prepared_amount": D("1000")}, version=stale)
        with self.assertRaises(AccountingError) as ctx:
            pp.update_plan(plan, actor=self.accountant, changes={"prepared_amount": D("2000")}, version=stale)
        self.assertEqual(ctx.exception.code, "conflict")
        with self.assertRaises(AccountingError):
            pp.approve_plan(plan, actor=self.accountant, version=stale)
        plan.refresh_from_db()
        self.assertEqual((plan.prepared_amount, plan.state), (D("1000"), PayoutPlan.State.DRAFT))

    def test_api_returns_409_on_conflict(self):
        plan = self.plan(approve=False)
        acc = self.client_for(self.accountant)
        ok = acc.patch(f"{API}/{plan.pk}/", {"prepared_amount": "5", "version": plan.version}, format="json")
        self.assertEqual(ok.status_code, 200)
        stale = acc.patch(f"{API}/{plan.pk}/", {"prepared_amount": "6", "version": plan.version}, format="json")
        self.assertEqual(stale.status_code, 409)
        self.assertEqual(stale.json()["code"], "conflict")


class CalendarSummaryTests(PayoutPlanFixture):
    def test_monthly_totals_and_calendar(self):
        oct1 = self.plan("600000", payrolls=self.payrolls[:2], payout_date=day(10, 1), title="1 октября")
        self.plan("0", payrolls=self.payrolls[2:3], payout_date=day(10, 15), title="15 октября")
        cancelled = self.plan(payrolls=self.payrolls[3:], payout_date=day(10, 20), title="Отменённый")
        pp.cancel_plan(cancelled, actor=self.accountant, reason="ошибка")
        self.pay(oct1, self.payrolls[0], "250000")
        plans = pp.filtered_plans({"year": 2026, "month": 9})
        summary = pp.summary(plans)
        self.assertEqual(summary["plans"], 2)
        self.assertEqual((summary["planned"], summary["paid"], summary["to_pay"]), (D("750000"), D("250000"), D("500000")))
        self.assertEqual(summary["prepared"], D("600000"))
        self.assertEqual(summary["deficit"], D("250000"))  # 1 окт: 500 000 − 600 000 → 0; 15 окт: 250 000
        self.assertEqual(summary["employees"], 3)
        self.assertEqual(summary["remaining_obligations"], D("500000"))
        cal = pp.calendar(plans, year=2026, month=9)
        self.assertEqual([d["date"] for d in cal["days"]], [day(10, 1), day(10, 15)])
        self.assertEqual(cal["days"][0]["to_pay"], D("250000"))
        self.assertEqual(cal["days"][0]["readiness_percent"], D("100.0"))
        self.assertEqual(cal["days"][1]["readiness_percent"], D("0.0"))
        # последний сотрудник (план отменён) — в рекомендациях
        self.assertEqual(sum(s["amount"] for s in cal["suggestions"]), D("250000"))
        self.assertEqual(len(pp.filtered_plans({"status": pp.CANCELLED})), 1)
        self.assertEqual(len(pp.filtered_plans({"employee": self.staff[2].pk})), 1)

    def test_candidates_show_free_balance(self):
        self.plan(payrolls=self.payrolls[:1], approve=False)
        rows = {r["payroll"]: r for r in pp.candidates(year=2026, month=9)}
        self.assertEqual(rows[self.payrolls[0].pk]["available"], D("0"))
        self.assertEqual(rows[self.payrolls[1].pk]["available"], D("250000"))


class AuditTests(PayoutPlanFixture):
    def test_history_records_every_action(self):
        plan = self.plan(approve=False)
        pp.update_plan(plan, actor=self.accountant, changes={"prepared_amount": D("500000")})
        pp.update_line(self.line(plan, self.payrolls[3]), actor=self.accountant, remove=True, reason="в следующий план")
        plan = pp.approve_plan(plan, actor=self.accountant)
        pp.update_plan(plan, actor=self.accountant, changes={"payout_date": day(10, 2)}, reason="банк не работает")
        self.pay(plan, self.payrolls[0], "250000")
        pp.cancel_plan(plan, actor=self.accountant, reason="перенос")
        plan_actions = list(PayrollAuditLog.objects.filter(entity_type="payoutplan", entity_id=plan.pk)
                            .order_by("id").values_list("action", flat=True))
        self.assertEqual(plan_actions, ["create", "change_prepared", "approve", "change_date", "pay_line", "cancel"])
        line_actions = set(PayrollAuditLog.objects.filter(entity_type="payoutplanline").values_list("action", flat=True))
        self.assertEqual(line_actions, {"add_line", "remove_line"})
        cancel = PayrollAuditLog.objects.get(entity_type="payoutplan", action="cancel")
        self.assertEqual((cancel.actor, cancel.reason), (self.accountant, "перенос"))
        date = PayrollAuditLog.objects.get(entity_type="payoutplan", action="change_date")
        self.assertEqual((date.old_values["payout_date"], date.new_values["payout_date"]), ("2026-10-01", "2026-10-02"))

    def test_detail_api_contains_lines_and_history(self):
        plan = self.plan("700000")
        data = self.client_for(self.director).get(f"{API}/{plan.pk}/").json()
        self.assertEqual(data["totals"]["deficit"], "300000.00")
        self.assertEqual(len(data["lines"]), 4)
        line = data["lines"][0]
        for key in ("employee_name", "position", "department_display", "salary_type_display", "period_label",
                    "accrued", "paid_before", "planned_amount", "due_after_plan", "status_display", "basis"):
            self.assertIn(key, line)
        self.assertIn("approve", [h["action"] for h in data["history"]])


class PermissionTests(PayoutPlanFixture):
    def body(self):
        return {"title": "1 октября", "year": 2026, "month": 9, "payout_date": "2026-10-01",
                "prepared_amount": "700000", "lines": [{"payroll": p.pk} for p in self.payrolls]}

    def test_accountant_full_flow_via_api(self):
        acc = self.client_for(self.accountant)
        created = acc.post(f"{API}/", self.body(), format="json")
        self.assertEqual(created.status_code, 201, created.content)
        plan = created.json()
        self.assertEqual(plan["totals"]["planned"], "1000000.00")
        approved = acc.post(f"{API}/{plan['id']}/approve/", {"version": plan["version"]}, format="json")
        self.assertEqual(approved.status_code, 200, approved.content)
        line_id = approved.json()["lines"][0]["id"]
        paid = acc.post(f"{API}/{plan['id']}/lines/{line_id}/pay/", {
            "amount": "250000", "payment_date": "2026-10-01", "idempotency_key": "plan-pay-1"}, format="json")
        self.assertEqual(paid.status_code, 201, paid.content)
        repeat = acc.post(f"{API}/{plan['id']}/lines/{line_id}/pay/", {
            "amount": "250000", "payment_date": "2026-10-01", "idempotency_key": "plan-pay-1"}, format="json")
        self.assertEqual(repeat.status_code, 200)
        over = acc.post(f"{API}/{plan['id']}/lines/{line_id}/pay/", {
            "amount": "1", "payment_date": "2026-10-01"}, format="json")
        self.assertEqual(over.status_code, 400)
        listing = acc.get(f"{API}/", {"year": 2026, "month": 9}).json()
        self.assertEqual(listing["count"], 1)
        self.assertEqual(listing["results"][0]["totals"]["status"], pp.PARTIALLY_PAID)
        for url in ("summary/", "calendar/", "candidates/", f"{plan['id']}/report.xlsx/", f"{plan['id']}/report.pdf/"):
            self.assertEqual(acc.get(f"{API}/{url}", {"year": 2026, "month": 9}).status_code, 200, url)
        cancelled = acc.post(f"{API}/{plan['id']}/cancel/", {"reason": "перенос"}, format="json")
        self.assertEqual(cancelled.json()["totals"]["status"], pp.CANCELLED)

    def test_director_reads_only(self):
        plan = self.plan(approve=False)
        boss = self.client_for(self.director)
        self.assertEqual(boss.get(f"{API}/").status_code, 200)
        self.assertEqual(boss.get(f"{API}/{plan.pk}/").status_code, 200)
        self.assertEqual(boss.get(f"{API}/summary/").status_code, 200)
        self.assertEqual(boss.post(f"{API}/", self.body(), format="json").status_code, 403)
        self.assertEqual(boss.post(f"{API}/{plan.pk}/approve/", {}, format="json").status_code, 403)
        self.assertEqual(boss.patch(f"{API}/{plan.pk}/", {"prepared_amount": "1"}, format="json").status_code, 403)
        self.assertEqual(boss.post(f"{API}/{plan.pk}/cancel/", {"reason": "x"}, format="json").status_code, 403)

    def test_employee_sees_only_own_planned_payouts(self):
        plan = self.plan()
        emp = self.client_for(self.staff[0])
        self.assertEqual(emp.get(f"{API}/").status_code, 403)
        self.assertEqual(emp.get(f"{API}/{plan.pk}/").status_code, 403)
        self.assertEqual(emp.get(f"{API}/summary/").status_code, 403)
        mine = emp.get("/api/v1/accounting/my/payout-plan/").json()["results"]
        self.assertEqual(len(mine), 1)
        self.assertEqual(mine[0]["planned_amount"], "250000.00")
        self.assertNotIn("prepared_amount", mine[0])
        other = self.client_for(self.trainer_user).get("/api/v1/accounting/my/payout-plan/").json()["results"]
        self.assertEqual(other, [])

    def test_anonymous_denied(self):
        from rest_framework.test import APIClient

        anon = APIClient()
        self.assertIn(anon.get(f"{API}/").status_code, (401, 403))
        self.assertIn(anon.get("/api/v1/accounting/my/payout-plan/").status_code, (401, 403))


@unittest.skipUnless(connection.vendor == "postgresql", "нужны настоящие параллельные транзакции (PostgreSQL)")
class ParallelPlanningTests(TransactionTestCase):
    """Два бухгалтера одновременно планируют один остаток — резерв не удваивается."""

    def test_parallel_plans_cannot_double_reserve(self):
        accountant = make_user("buh_p", User.Role.ACCOUNTANT)
        director = make_user("boss_p", User.Role.DIRECTOR)
        employee = make_user("emp_p", User.Role.ASSISTANT)
        profile = EmployeeSalaryProfile.objects.create(employee=employee, salary_type=SalaryType.FIXED,
                                                       effective_from=day(1, 1))
        SalaryRule.objects.create(employee_profile=profile, rule_type=R.FIXED, amount=D("10000"),
                                  calculation_method="MONTHLY", effective_from=day(1, 1))
        period = get_or_create_period(2026, 9, MONTH, accountant)[0]
        payroll = approve_payroll(calculate_payroll(period, employee, accountant), director)
        barrier = threading.Barrier(4)
        results = []

        def attempt(i):
            try:
                barrier.wait()
                pp.create_plan(actor=accountant, title=f"План {i}", year=2026, month=9, payout_date=day(10, 1),
                               lines=[{"payroll": payroll.pk, "amount": D("4000")}])
                results.append("ok")
            except AccountingError as exc:
                results.append(exc.code)
            finally:
                connection.close()

        threads = [threading.Thread(target=attempt, args=(i,)) for i in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(results.count("ok"), 2)
        self.assertEqual(results.count("exceeds_due"), 2)
        self.assertEqual(pp.available(payroll), D("2000"))
        self.assertEqual(PayoutPlan.objects.count(), 2)
