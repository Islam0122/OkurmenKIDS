"""«Моя зарплата» операционного директора: тот же расчёт и тот же API, что у
тренеров и HR (/accounting/my/…), только свои данные и только чтение."""
from __future__ import annotations

from apps.accounting.models import Payroll, PayrollAdjustment, SalaryRule, SalaryType
from apps.accounting.services.approval_service import approve_payroll, create_adjustment
from apps.accounting.services.payment_service import register_payment
from apps.accounting.tests.base import MONTH, D, AccountingFixture, day, make_user
from apps.accounting.tests.test_my_salary_hr import jwt_client
from apps.users.models import User

URL = "/api/v1/accounting/my/salary/"
R = SalaryRule.RuleType


class OperationsDirectorMySalaryTests(AccountingFixture):
    def setUp(self):
        super().setUp()
        self.od = make_user("odir", User.Role.OPERATIONS_DIRECTOR)
        self.od2 = make_user("odir2", User.Role.OPERATIONS_DIRECTOR)
        self.rule(self.profile(self.od, SalaryType.FIXED), R.FIXED, amount=D("90000"))

    def salary(self, user=None, **params):
        response = jwt_client(user or self.od).get(URL, params)
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()

    def test_sees_own_accruals_bonuses_deductions_and_payments(self):
        payroll = self.calc(MONTH, self.od)
        create_adjustment(payroll, kind=PayrollAdjustment.Kind.BONUS, amount=D("10000"), reason="Премия за KPI",
                          actor=self.accountant)
        create_adjustment(payroll, kind=PayrollAdjustment.Kind.DEDUCTION, amount=D("2000"), reason="Аванс в счёт",
                          actor=self.accountant)
        payroll = approve_payroll(Payroll.objects.get(pk=payroll.pk), self.director)
        register_payment(payroll, amount=D("50000"), payment_date=day(9, 25), actor=self.accountant,
                         comment="Первая часть, остаток — 10.10")
        data = self.salary()
        self.assertEqual(data["employee_name"], self.od.get_full_name())
        row = data["history"][0]
        # Разбивка из тех же записей расчёта: основная + бонусы − корректировки = начислено.
        self.assertEqual((row["base_amount"], row["bonuses"], row["accrued"]), ("90000.00", "10000.00", "98000.00"))
        self.assertEqual((row["paid"], row["status"]), ("50000.00", "PARTIALLY_PAID"))
        self.assertEqual(D(row["accrued"]) - D(row["deducted"]) - D(row["paid"]), D(row["due"]))
        self.assertEqual({a["reason"] for a in row["adjustments"]}, {"Премия за KPI", "Аванс в счёт"})
        self.assertEqual(data["payments"][0]["comment"], "Первая часть, остаток — 10.10")
        self.assertEqual((data["payments"][0]["payment_date"], data["totals"]["paid"]), ("2026-09-25", "50000.00"))
        self.assertEqual(len(self.salary(year=2026, month=9)["history"]), 1)
        self.assertEqual(self.salary(year=2026, month=8)["history"], [])

    def test_awaiting_payroll_hides_amounts(self):
        self.calc(MONTH, self.od)
        Payroll.objects.filter(employee=self.od).update(status=Payroll.Status.DRAFT)
        row = self.salary()["history"][0]
        self.assertEqual((row["base_amount"], row["bonuses"], row["accrued"]), (None, None, None))

    def test_cannot_see_other_employees_salary_by_changing_ids(self):
        self.rule(self.profile(self.trainer_user, SalaryType.FIXED), R.FIXED, amount=D("50000"))
        other = approve_payroll(self.calc(MONTH, self.trainer_user), self.director)
        register_payment(other, amount=D("1000"), payment_date=day(9, 20), actor=self.accountant)
        own = approve_payroll(self.calc(MONTH, self.od), self.director)
        client = jwt_client(self.od2)
        data = client.get(URL, {"employee": self.trainer_user.pk, "employee_id": self.od.pk, "user": self.od.pk}).json()
        self.assertEqual((data["employee_name"], data["history"], data["payments"]), (self.od2.get_full_name(), [], []))
        for payroll in (other, own):
            self.assertEqual(client.get(f"/api/v1/accounting/my/payrolls/{payroll.pk}/").status_code, 404)
        self.assertEqual(client.get("/api/v1/accounting/my/payments/").json()["results"], [])
        for url in ("/api/v1/accounting/payrolls/", f"/api/v1/accounting/payrolls/{other.pk}/",
                    "/api/v1/accounting/employees/", "/api/v1/accounting/salary-profiles/",
                    "/api/v1/accounting/payments/", f"/api/v1/accounting/earnings/{self.trainer_user.pk}/",
                    "/api/v1/accounting/earnings/", "/api/v1/accounting/reports/payroll.pdf?year=2026&month=9"):
            self.assertEqual(client.get(url).status_code, 403, url)

    def test_salary_is_read_only_for_operations_director(self):
        payroll = approve_payroll(self.calc(MONTH, self.od), self.director)
        client = jwt_client(self.od)
        before = (Payroll.objects.get(pk=payroll.pk).total_paid, PayrollAdjustment.objects.count())
        for method, url, body in (
            ("post", URL, {}),
            ("patch", f"/api/v1/accounting/salary-profiles/{self.od.salary_profile.pk}/", {"salary_type": "PERCENT"}),
            ("post", "/api/v1/accounting/payrolls/calculate/", {"period": payroll.period_id, "employee": self.od.pk}),
            ("post", f"/api/v1/accounting/payrolls/{payroll.pk}/payments/", {"amount": "1", "payment_date": "2026-09-20"}),
            ("post", f"/api/v1/accounting/payrolls/{payroll.pk}/adjustments/", {"kind": "BONUS", "amount": "1", "reason": "x"}),
            ("post", "/api/v1/accounting/my/payments/", {"amount": "1"}),
        ):
            self.assertIn(getattr(client, method)(url, body, format="json").status_code, (403, 405), url)
        self.assertEqual((Payroll.objects.get(pk=payroll.pk).total_paid, PayrollAdjustment.objects.count()), before)

    def test_all_own_salary_endpoints_open_with_token_and_cabinet_still_works(self):
        approve_payroll(self.calc(MONTH, self.od), self.director)
        client = jwt_client(self.od)
        for url in (URL, "/api/v1/accounting/my/salary/report.pdf", "/api/v1/accounting/my/payrolls/",
                    "/api/v1/accounting/my/payments/", "/api/v1/accounting/my/payout-plan/",
                    "/api/v1/accounting/my/estimates/", "/api/v1/operations/meta/"):
            self.assertEqual(client.get(url).status_code, 200, url)

    def test_other_staff_only_roles_still_isolated(self):
        response = jwt_client(make_user("rop", User.Role.ROP)).get(URL)
        self.assertEqual((response.status_code, response.json()["code"]), (403, "staff_only"))
