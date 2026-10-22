"""Демо-набор оплаты (seed_billing_demo / reset_billing_demo): сценарии A–O
получаются настоящей бизнес-логикой, повтор не дублирует, очистка удаляет
только демо-данные. Номера в docstring — пункты ТЗ «Автоматические проверки»."""
from __future__ import annotations

import datetime as dt
import io
import os
from decimal import Decimal as D
from unittest import mock

from django.apps import apps as django_apps
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.academy.models import Course, Group, Student
from apps.accounting.models import DemoSeedRecord, StudentPayment
from apps.billing.models import (
    BillingSettings,
    Invoice,
    LessonConsumption,
    LessonPackage,
    PaymentAllocation,
    Receipt,
    StudentBillingProfile,
)
from apps.billing.services import analytics, contracts, demo, payments, queues
from apps.billing.services.ledger import payment_unallocated
from apps.users.models import User

BASE = "/api/v1/accounting/billing/"


def profile(key: str) -> StudentBillingProfile:
    return demo.lookup(f"profile:{key}")


def live_invoices(p):
    return list(Invoice.objects.filter(profile=p).exclude(status="VOID").order_by("package__number"))


def months(p):
    return list(LessonPackage.objects.filter(profile=p).exclude(status="CANCELLED").order_by("number"))


def api(user) -> APIClient:
    client = APIClient()
    client.force_authenticate(user)
    return client


class DemoSeedTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        BillingSettings.load()
        cls.result = demo.seed()
        cls.today = timezone.localdate()

    def test_01_second_run_creates_nothing(self):
        """1. Повторный запуск seed_billing_demo не создаёт дубликаты."""
        counted = (DemoSeedRecord, Student, Group, Course, StudentBillingProfile, Invoice, StudentPayment, Receipt,
                   LessonConsumption, User)
        before = {m: m._base_manager.count() for m in counted}
        out = io.StringIO()
        call_command("seed_billing_demo", stdout=out)
        self.assertIn("ничего — набор уже создан", out.getvalue())
        self.assertEqual({m: m._base_manager.count() for m in counted}, before)
        self.assertEqual(self.result["created"], [sc.key for sc in demo.SCENARIOS])
        self.assertEqual(len(demo.SCENARIOS), 15)

    def test_02_background_tasks_do_not_duplicate_invoices(self):
        """2. Повторный запуск фоновых задач не создаёт дубликаты начислений."""
        from apps.billing.tasks import run_daily

        before = (Invoice.objects.count(), LessonPackage.objects.count(), PaymentAllocation.objects.count())
        run_daily(report=False)
        run_daily(report=False)
        self.assertEqual((Invoice.objects.count(), LessonPackage.objects.count(), PaymentAllocation.objects.count()),
                         before)

    def test_03_it_12_english_10_completes_month(self):
        """3. Студент I: IT 12, English 10 — месяц 1 завершён, месяц 2 к оплате."""
        p = profile("I")
        first, second = months(p)
        self.assertEqual((first.status, first.lessons_used, second.month_number), ("COMPLETED", 12, 2))
        self.assertEqual(p.consumptions.count(), 12)  # уроки English не списываются
        self.assertIn(p.pk, [r["profile"] for r in queues.queue_rows("to_pay", {})])

    def test_04_it_9_english_12_does_not_complete_month(self):
        """4. Студент J: IT 9, English 12 — месяц 1 не завершён."""
        p = profile("J")
        (only,) = months(p)
        self.assertEqual((only.status, only.lessons_used), ("ACTIVE", 9))
        self.assertEqual(len(live_invoices(p)), 1)

    def test_05_fixed_discount(self):
        """5. Студент C: 60 000 − 15 000 = 45 000, оплачено 15 000, остаток 30 000."""
        p = profile("C")
        self.assertEqual((p.standard_course_price, p.final_course_price, p.discount_amount),
                         (D("60000"), D("45000"), D("15000")))
        s = contracts.money_summary(p)
        self.assertEqual((s["paid_total"], s["outstanding"]), (D("15000"), D("30000")))
        self.assertEqual(live_invoices(p)[0].amount, D("11250"))

    def test_06_reservation_counted_once(self):
        """6. Студент D: бронь 3 000 + 12 000 закрывают месяц 1, бронь — один раз."""
        p = profile("D")
        (invoice,) = live_invoices(p)
        self.assertEqual((invoice.status, invoice.amount_paid), ("PAID", D("15000")))
        res_payment = p.reservations.get().payment
        allocated = sum(a.amount for a in PaymentAllocation.objects.filter(payment=res_payment, status="ACTIVE"))
        self.assertEqual((allocated, payment_unallocated(res_payment.pk)), (D("3000"), D("0")))
        s = contracts.money_summary(p)
        self.assertEqual((s["paid_total"], s["credit"], s["outstanding"]), (D("15000"), D("0"), D("45000")))

    def test_07_partial_payment(self):
        """7. Студент F: начислено 15 000, оплачено 8 000, долг 7 000."""
        (invoice,) = live_invoices(profile("F"))
        self.assertEqual((invoice.status, invoice.amount_paid, invoice.balance), ("PARTIALLY_PAID", D("8000"), D("7000")))

    def test_08_prepayment_covers_months(self):
        """8. Студент K: 45 000 = три месяца; не долг, не «скоро», не «просрочено»."""
        p = profile("K")
        self.assertTrue(all(i.status == "PAID" for i in live_invoices(p)))
        self.assertEqual(contracts.money_summary(p)["credit"], D("15000"))
        for queue in ("to_pay", "soon", "overdue"):
            self.assertNotIn(p.pk, [r["profile"] for r in queues.queue_rows(queue, {})], queue)
        a = profile("A")  # оплачен весь курс
        self.assertEqual(contracts.money_summary(a)["outstanding"], D("0"))
        self.assertEqual(len(live_invoices(a)), 1)

    def test_09_overdue_by_actual_deadline(self):
        """9. Просрочка — только после срока оплаты (3-й урок IT месяца)."""
        overdue = {r["profile"] for r in queues.queue_rows("overdue", {})}
        self.assertEqual(overdue, {profile(k).pk for k in ("E", "G", "M")})
        self.assertEqual(live_invoices(profile("G"))[1].status, "OVERDUE")
        self.assertEqual(contracts.money_summary(profile("M"))["overdue"], D("10000"))
        to_pay = {r["profile"] for r in queues.queue_rows("to_pay", {})}
        self.assertTrue({profile(k).pk for k in ("B", "F", "I", "L")} <= to_pay)
        soon = {r["profile"] for r in queues.queue_rows("soon", {})}
        self.assertEqual(soon, {profile(k).pk for k in ("H", "J")})
        # Будущие месяцы — не просрочка: у B месяц 2 ещё в сроке.
        self.assertEqual(contracts.money_summary(profile("B"))["overdue"], D("0"))

    def test_scenarios_individual_price_overpayment_refund(self):
        self.assertEqual([i.amount for i in live_invoices(profile("L"))], [D("12000"), D("12000")])
        n = contracts.money_summary(profile("N"))
        self.assertEqual((n["due_now"], n["credit"]), (D("0"), D("3000")))
        o = profile("O")
        original = StudentPayment.objects.get(billing_profile=o, kind="payment")
        refund = StudentPayment.objects.get(billing_profile=o, kind="refund")
        self.assertEqual((original.amount, original.status, refund.amount, refund.refund_of_id),
                         (D("20000"), "confirmed", D("3000"), original.pk))
        self.assertEqual(contracts.money_summary(o)["credit"], D("2000"))

    def test_10_receipts(self):
        """10. Чек на каждый платёж, номер уникален, печать не создаёт платежей."""
        demo_payments = demo.registered(StudentPayment)
        self.assertEqual(demo_payments.count(), 19)
        numbers = [p.receipt.number for p in demo_payments]
        self.assertEqual(len(set(numbers)), len(numbers))
        payment = StudentPayment.objects.get(billing_profile=profile("D"), purpose="tuition")
        snap = payment.receipt.snapshot
        self.assertEqual((snap["amount"], snap["previously_paid"], snap["outstanding"], snap["student"]),
                         ("12000.00", "3000.00", "45000.00", "Бронев Данияр"))
        accountant = demo.lookup("user:accountant")
        before = (StudentPayment.objects.count(), Receipt.objects.count())
        for _ in range(2):
            response = api(accountant).get(BASE + f"receipts/{payment.receipt.pk}/pdf/")
            self.assertEqual((response.status_code, response.content[:4]), (200, b"%PDF"))
        self.assertEqual((StudentPayment.objects.count(), Receipt.objects.count()), before)

    def test_11_roles(self):
        """11. Директор не изменяет; менеджер не корректирует платежи; бухгалтер работает."""
        p = profile("F")
        invoice = live_invoices(p)[0]
        payment = StudentPayment.objects.filter(billing_profile=p).first()
        body = {"profile": p.pk, "amount": "1000", "received_date": str(self.today)}
        director, manager, accountant = (demo.lookup(f"user:{k}") for k in ("director", "manager", "accountant"))
        self.assertEqual(api(director).get(BASE + "queues/overdue/").status_code, 200)
        self.assertEqual(api(director).post(BASE + "payments/", body, format="json").status_code, 403)
        self.assertEqual(api(director).post(BASE + f"payments/{payment.pk}/reverse/", {"reason": "x"},
                                            format="json").status_code, 403)
        self.assertEqual(api(manager).post(BASE + f"payments/{payment.pk}/reverse/", {"reason": "x"},
                                           format="json").status_code, 403)
        self.assertEqual(api(manager).get(BASE + "queues/all/").status_code, 200)
        response = api(accountant).post(BASE + "payments/", {**body, "amount": "7000", "mode": "invoice",
                                                             "invoice": invoice.pk}, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, "PAID")

    def test_13_analytics_matches_operations(self):
        """13. Аналитика = суммы тестовых операций (полученное ≠ стоимость курсов)."""
        start = dt.date.fromisoformat(self.result["start"])
        report = analytics.finance_analytics({}, date_from=start - dt.timedelta(days=30), date_to=self.today)
        demo_payments = demo.registered(StudentPayment).filter(status="confirmed")
        gross = sum(p.amount for p in demo_payments.filter(kind="payment"))
        self.assertEqual(gross, D("306000"))  # не 15 × стоимость курса
        self.assertEqual(report["received"]["gross"], f"{gross:.2f}")
        self.assertEqual((report["received"]["refunds"], report["received"]["net"]), ("3000.00", f"{gross - 3000:.2f}"))
        self.assertEqual(report["reservations"], "6000.00")  # D и E, по одному разу
        self.assertEqual(report["discounts"]["amount"], "27000.00")  # C 15 000 + L 12 000
        self.assertEqual(report["prepayment"], "60000.00")  # A — предоплата за весь курс
        # Долг на конец периода — только начисления, срок которых наступил (E, G, M);
        # выставленное, но ещё в сроке (B, F, I, L) — «к оплате», а не долг.
        overdue = sum(contracts.money_summary(profile(k))["due_now"] for k in ("E", "G", "M"))
        self.assertEqual(report["debt_end"], f"{overdue:.2f}")
        self.assertEqual(overdue, D("37000"))
        due = sum(contracts.money_summary(profile(sc.key))["due_now"] for sc in demo.SCENARIOS)
        self.assertEqual(due, D("86000"))
        self.assertEqual(report["expected"]["overdue_count"], 3)
        credit = sum(contracts.money_summary(profile(sc.key))["credit"] for sc in demo.SCENARIOS)
        self.assertEqual(credit, D("23750"))  # C 3 750 + K 15 000 + N 3 000 + O 2 000

    def test_passwords_are_local_only(self):
        result = demo.set_passwords("Demo-Only-123")
        self.assertEqual(set(result), {"demo_accountant", "demo_manager", "demo_director"})
        self.assertTrue(demo.lookup("user:accountant").check_password("Demo-Only-123"))
        with mock.patch.dict(os.environ, {"DJANGO_ENV": "production"}):
            with self.assertRaises(demo.DemoError):
                demo.set_passwords()
            with self.assertRaises(demo.DemoError):
                demo.seed()


class DemoResetTests(TestCase):
    def counts(self) -> dict:
        skip = {"accounting.DemoSeedRecord", "contenttypes.ContentType", "auth.Permission", "auth.Group",
                "billing.BillingSettings", "sessions.Session"}
        return {m._meta.label: m._base_manager.count() for m in django_apps.get_models()
                if m._meta.label not in skip and not m._meta.proxy}

    def real_data(self):
        """Реальные данные, которые очистка не должна тронуть."""
        from apps.billing.services import pricing, profiles

        BillingSettings.load()
        accountant = User.objects.create_user(username="real_buh", email="real@x.kg", password="Str0ngPassw0rd!",
                                              role=User.Role.ACCOUNTANT, is_verified=True)
        course = Course.objects.create(name="Real Course", count_lesson=48)
        group = Group.objects.create(name="Real group", course=course, start_date=timezone.localdate())
        student = Student.objects.create(first_name="Реальный", last_name="Студент", group=group,
                                         enrollment_date=timezone.localdate())
        plan = pricing.create_plan(actor=accountant, name="Real plan", lessons_per_package=12, package_price="5000",
                                   effective_from=timezone.localdate(), course=course)
        real = profiles.create_student_billing_profile(student=student, plan=plan, actor=accountant)
        payments.record_payment(profile=real, amount="5000", received_date=timezone.localdate(), actor=accountant)
        return accountant, real

    def test_12_reset_removes_only_demo_data(self):
        """12. Reset удаляет только демо-данные (включая платёж, внесённый вручную)."""
        _accountant, real = self.real_data()
        before = self.counts()
        demo.seed()
        # Проверка интерфейса: бухгалтер вносит платёж демо-студенту — это тоже демо.
        payments.record_payment(profile=profile("B"), amount="1000", received_date=timezone.localdate(),
                                actor=demo.lookup("user:accountant"))
        with self.assertRaises(CommandError):
            call_command("reset_billing_demo", stdout=io.StringIO())  # без --confirm ничего не делает
        call_command("reset_billing_demo", "--dry-run", stdout=io.StringIO())
        self.assertTrue(demo.exists())
        call_command("reset_billing_demo", "--confirm", stdout=io.StringIO())
        self.assertFalse(demo.exists())
        self.assertEqual(self.counts(), before)
        real.refresh_from_db()
        self.assertEqual(StudentPayment.objects.filter(billing_profile=real).count(), 1)
        demo.seed()  # после очистки создаётся заново
        self.assertEqual(StudentBillingProfile.objects.filter(student__last_name="Тестов").count(), 1)

    def test_reset_stops_when_real_data_depends_on_demo(self):
        _accountant, real = self.real_data()
        demo.seed()
        # Реальный платёж принят под демо-бухгалтером — очистка не должна его удалить.
        payments.record_payment(profile=real, amount="100", received_date=timezone.localdate(),
                                actor=demo.lookup("user:accountant"))
        before = self.counts()
        with self.assertRaises(demo.DemoError):
            demo.reset()
        self.assertEqual(self.counts(), before)
        self.assertTrue(demo.exists())
