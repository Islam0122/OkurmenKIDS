from __future__ import annotations

import datetime as dt
import os
from io import StringIO
from unittest import mock

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from apps.academy.models import Attendance, Course, Group, Lesson, Student
from apps.scholarships.demo import namespace as ns
from apps.scholarships.models import ScholarshipAward, ScholarshipEvaluation, ScholarshipPeriod
from apps.users.models import Subject, User

TODAY = "2026-09-26"


def seed(*args) -> str:
    out = StringIO()
    call_command("seed_scholarship_demo", "--today", TODAY, *args, stdout=out)
    return out.getvalue()


def fingerprint():
    return (
        list(Student.objects.filter(ns.demo_student_q()).order_by("id").values_list("first_name", "last_name", "enrollment_date")),
        Attendance.objects.count(),
        list(
            ScholarshipEvaluation.objects.order_by("period__period_start", "student_name", "overall_score")
            .values_list("period__period_start", "student_name", "overall_score", "rank")
        ),
    )


class SeedScholarshipDemoTests(TestCase):
    def test_seed_runs_all_checks_and_clear_removes_everything(self):
        output = seed("--students", "60")
        self.assertIn("15/15 checks passed", output)
        self.assertEqual(Student.objects.filter(ns.demo_student_q()).count(), 60)
        self.assertEqual(ScholarshipPeriod.objects.count(), 4)
        self.assertTrue(all(p.awards.count() <= p.max_recipients for p in ScholarshipPeriod.objects.all()))

        with self.assertRaises(CommandError):
            seed("--students", "60")  # refuses to seed twice

        seed("--clear")
        self.assertFalse(Student.objects.exists())
        self.assertFalse(Group.objects.exists())
        self.assertFalse(Lesson.objects.exists())
        self.assertFalse(ScholarshipPeriod.objects.exists())
        self.assertFalse(User.objects.filter(username__startswith=ns.USERNAME_PREFIX).exists())
        self.assertTrue(Subject.objects.filter(name="Soft Skills").exists())  # shared catalogue is kept

    def test_same_seed_produces_identical_data(self):
        seed("--students", "40", "--no-checks")
        first = fingerprint()
        seed("--reset", "--students", "40", "--no-checks")
        self.assertEqual(fingerprint(), first)
        seed("--reset", "--students", "40", "--no-checks", "--seed", "7")
        self.assertNotEqual(fingerprint()[0], first[0])

    def test_real_data_is_never_touched(self):
        subject = Subject.objects.get_or_create(name="Python")[0]
        course = Course.objects.create(name="Real course", count_lesson=10)
        course.subjects.set([subject])
        group = Group.objects.create(name="Real group", course=course, start_date=dt.date(2026, 1, 1))
        real = Student.objects.create(first_name="Real", group=group, phone="+996 555 000 111")
        real_user = User.objects.create_user(
            username="schdemo_lookalike", email="person@okurmen.kg", password="x", first_name="Look"
        )

        output = seed("--students", "40")
        # Periods would evaluate the real student too, so they are skipped.
        self.assertIn("не-демо студенты", output)
        self.assertFalse(ScholarshipPeriod.objects.exists())
        self.assertEqual(Student.objects.filter(ns.demo_student_q()).count(), 40)

        seed("--clear")
        self.assertTrue(Student.objects.filter(pk=real.pk).exists())
        self.assertTrue(Group.objects.filter(pk=group.pk).exists())
        self.assertTrue(Course.objects.filter(pk=course.pk).exists())
        self.assertTrue(User.objects.filter(pk=real_user.pk).exists())  # username alone is not enough
        self.assertFalse(Student.objects.filter(ns.demo_student_q()).exists())

    def test_refuses_to_run_in_production(self):
        with mock.patch.dict(os.environ, {"DJANGO_ENV": "production"}):
            with self.assertRaises(CommandError):
                seed()
            with self.assertRaises(CommandError):
                seed("--clear")

    def test_twenty_recipient_limit_with_many_eligible(self):
        seed("--students", "120", "--no-checks")
        for period in ScholarshipPeriod.objects.all():
            eligible = period.evaluations.filter(eligibility_status="eligible").count()
            self.assertGreater(eligible, 20)
            self.assertEqual(ScholarshipAward.objects.filter(period=period).count(), 20)
