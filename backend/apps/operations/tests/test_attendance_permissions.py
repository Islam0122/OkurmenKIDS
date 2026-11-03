"""«Отпросился» (AttendancePermission) в кабинете операционного директора и
права суперпользователя на конфигурацию учёта."""
from __future__ import annotations

from datetime import datetime, time

from django.core.exceptions import ValidationError
from django.test import Client
from django.urls import reverse

from apps.staff_attendance.models import (
    AttendanceAdminLog,
    AttendanceEmployeeSettings,
    AttendanceEvent,
    AttendancePermission,
    AttendanceSession,
    AttendanceWorkSchedule,
)
from apps.staff_attendance.services import permissions as permission_service
from apps.staff_attendance.services.reports import month_stats
from apps.staff_attendance.services.schedule import adjust_window
from apps.staff_attendance.tests.base import AttendanceFixture, frozen, local, make_user
from apps.users.models import User

OPS = "/api/v1/operations/attendance/"
PERMS = "/api/v1/operations/attendance/permissions/"
SA = "/api/v1/staff-attendance"
WED = (2026, 10, 21)
Kind = AttendancePermission.Kind


def at(hour, minute=0, day=WED) -> datetime:
    return local(*day, hour, minute)


class AdjustWindowTests(AttendanceFixture):
    """Чистая функция пересчёта окна: все виды и пересечения интервалов."""

    def test_intervals(self):
        start, end = at(9), at(18)
        cases = [
            ([(at(9), at(10, 30))], (at(10, 30), end)),                     # опоздание
            ([(at(8), at(10))], (at(10), end)),                             # начался до рабочего дня
            ([(at(16), at(18))], (start, at(16))),                          # ранний уход
            ([(at(16), at(20))], (start, at(16))),                          # закончился после рабочего дня
            ([(at(12), at(14))], (start, end)),                             # часть дня в середине — окно то же
            ([(at(9), at(10)), (at(10), at(12))], (at(12), end)),           # встык — складываются
            ([(at(9), at(11)), (at(10), at(12))], (at(12), end)),           # пересекаются — объединяются
            ([(at(9), at(10)), (at(10, 30), at(12))], (at(10), end)),       # с разрывом — только первое
            ([(at(9), at(10)), (at(17), at(18))], (at(10), at(17))),                # оба края
            ([(at(6), at(8)), (at(19), at(21))], (start, end)),             # вне рабочего времени
            ([(at(0), at(23, 59))], (None, None)),                          # весь день
            ([(at(9), at(13)), (at(13), at(18))], (None, None)),            # весь день из двух частей
        ]
        for intervals, expected in cases:
            with self.subTest(intervals=intervals):
                self.assertEqual(adjust_window(start, end, intervals), expected)


class PermissionModelTests(AttendanceFixture):
    def perm(self, kind, start, end, user=None, **extra):
        return permission_service.create(self.ops_director, user=user or self.assistant, kind=kind,
                                         starts_at=start, ends_at=end, reason=extra.pop("reason", "Врач"), **extra)

    def setUp(self):
        super().setUp()
        self.ops_director = make_user("odir", User.Role.OPERATIONS_DIRECTOR)

    def test_validation(self):
        for kind, start, end, field in (
                (Kind.PARTIAL_DAY, at(12), at(11), "ends_at"),
                (Kind.LATE_ARRIVAL, at(9), at(9, 0, (2026, 10, 22)), "ends_at"),   # часть дня — в пределах дня
                (Kind.FULL_DAY, at(0), at(0, 0, (2026, 12, 1)), "ends_at")):      # больше 31 дня
            with self.subTest(kind=kind), self.assertRaises(ValidationError) as ctx:
                self.perm(kind, start, end)
            self.assertIn(field, ctx.exception.message_dict)
        with self.assertRaises(ValidationError) as ctx:
            self.perm(Kind.PARTIAL_DAY, at(12), at(13), reason="  ")
        self.assertIn("reason", ctx.exception.message_dict)

    def test_full_day_covers_whole_local_days(self):
        one = self.perm(Kind.FULL_DAY, at(13), at(14))
        self.assertEqual((one.starts_at, one.ends_at), (at(0), at(0, 0, (2026, 10, 22))))
        many = self.perm(Kind.FULL_DAY, at(0, 0, (2026, 10, 26)), at(0, 0, (2026, 10, 29)), user=self.accountant)
        self.assertEqual(many.ends_at, at(0, 0, (2026, 10, 29)))  # «по 29.10 00:00» = по 28.10 включительно

    def test_overlapping_intervals(self):
        self.perm(Kind.LATE_ARRIVAL, at(9), at(10, 30))
        for start, end in ((at(10), at(11)), (at(8), at(9, 30)), (at(9), at(10, 30)), (at(9, 30), at(10))):
            with self.subTest(start=start, end=end), self.assertRaises(ValidationError) as ctx:
                self.perm(Kind.PARTIAL_DAY, start, end)
            self.assertIn("Пересекается", str(ctx.exception))
        with self.assertRaises(ValidationError):
            self.perm(Kind.FULL_DAY, at(0), at(23))                         # весь день перекрывает опоздание
        self.perm(Kind.PARTIAL_DAY, at(10, 30), at(12))                      # встык — можно
        self.perm(Kind.PARTIAL_DAY, at(10), at(11), user=self.accountant)    # другой сотрудник — можно

    def test_cancelled_permission_frees_interval_and_is_audited(self):
        perm = self.perm(Kind.LATE_ARRIVAL, at(9), at(10))
        with self.assertRaises(ValidationError):
            permission_service.cancel(self.ops_director, perm, "")
        permission_service.cancel(self.ops_director, perm, "Ошибочно")
        perm.refresh_from_db()
        self.assertEqual((perm.status, perm.cancelled_by, perm.cancel_reason),
                         ("cancelled", self.ops_director, "Ошибочно"))
        self.assertIsNotNone(perm.cancelled_at)
        with self.assertRaises(ValidationError):
            permission_service.cancel(self.ops_director, perm, "Ещё раз")
        self.perm(Kind.LATE_ARRIVAL, at(9), at(10))                          # снова можно
        actions = list(AttendanceAdminLog.objects.filter(object_type="AttendancePermission")
                       .values_list("action", "actor_id"))
        self.assertEqual(actions.count(("permission_create", self.ops_director.pk)), 2)
        self.assertIn(("permission_cancel", self.ops_director.pk), actions)


class PermissionAttendanceTests(AttendanceFixture):
    def setUp(self):
        super().setUp()
        self.ops_director = make_user("odir", User.Role.OPERATIONS_DIRECTOR)
        self.ops = self.as_user(self.ops_director)

    def create(self, kind, start, end, user=None, client=None, **extra):
        body = {"user": (user or self.assistant).pk, "kind": kind, "starts_at": start, "ends_at": end,
                "reason": extra.pop("reason", "Семейные обстоятельства"), **extra}
        return (client or self.ops).post(PERMS, body, format="json")

    def rows(self, moment=None, **params):
        params.setdefault("period", "today")
        with frozen(moment or at(20)):
            data = self.ops.get(OPS, params).data
        return data, {r["user"]["id"]: r for r in data["rows"]}

    # -- API и права ------------------------------------------------------

    def test_create_api_and_who_may_grant(self):
        response = self.create(Kind.LATE_ARRIVAL, "2026-10-21T09:00", "2026-10-21T10:30", comment="Пробки")
        self.assertEqual(response.status_code, 201, response.data)
        perm = AttendancePermission.objects.get(pk=response.data["id"])
        self.assertEqual((perm.starts_at, perm.ends_at), (at(9), at(10, 30)))  # время без пояса — время офиса
        self.assertEqual((perm.status, perm.created_by, perm.approved_by), ("approved", self.ops_director,
                                                                             self.ops_director))
        self.assertEqual((response.data["approved_by"]["id"], response.data["period_label"]),
                         (self.ops_director.pk, "21.10 09:00–10:30"))
        self.assertTrue(AttendanceAdminLog.objects.filter(action="permission_create", actor=self.ops_director).exists())
        for user in (self.director, self.admin, self.team_lead, self.assistant):
            with self.subTest(role=user.role):
                denied = self.create(Kind.PARTIAL_DAY, "2026-10-22T12:00", "2026-10-22T13:00",
                                     client=self.as_user(user))
                self.assertEqual(denied.status_code, 403)
        root = make_user("root_user", User.Role.ADMIN, is_superuser=True)
        self.assertEqual(self.create(Kind.PARTIAL_DAY, "2026-10-22T12:00", "2026-10-22T13:00",
                                     client=self.as_user(root)).status_code, 201)
        bad = self.create(Kind.PARTIAL_DAY, "2026-10-21T10:00", "2026-10-21T11:00")
        self.assertEqual(bad.status_code, 400)
        self.assertIn("starts_at", bad.data)

    def test_history_and_cancel_api(self):
        perm_id = self.create(Kind.LATE_ARRIVAL, at(9).isoformat(), at(10).isoformat()).data["id"]
        url = f"{PERMS}{perm_id}/cancel/"
        self.assertEqual(self.as_user(self.director).post(url, {"reason": "x"}, format="json").status_code, 403)
        self.assertEqual(self.ops.post(url, {}, format="json").status_code, 400)
        cancelled = self.ops.post(url, {"reason": "Передумал"}, format="json")
        self.assertEqual((cancelled.status_code, cancelled.data["status"]), (200, "cancelled"))
        self.assertEqual(cancelled.data["cancelled_by"]["id"], self.ops_director.pk)
        with frozen(at(20)):
            history = self.as_user(self.director).get(PERMS, {"period": "this_month"}).data  # директор видит
        self.assertEqual([p["status"] for p in history["results"]], ["cancelled"])
        self.assertFalse(history["can_manage"])
        self.assertEqual(self.as_user(self.assistant).get(PERMS).status_code, 403)

    # -- расчёт посещаемости ----------------------------------------------

    def test_full_day_is_not_an_absence(self):
        self.create(Kind.FULL_DAY, "2026-10-21T00:00", "2026-10-21T23:59")
        data, rows = self.rows()
        row = rows[self.assistant.pk]
        self.assertEqual((row["status"], row["status_label"]), ("excused_absence", "Отсутствует по разрешению"))
        self.assertEqual((row["schedule"]["kind"], row["schedule"]["label"]), ("excused", "По разрешению"))
        self.assertEqual(row["permissions"][0]["kind"], "full_day")
        others_absent = sum(1 for r in data["rows"] if r["status"] == "absent")
        self.assertEqual(data["summary"]["counts"]["absent"], others_absent)
        self.assertEqual(data["summary"]["expected_days"], len(data["rows"]) - 1)

    def test_late_arrival_granted_before_check_in(self):
        self.create(Kind.LATE_ARRIVAL, "2026-10-21T09:00", "2026-10-21T10:30")
        with frozen(at(10, 35)):
            session = self.mark(self.assistant).data["session"]
        self.assertEqual(session["late_minutes"], 0)  # 10:30 + 10 мин льготы
        self.assertTrue(session["expected_start"].startswith("2026-10-21T10:30"))
        row = self.rows()[1][self.assistant.pk]
        self.assertEqual((row["status"], row["status_label"]), ("permitted_late", "Разрешено опоздать"))
        self.assertEqual((row["schedule"]["expected_start"], row["schedule"]["base_expected_start"]),
                         ("10:30", "09:00"))

    def test_late_arrival_granted_after_check_in_keeps_qr_history(self):
        with frozen(at(10, 20)):
            self.mark(self.assistant)
        stored = AttendanceSession.objects.get(user=self.assistant)
        self.assertEqual(stored.late_minutes, 80)
        events = list(AttendanceEvent.objects.values_list("pk", "kind", "occurred_at"))
        self.create(Kind.LATE_ARRIVAL, "2026-10-21T09:00", "2026-10-21T10:30")
        row = self.rows()[1][self.assistant.pk]
        self.assertEqual((row["late_minutes"], row["status"]), (0, "permitted_late"))
        stored.refresh_from_db()
        self.assertEqual(stored.late_minutes, 80)  # отметка и сессия не меняются
        self.assertEqual(list(AttendanceEvent.objects.values_list("pk", "kind", "occurred_at")), events)
        self.assertEqual(AttendanceSession.objects.count(), 1)  # фиктивных отметок нет

    def test_arriving_later_than_allowed_is_still_late(self):
        self.create(Kind.LATE_ARRIVAL, "2026-10-21T09:00", "2026-10-21T10:00")
        with frozen(at(10, 30)):
            self.assertEqual(self.mark(self.assistant).data["session"]["late_minutes"], 30)
        row = self.rows()[1][self.assistant.pk]
        self.assertEqual((row["status"], row["late_minutes"]), ("late", 30))

    def test_early_departure_and_partial_day(self):
        self.create(Kind.EARLY_DEPARTURE, "2026-10-21T15:00", "2026-10-21T18:00")
        self.create(Kind.PARTIAL_DAY, "2026-10-21T12:00", "2026-10-21T14:00", user=self.accountant)
        for user in (self.assistant, self.accountant):
            with frozen(at(8, 55)):
                self.mark(user)
        with frozen(at(15, 0)):
            self.mark(self.assistant, "check-out")
        with frozen(at(18, 0)):
            self.mark(self.accountant, "check-out")
        rows = self.rows()[1]
        early, partial = rows[self.assistant.pk], rows[self.accountant.pk]
        self.assertEqual((early["status"], early["schedule"]["expected_end"]), ("permitted_early_leave", "15:00"))
        self.assertEqual(early["schedule"]["base_expected_end"], "18:00")
        self.assertEqual((partial["status"], partial["status_label"]), ("permitted_partial", "Отпросился"))
        self.assertEqual(partial["schedule"]["expected_start"], "09:00")

    def test_today_early_departure_ends_the_day_earlier(self):
        # Ранний уход сдвигает конец рабочего окна: в 16:00 окно бухгалтера
        # (09:00–15:00) уже закончилось, а прихода не было — это отсутствие;
        # у тренера окно до 18:00 ещё идёт — «Ещё не пришёл».
        self.create(Kind.EARLY_DEPARTURE, "2026-10-21T15:00", "2026-10-21T18:00", user=self.accountant)
        rows = self.rows(moment=at(16))[1]
        self.assertEqual(rows[self.accountant.pk]["status"], "absent")      # окно 09:00–15:00 закончилось
        self.assertEqual(rows[self.teacher.pk]["status"], "not_arrived")     # окно до 18:00 ещё идёт

    def test_cancel_restores_original_calculation(self):
        with frozen(at(10, 20)):
            self.mark(self.assistant)
        perm_id = self.create(Kind.LATE_ARRIVAL, "2026-10-21T09:00", "2026-10-21T10:30").data["id"]
        self.ops.post(f"{PERMS}{perm_id}/cancel/", {"reason": "Не подтвердилось"}, format="json")
        row = self.rows()[1][self.assistant.pk]
        self.assertEqual((row["status"], row["late_minutes"], row["permissions"]), ("late", 80, []))

    def test_monthly_report_and_kpi_use_permissions(self):
        with frozen(at(10, 20)):
            self.mark(self.assistant)
        self.create(Kind.LATE_ARRIVAL, "2026-10-21T09:00", "2026-10-21T10:30")
        self.create(Kind.FULL_DAY, "2026-10-20T00:00", "2026-10-20T23:59")
        with frozen(at(20)):
            stats = month_stats(self.config, self.assistant, 2026, 10)
            summary = self.ops.get(OPS, {"period": "this_month", "role": "assistant"}).data["summary"]
            dashboard = self.ops.get("/api/v1/operations/dashboard/", {"period": "this_month"})
        self.assertEqual((stats["late_days"], stats["late_minutes_total"]), (0, 0))
        self.assertEqual(stats["work_days"], 17)  # 18 рабочих дней октября по 21-е минус день по разрешению
        self.assertEqual(summary["counts"]["permitted_late"], 1)
        self.assertEqual(summary["counts"]["excused_absence"], 1)
        self.assertEqual(summary["punctuality_rate"], 100.0)
        self.assertEqual(summary["expected_days"], 17)
        self.assertEqual(dashboard.status_code, 200)

    def test_query_count_with_permissions_does_not_grow(self):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        def count():
            with CaptureQueriesContext(connection) as ctx:
                self.rows(period="this_month")
            return len(ctx.captured_queries)

        self.create(Kind.LATE_ARRIVAL, "2026-10-21T09:00", "2026-10-21T10:00")
        before = count()
        for i, user in enumerate((self.teacher, self.accountant, self.team_lead, self.director)):
            self.create(Kind.PARTIAL_DAY, f"2026-10-{10 + i}T12:00", f"2026-10-{10 + i}T13:00", user=user)
            self.create(Kind.FULL_DAY, f"2026-10-{15 + i}T00:00", f"2026-10-{15 + i}T23:59", user=user)
        self.assertEqual(count(), before)


class SuperuserConfigurationTests(AttendanceFixture):
    def setUp(self):
        super().setUp()
        self.ops_director = make_user("odir", User.Role.OPERATIONS_DIRECTOR)

    def test_only_superuser_changes_attendance_configuration_via_api(self):
        calls = [
            ("patch", f"{SA}/admin/settings/", {"late_grace_minutes": 5}),
            ("post", f"{SA}/admin/locations/", {"name": "Филиал", "latitude": 42.8, "longitude": 74.6}),
            ("patch", f"{SA}/admin/locations/{self.office.pk}/", {"radius_m": 300}),
            ("put", f"{SA}/admin/employees/{self.accountant.pk}/schedule/",
             {"work_start": "10:00", "work_end": "18:00", "work_days": [0, 1, 2]}),
        ]
        staff_admin = make_user("perm_admin", User.Role.ADMIN, is_staff=True)
        from django.contrib.auth.models import Permission

        staff_admin.user_permissions.set(Permission.objects.filter(content_type__app_label="staff_attendance"))
        for user in (self.admin, staff_admin, self.ops_director, self.director, self.assistant):
            for method, url, body in calls:
                with self.subTest(role=user.username, url=url):
                    self.assertEqual(getattr(self.as_user(user), method)(url, body, format="json").status_code, 403)
        root = self.as_root()
        for method, url, body in calls:
            with self.subTest(root=url):
                self.assertIn(getattr(root, method)(url, body, format="json").status_code, (200, 201))
        with frozen(at(9)):
            access = self.as_user(self.admin).get(f"{SA}/me/status/").data["access"]
        self.assertFalse(access["can_manage"])
        self.assertTrue(access["can_view_reports"])

    def test_only_superuser_changes_configuration_in_django_admin(self):
        from django.contrib.auth.models import Permission

        staff_admin = make_user("perm_admin", User.Role.ADMIN, is_staff=True)
        staff_admin.user_permissions.set(Permission.objects.filter(content_type__app_label="staff_attendance"))
        web = Client()
        web.force_login(staff_admin)
        schedule = AttendanceWorkSchedule.objects.create(user=self.assistant, work_start=time(9), work_end=time(18))
        for name, args in (("attendanceworkschedule_add", []), ("attendancelocation_add", []),
                           ("attendanceemployeesettings_add", []), ("attendancescheduleexception_add", []),
                           ("attendancesettings_change", [self.config.pk])):
            with self.subTest(page=name):
                self.assertEqual(web.post(reverse(f"admin:staff_attendance_{name}", args=args), {}).status_code, 403)
        change = reverse("admin:staff_attendance_attendanceworkschedule_change", args=[schedule.pk])
        self.assertEqual(web.post(change, {}).status_code, 403)
        search = reverse("admin:staff_attendance_attendanceworkschedule_employee_search")
        self.assertEqual(web.get(search).status_code, 403)
        root = User.objects.create_superuser(username="dj_root", email="dj_root@okurmen.kg", password="x")
        web.force_login(root)
        response = web.post(reverse("admin:staff_attendance_attendanceemployeesettings_add"),
                            {"user": self.teacher.pk, "excluded_from_calculations": "on", "tracking_enabled": "on",
                             "note": "Совместитель"})
        self.assertEqual(response.status_code, 302)
        saved = AttendanceEmployeeSettings.objects.get(user=self.teacher)
        self.assertEqual((saved.excluded_from_calculations, saved.updated_by), (True, root))
        self.assertTrue(AttendanceAdminLog.objects.filter(action="employee_settings_update", actor=root).exists())

    def test_tracking_disabled_and_excluded_employees(self):
        AttendanceEmployeeSettings.objects.create(user=self.accountant, tracking_enabled=False)
        AttendanceEmployeeSettings.objects.create(user=self.assistant, excluded_from_calculations=True)
        with frozen(at(9, 40)):
            self.assertEqual(self.mark(self.accountant).status_code, 403)    # учёт выключен
            late = self.mark(self.assistant)                                 # исключён, но отмечаться может
        self.assertEqual(late.status_code, 201)
        with frozen(at(20)):
            data = self.as_user(self.ops_director).get(OPS, {"period": "today"}).data
        rows = {r["user"]["id"]: r for r in data["rows"]}
        self.assertNotIn(self.accountant.pk, rows)
        excluded = rows[self.assistant.pk]
        self.assertEqual((excluded["status"], excluded["status_label"], excluded["late_minutes"]),
                         ("excluded", "Не учитывается", 0))
        self.assertEqual(data["summary"]["counts"]["late"], 0)
        self.assertEqual(data["summary"]["late_minutes"], 0)
        self.assertEqual(data["summary"]["expected_days"], len(rows) - 1)
        with frozen(at(20)):
            stats = month_stats(self.config, self.assistant, 2026, 10)
            records = self.as_root().get(f"{SA}/admin/records/", {"date": "2026-10-21"}).data
        self.assertEqual((stats["work_days"], stats["late_minutes_total"]), (0, 0))
        ids = {r["employee"]["id"] for r in records["results"]} if "results" in records else \
            {r["employee"]["id"] for r in records["rows"]}
        self.assertNotIn(self.accountant.pk, ids)

    def test_operations_director_view_rights(self):
        ops = self.as_user(self.ops_director)
        with frozen(at(20)):
            data = ops.get(OPS, {"period": "today"}).data
        self.assertTrue(data["can_manage_permissions"])
        self.assertTrue(all("schedule" in r and "permissions" in r and r["user"]["role_label"] for r in data["rows"]))
        self.assertEqual(ops.patch(f"{SA}/admin/settings/", {"late_grace_minutes": 0}, format="json").status_code, 403)
        with frozen(at(20)):
            self.assertFalse(self.as_user(self.director).get(OPS, {"period": "today"}).data["can_manage_permissions"])
