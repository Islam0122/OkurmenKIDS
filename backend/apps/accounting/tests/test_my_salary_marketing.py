"""«Моя зарплата» маркетолога: тот же расчёт и тот же API, что у тренеров и HR
(EmployeeSalaryProfile → Payroll → PayrollPayment), только свои данные.

Запросы — через вход по паролю и JWT, как в браузере: так они проходят через
AccountingIsolationMiddleware (роль `marketing` — с базовым доступом)."""
from __future__ import annotations

from apps.accounting.models import Payroll, SalaryRule, SalaryType
from apps.accounting.services.approval_service import approve_payroll
from apps.accounting.services.payment_service import register_payment
from apps.accounting.tests.base import MONTH, D, AccountingFixture, day, make_user
from apps.accounting.tests.test_my_salary_hr import jwt_client
from apps.users.models import User

URL = "/api/v1/accounting/my/salary/"
R = SalaryRule.RuleType


class MarketingMySalaryTests(AccountingFixture):
    def setUp(self):
        super().setUp()
        self.marketer = make_user("aida", User.Role.MARKETING)
        self.colleague = make_user("bermet", User.Role.MARKETING)
        self.rule(self.profile(self.marketer, SalaryType.FIXED), R.FIXED, amount=D("45000"))
        self.api = jwt_client(self.marketer)

    def get(self, client=None, url=URL, **params):
        response = (client or self.api).get(url, params)
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()

    def test_sees_own_accruals_payments_and_due(self):
        payroll = approve_payroll(self.calc(MONTH, self.marketer), self.director)
        register_payment(payroll, amount=D("20000"), payment_date=day(9, 20), actor=self.accountant)
        data = self.get()
        self.assertEqual(data["employee_name"], self.marketer.get_full_name())
        self.assertEqual((data["totals"]["accrued"], data["totals"]["paid"], data["totals"]["due"]),
                         ("45000.00", "20000.00", "25000.00"))
        self.assertEqual([r["status"] for r in data["history"]], ["PARTIALLY_PAID"])
        self.assertEqual([(p["amount"], p["payment_date"]) for p in data["payments"]], [("20000.00", "2026-09-20")])
        for url in ("/api/v1/accounting/my/salary/report.pdf", "/api/v1/accounting/my/payrolls/",
                    "/api/v1/accounting/my/payments/", "/api/v1/accounting/my/payout-plan/",
                    "/api/v1/accounting/my/estimates/"):
            self.assertEqual(self.api.get(url).status_code, 200, url)

    def test_period_filter(self):
        approve_payroll(self.calc(MONTH, self.marketer), self.director)
        self.assertEqual(len(self.get(year=2026, month=9)["history"]), 1)
        self.assertEqual(self.get(year=2026, month=8)["history"], [])
        self.assertEqual(self.api.get(URL, {"month": 13}).status_code, 400)

    def test_without_profile_or_accruals_is_empty_not_invented(self):
        data = self.get(jwt_client(self.colleague))
        self.assertFalse(data["has_profile"])
        self.assertEqual((data["history"], data["payments"]), ([], []))
        self.assertEqual((data["totals"]["accrued"], data["totals"]["paid"], data["totals"]["due"]),
                         ("0.00", "0.00", "0.00"))
        data = self.get()
        self.assertTrue(data["has_profile"])
        self.assertEqual((data["history"], data["totals"]["accrued"]), ([], "0.00"))

    def test_cannot_see_other_salaries_by_id_substitution(self):
        self.rule(self.profile(self.trainer_user, SalaryType.FIXED), R.FIXED, amount=D("50000"))
        approve_payroll(self.calc(MONTH, self.trainer_user), self.director)
        approve_payroll(self.calc(MONTH, self.marketer), self.director)
        other = Payroll.objects.get(employee=self.trainer_user)
        mine = Payroll.objects.get(employee=self.marketer)
        client = jwt_client(self.colleague)
        data = client.get(URL, {"employee": self.trainer_user.pk, "employee_id": self.marketer.pk,
                                "user": self.marketer.pk}).json()
        self.assertEqual(data["employee_name"], self.colleague.get_full_name())
        self.assertEqual(data["history"], [])
        for payroll in (other, mine):
            self.assertEqual(client.get(f"/api/v1/accounting/my/payrolls/{payroll.pk}/").status_code, 404)
        self.assertEqual(client.get("/api/v1/accounting/my/payments/").json()["results"], [])

    def test_no_accounting_rights(self):
        payroll = approve_payroll(self.calc(MONTH, self.marketer), self.director)
        for url in ("/api/v1/accounting/payrolls/", f"/api/v1/accounting/payrolls/{payroll.pk}/",
                    "/api/v1/accounting/employees/", "/api/v1/accounting/salary-profiles/",
                    "/api/v1/accounting/payments/", "/api/v1/accounting/reports/payroll.pdf?year=2026&month=9",
                    "/api/v1/accounting/", "/api/v1/trainers/"):
            self.assertEqual(self.api.get(url).status_code, 403, url)
        for method, url, body in (
            ("post", URL, {}),
            ("patch", f"/api/v1/accounting/salary-profiles/{self.marketer.salary_profile.pk}/", {"salary_type": "PERCENT"}),
            ("post", "/api/v1/accounting/payrolls/calculate/", {"period": payroll.period_id, "employee": self.marketer.pk}),
            ("post", f"/api/v1/accounting/payrolls/{payroll.pk}/payments/", {"amount": "1", "payment_date": "2026-09-20"}),
        ):
            self.assertIn(getattr(self.api, method)(url, body, format="json").status_code, (403, 405), url)
        self.assertEqual(Payroll.objects.get(pk=payroll.pk).status, payroll.status)

    def test_other_staff_only_roles_are_still_isolated(self):
        for role in (User.Role.ROP, User.Role.SALES_MANAGER, User.Role.DOP):
            response = jwt_client(make_user(f"user_{role}", role)).get(URL)
            self.assertEqual((response.status_code, response.json()["code"]), (403, "staff_only"), role)
