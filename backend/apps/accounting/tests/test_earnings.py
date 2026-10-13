"""Заработано на текущий момент: по фактически проведённым урокам, той же
формулой, что и официальное начисление; отдельно от официального начисления
и задолженности; одинаково у сотрудника и бухгалтера."""
from __future__ import annotations

import datetime as dt
from unittest import mock

from apps.academy.models import GroupTeacher, Lesson
from apps.accounting.models import CycleAccrual, Payroll, PayrollPayment, SalaryRule, SalaryType
from apps.accounting.services import deductions as ded
from apps.accounting.services import earnings
from apps.accounting.services import payout_plans as pp
from apps.accounting.services.approval_service import approve_payroll
from apps.accounting.services.payment_service import register_payment
from apps.accounting.tests.base import FIRST, D, AccountingFixture, day, make_user
from apps.accounting.tests.test_subject_cycles import SubjectFixture, days
from apps.users.models import Teacher, User

R = SalaryRule.RuleType
API = "/api/v1/accounting"
TODAY = day(10, 10)
OCT = (2026, 10)


class Fixture(AccountingFixture):
    """10 студентов × 10 000 сом × 10 %, блок — 12 уроков: полный блок = 10 000."""

    def setUp(self):
        super().setUp()
        self.course_settings(price="10000", lessons=12, start=None)
        self.rule(self.profile(salary_type=SalaryType.PERCENT), R.PERCENT, percentage=D("10"))
        for _ in range(10):
            self.student(self.group_a)

    def teach(self, dates, *, teacher=None):
        program = GroupTeacher.objects.filter(group=self.group_a, teacher=teacher or self.trainer).first()
        with self.captureOnCommitCallbacks(execute=True):
            for d in dates:
                Lesson.objects.create(group=self.group_a, group_teacher=program, teacher=program.teacher,
                                      subject=self.python, lesson_number=1000 + Lesson.objects.count(), date=d,
                                      start_time=dt.time(10), end_time=dt.time(11), status=Lesson.Status.COMPLETED)

    def earned(self, user=None):
        return earnings.summary(user or self.trainer_user, today=TODAY)


class OpenBlockTests(Fixture):
    def test_nine_of_twelve_lessons_earned_for_work_done(self):
        self.teach(days(10, 1, 9))
        data = self.earned()
        self.assertEqual(data["earned"]["gross"], D("7500.00"))  # 10 × 10 000 × 10 % × 9/12
        [row] = data["items"]
        self.assertEqual((row["source"], row["lessons_taught"], row["required_lessons"]), ("OPEN_BLOCK", 9, 12))
        self.assertEqual((data["official"]["gross"], data["company_owes"]), (D("0"), D("0")))
        self.assertEqual(data["difference"], D("7500.00"))
        self.assertEqual(data["difference_reasons"][0]["source"], "OPEN_BLOCK")
        # Ничего не создано: ни начисления, ни расчёта, ни платежа.
        self.assertFalse(CycleAccrual.objects.exists())
        self.assertFalse(Payroll.objects.exists())
        self.assertFalse(PayrollPayment.objects.exists())

    def test_completed_block_becomes_official_without_double_counting(self):
        self.teach(days(10, 1, 12))
        data = self.earned()
        self.assertEqual(data["earned"]["gross"], D("10000.00"))
        self.assertEqual([r["source"] for r in data["items"]], ["ACCRUAL_PENDING"])
        self.assertEqual(data["official"]["gross"], D("0"))
        payroll = self.calc(FIRST, year_month=OCT)
        data = self.earned()
        self.assertEqual((data["earned"]["gross"], [r["source"] for r in data["items"]]),
                         (D("10000.00"), ["PAYROLL_DRAFT"]))
        approve_payroll(payroll, self.director)
        data = self.earned()
        self.assertEqual((data["earned"]["gross"], data["official"]["gross"], data["company_owes"]),
                         (D("10000.00"), D("10000.00"), D("10000.00")))
        self.assertEqual(data["difference"], D("0"))
        # Следующий блок — снова только по проведённым урокам, отдельно от первого.
        self.teach(days(10, 13, 15))
        data = self.earned()
        self.assertEqual(data["earned"]["gross"], D("12500.00"))  # 10 000 + 3/12 × 10 000
        self.assertEqual(data["official"]["gross"], D("10000.00"))

    def test_several_trainers_by_actual_lessons(self):
        user = make_user("second")
        second = Teacher.objects.create(user=user)
        GroupTeacher.objects.create(group=self.group_a, teacher=second, subject=self.python)
        self.rule(self.profile(user, SalaryType.PERCENT), R.PERCENT, percentage=D("10"))
        self.teach(days(10, 1, 5))
        self.teach(days(10, 6, 9), teacher=second)
        self.assertEqual(self.earned()["earned"]["gross"], D("4166.67"))  # 5/12
        self.assertEqual(self.earned(user)["earned"]["gross"], D("3333.33"))  # 4/12

    def test_tax_once_per_month_and_never_negative(self):
        ded.create_rule(actor=self.accountant, name="Налог", kind="TAX", amount=D("3000"), frequency="MONTHLY",
                        scope="EMPLOYEE", employee=self.trainer_user, effective_from=day(1, 1))
        ded.create_rule(actor=self.accountant, name="Взнос", kind="OTHER", amount=D("500"), frequency="MONTHLY",
                        scope="EMPLOYEE", employee=self.trainer_user, effective_from=day(1, 1))
        self.teach(days(10, 1, 12))
        approve_payroll(self.calc(FIRST, year_month=OCT), self.director)  # 10 000 − 3 500
        self.teach(days(10, 13, 21))  # + незавершённый блок 9/12 в том же месяце
        data = self.earned()
        self.assertEqual(data["earned"]["gross"], D("17500.00"))
        self.assertEqual((data["earned"]["tax"], data["earned"]["other_deductions"]), (D("3000.00"), D("500.00")))
        self.assertEqual(data["earned"]["net"], D("14000.00"))
        self.assertEqual((data["official"]["tax"], data["official"]["other_deductions"]), (D("3000.00"), D("500.00")))
        self.assertEqual(data["company_owes"], D("6500.00"))

    def test_small_earning_capped_by_deduction(self):
        ded.create_rule(actor=self.accountant, name="Налог", kind="TAX", amount=D("3000"), frequency="MONTHLY",
                        scope="EMPLOYEE", employee=self.trainer_user, effective_from=day(1, 1))
        self.teach(days(10, 1, 2))  # 2/12 → 1666.67
        data = self.earned()
        self.assertEqual((data["earned"]["tax"], data["earned"]["net"]), (D("1666.67"), D("0.00")))
        [d] = data["deductions"]
        self.assertEqual(d["remaining"], D("1333.33"))

    def test_partial_payment_reduces_debt(self):
        ded.create_rule(actor=self.accountant, name="Налог", kind="TAX", amount=D("1000"), frequency="MONTHLY",
                        scope="EMPLOYEE", employee=self.trainer_user, effective_from=day(1, 1))
        self.teach(days(10, 1, 12))
        payroll = approve_payroll(self.calc(FIRST, year_month=OCT), self.director)
        register_payment(payroll, amount=D("4000"), payment_date=day(10, 15), actor=self.accountant)
        data = self.earned()
        self.assertEqual((data["paid"], data["company_owes"], data["earned_unpaid"]),
                         (D("4000.00"), D("5000.00"), D("5000.00")))

    def test_payout_plan_uses_only_official_amounts(self):
        self.teach(days(10, 1, 12))
        payroll = approve_payroll(self.calc(FIRST, year_month=OCT), self.director)
        self.teach(days(10, 13, 21))  # заработок по незавершённому блоку — не в план
        rows = pp.candidates(year=2026, month=10)
        self.assertEqual([(r["payroll"], r["available"]) for r in rows], [(payroll.pk, D("10000.00"))])
        self.assertEqual(self.earned()["earned"]["gross"], D("17500.00"))
        self.assertFalse(PayrollPayment.objects.exists())


class SubjectEarningsTests(SubjectFixture):
    def test_subjects_are_not_mixed(self):
        GroupTeacher.objects.filter(group=self.group_a, subject=self.english).update(teacher=self.trainer)
        self.teach(self.python, days(10, 1, 9))
        self.teach(self.english, days(10, 1, 6))
        self.teach(self.soft, days(10, 1, 3))  # чужой предмет — не у этого тренера
        data = earnings.summary(self.trainer_user, today=TODAY)
        rows = {r["subject_name"]: (r["lessons_taught"], r["gross"]) for r in data["items"]}
        self.assertEqual(rows, {"Python": (9, D("7500.00")), "English": (6, D("5000.00"))})
        soft_user = self.teachers[self.soft][0]
        soft = earnings.summary(soft_user, today=TODAY)
        self.assertEqual([(r["subject_name"], r["lessons_taught"]) for r in soft["items"]], [("Soft Skills", 3)])
        self.assertEqual(soft["earned"]["gross"], D("1250.00"))  # 10 × 10 000 × 5 % × 3/12


class SameNumbersTests(Fixture):
    def test_employee_and_accountant_see_the_same(self):
        ded.create_rule(actor=self.accountant, name="Налог", kind="TAX", amount=D("1000"), frequency="MONTHLY",
                        scope="EMPLOYEE", employee=self.trainer_user, effective_from=day(1, 1))
        self.teach(days(10, 1, 12))
        payroll = approve_payroll(self.calc(FIRST, year_month=OCT), self.director)
        register_payment(payroll, amount=D("2000"), payment_date=day(10, 15), actor=self.accountant)
        self.teach(days(10, 13, 21))
        with mock.patch("django.utils.timezone.localdate", return_value=TODAY):
            mine = self.client_for(self.trainer_user).get(f"{API}/my/salary/").json()["earnings"]
            detail = self.client_for(self.accountant).get(f"{API}/earnings/{self.trainer_user.pk}/").json()
            listing = self.client_for(self.director).get(f"{API}/earnings/").json()["results"]
        for key in ("earned", "official", "paid", "company_owes", "earned_unpaid", "next_payment_date", "difference"):
            self.assertEqual(mine[key], detail[key], key)
        row = next(r for r in listing if r["employee"] == self.trainer_user.pk)
        self.assertEqual(row["earned"], mine["earned"])
        self.assertEqual(mine["earned"], {"gross": "17500.00", "tax": "1000.00", "other_deductions": "0.00",
                                          "net": "16500.00"})
        self.assertEqual((mine["paid"], mine["company_owes"]), ("2000.00", "7000.00"))

    def test_access(self):
        self.assertEqual(self.client_for(self.trainer_user).get(f"{API}/earnings/").status_code, 403)
        other = make_user("other")
        self.assertEqual(self.client_for(self.trainer_user).get(f"{API}/earnings/{other.pk}/").status_code, 403)
        self.assertEqual(self.client_for(User.objects.get(username="buh")).get(f"{API}/earnings/").status_code, 200)
