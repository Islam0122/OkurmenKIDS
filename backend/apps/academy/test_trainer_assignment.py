"""Team Lead assigns / replaces a group's trainer — and nothing more.

Absolute imports only — see the note at the top of apps/academy/tests.py.
"""
from __future__ import annotations

import datetime as dt

from django.contrib.admin.models import LogEntry
from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from apps.academy.models import Course, Group, GroupSchedule, GroupTeacher, Lesson, Student
from apps.testing.models import Test, TestSession, TestStatus
from apps.users.models import Subject, Teacher, User

PASSWORD = "Str0ngPassw0rd!"
PAST = {"period": "custom", "start_date": "2020-01-01", "end_date": "2040-12-31"}


def make_teacher(username: str, *, active=True) -> Teacher:
    user = User.objects.create_user(
        username=username, email=f"{username}@okurmen.kg", password=PASSWORD,
        first_name=username.capitalize(), last_name="T", role=User.Role.TEACHER, is_verified=True,
    )
    return Teacher.objects.create(user=user, is_active=active)


class AssignmentFixture(TestCase):
    def setUp(self):
        self.lead = User.objects.create_user(
            username="lead", email="lead@okurmen.kg", password=PASSWORD, first_name="Нурлан", role=User.Role.TEAM_LEAD,
        )
        self.python, _ = Subject.objects.get_or_create(name="Python")
        self.english, _ = Subject.objects.get_or_create(name="English")
        self.course = Course.objects.create(name="Python PRO", count_lesson=20)
        self.course.subjects.set([self.python, self.english])
        self.group = Group.objects.create(name="Python PRO — группа 3", course=self.course, start_date=dt.date(2025, 1, 1))
        self.ivan = make_teacher("ivan")
        self.aigul = make_teacher("aigul")
        self.retired = make_teacher("retired", active=False)
        self.program = GroupTeacher.objects.create(group=self.group, teacher=self.ivan, subject=self.python)
        self.slot = GroupSchedule.objects.create(
            group=self.group, teacher=self.ivan, subject=self.python, day_of_week="mon",
            start_time=dt.time(10), end_time=dt.time(11),
        )
        today = timezone.localdate()
        self.past = Lesson.objects.create(
            group=self.group, group_teacher=self.program, teacher=self.ivan, subject=self.python, lesson_number=1,
            date=today - dt.timedelta(days=7), start_time=dt.time(10), end_time=dt.time(11), status=Lesson.Status.COMPLETED,
        )
        self.future = Lesson.objects.create(
            group=self.group, group_teacher=self.program, teacher=self.ivan, subject=self.python, lesson_number=2,
            date=today + dt.timedelta(days=7), start_time=dt.time(10), end_time=dt.time(11),
        )
        Student.objects.create(first_name="Азамат", last_name="Алиев", group=self.group)
        self.api = APIClient()
        self.api.force_authenticate(self.lead)
        self.url = f"/api/v1/groups/{self.group.pk}/assign-trainer/"


class TeamLeadViewsTests(AssignmentFixture):
    def test_team_lead_can_view_all_groups_and_trainers(self):
        other = Group.objects.create(name="Other", course=self.course, start_date=dt.date(2025, 1, 1))
        groups = {row["id"] for row in self.api.get("/api/v1/groups/").data["results"]}
        self.assertEqual(groups, {self.group.pk, other.pk})
        trainers = {row["id"] for row in self.api.get("/api/v1/trainers/").data["results"]}
        self.assertEqual(trainers, {self.ivan.pk, self.aigul.pk, self.retired.pk})
        self.assertEqual(self.api.get(f"/api/v1/trainers/{self.ivan.pk}/").status_code, 200)

    def test_overview_lists_programs_subjects_and_only_active_trainers(self):
        data = self.api.get(self.url).data
        self.assertEqual(data["group"]["name"], "Python PRO — группа 3")
        self.assertEqual([p["teacher"]["id"] for p in data["programs"]], [self.ivan.pk])
        self.assertEqual(data["programs"][0]["subject"]["name"], "Python")
        self.assertEqual({s["name"] for s in data["subjects"]}, {"Python", "English"})
        self.assertEqual({t["id"] for t in data["trainers"]}, {self.ivan.pk, self.aigul.pk})


class AssignAndReplaceTests(AssignmentFixture):
    def test_team_lead_can_assign_trainer_to_a_subject_without_one(self):
        response = self.api.post(self.url, {"teacher": self.aigul.pk, "subject": self.english.pk}, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.content)
        program = GroupTeacher.objects.get(group=self.group, subject=self.english)
        self.assertEqual(program.teacher, self.aigul)
        row = next(p for p in response.data["programs"] if p["id"] == program.pk)
        self.assertIn("Нурлан", row["assigned_by"])
        self.assertIsNotNone(row["assigned_at"])

    def test_team_lead_can_replace_trainer(self):
        response = self.api.post(self.url, {"teacher": self.aigul.pk, "program": self.program.pk}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.content)
        self.assertEqual(response.data["result"]["previous_teacher"], str(self.ivan))
        self.assertEqual(response.data["result"]["lessons_reassigned"], 1)
        self.program.refresh_from_db()
        self.slot.refresh_from_db()
        self.future.refresh_from_db()
        self.past.refresh_from_db()
        # Group → correct trainer: the program, its weekly slot and future lesson moved…
        self.assertEqual(self.program.teacher, self.aigul)
        self.assertEqual(self.slot.teacher, self.aigul)
        self.assertEqual(self.future.teacher, self.aigul)
        # …the conducted lesson stays the previous trainer's (history / KPI).
        self.assertEqual(self.past.teacher, self.ivan)
        # Audit in Django's own admin history.
        entry = LogEntry.objects.get(object_id=str(self.program.pk))
        self.assertEqual(entry.user, self.lead)
        self.assertIn(f"{self.ivan} → {self.aigul}", entry.change_message)

    def test_replace_by_subject_too(self):
        response = self.api.post(self.url, {"teacher": self.aigul.pk, "subject": self.python.pk}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.content)
        self.program.refresh_from_db()
        self.assertEqual(self.program.teacher, self.aigul)
        self.assertEqual(GroupTeacher.objects.filter(group=self.group, subject=self.python).count(), 1)

    def test_inactive_trainer_or_same_trainer_rejected(self):
        bad = self.api.post(self.url, {"teacher": self.retired.pk, "program": self.program.pk}, format="json")
        self.assertEqual(bad.status_code, 400)
        same = self.api.post(self.url, {"teacher": self.ivan.pk, "program": self.program.pk}, format="json")
        self.assertEqual(same.status_code, 400)
        foreign_subject = Subject.objects.create(name="Chess")
        wrong = self.api.post(self.url, {"teacher": self.aigul.pk, "subject": foreign_subject.pk}, format="json")
        self.assertEqual(wrong.status_code, 400)
        self.program.refresh_from_db()
        self.assertEqual(self.program.teacher, self.ivan)


class AfterAssignmentEverythingFollowsTests(AssignmentFixture):
    def test_reports_kpi_and_sessions_see_the_new_trainer(self):
        self.api.post(self.url, {"teacher": self.aigul.pk, "program": self.program.pk}, format="json")

        # Reports → the group's trainer.
        rows = self.api.get("/api/v1/reports/groups/", PAST).data["results"]
        row = next(r for r in rows if r["id"] == self.group.pk)
        self.assertEqual([t["id"] for t in row["teachers"]], [self.aigul.pk])

        # KPI → the new trainer's report includes the group.
        detail = self.api.get(f"/api/v1/reports/teachers/{self.aigul.pk}/", PAST).data
        self.assertIn(self.group.pk, [g["id"] for g in detail["groups"]])

        # Control → the future lesson is the new trainer's responsibility.
        control = self.api.get(f"/api/v1/control/lessons/{self.future.pk}/")
        self.assertEqual(control.status_code, 200)

        # Sessions → the trainer comes from the group automatically.
        test = Test.objects.create(title="Python Basics #4", subject=self.python, status=TestStatus.ACTIVE)
        today = timezone.localdate() + dt.timedelta(days=1)
        created = self.api.post(
            "/api/v1/teacher/sessions/",
            {"test": str(test.pk), "group": self.group.pk, "date": today.isoformat(), "start_time": "14:00", "end_time": "15:00"},
            format="json",
        )
        self.assertEqual(created.status_code, 201, created.content)
        self.assertEqual(TestSession.objects.get(pk=created.data["id"]).teacher, self.aigul)
        self.assertEqual(created.data["teacher_name"], str(self.aigul))


class TeamLeadStillCannotManageTrainersTests(AssignmentFixture):
    def test_cannot_edit_delete_create_or_verify_trainers(self):
        self.assertIn(self.api.patch(f"/api/v1/trainers/{self.ivan.pk}/", {"position": "X"}, format="json").status_code, (403, 405))
        self.assertIn(self.api.put(f"/api/v1/trainers/{self.ivan.pk}/", {"position": "X"}, format="json").status_code, (403, 405))
        self.assertEqual(self.api.delete(f"/api/v1/trainers/{self.ivan.pk}/").status_code, 403)
        self.assertEqual(self.api.post("/api/v1/trainers/", {"username": "x"}, format="json").status_code, 403)
        self.assertEqual(self.api.post(f"/api/v1/trainers/{self.ivan.pk}/verify/").status_code, 403)
        self.ivan.refresh_from_db()
        self.assertTrue(self.ivan.is_active)
        self.assertEqual(self.ivan.position, "Тренер")

    def test_cannot_change_trainer_role_or_permissions(self):
        web = self.client_class()
        web.force_login(self.lead)
        response = web.post(f"/admin/users/user/{self.ivan.user.pk}/change/", {"role": User.Role.ADMIN, "is_superuser": "on"})
        self.assertEqual(response.status_code, 302)  # bounced to the admin login
        self.ivan.user.refresh_from_db()
        self.assertEqual(self.ivan.user.role, User.Role.TEACHER)
        self.assertFalse(self.ivan.user.is_superuser)
        self.assertEqual(self.ivan.user.user_permissions.count(), 0)

    def test_cannot_edit_groups_or_programs_directly(self):
        self.assertEqual(self.api.patch(f"/api/v1/groups/{self.group.pk}/", {"name": "X"}, format="json").status_code, 403)
        self.assertEqual(self.api.delete(f"/api/v1/groups/{self.group.pk}/").status_code, 403)
        self.assertEqual(
            self.api.patch(f"/api/v1/programs/{self.program.pk}/", {"teacher": self.aigul.pk}, format="json").status_code, 403
        )
        self.assertEqual(self.api.delete(f"/api/v1/programs/{self.program.pk}/").status_code, 403)
        self.program.refresh_from_db()
        self.assertEqual(self.program.teacher, self.ivan)


class TrainerGetsNoNewRightTests(AssignmentFixture):
    def test_trainer_cannot_assign(self):
        trainer = APIClient()
        trainer.force_authenticate(self.ivan.user)
        self.assertEqual(trainer.get(self.url).status_code, 403)
        self.assertEqual(trainer.post(self.url, {"teacher": self.aigul.pk, "program": self.program.pk}, format="json").status_code, 403)
        self.program.refresh_from_db()
        self.assertEqual(self.program.teacher, self.ivan)

    def test_admin_can_assign(self):
        admin = User.objects.create_superuser(username="root", email="root@okurmen.kg", password=PASSWORD, first_name="R")
        client = APIClient()
        client.force_authenticate(admin)
        response = client.post(self.url, {"teacher": self.aigul.pk, "program": self.program.pk}, format="json")
        self.assertEqual(response.status_code, 200, response.content)
