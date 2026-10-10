"""«Моя зарплата» для Assistant и Team Lead (и любого сотрудника)."""
from __future__ import annotations

from django.utils import timezone

from apps.accounting.models import Payroll, PayrollPayment, SalaryRule, SalaryType
from apps.accounting.services.approval_service import approve_payroll
from apps.accounting.services.payment_service import register_payment
from apps.accounting.tests.base import FIRST, SECOND, D, AccountingFixture, day, make_user
from apps.users.models import User

URL = "/api/v1/accounting/my/salary/"
R = SalaryRule.RuleType


class MySalaryTests(AccountingFixture):
    def setUp(self):
        super().setUp()
        self.assistant = make_user("asya", User.Role.ASSISTANT)
        self.team_lead = make_user("lead", User.Role.TEAM_LEAD)
        self.rule(self.profile(self.assistant, SalaryType.FIXED), R.FIXED, amount=D("40000"))
        self.rule(self.profile(self.team_lead, SalaryType.FIXED), R.FIXED, amount=D("60000"))

    def get(self, user, url=URL, **params):
        response = self.client_for(user).get(url, params)
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()

    def test_assistant_sees_own_salary(self):
        approve_payroll(self.calc(FIRST, self.assistant), self.director)
        data = self.get(self.assistant)
        self.assertEqual(data["profile"]["salary_type"], "FIXED")
        self.assertEqual(data["profile"]["rates"][0]["amount"], "40000.00")
        self.assertEqual(data["totals"], {"accrued": "20000.00", "paid": "0.00", "due": "20000.00",
                                          "pending_approval": "0.00"})
        self.assertEqual([r["status"] for r in data["history"]], ["APPROVED"])
        self.assertEqual(data["history"][0]["lines"][0]["amount"], "20000.00")

    def test_team_lead_sees_own_salary(self):
        approve_payroll(self.calc(FIRST, self.team_lead), self.director)
        data = self.get(self.team_lead)
        self.assertEqual(data["employee_name"], self.team_lead.get_full_name())
        self.assertEqual(data["totals"]["accrued"], "30000.00")
        self.assertEqual(data["profile"]["rates"][0]["amount"], "60000.00")

    def test_no_access_to_someone_elses_data(self):
        approve_payroll(self.calc(FIRST, self.team_lead), self.director)
        other = Payroll.objects.get(employee=self.team_lead)
        client = self.client_for(self.assistant)
        # Подставленные id и параметры игнорируются — всегда свои данные.
        data = client.get(URL, {"employee": self.team_lead.pk, "employee_id": self.team_lead.pk}).json()
        self.assertEqual(data["employee_name"], self.assistant.get_full_name())
        self.assertEqual(data["history"], [])
        self.assertEqual(client.get(f"/api/v1/accounting/my/payrolls/{other.pk}/").status_code, 404)
        self.assertEqual(client.get(f"/api/v1/accounting/my/payrolls/{other.pk}/report.pdf/").status_code, 404)
        # Ни бухгалтерия, ни чужие расчёты Assistant / Team Lead не открываются.
        for user in (self.assistant, self.team_lead):
            c = self.client_for(user)
            for url in ("/api/v1/accounting/payrolls/", f"/api/v1/accounting/payrolls/{other.pk}/",
                        "/api/v1/accounting/employees/", "/api/v1/accounting/salary-profiles/",
                        "/api/v1/accounting/payments/", "/api/v1/accounting/reports/payroll.pdf?year=2026&month=9"):
                self.assertEqual(c.get(url).status_code, 403, url)

    def test_read_only(self):
        payroll = approve_payroll(self.calc(FIRST, self.assistant), self.director)
        client = self.client_for(self.assistant)
        profile = self.assistant.salary_profile
        rule = profile.rules.get()
        for method, url, body in (
            ("post", URL, {}), ("put", URL, {}), ("patch", URL, {}), ("delete", URL, None),
            ("patch", f"/api/v1/accounting/salary-profiles/{profile.pk}/", {"salary_type": "PERCENT"}),
            ("post", f"/api/v1/accounting/salary-rules/{rule.pk}/new-version/", {"effective_from": "2026-10-01", "amount": "1"}),
            ("post", "/api/v1/accounting/payrolls/calculate/", {"period": payroll.period_id, "employee": self.assistant.pk}),
            ("post", f"/api/v1/accounting/payrolls/{payroll.pk}/payments/", {"amount": "1", "payment_date": "2026-09-20"}),
            ("post", f"/api/v1/accounting/payrolls/{payroll.pk}/approve/", {}),
            ("post", f"/api/v1/accounting/payrolls/{payroll.pk}/adjustments/", {"kind": "BONUS", "amount": "1", "reason": "x"}),
            ("post", "/api/v1/accounting/my/payrolls/", {}),
        ):
            response = getattr(client, method)(url, body, format="json")
            self.assertIn(response.status_code, (403, 405), f"{method} {url}")
        self.assertEqual(PayrollPayment.objects.count(), 0)
        self.assertEqual(self.assistant.salary_profile.rules.get().amount, D("40000"))

    def test_status_before_approval(self):
        self.calc(FIRST, self.assistant)
        data = self.get(self.assistant)
        row = data["history"][0]
        self.assertEqual((row["status"], row["status_display"], row["is_final"]),
                         ("CALCULATED", "Рассчитано, ожидает утверждения", False))
        self.assertEqual(row["accrued"], "20000.00")
        self.assertEqual(data["totals"]["accrued"], "0.00")  # итоги — только утверждённое
        self.assertEqual(data["totals"]["pending_approval"], "20000.00")
        # Возвращённый на исправление — «ожидает расчёта», без непроверенных сумм.
        from apps.accounting.services.approval_service import return_payroll

        return_payroll(Payroll.objects.get(employee=self.assistant), self.director, "проверить")
        row = self.get(self.assistant)["history"][0]
        self.assertEqual((row["status"], row["accrued"], row["lines"]), ("AWAITING", None, []))

    def test_payment_updates_totals(self):
        payroll = approve_payroll(self.calc(FIRST, self.assistant), self.director)
        register_payment(payroll, amount=D("15000"), payment_date=day(9, 20), actor=self.accountant)
        data = self.get(self.assistant)
        self.assertEqual(data["totals"], {"accrued": "20000.00", "paid": "15000.00", "due": "5000.00",
                                          "pending_approval": "0.00"})
        self.assertEqual(data["history"][0]["status"], "PARTIALLY_PAID")
        self.assertEqual(data["last_payment"], {"payment_date": "2026-09-20", "amount": "15000.00"})
        register_payment(payroll, amount=D("5000"), payment_date=day(9, 25), actor=self.accountant)
        data = self.get(self.assistant)
        self.assertEqual((data["totals"]["due"], data["history"][0]["status"]), ("0.00", "PAID"))
        self.assertEqual([p["amount"] for p in data["payments"]], ["5000.00", "15000.00"])

    def test_empty_state_is_not_an_error(self):
        nobody = make_user("newbie", User.Role.ASSISTANT)
        data = self.get(nobody)
        self.assertFalse(data["has_profile"])
        self.assertIsNone(data["profile"])
        self.assertEqual((data["history"], data["payments"], data["last_payment"]), ([], [], None))
        self.assertEqual([p["status"] for p in data["current_month"]["periods"]], ["AWAITING", "AWAITING"])
        response = self.client_for(nobody).get("/api/v1/accounting/my/salary/report.pdf")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.content.startswith(b"%PDF"))

    def test_filters_and_current_month(self):
        approve_payroll(self.calc(FIRST, self.assistant), self.director)
        approve_payroll(self.calc(SECOND, self.assistant), self.director)
        self.assertEqual(len(self.get(self.assistant, year=2026, month=9)["history"]), 2)
        only = self.get(self.assistant, year=2026, month=9, period_type="SECOND_HALF")["history"]
        self.assertEqual([r["period_type"] for r in only], ["SECOND_HALF"])
        self.assertEqual(self.get(self.assistant, month=8)["history"], [])
        self.assertEqual(self.client_for(self.assistant).get(URL, {"period_type": "X"}).status_code, 400)
        today = timezone.localdate()
        current = self.get(self.assistant)["current_month"]
        self.assertEqual((current["year"], current["month"]), (today.year, today.month))
        self.assertEqual(len(current["periods"]), 2)

    def test_percent_employee_sees_rate(self):
        trainer_profile = self.profile(salary_type=SalaryType.PERCENT)
        self.rule(trainer_profile, R.PERCENT, percentage=D("12.5"), group=self.group_a)
        data = self.get(self.trainer_user)
        self.assertEqual(data["profile"]["salary_type"], "PERCENT")
        self.assertEqual((data["profile"]["rates"][0]["percentage"], data["profile"]["rates"][0]["scope"]),
                         ("12.50", "Group A"))

    def test_personal_pdf(self):
        approve_payroll(self.calc(FIRST, self.team_lead), self.director)
        response = self.client_for(self.team_lead).get("/api/v1/accounting/my/salary/report.pdf", {"year": 2026})
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertTrue(response.content.startswith(b"%PDF"))
        self.assertEqual(self.client.get("/api/v1/accounting/my/salary/report.pdf").status_code, 401)
