"""Бухгалтерия — изолированная зона: бухгалтер не пользователь LMS.

Запросы идут с настоящим JWT (как у фронтенда) и с сессией (как в Django
admin) — `force_authenticate` обходит middleware и здесь не годится.
"""
from __future__ import annotations

from django.contrib.auth.models import Group, Permission
from django.test import override_settings
from rest_framework.test import APIClient

from apps.accounting.access import ACCOUNTANT_GROUP
from apps.accounting.models import SalaryRule
from apps.accounting.services.approval_service import approve_payroll
from apps.accounting.tests.base import FIRST, D, AccountingFixture, day, make_user
from apps.users.models import User

PASSWORD = "Str0ngPassw0rd!"

LMS_ENDPOINTS = (
    "/api/v1/students/",
    "/api/v1/groups/",
    "/api/v1/courses/",
    "/api/v1/programs/",
    "/api/v1/lessons/",
    "/api/v1/attendance/",
    "/api/v1/homework/",
    "/api/v1/homework-results/",
    "/api/v1/trainers/",
    "/api/v1/subjects/",
    "/api/v1/rooms/",
    "/api/v1/schedule/board/",
    "/api/v1/analytics/dashboard/",
    "/api/v1/reports/students/",
    "/api/v1/control/",
    "/api/v1/teacher/news/",
    "/api/v1/worklog/entries/",
    "/api/v1/assistant/students/",
    "/api/v1/assistant/dashboard/",
    "/api/v1/scholarships/periods/",
    "/swagger-ui/",
    "/schema/",
)


class AccountantIsolationTests(AccountingFixture):
    def setUp(self):
        super().setUp()
        self.student_obj = self.student()
        self.rule(self.profile(salary_type="PERCENT"), SalaryRule.RuleType.PERCENT, percentage=D("10"))
        self.course_settings(price="10000", lessons=2)
        self.lessons(self.group_a, [day(9, 1), day(9, 2)])
        self.payroll = self.calc(FIRST)

    def jwt(self, user) -> APIClient:
        client = APIClient()
        response = client.post("/api/v1/auth/login/", {"username": user.username, "password": PASSWORD}, format="json")
        self.assertEqual(response.status_code, 200, response.content)
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {response.json()['access']}")
        return client

    def test_accountant_can_open_accounting(self):
        client = self.jwt(self.accountant)
        for url in ("/api/v1/accounting/dashboard/", "/api/v1/accounting/payrolls/",
                    f"/api/v1/accounting/payrolls/{self.payroll.pk}/", "/api/v1/accounting/employees/",
                    "/api/v1/auth/me/"):
            self.assertEqual(client.get(url).status_code, 200, url)
        self.assertEqual(client.get("/api/v1/auth/me/").json()["role"], "accountant")

    def test_accountant_cannot_open_lms(self):
        client = self.jwt(self.accountant)
        for url in LMS_ENDPOINTS:
            response = client.get(url)
            self.assertEqual(response.status_code, 403, url)
        self.assertEqual(client.get("/api/v1/groups/").json()["code"], "accounting_only")

    def test_accountant_cannot_read_students_by_id_or_write(self):
        client = self.jwt(self.accountant)
        sid = self.student_obj.pk
        for url in (f"/api/v1/students/{sid}/", f"/api/v1/assistant/students/{sid}/",
                    f"/api/v1/groups/{self.group_a.pk}/", f"/api/v1/assistant/control/students/{sid}/"):
            self.assertEqual(client.get(url).status_code, 403, url)
        self.assertEqual(client.patch(f"/api/v1/students/{sid}/", {"first_name": "X"}, format="json").status_code, 403)
        self.assertEqual(client.post("/api/v1/students/", {"first_name": "X"}, format="json").status_code, 403)

    def test_accounting_api_exposes_students_only_as_aggregate(self):
        client = self.jwt(self.accountant)
        line = client.get(f"/api/v1/accounting/payrolls/{self.payroll.pk}/").json()["lines"][0]
        self.assertEqual(line["metadata"]["students_count"], 1)
        self.assertNotIn("students", line["metadata"])
        self.assertNotIn(self.student_obj.first_name, str(line))
        found = client.get("/api/v1/accounting/students/?search=Student").json()
        self.assertEqual(set(found[0]), {"id", "name", "group", "group_name"})
        self.assertEqual(client.get("/api/v1/accounting/students/?search=S").json(), [])

    def test_accountant_cannot_access_django_admin(self):
        self.client.force_login(self.accountant)
        for url in ("/admin/", "/admin/accounting/payroll/", "/admin/users/user/", "/admin/academy/student/"):
            self.assertEqual(self.client.get(url).status_code, 403, url)
        self.client.logout()
        response = self.client.post("/admin/login/?next=/admin/", {"username": "buh", "password": PASSWORD})
        self.assertEqual(response.status_code, 200)  # форма входа снова — не staff
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_accountant_cannot_see_others_financial_data_beyond_rights(self):
        client = self.jwt(self.accountant)
        # Утверждение и закрытие периода — не его полномочия.
        self.assertEqual(client.post(f"/api/v1/accounting/payrolls/{self.payroll.pk}/approve/").status_code, 403)
        # Личный кабинет показывает только собственные начисления.
        approve_payroll(self.payroll, self.director)
        self.assertEqual(client.get("/api/v1/accounting/my/payrolls/").json()["count"], 0)
        self.assertEqual(client.get(f"/api/v1/accounting/my/payrolls/{self.payroll.pk}/").status_code, 404)
        # Тренер — наоборот, видит только своё и никакой бухгалтерии.
        trainer = self.jwt(self.trainer_user)
        self.assertEqual(trainer.get("/api/v1/accounting/payrolls/").status_code, 403)
        self.assertEqual(trainer.get("/api/v1/accounting/my/payrolls/").json()["count"], 1)

    def test_accountant_cannot_raise_own_privileges(self):
        client = self.jwt(self.accountant)
        self.assertEqual(client.patch("/api/v1/auth/me/", {"role": "admin"}, format="json").status_code, 405)
        self.assertEqual(client.post("/api/v1/trainers/", {}, format="json").status_code, 403)
        # Ни сохранение с флагами, ни выданные «лишние» права не переживают save().
        self.accountant.is_staff = self.accountant.is_superuser = True
        self.accountant.save()
        self.accountant.user_permissions.add(Permission.objects.get(codename="change_user"))
        self.accountant.groups.add(Group.objects.create(name="Extra"))
        self.accountant.save()
        fresh = User.objects.get(pk=self.accountant.pk)
        self.assertFalse(fresh.is_staff or fresh.is_superuser)
        self.assertEqual(list(fresh.groups.values_list("name", flat=True)), [ACCOUNTANT_GROUP])
        self.assertFalse(fresh.user_permissions.exists())
        self.assertFalse(fresh.has_perm("users.change_user"))
        self.assertFalse(fresh.has_perm("accounting.delete_payrollpayment"))
        self.assertTrue(fresh.has_perm("accounting.add_payrollpayment"))


class AccountantGroupTests(AccountingFixture):
    def test_group_has_only_financial_permissions(self):
        group = Group.objects.get(name=ACCOUNTANT_GROUP)
        codenames = set(group.permissions.values_list("content_type__app_label", "codename"))
        self.assertTrue(codenames)
        self.assertTrue(all(app == "accounting" for app, _ in codenames))
        self.assertFalse(any(code.startswith("delete_") for _, code in codenames))
        self.assertIn(("accounting", "view_payrollauditlog"), codenames)
        self.assertNotIn(("accounting", "change_payrollauditlog"), codenames)
        self.assertNotIn(("accounting", "add_payrollauditlog"), codenames)

    def test_group_follows_role(self):
        user = make_user("future", User.Role.ASSISTANT)
        self.assertFalse(user.groups.filter(name=ACCOUNTANT_GROUP).exists())
        user.role = User.Role.ACCOUNTANT
        user.save()
        self.assertTrue(user.groups.filter(name=ACCOUNTANT_GROUP).exists())
        user.role = User.Role.TEACHER
        user.save()
        self.assertFalse(user.groups.filter(name=ACCOUNTANT_GROUP).exists())

    def test_without_group_permissions_accountant_has_no_access(self):
        Group.objects.get(name=ACCOUNTANT_GROUP).permissions.clear()
        client = APIClient()
        client.force_authenticate(User.objects.get(pk=self.accountant.pk))
        self.assertEqual(client.get("/api/v1/accounting/payrolls/").status_code, 403)

    @override_settings(ACCOUNTING_ISOLATED_ROLES=("accountant", "director"))
    def test_isolation_roles_are_configurable(self):
        client = APIClient()
        token = client.post("/api/v1/auth/login/", {"username": "boss", "password": PASSWORD}, format="json").json()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {token['access']}")
        self.assertEqual(client.get("/api/v1/groups/").status_code, 403)
        self.assertEqual(client.get("/api/v1/accounting/dashboard/").status_code, 200)

    def test_other_roles_keep_lms_access(self):
        client = APIClient()
        token = client.post("/api/v1/auth/login/", {"username": "root", "password": PASSWORD}, format="json").json()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {token['access']}")
        self.assertEqual(client.get("/api/v1/groups/").status_code, 200)
