"""Administrator corrections of attendance and homework in Django Admin —
also after the lesson is completed — while the Trainer's lock on a completed
lesson stays as it is.

Absolute imports only — see the note at the top of apps/academy/tests.py.
"""
from __future__ import annotations

import datetime as dt

from django.contrib.admin.models import LogEntry
from django.core.exceptions import PermissionDenied
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.academy.models import (
    Attendance, Course, Group, GroupTeacher, Homework, HomeworkResult, Lesson, Student,
)
from apps.academy.services import admin_corrections
from apps.academy.services.reports import ReportFilters, build_teacher_detail
from apps.users.models import Subject, Teacher, User

PASSWORD = "Str0ngPassw0rd!"
DAY = timezone.localdate() - dt.timedelta(days=2)


def make_user(username, role, **extra):
    return User.objects.create_user(username=username, email=f"{username}@okurmen.kg", password=PASSWORD,
                                    first_name=username.capitalize(), role=role, is_verified=True, **extra)


class CorrectionFixture(TestCase):
    def setUp(self):
        self.python, _ = Subject.objects.get_or_create(name="Python")
        self.course = Course.objects.create(name="Prog", count_lesson=10)
        self.course.subjects.set([self.python])
        self.trainer = Teacher.objects.create(user=make_user("trainer", User.Role.TEACHER))
        self.group = Group.objects.create(name="PRO-01", course=self.course, start_date=DAY - dt.timedelta(days=30))
        self.program = GroupTeacher.objects.create(group=self.group, teacher=self.trainer, subject=self.python)
        self.s1 = Student.objects.create(first_name="Азамат", last_name="А", group=self.group)
        self.s2 = Student.objects.create(first_name="Айгерим", last_name="Б", group=self.group)
        self.lesson = Lesson.objects.create(
            group=self.group, group_teacher=self.program, teacher=self.trainer, subject=self.python, lesson_number=1,
            date=DAY, start_time=dt.time(10), end_time=dt.time(11), status=Lesson.Status.COMPLETED,
            completed_at=timezone.now(),
        )
        self.a1 = Attendance.objects.create(student=self.s1, lesson=self.lesson, status=Attendance.Status.ABSENT)
        self.a2 = Attendance.objects.create(student=self.s2, lesson=self.lesson, status=Attendance.Status.PRESENT)
        self.homework = Homework.objects.create(lesson=self.lesson, title="ДЗ 1")
        self.r1 = HomeworkResult.objects.create(homework=self.homework, student=self.s1, status="not_submitted")
        self.r2 = HomeworkResult.objects.create(homework=self.homework, student=self.s2, status="checked", score=8)

        self.superuser = User.objects.create_superuser(username="root", email="root@okurmen.kg", password=PASSWORD)
        self.admin_role = make_user("boss", User.Role.ADMIN, is_staff=True)

    def admin_post(self, user, url, data):
        self.client.force_login(user)
        return self.client.post(url, data)

    def attendance_url(self, record):
        return reverse("admin:academy_attendance_change", args=[record.pk])

    def result_url(self, result):
        return reverse("admin:academy_homeworkresult_change", args=[result.pk])

    def kpi(self):
        filters = ReportFilters.from_query({"period": "custom", "start_date": str(DAY), "end_date": str(DAY)})
        return build_teacher_detail(self.trainer, filters)


class TrainerStaysLockedTests(CorrectionFixture):
    def setUp(self):
        super().setUp()
        self.api = APIClient()
        self.api.force_authenticate(self.trainer.user)

    def test_trainer_cannot_change_attendance_of_a_completed_lesson(self):
        bulk = self.api.post(f"/api/v1/lessons/{self.lesson.pk}/attendance/",
                             [{"student": self.s1.pk, "status": "present"}], format="json")
        self.assertEqual(bulk.status_code, 403)
        direct = self.api.patch(f"/api/v1/attendance/{self.a1.pk}/", {"status": "present"}, format="json")
        self.assertEqual(direct.status_code, 403)
        self.a1.refresh_from_db()
        self.assertEqual(self.a1.status, Attendance.Status.ABSENT)

    def test_trainer_cannot_add_homework_to_a_completed_lesson(self):
        response = self.api.post("/api/v1/homework/", {"lesson": self.lesson.pk, "title": "Новое"}, format="json")
        self.assertEqual(response.status_code, 403)

    def test_trainer_cannot_use_the_admin_correction(self):
        trainer = self.trainer.user
        trainer.is_staff = True  # even a trainer given staff access by mistake
        trainer.save()
        response = self.admin_post(trainer, self.attendance_url(self.a1), {"status": "present"})
        self.assertIn(response.status_code, (302, 403))
        self.a1.refresh_from_db()
        self.assertEqual(self.a1.status, Attendance.Status.ABSENT)
        with self.assertRaises(PermissionDenied):
            admin_corrections.correct_attendance(self.a1, status="present", user=trainer)


class AdminCorrectsAttendanceTests(CorrectionFixture):
    def test_admin_marks_attendance_present_after_completion(self):
        for user in (self.superuser, self.admin_role):
            Attendance.objects.filter(pk=self.a1.pk).update(status=Attendance.Status.ABSENT, comment="")
            response = self.admin_post(user, self.attendance_url(self.a1), {"status": "present", "comment": "Был, отметили по ошибке"})
            self.assertRedirects(response, self.attendance_url(self.a1), fetch_redirect_response=False)
            self.a1.refresh_from_db()
            self.assertEqual((self.a1.status, self.a1.comment), ("present", "Был, отметили по ошибке"))
        self.lesson.refresh_from_db()
        self.assertEqual(self.lesson.status, Lesson.Status.COMPLETED)  # the lesson itself is untouched

    def test_every_existing_status_can_be_set_and_is_logged(self):
        for status in Attendance.Status.values:
            self.admin_post(self.superuser, self.attendance_url(self.a2), {"status": status})
            self.a2.refresh_from_db()
            self.assertEqual(self.a2.status, status)
        entry = LogEntry.objects.filter(object_id=str(self.a2.pk)).order_by("-action_time").first()
        self.assertEqual(entry.user, self.superuser)
        self.assertIn("статус:", entry.change_message)
        self.assertIn("занятие уже проведено", entry.change_message)

    def test_detail_page_shows_the_form_and_list_filters_still_work(self):
        self.client.force_login(self.superuser)
        page = self.client.get(self.attendance_url(self.a1))
        self.assertContains(page, "Исправить посещаемость")
        self.assertContains(page, 'name="csrfmiddlewaretoken"')
        listing = self.client.get(reverse("admin:academy_attendance_changelist"), {"q": "Азамат", "group": self.group.pk})
        self.assertEqual(listing.status_code, 200)

    def test_invalid_status_and_cancelled_lessons_are_refused(self):
        response = self.admin_post(self.superuser, self.attendance_url(self.a1), {"status": "teleported"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Выберите статус из списка.")
        self.a1.refresh_from_db()
        self.assertEqual(self.a1.status, Attendance.Status.ABSENT)
        Lesson.objects.filter(pk=self.lesson.pk).update(status=Lesson.Status.CANCELLED)
        response = self.admin_post(self.superuser, self.attendance_url(self.a1), {"status": "present"})
        self.assertContains(response, "Занятие отменено")
        self.a1.refresh_from_db()
        self.assertEqual(self.a1.status, Attendance.Status.ABSENT)

    def test_users_without_admin_rights_cannot_correct(self):
        lead = make_user("lead", User.Role.TEAM_LEAD)
        assistant = make_user("assist", User.Role.ASSISTANT)
        for user in (lead, assistant):
            response = self.admin_post(user, self.attendance_url(self.a1), {"status": "present"})
            self.assertIn(response.status_code, (302, 403))
        self.client.logout()
        response = self.client.post(self.attendance_url(self.a1), {"status": "present"})
        self.assertEqual(response.status_code, 302)  # to the admin login
        self.a1.refresh_from_db()
        self.assertEqual(self.a1.status, Attendance.Status.ABSENT)
        for user in (lead, assistant):
            with self.assertRaises(PermissionDenied):
                admin_corrections.correct_attendance(self.a1, status="present", user=user)

    def test_kpi_and_statistics_follow_the_correction(self):
        before = self.kpi()
        self.assertEqual((before["attendance"]["present"], before["attendance"]["absent"]), (1, 1))
        self.assertEqual(before["attendance"]["rate"], 50.0)
        self.admin_post(self.superuser, self.attendance_url(self.a1), {"status": "present"})
        after = self.kpi()
        self.assertEqual((after["attendance"]["present"], after["attendance"]["absent"]), (2, 0))
        self.assertEqual(after["attendance"]["rate"], 100.0)
        self.assertGreater(after["kpi"]["total"], before["kpi"]["total"])
        self.assertEqual(after["lessons"]["held"], before["lessons"]["held"])  # the lesson count doesn't move


class AdminCorrectsHomeworkTests(CorrectionFixture):
    def test_admin_corrects_a_homework_result_after_completion(self):
        response = self.admin_post(self.superuser, self.result_url(self.r1), {"status": "checked", "score": "9", "comment": "Сдал устно"})
        self.assertRedirects(response, self.result_url(self.r1), fetch_redirect_response=False)
        self.r1.refresh_from_db()
        self.assertEqual((self.r1.status, self.r1.score, self.r1.comment), ("checked", 9, "Сдал устно"))
        self.assertIsNotNone(self.r1.checked_at)
        self.assertTrue(LogEntry.objects.filter(object_id=str(self.r1.pk), change_message__contains="оценка").exists())

    def test_invalid_score_is_refused(self):
        response = self.admin_post(self.superuser, self.result_url(self.r1), {"status": "checked", "score": "15"})
        self.assertEqual(response.status_code, 200)
        self.r1.refresh_from_db()
        self.assertEqual((self.r1.status, self.r1.score), ("not_submitted", None))

    def test_homework_kpi_follows_the_correction(self):
        before = self.kpi()["homework"]
        self.assertEqual((before["results"], before["submitted"]), (2, 1))
        self.admin_post(self.superuser, self.result_url(self.r1), {"status": "submitted", "score": ""})
        after = self.kpi()["homework"]
        self.assertEqual((after["results"], after["submitted"]), (2, 2))
        self.assertGreater(after["completion_rate"], before["completion_rate"])

    def test_admin_corrects_the_homework_itself(self):
        url = reverse("admin:academy_homework_change", args=[self.homework.pk])
        response = self.admin_post(self.superuser, url, {"title": "ДЗ 1 (исправлено)", "description": "Задачи 1–5", "deadline": str(DAY + dt.timedelta(days=7))})
        self.assertRedirects(response, url, fetch_redirect_response=False)
        self.homework.refresh_from_db()
        self.assertEqual((self.homework.title, self.homework.deadline), ("ДЗ 1 (исправлено)", DAY + dt.timedelta(days=7)))
        self.assertEqual(self.admin_post(self.superuser, url, {"title": ""}).status_code, 200)
        self.homework.refresh_from_db()
        self.assertEqual(self.homework.title, "ДЗ 1 (исправлено)")

    def test_non_admins_cannot_correct_homework(self):
        lead = make_user("lead", User.Role.TEAM_LEAD)
        response = self.admin_post(lead, self.result_url(self.r1), {"status": "checked", "score": "9"})
        self.assertIn(response.status_code, (302, 403))
        self.r1.refresh_from_db()
        self.assertEqual(self.r1.status, "not_submitted")
        with self.assertRaises(PermissionDenied):
            admin_corrections.correct_homework_result(self.r1, status="checked", score=9, user=self.trainer.user)
        with self.assertRaises(PermissionDenied):
            admin_corrections.correct_homework(self.homework, title="x", user=self.trainer.user)

    def test_admin_still_cannot_add_or_delete_through_django_admin(self):
        self.client.force_login(self.superuser)
        self.assertEqual(self.client.get(reverse("admin:academy_attendance_add")).status_code, 403)
        self.assertEqual(self.client.post(reverse("admin:academy_attendance_delete", args=[self.a1.pk])).status_code, 403)
        self.assertTrue(Attendance.objects.filter(pk=self.a1.pk).exists())
