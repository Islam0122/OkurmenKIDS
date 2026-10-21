"""API: права ролей (в DRF и сервисах), валидация, идемпотентность, фильтры,
изоляция бухгалтера, отчёты, повторный запуск фоновых задач."""
from __future__ import annotations

import datetime as dt

from apps.accounting.models import StudentPayment
from apps.billing.models import (
    BillingEvent,
    BillingNotification,
    BillingTask,
    Invoice,
    LessonConsumption,
    LessonPackage,
    StudentBillingProfile,
)
from apps.billing.services import BillingError, contacts, payments
from apps.billing.services.reports import dashboard, financial_report, reconcile
from apps.billing.tests.base import BillingFixture, make_user
from apps.users.models import User

BASE = "/api/v1/accounting/billing/"


class ManagerRestrictionTests(BillingFixture):
    def test_manager_registers_student_and_sees_payment_status(self):
        student = self.student()
        api = self.client_for(self.manager)
        response = api.post(BASE + "profiles/", {
            "student": student.pk, "plan": self.it_plan.pk, "start_date": str(self.start),
            "parent_name": "Айгуль", "discount_type": "PERCENT", "discount_value": "10",
            "discount_reason": "Второй ребёнок", "reservation_amount": "1000",
        }, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        body = response.data
        self.assertEqual(body["payment_status"]["state"], "awaiting")
        self.assertEqual(body["payment_status"]["debt"], "3600.00")
        self.assertEqual(body["current_package"]["lessons_total"], 12)
        listed = api.get(BASE + "profiles/").data
        self.assertEqual(listed["count"], 1)

    def test_manager_cannot_touch_money(self):
        profile = self.profile()
        invoice = self.invoices(profile)[0]
        api = self.client_for(self.manager)
        forbidden = [
            ("post", "payments/", {"profile": profile.pk, "amount": "100", "received_date": str(self.today)}),
            ("get", "payments/", None),
            ("get", "allocations/", None),
            ("get", "debts/", None),
            ("get", "dashboard/", None),
            ("get", "contacts/", None),
            ("post", f"invoices/{invoice.pk}/void/", {"reason": "x"}),
            ("post", f"invoices/{invoice.pk}/adjustments/", {"amount": "10", "reason": "x"}),
            ("post", f"profiles/{profile.pk}/apply-credit/", {}),
            ("post", "plans/", {"name": "x", "lessons_per_package": 1, "package_price": "1",
                                "effective_from": str(self.today)}),
        ]
        for method, url, data in forbidden:
            with self.subTest(url=url, method=method):
                response = getattr(api, method)(BASE + url, data, format="json")
                self.assertEqual(response.status_code, 403, response.data)
        self.assertFalse(StudentPayment.objects.exists())
        # Сервисный слой тоже не пускает менеджера мимо API.
        with self.assertRaises(BillingError):
            payments.record_payment(profile=profile, amount="100", received_date=self.today, actor=self.manager)
        with self.assertRaises(BillingError):
            payments.apply_available_credit(profile, actor=self.manager)

    def test_teacher_and_anonymous_have_no_access(self):
        teacher = self.trainer.user
        self.assertEqual(self.client_for(teacher).get(BASE + "profiles/").status_code, 403)
        from rest_framework.test import APIClient

        self.assertEqual(APIClient().get(BASE + "profiles/").status_code, 401)

    def test_manager_discount_over_limit_goes_to_approval_via_api(self):
        profile = self.profile()
        api = self.client_for(self.manager)
        response = api.post(BASE + f"profiles/{profile.pk}/terms/", {
            "discount_type": "PERCENT", "discount_value": "40", "reason": "Просьба",
        }, format="json")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["status"], "PENDING")
        change_id = response.data["id"]
        self.assertEqual(api.post(BASE + f"terms-changes/{change_id}/decide/", {"approve": True},
                                  format="json").status_code, 403)
        director = self.client_for(self.director)
        self.assertEqual(director.post(BASE + f"terms-changes/{change_id}/decide/", {"approve": True},
                                       format="json").status_code, 200)


class AccountantApiTests(BillingFixture):
    def test_accountant_isolation_allows_billing(self):
        response = self.client_for(self.accountant).get(BASE + "dashboard/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["invoices_awaiting"], 0)

    def test_payment_api_idempotency_header_and_validation(self):
        profile = self.profile()
        api = self.client_for(self.accountant)
        payload = {"profile": profile.pk, "amount": "2500", "received_date": str(self.today)}
        first = api.post(BASE + "payments/", payload, format="json", HTTP_IDEMPOTENCY_KEY="k-1")
        second = api.post(BASE + "payments/", payload, format="json", HTTP_IDEMPOTENCY_KEY="k-1")
        self.assertEqual((first.status_code, second.status_code), (201, 200))
        self.assertEqual(first.data["id"], second.data["id"])
        self.assertEqual(StudentPayment.objects.count(), 1)
        invoice = api.get(BASE + f"invoices/{self.invoices(profile)[0].pk}/").data
        self.assertEqual((invoice["status"], invoice["balance"]), ("PARTIALLY_PAID", "1500.00"))
        self.assertEqual(len(invoice["allocations"]), 1)
        bad = api.post(BASE + "payments/", {**payload, "amount": "-1"}, format="json")
        self.assertEqual(bad.status_code, 400)

    def test_payment_with_explicit_allocations_and_prepay(self):
        profile = self.profile()
        api = self.client_for(self.accountant)
        response = api.post(BASE + "payments/", {
            "profile": profile.pk, "amount": "8000", "received_date": str(self.today), "prepay_packages": 1,
        }, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["unallocated"], "0.00")
        self.assertEqual(Invoice.objects.filter(profile=profile, status="PAID").count(), 2)

    def test_contacts_are_append_only_and_update_task(self):
        profile = self.profile()
        invoice = self.invoices(profile)[0]
        api = self.client_for(self.accountant)
        promised = self.today + dt.timedelta(days=3)
        response = api.post(BASE + "contacts/", {
            "profile": profile.pk, "invoice": invoice.pk, "channel": "WHATSAPP", "result": "PROMISED",
            "comment": "Оплатят в пятницу", "promised_payment_date": str(promised),
        }, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        task = BillingTask.objects.get(invoice=invoice)
        self.assertEqual((task.status, task.promised_date), ("PROMISED", promised))
        api.post(BASE + "contacts/", {"profile": profile.pk, "channel": "CALL", "result": "NO_ANSWER"}, format="json")
        self.assertEqual(api.get(BASE + "contacts/").data["count"], 2)
        missing = api.post(BASE + "contacts/", {"profile": profile.pk, "channel": "CALL", "result": "PROMISED"},
                           format="json")
        self.assertEqual(missing.status_code, 400)
        # Повторный контакт: обещание просрочено → уведомление.
        contacts.follow_up_due(on=promised + dt.timedelta(days=1))
        self.assertTrue(BillingNotification.objects.filter(kind="FOLLOW_UP").exists())
        # Оплата закрывает задачу автоматически.
        payments.record_payment(profile=profile, amount="4000", received_date=self.today, actor=self.accountant)
        task.refresh_from_db()
        self.assertEqual(task.status, "DONE")
        log = profile.contacts.first()
        log.comment = "переписать"
        with self.assertRaises(Exception):
            log.save()

    def test_invoice_filters_and_pagination(self):
        other_group_student = self.student(group=self.group_b)
        p1, p2 = self.profile(), self.profile(student=other_group_student)
        payments.record_payment(profile=p1, amount="4000", received_date=self.today, actor=self.accountant)
        api = self.client_for(self.accountant)
        self.assertEqual(api.get(BASE + "invoices/", {"group": self.group_b.pk}).data["count"], 1)
        self.assertEqual(api.get(BASE + "invoices/", {"status": "PAID"}).data["count"], 1)
        self.assertEqual(api.get(BASE + "invoices/", {"subject": self.it.pk}).data["count"], 2)
        self.assertEqual(api.get(BASE + "invoices/", {"student": p2.student_id}).data["count"], 1)
        self.assertEqual(api.get(BASE + "invoices/", {"status": "NOPE"}).status_code, 400)
        page = api.get(BASE + "invoices/", {"page_size": 1}).data
        self.assertEqual((page["count"], len(page["results"])), (2, 1))

    def test_reverse_consumption_api(self):
        self.profile()
        self.hold(1)
        consumption = LessonConsumption.objects.get()
        self.assertEqual(self.client_for(self.manager).post(
            BASE + f"consumptions/{consumption.pk}/reverse/", {"reason": "x"}, format="json").status_code, 403)
        response = self.client_for(self.accountant).post(
            BASE + f"consumptions/{consumption.pk}/reverse/", {"reason": "Ошибка тренера"}, format="json")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(LessonPackage.objects.get().lessons_used, 0)


class ReportTests(BillingFixture):
    def test_dashboard_separates_students_invoices_and_debt(self):
        a, b, c = self.profile(), self.profile(), self.profile()
        self.profile(student=a.student, plan=self.en_plan)  # второй счёт того же студента
        payments.record_payment(profile=b, amount="1000", received_date=self.today, actor=self.accountant)
        payments.record_payment(profile=c, amount="4500", received_date=self.today, actor=self.accountant)
        data = dashboard({})
        self.assertEqual(data["active_students"], 3)
        self.assertEqual(data["students_awaiting"], 2)       # a (2 счёта) и b
        self.assertEqual(data["invoices_awaiting"], 3)       # a: IT + English, b: IT
        self.assertEqual(data["total_debt"], "12000.00")     # 4000 + 5000 + 3000
        self.assertEqual(data["received"]["amount"], "5500.00")
        self.assertEqual(data["credit_total"], "500.00")
        self.assertEqual([r["student"] for r in data["partial"]], [b.student_id])
        overdue_day = self.invoices(a)[0].due_date + dt.timedelta(days=1)
        from apps.billing.services.invoices import mark_overdue_invoices

        mark_overdue_invoices(on=overdue_day)
        data = dashboard({}, on=overdue_day)
        self.assertEqual((data["overdue_invoices"], data["overdue_students"]), (3, 2))
        filtered = dashboard({"subject": self.english.pk})
        self.assertEqual((filtered["invoices_awaiting"], filtered["total_debt"]), (1, "5000.00"))
        self.assertEqual(dashboard({"accountant": self.director.pk})["invoices_awaiting"], 0)

    def test_financial_report_and_debtors(self):
        a = self.profile()
        payment, _ = payments.record_payment(profile=a, amount="5000", received_date=self.today, actor=self.accountant)
        payments.refund_payment(payment, actor=self.accountant, amount="1000", reason="Переплата")
        b = self.profile()
        report = financial_report({}, date_from=self.today.replace(day=1), date_to=self.today)
        self.assertEqual(report["invoiced"], {"amount": "8000.00", "invoices": 2, "students": 2})
        self.assertEqual((report["received"], report["refunded"], report["net_received"]),
                         ("5000.00", "1000.00", "4000.00"))
        self.assertEqual(report["debt_now"], {"amount": "4000.00", "invoices": 1, "students": 1})
        self.assertEqual(report["credit_now"], "0.00")
        rows = self.client_for(self.accountant).get(BASE + "debts/").data["results"]
        self.assertEqual([r["profile"] for r in rows], [b.pk])
        self.assertEqual(rows[0]["debt"], "4000.00")
        self.assertEqual(reconcile(), [])
        self.assertEqual(self.client_for(self.director).get(BASE + "reports/summary/").status_code, 200)


class TaskRerunTests(BillingFixture):
    def test_daily_tasks_are_idempotent(self):
        from apps.billing.tasks import run_daily

        profile = self.profile()
        pending = self.lesson(day=self.today - dt.timedelta(days=2))  # проведён, сигнал «не дошёл»
        self.assertFalse(LessonConsumption.objects.exists())
        due = self.invoices(profile)[0].due_date + dt.timedelta(days=1)
        first = run_daily(on=due)
        snapshot = (
            Invoice.objects.count(), LessonConsumption.objects.count(), BillingNotification.objects.count(),
            BillingTask.objects.count(), LessonPackage.objects.count(),
        )
        second = run_daily(on=due)
        self.assertEqual(snapshot, (
            Invoice.objects.count(), LessonConsumption.objects.count(), BillingNotification.objects.count(),
            BillingTask.objects.count(), LessonPackage.objects.count(),
        ))
        self.assertEqual(first["process_completed_lessons"]["consumed"], 1)
        self.assertEqual(second["process_completed_lessons"]["consumed"], 0)
        self.assertTrue(LessonConsumption.objects.filter(lesson_ref=pending.pk).exists())
        self.assertEqual(self.invoices(profile)[0].status, Invoice.Status.OVERDUE)
        event = BillingEvent.objects.get(key=f"task:mark_overdue_invoices:{due.isoformat()}")
        self.assertEqual((event.status, event.attempts), ("DONE", 2))

    def test_completed_package_without_successor_is_recovered_once(self):
        from apps.billing.tasks import process_completed_packages

        profile = self.profile()
        self.hold(12)
        second = self.packages(profile)[1]
        # Имитация сбоя: следующий пакет отменён, студент продолжает учиться.
        Invoice.objects.filter(package=second).update(status="VOID")
        LessonPackage.objects.filter(pk=second.pk).update(status="CANCELLED")
        self.assertEqual(process_completed_packages()["created"], 1)
        self.assertEqual(process_completed_packages()["created"], 0)
        self.assertEqual(LessonPackage.objects.filter(profile=profile, status="ACTIVE").count(), 1)

    def test_management_command(self):
        from io import StringIO

        from django.core.management import call_command

        self.profile()
        out = StringIO()
        call_command("billing_autorun", "--no-report", stdout=out)
        self.assertIn("mark_overdue_invoices", out.getvalue())


class PermissionHelpersTests(BillingFixture):
    def test_roles(self):
        from apps.billing.permissions import is_billing_accountant, is_billing_admin, is_manager

        self.assertTrue(is_billing_accountant(self.accountant))
        self.assertFalse(is_billing_accountant(self.manager))
        self.assertTrue(is_billing_admin(self.director))
        self.assertTrue(is_billing_admin(self.admin))
        self.assertFalse(is_billing_admin(self.accountant))
        self.assertTrue(is_manager(self.manager))
        other = make_user("other_buh", User.Role.ACCOUNTANT)
        other.groups.clear()
        self.assertFalse(is_billing_accountant(User.objects.get(pk=other.pk)))
        self.assertEqual(StudentBillingProfile.objects.count(), 0)
