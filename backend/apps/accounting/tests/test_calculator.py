"""Расчёт начислений: FIXED и PERCENT (процент от стоимости курса за
завершённый цикл) и пограничные случаи."""
from __future__ import annotations

import datetime as dt
from decimal import Decimal

from django.core.exceptions import ValidationError

from apps.academy.models import Lesson, TrainerAssignment
from apps.accounting.models import (
    CourseCycle,
    CoursePayrollSettings,
    CycleAccrual,
    EmployeeSalaryProfile,
    Payroll,
    PayrollLine,
    SalaryRule,
    SalaryType,
)
from apps.accounting.services import AccountingError
from apps.accounting.services.approval_service import approve_payroll, create_adjustment
from apps.accounting.services.cycles import sync_all
from apps.accounting.services.money import allocate_by_days, money
from apps.accounting.services.payroll_calculator import calculate_period
from apps.accounting.tests.base import FIRST, SECOND, D, AccountingFixture, day, make_user

R = SalaryRule.RuleType
M = SalaryRule.Method


def days(month, first, last):
    return [day(month, d) for d in range(first, last + 1)]


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



class PercentCycleTests(AccountingFixture):
    """Процент от стоимости курса: студенты × стоимость × процент / 100
    за каждый завершённый цикл (required_lessons проведённых уроков)."""

    def setUp(self):
        super().setUp()
        self.settings = self.course_settings(price="10000", lessons=12)
        self.p = self.profile(salary_type=SalaryType.PERCENT)
        self.rule(self.p, R.PERCENT, percentage=D("10"))
        self.students = [self.student(self.group_a) for _ in range(10)]

    def percent_lines(self, payroll):
        return list(payroll.lines.filter(line_type=PayrollLine.LineType.PERCENT))

    def test_completed_cycle_accrues_by_formula(self):
        self.lessons(self.group_a, days(9, 1, 12))
        payroll = self.calc(FIRST)
        line = payroll.lines.get()
        # 10 студентов × 10 000 × 10 % = 10 000
        self.assertEqual(line.amount, D("10000.00"))
        self.assertEqual((line.quantity, line.rate, line.percentage, line.base_amount),
                         (D("10"), D("10000"), D("10"), D("100000.00")))
        self.assertEqual(payroll.active_students, 10)
        accrual = CycleAccrual.objects.get()
        self.assertEqual((accrual.lessons, accrual.completed_on, accrual.student_count, accrual.course_price,
                          accrual.percentage, accrual.amount),
                         (12, day(9, 12), 10, D("10000"), D("10"), D("10000.00")))
        self.assertEqual(self.calc(SECOND).total_accrued, D("0"))

    def test_completion_date_picks_the_half_of_month(self):
        self.lessons(self.group_a, days(9, 4, 15))  # 12-й урок 15-го → первая половина
        self.lessons(self.group_b, days(9, 5, 16))  # 12-й урок 16-го → вторая половина
        for _ in range(5):
            self.student(self.group_b)
        self.assertEqual(self.calc(FIRST).total_accrued, D("10000.00"))
        self.assertEqual(self.calc(SECOND).total_accrued, D("5000.00"))

    def test_completion_date_is_last_lesson_not_group_status(self):
        self.lessons(self.group_a, days(9, 1, 11))
        self.lessons(self.group_a, [day(9, 20)])
        self.group_a.status = "completed"
        self.group_a.save()
        self.assertEqual(self.calc(FIRST).total_accrued, D("0"))
        self.assertEqual(self.calc(SECOND).total_accrued, D("10000.00"))
        self.assertEqual(CourseCycle.objects.get(status="COMPLETED").completed_on, day(9, 20))

    def test_unfinished_cycle_is_not_accrued_and_listed_separately(self):
        self.lessons(self.group_a, days(9, 1, 11))
        payroll = self.calc(FIRST)
        self.assertEqual(payroll.total_accrued, D("0"))
        self.assertTrue(any("нет завершённых циклов" in w for w in payroll.warnings))
        open_cycle = CourseCycle.objects.get(group=self.group_a)
        self.assertEqual((open_cycle.status, open_cycle.lessons_done, open_cycle.required_lessons),
                         ("IN_PROGRESS", 11, 12))

    def test_only_completed_lessons_count(self):
        self.lessons(self.group_a, days(9, 1, 11))
        self.lessons(self.group_a, [day(9, 12)], status=Lesson.Status.CANCELLED)
        self.lessons(self.group_a, [day(9, 13)], status=Lesson.Status.SCHEDULED)
        self.assertEqual(self.calc(FIRST).total_accrued, D("0"))

    def test_course_price_per_course(self):
        robo = self.group("Robo 1", course=self.other_course)
        self.course_settings(self.other_course, price="11000", lessons=20)
        for _ in range(5):
            self.student(robo)
        self.lessons(robo, days(9, 1, 20))
        # Prog SOFT ещё не завершён; Robotics: 5 × 11 000 × 10 % = 5 500
        self.assertEqual(self.calc(SECOND).total_accrued, D("5500.00"))

    def test_payments_and_attendance_do_not_change_the_base(self):
        self.lessons(self.group_a, days(9, 1, 12))
        self.pay(self.students[0], 999, day(9, 3))
        baseline = self.calc(FIRST).total_accrued
        self.assertEqual(baseline, D("10000.00"))

    def test_cycle_is_accrued_only_once(self):
        self.lessons(self.group_a, days(9, 1, 12))
        self.calc(FIRST)
        self.calc(FIRST)
        calculate_period(self.period(), self.accountant)
        self.assertEqual(CycleAccrual.objects.count(), 1)
        self.assertEqual(PayrollLine.objects.filter(line_type="PERCENT").count(), 1)
        approve_payroll(Payroll.objects.get(period__period_type=FIRST), self.director)
        # Следующие периоды этот цикл не получают.
        self.assertEqual(self.calc(SECOND).total_accrued, D("0"))
        self.assertEqual(self.calc(FIRST, year_month=(2026, 10)).total_accrued, D("0"))
        self.assertEqual(CycleAccrual.objects.count(), 1)

    def test_settings_change_does_not_touch_completed_cycles(self):
        self.lessons(self.group_a, days(9, 1, 12))
        approved = approve_payroll(self.calc(FIRST), self.director)
        self.settings.required_lessons = 20
        self.settings.price_per_student = D("15000")
        self.settings.save()
        self.lessons(self.group_a, days(9, 13, 30))  # ещё 18 уроков — меньше новых 20
        sync_all()
        done = CourseCycle.objects.get(status="COMPLETED")
        self.assertEqual((done.required_lessons, done.course_price, done.student_count), (12, D("10000"), 10))
        current = CourseCycle.objects.get(status="IN_PROGRESS", group=self.group_a)
        self.assertEqual((current.number, current.lessons_done, current.required_lessons), (2, 18, 20))
        approved.refresh_from_db()
        self.assertEqual(approved.total_accrued, D("10000.00"))
        self.assertEqual(self.calc(SECOND).total_accrued, D("0"))

    def test_consecutive_cycles(self):
        self.lessons(self.group_a, days(9, 1, 24))
        self.assertEqual(self.calc(FIRST).total_accrued, D("10000.00"))   # 12-й урок 12.09
        self.assertEqual(self.calc(SECOND).total_accrued, D("10000.00"))  # 24-й урок 24.09
        self.assertEqual(sorted(CourseCycle.objects.filter(status="COMPLETED").values_list("number", flat=True)), [1, 2])

    def test_lessons_before_tracking_start_are_ignored(self):
        self.settings.count_lessons_from = day(9, 5)
        self.settings.save()
        self.lessons(self.group_a, days(9, 1, 15))  # с 5-го только 11 уроков
        self.assertEqual(self.calc(FIRST).total_accrued, D("0"))

    def test_student_count_rules(self):
        self.lessons(self.group_a, days(9, 1, 12))
        self.leave(self.students[0], day(9, 10))
        self.assertEqual(self.calc(FIRST).lines.get().quantity, D("9"))  # на дату завершения
        self.settings.student_count_rule = CoursePayrollSettings.StudentCountRule.DURING_CYCLE
        self.settings.save()
        self.lessons(self.group_a, days(9, 13, 24))
        sync_all()
        second = CourseCycle.objects.get(number=2, group=self.group_a)
        # Во втором цикле ушедший студент уже ни дня не был активен.
        self.assertEqual(second.student_count, 9)
        self.assertEqual(CourseCycle.objects.get(number=1, group=self.group_a).student_count, 9)

    def test_during_cycle_rule_counts_students_who_left(self):
        self.settings.student_count_rule = CoursePayrollSettings.StudentCountRule.DURING_CYCLE
        self.settings.save()
        self.lessons(self.group_a, days(9, 1, 12))
        self.leave(self.students[0], day(9, 10))
        self.assertEqual(self.calc(FIRST).lines.get().quantity, D("10"))

    def test_trainer_on_completion_date_gets_the_cycle(self):
        TrainerAssignment.objects.filter(group=self.group_a).update(end_date=day(9, 10))
        self.lessons(self.group_a, days(9, 1, 12))
        self.assertEqual(self.calc(FIRST).total_accrued, D("0"))

    def test_cycle_marked_late_in_an_approved_period_is_not_lost(self):
        approve_payroll(self.calc(FIRST), self.director)  # циклов ещё нет
        self.lessons(self.group_a, days(9, 1, 12))  # уроки отметили задним числом
        line = self.calc(SECOND).lines.get()
        self.assertEqual(line.amount, D("10000.00"))
        self.assertTrue(line.metadata["late"])

    def test_fixed_salary_ignores_cycles(self):
        manager = make_user("manager")
        from apps.users.models import Teacher

        Teacher.objects.create(user=manager)
        fixed = self.profile(manager, SalaryType.FIXED)
        self.rule(fixed, R.FIXED, amount=D("30000"))
        self.lessons(self.group_a, days(9, 1, 12))
        payroll = self.calc(FIRST, manager)
        self.assertEqual([l.line_type for l in payroll.lines.all()], ["FIXED"])
        self.assertEqual(payroll.total_accrued, D("15000.00"))
        self.assertFalse(CycleAccrual.objects.filter(employee=manager).exists())

    def test_rule_scoped_to_program(self):
        robo = self.group("Robo 1", course=self.other_course)
        self.course_settings(self.other_course, price="11000", lessons=12)
        self.student(robo)
        self.p.rules.update(program=self.other_course)
        self.lessons(self.group_a, days(9, 1, 12))
        self.lessons(robo, days(9, 1, 12))
        self.assertEqual(self.calc(FIRST).total_accrued, D("1100.00"))


class RulesTests(AccountingFixture):
    def setUp(self):
        super().setUp()
        self.p = self.profile(salary_type=SalaryType.FIXED)

    def test_only_two_salary_types(self):
        self.assertEqual([t.value for t in SalaryRule.ACTIVE_TYPES], ["FIXED", "PERCENT"])
        profile = EmployeeSalaryProfile(employee=make_user("x"), salary_type="COMBINED", effective_from=day(1, 1))
        with self.assertRaises(ValidationError):
            profile.full_clean()
        for legacy in ("PER_STUDENT", "REVENUE_PERCENT", "PER_GROUP", "BONUS"):
            with self.assertRaises(ValidationError):
                self.rule(self.p, legacy, amount=D("1"), percentage=D("1"))

    def test_rule_must_match_profile_type(self):
        with self.assertRaises(ValidationError):
            self.rule(self.p, R.PERCENT, percentage=D("10"))

    def test_legacy_profile_is_an_error(self):
        legacy = EmployeeSalaryProfile.objects.create(employee=make_user("old"), salary_type="COMBINED",
                                                      effective_from=day(1, 1))
        payroll = self.calc(FIRST, legacy.employee)
        self.assertTrue(any("больше не поддерживается" in e for e in payroll.errors))

    def test_missing_rule_is_an_error(self):
        payroll = self.calc(FIRST)
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

    def test_rule_version_change(self):
        from apps.accounting.services.salary_rules import new_version

        old = self.rule(self.p, R.FIXED, amount=D("20000"))
        new_version(old, actor=self.accountant, changes={"amount": D("30000"), "effective_from": day(9, 16)})
        old.refresh_from_db()
        self.assertEqual(old.effective_to, day(9, 15))
        self.assertEqual(self.calc(FIRST).total_accrued, D("10000.00"))
        self.assertEqual(self.calc(SECOND).total_accrued, D("15000.00"))

    def test_rounding(self):
        self.rule(self.p, R.FIXED, amount=D("10000"), method=M.PRORATE_DAYS)
        self.assertEqual(self.calc(FIRST, year_month=(2026, 10)).total_accrued, D("4838.71"))
        self.assertEqual(money(D("0.005")), D("0.01"))
        parts = [allocate_by_days(D("100"), dt.date(2026, 1, 1), dt.date(2026, 1, 3), d, d)
                 for d in (dt.date(2026, 1, 1), dt.date(2026, 1, 2), dt.date(2026, 1, 3))]
        self.assertEqual(sum(parts), D("100.00"))

    def test_recalculating_draft_does_not_duplicate(self):
        rule = self.rule(self.p, R.FIXED, amount=D("20000"))
        first = self.calc(FIRST)
        from apps.accounting.services.salary_rules import new_version

        new_version(rule, actor=self.accountant, changes={"amount": D("22000"), "effective_from": day(9, 2)})
        again = self.calc(FIRST)
        self.assertEqual(first.pk, again.pk)
        self.assertEqual(Payroll.objects.count(), 1)
        self.assertEqual(again.lines.count(), 2)

    def test_approved_payroll_is_not_recalculated(self):
        self.rule(self.p, R.FIXED, amount=D("20000"))
        approve_payroll(self.calc(FIRST), self.director)
        with self.assertRaises(AccountingError):
            self.calc(FIRST)

    def test_mass_calculation_reports_every_employee(self):
        self.rule(self.p, R.FIXED, amount=D("20000"))
        broken = make_user("broken", "assistant")
        self.profile(broken)
        result = calculate_period(self.period(), self.accountant)
        by_user = {p.employee_id: p for p in result["calculated"]}
        self.assertEqual(len(by_user), 2)
        self.assertTrue(by_user[broken.pk].errors)
        self.assertFalse(by_user[self.trainer_user.pk].errors)

    def test_adjustments_are_the_way_to_add_bonuses(self):
        self.rule(self.p, R.FIXED, amount=D("20000"))
        payroll = self.calc(FIRST)
        create_adjustment(payroll, kind="BONUS", amount=D("1500"), reason="олимпиада", actor=self.accountant)
        create_adjustment(payroll, kind="DEDUCTION", amount=D("500"), reason="штраф", actor=self.accountant)
        payroll.refresh_from_db()
        self.assertEqual(payroll.amount_due, D("11000.00"))

    def test_descriptions_have_no_exponent_notation(self):
        self.rule(self.p, R.FIXED, amount=D("20000"))
        description = self.calc(FIRST).lines.get().description
        self.assertIn("50% месячного оклада", description)
        self.assertNotIn("E+", description)
