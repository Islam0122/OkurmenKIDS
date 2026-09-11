from __future__ import annotations

import datetime as dt
from unittest import mock

from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection
from django.test import Client as DjangoClient
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
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
    Room,
    Student,
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
from apps.academy.services.group_schedule_conflicts import (
    find_group_teacher_conflict,
    find_schedule_room_conflict,
    find_schedule_teacher_conflict,
)
from apps.academy.services.group_schedule_sync import sync_legacy_group_schedule
from apps.academy.services.homework_service import bulk_upsert_homework_results
from apps.academy.services.lesson_generator import LessonGenerationError, generate_lessons_for_group
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

    def test_group_capacity_cannot_exceed_room(self):
        response = self.admin_client.post(
            "/api/v1/groups/",
            {
                "name": "Too big", "course": self.course.id, "teacher": self.teacher1.id, "room": self.room2.id,
                "start_date": "2026-09-07", "start_time": "10:00", "end_time": "11:00",
                "days_of_week": ["mon"], "max_students": 99,
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

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


class GroupRoomConflictTests(AcademyTestBase):
    """group1 already occupies room1 on Mon/Wed 15:00-16:30 (see AcademyTestBase.setUp)."""

    def _create(self, **overrides):
        payload = {
            "name": "New Group",
            "course": self.course.id,
            "teacher": self.teacher2.id,
            "room": self.room1.id,
            "start_date": "2026-09-07",
            "start_time": "15:30",
            "end_time": "17:00",
            "days_of_week": ["mon"],
        }
        payload.update(overrides)
        return self.admin_client.post("/api/v1/groups/", payload, format="json")

    def test_overlapping_room_day_and_time_rejected(self):
        response = self._create()
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("room", response.data)

    def test_same_room_different_day_allowed(self):
        response = self._create(days_of_week=["tue"])
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)

    def test_same_room_non_overlapping_time_allowed(self):
        response = self._create(start_time="09:00", end_time="10:00")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)

    def test_different_room_same_day_and_time_allowed(self):
        response = self._create(room=self.room2.id)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)

    def test_cancelled_group_does_not_block_room(self):
        self.group1.status = Group.Status.CANCELLED
        self.group1.save(update_fields=["status"])
        response = self._create()
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)

    def test_editing_group_to_conflict_rejected(self):
        # group2 is room2/Tue,Thu 17:00-18:30 — moving it onto group1's own
        # room1/Mon slot must be rejected too, not just on create.
        response = self.admin_client.patch(
            f"/api/v1/groups/{self.group2.id}/",
            {"room": self.room1.id, "days_of_week": ["mon"], "start_time": "15:00", "end_time": "16:30"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("room", response.data)

    def test_editing_group_without_touching_its_own_schedule_not_blocked_by_itself(self):
        # Re-saving group1's own unchanged schedule must not conflict with itself.
        response = self.admin_client.patch(
            f"/api/v1/groups/{self.group1.id}/", {"description": "updated"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)

    def test_model_clean_also_rejects_conflict(self):
        # Admin's ModelForm validates via full_clean(), not the DRF serializer —
        # the same rule must hold there too.
        conflicting = Group(
            name="Model-level conflict",
            course=self.course,
            teacher=self.teacher2,
            room=self.room1,
            start_date=dt.date(2026, 9, 7),
            start_time=dt.time(15, 30),
            end_time=dt.time(17, 0),
            days_of_week=["mon"],
        )
        with self.assertRaises(Exception):
            conflicting.full_clean()

    def test_open_ended_group_conflicts_with_future_dated_group(self):
        # group1 has no end_date (open-ended) — a new group starting well in
        # the future, same room/day/time, must still be seen as overlapping.
        response = self._create(start_date="2027-01-04")  # a Monday
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("room", response.data)


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

    def test_group_level_teacher_conflict_helper(self):
        conflict = find_group_teacher_conflict(
            teacher=self.teacher1, days_of_week=["mon"], start_time=dt.time(15, 30), end_time=dt.time(16, 0),
            start_date=dt.date(2026, 9, 7),
        )
        self.assertIsNotNone(conflict)

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

    def test_group_change_page_renders_teaching_programs_summary(self):
        response = self.django_admin_client.get(f"/admin/academy/group/{self.group1.id}/change/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        body = response.content.decode()
        self.assertIn("Открыть рабочее пространство", body)
        self.assertIn("Свой план", body)
        self.assertIn("Общий план курса", body)

    def test_group_change_page_renders_group_summary_and_capacity(self):
        response = self.django_admin_client.get(f"/admin/academy/group/{self.group1.id}/change/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        body = response.content.decode()
        self.assertIn("Сводка группы", body)
        self.assertIn("Ближайшие занятия", body)
        self.assertIn("Выбрано студентов", body)

    def test_add_group_page_shows_helpful_pre_save_message(self):
        response = self.django_admin_client.get("/admin/academy/group/add/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        body = response.content.decode()
        self.assertIn("Сначала сохраните группу, затем добавьте учебные программы", body)

    def test_legacy_fieldset_has_warning_and_readonly_fields(self):
        response = self.django_admin_client.get(f"/admin/academy/group/{self.group1.id}/change/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        body = response.content.decode()
        self.assertIn("Поля для обратной совместимости", body)
        self.assertIn("сохранены только для совместимости", body)
        # Legacy fields are rendered read-only (no editable widget for
        # them) — group1's legacy teacher/room are shown as plain text, not
        # an `id="id_<field>"` input/select (unlike GroupScheduleInline's
        # own per-row teacher/room fields, which use a "schedules-0-…" id
        # and must stay editable).
        self.assertNotIn('id="id_teacher"', body)
        self.assertNotIn('id="id_room"', body)
        self.assertNotIn('id="id_start_time"', body)
        self.assertNotIn('id="id_end_time"', body)

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
        response = self.django_admin_client.get(f"/admin/academy/group/{self.group1.id}/change/")
        body = response.content.decode()
        self.assertNotIn("основной", body.lower())
        self.assertNotIn("(main)", body.lower())

    def test_schedule_inline_shows_every_row_including_legacy_origin_ones(self):
        # Previously the legacy-mirrored (subject=None) row was hidden from
        # this inline; now every GroupSchedule row of the group is an equal,
        # editable row here — no row is special-cased out.
        response = self.django_admin_client.get(f"/admin/academy/group/{self.group1.id}/change/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        formset_data = response.context["inline_admin_formsets"][0].formset
        schedule_ids = {form.instance.pk for form in formset_data.forms if form.instance.pk}
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
        response = self.django_admin_client.get(f"/admin/academy/group/{self.group1.id}/change/")
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
