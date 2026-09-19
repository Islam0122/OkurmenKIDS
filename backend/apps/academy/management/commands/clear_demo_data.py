"""Removes ONLY the dataset created by `seed_demo_data` — never touches real
project data.

There is no generic "is_demo" flag on any of these models (spec:
"НЕ добавляй сложную архитектуру только ради этого"), so this command
targets the exact, hardcoded registry `seed_demo_data` itself owns: the 10
named demo Groups, the demo Rooms/Courses ("[DEMO] ..." — the same marker
convention `seed_dev_data.py` already uses in this project), and the 5 demo
User accounts (admin + 4 teachers), matched by their exact usernames *and*,
for "admin", also by its `@okurmenkids.local` demo email — so a real
production account that happens to be named "admin" is never touched.

Deletion order matters because of PROTECT/CASCADE:
  Group (CASCADE) -> GroupSchedule, GroupTeacher, Lesson (CASCADE) ->
  Attendance, Homework (CASCADE) -> HomeworkResult
  Student.group is SET_NULL (not CASCADE), so demo Students are deleted
  explicitly before their Group.
  GroupTeacher.teacher is PROTECT, so every demo Group must be gone before
  a demo Teacher/User can be deleted.

Subjects are never deleted — they are shared/reusable catalogue data (spec:
"Если Subject уже существует — использовать его"), not demo-exclusive.

After this command, `seed_demo_data` can be run again from a clean slate.
"""
from __future__ import annotations

import os

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.academy.models import Attendance, Course, Group, Homework, HomeworkResult, Lesson, MonthlyTeacherReport, Room, Student
from apps.users.models import User

from .seed_demo_data import ADMIN_EMAIL, ADMIN_USERNAME, COURSE_DEFS, DEMO_GROUP_NAMES, DEMO_ROOM_NAMES, DEMO_TEACHERS

DEMO_TEACHER_USERNAMES = [cfg["username"] for cfg in DEMO_TEACHERS]


class Command(BaseCommand):
    help = (
        "Deletes ONLY the dataset created by seed_demo_data (demo users, groups, "
        "students, lessons, attendance, homework, monthly reports). Never touches "
        "real data. Development/testing only — refuses to run when "
        "DJANGO_ENV=production. Requires --confirm."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--confirm",
            action="store_true",
            help="Required. Acknowledges this deletes the OkurmenKIDS demo dataset.",
        )

    def handle(self, *args, **options):
        env = os.environ.get("DJANGO_ENV", "development")
        if env == "production":
            raise CommandError(
                "Refusing to run: DJANGO_ENV=production. clear_demo_data never "
                "touches a production database, no flag can override this."
            )

        if not options["confirm"]:
            raise CommandError(
                "This deletes the OkurmenKIDS demo dataset (demo users, groups, "
                "students, lessons, attendance, homework, monthly reports). "
                "Re-run with --confirm to proceed."
            )

        self._clear()

    @transaction.atomic
    def _clear(self) -> None:
        w = self.stdout.write

        # Counted up front, one model at a time — `QuerySet.delete()` returns
        # the *total* number of rows removed across the whole cascade (e.g.
        # deleting Students also cascade-deletes their Attendance/
        # HomeworkResult rows), which would make a misleading summary line
        # if printed directly.
        lesson_qs = Lesson.objects.filter(group__name__in=DEMO_GROUP_NAMES)
        counts = {
            "monthly reports": MonthlyTeacherReport.objects.filter(
                teacher__user__username__in=DEMO_TEACHER_USERNAMES
            ).count(),
            "students": Student.objects.filter(group__name__in=DEMO_GROUP_NAMES).count(),
            "attendance": Attendance.objects.filter(lesson__in=lesson_qs).count(),
            "lessons": lesson_qs.count(),
            "homework": Homework.objects.filter(lesson__in=lesson_qs).count(),
            "homework results": HomeworkResult.objects.filter(homework__lesson__in=lesson_qs).count(),
            "groups": Group.objects.filter(name__in=DEMO_GROUP_NAMES).count(),
            "rooms": Room.objects.filter(name__in=DEMO_ROOM_NAMES).count(),
            "courses": Course.objects.filter(name__in=COURSE_DEFS.keys()).count(),
            "teacher users": User.objects.filter(username__in=DEMO_TEACHER_USERNAMES).count(),
        }

        MonthlyTeacherReport.objects.filter(teacher__user__username__in=DEMO_TEACHER_USERNAMES).delete()
        Student.objects.filter(group__name__in=DEMO_GROUP_NAMES).delete()
        # Cascades GroupSchedule, GroupTeacher, Lesson, Attendance, Homework,
        # HomeworkResult — see module docstring.
        Group.objects.filter(name__in=DEMO_GROUP_NAMES).delete()
        Room.objects.filter(name__in=DEMO_ROOM_NAMES).delete()
        Course.objects.filter(name__in=COURSE_DEFS.keys()).delete()
        # Safe now — every GroupTeacher (which PROTECTs Teacher) referencing
        # a demo teacher was already removed via the Group cascade above.
        User.objects.filter(username__in=DEMO_TEACHER_USERNAMES).delete()

        for label, count in counts.items():
            w(f"Deleted {label}: {count}")

        admin_qs = User.objects.filter(username=ADMIN_USERNAME, email=ADMIN_EMAIL)
        if admin_qs.exists():
            admin_qs.delete()
            w("Deleted demo admin user.")
        elif User.objects.filter(username=ADMIN_USERNAME).exists():
            w(self.style.WARNING(
                f"A user named '{ADMIN_USERNAME}' exists but its email isn't "
                f"'{ADMIN_EMAIL}' — leaving it alone, it isn't the demo account."
            ))

        w(self.style.SUCCESS("Demo dataset cleared. Subjects were left untouched (shared catalogue data)."))
        w(self.style.SUCCESS("Run `python manage.py seed_demo_data` to recreate it."))
