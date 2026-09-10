from __future__ import annotations

import datetime as dt

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client as DjangoClient
from django.test import TestCase
from django.urls import reverse
from rest_framework import status
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
    Homework,
    HomeworkResult,
    Lesson,
    Room,
    Student,
)
from apps.academy.services.analytics import AnalyticsService
from apps.academy.services.attendance_service import bulk_mark_attendance
from apps.academy.services.group_schedule_conflicts import (
    find_group_teacher_conflict,
    find_schedule_room_conflict,
    find_schedule_teacher_conflict,
)
from apps.academy.services.group_schedule_sync import sync_legacy_group_schedule
from apps.academy.services.homework_service import bulk_upsert_homework_results
from apps.academy.services.lesson_generator import LessonGenerationError, generate_lessons_for_group

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
        response = self.admin_client.get("/api/v1/academy/groups/")
        self.assertEqual(response.data["count"], 2)

    def test_teacher_sees_only_own_groups(self):
        response = self.teacher1_client.get("/api/v1/academy/groups/")
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["name"], "Python Beginner")

    def test_teacher_cannot_access_other_teachers_group(self):
        response = self.teacher1_client.get(f"/api/v1/academy/groups/{self.group2.id}/")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_teacher_cannot_write_group(self):
        response = self.teacher1_client.patch(
            f"/api/v1/academy/groups/{self.group1.id}/", {"name": "Hacked"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_group_requires_days_of_week(self):
        response = self.admin_client.post(
            "/api/v1/academy/groups/",
            {
                "name": "No days", "course": self.course.id, "teacher": self.teacher1.id,
                "start_date": "2026-09-07", "start_time": "10:00", "end_time": "11:00",
                "days_of_week": [],
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_group_capacity_cannot_exceed_room(self):
        response = self.admin_client.post(
            "/api/v1/academy/groups/",
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
            "/api/v1/academy/groups/",
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
        return self.admin_client.post("/api/v1/academy/groups/", payload, format="json")

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
            f"/api/v1/academy/groups/{self.group2.id}/",
            {"room": self.room1.id, "days_of_week": ["mon"], "start_time": "15:00", "end_time": "16:30"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("room", response.data)

    def test_editing_group_without_touching_its_own_schedule_not_blocked_by_itself(self):
        # Re-saving group1's own unchanged schedule must not conflict with itself.
        response = self.admin_client.patch(
            f"/api/v1/academy/groups/{self.group1.id}/", {"description": "updated"}, format="json"
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
        response = self.admin_client.get("/api/v1/academy/rooms/available/")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_free_slot_lists_all_active_rooms_available(self):
        response = self.admin_client.get(
            "/api/v1/academy/rooms/available/",
            {"date": "2026-09-07", "start_time": "09:00", "end_time": "10:00"},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        available_ids = {room["id"] for room in response.data["available"]}
        self.assertEqual(available_ids, {self.room1.id, self.room2.id})
        self.assertEqual(response.data["occupied"], [])

    def test_occupied_room_excluded_and_reported(self):
        # 2026-09-07 is a Monday — group1's lesson there runs 15:00-16:30 in room1.
        response = self.admin_client.get(
            "/api/v1/academy/rooms/available/",
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
            "/api/v1/academy/rooms/available/",
            {"date": "2026-09-07", "start_time": "13:00", "end_time": "15:00"},
        )
        available_ids = {room["id"] for room in response.data["available"]}
        self.assertIn(self.room1.id, available_ids)

    def test_cancelled_lesson_never_occupies_room(self):
        lesson = Lesson.objects.filter(group=self.group1, date=dt.date(2026, 9, 7)).first()
        lesson.status = Lesson.Status.CANCELLED
        lesson.save(update_fields=["status"])

        response = self.admin_client.get(
            "/api/v1/academy/rooms/available/",
            {"date": "2026-09-07", "start_time": "15:15", "end_time": "16:00"},
        )
        available_ids = {room["id"] for room in response.data["available"]}
        self.assertIn(self.room1.id, available_ids)


class GroupScheduleEndpointTests(AcademyTestBase):
    def test_returns_group_and_dated_lessons_with_weekday(self):
        response = self.admin_client.get(f"/api/v1/academy/groups/{self.group1.id}/schedule/")
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
        response = self.teacher1_client.get(f"/api/v1/academy/groups/{self.group1.id}/schedule/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_teacher_cannot_see_other_teachers_group_schedule(self):
        response = self.teacher1_client.get(f"/api/v1/academy/groups/{self.group2.id}/schedule/")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_status_filter(self):
        lesson = Lesson.objects.filter(group=self.group1).first()
        lesson.status = Lesson.Status.CANCELLED
        lesson.save(update_fields=["status"])

        response = self.admin_client.get(
            f"/api/v1/academy/groups/{self.group1.id}/schedule/", {"status": "cancelled"}
        )
        self.assertEqual(len(response.data["lessons"]), 1)
        self.assertEqual(response.data["lessons"][0]["id"], lesson.id)


class GroupStudentsEndpointTests(AcademyTestBase):
    def test_returns_active_students_of_the_group(self):
        response = self.admin_client.get(f"/api/v1/academy/groups/{self.group1.id}/students/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        names = {row["full_name"] for row in response.data}
        self.assertEqual(names, {"Алина Иванова", "Мансур Алиев"})

    def test_inactive_student_excluded_by_default(self):
        self.student1.is_active = False
        self.student1.save(update_fields=["is_active"])
        response = self.admin_client.get(f"/api/v1/academy/groups/{self.group1.id}/students/")
        names = {row["full_name"] for row in response.data}
        self.assertEqual(names, {"Мансур Алиев"})

    def test_teacher_can_see_own_group_students(self):
        response = self.teacher1_client.get(f"/api/v1/academy/groups/{self.group1.id}/students/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 2)

    def test_teacher_cannot_see_other_teachers_group_students(self):
        response = self.teacher1_client.get(f"/api/v1/academy/groups/{self.group2.id}/students/")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class StudentTests(AcademyTestBase):
    def test_admin_sees_all_students(self):
        response = self.admin_client.get("/api/v1/academy/students/")
        self.assertEqual(response.data["count"], 3)

    def test_teacher_sees_only_own_groups_students(self):
        response = self.teacher1_client.get("/api/v1/academy/students/")
        self.assertEqual(response.data["count"], 2)
        names = {row["first_name"] for row in response.data["results"]}
        self.assertEqual(names, {"Алина", "Мансур"})


class LessonGenerationTests(AcademyTestBase):
    """Group creation (in AcademyTestBase.setUp) already triggers automatic
    generation via the `post_save` signal — see apps.academy.signals — so
    group1/group2 arrive with their lessons already made. Tests here either
    inspect that already-generated state, or spin up a fresh Group to
    observe generation happening from a clean slate.
    """

    def test_group_creation_automatically_generates_lessons(self):
        """The core new-workflow guarantee: Admin never has to click anything."""
        group = Group.objects.create(
            name="Auto-generated group",
            course=self.course,
            teacher=self.teacher1,
            room=self.room1,
            start_date=dt.date(2026, 9, 7),
            start_time=dt.time(9, 0),
            end_time=dt.time(10, 30),
            days_of_week=["mon", "wed"],
        )
        lessons = list(Lesson.objects.filter(group=group).order_by("lesson_number"))
        self.assertEqual(len(lessons), 4)
        self.assertEqual(
            [lesson.date for lesson in lessons],
            [dt.date(2026, 9, 7), dt.date(2026, 9, 9), dt.date(2026, 9, 14), dt.date(2026, 9, 16)],
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
            teacher=self.teacher1,
            room=self.room1,
            start_date=dt.date(2026, 9, 7),
            end_date=dt.date(2026, 9, 10),
            start_time=dt.time(9, 0),
            end_time=dt.time(10, 30),
            days_of_week=["mon", "wed"],
        )
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
        response = self.admin_client.post(f"/api/v1/academy/groups/{self.group1.id}/generate-lessons/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["created_count"], 0)
        self.assertEqual(response.data["first_lesson"], 1)
        self.assertEqual(response.data["last_lesson"], 4)
        self.assertEqual(Lesson.objects.filter(group=self.group1).count(), 4)

    def test_generate_lessons_api_admin_only(self):
        response = self.teacher1_client.post(f"/api/v1/academy/groups/{self.group1.id}/generate-lessons/")
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
            "/api/v1/academy/attendance/",
            {"student": self.student1.id, "lesson": self.lesson1.id, "status": "present"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(response.data["student_name"], "Алина Иванова")

    def test_student_from_other_group_rejected(self):
        response = self.admin_client.post(
            "/api/v1/academy/attendance/",
            {"student": self.student3.id, "lesson": self.lesson1.id, "status": "present"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_duplicate_rejected(self):
        Attendance.objects.create(student=self.student1, lesson=self.lesson1, status="present")
        response = self.admin_client.post(
            "/api/v1/academy/attendance/",
            {"student": self.student1.id, "lesson": self.lesson1.id, "status": "late"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_teacher_isolation_cannot_create_for_other_group(self):
        response = self.teacher1_client.post(
            "/api/v1/academy/attendance/",
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
        get_response = self.teacher1_client.get(f"/api/v1/academy/lessons/{self.lesson1.id}/attendance/")
        self.assertEqual(get_response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(get_response.data), 2)  # full roster, unmarked

        post_response = self.teacher1_client.post(
            f"/api/v1/academy/lessons/{self.lesson1.id}/attendance/",
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
            f"/api/v1/academy/lessons/{self.lesson1.id}/attendance/",
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
            "/api/v1/academy/homeworks/",
            {"lesson": self.lesson1.id, "title": "ДЗ 1", "description": "Решить примеры"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)

    def test_teacher_cannot_create_homework_for_other_lesson(self):
        response = self.teacher1_client.post(
            "/api/v1/academy/homeworks/",
            {"lesson": self.other_lesson.id, "title": "ДЗ 1"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_result_score_out_of_range_rejected(self):
        homework = Homework.objects.create(lesson=self.lesson1, title="ДЗ 1")
        response = self.admin_client.post(
            "/api/v1/academy/homework-results/",
            {"homework": homework.id, "student": self.student1.id, "status": "checked", "score": 11},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_result_wrong_group_student_rejected(self):
        homework = Homework.objects.create(lesson=self.lesson1, title="ДЗ 1")
        response = self.admin_client.post(
            "/api/v1/academy/homework-results/",
            {"homework": homework.id, "student": self.student3.id, "status": "submitted"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_result_uniqueness(self):
        homework = Homework.objects.create(lesson=self.lesson1, title="ДЗ 1")
        HomeworkResult.objects.create(homework=homework, student=self.student1, status="submitted")
        response = self.admin_client.post(
            "/api/v1/academy/homework-results/",
            {"homework": homework.id, "student": self.student1.id, "status": "checked", "score": 5},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_bulk_results_roster_and_grading(self):
        homework = Homework.objects.create(lesson=self.lesson1, title="ДЗ 1")

        get_response = self.teacher1_client.get(f"/api/v1/academy/homeworks/{homework.id}/results/")
        self.assertEqual(get_response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(get_response.data), 2)
        self.assertTrue(all(row["status"] == "not_submitted" for row in get_response.data))

        post_response = self.teacher1_client.post(
            f"/api/v1/academy/homeworks/{homework.id}/results/",
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


class AnalyticsServiceTests(AcademyTestBase):
    """Same fixture the old KPITests used (and the same expected numbers) —
    AnalyticsService must derive the identical figures straight from
    Lesson/Attendance/Homework/HomeworkResult, with nothing persisted."""

    def setUp(self):
        super().setUp()
        # group1's lessons were already generated automatically on creation
        # (see AcademyTestBase.setUp / apps.academy.signals).
        self.lessons = list(Lesson.objects.filter(group=self.group1).order_by("lesson_number"))
        self.date_from = dt.date(2026, 9, 1)
        self.date_to = dt.date(2026, 9, 30)

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
        return AnalyticsService(self.date_from, self.date_to, **kwargs).get_dashboard()

    def test_group_row_matches_old_kpigroup_formula(self):
        dashboard = self._dashboard(group_id=self.group1.id)
        row = dashboard["groups"][0]
        self.assertEqual(row["students"], 2)
        self.assertEqual(row["lessons"], 4)
        self.assertEqual(row["attendance_percent"], 75.0)
        self.assertEqual(row["homework_completion_percent"], 25.0)
        self.assertEqual(row["average_score"], 8.0)

    def test_teacher_row_matches_old_kpiteacher_formula(self):
        dashboard = self._dashboard(teacher_id=self.teacher1.id)
        row = dashboard["teachers"][0]
        self.assertEqual(row["groups"], 1)
        self.assertEqual(row["lessons"], 4)
        self.assertEqual(row["attendance_percent"], 75.0)
        self.assertEqual(row["average_score"], 8.0)

    def test_top_student_row_matches_old_kpistudent_formula(self):
        dashboard = self._dashboard(group_id=self.group1.id)
        row = next(r for r in dashboard["top_students"] if r["id"] == self.student1.id)
        self.assertEqual(row["lessons"], 4)
        self.assertEqual(row["attendance_percent"], 75.0)
        self.assertEqual(row["homework_completion_percent"], 50.0)
        self.assertEqual(row["average_score"], 8.0)

    def test_attendance_section_matches_old_kpiattendance_formula(self):
        dashboard = self._dashboard(group_id=self.group1.id)
        attendance = dashboard["attendance"]
        self.assertEqual(attendance["total"], 4)
        self.assertEqual(attendance["present"], 2)
        self.assertEqual(attendance["absent"], 1)
        self.assertEqual(attendance["late"], 1)
        self.assertEqual(attendance["percent"], 75.0)

    def test_homework_section_matches_old_kpihomework_formula(self):
        dashboard = self._dashboard(group_id=self.group1.id)
        homework = dashboard["homework"]
        self.assertEqual(homework["total_homeworks"], 2)
        self.assertEqual(homework["total_results"], 1)
        self.assertEqual(homework["checked"], 1)
        self.assertEqual(homework["completion_percent"], 100.0)
        self.assertEqual(homework["average_score"], 8.0)

    def test_overview_reflects_group_style_homework_percent(self):
        dashboard = self._dashboard(group_id=self.group1.id)
        overview = dashboard["overview"]
        self.assertEqual(overview["groups"], 1)
        self.assertEqual(overview["teachers"], 1)
        self.assertEqual(overview["students"], 2)
        self.assertEqual(overview["lessons"], 4)
        self.assertEqual(overview["attendance_percent"], 75.0)
        self.assertEqual(overview["homework_completion_percent"], 25.0)
        self.assertEqual(overview["average_score"], 8.0)

    def test_lesson_stats(self):
        dashboard = self._dashboard(group_id=self.group1.id)
        lessons = dashboard["lessons"]
        self.assertEqual(lessons["total"], 4)
        self.assertEqual(lessons["planned"], 4)
        self.assertEqual(lessons["completed"], 0)
        self.assertEqual(lessons["cancelled"], 0)

    def test_charts_carry_the_same_numbers_as_the_tables(self):
        dashboard = self._dashboard(group_id=self.group1.id)
        charts = dashboard["charts"]
        self.assertEqual(charts["group_performance"][0]["attendance_percent"], 75.0)
        self.assertEqual(charts["students_by_group"][0]["students"], 2)
        completed = sum(row["count"] for row in charts["lessons_by_status"] if row["status"] == "planned")
        self.assertEqual(completed, 4)

    def test_group_scoping_excludes_other_groups(self):
        dashboard = self._dashboard(group_id=self.group1.id)
        self.assertEqual(len(dashboard["groups"]), 1)
        self.assertEqual(dashboard["groups"][0]["id"], self.group1.id)

    def test_no_filters_covers_every_group(self):
        dashboard = self._dashboard()
        group_ids = {row["id"] for row in dashboard["groups"]}
        self.assertEqual(group_ids, {self.group1.id, self.group2.id})

    def test_empty_period_returns_zeros_not_errors(self):
        empty_dashboard = AnalyticsService(dt.date(2020, 1, 1), dt.date(2020, 1, 31)).get_dashboard()
        self.assertEqual(empty_dashboard["overview"]["lessons"], 0)
        self.assertEqual(empty_dashboard["overview"]["attendance_percent"], 0.0)
        self.assertEqual(empty_dashboard["overview"]["homework_completion_percent"], 0.0)
        self.assertEqual(empty_dashboard["overview"]["average_score"], 0.0)
        self.assertEqual(empty_dashboard["attendance"]["by_date"], [])

    def test_repeated_calls_reflect_new_data_immediately(self):
        """The whole point of dropping stored KPI rows: no recalculation step."""
        before = self._dashboard(group_id=self.group1.id)["attendance"]["percent"]
        Attendance.objects.create(student=self.student2, lesson=self.lessons[0], status=Attendance.Status.PRESENT)
        after = self._dashboard(group_id=self.group1.id)["attendance"]["percent"]
        self.assertNotEqual(before, after)
        self.assertEqual(after, 80.0)  # 4 attended out of 5 marked now


class AnalyticsDashboardAPITests(AcademyTestBase):
    def setUp(self):
        super().setUp()
        self.lessons = list(Lesson.objects.filter(group=self.group1).order_by("lesson_number"))
        Attendance.objects.create(student=self.student1, lesson=self.lessons[0], status=Attendance.Status.PRESENT)
        self.params = {"date_from": "2026-09-01", "date_to": "2026-09-30"}

    def test_requires_authentication(self):
        response = self.anon_client.get("/api/v1/academy/analytics/dashboard/", self.params)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_requires_date_range(self):
        response = self.admin_client.get("/api/v1/academy/analytics/dashboard/")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_admin_sees_every_group(self):
        response = self.admin_client.get("/api/v1/academy/analytics/dashboard/", self.params)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        group_ids = {row["id"] for row in response.data["groups"]}
        self.assertEqual(group_ids, {self.group1.id, self.group2.id})

    def test_teacher_is_scoped_to_own_groups_even_if_teacher_param_given(self):
        response = self.teacher1_client.get(
            "/api/v1/academy/analytics/dashboard/", {**self.params, "teacher": self.teacher2.id}
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        group_ids = {row["id"] for row in response.data["groups"]}
        self.assertEqual(group_ids, {self.group1.id})

    def test_teacher_requesting_other_teachers_group_gets_empty_dashboard(self):
        response = self.teacher1_client.get(
            "/api/v1/academy/analytics/dashboard/", {**self.params, "group": self.group2.id}
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["groups"], [])
        self.assertEqual(response.data["overview"]["lessons"], 0)

    def test_endpoint_is_read_only(self):
        response = self.admin_client.post("/api/v1/academy/analytics/dashboard/", self.params)
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_old_kpi_endpoints_are_gone(self):
        response = self.admin_client.get("/api/v1/academy/kpi/groups/")
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
        # Lessons were already generated automatically the moment the group
        # was created — the quick action is now a safe, idempotent retry.
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


# ---------------------------------------------------------------------------
# Student Import / Export — apps.academy.services.import_export
# ---------------------------------------------------------------------------

def _csv_file(content: str, name: str = "students.csv") -> SimpleUploadedFile:
    return SimpleUploadedFile(name, content.encode("utf-8"), content_type="text/csv")


class StudentImportExportAPITests(AcademyTestBase):
    """group1 = "Python Beginner" (teacher1, students Алина/Мансур).
    group2 = "Frontend Beginner" (teacher2, student Айбек)."""

    def test_export_returns_csv_with_expected_columns(self):
        response = self.admin_client.get("/api/v1/academy/students/export/?export_format=csv")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response["Content-Type"], "text/csv; charset=utf-8")
        content = response.content.decode("utf-8-sig")
        header = content.splitlines()[0]
        self.assertEqual(header, "id,first_name,last_name,phone,parent_phone,group,is_active,created_at")
        self.assertIn("Python Beginner", content)

    def test_export_xlsx_format(self):
        response = self.admin_client.get("/api/v1/academy/students/export/?export_format=xlsx")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response["Content-Type"],
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    def test_export_respects_current_filters(self):
        response = self.admin_client.get(
            f"/api/v1/academy/students/export/?export_format=csv&group={self.group1.id}"
        )
        content = response.content.decode("utf-8-sig")
        self.assertIn("Алина", content)
        self.assertNotIn("Айбек", content)

    def test_teacher_export_scoped_to_own_groups(self):
        """Teacher permission spec §12: export is limited to the teacher's own groups."""
        response = self.teacher1_client.get("/api/v1/academy/students/export/?export_format=csv")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        content = response.content.decode("utf-8-sig")
        self.assertIn("Алина", content)
        self.assertNotIn("Айбек", content)

    def test_anon_cannot_export(self):
        response = self.anon_client.get("/api/v1/academy/students/export/")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_import_creates_student_with_existing_group(self):
        csv_content = (
            "first_name,last_name,phone,parent_phone,group,is_active\n"
            "Данияр,Сыдыков,+996555000111,+996555000222,Python Beginner,true\n"
        )
        response = self.admin_client.post(
            "/api/v1/academy/students/import/", {"file": _csv_file(csv_content)}, format="multipart"
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
            "/api/v1/academy/students/import/", {"file": _csv_file(csv_content)}, format="multipart"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["invalid"], 1)
        self.assertIn("Несуществующая Группа", response.data["errors"][0]["errors"][0])
        self.assertEqual(Student.objects.count(), before)
        self.assertFalse(Student.objects.filter(first_name="Валидный").exists())

    def test_group_is_never_auto_created(self):
        csv_content = "first_name,group\nX,Совсем Новая Группа\n"
        self.admin_client.post(
            "/api/v1/academy/students/import/", {"file": _csv_file(csv_content)}, format="multipart"
        )
        self.assertFalse(Group.objects.filter(name="Совсем Новая Группа").exists())

    def test_import_preview_does_not_save_anything(self):
        csv_content = "first_name,last_name\nПревью,Студент\n"
        before = Student.objects.count()
        response = self.admin_client.post(
            "/api/v1/academy/students/import/preview/", {"file": _csv_file(csv_content)}, format="multipart"
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
            "/api/v1/academy/students/import/", {"file": _csv_file(csv_content)}, format="multipart"
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
            "/api/v1/academy/students/import/", {"file": _csv_file(csv_content)}, format="multipart"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("не найден", response.data["errors"][0]["errors"][0])

    def test_import_missing_first_name_is_rejected(self):
        csv_content = "first_name,last_name\n,Безымянный\n"
        response = self.admin_client.post(
            "/api/v1/academy/students/import/", {"file": _csv_file(csv_content)}, format="multipart"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("first_name", response.data["errors"][0]["errors"][0])

    def test_import_invalid_boolean_is_rejected(self):
        csv_content = "first_name,is_active\nТест,может_быть\n"
        response = self.admin_client.post(
            "/api/v1/academy/students/import/", {"file": _csv_file(csv_content)}, format="multipart"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("is_active", response.data["errors"][0]["errors"][0])

    def test_import_invalid_phone_is_rejected(self):
        csv_content = "first_name,phone\nТест,not-a-phone!!\n"
        response = self.admin_client.post(
            "/api/v1/academy/students/import/", {"file": _csv_file(csv_content)}, format="multipart"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_unsupported_file_extension_is_rejected(self):
        bad_file = SimpleUploadedFile("students.txt", b"whatever", content_type="text/plain")
        response = self.admin_client.post(
            "/api/v1/academy/students/import/", {"file": bad_file}, format="multipart"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_teacher_cannot_import_students(self):
        response = self.teacher1_client.post(
            "/api/v1/academy/students/import/", {"file": _csv_file("first_name\nX\n")}, format="multipart"
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(Student.objects.filter(first_name="X").exists())

    def test_teacher_cannot_use_import_preview_either(self):
        response = self.teacher1_client.post(
            "/api/v1/academy/students/import/preview/", {"file": _csv_file("first_name\nX\n")}, format="multipart"
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_round_trip_export_then_import_only_updates(self):
        export_response = self.admin_client.get("/api/v1/academy/students/export/?export_format=csv")
        content = export_response.content.decode("utf-8-sig")
        before = Student.objects.count()

        reimport_response = self.admin_client.post(
            "/api/v1/academy/students/import/", {"file": _csv_file(content)}, format="multipart"
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
            "/api/v1/academy/group-schedules/",
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
            "/api/v1/academy/group-schedules/",
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
            "/api/v1/academy/group-schedules/",
            {
                "group": self.group1.id, "teacher": self.teacher1.id, "subject": self.subject_python.id,
                "day_of_week": "mon", "start_time": "16:30", "end_time": "17:30",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)

    def test_teacher_cannot_write_group_schedule(self):
        response = self.teacher1_client.post(
            "/api/v1/academy/group-schedules/",
            {
                "group": self.group1.id, "teacher": self.teacher1.id, "subject": self.subject_python.id,
                "day_of_week": "fri", "start_time": "10:00", "end_time": "11:00",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class AvailabilityAPITests(AcademyTestBase):
    """group1: teacher1/room1, Mon/Wed 15:00-16:30. group2: teacher2/room2, Tue/Thu 17:00-18:30."""

    def test_free_rooms_excludes_occupied(self):
        response = self.admin_client.get(
            "/api/v1/academy/rooms/available/", {"date": "2026-09-07", "start_time": "15:00", "end_time": "16:30"}
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        available_names = {r["name"] for r in response.data["available"]}
        self.assertNotIn(self.room1.name, available_names)
        self.assertIn(self.room2.name, available_names)
        occupied_names = {o["room_name"] for o in response.data["occupied"]}
        self.assertIn(self.room1.name, occupied_names)

    def test_free_teachers_excludes_occupied(self):
        response = self.admin_client.get(
            "/api/v1/academy/teacher-availability/",
            {"date": "2026-09-07", "start_time": "15:00", "end_time": "16:30"},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        available_usernames = {t["user"]["username"] for t in response.data["available"]}
        self.assertNotIn(self.teacher1.user.username, available_usernames)
        self.assertIn(self.teacher2.user.username, available_usernames)
        occupied_names = {o["teacher_name"] for o in response.data["occupied"]}
        self.assertIn(str(self.teacher1), occupied_names)

    def test_free_teachers_requires_authentication(self):
        response = self.anon_client.get("/api/v1/academy/teacher-availability/")
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
        # stake in group1 at all, only this schedule slot.
        GroupSchedule.objects.create(
            group=self.group1, teacher=self.teacher2, subject=self.subject_frontend,
            day_of_week="mon", start_time=dt.time(17, 0), end_time=dt.time(18, 0), room=self.room1,
        )

    def test_teacher_with_only_schedule_slot_sees_the_group(self):
        response = self.teacher2_client.get("/api/v1/academy/groups/")
        names = {g["name"] for g in response.data["results"]}
        self.assertIn(self.group1.name, names)
        self.assertIn(self.group2.name, names)

    def test_teacher_with_only_schedule_slot_can_read_group_detail(self):
        response = self.teacher2_client.get(f"/api/v1/academy/groups/{self.group1.id}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_teacher_with_only_schedule_slot_can_access_lessons(self):
        lesson = Lesson.objects.filter(group=self.group1).order_by("lesson_number").first()
        response = self.teacher2_client.get(f"/api/v1/academy/lessons/{lesson.id}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_teacher_with_only_schedule_slot_can_mark_attendance(self):
        lesson = Lesson.objects.filter(group=self.group1).order_by("lesson_number").first()
        response = self.teacher2_client.post(
            f"/api/v1/academy/lessons/{lesson.id}/attendance/",
            [{"student": self.student1.id, "status": "present"}],
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_unrelated_teacher_still_denied(self):
        outsider = make_teacher("outsider_perm")
        outsider_client = APIClient()
        outsider_client.force_authenticate(outsider.user)

        response = outsider_client.get(f"/api/v1/academy/groups/{self.group1.id}/")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

        lesson = Lesson.objects.filter(group=self.group1).order_by("lesson_number").first()
        response = outsider_client.get(f"/api/v1/academy/lessons/{lesson.id}/")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
