"""Список всех студентов в оплате и массовое подключение к учёту."""
from __future__ import annotations

from apps.academy.models import Student
from apps.billing.models import Invoice, StudentBillingProfile
from apps.billing.services import payments
from apps.billing.tests.base import D, BillingFixture

BASE = "/api/v1/accounting/billing/"


class StudentsListTests(BillingFixture):
    def test_all_active_students_are_listed_with_payment_state(self):
        connected, plain = self.student(), self.student(group=self.group_b)
        gone = self.student()
        Student.objects.filter(pk=gone.pk).update(status=Student.Status.WITHDRAWN, is_active=False)
        profile = self.profile(student=connected)
        payments.record_payment(profile=profile, amount="5000", received_date=self.today, actor=self.accountant)

        data = self.client_for(self.accountant).get(BASE + "students/").data
        rows = {r["id"]: r for r in data["results"]}
        self.assertEqual(set(rows), {connected.pk, plain.pk})
        summary = rows[connected.pk]["profiles"][0]
        self.assertEqual((summary["payment_state"], summary["debt"], summary["credit"]), ("paid", "0", "1000.00"))
        self.assertEqual(summary["package"], {"number": 1, "used": 0, "total": 12})
        self.assertEqual(rows[plain.pk]["profiles"], [])

        api = self.client_for(self.accountant)
        self.assertEqual([r["id"] for r in api.get(BASE + "students/", {"registered": "no"}).data["results"]], [plain.pk])
        self.assertEqual([r["id"] for r in api.get(BASE + "students/", {"group": self.group_b.pk}).data["results"]],
                         [plain.pk])
        self.assertEqual(api.get(BASE + "students/", {"all": 1}).data["count"], 3)


class BulkRegisterTests(BillingFixture):
    def test_register_group_skips_already_connected(self):
        a, b = self.student(), self.student()
        self.student(group=self.group_b)
        self.profile(student=a)
        response = self.client_for(self.director).post(BASE + "profiles/bulk/", {
            "plan": self.it_plan.pk, "group": self.group.pk,
        }, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["created"], 1)
        self.assertEqual([s["student"] for s in response.data["skipped"]], [a.pk])
        profile = StudentBillingProfile.objects.get(student=b)
        self.assertEqual(profile.start_date, self.today)  # прошлые уроки не списываются
        self.assertEqual(profile.invoices.get().status, Invoice.Status.OPEN)

    def test_prepaid_first_package_closes_invoice_by_adjustment(self):
        students = [self.student(), self.student()]
        response = self.client_for(self.director).post(BASE + "profiles/bulk/", {
            "plan": self.it_plan.pk, "all_active": True, "prepaid_first_package": True,
            "prepaid_reason": "Оплачено наличными в сентябре",
        }, format="json")
        self.assertEqual(response.data["created"], 2)
        for st in students:
            invoice = Invoice.objects.get(profile__student=st)
            self.assertEqual((invoice.amount, invoice.amount_adjusted, invoice.status), (D("4000"), D("4000"), "PAID"))

    def test_permissions(self):
        self.student()
        api = self.client_for(self.accountant)
        self.assertEqual(api.post(BASE + "profiles/bulk/", {"plan": self.it_plan.pk, "all_active": True},
                                  format="json").status_code, 403)
        manager = self.client_for(self.manager)
        self.assertEqual(manager.post(BASE + "profiles/bulk/", {
            "plan": self.it_plan.pk, "all_active": True, "prepaid_first_package": True, "prepaid_reason": "x",
        }, format="json").status_code, 403)
        self.assertEqual(manager.post(BASE + "profiles/bulk/", {"plan": self.it_plan.pk, "all_active": True},
                                      format="json").data["created"], 1)
