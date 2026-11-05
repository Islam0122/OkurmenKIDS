"""Parent reports API: access rules, validation, history, regenerate, text edits."""
from __future__ import annotations

import datetime as dt
from unittest import mock

from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.academy.models import Group, GroupTeacher
from apps.reports.models import ParentReport
from apps.users.models import Subject, Teacher, User

from .base import TODAY, OctoberFixture, make_user

TEXT_ONLY = {"period": "last_month", "output_format": "text"}


_real_localdate = timezone.localdate


def _today(value=None, timezone=None):
    """`timezone.localdate()` pinned to TODAY; with a value it still converts it."""
    return TODAY if value is None else _real_localdate(value, timezone)


class ApiFixture(OctoberFixture):
    def setUp(self):
        super().setUp()
        # The API reads «today» from the clock; pin it to the fixture's day.
        patcher = mock.patch("django.utils.timezone.localdate", _today)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.admin = make_user("admin", User.Role.ADMIN)
        self.team_lead = make_user("lead", User.Role.TEAM_LEAD)
        self.assistant = make_user("assistant", User.Role.ASSISTANT)
        self.director = make_user("director", User.Role.DIRECTOR)
        self.other_trainer = Teacher.objects.create(user=make_user("other", User.Role.TEACHER))
        self.other_group = Group.objects.create(
            name="PY-99", course=self.course, teacher=self.other_trainer, start_date=dt.date(2026, 8, 1),
        )
        GroupTeacher.objects.create(group=self.other_group, teacher=self.other_trainer, subject=self.python)

    def client_for(self, user):
        client = APIClient()
        client.force_authenticate(user)
        return client

    def preview_url(self, group=None):
        return reverse("parent-report-preview", args=[(group or self.group).pk])

    def generate_url(self, group=None):
        return reverse("parent-report-generate", args=[(group or self.group).pk])


class AccessTests(ApiFixture):
    def test_trainer_previews_own_group_only(self):
        client = self.client_for(self.trainer.user)
        response = client.get(self.preview_url(), {"period": "last_month"})
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.data["snapshot"]["group_stats"]["conducted_lessons"], 3)
        self.assertEqual(response.data["snapshot"]["teacher_scope_id"], self.trainer.pk)
        self.assertTrue(response.data["text"].startswith("Уважаемые родители!"))
        # Another trainer's group is invisible: 404, not even a 403.
        self.assertEqual(client.get(self.preview_url(self.other_group), {"period": "last_month"}).status_code, 404)
        self.assertEqual(client.post(self.generate_url(self.other_group), TEXT_ONLY, format="json").status_code, 404)

    def test_preview_stores_nothing(self):
        self.client_for(self.admin).get(self.preview_url(), {"period": "last_month"})
        self.assertFalse(ParentReport.objects.exists())

    def test_preview_query_booleans_default_to_true(self):
        response = self.client_for(self.admin).get(self.preview_url(), {"period": "last_month"})
        self.assertIn("Коротко о группе", response.data["text"])
        response = self.client_for(self.admin).get(
            self.preview_url(), {"period": "last_month", "include_group_stats": "false"},
        )
        self.assertNotIn("Коротко о группе", response.data["text"])

    def test_admin_reaches_every_group(self):
        client = self.client_for(self.admin)
        self.assertEqual(client.get(self.preview_url(self.other_group), {"period": "last_month"}).status_code, 200)
        response = client.post(self.generate_url(self.other_group), TEXT_ONLY, format="json")
        self.assertEqual(response.status_code, 201, response.content)
        self.assertIsNone(response.data["snapshot"]["teacher_scope_id"])

    def test_team_lead_reads_but_never_generates(self):
        client = self.client_for(self.team_lead)
        self.assertEqual(client.get(self.preview_url(), {"period": "last_month"}).status_code, 200)
        self.assertEqual(client.post(self.generate_url(), TEXT_ONLY, format="json").status_code, 403)
        report = self.client_for(self.admin).post(self.generate_url(), TEXT_ONLY, format="json").data
        self.assertEqual(client.get(reverse("parent-report-detail", args=[report["id"]])).status_code, 200)
        self.assertEqual(client.post(reverse("parent-report-regenerate", args=[report["id"]])).status_code, 403)
        self.assertEqual(client.post(reverse("parent-report-text", args=[report["id"]]), {"text": "x"}, format="json").status_code, 403)

    def test_roles_without_kpi_access_are_denied(self):
        for user in (self.assistant, self.director):
            client = self.client_for(user)
            self.assertEqual(client.get(self.preview_url(), {"period": "last_month"}).status_code, 403, user.role)
            self.assertEqual(client.get(reverse("parent-report-list")).status_code, 403, user.role)
        self.assertEqual(APIClient().get(self.preview_url()).status_code, 401)

    def test_trainer_history_shows_only_own_scope(self):
        admin_report = self.client_for(self.admin).post(self.generate_url(), TEXT_ONLY, format="json").data
        client = self.client_for(self.trainer.user)
        own = client.post(self.generate_url(), TEXT_ONLY, format="json").data
        listing = client.get(reverse("parent-report-list")).data["results"]
        self.assertEqual([row["id"] for row in listing], [own["id"]])
        # A report built over every trainer's lessons is not the trainer's to read.
        self.assertEqual(client.get(reverse("parent-report-detail", args=[admin_report["id"]])).status_code, 404)
        other = self.client_for(self.other_trainer.user)
        self.assertEqual(other.get(reverse("parent-report-detail", args=[own["id"]])).status_code, 404)
        self.assertEqual(other.get(reverse("parent-report-list")).data["results"], [])

    def test_trainer_report_counts_only_own_lessons(self):
        english, _ = Subject.objects.get_or_create(name="English")
        program = GroupTeacher.objects.create(group=self.group, teacher=self.other_trainer, subject=english)
        theirs = self.lesson(dt.date(2026, 10, 6), teacher=self.other_trainer, program=program)
        self.mark(theirs, self.anna, "absent")
        own = self.client_for(self.trainer.user).post(self.generate_url(), TEXT_ONLY, format="json").data
        self.assertEqual(own["snapshot"]["group_stats"]["conducted_lessons"], 3)
        everything = self.client_for(self.admin).post(self.generate_url(), TEXT_ONLY, format="json").data
        self.assertEqual(everything["snapshot"]["group_stats"]["conducted_lessons"], 4)


class ValidationTests(ApiFixture):
    def test_dates_are_validated(self):
        client = self.client_for(self.admin)
        cases = [
            ({"period": "custom", "start_date": "2026-10-10", "end_date": "2026-10-01"}, "start_date"),
            ({"period": "custom", "start_date": "2026-12-01", "end_date": "2026-12-31"}, "start_date"),
            ({"period": "custom", "start_date": "2026-10-01"}, "start_date"),
            ({"period": "custom", "start_date": "not-a-date", "end_date": "2026-10-01"}, "start_date"),
            ({"period": "forever"}, "period"),
            ({"period": "last_month", "language": "en"}, "language"),
            ({"period": "last_month", "report_type": "school"}, "report_type"),
        ]
        for params, field in cases:
            response = client.get(self.preview_url(), params)
            self.assertEqual(response.status_code, 400, params)
            self.assertIn(field, response.data, params)

    def test_student_ids_must_belong_to_the_group(self):
        stranger = self.student("Чужой", "Студент", group=self.other_group)
        response = self.client_for(self.admin).post(
            self.generate_url(), {**TEXT_ONLY, "report_type": "students", "student_ids": [stranger.pk]}, format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("student_ids", response.data)

    def test_unknown_group(self):
        response = self.client_for(self.admin).get(reverse("parent-report-preview", args=[999999]))
        self.assertEqual(response.status_code, 404)

    def test_client_kpi_values_are_ignored(self):
        response = self.client_for(self.admin).post(
            self.generate_url(), {**TEXT_ONLY, "attendance_rate": 100, "group_stats": {"attendance_rate": 100}}, format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["snapshot"]["group_stats"]["attendance_rate"], 66.7)


class HistoryTests(ApiFixture):
    def test_generate_stores_history_and_never_overwrites(self):
        client = self.client_for(self.trainer.user)
        first = client.post(self.generate_url(), TEXT_ONLY, format="json").data
        second = client.post(self.generate_url(), {**TEXT_ONLY, "language": "ky"}, format="json").data
        self.assertNotEqual(first["id"], second["id"])
        self.assertEqual(ParentReport.objects.count(), 2)
        report = ParentReport.objects.get(pk=first["id"])
        self.assertEqual(report.group, self.group)
        self.assertEqual(report.created_by, self.trainer.user)
        self.assertEqual(report.teacher_scope, self.trainer)
        self.assertEqual((report.start_date, report.end_date), (dt.date(2026, 10, 1), dt.date(2026, 10, 31)))
        self.assertEqual((report.compare_start_date, report.compare_end_date), (dt.date(2026, 9, 1), dt.date(2026, 9, 30)))
        self.assertEqual(report.status, ParentReport.Status.READY)
        self.assertIn("Уважаемые родители", report.text)
        self.assertEqual(report.snapshot["group_stats"]["conducted_lessons"], 3)
        self.assertFalse(report.images.exists())  # text only
        self.assertTrue(second["final_text"].startswith("Саламатсыздарбы"))

        listing = client.get(reverse("parent-report-list"), {"group": self.group.pk}).data
        self.assertEqual([row["id"] for row in listing["results"]], [second["id"], first["id"]])

    def test_detail_has_recommendations(self):
        report = self.client_for(self.admin).post(self.generate_url(), TEXT_ONLY, format="json").data
        detail = self.client_for(self.admin).get(reverse("parent-report-detail", args=[report["id"]])).data
        self.assertEqual(set(detail["recommendations"]["group"]), {"strengths", "attention", "parents"})
        self.assertIn(str(self.anna.pk), detail["recommendations"]["students"])

    def test_individual_reports_have_one_text_per_student(self):
        report = self.client_for(self.admin).post(
            self.generate_url(), {**TEXT_ONLY, "report_type": "students"}, format="json",
        ).data
        self.assertEqual(set(report["student_texts"]), {str(self.anna.pk), str(self.bek.pk)})
        self.assertIn("*Анна Алиева*", report["student_texts"][str(self.anna.pk)])

    def test_regenerate_creates_a_new_report_from_current_data(self):
        client = self.client_for(self.admin)
        first = client.post(self.generate_url(), TEXT_ONLY, format="json").data
        self.mark(self.open_past, self.anna, "present")
        self.open_past.status = "completed"
        self.open_past.save()
        response = client.post(reverse("parent-report-regenerate", args=[first["id"]]))
        self.assertEqual(response.status_code, 201, response.content)
        new = response.data
        self.assertNotEqual(new["id"], first["id"])
        self.assertEqual(new["regenerated_from"], first["id"])
        self.assertEqual((new["start_date"], new["end_date"]), (first["start_date"], first["end_date"]))
        self.assertEqual(new["period_key"], "last_month")
        self.assertEqual(new["snapshot"]["group_stats"]["conducted_lessons"], 4)
        # The original is untouched.
        self.assertEqual(ParentReport.objects.get(pk=first["id"]).snapshot["group_stats"]["conducted_lessons"], 3)

    def test_admin_regenerating_a_trainer_report_keeps_its_scope(self):
        english, _ = Subject.objects.get_or_create(name="English")
        program = GroupTeacher.objects.create(group=self.group, teacher=self.other_trainer, subject=english)
        self.lesson(dt.date(2026, 10, 6), teacher=self.other_trainer, program=program)
        own = self.client_for(self.trainer.user).post(self.generate_url(), TEXT_ONLY, format="json").data
        again = self.client_for(self.admin).post(reverse("parent-report-regenerate", args=[own["id"]])).data
        self.assertEqual(again["snapshot"]["teacher_scope_id"], self.trainer.pk)
        self.assertEqual(again["snapshot"]["group_stats"]["conducted_lessons"], 3)

    def test_text_edit_reset_and_language(self):
        client = self.client_for(self.trainer.user)
        report = client.post(self.generate_url(), TEXT_ONLY, format="json").data
        url = reverse("parent-report-text", args=[report["id"]])

        edited = client.post(url, {"text": "Мой текст для родителей"}, format="json").data
        self.assertEqual(edited["final_text"], "Мой текст для родителей")
        self.assertIn("Уважаемые родители", edited["text"])  # the generated text is kept

        kyrgyz = client.post(url, {"language": "ky"}, format="json").data
        self.assertTrue(kyrgyz["text"].startswith("Саламатсыздарбы"))
        self.assertEqual(ParentReport.objects.get(pk=report["id"]).edited_text, "Мой текст для родителей")

        student = client.post(url, {"text": "Для Анны", "student_id": self.anna.pk}, format="json").data
        self.assertEqual(student["edited_student_texts"], {str(self.anna.pk): "Для Анны"})
        reset = client.post(url, {"reset": True}, format="json").data
        self.assertEqual(reset["final_text"], reset["text"])
        self.assertEqual(client.post(url, {"student_id": 999999, "text": "x"}, format="json").status_code, 400)
        self.assertEqual(client.post(url, {}, format="json").status_code, 400)

    def test_download_without_image(self):
        report = self.client_for(self.admin).post(self.generate_url(), TEXT_ONLY, format="json").data
        response = self.client_for(self.admin).get(reverse("parent-report-download", args=[report["id"]]))
        self.assertEqual(response.status_code, 404)
