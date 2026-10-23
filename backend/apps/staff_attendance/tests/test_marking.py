"""Приход, уход, геозона, точность GPS, локации, идемпотентность, опоздания."""
from __future__ import annotations

import uuid
from datetime import time

from apps.staff_attendance.models import (
    AttendanceEvent,
    AttendanceSession,
    AttendanceWorkSchedule,
)
from apps.staff_attendance.services.geo import haversine_m, within_radius
from apps.users.models import User

from .base import AttendanceFixture, frozen, local, make_user, north_of

WED = (2026, 10, 21)  # среда, рабочий день по умолчанию (Пн–Сб)


class CheckInOutTests(AttendanceFixture):
    def test_successful_check_in(self):
        with frozen(local(*WED, 8, 55)):
            response = self.mark(self.teacher)
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["event"], "check_in")
        self.assertEqual(response.data["employee"]["id"], self.teacher.pk)
        self.assertEqual(response.data["location"]["name"], self.office.name)
        self.assertAlmostEqual(response.data["distance_m"], 10.0, delta=0.2)
        session = AttendanceSession.objects.get(user=self.teacher)
        self.assertEqual(session.status, AttendanceSession.Status.OPEN)
        self.assertEqual(session.work_date.isoformat(), "2026-10-21")
        self.assertEqual(session.late_minutes, 0)
        self.assertEqual(AttendanceEvent.objects.filter(user=self.teacher, kind="check_in").count(), 1)

    def test_successful_check_out(self):
        with frozen(local(*WED, 9, 0)):
            self.mark(self.teacher)
        with frozen(local(*WED, 18, 30)):
            response = self.mark(self.teacher, "check-out")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["event"], "check_out")
        self.assertEqual(response.data["session"]["duration_seconds"], 9 * 3600 + 30 * 60)
        self.assertTrue(response.data["session"]["checked_in_at"].startswith("2026-10-21T09:00:00"))
        session = AttendanceSession.objects.get(user=self.teacher)
        self.assertEqual(session.status, AttendanceSession.Status.CLOSED)
        self.assertEqual(session.duration_seconds, 9 * 3600 + 30 * 60)

    def test_repeated_check_in_is_rejected(self):
        with frozen(local(*WED, 9, 0)):
            self.mark(self.teacher)
            response = self.mark(self.teacher)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data["code"], "already_checked_in")
        self.assertEqual(AttendanceSession.objects.filter(user=self.teacher).count(), 1)

    def test_check_out_without_check_in_is_rejected(self):
        with frozen(local(*WED, 18, 0)):
            response = self.mark(self.teacher, "check-out")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data["code"], "not_checked_in")
        self.assertFalse(AttendanceSession.objects.exists())

    def test_second_check_out_is_rejected(self):
        with frozen(local(*WED, 9, 0)):
            self.mark(self.teacher)
        with frozen(local(*WED, 18, 0)):
            self.mark(self.teacher, "check-out")
            response = self.mark(self.teacher, "check-out")
        self.assertEqual(response.data["code"], "not_checked_in")

    def test_check_in_again_after_check_out_same_day_is_not_late(self):
        with frozen(local(*WED, 9, 0)):
            self.mark(self.teacher)
        with frozen(local(*WED, 13, 0)):
            self.mark(self.teacher, "check-out")
        with frozen(local(*WED, 14, 0)):
            response = self.mark(self.teacher)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["session"]["late_minutes"], 0)

    def test_client_cannot_mark_for_another_user(self):
        with frozen(local(*WED, 9, 0)):
            response = self.mark(self.teacher, user_id=self.assistant.pk, employee_id=self.assistant.pk)
        self.assertEqual(response.status_code, 201)
        self.assertTrue(AttendanceSession.objects.filter(user=self.teacher).exists())
        self.assertFalse(AttendanceSession.objects.filter(user=self.assistant).exists())

    def test_device_time_is_ignored(self):
        with frozen(local(*WED, 9, 0)):
            response = self.mark(self.teacher, occurred_at="2020-01-01T00:00:00Z", checked_in_at="2020-01-01T00:00:00Z")
        self.assertTrue(response.data["occurred_at"].startswith("2026-10-21T09:00:00"))

    def test_stale_open_session_is_closed_as_missing_checkout_on_next_check_in(self):
        with frozen(local(2026, 10, 20, 9, 0)):
            self.mark(self.teacher)
        with frozen(local(*WED, 9, 0)):
            out = self.mark(self.teacher, "check-out")
            self.assertEqual(out.data["code"], "stale_session")
            response = self.mark(self.teacher)
        self.assertEqual(response.status_code, 201)
        self.assertIsNotNone(response.data["closed_stale_session"])
        old = AttendanceSession.objects.get(user=self.teacher, work_date="2026-10-20")
        self.assertEqual(old.status, AttendanceSession.Status.MISSING_CHECKOUT)
        self.assertIsNone(old.checked_out_at)
        self.assertTrue(AttendanceEvent.objects.filter(session=old, kind="auto_close").exists())


class GeofenceTests(AttendanceFixture):
    def test_inside_radius(self):
        with frozen(local(*WED, 9, 0)):
            response = self.mark(self.teacher, meters=60)
        self.assertEqual(response.status_code, 201)

    def test_exactly_on_radius_with_numeric_tolerance(self):
        lat, lon = north_of(100)
        distance = haversine_m(self.office.latitude, self.office.longitude, lat, lon)
        self.assertAlmostEqual(distance, 100.0, places=4)
        self.assertTrue(within_radius(distance, 100))
        self.assertTrue(within_radius(100.0 + 1e-7, 100))
        self.assertFalse(within_radius(100.05, 100))
        with frozen(local(*WED, 9, 0)):
            response = self.mark(self.teacher, meters=100)
        self.assertEqual(response.status_code, 201, response.data)

    def test_outside_radius(self):
        with frozen(local(*WED, 9, 0)):
            response = self.mark(self.teacher, meters=100.5)
            far = self.mark(self.teacher, meters=850)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["code"], "out_of_range")
        self.assertEqual(far.data["code"], "out_of_range")
        self.assertEqual(far.data["radius_m"], 100)
        self.assertAlmostEqual(far.data["distance_m"], 850, delta=1)
        self.assertFalse(AttendanceSession.objects.exists())

    def test_haversine_known_distance(self):
        # ~1 градус долготы на экваторе ≈ 111.2 км.
        self.assertAlmostEqual(haversine_m(0, 0, 0, 1), 111_195, delta=10)

    def test_low_gps_accuracy(self):
        self.config.max_gps_accuracy_m = 50
        self.config.save()
        with frozen(local(*WED, 9, 0)):
            response = self.mark(self.teacher, accuracy=80)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["code"], "low_accuracy")
        self.assertFalse(AttendanceSession.objects.exists())

    def test_geolocation_unavailable(self):
        client = self.as_user(self.teacher)
        with frozen(local(*WED, 9, 0)):
            response = client.post("/api/v1/staff-attendance/me/check-in/",
                                   {"location_code": self.office.code}, format="json")
            missing_accuracy = client.post("/api/v1/staff-attendance/me/check-in/", {
                "location_code": self.office.code, "latitude": 42.885, "longitude": 74.603}, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["code"], "geolocation_required")
        self.assertEqual(missing_accuracy.data["code"], "accuracy_required")

    def test_invalid_coordinates(self):
        with frozen(local(*WED, 9, 0)):
            response = self.as_user(self.teacher).post("/api/v1/staff-attendance/me/check-in/", {
                "location_code": self.office.code, "latitude": 123, "longitude": 74.6, "accuracy": 5}, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["code"], "invalid")

    def test_unknown_location(self):
        with frozen(local(*WED, 9, 0)):
            response = self.mark(self.teacher, code="no-such-office")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.data["code"], "location_not_found")
        verify = self.as_user(self.teacher).get("/api/v1/staff-attendance/me/locations/no-such-office/")
        self.assertEqual(verify.status_code, 404)

    def test_inactive_location(self):
        self.office.is_active = False
        self.office.save()
        with frozen(local(*WED, 9, 0)):
            response = self.mark(self.teacher)
        self.assertEqual(response.data["code"], "location_inactive")
        verify = self.as_user(self.teacher).get(f"/api/v1/staff-attendance/me/locations/{self.office.code}/")
        self.assertEqual(verify.data["code"], "location_inactive")

    def test_verify_active_location(self):
        response = self.as_user(self.teacher).get(f"/api/v1/staff-attendance/me/locations/{self.office.code}/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["name"], self.office.name)
        self.assertNotIn("latitude", response.data)

    def test_office_network_check(self):
        self.config.network_check_enabled = True
        self.config.office_networks = "10.10.0.0/16"
        self.config.save()
        with frozen(local(*WED, 9, 0)):
            outside = self.mark(self.teacher)
            inside = self.mark(self.teacher, client=self._client_from("10.10.4.2"))
        self.assertEqual(outside.status_code, 403)
        self.assertEqual(outside.data["code"], "network_mismatch")
        self.assertEqual(inside.status_code, 201)

    def _client_from(self, ip):
        client = self.as_user(self.teacher)
        client.defaults["REMOTE_ADDR"] = ip
        return client

    def test_employee_coordinates_are_not_stored(self):
        with frozen(local(*WED, 9, 0)):
            self.mark(self.teacher, meters=42)
        event = AttendanceEvent.objects.get()
        field_names = {f.name for f in AttendanceEvent._meta.fields} | {f.name for f in AttendanceSession._meta.fields}
        self.assertFalse({"latitude", "longitude"} & field_names)
        self.assertAlmostEqual(event.distance_m, 42, delta=0.2)


class IdempotencyTests(AttendanceFixture):
    def test_repeated_request_with_same_key_returns_first_result(self):
        key = uuid.uuid4()
        with frozen(local(*WED, 9, 0)):
            first = self.mark(self.teacher, key=key)
        with frozen(local(*WED, 9, 1)):
            again = self.mark(self.teacher, key=key)
        self.assertEqual(first.status_code, 201)
        self.assertEqual(again.status_code, 200)
        self.assertTrue(again.data["replayed"])
        self.assertEqual(again.data["session"]["id"], first.data["session"]["id"])
        self.assertEqual(again.data["occurred_at"], first.data["occurred_at"])
        self.assertEqual(AttendanceEvent.objects.count(), 1)

    def test_key_reused_for_other_action_conflicts(self):
        key = uuid.uuid4()
        with frozen(local(*WED, 9, 0)):
            self.mark(self.teacher, key=key)
            response = self.mark(self.teacher, "check-out", key=key)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data["code"], "idempotency_conflict")

    def test_keys_are_per_user(self):
        key = uuid.uuid4()
        with frozen(local(*WED, 9, 0)):
            self.assertEqual(self.mark(self.teacher, key=key).status_code, 201)
            self.assertEqual(self.mark(self.assistant, key=key).status_code, 201)


class LatenessTests(AttendanceFixture):
    def test_within_grace_is_not_late(self):
        with frozen(local(*WED, 9, 10)):
            response = self.mark(self.teacher)
        self.assertEqual(response.data["session"]["late_minutes"], 0)

    def test_late_counts_from_start_of_day(self):
        with frozen(local(*WED, 9, 25, 40)):
            response = self.mark(self.teacher)
        self.assertEqual(response.data["session"]["late_minutes"], 25)
        self.assertTrue(response.data["session"]["expected_start"].startswith("2026-10-21T09:00:00+06:00"))

    def test_day_off_is_never_late(self):
        with frozen(local(2026, 10, 25, 12, 0)):  # воскресенье
            response = self.mark(self.teacher)
        self.assertEqual(response.data["session"]["late_minutes"], 0)
        self.assertIsNone(response.data["session"]["expected_start"])

    def test_personal_schedule_overrides_default(self):
        AttendanceWorkSchedule.objects.create(user=self.assistant, work_start=time(11, 0), work_end=time(20, 0),
                                              work_days=[0, 1, 2, 3, 4], late_grace_minutes=0)
        with frozen(local(*WED, 10, 50)):
            on_time = self.mark(self.assistant)
        self.assertEqual(on_time.data["session"]["late_minutes"], 0)
        with frozen(local(*WED, 11, 50)):
            self.mark(self.assistant, "check-out")
        other = make_user("helper2", User.Role.ASSISTANT)
        AttendanceWorkSchedule.objects.create(user=other, work_start=time(11, 0), work_end=time(20, 0),
                                              work_days=[2], late_grace_minutes=0)
        with frozen(local(*WED, 11, 1)):
            late = self.mark(other)
        self.assertEqual(late.data["session"]["late_minutes"], 1)

    def test_teacher_start_from_first_lesson(self):
        import datetime as dt

        from apps.academy.models import Course, Group, GroupTeacher, Lesson
        from apps.users.models import Subject, Teacher

        self.config.teacher_schedule_from_lessons = True
        self.config.teacher_arrival_before_lesson_minutes = 15
        self.config.save()
        python = Subject.objects.get_or_create(name="Python")[0]
        course = Course.objects.create(name="Prog SOFT", count_lesson=48)
        group = Group.objects.create(name="PY-1", course=course, start_date=dt.date(2026, 9, 1))
        trainer = Teacher.objects.create(user=self.teacher)
        program = GroupTeacher.objects.create(group=group, teacher=trainer, subject=python)
        for number, (start, end) in enumerate(((time(16, 0), time(17, 30)), (time(14, 0), time(15, 30))), 1):
            Lesson.objects.create(group=group, group_teacher=program, teacher=trainer, subject=python,
                                  lesson_number=number, date=dt.date(*WED), start_time=start, end_time=end)
        # Ожидается к 13:45 (первое занятие 14:00 − 15 мин), льгота 10 мин.
        with frozen(local(*WED, 14, 0)):
            response = self.mark(self.teacher)
        self.assertEqual(response.data["session"]["late_minutes"], 15)
        self.assertTrue(response.data["session"]["expected_start"].startswith("2026-10-21T13:45:00"))
        # День без занятий — для тренера не рабочий: опоздание не считается.
        with frozen(local(2026, 10, 22, 13, 0)):
            next_day = self.mark(self.teacher)
        self.assertEqual(next_day.data["session"]["late_minutes"], 0)


class TimeDisplayTests(AttendanceFixture):
    def test_times_are_stored_in_utc_and_returned_in_office_timezone(self):
        with frozen(local(*WED, 0, 30)):  # 18:30 UTC предыдущего дня
            response = self.mark(self.teacher)
        session = AttendanceSession.objects.get()
        self.assertEqual(session.checked_in_at.utcoffset().total_seconds(), 0)
        self.assertEqual(session.checked_in_at.isoformat(), "2026-10-20T18:30:00+00:00")
        self.assertEqual(session.work_date.isoformat(), "2026-10-21")  # день — по часовому поясу офиса
        self.assertEqual(response.data["occurred_at"], "2026-10-21T00:30:00+06:00")
        self.assertEqual(response.data["timezone"], "Asia/Bishkek")
