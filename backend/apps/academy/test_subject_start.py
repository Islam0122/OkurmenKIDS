"""Each subject of a group has its own start date (models.GroupSubject,
services.subject_start): generation, re-planning on change, KPI, API and
permissions.

Absolute imports only — see the note at the top of apps/academy/tests.py.
"""
from __future__ import annotations

import datetime as dt

from django.contrib.admin.models import LogEntry
from django.core.exceptions import ValidationError
from django.test import TestCase
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


class SubjectStartFixture(TestCase):
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
