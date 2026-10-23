"""Очистка данных бухгалтерии через Django Admin (только суперпользователь)."""
from __future__ import annotations

import json
from unittest import mock

from django.core.exceptions import ValidationError
from django.urls import reverse

from apps.academy.models import Course, Group, Lesson, Student
from apps.accounting.models import (
    AppliedDeduction,
    CourseCycle,
    CoursePayrollSettings,
    CoursePriceVersion,
    CycleAccrual,
    CycleLesson,
    DeductionAllocation,
    DeductionRule,
    EmployeeSalaryProfile,
    PayoutPlan,
    PayoutPlanLine,
    Payroll,
    PayrollAdjustment,
    PayrollAuditLog,
    PayrollLine,
    PayrollPayment,
    PayrollPeriod,
    SalaryRule,
    SalaryType,
    StudentPayment,
)
from apps.accounting.services import AccountingError, deductions, maintenance, payout_plans
from apps.accounting.services.approval_service import approve_payroll, create_adjustment
from apps.accounting.services.payment_service import register_payment
from apps.accounting.services.pricing import set_price
from apps.accounting.services.salary_rules import new_version
from apps.accounting.tests.base import FIRST, AccountingFixture, D, day, make_user
from apps.users.models import Subject, Teacher, User

R = SalaryRule.RuleType
URL = reverse("admin:accounting_maintenance_purge")

PAYROLL_MODELS = (CycleAccrual, PayrollAuditLog, PayrollPayment, PayoutPlanLine, PayoutPlan, DeductionAllocation,
                  AppliedDeduction, PayrollAdjustment, PayrollLine, Payroll, PayrollPeriod)
KEPT_IN_A = (SalaryRule, EmployeeSalaryProfile, CourseCycle, CoursePayrollSettings, StudentPayment, CycleLesson,
             CoursePriceVersion, DeductionRule)


def n(model) -> int:
    return model._base_manager.count()


class PurgeFixture(AccountingFixture):
    def setUp(self):
        super().setUp()
        settings = self.course_settings(price="10000", lessons=12, start=None)
        settings.counted_subjects.set([self.python])
        set_price(course=self.course, price_per_student=D("10000"), effective_from=day(1, 1), reason="a",
                  actor=self.accountant)
        set_price(course=self.course, price_per_student=D("11000"), effective_from=day(2, 1), reason="b",
                  actor=self.accountant)  # цепочка версий тарифа
        profile = self.profile(salary_type=SalaryType.PERCENT)
        rule = self.rule(profile, R.PERCENT, percentage=D("10"))
        new_version(rule, actor=self.accountant, changes={"effective_from": day(3, 1)})  # цепочка версий правила
        kids = [self.student(self.group_a) for _ in range(5)]
        with self.captureOnCommitCallbacks(execute=True):
            self.lessons(self.group_a, [day(9, d) for d in range(1, 13)])
        deductions.create_rule(actor=self.accountant, name="Налог", kind="TAX", amount=D("100"), frequency="MONTHLY",
                               scope="EMPLOYEE", employee=self.trainer_user, effective_from=day(1, 1))
        payroll = approve_payroll(self.calc(FIRST), self.director)
        register_payment(payroll, amount=D("1000"), payment_date=day(9, 20), actor=self.accountant)
        plan = payout_plans.approve_plan(payout_plans.create_plan(
            actor=self.accountant, title="15 сентября", year=2026, month=9, payout_date=day(9, 15),
            lines=[{"payroll": payroll}]), actor=self.accountant)
        payout_plans.pay_line(plan.lines.get(), actor=self.accountant, amount=D("100"), payment_date=day(9, 21),
                              payment_method="bank")  # выплата по плану ссылается на строку плана (PROTECT)
        create_adjustment(payroll, kind="BONUS", amount=D("100"), reason="премия", actor=self.accountant)
        paid = self.pay(kids[0], "10000", day(9, 1))
        self.refund(paid, "2000", day(9, 5))
        self.superuser = self.admin
        self.lms = {"lessons": Lesson.objects.count(), "students": Student.objects.count(),
                    "groups": Group.objects.count(), "courses": Course.objects.count(),
                    "subjects": Subject.objects.count(), "teachers": Teacher.objects.count(),
                    "users": User.objects.count()}

    def assert_lms_untouched(self):
        self.assertEqual(self.lms, {"lessons": Lesson.objects.count(), "students": Student.objects.count(),
                                    "groups": Group.objects.count(), "courses": Course.objects.count(),
                                    "subjects": Subject.objects.count(), "teachers": Teacher.objects.count(),
                                    "users": User.objects.count()})

    def post(self, user=None, **data):
        client = self.client_class()
        client.force_login(user or self.superuser)
        snapshot = json.dumps(maintenance.preview(), sort_keys=True)
        body = {"snapshot": snapshot, "confirm_phrase": "DELETE ACCOUNTING", "backup_confirmed": "on", **data}
        return client.post(URL, body, follow=True)


class ServiceTests(PurgeFixture):
    def test_fixture_has_data_everywhere(self):
        for model in PAYROLL_MODELS + KEPT_IN_A:
            self.assertGreater(n(model), 0, model)

    def test_mode_a_deletes_only_payroll(self):
        kept = {m: n(m) for m in KEPT_IN_A}
        deleted = maintenance.purge(maintenance.PAYROLL, actor=self.superuser)
        self.assertEqual(deleted["payroll"], 1)
        for model in PAYROLL_MODELS:
            if model is PayrollAuditLog:
                continue
            self.assertEqual(n(model), 0, model)
        self.assertEqual({m: n(m) for m in KEPT_IN_A}, kept)
        [record] = PayrollAuditLog.objects.all()  # журнал очищен, остаётся запись о самой операции
        self.assertEqual((record.action, record.actor), ("purge_payroll", self.superuser))
        self.assertEqual(record.old_values["deleted"]["payrollpayment"], 2)
        self.assertEqual(record.old_values["deleted"]["payoutplan"], 1)
        self.assert_lms_untouched()

    def test_mode_a_then_recalculation_recreates_accruals_for_kept_cycles(self):
        maintenance.purge(maintenance.PAYROLL, actor=self.superuser)
        self.assertEqual(self.calc(FIRST).total_accrued, D("5500.00"))
        self.assertEqual(CycleAccrual.objects.count(), 1)

    def test_mode_b_deletes_all_accounting_but_keeps_tariffs_by_default(self):
        maintenance.purge(maintenance.FULL, actor=self.superuser)
        for model in PAYROLL_MODELS + KEPT_IN_A:
            if model in (PayrollAuditLog, CoursePriceVersion):
                continue
            self.assertEqual(n(model), 0, model)
        self.assertEqual(CoursePayrollSettings.counted_subjects.through.objects.count(), 0)
        self.assertEqual(n(CoursePriceVersion), 2)
        self.assertEqual(PayrollAuditLog.objects.get().action, "purge_full")
        self.assert_lms_untouched()

    def test_mode_b_with_tariffs(self):
        maintenance.purge(maintenance.FULL, actor=self.superuser, include_tariffs=True)
        self.assertEqual(n(CoursePriceVersion), 0)
        self.assert_lms_untouched()

    def test_only_superuser(self):
        for user in (self.accountant, self.director, make_user("staff", User.Role.ADMIN, is_staff=True)):
            with self.assertRaises(AccountingError):
                maintenance.purge(maintenance.FULL, actor=user)
        self.assertEqual(n(Payroll), 1)

    def test_any_error_rolls_back_everything(self):
        real = maintenance._delete

        def failing(table):
            if table.model is Payroll:
                raise RuntimeError("сбой посреди очистки")
            real(table)

        with mock.patch.object(maintenance, "_delete", side_effect=failing), self.assertRaises(RuntimeError):
            maintenance.purge(maintenance.FULL, actor=self.superuser)
        for model in PAYROLL_MODELS + KEPT_IN_A:
            self.assertGreater(n(model), 0, model)

    def test_wrong_order_is_caught_by_protect_and_rolled_back(self):
        payroll_table = next(t for t in maintenance.PAYROLL_TABLES if t.model is Payroll)
        reordered = (payroll_table,) + maintenance.PAYROLL_TABLES  # расчёты раньше выплат
        with mock.patch.object(maintenance, "PAYROLL_TABLES", reordered), self.assertRaises(Exception):
            maintenance.purge(maintenance.PAYROLL, actor=self.superuser)
        self.assertEqual((n(Payroll), n(PayrollPayment), n(CycleAccrual)), (1, 2, 1))

    def test_financial_records_stay_undeletable_outside_maintenance(self):
        with self.assertRaises(ValidationError):
            PayrollPayment.objects.all().delete()
        with self.assertRaises(ValidationError):
            PayrollAuditLog.objects.all().delete()


class AdminViewTests(PurgeFixture):
    def test_page_shows_counts_and_warning_to_superuser(self):
        self.client.force_login(self.superuser)
        r = self.client.get(URL)
        self.assertEqual(r.status_code, 200)
        content = r.content.decode()
        for text in ("Операция необратима без резервной копии", "Режим A", "Режим B", "accounting_cyclelesson",
                     "accounting_studentpayment", "DELETE ACCOUNTING", "FULL RESET", "accounting_coursepriceversion"):
            self.assertIn(text, content)
        row = [m for m in r.context["modes"] if m["key"] == "PAYROLL"][0]["delete"]
        self.assertEqual({x["db_table"]: x["count"] for x in row}["accounting_payroll"], 1)

    def test_hidden_and_forbidden_for_everyone_else(self):
        staff = make_user("staffadmin", User.Role.ADMIN, is_staff=True)
        self.client.force_login(staff)
        self.assertEqual(self.client.get(URL).status_code, 403)
        self.assertNotIn(URL, self.client.get(reverse("admin:index")).content.decode())
        self.client.force_login(self.superuser)
        self.assertIn(URL, self.client.get(reverse("admin:index")).content.decode())
        self.client.force_login(self.accountant)
        self.assertEqual(self.client.get(URL).status_code, 403)
        self.client.logout()
        self.assertEqual(self.client.get(URL).status_code, 302)  # на вход в админку
        self.assertEqual(n(Payroll), 1)

    def test_post_from_non_superuser_deletes_nothing(self):
        staff = make_user("staffadmin2", User.Role.ADMIN, is_staff=True)
        self.assertEqual(self.post(staff, mode="FULL", full_phrase="FULL RESET").status_code, 403)
        self.assertEqual(n(Payroll), 1)

    def test_confirmations_are_required(self):
        self.post(mode="PAYROLL", confirm_phrase="delete accounting")
        self.post(mode="PAYROLL", backup_confirmed="")
        self.post(mode="FULL")  # без FULL RESET
        self.post(mode="FULL", full_phrase="full reset")
        self.assertEqual((n(Payroll), n(SalaryRule)), (1, 2))
        r = self.post(mode="FULL")
        self.assertContains(r, "Для полной очистки введите ровно")

    def test_stale_counts_block_deletion(self):
        client = self.client_class()
        client.force_login(self.superuser)
        stale = json.dumps(maintenance.preview(), sort_keys=True)
        self.pay(Student.objects.first(), "500", day(9, 9))
        r = client.post(URL, {"mode": "PAYROLL", "snapshot": stale, "confirm_phrase": "DELETE ACCOUNTING",
                              "backup_confirmed": "on"}, follow=True)
        self.assertContains(r, "Количество записей изменилось")
        self.assertEqual(n(Payroll), 1)

    def test_successful_mode_a_and_b(self):
        r = self.post(mode="PAYROLL")
        self.assertContains(r, "Удалено записей")
        self.assertEqual((n(Payroll), n(SalaryRule)), (0, 2))
        r = self.post(mode="FULL", full_phrase="FULL RESET", include_tariffs="on")
        self.assertContains(r, "Удалено записей")
        self.assertEqual((n(SalaryRule), n(StudentPayment), n(CoursePriceVersion)), (0, 0, 0))
        self.assert_lms_untouched()


class BillingResetTests(PurgeFixture):
    """Полная очистка включает оплату обучения (apps.billing) и не трогает LMS."""

    def setUp(self):
        super().setUp()
        from apps.billing.services import payments as billing_payments
        from apps.billing.services import pricing, profiles

        self.plan = pricing.create_plan(actor=self.accountant, name="Тариф по ошибке", lessons_per_package=12,
                                        package_price="15000", effective_from=day(1, 1), course=self.course)
        pricing.add_plan_version(self.plan, actor=self.accountant, lessons_per_package=12, package_price="16000",
                                 effective_from=day(2, 1), reason="цепочка версий")
        student = self.student(self.group_a)
        # Договор с октября: сентябрьские уроки группы (фикстура зарплат) — до его начала.
        self.contract = profiles.create_student_billing_profile(student=student, plan=self.plan, actor=self.accountant,
                                                                start_date=day(10, 1))
        paid, _ = billing_payments.record_payment(profile=self.contract, amount="20000", received_date=day(10, 1),
                                                  actor=self.accountant)
        billing_payments.refund_payment(paid, actor=self.accountant, amount="1000", reason="переплата")
        self.lms = {**self.lms, "students": Student.objects.count()}

    def billing_counts(self):
        from apps.billing.models import BillingPlan, Invoice, Receipt, StudentBillingProfile

        return (n(StudentBillingProfile), n(Invoice), n(Receipt), n(StudentPayment), n(BillingPlan))

    def test_full_reset_removes_billing_and_keeps_lms_and_settings(self):
        from apps.billing.models import BillingPlan, BillingPlanVersion, BillingSettings

        BillingSettings.load()
        self.assertTrue(all(self.billing_counts()))
        deleted = maintenance.purge(maintenance.FULL, actor=self.superuser)
        self.assertEqual(self.billing_counts()[:4], (0, 0, 0, 0))
        self.assertEqual((n(BillingPlan), n(BillingPlanVersion)), (1, 2))  # тарифы — только по флажку
        self.assertEqual(deleted["studentbillingprofile"], 1)
        self.assertEqual(n(BillingSettings), 1)
        self.assert_lms_untouched()
        maintenance.purge(maintenance.FULL, actor=self.superuser, include_tariffs=True)
        self.assertEqual((n(BillingPlan), n(BillingPlanVersion), n(CoursePriceVersion)), (0, 0, 0))
        self.assert_lms_untouched()

    def test_nothing_outside_accounting_references_it(self):
        self.assertEqual(maintenance.external_references(), [])

    def test_command_audit_changes_nothing_and_execute_needs_backup_and_phrase(self):
        import io
        import tempfile

        from django.core.management import call_command
        from django.core.management.base import CommandError

        before = (self.billing_counts(), maintenance.preview())
        out = io.StringIO()
        call_command("reset_accounting", stdout=out)
        self.assertIn("только аудит", out.getvalue())
        self.assertIn("Тариф по ошибке", out.getvalue())
        self.assertEqual((self.billing_counts(), maintenance.preview()), before)
        with self.assertRaises(CommandError):
            call_command("reset_accounting", "--execute", "--actor", self.superuser.username, stdout=io.StringIO())
        with self.assertRaises(CommandError):  # без копии — нельзя
            call_command("reset_accounting", "--execute", "--actor", self.superuser.username,
                         "--confirm", maintenance.CONFIRM_PHRASE, stdout=io.StringIO())
        self.assertEqual(self.billing_counts(), before[0])
        with tempfile.TemporaryDirectory() as folder:
            backup = f"{folder}/db.dump"
            with open(backup, "wb") as fh:
                fh.write(b"existing full backup")
            call_command("reset_accounting", "--execute", "--actor", self.superuser.username, "--confirm",
                         maintenance.CONFIRM_PHRASE, "--backup-dir", folder, "--db-backup-file", backup,
                         "--include-tariffs", stdout=io.StringIO())
            import glob
            import json as _json

            [dump] = glob.glob(f"{folder}/accounting-billing-*.json")
            labels = {row["model"] for row in _json.load(open(dump, encoding="utf-8"))}
            self.assertIn("billing.studentbillingprofile", labels)
        self.assertEqual(self.billing_counts(), (0, 0, 0, 0, 0))
        self.assert_lms_untouched()
        self.assertEqual(PayrollAuditLog.objects.get().action, "purge_full")
