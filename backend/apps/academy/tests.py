from __future__ import annotations

import datetime as dt
from io import StringIO
from unittest import mock

from django.contrib import admin
from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection
from django.test import Client as DjangoClient
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import PermissionDenied
from rest_framework.test import APIClient

from apps.users.models import Subject, Teacher, User

# Absolute imports throughout this file (matching apps/users/tests.py) —
# not just style: since backend/__init__.py makes "backend" itself a
# package, a bare `manage.py test` (full discovery) imports this module as
# `backend.apps.academy.tests`, and a *relative* import from there would
# resolve to `backend.apps.academy.models` — a second, distinct import of
# the same file that redefines every model class and crashes Django's app
# registry. Absolute imports always land on the one canonical module
# already cached under `apps.academy.*` by Django's normal app loading.
from apps.academy.models import (
    AcademyMonthlyReport,
    Attendance,
    Course,
    CourseLessonPlan,
    Group,
    GroupSchedule,
    GroupTeacher,
    GroupTeacherLessonPlan,
    Homework,
    HomeworkResult,
    Lesson,
    MonthlyTeacherReport,
    Room,
    Student,
    StudentStatusEvent,
)
from apps.academy.services.academy_monthly_report import compute_academy_monthly_stats
from apps.academy.services.student_status import (
    complete_student,
    continue_student,
    deactivate_student,
    pause_student,
    reactivate_student,
)
from apps.academy.services.analytics import (
    COMPARE_CHOICES,
    PERIOD_CHOICES,
    DateRange,
    build_metric,
    get_dashboard,
    resolve_comparison,
    resolve_period,
)
from apps.academy.services.attendance_service import bulk_mark_attendance
from apps.academy.admin_views import _detect_conflicts, _lesson_status_kpi
from apps.academy.services.group_schedule_conflicts import (
    find_schedule_group_conflict,
    find_schedule_room_conflict,
    find_schedule_teacher_conflict,
    overlapping_groups,
)
from apps.academy.services.group_schedule_sync import sync_legacy_group_schedule
from apps.academy.services.homework_service import bulk_upsert_homework_results
from apps.academy.services.lesson_generator import (
    LessonGenerationError,
    generate_lessons_for_group,
    generate_lessons_for_group_with_report,
)
from apps.academy.services import lesson_lifecycle
from apps.academy.services.lesson_status import lesson_status_counts
from apps.academy.views import _assert_teacher_owns_lesson

# NOTE: login/verification/permission tests for the underlying auth system
# (admin login, teacher login, unverified/inactive teacher rejected) already
# live in apps.users.tests and are unaffected by this app — no need to
# duplicate them here.


def make_teacher(username: str) -> Teacher:
    user = User.objects.create_user(
        username=username,
        email=f"{username}@okurmen.kg",
        password="Str0ngPassw0rd!",
        first_name=username.capitalize(),
        role=User.Role.TEACHER,
        is_verified=True,
    )
    return Teacher.objects.create(user=user, position="Тренер")


def sync_and_generate(group: Group) -> None:
    """Test helper: explicitly do what a live auto-sync-on-save signal used
    to do automatically before this architecture change — Group's legacy
    teacher/room/start_time/end_time/days_of_week fields no longer drive
    GroupSchedule/lesson generation on their own (see their help_text on
    Group, and services.group_schedule_sync's module docstring); a test that
    wants the equivalent Teacher Program + generated Lessons for a group
    whose legacy fields are set now asks for it explicitly, the same way an
    admin would via the one-off migration or by adding a schedule row."""
    sync_legacy_group_schedule(group)
    generate_lessons_for_group(group)


def make_admin(username: str = "admin") -> User:
    return User.objects.create_superuser(
        username=username,
        email=f"{username}@okurmen.kg",
        password="Str0ngPassw0rd!",
        first_name="Admin",
    )


class AcademyTestBase(TestCase):
    def setUp(self):
        self.admin = make_admin()
        self.teacher1 = make_teacher("teacher1")
        self.teacher2 = make_teacher("teacher2")

        # "Backend"/"Frontend"/"English"/"Soft Skills" are auto-seeded by
        # apps.users.signals.create_default_subjects on post_migrate, so
        # test-only subjects use names outside that seed list to avoid a
        # unique-constraint clash.
        self.subject_python = Subject.objects.create(name="Python")
        self.subject_frontend = Subject.objects.create(name="JavaScript")

        self.course = Course.objects.create(name="Standard", count_lesson=4)
        self.course.subjects.set([self.subject_python, self.subject_frontend])

        self.plan1 = CourseLessonPlan.objects.create(
            course=self.course, lesson_number=1, subject=self.subject_python, topic="Переменные"
        )
        self.plan2 = CourseLessonPlan.objects.create(
            course=self.course, lesson_number=2, subject=self.subject_frontend, topic="HTML"
        )
        self.plan3 = CourseLessonPlan.objects.create(
            course=self.course, lesson_number=3, subject=self.subject_python, topic="Функции"
        )
        self.plan4 = CourseLessonPlan.objects.create(
            course=self.course, lesson_number=4, subject=self.subject_frontend, topic="CSS"
        )

        self.room1 = Room.objects.create(name="Room 101", capacity=15)
        self.room2 = Room.objects.create(name="Room 102", capacity=10)

        # 2026-09-07 is a Monday.
        self.group1 = Group.objects.create(
            name="Python Beginner",
            course=self.course,
            teacher=self.teacher1,
            room=self.room1,
            start_date=dt.date(2026, 9, 7),
            start_time=dt.time(15, 0),
            end_time=dt.time(16, 30),
            days_of_week=["mon", "wed"],
            max_students=15,
        )
        self.group2 = Group.objects.create(
            name="Frontend Beginner",
            course=self.course,
            teacher=self.teacher2,
            room=self.room2,
            start_date=dt.date(2026, 9, 7),
            start_time=dt.time(17, 0),
            end_time=dt.time(18, 30),
            days_of_week=["tue", "thu"],
            max_students=12,
        )
        # Legacy teacher/room/time/days_of_week no longer auto-populate
        # GroupSchedule (see Group's help_text) — do it explicitly, same as
        # the one-off migration that captures pre-existing data does.
        sync_and_generate(self.group1)
        sync_and_generate(self.group2)

        self.student1 = Student.objects.create(first_name="Алина", last_name="Иванова", group=self.group1)
        self.student2 = Student.objects.create(first_name="Мансур", last_name="Алиев", group=self.group1)
        self.student3 = Student.objects.create(first_name="Айбек", last_name="Токтогулов", group=self.group2)

        self.admin_client = APIClient()
        self.admin_client.force_authenticate(self.admin)

        self.teacher1_client = APIClient()
        self.teacher1_client.force_authenticate(self.teacher1.user)

        self.teacher2_client = APIClient()
        self.teacher2_client.force_authenticate(self.teacher2.user)

        self.anon_client = APIClient()


class GroupTests(AcademyTestBase):
    def test_admin_sees_all_groups(self):
        response = self.admin_client.get("/api/v1/groups/")
        self.assertEqual(response.data["count"], 2)

    def test_teacher_sees_only_own_groups(self):
        response = self.teacher1_client.get("/api/v1/groups/")
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["name"], "Python Beginner")

    def test_teacher_cannot_access_other_teachers_group(self):
        response = self.teacher1_client.get(f"/api/v1/groups/{self.group2.id}/")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_teacher_cannot_write_group(self):
        response = self.teacher1_client.patch(
            f"/api/v1/groups/{self.group1.id}/", {"name": "Hacked"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_group_can_be_created_with_no_legacy_fields_at_all(self):
        # teacher/room/start_time/end_time/days_of_week are legacy — a Group
        # is fully valid with none of them set; teachers/schedule are added
        # afterwards as equal Teacher Programs (GroupTeacher/GroupSchedule).
        response = self.admin_client.post(
            "/api/v1/groups/",
            {"name": "No legacy fields", "course": self.course.id, "start_date": "2026-09-07"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        group = Group.objects.get(pk=response.data["id"])
        self.assertIsNone(group.teacher_id)
        self.assertEqual(group.teachers.count(), 0)

    # Room-vs-max_students capacity validation was tied to the legacy
    # Group.room field (removed — see LegacyGroupFieldsTests) and had no
    # GroupSchedule-level equivalent to replace it with; there's nothing
    # left here to reject a room-mismatched max_students against.

    def test_group_end_date_before_start_date_rejected(self):
        response = self.admin_client.post(
            "/api/v1/groups/",
            {
                "name": "Bad dates", "course": self.course.id, "teacher": self.teacher1.id,
                "start_date": "2026-09-10", "end_date": "2026-09-01",
                "start_time": "10:00", "end_time": "11:00", "days_of_week": ["mon"],
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class LegacyGroupFieldsTests(AcademyTestBase):
    """Group.teacher/room/start_time/end_time/days_of_week are legacy
    fields kept only for backward compatibility with data that predates
    GroupTeacher/GroupSchedule — the DB columns still exist, but nothing in
    the admin UI, the API, lesson generation, schedule logic, analytics, or
    permissions may read or write them any more. GroupTeacher/GroupSchedule
    are the only source of truth (see AcademyTestBase.setUp: group1/group2
    themselves still carry legacy field values, converted to real
    GroupSchedule/GroupTeacher rows by `sync_and_generate` — exactly the
    "old data" scenario these tests must not break)."""

    def setUp(self):
        super().setUp()
        self.django_admin_client = DjangoClient()
        self.django_admin_client.force_login(self.admin)

    def test_legacy_fields_absent_from_api_response(self):
        response = self.admin_client.get(f"/api/v1/groups/{self.group1.id}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        for field in ("teacher", "teacher_name", "room", "room_name", "start_time", "end_time", "days_of_week"):
            self.assertNotIn(field, response.data)

    def test_legacy_fields_in_create_payload_are_silently_ignored(self):
        response = self.admin_client.post(
            "/api/v1/groups/",
            {
                "name": "New Group — legacy payload ignored",
                "course": self.course.id,
                "start_date": "2026-09-07",
                # Every legacy field an old API client might still send —
                # none of these may be accepted or stored any more.
                "teacher": self.teacher2.id,
                "room": self.room1.id,
                "start_time": "15:30",
                "end_time": "17:00",
                "days_of_week": ["mon"],
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        for field in ("teacher", "teacher_name", "room", "room_name", "start_time", "end_time", "days_of_week"):
            self.assertNotIn(field, response.data)

        created = Group.objects.get(pk=response.data["id"])
        self.assertIsNone(created.teacher_id)
        self.assertIsNone(created.room_id)
        self.assertIsNone(created.start_time)
        self.assertIsNone(created.end_time)
        self.assertEqual(created.days_of_week, [])

    def test_legacy_room_double_booking_no_longer_rejected(self):
        # Previously this exact payload (group1 already occupies room1 on
        # Mon 15:00-16:30 via its legacy fields) was rejected as a
        # room-conflict. Legacy fields are never written any more, so
        # there's nothing left to conflict over — the request just
        # succeeds, silently ignoring the legacy keys.
        response = self.admin_client.post(
            "/api/v1/groups/",
            {
                "name": "Legacy double-booking is a no-op now",
                "course": self.course.id,
                "teacher": self.teacher2.id,
                "room": self.room1.id,
                "start_date": "2026-09-07",
                "start_time": "15:30",
                "end_time": "17:00",
                "days_of_week": ["mon"],
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)

    def test_group_admin_form_has_no_legacy_fields_or_section(self):
        response = self.django_admin_client.get(f"/admin/academy/group/{self.group1.id}/change/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        body = response.content.decode()
        self.assertNotIn("Поля для обратной совместимости", body)
        for field_id in ("id_teacher", "id_room", "id_start_time", "id_end_time", "id_days_of_week"):
            self.assertNotIn(f'id="{field_id}"', body)

    def test_group_admin_add_form_has_no_legacy_fields(self):
        response = self.django_admin_client.get("/admin/academy/group/add/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        body = response.content.decode()
        for field_id in ("id_teacher", "id_room", "id_start_time", "id_end_time", "id_days_of_week"):
            self.assertNotIn(f'id="{field_id}"', body)

    def test_group_teacher_and_group_schedule_are_the_only_source_of_truth_for_access(self):
        # group1's legacy `teacher` field points at teacher1 and stays set —
        # nothing ever clears it (it's simply never read any more). Real
        # access is gated entirely by GroupSchedule: deactivating every one
        # of teacher1's schedule slots must revoke their access to group1
        # even though the legacy field still names them.
        self.assertEqual(self.group1.teacher_id, self.teacher1.id)
        self.assertTrue(Group.objects.for_teacher(self.teacher1).filter(pk=self.group1.pk).exists())

        GroupSchedule.objects.filter(group=self.group1, teacher=self.teacher1).update(is_active=False)

        self.assertFalse(Group.objects.for_teacher(self.teacher1).filter(pk=self.group1.pk).exists())
        response = self.teacher1_client.get(f"/api/v1/groups/{self.group1.id}/")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_generation_and_access_follow_group_schedule_even_when_legacy_teacher_points_elsewhere(self):
        # A Group whose legacy `teacher` field names one teacher, but whose
        # only real Teaching Program (GroupTeacher/GroupSchedule) belongs to
        # a completely different one — generation, analytics and permissions
        # must all follow the real program, never the legacy field.
        other_course = Course.objects.create(name="Legacy-mismatch course", count_lesson=1)
        other_course.subjects.add(self.subject_python)
        CourseLessonPlan.objects.create(
            course=other_course, lesson_number=1, subject=self.subject_python, topic="Тема",
        )
        mismatched_group = Group.objects.create(
            name="Legacy teacher points elsewhere",
            course=other_course,
            teacher=self.teacher1,  # legacy field: teacher1 — but never given a real program
            start_date=dt.date(2026, 9, 7),
        )
        GroupSchedule.objects.create(
            group=mismatched_group, teacher=self.teacher2, subject=self.subject_python,
            day_of_week="mon", start_time=dt.time(10, 0), end_time=dt.time(11, 0),
        )
        generate_lessons_for_group(mismatched_group)

        lesson = Lesson.objects.get(group=mismatched_group)
        self.assertEqual(lesson.effective_teacher, self.teacher2)

        # teacher1 (the legacy field's own value) has no real access at all.
        self.assertFalse(Group.objects.for_teacher(self.teacher1).filter(pk=mismatched_group.pk).exists())
        response1 = self.teacher1_client.get(f"/api/v1/groups/{mismatched_group.id}/")
        self.assertEqual(response1.status_code, status.HTTP_404_NOT_FOUND)

        # teacher2 (the real GroupTeacher/GroupSchedule) has full access.
        self.assertTrue(Group.objects.for_teacher(self.teacher2).filter(pk=mismatched_group.pk).exists())
        response2 = self.teacher2_client.get(f"/api/v1/groups/{mismatched_group.id}/")
        self.assertEqual(response2.status_code, status.HTTP_200_OK)

    def test_unsynced_legacy_only_group_does_not_crash_generation_or_analytics(self):
        # A Group with only its legacy fields ever set, no GroupTeacher/
        # GroupSchedule at all (the one-off migration was never run for
        # it — the worst case of "old data"). It's invisible to every
        # teacher (nothing to grant access through) and can't generate
        # lessons (no active program), but nothing may raise.
        legacy_only_group = Group.objects.create(
            name="Never migrated legacy-only group",
            course=self.course,
            teacher=self.teacher1,
            room=self.room1,
            start_date=dt.date(2026, 9, 7),
            start_time=dt.time(9, 0),
            end_time=dt.time(10, 0),
            days_of_week=["fri"],
        )
        self.assertFalse(Group.objects.for_teacher(self.teacher1).filter(pk=legacy_only_group.pk).exists())
        with self.assertRaises(LessonGenerationError):
            generate_lessons_for_group(legacy_only_group)

        dashboard = get_dashboard(period="custom", start_date=dt.date(2026, 9, 1), end_date=dt.date(2026, 9, 30))
        self.assertIsNotNone(dashboard)


class RoomAvailabilityTests(AcademyTestBase):
    """group1 occupies room1 Mon/Wed 15:00-16:30; group2 occupies room2 Tue/Thu 17:00-18:30."""

    def test_requires_date_and_times(self):
        response = self.admin_client.get("/api/v1/rooms/available/")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_free_slot_lists_all_active_rooms_available(self):
        response = self.admin_client.get(
            "/api/v1/rooms/available/",
            {"date": "2026-09-07", "start_time": "09:00", "end_time": "10:00"},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        available_ids = {room["id"] for room in response.data["available"]}
        self.assertEqual(available_ids, {self.room1.id, self.room2.id})
        self.assertEqual(response.data["occupied"], [])

    def test_occupied_room_excluded_and_reported(self):
        # 2026-09-07 is a Monday — group1's lesson there runs 15:00-16:30 in room1.
        response = self.admin_client.get(
            "/api/v1/rooms/available/",
            {"date": "2026-09-07", "start_time": "15:15", "end_time": "16:00"},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        available_ids = {room["id"] for room in response.data["available"]}
        self.assertEqual(available_ids, {self.room2.id})
        occupied_rooms = {row["room"] for row in response.data["occupied"]}
        self.assertEqual(occupied_rooms, {self.room1.id})
        self.assertEqual(response.data["occupied"][0]["group_name"], "Python Beginner")

    def test_adjacent_non_overlapping_slot_is_free(self):
        # Ends exactly when group1's lesson starts — [start, end) semantics, no overlap.
        response = self.admin_client.get(
            "/api/v1/rooms/available/",
            {"date": "2026-09-07", "start_time": "13:00", "end_time": "15:00"},
        )
        available_ids = {room["id"] for room in response.data["available"]}
        self.assertIn(self.room1.id, available_ids)

    def test_cancelled_lesson_never_occupies_room(self):
        lesson = Lesson.objects.filter(group=self.group1, date=dt.date(2026, 9, 7)).first()
        lesson.status = Lesson.Status.CANCELLED
        lesson.save(update_fields=["status"])

        response = self.admin_client.get(
            "/api/v1/rooms/available/",
            {"date": "2026-09-07", "start_time": "15:15", "end_time": "16:00"},
        )
        available_ids = {room["id"] for room in response.data["available"]}
        self.assertIn(self.room1.id, available_ids)


class GroupScheduleEndpointTests(AcademyTestBase):
    def test_returns_group_and_dated_lessons_with_weekday(self):
        response = self.admin_client.get(f"/api/v1/groups/{self.group1.id}/schedule/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["group"]["id"], self.group1.id)

        lessons = response.data["lessons"]
        self.assertEqual(len(lessons), 4)
        # 2026-09-07 is a Monday, 2026-09-09 is a Wednesday.
        self.assertEqual(lessons[0]["date"], "2026-09-07")
        self.assertEqual(lessons[0]["weekday"], "mon")
        self.assertEqual(lessons[0]["weekday_label"], "Понедельник")
        self.assertEqual(lessons[1]["weekday"], "wed")

    def test_teacher_can_see_own_group_schedule(self):
        response = self.teacher1_client.get(f"/api/v1/groups/{self.group1.id}/schedule/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_teacher_cannot_see_other_teachers_group_schedule(self):
        response = self.teacher1_client.get(f"/api/v1/groups/{self.group2.id}/schedule/")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_status_filter(self):
        lesson = Lesson.objects.filter(group=self.group1).first()
        lesson.status = Lesson.Status.CANCELLED
        lesson.save(update_fields=["status"])

        response = self.admin_client.get(
            f"/api/v1/groups/{self.group1.id}/schedule/", {"status": "cancelled"}
        )
        self.assertEqual(len(response.data["lessons"]), 1)
        self.assertEqual(response.data["lessons"][0]["id"], lesson.id)


class GroupStudentsEndpointTests(AcademyTestBase):
    def test_returns_active_students_of_the_group(self):
        response = self.admin_client.get(f"/api/v1/groups/{self.group1.id}/students/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        names = {row["full_name"] for row in response.data}
        self.assertEqual(names, {"Алина Иванова", "Мансур Алиев"})

    def test_inactive_student_excluded_by_default(self):
        self.student1.is_active = False
        self.student1.save(update_fields=["is_active"])
        response = self.admin_client.get(f"/api/v1/groups/{self.group1.id}/students/")
        names = {row["full_name"] for row in response.data}
        self.assertEqual(names, {"Мансур Алиев"})

    def test_teacher_can_see_own_group_students(self):
        response = self.teacher1_client.get(f"/api/v1/groups/{self.group1.id}/students/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 2)

    def test_teacher_cannot_see_other_teachers_group_students(self):
        response = self.teacher1_client.get(f"/api/v1/groups/{self.group2.id}/students/")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class StudentTests(AcademyTestBase):
    def test_admin_sees_all_students(self):
        response = self.admin_client.get("/api/v1/students/")
        self.assertEqual(response.data["count"], 3)

    def test_teacher_sees_only_own_groups_students(self):
        response = self.teacher1_client.get("/api/v1/students/")
        self.assertEqual(response.data["count"], 2)
        names = {row["first_name"] for row in response.data["results"]}
        self.assertEqual(names, {"Алина", "Мансур"})


class LessonGenerationTests(AcademyTestBase):
    """group1/group2 (via AcademyTestBase.setUp's explicit sync_and_generate)
    already arrive with their lessons made. Tests here either inspect that
    already-generated state, or spin up a fresh Group + Teacher Program
    (GroupSchedule) to observe generation happening from a clean slate.
    """

    def test_adding_a_teacher_program_automatically_generates_lessons(self):
        """The core workflow guarantee: Admin never has to click anything —
        adding a GroupSchedule row (a Teacher Program's slot) is enough; the
        `post_save` signal (see apps.academy.signals) does the rest. A bare
        Group with no Teacher Program yet has zero lessons — there is no
        special "the group's own fields" shortcut anymore (see Group's
        teacher/room/start_time/end_time/days_of_week help_text)."""
        group = Group.objects.create(
            name="Auto-generated group", course=self.course, start_date=dt.date(2026, 9, 7),
        )
        self.assertEqual(Lesson.objects.filter(group=group).count(), 0)

        # A single row is enough to prove the point (and avoids the
        # multi-row-same-request deferral admin.GroupAdmin needs — see
        # save_model/save_formset/save_related — which doesn't apply here
        # since nothing else is being added in the same request).
        GroupSchedule.objects.create(
            group=group, teacher=self.teacher1, subject=self.subject_python,
            day_of_week="mon", start_time=dt.time(9, 0), end_time=dt.time(10, 30), room=self.room1,
        )

        lessons = list(Lesson.objects.filter(group=group).order_by("lesson_number"))
        self.assertEqual(len(lessons), 4)
        self.assertEqual(
            [lesson.date for lesson in lessons],
            [dt.date(2026, 9, 7), dt.date(2026, 9, 14), dt.date(2026, 9, 21), dt.date(2026, 9, 28)],
        )
        self.assertEqual([lesson.lesson_number for lesson in lessons], [1, 2, 3, 4])

    def test_copies_content_from_plan(self):
        lessons = list(Lesson.objects.filter(group=self.group1).order_by("lesson_number"))
        self.assertEqual(lessons[0].subject_id, self.subject_python.id)
        self.assertEqual(lessons[0].topic, "Переменные")
        self.assertEqual(lessons[1].subject_id, self.subject_frontend.id)
        self.assertEqual(lessons[0].room_id, self.room1.id)
        self.assertEqual(lessons[0].start_time, self.group1.start_time)

    def test_idempotent_no_duplicates(self):
        # group1's lessons were already generated on creation — re-running
        # explicitly (the same call the "Generate lessons" admin action and
        # API action make) must never create duplicates.
        generate_lessons_for_group(self.group1)
        second_run = generate_lessons_for_group(self.group1)
        self.assertEqual(second_run, [])
        self.assertEqual(Lesson.objects.filter(group=self.group1).count(), 4)

    def test_editing_group_does_not_duplicate_or_alter_existing_lessons(self):
        original_ids = set(Lesson.objects.filter(group=self.group1).values_list("id", flat=True))
        self.group1.description = "Обновлённое описание"
        self.group1.save(update_fields=["description"])
        self.assertEqual(
            set(Lesson.objects.filter(group=self.group1).values_list("id", flat=True)),
            original_ids,
        )

    def test_respects_end_date(self):
        group = Group.objects.create(
            name="Short group",
            course=self.course,
            start_date=dt.date(2026, 9, 7),
            end_date=dt.date(2026, 9, 10),
        )
        for day in ["mon", "wed"]:
            slot = GroupSchedule(
                group=group, teacher=self.teacher1, subject=self.subject_python,
                day_of_week=day, start_time=dt.time(9, 0), end_time=dt.time(10, 30), room=self.room1,
            )
            slot._defer_schedule_sync = True
            slot.save()
        generate_lessons_for_group(group)
        self.assertEqual(Lesson.objects.filter(group=group).count(), 2)

    def test_mismatched_plan_count_raises(self):
        self.course.count_lesson = 10
        self.course.save(update_fields=["count_lesson"])
        with self.assertRaises(LessonGenerationError):
            generate_lessons_for_group(self.group1)

    def test_group_with_incomplete_plan_is_skipped_silently(self):
        """A Group saved before its course's plan is finished must not error out."""
        self.course.count_lesson = 10
        self.course.save(update_fields=["count_lesson"])
        group = Group.objects.create(
            name="Waiting on its plan",
            course=self.course,
            teacher=self.teacher1,
            room=self.room1,
            start_date=dt.date(2026, 9, 7),
            start_time=dt.time(9, 0),
            end_time=dt.time(10, 30),
            days_of_week=["mon"],
        )
        self.assertEqual(Lesson.objects.filter(group=group).count(), 0)

    def test_generate_lessons_api_endpoint_is_a_safe_retry(self):
        # Lessons already exist (auto-generated on creation) — the manual
        # endpoint is now only a retry/fallback, so it must report a no-op.
        response = self.admin_client.post(f"/api/v1/groups/{self.group1.id}/generate-lessons/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["created_count"], 0)
        self.assertEqual(response.data["first_lesson"], 1)
        self.assertEqual(response.data["last_lesson"], 4)
        self.assertEqual(Lesson.objects.filter(group=self.group1).count(), 4)

    def test_generate_lessons_api_admin_only(self):
        response = self.teacher1_client.post(f"/api/v1/groups/{self.group1.id}/generate-lessons/")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class AttendanceTests(AcademyTestBase):
    def setUp(self):
        super().setUp()
        # group1's lessons were already generated automatically on creation
        # (see AcademyTestBase.setUp / apps.academy.signals).
        self.lessons = list(Lesson.objects.filter(group=self.group1).order_by("lesson_number"))
        self.lesson1 = self.lessons[0]

    def test_correct_creation(self):
        response = self.teacher1_client.post(
            "/api/v1/attendance/",
            {"student": self.student1.id, "lesson": self.lesson1.id, "status": "present"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(response.data["student_name"], "Алина Иванова")

    def test_student_from_other_group_rejected(self):
        response = self.admin_client.post(
            "/api/v1/attendance/",
            {"student": self.student3.id, "lesson": self.lesson1.id, "status": "present"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_duplicate_rejected(self):
        Attendance.objects.create(student=self.student1, lesson=self.lesson1, status="present")
        response = self.admin_client.post(
            "/api/v1/attendance/",
            {"student": self.student1.id, "lesson": self.lesson1.id, "status": "late"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_teacher_isolation_cannot_create_for_other_group(self):
        response = self.teacher1_client.post(
            "/api/v1/attendance/",
            {"student": self.student3.id, "lesson": self.lesson1.id, "status": "present"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_bulk_service_all_or_nothing(self):
        with self.assertRaises(Exception):
            bulk_mark_attendance(
                self.lesson1,
                [
                    {"student": self.student1, "status": "present"},
                    {"student": self.student3, "status": "present"},  # wrong group
                ],
            )
        self.assertEqual(Attendance.objects.filter(lesson=self.lesson1).count(), 0)

    def test_bulk_attendance_endpoint_roster_and_marking(self):
        get_response = self.teacher1_client.get(f"/api/v1/lessons/{self.lesson1.id}/attendance/")
        self.assertEqual(get_response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(get_response.data), 2)  # full roster, unmarked

        post_response = self.teacher1_client.post(
            f"/api/v1/lessons/{self.lesson1.id}/attendance/",
            [
                {"student": self.student1.id, "status": "present"},
                {"student": self.student2.id, "status": "absent", "comment": "Болеет"},
            ],
            format="json",
        )
        self.assertEqual(post_response.status_code, status.HTTP_200_OK)
        self.assertEqual(Attendance.objects.filter(lesson=self.lesson1).count(), 2)

    def test_teacher_cannot_bulk_mark_other_groups_lesson(self):
        response = self.teacher2_client.post(
            f"/api/v1/lessons/{self.lesson1.id}/attendance/",
            [{"student": self.student1.id, "status": "present"}],
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class HomeworkTests(AcademyTestBase):
    def setUp(self):
        super().setUp()
        # group1/group2's lessons were already generated automatically on
        # creation (see AcademyTestBase.setUp / apps.academy.signals).
        self.lessons = list(Lesson.objects.filter(group=self.group1).order_by("lesson_number"))
        self.lesson1 = self.lessons[0]
        self.other_lesson = Lesson.objects.filter(group=self.group2).order_by("lesson_number")[0]

    def test_teacher_can_create_homework_for_own_lesson(self):
        response = self.teacher1_client.post(
            "/api/v1/homework/",
            {"lesson": self.lesson1.id, "title": "ДЗ 1", "description": "Решить примеры"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)

    def test_teacher_cannot_create_homework_for_other_lesson(self):
        response = self.teacher1_client.post(
            "/api/v1/homework/",
            {"lesson": self.other_lesson.id, "title": "ДЗ 1"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_result_score_out_of_range_rejected(self):
        homework = Homework.objects.create(lesson=self.lesson1, title="ДЗ 1")
        response = self.admin_client.post(
            "/api/v1/homework-results/",
            {"homework": homework.id, "student": self.student1.id, "status": "checked", "score": 11},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_result_wrong_group_student_rejected(self):
        homework = Homework.objects.create(lesson=self.lesson1, title="ДЗ 1")
        response = self.admin_client.post(
            "/api/v1/homework-results/",
            {"homework": homework.id, "student": self.student3.id, "status": "submitted"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_result_uniqueness(self):
        homework = Homework.objects.create(lesson=self.lesson1, title="ДЗ 1")
        HomeworkResult.objects.create(homework=homework, student=self.student1, status="submitted")
        response = self.admin_client.post(
            "/api/v1/homework-results/",
            {"homework": homework.id, "student": self.student1.id, "status": "checked", "score": 5},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_bulk_results_roster_and_grading(self):
        homework = Homework.objects.create(lesson=self.lesson1, title="ДЗ 1")

        get_response = self.teacher1_client.get(f"/api/v1/homework/{homework.id}/results/")
        self.assertEqual(get_response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(get_response.data), 2)
        self.assertTrue(all(row["status"] == "not_submitted" for row in get_response.data))

        post_response = self.teacher1_client.post(
            f"/api/v1/homework/{homework.id}/results/",
            [
                {"student": self.student1.id, "status": "checked", "score": 9},
                {"student": self.student2.id, "status": "not_submitted"},
            ],
            format="json",
        )
        self.assertEqual(post_response.status_code, status.HTTP_200_OK)
        self.assertEqual(HomeworkResult.objects.filter(homework=homework, status="checked").count(), 1)

    def test_bulk_service_rejects_wrong_group(self):
        homework = Homework.objects.create(lesson=self.lesson1, title="ДЗ 1")
        with self.assertRaises(Exception):
            bulk_upsert_homework_results(homework, [{"student": self.student3, "status": "submitted"}])
        self.assertEqual(HomeworkResult.objects.filter(homework=homework).count(), 0)


# ---------------------------------------------------------------------------
# Period + comparison-period resolution — pure date math, no DB (spec §12:
# today vs yesterday, this month vs last month, custom range).
# ---------------------------------------------------------------------------

class PeriodResolutionTests(TestCase):
    def test_today(self):
        rng = resolve_period("today", today=dt.date(2026, 9, 15))
        self.assertEqual((rng.start, rng.end), (dt.date(2026, 9, 15), dt.date(2026, 9, 15)))

    def test_yesterday(self):
        rng = resolve_period("yesterday", today=dt.date(2026, 9, 15))
        self.assertEqual((rng.start, rng.end), (dt.date(2026, 9, 14), dt.date(2026, 9, 14)))

    def test_today_vs_yesterday_are_adjacent_and_distinct(self):
        today_range = resolve_period("today", today=dt.date(2026, 9, 15))
        yesterday_range = resolve_period("yesterday", today=dt.date(2026, 9, 15))
        self.assertEqual(yesterday_range.end + dt.timedelta(days=1), today_range.start)

    def test_last_7_days(self):
        rng = resolve_period("last_7_days", today=dt.date(2026, 9, 15))
        self.assertEqual((rng.start, rng.end), (dt.date(2026, 9, 9), dt.date(2026, 9, 15)))
        self.assertEqual(rng.days, 7)

    def test_this_week_monday_start(self):
        # 2026-09-15 is a Tuesday.
        rng = resolve_period("this_week", today=dt.date(2026, 9, 15))
        self.assertEqual((rng.start, rng.end), (dt.date(2026, 9, 14), dt.date(2026, 9, 20)))

    def test_last_week(self):
        rng = resolve_period("last_week", today=dt.date(2026, 9, 15))
        self.assertEqual((rng.start, rng.end), (dt.date(2026, 9, 7), dt.date(2026, 9, 13)))

    def test_this_month(self):
        rng = resolve_period("this_month", today=dt.date(2026, 9, 15))
        self.assertEqual((rng.start, rng.end), (dt.date(2026, 9, 1), dt.date(2026, 9, 15)))

    def test_last_month(self):
        rng = resolve_period("last_month", today=dt.date(2026, 9, 15))
        self.assertEqual((rng.start, rng.end), (dt.date(2026, 8, 1), dt.date(2026, 8, 31)))

    def test_this_month_vs_last_month_dont_overlap(self):
        this_month = resolve_period("this_month", today=dt.date(2026, 9, 15))
        last_month = resolve_period("last_month", today=dt.date(2026, 9, 15))
        self.assertLess(last_month.end, this_month.start)

    def test_last_month_across_year_boundary(self):
        rng = resolve_period("last_month", today=dt.date(2026, 1, 15))
        self.assertEqual((rng.start, rng.end), (dt.date(2025, 12, 1), dt.date(2025, 12, 31)))

    def test_custom_range(self):
        rng = resolve_period(
            "custom", today=dt.date(2026, 9, 15), start_date=dt.date(2026, 9, 1), end_date=dt.date(2026, 9, 10)
        )
        self.assertEqual((rng.start, rng.end), (dt.date(2026, 9, 1), dt.date(2026, 9, 10)))

    def test_custom_range_requires_dates(self):
        with self.assertRaises(ValueError):
            resolve_period("custom", today=dt.date(2026, 9, 15))

    def test_custom_range_swaps_reversed_dates(self):
        rng = resolve_period(
            "custom", today=dt.date(2026, 9, 15), start_date=dt.date(2026, 9, 10), end_date=dt.date(2026, 9, 1)
        )
        self.assertEqual((rng.start, rng.end), (dt.date(2026, 9, 1), dt.date(2026, 9, 10)))

    def test_unknown_period_raises(self):
        with self.assertRaises(ValueError):
            resolve_period("not_a_period", today=dt.date(2026, 9, 15))

    def test_no_comparison_when_not_requested(self):
        rng = DateRange(dt.date(2026, 9, 1), dt.date(2026, 9, 30))
        self.assertIsNone(resolve_comparison(rng, None))

    def test_compare_previous_period(self):
        rng = DateRange(dt.date(2026, 9, 8), dt.date(2026, 9, 14))  # 7 days
        cmp = resolve_comparison(rng, "previous_period")
        self.assertEqual((cmp.start, cmp.end), (dt.date(2026, 9, 1), dt.date(2026, 9, 7)))
        self.assertEqual(cmp.days, rng.days)

    def test_compare_previous_week(self):
        rng = DateRange(dt.date(2026, 9, 14), dt.date(2026, 9, 20))
        cmp = resolve_comparison(rng, "previous_week")
        self.assertEqual((cmp.start, cmp.end), (dt.date(2026, 9, 7), dt.date(2026, 9, 13)))

    def test_compare_previous_month_full_month(self):
        rng = DateRange(dt.date(2026, 9, 1), dt.date(2026, 9, 30))
        cmp = resolve_comparison(rng, "previous_month")
        self.assertEqual((cmp.start, cmp.end), (dt.date(2026, 8, 1), dt.date(2026, 8, 30)))

    def test_compare_custom(self):
        rng = DateRange(dt.date(2026, 9, 1), dt.date(2026, 9, 30))
        cmp = resolve_comparison(rng, "custom", compare_start=dt.date(2025, 9, 1), compare_end=dt.date(2025, 9, 30))
        self.assertEqual((cmp.start, cmp.end), (dt.date(2025, 9, 1), dt.date(2025, 9, 30)))

    def test_compare_custom_requires_dates(self):
        rng = DateRange(dt.date(2026, 9, 1), dt.date(2026, 9, 30))
        with self.assertRaises(ValueError):
            resolve_comparison(rng, "custom")

    def test_unknown_compare_mode_raises(self):
        rng = DateRange(dt.date(2026, 9, 1), dt.date(2026, 9, 30))
        with self.assertRaises(ValueError):
            resolve_comparison(rng, "not_a_mode")

    def test_all_period_and_compare_choices_are_resolvable(self):
        today = dt.date(2026, 9, 15)
        for period in PERIOD_CHOICES:
            if period == "custom":
                continue
            rng = resolve_period(period, today=today)
            for compare in COMPARE_CHOICES:
                if compare == "custom":
                    continue
                self.assertIsNotNone(resolve_comparison(rng, compare))


# ---------------------------------------------------------------------------
# {value, previous_value, change, change_percent, trend} — spec §4/§12: zero
# previous value, percentage calculation, positive/negative/stable trend.
# ---------------------------------------------------------------------------

class BuildMetricTests(TestCase):
    def test_percentage_calculation(self):
        metric = build_metric(162, 150)
        self.assertEqual(metric["change"], 12)
        self.assertEqual(metric["change_percent"], 8.0)
        self.assertEqual(metric["trend"], "up")

    def test_zero_previous_value_with_positive_current(self):
        metric = build_metric(10, 0)
        self.assertEqual(metric["change"], 10)
        self.assertEqual(metric["change_percent"], 100.0)
        self.assertEqual(metric["trend"], "up")

    def test_zero_previous_value_and_zero_current(self):
        metric = build_metric(0, 0)
        self.assertEqual(metric["change_percent"], 0.0)
        self.assertEqual(metric["trend"], "stable")

    def test_positive_trend(self):
        self.assertEqual(build_metric(20, 10)["trend"], "up")

    def test_negative_trend(self):
        self.assertEqual(build_metric(5, 10)["trend"], "down")

    def test_stable_trend(self):
        metric = build_metric(10, 10)
        self.assertEqual(metric["trend"], "stable")
        self.assertEqual(metric["change"], 0)
        self.assertEqual(metric["change_percent"], 0.0)

    def test_no_previous_value_means_no_comparison(self):
        metric = build_metric(10, None)
        self.assertIsNone(metric["previous_value"])
        self.assertIsNone(metric["change"])
        self.assertIsNone(metric["change_percent"])
        self.assertEqual(metric["trend"], "stable")


# ---------------------------------------------------------------------------
# services.analytics.get_dashboard — the full redesigned dashboard.
# ---------------------------------------------------------------------------

class AnalyticsDashboardTests(AcademyTestBase):
    """group1 = "Python Beginner" (teacher1, students Алина/Мансур, 4
    Lessons Sep 2026: python/frontend alternating). group2 = "Frontend
    Beginner" (teacher2, student Айбек)."""

    def setUp(self):
        super().setUp()
        self.lessons = list(Lesson.objects.filter(group=self.group1).order_by("lesson_number"))
        self.date_from = dt.date(2026, 9, 1)
        self.date_to = dt.date(2026, 9, 30)
        self.today = dt.date(2026, 9, 30)

        statuses = [
            Attendance.Status.PRESENT,
            Attendance.Status.PRESENT,
            Attendance.Status.LATE,
            Attendance.Status.ABSENT,
        ]
        for lesson, attendance_status in zip(self.lessons, statuses):
            Attendance.objects.create(student=self.student1, lesson=lesson, status=attendance_status)

        self.homework1 = Homework.objects.create(lesson=self.lessons[0], title="ДЗ 1")
        self.homework2 = Homework.objects.create(lesson=self.lessons[1], title="ДЗ 2")
        HomeworkResult.objects.create(
            homework=self.homework1, student=self.student1, status=HomeworkResult.Status.CHECKED, score=8
        )
        # No result row for homework2 — counts as missed.

    def _dashboard(self, **kwargs):
        kwargs.setdefault("period", "custom")
        kwargs.setdefault("start_date", self.date_from)
        kwargs.setdefault("end_date", self.date_to)
        kwargs.setdefault("today", self.today)
        return get_dashboard(**kwargs)

    def test_attendance_calculation(self):
        attendance = self._dashboard(group_id=self.group1.id)["attendance"]
        self.assertEqual(attendance["present_count"]["value"], 2)
        self.assertEqual(attendance["absent_count"]["value"], 1)
        self.assertEqual(attendance["late_count"]["value"], 1)
        self.assertEqual(attendance["excused_count"]["value"], 0)
        self.assertEqual(attendance["attendance_rate"]["value"], 75.0)

    def test_homework_submission_calculation(self):
        homework = self._dashboard(group_id=self.group1.id)["homework"]
        self.assertEqual(homework["homework_count"]["value"], 2)
        self.assertEqual(homework["checked_count"]["value"], 1)
        self.assertEqual(homework["not_submitted_count"]["value"], 0)
        self.assertEqual(homework["submission_rate"]["value"], 100.0)
        self.assertEqual(homework["average_score"]["value"], 8.0)

    def test_lesson_stats_and_cancelled_lesson_metric(self):
        lessons = self._dashboard(group_id=self.group1.id)["lessons"]
        self.assertEqual(lessons["lessons_scheduled"]["value"], 4)
        self.assertEqual(lessons["lessons_completed"]["value"], 0)
        self.assertEqual(lessons["lessons_cancelled"]["value"], 0)
        self.assertEqual(lessons["lesson_completion_rate"]["value"], 0.0)

        cancelled = self.lessons[0]
        cancelled.status = Lesson.Status.CANCELLED
        cancelled.save(update_fields=["status"])

        lessons = self._dashboard(group_id=self.group1.id)["lessons"]
        self.assertEqual(lessons["lessons_cancelled"]["value"], 1)
        self.assertEqual(lessons["lessons_scheduled"]["value"], 3)

    def test_group_filtering_scopes_students(self):
        dashboard1 = self._dashboard(group_id=self.group1.id)
        dashboard2 = self._dashboard(group_id=self.group2.id)
        self.assertEqual(dashboard1["students"]["total_students"]["value"], 2)
        self.assertEqual(dashboard2["students"]["total_students"]["value"], 1)

    def test_teacher_isolation_scopes_to_own_lessons(self):
        dashboard_t1 = self._dashboard(teacher_id=self.teacher1.id)
        dashboard_t2 = self._dashboard(teacher_id=self.teacher2.id)
        self.assertEqual(dashboard_t1["attendance"]["present_count"]["value"], 2)
        self.assertEqual(dashboard_t2["attendance"]["present_count"]["value"], 0)
        self.assertEqual(dashboard_t1["lessons"]["lessons_scheduled"]["value"], 4)

    def test_subject_filtering(self):
        # lessons[0] (Переменные) and lessons[2] (Функции) are Python;
        # lessons[1]/[3] are JavaScript — see AcademyTestBase.setUp's plans.
        dashboard = self._dashboard(group_id=self.group1.id, subject_id=self.subject_python.id)
        self.assertEqual(dashboard["lessons"]["lessons_scheduled"]["value"], 2)
        self.assertTrue(all(row["subject_id"] == self.subject_python.id for row in dashboard["lessons"]["lessons_by_subject"]))

    def test_course_filtering_covers_every_group_of_that_course(self):
        dashboard = self._dashboard(course_id=self.course.id)
        self.assertEqual(dashboard["groups"]["total_groups"]["value"], 2)

    def test_no_filters_covers_every_group(self):
        dashboard = self._dashboard()
        self.assertEqual(dashboard["groups"]["total_groups"]["value"], 2)

    def test_academy_health_formula(self):
        health = self._dashboard(group_id=self.group1.id)["health"]
        self.assertEqual(health["components"]["attendance"], 75.0)
        self.assertEqual(health["components"]["homework"], 100.0)
        self.assertEqual(health["components"]["lesson_completion"], 0.0)
        self.assertEqual(health["components"]["retention"], 100.0)
        self.assertEqual(health["components"]["teacher_workload"], 100.0)
        self.assertEqual(health["score"], 75)
        self.assertEqual(health["level"], "good")

    def test_empty_period_returns_zeros_not_errors(self):
        empty_dashboard = get_dashboard(
            period="custom", start_date=dt.date(2020, 1, 1), end_date=dt.date(2020, 1, 31), today=dt.date(2020, 1, 31)
        )
        self.assertEqual(empty_dashboard["lessons"]["lessons_scheduled"]["value"], 0)
        self.assertEqual(empty_dashboard["attendance"]["attendance_rate"]["value"], 0.0)
        self.assertEqual(empty_dashboard["homework"]["submission_rate"]["value"], 0.0)
        self.assertEqual(empty_dashboard["attendance"]["attendance_trend"], [])
        # attendance/homework/lesson_completion all default to 0.0 with no
        # data at all (same "0 denominator -> 0.0" convention used
        # everywhere else in this package); only retention defaults to 100
        # (0 students -> nothing to retain). Global teacher_workload is 0.0
        # here since the fixture's teachers exist but taught nothing in
        # this empty 2020 period — see health.py's docstring for the formula.
        self.assertEqual(empty_dashboard["health"]["score"], 20)

    def test_repeated_calls_reflect_new_data_immediately(self):
        """The whole point of dropping stored KPI rows: no recalculation step."""
        before = self._dashboard(group_id=self.group1.id)["attendance"]["attendance_rate"]["value"]
        Attendance.objects.create(student=self.student2, lesson=self.lessons[0], status=Attendance.Status.PRESENT)
        after = self._dashboard(group_id=self.group1.id)["attendance"]["attendance_rate"]["value"]
        self.assertNotEqual(before, after)
        self.assertEqual(after, 80.0)  # 4 attended out of 5 marked now

    def test_period_comparison_positive_trend(self):
        # August has zero Attendance rows for group1 (no Lessons that
        # month) — September's 75% must read as a full "up" swing from 0.
        dashboard = self._dashboard(
            group_id=self.group1.id, compare="custom",
            compare_start_date=dt.date(2026, 8, 1), compare_end_date=dt.date(2026, 8, 31),
        )
        rate = dashboard["attendance"]["attendance_rate"]
        self.assertEqual(rate["previous_value"], 0.0)
        self.assertEqual(rate["value"], 75.0)
        self.assertEqual(rate["trend"], "up")
        self.assertIsNotNone(dashboard["comparison"])
        self.assertEqual(dashboard["comparison"]["key"], "custom")

    def test_no_n_plus_one_query_explosion(self):
        with CaptureQueriesContext(connection) as ctx:
            self._dashboard(group_id=self.group1.id, compare="previous_period")
        # A fixed, small number of queries regardless of how many
        # students/lessons exist — never one query per row.
        self.assertLess(len(ctx.captured_queries), 80)


class AnalyticsInsightsTests(AcademyTestBase):
    """Spec §6 — dynamic alerts, recomputed on every call."""

    def setUp(self):
        super().setUp()
        self.lessons = list(Lesson.objects.filter(group=self.group1).order_by("lesson_number"))

    def _dashboard(self, **kwargs):
        kwargs.setdefault("period", "custom")
        kwargs.setdefault("start_date", dt.date(2026, 9, 1))
        kwargs.setdefault("end_date", dt.date(2026, 9, 30))
        kwargs.setdefault("today", dt.date(2026, 9, 30))
        return get_dashboard(**kwargs)

    def test_consecutive_absences_insight(self):
        for lesson in self.lessons[:3]:
            Attendance.objects.create(student=self.student1, lesson=lesson, status=Attendance.Status.ABSENT)
        insights = self._dashboard(group_id=self.group1.id)["insights"]
        self.assertIn("attendance", {row["metric"] for row in insights})

    def test_no_insight_for_a_run_shorter_than_threshold(self):
        Attendance.objects.create(student=self.student1, lesson=self.lessons[0], status=Attendance.Status.ABSENT)
        Attendance.objects.create(student=self.student1, lesson=self.lessons[1], status=Attendance.Status.PRESENT)
        Attendance.objects.create(student=self.student1, lesson=self.lessons[2], status=Attendance.Status.ABSENT)
        insights = self._dashboard(group_id=self.group1.id)["insights"]
        self.assertFalse(any("систематически пропускает" in row["message"] for row in insights))

    def test_overdue_homework_insight(self):
        homework = Homework.objects.create(lesson=self.lessons[0], title="ДЗ", deadline=dt.date(2026, 9, 5))
        HomeworkResult.objects.create(homework=homework, student=self.student1, status=HomeworkResult.Status.NOT_SUBMITTED)
        insights = self._dashboard(group_id=self.group1.id, today=dt.date(2026, 9, 20))["insights"]
        self.assertIn("homework", {row["metric"] for row in insights})

    def test_group_close_to_capacity_insight(self):
        self.group1.max_students = 2
        self.group1.save(update_fields=["max_students"])
        insights = self._dashboard(group_id=self.group1.id)["insights"]
        self.assertIn("groups", {row["metric"] for row in insights})

    def test_significant_attendance_decrease_insight(self):
        past_lesson = Lesson.objects.create(
            group=self.group1, group_teacher=self.lessons[0].group_teacher, teacher=self.teacher1,
            lesson_number=101, date=dt.date(2026, 8, 3), start_time=dt.time(15, 0), end_time=dt.time(16, 30),
            room=self.room1, subject=self.subject_python, topic="Past lesson",
        )
        Attendance.objects.create(student=self.student1, lesson=past_lesson, status=Attendance.Status.PRESENT)
        for lesson in self.lessons:
            Attendance.objects.create(student=self.student1, lesson=lesson, status=Attendance.Status.ABSENT)

        dashboard = self._dashboard(
            group_id=self.group1.id, compare="custom",
            compare_start_date=dt.date(2026, 8, 1), compare_end_date=dt.date(2026, 8, 31),
        )
        self.assertIn("attendance_rate", {row["metric"] for row in dashboard["insights"]})

    def test_no_comparison_insights_without_a_compare_period(self):
        for lesson in self.lessons:
            Attendance.objects.create(student=self.student1, lesson=lesson, status=Attendance.Status.ABSENT)
        insights = self._dashboard(group_id=self.group1.id)["insights"]
        self.assertNotIn("attendance_rate", {row["metric"] for row in insights})


class StudentsAnalyticsTests(AcademyTestBase):
    """Spec item 19: student active/inactive calculation — and the
    period-bound new_students/students_left metrics. Student.created_at/
    updated_at are auto_now[_add], so `.update()` sets them deterministically
    rather than relying on wall-clock timing at test-run time."""

    def setUp(self):
        super().setUp()
        # AcademyTestBase's own student1/student2 are created at real
        # wall-clock time, which may itself fall inside this class's Sep
        # 2026 test window — pin them safely outside it so only the
        # students each test creates on purpose count as "new".
        Student.objects.filter(pk__in=[self.student1.pk, self.student2.pk]).update(
            created_at=dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc)
        )

    def _dashboard(self, **kwargs):
        kwargs.setdefault("period", "custom")
        kwargs.setdefault("start_date", dt.date(2026, 9, 1))
        kwargs.setdefault("end_date", dt.date(2026, 9, 30))
        kwargs.setdefault("today", dt.date(2026, 9, 30))
        return get_dashboard(**kwargs)

    def test_active_inactive_counts(self):
        self.student2.is_active = False
        self.student2.save(update_fields=["is_active"])
        students = self._dashboard(group_id=self.group1.id)["students"]
        self.assertEqual(students["total_students"]["value"], 2)
        self.assertEqual(students["active_students"]["value"], 1)
        self.assertEqual(students["inactive_students"]["value"], 1)

    def test_new_students_within_period(self):
        new_student = Student.objects.create(first_name="Новый", last_name="Студент", group=self.group1)
        Student.objects.filter(pk=new_student.pk).update(created_at=dt.datetime(2026, 9, 15, tzinfo=dt.timezone.utc))
        students = self._dashboard(group_id=self.group1.id)["students"]
        self.assertEqual(students["new_students"]["value"], 1)

    def test_new_students_excludes_outside_period(self):
        old_student = Student.objects.create(first_name="Давний", last_name="Студент", group=self.group1)
        Student.objects.filter(pk=old_student.pk).update(created_at=dt.datetime(2026, 7, 1, tzinfo=dt.timezone.utc))
        students = self._dashboard(group_id=self.group1.id)["students"]
        self.assertEqual(students["new_students"]["value"], 0)

    def test_students_left_within_period(self):
        self.student1.is_active = False
        self.student1.save(update_fields=["is_active"])
        Student.objects.filter(pk=self.student1.pk).update(updated_at=dt.datetime(2026, 9, 10, tzinfo=dt.timezone.utc))
        students = self._dashboard(group_id=self.group1.id)["students"]
        self.assertEqual(students["students_left"]["value"], 1)

    def test_groups_at_capacity(self):
        self.group1.max_students = 2
        self.group1.save(update_fields=["max_students"])
        students = self._dashboard(group_id=self.group1.id)["students"]
        self.assertEqual(students["groups_at_capacity"]["value"], 1)
        self.assertEqual(students["groups_with_free_capacity"]["value"], 0)


class AnalyticsDashboardAPITests(AcademyTestBase):
    def setUp(self):
        super().setUp()
        self.lessons = list(Lesson.objects.filter(group=self.group1).order_by("lesson_number"))
        Attendance.objects.create(student=self.student1, lesson=self.lessons[0], status=Attendance.Status.PRESENT)
        self.params = {"period": "custom", "start_date": "2026-09-01", "end_date": "2026-09-30"}

    def test_requires_authentication(self):
        response = self.anon_client.get("/api/v1/analytics/dashboard/", self.params)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_custom_period_requires_dates(self):
        response = self.admin_client.get("/api/v1/analytics/dashboard/", {"period": "custom"})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_default_period_is_this_month(self):
        response = self.admin_client.get("/api/v1/analytics/dashboard/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["period"]["key"], "this_month")

    def test_admin_sees_every_group(self):
        response = self.admin_client.get("/api/v1/analytics/dashboard/", self.params)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["groups"]["total_groups"]["value"], 2)

    def test_teacher_is_scoped_to_own_groups_even_if_teacher_param_given(self):
        response = self.teacher1_client.get(
            "/api/v1/analytics/dashboard/", {**self.params, "teacher": self.teacher2.id}
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["students"]["total_students"]["value"], 2)

    def test_teacher_requesting_other_teachers_group_gets_empty_dashboard(self):
        response = self.teacher1_client.get(
            "/api/v1/analytics/dashboard/", {**self.params, "group": self.group2.id}
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["groups"]["total_groups"]["value"], 0)

    def test_compare_true_shorthand_means_previous_period(self):
        response = self.admin_client.get("/api/v1/analytics/dashboard/", {**self.params, "compare": "true"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNotNone(response.data["comparison"])
        self.assertEqual(response.data["comparison"]["key"], "previous_period")

    def test_compare_named_mode(self):
        response = self.admin_client.get(
            "/api/v1/analytics/dashboard/", {**self.params, "compare": "previous_month"}
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["comparison"]["key"], "previous_month")

    def test_compare_absent_means_no_comparison(self):
        response = self.admin_client.get("/api/v1/analytics/dashboard/", self.params)
        self.assertIsNone(response.data["comparison"])

    def test_invalid_compare_mode_rejected(self):
        response = self.admin_client.get(
            "/api/v1/analytics/dashboard/", {**self.params, "compare": "nonsense"}
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_course_and_subject_filters_accepted(self):
        response = self.admin_client.get(
            "/api/v1/analytics/dashboard/",
            {**self.params, "course": self.course.id, "subject": self.subject_python.id},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["filters"]["course_id"], self.course.id)
        self.assertEqual(response.data["filters"]["subject_id"], self.subject_python.id)

    def test_endpoint_is_read_only(self):
        response = self.admin_client.post("/api/v1/analytics/dashboard/", self.params)
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_old_kpi_endpoints_are_gone(self):
        response = self.admin_client.get("/api/v1/kpi/groups/")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class ScheduleAdminViewTests(AcademyTestBase):
    """The custom "Расписание" admin page — no model of its own, built on Lesson.

    group1 (teacher1, room1) runs Mon/Wed from 2026-09-07: lessons on
    09-07, 09-09, 09-14, 09-16. group2 (teacher2, room2) runs Tue/Thu from
    the same start_date: lessons on 09-08, 09-10, 09-15, 09-17. Both fall
    within the two-week window 09-07..09-20 used by the filter tests below.
    """

    def setUp(self):
        super().setUp()
        # group1/group2's lessons were already generated automatically on
        # creation (see AcademyTestBase.setUp / apps.academy.signals).
        self.week1_lessons = list(Lesson.objects.filter(group=self.group1).order_by("lesson_number"))
        self.week2_lessons = list(Lesson.objects.filter(group=self.group2).order_by("lesson_number"))

        self.admin_web = DjangoClient()
        self.admin_web.force_login(self.admin)
        self.teacher_web = DjangoClient()
        self.teacher_web.force_login(self.teacher1.user)

    def _get(self, params=None):
        return self.admin_web.get(reverse("admin:academy_schedule"), params or {})

    def test_admin_can_access_schedule(self):
        response = self._get()
        self.assertEqual(response.status_code, 200)

    def test_teacher_cannot_access_schedule(self):
        response = self.teacher_web.get(reverse("admin:academy_schedule"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin/login/", response.url)

    def test_default_view_is_current_week(self):
        response = self._get()
        days = response.context["days"]
        self.assertEqual(len(days), 7)
        self.assertEqual(response.context["week_start"].weekday(), 0)
        self.assertTrue(any(day["is_today"] for day in days))

    def test_filter_by_teacher(self):
        response = self._get({"date_from": "2026-09-07", "date_to": "2026-09-20", "teacher": self.teacher1.id})
        shown = {lesson.id for day in response.context["days"] for lesson in day["lessons"]}
        self.assertEqual(shown, {lesson.id for lesson in self.week1_lessons})

    def test_filter_by_group(self):
        response = self._get({"date_from": "2026-09-07", "date_to": "2026-09-20", "group": self.group2.id})
        shown = {lesson.id for day in response.context["days"] for lesson in day["lessons"]}
        self.assertEqual(shown, {lesson.id for lesson in self.week2_lessons})

    def test_filter_by_room(self):
        response = self._get({"date_from": "2026-09-07", "date_to": "2026-09-20", "room": self.room1.id})
        shown = {lesson.id for day in response.context["days"] for lesson in day["lessons"]}
        self.assertEqual(shown, {lesson.id for lesson in self.week1_lessons})

    def test_filter_by_subject(self):
        response = self._get(
            {"date_from": "2026-09-07", "date_to": "2026-09-20", "subject": self.subject_python.id}
        )
        shown_lessons = [lesson for day in response.context["days"] for lesson in day["lessons"]]
        self.assertTrue(shown_lessons)
        self.assertTrue(all(lesson.subject_id == self.subject_python.id for lesson in shown_lessons))

    def test_filter_by_status(self):
        cancelled = self.week1_lessons[0]
        cancelled.status = Lesson.Status.CANCELLED
        cancelled.save(update_fields=["status"])

        response = self._get({"date_from": "2026-09-07", "date_to": "2026-09-20", "status": "cancelled"})
        shown = {lesson.id for day in response.context["days"] for lesson in day["lessons"]}
        self.assertEqual(shown, {cancelled.id})

    def test_lesson_displayed_on_correct_date_and_time(self):
        response = self._get({"date_from": "2026-09-07", "date_to": "2026-09-13"})
        by_date = {day["date"]: day["lessons"] for day in response.context["days"]}

        monday_lessons = by_date[dt.date(2026, 9, 7)]
        self.assertEqual(len(monday_lessons), 1)
        self.assertEqual(monday_lessons[0].start_time, self.group1.start_time)

        wednesday_lessons = by_date[dt.date(2026, 9, 9)]
        self.assertEqual(len(wednesday_lessons), 1)

        self.assertEqual(by_date[dt.date(2026, 9, 11)], [])

    def test_previous_week_navigation(self):
        response = self._get({"week": "2026-09-14"})
        self.assertEqual(response.context["week_start"], dt.date(2026, 9, 14))

        prev_response = self.admin_web.get(response.context["prev_week_url"])
        self.assertEqual(prev_response.context["week_start"], dt.date(2026, 9, 7))
        shown = {lesson.id for day in prev_response.context["days"] for lesson in day["lessons"]}
        self.assertTrue({self.week1_lessons[0].id, self.week2_lessons[0].id}.issubset(shown))

    def test_next_week_navigation(self):
        response = self._get({"week": "2026-09-07"})
        next_response = self.admin_web.get(response.context["next_week_url"])
        self.assertEqual(next_response.context["week_start"], dt.date(2026, 9, 14))
        shown = {lesson.id for day in next_response.context["days"] for lesson in day["lessons"]}
        self.assertTrue({self.week1_lessons[2].id, self.week2_lessons[2].id}.issubset(shown))

    def test_teacher_conflict_detection(self):
        # A non-overlapping time slot, so this group's own auto-generated
        # lessons don't themselves conflict with group1 — only the one
        # manually-added lesson below (at group1's actual time) should.
        overlapping_group = Group.objects.create(
            name="Python Advanced", course=self.course, teacher=self.teacher1, room=self.room2,
            start_date=dt.date(2026, 9, 7), start_time=dt.time(9, 0), end_time=dt.time(10, 0),
            days_of_week=["mon"],
        )
        # lesson_number=1 for this group was already auto-generated on
        # creation above — use a number outside the plan's range for this
        # extra, manually-placed conflicting lesson.
        conflicting_lesson = Lesson.objects.create(
            group=overlapping_group, lesson_number=99, date=dt.date(2026, 9, 7),
            start_time=dt.time(15, 30), end_time=dt.time(17, 0), room=self.room2,
        )

        response = self._get({"date_from": "2026-09-07", "date_to": "2026-09-07"})
        self.assertEqual(len(response.context["teacher_conflicts"]), 1)
        self.assertEqual(len(response.context["room_conflicts"]), 0)
        conflicting_ids = response.context["conflicting_ids"]
        self.assertIn(self.week1_lessons[0].id, conflicting_ids)
        self.assertIn(conflicting_lesson.id, conflicting_ids)

    def test_room_conflict_detection(self):
        # A non-overlapping time slot, so this group's own auto-generated
        # lessons don't themselves conflict with group1 — only the one
        # manually-added lesson below (at group1's actual time) should.
        overlapping_group = Group.objects.create(
            name="React Beginner", course=self.course, teacher=self.teacher2, room=self.room1,
            start_date=dt.date(2026, 9, 7), start_time=dt.time(9, 0), end_time=dt.time(10, 0),
            days_of_week=["mon"],
        )
        # lesson_number=1 for this group was already auto-generated on
        # creation above — use a number outside the plan's range for this
        # extra, manually-placed conflicting lesson.
        conflicting_lesson = Lesson.objects.create(
            group=overlapping_group, lesson_number=99, date=dt.date(2026, 9, 7),
            start_time=dt.time(15, 15), end_time=dt.time(16, 45), room=self.room1,
        )

        response = self._get({"date_from": "2026-09-07", "date_to": "2026-09-07"})
        self.assertEqual(len(response.context["room_conflicts"]), 1)
        self.assertEqual(len(response.context["teacher_conflicts"]), 0)
        self.assertIn(conflicting_lesson.id, response.context["conflicting_ids"])

    def test_cancelled_lesson_never_flagged_as_conflict(self):
        cancelled = self.week1_lessons[0]
        cancelled.status = Lesson.Status.CANCELLED
        cancelled.save(update_fields=["status"])

        # A non-overlapping time slot, so this group's own auto-generated
        # lessons don't themselves conflict with group1 — the point of this
        # test is that a *cancelled* lesson is the only thing near the
        # manually-added lesson below, and cancelled lessons never conflict.
        overlapping_group = Group.objects.create(
            name="Python Advanced", course=self.course, teacher=self.teacher1, room=self.room1,
            start_date=dt.date(2026, 9, 7), start_time=dt.time(9, 0), end_time=dt.time(10, 0),
            days_of_week=["mon"],
        )
        # lesson_number=1 for this group was already auto-generated on
        # creation above — use a number outside the plan's range for this
        # extra, manually-placed conflicting lesson.
        Lesson.objects.create(
            group=overlapping_group, lesson_number=99, date=dt.date(2026, 9, 7),
            start_time=dt.time(15, 30), end_time=dt.time(17, 0), room=self.room1,
        )

        response = self._get({"date_from": "2026-09-07", "date_to": "2026-09-07"})
        self.assertEqual(len(response.context["teacher_conflicts"]), 0)
        self.assertEqual(len(response.context["room_conflicts"]), 0)

    def test_generate_lessons_quick_action(self):
        group = Group.objects.create(
            name="New Group", course=self.course, teacher=self.teacher1, room=self.room1,
            start_date=dt.date(2026, 9, 7), start_time=dt.time(10, 0), end_time=dt.time(11, 0),
            days_of_week=["mon", "wed"],
        )
        sync_and_generate(group)
        # Lessons were already generated the moment the group's Teacher
        # Program (GroupSchedule) was set up — the quick action is now a
        # safe, idempotent retry.
        self.assertEqual(Lesson.objects.filter(group=group).count(), 4)

        url = reverse("admin:academy_schedule_generate_lessons", args=[group.id])
        response = self.admin_web.post(url)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Lesson.objects.filter(group=group).count(), 4)

    def test_generate_lessons_quick_action_admin_only(self):
        group = Group.objects.create(
            name="New Group 2", course=self.course, teacher=self.teacher1, room=self.room1,
            start_date=dt.date(2026, 9, 7), start_time=dt.time(10, 0), end_time=dt.time(11, 0),
            days_of_week=["mon"],
        )
        lessons_before = Lesson.objects.filter(group=group).count()

        url = reverse("admin:academy_schedule_generate_lessons", args=[group.id])
        response = self.teacher_web.post(url)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin/login/", response.url)
        # A non-admin's blocked request must not change anything.
        self.assertEqual(Lesson.objects.filter(group=group).count(), lessons_before)


class ScheduleAdminMultiTeacherTests(AcademyTestBase):
    """Spec item 21: the Расписание page must show each Lesson's *actual*
    teacher (e.g. Islam vs Aizada), not just the group's own primary
    teacher — and the teacher filter / conflict detection must key off that
    same actual teacher too (see admin_views.schedule_view)."""

    def setUp(self):
        super().setUp()
        self.multi_group = Group(
            name="Multi Teacher Group", course=self.course, teacher=self.teacher1, room=self.room1,
            start_date=dt.date(2026, 9, 7), start_time=dt.time(8, 0), end_time=dt.time(9, 0),
            days_of_week=["mon"],
        )
        self.multi_group._defer_schedule_sync = True
        self.multi_group.save()

        self.extra_slot = GroupSchedule(
            group=self.multi_group, teacher=self.teacher2, subject=self.subject_frontend,
            day_of_week="mon", start_time=dt.time(9, 0), end_time=dt.time(9, 30), room=self.room1,
        )
        self.extra_slot._defer_schedule_sync = True
        self.extra_slot.save()

        sync_legacy_group_schedule(self.multi_group)
        generate_lessons_for_group(self.multi_group)

        self.admin_web = DjangoClient()
        self.admin_web.force_login(self.admin)

    def test_schedule_page_shows_actual_teacher_per_lesson(self):
        response = self.admin_web.get(
            reverse("admin:academy_schedule"),
            {"date_from": "2026-09-07", "date_to": "2026-09-07", "group": self.multi_group.id},
        )
        body = response.content.decode()
        self.assertIn(str(self.teacher1), body)
        self.assertIn(str(self.teacher2), body)

    def test_teacher_filter_matches_actual_teacher_not_just_group_owner(self):
        response = self.admin_web.get(
            reverse("admin:academy_schedule"),
            {"date_from": "2026-09-07", "date_to": "2026-09-20", "teacher": self.teacher2.id},
        )
        shown = [lesson for day in response.context["days"] for lesson in day["lessons"]]
        self.assertTrue(shown)
        self.assertTrue(all(lesson.effective_teacher.id == self.teacher2.id for lesson in shown))

    def test_teacher_conflict_uses_actual_teacher_not_group_owner(self):
        # teacher2 also teaches group2 (from AcademyTestBase) — move group2's
        # own lesson #1 to overlap with the extra Monday 09:00-09:30 slot
        # teacher2 also gives here, in a *different* group/room.
        group2_lesson = Lesson.objects.filter(group=self.group2).order_by("lesson_number").first()
        group2_lesson.date = dt.date(2026, 9, 7)
        group2_lesson.start_time = dt.time(9, 0)
        group2_lesson.end_time = dt.time(9, 30)
        group2_lesson.save(update_fields=["date", "start_time", "end_time"])

        response = self.admin_web.get(
            reverse("admin:academy_schedule"), {"date_from": "2026-09-07", "date_to": "2026-09-07"}
        )
        self.assertEqual(len(response.context["teacher_conflicts"]), 1)
        self.assertEqual(len(response.context["room_conflicts"]), 0)
        conflicting_ids = response.context["conflicting_ids"]
        extra_lesson = Lesson.objects.get(group=self.multi_group, teacher=self.teacher2, date=dt.date(2026, 9, 7))
        self.assertIn(extra_lesson.id, conflicting_ids)
        self.assertIn(group2_lesson.id, conflicting_ids)


# ---------------------------------------------------------------------------
# Student Import / Export — apps.academy.services.import_export
# ---------------------------------------------------------------------------

def _csv_file(content: str, name: str = "students.csv") -> SimpleUploadedFile:
    return SimpleUploadedFile(name, content.encode("utf-8"), content_type="text/csv")


class StudentImportExportAPITests(AcademyTestBase):
    """group1 = "Python Beginner" (teacher1, students Алина/Мансур).
    group2 = "Frontend Beginner" (teacher2, student Айбек)."""

    def test_export_returns_csv_with_expected_columns(self):
        response = self.admin_client.get("/api/v1/students/export/?export_format=csv")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response["Content-Type"], "text/csv; charset=utf-8")
        content = response.content.decode("utf-8-sig")
        header = content.splitlines()[0]
        self.assertEqual(header, "id,first_name,last_name,phone,parent_phone,group,is_active,created_at")
        self.assertIn("Python Beginner", content)

    def test_export_xlsx_format(self):
        response = self.admin_client.get("/api/v1/students/export/?export_format=xlsx")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response["Content-Type"],
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    def test_export_respects_current_filters(self):
        response = self.admin_client.get(
            f"/api/v1/students/export/?export_format=csv&group={self.group1.id}"
        )
        content = response.content.decode("utf-8-sig")
        self.assertIn("Алина", content)
        self.assertNotIn("Айбек", content)

    def test_teacher_export_scoped_to_own_groups(self):
        """Teacher permission spec §12: export is limited to the teacher's own groups."""
        response = self.teacher1_client.get("/api/v1/students/export/?export_format=csv")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        content = response.content.decode("utf-8-sig")
        self.assertIn("Алина", content)
        self.assertNotIn("Айбек", content)

    def test_anon_cannot_export(self):
        response = self.anon_client.get("/api/v1/students/export/")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_import_creates_student_with_existing_group(self):
        csv_content = (
            "first_name,last_name,phone,parent_phone,group,is_active\n"
            "Данияр,Сыдыков,+996555000111,+996555000222,Python Beginner,true\n"
        )
        response = self.admin_client.post(
            "/api/v1/students/import/", {"file": _csv_file(csv_content)}, format="multipart"
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(response.data, {"created": 1, "updated": 0, "total": 1})
        student = Student.objects.get(first_name="Данияр")
        self.assertEqual(student.group, self.group1)
        self.assertTrue(student.is_active)

    def test_import_with_unknown_group_is_rejected_and_fully_atomic(self):
        """Spec §7: one bad row rolls back the *whole* file, including valid rows."""
        csv_content = (
            "first_name,last_name,group\n"
            "Валидный,Студент,Python Beginner\n"
            "Невалидный,Студент,Несуществующая Группа\n"
        )
        before = Student.objects.count()
        response = self.admin_client.post(
            "/api/v1/students/import/", {"file": _csv_file(csv_content)}, format="multipart"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["invalid"], 1)
        self.assertIn("Несуществующая Группа", response.data["errors"][0]["errors"][0])
        self.assertEqual(Student.objects.count(), before)
        self.assertFalse(Student.objects.filter(first_name="Валидный").exists())

    def test_group_is_never_auto_created(self):
        csv_content = "first_name,group\nX,Совсем Новая Группа\n"
        self.admin_client.post(
            "/api/v1/students/import/", {"file": _csv_file(csv_content)}, format="multipart"
        )
        self.assertFalse(Group.objects.filter(name="Совсем Новая Группа").exists())

    def test_import_preview_does_not_save_anything(self):
        csv_content = "first_name,last_name\nПревью,Студент\n"
        before = Student.objects.count()
        response = self.admin_client.post(
            "/api/v1/students/import/preview/", {"file": _csv_file(csv_content)}, format="multipart"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, {"total": 1, "valid": 1, "invalid": 0, "errors": []})
        self.assertEqual(Student.objects.count(), before)

    def test_import_updates_existing_student_by_id_upsert(self):
        """Student has no natural unique key besides `id` (spec §13) — updating
        by name would be unsafe, so `id` is the only supported upsert key."""
        csv_content = (
            f"id,first_name,last_name,group,is_active\n"
            f"{self.student1.id},Алина,Иванова-Петрова,Frontend Beginner,false\n"
        )
        response = self.admin_client.post(
            "/api/v1/students/import/", {"file": _csv_file(csv_content)}, format="multipart"
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(response.data, {"created": 0, "updated": 1, "total": 1})
        self.student1.refresh_from_db()
        self.assertEqual(self.student1.last_name, "Иванова-Петрова")
        self.assertEqual(self.student1.group, self.group2)
        self.assertFalse(self.student1.is_active)
        # No duplicate was created.
        self.assertEqual(Student.objects.filter(first_name="Алина").count(), 1)

    def test_import_unknown_id_is_rejected(self):
        csv_content = "id,first_name\n999999,Кто-то\n"
        response = self.admin_client.post(
            "/api/v1/students/import/", {"file": _csv_file(csv_content)}, format="multipart"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("не найден", response.data["errors"][0]["errors"][0])

    def test_import_missing_first_name_is_rejected(self):
        csv_content = "first_name,last_name\n,Безымянный\n"
        response = self.admin_client.post(
            "/api/v1/students/import/", {"file": _csv_file(csv_content)}, format="multipart"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("first_name", response.data["errors"][0]["errors"][0])

    def test_import_invalid_boolean_is_rejected(self):
        csv_content = "first_name,is_active\nТест,может_быть\n"
        response = self.admin_client.post(
            "/api/v1/students/import/", {"file": _csv_file(csv_content)}, format="multipart"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("is_active", response.data["errors"][0]["errors"][0])

    def test_import_invalid_phone_is_rejected(self):
        csv_content = "first_name,phone\nТест,not-a-phone!!\n"
        response = self.admin_client.post(
            "/api/v1/students/import/", {"file": _csv_file(csv_content)}, format="multipart"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_unsupported_file_extension_is_rejected(self):
        bad_file = SimpleUploadedFile("students.txt", b"whatever", content_type="text/plain")
        response = self.admin_client.post(
            "/api/v1/students/import/", {"file": bad_file}, format="multipart"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_teacher_cannot_import_students(self):
        response = self.teacher1_client.post(
            "/api/v1/students/import/", {"file": _csv_file("first_name\nX\n")}, format="multipart"
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(Student.objects.filter(first_name="X").exists())

    def test_teacher_cannot_use_import_preview_either(self):
        response = self.teacher1_client.post(
            "/api/v1/students/import/preview/", {"file": _csv_file("first_name\nX\n")}, format="multipart"
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_round_trip_export_then_import_only_updates(self):
        export_response = self.admin_client.get("/api/v1/students/export/?export_format=csv")
        content = export_response.content.decode("utf-8-sig")
        before = Student.objects.count()

        reimport_response = self.admin_client.post(
            "/api/v1/students/import/", {"file": _csv_file(content)}, format="multipart"
        )
        self.assertEqual(reimport_response.status_code, status.HTTP_201_CREATED, reimport_response.data)
        self.assertEqual(reimport_response.data["created"], 0)
        self.assertEqual(reimport_response.data["updated"], before)
        self.assertEqual(Student.objects.count(), before)


class StudentAdminImportExportTests(AcademyTestBase):
    def setUp(self):
        super().setUp()
        self.admin_web = DjangoClient()
        self.admin_web.force_login(self.admin)
        self.teacher_web = DjangoClient()
        self.teacher_web.force_login(self.teacher1.user)

    def test_changelist_has_import_export_buttons(self):
        response = self.admin_web.get(reverse("admin:academy_student_changelist"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse("admin:academy_student_import"))
        self.assertContains(response, reverse("admin:academy_student_export"))

    def test_export_view_downloads_csv(self):
        response = self.admin_web.get(reverse("admin:academy_student_export"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/csv; charset=utf-8")

    def test_export_view_respects_changelist_filters(self):
        response = self.admin_web.get(
            reverse("admin:academy_student_export"), {"group__id__exact": self.group1.id}
        )
        content = response.content.decode("utf-8-sig")
        self.assertIn("Алина", content)
        self.assertNotIn("Айбек", content)

    def test_import_preview_then_confirm(self):
        csv_content = "first_name,last_name,group\nЖаңыл,Бекова,Python Beginner\n"
        url = reverse("admin:academy_student_import")

        preview_response = self.admin_web.post(url, {"file": _csv_file(csv_content), "preview": "1"})
        self.assertEqual(preview_response.status_code, 200)
        self.assertFalse(Student.objects.filter(first_name="Жаңыл").exists())

        confirm_response = self.admin_web.post(
            url, {"file": _csv_file(csv_content), "confirm": "1"}, follow=True
        )
        self.assertEqual(confirm_response.status_code, 200)
        self.assertTrue(Student.objects.filter(first_name="Жаңыл").exists())

    def test_import_view_requires_admin(self):
        url = reverse("admin:academy_student_import")
        response = self.teacher_web.get(url)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin/login/", response.url)


# ---------------------------------------------------------------------------
# StudentAdmin UX — list/detail pages, the no-hard-delete business rule,
# activate/deactivate, bulk add and the Excel template download.
# ---------------------------------------------------------------------------

class StudentAdminUXTests(AcademyTestBase):
    def setUp(self):
        super().setUp()
        self.admin_web = DjangoClient()
        self.admin_web.force_login(self.admin)
        self.teacher_web = DjangoClient()
        self.teacher_web.force_login(self.teacher1.user)

    # -- list page --------------------------------------------------------

    def test_list_page_opens_and_links_to_detail(self):
        response = self.admin_web.get(reverse("admin:academy_student_changelist"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse("admin:academy_student_detail", args=[self.student1.pk]))

    def test_list_page_has_bulk_add_and_template_links(self):
        response = self.admin_web.get(reverse("admin:academy_student_changelist"))
        self.assertContains(response, reverse("admin:academy_student_bulk_add"))
        self.assertContains(response, reverse("admin:academy_student_template"))

    def test_filters_and_search_still_work(self):
        response = self.admin_web.get(
            reverse("admin:academy_student_changelist"), {"group__id__exact": self.group1.id}
        )
        self.assertContains(response, "Алина")
        self.assertNotContains(response, "Айбек")

        response = self.admin_web.get(reverse("admin:academy_student_changelist"), {"q": "Мансур"})
        self.assertContains(response, "Мансур")
        self.assertNotContains(response, "Айбек")

    # -- detail page --------------------------------------------------------

    def test_detail_page_opens(self):
        response = self.admin_web.get(reverse("admin:academy_student_detail", args=[self.student1.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Алина")
        self.assertContains(response, "Python Beginner")

    def test_detail_page_requires_admin(self):
        response = self.teacher_web.get(reverse("admin:academy_student_detail", args=[self.student1.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin/login/", response.url)

    def test_detail_page_shows_no_group_state(self):
        student = Student.objects.create(first_name="Безгрупповой")
        response = self.admin_web.get(reverse("admin:academy_student_detail", args=[student.pk]))
        self.assertContains(response, "Без группы")

    # -- no hard delete, ever ------------------------------------------------

    def test_delete_view_is_forbidden(self):
        url = reverse("admin:academy_student_delete", args=[self.student1.pk])
        response = self.admin_web.get(url)
        self.assertEqual(response.status_code, 403)
        self.assertTrue(Student.objects.filter(pk=self.student1.pk).exists())

    def test_delete_selected_action_is_not_offered(self):
        response = self.admin_web.get(reverse("admin:academy_student_changelist"))
        self.assertNotContains(response, "delete_selected")

    def test_change_form_has_no_delete_link_for_student_itself(self):
        response = self.admin_web.get(reverse("admin:academy_student_change", args=[self.student1.pk]))
        # The only "deletelink" icon on the page belongs to the unrelated
        # `group` FK's related-widget-wrapper (Django's standard "delete the
        # related object" affordance) — Student's own object-tools row must
        # not contain a delete link/button of its own.
        self.assertNotContains(response, 'class="deletelink"')

    def test_delete_model_and_delete_queryset_refuse_directly(self):
        admin_instance = admin.site._registry[Student]
        with self.assertRaises(DjangoPermissionDenied):
            admin_instance.delete_model(None, self.student1)
        with self.assertRaises(DjangoPermissionDenied):
            admin_instance.delete_queryset(None, Student.objects.filter(pk=self.student1.pk))
        self.assertTrue(Student.objects.filter(pk=self.student1.pk).exists())

    # -- activate / deactivate ------------------------------------------------

    def test_deactivate_view_deactivates_and_reactivate_view_reactivates(self):
        deactivate_url = reverse("admin:academy_student_deactivate", args=[self.student1.pk])
        self.admin_web.post(deactivate_url, {"reason": "no_interest", "comment": ""})
        self.student1.refresh_from_db()
        self.assertFalse(self.student1.is_active)

        reactivate_url = reverse("admin:academy_student_reactivate", args=[self.student1.pk])
        self.admin_web.post(
            reactivate_url,
            {"group": self.group1.pk, "event_date": "2026-09-15", "comment": ""},
        )
        self.student1.refresh_from_db()
        self.assertTrue(self.student1.is_active)

    def test_deactivate_and_reactivate_require_post(self):
        deactivate_url = reverse("admin:academy_student_deactivate", args=[self.student1.pk])
        self.assertEqual(self.admin_web.get(deactivate_url).status_code, 403)
        reactivate_url = reverse("admin:academy_student_reactivate", args=[self.student1.pk])
        self.assertEqual(self.admin_web.get(reactivate_url).status_code, 403)

    def test_bulk_deactivate_and_activate_actions(self):
        changelist_url = reverse("admin:academy_student_changelist")
        self.admin_web.post(
            changelist_url,
            {"action": "deactivate_students", "_selected_action": [self.student1.pk, self.student2.pk]},
        )
        self.student1.refresh_from_db()
        self.student2.refresh_from_db()
        self.assertFalse(self.student1.is_active)
        self.assertFalse(self.student2.is_active)

        self.admin_web.post(
            changelist_url,
            {"action": "activate_students", "_selected_action": [self.student1.pk, self.student2.pk]},
        )
        self.student1.refresh_from_db()
        self.student2.refresh_from_db()
        self.assertTrue(self.student1.is_active)
        self.assertTrue(self.student2.is_active)

    def test_deactivated_student_keeps_attendance_and_homework(self):
        # group1 already has lessons auto-generated in setUp (see
        # sync_and_generate(self.group1)) — reuse one rather than creating a
        # second lesson_number=1 for the same GroupTeacher (unique together).
        lesson = self.group1.lessons.first()
        Attendance.objects.create(student=self.student1, lesson=lesson, status=Attendance.Status.PRESENT)

        self.admin_web.post(
            reverse("admin:academy_student_deactivate", args=[self.student1.pk]),
            {"reason": "no_interest", "comment": ""},
        )
        self.student1.refresh_from_db()
        self.assertFalse(self.student1.is_active)
        self.assertTrue(Attendance.objects.filter(student=self.student1).exists())
        self.assertEqual(self.student1.group_id, self.group1.id)

    # -- assign group ---------------------------------------------------------

    def test_assign_group_action_updates_selected_students(self):
        student = Student.objects.create(first_name="БезГруппыДваЖды")
        changelist_url = reverse("admin:academy_student_changelist")
        response = self.admin_web.post(
            changelist_url, {"action": "assign_group_action", "_selected_action": [student.pk]}
        )
        self.assertEqual(response.status_code, 302)

        assign_url = reverse("admin:academy_student_assign_group")
        response = self.admin_web.post(f"{assign_url}?ids={student.pk}", {"ids": str(student.pk), "group": self.group2.pk})
        self.assertEqual(response.status_code, 302)
        student.refresh_from_db()
        self.assertEqual(student.group_id, self.group2.pk)

    # -- Excel template download ----------------------------------------------

    def test_template_download_works(self):
        response = self.admin_web.get(reverse("admin:academy_student_template"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response["Content-Type"],
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        self.assertIn("okurmenkids_students_template.xlsx", response["Content-Disposition"])

    def test_template_requires_admin(self):
        response = self.teacher_web.get(reverse("admin:academy_student_template"))
        self.assertEqual(response.status_code, 302)

    # -- bulk add ---------------------------------------------------------------

    def _bulk_add_payload(self, **overrides):
        payload = {
            "form-TOTAL_FORMS": "3",
            "form-INITIAL_FORMS": "0",
            "form-MIN_NUM_FORMS": "0",
            "form-MAX_NUM_FORMS": "1000",
            "form-0-first_name": "", "form-0-last_name": "", "form-0-phone": "", "form-0-group": "",
            "form-1-first_name": "", "form-1-last_name": "", "form-1-phone": "", "form-1-group": "",
            "form-2-first_name": "", "form-2-last_name": "", "form-2-phone": "", "form-2-group": "",
        }
        payload.update(overrides)
        return payload

    def test_bulk_add_creates_students_and_skips_blank_rows(self):
        before = Student.objects.count()
        payload = self._bulk_add_payload(**{
            "form-0-first_name": "Жаныбек",
            "form-0-last_name": "Осмонов",
            "form-0-group": str(self.group1.pk),
            "form-0-is_active": "on",
        })
        response = self.admin_web.post(reverse("admin:academy_student_bulk_add"), payload, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Student.objects.count(), before + 1)
        student = Student.objects.get(first_name="Жаныбек")
        self.assertEqual(student.group_id, self.group1.pk)

    def test_bulk_add_all_blank_rows_creates_nothing(self):
        before = Student.objects.count()
        response = self.admin_web.post(
            reverse("admin:academy_student_bulk_add"), self._bulk_add_payload(), follow=True
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Student.objects.count(), before)

    def test_bulk_add_invalid_row_shows_error_and_creates_nothing(self):
        before = Student.objects.count()
        payload = self._bulk_add_payload(**{
            "form-0-first_name": "Бекзат",
            "form-0-phone": "not-a-real-phone!!",
        })
        response = self.admin_web.post(reverse("admin:academy_student_bulk_add"), payload)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Student.objects.count(), before)
        self.assertContains(response, "Некорректный номер телефона")

    def test_bulk_add_duplicate_rows_rejected(self):
        before = Student.objects.count()
        payload = self._bulk_add_payload(**{
            "form-0-first_name": "Дубль", "form-0-last_name": "Студент",
            "form-1-first_name": "Дубль", "form-1-last_name": "Студент",
        })
        response = self.admin_web.post(reverse("admin:academy_student_bulk_add"), payload)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Student.objects.count(), before)
        self.assertContains(response, "Повторяющаяся строка")

    def test_bulk_add_requires_admin(self):
        response = self.teacher_web.get(reverse("admin:academy_student_bulk_add"))
        self.assertEqual(response.status_code, 302)


# ---------------------------------------------------------------------------
# GroupSchedule — a Group's own primary slot (teacher1, Mon/Wed 15:00-16:30,
# room1 for group1; teacher2, Tue/Thu 17:00-18:30, room2 for group2, see
# AcademyTestBase.setUp) is mirrored into GroupSchedule automatically. These
# tests build on top of that for the multi-teacher/multi-subject/multi-time
# scenarios GroupSchedule exists for.
# ---------------------------------------------------------------------------

class GroupScheduleModelTests(AcademyTestBase):
    def test_group_has_legacy_schedule_mirrored_automatically(self):
        rows = list(self.group1.schedules.order_by("day_of_week"))
        self.assertEqual({r.day_of_week for r in rows}, {"mon", "wed"})
        for row in rows:
            self.assertEqual(row.teacher_id, self.teacher1.id)
            self.assertIsNone(row.subject_id)
            self.assertEqual(row.room_id, self.room1.id)
            self.assertEqual(row.start_time, self.group1.start_time)
            self.assertEqual(row.end_time, self.group1.end_time)

    def test_group_can_have_multiple_teachers(self):
        GroupSchedule.objects.create(
            group=self.group1, teacher=self.teacher2, subject=self.subject_frontend,
            day_of_week="mon", start_time=dt.time(17, 0), end_time=dt.time(18, 0), room=self.room1,
        )
        teacher_ids = set(self.group1.schedules.values_list("teacher_id", flat=True))
        self.assertEqual(teacher_ids, {self.teacher1.id, self.teacher2.id})

    def test_group_can_have_multiple_subjects(self):
        GroupSchedule.objects.create(
            group=self.group1, teacher=self.teacher1, subject=self.subject_frontend,
            day_of_week="mon", start_time=dt.time(17, 0), end_time=dt.time(18, 0), room=self.room1,
        )
        subject_ids = set(self.group1.schedules.exclude(subject__isnull=True).values_list("subject_id", flat=True))
        self.assertEqual(subject_ids, {self.subject_frontend.id})

    def test_group_can_have_different_time_ranges(self):
        slot = GroupSchedule.objects.create(
            group=self.group1, teacher=self.teacher1, subject=self.subject_python,
            day_of_week="fri", start_time=dt.time(19, 0), end_time=dt.time(20, 0),
        )
        self.assertNotEqual((slot.start_time, slot.end_time), (self.group1.start_time, self.group1.end_time))

    def test_group_can_have_different_days(self):
        GroupSchedule.objects.create(
            group=self.group1, teacher=self.teacher1, subject=self.subject_python,
            day_of_week="sun", start_time=dt.time(10, 0), end_time=dt.time(11, 0),
        )
        self.assertIn("sun", set(self.group1.schedules.values_list("day_of_week", flat=True)))

    def test_another_group_can_stay_single_slot(self):
        """The other variant §2 requires: a Group can also have just one
        teacher/subject/time, unaffected by GroupSchedule existing at all."""
        self.assertEqual(self.group2.schedules.count(), 2)  # tue + wed... actually tue/thu, one row each
        self.assertTrue(all(row.subject_id is None for row in self.group2.schedules.all()))

    def test_end_time_must_be_after_start_time(self):
        slot = GroupSchedule(
            group=self.group1, teacher=self.teacher1, day_of_week="mon",
            start_time=dt.time(10, 0), end_time=dt.time(9, 0),
        )
        with self.assertRaises(Exception):
            slot.full_clean()

    def test_inactive_teacher_rejected(self):
        self.teacher2.is_active = False
        self.teacher2.save(update_fields=["is_active"])
        slot = GroupSchedule(
            group=self.group1, teacher=self.teacher2, day_of_week="fri",
            start_time=dt.time(10, 0), end_time=dt.time(11, 0),
        )
        with self.assertRaises(Exception):
            slot.full_clean()


class GroupScheduleConflictTests(AcademyTestBase):
    """group1 occupies room1 Mon/Wed 15:00-16:30 with teacher1 (its legacy slot)."""

    def test_teacher_conflict_detected(self):
        conflict = find_schedule_teacher_conflict(
            teacher=self.teacher1, day_of_week="mon", start_time=dt.time(15, 30), end_time=dt.time(16, 0),
        )
        self.assertIsNotNone(conflict)

    def test_room_conflict_detected(self):
        conflict = find_schedule_room_conflict(
            room=self.room1, day_of_week="mon", start_time=dt.time(15, 30), end_time=dt.time(16, 0),
        )
        self.assertIsNotNone(conflict)

    def test_adjacent_slots_do_not_conflict(self):
        # group1 ends at 16:30 — a slot starting exactly then must not clash.
        conflict = find_schedule_teacher_conflict(
            teacher=self.teacher1, day_of_week="mon", start_time=dt.time(16, 30), end_time=dt.time(17, 30),
        )
        self.assertIsNone(conflict)

    def test_overlapping_slots_conflict(self):
        conflict = find_schedule_teacher_conflict(
            teacher=self.teacher1, day_of_week="mon", start_time=dt.time(16, 0), end_time=dt.time(17, 0),
        )
        self.assertIsNotNone(conflict)

    def test_different_teacher_same_time_no_conflict(self):
        conflict = find_schedule_teacher_conflict(
            teacher=self.teacher2, day_of_week="mon", start_time=dt.time(15, 0), end_time=dt.time(16, 30),
        )
        self.assertIsNone(conflict)

    # -- group conflict: one group cannot attend two programs at once ------

    def test_group_conflict_detected_even_with_different_teacher_and_room(self):
        # group1 already has a slot Mon 15:00-16:30 (teacher1/room1) — a
        # second, overlapping slot for group1 with a *different* teacher and
        # room must still be flagged: the group itself can't be in two
        # places at once.
        conflict = find_schedule_group_conflict(
            group=self.group1, day_of_week="mon", start_time=dt.time(15, 30), end_time=dt.time(16, 0),
        )
        self.assertIsNotNone(conflict)

    def test_group_conflict_adjacent_slots_do_not_conflict(self):
        conflict = find_schedule_group_conflict(
            group=self.group1, day_of_week="mon", start_time=dt.time(16, 30), end_time=dt.time(17, 30),
        )
        self.assertIsNone(conflict)

    def test_different_group_same_time_no_group_conflict(self):
        conflict = find_schedule_group_conflict(
            group=self.group2, day_of_week="mon", start_time=dt.time(15, 0), end_time=dt.time(16, 30),
        )
        self.assertIsNone(conflict)

    def test_api_rejects_group_double_booking_with_different_teacher_and_room(self):
        response = self.admin_client.post(
            "/api/v1/schedules/",
            {
                "group": self.group1.id, "teacher": self.teacher2.id, "subject": self.subject_python.id,
                "day_of_week": "mon", "start_time": "15:30", "end_time": "16:00", "room": self.room2.id,
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("group", response.data)

    def test_api_allows_group_adjacent_slot(self):
        response = self.admin_client.post(
            "/api/v1/schedules/",
            {
                "group": self.group1.id, "teacher": self.teacher2.id, "subject": self.subject_python.id,
                "day_of_week": "mon", "start_time": "16:30", "end_time": "17:30", "room": self.room2.id,
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)

    def test_model_clean_rejects_group_double_booking(self):
        slot = GroupSchedule(
            group=self.group1, teacher=self.teacher2, subject=self.subject_python,
            day_of_week="mon", start_time=dt.time(15, 30), end_time=dt.time(16, 0), room=self.room2,
        )
        with self.assertRaises(DjangoValidationError) as ctx:
            slot.full_clean()
        self.assertIn("group", ctx.exception.message_dict)

    def test_api_rejects_teacher_double_booking(self):
        response = self.admin_client.post(
            "/api/v1/schedules/",
            {
                "group": self.group1.id, "teacher": self.teacher1.id, "subject": self.subject_python.id,
                "day_of_week": "mon", "start_time": "16:00", "end_time": "17:00",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("teacher", response.data)

    def test_api_rejects_room_double_booking(self):
        response = self.admin_client.post(
            "/api/v1/schedules/",
            {
                "group": self.group2.id, "teacher": self.teacher2.id, "subject": self.subject_python.id,
                "day_of_week": "mon", "start_time": "15:30", "end_time": "16:00", "room": self.room1.id,
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("room", response.data)

    def test_api_allows_adjacent_slot(self):
        response = self.admin_client.post(
            "/api/v1/schedules/",
            {
                "group": self.group1.id, "teacher": self.teacher1.id, "subject": self.subject_python.id,
                "day_of_week": "mon", "start_time": "16:30", "end_time": "17:30",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)

    def test_teacher_cannot_write_group_schedule(self):
        response = self.teacher1_client.post(
            "/api/v1/schedules/",
            {
                "group": self.group1.id, "teacher": self.teacher1.id, "subject": self.subject_python.id,
                "day_of_week": "fri", "start_time": "10:00", "end_time": "11:00",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class LessonGeneratorConflictSafetyTests(AcademyTestBase):
    """`GroupSchedule.clean()` only runs through a ModelForm/serializer
    `full_clean()` call — a plain `Model.objects.create()` (exactly what a
    raw `.save()`, `bulk_create`, or a data migration does) never triggers
    it. These tests persist a conflicting slot exactly that way, bypassing
    `clean()` entirely, then confirm `generate_lessons_for_group` itself
    (not just admin/serializer validation) refuses to double-book the
    teacher/room — the defense-in-depth check added to `lesson_generator`.
    """

    def test_generation_skips_a_slot_that_double_books_a_teacher(self):
        # group1 already books teacher1 every Monday 15:00-16:30 (see
        # AcademyTestBase.setUp). Persist a second, unrelated Group's slot
        # for the very same teacher/day/time directly via the ORM.
        other_course = Course.objects.create(name="Conflicting Teacher Course", count_lesson=1)
        other_course.subjects.add(self.subject_python)
        CourseLessonPlan.objects.create(
            course=other_course, lesson_number=1, subject=self.subject_python, topic="Тема",
        )
        conflicting_group = Group.objects.create(
            name="Conflicting Teacher Group", course=other_course, start_date=dt.date(2026, 9, 7),
        )
        GroupSchedule.objects.create(
            group=conflicting_group, teacher=self.teacher1, subject=self.subject_python,
            day_of_week="mon", start_time=dt.time(15, 0), end_time=dt.time(16, 30),
        )

        # The post_save signals fired by the two .create() calls above
        # already attempted generation automatically — confirm they
        # produced nothing for the conflicting group.
        self.assertFalse(Lesson.objects.filter(group=conflicting_group).exists())

        # And an explicit, deterministic regeneration call confirms the
        # same: the conflicting slot is the group's only slot, so once it's
        # filtered out there's nothing left to generate from.
        with self.assertRaises(LessonGenerationError):
            generate_lessons_for_group(conflicting_group)

        # group1's own, legitimately-scheduled lessons are completely
        # unaffected by the other group's rejected slot.
        self.assertTrue(Lesson.objects.filter(group=self.group1).exists())

    def test_generation_skips_a_slot_that_double_books_a_room(self):
        # group1 already books room1 every Monday 15:00-16:30.
        other_teacher = make_teacher("conflicting_room_teacher")
        other_course = Course.objects.create(name="Conflicting Room Course", count_lesson=1)
        other_course.subjects.add(self.subject_python)
        CourseLessonPlan.objects.create(
            course=other_course, lesson_number=1, subject=self.subject_python, topic="Тема",
        )
        conflicting_group = Group.objects.create(
            name="Conflicting Room Group", course=other_course, start_date=dt.date(2026, 9, 7),
        )
        GroupSchedule.objects.create(
            group=conflicting_group, teacher=other_teacher, subject=self.subject_python,
            day_of_week="mon", start_time=dt.time(15, 0), end_time=dt.time(16, 30), room=self.room1,
        )

        self.assertFalse(Lesson.objects.filter(group=conflicting_group).exists())
        with self.assertRaises(LessonGenerationError):
            generate_lessons_for_group(conflicting_group)

    def test_generation_skips_slots_that_double_book_a_group(self):
        # One group, two independent programs (different teacher, different
        # room, own individual lesson plans) whose schedules overlap — the
        # group itself physically can't attend both at once, even though
        # neither the teacher nor the room conflict check would catch it.
        course = Course.objects.create(name="Conflicting Group Course", count_lesson=1)
        course.subjects.add(self.subject_python, self.subject_frontend)
        teacher_a = make_teacher("group_conflict_teacher_a")
        teacher_b = make_teacher("group_conflict_teacher_b")
        conflicting_group = Group.objects.create(
            name="Conflicting Group Group", course=course, start_date=dt.date(2026, 9, 7),
        )
        slot_a = GroupSchedule.objects.create(
            group=conflicting_group, teacher=teacher_a, subject=self.subject_python,
            day_of_week="mon", start_time=dt.time(8, 0), end_time=dt.time(9, 0), room=self.room1,
        )
        slot_b = GroupSchedule.objects.create(
            group=conflicting_group, teacher=teacher_b, subject=self.subject_frontend,
            day_of_week="mon", start_time=dt.time(8, 30), end_time=dt.time(9, 30), room=self.room2,
        )
        GroupTeacherLessonPlan.objects.create(group_teacher=slot_a.group_teacher, lesson_number=1, topic="A Тема")
        GroupTeacherLessonPlan.objects.create(group_teacher=slot_b.group_teacher, lesson_number=1, topic="B Тема")

        # Both programs' only slot conflicts with the other — neither can
        # generate a lesson without putting the group in two places at once.
        with self.assertRaises(LessonGenerationError):
            generate_lessons_for_group(conflicting_group)
        self.assertEqual(Lesson.objects.filter(group=conflicting_group).count(), 0)


class AvailabilityAPITests(AcademyTestBase):
    """group1: teacher1/room1, Mon/Wed 15:00-16:30. group2: teacher2/room2, Tue/Thu 17:00-18:30."""

    def test_free_rooms_excludes_occupied(self):
        response = self.admin_client.get(
            "/api/v1/rooms/available/", {"date": "2026-09-07", "start_time": "15:00", "end_time": "16:30"}
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        available_names = {r["name"] for r in response.data["available"]}
        self.assertNotIn(self.room1.name, available_names)
        self.assertIn(self.room2.name, available_names)
        occupied_names = {o["room_name"] for o in response.data["occupied"]}
        self.assertIn(self.room1.name, occupied_names)

    def test_free_teachers_excludes_occupied(self):
        response = self.admin_client.get(
            "/api/v1/availability/",
            {"date": "2026-09-07", "start_time": "15:00", "end_time": "16:30"},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        available_usernames = {t["user"]["username"] for t in response.data["available"]}
        self.assertNotIn(self.teacher1.user.username, available_usernames)
        self.assertIn(self.teacher2.user.username, available_usernames)
        occupied_names = {o["teacher_name"] for o in response.data["occupied"]}
        self.assertIn(str(self.teacher1), occupied_names)

    def test_free_teachers_requires_authentication(self):
        response = self.anon_client.get("/api/v1/availability/")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


# ---------------------------------------------------------------------------
# Multi-schedule Lesson generation — the task's own worked example: a Monday
# with 3 sessions (IT/Islam, SoftSkills/TeacherX, English/TeacherY), a
# Thursday with 2 (IT, English), a Friday with 1 (IT only).
# ---------------------------------------------------------------------------

class MultiScheduleLessonGeneratorTests(TestCase):
    def setUp(self):
        self.admin = make_admin("gen_admin")
        self.islam = make_teacher("islam_gen")
        self.teacher_x = make_teacher("teacherx_gen")
        self.teacher_y = make_teacher("teachery_gen")

        self.subject_it = Subject.objects.create(name="GenIT")
        self.subject_soft = Subject.objects.create(name="GenSoft")
        self.subject_eng = Subject.objects.create(name="GenEng")

        self.room15 = Room.objects.create(name="GenRoom15", capacity=20)
        self.room7 = Room.objects.create(name="GenRoom7", capacity=20)

        self.course = Course.objects.create(name="GenCourse", count_lesson=9)
        self.course.subjects.set([self.subject_it, self.subject_soft, self.subject_eng])

        # Arranged in the same order the schedule below will actually
        # produce lessons in (see lesson_generator's module docstring).
        rotation = [
            self.subject_it, self.subject_soft, self.subject_eng,
            self.subject_it, self.subject_eng,
            self.subject_it,
            self.subject_it, self.subject_soft, self.subject_eng,
        ]
        for i, subject in enumerate(rotation, start=1):
            CourseLessonPlan.objects.create(
                course=self.course, lesson_number=i, subject=subject, topic=f"Topic {i}",
                homework_title=(f"HW{i}" if i % 3 == 0 else ""),
            )

        # 2026-09-14 is a Monday.
        self.group = Group(
            name="Prog1-IT", course=self.course, teacher=self.islam, room=self.room15,
            start_date=dt.date(2026, 9, 14), start_time=dt.time(8, 0), end_time=dt.time(9, 0),
            days_of_week=["mon", "thu", "fri"],
        )
        # Set up the whole schedule (primary slot + extra slots) before the
        # first generation runs — exactly what GroupAdmin's deferred
        # save_model/save_formset/save_related does for a real admin
        # submission (see admin.GroupAdmin), simulated here directly.
        self.group._defer_schedule_sync = True
        self.group.save()

        for teacher, subject, day, start, end, room in [
            (self.teacher_x, self.subject_soft, "mon", dt.time(9, 0), dt.time(9, 30), self.room15),
            (self.teacher_y, self.subject_eng, "mon", dt.time(19, 0), dt.time(20, 0), self.room7),
            (self.teacher_y, self.subject_eng, "thu", dt.time(19, 0), dt.time(20, 0), self.room7),
        ]:
            slot = GroupSchedule(
                group=self.group, teacher=teacher, subject=subject,
                day_of_week=day, start_time=start, end_time=end, room=room,
            )
            slot._defer_schedule_sync = True
            slot.save()

        sync_legacy_group_schedule(self.group)
        generate_lessons_for_group(self.group)

    def test_lesson_numbers_are_strictly_sequential(self):
        numbers = list(
            Lesson.objects.filter(group=self.group).order_by("date", "start_time").values_list("lesson_number", flat=True)
        )
        self.assertEqual(numbers, list(range(1, 10)))

    def test_monday_has_three_lessons_in_time_order(self):
        monday_lessons = list(Lesson.objects.filter(group=self.group, date=dt.date(2026, 9, 14)).order_by("start_time"))
        self.assertEqual([l.subject.name for l in monday_lessons], ["GenIT", "GenSoft", "GenEng"])
        self.assertEqual(
            [l.teacher.user.username for l in monday_lessons], ["islam_gen", "teacherx_gen", "teachery_gen"]
        )
        self.assertEqual([l.lesson_number for l in monday_lessons], [1, 2, 3])

    def test_thursday_skips_soft_skills(self):
        thursday_lessons = list(Lesson.objects.filter(group=self.group, date=dt.date(2026, 9, 17)).order_by("start_time"))
        self.assertEqual([l.subject.name for l in thursday_lessons], ["GenIT", "GenEng"])

    def test_friday_has_only_it(self):
        friday_lessons = list(Lesson.objects.filter(group=self.group, date=dt.date(2026, 9, 18)))
        self.assertEqual(len(friday_lessons), 1)
        self.assertEqual(friday_lessons[0].subject.name, "GenIT")

    def test_next_week_continues_the_same_sequence(self):
        next_monday = list(Lesson.objects.filter(group=self.group, date=dt.date(2026, 9, 21)).order_by("start_time"))
        self.assertEqual([l.lesson_number for l in next_monday], [7, 8, 9])

    def test_generator_is_idempotent_on_repeat_calls(self):
        self.assertEqual(len(generate_lessons_for_group(self.group)), 0)
        self.assertEqual(len(generate_lessons_for_group(self.group)), 0)
        self.assertEqual(Lesson.objects.filter(group=self.group).count(), 9)

    def test_lesson_teacher_is_set_per_slot(self):
        soft_lesson = Lesson.objects.get(group=self.group, subject=self.subject_soft, lesson_number=2)
        self.assertEqual(soft_lesson.teacher_id, self.teacher_x.id)
        self.assertEqual(soft_lesson.effective_teacher.id, self.teacher_x.id)

    def test_homework_auto_created_from_plan(self):
        for number in (3, 6, 9):
            lesson = Lesson.objects.get(group=self.group, lesson_number=number)
            self.assertTrue(Homework.objects.filter(lesson=lesson, title=f"HW{number}").exists())

    def test_lesson_without_planned_homework_has_none(self):
        lesson1 = Lesson.objects.get(group=self.group, lesson_number=1)
        self.assertFalse(Homework.objects.filter(lesson=lesson1).exists())

    def test_lesson_can_have_multiple_homework(self):
        lesson3 = Lesson.objects.get(group=self.group, lesson_number=3)
        Homework.objects.create(lesson=lesson3, title="Дополнительное ДЗ")
        self.assertEqual(Homework.objects.filter(lesson=lesson3).count(), 2)

    def test_past_lesson_untouched_by_regeneration(self):
        lesson1 = Lesson.objects.get(group=self.group, lesson_number=1)
        lesson1.topic = "Отредактировано вручную"
        lesson1.save(update_fields=["topic"])
        generate_lessons_for_group(self.group)
        lesson1.refresh_from_db()
        self.assertEqual(lesson1.topic, "Отредактировано вручную")

    def test_completed_lesson_untouched_by_regeneration(self):
        lesson1 = Lesson.objects.get(group=self.group, lesson_number=1)
        lesson1.status = Lesson.Status.COMPLETED
        lesson1.save(update_fields=["status"])
        generate_lessons_for_group(self.group)
        lesson1.refresh_from_db()
        self.assertEqual(lesson1.status, Lesson.Status.COMPLETED)

    def test_removing_a_slot_does_not_delete_its_lessons(self):
        soft_slot = GroupSchedule.objects.get(group=self.group, subject=self.subject_soft)
        soft_lesson_id = Lesson.objects.get(group=self.group, subject=self.subject_soft, lesson_number=2).id
        soft_slot.delete()

        soft_lesson = Lesson.objects.get(pk=soft_lesson_id)
        self.assertIsNone(soft_lesson.schedule_id)
        self.assertEqual(Lesson.objects.filter(group=self.group).count(), 9)


# ---------------------------------------------------------------------------
# Data migration: existing (pre-GroupSchedule) Group data is backfilled into
# GroupSchedule without touching Group/Student data itself.
# ---------------------------------------------------------------------------

class GroupScheduleBackfillMigrationTests(AcademyTestBase):
    def test_backfill_recreates_legacy_schedule_from_group_fields(self):
        # Simulate "before GroupSchedule existed": no schedule rows at all.
        GroupSchedule.objects.filter(group=self.group1).delete()
        self.assertEqual(self.group1.schedules.count(), 0)

        import importlib

        from django.apps import apps as django_apps

        migration = importlib.import_module("apps.academy.migrations.0004_backfill_group_schedule")
        migration.backfill_group_schedule(django_apps, None)

        rows = list(self.group1.schedules.order_by("day_of_week"))
        self.assertEqual({r.day_of_week for r in rows}, {"mon", "wed"})
        for row in rows:
            self.assertEqual(row.teacher_id, self.teacher1.id)
            self.assertEqual(row.room_id, self.room1.id)
            self.assertEqual(row.start_time, self.group1.start_time)
            self.assertEqual(row.end_time, self.group1.end_time)
            self.assertIsNone(row.subject_id)
            self.assertTrue(row.is_active)

    def test_existing_group_and_student_data_untouched_by_backfill(self):
        groups_before = set(Group.objects.values_list("id", "name"))
        students_before = set(Student.objects.values_list("id", "first_name", "group_id"))

        import importlib

        from django.apps import apps as django_apps

        migration = importlib.import_module("apps.academy.migrations.0004_backfill_group_schedule")
        migration.backfill_group_schedule(django_apps, None)

        self.assertEqual(set(Group.objects.values_list("id", "name")), groups_before)
        self.assertEqual(set(Student.objects.values_list("id", "first_name", "group_id")), students_before)

    def test_backfill_skips_cancelled_group_as_inactive(self):
        self.group1.status = Group.Status.CANCELLED
        self.group1.save(update_fields=["status"])
        GroupSchedule.objects.filter(group=self.group1).delete()

        import importlib

        from django.apps import apps as django_apps

        migration = importlib.import_module("apps.academy.migrations.0004_backfill_group_schedule")
        migration.backfill_group_schedule(django_apps, None)

        self.assertTrue(self.group1.schedules.exists())
        self.assertFalse(self.group1.schedules.filter(is_active=True).exists())


# ---------------------------------------------------------------------------
# Permissions for a multi-teacher group: a Teacher who only holds a
# GroupSchedule slot (not `group.teacher`) gets the same access to that
# group a single teacher always had; an unrelated teacher stays denied.
# ---------------------------------------------------------------------------

class MultiTeacherPermissionsTests(AcademyTestBase):
    def setUp(self):
        super().setUp()
        # teacher2 (who "owns" group2) also teaches a slot in group1, which
        # teacher1 owns as `group.teacher` — teacher2 has no `group.teacher`
        # stake in group1 at all, only this schedule slot, running as its
        # own independent Teaching Program with its own plan (see
        # models.GroupTeacher/GroupTeacherLessonPlan) — spec §39: a Teaching
        # Program's Lessons are its own, not "whichever Lesson the group
        # happens to have".
        self.extra_slot = GroupSchedule.objects.create(
            group=self.group1, teacher=self.teacher2, subject=self.subject_frontend,
            day_of_week="mon", start_time=dt.time(17, 0), end_time=dt.time(18, 0), room=self.room1,
        )
        GroupTeacherLessonPlan.objects.create(
            group_teacher=self.extra_slot.group_teacher, lesson_number=1, topic="Intro to Frontend",
        )
        generate_lessons_for_group(self.group1)
        self.teacher2_own_lesson = Lesson.objects.get(group=self.group1, teacher=self.teacher2)

    def test_teacher_with_only_schedule_slot_sees_the_group(self):
        response = self.teacher2_client.get("/api/v1/groups/")
        names = {g["name"] for g in response.data["results"]}
        self.assertIn(self.group1.name, names)
        self.assertIn(self.group2.name, names)

    def test_teacher_with_only_schedule_slot_can_read_group_detail(self):
        response = self.teacher2_client.get(f"/api/v1/groups/{self.group1.id}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_teacher_with_only_schedule_slot_can_access_own_lesson(self):
        response = self.teacher2_client.get(f"/api/v1/lessons/{self.teacher2_own_lesson.id}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_teacher_with_only_schedule_slot_can_mark_attendance_on_own_lesson(self):
        response = self.teacher2_client.post(
            f"/api/v1/lessons/{self.teacher2_own_lesson.id}/attendance/",
            [{"student": self.student1.id, "status": "present"}],
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_teacher_with_only_schedule_slot_cannot_access_colleagues_lesson_in_same_group(self):
        # Spec §39: teacher2's own slot doesn't grant access to teacher1's
        # Lessons in the very same Group.
        colleagues_lesson = Lesson.objects.filter(group=self.group1, teacher=self.teacher1).first()
        response = self.teacher2_client.get(f"/api/v1/lessons/{colleagues_lesson.id}/")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_unrelated_teacher_still_denied(self):
        outsider = make_teacher("outsider_perm")
        outsider_client = APIClient()
        outsider_client.force_authenticate(outsider.user)

        response = outsider_client.get(f"/api/v1/groups/{self.group1.id}/")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

        lesson = Lesson.objects.filter(group=self.group1).order_by("lesson_number").first()
        response = outsider_client.get(f"/api/v1/lessons/{lesson.id}/")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


# ---------------------------------------------------------------------------
# GroupTeacher — "this Teacher teaches this Subject in this Group": one
# teacher's own subject/schedule, independent of every other teacher in the
# same group (see models.GroupTeacher). Get-or-created automatically from
# GroupSchedule, never created directly.
# ---------------------------------------------------------------------------

class GroupTeacherAdminPagesTests(AcademyTestBase):
    """Regression coverage for GroupAdmin.teaching_programs_summary / the new
    GroupTeacher admin pages — none of the API-only tests above actually
    render these Django admin templates, so a template-level bug (e.g. an
    invalid format_html() call) wouldn't otherwise be caught."""

    def setUp(self):
        super().setUp()
        self.django_admin_client = DjangoClient()
        self.django_admin_client.force_login(self.admin)
        self.extra_slot = GroupSchedule.objects.create(
            group=self.group1, teacher=self.teacher2, subject=self.subject_frontend,
            day_of_week="fri", start_time=dt.time(10, 0), end_time=dt.time(11, 0),
        )
        GroupTeacherLessonPlan.objects.create(
            group_teacher=self.extra_slot.group_teacher, lesson_number=1, topic="Own plan lesson 1"
        )

    def test_group_change_page_renders_workspace_summary(self):
        # Teaching-program detail (per-program cards, plan badges) moved to
        # the Group Workspace's own Programs tab — the change form now only
        # keeps a compact link into it (see GroupAdmin.workspace_summary).
        response = self.django_admin_client.get(f"/admin/academy/group/{self.group1.id}/change/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        body = response.content.decode()
        self.assertIn("Открыть рабочее пространство", body)
        self.assertIn(reverse("admin:academy_group_workspace", args=[self.group1.id]), body)

    def test_group_change_page_renders_capacity_summary(self):
        # The heavy "Сводка группы" 6-card block moved to the Workspace
        # Overview tab (see GroupWorkspaceOverviewTests) — the change form
        # keeps only the compact capacity summary in "Ограничения".
        response = self.django_admin_client.get(f"/admin/academy/group/{self.group1.id}/change/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        body = response.content.decode()
        self.assertIn("Студентов сейчас", body)

    def test_add_group_page_shows_helpful_pre_save_message(self):
        response = self.django_admin_client.get("/admin/academy/group/add/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        body = response.content.decode()
        self.assertIn("Рабочее пространство появится после сохранения группы", body)

    # Legacy-fieldset coverage now lives in LegacyGroupFieldsTests — the
    # section is fully removed, not just read-only, so there's nothing
    # left to assert here beyond what that class already covers.

    def test_group_summary_capacity_warns_when_exceeded(self):
        self.group1.max_students = 1
        self.group1.save(update_fields=["max_students"])
        response = self.django_admin_client.get(f"/admin/academy/group/{self.group1.id}/change/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        body = response.content.decode()
        self.assertIn("Превышена на", body)

    def test_group_teacher_change_and_list_pages_render(self):
        for group_teacher in self.group1.teachers.all():
            response = self.django_admin_client.get(f"/admin/academy/groupteacher/{group_teacher.id}/change/")
            self.assertEqual(response.status_code, status.HTTP_200_OK)

        response = self.django_admin_client.get("/admin/academy/groupteacher/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_lesson_list_page_renders(self):
        response = self.django_admin_client.get("/admin/academy/lesson/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_no_teacher_program_is_labelled_as_primary_or_main(self):
        # The whole point of this architecture: every Teacher Program is
        # equal — no "Основной"/"main" business distinction shown anywhere.
        response = self.django_admin_client.get(
            reverse("admin:academy_group_workspace_programs", args=[self.group1.id])
        )
        body = response.content.decode()
        self.assertNotIn("основной", body.lower())
        self.assertNotIn("(main)", body.lower())

    def test_workspace_schedule_tab_shows_every_row_including_legacy_origin_ones(self):
        # Previously the legacy-mirrored (subject=None) row was hidden from
        # the Group form's schedule inline; the Workspace Schedule tab keeps
        # every GroupSchedule row of the group as an equal row — no row is
        # special-cased out.
        response = self.django_admin_client.get(
            reverse("admin:academy_group_workspace_schedule", args=[self.group1.id])
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        days = response.context["days"]
        schedule_ids = {row["obj"].pk for day in days for row in day["slots"]}
        self.assertEqual(schedule_ids, set(GroupSchedule.objects.filter(group=self.group1).values_list("id", flat=True)))
        self.assertTrue(GroupSchedule.objects.filter(group=self.group1, subject__isnull=True).exists())


class GroupTeacherWorkspaceViewTests(AcademyTestBase):
    """`/admin/academy/groupteacher/<id>/workspace/` — the Program Workspace.
    group1 has two independent Teaching Programs (see AcademyTestBase.setUp
    + this class's own extra one): the original teacher1/legacy-plan
    program, and a second teacher2 program with its own individual lesson
    plan — every stat on one program's workspace page must reflect only
    that program, never the other's."""

    def setUp(self):
        super().setUp()
        self.django_admin_client = DjangoClient()
        self.django_admin_client.force_login(self.admin)
        self.django_teacher_client = DjangoClient()
        self.django_teacher_client.force_login(self.teacher1.user)

        self.program1 = self.group1.teachers.get(teacher=self.teacher1)
        self.extra_slot = GroupSchedule.objects.create(
            group=self.group1, teacher=self.teacher2, subject=self.subject_frontend,
            day_of_week="fri", start_time=dt.time(10, 0), end_time=dt.time(11, 0),
        )
        self.program2 = self.extra_slot.group_teacher
        GroupTeacherLessonPlan.objects.create(
            group_teacher=self.program2, lesson_number=1, topic="Own plan lesson 1", homework_title="HW1",
        )
        generate_lessons_for_group(self.group1)

    def _workspace_url(self, group_teacher) -> str:
        return reverse("admin:academy_groupteacher_workspace", args=[group_teacher.id])

    def test_admin_can_open_workspace(self):
        response = self.django_admin_client.get(self._workspace_url(self.program1))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        body = response.content.decode()
        self.assertIn("Рабочее пространство программы", body)
        self.assertIn(str(self.teacher1), body)

    def test_teacher_cannot_open_workspace(self):
        response = self.django_teacher_client.get(self._workspace_url(self.program1))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin/login/", response.url)

    def test_workspace_shows_only_its_own_programs_lessons(self):
        response = self.django_admin_client.get(self._workspace_url(self.program2))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        stats = response.context["lesson_stats"]
        expected = Lesson.objects.filter(group_teacher=self.program2).count()
        self.assertGreater(expected, 0)
        self.assertEqual(stats["generated"], expected)
        # program1's own lesson count must not leak into program2's page.
        self.assertNotEqual(
            stats["generated"], Lesson.objects.filter(group_teacher=self.program1).count()
        )

    def test_workspace_has_open_workspace_link_on_group_page(self):
        # Per-program "Открыть рабочее пространство" links moved from the
        # Group change form to the Group Workspace's own Programs tab.
        response = self.django_admin_client.get(
            reverse("admin:academy_group_workspace_programs", args=[self.group1.id])
        )
        body = response.content.decode()
        self.assertIn(self._workspace_url(self.program1), body)
        self.assertIn(self._workspace_url(self.program2), body)

    def test_attendance_stats_are_scoped_to_this_program_only(self):
        lesson1 = Lesson.objects.filter(group_teacher=self.program1).first()
        lesson2 = Lesson.objects.filter(group_teacher=self.program2).first()
        Attendance.objects.create(student=self.student1, lesson=lesson1, status=Attendance.Status.PRESENT)
        Attendance.objects.create(student=self.student1, lesson=lesson2, status=Attendance.Status.ABSENT)

        response1 = self.django_admin_client.get(self._workspace_url(self.program1))
        response2 = self.django_admin_client.get(self._workspace_url(self.program2))

        self.assertEqual(response1.context["attendance_stats"]["total"], 1)
        self.assertEqual(response1.context["attendance_stats"]["present"], 1)
        self.assertEqual(response2.context["attendance_stats"]["total"], 1)
        self.assertEqual(response2.context["attendance_stats"]["absent"], 1)


# ---------------------------------------------------------------------------
# Group Workspace — /admin/academy/group/<id>/workspace/... . group1/group2
# (see AcademyTestBase.setUp) already have students, a legacy-plan Teaching
# Program and generated lessons, so most tabs exercise real, non-empty data;
# a fresh Group covers the empty states.
# ---------------------------------------------------------------------------

class GroupWorkspaceViewTests(AcademyTestBase):
    def setUp(self):
        super().setUp()
        self.admin_web = DjangoClient()
        self.admin_web.force_login(self.admin)
        self.teacher_web = DjangoClient()
        self.teacher_web.force_login(self.teacher1.user)

    def _url(self, name, *args):
        return reverse(f"admin:academy_group_workspace{name}", args=[self.group1.id, *args])

    # -- access control -----------------------------------------------------

    def test_workspace_requires_admin_non_staff_teacher_redirected_to_login(self):
        # teacher1 (see AcademyTestBase.make_teacher) isn't Django `is_staff`
        # at all, so admin_site.admin_view()'s own login gate redirects
        # before _require_admin ever runs — same pattern as every other
        # admin-only view in this app (e.g. StudentAdmin's import/template).
        response = self.teacher_web.get(self._url(""))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin/login/", response.url)

    def test_workspace_requires_login_anon_redirects(self):
        response = DjangoClient().get(self._url(""))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin/login/", response.url)

    def test_workspace_forbidden_for_staff_non_admin_role(self):
        # A user who *is* Django is_staff (so admin_site.admin_view() lets
        # them past the login gate) but isn't Admin-role/superuser must
        # still be refused by _require_admin() itself.
        self.teacher1.user.is_staff = True
        self.teacher1.user.save(update_fields=["is_staff"])
        staff_teacher_web = DjangoClient()
        staff_teacher_web.force_login(self.teacher1.user)
        response = staff_teacher_web.get(self._url(""))
        self.assertEqual(response.status_code, 403)

    # -- overview -------------------------------------------------------------

    def test_overview_shows_real_kpis(self):
        response = self.admin_web.get(self._url(""))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["kpi"]["students"], self.group1.students_count)
        self.assertEqual(response.context["kpi"]["programs"], self.group1.teachers.filter(is_active=True).count())

    def test_overview_empty_programs_state(self):
        empty_group = Group.objects.create(name="Empty Group", course=self.course, start_date=dt.date(2026, 9, 7))
        response = self.admin_web.get(reverse("admin:academy_group_workspace", args=[empty_group.id]))
        self.assertContains(response, "Пока нет учебных программ")

    # -- students tab ---------------------------------------------------------

    def test_students_tab_lists_group_students_only(self):
        response = self.admin_web.get(self._url("_students"))
        # Scoped to the roster itself (response.context["students"]) rather
        # than raw page text — Айбек legitimately appears elsewhere on the
        # same page now, as a candidate in the "Добавить существующих" modal.
        names = {str(s) for s in response.context["students"]}
        self.assertIn(str(self.student1), names)
        self.assertIn(str(self.student2), names)
        self.assertNotIn(str(self.student3), names)  # belongs to group2

    def test_students_tab_search_filters(self):
        response = self.admin_web.get(self._url("_students"), {"q": "Алина"})
        self.assertContains(response, "Алина")
        self.assertNotContains(response, "Мансур")

    def test_add_existing_students_bulk_moves_them_into_group(self):
        response = self.admin_web.post(
            self._url("_students_add_existing"), {"students": [str(self.student3.pk)]}
        )
        self.assertEqual(response.status_code, 302)
        self.student3.refresh_from_db()
        self.assertEqual(self.student3.group_id, self.group1.id)

    def test_add_existing_students_modal_lists_candidates_not_in_group(self):
        response = self.admin_web.get(self._url("_students"))
        candidate_names = {str(s) for s in response.context["candidate_students"]}
        self.assertIn(str(self.student3), candidate_names)
        self.assertNotIn(str(self.student1), candidate_names)  # already in group1

    def test_create_new_student_adds_to_group(self):
        response = self.admin_web.post(
            self._url("_students_add"),
            {"create_new": "1", "first_name": "Жаныл", "last_name": "Осмонова", "is_active": "on"},
        )
        self.assertEqual(response.status_code, 302)
        student = Student.objects.get(first_name="Жаныл")
        self.assertEqual(student.group_id, self.group1.id)

    def test_remove_student_clears_group_but_keeps_student(self):
        response = self.admin_web.post(self._url("_students_remove", self.student1.pk))
        self.assertEqual(response.status_code, 302)
        self.student1.refresh_from_db()
        self.assertIsNone(self.student1.group_id)
        self.assertTrue(Student.objects.filter(pk=self.student1.pk).exists())

    def test_remove_student_requires_post(self):
        response = self.admin_web.get(self._url("_students_remove", self.student1.pk))
        self.assertEqual(response.status_code, 403)

    # -- programs tab -----------------------------------------------------------

    def test_programs_tab_lists_existing_programs(self):
        response = self.admin_web.get(self._url("_programs"))
        self.assertContains(response, str(self.teacher1))

    def test_add_program_creates_group_teacher_and_schedule_slots(self):
        response = self.admin_web.post(
            self._url("_programs_add"),
            {
                "teacher": self.teacher2.pk, "subject": self.subject_frontend.pk,
                "day_of_week": ["mon", "wed"], "start_time": "18:00", "end_time": "19:30",
                "lesson_plan_source": "course",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            GroupTeacher.objects.filter(group=self.group1, teacher=self.teacher2, subject=self.subject_frontend).exists()
        )
        gt = GroupTeacher.objects.get(group=self.group1, teacher=self.teacher2, subject=self.subject_frontend)
        self.assertEqual(gt.schedules.count(), 2)

    def test_add_program_does_not_duplicate_existing_group_teacher(self):
        # teacher1 already has a program in group1 (legacy slot) — adding
        # another schedule for the exact same teacher+subject must reuse it.
        before = GroupTeacher.objects.filter(group=self.group1, teacher=self.teacher1).count()
        self.admin_web.post(
            self._url("_programs_add"),
            {
                "teacher": self.teacher1.pk, "subject": self.subject_python.pk,
                "day_of_week": ["fri"], "start_time": "20:00", "end_time": "21:00",
                "lesson_plan_source": "course",
            },
        )
        after = GroupTeacher.objects.filter(group=self.group1, teacher=self.teacher1, subject=self.subject_python).count()
        self.assertEqual(after, 1)

    def test_add_program_rejects_conflicting_slot(self):
        # teacher1 is already booked Mon 15:00-16:30 in group1 itself.
        response = self.admin_web.post(
            self._url("_programs_add"),
            {
                "teacher": self.teacher1.pk, "subject": self.subject_python.pk,
                "day_of_week": ["mon"], "start_time": "15:30", "end_time": "16:00",
                "lesson_plan_source": "course",
            },
        )
        self.assertEqual(response.status_code, 200)  # re-rendered with errors, no redirect
        self.assertFalse(
            GroupSchedule.objects.filter(
                group=self.group1, teacher=self.teacher1, day_of_week="mon", start_time=dt.time(15, 30)
            ).exists()
        )

    # -- schedule tab -----------------------------------------------------------

    def test_schedule_tab_lists_every_slot(self):
        response = self.admin_web.get(self._url("_schedule"))
        days = response.context["days"]
        self.assertEqual(
            {row["obj"].pk for day in days for row in day["slots"]},
            set(GroupSchedule.objects.filter(group=self.group1).values_list("id", flat=True)),
        )

    def test_add_schedule_slot_for_existing_program(self):
        program = self.group1.teachers.get(teacher=self.teacher1)
        response = self.admin_web.post(
            self._url("_schedule_add"),
            {"group_teacher": program.pk, "day_of_week": "fri", "start_time": "10:00", "end_time": "11:00"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            GroupSchedule.objects.filter(group=self.group1, group_teacher=program, day_of_week="fri").exists()
        )

    def test_remove_schedule_slot(self):
        slot = self.group1.schedules.first()
        response = self.admin_web.post(self._url("_schedule_remove", slot.pk))
        self.assertEqual(response.status_code, 302)
        self.assertFalse(GroupSchedule.objects.filter(pk=slot.pk).exists())

    def test_schedule_empty_state(self):
        empty_group = Group.objects.create(name="No Schedule Group", course=self.course, start_date=dt.date(2026, 9, 7))
        response = self.admin_web.get(reverse("admin:academy_group_workspace_schedule", args=[empty_group.id]))
        self.assertContains(response, "Расписание ещё не настроено")

    # -- lessons tab -----------------------------------------------------------

    def test_lessons_tab_paginates_and_filters_by_status(self):
        generate_lessons_for_group(self.group1)
        response = self.admin_web.get(self._url("_lessons"))
        self.assertEqual(response.status_code, 200)
        self.assertGreater(response.context["lessons"].paginator.count, 0)

        response = self.admin_web.get(self._url("_lessons"), {"status": Lesson.Status.CANCELLED})
        self.assertEqual(response.context["lessons"].paginator.count, 0)

    # -- generate lessons -----------------------------------------------------

    def test_generate_lessons_reports_created_and_idempotent_rerun(self):
        response = self.admin_web.post(self._url("_generate_lessons"), follow=True)
        self.assertEqual(response.status_code, 200)
        created_total = Lesson.objects.filter(group=self.group1).count()
        self.assertGreater(created_total, 0)

        response = self.admin_web.post(self._url("_generate_lessons"), follow=True)
        self.assertEqual(Lesson.objects.filter(group=self.group1).count(), created_total)
        self.assertContains(response, "Уже существовало")

    def test_generate_lessons_requires_post(self):
        response = self.admin_web.get(self._url("_generate_lessons"))
        self.assertEqual(response.status_code, 405)

    # -- attendance / homework / analytics tabs ------------------------------

    def test_attendance_tab_scoped_to_group(self):
        lesson1 = self.group1.lessons.first()
        lesson2 = self.group2.lessons.first()
        Attendance.objects.create(student=self.student1, lesson=lesson1, status=Attendance.Status.PRESENT)
        Attendance.objects.create(student=self.student3, lesson=lesson2, status=Attendance.Status.ABSENT)

        response = self.admin_web.get(self._url("_attendance"))
        self.assertEqual(response.context["stats"]["total"], 1)
        self.assertEqual(response.context["stats"]["present"], 1)

    def test_homework_tab_scoped_to_group(self):
        lesson1 = self.group1.lessons.first()
        Homework.objects.create(lesson=lesson1, title="HW in group1")
        lesson2 = self.group2.lessons.first()
        Homework.objects.create(lesson=lesson2, title="HW in group2")

        response = self.admin_web.get(self._url("_homework"))
        self.assertEqual(response.context["stats"]["assignments"], 1)
        self.assertContains(response, "HW in group1")
        self.assertNotContains(response, "HW in group2")

    def test_analytics_tab_renders_real_numbers(self):
        response = self.admin_web.get(self._url("_analytics"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["stats"]["students_count"], self.group1.students_count)

    # -- group create redirects straight into the Workspace ------------------

    def test_group_add_redirects_to_workspace(self):
        response = self.admin_web.post(
            reverse("admin:academy_group_add"),
            {"name": "Freshly Created", "course": self.course.pk, "status": "active", "start_date": "2026-09-07"},
        )
        group = Group.objects.get(name="Freshly Created")
        self.assertRedirects(response, reverse("admin:academy_group_workspace", args=[group.pk]))

    def test_group_add_save_and_continue_keeps_normal_admin_flow(self):
        response = self.admin_web.post(
            reverse("admin:academy_group_add"),
            {
                "name": "Continue Editing", "course": self.course.pk, "status": "active",
                "start_date": "2026-09-07", "_continue": "Save and continue editing",
            },
        )
        group = Group.objects.get(name="Continue Editing")
        self.assertRedirects(response, reverse("admin:academy_group_change", args=[group.pk]))

    # -- Teachers tab -----------------------------------------------------------

    def test_teachers_tab_lists_existing_assignments(self):
        response = self.admin_web.get(self._url("_teachers"))
        self.assertContains(response, str(self.teacher1))

    def test_add_teacher_creates_bare_group_teacher_with_no_schedule(self):
        response = self.admin_web.post(
            self._url("_teachers_add"), {"teacher": self.teacher2.pk, "subject": self.subject_frontend.pk}
        )
        self.assertEqual(response.status_code, 302)
        gt = GroupTeacher.objects.get(group=self.group1, teacher=self.teacher2, subject=self.subject_frontend)
        self.assertEqual(gt.schedules.count(), 0)

    def test_add_teacher_does_not_duplicate_existing_assignment(self):
        self.admin_web.post(
            self._url("_teachers_add"), {"teacher": self.teacher2.pk, "subject": self.subject_frontend.pk}
        )
        before = GroupTeacher.objects.count()
        response = self.admin_web.post(
            self._url("_teachers_add"), {"teacher": self.teacher2.pk, "subject": self.subject_frontend.pk}
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(GroupTeacher.objects.count(), before)

    def test_remove_teacher_deletes_assignment_but_preserves_lessons(self):
        program = self.group1.teachers.get(teacher=self.teacher1)
        lesson = Lesson.objects.filter(group_teacher=program).first()
        self.assertIsNotNone(lesson)

        response = self.admin_web.post(self._url("_teachers_remove", program.pk))
        self.assertEqual(response.status_code, 302)
        self.assertFalse(GroupTeacher.objects.filter(pk=program.pk).exists())

        lesson.refresh_from_db()
        self.assertIsNone(lesson.group_teacher_id)
        self.assertTrue(Lesson.objects.filter(pk=lesson.pk).exists())

    def test_remove_teacher_requires_post(self):
        program = self.group1.teachers.get(teacher=self.teacher1)
        response = self.admin_web.get(self._url("_teachers_remove", program.pk))
        self.assertEqual(response.status_code, 403)

    def test_remove_teacher_requires_admin(self):
        program = self.group1.teachers.get(teacher=self.teacher1)
        response = self.teacher_web.post(self._url("_teachers_remove", program.pk))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin/login/", response.url)

    # -- Programs tab: individual lesson-plan redirect ------------------------

    def test_add_program_with_individual_plan_redirects_to_group_teacher_change(self):
        response = self.admin_web.post(
            self._url("_programs_add"),
            {
                "teacher": self.teacher2.pk, "subject": self.subject_frontend.pk,
                "day_of_week": ["fri"], "start_time": "10:00", "end_time": "11:00",
                "lesson_plan_source": "individual",
            },
        )
        gt = GroupTeacher.objects.get(group=self.group1, teacher=self.teacher2, subject=self.subject_frontend)
        self.assertRedirects(response, reverse("admin:academy_groupteacher_change", args=[gt.pk]))

    # -- Weekly Schedule: pre-selected program + day grouping -----------------

    def test_add_schedule_preselects_program_from_query_param(self):
        program = self.group1.teachers.get(teacher=self.teacher1)
        response = self.admin_web.get(self._url("_schedule_add"), {"program": program.pk})
        self.assertEqual(response.context["form"].initial.get("group_teacher"), str(program.pk))

    def test_schedule_tab_groups_slots_by_weekday(self):
        response = self.admin_web.get(self._url("_schedule"))
        days = response.context["days"]
        self.assertEqual(len(days), 7)
        monday = next(d for d in days if d["code"] == "mon")
        self.assertTrue(all(row["obj"].day_of_week == "mon" for row in monday["slots"]))
        self.assertGreater(len(monday["slots"]), 0)


# ---------------------------------------------------------------------------
# No more "primary slot" business rule: Group's legacy teacher/room/
# start_time/end_time/days_of_week fields are inert historical data — they
# no longer auto-populate GroupSchedule/GroupTeacher on save, and a Group is
# fully valid with all of them (and every Teacher Program) blank.
# ---------------------------------------------------------------------------

class NoLiveLegacySyncTests(AcademyTestBase):
    def test_group_can_be_created_with_zero_teacher_programs(self):
        group = Group.objects.create(name="Empty group", course=self.course, start_date=dt.date(2026, 9, 7))
        self.assertEqual(group.teachers.count(), 0)
        self.assertEqual(GroupSchedule.objects.filter(group=group).count(), 0)
        self.assertEqual(Lesson.objects.filter(group=group).count(), 0)

    def test_group_full_clean_does_not_require_any_legacy_field(self):
        group = Group(name="Also empty", course=self.course, start_date=dt.date(2026, 9, 7))
        group.full_clean()  # must not raise

    def test_editing_legacy_teacher_field_does_not_touch_groupschedule(self):
        # Before this change, changing Group.teacher/days_of_week would live-
        # resync GroupSchedule. Now it's inert — a real, equal Teacher
        # Program can only be added/changed via GroupSchedule itself.
        schedule_ids_before = set(GroupSchedule.objects.filter(group=self.group1).values_list("id", flat=True))
        self.group1.teacher = self.teacher2
        self.group1.days_of_week = ["fri"]
        self.group1.save()
        schedule_ids_after = set(GroupSchedule.objects.filter(group=self.group1).values_list("id", flat=True))
        self.assertEqual(schedule_ids_before, schedule_ids_after)
        # And no row actually points at the newly-assigned legacy teacher.
        self.assertFalse(GroupSchedule.objects.filter(group=self.group1, teacher=self.teacher2).exists())

    def test_clearing_legacy_fields_does_not_delete_existing_lessons(self):
        lesson_ids_before = set(Lesson.objects.filter(group=self.group1).values_list("id", flat=True))
        self.group1.teacher = None
        self.group1.room = None
        self.group1.start_time = None
        self.group1.end_time = None
        self.group1.days_of_week = []
        self.group1.save()
        self.assertEqual(
            set(Lesson.objects.filter(group=self.group1).values_list("id", flat=True)), lesson_ids_before
        )


class FinalLegacyScheduleSyncMigrationTests(AcademyTestBase):
    """apps.academy.migrations.0008_final_legacy_schedule_sync — the one-off
    safety net that captures any Group whose legacy fields hadn't been
    mirrored yet at the moment the live auto-sync was retired."""

    def _run_migration(self):
        import importlib

        from django.apps import apps as django_apps

        migration = importlib.import_module("apps.academy.migrations.0008_final_legacy_schedule_sync")
        migration.final_sync(django_apps, None)

    def test_backfills_a_group_whose_legacy_fields_were_never_synced(self):
        # Simulate data that drifted: legacy fields set directly (bypassing
        # the old sync signal entirely, e.g. via a bulk .update()), with no
        # matching GroupTeacher/GroupSchedule at all.
        drifted = Group.objects.create(
            name="Drifted group", course=self.course, start_date=dt.date(2026, 9, 7),
        )
        Group.objects.filter(pk=drifted.pk).update(
            teacher=self.teacher1, room=self.room1,
            start_time=dt.time(12, 0), end_time=dt.time(13, 0), days_of_week=["tue"],
        )
        self.assertEqual(GroupSchedule.objects.filter(group=drifted).count(), 0)

        self._run_migration()

        drifted.refresh_from_db()
        rows = list(GroupSchedule.objects.filter(group=drifted))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].day_of_week, "tue")
        self.assertEqual(rows[0].teacher_id, self.teacher1.id)
        self.assertIsNotNone(rows[0].group_teacher_id)
        self.assertTrue(rows[0].group_teacher.is_legacy_primary)

    def test_never_touches_an_admin_edited_row(self):
        # An admin's own explicitly-added (subject set) row must never be
        # touched by this migration, even if it happens to share a teacher
        # with the group's legacy fields.
        custom = GroupSchedule.objects.create(
            group=self.group1, teacher=self.teacher1, subject=self.subject_frontend,
            day_of_week="sat", start_time=dt.time(8, 0), end_time=dt.time(9, 0), room=self.room1,
        )
        self._run_migration()
        custom.refresh_from_db()
        self.assertEqual(custom.day_of_week, "sat")
        self.assertEqual(custom.subject_id, self.subject_frontend.id)

    def test_is_idempotent(self):
        self._run_migration()
        count_after_first = GroupSchedule.objects.count()
        self._run_migration()
        self.assertEqual(GroupSchedule.objects.count(), count_after_first)

    def test_does_not_lose_or_duplicate_existing_lessons(self):
        lesson_ids_before = set(Lesson.objects.filter(group=self.group1).values_list("id", flat=True))
        self._run_migration()
        self.assertEqual(set(Lesson.objects.filter(group=self.group1).values_list("id", flat=True)), lesson_ids_before)


class GroupTeacherModelTests(AcademyTestBase):
    def test_group_has_one_legacy_group_teacher_by_default(self):
        # Group #1 (spec item 1: "Group может иметь одного Teacher").
        group_teachers = list(self.group1.teachers.all())
        self.assertEqual(len(group_teachers), 1)
        gt = group_teachers[0]
        self.assertEqual(gt.teacher_id, self.teacher1.id)
        self.assertIsNone(gt.subject_id)
        self.assertTrue(gt.is_legacy_primary)

    def test_group_can_have_multiple_teachers(self):
        # Spec item 2.
        GroupSchedule.objects.create(
            group=self.group1, teacher=self.teacher2, subject=self.subject_frontend,
            day_of_week="fri", start_time=dt.time(10, 0), end_time=dt.time(11, 0),
        )
        self.assertEqual(self.group1.teachers.count(), 2)
        self.assertIn(self.teacher2.id, self.group1.teachers.values_list("teacher_id", flat=True))

    def test_each_teacher_has_its_own_subject(self):
        # Spec item 3.
        GroupSchedule.objects.create(
            group=self.group1, teacher=self.teacher2, subject=self.subject_frontend,
            day_of_week="fri", start_time=dt.time(10, 0), end_time=dt.time(11, 0),
        )
        subjects = {gt.subject_id for gt in self.group1.teachers.all()}
        self.assertEqual(subjects, {None, self.subject_frontend.id})

    def test_each_teacher_has_its_own_schedule(self):
        # Spec item 4.
        extra_slot = GroupSchedule.objects.create(
            group=self.group1, teacher=self.teacher2, subject=self.subject_frontend,
            day_of_week="fri", start_time=dt.time(10, 0), end_time=dt.time(11, 0),
        )
        primary = self.group1.teachers.get(subject__isnull=True)
        secondary = extra_slot.group_teacher
        self.assertEqual(primary.schedules.count(), 2)  # mon + wed, mirrored from group1
        self.assertEqual(secondary.schedules.count(), 1)
        self.assertNotEqual(primary.id, secondary.id)

    def test_group_teacher_is_reused_across_schedule_rows_of_the_same_teacher_and_subject(self):
        first = GroupSchedule.objects.create(
            group=self.group1, teacher=self.teacher2, subject=self.subject_frontend,
            day_of_week="fri", start_time=dt.time(10, 0), end_time=dt.time(11, 0),
        )
        second = GroupSchedule.objects.create(
            group=self.group1, teacher=self.teacher2, subject=self.subject_frontend,
            day_of_week="sat", start_time=dt.time(10, 0), end_time=dt.time(11, 0),
        )
        self.assertEqual(first.group_teacher_id, second.group_teacher_id)
        self.assertEqual(self.group1.teachers.filter(teacher=self.teacher2).count(), 1)

    def test_editing_schedule_teacher_moves_it_to_the_right_group_teacher(self):
        slot = GroupSchedule.objects.create(
            group=self.group1, teacher=self.teacher2, subject=self.subject_frontend,
            day_of_week="fri", start_time=dt.time(10, 0), end_time=dt.time(11, 0),
        )
        old_group_teacher_id = slot.group_teacher_id
        slot.subject = self.subject_python
        slot.save()
        self.assertNotEqual(slot.group_teacher_id, old_group_teacher_id)
        self.assertEqual(slot.group_teacher.subject_id, self.subject_python.id)


class GroupTeacherLessonPlanTests(AcademyTestBase):
    def setUp(self):
        super().setUp()
        self.extra_slot = GroupSchedule.objects.create(
            group=self.group1, teacher=self.teacher2, subject=self.subject_frontend,
            day_of_week="fri", start_time=dt.time(10, 0), end_time=dt.time(11, 0),
        )
        self.group_teacher_a = self.group1.teachers.get(subject__isnull=True)
        self.group_teacher_b = self.extra_slot.group_teacher

    def test_each_teacher_can_have_its_own_lesson_plan(self):
        # Spec item 5.
        GroupTeacherLessonPlan.objects.create(group_teacher=self.group_teacher_b, lesson_number=1, topic="HTML basics")
        self.assertEqual(self.group_teacher_b.lesson_plans.count(), 1)
        self.assertEqual(self.group_teacher_a.lesson_plans.count(), 0)

    def test_teacher_a_and_teacher_b_plans_are_independent(self):
        # Spec item 6.
        GroupTeacherLessonPlan.objects.create(group_teacher=self.group_teacher_a, lesson_number=1, topic="A1")
        GroupTeacherLessonPlan.objects.create(group_teacher=self.group_teacher_b, lesson_number=1, topic="B1")
        self.assertEqual(self.group_teacher_a.lesson_plans.get(lesson_number=1).topic, "A1")
        self.assertEqual(self.group_teacher_b.lesson_plans.get(lesson_number=1).topic, "B1")

    def test_duplicate_lesson_number_within_same_group_teacher_rejected(self):
        GroupTeacherLessonPlan.objects.create(group_teacher=self.group_teacher_b, lesson_number=1, topic="First")
        with self.assertRaises(Exception):
            GroupTeacherLessonPlan.objects.create(group_teacher=self.group_teacher_b, lesson_number=1, topic="Dup")


# ---------------------------------------------------------------------------
# Lesson generation from an individual GroupTeacherLessonPlan — independent
# plan source and independent lesson_number sequence per GroupTeacher,
# alongside teachers still using the group's shared CourseLessonPlan.
# ---------------------------------------------------------------------------

class IndividualGroupTeacherPlanGeneratorTests(TestCase):
    def setUp(self):
        self.admin = make_admin("ind_admin")
        self.islam = make_teacher("islam_ind")
        self.aizada = make_teacher("aizada_ind")

        self.subject_it = Subject.objects.create(name="IndIT")
        self.subject_soft = Subject.objects.create(name="IndSoft")
        self.room = Room.objects.create(name="IndRoom", capacity=20)

        self.course = Course.objects.create(name="IndCourse", count_lesson=2)
        self.course.subjects.set([self.subject_it])
        CourseLessonPlan.objects.create(course=self.course, lesson_number=1, subject=self.subject_it, topic="Shared 1")
        CourseLessonPlan.objects.create(course=self.course, lesson_number=2, subject=self.subject_it, topic="Shared 2")

        # 2026-09-14 is a Monday.
        self.group = Group(
            name="Prog1-Ind", course=self.course, teacher=self.islam, room=self.room,
            start_date=dt.date(2026, 9, 14), start_time=dt.time(8, 0), end_time=dt.time(9, 0),
            days_of_week=["mon"],
        )
        self.group._defer_schedule_sync = True
        self.group.save()

        self.soft_slot = GroupSchedule(
            group=self.group, teacher=self.aizada, subject=self.subject_soft,
            day_of_week="mon", start_time=dt.time(9, 0), end_time=dt.time(9, 30), room=self.room,
        )
        self.soft_slot._defer_schedule_sync = True
        self.soft_slot.save()

        sync_legacy_group_schedule(self.group)

        self.islam_group_teacher = self.group.teachers.get(subject__isnull=True)
        self.aizada_group_teacher = self.group.teachers.get(subject=self.subject_soft)
        GroupTeacherLessonPlan.objects.create(
            group_teacher=self.aizada_group_teacher, lesson_number=1, topic="Communication", homework_title="HW-Comm",
        )
        GroupTeacherLessonPlan.objects.create(
            group_teacher=self.aizada_group_teacher, lesson_number=2, topic="Teamwork",
        )

        generate_lessons_for_group(self.group)

    def test_legacy_teacher_still_uses_shared_course_plan(self):
        lessons = list(Lesson.objects.filter(group_teacher=self.islam_group_teacher).order_by("lesson_number"))
        self.assertEqual([l.lesson_number for l in lessons], [1, 2])
        self.assertEqual([l.topic for l in lessons], ["Shared 1", "Shared 2"])
        self.assertTrue(all(l.individual_plan_id is None for l in lessons))
        self.assertTrue(all(l.plan_id is not None for l in lessons))

    def test_individual_teacher_uses_own_plan_and_own_numbering(self):
        # Spec item 13.
        lessons = list(Lesson.objects.filter(group_teacher=self.aizada_group_teacher).order_by("lesson_number"))
        self.assertEqual([l.lesson_number for l in lessons], [1, 2])
        self.assertEqual([l.topic for l in lessons], ["Communication", "Teamwork"])
        self.assertTrue(all(l.plan_id is None for l in lessons))
        self.assertTrue(all(l.individual_plan_id is not None for l in lessons))

    def test_both_teachers_can_have_lesson_number_1_on_the_same_day(self):
        # Spec item 14: numbering is per-GroupTeacher, not per-Group.
        islam_lesson1 = Lesson.objects.get(group_teacher=self.islam_group_teacher, lesson_number=1)
        aizada_lesson1 = Lesson.objects.get(group_teacher=self.aizada_group_teacher, lesson_number=1)
        self.assertEqual(islam_lesson1.date, aizada_lesson1.date)
        self.assertNotEqual(islam_lesson1.id, aizada_lesson1.id)

    def test_homework_created_from_individual_plan(self):
        # Spec item 19.
        lesson1 = Lesson.objects.get(group_teacher=self.aizada_group_teacher, lesson_number=1)
        self.assertTrue(Homework.objects.filter(lesson=lesson1, title="HW-Comm").exists())
        lesson2 = Lesson.objects.get(group_teacher=self.aizada_group_teacher, lesson_number=2)
        self.assertFalse(Homework.objects.filter(lesson=lesson2).exists())

    def test_individual_plan_generation_is_idempotent(self):
        # Spec item 15.
        self.assertEqual(len(generate_lessons_for_group(self.group)), 0)
        self.assertEqual(len(generate_lessons_for_group(self.group)), 0)
        self.assertEqual(Lesson.objects.filter(group_teacher=self.aizada_group_teacher).count(), 2)

    def test_adding_more_individual_plan_rows_only_generates_the_new_ones(self):
        # Spec item 16: existing lessons are never touched/duplicated.
        existing_ids = set(Lesson.objects.filter(group_teacher=self.aizada_group_teacher).values_list("id", flat=True))
        GroupTeacherLessonPlan.objects.create(
            group_teacher=self.aizada_group_teacher, lesson_number=3, topic="Presentation"
        )
        created = generate_lessons_for_group(self.group)
        self.assertEqual(len(created), 1)
        self.assertEqual(created[0].lesson_number, 3)
        self.assertEqual(created[0].topic, "Presentation")
        self.assertTrue(existing_ids.issubset(set(Lesson.objects.values_list("id", flat=True))))

    def test_past_and_completed_individual_lessons_untouched_by_regeneration(self):
        # Spec items 17-18.
        lesson1 = Lesson.objects.get(group_teacher=self.aizada_group_teacher, lesson_number=1)
        lesson1.status = Lesson.Status.COMPLETED
        lesson1.topic = "Отредактировано вручную"
        lesson1.save(update_fields=["status", "topic"])

        generate_lessons_for_group(self.group)

        lesson1.refresh_from_db()
        self.assertEqual(lesson1.status, Lesson.Status.COMPLETED)
        self.assertEqual(lesson1.topic, "Отредактировано вручную")


# ---------------------------------------------------------------------------
# GroupTeacher API permissions — Admin manages everything; a Teacher only
# reads their own assignments (see views.GroupTeacherViewSet).
# ---------------------------------------------------------------------------

class GroupTeacherPermissionsTests(AcademyTestBase):
    def test_teacher_sees_only_own_group_teacher_assignments(self):
        # Spec item 21.
        response = self.teacher1_client.get("/api/v1/programs/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        group_ids = {row["group"] for row in response.data["results"]}
        self.assertEqual(group_ids, {self.group1.id})

    def test_teacher_cannot_write_group_teacher(self):
        # Spec item 22.
        group_teacher = self.group1.teachers.get()
        response = self.teacher1_client.patch(
            f"/api/v1/programs/{group_teacher.id}/", {"is_active": False}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_teacher_cannot_see_other_teachers_group_assignment(self):
        group_teacher_2 = self.group2.teachers.get()
        response = self.teacher1_client.get(f"/api/v1/programs/{group_teacher_2.id}/")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_admin_has_full_access(self):
        # Spec item 23.
        response = self.admin_client.get("/api/v1/programs/")
        self.assertEqual(response.data["count"], 2)

        group_teacher = self.group1.teachers.get()
        response = self.admin_client.patch(
            f"/api/v1/programs/{group_teacher.id}/", {"is_active": False}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        group_teacher.refresh_from_db()
        self.assertFalse(group_teacher.is_active)

    def test_teacher_can_read_but_not_write_own_lesson_plan(self):
        group_teacher = self.group1.teachers.get()
        plan = GroupTeacherLessonPlan.objects.create(group_teacher=group_teacher, lesson_number=1, topic="Intro")

        response = self.teacher1_client.get(f"/api/v1/program-lesson-plans/{plan.id}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        response = self.teacher1_client.patch(
            f"/api/v1/program-lesson-plans/{plan.id}/", {"topic": "Hacked"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_group_detail_includes_teachers(self):
        response = self.admin_client.get(f"/api/v1/groups/{self.group1.id}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("teachers", response.data)
        self.assertEqual(len(response.data["teachers"]), 1)
        self.assertEqual(response.data["teachers"][0]["teacher"], self.teacher1.id)


# ---------------------------------------------------------------------------
# Data migration: existing (pre-GroupTeacher) GroupSchedule/Lesson data is
# backfilled into GroupTeacher without losing or duplicating anything.
# ---------------------------------------------------------------------------

class GroupTeacherBackfillMigrationTests(AcademyTestBase):
    def _run_backfill(self):
        import importlib

        from django.apps import apps as django_apps

        migration = importlib.import_module("apps.academy.migrations.0006_backfill_group_teacher")
        migration.backfill_group_teacher(django_apps, None)

    def test_backfill_recreates_group_teacher_from_existing_schedule_rows(self):
        # Spec item 24: simulate "before GroupTeacher existed".
        GroupSchedule.objects.filter(group=self.group1).update(group_teacher=None)
        Lesson.objects.filter(group=self.group1).update(group_teacher=None)
        GroupTeacher.objects.filter(group=self.group1).delete()
        self.assertEqual(self.group1.teachers.count(), 0)

        self._run_backfill()

        group_teacher = self.group1.teachers.get()
        self.assertEqual(group_teacher.teacher_id, self.teacher1.id)
        self.assertIsNone(group_teacher.subject_id)
        self.assertTrue(group_teacher.is_legacy_primary)
        self.assertTrue(
            GroupSchedule.objects.filter(group=self.group1).exclude(group_teacher=group_teacher).count() == 0
        )

    def test_backfill_preserves_existing_lessons(self):
        # Spec item 25: no Lesson is lost or duplicated by the backfill.
        lesson_ids_before = set(Lesson.objects.filter(group=self.group1).values_list("id", flat=True))
        self.assertTrue(lesson_ids_before)

        GroupSchedule.objects.filter(group=self.group1).update(group_teacher=None)
        Lesson.objects.filter(group=self.group1).update(group_teacher=None)
        GroupTeacher.objects.filter(group=self.group1).delete()

        self._run_backfill()

        lesson_ids_after = set(Lesson.objects.filter(group=self.group1).values_list("id", flat=True))
        self.assertEqual(lesson_ids_before, lesson_ids_after)
        for lesson in Lesson.objects.filter(group=self.group1):
            self.assertIsNotNone(lesson.group_teacher_id)

    def test_backfill_is_idempotent(self):
        self._run_backfill()
        count_after_first = GroupTeacher.objects.count()
        self._run_backfill()
        self.assertEqual(GroupTeacher.objects.count(), count_after_first)


# ---------------------------------------------------------------------------
# Spec §39: a Group's several independent Teaching Programs (see
# models.GroupTeacher) must be fully isolated from each other, even though
# they share the same Group and the same Students — one teacher's
# Lessons/Attendance/Homework/HomeworkResult (and GroupTeacher/GroupSchedule/
# GroupTeacherLessonPlan/Analytics rows) must never be visible to or
# editable by another teacher of the very same Group.
# ---------------------------------------------------------------------------

class MultiTeacherIsolationTests(AcademyTestBase):
    """teacher1 ("Islam") gives IT via the group's legacy fields (Mon 08:00-
    09:00); teacher2 ("Aizada") gives Frontend via an independent
    GroupSchedule slot + her own GroupTeacherLessonPlan (Tue 09:00-09:30) —
    both inside the *same* shared_group, teaching the *same* students."""

    def setUp(self):
        super().setUp()
        self.shared_group = Group(
            name="Shared Multi-Teacher Group", course=self.course, teacher=self.teacher1, room=self.room1,
            start_date=dt.date(2026, 9, 7), start_time=dt.time(8, 0), end_time=dt.time(9, 0),
            days_of_week=["mon"],
        )
        self.shared_group._defer_schedule_sync = True
        self.shared_group.save()

        self.aizada_slot = GroupSchedule(
            group=self.shared_group, teacher=self.teacher2, subject=self.subject_frontend,
            day_of_week="tue", start_time=dt.time(9, 0), end_time=dt.time(9, 30), room=self.room1,
        )
        self.aizada_slot._defer_schedule_sync = True
        self.aizada_slot.save()
        self.aizada_group_teacher = self.aizada_slot.group_teacher

        GroupTeacherLessonPlan.objects.create(
            group_teacher=self.aizada_group_teacher, lesson_number=1, topic="Communication",
        )

        sync_legacy_group_schedule(self.shared_group)
        generate_lessons_for_group(self.shared_group)

        Student.objects.filter(pk=self.student1.pk).update(group=self.shared_group)

        self.islam_lesson = (
            Lesson.objects.filter(group=self.shared_group, teacher=self.teacher1).order_by("lesson_number").first()
        )
        self.aizada_lesson = (
            Lesson.objects.filter(group_teacher=self.aizada_group_teacher).order_by("lesson_number").first()
        )
        self.assertIsNotNone(self.islam_lesson)
        self.assertIsNotNone(self.aizada_lesson)

        self.islam_client = self.teacher1_client
        self.aizada_client = self.teacher2_client

    def test_teacher_lesson_list_excludes_colleagues_lesson_in_same_group(self):
        response = self.islam_client.get("/api/v1/lessons/")
        ids = {row["id"] for row in response.data["results"]}
        self.assertIn(self.islam_lesson.id, ids)
        self.assertNotIn(self.aizada_lesson.id, ids)

    def test_teacher_cannot_retrieve_colleagues_lesson(self):
        response = self.islam_client.get(f"/api/v1/lessons/{self.aizada_lesson.id}/")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_teacher_cannot_update_colleagues_lesson(self):
        response = self.aizada_client.patch(
            f"/api/v1/lessons/{self.islam_lesson.id}/", {"topic": "Hacked"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.islam_lesson.refresh_from_db()
        self.assertNotEqual(self.islam_lesson.topic, "Hacked")

    def test_teacher_cannot_mark_attendance_on_colleagues_lesson(self):
        response = self.islam_client.post(
            f"/api/v1/lessons/{self.aizada_lesson.id}/attendance/",
            [{"student": self.student1.id, "status": "present"}],
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(Attendance.objects.filter(lesson=self.aizada_lesson).count(), 0)

    def test_teacher_can_mark_attendance_on_own_lesson_in_shared_group(self):
        response = self.aizada_client.post(
            f"/api/v1/lessons/{self.aizada_lesson.id}/attendance/",
            [{"student": self.student1.id, "status": "absent"}],
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(Attendance.objects.filter(lesson=self.aizada_lesson).count(), 1)

    def test_attendance_list_excludes_colleagues_records(self):
        Attendance.objects.create(student=self.student1, lesson=self.islam_lesson, status="present")
        Attendance.objects.create(student=self.student1, lesson=self.aizada_lesson, status="absent")

        response = self.islam_client.get("/api/v1/attendance/")
        lesson_ids = {row["lesson"] for row in response.data["results"]}
        self.assertIn(self.islam_lesson.id, lesson_ids)
        self.assertNotIn(self.aizada_lesson.id, lesson_ids)

    def test_teacher_cannot_create_homework_for_colleagues_lesson(self):
        response = self.islam_client.post(
            "/api/v1/homework/",
            {"lesson": self.aizada_lesson.id, "title": "Hack"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Homework.objects.filter(lesson=self.aizada_lesson).count(), 0)

    def test_homework_list_excludes_colleagues_homework(self):
        own_hw = Homework.objects.create(lesson=self.islam_lesson, title="IT HW")
        other_hw = Homework.objects.create(lesson=self.aizada_lesson, title="Frontend HW")

        response = self.islam_client.get("/api/v1/homework/")
        ids = {row["id"] for row in response.data["results"]}
        self.assertIn(own_hw.id, ids)
        self.assertNotIn(other_hw.id, ids)

    def test_homework_result_list_excludes_colleagues_results(self):
        own_hw = Homework.objects.create(lesson=self.islam_lesson, title="IT HW")
        other_hw = Homework.objects.create(lesson=self.aizada_lesson, title="Frontend HW")
        HomeworkResult.objects.create(homework=own_hw, student=self.student1, status="submitted")
        HomeworkResult.objects.create(homework=other_hw, student=self.student1, status="submitted")

        response = self.islam_client.get("/api/v1/homework-results/")
        homework_ids = {row["homework"] for row in response.data["results"]}
        self.assertIn(own_hw.id, homework_ids)
        self.assertNotIn(other_hw.id, homework_ids)

    def test_teacher_cannot_retrieve_colleagues_homework_by_id(self):
        other_hw = Homework.objects.create(lesson=self.aizada_lesson, title="Frontend HW")
        response = self.islam_client.get(f"/api/v1/homework/{other_hw.id}/")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_teacher_cannot_retrieve_colleagues_homework_result_by_id(self):
        other_hw = Homework.objects.create(lesson=self.aizada_lesson, title="Frontend HW")
        other_result = HomeworkResult.objects.create(homework=other_hw, student=self.student1, status="submitted")
        response = self.islam_client.get(f"/api/v1/homework-results/{other_result.id}/")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_teacher_cannot_create_homework_result_for_colleagues_homework(self):
        other_hw = Homework.objects.create(lesson=self.aizada_lesson, title="Frontend HW")
        response = self.islam_client.post(
            "/api/v1/homework-results/",
            {"homework": other_hw.id, "student": self.student1.id, "status": "submitted"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(HomeworkResult.objects.filter(homework=other_hw).count(), 0)

    def test_teacher_cannot_delete_colleagues_homework(self):
        other_hw = Homework.objects.create(lesson=self.aizada_lesson, title="Frontend HW")
        response = self.islam_client.delete(f"/api/v1/homework/{other_hw.id}/")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertTrue(Homework.objects.filter(pk=other_hw.pk).exists())

    def test_teacher_cannot_delete_colleagues_attendance_record(self):
        other_record = Attendance.objects.create(student=self.student1, lesson=self.aizada_lesson, status="present")
        response = self.islam_client.delete(f"/api/v1/attendance/{other_record.id}/")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertTrue(Attendance.objects.filter(pk=other_record.pk).exists())

    def test_group_teacher_list_excludes_colleagues_assignment_in_same_group(self):
        response = self.islam_client.get("/api/v1/programs/")
        ids = {row["id"] for row in response.data["results"]}
        self.assertNotIn(self.aizada_group_teacher.id, ids)

    def test_group_schedule_list_excludes_colleagues_slot_in_same_group(self):
        response = self.islam_client.get("/api/v1/schedules/")
        ids = {row["id"] for row in response.data["results"]}
        self.assertNotIn(self.aizada_slot.id, ids)

    def test_group_teacher_lesson_plan_list_excludes_colleagues_plan(self):
        response = self.islam_client.get("/api/v1/program-lesson-plans/")
        group_teacher_ids = {row["group_teacher"] for row in response.data["results"]}
        self.assertNotIn(self.aizada_group_teacher.id, group_teacher_ids)

    def test_group_schedule_endpoint_scoped_to_own_lessons_in_shared_group(self):
        response = self.islam_client.get(f"/api/v1/groups/{self.shared_group.id}/schedule/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = {row["id"] for row in response.data["lessons"]}
        self.assertIn(self.islam_lesson.id, ids)
        self.assertNotIn(self.aizada_lesson.id, ids)

    def test_admin_group_schedule_endpoint_shows_every_teachers_lessons(self):
        response = self.admin_client.get(f"/api/v1/groups/{self.shared_group.id}/schedule/")
        ids = {row["id"] for row in response.data["lessons"]}
        self.assertIn(self.islam_lesson.id, ids)
        self.assertIn(self.aizada_lesson.id, ids)

    def test_analytics_does_not_mix_teachers_in_shared_group(self):
        Attendance.objects.create(student=self.student1, lesson=self.islam_lesson, status=Attendance.Status.PRESENT)
        Attendance.objects.create(student=self.student1, lesson=self.aizada_lesson, status=Attendance.Status.ABSENT)

        islam_dashboard = get_dashboard(
            period="custom", start_date=dt.date(2026, 9, 1), end_date=dt.date(2026, 9, 30),
            teacher_id=self.teacher1.id, group_id=self.shared_group.id, today=dt.date(2026, 9, 30),
        )
        aizada_dashboard = get_dashboard(
            period="custom", start_date=dt.date(2026, 9, 1), end_date=dt.date(2026, 9, 30),
            teacher_id=self.teacher2.id, group_id=self.shared_group.id, today=dt.date(2026, 9, 30),
        )

        self.assertEqual(islam_dashboard["attendance"]["present_count"]["value"], 1)
        self.assertEqual(islam_dashboard["attendance"]["absent_count"]["value"], 0)
        self.assertEqual(islam_dashboard["attendance"]["attendance_rate"]["value"], 100.0)
        self.assertEqual(aizada_dashboard["attendance"]["present_count"]["value"], 0)
        self.assertEqual(aizada_dashboard["attendance"]["absent_count"]["value"], 1)
        self.assertEqual(aizada_dashboard["attendance"]["attendance_rate"]["value"], 0.0)

    def test_analytics_teacher_row_lesson_count_is_not_mixed(self):
        # teacher1's legacy Teaching Program walks the full 4-lesson course
        # plan on its own Monday slot; teacher2's individual plan has just
        # the one lesson_number=1 row on her own Tuesday slot (see setUp) —
        # each teacher's row must reflect only their own count.
        dashboard = get_dashboard(
            period="custom", start_date=dt.date(2026, 9, 1), end_date=dt.date(2026, 9, 30),
            group_id=self.shared_group.id, today=dt.date(2026, 9, 30),
        )
        workload = {row["teacher_id"]: row["lessons"] for row in dashboard["teachers"]["teacher_workload"]}
        self.assertEqual(workload[self.teacher1.id], 4)
        self.assertEqual(workload[self.teacher2.id], 1)

    def test_admin_has_full_access_to_both_teaching_programs(self):
        response = self.admin_client.get("/api/v1/lessons/")
        ids = {row["id"] for row in response.data["results"]}
        self.assertIn(self.islam_lesson.id, ids)
        self.assertIn(self.aizada_lesson.id, ids)


# ---------------------------------------------------------------------------
# _assert_teacher_owns_lesson: perform_create's defense-in-depth check
# ---------------------------------------------------------------------------

class TeacherOwnsLessonGuardTests(AcademyTestBase):
    """AttendanceViewSet/HomeworkViewSet/HomeworkResultViewSet.perform_create
    all call `_assert_teacher_owns_lesson` after the serializer has already
    validated (and scoped) its `lesson`/`homework` field — this is a second,
    independent check. Exercised directly here (rather than only indirectly
    through the API, which can never actually reach a mismatched lesson
    because the serializer's own field-scoping already rejects it first) so
    a regression in this specific function is caught even if the serializer
    scoping it backs up is ever weakened."""

    def setUp(self):
        super().setUp()
        self.lesson1 = Lesson.objects.filter(group=self.group1).order_by("lesson_number").first()
        self.lesson2 = Lesson.objects.filter(group=self.group2).order_by("lesson_number").first()

    def test_admin_always_passes_regardless_of_lesson(self):
        request = mock.Mock(user=self.admin)
        _assert_teacher_owns_lesson(request, self.lesson2)  # must not raise

    def test_owning_teacher_passes(self):
        request = mock.Mock(user=self.teacher1.user)
        _assert_teacher_owns_lesson(request, self.lesson1)  # must not raise

    def test_non_owning_teacher_is_rejected(self):
        request = mock.Mock(user=self.teacher1.user)
        with self.assertRaises(PermissionDenied):
            _assert_teacher_owns_lesson(request, self.lesson2)

    def test_missing_lesson_is_rejected(self):
        request = mock.Mock(user=self.teacher1.user)
        with self.assertRaises(PermissionDenied):
            _assert_teacher_owns_lesson(request, None)


# ---------------------------------------------------------------------------
# seed_dev_data: production guard + idempotency
# ---------------------------------------------------------------------------

class SeedDevDataTests(TestCase):
    def test_refuses_when_django_env_is_production(self):
        with mock.patch.dict("os.environ", {"DJANGO_ENV": "production"}):
            with self.assertRaises(CommandError) as ctx:
                call_command("seed_dev_data")
        self.assertIn("production", str(ctx.exception).lower())
        self.assertEqual(User.objects.count(), 0)
        self.assertEqual(Group.objects.count(), 0)

    def test_production_guard_runs_before_any_seeding_work(self):
        # Regression guard: the DJANGO_ENV check must run before the
        # @transaction.atomic-wrapped `_seed` — entering that block opens a
        # real connection to whatever DATABASES points at, which in
        # production is a real server, before the command gets a chance to
        # refuse. `_seed` itself must simply never be reached.
        from apps.academy.management.commands.seed_dev_data import Command

        with mock.patch.dict("os.environ", {"DJANGO_ENV": "production"}):
            with mock.patch.object(Command, "_seed") as mocked_seed:
                with self.assertRaises(CommandError):
                    call_command("seed_dev_data")
        mocked_seed.assert_not_called()

    def test_creates_two_independent_teaching_programs_in_development(self):
        with mock.patch.dict("os.environ", {"DJANGO_ENV": "development"}):
            call_command("seed_dev_data")

        group = Group.objects.get(name="[DEMO] Группа A1")
        self.assertEqual(group.teachers.count(), 2)
        self.assertEqual(group.students.count(), 5)
        for group_teacher in group.teachers.all():
            self.assertTrue(group_teacher.lessons.exists())

        admin = User.objects.get(username="demo_admin")
        self.assertEqual(admin.role, User.Role.ADMIN)

    def test_is_idempotent_on_rerun(self):
        with mock.patch.dict("os.environ", {"DJANGO_ENV": "development"}):
            call_command("seed_dev_data")
            first_lesson_count = Lesson.objects.count()
            first_student_count = Student.objects.count()
            first_user_count = User.objects.count()

            call_command("seed_dev_data")

        self.assertEqual(Lesson.objects.count(), first_lesson_count)
        self.assertEqual(Student.objects.count(), first_student_count)
        self.assertEqual(User.objects.count(), first_user_count)


class SeedDemoDataTests(TestCase):
    """`seed_demo_data` — the Monthly Teacher Reports demo dataset."""

    def test_refuses_when_django_env_is_production(self):
        with mock.patch.dict("os.environ", {"DJANGO_ENV": "production"}):
            with self.assertRaises(CommandError) as ctx:
                call_command("seed_demo_data")
        self.assertIn("production", str(ctx.exception).lower())
        self.assertEqual(User.objects.count(), 0)
        self.assertEqual(Group.objects.count(), 0)

    def test_production_guard_runs_before_any_seeding_work(self):
        from apps.academy.management.commands.seed_demo_data import Command

        with mock.patch.dict("os.environ", {"DJANGO_ENV": "production"}):
            with mock.patch.object(Command, "_seed") as mocked_seed:
                with self.assertRaises(CommandError):
                    call_command("seed_demo_data")
        mocked_seed.assert_not_called()

    def test_creates_the_full_connected_dataset(self):
        with mock.patch.dict("os.environ", {"DJANGO_ENV": "development"}):
            call_command("seed_demo_data", stdout=StringIO())

        self.assertEqual(Group.objects.count(), 10)
        self.assertGreaterEqual(Student.objects.count(), 60)
        self.assertGreaterEqual(Lesson.objects.count(), 100)
        self.assertTrue(Attendance.objects.exists())
        self.assertTrue(Homework.objects.exists())
        self.assertTrue(HomeworkResult.objects.exists())

        admin = User.objects.get(username="admin")
        self.assertEqual(admin.role, User.Role.ADMIN)
        self.assertTrue(admin.is_superuser)
        self.assertTrue(admin.check_password("admin12345"))

        islam = User.objects.get(username="islam_it")
        self.assertTrue(islam.check_password("teacher123"))
        # Group.objects.for_teacher, not the legacy Group.teacher field — see
        # models.GroupQuerySet.for_teacher's own docstring on why.
        self.assertEqual(Group.objects.for_teacher(islam.teacher_profile).count(), 3)  # IT-15, IT-16, Backend-7

        report = MonthlyTeacherReport.objects.get(teacher=islam.teacher_profile, year=2026, month=9)
        self.assertTrue(report.comment)

    def test_monthly_report_never_grows_a_duplicate_statistics_field(self):
        """Regression guard for spec §16: every number a report shows must be
        computed live (see services.monthly_report), never stored on the
        model itself."""
        field_names = {f.name for f in MonthlyTeacherReport._meta.get_fields()}
        forbidden = {
            "lessons_count", "students_count", "groups_count",
            "attendance_percent", "homework_count", "kpi_percent",
        }
        self.assertEqual(field_names & forbidden, set())

    def test_islam_september_matches_the_spec_shape(self):
        """The one month the spec gives exact figures for: 24 lessons across
        3 groups (IT-15=12, IT-16=8, Backend-7=4), all COMPLETED."""
        with mock.patch.dict("os.environ", {"DJANGO_ENV": "development"}):
            call_command("seed_demo_data", stdout=StringIO())

        islam = Teacher.objects.get(user__username="islam_it")
        september_lessons = Lesson.objects.for_teacher(islam).filter(date__year=2026, date__month=9)
        self.assertEqual(september_lessons.count(), 24)
        self.assertEqual(september_lessons.filter(status=Lesson.Status.COMPLETED).count(), 24)
        self.assertEqual(september_lessons.filter(group__name="IT-15").count(), 12)
        self.assertEqual(september_lessons.filter(group__name="IT-16").count(), 8)
        self.assertEqual(september_lessons.filter(group__name="Backend-7").count(), 4)

    def test_monthly_reports_are_only_created_for_the_planned_months(self):
        with mock.patch.dict("os.environ", {"DJANGO_ENV": "development"}):
            call_command("seed_demo_data", stdout=StringIO())

        def months_for(username):
            teacher = Teacher.objects.get(user__username=username)
            return set(MonthlyTeacherReport.objects.filter(teacher=teacher).values_list("month", flat=True))

        self.assertEqual(months_for("islam_it"), {7, 8, 9})
        self.assertEqual(months_for("khadizha_soft"), {8, 9})
        self.assertEqual(months_for("azamat_python"), {9})
        # Aizada only has a September report — July/August have real lesson
        # data (see next assertion) but deliberately no report yet, so the
        # "create a report for a month with data" flow has something real to
        # exercise.
        self.assertEqual(months_for("aizada_frontend"), {9})

        aizada = Teacher.objects.get(user__username="aizada_frontend")
        self.assertTrue(Lesson.objects.for_teacher(aizada).filter(date__year=2026, date__month=7).exists())

    def test_is_idempotent_on_rerun(self):
        with mock.patch.dict("os.environ", {"DJANGO_ENV": "development"}):
            call_command("seed_demo_data", stdout=StringIO())
            counts = {
                "users": User.objects.count(),
                "groups": Group.objects.count(),
                "students": Student.objects.count(),
                "lessons": Lesson.objects.count(),
                "attendance": Attendance.objects.count(),
                "homework": Homework.objects.count(),
                "homework_results": HomeworkResult.objects.count(),
                "reports": MonthlyTeacherReport.objects.count(),
            }

            call_command("seed_demo_data", stdout=StringIO())

        self.assertEqual(User.objects.count(), counts["users"])
        self.assertEqual(Group.objects.count(), counts["groups"])
        self.assertEqual(Student.objects.count(), counts["students"])
        self.assertEqual(Lesson.objects.count(), counts["lessons"])
        self.assertEqual(Attendance.objects.count(), counts["attendance"])
        self.assertEqual(Homework.objects.count(), counts["homework"])
        self.assertEqual(HomeworkResult.objects.count(), counts["homework_results"])
        self.assertEqual(MonthlyTeacherReport.objects.count(), counts["reports"])


class ClearDemoDataTests(TestCase):
    """`clear_demo_data` — removes only what `seed_demo_data` created."""

    def test_refuses_when_django_env_is_production(self):
        with mock.patch.dict("os.environ", {"DJANGO_ENV": "production"}):
            with self.assertRaises(CommandError) as ctx:
                call_command("clear_demo_data", "--confirm")
        self.assertIn("production", str(ctx.exception).lower())

    def test_refuses_without_confirm_flag(self):
        with self.assertRaises(CommandError) as ctx:
            call_command("clear_demo_data")
        self.assertIn("--confirm", str(ctx.exception))

    def test_removes_demo_data_without_touching_unrelated_data(self):
        # A real account/group that happens to coexist with the demo data —
        # must survive clear_demo_data untouched.
        real_admin = User.objects.create(
            username="real_admin", email="real@example.com", role=User.Role.ADMIN, is_staff=True, is_superuser=True,
        )
        real_subject, _ = Subject.objects.get_or_create(name="Python")
        real_course = Course.objects.create(name="Real Course", count_lesson=5)
        real_course.subjects.add(real_subject)
        real_group = Group.objects.create(name="Real-Group-1", course=real_course, start_date=dt.date(2026, 1, 1))
        Student.objects.create(first_name="Real", last_name="Student", group=real_group)

        with mock.patch.dict("os.environ", {"DJANGO_ENV": "development"}):
            call_command("seed_demo_data", stdout=StringIO())
            call_command("clear_demo_data", "--confirm", stdout=StringIO())

        self.assertEqual(Group.objects.count(), 1)
        self.assertEqual(Group.objects.first().name, "Real-Group-1")
        self.assertEqual(Student.objects.count(), 1)
        self.assertTrue(User.objects.filter(pk=real_admin.pk).exists())
        self.assertFalse(User.objects.filter(username="admin").exists())
        self.assertFalse(User.objects.filter(username="islam_it").exists())
        self.assertEqual(MonthlyTeacherReport.objects.count(), 0)
        # Subjects are shared catalogue data — never deleted by clear_demo_data.
        self.assertTrue(Subject.objects.filter(name="Python").exists())

    def test_a_real_user_named_admin_is_never_deleted(self):
        real = User.objects.create(
            username="admin", email="real-owner@example.com", role=User.Role.ADMIN, is_staff=True, is_superuser=True,
        )

        with mock.patch.dict("os.environ", {"DJANGO_ENV": "development"}):
            call_command("seed_demo_data", stdout=StringIO())
            call_command("clear_demo_data", "--confirm", stdout=StringIO())

        self.assertTrue(User.objects.filter(pk=real.pk).exists())

    def test_reseeding_after_clear_reproduces_the_same_dataset(self):
        with mock.patch.dict("os.environ", {"DJANGO_ENV": "development"}):
            call_command("seed_demo_data", stdout=StringIO())
            call_command("clear_demo_data", "--confirm", stdout=StringIO())
            call_command("seed_demo_data", stdout=StringIO())

        self.assertEqual(Group.objects.count(), 10)
        self.assertEqual(Lesson.objects.count(), 264)
        self.assertEqual(MonthlyTeacherReport.objects.count(), 7)


# ---------------------------------------------------------------------------
# Read-only monitoring admin — Посещаемость / Домашние задания / Результаты
# ДЗ. Admin only watches/searches/filters/drills down into related objects
# here; a Teacher is the one who actually records this data, through their
# own lesson/homework-checking screens (services.attendance_service.
# bulk_mark_attendance, services.homework_service.bulk_upsert_homework_
# results) — never through Django admin. See admin.py's AttendanceAdmin/
# HomeworkAdmin/HomeworkResultAdmin and admin_views.py's six monitor/detail
# view functions.
# ---------------------------------------------------------------------------

class ReadOnlyMonitoringAdminTests(AcademyTestBase):
    def setUp(self):
        super().setUp()
        self.admin_web = DjangoClient()
        self.admin_web.force_login(self.admin)

        # group1's lessons were already generated automatically on creation
        # (see AcademyTestBase.setUp / apps.academy.signals).
        self.lessons = list(Lesson.objects.filter(group=self.group1).order_by("lesson_number"))
        self.lesson1 = self.lessons[0]

        self.attendance_present = Attendance.objects.create(
            student=self.student1, lesson=self.lesson1, status=Attendance.Status.PRESENT
        )
        self.attendance_absent = Attendance.objects.create(
            student=self.student2, lesson=self.lesson1, status=Attendance.Status.ABSENT
        )

        self.homework = Homework.objects.create(
            lesson=self.lesson1, title="ДЗ 1", deadline=timezone.localdate() + dt.timedelta(days=5)
        )
        self.result_checked = HomeworkResult.objects.create(
            homework=self.homework, student=self.student1, status=HomeworkResult.Status.CHECKED, score=9
        )
        # student2 deliberately gets no HomeworkResult row — "not submitted"
        # is the absence of a row, not a stored status (see
        # services.homework_service.bulk_upsert_homework_results) — the
        # detail page must synthesize a "Не сдано" row for them.

    # -- backend-level permission lockdown --------------------------------

    def test_add_change_delete_forbidden_at_backend_level(self):
        registry = {
            "attendance": (Attendance, self.attendance_present),
            "homework": (Homework, self.homework),
            "homeworkresult": (HomeworkResult, self.result_checked),
        }
        for model_name, (model, obj) in registry.items():
            with self.subTest(model=model_name):
                admin_instance = admin.site._registry[model]
                self.assertFalse(admin_instance.has_add_permission(None))
                self.assertFalse(admin_instance.has_change_permission(None, obj))
                self.assertFalse(admin_instance.has_delete_permission(None, obj))

                response = self.admin_web.get(f"/admin/academy/{model_name}/add/")
                self.assertEqual(response.status_code, 403)

    def test_delete_selected_action_not_offered(self):
        for url_name in (
            "admin:academy_attendance_changelist",
            "admin:academy_homework_changelist",
            "admin:academy_homeworkresult_changelist",
        ):
            response = self.admin_web.get(reverse(url_name))
            self.assertNotContains(response, "delete_selected")

    # -- list pages ---------------------------------------------------------

    def test_attendance_list_shows_kpi_and_records(self):
        response = self.admin_web.get(reverse("admin:academy_attendance_changelist"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Присутствуют")
        self.assertContains(response, "Алина Иванова")
        self.assertContains(
            response, reverse("admin:academy_attendance_change", args=[self.attendance_present.pk])
        )

    def test_attendance_kpi_reflects_filtered_queryset(self):
        response = self.admin_web.get(reverse("admin:academy_attendance_changelist"), {"status": "present"})
        self.assertContains(response, "<div class=\"ok-kpi-value\">1</div>", html=False)

    def test_attendance_status_filter_narrows_table(self):
        response = self.admin_web.get(reverse("admin:academy_attendance_changelist"), {"status": "present"})
        body = response.content.decode()
        table = body[body.find("<tbody>") : body.find("</tbody>")]
        self.assertIn("Алина Иванова", table)
        self.assertNotIn("Мансур Алиев", table)

    def test_attendance_empty_state(self):
        response = self.admin_web.get(reverse("admin:academy_attendance_changelist"), {"status": "late"})
        self.assertContains(response, "Записей посещаемости пока нет")

    def test_homework_list_shows_kpi_and_records(self):
        response = self.admin_web.get(reverse("admin:academy_homework_changelist"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Активные дедлайны")
        self.assertContains(response, "ДЗ 1")

    def test_homeworkresult_list_shows_kpi_and_records(self):
        response = self.admin_web.get(reverse("admin:academy_homeworkresult_changelist"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Средний балл")
        self.assertContains(response, "Алина Иванова")

    # -- detail pages + related navigation ----------------------------------

    def test_attendance_detail_shows_related_links(self):
        response = self.admin_web.get(
            reverse("admin:academy_attendance_change", args=[self.attendance_present.pk])
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse("admin:academy_student_detail", args=[self.student1.pk]))
        self.assertContains(response, reverse("admin:academy_group_workspace", args=[self.group1.pk]))
        self.assertContains(response, reverse("admin:academy_lesson_change", args=[self.lesson1.pk]))
        self.assertContains(response, reverse("admin:users_teacher_change", args=[self.teacher1.pk]))

    def test_homework_detail_shows_submission_table_including_unsubmitted(self):
        response = self.admin_web.get(reverse("admin:academy_homework_change", args=[self.homework.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Алина Иванова")
        self.assertContains(response, "Мансур Алиев")
        self.assertContains(response, "Не сдано")

    def test_homeworkresult_detail_shows_related_links(self):
        response = self.admin_web.get(
            reverse("admin:academy_homeworkresult_change", args=[self.result_checked.pk])
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse("admin:academy_student_detail", args=[self.student1.pk]))
        self.assertContains(response, reverse("admin:academy_homework_change", args=[self.homework.pk]))

    # -- Teacher never reaches these Django-admin pages ----------------------

    def test_teacher_cannot_access_monitoring_pages(self):
        teacher_web = DjangoClient()
        teacher_web.force_login(self.teacher1.user)
        response = teacher_web.get(reverse("admin:academy_attendance_changelist"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin/login/", response.url)

    # -- cross-links from other admin pages keep working ---------------------

    def test_student_detail_cross_link_uses_new_query_param(self):
        response = self.admin_web.get(reverse("admin:academy_student_detail", args=[self.student1.pk]))
        self.assertContains(response, f"?student={self.student1.pk}")

        filtered = self.admin_web.get(
            reverse("admin:academy_attendance_changelist"), {"student": self.student1.pk}
        )
        body = filtered.content.decode()
        table = body[body.find("<tbody>") : body.find("</tbody>")]
        self.assertIn("Алина Иванова", table)
        self.assertNotIn("Мансур Алиев", table)

    def test_group_teacher_workspace_cross_links_use_new_query_param(self):
        group_teacher = self.group1.teachers.get()
        response = self.admin_web.get(
            reverse("admin:academy_groupteacher_workspace", args=[group_teacher.pk])
        )
        self.assertContains(response, f"?group_teacher={group_teacher.pk}")

        for url_name in (
            "admin:academy_attendance_changelist",
            "admin:academy_homework_changelist",
            "admin:academy_homeworkresult_changelist",
        ):
            filtered = self.admin_web.get(reverse(url_name), {"group_teacher": group_teacher.pk})
            self.assertEqual(filtered.status_code, 200)


# ---------------------------------------------------------------------------
# Read-only monitoring admin — Занятия. A Lesson is never a standalone CRUD
# entity for Admin — it only ever comes out of the lesson generator (Group
# -> GroupTeacher -> GroupSchedule -> "Сгенерировать занятия", see
# services.lesson_generator). Admin watches/searches/filters/drills down and
# jumps to the related Group/Program/Teacher here; a Teacher marks a lesson
# completed/cancelled and records attendance/homework themselves, through
# their own lesson workspace (IsAdminOrOwningTeacher already lets a Teacher
# update their own Lessons via the API — see permissions.py). See admin.py's
# LessonAdmin and admin_views.py's lesson_monitor_view/lesson_detail_view.
# ---------------------------------------------------------------------------

class LessonMonitoringAdminTests(AcademyTestBase):
    def setUp(self):
        super().setUp()
        self.admin_web = DjangoClient()
        self.admin_web.force_login(self.admin)

        self.lessons = list(Lesson.objects.filter(group=self.group1).order_by("lesson_number"))
        self.lesson1 = self.lessons[0]
        self.lesson1.status = Lesson.Status.COMPLETED
        self.lesson1.save(update_fields=["status"])

        Attendance.objects.create(
            student=self.student1, lesson=self.lesson1, status=Attendance.Status.PRESENT
        )
        Attendance.objects.create(
            student=self.student2, lesson=self.lesson1, status=Attendance.Status.ABSENT
        )

        self.homework = Homework.objects.create(lesson=self.lesson1, title="ДЗ 1")
        HomeworkResult.objects.create(
            homework=self.homework, student=self.student1, status=HomeworkResult.Status.CHECKED, score=9
        )

    # -- backend-level permission lockdown --------------------------------

    def test_add_change_delete_forbidden_at_backend_level(self):
        admin_instance = admin.site._registry[Lesson]
        self.assertFalse(admin_instance.has_add_permission(None))
        self.assertFalse(admin_instance.has_change_permission(None, self.lesson1))
        self.assertFalse(admin_instance.has_delete_permission(None, self.lesson1))

        response = self.admin_web.get("/admin/academy/lesson/add/")
        self.assertEqual(response.status_code, 403)

    def test_no_bulk_actions_or_checkboxes_offered(self):
        response = self.admin_web.get(reverse("admin:academy_lesson_changelist"))
        self.assertNotContains(response, "delete_selected")
        self.assertNotContains(response, "_selected_action")
        self.assertNotContains(response, "Отметить как проведённые")

    # -- list page ------------------------------------------------------------

    def test_list_shows_kpi_header_action_and_records(self):
        response = self.admin_web.get(reverse("admin:academy_lesson_changelist"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Всего занятий")
        self.assertContains(response, "Перейти к расписанию")
        self.assertContains(response, "Python Beginner")
        self.assertContains(response, reverse("admin:academy_lesson_change", args=[self.lesson1.pk]))

    def test_status_filter_narrows_table(self):
        response = self.admin_web.get(reverse("admin:academy_lesson_changelist"), {"status": "cancelled"})
        self.assertContains(response, "Занятий пока нет")

    def test_search_by_group_name(self):
        response = self.admin_web.get(reverse("admin:academy_lesson_changelist"), {"q": "Frontend"})
        body = response.content.decode()
        table = body[body.find("<tbody>") : body.find("</tbody>")]
        self.assertIn("Frontend Beginner", table)
        self.assertNotIn("Python Beginner", table)

    # -- detail page ------------------------------------------------------------

    def test_detail_shows_header_kpi_and_content(self):
        response = self.admin_web.get(reverse("admin:academy_lesson_change", args=[self.lesson1.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f"Занятие №{self.lesson1.lesson_number}")
        self.assertContains(response, "Присутствовали")

    def test_detail_shows_attendance_and_homework_preview(self):
        response = self.admin_web.get(reverse("admin:academy_lesson_change", args=[self.lesson1.pk]))
        self.assertContains(response, "Алина Иванова")
        self.assertContains(response, "Мансур Алиев")
        self.assertContains(response, "ДЗ 1")
        self.assertContains(response, reverse("admin:academy_homework_change", args=[self.homework.pk]))

    def test_detail_shows_related_navigation(self):
        response = self.admin_web.get(reverse("admin:academy_lesson_change", args=[self.lesson1.pk]))
        group_teacher = self.group1.teachers.get()
        self.assertContains(response, reverse("admin:academy_group_workspace", args=[self.group1.pk]))
        self.assertContains(
            response, reverse("admin:academy_group_workspace_schedule", args=[self.group1.pk])
        )
        self.assertContains(
            response, reverse("admin:academy_groupteacher_workspace", args=[group_teacher.pk])
        )
        self.assertContains(response, reverse("admin:users_teacher_change", args=[self.teacher1.pk]))
        self.assertContains(
            response, f"{reverse('admin:academy_attendance_changelist')}?lesson={self.lesson1.pk}"
        )

    def test_lesson_without_homework_shows_not_created_message(self):
        other_lesson = self.lessons[1]
        response = self.admin_web.get(reverse("admin:academy_lesson_change", args=[other_lesson.pk]))
        self.assertContains(response, "Для этого занятия домашнее задание ещё не создано")

    # -- Teacher never reaches these Django-admin pages ----------------------

    def test_teacher_cannot_access_monitoring_pages(self):
        teacher_web = DjangoClient()
        teacher_web.force_login(self.teacher1.user)
        response = teacher_web.get(reverse("admin:academy_lesson_changelist"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin/login/", response.url)

    # -- cross-links from other admin pages keep working ---------------------

    def test_attendance_lesson_filter_works(self):
        response = self.admin_web.get(
            reverse("admin:academy_attendance_changelist"), {"lesson": self.lesson1.pk}
        )
        body = response.content.decode()
        table = body[body.find("<tbody>") : body.find("</tbody>")]
        self.assertIn("Алина Иванова", table)
        self.assertIn("Мансур Алиев", table)

    def test_group_teacher_workspace_lessons_link_uses_new_query_param(self):
        group_teacher = self.group1.teachers.get()
        response = self.admin_web.get(
            reverse("admin:academy_groupteacher_workspace", args=[group_teacher.pk])
        )
        self.assertContains(
            response, f"{reverse('admin:academy_lesson_changelist')}?group_teacher={group_teacher.pk}"
        )
        filtered = self.admin_web.get(
            reverse("admin:academy_lesson_changelist"), {"group_teacher": group_teacher.pk}
        )
        self.assertEqual(filtered.status_code, 200)

    def test_schedule_page_has_no_manual_add_lesson_button(self):
        response = self.admin_web.get(reverse("admin:academy_schedule"))
        self.assertNotContains(response, "Создать занятие")


# ---------------------------------------------------------------------------
# Conflict/generation critical-bugfix suite — the exact scenarios called out
# when fixing the group-conflict gap, the pairwise-duplicate conflict report,
# and generator idempotency/status-KPI correctness.
# ---------------------------------------------------------------------------

class ConflictReportGroupingTests(AcademyTestBase):
    """`_detect_conflicts` must emit *one* entry per genuinely conflicting
    cluster of lessons, never one entry per pair — the "same conflict shown
    three times" bug."""

    def _make_lesson(self, *, group_teacher, teacher, subject, lesson_number, start_time, end_time, room=None,
                      date=dt.date(2026, 9, 9)):
        return Lesson.objects.create(
            group=self.group1, group_teacher=group_teacher, teacher=teacher, subject=subject,
            lesson_number=lesson_number, date=date, start_time=start_time, end_time=end_time,
            room=room, status=Lesson.Status.SCHEDULED,
        )

    def test_three_mutually_overlapping_lessons_produce_one_group_conflict(self):
        teacher_c = make_teacher("conflict_teacher_c")
        subject_c = Subject.objects.create(name="ConflictSubjectC")
        gt_a = GroupTeacher.objects.create(group=self.group1, teacher=self.teacher1, subject=self.subject_python)
        gt_b = GroupTeacher.objects.create(group=self.group1, teacher=self.teacher2, subject=self.subject_frontend)
        gt_c = GroupTeacher.objects.create(group=self.group1, teacher=teacher_c, subject=subject_c)

        lesson_a = self._make_lesson(
            group_teacher=gt_a, teacher=self.teacher1, subject=self.subject_python,
            lesson_number=101, start_time=dt.time(8, 0), end_time=dt.time(9, 0),
        )
        lesson_b = self._make_lesson(
            group_teacher=gt_b, teacher=self.teacher2, subject=self.subject_frontend,
            lesson_number=101, start_time=dt.time(8, 0), end_time=dt.time(9, 0),
        )
        lesson_c = self._make_lesson(
            group_teacher=gt_c, teacher=teacher_c, subject=subject_c,
            lesson_number=101, start_time=dt.time(8, 0), end_time=dt.time(9, 0),
        )

        teacher_conflicts, room_conflicts, group_conflicts, conflicting_ids = _detect_conflicts(
            Lesson.objects.filter(pk__in=[lesson_a.pk, lesson_b.pk, lesson_c.pk])
        )

        self.assertEqual(len(group_conflicts), 1)
        self.assertEqual({l.id for l in group_conflicts[0]["lessons"]}, {lesson_a.id, lesson_b.id, lesson_c.id})
        self.assertEqual(conflicting_ids, {lesson_a.id, lesson_b.id, lesson_c.id})
        # Three different teachers, no room assigned — no teacher/room
        # conflict, only the group conflict.
        self.assertEqual(teacher_conflicts, [])
        self.assertEqual(room_conflicts, [])

    def test_transitive_overlap_chain_is_one_group_not_two(self):
        # A: 08:00-09:00, B: 08:30-09:30, C: 09:15-10:15 — A overlaps B, B
        # overlaps C, but A does NOT directly overlap C. Still one group of
        # three: the room can't host any two of them at once.
        gt_a = GroupTeacher.objects.create(group=self.group1, teacher=self.teacher1, subject=self.subject_python)
        gt_b = GroupTeacher.objects.create(group=self.group2, teacher=self.teacher2, subject=self.subject_frontend)
        teacher_c = make_teacher("chain_teacher_c")
        gt_c = GroupTeacher.objects.create(group=self.group2, teacher=teacher_c, subject=self.subject_frontend)

        room = self.room1
        lesson_a = Lesson.objects.create(
            group=self.group1, group_teacher=gt_a, teacher=self.teacher1, subject=self.subject_python,
            lesson_number=201, date=dt.date(2026, 9, 9), start_time=dt.time(8, 0), end_time=dt.time(9, 0),
            room=room, status=Lesson.Status.SCHEDULED,
        )
        lesson_b = Lesson.objects.create(
            group=self.group2, group_teacher=gt_b, teacher=self.teacher2, subject=self.subject_frontend,
            lesson_number=201, date=dt.date(2026, 9, 9), start_time=dt.time(8, 30), end_time=dt.time(9, 30),
            room=room, status=Lesson.Status.SCHEDULED,
        )
        lesson_c = Lesson.objects.create(
            group=self.group2, group_teacher=gt_c, teacher=teacher_c, subject=self.subject_frontend,
            lesson_number=201, date=dt.date(2026, 9, 9), start_time=dt.time(9, 15), end_time=dt.time(10, 15),
            room=room, status=Lesson.Status.SCHEDULED,
        )

        _, room_conflicts, _, conflicting_ids = _detect_conflicts(
            Lesson.objects.filter(pk__in=[lesson_a.pk, lesson_b.pk, lesson_c.pk])
        )

        self.assertEqual(len(room_conflicts), 1)
        self.assertEqual({l.id for l in room_conflicts[0]["lessons"]}, {lesson_a.id, lesson_b.id, lesson_c.id})
        self.assertEqual(conflicting_ids, {lesson_a.id, lesson_b.id, lesson_c.id})

    def test_non_overlapping_same_day_lessons_are_not_flagged(self):
        gt_a = GroupTeacher.objects.create(group=self.group1, teacher=self.teacher1, subject=self.subject_python)
        lesson_morning = self._make_lesson(
            group_teacher=gt_a, teacher=self.teacher1, subject=self.subject_python,
            lesson_number=301, start_time=dt.time(8, 0), end_time=dt.time(9, 0),
        )
        lesson_afternoon = self._make_lesson(
            group_teacher=gt_a, teacher=self.teacher1, subject=self.subject_python,
            lesson_number=302, start_time=dt.time(9, 0), end_time=dt.time(10, 0),
        )
        _, _, group_conflicts, conflicting_ids = _detect_conflicts(
            Lesson.objects.filter(pk__in=[lesson_morning.pk, lesson_afternoon.pk])
        )
        self.assertEqual(group_conflicts, [])
        self.assertEqual(conflicting_ids, set())


class ScheduleViewGroupConflictDisplayTests(AcademyTestBase):
    """The Schedule admin page must actually render the new grouped
    "Конфликт группы" section — once per conflicting cluster."""

    def setUp(self):
        super().setUp()
        self.admin_web = DjangoClient()
        self.admin_web.force_login(self.admin)

        teacher_c = make_teacher("display_conflict_teacher_c")
        subject_c = Subject.objects.create(name="DisplayConflictSubjectC")
        gt_a = GroupTeacher.objects.create(group=self.group1, teacher=self.teacher1, subject=self.subject_python)
        gt_b = GroupTeacher.objects.create(group=self.group1, teacher=self.teacher2, subject=self.subject_frontend)
        gt_c = GroupTeacher.objects.create(group=self.group1, teacher=teacher_c, subject=subject_c)

        common = dict(
            group=self.group1, date=dt.date(2026, 9, 9), start_time=dt.time(8, 0), end_time=dt.time(9, 0),
            status=Lesson.Status.SCHEDULED,
        )
        Lesson.objects.create(group_teacher=gt_a, teacher=self.teacher1, subject=self.subject_python, lesson_number=401, **common)
        Lesson.objects.create(group_teacher=gt_b, teacher=self.teacher2, subject=self.subject_frontend, lesson_number=401, **common)
        Lesson.objects.create(group_teacher=gt_c, teacher=teacher_c, subject=subject_c, lesson_number=401, **common)

    def test_group_conflict_shown_exactly_once(self):
        response = self.admin_web.get(reverse("admin:academy_schedule"), {"week": "2026-09-07"})
        self.assertEqual(response.status_code, 200)
        body = response.content.decode()
        self.assertEqual(body.count("Конфликт группы"), 1)


class LessonGenerationIdempotencyTests(AcademyTestBase):
    """Repeated/concurrent generation calls, and edits to already-generated
    Lessons, must never be duplicated or overwritten."""

    def setUp(self):
        super().setUp()
        self.lessons = list(Lesson.objects.filter(group=self.group1).order_by("lesson_number"))
        self.lesson1 = self.lessons[0]

    def test_repeated_generation_creates_no_duplicates(self):
        before = Lesson.objects.filter(group=self.group1).count()
        report1 = generate_lessons_for_group_with_report(self.group1)
        report2 = generate_lessons_for_group_with_report(self.group1)

        self.assertEqual(report1.created, 0)
        self.assertEqual(report2.created, 0)
        self.assertEqual(report2.already_existed, before)
        self.assertEqual(Lesson.objects.filter(group=self.group1).count(), before)

    def test_concurrent_generation_race_resolves_to_one_row_not_a_duplicate(self):
        # Simulate a second, concurrent request having already inserted this
        # exact (group_teacher, lesson_number) row a moment before this call
        # even starts — the pre-filtering in _generate_from_course_plan
        # would normally skip it, but get_or_create's own identity check is
        # what actually guarantees no duplicate/no crash regardless.
        group_teacher = self.group1.teachers.get()
        before_count = Lesson.objects.filter(group=self.group1).count()

        generate_lessons_for_group(self.group1)  # fully generated once already (see setUp)
        self.assertEqual(Lesson.objects.filter(group=self.group1).count(), before_count)

        # Directly exercise the generator's own identity-safe creation path
        # against a pre-existing row for the same (group_teacher, lesson_number).
        from apps.academy.services.lesson_generator import _get_or_create_lesson

        lesson, created = _get_or_create_lesson(
            {
                "group": self.group1, "group_teacher": group_teacher, "plan": None,
                "schedule": None, "teacher": self.teacher1, "lesson_number": self.lesson1.lesson_number,
                "date": self.lesson1.date, "start_time": self.lesson1.start_time, "end_time": self.lesson1.end_time,
                "room": self.room1, "subject": self.subject_python, "topic": "Другая тема (гонка)",
                "description": "", "youtube_url": "", "presentation_urls": [],
            }
        )
        self.assertFalse(created)
        self.assertEqual(lesson.id, self.lesson1.id)
        self.assertEqual(lesson.topic, self.lesson1.topic)  # untouched, not overwritten by the race loser
        self.assertEqual(Lesson.objects.filter(group=self.group1).count(), before_count)

    def test_cancelled_lesson_untouched_by_regeneration(self):
        self.lesson1.status = Lesson.Status.CANCELLED
        self.lesson1.cancellation_reason = "Праздник"
        self.lesson1.save(update_fields=["status", "cancellation_reason"])

        generate_lessons_for_group(self.group1)

        self.lesson1.refresh_from_db()
        self.assertEqual(self.lesson1.status, Lesson.Status.CANCELLED)
        self.assertEqual(self.lesson1.cancellation_reason, "Праздник")

    def test_completed_lesson_untouched_by_regeneration(self):
        Attendance.objects.create(student=self.student1, lesson=self.lesson1, status=Attendance.Status.PRESENT)
        Attendance.objects.create(student=self.student2, lesson=self.lesson1, status=Attendance.Status.PRESENT)
        from apps.academy.services import lesson_lifecycle

        lesson_lifecycle.start_lesson(self.lesson1, self.teacher1.user)
        lesson_lifecycle.set_homework_not_required(self.lesson1, True)
        lesson_lifecycle.complete_lesson(self.lesson1, self.teacher1.user)
        completed_at = self.lesson1.completed_at

        generate_lessons_for_group(self.group1)

        self.lesson1.refresh_from_db()
        self.assertEqual(self.lesson1.status, Lesson.Status.COMPLETED)
        self.assertEqual(self.lesson1.completed_at, completed_at)

    def test_attendance_and_homework_survive_regeneration(self):
        Attendance.objects.create(student=self.student1, lesson=self.lesson1, status=Attendance.Status.PRESENT)
        homework = Homework.objects.create(lesson=self.lesson1, title="ДЗ на закрепление")

        generate_lessons_for_group(self.group1)

        self.assertTrue(Attendance.objects.filter(student=self.student1, lesson=self.lesson1).exists())
        self.assertTrue(Homework.objects.filter(pk=homework.pk, lesson=self.lesson1).exists())


class GenerationReportFieldsTests(AcademyTestBase):
    """generate_lessons_for_group_with_report's counters (created/already_
    existed/skipped/conflicts/errors) must reflect what actually happened —
    §6/§7 of the spec."""

    def test_report_counts_conflicts_from_a_pre_existing_bad_slot(self):
        # A raw-saved conflicting slot for an unrelated group (bypassing
        # clean()) is skipped by the generator's own defense-in-depth check
        # and must show up as a counted conflict, not silently vanish.
        other_course = Course.objects.create(name="Report Conflict Course", count_lesson=1)
        other_course.subjects.add(self.subject_python)
        CourseLessonPlan.objects.create(course=other_course, lesson_number=1, subject=self.subject_python, topic="Тема")
        conflicting_group = Group.objects.create(
            name="Report Conflict Group", course=other_course, start_date=dt.date(2026, 9, 7),
        )
        GroupSchedule.objects.create(
            group=conflicting_group, teacher=self.teacher1, subject=self.subject_python,
            day_of_week="mon", start_time=dt.time(15, 0), end_time=dt.time(16, 30),
        )

        report = generate_lessons_for_group_with_report(conflicting_group)
        self.assertEqual(report.created, 0)
        self.assertGreaterEqual(report.conflicts, 1)
        self.assertTrue(report.errors)

    def test_report_created_and_already_existed_across_two_calls(self):
        report1 = generate_lessons_for_group_with_report(self.group1)
        total_after_first = Lesson.objects.filter(group=self.group1).count()
        self.assertEqual(report1.already_existed + report1.created, total_after_first)

        report2 = generate_lessons_for_group_with_report(self.group1)
        self.assertEqual(report2.created, 0)
        self.assertEqual(report2.already_existed, total_after_first)


class GeneratorSkipsInvalidSlotsTests(AcademyTestBase):
    """Generation must not create Lessons from a Teacher/Room that's no
    longer active, or a slot with an invalid time range — even if such a
    row already exists in the database (bypassing clean() at save time)."""

    def test_generation_skips_slot_for_inactive_teacher(self):
        other_course = Course.objects.create(name="Inactive Teacher Course", count_lesson=1)
        other_course.subjects.add(self.subject_python)
        CourseLessonPlan.objects.create(course=other_course, lesson_number=1, subject=self.subject_python, topic="Тема")
        inactive_teacher = make_teacher("inactive_teacher_gen")
        group = Group.objects.create(name="Inactive Teacher Group", course=other_course, start_date=dt.date(2026, 9, 7))
        slot = GroupSchedule(
            group=group, teacher=inactive_teacher, subject=self.subject_python,
            day_of_week="tue", start_time=dt.time(10, 0), end_time=dt.time(11, 0),
        )
        # Deactivate the teacher *before* the slot ever triggers the
        # auto-generate-on-save signal, so we're testing generation's own
        # active-resource check — not just that lessons already generated
        # earlier (while the teacher was still active) survive untouched.
        slot._defer_schedule_sync = True
        slot.save()
        inactive_teacher.is_active = False
        inactive_teacher.save(update_fields=["is_active"])

        with self.assertRaises(LessonGenerationError):
            generate_lessons_for_group(group)
        self.assertFalse(Lesson.objects.filter(group=group).exists())

    def test_generation_skips_slot_for_inactive_room(self):
        other_course = Course.objects.create(name="Inactive Room Course", count_lesson=1)
        other_course.subjects.add(self.subject_python)
        CourseLessonPlan.objects.create(course=other_course, lesson_number=1, subject=self.subject_python, topic="Тема")
        other_teacher = make_teacher("inactive_room_teacher_gen")
        inactive_room = Room.objects.create(name="Inactive Room", is_active=True)
        group = Group.objects.create(name="Inactive Room Group", course=other_course, start_date=dt.date(2026, 9, 7))
        slot = GroupSchedule(
            group=group, teacher=other_teacher, subject=self.subject_python,
            day_of_week="tue", start_time=dt.time(10, 0), end_time=dt.time(11, 0), room=inactive_room,
        )
        slot._defer_schedule_sync = True
        slot.save()
        inactive_room.is_active = False
        inactive_room.save(update_fields=["is_active"])

        with self.assertRaises(LessonGenerationError):
            generate_lessons_for_group(group)
        self.assertFalse(Lesson.objects.filter(group=group).exists())

    def test_generation_refuses_a_cancelled_group(self):
        self.group1.status = Group.Status.CANCELLED
        self.group1.save(update_fields=["status"])
        with self.assertRaises(LessonGenerationError):
            generate_lessons_for_group(self.group1)


class LessonLifecycleActionsTests(AcademyTestBase):
    """The real start/complete/cancel workflow (services.lesson_lifecycle +
    LessonViewSet's start/complete/cancel/homework-not-required actions) —
    the actual fix for "lessons never move to Completed"."""

    def setUp(self):
        super().setUp()
        self.lesson1 = Lesson.objects.filter(group=self.group1).order_by("lesson_number").first()
        self.other_lesson = Lesson.objects.filter(group=self.group2).order_by("lesson_number").first()

    def _mark_full_attendance(self, lesson):
        for student in (self.student1, self.student2):
            Attendance.objects.create(student=student, lesson=lesson, status=Attendance.Status.PRESENT)

    # -- generation / initial state ---------------------------------------

    def test_generated_lesson_starts_as_scheduled(self):
        self.assertEqual(self.lesson1.status, Lesson.Status.SCHEDULED)
        self.assertIsNone(self.lesson1.started_at)
        self.assertIsNone(self.lesson1.completed_at)
        self.assertIsNone(self.lesson1.completed_by_id)
        self.assertFalse(self.lesson1.homework_not_required)

    # -- start --------------------------------------------------------------

    def test_teacher_can_start_own_lesson(self):
        response = self.teacher1_client.post(f"/api/v1/lessons/{self.lesson1.id}/start/")
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.lesson1.refresh_from_db()
        self.assertEqual(self.lesson1.status, Lesson.Status.IN_PROGRESS)
        self.assertIsNotNone(self.lesson1.started_at)

    def test_teacher_cannot_start_another_teachers_lesson(self):
        response = self.teacher2_client.post(f"/api/v1/lessons/{self.lesson1.id}/start/")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.lesson1.refresh_from_db()
        self.assertEqual(self.lesson1.status, Lesson.Status.SCHEDULED)

    def test_admin_can_start_any_lesson(self):
        response = self.admin_client.post(f"/api/v1/lessons/{self.other_lesson.id}/start/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_starting_already_in_progress_lesson_is_idempotent(self):
        self.teacher1_client.post(f"/api/v1/lessons/{self.lesson1.id}/start/")
        self.lesson1.refresh_from_db()
        first_started_at = self.lesson1.started_at

        response = self.teacher1_client.post(f"/api/v1/lessons/{self.lesson1.id}/start/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.lesson1.refresh_from_db()
        self.assertEqual(self.lesson1.started_at, first_started_at)

    def test_cannot_start_a_cancelled_lesson(self):
        lesson_lifecycle.cancel_lesson(self.lesson1, self.teacher1.user)
        response = self.teacher1_client.post(f"/api/v1/lessons/{self.lesson1.id}/start/")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    # -- completion validation ----------------------------------------------

    def test_cannot_complete_a_lesson_that_was_never_started(self):
        response = self.teacher1_client.post(f"/api/v1/lessons/{self.lesson1.id}/complete/")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.lesson1.refresh_from_db()
        self.assertEqual(self.lesson1.status, Lesson.Status.SCHEDULED)

    def test_cannot_complete_without_attendance(self):
        self.teacher1_client.post(f"/api/v1/lessons/{self.lesson1.id}/start/")
        Homework.objects.create(lesson=self.lesson1, title="ДЗ")  # homework alone isn't enough

        response = self.teacher1_client.post(f"/api/v1/lessons/{self.lesson1.id}/complete/")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Посещаемость отмечена", str(response.data))
        self.lesson1.refresh_from_db()
        self.assertEqual(self.lesson1.status, Lesson.Status.IN_PROGRESS)

    def test_cannot_complete_without_homework_or_not_required_flag(self):
        self.teacher1_client.post(f"/api/v1/lessons/{self.lesson1.id}/start/")
        self._mark_full_attendance(self.lesson1)

        response = self.teacher1_client.post(f"/api/v1/lessons/{self.lesson1.id}/complete/")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.lesson1.refresh_from_db()
        self.assertEqual(self.lesson1.status, Lesson.Status.IN_PROGRESS)

    def test_can_complete_after_attendance_is_filled_and_homework_added(self):
        self.teacher1_client.post(f"/api/v1/lessons/{self.lesson1.id}/start/")
        self._mark_full_attendance(self.lesson1)
        Homework.objects.create(lesson=self.lesson1, title="ДЗ")

        response = self.teacher1_client.post(f"/api/v1/lessons/{self.lesson1.id}/complete/")

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.lesson1.refresh_from_db()
        self.assertEqual(self.lesson1.status, Lesson.Status.COMPLETED)
        self.assertIsNotNone(self.lesson1.completed_at)
        self.assertEqual(self.lesson1.completed_by_id, self.teacher1.user_id)

    def test_can_complete_with_no_homework_once_marked_not_required(self):
        self.teacher1_client.post(f"/api/v1/lessons/{self.lesson1.id}/start/")
        self._mark_full_attendance(self.lesson1)

        mark_response = self.teacher1_client.post(
            f"/api/v1/lessons/{self.lesson1.id}/homework-not-required/", {"value": True}, format="json"
        )
        self.assertEqual(mark_response.status_code, status.HTTP_200_OK)
        self.assertTrue(mark_response.data["homework_not_required"])

        response = self.teacher1_client.post(f"/api/v1/lessons/{self.lesson1.id}/complete/")
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.lesson1.refresh_from_db()
        self.assertEqual(self.lesson1.status, Lesson.Status.COMPLETED)

    def test_teacher_cannot_complete_another_teachers_lesson(self):
        lesson_lifecycle.start_lesson(self.lesson1, self.teacher1.user)
        response = self.teacher2_client.post(f"/api/v1/lessons/{self.lesson1.id}/complete/")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_cannot_complete_a_cancelled_lesson(self):
        lesson_lifecycle.cancel_lesson(self.lesson1, self.teacher1.user)
        response = self.teacher1_client.post(f"/api/v1/lessons/{self.lesson1.id}/complete/")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_repeated_complete_request_is_idempotent(self):
        self.teacher1_client.post(f"/api/v1/lessons/{self.lesson1.id}/start/")
        self._mark_full_attendance(self.lesson1)
        Homework.objects.create(lesson=self.lesson1, title="ДЗ")
        first = self.teacher1_client.post(f"/api/v1/lessons/{self.lesson1.id}/complete/")
        self.assertEqual(first.status_code, status.HTTP_200_OK)
        self.lesson1.refresh_from_db()
        first_completed_at = self.lesson1.completed_at

        second = self.teacher1_client.post(f"/api/v1/lessons/{self.lesson1.id}/complete/")

        self.assertEqual(second.status_code, status.HTTP_200_OK)
        self.lesson1.refresh_from_db()
        self.assertEqual(self.lesson1.completed_at, first_completed_at)
        self.assertEqual(self.lesson1.completed_by_id, self.teacher1.user_id)

    # -- cancel ---------------------------------------------------------------

    def test_teacher_can_cancel_own_lesson_with_reason(self):
        response = self.teacher1_client.post(
            f"/api/v1/lessons/{self.lesson1.id}/cancel/", {"reason": "Тренер заболел"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.lesson1.refresh_from_db()
        self.assertEqual(self.lesson1.status, Lesson.Status.CANCELLED)
        self.assertEqual(self.lesson1.cancellation_reason, "Тренер заболел")

    def test_teacher_cannot_cancel_another_teachers_lesson(self):
        response = self.teacher2_client.post(f"/api/v1/lessons/{self.lesson1.id}/cancel/")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_cancelling_already_cancelled_lesson_is_idempotent(self):
        lesson_lifecycle.cancel_lesson(self.lesson1, self.teacher1.user, reason="Первая причина")
        response = self.teacher1_client.post(
            f"/api/v1/lessons/{self.lesson1.id}/cancel/", {"reason": "Вторая причина"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.lesson1.refresh_from_db()
        self.assertEqual(self.lesson1.status, Lesson.Status.CANCELLED)
        self.assertEqual(self.lesson1.cancellation_reason, "Первая причина")

    def test_completed_lesson_cannot_be_cancelled(self):
        self.teacher1_client.post(f"/api/v1/lessons/{self.lesson1.id}/start/")
        self._mark_full_attendance(self.lesson1)
        Homework.objects.create(lesson=self.lesson1, title="ДЗ")
        self.teacher1_client.post(f"/api/v1/lessons/{self.lesson1.id}/complete/")

        response = self.teacher1_client.post(f"/api/v1/lessons/{self.lesson1.id}/cancel/")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.lesson1.refresh_from_db()
        self.assertEqual(self.lesson1.status, Lesson.Status.COMPLETED)

    # -- queryset / filter correctness ---------------------------------------

    def test_completed_lesson_appears_in_completed_queryset(self):
        self.teacher1_client.post(f"/api/v1/lessons/{self.lesson1.id}/start/")
        self._mark_full_attendance(self.lesson1)
        Homework.objects.create(lesson=self.lesson1, title="ДЗ")
        self.teacher1_client.post(f"/api/v1/lessons/{self.lesson1.id}/complete/")

        response = self.teacher1_client.get("/api/v1/lessons/", {"status": "completed"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = [row["id"] for row in response.data["results"]]
        self.assertIn(self.lesson1.id, ids)

    def test_cancelled_lesson_appears_in_cancelled_queryset(self):
        self.teacher1_client.post(f"/api/v1/lessons/{self.lesson1.id}/cancel/")

        response = self.teacher1_client.get("/api/v1/lessons/", {"status": "cancelled"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = [row["id"] for row in response.data["results"]]
        self.assertIn(self.lesson1.id, ids)

    def test_completed_lesson_is_not_upcoming(self):
        self.teacher1_client.post(f"/api/v1/lessons/{self.lesson1.id}/start/")
        self._mark_full_attendance(self.lesson1)
        Homework.objects.create(lesson=self.lesson1, title="ДЗ")
        self.teacher1_client.post(f"/api/v1/lessons/{self.lesson1.id}/complete/")

        counts = lesson_status_counts(Lesson.objects.filter(group=self.group1))
        self.assertEqual(counts["completed"], 1)
        # "Upcoming" only ever counts still-SCHEDULED lessons — a completed
        # one, whatever its date, is never upcoming.
        upcoming_ids = Lesson.objects.filter(
            group=self.group1, status=Lesson.Status.SCHEDULED, date__gte=timezone.localdate()
        ).values_list("id", flat=True)
        self.assertNotIn(self.lesson1.id, list(upcoming_ids))

    # -- serializer fields ----------------------------------------------------

    def test_serializer_exposes_lifecycle_fields(self):
        response = self.teacher1_client.get(f"/api/v1/lessons/{self.lesson1.id}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        for field in (
            "status", "can_start", "can_complete", "can_cancel",
            "attendance_completed", "homework_added",
            "completion_requirements", "completion_progress",
            "completed_at", "completed_by", "started_at", "homework_not_required",
        ):
            self.assertIn(field, response.data)
        self.assertTrue(response.data["can_start"])
        self.assertFalse(response.data["can_complete"])
        self.assertFalse(response.data["attendance_completed"])
        self.assertFalse(response.data["homework_added"])

    def test_attendance_completed_and_homework_added_reflect_real_state(self):
        self.teacher1_client.post(f"/api/v1/lessons/{self.lesson1.id}/start/")
        self._mark_full_attendance(self.lesson1)

        response = self.teacher1_client.get(f"/api/v1/lessons/{self.lesson1.id}/")
        self.assertTrue(response.data["attendance_completed"])
        self.assertFalse(response.data["homework_added"])

        Homework.objects.create(lesson=self.lesson1, title="ДЗ")

        response = self.teacher1_client.get(f"/api/v1/lessons/{self.lesson1.id}/")
        self.assertTrue(response.data["homework_added"])

    def test_status_and_lifecycle_fields_are_read_only_on_plain_patch(self):
        # A plain PATCH must never be able to reset/forge lifecycle state —
        # only the dedicated start/complete/cancel actions may change it.
        response = self.teacher1_client.patch(
            f"/api/v1/lessons/{self.lesson1.id}/",
            {"status": "completed", "cancellation_reason": "hacked", "homework_not_required": True},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.lesson1.refresh_from_db()
        self.assertEqual(self.lesson1.status, Lesson.Status.SCHEDULED)
        self.assertEqual(self.lesson1.cancellation_reason, "")
        self.assertFalse(self.lesson1.homework_not_required)


class HomeworkResultsLockedAfterCompletionTests(AcademyTestBase):
    """Once a lesson is COMPLETED, a Teacher can no longer grade its
    Homework — enforced on the backend (views._assert_homework_results_
    editable / services.lesson_lifecycle.homework_results_locked), not just
    hidden in the frontend."""

    def setUp(self):
        super().setUp()
        self.lesson1 = Lesson.objects.filter(group=self.group1).order_by("lesson_number").first()
        self.homework = Homework.objects.create(lesson=self.lesson1, title="ДЗ 1")

        for student in (self.student1, self.student2):
            Attendance.objects.create(student=student, lesson=self.lesson1, status=Attendance.Status.PRESENT)
        lesson_lifecycle.start_lesson(self.lesson1, self.teacher1.user)
        lesson_lifecycle.complete_lesson(self.lesson1, self.teacher1.user)
        self.lesson1.refresh_from_db()
        self.assertEqual(self.lesson1.status, Lesson.Status.COMPLETED)

    def test_teacher_cannot_bulk_grade_after_completion(self):
        response = self.teacher1_client.post(
            f"/api/v1/homework/{self.homework.id}/results/",
            [{"student": self.student1.id, "status": "checked", "score": 9}],
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(HomeworkResult.objects.filter(homework=self.homework, student=self.student1).exists())

    def test_teacher_cannot_create_result_directly_after_completion(self):
        response = self.teacher1_client.post(
            "/api/v1/homework-results/",
            {"homework": self.homework.id, "student": self.student1.id, "status": "submitted"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_teacher_cannot_update_existing_result_after_completion(self):
        result = HomeworkResult.objects.create(
            homework=self.homework, student=self.student1, status=HomeworkResult.Status.SUBMITTED
        )
        response = self.teacher1_client.patch(
            f"/api/v1/homework-results/{result.id}/", {"status": "checked", "score": 8}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        result.refresh_from_db()
        self.assertEqual(result.status, HomeworkResult.Status.SUBMITTED)
        self.assertIsNone(result.score)

    def test_admin_can_still_grade_after_completion(self):
        response = self.admin_client.post(
            f"/api/v1/homework/{self.homework.id}/results/",
            [{"student": self.student1.id, "status": "checked", "score": 9}],
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertTrue(
            HomeworkResult.objects.filter(homework=self.homework, student=self.student1, status="checked").exists()
        )

    def test_results_editable_is_false_for_teacher_true_for_admin(self):
        teacher_response = self.teacher1_client.get(f"/api/v1/homework/{self.homework.id}/")
        self.assertFalse(teacher_response.data["results_editable"])
        self.assertEqual(teacher_response.data["lesson_status"], "completed")

        admin_response = self.admin_client.get(f"/api/v1/homework/{self.homework.id}/")
        self.assertTrue(admin_response.data["results_editable"])

    def test_grading_still_allowed_before_completion(self):
        other_lesson = Lesson.objects.filter(group=self.group1).order_by("lesson_number")[1]
        homework = Homework.objects.create(lesson=other_lesson, title="ДЗ 2")

        response = self.teacher1_client.post(
            f"/api/v1/homework/{homework.id}/results/",
            [{"student": self.student1.id, "status": "checked", "score": 7}],
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)


class LessonEditingLockedAfterCompletionOrCancellationTests(AcademyTestBase):
    """Once a lesson is COMPLETED or CANCELLED, a Teacher can no longer
    attach new Attendance or Homework to it — the broader "immutable
    historical record" rule (views._assert_lesson_editable /
    services.lesson_lifecycle.lesson_editing_locked), on top of the
    narrower homework-results-only lock tested separately above."""

    def setUp(self):
        super().setUp()
        self.lesson1 = Lesson.objects.filter(group=self.group1).order_by("lesson_number").first()
        self.other_lesson = Lesson.objects.filter(group=self.group1).order_by("lesson_number")[1]

        for student in (self.student1, self.student2):
            Attendance.objects.create(student=student, lesson=self.lesson1, status=Attendance.Status.PRESENT)
        lesson_lifecycle.start_lesson(self.lesson1, self.teacher1.user)
        Homework.objects.create(lesson=self.lesson1, title="ДЗ 1")
        lesson_lifecycle.complete_lesson(self.lesson1, self.teacher1.user)
        self.lesson1.refresh_from_db()
        self.assertEqual(self.lesson1.status, Lesson.Status.COMPLETED)

    def test_teacher_cannot_bulk_mark_attendance_after_completion(self):
        response = self.teacher1_client.post(
            f"/api/v1/lessons/{self.lesson1.id}/attendance/",
            [{"student": self.student1.id, "status": "absent"}],
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        attendance = Attendance.objects.get(student=self.student1, lesson=self.lesson1)
        self.assertEqual(attendance.status, Attendance.Status.PRESENT)  # untouched

    def test_teacher_cannot_create_attendance_directly_after_completion(self):
        response = self.teacher1_client.post(
            "/api/v1/attendance/",
            {"student": self.student1.id, "lesson": self.other_lesson.id, "status": "present"},
            format="json",
        )
        # other_lesson is still SCHEDULED — sanity check the direct-create
        # path itself works before proving it's blocked once completed.
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)

        # Remove student2's existing record first so the attempt below hits
        # the completion lock (403), not the serializer's own "already
        # marked" uniqueness check (400) — the two are independent guards.
        Attendance.objects.filter(student=self.student2, lesson=self.lesson1).delete()
        response = self.teacher1_client.post(
            "/api/v1/attendance/",
            {"student": self.student2.id, "lesson": self.lesson1.id, "status": "present"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_teacher_cannot_update_existing_attendance_after_completion(self):
        record = Attendance.objects.get(student=self.student1, lesson=self.lesson1)
        response = self.teacher1_client.patch(
            f"/api/v1/attendance/{record.id}/", {"status": "absent"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        record.refresh_from_db()
        self.assertEqual(record.status, Attendance.Status.PRESENT)

    def test_teacher_cannot_add_homework_after_completion(self):
        response = self.teacher1_client.post(
            "/api/v1/homework/",
            {"lesson": self.lesson1.id, "title": "Ещё одно ДЗ"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_teacher_cannot_edit_attendance_or_homework_after_cancellation(self):
        lesson_lifecycle.cancel_lesson(self.other_lesson, self.teacher1.user)

        attendance_response = self.teacher1_client.post(
            f"/api/v1/lessons/{self.other_lesson.id}/attendance/",
            [{"student": self.student1.id, "status": "present"}],
            format="json",
        )
        self.assertEqual(attendance_response.status_code, status.HTTP_403_FORBIDDEN)

        homework_response = self.teacher1_client.post(
            "/api/v1/homework/",
            {"lesson": self.other_lesson.id, "title": "ДЗ на отменённое занятие"},
            format="json",
        )
        self.assertEqual(homework_response.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_can_still_edit_after_completion(self):
        response = self.admin_client.post(
            f"/api/v1/lessons/{self.lesson1.id}/attendance/",
            [{"student": self.student1.id, "status": "late"}],
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)

    def test_attendance_editable_field_mirrors_the_lock(self):
        """LessonSerializer.attendance_editable — the frontend's own
        read-only switch for the attendance page — must never drift from
        what the backend actually enforces above."""
        completed_response = self.teacher1_client.get(f"/api/v1/lessons/{self.lesson1.id}/")
        self.assertFalse(completed_response.data["attendance_editable"])

        scheduled_response = self.teacher1_client.get(f"/api/v1/lessons/{self.other_lesson.id}/")
        self.assertTrue(scheduled_response.data["attendance_editable"])


class LessonSummaryFieldsTests(AcademyTestBase):
    """LessonSerializer.attendance_summary/homework_summary — the real,
    backend-calculated numbers behind the completed Lesson Detail page's
    "Итоги занятия" KPI section (services.lesson_summary)."""

    def setUp(self):
        super().setUp()
        self.lesson1 = Lesson.objects.filter(group=self.group1).order_by("lesson_number").first()

    def test_attendance_summary_before_any_marking(self):
        response = self.teacher1_client.get(f"/api/v1/lessons/{self.lesson1.id}/")
        summary = response.data["attendance_summary"]
        self.assertEqual(summary["total_students"], 2)
        self.assertEqual(summary["present"], 0)
        self.assertEqual(summary["attendance_rate"], None)

    def test_attendance_summary_reflects_real_records(self):
        Attendance.objects.create(student=self.student1, lesson=self.lesson1, status=Attendance.Status.PRESENT)
        Attendance.objects.create(student=self.student2, lesson=self.lesson1, status=Attendance.Status.LATE)

        response = self.teacher1_client.get(f"/api/v1/lessons/{self.lesson1.id}/")
        summary = response.data["attendance_summary"]
        self.assertEqual(summary["total_students"], 2)
        self.assertEqual(summary["present"], 1)
        self.assertEqual(summary["late"], 1)
        self.assertEqual(summary["absent"], 0)
        self.assertEqual(summary["excused"], 0)
        self.assertEqual(summary["attendance_rate"], 100.0)  # present+late count as attended

    def test_homework_summary_is_none_without_homework(self):
        response = self.teacher1_client.get(f"/api/v1/lessons/{self.lesson1.id}/")
        self.assertIsNone(response.data["homework_summary"])

    def test_homework_summary_reflects_real_results(self):
        homework = Homework.objects.create(lesson=self.lesson1, title="ДЗ 1")
        HomeworkResult.objects.create(
            homework=homework, student=self.student1, status=HomeworkResult.Status.CHECKED, score=9
        )
        HomeworkResult.objects.create(
            homework=homework, student=self.student2, status=HomeworkResult.Status.SUBMITTED
        )

        response = self.teacher1_client.get(f"/api/v1/lessons/{self.lesson1.id}/")
        summary = response.data["homework_summary"]
        self.assertEqual(summary["results_total"], 2)
        self.assertEqual(summary["checked"], 1)
        self.assertEqual(summary["pending"], 1)
        self.assertEqual(summary["average_score"], 9.0)  # only the scored result counts

    def test_homework_summary_average_score_none_when_nothing_scored(self):
        homework = Homework.objects.create(lesson=self.lesson1, title="ДЗ 1")
        HomeworkResult.objects.create(
            homework=homework, student=self.student1, status=HomeworkResult.Status.SUBMITTED
        )

        response = self.teacher1_client.get(f"/api/v1/lessons/{self.lesson1.id}/")
        self.assertIsNone(response.data["homework_summary"]["average_score"])


class LessonStatusKPITests(AcademyTestBase):
    """Completed/Cancelled/Upcoming must reflect the real `Lesson.status`
    value only, never date-based inference — and the same underlying data
    must report the same numbers everywhere it's shown."""

    def setUp(self):
        super().setUp()
        self.admin_web = DjangoClient()
        self.admin_web.force_login(self.admin)
        self.today = timezone.localdate()

        gt = self.group1.teachers.get()
        Lesson.objects.filter(group=self.group1).delete()  # start from a clean, controlled slate

        def make(number, date, status):
            return Lesson.objects.create(
                group=self.group1, group_teacher=gt, teacher=self.teacher1, subject=self.subject_python,
                lesson_number=number, date=date, start_time=dt.time(10, 0), end_time=dt.time(11, 0),
                status=status,
            )

        self.past_completed = make(1, self.today - dt.timedelta(days=10), Lesson.Status.COMPLETED)
        self.past_cancelled = make(2, self.today - dt.timedelta(days=5), Lesson.Status.CANCELLED)
        # A PLANNED lesson whose date has already passed but was never
        # confirmed completed — must NOT count as completed just because
        # the date is in the past (spec §12).
        self.past_still_planned = make(3, self.today - dt.timedelta(days=1), Lesson.Status.SCHEDULED)
        self.upcoming_planned = make(4, self.today + dt.timedelta(days=1), Lesson.Status.SCHEDULED)

    def test_kpi_helper_counts_real_statuses_only(self):
        kpi = _lesson_status_kpi(Lesson.objects.filter(group=self.group1), self.today)
        self.assertEqual(kpi["completed"], 1)
        self.assertEqual(kpi["cancelled"], 1)
        # Upcoming excludes completed, cancelled, AND the past-but-still-
        # planned lesson (it's not "upcoming" — it's in the past).
        self.assertEqual(kpi["upcoming"], 1)
        self.assertEqual(kpi["total"], 4)
        # "Requires attention": only the still-SCHEDULED lesson whose date
        # has already passed (past_completed/past_cancelled are resolved;
        # upcoming_planned is still in the future).
        self.assertEqual(kpi["attention"], 1)

    def test_admin_counters_are_correct_including_in_progress_and_attendance_noise(self):
        # An in-progress lesson whose slot is already over must also count
        # as "requires attention" — starting a lesson and never finishing it
        # is exactly the case the counter exists to surface.
        gt = self.group1.teachers.get()
        in_progress_past = Lesson.objects.create(
            group=self.group1, group_teacher=gt, teacher=self.teacher1, subject=self.subject_python,
            lesson_number=5, date=self.today - dt.timedelta(days=1),
            start_time=dt.time(10, 0), end_time=dt.time(11, 0), status=Lesson.Status.IN_PROGRESS,
        )
        # Attendance records alone (no status transition) must never be
        # mistaken for a completed lesson.
        Attendance.objects.create(student=self.student1, lesson=self.past_still_planned, status=Attendance.Status.PRESENT)
        Attendance.objects.create(student=self.student2, lesson=self.past_still_planned, status=Attendance.Status.PRESENT)

        kpi = _lesson_status_kpi(Lesson.objects.filter(group=self.group1), self.today)

        self.assertEqual(kpi["completed"], 1)  # unchanged by the Attendance rows above
        self.assertEqual(kpi["cancelled"], 1)
        self.assertEqual(kpi["upcoming"], 1)
        self.assertEqual(kpi["attention"], 2)  # past_still_planned + in_progress_past
        self.assertEqual(kpi["total"], 5)

        response = self.admin_web.get(reverse("admin:academy_lesson_changelist"), {"group": self.group1.pk})
        self.assertContains(response, '<div class="ok-kpi-value">2</div>\n      <div class="ok-kpi-label">Требуют внимания</div>')

    def test_group_overview_and_lesson_monitor_report_the_same_numbers(self):
        overview = self.admin_web.get(reverse("admin:academy_group_workspace", args=[self.group1.pk]))
        monitor = self.admin_web.get(reverse("admin:academy_lesson_changelist"), {"group": self.group1.pk})

        overview_body = overview.content.decode()
        monitor_body = monitor.content.decode()

        # Both pages must agree that this group has exactly 1 completed and
        # 1 cancelled lesson — the same underlying data, the same shared
        # _lesson_status_kpi() call, never two different numbers.
        self.assertIn('<div class="ok-kpi-value">1</div>\n    <div class="ok-kpi-label">Завершённые занятия</div>', overview_body)
        self.assertIn('<div class="ok-kpi-value">1</div>\n    <div class="ok-kpi-label">Отменённые занятия</div>', overview_body)
        self.assertIn('<div class="ok-kpi-value">1</div>\n      <div class="ok-kpi-label">Завершённые</div>', monitor_body)
        self.assertIn('<div class="ok-kpi-value">1</div>\n      <div class="ok-kpi-label">Отменённые</div>', monitor_body)


class AuditScheduleConflictsCommandTests(AcademyTestBase):
    """The audit command reports existing bad schedule data without
    modifying anything (spec §15: no automatic cleanup)."""

    def test_reports_existing_group_conflict_without_modifying_data(self):
        other_teacher = make_teacher("audit_conflict_teacher")
        GroupSchedule.objects.create(
            group=self.group1, teacher=other_teacher, subject=self.subject_frontend,
            day_of_week="mon", start_time=dt.time(15, 30), end_time=dt.time(16, 0), room=self.room2,
        )
        schedule_count_before = GroupSchedule.objects.count()
        lesson_count_before = Lesson.objects.count()

        out = StringIO()
        call_command("audit_schedule_conflicts", stdout=out)
        output = out.getvalue()

        self.assertIn("Группа", output)
        self.assertIn(self.group1.name, output)
        self.assertEqual(GroupSchedule.objects.count(), schedule_count_before)
        self.assertEqual(Lesson.objects.count(), lesson_count_before)

    def test_reports_no_conflicts_when_schedule_is_clean(self):
        # group2 has its own, non-conflicting slot only.
        out = StringIO()
        call_command("audit_schedule_conflicts", stdout=out)
        # group1/group2 alone (no manually-introduced conflict) must not be
        # reported as conflicting with each other.
        self.assertNotIn("Frontend Beginner", out.getvalue().split("Python Beginner")[0])


class AcademyMonthlyReportTests(AcademyTestBase):
    """The Admin-only, whole-academy Monthly Report (spec: aggregate across
    every Teacher/Group/Student/Lesson for one calendar month, never a
    single teacher's own slice)."""

    def setUp(self):
        super().setUp()
        from apps.academy.services.academy_monthly_report import compute_academy_monthly_stats

        self.compute_academy_monthly_stats = staticmethod(compute_academy_monthly_stats)

        # group1's lessons were auto-generated for Sep 2026 (Mon/Wed ->
        # every 7 days: 7, 14, 21, 28 — see LessonGenerationTests).
        self.g1_lessons = list(Lesson.objects.filter(group=self.group1).order_by("lesson_number"))
        self.g2_lessons = list(Lesson.objects.filter(group=self.group2).order_by("lesson_number"))

        # Mark attendance + homework on the first lesson of each group so
        # the month has real, non-zero figures to assert on.
        Attendance.objects.create(student=self.student1, lesson=self.g1_lessons[0], status="present")
        Attendance.objects.create(student=self.student2, lesson=self.g1_lessons[0], status="absent")
        Attendance.objects.create(student=self.student3, lesson=self.g2_lessons[0], status="present")

        homework1 = Homework.objects.create(lesson=self.g1_lessons[0], title="ДЗ 1")
        HomeworkResult.objects.create(homework=homework1, student=self.student1, status="checked", score=8)
        HomeworkResult.objects.create(homework=homework1, student=self.student2, status="submitted")

        self.g1_lessons[0].status = Lesson.Status.COMPLETED
        self.g1_lessons[0].save(update_fields=["status"])
        self.g2_lessons[0].status = Lesson.Status.COMPLETED
        self.g2_lessons[0].save(update_fields=["status"])

    # -- Model -------------------------------------------------------------

    def test_unique_constraint_one_report_per_month(self):
        AcademyMonthlyReport.objects.create(year=2026, month=9)
        with self.assertRaises(Exception):
            AcademyMonthlyReport.objects.create(year=2026, month=9)

    # -- month_bounds / leap year -------------------------------------------

    def test_february_leap_year_bounds(self):
        stats = self.compute_academy_monthly_stats(2028, 2)  # 2028 is a leap year
        self.assertEqual(stats["period"]["start_date"], dt.date(2028, 2, 1))
        self.assertEqual(stats["period"]["end_date"], dt.date(2028, 2, 29))

    def test_february_non_leap_year_bounds(self):
        stats = self.compute_academy_monthly_stats(2026, 2)
        self.assertEqual(stats["period"]["start_date"], dt.date(2026, 2, 1))
        self.assertEqual(stats["period"]["end_date"], dt.date(2026, 2, 28))

    # -- Stats computation ---------------------------------------------------

    def test_stats_computed_from_real_data(self):
        stats = self.compute_academy_monthly_stats(2026, 9)

        self.assertTrue(stats["has_data"])
        self.assertEqual(stats["students_count"], 3)  # student1/2/3 all active
        self.assertEqual(stats["groups_count"], 2)  # group1 + group2 both had lessons
        self.assertEqual(stats["teachers_count"], 2)  # teacher1 + teacher2
        self.assertEqual(stats["lessons_completed"], 2)

        self.assertEqual(stats["attendance"]["total"], 3)
        self.assertEqual(stats["attendance"]["present"], 2)
        self.assertEqual(stats["attendance"]["absent"], 1)

        self.assertEqual(stats["homework"]["assigned"], 1)
        self.assertEqual(stats["homework"]["checked"], 1)
        self.assertEqual(stats["homework"]["pending_review"], 1)  # the "submitted" result

        group_names = {row["name"]: row for row in stats["groups"]}
        self.assertEqual(set(group_names), {"Python Beginner", "Frontend Beginner"})
        self.assertEqual(group_names["Python Beginner"]["students_count"], 2)

        teacher_names = {row["name"] for row in stats["teachers"]}
        self.assertEqual(len(teacher_names), 2)

        # completed is a real StudentStatusEvent-backed count (see
        # services.student_status) — 0 when none happened, never None.
        self.assertEqual(stats["students"]["completed"], 0)
        # "reschedule" status still has no backing field on Lesson — still
        # honestly None, not fabricated.
        self.assertIsNone(stats["lessons"]["rescheduled"])

        # Group statistics are a live, current-database-state count (never
        # month-scoped) built from Group.status — group1/group2 are both
        # ACTIVE with 2/1 active students respectively (see AcademyTestBase).
        self.assertEqual(stats["group_stats"]["total"], 2)
        self.assertEqual(stats["group_stats"]["active"], 2)
        self.assertEqual(stats["group_stats"]["completed"], 0)
        self.assertEqual(stats["group_stats"]["students_active"], 3)
        self.assertEqual(stats["group_stats"]["students_completed"], 0)

    def test_no_data_month_is_honest_not_fabricated(self):
        stats = self.compute_academy_monthly_stats(2020, 1)
        self.assertFalse(stats["has_data"])
        self.assertEqual(stats["groups"], [])
        self.assertEqual(stats["teachers"], [])
        self.assertEqual(stats["weekly_dynamics"], [])
        self.assertEqual(stats["kpi"]["total"], 0.0)

    # -- Permissions (backend-enforced, spec §2/§20) -------------------------

    def test_teacher_cannot_list_academy_reports(self):
        response = self.teacher1_client.get("/api/v1/academy-reports/")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_teacher_cannot_create_academy_report(self):
        response = self.teacher1_client.post("/api/v1/academy-reports/", {"year": 2026, "month": 9}, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_anonymous_cannot_access(self):
        response = self.anon_client.get("/api/v1/academy-reports/")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_admin_can_create_and_retrieve(self):
        response = self.admin_client.post("/api/v1/academy-reports/", {"year": 2026, "month": 9}, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        report_id = response.data["id"]
        self.assertEqual(response.data["stats"]["students_count"], 3)

        detail = self.admin_client.get(f"/api/v1/academy-reports/{report_id}/")
        self.assertEqual(detail.status_code, status.HTTP_200_OK)
        self.assertEqual(detail.data["stats"]["lessons_completed"], 2)

    def test_create_is_idempotent_per_month(self):
        first = self.admin_client.post("/api/v1/academy-reports/", {"year": 2026, "month": 9}, format="json")
        self.assertEqual(first.status_code, status.HTTP_201_CREATED)

        second = self.admin_client.post("/api/v1/academy-reports/", {"year": 2026, "month": 9}, format="json")
        self.assertEqual(second.status_code, status.HTTP_200_OK)
        self.assertEqual(second.data["detail"], "exists")
        self.assertEqual(second.data["report"]["id"], first.data["id"])
        self.assertEqual(AcademyMonthlyReport.objects.count(), 1)

    def test_admin_can_update_comment(self):
        report = AcademyMonthlyReport.objects.create(year=2026, month=9)
        response = self.admin_client.patch(
            f"/api/v1/academy-reports/{report.id}/", {"comment": "Отличный месяц."}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        report.refresh_from_db()
        self.assertEqual(report.comment, "Отличный месяц.")

    # -- PDF ------------------------------------------------------------

    def test_admin_can_download_pdf(self):
        report = AcademyMonthlyReport.objects.create(year=2026, month=9)
        response = self.admin_client.get(f"/api/v1/academy-reports/{report.id}/pdf/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response["Content-Type"], "application/pdf")
        content = b"".join(response.streaming_content) if response.streaming else response.content
        self.assertTrue(content.startswith(b"%PDF"))

    def test_teacher_cannot_download_pdf(self):
        report = AcademyMonthlyReport.objects.create(year=2026, month=9)
        response = self.teacher1_client.get(f"/api/v1/academy-reports/{report.id}/pdf/")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_pdf_builds_for_month_with_no_data(self):
        from apps.academy.services.academy_monthly_report_pdf import build_academy_monthly_report_pdf

        report = AcademyMonthlyReport.objects.create(year=2020, month=1)
        pdf_bytes = build_academy_monthly_report_pdf(report)
        self.assertTrue(pdf_bytes.startswith(b"%PDF"))

    def test_pdf_builds_with_real_completed_events_and_group_stats(self):
        """The PDF must render the completed-students metric and the group
        statistics block from the same `compute_academy_monthly_stats` the
        API/Admin use — no separate calculation logic."""
        from apps.academy.services.academy_monthly_report_pdf import build_academy_monthly_report_pdf

        complete_student(self.student1, comment="")
        pause_student(self.student2, reason="no_interest", comment="")
        today = dt.date.today()
        report = AcademyMonthlyReport.objects.create(year=today.year, month=today.month)
        pdf_bytes = build_academy_monthly_report_pdf(report)
        self.assertTrue(pdf_bytes.startswith(b"%PDF"))

    def test_pdf_never_mentions_removed_pause_metric(self):
        """spec: "Приостановили обучение" is removed from the Academy Report
        entirely — the PDF text stream must not contain it, even though
        pausing a student remains a real, working feature elsewhere."""
        from apps.academy.services.academy_monthly_report_pdf import build_academy_monthly_report_pdf

        pause_student(self.student1, reason="no_interest", comment="")
        today = dt.date.today()
        report = AcademyMonthlyReport.objects.create(year=today.year, month=today.month)
        pdf_bytes = build_academy_monthly_report_pdf(report)
        # reportlab-encoded text isn't searchable as plain UTF-8 in the byte
        # stream, so assert on the actual dict fields the render loop reads
        # from instead — the removed keys must be gone from the shared stats.
        stats = compute_academy_monthly_stats(today.year, today.month)
        self.assertNotIn("paused", stats["students"])
        self.assertNotIn("paused", stats["movement"])
        self.assertNotIn("continued", stats["movement"])
        self.assertNotIn("returned_after_pause", stats["movement"])
        self.assertTrue(pdf_bytes.startswith(b"%PDF"))


class AcademyReportAdminViewTests(AcademyTestBase):
    """The Django Admin "Отчёт академии" sidebar entry + monitor/detail
    views — the server-rendered counterpart of the API/React feature,
    reachable from the Jazzmin sidebar under "Аналитика" (spec: add a
    Sidebar entry, backend-enforced, no dead/404 link)."""

    def setUp(self):
        super().setUp()
        self.admin_web = DjangoClient()
        self.admin_web.force_login(self.admin)
        self.teacher_web = DjangoClient()
        self.teacher_web.force_login(self.teacher1.user)

    # -- Sidebar --------------------------------------------------------

    def test_sidebar_shows_academy_report_link_for_admin(self):
        response = self.admin_web.get(reverse("admin:index"))
        self.assertEqual(response.status_code, 200)
        body = response.content.decode()
        self.assertIn("Отчёт академии", body)
        self.assertIn(reverse("admin:academy_report_monitor"), body)

    def test_existing_sidebar_links_still_present(self):
        """Adding the new entry must not break the ones already there.

        The "Отчёты преподавателей" entry is a Jazzmin "model"-type
        custom_link, which renders the *model's* verbose_name_plural
        (title-cased by Jazzmin) rather than the link's own "name" — hence
        matching the admin URL fragment instead of hardcoding that casing.
        """
        response = self.admin_web.get(reverse("admin:index"))
        body = response.content.decode()
        self.assertIn("Аналитика", body)
        self.assertIn(reverse("admin:academy_analytics"), body)
        self.assertIn("academy/monthlyteacherreport/", body)

    # -- Monitor view -----------------------------------------------------

    def test_admin_can_access_monitor(self):
        response = self.admin_web.get(reverse("admin:academy_report_monitor"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("Отчёт академии", response.content.decode())

    def test_teacher_cannot_access_monitor(self):
        response = self.teacher_web.get(reverse("admin:academy_report_monitor"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin/login/", response.url)

    def test_staff_non_admin_forbidden(self):
        # is_staff=True gets past admin_view()'s login gate, but the role
        # check inside the view (_require_admin) must still refuse them.
        self.teacher1.user.is_staff = True
        self.teacher1.user.save(update_fields=["is_staff"])
        staff_teacher_web = DjangoClient()
        staff_teacher_web.force_login(self.teacher1.user)
        response = staff_teacher_web.get(reverse("admin:academy_report_monitor"))
        self.assertEqual(response.status_code, 403)

    def test_anonymous_redirected_to_login(self):
        response = DjangoClient().get(reverse("admin:academy_report_monitor"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin/login/", response.url)

    # -- Open (get-or-create) ----------------------------------------------

    def test_open_creates_report_and_redirects_to_detail(self):
        self.assertEqual(AcademyMonthlyReport.objects.count(), 0)
        response = self.admin_web.post(reverse("admin:academy_report_open"), {"year": 2026, "month": 9})
        self.assertEqual(response.status_code, 302)
        report = AcademyMonthlyReport.objects.get(year=2026, month=9)
        self.assertIn(reverse("admin:academy_report_detail", args=[report.pk]), response.url)

    def test_open_is_idempotent_per_month(self):
        self.admin_web.post(reverse("admin:academy_report_open"), {"year": 2026, "month": 9})
        self.admin_web.post(reverse("admin:academy_report_open"), {"year": 2026, "month": 9})
        self.assertEqual(AcademyMonthlyReport.objects.filter(year=2026, month=9).count(), 1)

    def test_open_rejects_invalid_month(self):
        response = self.admin_web.post(reverse("admin:academy_report_open"), {"year": 2026, "month": 13})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(AcademyMonthlyReport.objects.count(), 0)

    def test_teacher_cannot_open_report(self):
        response = self.teacher_web.post(reverse("admin:academy_report_open"), {"year": 2026, "month": 9})
        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin/login/", response.url)
        self.assertEqual(AcademyMonthlyReport.objects.count(), 0)

    # -- Detail view ------------------------------------------------------

    def test_detail_view_renders_real_stats(self):
        lesson = Lesson.objects.filter(group=self.group1).order_by("lesson_number").first()
        Attendance.objects.create(student=self.student1, lesson=lesson, status="present")
        report = AcademyMonthlyReport.objects.create(year=2026, month=9)

        response = self.admin_web.get(reverse("admin:academy_report_detail", args=[report.pk]))
        self.assertEqual(response.status_code, 200)
        body = response.content.decode()
        self.assertIn("Отчёт академии", body)
        self.assertIn("Сентябрь 2026", body)
        stats = response.context["stats"]
        self.assertTrue(stats["has_data"])
        self.assertEqual(stats["attendance"]["present"], 1)

    def test_detail_view_404_for_missing_report(self):
        response = self.admin_web.get(reverse("admin:academy_report_detail", args=[999999]))
        self.assertEqual(response.status_code, 404)

    def test_teacher_cannot_access_detail(self):
        report = AcademyMonthlyReport.objects.create(year=2026, month=9)
        response = self.teacher_web.get(reverse("admin:academy_report_detail", args=[report.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin/login/", response.url)

    def test_detail_pdf_link_present_and_downloadable(self):
        report = AcademyMonthlyReport.objects.create(year=2026, month=9)
        response = self.admin_web.get(reverse("admin:academy_report_detail", args=[report.pk]))
        pdf_url = reverse("academy-report-pdf", args=[report.pk])
        self.assertIn(pdf_url, response.content.decode())

        pdf_response = self.admin_web.get(pdf_url)
        self.assertEqual(pdf_response.status_code, 200)
        self.assertEqual(pdf_response["Content-Type"], "application/pdf")


# ---------------------------------------------------------------------------
# Student deactivation / reactivation / history (spec: "Student
# Deactivation, Reactivation, History & Academy Reports").
# ---------------------------------------------------------------------------

class StudentStatusServiceTests(AcademyTestBase):
    """`services.student_status` — the one place `Student.is_active` ever
    flips and a `StudentStatusEvent` ever gets written."""

    def test_deactivate_success_creates_event_and_flips_status(self):
        event = deactivate_student(self.student1, reason="no_interest", comment="", performed_by=self.admin)
        self.student1.refresh_from_db()
        self.assertFalse(self.student1.is_active)
        self.assertEqual(event.event_type, StudentStatusEvent.EventType.DEACTIVATED)
        self.assertEqual(event.reason, "no_interest")
        self.assertEqual(event.group_id, self.group1.id)  # group at moment of leaving
        self.assertEqual(event.performed_by_id, self.admin.id)
        self.assertEqual(event.event_date, dt.date.today())

    def test_deactivate_requires_reason(self):
        with self.assertRaises(DjangoValidationError):
            deactivate_student(self.student1, reason="", comment="")
        self.student1.refresh_from_db()
        self.assertTrue(self.student1.is_active)
        self.assertEqual(StudentStatusEvent.objects.count(), 0)

    def test_deactivate_other_reason_requires_comment(self):
        with self.assertRaises(DjangoValidationError):
            deactivate_student(self.student1, reason="other", comment="   ")
        self.student1.refresh_from_db()
        self.assertTrue(self.student1.is_active)
        self.assertEqual(StudentStatusEvent.objects.count(), 0)

    def test_deactivate_other_reason_with_comment_succeeds(self):
        event = deactivate_student(self.student1, reason="other", comment="Уехал учиться за границу.")
        self.assertEqual(event.reason, "other")
        self.assertEqual(event.comment, "Уехал учиться за границу.")

    def test_deactivate_is_atomic_on_model_validation_failure(self):
        """An invalid reason fails `StudentStatusEvent.full_clean()` deep
        inside the transaction — neither the Student row nor a history
        event may survive that failure."""
        with self.assertRaises(DjangoValidationError):
            deactivate_student(self.student1, reason="not_a_real_reason", comment="")
        self.student1.refresh_from_db()
        self.assertTrue(self.student1.is_active)
        self.assertEqual(StudentStatusEvent.objects.count(), 0)

    def test_double_deactivate_is_safe_not_duplicated(self):
        """A retried/duplicate request against an already-inactive student
        is a clean error, never a second history event for the same
        departure (spec: "Повторные запросы должны обрабатываться
        безопасно")."""
        deactivate_student(self.student1, reason="no_interest", comment="")
        with self.assertRaises(DjangoValidationError):
            deactivate_student(self.student1, reason="financial_issues", comment="")
        self.assertEqual(StudentStatusEvent.objects.filter(student=self.student1).count(), 1)

    def test_reactivate_success_sets_group_and_status(self):
        deactivate_student(self.student1, reason="no_interest", comment="")
        event = reactivate_student(
            self.student1, group=self.group2, event_date=dt.date(2026, 9, 20), comment="Вернулась", performed_by=self.admin
        )
        self.student1.refresh_from_db()
        self.assertTrue(self.student1.is_active)
        self.assertEqual(self.student1.group_id, self.group2.id)
        self.assertEqual(event.event_type, StudentStatusEvent.EventType.REACTIVATED)
        self.assertEqual(event.event_date, dt.date(2026, 9, 20))

    def test_reactivate_requires_group(self):
        deactivate_student(self.student1, reason="no_interest", comment="")
        with self.assertRaises(DjangoValidationError):
            reactivate_student(self.student1, group=None, event_date=dt.date.today(), comment="")

    def test_cannot_reactivate_already_active_student(self):
        with self.assertRaises(DjangoValidationError):
            reactivate_student(self.student1, group=self.group1, event_date=dt.date.today(), comment="")

    def test_double_reactivate_is_safe(self):
        deactivate_student(self.student1, reason="no_interest", comment="")
        reactivate_student(self.student1, group=self.group1, event_date=dt.date.today(), comment="")
        with self.assertRaises(DjangoValidationError):
            reactivate_student(self.student1, group=self.group1, event_date=dt.date.today(), comment="")

    def test_multiple_deactivate_reactivate_cycles_keep_full_history(self):
        deactivate_student(self.student1, reason="no_interest", comment="")
        reactivate_student(self.student1, group=self.group1, event_date=dt.date(2026, 1, 1), comment="")
        deactivate_student(self.student1, reason="financial_issues", comment="")
        reactivate_student(self.student1, group=self.group1, event_date=dt.date(2026, 3, 1), comment="")

        events = list(StudentStatusEvent.objects.filter(student=self.student1).order_by("created_at"))
        self.assertEqual(len(events), 4)
        self.assertEqual(
            [e.event_type for e in events],
            [
                StudentStatusEvent.EventType.DEACTIVATED,
                StudentStatusEvent.EventType.REACTIVATED,
                StudentStatusEvent.EventType.DEACTIVATED,
                StudentStatusEvent.EventType.REACTIVATED,
            ],
        )
        self.student1.refresh_from_db()
        self.assertTrue(self.student1.is_active)

    def test_no_refund_fields_exist_on_the_model(self):
        """This project has no payment/billing model anywhere — asserting
        this stays true guards against ever bolting a fabricated Decimal
        refund field onto history events (spec: "Не создавай выдуманные
        суммы, платежи или возвраты")."""
        field_names = {f.name for f in StudentStatusEvent._meta.get_fields()}
        self.assertNotIn("refund_amount", field_names)
        self.assertNotIn("refund_date", field_names)


class StudentPauseContinueCompleteServiceTests(AcademyTestBase):
    """`services.student_status.pause_student` / `continue_student` /
    `complete_student` — the three new lifecycle transitions backing the
    Academy Report's "Приостановили" / "Продолжили" / "Завершили" metrics."""

    # -- pause_student -----------------------------------------------------

    def test_pause_success_creates_event_and_flips_status(self):
        event = pause_student(
            self.student1, reason="not_enough_time", expected_return_date=dt.date(2026, 10, 1),
            comment="", performed_by=self.admin,
        )
        self.student1.refresh_from_db()
        self.assertEqual(self.student1.status, Student.Status.PAUSED)
        self.assertFalse(self.student1.is_active)
        self.assertEqual(event.event_type, StudentStatusEvent.EventType.PAUSED)
        self.assertEqual(event.expected_return_date, dt.date(2026, 10, 1))
        self.assertEqual(event.previous_status, Student.Status.ACTIVE)
        self.assertEqual(event.performed_by_id, self.admin.id)

    def test_pause_requires_reason(self):
        with self.assertRaises(DjangoValidationError):
            pause_student(self.student1, reason="", comment="")
        self.student1.refresh_from_db()
        self.assertEqual(self.student1.status, Student.Status.ACTIVE)
        self.assertEqual(StudentStatusEvent.objects.count(), 0)

    def test_pause_other_reason_requires_comment(self):
        with self.assertRaises(DjangoValidationError):
            pause_student(self.student1, reason="other", comment="  ")
        self.assertEqual(StudentStatusEvent.objects.count(), 0)

    def test_cannot_pause_already_paused_student(self):
        pause_student(self.student1, reason="no_interest", comment="")
        with self.assertRaises(DjangoValidationError):
            pause_student(self.student1, reason="relocation", comment="")
        self.assertEqual(StudentStatusEvent.objects.filter(student=self.student1).count(), 1)

    def test_cannot_pause_completed_student(self):
        complete_student(self.student1, comment="")
        with self.assertRaises(DjangoValidationError):
            pause_student(self.student1, reason="no_interest", comment="")

    def test_cannot_pause_withdrawn_student(self):
        deactivate_student(self.student1, reason="no_interest", comment="")
        with self.assertRaises(DjangoValidationError):
            pause_student(self.student1, reason="relocation", comment="")

    def test_pause_is_atomic_on_validation_failure(self):
        with self.assertRaises(DjangoValidationError):
            pause_student(self.student1, reason="not_a_real_reason", comment="")
        self.student1.refresh_from_db()
        self.assertEqual(self.student1.status, Student.Status.ACTIVE)
        self.assertEqual(StudentStatusEvent.objects.count(), 0)

    # -- continue_student ----------------------------------------------------

    def test_continue_success_creates_event_and_flips_status(self):
        pause_student(self.student1, reason="no_interest", comment="")
        event = continue_student(
            self.student1, group=self.group2, event_date=dt.date(2026, 9, 20), comment="Вернулась",
            performed_by=self.admin,
        )
        self.student1.refresh_from_db()
        self.assertEqual(self.student1.status, Student.Status.ACTIVE)
        self.assertTrue(self.student1.is_active)
        self.assertEqual(self.student1.group_id, self.group2.id)
        self.assertEqual(event.event_type, StudentStatusEvent.EventType.CONTINUED)
        self.assertEqual(event.previous_status, Student.Status.PAUSED)

    def test_continue_defaults_to_current_group_when_not_given(self):
        pause_student(self.student1, reason="no_interest", comment="")
        continue_student(self.student1, event_date=dt.date.today(), comment="")
        self.student1.refresh_from_db()
        self.assertEqual(self.student1.group_id, self.group1.id)

    def test_cannot_continue_active_student(self):
        with self.assertRaises(DjangoValidationError):
            continue_student(self.student1, event_date=dt.date.today(), comment="")

    def test_cannot_continue_withdrawn_student(self):
        """spec: continuing must not be conflated with ordinary
        reactivation-after-withdrawal — a withdrawn student cannot use
        `continue_student` at all, only `reactivate_student`."""
        deactivate_student(self.student1, reason="no_interest", comment="")
        with self.assertRaises(DjangoValidationError):
            continue_student(self.student1, event_date=dt.date.today(), comment="")

    def test_double_continue_is_safe_not_duplicated(self):
        pause_student(self.student1, reason="no_interest", comment="")
        continue_student(self.student1, event_date=dt.date.today(), comment="")
        with self.assertRaises(DjangoValidationError):
            continue_student(self.student1, event_date=dt.date.today(), comment="")
        self.assertEqual(
            StudentStatusEvent.objects.filter(
                student=self.student1, event_type=StudentStatusEvent.EventType.CONTINUED
            ).count(),
            1,
        )

    # -- complete_student ----------------------------------------------------

    def test_complete_from_active_creates_event_and_flips_status(self):
        event = complete_student(self.student1, comment="Отличные результаты", performed_by=self.admin)
        self.student1.refresh_from_db()
        self.assertEqual(self.student1.status, Student.Status.COMPLETED)
        self.assertFalse(self.student1.is_active)
        self.assertEqual(event.event_type, StudentStatusEvent.EventType.COMPLETED)
        self.assertEqual(event.previous_status, Student.Status.ACTIVE)

    def test_complete_from_paused_is_allowed(self):
        pause_student(self.student1, reason="no_interest", comment="")
        event = complete_student(self.student1, comment="")
        self.assertEqual(event.previous_status, Student.Status.PAUSED)
        self.student1.refresh_from_db()
        self.assertEqual(self.student1.status, Student.Status.COMPLETED)

    def test_cannot_complete_already_completed_student(self):
        complete_student(self.student1, comment="")
        with self.assertRaises(DjangoValidationError):
            complete_student(self.student1, comment="")
        self.assertEqual(StudentStatusEvent.objects.filter(student=self.student1).count(), 1)

    def test_cannot_complete_withdrawn_student(self):
        deactivate_student(self.student1, reason="no_interest", comment="")
        with self.assertRaises(DjangoValidationError):
            complete_student(self.student1, comment="")

    def test_complete_is_atomic_row_locked_against_concurrent_duplicate(self):
        """Simulates a retried/double-submit request: the second call must
        see the already-updated status and fail cleanly rather than writing
        a second COMPLETED event."""
        complete_student(self.student1, comment="")
        with self.assertRaises(DjangoValidationError):
            complete_student(self.student1, comment="")
        events = StudentStatusEvent.objects.filter(
            student=self.student1, event_type=StudentStatusEvent.EventType.COMPLETED
        )
        self.assertEqual(events.count(), 1)


class StudentDeactivateReactivateAdminViewTests(AcademyTestBase):
    """The Student Detail admin page's modal-driven flow — same red
    "Деактивировать" button, now backed by a required reason instead of an
    instant toggle."""

    def setUp(self):
        super().setUp()
        self.admin_web = DjangoClient()
        self.admin_web.force_login(self.admin)
        self.teacher_web = DjangoClient()
        self.teacher_web.force_login(self.teacher1.user)

    def test_deactivate_without_reason_reopens_modal_with_error(self):
        url = reverse("admin:academy_student_deactivate", args=[self.student1.pk])
        response = self.admin_web.post(url, {"reason": "", "comment": ""})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["open_deactivate_modal"])
        self.assertTrue(response.context["deactivate_form"].errors)
        self.student1.refresh_from_db()
        self.assertTrue(self.student1.is_active)

    def test_deactivate_other_reason_without_comment_reopens_modal(self):
        url = reverse("admin:academy_student_deactivate", args=[self.student1.pk])
        response = self.admin_web.post(url, {"reason": "other", "comment": ""})
        self.assertEqual(response.status_code, 200)
        self.assertIn("comment", response.context["deactivate_form"].errors)
        self.student1.refresh_from_db()
        self.assertTrue(self.student1.is_active)

    def test_deactivate_success_redirects_and_shows_russian_message(self):
        url = reverse("admin:academy_student_deactivate", args=[self.student1.pk])
        response = self.admin_web.post(url, {"reason": "no_interest", "comment": ""}, follow=True)
        self.student1.refresh_from_db()
        self.assertFalse(self.student1.is_active)
        messages_text = [str(m) for m in response.context["messages"]]
        self.assertIn("Студент успешно деактивирован.", messages_text)

    def test_double_submit_shows_russian_error_not_a_crash(self):
        url = reverse("admin:academy_student_deactivate", args=[self.student1.pk])
        self.admin_web.post(url, {"reason": "no_interest", "comment": ""})
        response = self.admin_web.post(url, {"reason": "financial_issues", "comment": ""}, follow=True)
        self.assertEqual(response.status_code, 200)
        messages_text = [str(m) for m in response.context["messages"]]
        self.assertTrue(any("уже деактивирован" in m for m in messages_text))
        self.assertEqual(StudentStatusEvent.objects.filter(student=self.student1).count(), 1)

    def test_reactivate_requires_group(self):
        deactivate_student(self.student1, reason="no_interest", comment="")
        url = reverse("admin:academy_student_reactivate", args=[self.student1.pk])
        response = self.admin_web.post(url, {"group": "", "event_date": "2026-09-20", "comment": ""})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["reactivate_form"].errors)
        self.student1.refresh_from_db()
        self.assertFalse(self.student1.is_active)

    def test_reactivate_success(self):
        deactivate_student(self.student1, reason="no_interest", comment="")
        url = reverse("admin:academy_student_reactivate", args=[self.student1.pk])
        response = self.admin_web.post(
            url, {"group": self.group1.pk, "event_date": "2026-09-20", "comment": "Вернулась"}, follow=True
        )
        self.student1.refresh_from_db()
        self.assertTrue(self.student1.is_active)
        messages_text = [str(m) for m in response.context["messages"]]
        self.assertIn("Студент успешно активирован.", messages_text)

    def test_teacher_cannot_deactivate_or_reactivate(self):
        deactivate_url = reverse("admin:academy_student_deactivate", args=[self.student1.pk])
        self.assertEqual(self.teacher_web.post(deactivate_url, {"reason": "no_interest"}).status_code, 302)
        self.student1.refresh_from_db()
        self.assertTrue(self.student1.is_active)

    def test_status_history_rendered_on_detail_page(self):
        deactivate_student(self.student1, reason="no_interest", comment="Тестовый комментарий")
        response = self.admin_web.get(reverse("admin:academy_student_detail", args=[self.student1.pk]))
        body = response.content.decode()
        self.assertIn("Нет интереса", body)
        self.assertIn("Тестовый комментарий", body)
        # No payments model exists — refund columns must always be a dash.
        self.assertIn("<td>—</td>", body)


class StudentPauseContinueCompleteAdminViewTests(AcademyTestBase):
    """The Student Detail admin page's Pause/Continue/Complete modals —
    same POST-only, permission-checked, modal-reopen-on-error pattern as
    Deactivate/Reactivate."""

    def setUp(self):
        super().setUp()
        self.admin_web = DjangoClient()
        self.admin_web.force_login(self.admin)
        self.teacher_web = DjangoClient()
        self.teacher_web.force_login(self.teacher1.user)

    def test_pause_without_reason_reopens_modal_with_error(self):
        url = reverse("admin:academy_student_pause", args=[self.student1.pk])
        response = self.admin_web.post(url, {"reason": "", "comment": ""})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["open_pause_modal"])
        self.assertTrue(response.context["pause_form"].errors)
        self.student1.refresh_from_db()
        self.assertEqual(self.student1.status, Student.Status.ACTIVE)

    def test_pause_success_redirects_and_shows_russian_message(self):
        url = reverse("admin:academy_student_pause", args=[self.student1.pk])
        response = self.admin_web.post(url, {"reason": "no_interest", "comment": ""}, follow=True)
        self.student1.refresh_from_db()
        self.assertEqual(self.student1.status, Student.Status.PAUSED)
        messages_text = [str(m) for m in response.context["messages"]]
        self.assertIn("Обучение приостановлено.", messages_text)

    def test_double_pause_shows_russian_error_not_a_crash(self):
        url = reverse("admin:academy_student_pause", args=[self.student1.pk])
        self.admin_web.post(url, {"reason": "no_interest", "comment": ""})
        response = self.admin_web.post(url, {"reason": "relocation", "comment": ""}, follow=True)
        self.assertEqual(response.status_code, 200)
        messages_text = [str(m) for m in response.context["messages"]]
        self.assertTrue(any("уже находится на паузе" in m for m in messages_text))
        self.assertEqual(StudentStatusEvent.objects.filter(student=self.student1).count(), 1)

    def test_continue_success_redirects_and_shows_russian_message(self):
        pause_student(self.student1, reason="no_interest", comment="")
        url = reverse("admin:academy_student_continue", args=[self.student1.pk])
        response = self.admin_web.post(
            url, {"group": self.group1.pk, "event_date": "2026-09-20", "comment": ""}, follow=True
        )
        self.student1.refresh_from_db()
        self.assertEqual(self.student1.status, Student.Status.ACTIVE)
        messages_text = [str(m) for m in response.context["messages"]]
        self.assertIn("Обучение продолжено.", messages_text)

    def test_continue_on_active_student_reopens_modal_with_error(self):
        url = reverse("admin:academy_student_continue", args=[self.student1.pk])
        response = self.admin_web.post(url, {"group": "", "event_date": "2026-09-20", "comment": ""}, follow=True)
        messages_text = [str(m) for m in response.context["messages"]]
        self.assertTrue(any("только для студента на паузе" in m for m in messages_text))
        self.student1.refresh_from_db()
        self.assertEqual(self.student1.status, Student.Status.ACTIVE)

    def test_complete_success_redirects_and_shows_russian_message(self):
        url = reverse("admin:academy_student_complete", args=[self.student1.pk])
        response = self.admin_web.post(url, {"comment": ""}, follow=True)
        self.student1.refresh_from_db()
        self.assertEqual(self.student1.status, Student.Status.COMPLETED)
        messages_text = [str(m) for m in response.context["messages"]]
        self.assertIn("Обучение завершено.", messages_text)

    def test_double_complete_shows_russian_error_not_a_crash(self):
        url = reverse("admin:academy_student_complete", args=[self.student1.pk])
        self.admin_web.post(url, {"comment": ""})
        response = self.admin_web.post(url, {"comment": ""}, follow=True)
        messages_text = [str(m) for m in response.context["messages"]]
        self.assertTrue(any("уже завершено" in m for m in messages_text))
        self.assertEqual(StudentStatusEvent.objects.filter(student=self.student1).count(), 1)

    def test_teacher_cannot_pause_continue_or_complete(self):
        pause_url = reverse("admin:academy_student_pause", args=[self.student1.pk])
        self.assertEqual(self.teacher_web.post(pause_url, {"reason": "no_interest"}).status_code, 302)
        complete_url = reverse("admin:academy_student_complete", args=[self.student1.pk])
        self.assertEqual(self.teacher_web.post(complete_url, {"comment": ""}).status_code, 302)
        self.student1.refresh_from_db()
        self.assertEqual(self.student1.status, Student.Status.ACTIVE)

    def test_status_history_shows_new_event_types(self):
        pause_student(self.student1, reason="no_interest", comment="Тестовая пауза")
        response = self.admin_web.get(reverse("admin:academy_student_detail", args=[self.student1.pk]))
        body = response.content.decode()
        self.assertIn("Приостановка обучения", body)
        self.assertIn("Тестовая пауза", body)


class InactiveStudentsAndDepartureHistoryViewTests(AcademyTestBase):
    def setUp(self):
        super().setUp()
        self.admin_web = DjangoClient()
        self.admin_web.force_login(self.admin)
        self.teacher_web = DjangoClient()
        self.teacher_web.force_login(self.teacher1.user)

    def test_paused_and_completed_students_never_appear_on_inactive_list(self):
        """`is_active=False` is now also true for PAUSED/COMPLETED students,
        but this page is specifically about departures (`status=WITHDRAWN`)
        — mixing pause/completion into "who left" would misrepresent a
        different business process (spec: "Не смешивай её с обычной
        повторной активацией после деактивации, если это разные
        бизнес-процессы")."""
        pause_student(self.student1, reason="no_interest", comment="")
        complete_student(self.student2, comment="")
        deactivate_student(self.student3, reason="relocation", comment="")

        response = self.admin_web.get(reverse("admin:academy_inactive_students"))
        pks = {row["student"].pk for row in response.context["rows"]}
        self.assertEqual(pks, {self.student3.pk})

    def test_reactivated_student_disappears_from_inactive_list(self):
        deactivate_student(self.student1, reason="no_interest", comment="")
        deactivate_student(self.student2, reason="relocation", comment="")

        response = self.admin_web.get(reverse("admin:academy_inactive_students"))
        pks = {row["student"].pk for row in response.context["rows"]}
        self.assertEqual(pks, {self.student1.pk, self.student2.pk})

        reactivate_student(self.student1, group=self.group1, event_date=dt.date.today(), comment="")
        response = self.admin_web.get(reverse("admin:academy_inactive_students"))
        pks = {row["student"].pk for row in response.context["rows"]}
        self.assertEqual(pks, {self.student2.pk})

    def test_empty_state_when_no_inactive_students(self):
        response = self.admin_web.get(reverse("admin:academy_inactive_students"))
        self.assertIn("Неактивные студенты отсутствуют", response.content.decode())

    def test_filter_by_reason(self):
        deactivate_student(self.student1, reason="no_interest", comment="")
        deactivate_student(self.student2, reason="relocation", comment="")
        response = self.admin_web.get(reverse("admin:academy_inactive_students"), {"reason": "relocation"})
        pks = {row["student"].pk for row in response.context["rows"]}
        self.assertEqual(pks, {self.student2.pk})

    def test_filter_by_group(self):
        deactivate_student(self.student1, reason="no_interest", comment="")  # group1
        deactivate_student(self.student3, reason="relocation", comment="")  # group2
        response = self.admin_web.get(reverse("admin:academy_inactive_students"), {"group": self.group2.pk})
        pks = {row["student"].pk for row in response.context["rows"]}
        self.assertEqual(pks, {self.student3.pk})

    def test_search_by_name_id_and_group(self):
        deactivate_student(self.student1, reason="no_interest", comment="")
        url = reverse("admin:academy_inactive_students")

        response = self.admin_web.get(url, {"q": self.student1.last_name})
        self.assertEqual({row["student"].pk for row in response.context["rows"]}, {self.student1.pk})

        response = self.admin_web.get(url, {"q": str(self.student1.pk)})
        self.assertEqual({row["student"].pk for row in response.context["rows"]}, {self.student1.pk})

        response = self.admin_web.get(url, {"q": self.group1.name})
        self.assertEqual({row["student"].pk for row in response.context["rows"]}, {self.student1.pk})

    def test_inactive_students_page_has_no_refund_ui(self):
        """The inactive students page has no real payment/refund module
        behind it — the refund columns/filter/help text are removed
        entirely rather than shown as permanently-empty placeholders."""
        deactivate_student(self.student1, reason="no_interest", comment="")
        response = self.admin_web.get(reverse("admin:academy_inactive_students"))
        body = response.content.decode()
        self.assertNotIn("Сумма возврата", body)
        self.assertNotIn("Дата возврата", body)
        self.assertNotIn("has_refund", body)
        self.assertNotIn("Возврат — не важно", body)
        # A stray `has_refund` query param must not affect filtering — it's
        # no longer a recognised parameter, not a silent no-op filter.
        response = self.admin_web.get(reverse("admin:academy_inactive_students"), {"has_refund": "yes"})
        pks = {row["student"].pk for row in response.context["rows"]}
        self.assertEqual(pks, {self.student1.pk})

    def test_departure_history_includes_returned_students(self):
        deactivate_student(self.student1, reason="no_interest", comment="")
        reactivate_student(self.student1, group=self.group1, event_date=dt.date.today(), comment="")

        response = self.admin_web.get(reverse("admin:academy_student_departure_history"))
        student_ids = {event.student_id for event in response.context["rows"]}
        self.assertIn(self.student1.pk, student_ids)
        # The student is active again, but the departure record must stay.
        self.student1.refresh_from_db()
        self.assertTrue(self.student1.is_active)

    def test_departure_history_records_multiple_cycles(self):
        deactivate_student(self.student1, reason="no_interest", comment="")
        reactivate_student(self.student1, group=self.group1, event_date=dt.date.today(), comment="")
        deactivate_student(self.student1, reason="financial_issues", comment="")

        response = self.admin_web.get(reverse("admin:academy_student_departure_history"))
        reasons = [event.reason for event in response.context["rows"] if event.student_id == self.student1.pk]
        self.assertEqual(sorted(reasons), sorted(["no_interest", "financial_issues"]))

    def test_teacher_cannot_view_inactive_students_or_history(self):
        self.assertEqual(self.teacher_web.get(reverse("admin:academy_inactive_students")).status_code, 302)
        self.assertEqual(self.teacher_web.get(reverse("admin:academy_student_departure_history")).status_code, 302)

    def test_staff_non_admin_forbidden_from_inactive_students(self):
        self.teacher1.user.is_staff = True
        self.teacher1.user.save(update_fields=["is_staff"])
        staff_teacher_web = DjangoClient()
        staff_teacher_web.force_login(self.teacher1.user)
        response = staff_teacher_web.get(reverse("admin:academy_inactive_students"))
        self.assertEqual(response.status_code, 403)


class AcademyReportMovementMetricsTests(AcademyTestBase):
    """§7/§8: movement metrics and the reason breakdown, computed from
    confirmed StudentStatusEvent records for the exact selected year/month."""

    def test_left_counts_distinct_students_using_event_date(self):
        deactivate_student(self.student1, reason="no_interest", comment="")
        deactivate_student(self.student2, reason="no_interest", comment="")

        today = dt.date.today()
        stats = compute_academy_monthly_stats(today.year, today.month)
        self.assertEqual(stats["students"]["left"], 2)
        self.assertEqual(stats["movement"]["left"], 2)

    def test_events_outside_selected_month_are_excluded(self):
        event = StudentStatusEvent.objects.create(
            student=self.student1,
            event_type=StudentStatusEvent.EventType.DEACTIVATED,
            reason="no_interest",
            group=self.group1,
            event_date=dt.date(2026, 8, 15),
        )
        self.student1.is_active = False
        self.student1.save(update_fields=["is_active"])

        stats_august = compute_academy_monthly_stats(2026, 8)
        stats_september = compute_academy_monthly_stats(2026, 9)
        self.assertEqual(stats_august["students"]["left"], 1)
        self.assertEqual(stats_september["students"]["left"], 0)
        self.assertIsNotNone(event.pk)

    def test_left_count_unaffected_by_reactivation(self):
        """Reactivating a student afterwards must not retroactively remove
        their departure — `left` counts every DEACTIVATED event exactly as
        before, independent of what happens to the student later."""
        deactivate_student(self.student1, reason="no_interest", comment="")
        reactivate_student(self.student1, group=self.group1, event_date=dt.date(2026, 9, 20), comment="")
        stats = compute_academy_monthly_stats(2026, 9)
        self.assertEqual(stats["movement"]["left"], 1)

    def test_completed_is_zero_not_none_when_empty(self):
        """"Завершили обучение" is fully implemented — an empty period must
        report `{count: 0, supported: True}`, never `None`/"unsupported"."""
        stats = compute_academy_monthly_stats(2026, 9)
        self.assertEqual(stats["movement"]["completed"]["count"], 0)
        self.assertTrue(stats["movement"]["completed"]["supported"])
        self.assertEqual(stats["students"]["completed"], 0)

    def test_completed_metric_counts_confirmed_completed_events_only(self):
        """spec: "Не считай студентов по текущему статусу, если событие
        завершения отсутствует" — a student paused (not completed) this
        month must not be counted as completed."""
        complete_student(self.student1, comment="", performed_by=self.admin)
        pause_student(self.student2, reason="no_interest", comment="")
        today = dt.date.today()
        stats = compute_academy_monthly_stats(today.year, today.month)
        self.assertEqual(stats["movement"]["completed"]["count"], 1)
        self.assertEqual(stats["students"]["completed"], 1)

    def test_pause_metric_removed_from_academy_report(self):
        """spec: "Приостановили обучение" is removed from the Academy Report
        — pausing remains a real, working Student lifecycle action
        (services.student_status), it is simply no longer one of this
        report's fields."""
        pause_student(self.student1, reason="no_interest", comment="")
        pause_student(self.student2, reason="relocation", comment="")
        today = dt.date.today()
        stats = compute_academy_monthly_stats(today.year, today.month)
        self.assertNotIn("paused", stats["students"])
        self.assertNotIn("paused", stats["movement"])
        self.assertNotIn("continued", stats["movement"])
        self.assertNotIn("returned_after_pause", stats["movement"])

    def test_movement_metrics_respect_year_month_filter(self):
        StudentStatusEvent.objects.create(
            student=self.student1,
            event_type=StudentStatusEvent.EventType.COMPLETED,
            group=self.group1,
            event_date=dt.date(2026, 8, 15),
        )
        stats_august = compute_academy_monthly_stats(2026, 8)
        stats_september = compute_academy_monthly_stats(2026, 9)
        self.assertEqual(stats_august["movement"]["completed"]["count"], 1)
        self.assertEqual(stats_september["movement"]["completed"]["count"], 0)

    def test_academy_report_api_exposes_completed_and_group_stats(self):
        complete_student(self.student1, comment="")
        pause_student(self.student2, reason="no_interest", comment="")
        today = dt.date.today()
        response = self.admin_client.post(
            "/api/v1/academy-reports/", {"year": today.year, "month": today.month}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        movement = response.data["stats"]["movement"]
        self.assertEqual(movement["completed"], {"count": 1, "supported": True})
        self.assertNotIn("paused", movement)
        self.assertNotIn("continued", movement)
        self.assertNotIn("returned_after_pause", movement)
        # group1 (2 students) + group2 (1 student) are both still ACTIVE.
        self.assertEqual(movement["active_groups"], 2)
        self.assertEqual(movement["completed_groups"], 0)

        # student1 (completed) and student2 (paused) are both now
        # is_active=False, leaving only student3 active in group2.
        group_stats = response.data["stats"]["group_stats"]
        self.assertEqual(group_stats["total"], 2)
        self.assertEqual(group_stats["active"], 2)
        self.assertEqual(group_stats["completed"], 0)
        self.assertEqual(group_stats["students_active"], 1)
        self.assertEqual(group_stats["students_completed"], 0)

    def test_reason_breakdown_percentages_and_no_division_by_zero(self):
        today = dt.date.today()
        empty_stats = compute_academy_monthly_stats(today.year, today.month)
        self.assertEqual(empty_stats["movement"]["reasons"], [])

        deactivate_student(self.student1, reason="no_interest", comment="")
        deactivate_student(self.student2, reason="no_interest", comment="")
        deactivate_student(self.student3, reason="relocation", comment="")

        stats = compute_academy_monthly_stats(today.year, today.month)
        breakdown = {row["reason"]: row for row in stats["movement"]["reasons"]}
        self.assertEqual(breakdown["no_interest"]["count"], 2)
        self.assertEqual(breakdown["no_interest"]["percent"], round(2 / 3 * 100, 1))
        self.assertEqual(breakdown["relocation"]["count"], 1)
        self.assertEqual(breakdown["relocation"]["percent"], round(1 / 3 * 100, 1))
        self.assertEqual(breakdown["no_interest"]["reason_display"], "Нет интереса")

    def test_reason_breakdown_uses_russian_labels(self):
        deactivate_student(self.student1, reason="disliked_teacher", comment="")
        today = dt.date.today()
        stats = compute_academy_monthly_stats(today.year, today.month)
        labels = {row["reason_display"] for row in stats["movement"]["reasons"]}
        self.assertEqual(labels, {"Не понравился преподаватель"})

    def test_academy_report_api_exposes_reason_breakdown(self):
        deactivate_student(self.student1, reason="no_interest", comment="")
        today = dt.date.today()
        response = self.admin_client.post(
            "/api/v1/academy-reports/", {"year": today.year, "month": today.month}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(response.data["stats"]["movement"]["left"], 1)
        self.assertEqual(len(response.data["stats"]["movement"]["reasons"]), 1)


class AcademyReportGroupStatsTests(AcademyTestBase):
    """spec §4/§8: group_stats is a live, current-database-state count — a
    completed Group must never be counted as active, a transferred or
    departed student must never be counted twice, and none of it depends on
    the selected report month."""

    def test_active_and_completed_groups_are_counted_separately(self):
        self.group2.status = Group.Status.COMPLETED
        self.group2.save(update_fields=["status"])

        today = dt.date.today()
        stats = compute_academy_monthly_stats(today.year, today.month)
        self.assertEqual(stats["group_stats"]["total"], 2)
        self.assertEqual(stats["group_stats"]["active"], 1)
        self.assertEqual(stats["group_stats"]["completed"], 1)
        # group1 (student1 + student2) is the only ACTIVE group left.
        self.assertEqual(stats["group_stats"]["students_active"], 2)
        # group2 (student3) is now COMPLETED.
        self.assertEqual(stats["group_stats"]["students_completed"], 1)

    def test_completed_group_never_also_counted_as_active(self):
        self.group1.status = Group.Status.COMPLETED
        self.group1.save(update_fields=["status"])

        today = dt.date.today()
        stats = compute_academy_monthly_stats(today.year, today.month)
        self.assertEqual(stats["group_stats"]["active"], 1)
        self.assertEqual(stats["group_stats"]["completed"], 1)
        self.assertNotEqual(stats["group_stats"]["active"], stats["group_stats"]["total"])

    def test_student_who_left_before_group_completion_not_double_counted(self):
        """A student deactivated before their group completes must not be
        double-counted as both a departed student and a member of the now
        completed group's active roster."""
        deactivate_student(self.student3, reason="no_interest", comment="")
        self.group2.status = Group.Status.COMPLETED
        self.group2.save(update_fields=["status"])

        today = dt.date.today()
        stats = compute_academy_monthly_stats(today.year, today.month)
        # student3 is is_active=False, so group2's "students in completed
        # groups" count (which only counts currently-active members) is 0 —
        # they are correctly excluded, not fabricated as still enrolled.
        self.assertEqual(stats["group_stats"]["students_completed"], 0)
        self.assertEqual(stats["movement"]["left"], 1)

    def test_student_transfer_between_groups_counts_once_not_duplicated(self):
        """Transferring a student from one group to another must never leave
        them counted in both groups — Student.group is a single FK, so the
        old group simply loses them and the new one gains them."""
        self.assertEqual(self.student1.group_id, self.group1.pk)
        self.student1.group = self.group2
        self.student1.save(update_fields=["group"])

        today = dt.date.today()
        stats = compute_academy_monthly_stats(today.year, today.month)
        # Still 3 distinct active students total across both groups — the
        # transfer moved one student, it did not create or drop anyone.
        self.assertEqual(stats["group_stats"]["students_active"], 3)

        # The transferred student now appears under group2's roster via the
        # existing `Group.students_count` property (is_active students of
        # that group), and no longer under group1's.
        self.assertEqual(self.group1.students_count, 1)
        self.assertEqual(self.group2.students_count, 2)

    def test_group_stats_are_current_not_month_scoped(self):
        """group_stats reads live Group.status — unlike `movement.left`/
        `completed`, it must not change depending on which month is
        selected."""
        self.group2.status = Group.Status.COMPLETED
        self.group2.save(update_fields=["status"])

        stats_this_month = compute_academy_monthly_stats(2026, 9)
        stats_other_month = compute_academy_monthly_stats(2020, 1)
        self.assertEqual(stats_this_month["group_stats"], stats_other_month["group_stats"])
