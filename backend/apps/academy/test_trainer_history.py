"""A group changing trainers never rewrites the previous trainer's KPI.

Scenario of the bug: trainer A runs the group in the previous month, the
group goes to trainer B on the 1st of the current month. A's previous month
must stay exactly what it was; B's current month is B's own work only.

Absolute imports only — see the note at the top of apps/academy/tests.py.
"""
from __future__ import annotations

import datetime as dt
import importlib
import shutil
import subprocess
import unittest
from contextlib import contextmanager
from unittest import mock

from django.apps import apps as django_apps
from django.contrib.admin.models import CHANGE, LogEntry
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.academy.models import (
    Attendance, Course, Group, GroupSchedule, GroupTeacher, Homework, HomeworkResult, Lesson, Student, TrainerAssignment,
)
from apps.academy.services import trainer_history
from apps.academy.services.reports import ReportFilters, build_full_report, build_teacher_detail
from apps.academy.services.trainer_assignment import assign_trainer
from apps.users.models import Subject, Teacher, User

PASSWORD = "Str0ngPassw0rd!"

TODAY = timezone.localdate()
CUR_START = TODAY.replace(day=1)
PREV_END = CUR_START - dt.timedelta(days=1)
PREV_START = PREV_END.replace(day=1)


def make_teacher(username: str) -> Teacher:
    user = User.objects.create_user(
        username=username, email=f"{username}@okurmen.kg", password=PASSWORD,
        first_name=username.capitalize(), last_name="T", role=User.Role.TEACHER, is_verified=True,
    )
    return Teacher.objects.create(user=user)


def period(start: dt.date, end: dt.date) -> ReportFilters:
    return ReportFilters.from_query({"period": "custom", "start_date": start.isoformat(), "end_date": end.isoformat()},
                                    today=TODAY)


@contextmanager
def on_day(day: dt.date):
    """Run an assignment change as if it happened on `day` (project time zone)."""
    with mock.patch("apps.academy.services.trainer_history.timezone.localdate", return_value=day):
        yield


def figures(detail: dict) -> dict:
    """What the trainer profile shows, minus the identity block."""
    return {
        "lessons": detail["lessons"],
        "attendance": detail["attendance"],
        "homework": detail["homework"],
        "kpi": detail["kpi"],
        "metrics": detail["metrics"],
        "groups": [g["id"] for g in detail["groups"]],
        "group_performance": [(g["id"], g["attendance_rate"], g["lessons"]) for g in detail["group_performance"]],
    }


class HandoverFixture(TestCase):
    def setUp(self):
        self.lead = User.objects.create_user(
            username="lead", email="lead@okurmen.kg", password=PASSWORD, first_name="Нурлан", role=User.Role.TEAM_LEAD,
        )
        self.python, _ = Subject.objects.get_or_create(name="Python")
        self.course = Course.objects.create(name="Prog SOFT", count_lesson=40)
        self.course.subjects.set([self.python])
        self.group = Group.objects.create(name="Prog SOFT 1", course=self.course, start_date=PREV_START - dt.timedelta(days=60))
        self.a = make_teacher("aibek")
        self.b = make_teacher("bakyt")
        self.c = make_teacher("chynara")
        with on_day(PREV_START - dt.timedelta(days=60)):
            self.program = GroupTeacher.objects.create(group=self.group, teacher=self.a, subject=self.python)
            GroupSchedule.objects.create(group=self.group, teacher=self.a, subject=self.python, day_of_week="mon",
                                         start_time=dt.time(10), end_time=dt.time(11))
        self.s1 = Student.objects.create(first_name="Азамат", last_name="Алиев", group=self.group)
        self.s2 = Student.objects.create(first_name="Айгерим", last_name="Өмүрова", group=self.group)
        self.number = 0

    def lesson(self, day: dt.date, *, status=Lesson.Status.COMPLETED, teacher="program", present=(True, True),
               homework=("checked", "not_submitted"), score=80):
        """A lesson of the program on `day` with attendance and homework results.
        `teacher="program"` — the trainer is filled by Lesson.save() from the
        program (what every new lesson gets); None — a legacy lesson without one."""
        self.number += 1
        lesson = Lesson.objects.create(
            group=self.group, group_teacher=self.program, subject=self.python, lesson_number=self.number,
            date=day, start_time=dt.time(10), end_time=dt.time(11), status=status,
            **({} if teacher == "program" else {"teacher": teacher}),
        )
        if teacher is None:
            Lesson.objects.filter(pk=lesson.pk).update(teacher=None)
            lesson.refresh_from_db()
        if status == Lesson.Status.COMPLETED:
            for student, here in zip((self.s1, self.s2), present):
                Attendance.objects.create(student=student, lesson=lesson,
                                          status=Attendance.Status.PRESENT if here else Attendance.Status.ABSENT)
            hw = Homework.objects.create(lesson=lesson, title="ДЗ")
            for student, result in zip((self.s1, self.s2), homework):
                HomeworkResult.objects.create(homework=hw, student=student, status=result,
                                              score=score if result == "checked" else None)
        return lesson

    def september(self):
        """A runs the group through the previous month (3 held lessons)."""
        return [
            self.lesson(PREV_START + dt.timedelta(days=2), present=(True, True)),
            self.lesson(PREV_START + dt.timedelta(days=9), present=(True, False)),
            self.lesson(PREV_START + dt.timedelta(days=16), present=(False, False), homework=("not_submitted", "not_submitted")),
        ]

    def hand_over(self, teacher, day=CUR_START, user=None):
        with on_day(day), mock.patch("apps.academy.services.program_editing.local_now",
                                     return_value=timezone.make_aware(dt.datetime.combine(day, dt.time(0, 1)))):
            return assign_trainer(self.group, teacher=teacher, user=user or self.lead, program=self.program)

    def detail(self, teacher, start=PREV_START, end=PREV_END):
        return build_teacher_detail(teacher, period(start, end))


class HandoverKeepsHistoryTests(HandoverFixture):
    def test_previous_trainer_month_is_unchanged_by_the_handover(self):
        """1–3: A ran September; the group goes to B in October; A's September KPI stays as it was."""
        self.september()
        before = figures(self.detail(self.a))
        self.assertEqual(before["lessons"]["held"], 3)
        self.assertEqual(before["groups"], [self.group.pk])

        self.hand_over(self.b)
        self.program.refresh_from_db()
        self.assertEqual(self.program.teacher_id, self.b.pk)  # the program itself moved on

        after = figures(self.detail(self.a))
        self.assertEqual(after, before)
        self.assertEqual(after["attendance"]["present"], 3)
        self.assertEqual(after["attendance"]["total"], 6)
        self.assertEqual(after["group_performance"][0][0], self.group.pk)

    def test_new_trainer_gets_only_their_own_month(self):
        """4: B's October is B's lessons only; B has nothing in September."""
        self.september()
        self.hand_over(self.b)
        self.lesson(CUR_START, present=(True, True), homework=("checked", "checked"), score=90)

        b_october = self.detail(self.b, CUR_START, TODAY)
        self.assertEqual(b_october["lessons"]["held"], 1)
        self.assertEqual(b_october["attendance"]["total"], 2)
        self.assertEqual(b_october["attendance"]["present"], 2)
        self.assertEqual(b_october["homework"]["submitted"], 2)
        self.assertEqual([g["id"] for g in b_october["groups"]], [self.group.pk])

        b_september = self.detail(self.b)
        self.assertEqual(b_september["lessons"]["total"], 0)
        self.assertEqual(b_september["attendance"]["total"], 0)
        self.assertEqual(b_september["groups"], [])  # B wasn't responsible for the group then

        a_october = self.detail(self.a, CUR_START, TODAY)
        self.assertEqual(a_october["lessons"]["total"], 0)
        self.assertEqual(a_october["attendance"]["total"], 0)

    def test_attendance_and_homework_stay_with_the_trainer_who_gave_the_lesson(self):
        """5–6: no attendance mark, homework result or score moves to the new trainer."""
        lessons = self.september()
        self.hand_over(self.b)
        for lesson in lessons:
            lesson.refresh_from_db()
            self.assertEqual(lesson.teacher_id, self.a.pk)
            self.assertEqual(lesson.effective_teacher, self.a)
        a = self.detail(self.a)
        b = self.detail(self.b)
        self.assertEqual((a["homework"]["results"], a["homework"]["submitted"]), (6, 2))
        self.assertEqual(a["homework"]["average_score"], 80.0)
        self.assertEqual((b["homework"]["results"], b["attendance"]["total"]), (0, 0))
        # The access rule follows the same history: B can't edit A's past lessons.
        self.assertFalse(Lesson.objects.for_teacher(self.b).filter(pk__in=[l.pk for l in lessons]).exists())
        self.assertEqual(Lesson.objects.for_teacher(self.a).filter(pk__in=[l.pk for l in lessons]).count(), 3)

    def test_future_lessons_move_and_past_ones_stay(self):
        self.september()
        monday = TODAY + dt.timedelta(days=7 + (7 - TODAY.weekday()) % 7)  # follows the Monday 10:00 slot
        future = self.lesson(monday, status=Lesson.Status.SCHEDULED)
        self.hand_over(self.b, day=TODAY)
        future.refresh_from_db()
        self.assertEqual(future.teacher_id, self.b.pk)

    def test_repeated_handover_keeps_every_period(self):
        """9: A → B → C: three non-overlapping assignments, each month its own trainer."""
        self.september()
        self.hand_over(self.b, day=CUR_START)
        if TODAY > CUR_START:
            self.lesson(CUR_START)
        later = min(TODAY, CUR_START + dt.timedelta(days=1)) if TODAY > CUR_START else CUR_START
        self.hand_over(self.c, day=later)
        self.hand_over(self.a, day=later)  # and back the same day: a zero-length row for C

        rows = list(TrainerAssignment.objects.filter(program=self.program).order_by("start_date", "id"))
        self.assertEqual([r.teacher_id for r in rows], [self.a.pk, self.b.pk, self.c.pk, self.a.pk])
        self.assertEqual(TrainerAssignment.objects.filter(program=self.program, end_date__isnull=True).count(), 1)
        for prev, nxt in zip(rows, rows[1:]):
            self.assertEqual(prev.end_date, nxt.start_date)  # back to back, never overlapping
        self.assertEqual(rows[2].start_date, rows[2].end_date)  # C — replaced the same day, covers no date
        self.assertEqual(rows[1].changed_by, self.lead)

        self.assertEqual(self.detail(self.a)["lessons"]["held"], 3)
        self.assertEqual(self.detail(self.c)["lessons"]["total"], 0)
        if TODAY > CUR_START:
            self.assertEqual(self.detail(self.b, CUR_START, CUR_START)["lessons"]["held"], 1)

    def test_deactivating_closes_and_reactivating_opens(self):
        with on_day(CUR_START):
            self.program.is_active = False
            self.program.save(update_fields=["is_active", "updated_at"])
        self.assertFalse(TrainerAssignment.objects.filter(program=self.program, end_date__isnull=True).exists())
        with on_day(TODAY):
            self.program.is_active = True
            self.program.save(update_fields=["is_active", "updated_at"])
        self.assertEqual(TrainerAssignment.objects.filter(program=self.program).count(), 2)


class PeriodFilterTests(HandoverFixture):
    def test_last_month_period_shows_the_previous_trainer(self):
        """7: the «Прошлый месяц» filter of the profile API, after the handover."""
        self.september()
        self.hand_over(self.b)
        api = APIClient()
        api.force_authenticate(self.lead)
        a = api.get(f"/api/v1/reports/teachers/{self.a.pk}/", {"period": "last_month"}).data
        self.assertEqual(a["lessons"]["held"], 3)
        self.assertEqual([g["id"] for g in a["group_performance"]], [self.group.pk])
        b = api.get(f"/api/v1/reports/teachers/{self.b.pk}/", {"period": "last_month"}).data
        self.assertEqual(b["lessons"]["total"], 0)
        self.assertEqual(b["group_performance"], [])

    def test_group_row_lists_the_trainer_of_that_period(self):
        self.september()
        self.hand_over(self.b)
        rows = build_full_report(period(PREV_START, PREV_END))["groups"]
        row = next(r for r in rows if r["id"] == self.group.pk)
        self.assertEqual([t["id"] for t in row["teachers"]], [self.a.pk])
        rows = build_full_report(period(CUR_START, TODAY))["groups"]
        row = next(r for r in rows if r["id"] == self.group.pk)
        self.assertEqual([t["id"] for t in row["teachers"]], [self.b.pk])

    def test_teachers_of_a_group_report_include_the_previous_trainer(self):
        self.september()
        self.hand_over(self.b)
        filters = ReportFilters.from_query({"period": "custom", "start_date": PREV_START.isoformat(),
                                            "end_date": PREV_END.isoformat(), "group": self.group.pk}, today=TODAY)
        teachers = {row["id"]: row for row in build_full_report(filters)["teachers"]}
        self.assertIn(self.a.pk, teachers)
        self.assertEqual(teachers[self.a.pk]["lessons"]["held"], 3)
        self.assertNotIn(self.b.pk, teachers)


def _pdf_text(content: bytes) -> str:
    if not shutil.which("pdftotext"):
        raise unittest.SkipTest("pdftotext is not available")
    return subprocess.run(["pdftotext", "-layout", "-", "-"], input=content, capture_output=True, check=True).stdout.decode()


class ProfileAndPdfTests(HandoverFixture):
    def test_profile_and_pdf_show_the_same_figures(self):
        """8: the trainer profile and the Reports PDF come from one calculation."""
        self.september()
        self.hand_over(self.b)
        api = APIClient()
        api.force_authenticate(self.lead)
        params = {"period": "custom", "start_date": PREV_START.isoformat(), "end_date": PREV_END.isoformat()}
        profile = api.get(f"/api/v1/reports/teachers/{self.a.pk}/", params).data
        row = next(t for t in build_full_report(period(PREV_START, PREV_END))["teachers"] if t["id"] == self.a.pk)
        self.assertEqual(row["lessons"], {k: profile["lessons"][k] for k in row["lessons"]})
        self.assertEqual(row["attendance_rate"], profile["attendance"]["rate"])
        self.assertEqual(row["homework_rate"], profile["homework"]["completion_rate"])
        self.assertEqual([g["id"] for g in row["groups"]], [g["id"] for g in profile["groups"]])

        pdf = api.get("/api/v1/reports/export/pdf/", {**params, "teacher": self.a.pk})
        self.assertEqual(pdf.status_code, 200)
        text = _pdf_text(pdf.content)
        self.assertIn("Aibek T", text)
        self.assertIn(f"{profile['attendance']['rate']:g}%", text.replace(",", "."))

        # The Team Lead's trainer review (worklog) reads the same service.
        from apps.worklog.metrics import teacher_metrics

        review = teacher_metrics(self.a, PREV_START, PREV_END)
        self.assertEqual(review["attendance"], profile["attendance"]["rate"])
        self.assertEqual([*review["groups"]], [self.group.name])


class LegacyDataTests(HandoverFixture):
    def test_legacy_lesson_without_trainer_follows_the_history_not_the_current_trainer(self):
        """10: a lesson that never stored its trainer is not handed to the current one."""
        legacy = self.lesson(PREV_START + dt.timedelta(days=3), teacher=None)
        self.hand_over(self.b)
        self.assertIsNone(Lesson.objects.get(pk=legacy.pk).teacher_id)
        self.assertEqual(Lesson.objects.get(pk=legacy.pk).effective_teacher, self.a)  # A's assignment covers it
        self.assertEqual(self.detail(self.a)["lessons"]["held"], 1)
        self.assertEqual(self.detail(self.b)["lessons"]["total"], 0)

    def test_lesson_outside_any_known_assignment_counts_for_nobody(self):
        TrainerAssignment.objects.filter(program=self.program).update(start_date=CUR_START)  # history starts later
        orphan = self.lesson(PREV_START + dt.timedelta(days=3), teacher=None)
        self.assertIsNone(Lesson.objects.get(pk=orphan.pk).effective_teacher)
        self.assertEqual(self.detail(self.a)["lessons"]["total"], 0)
        # …but it still counts for the group.
        group_row = next(r for r in build_full_report(period(PREV_START, PREV_END))["groups"] if r["id"] == self.group.pk)
        self.assertEqual(group_row["lessons"]["held"], 1)

    def test_new_lessons_always_store_their_trainer(self):
        lesson = self.lesson(TODAY, status=Lesson.Status.SCHEDULED)
        self.assertEqual(lesson.teacher_id, self.a.pk)

    def _run_backfill(self):
        migration = importlib.import_module("apps.academy.migrations.0023_backfill_trainer_history")
        migration.backfill(django_apps, None)

    def test_migration_backfills_only_confirmed_history(self):
        """Legacy data: a program whose trainer change is on record keeps
        older trainer-less lessons unattributed; a program with no change on
        record gets its trainer for all of them."""
        clean_lesson = self.lesson(PREV_START + dt.timedelta(days=2), teacher=None)
        other_group = Group.objects.create(name="Prog SOFT 2", course=self.course, start_date=PREV_START)
        changed = GroupTeacher.objects.create(group=other_group, teacher=self.b, subject=self.python)
        old = Lesson.objects.create(group=other_group, group_teacher=changed, subject=self.python, lesson_number=1,
                                    date=PREV_START + dt.timedelta(days=2), start_time=dt.time(12), end_time=dt.time(13))
        new = Lesson.objects.create(group=other_group, group_teacher=changed, subject=self.python, lesson_number=2,
                                    date=CUR_START + dt.timedelta(days=1), start_time=dt.time(12), end_time=dt.time(13))
        Lesson.objects.filter(pk__in=[old.pk, new.pk]).update(teacher=None)
        LogEntry.objects.create(
            user=self.lead, content_type=ContentType.objects.get_for_model(GroupTeacher), object_id=str(changed.pk),
            object_repr=str(changed), action_flag=CHANGE, change_message="Заменил тренера группы «Prog SOFT 2» (Python): Aibek T → Bakyt T.",
        )
        LogEntry.objects.filter(object_id=str(changed.pk)).update(
            action_time=timezone.make_aware(dt.datetime.combine(CUR_START, dt.time(12))))
        TrainerAssignment.objects.all().delete()  # the state before the migration

        self._run_backfill()

        self.assertEqual(Lesson.objects.get(pk=clean_lesson.pk).teacher_id, self.a.pk)
        self.assertIsNone(Lesson.objects.get(pk=old.pk).teacher_id)  # before the recorded change: unknown
        self.assertEqual(Lesson.objects.get(pk=new.pk).teacher_id, self.b.pk)
        history = TrainerAssignment.objects.get(program=changed)
        self.assertEqual((history.start_date, history.source), (CUR_START, "migration"))
        self.assertEqual(self.detail(self.b)["lessons"]["total"], 0)  # B gets no lesson he may not have given

        self._run_backfill()  # idempotent
        self.assertEqual(TrainerAssignment.objects.filter(program=changed).count(), 1)

    def test_migration_uses_lessons_of_another_trainer_as_evidence(self):
        self.lesson(PREV_START + dt.timedelta(days=2), teacher=self.c)  # given by C, program now A's
        orphan = self.lesson(PREV_START + dt.timedelta(days=1), teacher=None)
        later = self.lesson(PREV_START + dt.timedelta(days=9), teacher=None)
        TrainerAssignment.objects.all().delete()
        self._run_backfill()
        self.assertIsNone(Lesson.objects.get(pk=orphan.pk).teacher_id)
        self.assertEqual(Lesson.objects.get(pk=later.pk).teacher_id, self.a.pk)

    def test_audit_command_lists_unattributed_lessons(self):
        from io import StringIO

        from django.core.management import call_command

        TrainerAssignment.objects.filter(program=self.program).update(start_date=CUR_START)
        self.lesson(PREV_START + dt.timedelta(days=3), teacher=None)
        out = StringIO()
        call_command("audit_trainer_history", stdout=out)
        self.assertIn("Занятий без определимого тренера: 1", out.getvalue())


class HistoryRecordTests(HandoverFixture):
    def test_handover_through_the_api_records_who_and_when(self):
        api = APIClient()
        api.force_authenticate(self.lead)
        with on_day(TODAY):
            response = api.post(f"/api/v1/groups/{self.group.pk}/assign-trainer/",
                                {"program": self.program.pk, "teacher": self.b.pk}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        closed, current = TrainerAssignment.objects.filter(program=self.program).order_by("id")
        self.assertEqual((closed.teacher_id, closed.end_date), (self.a.pk, TODAY))
        self.assertIsNotNone(closed.closed_at)
        self.assertEqual((current.teacher_id, current.start_date, current.end_date), (self.b.pk, TODAY, None))
        self.assertEqual(current.changed_by, self.lead)
        self.assertEqual(trainer_history.teacher_at(self.program.pk, TODAY - dt.timedelta(days=1)), self.a)
        self.assertEqual(trainer_history.teacher_at(self.program.pk, TODAY), self.b)

    def test_history_is_read_only_in_admin(self):
        admin = User.objects.create_superuser(username="root", email="root@okurmen.kg", password=PASSWORD)
        client = self.client
        client.force_login(admin)
        row = TrainerAssignment.objects.get(program=self.program)
        self.assertEqual(client.get(f"/admin/academy/trainerassignment/{row.pk}/delete/").status_code, 403)
        self.assertEqual(client.get("/admin/academy/trainerassignment/").status_code, 200)
