"""Общая фикстура тестов учёта прихода и ухода."""
from __future__ import annotations

import math
from contextlib import contextmanager
from datetime import date, datetime
from unittest import mock
from zoneinfo import ZoneInfo

from django.test import TestCase
from rest_framework.test import APIClient

from apps.staff_attendance.models import AttendanceLocation, AttendanceSettings
from apps.staff_attendance.services.geo import EARTH_RADIUS_M
from apps.users.models import User

TZ = ZoneInfo("Asia/Bishkek")
OFFICE_LAT, OFFICE_LON = 42.88543338574097, 74.60303549712579
PASSWORD = "Str0ngPassw0rd!"


def local(year, month, day, hour=9, minute=0, second=0) -> datetime:
    return datetime(year, month, day, hour, minute, second, tzinfo=TZ)


def north_of(meters: float, lat: float = OFFICE_LAT, lon: float = OFFICE_LON) -> tuple[float, float]:
    """Точка ровно в `meters` к северу от (lat, lon) по той же сфере, что и haversine."""
    return lat + math.degrees(meters / EARTH_RADIUS_M), lon


@contextmanager
def frozen(moment: datetime):
    with mock.patch("django.utils.timezone.now", return_value=moment):
        yield


def make_user(username: str, role=User.Role.TEACHER, **extra) -> User:
    # Тесты живут в октябре 2026: сотрудник «работает» с начала года.
    extra.setdefault("date_joined", local(2026, 1, 1))
    return User.objects.create_user(
        username=username, email=f"{username}@okurmen.kg", password=PASSWORD,
        first_name=extra.pop("first_name", username.capitalize()), last_name=extra.pop("last_name", "Test"),
        role=role, is_verified=True, **extra,
    )


class AttendanceFixture(TestCase):
    def setUp(self):
        # Главный офис создаёт миграция 0002; после TransactionTestCase (flush)
        # других приложений его может не быть — тогда создаём такой же.
        self.office = AttendanceLocation.objects.filter(name="OkurmenKIDS — главный офис").first() or \
            AttendanceLocation.objects.create(name="OkurmenKIDS — главный офис", latitude=OFFICE_LAT,
                                              longitude=OFFICE_LON, radius_m=100)
        self.config = AttendanceSettings.load()
        self.config.tracking_started_on = date(2026, 1, 1)
        self.config.save()
        self.teacher = make_user("trainer")
        self.assistant = make_user("helper", User.Role.ASSISTANT)
        self.accountant = make_user("buh", User.Role.ACCOUNTANT)
        self.director = make_user("boss", User.Role.DIRECTOR)
        self.team_lead = make_user("lead", User.Role.TEAM_LEAD)
        self.admin = make_user("office_admin", User.Role.ADMIN)
        self.client = APIClient()

    def as_user(self, user) -> APIClient:
        client = APIClient()
        client.force_authenticate(user)
        return client

    def mark(self, user, kind="check-in", meters=10.0, accuracy=15.0, code=None, key=None, client=None, **extra):
        lat, lon = north_of(meters)
        body = {"location_code": code or self.office.code, "latitude": lat, "longitude": lon, "accuracy": accuracy}
        if key:
            body["idempotency_key"] = str(key)
        body.update(extra)
        return (client or self.as_user(user)).post(f"/api/v1/staff-attendance/me/{kind}/", body, format="json")
