"""«Моя зарплата»: налоги и удержания сотрудника — суммы до и после удержаний,
блок удержаний, предварительная зарплата без выдуманного налога, только свои
данные. Все цифры — из тех же записей, что у бухгалтерии."""
from __future__ import annotations

from unittest import mock

from apps.accounting.models import SalaryRule, SalaryType
from apps.accounting.services import deductions as ded
from apps.accounting.services.approval_service import approve_payroll
from apps.accounting.services.payment_service import register_payment
from apps.accounting.tests.base import FIRST, MONTH, SECOND, D, AccountingFixture, day, make_user
from apps.accounting.tests.test_subject_cycles import days
from apps.users.models import User

R = SalaryRule.RuleType
URL = "/api/v1/accounting/my/salary/"
OCT = (2026, 10)


class Fixture(AccountingFixture):
    def deduction(self, amount, employee, *, name="Налог", kind="TAX", start=day(1, 1)):
        return ded.create_rule(actor=self.accountant, name=name, kind=kind, amount=D(amount), frequency="MONTHLY",
                               scope="EMPLOYEE", employee=employee, effective_from=start)[0]

    def my(self, user, **params):
        response = self.client_for(user).get(URL, params)
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()


class FixedSalaryTests(Fixture):
    def setUp(self):
        super().setUp()
        self.emp = make_user("emp", User.Role.ASSISTANT)
        self.rule(self.profile(self.emp, SalaryType.FIXED), R.FIXED, amount=D("50000"))

    def test_without_deductions(self):
        approve_payroll(self.calc(MONTH, self.emp, OCT), self.director)
        data = self.my(self.emp)
        t = data["totals"]
        self.assertEqual((t["accrued"], t["deducted"], t["net"], t["paid"], t["due"]),
                         ("50000.00", "0.00", "50000.00", "0.00", "50000.00"))
        self.assertEqual(data["deductions"], [])

    def test_one_fixed_deduction_and_partial_payment(self):
        """Пример из задачи: 50 000 − 3 000 = 47 000; выплачено 20 000 → остаток 27 000."""
        self.deduction("3000", self.emp)
        payroll = approve_payroll(self.calc(MONTH, self.emp, OCT), self.director)
        register_payment(payroll, amount=D("20000"), payment_date=day(11, 1), actor=self.accountant)
        data = self.my(self.emp)
        t = data["totals"]
        self.assertEqual((t["accrued"], t["deducted"], t["net"], t["paid"], t["due"]),
                         ("50000.00", "3000.00", "47000.00", "20000.00", "27000.00"))
        [row] = data["deductions"]
        self.assertEqual((row["name"], row["period_label"], row["month_amount"], row["withheld"], row["status"]),
                         ("Налог", "Октябрь 2026", "3000.00", "3000.00", "WITHHELD"))
        self.assertIsNotNone(row["applied_at"])
        [history] = data["history"]
        self.assertEqual((history["accrued"], history["deducted"], history["due"]), ("50000.00", "3000.00", "27000.00"))
        # Повторно удержание не вычитается: выплатить можно ровно остаток.
        register_payment(payroll, amount=D("27000"), payment_date=day(11, 2), actor=self.accountant)
        self.assertEqual(self.my(self.emp)["totals"]["due"], "0.00")

    def test_calculated_deduction_is_marked_pending_and_draft_hidden(self):
        self.deduction("3000", self.emp)
        self.calc(MONTH, self.emp, OCT)  # рассчитано, не утверждено
        data = self.my(self.emp)
        [row] = data["deductions"]
        self.assertEqual((row["status"], row["applied_at"]), ("PENDING", None))
        self.assertEqual(data["totals"]["deducted"], "0.00")  # итоги — только по утверждённым

    def test_change_of_amount_keeps_history(self):
        rule = self.deduction("3000", self.emp)
        approve_payroll(self.calc(MONTH, self.emp, OCT), self.director)
        ded.change_rule(rule, actor=self.accountant, changes={"amount": D("4000"), "effective_from": day(11, 1),
                                                              "name": "Налог (новый)"}, reason="рост")
        approve_payroll(self.calc(MONTH, self.emp, (2026, 11)), self.director)
        rows = {r["period_label"]: (r["name"], r["month_amount"]) for r in self.my(self.emp)["deductions"]}
        self.assertEqual(rows, {"Октябрь 2026": ("Налог", "3000.00"), "Ноябрь 2026": ("Налог (новый)", "4000.00")})
        self.assertEqual(self.my(self.emp)["totals"]["deducted"], "7000.00")
        self.assertEqual(len(self.my(self.emp, month=10)["deductions"]), 1)

    def test_employee_never_sees_other_employee(self):
        other = make_user("other", User.Role.ASSISTANT)
        self.rule(self.profile(other, SalaryType.FIXED), R.FIXED, amount=D("99000"))
        self.deduction("3000", self.emp)
        self.deduction("7777", other, name="Чужой налог")
        approve_payroll(self.calc(MONTH, self.emp, OCT), self.director)
        approve_payroll(self.calc(MONTH, other, OCT), self.director)
        data = self.my(self.emp, employee=other.pk)  # параметр игнорируется — только свои
        self.assertEqual(data["totals"]["accrued"], "50000.00")
        self.assertEqual([r["name"] for r in data["deductions"]], ["Налог"])
        self.assertNotIn("Чужой налог", str(data))
        self.assertNotIn("99000", str(data))
        self.assertIn(self.client_for(self.emp).get("/api/v1/accounting/deduction-rules/").status_code, (403,))
        self.assertIn(self.client_for(self.emp).get("/api/v1/accounting/applied-deductions/").status_code, (403,))
        pdf = self.client_for(self.emp).get(f"{URL}report.pdf")
        self.assertEqual(pdf.status_code, 200)


class PercentTests(Fixture):
    def setUp(self):
        super().setUp()
        self.course_settings(price="10000", lessons=12, start=None)
        self.rule(self.profile(salary_type=SalaryType.PERCENT), R.PERCENT, percentage=D("10"))
        for _ in range(30):
            self.student(self.group_a)
        for _ in range(20):
            self.student(self.group_b)

    def test_two_payrolls_in_month_one_deduction(self):
        with self.captureOnCommitCallbacks(execute=True):
            self.lessons(self.group_a, days(10, 1, 12))
            self.lessons(self.group_b, days(10, 16, 27))
        self.deduction("3000", self.trainer_user)
        approve_payroll(self.calc(FIRST, year_month=OCT), self.director)
        approve_payroll(self.calc(SECOND, year_month=OCT), self.director)
        data = self.my(self.trainer_user)
        t = data["totals"]
        self.assertEqual((t["accrued"], t["deducted"], t["net"], t["due"]),
                         ("50000.00", "3000.00", "47000.00", "47000.00"))
        self.assertEqual(len(data["deductions"]), 1)
        self.assertEqual(data["deductions"][0]["withheld"], "3000.00")

    def test_estimate_is_not_taxed_and_says_so(self):
        """Незавершённые блоки: предварительная сумма без налога и с пометкой;
        одно ежемесячное удержание не вычитается из каждого блока."""
        with self.captureOnCommitCallbacks(execute=True):
            self.lessons(self.group_a, days(10, 1, 5))
            self.lessons(self.group_b, days(10, 1, 4))
        self.deduction("3000", self.trainer_user)
        with mock.patch("apps.accounting.services.my_salary.timezone.localdate", return_value=day(10, 10)):
            data = self.my(self.trainer_user)
        t = data["totals"]
        self.assertEqual(len(data["estimates"]), 2)
        expected = sum(D(e["expected_amount"]) for e in data["estimates"])
        self.assertEqual(D(t["estimated"]), expected)  # без вычета удержания
        self.assertEqual(D(t["estimated"]), D("50000"))
        self.assertIsNone(t["estimated_deductions"])
        self.assertEqual(t["estimated_deductions_note"], "Будет рассчитано после начисления")
        self.assertEqual((t["accrued"], t["deducted"]), ("0.00", "0.00"))  # не начислено официально
        self.assertEqual(data["deductions"], [])
