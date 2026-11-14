"""«Оплата» in the Student & Parent Portal against the REAL accounting
services: contracts, invoices, payments and receipts are created exactly as
the accountant creates them (billing.services.*), and the family's API must
show them — read-only, only for linked children, receipts only as issued."""
from __future__ import annotations

from django.urls import reverse
from rest_framework.test import APIClient

from apps.accounting.models import StudentPayment
from apps.billing.models import Receipt
from apps.billing.services import payments
from apps.billing.tests.base import D, BillingFixture

from .models import PortalAccount
from .services import accounts

NEW_PASSWORD = "Family-Secret-2026"


class FinancePortalTests(BillingFixture):
    def setUp(self):
        super().setUp()
        self.kid = self.student()
        self.profile_ = self.profile(self.kid)
        self.hold(3)  # lessons held → the first package invoice is issued
        issued = accounts.provision_account(self.kid, performed_by=self.manager)
        accounts.change_own_password(issued.account.user, current_password=issued.password, new_password=NEW_PASSWORD)
        self.account = issued.account
        self.family = self.login(issued.login)

    def login(self, username):
        client = APIClient()
        response = client.post(reverse("auth-login"), {"username": username, "password": NEW_PASSWORD}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {response.data['access']}")
        return client

    def url(self, name, *args, student=None):
        return reverse(f"portal:{name}", args=[(student or self.kid).pk, *args])

    def pay(self, amount, **extra):
        payment, _ = payments.record_payment(profile=self.profile_, amount=amount, received_date=self.today,
                                             actor=self.accountant, **extra)
        return payment

    # -- overview -----------------------------------------------------------
    def test_overview_matches_the_accounting_summary(self):
        from apps.billing.services.archive import student_finance

        data = self.family.get(self.url("payments")).data
        expected = student_finance(self.kid)
        self.assertEqual(data["summary"]["debt"], expected["debt"])
        self.assertEqual(data["summary"]["paid"], "0.00")
        self.assertEqual(len(data["open_invoices"]), 1)
        self.assertEqual(data["next_payment"]["amount"], "4000.00")
        self.assertIn(data["status"], ("upcoming", "due", "overdue"))
        self.assertEqual(data["contracts"][0]["course"], self.it_plan.name if not self.it_plan.course_id else self.course.name)

    def test_a_payment_by_the_accountant_appears_with_its_receipt(self):
        payment = self.pay(D("4000"), method=StudentPayment.Method.CARD, reference="TXN-77")
        receipt = Receipt.objects.get(payment=payment)
        self.assertTrue(receipt.number.startswith("OK-"))

        data = self.family.get(self.url("payments")).data
        self.assertEqual(data["summary"]["paid"], "4000.00")
        self.assertEqual(data["open_invoices"], [])
        self.assertEqual(data["status"], "paid")

        rows = self.family.get(self.url("payment-transactions")).data["results"]
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual((row["amount"], row["status"], row["method"], row["reference"]),
                         ("4000.00", "completed", "card", "TXN-77"))
        self.assertEqual(row["receipt"], {"id": receipt.pk, "number": receipt.number, "status": "ISSUED"})
        self.assertEqual(row["cashier"], self.accountant.get_full_name())

        docs = self.family.get(self.url("payment-documents")).data
        self.assertEqual([r["number"] for r in docs["receipts"]], [receipt.number])
        detail = self.family.get(self.url("receipt-detail", receipt.pk)).data
        self.assertEqual((detail["amount"], detail["status"], detail["kind"]), ("4000.00", "ISSUED", "PAYMENT"))
        self.assertEqual(detail["outstanding"], receipt.snapshot["outstanding"])

    def test_receipt_pdf_is_the_accounting_document_and_read_only(self):
        receipt = Receipt.objects.get(payment=self.pay(D("1500")))
        response = self.family.get(self.url("receipt-pdf", receipt.pk), {"download": "1"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertTrue(response.content.startswith(b"%PDF"))
        self.assertIn("attachment", response["Content-Disposition"])
        self.assertIn(receipt.number, response["Content-Disposition"])
        inline = self.family.get(self.url("receipt-pdf", receipt.pk))
        self.assertIn("inline", inline["Content-Disposition"])
        receipt.refresh_from_db()
        self.assertEqual(receipt.print_count, 0)  # the family's views never touch accounting records

    def test_cancelled_and_refunded_operations(self):
        first = self.pay(D("5000"))  # 4000 settles the invoice, 1000 stays as credit — refundable
        payments.refund_payment(first, actor=self.accountant, amount=D("1000"), reason="Переплата")
        second = self.pay(D("500"))
        payments.reverse_payment(second, actor=self.accountant, reason="Ошибка кассира")

        statuses = lambda f: sorted(r["status"] for r in self.family.get(self.url("payment-transactions"), {"status": f}).data["results"])  # noqa: E731
        self.assertEqual(statuses("all"), ["cancelled", "completed", "refunded"])
        self.assertEqual(statuses("completed"), ["completed"])
        self.assertEqual(statuses("refunded"), ["refunded"])
        self.assertEqual(statuses("cancelled"), ["cancelled"])
        self.assertEqual(self.family.get(self.url("payment-transactions"), {"status": "bogus"}).status_code, 400)

        cancelled = self.family.get(self.url("payment-transactions"), {"status": "cancelled"}).data["results"][0]
        self.assertEqual(cancelled["receipt"]["status"], "CANCELLED")  # annulled, not hidden, not re-numbered

    def test_payment_without_receipt_is_not_given_one(self):
        # A payment registered in accounting outside tuition billing — no receipt is issued for it.
        StudentPayment.objects.create(student=self.kid, group=self.group, course=self.course, amount=D("700"),
                                      received_date=self.today, created_by=self.accountant,
                                      service_start=self.today, service_end=self.today)
        rows = self.family.get(self.url("payment-transactions")).data["results"]
        self.assertEqual([(r["amount"], r["receipt"]) for r in rows], [("700.00", None)])
        self.assertEqual(self.family.get(self.url("payment-documents")).data["receipts"], [])

    def test_family_cannot_see_other_students_money(self):
        other = self.student()
        other_profile = self.profile(other)
        other_payment, _ = payments.record_payment(profile=other_profile, amount=D("4000"), received_date=self.today,
                                                   actor=self.accountant)
        other_receipt = Receipt.objects.get(payment=other_payment)
        for name in ("payments", "payment-transactions", "payment-documents"):
            self.assertEqual(self.family.get(self.url(name, student=other)).status_code, 404, name)
        # Another student's receipt id under this child's URL is also «not found».
        self.assertEqual(self.family.get(self.url("receipt-detail", other_receipt.pk)).status_code, 404)
        self.assertEqual(self.family.get(self.url("receipt-pdf", other_receipt.pk)).status_code, 404)

    def test_parent_sees_each_linked_child(self):
        sibling = self.student()
        sibling_profile = self.profile(sibling)
        accounts.link_student(self.account, sibling, performed_by=self.manager)
        payment, _ = payments.record_payment(profile=sibling_profile, amount=D("2500"), received_date=self.today,
                                             actor=self.accountant)
        rows = self.family.get(self.url("payment-transactions", student=sibling)).data["results"]
        self.assertEqual([r["amount"] for r in rows], ["2500.00"])
        receipt = Receipt.objects.get(payment=payment)
        self.assertEqual(self.family.get(self.url("receipt-pdf", receipt.pk, student=sibling)).status_code, 200)
        # …and not under the other child's URL.
        self.assertEqual(self.family.get(self.url("receipt-pdf", receipt.pk)).status_code, 404)

    def test_hidden_payments_and_read_only(self):
        receipt = Receipt.objects.get(payment=self.pay(D("100")))
        for method in ("post", "put", "patch", "delete"):
            response = getattr(self.family, method)(self.url("payment-transactions"), {}, format="json")
            self.assertEqual(response.status_code, 405, method)
        # The accounting API itself stays closed to the family.
        self.assertEqual(self.family.get(f"/api/v1/billing/receipts/{receipt.pk}/pdf/").status_code, 403)
        PortalAccount.objects.filter(pk=self.account.pk).update(can_view_payments=False)
        for name, args in (("payments", ()), ("payment-transactions", ()), ("payment-documents", ()),
                           ("receipt-pdf", (receipt.pk,))):
            self.assertEqual(self.family.get(self.url(name, *args)).status_code, 403, name)
