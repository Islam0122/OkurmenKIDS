"""Team Lead role: sees the whole academy, never writes.

Absolute imports only — see the note at the top of apps/academy/tests.py.
"""
from __future__ import annotations

import datetime as dt

from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from apps.academy.models import (
    AcademyMonthlyReport,
    Attendance,
    Course,
    Group,
    GroupTeacher,
    Homework,
    HomeworkResult,
    Lesson,
    Student,
)
from apps.users.models import Subject, Teacher, User

PAST = {"period": "custom", "start_date": "2025-03-01", "end_date": "2025-03-31"}
PASSWORD = "Str0ngPassw0rd!"


def make_teacher(username: str) -> Teacher:
    user = User.objects.create_user(
        username=username, email=f"{username}@okurmen.kg", password=PASSWORD,
        first_name=username.capitalize(), role=User.Role.TEACHER, is_verified=True,
    )
    return Teacher.objects.create(user=user)


class TeamLeadTestBase(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser(
            username="admin", email="admin@okurmen.kg", password=PASSWORD, first_name="Admin"
        )
        self.lead = User.objects.create_user(
            username="lead", email="lead@okurmen.kg", password=PASSWORD,
            first_name="Lead", role=User.Role.TEAM_LEAD,
        )
        self.python, _ = Subject.objects.get_or_create(name="Python")
        self.course = Course.objects.create(name="Prog", count_lesson=20)
        self.course.subjects.set([self.python])

        self.ivan = make_teacher("ivan")
        self.aida = make_teacher("aida")
        self.g1 = Group.objects.create(name="Python-01", course=self.course, start_date=dt.date(2025, 1, 1))
        self.g2 = Group.objects.create(name="Python-02", course=self.course, start_date=dt.date(2025, 1, 1))
        self.gt1 = GroupTeacher.objects.create(group=self.g1, teacher=self.ivan, subject=self.python)
        self.gt2 = GroupTeacher.objects.create(group=self.g2, teacher=self.aida, subject=self.python)
        self.s1 = Student.objects.create(first_name="Сумая", last_name="К", group=self.g1)
        self.s2 = Student.objects.create(first_name="Артём", last_name="И", group=self.g2)

        self.l1 = self._lesson(self.gt1, 1)
        self.l2 = self._lesson(self.gt2, 2)
        self.a1 = Attendance.objects.create(lesson=self.l1, student=self.s1, status=Attendance.Status.PRESENT)
        self.hw2 = Homework.objects.create(lesson=self.l2, title="HW")
        self.r2 = HomeworkResult.objects.create(
            homework=self.hw2, student=self.s2, status=HomeworkResult.Status.CHECKED, score=8
        )

        self.client = APIClient()
        self.client.force_authenticate(self.lead)

    def _lesson(self, gt, number) -> Lesson:
        return Lesson.objects.create(
            group=gt.group, group_teacher=gt, subject=gt.subject, teacher=gt.teacher, lesson_number=number,
            date=dt.date(2025, 3, 10), start_time=dt.time(10), end_time=dt.time(11),
            status=Lesson.Status.COMPLETED,
        )

    def ids(self, url, **params):
        response = self.client.get(url, params)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.content)
        data = response.data
        rows = data["results"] if isinstance(data, dict) and "results" in data else data
        return {row["id"] for row in rows}


class TeamLeadLoginTests(TeamLeadTestBase):
    def test_login_and_me(self):
        response = APIClient().post("/api/v1/auth/login/", {"username": "lead", "password": PASSWORD})
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.content)
        self.assertEqual(response.data["user"]["role"], "team_lead")
        self.assertEqual(self.client.get("/api/v1/auth/me/").data["role"], "team_lead")


class TeamLeadReadAccessTests(TeamLeadTestBase):
    """Every trainer's data is visible — not only one trainer's slice."""

    def test_sees_every_trainer(self):
        self.assertEqual(self.ids("/api/v1/trainers/"), {self.ivan.id, self.aida.id})
        response = self.client.get(f"/api/v1/trainers/{self.ivan.id}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_sees_every_group_student_lesson(self):
        self.assertEqual(self.ids("/api/v1/groups/"), {self.g1.id, self.g2.id})
        self.assertEqual(self.ids("/api/v1/students/"), {self.s1.id, self.s2.id})
        self.assertEqual(self.ids("/api/v1/lessons/"), {self.l1.id, self.l2.id})
        self.assertEqual(self.ids("/api/v1/attendance/"), {self.a1.id})
        self.assertEqual(self.ids("/api/v1/homework/"), {self.hw2.id})
        self.assertEqual(self.ids("/api/v1/homework-results/"), {self.r2.id})
        self.assertEqual(self.ids("/api/v1/programs/"), {self.gt1.id, self.gt2.id})
        self.assertIn(self.python.id, self.ids("/api/v1/subjects/"))

    def test_group_pages(self):
        for suffix in ("", "students/", "schedule/", "analytics/"):
            response = self.client.get(f"/api/v1/groups/{self.g1.id}/{suffix}")
            self.assertEqual(response.status_code, status.HTTP_200_OK, (suffix, response.content))
        lessons = self.client.get(f"/api/v1/groups/{self.g1.id}/schedule/").data["lessons"]
        self.assertEqual([row["id"] for row in lessons], [self.l1.id])

    def test_lesson_detail_shows_no_management_actions(self):
        response = self.client.get(f"/api/v1/lessons/{self.l1.id}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data["can_start"])
        self.assertFalse(response.data["can_cancel"])
        self.assertFalse(response.data["attendance_editable"])
        self.assertEqual(self.client.get(f"/api/v1/lessons/{self.l1.id}/attendance/").status_code, 200)
        self.assertEqual(self.client.get(f"/api/v1/homework/{self.hw2.id}/results/").status_code, 200)
        self.assertFalse(self.client.get(f"/api/v1/homework/{self.hw2.id}/").data["results_editable"])

    def test_analytics_dashboard_is_academy_wide(self):
        response = self.client.get("/api/v1/analytics/dashboard/", {"period": "custom", "start_date": "2025-03-01", "end_date": "2025-03-31"})
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.content)
        admin = APIClient()
        admin.force_authenticate(self.admin)
        expected = admin.get("/api/v1/analytics/dashboard/", {"period": "custom", "start_date": "2025-03-01", "end_date": "2025-03-31"})
        self.assertEqual(response.data, expected.data)

    def test_reports_kpi_and_control(self):
        for url in (
            "/api/v1/reports/overview/",
            "/api/v1/reports/filters/",
            "/api/v1/reports/teachers/",
            f"/api/v1/reports/teachers/{self.ivan.id}/",
            "/api/v1/reports/groups/",
            f"/api/v1/reports/groups/{self.g1.id}/",
            "/api/v1/reports/subjects/",
            f"/api/v1/reports/subjects/{self.python.id}/",
            "/api/v1/reports/students/",
            "/api/v1/control/",
        ):
            response = self.client.get(url, PAST)
            self.assertEqual(response.status_code, status.HTTP_200_OK, (url, response.content))
        teachers = self.client.get("/api/v1/reports/teachers/", PAST).data
        self.assertEqual({row["id"] for row in teachers["results"]}, {self.ivan.id, self.aida.id})
        students = self.client.get("/api/v1/reports/students/", PAST).data
        self.assertEqual({row["id"] for row in students["results"]}, {self.s1.id, self.s2.id})
        lesson_check = self.client.get(f"/api/v1/control/lessons/{self.l2.id}/")
        self.assertEqual(lesson_check.status_code, status.HTTP_200_OK)

    def test_report_exports(self):
        self.assertEqual(self.client.get("/api/v1/reports/export/excel/", PAST).status_code, 200)

    def test_academy_reports_readable(self):
        report = AcademyMonthlyReport.objects.create(year=2025, month=3)
        self.assertEqual(self.ids("/api/v1/academy-reports/"), {report.id})
        self.assertEqual(self.client.get(f"/api/v1/academy-reports/{report.id}/").status_code, 200)

    def test_tests_and_exam_sessions_readable(self):
        self.assertEqual(self.client.get("/api/v1/tests/").status_code, status.HTTP_200_OK)
        self.assertEqual(self.client.get("/api/v1/teacher/sessions/").status_code, status.HTTP_200_OK)


class TeamLeadWriteDeniedTests(TeamLeadTestBase):
    """Read-only everywhere — refused on the backend, not just hidden in the UI."""

    def assertDenied(self, response):
        self.assertIn(response.status_code, (status.HTTP_403_FORBIDDEN, status.HTTP_405_METHOD_NOT_ALLOWED), response.content)

    def test_students_cannot_be_created_changed_or_deleted(self):
        self.assertDenied(self.client.post("/api/v1/students/", {"first_name": "X", "group": self.g1.id}))
        self.assertDenied(self.client.patch(f"/api/v1/students/{self.s1.id}/", {"first_name": "X"}))
        self.assertDenied(self.client.delete(f"/api/v1/students/{self.s1.id}/"))
        self.assertTrue(Student.objects.filter(pk=self.s1.pk, first_name="Сумая").exists())

    def test_groups_and_programs_are_read_only(self):
        self.assertDenied(self.client.patch(f"/api/v1/groups/{self.g1.id}/", {"name": "X"}))
        self.assertDenied(self.client.delete(f"/api/v1/groups/{self.g1.id}/"))
        # Generating lessons is part of the academic configuration a Team Lead
        # manages — see test_group_academic_config.
        self.assertDenied(self.client.delete(f"/api/v1/programs/{self.gt1.id}/"))
        self.assertDenied(self.client.post("/api/v1/courses/", {"name": "X", "count_lesson": 1}))

    def test_lessons_are_read_only(self):
        self.assertDenied(self.client.patch(f"/api/v1/lessons/{self.l1.id}/", {"topic": "X"}))
        for action in ("start", "complete", "cancel", "reschedule", "homework-not-required"):
            self.assertDenied(self.client.post(f"/api/v1/lessons/{self.l1.id}/{action}/", {}, format="json"))
        self.assertDenied(self.client.post(
            f"/api/v1/lessons/{self.l1.id}/attendance/", [{"student": self.s1.id, "status": "absent"}], format="json"
        ))
        self.assertEqual(Attendance.objects.get(pk=self.a1.pk).status, Attendance.Status.PRESENT)

    def test_attendance_and_homework_are_read_only(self):
        self.assertDenied(self.client.patch(f"/api/v1/attendance/{self.a1.id}/", {"status": "absent"}))
        self.assertDenied(self.client.delete(f"/api/v1/attendance/{self.a1.id}/"))
        self.assertDenied(self.client.post("/api/v1/homework/", {"lesson": self.l1.id, "title": "X"}))
        self.assertDenied(self.client.delete(f"/api/v1/homework/{self.hw2.id}/"))
        self.assertDenied(self.client.post(
            f"/api/v1/homework/{self.hw2.id}/results/", [{"student": self.s2.id, "status": "checked", "score": 1}], format="json"
        ))
        self.assertDenied(self.client.patch(f"/api/v1/homework-results/{self.r2.id}/", {"score": 1}))
        self.assertEqual(HomeworkResult.objects.get(pk=self.r2.pk).score, 8)

    def test_tests_cannot_be_created_edited_or_deleted(self):
        self.assertDenied(self.client.post("/api/v1/tests/", {"title": "X"}))

    def test_reports_cannot_be_created_or_commented(self):
        report = AcademyMonthlyReport.objects.create(year=2025, month=3)
        self.assertDenied(self.client.post("/api/v1/academy-reports/", {"year": 2025, "month": 4}))
        self.assertDenied(self.client.patch(f"/api/v1/academy-reports/{report.id}/", {"comment": "X"}))
        self.assertDenied(self.client.post("/api/v1/monthly-reports/", {"year": 2025, "month": 4}))

    def test_no_user_management(self):
        self.assertDenied(self.client.post("/api/v1/trainers/", {"username": "x"}))
        self.assertDenied(self.client.delete(f"/api/v1/trainers/{self.ivan.id}/"))
        self.assertDenied(self.client.post(f"/api/v1/trainers/{self.ivan.id}/verify/"))
        self.assertDenied(self.client.get("/api/v1/trainers/export/"))
        self.ivan.refresh_from_db()
        self.assertTrue(self.ivan.is_active)

    def test_no_django_admin(self):
        self.lead.is_staff = True  # even a mistakenly staff-flagged Team Lead
        self.lead.save()
        web = self.client_class()
        web.force_login(self.lead)
        response = web.get("/admin/")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin/login/", response["Location"])

    def test_scholarships_feedback_and_news_stay_closed(self):
        for url in ("/api/v1/teacher/news/", "/api/v1/feedback/analytics/overview/"):
            response = self.client.get(url)
            self.assertIn(response.status_code, (403, 404), (url, response.status_code))


class OtherRolesUnchangedTests(TeamLeadTestBase):
    """Team Lead scoping must not leak into the Teacher's own scope."""

    def test_teacher_still_scoped_to_own_data(self):
        teacher = APIClient()
        teacher.force_authenticate(self.ivan.user)
        self.client = teacher
        self.assertEqual(self.ids("/api/v1/groups/"), {self.g1.id})
        self.assertEqual(self.ids("/api/v1/students/"), {self.s1.id})
        self.assertEqual(teacher.get("/api/v1/trainers/").status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(teacher.get("/api/v1/reports/overview/").status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(teacher.get(f"/api/v1/groups/{self.g1.id}/analytics/").status_code, status.HTTP_403_FORBIDDEN)
