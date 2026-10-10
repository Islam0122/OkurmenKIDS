"""Исправление ошибочно созданных правил зарплаты и замена использованных
без изменения истории начислений и выплат."""
from __future__ import annotations

import datetime as dt

from apps.accounting.models import (
    CycleAccrual,
    EmployeeSalaryProfile,
    Payroll,
    PayrollAuditLog,
    PayrollPayment,
    SalaryRule,
    SalaryType,
)
from apps.accounting.services import AccountingError
from apps.accounting.services.approval_service import approve_payroll
from apps.accounting.services.payment_service import register_payment
from apps.accounting.services.salary_rules import correct_rule, replace_rule, rule_usage
from apps.accounting.tests.base import FIRST, MONTH, D, AccountingFixture, day

R = SalaryRule.RuleType
API = "/api/v1/accounting"


def days(month, first, last):
    return [day(month, d) for d in range(first, last + 1)]


class CorrectUnusedRuleTests(AccountingFixture):
    """Сценарий из жалобы: случайно создан «Фиксированный оклад» вместо процента."""

    def setUp(self):
        super().setUp()
        self.course_settings(price="10000", lessons=12, start=None)
        for _ in range(10):
            self.student(self.group_a)
        self.profile_ = self.profile(salary_type=SalaryType.FIXED)
        self.wrong = self.rule(self.profile_, R.FIXED, amount=D("30000"))

    def test_fixed_rule_created_by_mistake_becomes_percent(self):
        self.assertTrue(rule_usage(self.wrong)["can_correct"])
        rule, _ = correct_rule(self.wrong, actor=self.accountant, reason="Ошибочно выбран оклад",
                               changes={"rule_type": R.PERCENT, "percentage": D("10")})
        self.assertEqual((rule.pk, rule.rule_type, rule.amount, rule.percentage, rule.calculation_method),
                         (self.wrong.pk, R.PERCENT, None, D("10"), "STANDARD"))
        self.profile_.refresh_from_db()
        self.assertEqual(self.profile_.salary_type, SalaryType.PERCENT)
        log = PayrollAuditLog.objects.get(entity_type="salaryrule", action="correct")
        self.assertEqual((log.old_values["rule_type"], log.new_values["rule_type"], log.reason),
                         ("FIXED", "PERCENT", "Ошибочно выбран оклад"))
        self.assertTrue(PayrollAuditLog.objects.filter(action="change_salary_type").exists())
        # Дальше процент начисляется как обычно.
        with self.captureOnCommitCallbacks(execute=True):
            self.lessons(self.group_a, days(9, 1, 12))
        self.assertEqual(self.calc(FIRST).total_accrued, D("10000.00"))

    def test_draft_payroll_is_recalculated_after_rate_fix(self):
        draft = self.calc(MONTH)
        self.assertEqual(draft.total_accrued, D("30000.00"))
        _, effects = correct_rule(self.wrong, actor=self.accountant, reason="опечатка", changes={"amount": D("25000")})
        draft.refresh_from_db()
        self.assertEqual((draft.total_accrued, effects["payrolls_recalculated"]), (D("25000.00"), [draft.pk]))

    def test_draft_payroll_of_wrong_type_is_voided_not_deleted(self):
        draft = self.calc(MONTH)
        _, effects = correct_rule(self.wrong, actor=self.accountant, reason="не оклад",
                                  changes={"rule_type": R.PERCENT, "percentage": D("10")})
        draft.refresh_from_db()
        self.assertEqual((draft.status, effects["payrolls_voided"]), (Payroll.Status.VOID, [draft.pk]))
        self.assertTrue(PayrollAuditLog.objects.filter(entity_type="payroll", action="void", entity_id=draft.pk).exists())

    def test_type_change_refused_when_profile_has_other_rules(self):
        self.wrong.effective_to = day(5, 31)
        self.wrong.save()
        self.rule(self.profile_, R.FIXED, amount=D("1000"), start=day(6, 1))
        with self.assertRaises(AccountingError) as ctx:
            correct_rule(self.wrong, actor=self.accountant, reason="x",
                         changes={"rule_type": R.PERCENT, "percentage": D("10")})
        self.assertEqual(ctx.exception.code, "type_conflict")

    def test_reason_and_overlap_are_validated(self):
        with self.assertRaises(AccountingError):
            correct_rule(self.wrong, actor=self.accountant, reason=" ", changes={"amount": D("1")})
        self.wrong.effective_to = day(5, 31)
        self.wrong.save()
        second = self.rule(self.profile_, R.FIXED, amount=D("1000"), start=day(6, 1))
        with self.assertRaises(AccountingError) as ctx:
            correct_rule(second, actor=self.accountant, reason="даты", changes={"effective_from": day(5, 1)})
        self.assertEqual(ctx.exception.code, "overlap")


class CorrectPercentAccrualTests(AccountingFixture):
    def setUp(self):
        super().setUp()
        self.course_settings(price="10000", lessons=12, start=None)
        for _ in range(10):
            self.student(self.group_a)
        self.rule_ = self.rule(self.profile(salary_type=SalaryType.PERCENT), R.PERCENT, percentage=D("10"))
        with self.captureOnCommitCallbacks(execute=True):
            self.lessons(self.group_a, days(9, 1, 12))
        self.accrual = CycleAccrual.objects.get()

    def test_unapproved_accrual_follows_corrected_rate(self):
        draft = self.calc(FIRST)
        correct_rule(self.rule_, actor=self.accountant, reason="ставка 15%", changes={"percentage": D("15")})
        self.accrual.refresh_from_db()
        draft.refresh_from_db()
        self.assertEqual((self.accrual.amount, self.accrual.percentage, draft.total_accrued),
                         (D("15000.00"), D("15"), D("15000.00")))

    def test_accrual_not_due_after_scope_fix_is_cancelled_and_kept(self):
        correct_rule(self.rule_, actor=self.accountant, reason="только группа B", changes={"group": self.group_b})
        self.accrual.refresh_from_db()
        self.assertEqual(self.accrual.status, CycleAccrual.Status.CANCELLED)
        self.assertEqual(CycleAccrual.objects.count(), 1)


class UsedRuleTests(AccountingFixture):
    """Правило уже в утверждённом начислении с выплатой — история неизменна."""

    def setUp(self):
        super().setUp()
        self.profile_ = self.profile(salary_type=SalaryType.FIXED)
        self.used = self.rule(self.profile_, R.FIXED, amount=D("30000"))
        self.payroll = approve_payroll(self.calc(MONTH), self.director)  # сентябрь утверждён
        register_payment(self.payroll, amount=D("10000"), payment_date=day(9, 30), actor=self.accountant)

    def test_correction_is_refused(self):
        usage = rule_usage(self.used)
        self.assertEqual((usage["can_correct"], usage["locked_payrolls"], usage["used_until"]),
                         (False, 1, day(9, 30)))
        with self.assertRaises(AccountingError) as ctx:
            correct_rule(self.used, actor=self.accountant, reason="x", changes={"amount": D("1")})
        self.assertEqual(ctx.exception.code, "rule_used")
        self.used.refresh_from_db()
        self.assertEqual(self.used.amount, D("30000"))

    def test_replace_from_a_date_keeps_history(self):
        with self.assertRaises(AccountingError):  # раньше последнего утверждённого использования
            replace_rule(self.used, actor=self.accountant, effective_from=day(9, 15), reason="x",
                         data={"rule_type": R.FIXED, "amount": D("35000")})
        with self.assertRaises(AccountingError) as ctx:  # смена типа — только с 1-го числа
            replace_rule(self.used, actor=self.accountant, effective_from=day(10, 10), reason="x",
                         data={"rule_type": R.PERCENT, "percentage": D("10")})
        self.assertEqual(ctx.exception.code, "bad_date")
        new, _ = replace_rule(self.used, actor=self.accountant, effective_from=day(10, 1), reason="Переход на процент",
                              data={"rule_type": R.PERCENT, "percentage": D("10")})
        self.used.refresh_from_db()
        self.profile_.refresh_from_db()
        self.assertEqual((self.used.effective_to, new.effective_from, new.previous_version_id, new.rule_type),
                         (day(9, 30), day(10, 1), self.used.pk, R.PERCENT))
        self.assertEqual(self.profile_.salary_type, SalaryType.PERCENT)
        self.payroll.refresh_from_db()
        self.assertEqual((self.payroll.status, self.payroll.total_accrued, self.payroll.total_paid),
                         (Payroll.Status.PARTIALLY_PAID, D("30000.00"), D("10000.00")))
        self.assertEqual(self.payroll.lines.get().salary_rule_id, self.used.pk)
        self.assertEqual(PayrollPayment.objects.count(), 1)

    def test_same_type_replacement_with_new_rate(self):
        new, _ = replace_rule(self.used, actor=self.accountant, effective_from=day(10, 1), reason="повышение",
                              data={"rule_type": R.FIXED, "amount": D("35000")})
        self.assertEqual(self.calc(MONTH, year_month=(2026, 10)).total_accrued, D("35000.00"))
        self.assertEqual(new.employee_profile.salary_type, SalaryType.FIXED)


class PercentToFixedGuardTests(AccountingFixture):
    def test_pending_percent_accruals_block_type_switch(self):
        self.course_settings(price="10000", lessons=12, start=None)
        self.student(self.group_a)
        rule = self.rule(self.profile(salary_type=SalaryType.PERCENT), R.PERCENT, percentage=D("10"))
        with self.captureOnCommitCallbacks(execute=True):
            self.lessons(self.group_a, days(9, 1, 12))
        approve_payroll(self.calc(FIRST), self.director)
        with self.captureOnCommitCallbacks(execute=True):
            self.lessons(self.group_a, [dt.date(2026, 9, 20) + dt.timedelta(days=i) for i in range(12)])
        with self.assertRaises(AccountingError) as ctx:
            replace_rule(rule, actor=self.accountant, effective_from=day(11, 1), reason="на оклад",
                         data={"rule_type": R.FIXED, "amount": D("30000")})
        self.assertEqual(ctx.exception.code, "pending_accruals")


class RuleCorrectionApiTests(AccountingFixture):
    def setUp(self):
        super().setUp()
        self.profile_ = self.profile(salary_type=SalaryType.FIXED)
        self.wrong = self.rule(self.profile_, R.FIXED, amount=D("30000"))

    def test_correct_endpoint_and_rights(self):
        url = f"{API}/salary-rules/{self.wrong.pk}/correct/"
        body = {"rule_type": "PERCENT", "percentage": "12.5", "reason": "Ошибочно выбран оклад"}
        for user in (self.director, self.trainer_user):
            self.assertEqual(self.client_for(user).post(url, body, format="json").status_code, 403)
        acc = self.client_for(self.accountant)
        self.assertEqual(acc.post(url, {"rule_type": "PERCENT"}, format="json").status_code, 400)  # без причины
        r = acc.post(url, body, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual((r.json()["rule"]["rule_type"], r.json()["rule"]["percentage"]), ("PERCENT", "12.50"))
        profile = acc.get(f"{API}/salary-profiles/{self.profile_.pk}/").json()
        self.assertEqual(profile["salary_type"], "PERCENT")
        self.assertTrue(profile["rules"][0]["usage"]["can_correct"])

    def test_used_rule_offers_replace(self):
        approve_payroll(self.calc(MONTH), self.director)
        acc = self.client_for(self.accountant)
        rule = acc.get(f"{API}/salary-rules/{self.wrong.pk}/").json()
        self.assertEqual((rule["usage"]["can_correct"], rule["usage"]["used_until"]), (False, "2026-09-30"))
        r = acc.post(f"{API}/salary-rules/{self.wrong.pk}/correct/", {"amount": "1", "reason": "x"}, format="json")
        self.assertEqual((r.status_code, r.json()["code"]), (400, "rule_used"))
        r = acc.post(f"{API}/salary-rules/{self.wrong.pk}/replace/",
                     {"effective_from": "2026-10-01", "rule_type": "PERCENT", "percentage": "10",
                      "reason": "Нужен процент"}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(EmployeeSalaryProfile.objects.get().salary_type, "PERCENT")

    def test_overlapping_rule_cannot_be_created(self):
        r = self.client_for(self.accountant).post(f"{API}/salary-rules/", {
            "employee_profile": self.profile_.pk, "rule_type": "FIXED", "amount": "1000",
            "effective_from": "2026-06-01"}, format="json")
        self.assertEqual((r.status_code, r.json()["code"]), (400, "overlap"))
