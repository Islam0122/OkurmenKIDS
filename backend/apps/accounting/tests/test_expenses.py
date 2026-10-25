"""Расходы компании, финансовая панель и касса."""
from __future__ import annotations

import datetime as dt
from decimal import Decimal
from unittest import mock

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.accounting.models import (
    Expense,
    ExpenseCategory,
    PayrollAuditLog,
    PayrollPayment,
    RecurringExpense,
    StudentPayment,
)
from apps.accounting.services import AccountingError
from apps.accounting.services import expenses as svc
from apps.accounting.services import finance_overview
from apps.accounting.tests.base import AccountingFixture, make_user
from apps.users.models import User

D = Decimal
URL = "/api/v1/accounting/"
TODAY = dt.date(2026, 10, 20)


def _today():
    return TODAY


class ExpenseFixture(AccountingFixture):
    def setUp(self):
        super().setUp()
        patcher = mock.patch("apps.accounting.services.expenses._today", _today)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.rent = ExpenseCategory.objects.get(code="rent")
        self.ads = ExpenseCategory.objects.get(code="marketing")

    def expense(self, **kw):
        defaults = {"actor": self.accountant, "category": self.rent, "description": "Аренда октябрь",
                    "amount": D("50000"), "expense_date": dt.date(2026, 10, 1)}
        defaults.update(kw)
        return svc.create_expense(**defaults)[0]


class ExpenseServiceTests(ExpenseFixture):
    def test_default_categories_seeded(self):
        codes = set(ExpenseCategory.objects.values_list("code", flat=True))
        self.assertTrue({"rent", "utilities", "internet", "stationery", "materials", "equipment", "repair",
                         "marketing", "transport", "household", "other"} <= codes)

    def test_unpaid_expense_is_not_spent_money(self):
        self.expense()
        self.assertEqual(svc.paid_total(dt.date(2026, 10, 1), dt.date(2026, 10, 31)), D("0"))
        report = svc.report(dt.date(2026, 10, 1), dt.date(2026, 10, 31))
        self.assertEqual(report["paid"], D("0"))
        self.assertEqual(report["incurred"], D("50000"))
        self.assertEqual(report["unpaid"], D("50000"))

    def test_pay_counts_by_paid_date_and_only_once(self):
        e = self.expense()
        svc.mark_paid(e, actor=self.accountant, paid_date=dt.date(2026, 10, 5))
        with self.assertRaises(AccountingError) as ctx:
            svc.mark_paid(e, actor=self.accountant, paid_date=dt.date(2026, 10, 6))
        self.assertEqual(ctx.exception.code, "already_paid")
        self.assertEqual(svc.paid_total(dt.date(2026, 10, 1), dt.date(2026, 10, 31)), D("50000"))
        self.assertEqual(svc.paid_total(dt.date(2026, 9, 1), dt.date(2026, 9, 30)), D("0"))

    def test_future_paid_date_rejected(self):
        e = self.expense()
        with self.assertRaises(AccountingError):
            svc.mark_paid(e, actor=self.accountant, paid_date=TODAY + dt.timedelta(days=1))

    def test_idempotency_key_returns_same_expense(self):
        a, created_a = svc.create_expense(actor=self.accountant, category=self.rent, description="x", amount=D("10"),
                                          expense_date=TODAY, idempotency_key="k1")
        b, created_b = svc.create_expense(actor=self.accountant, category=self.rent, description="x", amount=D("10"),
                                          expense_date=TODAY, idempotency_key="k1")
        self.assertEqual(a.pk, b.pk)
        self.assertTrue(created_a)
        self.assertFalse(created_b)
        self.assertEqual(Expense.objects.count(), 1)

    def test_same_vendor_document_not_posted_twice(self):
        self.expense(vendor="ОсОО Арендодатель", reference="INV-7")
        with self.assertRaises(AccountingError) as ctx:
            self.expense(vendor="ОсОО Арендодатель", reference="INV-7")
        self.assertEqual(ctx.exception.code, "duplicate_document")
        # После отмены ошибочного — можно провести заново.
        Expense.objects.filter(reference="INV-7").update(status=Expense.Status.VOID)
        self.expense(vendor="ОсОО Арендодатель", reference="INV-7")

    def test_paid_money_fields_need_reason(self):
        e = self.expense(paid=True, paid_date=dt.date(2026, 10, 2))
        with self.assertRaises(AccountingError) as ctx:
            svc.update_expense(e, actor=self.accountant, changes={"amount": D("45000")})
        self.assertEqual(ctx.exception.code, "reason_required")
        e = svc.update_expense(e, actor=self.accountant, changes={"amount": D("45000")}, reason="Ошибка в сумме")
        self.assertEqual(e.amount, D("45000"))
        entry = PayrollAuditLog.objects.filter(entity_type="expense", action="expense_update").get()
        self.assertEqual(entry.old_values["amount"], "50000.00")
        self.assertEqual(entry.new_values["amount"], "45000.00")
        self.assertEqual(entry.reason, "Ошибка в сумме")

    def test_version_conflict(self):
        e = self.expense()
        svc.update_expense(e, actor=self.accountant, changes={"comment": "a"}, version=1)
        with self.assertRaises(AccountingError) as ctx:
            svc.update_expense(e, actor=self.accountant, changes={"comment": "b"}, version=1)
        self.assertEqual(ctx.exception.code, "conflict")

    def test_void_keeps_record_and_excludes_from_reports(self):
        e = self.expense(paid=True, paid_date=dt.date(2026, 10, 2))
        svc.void_expense(e, actor=self.accountant, reason="Дубль")
        self.assertEqual(svc.paid_total(dt.date(2026, 10, 1), dt.date(2026, 10, 31)), D("0"))
        self.assertTrue(Expense.objects.filter(pk=e.pk, status=Expense.Status.VOID).exists())
        with self.assertRaises(ValidationError):
            Expense.objects.filter(pk=e.pk).delete()
        with self.assertRaises(ValidationError):
            e.delete()

    def test_unpay_returns_to_unpaid(self):
        e = self.expense(paid=True, paid_date=dt.date(2026, 10, 2))
        e = svc.unmark_paid(e, actor=self.accountant, reason="Оплата не прошла")
        self.assertEqual((e.status, e.paid_date), (Expense.Status.UNPAID, None))

    def test_inactive_category_rejected_for_new_expenses(self):
        self.ads.is_active = False
        self.ads.save()
        with self.assertRaises(AccountingError):
            self.expense(category=self.ads)

    def test_recurring_generates_once_per_month(self):
        tpl = svc.save_recurring(actor=self.accountant, category=self.rent, description="Аренда", amount=D("50000"),
                                 day_of_month=5, start_month=dt.date(2026, 9, 15))
        self.assertEqual(tpl.start_month, dt.date(2026, 9, 1))
        first = svc.generate_recurring(2026, 10, actor=self.accountant)
        again = svc.generate_recurring(2026, 10, actor=self.accountant)
        self.assertEqual(len(first["created"]), 1)
        self.assertEqual(again["created"], [])
        e = Expense.objects.get(recurring=tpl)
        self.assertEqual((e.expense_date, e.status, e.amount), (dt.date(2026, 10, 5), Expense.Status.UNPAID, D("50000")))
        # Отменённый расход месяца не создаётся заново.
        svc.void_expense(e, actor=self.accountant, reason="Аренда отменена")
        self.assertEqual(svc.generate_recurring(2026, 10)["created"], [])
        # До начала и после окончания — не создаётся.
        self.assertEqual(svc.generate_recurring(2026, 8)["created"], [])
        svc.save_recurring(actor=self.accountant, recurring=tpl, end_month=dt.date(2026, 10, 1))
        self.assertEqual(svc.generate_recurring(2026, 11)["created"], [])

    def test_report_by_category(self):
        self.expense(paid=True, paid_date=dt.date(2026, 10, 3))
        self.expense(category=self.ads, description="Таргет", amount=D("10000"), paid=True, paid_date=dt.date(2026, 10, 4))
        self.expense(category=self.ads, description="Баннер", amount=D("5000"))
        report = svc.report(dt.date(2026, 10, 1), dt.date(2026, 10, 31))
        rows = {r["category_name"]: r for r in report["by_category"]}
        self.assertEqual(report["paid"], D("60000"))
        self.assertEqual(rows["Реклама и маркетинг"]["paid"], D("10000"))
        self.assertEqual(rows["Реклама и маркетинг"]["unpaid"], D("5000"))
        self.assertEqual(rows["Аренда офиса и учебных помещений"]["share_percent"], D("83.3"))


class FinanceOverviewTests(ExpenseFixture):
    def setUp(self):
        super().setUp()
        self.student_a = self.student()

    def pay_student(self, amount, on, kind=StudentPayment.Kind.PAYMENT, refund_of=None, method="cash"):
        return StudentPayment.objects.create(
            student=self.student_a, group=self.group_a, course=self.course, kind=kind, amount=D(amount),
            received_date=on, service_start=on, service_end=on, refund_of=refund_of, method=method,
            created_by=self.accountant,
        )

    def test_cash_flow_separates_money_kinds(self):
        p = self.pay_student("30000", dt.date(2026, 10, 2))
        self.pay_student("2000", dt.date(2026, 10, 3), kind=StudentPayment.Kind.REFUND, refund_of=p)
        StudentPayment.objects.filter(pk=self.pay_student("999", dt.date(2026, 10, 4)).pk).update(
            status=StudentPayment.Status.VOID)
        self.expense(paid=True, paid_date=dt.date(2026, 10, 5), payment_method="bank")
        self.expense(description="Не оплачено", amount=D("7000"))
        data = finance_overview.overview(dt.date(2026, 10, 1), dt.date(2026, 10, 31), today=TODAY)
        self.assertEqual(data["students"]["gross"], D("30000"))
        self.assertEqual(data["students"]["refunds"], D("2000"))
        self.assertEqual(data["expenses"]["paid"], D("50000"))
        self.assertEqual(data["expenses"]["incurred"], D("57000"))
        self.assertEqual(data["expenses"]["unpaid_now_amount"], D("7000.00"))
        self.assertEqual(data["cash_flow"]["inflow"], D("30000"))
        self.assertEqual(data["cash_flow"]["outflow"], D("52000"))
        self.assertEqual(data["result"]["cash"], D("-22000"))
        self.assertIsNone(data["result"]["accrual"])
        self.assertFalse(data["branches_supported"])
        methods = {m["method"]: m for m in data["cash_flow"]["by_method"]}
        self.assertEqual(methods["cash"]["net"], D("28000"))
        self.assertEqual(methods["bank"]["outflow"], D("50000"))
        self.assertEqual(data["previous_period"], {"date_from": dt.date(2026, 9, 1), "date_to": dt.date(2026, 9, 30)})
        self.assertEqual(data["history"][-1]["net"], D("-22000"))

    def test_comparison_with_previous_month(self):
        self.pay_student("10000", dt.date(2026, 9, 10))
        self.pay_student("15000", dt.date(2026, 10, 10))
        data = finance_overview.overview(dt.date(2026, 10, 1), dt.date(2026, 10, 31), today=TODAY)
        cmp = data["comparison"]["student_receipts"]
        self.assertEqual((cmp["current"], cmp["previous"], cmp["delta"], cmp["percent"]),
                         (D("15000"), D("10000"), D("5000"), D("50.0")))

    def test_cash_movements_ledger(self):
        self.pay_student("30000", dt.date(2026, 10, 2))
        self.expense(paid=True, paid_date=dt.date(2026, 10, 5))
        data = finance_overview.cash_movements(dt.date(2026, 10, 1), dt.date(2026, 10, 31))
        self.assertEqual([r["kind"] for r in data["results"]], ["expense", "student_payment"])
        self.assertEqual(data["summary"]["net"], D("-20000.00"))
        only_in = finance_overview.cash_movements(dt.date(2026, 10, 1), dt.date(2026, 10, 31), direction="in")
        self.assertEqual(only_in["summary"]["count"], 1)

    def test_previous_range(self):
        self.assertEqual(finance_overview.previous_range(dt.date(2026, 3, 1), dt.date(2026, 3, 31)),
                         (dt.date(2026, 2, 1), dt.date(2026, 2, 28)))
        self.assertEqual(finance_overview.previous_range(dt.date(2026, 3, 10), dt.date(2026, 3, 19)),
                         (dt.date(2026, 2, 28), dt.date(2026, 3, 9)))


class ExpenseApiTests(ExpenseFixture):
    def setUp(self):
        super().setUp()
        from rest_framework.test import APIClient

        self.api = APIClient()
        self.api.force_authenticate(self.accountant)

    def test_create_pay_void_flow_and_history(self):
        body = {"category": self.rent.pk, "description": "Аренда", "amount": "50000", "expense_date": "2026-10-01",
                "vendor": "Арендодатель", "payment_method": "bank"}
        r = self.api.post(f"{URL}expenses/", body, format="json", HTTP_IDEMPOTENCY_KEY="abc")
        self.assertEqual(r.status_code, 201, r.data)
        again = self.api.post(f"{URL}expenses/", body, format="json", HTTP_IDEMPOTENCY_KEY="abc")
        self.assertEqual(again.status_code, 200)
        self.assertEqual(again.data["id"], r.data["id"])
        pk = r.data["id"]
        r = self.api.post(f"{URL}expenses/{pk}/pay/", {"paid_date": "2026-10-02"}, format="json")
        self.assertEqual(r.data["status"], "PAID")
        r = self.api.post(f"{URL}expenses/{pk}/pay/", {"paid_date": "2026-10-02"}, format="json")
        self.assertEqual(r.status_code, 400)
        r = self.api.patch(f"{URL}expenses/{pk}/", {"amount": "40000", "version": 1}, format="json")
        self.assertEqual(r.status_code, 409)
        r = self.api.patch(f"{URL}expenses/{pk}/", {"amount": "40000", "version": 2}, format="json")
        self.assertEqual(r.status_code, 400)  # оплаченный — нужна причина
        r = self.api.patch(f"{URL}expenses/{pk}/", {"amount": "40000", "version": 2, "reason": "скидка"}, format="json")
        self.assertEqual(r.data["amount"], "40000.00")
        r = self.api.post(f"{URL}expenses/{pk}/void/", {"reason": "дубль"}, format="json")
        self.assertEqual(r.data["status"], "VOID")
        self.assertEqual(self.api.delete(f"{URL}expenses/{pk}/").status_code, 405)
        history = self.api.get(f"{URL}expenses/{pk}/history/").data["results"]
        self.assertEqual([h["action"] for h in history],
                         ["expense_void", "expense_update", "expense_pay", "expense_create"])

    def test_list_filters_and_totals(self):
        self.expense(paid=True, paid_date=dt.date(2026, 10, 3))
        self.expense(category=self.ads, description="Таргет инстаграм", amount=D("10000"))
        r = self.api.get(f"{URL}expenses/", {"category": self.ads.pk})
        self.assertEqual(r.data["count"], 1)
        r = self.api.get(f"{URL}expenses/", {"search": "инстаграм"})
        self.assertEqual(r.data["count"], 1)
        r = self.api.get(f"{URL}expenses/", {"status": "PAID"})
        self.assertEqual(r.data["totals"]["paid"], "50000.00")
        r = self.api.get(f"{URL}expenses/")
        self.assertEqual(r.data["totals"], {"total": "60000.00", "paid": "50000.00", "unpaid": "10000.00"})

    def test_document_upload_and_download_through_api_only(self):
        e = self.expense()
        upload = SimpleUploadedFile("check.pdf", b"%PDF-1.4 test", content_type="application/pdf")
        r = self.api.post(f"{URL}expenses/{e.pk}/document/", {"document": upload}, format="multipart")
        self.assertEqual(r.status_code, 200, r.data)
        self.assertTrue(r.data["has_document"])
        self.assertNotIn("document", r.data)  # путь к файлу не отдаётся
        r = self.api.get(f"{URL}expenses/{e.pk}/document/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(b"".join(r.streaming_content), b"%PDF-1.4 test")
        bad = SimpleUploadedFile("run.exe", b"MZ", content_type="application/octet-stream")
        r = self.api.post(f"{URL}expenses/{e.pk}/document/", {"document": bad}, format="multipart")
        self.assertEqual(r.status_code, 400)

    def test_create_with_document_multipart(self):
        upload = SimpleUploadedFile("receipt.jpg", b"\xff\xd8\xff", content_type="image/jpeg")
        r = self.api.post(f"{URL}expenses/", {"category": self.rent.pk, "description": "Ремонт", "amount": "1500",
                                             "expense_date": "2026-10-01", "paid": "true", "paid_date": "2026-10-01",
                                             "document": upload}, format="multipart")
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual((r.data["status"], r.data["document_name"]), ("PAID", "receipt.jpg"))

    def test_permissions(self):
        director = APIClientFor(self.director)
        self.assertEqual(director.get(f"{URL}expenses/").status_code, 200)
        self.assertEqual(director.post(f"{URL}expenses/", {}, format="json").status_code, 403)
        self.assertEqual(director.get(f"{URL}finance/overview/").status_code, 200)
        teacher = APIClientFor(make_user("t2"))
        self.assertEqual(teacher.get(f"{URL}expenses/").status_code, 403)
        self.assertEqual(teacher.get(f"{URL}finance/overview/").status_code, 403)
        self.assertEqual(teacher.get(f"{URL}finance/cash-flow/").status_code, 403)

    def test_categories_and_recurring_api(self):
        r = self.api.post(f"{URL}expense-categories/", {"name": "Охрана"}, format="json")
        self.assertEqual(r.status_code, 201, r.data)
        r = self.api.post(f"{URL}expense-categories/", {"name": "охрана"}, format="json")
        self.assertEqual(r.status_code, 400)
        r = self.api.post(f"{URL}recurring-expenses/", {"category": self.rent.pk, "description": "Интернет",
                                                        "amount": "2500", "day_of_month": 10,
                                                        "start_month": "2026-10-01"}, format="json")
        self.assertEqual(r.status_code, 201, r.data)
        r = self.api.post(f"{URL}recurring-expenses/generate/", {"year": 2026, "month": 10}, format="json")
        self.assertEqual(len(r.data["created"]), 1)
        self.assertEqual(RecurringExpense.objects.get().expenses.count(), 1)

    def test_reports_and_exports(self):
        self.expense(paid=True, paid_date=dt.date(2026, 10, 3))
        r = self.api.get(f"{URL}expenses/report/", {"month": "2026-10"})
        self.assertEqual(r.data["paid"], "50000.00")
        r = self.api.get(f"{URL}expenses/export.xlsx/", {"month": "2026-10"})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.content.startswith(b"PK"))
        r = self.api.get(f"{URL}finance/overview/", {"month": "2026-10"})
        self.assertEqual(r.data["expenses"]["paid"], "50000.00")
        r = self.api.get(f"{URL}finance/cash-flow/", {"date_from": "2026-10-01", "date_to": "2026-10-31"})
        self.assertEqual((r.data["count"], r.data["summary"]["outflow"]), (1, "50000.00"))
        r = self.api.get(f"{URL}finance/report.xlsx", {"month": "2026-10"})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.content.startswith(b"PK"))
        self.assertEqual(self.api.get(f"{URL}finance/overview/", {"month": "2026-13"}).status_code, 400)

    def test_payroll_payment_appears_in_cash_flow(self):
        payroll = self.make_approved_payroll()
        PayrollPayment.objects.create(payroll=payroll, amount=D("1000"), payment_date=dt.date(2026, 10, 7),
                                      created_by=self.accountant)
        r = self.api.get(f"{URL}finance/cash-flow/", {"month": "2026-10", "kind": "payroll_payment"})
        self.assertEqual(r.data["count"], 1)
        self.assertEqual(r.data["results"][0]["link"], f"/accounting/payrolls/{payroll.pk}")

    def make_approved_payroll(self):
        from apps.accounting.models import Payroll
        from apps.accounting.services.periods import get_or_create_period

        period, _ = get_or_create_period(2026, 10, "FIRST_HALF", actor=self.accountant)
        return Payroll.objects.create(employee=self.trainer_user, period=period, status=Payroll.Status.APPROVED,
                                      salary_type="PERCENT")


def APIClientFor(user: User):
    from rest_framework.test import APIClient

    client = APIClient()
    client.force_authenticate(user)
    return client
