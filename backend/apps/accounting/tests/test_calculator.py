"""Расчёт начислений: все схемы оплаты и пограничные случаи (ТЗ §12)."""
from __future__ import annotations

import datetime as dt
from decimal import Decimal

from apps.academy.models import TrainerAssignment
from apps.accounting.models import Payroll, PayrollLine, SalaryRule, SalaryType
from apps.accounting.services import AccountingError
from apps.accounting.services.approval_service import approve_payroll, create_adjustment
from apps.accounting.services.money import allocate_by_days, money
from apps.accounting.services.payroll_calculator import calculate_period
from apps.accounting.tests.base import FIRST, SECOND, D, AccountingFixture, day, make_user

R = SalaryRule.RuleType
M = SalaryRule.Method


class FixedSalaryTests(AccountingFixture):
    def setUp(self):
        super().setUp()
        self.manager = make_user("manager", "assistant")
        self.p = self.profile(self.manager, SalaryType.FIXED)

    def test_full_month_is_both_halves(self):
        self.rule(self.p, R.FIXED, amount=D("30000"))
        first, second = self.calc(FIRST, self.manager), self.calc(SECOND, self.manager)
        self.assertEqual(first.total_accrued, D("15000.00"))
        self.assertEqual(second.total_accrued, D("15000.00"))
        self.assertEqual(first.total_accrued + second.total_accrued, D("30000.00"))

    def test_half_month_custom_split(self):
        self.rule(self.p, R.FIXED, amount=D("30000"), first_half_share=D("40"))
        self.assertEqual(self.calc(FIRST, self.manager).total_accrued, D("12000.00"))
        self.assertEqual(self.calc(SECOND, self.manager).total_accrued, D("18000.00"))

    def test_prorate_by_calendar_days(self):
        # Сентябрь — 30 дней: первая половина 15/30, вторая 15/30.
        self.rule(self.p, R.FIXED, amount=D("30000"), method=M.PRORATE_DAYS)
        self.assertEqual(self.calc(FIRST, self.manager).total_accrued, D("15000.00"))
        # Октябрь — 31 день: 15/31 и 16/31, в сумме ровно оклад.
        a = self.calc(FIRST, self.manager, (2026, 10)).total_accrued
        b = self.calc(SECOND, self.manager, (2026, 10)).total_accrued
        self.assertEqual(a, money(D("30000") * 15 / 31))
        self.assertEqual(b, money(D("30000") * 16 / 31))

    def test_started_mid_period(self):
        self.p.effective_from = day(9, 6)
        self.p.save()
        self.rule(self.p, R.FIXED, amount=D("30000"), start=day(9, 6))
        # 10 из 15 дней первой половины, доля 50%.
        self.assertEqual(self.calc(FIRST, self.manager).total_accrued, D("10000.00"))


class RevenuePercentTests(AccountingFixture):
    def setUp(self):
        super().setUp()
        self.p = self.profile(salary_type=SalaryType.REVENUE_PERCENT)

    def test_single_student(self):
        self.rule(self.p, R.REVENUE_PERCENT, percentage=D("10"), group=self.group_a)
        self.pay(self.student(), 10000, day(9, 3))
        payroll = self.calc()
        self.assertEqual(payroll.total_accrued, D("1000.00"))
        line = payroll.lines.get()
        self.assertEqual(line.base_amount, D("10000.00"))
        self.assertEqual(line.percentage, D("10"))
        self.assertEqual(len(line.metadata["payments"]), 1)

    def test_group_of_ten(self):
        self.rule(self.p, R.REVENUE_PERCENT, percentage=D("10"), group=self.group_a)
        for _ in range(10):
            self.pay(self.student(), 10000, day(9, 5))
        payroll = self.calc()
        self.assertEqual(payroll.total_accrued, D("10000.00"))
        self.assertIn("Group A", payroll.lines.get().description)

    def test_only_payments_received_in_period(self):
        self.rule(self.p, R.REVENUE_PERCENT, percentage=D("10"))
        s = self.student()
        self.pay(s, 10000, day(9, 5))
        self.pay(s, 5000, day(9, 20))
        self.pay(s, 7000, day(8, 30))
        self.assertEqual(self.calc(FIRST).total_accrued, D("1000.00"))
        self.assertEqual(self.calc(SECOND).total_accrued, D("500.00"))

    def test_refund_of_earlier_payment(self):
        self.rule(self.p, R.REVENUE_PERCENT, percentage=D("10"))
        s = self.student()
        original = self.pay(s, 10000, day(9, 5))
        first = self.calc(FIRST)
        approve_payroll(first, self.director)
        self.refund(original, 4000, day(9, 20))
        second = self.calc(SECOND)
        line = second.lines.get(line_type=PayrollLine.LineType.REFUND_CORRECTION)
        self.assertEqual(line.amount, D("-400.00"))
        self.assertEqual(line.metadata["original_payment_id"], original.pk)
        self.assertEqual(line.metadata["original_payroll_id"], first.pk)
        # Утверждённое начисление первой половины не изменилось.
        first.refresh_from_db()
        self.assertEqual(first.total_accrued, D("1000.00"))

    def test_refund_of_payment_outside_scope_is_not_deducted(self):
        self.rule(self.p, R.REVENUE_PERCENT, percentage=D("10"), group=self.group_a)
        other = self.student(self.group_b)
        original = self.pay(other, 10000, day(8, 5))
        self.refund(original, 10000, day(9, 3))
        self.assertEqual(self.calc().lines.count(), 0)

    def test_refund_policy_ignore(self):
        self.rule(self.p, R.REVENUE_PERCENT, percentage=D("10"), refund_policy=SalaryRule.RefundPolicy.IGNORE)
        s = self.student()
        original = self.pay(s, 10000, day(8, 5))
        self.refund(original, 10000, day(9, 3))
        self.assertEqual(self.calc().total_accrued, D("0.00"))

    def test_multi_period_payment_counted_once_on_received_basis(self):
        self.rule(self.p, R.REVENUE_PERCENT, percentage=D("10"))
        s = self.student()
        self.pay(s, 30000, day(9, 2), service=(day(9, 1), day(11, 30)))
        totals = [self.calc(FIRST).total_accrued, self.calc(SECOND).total_accrued,
                  self.calc(FIRST, year_month=(2026, 10)).total_accrued]
        self.assertEqual(totals, [D("3000.00"), D("0.00"), D("0.00")])

    def test_multi_period_payment_allocated_by_days(self):
        self.rule(self.p, R.REVENUE_PERCENT, percentage=D("10"), revenue_basis=SalaryRule.RevenueBasis.ALLOCATED)
        s = self.student()
        # 91 день обучения (сентябрь–ноябрь), 9100 сом → 100 сом в день.
        self.pay(s, 9100, day(9, 2), service=(day(9, 1), day(11, 30)))
        periods = [((2026, 9), FIRST), ((2026, 9), SECOND), ((2026, 10), FIRST), ((2026, 10), SECOND),
                   ((2026, 11), FIRST), ((2026, 11), SECOND)]
        bases = []
        for ym, half in periods:
            payroll = self.calc(half, year_month=ym)
            bases.append(sum((l.base_amount for l in payroll.lines.all()), D("0")))
        self.assertEqual(bases, [D("1500.00"), D("1500.00"), D("1500.00"), D("1600.00"), D("1500.00"), D("1500.00")])
        self.assertEqual(sum(bases), D("9100.00"))

    def test_trainer_change_attributes_payment_to_responsible_trainer(self):
        self.rule(self.p, R.REVENUE_PERCENT, percentage=D("10"))
        s = self.student()
        TrainerAssignment.objects.filter(group=self.group_a).update(end_date=day(9, 10))
        self.pay(s, 10000, day(9, 5))
        self.pay(s, 20000, day(9, 12))
        self.assertEqual(self.calc().total_accrued, D("1000.00"))

    def test_prepayment_before_group_start_goes_to_first_trainer(self):
        self.rule(self.p, R.REVENUE_PERCENT, percentage=D("10"))
        new_group = self.group("New", start=day(9, 10))
        self.pay(self.student(new_group), 10000, day(9, 2), service=(day(9, 10), day(10, 9)))
        self.assertEqual(self.calc().total_accrued, D("1000.00"))

    def test_same_payment_not_counted_twice_by_two_rules(self):
        self.rule(self.p, R.REVENUE_PERCENT, percentage=D("10"), group=self.group_a)
        self.rule(self.p, R.REVENUE_PERCENT, percentage=D("10"), program=self.course)
        self.pay(self.student(), 10000, day(9, 5))
        payroll = self.calc()
        self.assertEqual(payroll.total_accrued, D("1000.00"))
        self.assertTrue(any("уже учтены" in w for w in payroll.warnings))

    def test_voided_payment_is_excluded(self):
        from apps.accounting.services.student_payments import void_student_payment

        self.rule(self.p, R.REVENUE_PERCENT, percentage=D("10"))
        payment = self.pay(self.student(), 10000, day(9, 5))
        void_student_payment(payment, actor=self.accountant, reason="ошибка")
        self.assertEqual(self.calc().total_accrued, D("0.00"))


class PerStudentTests(AccountingFixture):
    """Программист: 11 000 сом за активного студента в месяц."""

    RATE = D("11000")

    def setUp(self):
        super().setUp()
        self.p = self.profile(salary_type=SalaryType.PER_STUDENT)

    def month_total(self):
        return self.calc(FIRST).total_accrued + self.calc(SECOND).total_accrued

    def test_one_active_student(self):
        self.rule(self.p, R.PER_STUDENT, amount=self.RATE)
        self.student()
        self.assertEqual(self.month_total(), D("11000.00"))
        self.assertEqual(Payroll.objects.get(period__period_type=FIRST).active_students, 1)

    def test_ten_active_students(self):
        self.rule(self.p, R.PER_STUDENT, amount=self.RATE)
        for _ in range(10):
            self.student()
        self.assertEqual(self.month_total(), D("110000.00"))

    def test_count_changes_during_month_is_prorated(self):
        # Сентябрь — 30 дней: A весь месяц, B с 16-го (15 дней) → 11000 × 1.5.
        self.rule(self.p, R.PER_STUDENT, amount=self.RATE)
        self.student()
        self.student(enrolled=day(9, 16))
        first = self.calc(FIRST)
        second = self.calc(SECOND)
        self.assertEqual(first.total_accrued, D("5500.00"))
        self.assertEqual(second.total_accrued, D("11000.00"))
        self.assertEqual(first.total_accrued + second.total_accrued, D("16500.00"))

    def test_student_who_left_counts_until_departure(self):
        self.rule(self.p, R.PER_STUDENT, amount=self.RATE)
        s = self.student()
        self.leave(s, day(9, 11))  # активен 1–10 сентября
        self.assertEqual(self.calc(FIRST).total_accrued, money(self.RATE * 10 / 30))
        self.assertEqual(self.calc(SECOND).total_accrued, D("0.00"))

    def test_student_in_several_groups_counted_once(self):
        self.rule(self.p, R.PER_STUDENT, amount=self.RATE, group=self.group_a)
        self.rule(self.p, R.PER_STUDENT, amount=self.RATE, group=self.group_b)
        s = self.student(self.group_a)
        self.transfer(s, self.group_b, day(9, 8))
        payroll = self.calc(FIRST)
        # 15 студенто-дней одного студента, несмотря на две группы и два правила.
        self.assertEqual(payroll.total_accrued, money(self.RATE * 15 / 30))
        self.assertEqual(payroll.active_students, 1)

    def test_overlapping_program_and_group_rules_do_not_double_count(self):
        self.rule(self.p, R.PER_STUDENT, amount=self.RATE, group=self.group_a)
        self.rule(self.p, R.PER_STUDENT, amount=self.RATE, program=self.course)
        self.student(self.group_a)
        payroll = self.calc(FIRST)
        self.assertEqual(payroll.total_accrued, D("5500.00"))
        self.assertTrue(any("уже учтены" in w for w in payroll.warnings))

    def test_rate_only_for_program(self):
        robo = self.group("Robo 1", course=self.other_course)
        self.rule(self.p, R.PER_STUDENT, amount=self.RATE, program=self.course)
        self.student(self.group_a)
        self.student(robo)
        self.assertEqual(self.calc(FIRST).total_accrued, D("5500.00"))

    def test_snapshot_mode(self):
        self.rule(self.p, R.PER_STUDENT, amount=self.RATE, method=M.SNAPSHOT)
        self.student()
        gone = self.student()
        self.leave(gone, day(9, 10))
        self.assertEqual(self.calc(FIRST).total_accrued, D("5500.00"))

    def test_paused_student_not_counted(self):
        from apps.academy.models import Student, StudentStatusEvent

        self.rule(self.p, R.PER_STUDENT, amount=self.RATE)
        s = self.student()
        StudentStatusEvent.objects.create(
            student=s, event_type=StudentStatusEvent.EventType.PAUSED, reason=StudentStatusEvent.Reason.HEALTH,
            previous_status=Student.Status.ACTIVE, group=s.group, event_date=day(9, 6),
        )
        Student.objects.filter(pk=s.pk).update(status=Student.Status.PAUSED, is_active=False)
        self.assertEqual(self.calc(FIRST).total_accrued, money(self.RATE * 5 / 30))

    def test_no_students_gives_warning(self):
        self.rule(self.p, R.PER_STUDENT, amount=self.RATE)
        payroll = self.calc(FIRST)
        self.assertEqual(payroll.total_accrued, D("0.00"))
        self.assertTrue(any("нет данных об активных студентах" in w for w in payroll.warnings))


class PerGroupTests(AccountingFixture):
    def setUp(self):
        super().setUp()
        self.p = self.profile(salary_type=SalaryType.PER_GROUP)

    def test_two_groups(self):
        self.rule(self.p, R.PER_GROUP, amount=D("10000"))
        total = self.calc(FIRST).total_accrued + self.calc(SECOND).total_accrued
        self.assertEqual(total, D("20000.00"))
        self.assertEqual(Payroll.objects.get(period__period_type=FIRST).lines.count(), 2)

    def test_trainer_replaced_mid_month(self):
        self.rule(self.p, R.PER_GROUP, amount=D("10000"), group=self.group_a)
        TrainerAssignment.objects.filter(group=self.group_a).update(end_date=day(9, 11))
        self.assertEqual(self.calc(FIRST).total_accrued, money(D("10000") * 10 / 30))
        self.assertEqual(self.calc(SECOND).total_accrued, D("0.00"))

    def test_group_started_mid_month(self):
        late = self.group("Late", start=day(9, 21))
        self.rule(self.p, R.PER_GROUP, amount=D("9000"), group=late)
        self.assertEqual(self.calc(SECOND).total_accrued, money(D("9000") * 10 / 30))


class CombinedAndRulesTests(AccountingFixture):
    def setUp(self):
        super().setUp()
        self.p = self.profile(salary_type=SalaryType.COMBINED)

    def test_combined_scheme(self):
        self.rule(self.p, R.FIXED, amount=D("20000"))
        self.rule(self.p, R.REVENUE_PERCENT, percentage=D("5"), group=self.group_a)
        self.rule(self.p, R.PER_GROUP, amount=D("4000"), group=self.group_b)
        self.rule(self.p, R.BONUS, amount=D("1500"), start=day(9, 10), description="Олимпиада")
        self.pay(self.student(), 20000, day(9, 3))
        payroll = self.calc(FIRST)
        types = sorted(payroll.lines.values_list("line_type", flat=True))
        self.assertEqual(types, sorted(["FIXED", "REVENUE_PERCENT", "PER_GROUP", "BONUS"]))
        self.assertEqual(payroll.total_accrued, D("10000") + D("1000") + D("2000") + D("1500"))
        create_adjustment(payroll, kind="DEDUCTION", amount=D("500"), reason="штраф", actor=self.accountant)
        payroll.refresh_from_db()
        self.assertEqual(payroll.total_adjustments, D("-500.00"))
        self.assertEqual(payroll.amount_due, D("14000.00"))

    def test_bonus_only_in_its_period(self):
        self.rule(self.p, R.BONUS, amount=D("1500"), start=day(9, 20))
        self.assertEqual(self.calc(FIRST).total_accrued, D("0.00"))
        self.assertEqual(self.calc(SECOND).total_accrued, D("1500.00"))

    def test_missing_rule_is_an_error(self):
        payroll = self.calc(FIRST)
        self.assertTrue(payroll.errors)
        self.assertIn("Не настроена ставка", payroll.errors[0])
        with self.assertRaises(AccountingError):
            approve_payroll(payroll, self.director)

    def test_overlapping_rules_block_approval(self):
        self.rule(self.p, R.FIXED, amount=D("20000"))
        self.rule(self.p, R.FIXED, amount=D("25000"), start=day(9, 1))
        payroll = self.calc(FIRST)
        self.assertTrue(any("Пересекающиеся" in e for e in payroll.errors))
        with self.assertRaises(AccountingError):
            approve_payroll(payroll, self.director)

    def test_rule_version_change_does_not_overlap(self):
        from apps.accounting.services.salary_rules import new_version

        old = self.rule(self.p, R.FIXED, amount=D("20000"))
        new_version(old, actor=self.accountant, changes={"amount": D("30000"), "effective_from": day(9, 16)})
        old.refresh_from_db()
        self.assertEqual(old.effective_to, day(9, 15))
        self.assertEqual(self.calc(FIRST).total_accrued, D("10000.00"))
        self.assertEqual(self.calc(SECOND).total_accrued, D("15000.00"))

    def test_rounding(self):
        self.rule(self.p, R.FIXED, amount=D("10000"), method=M.PRORATE_DAYS)
        # 10000 × 15 / 31 = 4838.709… → 4838.71 (ROUND_HALF_UP)
        self.assertEqual(self.calc(FIRST, year_month=(2026, 10)).total_accrued, D("4838.71"))
        self.assertEqual(money(D("0.005")), D("0.01"))
        parts = [allocate_by_days(D("100"), dt.date(2026, 1, 1), dt.date(2026, 1, 3), d, d)
                 for d in (dt.date(2026, 1, 1), dt.date(2026, 1, 2), dt.date(2026, 1, 3))]
        self.assertEqual(sum(parts), D("100.00"))

    def test_recalculating_draft_does_not_duplicate(self):
        self.rule(self.p, R.FIXED, amount=D("20000"))
        first = self.calc(FIRST)
        self.rule(self.p, R.BONUS, amount=D("1000"), start=day(9, 2))
        again = self.calc(FIRST)
        self.assertEqual(first.pk, again.pk)
        self.assertEqual(Payroll.objects.count(), 1)
        self.assertEqual(again.lines.count(), 2)
        self.assertEqual(again.total_accrued, D("11000.00"))

    def test_approved_payroll_is_not_recalculated(self):
        self.rule(self.p, R.FIXED, amount=D("20000"))
        approve_payroll(self.calc(FIRST), self.director)
        with self.assertRaises(AccountingError):
            self.calc(FIRST)

    def test_mass_calculation_reports_every_employee(self):
        self.rule(self.p, R.FIXED, amount=D("20000"))
        broken = make_user("broken", "assistant")
        self.profile(broken)  # без правил
        result = calculate_period(self.period(), self.accountant)
        self.assertEqual(len(result["calculated"]), 2)
        by_user = {p.employee_id: p for p in result["calculated"]}
        self.assertTrue(by_user[broken.pk].errors)
        self.assertFalse(by_user[self.trainer_user.pk].errors)

    def test_big_change_warning(self):
        self.rule(self.p, R.FIXED, amount=D("20000"))
        approve_payroll(self.calc(FIRST), self.director)
        self.rule(self.p, R.BONUS, amount=D("50000"), start=day(9, 20))
        payroll = self.calc(SECOND)
        self.assertTrue(any("существенно отличается" in w for w in payroll.warnings))
