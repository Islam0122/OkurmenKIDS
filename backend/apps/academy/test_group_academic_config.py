"""Team Lead manages a group's academic configuration — trainer, subject and
per-day weekly slots (time + room) — and generates its lessons, through the
existing GroupTeacher / GroupSchedule / lesson generator. Nothing else.

Absolute imports only — see the note at the top of apps/academy/tests.py.
"""
from __future__ import annotations

import datetime as dt

from django.contrib.admin.models import LogEntry
from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from apps.academy.models import Course, CourseLessonPlan, Group, GroupSchedule, GroupTeacher, Lesson, Room, Student
from apps.testing.models import Test, TestSession, TestStatus
from apps.users.models import Subject, Teacher, User

PASSWORD = "Str0ngPassw0rd!"


def make_teacher(username: str) -> Teacher:
    user = User.objects.create_user(
        username=username, email=f"{username}@okurmen.kg", password=PASSWORD,
        first_name=username.capitalize(), last_name="T", role=User.Role.TEACHER, is_verified=True,
    )
    return Teacher.objects.create(user=user)


def next_weekday(weekday: int) -> dt.date:
    today = timezone.localdate()
    return today + dt.timedelta(days=(weekday - today.weekday()) % 7 or 7)


class ConfigFixture(TestCase):
    def setUp(self):
        self.lead = User.objects.create_user(
            username="lead", email="lead@okurmen.kg", password=PASSWORD, first_name="Нурлан", role=User.Role.TEAM_LEAD,
        )
        self.python, _ = Subject.objects.get_or_create(name="Python")
        self.english, _ = Subject.objects.get_or_create(name="English")
        self.course = Course.objects.create(name="Python PRO", count_lesson=8)
        self.course.subjects.set([self.python, self.english])
        for number in range(1, 9):
            CourseLessonPlan.objects.create(course=self.course, lesson_number=number, subject=self.python, topic=f"Тема {number}")
        self.start = next_weekday(0)  # a coming Monday
        self.group = Group.objects.create(name="Python PRO — группа 3", course=self.course, start_date=self.start)
        self.other_group = Group.objects.create(name="Frontend-1", course=self.course, start_date=self.start)
        self.ivan = make_teacher("ivan")
        self.petrov = make_teacher("petrov")
        self.room101 = Room.objects.create(name="Кабинет 101", capacity=12)
        self.room205 = Room.objects.create(name="Кабинет 205", capacity=12)
        Student.objects.create(first_name="Азамат", last_name="Алиев", group=self.group)
        self.api = APIClient()
        self.api.force_authenticate(self.lead)
        self.url = f"/api/v1/groups/{self.group.pk}/academic-config/"

    SCHEDULE = [
        {"weekday": 1, "start_time": "13:00", "end_time": "14:00", "room_id": None},
        {"day": "wed", "start": "13:00", "end": "14:00", "room": None},
        {"weekday": "friday", "start_time": "13:00", "end_time": "14:00", "room_id": None},
        {"weekday": 7, "start_time": "20:00", "end_time": "21:00", "room_id": None},
    ]

    def schedule(self, rooms=(None, None, None, None)):
        return [{**slot, ("room_id" if "room_id" in slot else "room"): room} for slot, room in zip(self.SCHEDULE, rooms)]

    def create_program(self, **overrides):
        body = {
            "teacher": self.ivan.pk,
            "subject": self.python.pk,
            "schedule": self.schedule((self.room101.pk, self.room101.pk, self.room101.pk, self.room205.pk)),
            **overrides,
        }
        return self.api.post(self.url, body, format="json")


class TeamLeadConfiguresGroupTests(ConfigFixture):
    def test_overview_lists_what_can_be_chosen(self):
        data = self.api.get(self.url).data
        self.assertEqual(data["programs"], [])
        self.assertEqual({s["name"] for s in data["subjects"]}, {"Python", "English"})
        self.assertEqual({t["id"] for t in data["trainers"]}, {self.ivan.pk, self.petrov.pk})
        self.assertEqual({r["name"] for r in data["rooms"]}, {"Кабинет 101", "Кабинет 205"})
        self.assertEqual([d["code"] for d in data["weekdays"]], ["mon", "tue", "wed", "thu", "fri", "sat", "sun"])

    def test_assign_trainer_subject_and_per_day_schedule_with_rooms(self):
        response = self.create_program()
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.content)
        program = GroupTeacher.objects.get(group=self.group, subject=self.python)
        self.assertEqual(program.teacher, self.ivan)
        slots = {s.day_of_week: s for s in GroupSchedule.objects.filter(group_teacher=program)}
        self.assertEqual(set(slots), {"mon", "wed", "fri", "sun"})
        self.assertEqual((slots["sun"].start_time, slots["sun"].end_time, slots["sun"].room), (dt.time(20), dt.time(21), self.room205))
        self.assertEqual(slots["mon"].room, self.room101)
        self.assertTrue(all(s.teacher == self.ivan and s.subject == self.python for s in slots.values()))
        row = response.data["programs"][0]
        self.assertEqual([s["day"] for s in row["slots"]], ["mon", "wed", "fri", "sun"])
        self.assertEqual(row["slots"][3]["room"]["name"], "Кабинет 205")
        self.assertIn("Нурлан", row["assigned_by"])

    def test_different_subject_and_trainer_on_another_day(self):
        self.create_program()
        response = self.api.post(self.url, {
            "teacher": self.petrov.pk, "subject": self.english.pk,
            "schedule": [{"day": "tue", "start": "15:00", "end": "16:30", "room": self.room101.pk}],
        }, format="json")
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(GroupTeacher.objects.filter(group=self.group).count(), 2)

    def test_change_schedule_trainer_and_remove_one_slot(self):
        self.create_program()
        program = GroupTeacher.objects.get(group=self.group, subject=self.python)
        slots = {s.day_of_week: s for s in program.schedules.all()}
        response = self.api.put(f"{self.url}programs/{program.pk}/", {
            "teacher": self.petrov.pk, "subject": self.python.pk,
            "schedule": [
                {"id": slots["mon"].pk, "day": "mon", "start": "13:00", "end": "14:00", "room": self.room101.pk},
                {"id": slots["wed"].pk, "day": "wed", "start": "15:00", "end": "16:30", "room": self.room101.pk},
                {"id": slots["fri"].pk, "day": "fri", "start": "13:00", "end": "14:00", "room": self.room205.pk},
                # Sunday left out → only that slot is removed.
            ],
        }, format="json")
        self.assertEqual(response.status_code, 200, response.content)
        program.refresh_from_db()
        self.assertEqual(program.teacher, self.petrov)
        after = {s.day_of_week: s for s in program.schedules.all()}
        self.assertEqual(set(after), {"mon", "wed", "fri"})
        self.assertEqual(after["mon"].pk, slots["mon"].pk)
        self.assertEqual((after["wed"].start_time, after["wed"].end_time), (dt.time(15), dt.time(16, 30)))
        self.assertEqual(after["fri"].room, self.room205)
        self.assertTrue(all(s.teacher == self.petrov for s in after.values()))
        # History: before → after.
        entry = LogEntry.objects.filter(object_id=str(program.pk)).order_by("-action_time").first()
        self.assertIn("Было: Тренер: Ivan T", entry.change_message)
        self.assertIn("Стало: Тренер: Petrov T", entry.change_message)

    def test_team_lead_generates_lessons_from_each_slot(self):
        self.create_program()
        response = self.api.post(f"/api/v1/groups/{self.group.pk}/generate-lessons/")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.content)
        lessons = list(Lesson.objects.filter(group=self.group).order_by("date", "start_time"))
        self.assertEqual(len(lessons), 8)
        for lesson in lessons:
            weekday = lesson.date.weekday()
            self.assertIn(weekday, (0, 2, 4, 6))
            self.assertEqual(lesson.teacher, self.ivan)
            self.assertEqual(lesson.subject, self.python)
            if weekday == 6:
                self.assertEqual((lesson.start_time, lesson.room), (dt.time(20), self.room205))
            else:
                self.assertEqual((lesson.start_time, lesson.room), (dt.time(13), self.room101))
        preview = self.api.get(f"/api/v1/groups/{self.group.pk}/generate-lessons/preview/")
        self.assertEqual(preview.status_code, 200)

    def test_session_takes_trainer_and_subject_from_the_group(self):
        self.create_program()
        test = Test.objects.create(title="Python Basics #4", subject=self.python, status=TestStatus.ACTIVE)
        created = self.api.post("/api/v1/teacher/sessions/", {
            "test": str(test.pk), "group": self.group.pk,
            "date": (timezone.localdate() + dt.timedelta(days=3)).isoformat(), "start_time": "14:00", "end_time": "15:30",
        }, format="json")
        self.assertEqual(created.status_code, 201, created.content)
        session = TestSession.objects.get(pk=created.data["id"])
        self.assertEqual(session.teacher, self.ivan)
        self.assertEqual(created.data["subject"], "Python")


class ConflictAndValidationTests(ConfigFixture):
    def test_trainer_conflict(self):
        GroupSchedule.objects.create(group=self.other_group, teacher=self.ivan, subject=self.python,
                                     day_of_week="mon", start_time=dt.time(13, 30), end_time=dt.time(14, 30))
        response = self.create_program()
        self.assertEqual(response.status_code, 400)
        self.assertIn("Тренер «Ivan T» уже занят", " ".join(response.data["schedule"]))
        self.assertIn("Понедельник 13:30–14:30", " ".join(response.data["schedule"]))
        self.assertFalse(GroupTeacher.objects.filter(group=self.group).exists())  # all or nothing

    def test_room_conflict(self):
        GroupSchedule.objects.create(group=self.other_group, teacher=self.petrov, subject=self.python,
                                     day_of_week="mon", start_time=dt.time(13, 30), end_time=dt.time(14, 30), room=self.room101)
        response = self.create_program()
        self.assertEqual(response.status_code, 400)
        message = " ".join(response.data["schedule"])
        self.assertIn("Аудитория «Кабинет 101» уже занята", message)
        self.assertIn("Frontend-1", message)

    def test_group_conflict(self):
        self.create_program()
        response = self.api.post(self.url, {
            "teacher": self.petrov.pk, "subject": self.english.pk,
            "schedule": [{"day": "mon", "start": "13:30", "end": "14:30", "room": None}],
        }, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("уже занята в это время программой", " ".join(response.data["schedule"]))

    def test_overlap_within_the_list_and_touching_ends(self):
        overlap = self.create_program(schedule=[
            {"day": "mon", "start": "14:00", "end": "15:30"}, {"day": "mon", "start": "15:00", "end": "16:00"},
        ])
        self.assertEqual(overlap.status_code, 400)
        touching = self.create_program(schedule=[
            {"day": "mon", "start": "14:00", "end": "15:30"}, {"day": "mon", "start": "15:30", "end": "17:00"},
        ])
        self.assertEqual(touching.status_code, 201, touching.content)

    def test_invalid_time_and_weekday(self):
        bad_time = self.create_program(schedule=[{"day": "mon", "start": "14:00", "end": "13:00"}])
        self.assertEqual(bad_time.status_code, 400)
        self.assertIn("время окончания должно быть позже времени начала", " ".join(bad_time.data["schedule"]))
        bad_day = self.create_program(schedule=[{"day": "funday", "start": "14:00", "end": "15:00"}])
        self.assertEqual(bad_day.status_code, 400)
        bad_number = self.create_program(schedule=[{"weekday": 9, "start_time": "14:00", "end_time": "15:00"}])
        self.assertEqual(bad_number.status_code, 400)
        no_schedule = self.api.post(self.url, {"teacher": self.ivan.pk, "subject": self.python.pk}, format="json")
        self.assertEqual(no_schedule.status_code, 400)
        self.assertFalse(GroupTeacher.objects.filter(group=self.group).exists())

    def test_second_program_for_the_same_subject_is_refused(self):
        self.create_program()
        again = self.api.post(self.url, {
            "teacher": self.petrov.pk, "subject": self.python.pk,
            "schedule": [{"day": "tue", "start": "10:00", "end": "11:00"}],
        }, format="json")
        self.assertEqual(again.status_code, 400)
        self.assertIn("subject", again.data)


class TeamLeadStillCannotEditEntitiesTests(ConfigFixture):
    def test_cannot_edit_trainer_subject_room_student_test(self):
        student = Student.objects.get()
        test = Test.objects.create(title="T", subject=self.python, status=TestStatus.ACTIVE)
        self.assertEqual(self.api.delete(f"/api/v1/trainers/{self.ivan.pk}/").status_code, 403)
        self.assertIn(self.api.patch(f"/api/v1/trainers/{self.ivan.pk}/", {"position": "X"}, format="json").status_code, (403, 405))
        self.assertIn(self.api.patch(f"/api/v1/subjects/{self.python.pk}/", {"name": "X"}, format="json").status_code, (403, 405))
        self.assertIn(self.api.delete(f"/api/v1/subjects/{self.python.pk}/").status_code, (403, 405))
        self.assertEqual(self.api.patch(f"/api/v1/rooms/{self.room101.pk}/", {"name": "X"}, format="json").status_code, 403)
        self.assertEqual(self.api.patch(f"/api/v1/students/{student.pk}/", {"group": self.other_group.pk}, format="json").status_code, 403)
        self.assertEqual(self.api.patch(f"/api/v1/tests/{test.pk}/", {"title": "X"}, format="json").status_code, 403)
        self.assertEqual(self.api.delete(f"/api/v1/groups/{self.group.pk}/").status_code, 403)
        self.assertEqual(self.api.patch(f"/api/v1/groups/{self.group.pk}/", {"name": "X"}, format="json").status_code, 403)
        # The direct slot / program endpoints stay Admin-only too.
        self.assertEqual(self.api.post("/api/v1/schedules/", {}, format="json").status_code, 403)
        self.python.refresh_from_db()
        student.refresh_from_db()
        self.assertEqual(self.python.name, "Python")
        self.assertEqual(student.group, self.group)


class OtherRolesTests(ConfigFixture):
    def test_trainer_has_no_access(self):
        trainer = APIClient()
        trainer.force_authenticate(self.ivan.user)
        self.assertEqual(trainer.get(self.url).status_code, 403)
        self.assertEqual(trainer.post(self.url, {}, format="json").status_code, 403)
        self.assertEqual(trainer.post(f"/api/v1/groups/{self.group.pk}/generate-lessons/").status_code, 403)

    def test_admin_still_can(self):
        admin = User.objects.create_superuser(username="root", email="root@okurmen.kg", password=PASSWORD, first_name="R")
        client = APIClient()
        client.force_authenticate(admin)
        self.api = client
        self.assertEqual(self.create_program().status_code, 201)
        self.assertEqual(client.post(f"/api/v1/groups/{self.group.pk}/generate-lessons/").status_code, 201)
