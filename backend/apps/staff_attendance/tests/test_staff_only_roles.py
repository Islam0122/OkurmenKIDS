"""Роли с базовым доступом (ДОП, РОП, РОМ, операционный директор,
HR-менеджер, менеджер по продажам, маркетинг): вход, отметка прихода и
ухода, только свои данные, контроль руководством через существующие отчёты."""
from __future__ import annotations

import importlib

from django.contrib.auth.models import Permission
from django.test import Client
from django.urls import reverse
from rest_framework.test import APIClient

from apps.staff_attendance.models import AttendanceEvent, AttendanceSession, AttendanceSettings
from apps.users.models import User

from .base import PASSWORD, AttendanceFixture, frozen, local, make_user

WED = (2026, 10, 21)
API = "/api/v1/staff-attendance"


def jwt_client(username: str) -> APIClient:
    client = APIClient()
    response = client.post("/api/v1/auth/login/", {"username": username, "password": PASSWORD}, format="json")
    assert response.status_code == 200, response.data
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {response.data['access']}")
    return client


class StaffOnlyRolesTests(AttendanceFixture):
    def setUp(self):
        super().setUp()
        self.staff = {role: make_user(f"staff_{role}", role) for role in User.STAFF_ONLY_ROLES}

    def test_all_new_roles_exist_once(self):
        labels = dict(User.Role.choices)
        expected = {"dop": "ДОП", "rop": "РОП", "operations_director": "Операционный директор",
                    "hr_manager": "HR-менеджер", "sales_manager": "Менеджер по продажам", "marketing": "Маркетинг"}
        for value, label in expected.items():
            self.assertEqual(labels[value], label)
        self.assertEqual(len(labels), len(set(labels.values())))

    def test_never_admin_or_staff(self):
        for user in self.staff.values():
            user.is_staff = True
            user.is_superuser = True
            user.save()
            user.refresh_from_db()
            self.assertFalse(user.is_staff)
            self.assertFalse(user.is_superuser)

    def test_login_check_in_and_check_out_with_exact_time(self):
        for role, user in self.staff.items():
            client = jwt_client(user.username)
            me = client.get("/api/v1/auth/me/")
            self.assertEqual(me.status_code, 200, role)
            self.assertEqual(me.data["role"], role)
            with frozen(local(*WED, 8, 57, 13)):
                self.assertEqual(client.get(f"{API}/me/status/").data["state"], "not_arrived", role)
                self.assertEqual(self.mark(user, client=client).status_code, 201, role)
                self.assertEqual(client.get(f"{API}/me/status/").data["state"], "at_work", role)
            with frozen(local(*WED, 18, 4, 41)):
                self.assertEqual(self.mark(user, "check-out", client=client).status_code, 201, role)
                self.assertEqual(client.get(f"{API}/me/status/").data["state"], "day_finished", role)
            session = AttendanceSession.objects.get(user=user)
            self.assertEqual(session.checked_in_at, local(*WED, 8, 57, 13))
            self.assertEqual(session.checked_out_at, local(*WED, 18, 4, 41))
            self.assertEqual(session.status, AttendanceSession.Status.CLOSED)
            self.assertEqual(AttendanceEvent.objects.filter(user=user).count(), 2)

    def test_history_shows_only_own_data(self):
        rop, sales = self.staff[User.Role.ROP], self.staff[User.Role.SALES_MANAGER]
        with frozen(local(*WED, 9, 0)):
            self.mark(rop)
            self.mark(sales)
        client = jwt_client(rop.username)
        history = client.get(f"{API}/me/history/", {"user": sales.pk}).data
        self.assertEqual([row["id"] for row in history["results"]],
                         [AttendanceSession.objects.get(user=rop).pk])
        self.assertEqual(client.get(f"{API}/admin/employees/{sales.pk}/").status_code, 403)

    def test_rest_of_system_is_closed(self):
        client = jwt_client(self.staff[User.Role.OPERATIONS_DIRECTOR].username)
        for url in ("/api/v1/trainers/", "/api/v1/accounting/", "/api/v1/assistant/", "/api/v1/subjects/"):
            response = client.get(url)
            self.assertEqual(response.status_code, 403, url)
            self.assertEqual(response.json()["code"], "staff_only", url)
        for url in ("/admin/records/", "/admin/locations/", "/admin/settings/"):
            self.assertEqual(client.get(f"{API}{url}").status_code, 403, url)

    def test_explicit_permission_still_grants_reports(self):
        hr = self.staff[User.Role.HR_MANAGER]
        hr.user_permissions.add(Permission.objects.get(codename="view_attendance_reports"))
        client = jwt_client(hr.username)
        self.assertEqual(client.get(f"{API}/admin/records/").status_code, 200)
        self.assertEqual(client.get(f"{API}/admin/locations/").status_code, 403)
        self.assertEqual(client.get("/api/v1/trainers/").status_code, 403)

    def test_management_sees_new_roles_with_filters(self):
        rop = self.staff[User.Role.ROP]
        with frozen(local(*WED, 9, 20)):
            self.mark(rop)
        for boss in (self.admin, self.director):
            client = self.as_user(boss)
            meta = client.get(f"{API}/admin/meta/").data
            self.assertTrue({r["value"] for r in meta["roles"]} >= set(User.STAFF_ONLY_ROLES))
            with frozen(local(*WED, 12, 0)):
                by_role = client.get(f"{API}/admin/records/", {"date": "2026-10-21", "role": "rop"}).data
                by_name = client.get(f"{API}/admin/records/", {"date": "2026-10-21", "search": "staff_rop"}).data
                at_work = client.get(f"{API}/admin/records/", {"date": "2026-10-21", "status": "at_work",
                                                               "page_size": 100}).data
            self.assertEqual([r["employee"]["id"] for r in by_role["results"]], [rop.pk])
            self.assertEqual(by_role["results"][0]["employee"]["role_label"], "РОП")
            self.assertEqual(by_role["results"][0]["late_minutes"], 20)
            self.assertEqual([r["employee"]["id"] for r in by_name["results"]], [rop.pk])
            self.assertIn(rop.pk, [r["employee"]["id"] for r in at_work["results"]])
            card = client.get(f"{API}/admin/employees/{rop.pk}/",
                              {"date_from": "2026-10-01", "date_to": "2026-10-31"})
            self.assertEqual(card.status_code, 200)
        # Team Lead руководит только тренерами — новые роли ему не видны.
        lead = self.as_user(self.team_lead)
        self.assertEqual(lead.get(f"{API}/admin/employees/{rop.pk}/").status_code, 404)

    def test_existing_settings_get_new_roles_from_migration(self):
        from django.apps import apps as django_apps

        # 0003 ещё добавляла упразднённую роль РОМ — 0004 её убирает.
        migrations = [importlib.import_module(f"apps.staff_attendance.migrations.{name}")
                      for name in ("0003_track_staff_only_roles", "0004_remove_rom_role")]
        self.config.tracked_roles = [User.Role.TEACHER, User.Role.ACCOUNTANT]
        self.config.save()
        for migration in migrations:
            migration.forwards(django_apps, None)
        tracked = AttendanceSettings.load().tracked_roles
        self.assertEqual(tracked[:2], [User.Role.TEACHER, User.Role.ACCOUNTANT])
        self.assertEqual(set(tracked[2:]), set(User.STAFF_ONLY_ROLES))
        for migration in migrations:
            migration.forwards(django_apps, None)
        self.assertEqual(AttendanceSettings.load().tracked_roles, tracked)

    def test_django_admin_lists_new_roles(self):
        superuser = User.objects.create_superuser("root", "root@okurmen.kg", PASSWORD)
        web = Client()
        web.force_login(superuser)
        with frozen(local(*WED, 9, 0)):
            self.mark(self.staff[User.Role.MARKETING])
        users = web.get(reverse("admin:users_user_changelist"), {"role__exact": "marketing"})
        self.assertContains(users, "staff_marketing")
        sessions = web.get(reverse("admin:staff_attendance_attendancesession_changelist"),
                           {"user__role": "marketing"})
        self.assertEqual(sessions.status_code, 200)
        self.assertContains(sessions, "Staff_marketing")

    def test_django_admin_login_is_refused(self):
        web = Client()
        response = web.post(reverse("admin:login"), {"username": "staff_dop", "password": PASSWORD})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "входит в LMS")
