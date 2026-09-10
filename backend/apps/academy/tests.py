from __future__ import annotations

import datetime as dt

from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from apps.users.models import Teacher, User

from .models import KPI, Attendance, Group, Homework, Room, Schedule, Student


def make_teacher(username: str, email: str) -> Teacher:
    user = User.objects.create_user(
        username=username,
        email=email,
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
        self.teacher1 = make_teacher("teacher1", "teacher1@okurmen.kg")
        self.teacher2 = make_teacher("teacher2", "teacher2@okurmen.kg")

        self.room1 = Room.objects.create(name="Room 101", capacity=15)
        self.room2 = Room.objects.create(name="Room 102", capacity=10)

        self.group1 = Group.objects.create(
            name="Python Beginner",
            teacher=self.teacher1,
            room=self.room1,
            start_date=dt.date(2026, 9, 1),
            start_time=dt.time(15, 0),
            end_time=dt.time(16, 30),
            days_of_week=["mon", "wed", "fri"],
            max_students=15,
        )
        self.group2 = Group.objects.create(
            name="Frontend Beginner",
            teacher=self.teacher2,
            room=self.room2,
            start_date=dt.date(2026, 9, 1),
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


class PermissionsTests(AcademyTestBase):
    def test_anonymous_cannot_list_students(self):
        response = self.anon_client.get("/api/v1/academy/students/")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_admin_can_access_all_endpoints(self):
        for path in ("students", "groups", "rooms", "schedules", "attendance", "homework", "kpi"):
            response = self.admin_client.get(f"/api/v1/academy/{path}/")
            self.assertEqual(response.status_code, status.HTTP_200_OK, path)

    def test_teacher_cannot_access_another_teachers_group_detail(self):
        response = self.teacher1_client.get(f"/api/v1/academy/groups/{self.group2.id}/")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_teacher_cannot_write_group(self):
        response = self.teacher1_client.patch(
            f"/api/v1/academy/groups/{self.group1.id}/", {"name": "Hacked"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class StudentScopingTests(AcademyTestBase):
    def test_admin_sees_all_students(self):
        response = self.admin_client.get("/api/v1/academy/students/")
        self.assertEqual(response.data["count"], 3)

    def test_teacher_sees_only_own_students(self):
        response = self.teacher1_client.get("/api/v1/academy/students/")
        self.assertEqual(response.data["count"], 2)
        names = {row["first_name"] for row in response.data["results"]}
        self.assertEqual(names, {"Алина", "Мансур"})

    def test_teacher_cannot_fetch_other_teachers_student(self):
        response = self.teacher1_client.get(f"/api/v1/academy/students/{self.student3.id}/")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class GroupScopingTests(AcademyTestBase):
    def test_admin_sees_all_groups(self):
        response = self.admin_client.get("/api/v1/academy/groups/")
        self.assertEqual(response.data["count"], 2)

    def test_teacher_sees_only_own_groups(self):
        response = self.teacher1_client.get("/api/v1/academy/groups/")
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["name"], "Python Beginner")

    def test_group_serializer_reports_students_count(self):
        response = self.admin_client.get(f"/api/v1/academy/groups/{self.group1.id}/")
        self.assertEqual(response.data["students_count"], 2)

    def test_admin_cannot_assign_inactive_teacher(self):
        self.teacher2.is_active = False
        self.teacher2.save(update_fields=["is_active"])
        response = self.admin_client.patch(
            f"/api/v1/academy/groups/{self.group1.id}/", {"teacher": self.teacher2.id}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_group_end_date_before_start_date_rejected(self):
        response = self.admin_client.post(
            "/api/v1/academy/groups/",
            {
                "name": "Bad Group",
                "teacher": self.teacher1.id,
                "start_date": "2026-09-10",
                "end_date": "2026-09-01",
                "start_time": "10:00",
                "end_time": "11:00",
                "days_of_week": ["mon"],
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class AttendanceTests(AcademyTestBase):
    def test_correct_creation(self):
        response = self.teacher1_client.post(
            "/api/v1/academy/attendance/",
            {
                "student": self.student1.id,
                "group": self.group1.id,
                "date": "2026-09-12",
                "status": "present",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(response.data["student_name"], "Алина Иванова")
        self.assertEqual(response.data["status_display"], "Присутствовал")

    def test_student_from_other_group_rejected(self):
        response = self.admin_client.post(
            "/api/v1/academy/attendance/",
            {
                "student": self.student3.id,  # belongs to group2
                "group": self.group1.id,
                "date": "2026-09-12",
                "status": "present",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_duplicate_rejected(self):
        Attendance.objects.create(
            student=self.student1, group=self.group1, date=dt.date(2026, 9, 12), status="present"
        )
        response = self.admin_client.post(
            "/api/v1/academy/attendance/",
            {
                "student": self.student1.id,
                "group": self.group1.id,
                "date": "2026-09-12",
                "status": "late",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_teacher_isolation_cannot_create_for_other_group(self):
        response = self.teacher1_client.post(
            "/api/v1/academy/attendance/",
            {
                "student": self.student3.id,
                "group": self.group2.id,
                "date": "2026-09-12",
                "status": "present",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_teacher_isolation_cannot_edit_other_groups_attendance(self):
        record = Attendance.objects.create(
            student=self.student3, group=self.group2, date=dt.date(2026, 9, 12), status="present"
        )
        response = self.teacher1_client.patch(
            f"/api/v1/academy/attendance/{record.id}/", {"status": "absent"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_group_attendance_by_date_view(self):
        Attendance.objects.create(student=self.student1, group=self.group1, date=dt.date(2026, 9, 12), status="present")
        Attendance.objects.create(student=self.student2, group=self.group1, date=dt.date(2026, 9, 12), status="absent")
        response = self.admin_client.get(
            "/api/v1/academy/attendance/", {"group": self.group1.id, "date": "2026-09-12"}
        )
        self.assertEqual(response.data["count"], 2)


class HomeworkTests(AcademyTestBase):
    def test_score_out_of_range_rejected(self):
        response = self.admin_client.post(
            "/api/v1/academy/homework/",
            {"student": self.student1.id, "group": self.group1.id, "date": "2026-09-12", "score": 11},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_wrong_group_rejected(self):
        response = self.admin_client.post(
            "/api/v1/academy/homework/",
            {"student": self.student3.id, "group": self.group1.id, "date": "2026-09-12", "score": 8},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_duplicate_rejected(self):
        Homework.objects.create(student=self.student1, group=self.group1, date=dt.date(2026, 9, 12), score=8)
        response = self.admin_client.post(
            "/api/v1/academy/homework/",
            {"student": self.student1.id, "group": self.group1.id, "date": "2026-09-12", "score": 5},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_teacher_isolation(self):
        response = self.teacher2_client.get("/api/v1/academy/homework/", {"group": self.group1.id})
        self.assertEqual(response.data["count"], 0)


class KPITests(AcademyTestBase):
    def setUp(self):
        super().setUp()
        self.date_from = dt.date(2026, 9, 1)
        self.date_to = dt.date(2026, 9, 30)

        for day, attendance_status in [
            (1, Attendance.Status.PRESENT),
            (3, Attendance.Status.PRESENT),
            (8, Attendance.Status.LATE),
            (10, Attendance.Status.ABSENT),
        ]:
            Attendance.objects.create(
                student=self.student1,
                group=self.group1,
                date=dt.date(2026, 9, day),
                status=attendance_status,
            )

        Homework.objects.create(student=self.student1, group=self.group1, date=dt.date(2026, 9, 1), score=8)
        Homework.objects.create(student=self.student1, group=self.group1, date=dt.date(2026, 9, 8), score=6)

        self.kpi = KPI.objects.create(
            student=self.student1, group=self.group1, date_from=self.date_from, date_to=self.date_to
        )

    def test_correct_calculation(self):
        response = self.admin_client.get(f"/api/v1/academy/kpi/{self.kpi.id}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        attendance = response.data["attendance"]
        self.assertEqual(attendance["total_lessons"], 4)
        self.assertEqual(attendance["present"], 2)
        self.assertEqual(attendance["late"], 1)
        self.assertEqual(attendance["absent"], 1)
        self.assertEqual(attendance["attendance_percentage"], 75.0)

        homework = response.data["homework"]
        self.assertEqual(homework["total_records"], 2)
        self.assertEqual(homework["average_score"], 7.0)
        self.assertEqual(homework["homework_percentage"], 70.0)

    def test_teacher_isolation(self):
        other_kpi = KPI.objects.create(
            student=self.student3, group=self.group2, date_from=self.date_from, date_to=self.date_to
        )
        response = self.teacher1_client.get(f"/api/v1/academy/kpi/{other_kpi.id}/")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

        response = self.teacher1_client.get(f"/api/v1/academy/kpi/{self.kpi.id}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_kpi_is_read_only(self):
        response = self.admin_client.post(
            "/api/v1/academy/kpi/",
            {
                "student": self.student1.id,
                "group": self.group1.id,
                "date_from": "2026-10-01",
                "date_to": "2026-10-31",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)


class ScheduleTests(AcademyTestBase):
    def test_end_time_before_start_time_rejected(self):
        response = self.admin_client.post(
            "/api/v1/academy/schedules/",
            {
                "group": self.group1.id,
                "date": "2026-09-12",
                "start_time": "16:00",
                "end_time": "15:00",
                "room": self.room1.id,
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_conflicting_room_booking_rejected(self):
        Schedule.objects.create(
            group=self.group1,
            date=dt.date(2026, 9, 12),
            start_time=dt.time(15, 0),
            end_time=dt.time(16, 30),
            room=self.room1,
        )
        response = self.admin_client.post(
            "/api/v1/academy/schedules/",
            {
                "group": self.group2.id,
                "date": "2026-09-12",
                "start_time": "16:00",
                "end_time": "17:00",
                "room": self.room1.id,
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_inactive_room_rejected_for_new_schedule(self):
        self.room1.is_active = False
        self.room1.save(update_fields=["is_active"])
        response = self.admin_client.post(
            "/api/v1/academy/schedules/",
            {
                "group": self.group1.id,
                "date": "2026-09-20",
                "start_time": "15:00",
                "end_time": "16:00",
                "room": self.room1.id,
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_teacher_sees_only_own_schedule(self):
        Schedule.objects.create(
            group=self.group1, date=dt.date(2026, 9, 12), start_time=dt.time(15, 0), end_time=dt.time(16, 30), room=self.room1
        )
        Schedule.objects.create(
            group=self.group2, date=dt.date(2026, 9, 13), start_time=dt.time(17, 0), end_time=dt.time(18, 30), room=self.room2
        )
        response = self.teacher1_client.get("/api/v1/academy/schedules/")
        self.assertEqual(response.data["count"], 1)
