"""The schedule board API (/api/v1/schedule/) behind the Team Lead's and the
Assistant's «Расписание»: the 08:00–24:00 day, filters, free rooms, the
interval-overlap rule, trainer colors, permissions and query counts."""
from __future__ import annotations

import datetime as dt
from unittest import mock

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from apps.academy.models import Course, Group, GroupTeacher, Lesson, Room, Student
from apps.academy.services import schedule_board as service
from apps.users.models import TRAINER_PALETTE, Subject, Teacher, User

PASSWORD = "Str0ngPassw0rd!"
DAY = dt.date(2026, 10, 12)  # a Monday


def make_user(username, role):
    return User.objects.create_user(username=username, email=f"{username}@okurmen.kg", password=PASSWORD,
                                    first_name=username.capitalize(), role=role, is_verified=True)


def make_teacher(username):
    return Teacher.objects.create(user=make_user(username, User.Role.TEACHER))


class BoardTestBase(TestCase):
    def setUp(self):
        self.python, _ = Subject.objects.get_or_create(name="Python")
        self.course = Course.objects.create(name="Prog", count_lesson=40)
        self.islam = make_teacher("islam")
        self.aibek = make_teacher("aibek")
        self.room_a = Room.objects.create(name="A1")
        self.room_b = Room.objects.create(name="B2")
        self.room_c = Room.objects.create(name="C3")
        self.g1 = Group.objects.create(name="PRO-01", course=self.course, start_date=DAY - dt.timedelta(days=30))
        self.g2 = Group.objects.create(name="PRO-02", course=self.course, start_date=DAY - dt.timedelta(days=30))
        self.gt1 = GroupTeacher.objects.create(group=self.g1, teacher=self.islam, subject=self.python)
        self.gt2 = GroupTeacher.objects.create(group=self.g2, teacher=self.aibek, subject=self.python)
        Student.objects.create(first_name="A", last_name="B", group=self.g1)
        self.numbers = {}
        self.assistant = make_user("assist", User.Role.ASSISTANT)
        self.lead = make_user("lead", User.Role.TEAM_LEAD)
        self.admin = make_user("boss", User.Role.ADMIN)
        self.client = APIClient()
        self.client.force_authenticate(self.assistant)

    def lesson(self, gt, start, end, room=None, date=DAY, status=Lesson.Status.SCHEDULED):
        number = self.numbers.get(gt.pk, 0) + 1
        self.numbers[gt.pk] = number
        return Lesson.objects.create(
            group=gt.group, group_teacher=gt, teacher=gt.teacher, subject=self.python, lesson_number=number,
            date=date, start_time=start, end_time=end, room=room, status=status,
        )

    def board(self, **params):
        params.setdefault("start", str(DAY))
        return self.client.get(reverse("schedule-board"), params)


class WorkingDayTests(BoardTestBase):
    def test_board_declares_08_to_24_and_keeps_long_and_late_lessons(self):
        self.lesson(self.gt1, dt.time(8), dt.time(10, 30), self.room_a)        # 2.5 h
        self.lesson(self.gt2, dt.time(21, 15), dt.time(23, 45), self.room_b)   # late evening
        data = self.board().data
        self.assertEqual(data["hours"], {"start": "08:00", "end": "24:00"})
        rows = {row["start"]: row for row in data["lessons"]}
        self.assertEqual(rows["08:00"]["duration_minutes"], 150)
        self.assertEqual(rows["21:15"]["end"], "23:45")
        self.assertEqual(rows["21:15"]["duration_minutes"], 150)
        self.assertEqual(data["stats"]["lessons"], 2)

    def test_now_is_in_project_timezone(self):
        data = self.board().data
        self.assertEqual(data["now"]["timezone"], "Asia/Bishkek")
        self.assertEqual(data["now"]["date"], timezone.localdate())

    def test_empty_schedule(self):
        data = self.board().data
        self.assertEqual(data["lessons"], [])
        self.assertEqual(data["conflicts"], [])
        self.assertEqual(data["legend"], [])
        self.assertEqual(data["stats"]["lessons"], 0)

    def test_invalid_period_is_refused(self):
        self.assertEqual(self.board(end=str(DAY - dt.timedelta(days=1))).status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(self.board(end=str(DAY + dt.timedelta(days=40))).status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(self.board(start="12-10-2026").status_code, status.HTTP_400_BAD_REQUEST)

    def test_week_range(self):
        self.lesson(self.gt1, dt.time(10), dt.time(11), date=DAY)
        self.lesson(self.gt1, dt.time(10), dt.time(11), date=DAY + dt.timedelta(days=6))
        self.lesson(self.gt1, dt.time(10), dt.time(11), date=DAY + dt.timedelta(days=7))
        data = self.board(end=str(DAY + dt.timedelta(days=6))).data
        self.assertEqual(len(data["lessons"]), 2)


class FilterTests(BoardTestBase):
    def setUp(self):
        super().setUp()
        self.a = self.lesson(self.gt1, dt.time(10), dt.time(11), self.room_a)
        self.b = self.lesson(self.gt2, dt.time(10), dt.time(11), self.room_b)
        self.c = self.lesson(self.gt2, dt.time(12), dt.time(13), self.room_c)

    def ids(self, **params):
        response = self.board(**params)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        return {row["id"] for row in response.data["lessons"]}

    def test_one_room(self):
        self.assertEqual(self.ids(room=self.room_a.pk), {self.a.pk})

    def test_several_rooms(self):
        self.assertEqual(self.ids(room=f"{self.room_a.pk},{self.room_c.pk}"), {self.a.pk, self.c.pk})

    def test_rooms_as_repeated_params(self):
        response = self.client.get(reverse("schedule-board"), {"start": str(DAY), "room": [self.room_b.pk, self.room_c.pk]})
        self.assertEqual({row["id"] for row in response.data["lessons"]}, {self.b.pk, self.c.pk})

    def test_no_filter_is_every_room(self):
        self.assertEqual(self.ids(), {self.a.pk, self.b.pk, self.c.pk})

    def test_room_combined_with_teacher_and_group(self):
        self.assertEqual(self.ids(room=f"{self.room_b.pk},{self.room_c.pk}", teacher=self.aibek.pk), {self.b.pk, self.c.pk})
        self.assertEqual(self.ids(room=self.room_a.pk, teacher=self.aibek.pk), set())
        self.assertEqual(self.ids(group=self.g2.pk, room=self.room_c.pk), {self.c.pk})

    def test_teacher_filter_includes_program_teacher_fallback(self):
        self.a.teacher = None
        self.a.save(update_fields=["teacher"])
        self.assertEqual(self.ids(teacher=self.islam.pk), {self.a.pk})

    def test_garbage_filter_values_are_ignored(self):
        self.assertEqual(self.ids(room="x,,", teacher="abc", status="nope"), {self.a.pk, self.b.pk, self.c.pk})

    def test_status_filter(self):
        self.c.status = Lesson.Status.CANCELLED
        self.c.save(update_fields=["status"])
        self.assertEqual(self.ids(status="cancelled"), {self.c.pk})


class FreeRoomsTests(BoardTestBase):
    def free(self, **params):
        params.setdefault("date", str(DAY))
        response = self.client.get(reverse("schedule-free-rooms"), params)
        return response

    def rooms(self, **params):
        response = self.free(**params)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        return {row["room"]["name"]: row for row in response.data["rooms"]}

    def test_overlap_makes_room_busy_and_reports_when_it_frees(self):
        # 14:00–15:30 in A1 — A1 is not free for 15:00–16:00.
        self.lesson(self.gt1, dt.time(14), dt.time(15, 30), self.room_a)
        rooms = self.rooms(start="15:00", end="16:00")
        self.assertFalse(rooms["A1"]["is_free"])
        self.assertEqual(rooms["A1"]["free_at"], "15:30")
        self.assertEqual(rooms["A1"]["next_free"], {"start": "15:30", "end": "24:00"})
        self.assertEqual(rooms["A1"]["conflicting_lessons"][0]["group"]["name"], "PRO-01")
        self.assertTrue(rooms["B2"]["is_free"])
        self.assertEqual(rooms["B2"]["free_window"], {"start": "08:00", "end": "24:00"})

    def test_touching_ends_are_free(self):
        self.lesson(self.gt1, dt.time(14), dt.time(15), self.room_a)
        self.lesson(self.gt2, dt.time(16), dt.time(17), self.room_a)
        rooms = self.rooms(start="15:00", end="16:00")
        self.assertTrue(rooms["A1"]["is_free"])
        self.assertEqual(rooms["A1"]["free_window"], {"start": "15:00", "end": "16:00"})

    def test_next_free_skips_too_short_gaps_and_chained_lessons(self):
        self.lesson(self.gt1, dt.time(10), dt.time(11), self.room_a)
        self.lesson(self.gt2, dt.time(11), dt.time(12), self.room_a)    # chained: frees at 12:00
        self.lesson(self.gt1, dt.time(12, 30), dt.time(14), self.room_a)  # 30-min gap is too short
        rooms = self.rooms(start="10:30", end="11:30")
        self.assertEqual(rooms["A1"]["free_at"], "12:00")
        self.assertEqual(rooms["A1"]["next_free"], {"start": "14:00", "end": "24:00"})

    def test_cancelled_lessons_and_inactive_rooms_do_not_count(self):
        self.lesson(self.gt1, dt.time(15), dt.time(16), self.room_a, status=Lesson.Status.CANCELLED)
        self.room_c.is_active = False
        self.room_c.save()
        rooms = self.rooms(start="15:00", end="16:00")
        self.assertTrue(rooms["A1"]["is_free"])
        self.assertNotIn("C3", rooms)

    def test_uses_database_not_another_day(self):
        self.lesson(self.gt1, dt.time(15), dt.time(16), self.room_a, date=DAY + dt.timedelta(days=1))
        self.assertTrue(self.rooms(start="15:00", end="16:00")["A1"]["is_free"])
        data = self.free(date=str(DAY + dt.timedelta(days=1)), start="15:00", end="16:00").data
        self.assertEqual(data["busy_count"], 1)
        self.assertEqual(data["free_count"], 2)

    def test_until_midnight_window(self):
        self.lesson(self.gt1, dt.time(22), dt.time(23), self.room_a)
        rooms = self.rooms(start="23:00", end="24:00")
        self.assertTrue(rooms["A1"]["is_free"])
        self.assertFalse(self.rooms(start="22:30", end="24:00")["A1"]["is_free"])

    def test_invalid_window(self):
        self.assertEqual(self.free(start="16:00", end="15:00").status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(self.free(start="16:00", end="16:00").status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(self.free(start="25:00", end="26:00").status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(self.free(start="", end="10:00").status_code, status.HTTP_400_BAD_REQUEST)


class ConflictTests(BoardTestBase):
    def test_overlap_rule(self):
        self.assertTrue(service.overlaps(14 * 60, 15 * 60 + 30, 15 * 60, 16 * 60))
        self.assertFalse(service.overlaps(14 * 60, 15 * 60, 15 * 60, 16 * 60))
        self.assertTrue(service.overlaps(10 * 60, 18 * 60, 12 * 60, 13 * 60))

    def test_board_flags_teacher_room_and_group_clashes(self):
        gt_other = GroupTeacher.objects.create(group=self.g2, teacher=self.islam, subject=self.python)
        a = self.lesson(self.gt1, dt.time(14), dt.time(15, 30), self.room_a)
        b = self.lesson(gt_other, dt.time(15), dt.time(16), self.room_a)  # same teacher + same room
        c = self.lesson(self.gt1, dt.time(15, 30), dt.time(16, 30), self.room_b)  # touches a: fine
        data = self.board().data
        rows = {row["id"]: row for row in data["lessons"]}
        self.assertEqual({c["kind"] for c in rows[a.pk]["conflicts"]}, {"teacher", "room"})
        self.assertEqual(rows[a.pk]["conflicts"][0]["with"], [b.pk])
        # b vs c: same trainer 15:30–16:00 → teacher clash.
        self.assertIn("teacher", {c["kind"] for c in rows[c.pk]["conflicts"]})
        self.assertEqual(data["stats"]["conflicts"], len(data["conflicts"]))
        self.assertTrue(all(c["message"] for c in data["conflicts"]))

    def test_conflict_outside_the_room_filter_is_still_reported(self):
        gt_other = GroupTeacher.objects.create(group=self.g2, teacher=self.islam, subject=self.python)
        a = self.lesson(self.gt1, dt.time(14), dt.time(15), self.room_a)
        self.lesson(gt_other, dt.time(14), dt.time(15), self.room_b)
        row = self.board(room=self.room_a.pk).data["lessons"][0]
        self.assertEqual(row["id"], a.pk)
        self.assertEqual(row["conflicts"][0]["kind"], "teacher")

    def test_cancelled_lessons_never_clash(self):
        self.lesson(self.gt1, dt.time(14), dt.time(15), self.room_a)
        self.lesson(self.gt2, dt.time(14), dt.time(15), self.room_a, status=Lesson.Status.CANCELLED)
        self.assertEqual(self.board().data["conflicts"], [])

    def check(self, **params):
        params.setdefault("date", str(DAY))
        return self.client.get(reverse("schedule-check"), params)

    def test_check_endpoint_returns_conflicting_lesson_data(self):
        a = self.lesson(self.gt1, dt.time(14), dt.time(15, 30), self.room_a)
        data = self.check(start="15:00", end="16:00", teacher=self.islam.pk, room=self.room_b.pk, group=self.g2.pk).data
        self.assertFalse(data["ok"])
        self.assertEqual(data["conflicts"][0]["kind"], "teacher")
        self.assertEqual(data["conflicts"][0]["lesson"]["id"], a.pk)
        self.assertIn("Тренер «Islam» уже ведёт занятие в группе «PRO-01» (14:00–15:30)", data["conflicts"][0]["message"])
        self.assertTrue(self.check(start="15:30", end="16:30", teacher=self.islam.pk).data["ok"])

    def test_check_existing_lesson_ignores_itself(self):
        a = self.lesson(self.gt1, dt.time(14), dt.time(15), self.room_a)
        self.lesson(self.gt2, dt.time(16), dt.time(17), self.room_a)
        self.assertTrue(self.check(lesson=a.pk, start="14:30", end="15:30").data["ok"])
        data = self.check(lesson=a.pk, start="15:30", end="16:30").data
        self.assertEqual([c["kind"] for c in data["conflicts"]], ["room"])

    def test_check_refuses_bad_interval(self):
        self.assertEqual(self.check(start="16:00", end="15:00").status_code, status.HTTP_400_BAD_REQUEST)

    def test_move_lesson_is_refused_on_room_conflict_and_allowed_back_to_back(self):
        a = self.lesson(self.gt1, dt.time(10), dt.time(11), self.room_a)
        self.lesson(self.gt2, dt.time(14), dt.time(15, 30), self.room_a)
        url = reverse("assistant:lesson-move", args=[a.pk])
        refused = self.client.post(url, {"date": str(DAY), "start_time": "15:00", "end_time": "16:00"})
        self.assertEqual(refused.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Аудитория «A1» уже занята группой «PRO-02» (14:00–15:30)", str(refused.data))
        allowed = self.client.post(url, {"date": str(DAY), "start_time": "15:30", "end_time": "17:00"})
        self.assertEqual(allowed.status_code, status.HTTP_200_OK, allowed.data)
        a.refresh_from_db()
        self.assertEqual((a.start_time, a.end_time), (dt.time(15, 30), dt.time(17)))

    def test_move_with_invalid_interval_is_refused(self):
        a = self.lesson(self.gt1, dt.time(10), dt.time(11), self.room_a)
        response = self.client.post(reverse("assistant:lesson-move", args=[a.pk]),
                                    {"date": str(DAY), "start_time": "12:00", "end_time": "11:00"})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_new_slot_with_group_conflict_is_refused(self):
        """Creating a lesson = saving a weekly slot of a group's program: the
        backend refuses a slot clashing with the group's own other slot."""
        from apps.academy.models import GroupSchedule

        GroupSchedule.objects.create(group=self.g1, teacher=self.islam, subject=self.python, day_of_week="mon",
                                     start_time=dt.time(16), end_time=dt.time(17), room=self.room_a)
        english, _ = Subject.objects.get_or_create(name="English")
        self.course.subjects.add(self.python, english)
        response = self.client.post(reverse("assistant:group-programs", args=[self.g1.pk]), {
            "teacher": self.aibek.pk, "subject": english.pk,
            "slots": [{"day": "mon", "start": "16:30", "end": "17:30", "room": self.room_b.pk}],
        }, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        ok = self.client.post(reverse("assistant:group-programs", args=[self.g1.pk]), {
            "teacher": self.aibek.pk, "subject": english.pk,
            "slots": [{"day": "mon", "start": "17:00", "end": "18:00", "room": self.room_b.pk}],
        }, format="json")
        self.assertEqual(ok.status_code, status.HTTP_200_OK, ok.data)


class TrainerColorTests(BoardTestBase):
    def test_new_trainers_get_distinct_palette_colors(self):
        colors = [self.islam.color, self.aibek.color]
        self.assertEqual(colors, list(TRAINER_PALETTE[:2]))
        third = make_teacher("dana")
        self.assertEqual(third.color, TRAINER_PALETTE[2])

    def test_color_is_stable_across_saves_and_reloads(self):
        color = self.islam.color
        self.islam.phone = "+996"
        self.islam.save()
        self.islam.refresh_from_db()
        self.assertEqual(self.islam.color, color)
        self.assertEqual(Teacher.objects.get(pk=self.islam.pk).color, color)

    def test_explicit_color_is_kept_and_reused_colors_spread(self):
        custom = Teacher.objects.create(user=make_user("custom", User.Role.TEACHER), color="#123456")
        self.assertEqual(custom.color, "#123456")
        for index in range(len(TRAINER_PALETTE)):
            make_teacher(f"t{index}")
        used = list(Teacher.objects.exclude(color="#123456").values_list("color", flat=True))
        counts = {color: used.count(color) for color in TRAINER_PALETTE}
        self.assertLessEqual(max(counts.values()) - min(counts.values()), 1)

    def test_save_with_update_fields_fills_missing_color(self):
        Teacher.objects.filter(pk=self.islam.pk).update(color="")
        teacher = Teacher.objects.get(pk=self.islam.pk)
        teacher.phone = "1"
        teacher.save(update_fields=["phone"])
        self.assertTrue(Teacher.objects.get(pk=self.islam.pk).color)

    def test_board_and_options_expose_colors_and_legend(self):
        self.lesson(self.gt1, dt.time(10), dt.time(11), self.room_a)
        self.lesson(self.gt1, dt.time(12), dt.time(13), self.room_a)
        data = self.board().data
        self.assertEqual(data["lessons"][0]["teacher"]["color"], self.islam.color)
        self.assertEqual(data["legend"], [{"id": self.islam.pk, "name": "Islam", "color": self.islam.color, "lessons_count": 2}])
        options = self.client.get(reverse("schedule-options")).data
        self.assertEqual({t["name"]: t["color"] for t in options["teachers"]},
                         {"Islam": self.islam.color, "Aibek": self.aibek.color})
        self.assertEqual(options["hours"], {"start": "08:00", "end": "24:00"})


class PermissionTests(BoardTestBase):
    URLS = ("schedule-board", "schedule-options", "schedule-free-rooms", "schedule-check")

    def get(self, user, name):
        client = APIClient()
        if user is not None:
            client.force_authenticate(user)
        return client.get(reverse(name), {"date": str(DAY), "start": "10:00", "end": "11:00"} if name in (
            "schedule-free-rooms", "schedule-check") else {"start": str(DAY)})

    def test_team_lead_reads_but_cannot_edit(self):
        for name in self.URLS:
            self.assertEqual(self.get(self.lead, name).status_code, status.HTTP_200_OK, name)
        self.assertFalse(self.get(self.lead, "schedule-board").data["capabilities"]["can_edit"])
        lesson = self.lesson(self.gt1, dt.time(10), dt.time(11), self.room_a)
        client = APIClient()
        client.force_authenticate(self.lead)
        moved = client.post(reverse("assistant:lesson-move", args=[lesson.pk]),
                            {"date": str(DAY), "start_time": "12:00", "end_time": "13:00"})
        self.assertEqual(moved.status_code, status.HTTP_403_FORBIDDEN)

    def test_assistant_and_admin_can_edit(self):
        for user in (self.assistant, self.admin):
            for name in self.URLS:
                self.assertEqual(self.get(user, name).status_code, status.HTTP_200_OK, name)
            self.assertTrue(self.get(user, "schedule-board").data["capabilities"]["can_edit"])

    def test_trainer_inactive_and_anonymous_are_refused(self):
        self.assertEqual(self.get(self.islam.user, "schedule-board").status_code, status.HTTP_403_FORBIDDEN)
        self.lead.is_active = False
        self.lead.save()
        self.assertIn(self.get(self.lead, "schedule-board").status_code, (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN))
        self.assertEqual(self.get(None, "schedule-board").status_code, status.HTTP_401_UNAUTHORIZED)


class QueryCountTests(BoardTestBase):
    def fill(self, n):
        rooms = [self.room_a, self.room_b, self.room_c]
        for index in range(n):
            teacher = make_teacher(f"q{index}-{Teacher.objects.count()}")
            group = Group.objects.create(name=f"G-{index}-{Group.objects.count()}", course=self.course, start_date=DAY)
            gt = GroupTeacher.objects.create(group=group, teacher=teacher, subject=self.python)
            Student.objects.create(first_name="S", last_name=str(index), group=group)
            self.lesson(gt, dt.time(8 + index % 14), dt.time(9 + index % 14), rooms[index % 3],
                        date=DAY + dt.timedelta(days=index % 7))

    def count(self, url, params):
        with CaptureQueriesContext(connection) as ctx:
            response = self.client.get(url, params)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        return len(ctx.captured_queries)

    def test_board_queries_do_not_grow_with_lessons(self):
        params = {"start": str(DAY), "end": str(DAY + dt.timedelta(days=6))}
        self.fill(3)
        small = self.count(reverse("schedule-board"), params)
        self.fill(20)
        self.assertEqual(self.count(reverse("schedule-board"), params), small)

    def test_free_rooms_queries_do_not_grow(self):
        params = {"date": str(DAY), "start": "10:00", "end": "11:00"}
        self.fill(3)
        small = self.count(reverse("schedule-free-rooms"), params)
        for index in range(5):
            Room.objects.create(name=f"R{index}")
        self.fill(14)
        self.assertEqual(self.count(reverse("schedule-free-rooms"), params), small)


class FreeRoomsCounterTests(BoardTestBase):
    def test_free_now_counter_for_today(self):
        self.lesson(self.gt1, dt.time(10), dt.time(12), self.room_a)
        fake_now = timezone.make_aware(dt.datetime.combine(DAY, dt.time(11)))
        with mock.patch("apps.academy.services.schedule_board.timezone.localtime", return_value=fake_now):
            stat = self.board().data["stats"]["free_rooms"]
        self.assertEqual(stat, {"mode": "now", "free": 2, "total": 3, "date": DAY, "at": "11:00"})

    def test_idle_rooms_counter_for_another_day(self):
        self.lesson(self.gt1, dt.time(10), dt.time(12), self.room_a)
        fake_now = timezone.make_aware(dt.datetime.combine(DAY - dt.timedelta(days=3), dt.time(11)))
        with mock.patch("apps.academy.services.schedule_board.timezone.localtime", return_value=fake_now):
            stat = self.board().data["stats"]["free_rooms"]
        self.assertEqual(stat["mode"], "day")
        self.assertEqual((stat["free"], stat["total"]), (2, 3))


class ReadOnlySiteTests(BoardTestBase):
    """The separate «OkurmenKIDS Schedule» site reads these endpoints only:
    the server refuses every write, not just a hidden button."""

    URLS = ("schedule-board", "schedule-options", "schedule-free-rooms", "schedule-check")

    def test_every_write_method_is_refused_and_nothing_changes(self):
        lesson = self.lesson(self.gt1, dt.time(10), dt.time(11), self.room_a)
        before = Lesson.objects.values().get(pk=lesson.pk)
        for user in (self.admin, self.assistant, self.lead):
            client = APIClient()
            client.force_authenticate(user)
            for name in self.URLS:
                url = reverse(name)
                for method in ("post", "put", "patch", "delete"):
                    response = getattr(client, method)(url, {"id": lesson.pk, "start_time": "12:00"}, format="json")
                    self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED, (user.role, name, method))
        self.assertEqual(Lesson.objects.values().get(pk=lesson.pk), before)

    def test_head_and_options_are_allowed(self):
        self.assertEqual(self.client.head(reverse("schedule-board"), {"start": str(DAY)}).status_code, status.HTTP_200_OK)
        self.assertEqual(self.client.options(reverse("schedule-board")).status_code, status.HTTP_200_OK)

    def test_full_names_and_no_student_personal_data(self):
        self.islam.user.last_name = "Дуйшобаев"
        self.islam.user.save()
        self.lesson(self.gt1, dt.time(10), dt.time(11), self.room_a)
        data = self.board().data
        row = data["lessons"][0]
        self.assertEqual(row["teacher"]["name"], "Islam Дуйшобаев")
        self.assertEqual(row["group"]["name"], "PRO-01")
        text = str(data)
        for secret in ("phone", "parent_phone", "last_name", "first_name"):
            self.assertNotIn(secret, text)

    def test_past_lessons_keep_their_trainer_after_a_handover(self):
        from apps.academy.services.program_editing import update_teaching_program

        past = self.lesson(self.gt1, dt.time(10), dt.time(11), self.room_a, date=DAY)
        legacy = self.lesson(self.gt1, dt.time(12), dt.time(13), self.room_b, date=DAY)
        Lesson.objects.filter(pk=legacy.pk).update(teacher=None)  # a lesson that never stored its trainer
        self.course.subjects.add(self.python)
        handover = DAY + dt.timedelta(days=30)
        with mock.patch("apps.academy.services.trainer_history.timezone.localdate", return_value=handover):
            update_teaching_program(self.gt1, teacher=self.aibek, subject=self.python, is_active=True,
                                    reassign_future_lessons=False, today=handover)
        rows = {r["id"]: r for r in self.board().data["lessons"]}
        self.assertEqual(rows[past.pk]["teacher"]["name"], "Islam")
        self.assertEqual(rows[legacy.pk]["teacher"]["name"], "Islam")
        ids = {r["id"] for r in self.board(teacher=self.aibek.pk).data["lessons"]}
        self.assertNotIn(past.pk, ids)
        self.assertNotIn(legacy.pk, ids)
