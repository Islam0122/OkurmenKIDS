"""Очистка данных бухгалтерии через Django Admin (только суперпользователь)."""
from __future__ import annotations

import json
from unittest import mock

from django.core.exceptions import ValidationError
from django.urls import reverse

from apps.academy.models import Course, Group, Lesson, Student
from apps.accounting.models import (
    CourseCycle,
    CoursePayrollSettings,
    CoursePriceVersion,
    CycleAccrual,
    CycleLesson,
    EmployeeSalaryProfile,
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
from apps.accounting.services import AccountingError, maintenance
from apps.accounting.services.approval_service import approve_payroll, create_adjustment
from apps.accounting.services.payment_service import register_payment
from apps.accounting.services.pricing import set_price
from apps.accounting.services.salary_rules import new_version
from apps.accounting.tests.base import FIRST, D, AccountingFixture, day, make_user
from apps.users.models import Subject, Teacher, User

R = SalaryRule.RuleType
URL = reverse("admin:accounting_maintenance_purge")

PAYROLL_MODELS = (CycleAccrual, PayrollAuditLog, PayrollPayment, PayrollAdjustment, PayrollLine, Payroll, PayrollPeriod)
KEPT_IN_A = (SalaryRule, EmployeeSalaryProfile, CourseCycle, CoursePayrollSettings, StudentPayment, CycleLesson,
             CoursePriceVersion)


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
        payroll = approve_payroll(self.calc(FIRST), self.director)
        register_payment(payroll, amount=D("1000"), payment_date=day(9, 20), actor=self.accountant)
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
        self.assertEqual(record.old_values["deleted"]["payrollpayment"], 1)
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
        reordered = (maintenance.PAYROLL_TABLES[5],) + maintenance.PAYROLL_TABLES  # расчёты раньше выплат
        with mock.patch.object(maintenance, "PAYROLL_TABLES", reordered), self.assertRaises(Exception):
            maintenance.purge(maintenance.PAYROLL, actor=self.superuser)
        self.assertEqual((n(Payroll), n(PayrollPayment), n(CycleAccrual)), (1, 1, 1))

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
