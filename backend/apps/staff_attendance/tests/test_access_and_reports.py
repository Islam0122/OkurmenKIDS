"""Права доступа, отчёты, фильтры, экспорт, исправления с аудитом,
офисы и настройки."""
from __future__ import annotations

from datetime import date
from unittest import mock

from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.staff_attendance.models import (
    AttendanceAdjustment,
    AttendanceAdminLog,
    AttendanceEvent,
    AttendanceLocation,
    AttendanceSession,
)
from apps.staff_attendance.services.export import safe_cell
from apps.users.models import User

from .base import AttendanceFixture, frozen, local, make_user

WED = (2026, 10, 21)
API = "/api/v1/staff-attendance"


class PersonalAccessTests(AttendanceFixture):
    def test_unauthenticated_is_rejected(self):
        anon = APIClient()
        for method, url in (("get", "/me/status/"), ("post", "/me/check-in/"), ("post", "/me/check-out/"),
                            ("get", "/me/history/"), ("get", "/admin/records/")):
            response = getattr(anon, method)(f"{API}{url}", {}, format="json")
            self.assertEqual(response.status_code, 401, url)

    def test_untracked_role_cannot_mark(self):
        self.config.tracked_roles = [User.Role.TEACHER]
        self.config.save()
        with frozen(local(*WED, 9, 0)):
            response = self.mark(self.assistant)
        self.assertEqual(response.status_code, 403)

    def test_history_shows_only_own_sessions(self):
        with frozen(local(*WED, 9, 0)):
            self.mark(self.teacher)
            self.mark(self.assistant)
            response = self.as_user(self.teacher).get(f"{API}/me/history/", {"user": self.assistant.pk})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)
        own = AttendanceSession.objects.get(user=self.teacher)
        self.assertEqual(response.data["results"][0]["id"], own.pk)

    def test_cannot_open_colleague_card(self):
        response = self.as_user(self.teacher).get(f"{API}/admin/employees/{self.assistant.pk}/")
        self.assertEqual(response.status_code, 403)

    def test_status_states(self):
        client = self.as_user(self.teacher)
        with frozen(local(*WED, 8, 0)):
            self.assertEqual(client.get(f"{API}/me/status/").data["state"], "not_arrived")
            self.mark(self.teacher)
            status = client.get(f"{API}/me/status/").data
            self.assertEqual(status["state"], "at_work")
            self.assertEqual(status["next_action"], "check_out")
            self.assertFalse(status["access"]["can_view_reports"])
        with frozen(local(*WED, 17, 0)):
            self.mark(self.teacher, "check-out")
            status = client.get(f"{API}/me/status/").data
        self.assertEqual(status["state"], "day_finished")
        self.assertEqual(status["today"]["duration_seconds"], 9 * 3600)

    def test_month_stats(self):
        for d, (h, m) in ((19, (9, 0)), (20, (9, 40)), (21, (8, 50))):
            with frozen(local(2026, 10, d, h, m)):
                self.mark(self.teacher)
            with frozen(local(2026, 10, d, 18, 0)):
                self.mark(self.teacher, "check-out")
        with frozen(local(2026, 10, 21, 19, 0)):
            stats = self.as_user(self.teacher).get(f"{API}/me/stats/", {"month": "2026-10"}).data
        self.assertEqual(stats["days_present"], 3)
        self.assertEqual(stats["late_days"], 1)
        self.assertEqual(stats["late_minutes_total"], 40)
        # 1–21 октября: Пн–Сб без отметок до 19-го — «нет прихода».
        self.assertEqual(stats["work_days"], 18)
        self.assertEqual(stats["no_check_in_days"], 15)
        self.assertEqual(stats["total_seconds"], (9 * 60 + 8 * 60 + 20 + 9 * 60 + 10) * 60)

    def test_days_before_tracking_are_not_absences(self):
        newcomer = make_user("newbie", User.Role.ASSISTANT, date_joined=local(2026, 10, 20, 15, 0))
        with frozen(local(2026, 10, 21, 19, 0)):
            stats = self.as_user(newcomer).get(f"{API}/me/stats/", {"month": "2026-10"}).data
            before = self.as_user(self.admin).get(f"{API}/admin/records/", {
                "date": "2026-10-19", "search": "newbie"}).data["results"][0]
        # Учёт с 20-го (дата регистрации): пропуски — только 20 и 21 октября.
        self.assertEqual(stats["work_days"], 2)
        self.assertEqual(stats["no_check_in_days"], 2)
        self.assertEqual(before["status"], "not_tracked")
        self.config.tracking_started_on = date(2026, 10, 21)
        self.config.save()
        with frozen(local(2026, 10, 21, 19, 0)):
            stats = self.as_user(newcomer).get(f"{API}/me/stats/", {"month": "2026-10"}).data
        self.assertEqual(stats["no_check_in_days"], 1)

    def test_accountant_reaches_personal_attendance_but_not_reports(self):
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(self.accountant).access_token}")
        self.assertEqual(client.get(f"{API}/me/status/").status_code, 200)
        with frozen(local(*WED, 9, 0)):
            self.assertEqual(self.mark(self.accountant, client=client).status_code, 201)
        blocked = client.get(f"{API}/admin/records/")
        self.assertEqual(blocked.status_code, 403)
        self.assertEqual(blocked.json()["code"], "accounting_only")
        # Остальная LMS для бухгалтера по-прежнему закрыта.
        self.assertEqual(client.get("/api/v1/trainers/").status_code, 403)


class AdminAccessTests(AttendanceFixture):
    def test_reports_permissions_by_role(self):
        expected = {self.teacher: 403, self.assistant: 403, self.accountant: 403,
                    self.admin: 200, self.director: 200, self.team_lead: 200}
        for user, code in expected.items():
            self.assertEqual(self.as_user(user).get(f"{API}/admin/records/").status_code, code, user.role)

    def test_team_lead_sees_only_teachers(self):
        response = self.as_user(self.team_lead).get(f"{API}/admin/records/", {"page_size": 100})
        roles = {row["employee"]["role"] for row in response.data["results"]}
        self.assertEqual(roles, {User.Role.TEACHER})
        card = self.as_user(self.team_lead).get(f"{API}/admin/employees/{self.accountant.pk}/")
        self.assertEqual(card.status_code, 404)
        meta = self.as_user(self.team_lead).get(f"{API}/admin/meta/").data
        self.assertEqual(meta["access"]["scope"], "teachers")

    def test_director_reads_but_cannot_adjust_or_manage(self):
        with frozen(local(*WED, 9, 0)):
            self.mark(self.teacher)
        session = AttendanceSession.objects.get()
        director = self.as_user(self.director)
        self.assertEqual(director.post(f"{API}/admin/sessions/{session.pk}/adjust/", {
            "checked_in_at": "2026-10-21T08:00:00+06:00", "reason": "Ошибка сканера"}, format="json").status_code, 403)
        self.assertEqual(director.get(f"{API}/admin/locations/").status_code, 403)
        self.assertEqual(director.patch(f"{API}/admin/settings/", {"late_grace_minutes": 0},
                                        format="json").status_code, 403)
        self.assertEqual(director.get(f"{API}/admin/settings/").status_code, 200)

    def test_explicit_permission_grants_reports(self):
        from django.contrib.auth.models import Permission

        hr = make_user("hr_person", User.Role.ASSISTANT)
        self.assertEqual(self.as_user(hr).get(f"{API}/admin/records/").status_code, 403)
        hr.user_permissions.add(Permission.objects.get(codename="view_attendance_reports"))
        hr = User.objects.get(pk=hr.pk)
        self.assertEqual(self.as_user(hr).get(f"{API}/admin/records/").status_code, 200)
        self.assertEqual(self.as_user(hr).get(f"{API}/admin/locations/").status_code, 403)

    def test_inactive_admin_is_denied(self):
        self.admin.is_active = False
        self.admin.save()
        self.assertEqual(self.as_user(self.admin).get(f"{API}/admin/records/").status_code, 403)


class ReportTests(AttendanceFixture):
    def setUp(self):
        super().setUp()
        with frozen(local(*WED, 8, 55)):
            self.mark(self.teacher)
        with frozen(local(*WED, 9, 30)):
            self.mark(self.assistant)  # опоздание 30 мин
        with frozen(local(*WED, 9, 0)):
            self.mark(self.director)
        with frozen(local(*WED, 13, 0)):
            self.mark(self.director, "check-out")

    def test_overview_counts_from_real_data(self):
        with frozen(local(*WED, 14, 0)):
            data = self.as_user(self.admin).get(f"{API}/admin/overview/", {"date": "2026-10-21"}).data
        self.assertEqual(data["total_employees"], 6)
        self.assertEqual(data["arrived"], 3)
        self.assertEqual(data["at_work"], 2)
        self.assertEqual(data["late"], 1)
        self.assertEqual(data["finished"], 1)
        self.assertEqual(data["not_arrived"], 3)  # рабочий день ещё идёт — это не «нет прихода»
        self.assertEqual(data["no_check_in"], 0)
        with frozen(local(*WED, 19, 0)):
            evening = self.as_user(self.admin).get(f"{API}/admin/overview/", {"date": "2026-10-21"}).data
        self.assertEqual(evening["no_check_in"], 3)
        self.assertEqual(evening["not_arrived"], 0)

    def test_previous_day_open_session_is_no_check_out(self):
        with frozen(local(2026, 10, 22, 10, 0)):
            rows = self.as_user(self.admin).get(f"{API}/admin/records/", {
                "date": "2026-10-21", "status": "no_check_out"}).data["results"]
        self.assertEqual({r["employee"]["id"] for r in rows}, {self.teacher.pk, self.assistant.pk})

    def test_filters_search_and_ordering(self):
        admin = self.as_user(self.admin)
        with frozen(local(*WED, 14, 0)):
            late = admin.get(f"{API}/admin/records/", {"date": "2026-10-21", "status": "late"}).data
            role = admin.get(f"{API}/admin/records/", {"date": "2026-10-21", "role": "director"}).data
            search = admin.get(f"{API}/admin/records/", {"date": "2026-10-21", "search": "helper"}).data
            at_work = admin.get(f"{API}/admin/records/", {"date": "2026-10-21", "status": "at_work",
                                                          "ordering": "-check_in"}).data
            bad = admin.get(f"{API}/admin/records/", {"status": "nonsense"})
            paged = admin.get(f"{API}/admin/records/", {"date": "2026-10-21", "page_size": 2, "page": 2}).data
        self.assertEqual([r["employee"]["id"] for r in late["results"]], [self.assistant.pk])
        self.assertEqual(late["results"][0]["late_minutes"], 30)
        self.assertEqual([r["employee"]["id"] for r in role["results"]], [self.director.pk])
        self.assertEqual(role["results"][0]["status"], "day_finished")
        self.assertEqual(role["results"][0]["duration_seconds"], 4 * 3600)
        self.assertEqual([r["employee"]["id"] for r in search["results"]], [self.assistant.pk])
        self.assertEqual([r["employee"]["id"] for r in at_work["results"]], [self.assistant.pk, self.teacher.pk])
        self.assertEqual(bad.status_code, 400)
        self.assertEqual(paged["count"], 6)
        self.assertEqual(len(paged["results"]), 2)

    def test_location_filter(self):
        other = AttendanceLocation.objects.create(name="Филиал", latitude=42.0, longitude=74.0)
        with frozen(local(*WED, 14, 0)):
            rows = self.as_user(self.admin).get(f"{API}/admin/records/", {
                "date": "2026-10-21", "location": other.pk}).data
        self.assertEqual(rows["count"], 0)

    def test_range_records(self):
        with frozen(local(*WED, 14, 0)):
            data = self.as_user(self.admin).get(f"{API}/admin/records/", {
                "date_from": "2026-10-19", "date_to": "2026-10-21", "page_size": 100}).data
            too_long = self.as_user(self.admin).get(f"{API}/admin/records/", {
                "date_from": "2026-01-01", "date_to": "2026-10-21"})
        self.assertEqual(data["count"], 18)
        self.assertEqual(too_long.status_code, 400)

    def test_csv_export_matches_filters_and_escapes_formulas(self):
        self.assistant.first_name = "=HYPERLINK(\"http://evil\")"
        self.assistant.save()
        with frozen(local(*WED, 14, 0)):
            response = self.as_user(self.admin).get(f"{API}/admin/export/", {"date": "2026-10-21", "status": "late"})
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/csv", response["Content-Type"])
        text = response.content.decode("utf-8-sig")
        lines = [line for line in text.splitlines() if line]
        self.assertEqual(len(lines), 2)  # заголовок + одна строка
        self.assertIn("'=HYPERLINK", lines[1])
        self.assertIn("09:30", lines[1])
        self.assertIn("Опоздание", lines[0])
        self.assertEqual(safe_cell("-1+2"), "'-1+2")
        self.assertEqual(safe_cell("@SUM(A1)"), "'@SUM(A1)")
        self.assertEqual(safe_cell("Иван"), "Иван")
        forbidden = self.as_user(self.teacher).get(f"{API}/admin/export/")
        self.assertEqual(forbidden.status_code, 403)

    def test_employee_card(self):
        with frozen(local(*WED, 14, 0)):
            data = self.as_user(self.admin).get(f"{API}/admin/employees/{self.director.pk}/", {
                "date_from": "2026-10-21", "date_to": "2026-10-21"}).data
        self.assertEqual(data["employee"]["id"], self.director.pk)
        self.assertEqual(len(data["days"]), 1)
        self.assertEqual({e["kind"] for e in data["events"]}, {"check_in", "check_out"})
        self.assertEqual(data["stats"]["total_seconds"], 4 * 3600)


class AdjustmentTests(AttendanceFixture):
    def setUp(self):
        super().setUp()
        with frozen(local(*WED, 9, 40)):
            self.mark(self.teacher)
        self.session = AttendanceSession.objects.get(user=self.teacher)

    def adjust(self, user=None, **body):
        return self.as_user(user or self.admin).post(
            f"{API}/admin/sessions/{self.session.pk}/adjust/", body, format="json")

    def test_adjustment_is_audited_and_events_kept(self):
        with frozen(local(*WED, 20, 0)):
            response = self.adjust(checked_in_at="2026-10-21T08:58:00+06:00",
                                   checked_out_at="2026-10-21T18:05:00+06:00",
                                   reason="Сотрудник пришёл вовремя, телефон не видел QR")
        self.assertEqual(response.status_code, 200, response.data)
        adjustment = AttendanceAdjustment.objects.get()
        self.assertEqual(adjustment.adjusted_by, self.admin)
        self.assertEqual(adjustment.old_values["late_minutes"], 40)
        self.assertEqual(adjustment.old_values["status"], "open")
        self.assertIsNone(adjustment.old_values["checked_out_at"])
        self.assertEqual(adjustment.new_values["late_minutes"], 0)
        self.assertEqual(adjustment.new_values["status"], "closed")
        self.assertIn("телефон", adjustment.reason)
        self.assertIsNotNone(adjustment.created_at)
        self.session.refresh_from_db()
        self.assertTrue(self.session.is_adjusted)
        self.assertEqual(self.session.duration_seconds, (9 * 60 + 7) * 60)
        # Исходное событие прихода не тронуто.
        original = AttendanceEvent.objects.get(kind="check_in")
        self.assertEqual(original.occurred_at, local(*WED, 9, 40))
        with frozen(local(*WED, 20, 0)):
            row = self.as_user(self.admin).get(f"{API}/admin/records/", {
                "date": "2026-10-21", "status": "adjusted"}).data["results"]
        self.assertEqual([r["employee"]["id"] for r in row], [self.teacher.pk])

    def test_reason_is_required(self):
        with frozen(local(*WED, 20, 0)):
            response = self.adjust(checked_in_at="2026-10-21T09:00:00+06:00", reason="  ")
        self.assertEqual(response.status_code, 400)
        self.assertFalse(AttendanceAdjustment.objects.exists())

    def test_invalid_ranges(self):
        with frozen(local(*WED, 20, 0)):
            backwards = self.adjust(checked_in_at="2026-10-21T10:00:00+06:00",
                                    checked_out_at="2026-10-21T09:00:00+06:00", reason="Проверка порядка")
            future = self.adjust(checked_in_at="2026-10-22T10:00:00+06:00", reason="Проверка будущего")
        self.assertEqual(backwards.data["code"], "invalid_range")
        self.assertEqual(future.data["code"], "future_time")

    def test_excused_lateness_override(self):
        with frozen(local(*WED, 20, 0)):
            response = self.adjust(checked_in_at="2026-10-21T09:40:00+06:00",
                                   checked_out_at="2026-10-21T18:00:00+06:00",
                                   late_minutes=0, reason="Опоздание согласовано с директором")
        self.assertEqual(response.data["new_values"]["late_minutes"], 0)

    def test_employee_cannot_adjust_own_record(self):
        with frozen(local(*WED, 20, 0)):
            response = self.adjust(user=self.teacher, checked_in_at="2026-10-21T09:00:00+06:00",
                                   reason="Хочу исправить себе")
        self.assertEqual(response.status_code, 403)
        self.session.refresh_from_db()
        self.assertEqual(self.session.late_minutes, 40)

    def test_manual_session_for_forgotten_scan(self):
        with frozen(local(*WED, 20, 0)):
            response = self.as_user(self.admin).post(f"{API}/admin/sessions/", {
                "user": self.assistant.pk, "checked_in_at": "2026-10-20T09:00:00+06:00",
                "checked_out_at": "2026-10-20T18:00:00+06:00", "location": self.office.pk,
                "reason": "Забыл отсканировать QR, подтверждено руководителем"}, format="json")
            overlap = self.as_user(self.admin).post(f"{API}/admin/sessions/", {
                "user": self.teacher.pk, "checked_in_at": "2026-10-21T09:00:00+06:00",
                "checked_out_at": "2026-10-21T10:00:00+06:00", "reason": "Пересечение с сессией"}, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["action"], "create")
        session = AttendanceSession.objects.get(user=self.assistant)
        self.assertEqual(session.source, "manual")
        self.assertTrue(AttendanceEvent.objects.filter(session=session, kind="manual_create",
                                                       created_by=self.admin).exists())
        self.assertEqual(overlap.status_code, 409)
        self.assertEqual(overlap.data["code"], "overlap")


class LocationAndSettingsTests(AttendanceFixture):
    def test_admin_manages_locations_with_log(self):
        admin = self.as_user(self.admin)
        created = admin.post(f"{API}/admin/locations/", {
            "name": "Филиал Восток", "latitude": 42.87, "longitude": 74.65, "radius_m": 150}, format="json")
        self.assertEqual(created.status_code, 201, created.data)
        self.assertTrue(created.data["qr_url"].startswith("https://"))
        self.assertIn("/attendance/scan?office=", created.data["qr_url"])
        pk = created.data["id"]
        patched = admin.patch(f"{API}/admin/locations/{pk}/", {"is_active": False, "code": "hijack"}, format="json")
        self.assertFalse(patched.data["is_active"])
        self.assertNotEqual(patched.data["code"], "hijack")  # код только для чтения
        bad = admin.post(f"{API}/admin/locations/", {"name": "X", "latitude": 95, "longitude": 0}, format="json")
        self.assertEqual(bad.status_code, 400)
        self.assertEqual(set(AttendanceAdminLog.objects.values_list("action", flat=True)),
                         {"location_create", "location_update"})

    def test_qr_svg_contains_only_public_url(self):
        response = self.as_user(self.admin).get(f"{API}/admin/locations/{self.office.pk}/qr.svg")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "image/svg+xml")
        self.assertIn("<svg", response.content.decode())
        self.assertEqual(response["X-QR-URL"].split("office=")[1], self.office.code)

    def test_main_office_from_migration(self):
        self.assertAlmostEqual(self.office.latitude, 42.88543338574097)
        self.assertAlmostEqual(self.office.longitude, 74.60303549712579)
        self.assertEqual(self.office.radius_m, 100)

    def test_settings_validation_and_update(self):
        admin = self.as_user(self.admin)
        ok = admin.patch(f"{API}/admin/settings/", {"late_grace_minutes": 5, "work_days": [0, 1, 2, 3, 4, 4]},
                         format="json")
        self.assertEqual(ok.status_code, 200, ok.data)
        self.assertEqual(ok.data["work_days"], [0, 1, 2, 3, 4])
        for body in ({"work_start": "19:00", "work_end": "09:00"}, {"timezone": "Mars/Base"},
                     {"office_networks": "not-a-network"}, {"tracked_roles": ["pilot"]}):
            self.assertEqual(admin.patch(f"{API}/admin/settings/", body, format="json").status_code, 400, body)
        self.assertTrue(AttendanceAdminLog.objects.filter(action="settings_update").exists())

    def test_personal_schedule_crud(self):
        admin = self.as_user(self.admin)
        put = admin.put(f"{API}/admin/employees/{self.accountant.pk}/schedule/", {
            "work_start": "10:00", "work_end": "17:00", "work_days": [0, 1, 2, 3, 4]}, format="json")
        self.assertEqual(put.status_code, 200, put.data)
        self.assertEqual(admin.get(f"{API}/admin/schedules/").data[0]["user"], self.accountant.pk)
        self.assertEqual(admin.delete(f"{API}/admin/employees/{self.accountant.pk}/schedule/").status_code, 204)
        self.assertEqual(self.as_user(self.director).put(
            f"{API}/admin/employees/{self.accountant.pk}/schedule/", {}, format="json").status_code, 403)


class StaleSessionCommandTests(AttendanceFixture):
    def test_close_stale_sessions(self):
        from django.core.management import call_command

        with frozen(local(2026, 10, 20, 9, 0)):
            self.mark(self.teacher)
        with frozen(local(*WED, 9, 0)):
            self.mark(self.assistant)
            call_command("close_stale_attendance_sessions", stdout=mock.MagicMock())
            call_command("close_stale_attendance_sessions", stdout=mock.MagicMock())
        statuses = dict(AttendanceSession.objects.values_list("user_id", "status"))
        self.assertEqual(statuses[self.teacher.pk], "missing_checkout")
        self.assertEqual(statuses[self.assistant.pk], "open")
        self.assertEqual(AttendanceEvent.objects.filter(kind="auto_close").count(), 1)


class RateLimitTests(AttendanceFixture):
    def test_mark_endpoint_is_throttled(self):
        from django.core.cache import caches
        from django.test import override_settings

        from apps.staff_attendance import views

        cache = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "sa-throttle"}}
        with override_settings(CACHES=cache):
            caches["default"].clear()
            with mock.patch.dict(views.ScopedRateThrottle.THROTTLE_RATES, {"staff_attendance_mark": "2/hour"}), \
                    mock.patch.object(views.ScopedRateThrottle, "cache", caches["default"]):
                with frozen(local(*WED, 9, 0)):
                    codes = [self.mark(self.teacher, meters=500).status_code for _ in range(3)]
        self.assertEqual(codes, [400, 400, 429])

