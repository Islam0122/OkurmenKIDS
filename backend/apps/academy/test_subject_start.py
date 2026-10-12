"""Each subject of a group has its own start date (models.GroupSubject,
services.subject_start): generation, re-planning on change, KPI, API and
permissions.

Absolute imports only — see the note at the top of apps/academy/tests.py.
"""
from __future__ import annotations

import datetime as dt
import threading
from unittest import skipUnless

from django.contrib.admin.models import LogEntry
from django.core.exceptions import ValidationError
from django.db import connection
from django.test import TestCase, TransactionTestCase
from django.test.utils import CaptureQueriesContext
from rest_framework import status
from rest_framework.test import APIClient

from apps.academy.models import (
    Attendance,
    Course,
    CourseLessonPlan,
    Group,
    GroupSchedule,
    GroupSubject,
    GroupTeacher,
    Lesson,
    Student,
)
from apps.academy.services.kpi_engine import KPIEngine
from apps.academy.services.lesson_generator import generate_lessons_for_group_with_report
from apps.academy.services.lesson_move import move_lesson
from apps.academy.services.subject_start import overview, set_subject_start_date
from apps.users.models import Subject, Teacher, User

PASSWORD = "Str0ngPassw0rd!"
D = dt.date


def make_user(username: str, role: str) -> User:
    return User.objects.create_user(
        username=username, email=f"{username}@okurmen.kg", password=PASSWORD,
        first_name=username.capitalize(), last_name="T", role=role, is_verified=True,
    )


def make_teacher(username: str) -> Teacher:
    return Teacher.objects.create(user=make_user(username, User.Role.TEACHER))


class SubjectStartData:
    """Group starts Mon 05.10.2026. IT: Sat/Mon/Wed 09:00 (Ivan), English:
    Mon/Wed/Fri 10:00 (Aida); 4 plan rows each."""

    def setUp(self):
        self.it, _ = Subject.objects.get_or_create(name="IT")
        self.english, _ = Subject.objects.get_or_create(name="English")
        self.course = Course.objects.create(name="Prog SOFT", count_lesson=8)
        self.course.subjects.set([self.it, self.english])
        for number in range(1, 9):
            subject = self.it if number % 2 else self.english
            CourseLessonPlan.objects.create(course=self.course, lesson_number=number, subject=subject, topic=f"Тема {number}")
        self.group = Group.objects.create(name="Prog SOFT 1", course=self.course, start_date=D(2026, 10, 5))
        self.ivan = make_teacher("ivan")
        self.aida = make_teacher("aida")
        for day in ("sat", "mon", "wed"):
            GroupSchedule.objects.create(
                group=self.group, teacher=self.ivan, subject=self.it, day_of_week=day,
                start_time=dt.time(9), end_time=dt.time(10),
            )
        for day in ("mon", "wed", "fri"):
            GroupSchedule.objects.create(
                group=self.group, teacher=self.aida, subject=self.english, day_of_week=day,
                start_time=dt.time(10), end_time=dt.time(11),
            )
        self.it_program = GroupTeacher.objects.get(group=self.group, subject=self.it)
        self.english_program = GroupTeacher.objects.get(group=self.group, subject=self.english)
        self.student = Student.objects.create(first_name="Азамат", last_name="Алиев", group=self.group)
        self.lead = make_user("lead", User.Role.TEAM_LEAD)
        self.assistant = make_user("assist", User.Role.ASSISTANT)

    def dates(self, subject) -> list[dt.date]:
        return list(
            Lesson.objects.filter(group=self.group, subject=subject).order_by("date").values_list("date", flat=True)
        )

    def set_starts(self, it=D(2026, 10, 10), english=D(2026, 10, 12)):
        GroupSubject.objects.create(group=self.group, subject=self.it, start_date=it)
        GroupSubject.objects.create(group=self.group, subject=self.english, start_date=english)


class SubjectStartFixture(SubjectStartData, TestCase):
    pass


class GenerationRespectsSubjectStartTests(SubjectStartFixture):
    def test_existing_group_without_dates_starts_every_subject_with_the_group(self):
        generate_lessons_for_group_with_report(self.group)
        self.assertEqual(self.dates(self.it)[0], D(2026, 10, 5))  # Monday — the group's start
        self.assertEqual(self.dates(self.english)[0], D(2026, 10, 5))
        self.assertEqual(Lesson.objects.filter(group=self.group).count(), 8)

    def test_each_subject_starts_on_its_own_date(self):
        self.set_starts(it=D(2026, 10, 10), english=D(2026, 10, 12))
        report = generate_lessons_for_group_with_report(self.group)
        self.assertEqual(report.created, 8)
        self.assertEqual(self.dates(self.it), [D(2026, 10, 10), D(2026, 10, 12), D(2026, 10, 14), D(2026, 10, 17)])
        self.assertEqual(self.dates(self.english), [D(2026, 10, 12), D(2026, 10, 14), D(2026, 10, 16), D(2026, 10, 19)])
        self.group.refresh_from_db()
        self.assertEqual(self.group.start_date, D(2026, 10, 5))

    def test_it_has_started_and_english_has_not(self):
        self.set_starts(it=D(2026, 10, 10), english=D(2026, 10, 12))
        generate_lessons_for_group_with_report(self.group)
        rows = {row["subject"]["name"]: row for row in overview(self.group, today=D(2026, 10, 11))["subjects"]}
        self.assertEqual(rows["IT"]["status"], "in_progress")
        self.assertEqual(rows["IT"]["status_display"], "Идёт обучение")
        self.assertEqual(rows["English"]["status"], "not_started")
        self.assertEqual(rows["English"]["start_date"], D(2026, 10, 12))
        self.assertTrue(rows["English"]["is_custom"])

    def test_generation_twice_creates_no_duplicates(self):
        self.set_starts()
        generate_lessons_for_group_with_report(self.group)
        second = generate_lessons_for_group_with_report(self.group)
        self.assertEqual(second.created, 0)
        self.assertEqual(Lesson.objects.filter(group=self.group).count(), 8)


class ChangeSubjectStartTests(SubjectStartFixture):
    def setUp(self):
        super().setUp()
        self.set_starts()
        generate_lessons_for_group_with_report(self.group)

    def test_later_start_moves_only_that_subjects_open_lessons(self):
        it_before = list(Lesson.objects.filter(subject=self.it).values_list("pk", "date", "start_time"))
        english_ids = sorted(Lesson.objects.filter(subject=self.english).values_list("pk", flat=True))

        change = set_subject_start_date(self.group, self.english, D(2026, 10, 19), user=self.lead)

        self.assertEqual(change.previous, D(2026, 10, 12))
        self.assertEqual(change.moved, 4)
        self.assertEqual(self.dates(self.english), [D(2026, 10, 19), D(2026, 10, 21), D(2026, 10, 23), D(2026, 10, 26)])
        # Same rows, same numbers: nothing deleted or recreated.
        self.assertEqual(sorted(Lesson.objects.filter(subject=self.english).values_list("pk", flat=True)), english_ids)
        self.assertEqual(
            list(Lesson.objects.filter(subject=self.english).order_by("date").values_list("lesson_number", flat=True)),
            [2, 4, 6, 8],
        )
        # IT and the group's own dates are untouched.
        self.assertEqual(list(Lesson.objects.filter(subject=self.it).values_list("pk", "date", "start_time")), it_before)
        self.group.refresh_from_db()
        self.assertEqual(self.group.start_date, D(2026, 10, 5))
        self.assertEqual(GroupSubject.objects.get(group=self.group, subject=self.it).start_date, D(2026, 10, 10))
        self.assertTrue(LogEntry.objects.filter(object_id=str(self.group.pk), change_message__contains="English").exists())
        # A regeneration afterwards neither duplicates nor moves anything back.
        report = generate_lessons_for_group_with_report(self.group)
        self.assertEqual(report.created, 0)
        self.assertEqual(self.dates(self.english)[0], D(2026, 10, 19))

    def test_earlier_start_of_a_subject_not_yet_given_pulls_it_forward(self):
        set_subject_start_date(self.group, self.english, D(2026, 10, 7))
        self.assertEqual(self.dates(self.english), [D(2026, 10, 7), D(2026, 10, 9), D(2026, 10, 12), D(2026, 10, 14)])

    def test_start_after_a_conducted_lesson_is_refused_and_history_kept(self):
        first = Lesson.objects.filter(subject=self.english).order_by("date").first()
        Attendance.objects.create(lesson=first, student=self.student, status=Attendance.Status.PRESENT)
        with self.assertRaises(ValidationError) as ctx:
            set_subject_start_date(self.group, self.english, D(2026, 10, 19))
        self.assertIn("уже есть проведённые", str(ctx.exception))
        self.assertEqual(self.dates(self.english)[0], D(2026, 10, 12))
        self.assertEqual(GroupSubject.objects.get(group=self.group, subject=self.english).start_date, D(2026, 10, 12))

    def test_start_before_group_start_or_after_its_end_is_refused(self):
        with self.assertRaises(ValidationError):
            set_subject_start_date(self.group, self.english, D(2026, 10, 1))
        self.group.end_date = D(2026, 12, 31)
        self.group.save()
        with self.assertRaises(ValidationError):
            set_subject_start_date(self.group, self.english, D(2027, 1, 5))

    def test_lessons_that_no_longer_fit_before_group_end_change_nothing(self):
        self.group.end_date = D(2026, 10, 24)
        self.group.save()
        with self.assertRaises(ValidationError):
            set_subject_start_date(self.group, self.english, D(2026, 10, 19))
        self.assertEqual(self.dates(self.english)[0], D(2026, 10, 12))
        self.assertEqual(GroupSubject.objects.get(group=self.group, subject=self.english).start_date, D(2026, 10, 12))

    def test_lesson_cannot_be_moved_by_hand_before_its_subject_start(self):
        lesson = Lesson.objects.filter(subject=self.english).order_by("date").first()
        with self.assertRaises(ValidationError):
            move_lesson(lesson, date=D(2026, 10, 8), start_time=dt.time(15), end_time=dt.time(16))


class KpiIgnoresLessonsBeforeSubjectStartTests(SubjectStartFixture):
    def test_lessons_before_the_subject_start_are_not_due_and_their_attendance_not_counted(self):
        GroupSubject.objects.create(group=self.group, subject=self.english, start_date=D(2026, 10, 12))
        # Planned before the start (e.g. data from before the date existed).
        early = Lesson.objects.create(
            group=self.group, group_teacher=self.english_program, subject=self.english, lesson_number=2,
            date=D(2026, 10, 7), start_time=dt.time(10), end_time=dt.time(11),
        )
        Attendance.objects.create(lesson=early, student=self.student, status=Attendance.Status.ABSENT)
        it_lesson = Lesson.objects.create(
            group=self.group, group_teacher=self.it_program, subject=self.it, lesson_number=1,
            date=D(2026, 10, 7), start_time=dt.time(9), end_time=dt.time(10), status=Lesson.Status.COMPLETED,
        )
        Attendance.objects.create(lesson=it_lesson, student=self.student, status=Attendance.Status.PRESENT)

        result = KPIEngine.calculate(start=D(2026, 10, 1), end=D(2026, 10, 31), group_id=self.group.pk, today=D(2026, 10, 11))
        self.assertEqual(result.counts.lessons_due, 1)
        self.assertEqual(result.counts.lessons_held, 1)
        self.assertEqual(result.counts.attendance_total, 1)
        self.assertEqual(result.metrics_exact["attendance"], 100)

        teacher_kpi = KPIEngine.calculate(
            start=D(2026, 10, 1), end=D(2026, 10, 31), teacher_id=self.aida.pk, today=D(2026, 10, 11),
        )
        self.assertEqual(teacher_kpi.counts.lessons_due, 0)

    def test_group_without_subject_dates_keeps_its_kpi(self):
        Lesson.objects.create(
            group=self.group, group_teacher=self.english_program, subject=self.english, lesson_number=2,
            date=D(2026, 10, 7), start_time=dt.time(10), end_time=dt.time(11),
        )
        result = KPIEngine.calculate(start=D(2026, 10, 1), end=D(2026, 10, 31), group_id=self.group.pk, today=D(2026, 10, 11))
        self.assertEqual(result.counts.lessons_due, 1)


class SubjectStartApiTests(SubjectStartFixture):
    def url(self, subject=None, prefix="/api/v1"):
        base = f"{prefix}/groups/{self.group.pk}/subject-start-dates/"
        return f"{base}{subject.pk}/" if subject else base

    def client_for(self, user):
        api = APIClient()
        api.force_authenticate(user)
        return api

    def test_team_lead_reads_and_changes_one_subject(self):
        api = self.client_for(self.lead)
        data = api.get(self.url()).data
        self.assertEqual([(r["subject"]["name"], r["start_date"], r["is_custom"]) for r in data["subjects"]],
                         [("English", D(2026, 10, 5), False), ("IT", D(2026, 10, 5), False)])

        response = api.patch(self.url(self.english), {"start_date": "2026-10-12"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data["saved"]["start_date"], D(2026, 10, 12))
        rows = {r["subject"]["name"]: r for r in response.data["subjects"]}
        self.assertEqual(rows["English"]["start_date"], D(2026, 10, 12))
        self.assertEqual(rows["IT"]["start_date"], D(2026, 10, 5))
        self.assertFalse(GroupSubject.objects.filter(subject=self.it).exists())
        self.group.refresh_from_db()
        self.assertEqual(self.group.start_date, D(2026, 10, 5))

        # The group endpoint returns every subject's date as well (JSON).
        group = api.get(f"/api/v1/groups/{self.group.pk}/").json()
        self.assertIn({"subject": self.english.pk, "subject_name": "English", "start_date": "2026-10-12", "is_custom": True},
                      group["subject_starts"])

    def test_invalid_dates_are_400(self):
        api = self.client_for(self.lead)
        self.assertEqual(api.patch(self.url(self.english), {"start_date": "12.10.2026"}, format="json").status_code, 400)
        response = api.patch(self.url(self.english), {"start_date": "2026-09-01"}, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("start_date", response.data)
        other, _ = Subject.objects.get_or_create(name="Soft Skills")
        self.assertEqual(api.patch(self.url(other), {"start_date": "2026-10-12"}, format="json").status_code, 400)

    def test_assistant_may_change_dates_in_its_workspace_and_the_lms(self):
        api = self.client_for(self.assistant)
        response = api.patch(self.url(self.english, prefix="/api/v1/assistant"), {"start_date": "2026-10-12"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(api.get(self.url(prefix="/api/v1/assistant")).status_code, 200)
        self.assertEqual(api.patch(self.url(self.it), {"start_date": "2026-10-10"}, format="json").status_code, 200)

    def test_trainer_and_anonymous_cannot_change_dates(self):
        api = self.client_for(self.ivan.user)
        self.assertEqual(api.get(self.url()).status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(api.patch(self.url(self.it), {"start_date": "2026-10-12"}, format="json").status_code, 403)
        self.assertEqual(
            api.patch(self.url(self.it, prefix="/api/v1/assistant"), {"start_date": "2026-10-12"}, format="json").status_code,
            403,
        )
        self.assertEqual(APIClient().patch(self.url(self.it), {"start_date": "2026-10-12"}, format="json").status_code, 401)
        self.assertFalse(GroupSubject.objects.exists())

    def test_team_lead_still_cannot_change_the_group_itself(self):
        response = self.client_for(self.lead).patch(f"/api/v1/groups/{self.group.pk}/", {"start_date": "2026-10-12"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.group.refresh_from_db()
        self.assertEqual(self.group.start_date, D(2026, 10, 5))

    def test_trainer_sees_the_dates_in_the_group(self):
        GroupSubject.objects.create(group=self.group, subject=self.english, start_date=D(2026, 10, 12))
        group = self.client_for(self.ivan.user).get(f"/api/v1/groups/{self.group.pk}/").json()
        dates = {row["subject_name"]: row["start_date"] for row in group["subject_starts"]}
        self.assertEqual(dates, {"English": "2026-10-12", "IT": "2026-10-05"})


class SubjectStartAdminTests(SubjectStartFixture):
    def test_admin_saves_through_the_service(self):
        admin = User.objects.create_superuser(username="root", email="root@okurmen.kg", password=PASSWORD)
        self.client.force_login(admin)
        generate_lessons_for_group_with_report(self.group)
        response = self.client.post("/admin/academy/groupsubject/add/", {
            "group": self.group.pk, "subject": self.english.pk, "start_date": "2026-10-12",
        })
        self.assertEqual(response.status_code, 302, getattr(response, "context", None) and response.context["errors"])
        self.assertEqual(GroupSubject.objects.get().start_date, D(2026, 10, 12))
        self.assertEqual(self.dates(self.english)[0], D(2026, 10, 12))

    def test_admin_changes_only_the_date_of_an_existing_row(self):
        admin = User.objects.create_superuser(username="root", email="root@okurmen.kg", password=PASSWORD)
        self.client.force_login(admin)
        row = GroupSubject.objects.create(group=self.group, subject=self.english, start_date=D(2026, 10, 12))
        generate_lessons_for_group_with_report(self.group)
        response = self.client.post(f"/admin/academy/groupsubject/{row.pk}/change/", {"start_date": "2026-10-19"})
        self.assertEqual(response.status_code, 302)
        row.refresh_from_db()
        self.assertEqual(row.start_date, D(2026, 10, 19))
        self.assertEqual(self.dates(self.english)[0], D(2026, 10, 19))
        self.assertEqual(self.dates(self.it)[0], D(2026, 10, 5))


# ---------------------------------------------------------------------------
# PostgreSQL: the subject's lessons are loaded with nullable relations
# (schedule, group_teacher, the make-up — LEFT OUTER JOIN). Only the lesson
# and group rows may be locked: "FOR UPDATE cannot be applied to the nullable
# side of an outer join" (HTTP 500 on PATCH .../subject-start-dates/{id}/).
# SQLite ignores FOR UPDATE, so these run on PostgreSQL only.
# ---------------------------------------------------------------------------

def _with_nullable_relations(fixture):
    """Lessons whose nullable joins really are NULL / present: a lesson
    whose slot was deleted (schedule NULL), a cancelled lesson with its
    make-up (rescheduled_to), the rest with their slot and program."""
    generate_lessons_for_group_with_report(fixture.group)
    english = list(Lesson.objects.filter(subject=fixture.english).order_by("date"))
    Lesson.objects.filter(pk=english[1].pk).update(schedule=None)
    it = list(Lesson.objects.filter(subject=fixture.it).order_by("date"))
    Lesson.objects.filter(pk=it[-1].pk).update(status=Lesson.Status.CANCELLED)
    Lesson.objects.create(
        group=fixture.group, group_teacher=fixture.it_program, subject=fixture.it, lesson_number=it[-1].lesson_number,
        date=D(2026, 10, 31), start_time=dt.time(9), end_time=dt.time(10), rescheduled_from=it[-1],
    )


@skipUnless(connection.vendor == "postgresql", "row locks are only emitted on PostgreSQL")
class SubjectStartLockingTests(SubjectStartFixture):
    def test_only_lesson_and_group_rows_are_locked(self):
        _with_nullable_relations(self)
        with CaptureQueriesContext(connection) as ctx:
            set_subject_start_date(self.group, self.english, D(2026, 10, 19))
        locking = [q["sql"] for q in ctx.captured_queries if "FOR UPDATE" in q["sql"]]
        self.assertTrue(any("LEFT OUTER JOIN" in sql and 'FOR UPDATE OF "academy_lesson"' in sql for sql in locking))
        self.assertTrue(any('FOR UPDATE OF "academy_group"' in sql for sql in locking))
        for sql in locking:
            if "JOIN" in sql:  # a joined query locks only its own table
                self.assertRegex(sql, r'FOR UPDATE OF "academy_(lesson|group)"$')
            else:  # update_or_create's own lock of the GroupSubject row
                self.assertIn('FROM "academy_groupsubject"', sql)


@skipUnless(connection.vendor == "postgresql", "needs real transactions and row locks (PostgreSQL)")
class SubjectStartPostgresApiTests(SubjectStartData, TransactionTestCase):
    """Committed transactions, as in production (no test-case atomic block)."""

    def setUp(self):
        super().setUp()
        self.set_starts()
        _with_nullable_relations(self)

    def patch(self, subject, start_date, user=None):
        api = APIClient()
        api.force_authenticate(user or self.assistant)
        return api.patch(
            f"/api/v1/assistant/groups/{self.group.pk}/subject-start-dates/{subject.pk}/",
            {"start_date": start_date}, format="json",
        )

    def test_patch_changes_one_subject_with_nullable_relations(self):
        it_before = list(Lesson.objects.filter(subject=self.it).order_by("pk").values_list("pk", "date", "status"))
        english_ids = set(Lesson.objects.filter(subject=self.english).values_list("pk", flat=True))

        response = self.patch(self.english, "2026-10-19")

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.content)
        self.assertEqual(response.json()["saved"]["start_date"], "2026-10-19")
        self.assertEqual(GroupSubject.objects.get(group=self.group, subject=self.english).start_date, D(2026, 10, 19))
        self.assertEqual(GroupSubject.objects.get(group=self.group, subject=self.it).start_date, D(2026, 10, 10))
        self.assertEqual(set(Lesson.objects.filter(subject=self.english).values_list("pk", flat=True)), english_ids)
        self.assertEqual(min(self.dates(self.english)), D(2026, 10, 19))
        # The detached lesson got a slot of its program back.
        self.assertFalse(Lesson.objects.filter(subject=self.english, schedule__isnull=True).exists())
        self.assertEqual(
            list(Lesson.objects.filter(subject=self.it).order_by("pk").values_list("pk", "date", "status")), it_before,
        )
        self.group.refresh_from_db()
        self.assertEqual((self.group.start_date, self.group.end_date), (D(2026, 10, 5), None))

    def test_concurrent_changes_keep_the_data_consistent(self):
        barrier = threading.Barrier(3)
        responses, errors = [], []

        def worker(subject, start_date):
            try:
                barrier.wait(timeout=10)
                responses.append(self.patch(subject, start_date).status_code)
            except Exception as exc:  # surfaced by the assertions below
                errors.append(exc)
            finally:
                connection.close()

        threads = [
            threading.Thread(target=worker, args=(self.english, "2026-10-19")),
            threading.Thread(target=worker, args=(self.english, "2026-10-26")),
            threading.Thread(target=worker, args=(self.it, "2026-10-12")),
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=60)

        self.assertEqual(errors, [])
        self.assertEqual(sorted(responses), [200, 200, 200])
        starts = dict(GroupSubject.objects.filter(group=self.group).values_list("subject_id", "start_date"))
        self.assertIn(starts[self.english.pk], (D(2026, 10, 19), D(2026, 10, 26)))
        self.assertEqual(starts[self.it.pk], D(2026, 10, 12))
        self.assertEqual(GroupSubject.objects.filter(group=self.group).count(), 2)

        live = list(Lesson.objects.filter(group=self.group).exclude(status=Lesson.Status.CANCELLED))
        self.assertEqual(len(live), 8)  # nothing deleted or duplicated
        for lesson in live:
            self.assertGreaterEqual(lesson.date, starts[lesson.subject_id], lesson)
        # One live lesson per program and number, never two at the same time.
        self.assertEqual(len({(l.group_teacher_id, l.lesson_number) for l in live}), 8)
        slots = [(l.date, l.start_time) for l in live]
        self.assertEqual(len(slots), len(set(slots)))
        self.group.refresh_from_db()
        self.assertEqual(self.group.start_date, D(2026, 10, 5))
