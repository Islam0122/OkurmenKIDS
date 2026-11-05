"""seed_reports_demo — the demo data of the demo video."""
from __future__ import annotations

import io
import os
from unittest import mock

from django.core.management import CommandError, call_command
from django.test import TestCase
from django.utils import timezone

from apps.academy.models import Group, Lesson, Student
from apps.reports.management.commands.seed_reports_demo import DEMO_GROUP, DEMO_USERNAME
from apps.reports.services import analytics, periods
from apps.users.models import User


class SeedDemoTests(TestCase):
    def run_seed(self):
        call_command("seed_reports_demo", password="Demo-Pass-123", stdout=io.StringIO())

    def test_creates_demo_group_and_is_idempotent(self):
        self.run_seed()
        self.run_seed()
        group = Group.objects.get(name=DEMO_GROUP)
        self.assertEqual(Group.objects.filter(name=DEMO_GROUP).count(), 1)
        self.assertEqual(Student.objects.filter(group=group).count(), 12)
        self.assertFalse(Student.objects.filter(group=group).exclude(phone="").exists())
        self.assertTrue(Lesson.objects.filter(group=group, status=Lesson.Status.COMPLETED).exists())
        trainer = User.objects.get(username=DEMO_USERNAME)
        self.assertTrue(trainer.check_password("Demo-Pass-123"))

        data = analytics.build_report_data(group, periods.resolve("last_month", today=timezone.localdate()))
        self.assertEqual(data["group_stats"]["active_students"], 12)
        self.assertGreater(data["group_stats"]["conducted_lessons"], 0)
        self.assertIsNotNone(data["group_stats"]["test_average"])

    def test_refuses_production(self):
        with mock.patch.dict(os.environ, {"DJANGO_ENV": "production"}):
            with self.assertRaises(CommandError):
                self.run_seed()
