"""Параллельные отметки одного сотрудника. Блокировки строк есть только в
PostgreSQL (SQLite игнорирует select_for_update), поэтому тест запускается
с TEST_DATABASE_URL=postgres://… и пропускается на SQLite."""
from __future__ import annotations

import threading
import uuid
from unittest import skipUnless

from django.db import connection, connections
from django.test import TransactionTestCase
from rest_framework.test import APIClient

from apps.staff_attendance.models import AttendanceEvent, AttendanceLocation, AttendanceSession
from apps.users.models import User

from .base import frozen, local, make_user, north_of

THREADS = 6


@skipUnless(connection.vendor == "postgresql", "Блокировки строк проверяются только на PostgreSQL.")
class ConcurrentMarkTests(TransactionTestCase):
    def setUp(self):
        self.office = AttendanceLocation.objects.create(
            name="Офис", latitude=42.88543338574097, longitude=74.60303549712579, radius_m=100)
        self.user = make_user("racer", User.Role.ASSISTANT)

    def _race(self, kind: str, keys: list) -> list[int]:
        lat, lon = north_of(5)
        barrier = threading.Barrier(len(keys))
        codes: list[int] = []
        lock = threading.Lock()

        def worker(key):
            client = APIClient()
            client.force_authenticate(self.user)
            body = {"location_code": self.office.code, "latitude": lat, "longitude": lon, "accuracy": 10}
            if key:
                body["idempotency_key"] = str(key)
            try:
                barrier.wait()
                response = client.post(f"/api/v1/staff-attendance/me/{kind}/", body, format="json")
                with lock:
                    codes.append(response.status_code)
            finally:
                connections.close_all()

        with frozen(local(2026, 10, 21, 9, 0)):
            threads = [threading.Thread(target=worker, args=(k,)) for k in keys]
            for t in threads:
                t.start()
            for t in threads:
                t.join()
        return sorted(codes)

    def test_parallel_check_ins_create_exactly_one_session(self):
        codes = self._race("check-in", [None] * THREADS)
        self.assertEqual(codes, [201] + [409] * (THREADS - 1))
        self.assertEqual(AttendanceSession.objects.filter(user=self.user).count(), 1)
        self.assertEqual(AttendanceEvent.objects.filter(user=self.user, kind="check_in").count(), 1)

    def test_parallel_retries_of_one_request_are_idempotent(self):
        key = uuid.uuid4()
        codes = self._race("check-in", [key] * THREADS)
        self.assertEqual(codes, [200] * (THREADS - 1) + [201])
        self.assertEqual(AttendanceEvent.objects.filter(user=self.user).count(), 1)

    def test_parallel_check_outs_close_once(self):
        self._race("check-in", [None])
        codes = self._race("check-out", [None] * THREADS)
        self.assertEqual(codes, [201] + [409] * (THREADS - 1))
        self.assertEqual(AttendanceEvent.objects.filter(user=self.user, kind="check_out").count(), 1)
