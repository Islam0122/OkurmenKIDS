"""Сайт «Общая статистика»: вход по ключу «только чтение» (X-Dashboard-Key)."""
from __future__ import annotations

import datetime as dt
import io

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.performance.models import DashboardAccessKey
from apps.performance.services.access_keys import hash_key, issue_key
from apps.users.models import User

from .test_performance import URL, PerformanceFixture, at, frozen, make_user


class DashboardKeyTests(PerformanceFixture):
    def setUp(self):
        super().setUp()
        self.client = APIClient()
        self.key, self.raw = issue_key("Телевизор в офисе")

    def get(self, path="", key=None, **params):
        headers = {"HTTP_X_DASHBOARD_KEY": key if key is not None else self.raw}
        return self.client.get(URL + path, params, **headers)

    def test_key_opens_every_read_endpoint(self):
        with frozen(at(self.D2, 12)):
            for suffix in ("", "snapshots/", "summary/", "trends/"):
                response = self.get(suffix)
                self.assertEqual(response.status_code, 200, (suffix, response.content[:200]))
            data = self.get().data
        self.assertEqual(data["access"], {"mode": "key", "name": "Телевизор в офисе"})
        self.assertFalse(data["can_edit"])
        self.assertEqual(set(data["trends"]), {"attendance", "homework", "groups", "students"})
        self.key.refresh_from_db()
        self.assertIsNotNone(self.key.last_used_at)

    def test_only_hash_is_stored(self):
        self.assertTrue(self.raw.startswith("okd_"))
        self.assertEqual(self.key.key_hash, hash_key(self.raw))
        self.assertFalse(DashboardAccessKey.objects.filter(key_hash=self.raw).exists())

    def test_invalid_disabled_or_expired_key_is_rejected(self):
        self.assertEqual(self.get(key="okd_wrong").status_code, 401)
        self.key.is_active = False
        self.key.save()
        self.assertEqual(self.get().status_code, 401)
        self.key.is_active = True
        self.key.expires_at = timezone.now() - dt.timedelta(minutes=1)
        self.key.save()
        self.assertEqual(self.get().status_code, 401)

    def test_key_cannot_correct_numbers(self):
        response = self.client.patch(URL + "snapshots/2026-11-01/", {"active_groups": 3}, format="json",
                                     HTTP_X_DASHBOARD_KEY=self.raw)
        self.assertIn(response.status_code, (401, 403))

    def test_key_opens_nothing_else_in_lms(self):
        for path in ("/api/v1/students/", "/api/v1/groups/", "/api/v1/auth/me/", "/api/v1/accounting/my/salary/"):
            response = self.client.get(path, HTTP_X_DASHBOARD_KEY=self.raw)
            self.assertIn(response.status_code, (401, 403), path)

    def test_response_has_no_personal_data(self):
        with frozen(at(self.D2, 12)):
            body = self.get().content.decode()
        for student in self.students:
            self.assertNotIn(student.first_name, body)
        self.assertNotIn(self.group.name, body)

    def test_staff_jwt_still_works_without_key(self):
        user = make_user("hr", User.Role.HR_MANAGER)
        self.client.force_authenticate(user)
        with frozen(at(self.D2, 12)):
            data = self.client.get(URL).data
        self.assertEqual(data["access"]["mode"], "user")

    def test_create_command_prints_key_once(self):
        out = io.StringIO()
        call_command("create_dashboard_key", "Ресепшн", "--days", "30", stdout=out)
        raw = out.getvalue().strip().splitlines()[-1]
        key = DashboardAccessKey.objects.get(name="Ресепшн")
        self.assertEqual(key.key_hash, hash_key(raw))
        self.assertIsNotNone(key.expires_at)


class AdminCreatesKeyTests(TestCase):
    def test_admin_add_shows_key_once(self):
        admin = User.objects.create_superuser(username="root", email="r@x.kg", password="Str0ngPassw0rd!")
        self.client.force_login(admin)
        response = self.client.post("/admin/performance/dashboardaccesskey/add/",
                                    {"name": "Телевизор", "is_active": "on"}, follow=True)
        self.assertEqual(response.status_code, 200)
        key = DashboardAccessKey.objects.get()
        shown = [str(m) for m in response.context["messages"]]
        self.assertTrue(any("okd_" in m for m in shown), shown)
        raw = next(part for m in shown for part in m.split() if part.startswith("okd_"))
        self.assertEqual(key.key_hash, hash_key(raw))
        self.assertEqual(key.created_by, admin)
