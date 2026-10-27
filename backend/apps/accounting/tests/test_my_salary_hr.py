"""«Моя зарплата» HR-менеджера: тот же расчёт, что у тренеров и ассистентов
(EmployeeSalaryProfile → Payroll → PayrollPayment), только свои данные."""
from __future__ import annotations

from apps.accounting.models import Payroll, SalaryRule, SalaryType
from apps.accounting.services.approval_service import approve_payroll
from apps.accounting.services.payment_service import register_payment
from apps.accounting.tests.base import MONTH, D, AccountingFixture, day, make_user
from apps.users.models import User

URL = "/api/v1/accounting/my/salary/"
R = SalaryRule.RuleType


class HRMySalaryTests(AccountingFixture):
    def setUp(self):
        super().setUp()
        self.hr = make_user("hr", User.Role.HR_MANAGER)
        self.hr2 = make_user("hr2", User.Role.HR_MANAGER)
        self.rule(self.profile(self.hr, SalaryType.FIXED), R.FIXED, amount=D("40000"))

    def get(self, user, url=URL, **params):
        response = self.client_for(user).get(url, params)
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()

    def test_hr_sees_own_accruals_payments_and_due(self):
        payroll = approve_payroll(self.calc(MONTH, self.hr), self.director)
        register_payment(payroll, amount=D("15000"), payment_date=day(9, 20), actor=self.accountant)
        data = self.get(self.hr)
        self.assertEqual(data["employee_name"], self.hr.get_full_name())
        self.assertEqual(data["profile"]["salary_type"], "FIXED")
        self.assertEqual(data["profile"]["rates"][0]["amount"], "40000.00")
        self.assertEqual((data["totals"]["accrued"], data["totals"]["paid"], data["totals"]["due"]),
                         ("40000.00", "15000.00", "25000.00"))
        self.assertEqual([r["status"] for r in data["history"]], ["PARTIALLY_PAID"])
        self.assertEqual([(p["amount"], p["payment_date"]) for p in data["payments"]], [("15000.00", "2026-09-20")])

    def test_period_filter(self):
        approve_payroll(self.calc(MONTH, self.hr), self.director)
        self.assertEqual(len(self.get(self.hr, year=2026, month=9)["history"]), 1)
        self.assertEqual(self.get(self.hr, year=2026, month=8)["history"], [])
        self.assertEqual(self.client_for(self.hr).get(URL, {"month": 13}).status_code, 400)

    def test_without_profile_or_accruals_is_empty_not_invented(self):
        data = self.get(self.hr2)
        self.assertFalse(data["has_profile"])
        self.assertIsNone(data["profile"])
        self.assertEqual((data["history"], data["payments"]), ([], []))
        self.assertEqual((data["totals"]["accrued"], data["totals"]["paid"], data["totals"]["due"]),
                         ("0.00", "0.00", "0.00"))
        # Профиль есть, но расчётов ещё нет — тоже пусто, сумма не придумывается.
        data = self.get(self.hr)
        self.assertTrue(data["has_profile"])
        self.assertEqual((data["history"], data["totals"]["accrued"]), ([], "0.00"))

    def test_draft_payroll_shows_no_amounts(self):
        self.calc(MONTH, self.hr)  # рассчитан, не утверждён
        Payroll.objects.filter(employee=self.hr).update(status=Payroll.Status.DRAFT)
        row = self.get(self.hr)["history"][0]
        self.assertEqual((row["status"], row["accrued"], row["due"]), ("AWAITING", None, None))

    def test_hr_cannot_see_other_salaries(self):
        self.rule(self.profile(self.trainer_user, SalaryType.FIXED), R.FIXED, amount=D("50000"))
        approve_payroll(self.calc(MONTH, self.trainer_user), self.director)
        other = Payroll.objects.get(employee=self.trainer_user)
        client = self.client_for(self.hr2)
        data = client.get(URL, {"employee": self.trainer_user.pk, "employee_id": self.hr.pk}).json()
        self.assertEqual(data["employee_name"], self.hr2.get_full_name())
        self.assertEqual(data["history"], [])
        self.assertEqual(client.get(f"/api/v1/accounting/my/payrolls/{other.pk}/").status_code, 404)
        self.assertEqual(client.get("/api/v1/accounting/my/payments/").json()["results"], [])
        for url in ("/api/v1/accounting/payrolls/", f"/api/v1/accounting/payrolls/{other.pk}/",
                    "/api/v1/accounting/employees/", "/api/v1/accounting/salary-profiles/",
                    "/api/v1/accounting/payments/", "/api/v1/accounting/reports/payroll.pdf?year=2026&month=9"):
            self.assertEqual(client.get(url).status_code, 403, url)

    def test_other_staff_cannot_see_hr_salary(self):
        approve_payroll(self.calc(MONTH, self.hr), self.director)
        payroll = Payroll.objects.get(employee=self.hr)
        for user in (self.trainer_user, self.hr2):
            client = self.client_for(user)
            self.assertEqual(client.get(URL, {"employee": self.hr.pk}).json()["history"], [], user.role)
            self.assertEqual(client.get(f"/api/v1/accounting/my/payrolls/{payroll.pk}/").status_code, 404)

    def test_repeated_requests_create_nothing(self):
        approve_payroll(self.calc(MONTH, self.hr), self.director)
        before = (Payroll.objects.count(), self.hr.salary_profile.rules.count())
        for _ in range(3):
            self.get(self.hr)
            self.client_for(self.hr).get("/api/v1/accounting/my/salary/report.pdf")
        self.assertEqual((Payroll.objects.count(), self.hr.salary_profile.rules.count()), before)

    def test_hr_salary_is_read_only(self):
        payroll = approve_payroll(self.calc(MONTH, self.hr), self.director)
        client = self.client_for(self.hr)
        for method, url, body in (
            ("post", URL, {}),
            ("patch", f"/api/v1/accounting/salary-profiles/{self.hr.salary_profile.pk}/", {"salary_type": "PERCENT"}),
            ("post", "/api/v1/accounting/payrolls/calculate/", {"period": payroll.period_id, "employee": self.hr.pk}),
            ("post", f"/api/v1/accounting/payrolls/{payroll.pk}/payments/", {"amount": "1", "payment_date": "2026-09-20"}),
            ("post", f"/api/v1/accounting/payrolls/{payroll.pk}/adjustments/", {"kind": "BONUS", "amount": "1", "reason": "x"}),
        ):
            self.assertIn(getattr(client, method)(url, body, format="json").status_code, (403, 405), url)
