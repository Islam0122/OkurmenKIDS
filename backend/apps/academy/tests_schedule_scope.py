"""Role scope of the schedule and the data around it (who sees what):

    Admin      everything; writes
    Team Lead  the whole academy, read-only (apps.users.permissions —
               can_view_academy); plus the group's academic configuration
    Trainer    own lessons / slots / programs; the groups they teach (roster)

Every rule is enforced in the backend querysets — a query parameter or an
id in the URL never widens it (IDOR). Absolute imports only (see
apps/academy/tests.py)."""
from __future__ import annotations

import datetime as dt

from django.test import TestCase
from rest_framework.test import APIClient

from apps.academy.models import Course, CourseLessonPlan, Group, GroupSchedule, Lesson, Room, Student
from apps.academy.services.lesson_generator import generate_lessons_for_group
from apps.academy.tests import make_admin, make_teacher
from apps.users.models import Subject, User

START = dt.date(2026, 10, 5)  # a Monday
API = "/api/v1"


class ScheduleScopeFixture(TestCase):
    """Prog SOFT 1: Aizhan teaches English (Mon 19:30), Islam teaches IT
    (Mon 08:00) — one shared group, two trainers. Prog SOFT 2: only Nurisa."""

    def setUp(self):
        self.admin = make_admin("scope_admin")
        self.lead = User.objects.create_user(
            username="scope_lead", email="lead@okurmen.kg", password="x", first_name="Lead", role=User.Role.TEAM_LEAD,
        )
        self.aizhan = make_teacher("aizhan_scope")
        self.islam = make_teacher("islam_scope")
        self.nurisa = make_teacher("nurisa_scope")
        self.english = Subject.objects.get_or_create(name="English")[0]
        self.it = Subject.objects.get_or_create(name="IT")[0]
        self.room = Room.objects.create(name="online_1", capacity=20)
        self.room2 = Room.objects.create(name="Аудитория 22", capacity=20)

        course = Course.objects.create(name="Scope course", count_lesson=4)
        course.subjects.set([self.english, self.it])
        for number, subject in enumerate([self.english, self.it, self.english, self.it], start=1):
            CourseLessonPlan.objects.create(course=course, lesson_number=number, subject=subject, topic=f"Тема {number}")
        self.shared = Group.objects.create(name="Prog SOFT 1", course=course, start_date=START)
        GroupSchedule.objects.create(group=self.shared, teacher=self.aizhan, subject=self.english, day_of_week="mon",
                                     start_time=dt.time(19, 30), end_time=dt.time(20, 30), room=self.room)
        GroupSchedule.objects.create(group=self.shared, teacher=self.islam, subject=self.it, day_of_week="mon",
                                     start_time=dt.time(8, 0), end_time=dt.time(9, 0), room=self.room2)
        generate_lessons_for_group(self.shared)

        course2 = Course.objects.create(name="Scope course 2", count_lesson=2)
        course2.subjects.set([self.it])
        for number in (1, 2):
            CourseLessonPlan.objects.create(course=course2, lesson_number=number, subject=self.it, topic=f"IT {number}")
        self.other = Group.objects.create(name="Prog SOFT 2", course=course2, start_date=START)
        GroupSchedule.objects.create(group=self.other, teacher=self.nurisa, subject=self.it, day_of_week="mon",
                                     start_time=dt.time(19, 30), end_time=dt.time(20, 30), room=self.room2)
        generate_lessons_for_group(self.other)
        self.student = Student.objects.create(first_name="Айдай", group=self.other)

        self.aizhan_lesson = Lesson.objects.filter(group=self.shared, subject=self.english).first()
        self.islam_lesson = Lesson.objects.filter(group=self.shared, subject=self.it).first()
        self.nurisa_lesson = Lesson.objects.filter(group=self.other).first()
        assert self.aizhan_lesson and self.islam_lesson and self.nurisa_lesson

    def client_for(self, user):
        client = APIClient()
        client.force_authenticate(user)
        return client

    def lesson_ids(self, client, **params):
        response = client.get(f"{API}/lessons/", {"page_size": 200, **params})
        self.assertEqual(response.status_code, 200)
        return {row["id"] for row in response.data["results"]}


class TrainerScopeTests(ScheduleScopeFixture):
    def setUp(self):
        super().setUp()
        self.api = self.client_for(self.aizhan.user)

    def test_schedule_is_own_lessons_only(self):
        ids = self.lesson_ids(self.api, date_from="2026-10-01", date_to="2026-12-31")
        own = set(Lesson.objects.filter(teacher=self.aizhan).values_list("id", flat=True))
        self.assertEqual(ids, own)
        self.assertNotIn(self.islam_lesson.id, ids)  # a colleague in the same group
        self.assertNotIn(self.nurisa_lesson.id, ids)  # another group

    def test_query_params_never_widen_the_scope(self):
        self.assertEqual(self.lesson_ids(self.api, group=self.other.id), set())
        self.assertEqual(self.lesson_ids(self.api, subject=self.it.id), set())
        self.assertEqual(self.lesson_ids(self.api, room=self.room2.id), set())
        self.assertNotIn(self.islam_lesson.id, self.lesson_ids(self.api, teacher=self.islam.id))

    def test_idor_by_id(self):
        for url in (
            f"{API}/lessons/{self.islam_lesson.id}/",
            f"{API}/lessons/{self.nurisa_lesson.id}/",
            f"{API}/groups/{self.other.id}/",
            f"{API}/groups/{self.other.id}/schedule/",
            f"{API}/groups/{self.other.id}/students/",
            f"{API}/students/{self.student.id}/",
        ):
            self.assertEqual(self.api.get(url).status_code, 404, url)

    def test_shared_group_shows_only_own_programs_and_slots(self):
        group = self.api.get(f"{API}/groups/{self.shared.id}/").data
        self.assertEqual({slot["teacher"] for slot in group["schedules"]}, {self.aizhan.id})
        self.assertEqual({program["teacher"] for program in group["teachers"]}, {self.aizhan.id})
        listed = next(g for g in self.api.get(f"{API}/groups/").data["results"] if g["id"] == self.shared.id)
        self.assertEqual({slot["teacher"] for slot in listed["schedules"]}, {self.aizhan.id})
        schedule = self.api.get(f"{API}/groups/{self.shared.id}/schedule/").data
        self.assertEqual({slot["teacher"] for slot in schedule["group"]["schedules"]}, {self.aizhan.id})
        lesson_ids = {row["id"] for row in schedule["lessons"]}
        self.assertIn(self.aizhan_lesson.id, lesson_ids)
        self.assertNotIn(self.islam_lesson.id, lesson_ids)
        # The slot / program endpoints follow the same rule.
        self.assertEqual({row["teacher"] for row in self.api.get(f"{API}/schedules/").data["results"]}, {self.aizhan.id})
        self.assertEqual({row["teacher"] for row in self.api.get(f"{API}/programs/").data["results"]}, {self.aizhan.id})

    def test_academy_wide_tools_are_not_for_trainers(self):
        params = {"date": self.islam_lesson.date.isoformat(), "start_time": "07:00", "end_time": "22:00"}
        self.assertEqual(self.api.get(f"{API}/availability/", params).status_code, 403)
        self.assertEqual(self.api.get(f"{API}/groups/{self.shared.id}/analytics/").status_code, 403)
        self.assertEqual(self.api.get(f"{API}/groups/{self.shared.id}/academic-config/").status_code, 403)

    def test_free_rooms_hide_other_groups(self):
        params = {"date": self.aizhan_lesson.date.isoformat(), "start_time": "07:00", "end_time": "22:00"}
        rows = self.api.get(f"{API}/rooms/available/", params).data["occupied"]
        by_lesson = {row["lesson"]: row for row in rows}
        self.assertEqual(by_lesson[self.aizhan_lesson.id]["group_name"], "Prog SOFT 1")  # own lesson
        self.assertIsNone(by_lesson[self.islam_lesson.id]["group_name"])  # busy, but not whose
        self.assertIsNone(by_lesson[self.nurisa_lesson.id]["group"])
        self.assertEqual(by_lesson[self.nurisa_lesson.id]["room_name"], "Аудитория 22")

    def test_cannot_change_a_colleagues_lesson(self):
        response = self.api.patch(f"{API}/lessons/{self.islam_lesson.id}/", {"topic": "x"}, format="json")
        self.assertEqual(response.status_code, 404)


class TeamLeadScopeTests(ScheduleScopeFixture):
    def setUp(self):
        super().setUp()
        self.api = self.client_for(self.lead)

    def test_sees_every_trainer_and_group(self):
        ids = self.lesson_ids(self.api, date_from="2026-10-01", date_to="2026-12-31")
        self.assertTrue({self.aizhan_lesson.id, self.islam_lesson.id, self.nurisa_lesson.id} <= ids)
        group = self.api.get(f"{API}/groups/{self.shared.id}/").data
        self.assertEqual({slot["teacher"] for slot in group["schedules"]}, {self.aizhan.id, self.islam.id})
        self.assertEqual(self.api.get(f"{API}/groups/{self.other.id}/").status_code, 200)
        params = {"date": self.aizhan_lesson.date.isoformat(), "start_time": "07:00", "end_time": "22:00"}
        self.assertEqual(self.api.get(f"{API}/availability/", params).status_code, 200)
        rooms = self.api.get(f"{API}/rooms/available/", params).data["occupied"]
        self.assertTrue(all(row["group_name"] for row in rooms))

    def test_reads_only(self):
        self.assertEqual(self.api.patch(f"{API}/lessons/{self.aizhan_lesson.id}/", {"topic": "x"}, format="json").status_code, 403)
        self.assertEqual(self.api.patch(f"{API}/groups/{self.shared.id}/", {"name": "x"}, format="json").status_code, 403)
        self.assertEqual(self.api.delete(f"{API}/groups/{self.other.id}/").status_code, 403)
        # …except the group's academic configuration (trainer, subject, slots), its documented right.
        self.assertEqual(self.api.get(f"{API}/groups/{self.shared.id}/academic-config/").status_code, 200)


class AdminScopeTests(ScheduleScopeFixture):
    def test_admin_sees_and_changes_everything(self):
        api = self.client_for(self.admin)
        ids = self.lesson_ids(api, date_from="2026-10-01", date_to="2026-12-31")
        self.assertEqual(ids, set(Lesson.objects.filter(date__gte="2026-10-01").values_list("id", flat=True)))
        self.assertEqual(api.patch(f"{API}/lessons/{self.islam_lesson.id}/", {"topic": "Новая тема"}, format="json").status_code, 200)
