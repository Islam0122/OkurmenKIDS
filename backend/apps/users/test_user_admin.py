"""Simplified User admin: the role is the access.

Create / edit a user through the real Django admin, check the form has no
groups / per-user permissions, that a Team Lead never becomes superuser or
staff, that role changes take effect immediately, and that the other roles
keep their access.
"""
from __future__ import annotations

import datetime as dt

from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from apps.academy.models import Course, Group, GroupTeacher, Student
from apps.users.admin import UserAddForm, UserEditForm
from apps.users.models import Subject, Teacher, User

PASSWORD = "Str0ngPassw0rd!"


class UserAdminTestBase(TestCase):
    def setUp(self):
        self.superuser = User.objects.create_superuser(
            username="root", email="root@okurmen.kg", password=PASSWORD, first_name="Root"
        )
        self.web = self.client_class()
        self.web.force_login(self.superuser)

    def add_user(self, **overrides):
        data = {
            "first_name": "Нурлан",
            "last_name": "Асанов",
            "username": "nurlan",
            "email": "nurlan@okurmen.kg",
            "password1": PASSWORD,
            "password2": PASSWORD,
            "role": User.Role.TEAM_LEAD,
            "is_verified": "on",
            "is_active": "on",
            **overrides,
        }
        return self.web.post(reverse("admin:users_user_add"), data)

    def change_data(self, user: User, **overrides) -> dict:
        data = {
            "first_name": user.first_name,
            "last_name": user.last_name,
            "username": user.username,
            "email": user.email,
            "role": user.role,
            "is_active": "on" if user.is_active else "",
            "is_verified": "on" if user.is_verified else "",
            **overrides,
        }
        return {key: value for key, value in data.items() if value != ""}


class UserAdminFormTests(UserAdminTestBase):
    def test_add_form_is_simple(self):
        response = self.web.get(reverse("admin:users_user_add"))
        self.assertEqual(response.status_code, 200)
        form = response.context["adminform"].form
        for name in ("first_name", "last_name", "username", "email", "password1", "password2", "role", "is_verified", "is_active"):
            self.assertIn(name, form.fields)
        for name in ("groups", "user_permissions", "usable_password"):
            self.assertNotIn(name, form.fields)
        self.assertTrue(form.fields["role"].required)
        self.assertNotContains(response, "Сначала введите имя пользователя и пароль")
        labels = dict(form.fields["role"].choices)
        self.assertEqual(labels[User.Role.TEAM_LEAD], "👨‍🏫 Team Lead — руководитель тренеров")
        self.assertEqual(labels[User.Role.TEACHER], "👨‍💻 Тренер")
        self.assertEqual(labels[User.Role.ADMIN], "👑 Администратор")
        # Only the roles that really exist — no invented Director/Assistant/…
        self.assertEqual(set(labels) - {""}, set(User.Role.values))
        self.assertNotContains(response, "Can add")

    def test_change_form_has_no_groups_and_no_permissions_list(self):
        teacher = User.objects.create_user(username="t", email="t@okurmen.kg", password=PASSWORD, first_name="T")
        response = self.web.get(reverse("admin:users_user_change", args=[teacher.pk]))
        self.assertEqual(response.status_code, 200)
        form = response.context["adminform"].form
        self.assertNotIn("groups", form.fields)
        self.assertNotIn("user_permissions", form.fields)
        self.assertNotContains(response, "Доступные права пользователя")
        self.assertNotContains(response, "Can add")
        self.assertIn("role", form.fields)
        self.assertIn("password", form.fields)  # the «change password» link stays

    def test_form_classes_never_declare_groups_or_permissions(self):
        self.assertNotIn("groups", UserAddForm.base_fields)
        self.assertNotIn("user_permissions", UserAddForm.base_fields)
        self.assertNotIn("groups", UserEditForm.base_fields)
        self.assertNotIn("user_permissions", UserEditForm.base_fields)
        fields = self.non_superuser_form_fields()
        for name in ("groups", "user_permissions", "is_superuser", "is_staff"):
            self.assertNotIn(name, fields)

    def non_superuser_form_fields(self):
        manager = User.objects.create_user(
            username="manager", email="manager@okurmen.kg", password=PASSWORD, first_name="M",
            role=User.Role.ADMIN, is_staff=True,
        )
        manager.user_permissions.add(*Permission.objects.filter(codename__in=["view_user", "change_user", "add_user"]))
        web = self.client_class()
        web.force_login(manager)
        response = web.get(reverse("admin:users_user_add"))
        self.assertEqual(response.status_code, 200)
        return response.context["adminform"].form.fields

    def test_non_superuser_cannot_grant_admin_role(self):
        fields = self.non_superuser_form_fields()
        self.assertNotIn(User.Role.ADMIN, dict(fields["role"].choices))


class CreateTeamLeadTests(UserAdminTestBase):
    def test_create_team_lead_by_role_only(self):
        permissions_before = Permission.objects.count()
        response = self.add_user()
        self.assertEqual(response.status_code, 302, response.content.decode()[:2000])
        user = User.objects.get(username="nurlan")
        self.assertEqual(user.role, User.Role.TEAM_LEAD)
        self.assertFalse(user.is_superuser)
        self.assertFalse(user.is_staff)
        self.assertTrue(user.is_verified)
        self.assertEqual(user.email, "nurlan@okurmen.kg")
        # Password hashed, login works.
        self.assertNotEqual(user.password, PASSWORD)
        self.assertTrue(user.check_password(PASSWORD))
        # No per-user Django permissions or groups were handed out …
        self.assertEqual(user.user_permissions.count(), 0)
        self.assertEqual(user.groups.count(), 0)
        # … and nothing was removed from the permission table.
        self.assertEqual(Permission.objects.count(), permissions_before)

    def test_role_is_required(self):
        response = self.add_user(role="")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(username="nurlan").exists())

    def test_password_mismatch_rejected(self):
        response = self.add_user(password2="Other0ne!!x")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(username="nurlan").exists())

    def test_team_lead_cannot_be_made_superuser_or_staff(self):
        response = self.add_user(is_superuser="on", is_staff="on")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(username="nurlan").exists())
        form = response.context["adminform"].form
        self.assertIn("is_superuser", form.errors)

    def test_model_never_saves_a_superuser_team_lead(self):
        user = User.objects.create_user(
            username="x", email="x@okurmen.kg", password=PASSWORD, first_name="X",
            role=User.Role.TEAM_LEAD, is_superuser=True, is_staff=True,
        )
        user.refresh_from_db()
        self.assertFalse(user.is_superuser)
        self.assertFalse(user.is_staff)

    def test_created_team_lead_logs_in_and_gets_team_lead_access(self):
        self.add_user()
        api = APIClient()
        login = api.post("/api/v1/auth/login/", {"username": "nurlan", "password": PASSWORD})
        self.assertEqual(login.status_code, status.HTTP_200_OK, login.content)
        self.assertEqual(login.data["user"]["role"], "team_lead")
        api.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")
        for url in (
            "/api/v1/trainers/",
            "/api/v1/groups/",
            "/api/v1/students/",
            "/api/v1/analytics/dashboard/",
            "/api/v1/reports/overview/",
            "/api/v1/reports/teachers/",
            "/api/v1/academy-reports/",
            "/api/v1/control/",
        ):
            self.assertEqual(api.get(url).status_code, status.HTTP_200_OK, url)
        # No Django admin either.
        web = self.client_class()
        self.assertTrue(web.login(username="nurlan", password=PASSWORD))
        self.assertEqual(web.get(reverse("admin:users_user_changelist")).status_code, 302)


class RoleChangeTests(UserAdminTestBase):
    def setUp(self):
        super().setUp()
        python, _ = Subject.objects.get_or_create(name="Python")
        course = Course.objects.create(name="Prog", count_lesson=10)
        self.mine = Group.objects.create(name="Mine", course=course, start_date=dt.date(2025, 1, 1))
        self.other = Group.objects.create(name="Other", course=course, start_date=dt.date(2025, 1, 1))
        self.user = User.objects.create_user(
            username="ivan", email="ivan@okurmen.kg", password=PASSWORD, first_name="Ivan",
            role=User.Role.TEACHER, is_verified=True,
        )
        teacher = Teacher.objects.create(user=self.user)
        GroupTeacher.objects.create(group=self.mine, teacher=teacher, subject=python)
        other_user = User.objects.create_user(
            username="aida", email="aida@okurmen.kg", password=PASSWORD, first_name="Aida",
            role=User.Role.TEACHER, is_verified=True,
        )
        GroupTeacher.objects.create(group=self.other, teacher=Teacher.objects.create(user=other_user), subject=python)
        Student.objects.create(first_name="S", last_name="1", group=self.mine)
        Student.objects.create(first_name="S", last_name="2", group=self.other)
        self.api = APIClient()
        self.api.force_authenticate(self.user)

    def set_role(self, role):
        url = reverse("admin:users_user_change", args=[self.user.pk])
        response = self.web.post(url, self.change_data(self.user, role=role))
        self.assertEqual(response.status_code, 302, response.content.decode()[:2000])
        self.user.refresh_from_db()
        self.api.force_authenticate(self.user)

    def group_ids(self):
        response = self.api.get("/api/v1/groups/")
        self.assertEqual(response.status_code, 200)
        return {row["id"] for row in response.data["results"]}

    def test_teacher_to_team_lead_and_back(self):
        self.assertEqual(self.group_ids(), {self.mine.id})
        self.assertEqual(self.api.get("/api/v1/reports/overview/").status_code, 403)

        self.set_role(User.Role.TEAM_LEAD)
        self.assertEqual(self.user.role, User.Role.TEAM_LEAD)
        self.assertEqual(self.group_ids(), {self.mine.id, self.other.id})
        self.assertEqual(self.api.get("/api/v1/reports/overview/").status_code, 200)
        self.assertEqual(self.api.get("/api/v1/trainers/").status_code, 200)
        # Read-only even on the groups they used to teach.
        self.assertEqual(self.api.patch(f"/api/v1/groups/{self.mine.id}/", {"name": "X"}).status_code, 403)
        self.assertEqual(self.user.user_permissions.count(), 0)

        self.set_role(User.Role.TEACHER)
        self.assertEqual(self.group_ids(), {self.mine.id})
        self.assertEqual(self.api.get("/api/v1/reports/overview/").status_code, 403)
        self.assertEqual(self.api.get("/api/v1/trainers/").status_code, 403)

    def test_edit_keeps_password(self):
        old_hash = self.user.password
        self.set_role(User.Role.TEAM_LEAD)
        self.assertEqual(self.user.password, old_hash)
        self.assertTrue(self.user.check_password(PASSWORD))


class TeamLeadUserManagementDeniedTests(TestCase):
    def setUp(self):
        self.lead = User.objects.create_user(
            username="lead", email="lead@okurmen.kg", password=PASSWORD, first_name="Lead", role=User.Role.TEAM_LEAD,
        )
        self.teacher = Teacher.objects.create(
            user=User.objects.create_user(username="t", email="t@okurmen.kg", password=PASSWORD, first_name="T", is_verified=True)
        )
        self.api = APIClient()
        self.api.force_authenticate(self.lead)

    def test_no_user_or_role_management_through_api(self):
        self.assertEqual(self.api.post("/api/v1/trainers/", {"username": "new"}).status_code, 403)
        self.assertEqual(self.api.patch(f"/api/v1/trainers/{self.teacher.id}/", {"is_active": False}).status_code, 403)
        self.assertEqual(self.api.delete(f"/api/v1/trainers/{self.teacher.id}/").status_code, 403)
        self.assertEqual(self.api.post(f"/api/v1/trainers/{self.teacher.id}/verify/").status_code, 403)
        # /auth/me/ is read-only: the role can't be changed through it.
        self.assertIn(self.api.patch("/api/v1/auth/me/", {"role": "admin"}).status_code, (403, 405))
        self.lead.refresh_from_db()
        self.assertEqual(self.lead.role, User.Role.TEAM_LEAD)

    def test_no_user_or_permission_management_through_admin(self):
        web = self.client_class()
        web.force_login(self.lead)
        for url in (
            reverse("admin:users_user_add"),
            reverse("admin:users_user_change", args=[self.lead.pk]),
            reverse("admin:users_user_changelist"),
        ):
            self.assertEqual(web.get(url).status_code, 302, url)
        web.post(reverse("admin:users_user_change", args=[self.lead.pk]), {"role": User.Role.ADMIN})
        self.lead.refresh_from_db()
        self.assertEqual(self.lead.role, User.Role.TEAM_LEAD)


class OtherRolesRegressionTests(UserAdminTestBase):
    def test_superuser_still_created_as_admin_with_full_admin_access(self):
        self.assertEqual(self.superuser.role, User.Role.ADMIN)
        self.assertTrue(self.superuser.is_superuser and self.superuser.is_staff)
        response = self.web.get(reverse("admin:users_user_change", args=[self.superuser.pk]))
        form = response.context["adminform"].form
        # Superuser keeps the two system flags (to create another admin)…
        for name in ("is_staff", "is_superuser"):
            self.assertIn(name, form.fields)
        # … but no per-user permission list, even for them.
        self.assertNotIn("user_permissions", form.fields)

    def test_admin_role_api_access_unchanged(self):
        api = APIClient()
        api.force_authenticate(self.superuser)
        self.assertEqual(api.get("/api/v1/trainers/").status_code, 200)
        course = Course.objects.create(name="C", count_lesson=3)
        group = Group.objects.create(name="G", course=course, start_date=dt.date(2025, 1, 1))
        student = Student.objects.create(first_name="S", last_name="S", group=group)
        self.assertEqual(api.patch(f"/api/v1/students/{student.id}/", {"first_name": "Z"}).status_code, 200)
        self.assertEqual(api.delete(f"/api/v1/students/{student.id}/").status_code, 204)

    def test_superuser_can_still_create_an_admin(self):
        response = self.add_user(username="boss", email="boss@okurmen.kg", role=User.Role.ADMIN, is_staff="on")
        self.assertEqual(response.status_code, 302)
        boss = User.objects.get(username="boss")
        self.assertEqual(boss.role, User.Role.ADMIN)
        self.assertTrue(boss.is_staff)
        self.assertFalse(boss.is_superuser)

    def test_existing_user_permissions_survive_an_edit(self):
        user = User.objects.create_user(username="pay", email="pay@okurmen.kg", password=PASSWORD, first_name="P", role=User.Role.ADMIN)
        perm = Permission.objects.get(codename="view_user")
        user.user_permissions.add(perm)
        # A non-superuser editor's form doesn't contain user_permissions,
        # so saving must not wipe what a superuser granted earlier.
        manager = User.objects.create_user(
            username="manager", email="manager@okurmen.kg", password=PASSWORD, first_name="M",
            role=User.Role.ADMIN, is_staff=True,
        )
        manager.user_permissions.add(*Permission.objects.filter(codename__in=["view_user", "change_user"]))
        web = self.client_class()
        web.force_login(manager)
        response = web.post(
            reverse("admin:users_user_change", args=[user.pk]), self.change_data(user, first_name="Paul")
        )
        self.assertEqual(response.status_code, 302, response.content.decode()[:2000])
        user.refresh_from_db()
        self.assertEqual(user.first_name, "Paul")
        self.assertTrue(user.user_permissions.filter(pk=perm.pk).exists())
        # The same through a superuser's form.
        response = self.web.post(
            reverse("admin:users_user_change", args=[user.pk]), self.change_data(user, last_name="Smith")
        )
        self.assertEqual(response.status_code, 302, response.content.decode()[:2000])
        self.assertTrue(user.user_permissions.filter(pk=perm.pk).exists())

    def test_trainer_access_unchanged(self):
        teacher_user = User.objects.create_user(
            username="tr", email="tr@okurmen.kg", password=PASSWORD, first_name="Tr", is_verified=True
        )
        Teacher.objects.create(user=teacher_user)
        api = APIClient()
        api.force_authenticate(teacher_user)
        self.assertEqual(api.get("/api/v1/trainers/me/").status_code, 200)
        self.assertEqual(api.get("/api/v1/groups/").status_code, 200)
        self.assertEqual(api.get("/api/v1/trainers/").status_code, 403)
        self.assertEqual(api.get("/api/v1/reports/overview/").status_code, 403)
