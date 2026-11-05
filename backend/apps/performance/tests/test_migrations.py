"""Миграция 0003: снимки первой версии (продакшн) → показатели по расписанию дня.

Воспроизводит продакшн: 0001_initial и 0002 применены, в таблице старые
колонки и ручная корректировка; после 0003 — все колонки модели на месте,
старые значения сохранены в legacy_*, корректировка перенесена.
"""
from __future__ import annotations

import datetime as dt
from decimal import Decimal
from unittest import mock

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase

from apps.performance.models import DailyPerformanceSnapshot

OLD = [("performance", "0002_dashboardaccesskey")]
NEW = [("performance", "0003_schedule_based_metrics")]


class Migration0003Tests(TransactionTestCase):
    def setUp(self):
        executor = MigrationExecutor(connection)
        executor.migrate(OLD)
        old_apps = executor.loader.project_state(OLD).apps
        Snapshot = old_apps.get_model("performance", "DailyPerformanceSnapshot")
        Snapshot.objects.create(
            date=dt.date(2026, 11, 3), attendance_percent=Decimal("73.3"), attendance_marked=15, attendance_attended=11,
            homework_percent=Decimal("80.0"), lessons_count=2, active_groups=9, active_students=40, status="final",
            manual_fields=["active_groups", "attendance_percent"], manual_comment="Ручная сверка",
        )
        Snapshot.objects.create(date=dt.date(2026, 11, 2), attendance_percent=Decimal("90.0"), active_groups=4,
                                active_students=32, status="final")
        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate(NEW)

    def tearDown(self):
        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate(executor.loader.graph.leaf_nodes())

    def test_every_model_column_exists(self):
        with connection.cursor() as cursor:
            columns = {c.name for c in connection.introspection.get_table_description(
                cursor, DailyPerformanceSnapshot._meta.db_table)}
        for field in DailyPerformanceSnapshot._meta.concrete_fields:
            self.assertIn(field.column, columns, field.name)
        self.assertNotIn("active_groups", columns)  # переименована, не удалена

    def test_old_values_are_preserved_and_corrections_moved(self):
        corrected = DailyPerformanceSnapshot.objects.get(date=dt.date(2026, 11, 3))
        self.assertEqual((corrected.legacy_active_groups, corrected.legacy_active_students), (9, 40))
        self.assertEqual((corrected.legacy_attendance_marked, corrected.legacy_attendance_attended), (15, 11))
        self.assertEqual((corrected.legacy_attendance_percent, corrected.legacy_homework_percent),
                         (Decimal("73.3"), Decimal("80.0")))
        self.assertEqual(corrected.scheduled_groups, 9)  # ручная корректировка перенесена
        self.assertEqual(corrected.manual_fields, ["scheduled_groups", "attendance_percent"])
        self.assertEqual(corrected.attendance_percent, Decimal("73.3"))
        self.assertEqual(corrected.manual_comment, "Ручная сверка")
        plain = DailyPerformanceSnapshot.objects.get(date=dt.date(2026, 11, 2))
        self.assertEqual((plain.legacy_active_groups, plain.scheduled_groups), (4, None))
        # Оба снимка будут пересчитаны по расписанию дня планировщиком.
        self.assertEqual({s.status for s in DailyPerformanceSnapshot.objects.all()}, {"provisional"})

    def test_capture_runs_after_migration(self):
        from django.utils import timezone

        from apps.performance.services.snapshots import capture

        now = timezone.make_aware(dt.datetime(2026, 11, 5, 20))
        with mock.patch("django.utils.timezone.now", return_value=now):
            result = capture(now=now)
        self.assertEqual(result["date"], "2026-11-05")
        plain = DailyPerformanceSnapshot.objects.get(date=dt.date(2026, 11, 2))
        self.assertEqual(plain.scheduled_groups, 0)  # занятий в базе нет — 0 по расписанию
        self.assertEqual(plain.legacy_active_groups, 4)
        self.assertEqual(DailyPerformanceSnapshot.objects.get(date=dt.date(2026, 11, 3)).scheduled_groups, 9)
