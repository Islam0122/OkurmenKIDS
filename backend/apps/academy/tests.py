from __future__ import annotations

import datetime as dt

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
    Homework,
    HomeworkResult,
    KPIGroup,
    Lesson,
    Room,
    Student,
)
from apps.academy.services.attendance_service import bulk_mark_attendance
from apps.academy.services.homework_service import bulk_upsert_homework_results
from apps.academy.services.kpi_calculator import (
    calculate_attendance_kpi,
    calculate_group_kpi,
    calculate_homework_kpi,
    calculate_lesson_kpi,
    calculate_student_kpi,
    calculate_teacher_kpi,
)
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


class KPITests(AcademyTestBase):
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

    def test_calculate_student_kpi(self):
        kpi = calculate_student_kpi(self.student1, self.group1, self.date_from, self.date_to)
        self.assertEqual(kpi.total_lessons, 4)
        self.assertEqual(kpi.present_count, 2)
        self.assertEqual(kpi.absent_count, 1)
        self.assertEqual(kpi.late_count, 1)
        self.assertEqual(kpi.attendance_percent, 75.0)
        self.assertEqual(kpi.total_homeworks, 2)
        self.assertEqual(kpi.completed_homeworks, 1)
        self.assertEqual(kpi.missed_homeworks, 1)
        self.assertEqual(kpi.homework_completion_percent, 50.0)
        self.assertEqual(kpi.average_score, 8.0)

    def test_calculate_group_kpi(self):
        kpi = calculate_group_kpi(self.group1, self.date_from, self.date_to)
        self.assertEqual(kpi.total_students, 2)
        self.assertEqual(kpi.total_lessons, 4)
        self.assertEqual(kpi.attendance_percent, 75.0)
        self.assertEqual(kpi.homework_completion_percent, 25.0)
        self.assertEqual(kpi.average_score, 8.0)

    def test_calculate_teacher_kpi(self):
        kpi = calculate_teacher_kpi(self.teacher1, self.date_from, self.date_to)
        self.assertEqual(kpi.total_groups, 1)
        self.assertEqual(kpi.total_lessons, 4)
        self.assertEqual(kpi.attendance_percent, 75.0)
        self.assertEqual(kpi.average_student_score, 8.0)

    def test_calculate_lesson_kpi(self):
        kpi = calculate_lesson_kpi(self.lessons[0])
        self.assertEqual(kpi.total_students, 2)
        self.assertEqual(kpi.present_count, 1)
        self.assertEqual(kpi.attendance_percent, 100.0)
        self.assertEqual(kpi.homework_completed_count, 1)
        self.assertEqual(kpi.average_homework_score, 8.0)

    def test_calculate_attendance_kpi(self):
        kpi = calculate_attendance_kpi(self.group1, self.date_from, self.date_to)
        self.assertEqual(kpi.total_records, 4)
        self.assertEqual(kpi.attendance_percent, 75.0)

    def test_calculate_homework_kpi(self):
        kpi = calculate_homework_kpi(self.group1, self.date_from, self.date_to)
        self.assertEqual(kpi.total_homeworks, 2)
        self.assertEqual(kpi.total_results, 1)
        self.assertEqual(kpi.checked_count, 1)
        self.assertEqual(kpi.completion_percent, 100.0)
        self.assertEqual(kpi.average_score, 8.0)

    def test_kpi_viewsets_are_read_only(self):
        response = self.admin_client.post(
            "/api/v1/academy/kpi/groups/",
            {"group": self.group1.id, "date_from": "2026-09-01", "date_to": "2026-09-30"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_calculate_endpoint_is_admin_only(self):
        response = self.teacher1_client.post(
            f"/api/v1/academy/kpi/groups/{self.group1.id}/calculate/",
            {"date_from": "2026-09-01", "date_to": "2026-09-30"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_calculate_endpoint_admin_creates_kpi(self):
        response = self.admin_client.post(
            f"/api/v1/academy/kpi/groups/{self.group1.id}/calculate/",
            {"date_from": "2026-09-01", "date_to": "2026-09-30"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["attendance_percent"], 75.0)
        self.assertTrue(KPIGroup.objects.filter(group=self.group1).exists())

    def test_teacher_kpi_isolation(self):
        calculate_group_kpi(self.group1, self.date_from, self.date_to)
        calculate_group_kpi(self.group2, self.date_from, self.date_to)
        response = self.teacher1_client.get("/api/v1/academy/kpi/groups/")
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["group"], self.group1.id)

    def test_student_kpi_group_isolation(self):
        calculate_student_kpi(self.student1, self.group1, self.date_from, self.date_to)
        response = self.teacher2_client.get("/api/v1/academy/kpi/students/")
        self.assertEqual(response.data["count"], 0)


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
