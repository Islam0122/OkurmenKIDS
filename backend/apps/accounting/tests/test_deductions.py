"""Налоги и удержания: одно ежемесячное удержание на сотрудника за месяц,
сколько бы у него ни было начислений, без отрицательного остатка, с историей
версий, корректной работой выплат и «Плана выплат»."""
from __future__ import annotations

import threading
import unittest

from django.db import IntegrityError, connection, transaction
from django.test import TransactionTestCase

from apps.academy.models import GroupTeacher
from apps.accounting.models import (
    AppliedDeduction,
    DeductionAllocation,
    DeductionRule,
    Payroll,
    PayrollAuditLog,
    SalaryRule,
    SalaryType,
)
from apps.accounting.services import AccountingError
from apps.accounting.services import deductions as ded
from apps.accounting.services import payout_plans as pp
from apps.accounting.services.approval_service import approve_payroll, create_adjustment, void_payroll
from apps.accounting.services.payment_service import register_payment
from apps.accounting.services.payroll_calculator import calculate_period
from apps.accounting.tests.base import FIRST, MONTH, SECOND, D, AccountingFixture, day, make_user
from apps.accounting.tests.test_subject_cycles import SubjectFixture, days
from apps.users.models import User

R = SalaryRule.RuleType
K, F, S = DeductionRule.Kind, DeductionRule.Frequency, DeductionRule.Scope
API = "/api/v1/accounting"
OCT = (2026, 10)


class DeductionFixture(AccountingFixture):
    def deduction(self, amount, *, employee=None, name="Налог", kind=K.TAX, frequency=F.MONTHLY, start=day(1, 1),
                  end=None, scope=S.EMPLOYEE, department=""):
        rule, _ = ded.create_rule(
            actor=self.accountant, name=name, kind=kind, amount=D(amount), frequency=frequency, scope=scope,
            employee=employee if scope == S.EMPLOYEE else None, department=department, effective_from=start,
            effective_to=end,
        )
        return rule

    def fixed(self, user, salary):
        self.rule(self.profile(user), R.FIXED, amount=D(salary))

    def fresh(self, payroll):
        return Payroll.objects.get(pk=payroll.pk)


class FixedSalaryTests(DeductionFixture):
    def setUp(self):
        super().setUp()
        self.emp = make_user("emp", User.Role.ASSISTANT)
        self.fixed(self.emp, "20000")

    def test_one_payroll_one_monthly_deduction(self):
        self.deduction("3000", employee=self.emp)
        payroll = self.calc(MONTH, user=self.emp, year_month=OCT)
        self.assertEqual((payroll.total_accrued, payroll.total_deductions, payroll.amount_due),
                         (D("20000"), D("3000"), D("17000")))
        self.assertEqual(AppliedDeduction.objects.count(), 1)
        [row] = ded.payroll_deductions(payroll)
        self.assertEqual((row["name"], row["amount"], row["remaining"]), ("Налог", D("3000"), D("0")))

    def test_two_different_rules_are_separate_records(self):
        self.deduction("2000", employee=self.emp, name="Налог", kind=K.TAX)
        self.deduction("500", employee=self.emp, name="Профсоюз", kind=K.OTHER)
        payroll = self.calc(MONTH, user=self.emp, year_month=OCT)
        self.assertEqual((payroll.total_deductions, payroll.amount_due), (D("2500"), D("17500")))
        self.assertEqual(sorted(AppliedDeduction.objects.values_list("name", "kind", "amount")),
                         [("Налог", K.TAX, D("2000.00")), ("Профсоюз", K.OTHER, D("500.00"))])

    def test_recalculation_does_not_duplicate(self):
        self.deduction("3000", employee=self.emp)
        for _ in range(3):
            payroll = self.calc(MONTH, user=self.emp, year_month=OCT)
        calculate_period(self.period(OCT, MONTH), self.accountant)
        payroll = self.fresh(payroll)
        self.assertEqual(AppliedDeduction.objects.count(), 1)
        self.assertEqual(DeductionAllocation.objects.count(), 1)
        self.assertEqual((payroll.total_deductions, payroll.amount_due), (D("3000"), D("17000")))

    def test_unique_constraint_blocks_second_record_for_same_month(self):
        rule = self.deduction("3000", employee=self.emp)
        self.calc(MONTH, user=self.emp, year_month=OCT)
        with self.assertRaises(IntegrityError), transaction.atomic():
            AppliedDeduction.objects.create(rule=rule, series=rule.series, employee=self.emp, year=2026, month=10,
                                            name="x", kind=rule.kind, amount=D("1"))

    def test_partial_payment_reduces_remaining(self):
        self.deduction("3000", employee=self.emp)
        payroll = approve_payroll(self.calc(MONTH, user=self.emp, year_month=OCT), self.director)
        register_payment(payroll, amount=D("7000"), payment_date=day(11, 1), actor=self.accountant)
        payroll = self.fresh(payroll)
        self.assertEqual((payroll.total_paid, payroll.amount_due, payroll.status),
                         (D("7000"), D("10000"), Payroll.Status.PARTIALLY_PAID))
        with self.assertRaises(AccountingError):
            register_payment(payroll, amount=D("10000.01"), payment_date=day(11, 1), actor=self.accountant)
        register_payment(payroll, amount=D("10000"), payment_date=day(11, 2), actor=self.accountant)
        self.assertEqual(self.fresh(payroll).status, Payroll.Status.PAID)

    def test_payout_plan_does_not_subtract_again(self):
        self.deduction("3000", employee=self.emp)
        payroll = approve_payroll(self.calc(MONTH, user=self.emp, year_month=OCT), self.director)
        plan = pp.create_plan(actor=self.accountant, title="Октябрь", year=2026, month=10, payout_date=day(11, 1),
                              lines=[{"payroll": payroll}])
        line = plan.lines.get()
        self.assertEqual(line.planned_amount, D("17000"))
        self.assertEqual(pp.explain_line(line)["deductions"], D("3000"))
        with self.assertRaises(AccountingError):
            pp.add_lines(plan, actor=self.accountant, items=[{"payroll": payroll}])
        plan = pp.approve_plan(plan, actor=self.accountant)
        pp.pay_line(line, actor=self.accountant, amount=D("17000"), payment_date=day(11, 1), payment_method="bank")
        self.assertEqual(pp.totals(plan).status, pp.PAID)
        self.assertEqual(self.fresh(payroll).amount_due, D("0"))

    def test_deduction_larger_than_salary_never_goes_negative(self):
        self.deduction("25000", employee=self.emp)
        payroll = self.calc(MONTH, user=self.emp, year_month=OCT)
        self.assertEqual((payroll.total_deductions, payroll.amount_due), (D("20000"), D("0")))
        [row] = ded.payroll_deductions(payroll)
        self.assertEqual(row["remaining"], D("5000"))
        # Остаток не переносится автоматически: в ноябре — снова сумма месяца, не 30 000.
        november = self.calc(MONTH, user=self.emp, year_month=(2026, 11))
        self.assertEqual(november.total_deductions, D("20000"))
        self.assertEqual(AppliedDeduction.objects.get(year=2026, month=11).amount, D("25000"))

    def test_draft_adjustment_redistributes_without_negative(self):
        self.deduction("3000", employee=self.emp)
        payroll = self.calc(MONTH, user=self.emp, year_month=OCT)
        create_adjustment(payroll, kind="DEDUCTION", amount=D("18000"), reason="штраф", actor=self.accountant)
        payroll = self.fresh(payroll)
        self.assertEqual((payroll.total_adjustments, payroll.total_deductions, payroll.amount_due),
                         (D("-18000"), D("2000"), D("0")))

    def test_once_rule_applies_only_in_its_month(self):
        self.deduction("1000", employee=self.emp, name="Форма", kind=K.OTHER, frequency=F.ONCE, start=day(10, 5))
        self.assertEqual(self.calc(MONTH, user=self.emp, year_month=OCT).total_deductions, D("1000"))
        self.assertEqual(self.calc(MONTH, user=self.emp, year_month=(2026, 11)).total_deductions, D("0"))

    def test_period_rule_only_inside_range_and_requires_end(self):
        with self.assertRaises(AccountingError):
            self.deduction("1000", employee=self.emp, frequency=F.PERIOD, start=day(10, 1))
        self.deduction("1000", employee=self.emp, frequency=F.PERIOD, start=day(10, 1), end=day(10, 31))
        self.assertEqual(self.calc(MONTH, user=self.emp, year_month=OCT).total_deductions, D("1000"))
        self.assertEqual(self.calc(MONTH, user=self.emp, year_month=(2026, 11)).total_deductions, D("0"))

    def test_department_scope(self):
        other = make_user("other", User.Role.ASSISTANT)
        self.fixed(other, "10000")
        self.deduction("700", scope=S.DEPARTMENT, department="ASSISTANT", name="Взнос", kind=K.CONTRIBUTION)
        self.assertEqual(self.calc(MONTH, user=self.emp, year_month=OCT).total_deductions, D("700"))
        self.assertEqual(self.calc(MONTH, user=other, year_month=OCT).total_deductions, D("700"))

    def test_disabled_rule_is_not_applied_and_stale_record_removed(self):
        rule = self.deduction("3000", employee=self.emp)
        payroll = self.calc(MONTH, user=self.emp, year_month=OCT)
        ded.change_rule(rule, actor=self.accountant, changes={"is_active": False}, reason="ошибка")
        payroll = self.fresh(payroll)  # черновик пересчитан автоматически
        self.assertEqual((payroll.total_deductions, payroll.amount_due), (D("0"), D("20000")))
        self.assertFalse(AppliedDeduction.objects.exists())


class HistoryTests(DeductionFixture):
    def setUp(self):
        super().setUp()
        self.emp = make_user("emp", User.Role.ASSISTANT)
        self.fixed(self.emp, "20000")

    def test_unused_rule_is_corrected_in_place_and_draft_recalculated(self):
        rule = self.deduction("3000", employee=self.emp)
        payroll = self.calc(MONTH, user=self.emp, year_month=OCT)
        rule, effects = ded.change_rule(rule, actor=self.accountant, changes={"amount": D("2500")}, reason="опечатка")
        self.assertEqual(effects["payrolls_recalculated"], [payroll.pk])
        self.assertEqual(self.fresh(payroll).total_deductions, D("2500"))
        self.assertEqual(DeductionRule.objects.count(), 1)
        log = PayrollAuditLog.objects.get(entity_type="deductionrule", action="deduction_rule_correct")
        self.assertEqual((log.old_values["amount"], log.new_values["amount"], log.reason, log.actor),
                         ("3000.00", "2500.00", "опечатка", self.accountant))

    def test_change_after_approval_keeps_history(self):
        rule = self.deduction("3000", employee=self.emp)
        october = approve_payroll(self.calc(MONTH, user=self.emp, year_month=OCT), self.director)
        with self.assertRaises(AccountingError) as ctx:
            ded.change_rule(rule, actor=self.accountant, changes={"amount": D("4000")}, reason="рост")
        self.assertEqual(ctx.exception.code, "date_required")
        with self.assertRaises(AccountingError) as ctx:
            ded.change_rule(rule, actor=self.accountant, changes={"amount": D("4000"), "effective_from": day(10, 1)},
                            reason="рост")
        self.assertEqual(ctx.exception.code, "used")
        with self.assertRaises(AccountingError) as ctx:
            ded.change_rule(rule, actor=self.accountant, changes={"amount": D("4000"), "effective_from": day(11, 10)},
                            reason="рост")
        self.assertEqual(ctx.exception.code, "month_start")
        with self.assertRaises(AccountingError):
            ded.change_rule(rule, actor=self.accountant, changes={"amount": D("4000"), "effective_from": day(11, 1)},
                            reason=" ")
        new, _ = ded.change_rule(rule, actor=self.accountant,
                                 changes={"amount": D("4000"), "effective_from": day(11, 1)}, reason="рост")
        rule.refresh_from_db()
        self.assertEqual((rule.amount, rule.effective_to), (D("3000"), day(10, 31)))
        self.assertEqual((new.amount, new.effective_from, new.previous_version, new.series),
                         (D("4000"), day(11, 1), rule, rule.series))
        self.assertEqual(self.fresh(october).total_deductions, D("3000"))  # утверждённое не переписано
        self.assertEqual(self.calc(MONTH, user=self.emp, year_month=(2026, 11)).total_deductions, D("4000"))
        log = PayrollAuditLog.objects.get(entity_type="deductionrule", action="deduction_rule_new_version")
        self.assertEqual((log.old_values["amount"], log.new_values["amount"], log.reason), ("3000.00", "4000.00", "рост"))
        with self.assertRaises(AccountingError):  # менять можно только последнюю версию
            ded.change_rule(rule, actor=self.accountant, changes={"name": "x"}, reason="y")
        with self.assertRaises(AccountingError):  # закрыть раньше утверждённого месяца нельзя
            ded.change_rule(new, actor=self.accountant, changes={"effective_to": day(10, 15)}, reason="y")

    def test_rules_cannot_be_deleted(self):
        rule = self.deduction("3000", employee=self.emp)
        with self.assertRaises(Exception):
            rule.delete()
        with self.assertRaises(Exception):
            DeductionRule.objects.all().delete()


class HalfMonthTests(DeductionFixture):
    """Процент: два начисления в месяце (1–15 и 16–конец) — 30 000 + 20 000."""

    def setUp(self):
        super().setUp()
        self.course_settings(price="10000", lessons=12, start=None)
        self.rule(self.profile(salary_type=SalaryType.PERCENT), R.PERCENT, percentage=D("10"))
        for _ in range(30):
            self.student(self.group_a)
        for _ in range(20):
            self.student(self.group_b)
        with self.captureOnCommitCallbacks(execute=True):
            self.lessons(self.group_a, days(10, 1, 12))
            self.lessons(self.group_b, days(10, 16, 27))

    def test_two_payrolls_in_month_deduct_once(self):
        self.deduction("3000", employee=self.trainer_user)
        first = self.calc(FIRST, year_month=OCT)
        second = self.calc(SECOND, year_month=OCT)
        first, second = self.fresh(first), self.fresh(second)
        self.assertEqual((first.total_accrued, second.total_accrued), (D("30000"), D("20000")))
        self.assertEqual(first.total_deductions + second.total_deductions, D("3000"))
        self.assertEqual(first.amount_due + second.amount_due, D("47000"))
        self.assertEqual(AppliedDeduction.objects.count(), 1)
        for _ in range(2):  # повторные пересчёты обеих половин — без дублей
            self.calc(SECOND, year_month=OCT)
            self.calc(FIRST, year_month=OCT)
        total = sum((p.total_deductions for p in Payroll.objects.filter(period__month=10)), D("0"))
        self.assertEqual((total, AppliedDeduction.objects.count()), (D("3000"), 1))

    def test_shortfall_in_first_half_is_taken_from_second_half_of_same_month(self):
        self.deduction("35000", employee=self.trainer_user)
        first = self.fresh(self.calc(FIRST, year_month=OCT))
        self.assertEqual((first.total_deductions, first.amount_due), (D("30000"), D("0")))
        second = self.fresh(self.calc(SECOND, year_month=OCT))
        self.assertEqual((second.total_deductions, second.amount_due), (D("5000"), D("15000")))

    def test_void_payroll_releases_its_share(self):
        self.deduction("3000", employee=self.trainer_user)
        first = self.calc(FIRST, year_month=OCT)
        second = self.calc(SECOND, year_month=OCT)
        void_payroll(first, self.director, "ошибка")
        second = self.fresh(self.calc(SECOND, year_month=OCT))
        self.assertEqual(second.total_deductions, D("3000"))

    def test_approved_first_half_keeps_its_deduction(self):
        self.deduction("3000", employee=self.trainer_user)
        approve_payroll(self.calc(FIRST, year_month=OCT), self.director)
        second = self.fresh(self.calc(SECOND, year_month=OCT))
        self.assertEqual(second.total_deductions, D("0"))
        self.assertEqual(second.amount_due, D("20000"))


class SubjectsTests(SubjectFixture, DeductionFixture):
    """Несколько предметов и несколько циклов у одного тренера."""

    def test_several_subjects_and_cycles_deduct_once(self):
        GroupTeacher.objects.filter(group=self.group_a, subject=self.english).update(teacher=self.trainer)
        self.deduction("1500", employee=self.trainer_user)
        self.teach(self.python, days(10, 1, 12))
        self.teach(self.english, days(10, 1, 12))
        self.teach(self.python, days(10, 16, 27))
        first = self.fresh(self.calc(FIRST, year_month=OCT))
        second = self.fresh(self.calc(SECOND, year_month=OCT))
        self.assertGreaterEqual(first.lines.count(), 2)  # два предмета, два цикла — две строки
        self.assertEqual(first.total_deductions + second.total_deductions, D("1500"))
        self.assertEqual(AppliedDeduction.objects.count(), 1)


class PermissionTests(DeductionFixture):
    def setUp(self):
        super().setUp()
        self.emp = make_user("emp", User.Role.ASSISTANT)
        self.fixed(self.emp, "20000")
        self.body = {"name": "Налог", "kind": "TAX", "amount": "3000", "frequency": "MONTHLY", "scope": "EMPLOYEE",
                     "employee": self.emp.pk, "effective_from": "2026-10-01"}

    def test_accountant_creates_and_changes(self):
        acc = self.client_for(self.accountant)
        created = acc.post(f"{API}/deduction-rules/", self.body, format="json")
        self.assertEqual(created.status_code, 201, created.content)
        rule_id = created.json()["rule"]["id"]
        bad = acc.post(f"{API}/deduction-rules/{rule_id}/change/", {"amount": "2000"}, format="json")
        self.assertEqual(bad.status_code, 400)  # без причины
        ok = acc.post(f"{API}/deduction-rules/{rule_id}/change/", {"amount": "2000", "reason": "уточнение"},
                      format="json")
        self.assertEqual(ok.status_code, 200, ok.content)
        self.assertEqual(ok.json()["rule"]["amount"], "2000.00")
        history = acc.get(f"{API}/deduction-rules/{rule_id}/history/").json()
        self.assertEqual([a["action"] for a in history["audit"]], ["deduction_rule_correct", "deduction_rule_create"])
        self.assertEqual(acc.post(f"{API}/deduction-rules/", {**self.body, "amount": "-5"}, format="json").status_code,
                         400)
        payroll = self.calc(MONTH, user=self.emp, year_month=OCT)
        detail = acc.get(f"{API}/payrolls/{payroll.pk}/").json()
        self.assertEqual((detail["total_deductions"], detail["amount_due"]), ("2000.00", "18000.00"))
        self.assertEqual(detail["deductions"][0]["name"], "Налог")
        self.assertEqual(acc.get(f"{API}/applied-deductions/", {"year": 2026, "month": 10}).json()["count"], 1)

    def test_director_reads_only(self):
        boss = self.client_for(self.director)
        self.assertEqual(boss.get(f"{API}/deduction-rules/").status_code, 200)
        self.assertEqual(boss.get(f"{API}/applied-deductions/").status_code, 200)
        self.assertEqual(boss.post(f"{API}/deduction-rules/", self.body, format="json").status_code, 403)
        rule = self.deduction("3000", employee=self.emp)
        self.assertEqual(boss.post(f"{API}/deduction-rules/{rule.pk}/change/", {"amount": "1", "reason": "x"},
                                   format="json").status_code, 403)

    def test_employee_sees_only_own_deductions(self):
        other = make_user("other", User.Role.ASSISTANT)
        self.fixed(other, "50000")
        self.deduction("3000", employee=self.emp)
        self.deduction("9999", employee=other, name="Чужое")
        approve_payroll(self.calc(MONTH, user=self.emp, year_month=OCT), self.director)
        approve_payroll(self.calc(MONTH, user=other, year_month=OCT), self.director)
        emp = self.client_for(self.emp)
        self.assertEqual(emp.get(f"{API}/deduction-rules/").status_code, 403)
        self.assertEqual(emp.get(f"{API}/applied-deductions/").status_code, 403)
        data = emp.get(f"{API}/my/salary/").json()
        rows = data["history"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["deducted"], "3000.00")
        self.assertEqual([d["name"] for d in rows[0]["deductions"]], ["Налог"])
        self.assertEqual(data["totals"]["due"], "17000.00")
        self.assertNotIn("Чужое", str(data))


@unittest.skipUnless(connection.vendor == "postgresql", "нужны настоящие параллельные транзакции (PostgreSQL)")
class ParallelCalculationTests(TransactionTestCase):
    """Две половины месяца одного сотрудника считаются одновременно — удержание
    месяца всё равно одно (блокировка записи месяца + уникальный индекс)."""

    def test_parallel_halves_deduct_once(self):
        from apps.accounting.models import EmployeeSalaryProfile, PayrollLine
        from apps.accounting.services.payroll_calculator import refresh_totals
        from apps.accounting.services.periods import get_or_create_period

        accountant = make_user("buh_d", User.Role.ACCOUNTANT)
        employee = make_user("emp_d", User.Role.TEACHER)
        EmployeeSalaryProfile.objects.create(employee=employee, salary_type=SalaryType.PERCENT, effective_from=day(1, 1))
        ded.create_rule(actor=accountant, name="Налог", kind=K.TAX, amount=D("3000"), frequency=F.MONTHLY,
                        scope=S.EMPLOYEE, employee=employee, effective_from=day(1, 1))
        payrolls = []
        for half in (FIRST, SECOND):
            period = get_or_create_period(2026, 10, half, accountant)[0]
            p = Payroll.objects.create(period=period, employee=employee, status=Payroll.Status.CALCULATED)
            PayrollLine.objects.create(payroll=p, line_type="PERCENT", description="цикл", amount=D("10000"))
            payrolls.append(p)
        barrier = threading.Barrier(2)
        errors = []

        def attempt(payroll):
            try:
                barrier.wait()
                with transaction.atomic():
                    locked = Payroll.objects.select_for_update().get(pk=payroll.pk)
                    ded.apply_to_payroll(locked, accountant)
                    refresh_totals(locked)
                    locked.save()
            except Exception as exc:  # noqa: BLE001
                errors.append(repr(exc))
            finally:
                connection.close()

        threads = [threading.Thread(target=attempt, args=(p,)) for p in payrolls]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(errors, [])
        self.assertEqual(AppliedDeduction.objects.count(), 1)
        total = sum((p.total_deductions for p in Payroll.objects.filter(pk__in=[p.pk for p in payrolls])), D("0"))
        self.assertEqual(total, D("3000"))
