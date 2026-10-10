"""The public schedule API (/api/v1/public/schedule/): open to anyone, GET
only, a closed whitelist of fields — never personal data or database ids.

Absolute imports only — see the note at the top of apps/academy/tests.py.
"""
from __future__ import annotations

import datetime as dt
import json
import re

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.academy.models import (
    Attendance, Course, Group, GroupTeacher, Homework, HomeworkResult, Lesson, Room, Student,
)
from apps.academy.services import public_schedule
from apps.users.models import Subject, Teacher, User

TODAY = timezone.localdate()
LOCMEM = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "public-schedule-tests"}}

LESSON_KEYS = {"key", "date", "start", "end", "duration_minutes", "group", "course", "subject", "status",
               "status_label", "rescheduled", "trainer", "room"}
GROUP_KEYS = {"key", "name"}
TRAINER_KEYS = {"key", "name", "color"}
ROOM_KEYS = {"key", "name"}


class PublicScheduleFixture(TestCase):
    def setUp(self):
        cache.clear()
        self.python, _ = Subject.objects.get_or_create(name="Python")
        self.course = Course.objects.create(name="Prog SOFT", count_lesson=40)
        self.course.subjects.set([self.python])
        self.user = User.objects.create_user(
            username="trainer.secret", email="trainer.secret@okurmen.kg", password="x", first_name="Айжаркын",
            last_name="Өмүрбекова", role=User.Role.TEACHER, is_verified=True,
        )
        self.teacher = Teacher.objects.create(user=self.user, phone="+996 555 123 456", bio="Внутренняя заметка")
        self.other = Teacher.objects.create(user=User.objects.create_user(
            username="b2", email="b2@okurmen.kg", password="x", first_name="Бакыт", last_name="Асанов",
            role=User.Role.TEACHER, is_verified=True))
        self.group = Group.objects.create(name="Prog SOFT 1 — вечерняя группа", course=self.course, start_date=TODAY - dt.timedelta(days=60),
                                          description="Внутренний комментарий группы")
        self.room = Room.objects.create(name="Кабинет 201", description="Ключ у охраны")
        self.program = GroupTeacher.objects.create(group=self.group, teacher=self.teacher, subject=self.python)
        self.student = Student.objects.create(first_name="Азамат", last_name="Студентов", group=self.group,
                                              phone="+996 700 000 111", parent_phone="+996 700 000 222")
        self.lesson = Lesson.objects.create(
            group=self.group, group_teacher=self.program, subject=self.python, lesson_number=1, date=TODAY,
            start_time=dt.time(14), end_time=dt.time(15, 30), room=self.room, topic="Тема: внутренний план урока",
            description="Внутреннее описание",
        )
        Attendance.objects.create(student=self.student, lesson=self.lesson, status=Attendance.Status.ABSENT, comment="болел")
        hw = Homework.objects.create(lesson=self.lesson, title="Секретное ДЗ")
        HomeworkResult.objects.create(homework=hw, student=self.student, status="checked", score=37, comment="списал")
        self.api = APIClient()

    def get(self, name="public-schedule", **params):
        return self.api.get(reverse(name), params)


class PublicAccessTests(PublicScheduleFixture):
    def test_anyone_sees_today_without_login(self):
        response = self.get()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["start"], TODAY)
        self.assertEqual(len(response.data["lessons"]), 1)
        options = self.get("public-schedule-options")
        self.assertEqual(options.status_code, 200)

    def test_a_token_or_session_is_ignored_not_required(self):
        self.api.credentials(HTTP_AUTHORIZATION="Bearer not-a-real-token")
        self.assertEqual(self.get().status_code, 200)

    def test_only_get(self):
        before = Lesson.objects.values().get(pk=self.lesson.pk)
        for name in ("public-schedule", "public-schedule-options"):
            for method in ("post", "put", "patch", "delete"):
                response = getattr(self.api, method)(reverse(name), {"start_time": "09:00"}, format="json")
                self.assertEqual(response.status_code, 405, (name, method))
        self.assertEqual(Lesson.objects.values().get(pk=self.lesson.pk), before)

    def test_internal_endpoints_stay_closed(self):
        for url in ("/api/v1/schedule/board/", "/api/v1/schedule/options/", "/api/v1/schedule/free-rooms/",
                    "/api/v1/lessons/", "/api/v1/students/", "/api/v1/groups/", "/api/v1/reports/teachers/",
                    f"/api/v1/lessons/{self.lesson.pk}/attendance/"):
            self.assertIn(APIClient().get(url).status_code, (401, 403), url)


class NoPersonalDataTests(PublicScheduleFixture):
    SECRETS = (
        "Азамат", "Студентов", "+996", "@okurmen.kg", "trainer.secret", "болел", "списал", "Секретное ДЗ",
        "внутренний план", "Внутреннее описание", "Внутренний комментарий", "Внутренняя заметка", "Ключ у охраны",
        "students_count", "attendance", "homework", "score", "kpi", "phone", "email", "topic", "description",
        "comment", "lesson_number",
    )

    def payloads(self):
        return [self.get().data, self.get("public-schedule-options").data]

    def test_exact_whitelist_of_lesson_fields(self):
        lesson = self.get().data["lessons"][0]
        self.assertEqual(set(lesson), LESSON_KEYS)
        self.assertEqual(set(lesson["group"]), GROUP_KEYS)
        self.assertEqual(set(lesson["trainer"]), TRAINER_KEYS)
        self.assertEqual(set(lesson["room"]), ROOM_KEYS)
        self.assertEqual(lesson["trainer"]["name"], "Айжаркын Өмүрбекова")
        self.assertEqual(lesson["group"]["name"], "Prog SOFT 1 — вечерняя группа")
        self.assertEqual((lesson["start"], lesson["end"], lesson["duration_minutes"]), ("14:00", "15:30", 90))
        self.assertEqual(lesson["status"], "scheduled")

    def test_no_personal_or_internal_data_anywhere(self):
        for payload in self.payloads():
            text = json.dumps(payload, default=str, ensure_ascii=False)
            for secret in self.SECRETS:
                self.assertNotIn(secret, text, secret)

    def test_no_database_ids(self):
        ids = {str(pk) for pk in (self.lesson.pk, self.group.pk, self.teacher.pk, self.room.pk, self.student.pk, self.user.pk)}
        for payload in self.payloads():
            text = json.dumps(payload, default=str)
            self.assertNotIn('"id"', text)
            for key in re.findall(r'"key": "([^"]+)"', text):
                self.assertNotIn(key, ids)
                self.assertRegex(key, r"^[a-z2-7]{13}$")

    @override_settings(PUBLIC_SCHEDULE_SHOW_TRAINERS=False, PUBLIC_SCHEDULE_SHOW_ROOMS=False)
    def test_academy_can_hide_trainers_and_rooms(self):
        lesson = self.get().data["lessons"][0]
        self.assertNotIn("trainer", lesson)
        self.assertNotIn("room", lesson)
        options = self.get("public-schedule-options").data
        self.assertEqual((options["trainers"], options["rooms"]), ([], []))
        text = json.dumps(self.get().data, default=str, ensure_ascii=False)
        self.assertNotIn("Айжаркын", text)
        self.assertNotIn("Кабинет 201", text)
        # …and a trainer key can't be used to probe who teaches what.
        key = public_schedule.public_key("trainer", self.other.pk)
        self.assertEqual(len(self.get(trainer=key).data["lessons"]), 1)


class FilterTests(PublicScheduleFixture):
    def test_filters_by_public_keys(self):
        options = self.get("public-schedule-options").data
        group_key = options["groups"][0]["key"]
        trainer_key = next(t["key"] for t in options["trainers"] if t["name"] == "Айжаркын Өмүрбекова")
        room_key = options["rooms"][0]["key"]
        self.assertEqual(len(self.get(group=group_key).data["lessons"]), 1)
        self.assertEqual(len(self.get(trainer=trainer_key, room=room_key).data["lessons"]), 1)
        other_key = public_schedule.public_key("trainer", self.other.pk)
        self.assertEqual(self.get(trainer=other_key).data["lessons"], [])

    def test_unknown_or_raw_id_filter_returns_nothing(self):
        self.assertEqual(self.get(group="abcdefghijklm").data["lessons"], [])
        self.assertEqual(self.get(group=str(self.group.pk)).data["lessons"], [])
        self.assertEqual(self.get(trainer="<script>").data["lessons"], [])

    def test_week_and_limits(self):
        self.assertEqual(self.get(start=str(TODAY), end=str(TODAY + dt.timedelta(days=6))).status_code, 200)
        self.assertEqual(self.get(start=str(TODAY), end=str(TODAY + dt.timedelta(days=7))).status_code, 400)
        self.assertEqual(self.get(start=str(TODAY), end=str(TODAY - dt.timedelta(days=1))).status_code, 400)
        self.assertEqual(self.get(start=str(TODAY - dt.timedelta(days=400))).status_code, 400)  # not published that far back
        self.assertEqual(self.get(start="12.10.2026").status_code, 400)


class FreshnessTests(PublicScheduleFixture):
    def test_moved_and_cancelled_lessons_show_their_current_state(self):
        self.lesson.start_time, self.lesson.end_time, self.lesson.schedule_overridden = dt.time(16), dt.time(17), True
        self.lesson.save()
        row = self.get().data["lessons"][0]
        self.assertEqual((row["start"], row["end"], row["rescheduled"]), ("16:00", "17:00", True))
        self.lesson.status = Lesson.Status.CANCELLED
        self.lesson.save()
        row = self.get().data["lessons"][0]
        self.assertEqual((row["status"], row["status_label"]), ("cancelled", "Отменён"))

    @override_settings(CACHES=LOCMEM)
    def test_cached_but_rebuilt_on_every_lesson_change(self):
        cache.clear()
        first = self.get()
        self.assertEqual(first["Cache-Control"], "public, max-age=60")
        Lesson.objects.filter(pk=self.lesson.pk).update(start_time=dt.time(9))  # bypasses signals: cached
        self.assertEqual(self.get().data["lessons"][0]["start"], "14:00")
        self.lesson.refresh_from_db()
        self.lesson.end_time = dt.time(10)
        self.lesson.save()  # a real save: the cache is rebuilt at once
        self.assertEqual(self.get().data["lessons"][0]["start"], "09:00")

    def test_past_lessons_keep_their_trainer_after_a_handover(self):
        from unittest import mock

        from apps.academy.services.program_editing import update_teaching_program

        past = Lesson.objects.create(group=self.group, group_teacher=self.program, subject=self.python, lesson_number=2,
                                     date=TODAY - dt.timedelta(days=3), start_time=dt.time(10), end_time=dt.time(11))
        with mock.patch("apps.academy.services.trainer_history.timezone.localdate", return_value=TODAY - dt.timedelta(days=1)):
            update_teaching_program(self.program, teacher=self.other, subject=self.python, is_active=True,
                                    reassign_future_lessons=False)
        row = self.get(start=str(past.date)).data["lessons"][0]
        self.assertEqual(row["trainer"]["name"], "Айжаркын Өмүрбекова")


class RateLimitTests(PublicScheduleFixture):
    @override_settings(CACHES=LOCMEM)
    def test_requests_per_ip_are_limited(self):
        from apps.academy.public_schedule_views import PublicScheduleThrottle

        cache.clear()
        with self._rate("3/minute", PublicScheduleThrottle):
            codes = [self.get().status_code for _ in range(4)]
        self.assertEqual(codes, [200, 200, 200, 429])

    @staticmethod
    def _rate(rate, throttle):
        from unittest import mock

        return mock.patch.object(throttle, "THROTTLE_RATES", {**throttle.THROTTLE_RATES, "public_schedule": rate})


class QueryCountTests(PublicScheduleFixture):
    def test_queries_do_not_grow_with_lessons(self):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        def count():
            with CaptureQueriesContext(connection) as ctx:
                self.assertEqual(self.get(start=str(TODAY), end=str(TODAY + dt.timedelta(days=6))).status_code, 200)
            return len(ctx.captured_queries)

        small = count()
        for i in range(2, 30):
            Lesson.objects.create(group=self.group, group_teacher=self.program, subject=self.python, lesson_number=i,
                                  date=TODAY + dt.timedelta(days=i % 7), start_time=dt.time(8 + i % 12),
                                  end_time=dt.time(9 + i % 12), room=self.room)
        self.assertEqual(count(), small)
