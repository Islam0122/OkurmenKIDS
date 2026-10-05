"""A changed weekly slot moves its open future lessons (and nothing else) —
services.schedule_lesson_sync, through every path that edits a slot:
save_teaching_program (the LMS «Изменить расписание» / the admin drawer)
and PATCH /schedules/:id/. Absolute imports only (see apps/academy/tests.py)."""
from __future__ import annotations

import datetime as dt

from django.core.exceptions import ValidationError
from django.db.models import Count
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.academy.models import (
    Attendance, Course, CourseLessonPlan, Group, GroupSchedule, GroupTeacher, Homework, HomeworkResult, Lesson, Room,
    Student,
)
from apps.academy.services.lesson_generator import generate_lessons_for_group
from apps.academy.services.program_editing import parse_schedule_specs, save_teaching_program
from apps.academy.services.schedule_lesson_sync import snapshot, sync_schedule_lessons
from apps.academy.tests import make_admin, make_teacher
from apps.users.models import Subject, User

T = dt.time


def next_monday(after: dt.date) -> dt.date:
    return after + dt.timedelta(days=7 - after.weekday())


class ScheduleSyncFixture(TestCase):
    """Group A: English — Aizhan, Sunday 10:00–11:00 (online_1);
    IT — Islam, Wednesday 08:00–09:00 (Аудитория 22). Four lessons each."""

    def setUp(self):
        self.admin = make_admin("sync_admin")
        self.lead = User.objects.create_user(username="sync_lead", email="sl@okurmen.kg", password="x",
                                             first_name="Lead", role=User.Role.TEAM_LEAD)
        self.aizhan = make_teacher("aizhan_sync")
        self.islam = make_teacher("islam_sync")
        self.nurisa = make_teacher("nurisa_sync")
        self.english = Subject.objects.get_or_create(name="English")[0]
        self.it = Subject.objects.get_or_create(name="IT")[0]
        self.room1 = Room.objects.create(name="online_1", capacity=20)
        self.room2 = Room.objects.create(name="Аудитория 22", capacity=20)
        self.room3 = Room.objects.create(name="Аудитория 3", capacity=20)
        course = Course.objects.create(name="Sync course", count_lesson=8)
        course.subjects.set([self.english, self.it])
        for number in range(1, 9):
            CourseLessonPlan.objects.create(course=course, lesson_number=number,
                                            subject=self.english if number % 2 else self.it, topic=f"Тема {number}")
        self.start = next_monday(timezone.localdate())
        self.group = Group.objects.create(name="Group A", course=course, start_date=self.start)
        self.english_slot = GroupSchedule.objects.create(
            group=self.group, teacher=self.aizhan, subject=self.english, day_of_week="sun",
            start_time=T(10, 0), end_time=T(11, 0), room=self.room1)
        self.it_slot = GroupSchedule.objects.create(
            group=self.group, teacher=self.islam, subject=self.it, day_of_week="wed",
            start_time=T(8, 0), end_time=T(9, 0), room=self.room2)
        generate_lessons_for_group(self.group)
        self.english_program = GroupTeacher.objects.get(group=self.group, subject=self.english)
        self.student = Student.objects.create(first_name="Айдай", group=self.group)

    def english_lessons(self):
        return list(Lesson.objects.filter(schedule=self.english_slot).order_by("date"))

    def it_rows(self):
        return list(Lesson.objects.filter(subject=self.it).order_by("date").values_list("date", "start_time", "end_time", "room_id"))

    def edit_slot(self, **values):
        before = snapshot(self.english_slot)
        for name, value in values.items():
            setattr(self.english_slot, name, value)
        self.english_slot.save()
        return before


class TimeChangeTests(ScheduleSyncFixture):
    def test_future_lessons_take_the_new_time_on_the_same_date(self):
        dates = [lesson.date for lesson in self.english_lessons()]
        self.assertEqual(len(dates), 4)
        self.assertTrue(all(date.weekday() == 6 for date in dates))
        it_before = self.it_rows()
        result = sync_schedule_lessons(self.english_slot, self.edit_slot(start_time=T(12, 0), end_time=T(13, 0)))
        self.assertEqual(result.updated, 4)
        lessons = self.english_lessons()
        self.assertEqual([lesson.date for lesson in lessons], dates)  # same dates
        self.assertTrue(all((lesson.start_time, lesson.end_time) == (T(12, 0), T(13, 0)) for lesson in lessons))
        self.assertEqual(self.it_rows(), it_before)  # the IT program is untouched

    def test_history_and_hand_moved_lessons_never_move(self):
        first, second, third, fourth = self.english_lessons()
        Lesson.objects.filter(pk=first.pk).update(status=Lesson.Status.COMPLETED, started_at=timezone.now())  # completed
        Attendance.objects.create(student=self.student, lesson=second, status=Attendance.Status.PRESENT)  # has data
        Lesson.objects.filter(pk=third.pk).update(status=Lesson.Status.CANCELLED)  # cancelled
        Lesson.objects.filter(pk=fourth.pk).update(start_time=T(15, 0), end_time=T(16, 0))  # moved by hand
        result = sync_schedule_lessons(self.english_slot, self.edit_slot(start_time=T(12, 0), end_time=T(13, 0)))
        self.assertEqual(result.updated, 0)
        self.assertEqual(result.kept, 3)  # cancelled ones aren't even counted
        times = [(lesson.start_time, lesson.status) for lesson in self.english_lessons()]
        self.assertEqual(times, [
            (T(10, 0), Lesson.Status.COMPLETED), (T(10, 0), Lesson.Status.SCHEDULED),
            (T(10, 0), Lesson.Status.CANCELLED), (T(15, 0), Lesson.Status.SCHEDULED),
        ])

    def test_past_lessons_never_move(self):
        lessons = self.english_lessons()
        today = lessons[2].date  # «today» is the third Sunday
        result = sync_schedule_lessons(self.english_slot, self.edit_slot(start_time=T(12, 0), end_time=T(13, 0)), today=today)
        self.assertEqual(result.updated, 2)
        starts = [lesson.start_time for lesson in self.english_lessons()]
        self.assertEqual(starts, [T(10, 0), T(10, 0), T(12, 0), T(12, 0)])

    def test_room_follows_where_it_was_the_slots(self):
        first, second, *_ = self.english_lessons()
        Lesson.objects.filter(pk=second.pk).update(room=self.room3)  # its own room
        sync_schedule_lessons(self.english_slot, self.edit_slot(room=self.room2, start_time=T(12, 0), end_time=T(13, 0)))
        rooms = [lesson.room_id for lesson in self.english_lessons()]
        self.assertEqual(rooms, [self.room2.pk, self.room3.pk, self.room2.pk, self.room2.pk])


class WeekdayChangeTests(ScheduleSyncFixture):
    def test_sunday_to_saturday_stays_in_each_lessons_week(self):
        dates = [lesson.date for lesson in self.english_lessons()]
        sync_schedule_lessons(self.english_slot, self.edit_slot(day_of_week="sat", start_time=T(12, 0), end_time=T(13, 0)))
        moved = self.english_lessons()
        self.assertEqual([lesson.date for lesson in moved], [date - dt.timedelta(days=1) for date in dates])
        self.assertTrue(all(lesson.date.weekday() == 5 for lesson in moved))
        self.assertEqual(len({lesson.date for lesson in moved}), len(moved))  # no two on one date
        self.assertEqual([lesson.lesson_number for lesson in moved], sorted(lesson.lesson_number for lesson in moved))

    def test_saturday_to_monday_never_into_the_past(self):
        original = [lesson.date for lesson in self.english_lessons()]  # Sundays
        sync_schedule_lessons(self.english_slot, self.edit_slot(day_of_week="sat"))
        # «Today» is the Wednesday of the second lesson's week: its Monday is past.
        today = original[1] - dt.timedelta(days=4)
        result = sync_schedule_lessons(self.english_slot, self.edit_slot(day_of_week="mon"), today=today)
        dates = [lesson.date for lesson in self.english_lessons()]
        self.assertEqual(result.updated, 2)  # weeks 3 and 4
        self.assertEqual(dates[2:], [date - dt.timedelta(days=6) for date in original[2:]])  # Mondays of their weeks
        self.assertEqual(dates[1], original[1] - dt.timedelta(days=1))  # stayed on Saturday — Monday was past
        self.assertTrue(all(date >= today for date in dates[1:]))
        self.assertEqual(len(set(dates)), len(dates))

    def test_a_move_past_the_groups_end_is_refused_whole(self):
        it_program = GroupTeacher.objects.get(group=self.group, subject=self.it)
        it_dates = [row[0] for row in self.it_rows()]
        Group.objects.filter(pk=self.group.pk).update(end_date=it_dates[-1] + dt.timedelta(days=1))
        specs = parse_schedule_specs(it_program, [
            {"id": self.it_slot.pk, "day": "sun", "start": "08:00", "end": "09:00", "room": self.room2.pk},
        ])
        with self.assertRaises(ValidationError) as caught:
            save_teaching_program(it_program, teacher=self.islam, subject=self.it, is_active=True, slots=specs)
        self.assertIn("дату окончания группы", " ".join(caught.exception.messages))
        self.it_slot.refresh_from_db()
        self.assertEqual(self.it_slot.day_of_week, "wed")
        self.assertEqual([row[0] for row in self.it_rows()], it_dates)


class ClashAndAtomicityTests(ScheduleSyncFixture):
    def test_a_clash_rolls_back_the_slot_and_every_lesson(self):
        # Nurisa's other group has a one-off lesson on the first English Sunday at 12:00 in online_1.
        other = Group.objects.create(name="Group B", course=self.group.course, start_date=self.start)
        program = GroupTeacher.objects.create(group=other, teacher=self.nurisa, subject=self.english)
        first = self.english_lessons()[0]
        Lesson.objects.create(group=other, group_teacher=program, teacher=self.nurisa, subject=self.english,
                              date=first.date, start_time=T(12, 0), end_time=T(13, 0), room=self.room1, lesson_number=1)
        specs = parse_schedule_specs(self.english_program, [
            {"id": self.english_slot.pk, "day": "sun", "start": "12:00", "end": "13:00", "room": self.room1.pk},
        ])
        with self.assertRaises(ValidationError) as caught:
            save_teaching_program(self.english_program, teacher=self.aizhan, subject=self.english, is_active=True, slots=specs)
        self.assertIn("аудитория занята", " ".join(caught.exception.messages))
        self.english_slot.refresh_from_db()
        self.assertEqual((self.english_slot.start_time, self.english_slot.is_active), (T(10, 0), True))
        self.assertTrue(all(lesson.start_time == T(10, 0) for lesson in self.english_lessons()))


class SavePathTests(ScheduleSyncFixture):
    def test_lms_change_schedule_moves_the_lessons(self):
        api = APIClient()
        api.force_authenticate(self.lead)
        response = api.put(
            f"/api/v1/groups/{self.group.pk}/academic-config/programs/{self.english_program.pk}/",
            {"teacher": self.aizhan.pk, "subject": self.english.pk,
             "schedule": [{"id": self.english_slot.pk, "day": "sun", "start": "12:00", "end": "13:00", "room": self.room1.pk}]},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertTrue(all((lesson.start_time, lesson.end_time) == (T(12, 0), T(13, 0)) for lesson in self.english_lessons()))
        self.assertTrue(all(row[1] == T(8, 0) for row in self.it_rows()))

    def test_trainer_change_moves_future_lessons_to_the_new_trainer(self):
        specs = parse_schedule_specs(self.english_program, [
            {"id": self.english_slot.pk, "day": "sun", "start": "10:00", "end": "11:00", "room": self.room1.pk},
        ])
        save_teaching_program(self.english_program, teacher=self.nurisa, subject=self.english, is_active=True, slots=specs)
        self.assertTrue(all(lesson.teacher_id == self.nurisa.pk for lesson in self.english_lessons()))

    def test_schedule_api_patch_moves_the_lessons(self):
        api = APIClient()
        api.force_authenticate(self.admin)
        response = api.patch(f"/api/v1/schedules/{self.english_slot.pk}/", {"start_time": "12:00", "end_time": "13:00"}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertTrue(all(lesson.start_time == T(12, 0) for lesson in self.english_lessons()))


# ---------------------------------------------------------------------------
# QA: time zone, today / running lessons, history matrix, conflicts,
# rollback, isolation, trainer / room, both save paths, performance,
# concurrency, idempotency — and the «Сгенерировать занятия» button.
# ---------------------------------------------------------------------------

def bishkek(date: dt.date, time: dt.time) -> dt.datetime:
    """An aware moment in the project's time zone (settings.TIME_ZONE)."""
    return timezone.make_aware(dt.datetime.combine(date, time))


class QAFixture(ScheduleSyncFixture):
    def setUp(self):
        super().setUp()
        self.it_program = GroupTeacher.objects.get(group=self.group, subject=self.it)

    def save_english(self, *, day="sun", start="12:00", end="13:00", room=None, teacher=None, today=None):
        specs = parse_schedule_specs(self.english_program, [
            {"id": self.english_slot.pk, "day": day, "start": start, "end": end, "room": (room or self.room1).pk},
        ])
        result = save_teaching_program(self.english_program, teacher=teacher or self.aizhan, subject=self.english,
                                       is_active=True, slots=specs, today=today)
        self.english_slot.refresh_from_db()
        return result

    def english_rows(self):
        return [(lesson.date, lesson.start_time, lesson.end_time) for lesson in self.english_lessons()]

    def make_group_b(self, teacher=None, room=None):
        """Group B: English, Sunday 10:00–11:00 — another group, own trainer and room."""
        teacher = teacher or make_teacher("bek_sync")
        group = Group.objects.create(name="Group B", course=self.group.course, start_date=self.start)
        slot = GroupSchedule.objects.create(group=group, teacher=teacher, subject=self.english, day_of_week="sun",
                                            start_time=T(10, 0), end_time=T(11, 0), room=room or self.room3)
        generate_lessons_for_group(group)
        return group, slot


class TimezoneTests(QAFixture):
    def test_the_project_time_zone_decides_today(self):
        from django.conf import settings

        from apps.academy.services.schedule_lesson_sync import local_now

        self.assertEqual((settings.TIME_ZONE, settings.USE_TZ), ("Asia/Bishkek", True))  # UTC+6, no DST since 2005
        day = self.english_lessons()[0].date
        utc = dt.timezone.utc
        cases = {
            dt.datetime.combine(day - dt.timedelta(days=1), T(17, 30), tzinfo=utc): (day - dt.timedelta(days=1), T(23, 30)),
            dt.datetime.combine(day - dt.timedelta(days=1), T(18, 0), tzinfo=utc): (day, T(0, 0)),
            dt.datetime.combine(day - dt.timedelta(days=1), T(18, 30), tzinfo=utc): (day, T(0, 30)),
        }
        for moment, (date, time) in cases.items():
            local = local_now(now=moment)
            self.assertEqual((local.date(), local.time()), (date, time), moment)

    def test_a_lesson_that_already_began_in_local_time_stays(self):
        day = self.english_lessons()[0].date
        # 04:30 UTC is 10:30 in Bishkek: the 10:00 lesson has begun (in UTC it would look ahead).
        now = dt.datetime.combine(day, T(4, 30), tzinfo=dt.timezone.utc)
        result = sync_schedule_lessons(self.english_slot, self.edit_slot(start_time=T(12, 0), end_time=T(13, 0)), now=now)
        self.assertEqual(result.updated, 3)
        self.assertEqual(self.english_lessons()[0].start_time, T(10, 0))

    def test_around_midnight(self):
        day = self.english_lessons()[0].date
        for local_moment in (bishkek(day - dt.timedelta(days=1), T(23, 30)), bishkek(day, T(0, 0)), bishkek(day, T(0, 30))):
            with self.subTest(local_moment=local_moment):
                before = snapshot(self.english_slot)
                new = T(12, 0) if self.english_slot.start_time != T(12, 0) else T(14, 0)
                self.english_slot.start_time, self.english_slot.end_time = new, T(new.hour + 1, 0)
                self.english_slot.save()
                result = sync_schedule_lessons(self.english_slot, before, now=local_moment)
                self.assertEqual(result.updated, 4)  # the day's 10:00 lesson is still ahead at 23:30 / 00:00 / 00:30
                self.assertEqual(self.english_lessons()[0].start_time, new)


class TodayAndRunningTests(QAFixture):
    def test_today_later_lesson_moves_earlier_one_stays(self):
        day = self.english_lessons()[0].date
        self.save_english(start="19:00", end="20:00")
        now = bishkek(day, T(11, 28))
        result = sync_schedule_lessons(self.english_slot, self.edit_slot(start_time=T(20, 0), end_time=T(21, 0)), now=now)
        self.assertEqual(result.updated, 4)
        self.assertEqual(self.english_rows()[0], (day, T(20, 0), T(21, 0)))
        # A lesson today at 09:00, already over at 11:28, does not move.
        self.edit_slot(start_time=T(9, 0), end_time=T(10, 0))
        Lesson.objects.filter(schedule=self.english_slot).update(start_time=T(9, 0), end_time=T(10, 0))
        result = sync_schedule_lessons(self.english_slot, self.edit_slot(start_time=T(12, 0), end_time=T(13, 0)), now=now)
        self.assertEqual(result.updated, 3)
        self.assertEqual(self.english_rows()[0], (day, T(9, 0), T(10, 0)))

    def test_a_running_lesson_is_not_rewritten(self):
        day = self.english_lessons()[0].date
        self.save_english(start="19:30", end="20:30")
        result = sync_schedule_lessons(self.english_slot, self.edit_slot(start_time=T(21, 0), end_time=T(22, 0)),
                                       now=bishkek(day, T(19, 45)))
        self.assertEqual(result.updated, 3)
        self.assertEqual(self.english_rows()[0], (day, T(19, 30), T(20, 30)))

    def test_new_time_already_past_today_is_not_applied(self):
        day = self.english_lessons()[0].date
        self.save_english(start="19:00", end="20:00")
        result = sync_schedule_lessons(self.english_slot, self.edit_slot(start_time=T(9, 0), end_time=T(10, 0)),
                                       now=bishkek(day, T(11, 28)))
        self.assertEqual((result.updated, result.kept), (3, 1))
        self.assertEqual(self.english_rows()[0], (day, T(19, 0), T(20, 0)))


class HistoryMatrixTests(QAFixture):
    def test_nothing_with_history_moves(self):
        from apps.academy.models import Homework, HomeworkResult

        completed, running, with_attendance, with_homework = self.english_lessons()
        Lesson.objects.filter(pk=completed.pk).update(status=Lesson.Status.COMPLETED, started_at=timezone.now())
        Lesson.objects.filter(pk=running.pk).update(status=Lesson.Status.IN_PROGRESS, started_at=timezone.now())
        Attendance.objects.create(student=self.student, lesson=with_attendance, status=Attendance.Status.PRESENT)
        homework = Homework.objects.create(lesson=with_homework, title="ДЗ")
        HomeworkResult.objects.create(homework=homework, student=self.student, status=HomeworkResult.Status.CHECKED)
        cancelled = Lesson.objects.create(
            group=self.group, group_teacher=self.english_program, schedule=self.english_slot, teacher=self.aizhan,
            subject=self.english, date=with_homework.date + dt.timedelta(days=7), start_time=T(10, 0),
            end_time=T(11, 0), room=self.room1, lesson_number=101, status=Lesson.Status.CANCELLED)
        before = {lesson.pk: (lesson.date, lesson.start_time, lesson.status) for lesson in Lesson.objects.filter(schedule=self.english_slot)}
        self.save_english()
        after = {lesson.pk: (lesson.date, lesson.start_time, lesson.status) for lesson in Lesson.objects.filter(schedule=self.english_slot)}
        self.assertEqual(after, before)
        self.assertIn(cancelled.pk, after)


class ManualRescheduleTests(QAFixture):
    def test_a_hand_moved_lesson_is_an_override(self):
        moved = self.english_lessons()[1]
        Lesson.objects.filter(pk=moved.pk).update(start_time=T(12, 0), end_time=T(13, 0))
        self.save_english(start="14:00", end="15:00")
        rows = {lesson.pk: (lesson.start_time, lesson.end_time) for lesson in self.english_lessons()}
        self.assertEqual(rows.pop(moved.pk), (T(12, 0), T(13, 0)))
        self.assertTrue(all(value == (T(14, 0), T(15, 0)) for value in rows.values()))


class ConflictRollbackTests(QAFixture):
    def assert_refused(self, fragment):
        rows = self.english_rows()
        with self.assertRaises(ValidationError) as caught:
            self.save_english()
        self.assertIn(fragment, " ".join(caught.exception.messages))
        self.english_slot.refresh_from_db()
        self.assertEqual((self.english_slot.start_time, self.english_slot.is_active), (T(10, 0), True))
        self.assertEqual(self.english_rows(), rows)

    def one_off(self, group, program, teacher, room, number=100):
        day = self.english_lessons()[0].date
        return Lesson.objects.create(group=group, group_teacher=program, teacher=teacher, subject=program.subject,
                                     date=day, start_time=T(12, 0), end_time=T(13, 0), room=room, lesson_number=number)

    def test_group_conflict(self):
        self.one_off(self.group, self.it_program, self.islam, self.room3)
        self.assert_refused("у группы уже есть занятие")

    def test_trainer_conflict(self):
        group, slot = self.make_group_b()
        self.one_off(group, slot.group_teacher, self.aizhan, self.room2, number=200)
        self.assert_refused("тренер занят")

    def test_room_conflict(self):
        group, slot = self.make_group_b()
        self.one_off(group, slot.group_teacher, slot.teacher, self.room1, number=200)
        self.assert_refused("аудитория занята")

    def test_a_failure_while_writing_lessons_saves_nothing(self):
        from unittest import mock

        from django.db import DatabaseError

        rows = self.english_rows()
        with mock.patch("django.db.models.query.QuerySet.bulk_update", side_effect=DatabaseError("boom")):
            with self.assertRaises(DatabaseError):
                self.save_english()
        self.english_slot.refresh_from_db()
        self.assertEqual((self.english_slot.start_time, self.english_slot.end_time), (T(10, 0), T(11, 0)))
        self.assertEqual(self.english_rows(), rows)


class IsolationTests(QAFixture):
    def test_other_slot_and_other_group_untouched(self):
        group_b, slot_b = self.make_group_b()
        it_before, b_before = self.it_rows(), list(Lesson.objects.filter(group=group_b).values_list("date", "start_time", "end_time"))
        self.save_english()
        self.assertEqual(self.it_rows(), it_before)
        self.assertEqual(list(Lesson.objects.filter(group=group_b).values_list("date", "start_time", "end_time")), b_before)


class TrainerAndRoomTests(QAFixture):
    def test_trainer_change_spares_history_and_overrides(self):
        first, second, third, fourth = self.english_lessons()
        Lesson.objects.filter(pk=first.pk).update(status=Lesson.Status.COMPLETED, started_at=timezone.now())
        Lesson.objects.filter(pk=fourth.pk).update(start_time=T(14, 0), end_time=T(15, 0))  # moved by hand
        self.save_english(start="10:00", end="11:00", teacher=self.nurisa, today=third.date)
        teachers = [lesson.teacher_id for lesson in self.english_lessons()]
        # completed (past) · past · future → Nurisa · hand-moved stays
        self.assertEqual(teachers, [self.aizhan.pk, self.aizhan.pk, self.nurisa.pk, self.aizhan.pk])

    def test_room_follows_the_slot_unless_the_lesson_has_its_own(self):
        own = self.english_lessons()[1]
        Lesson.objects.filter(pk=own.pk).update(room=self.room3)
        self.save_english(start="10:00", end="11:00", room=self.room2)
        rooms = {lesson.pk: lesson.room_id for lesson in self.english_lessons()}
        self.assertEqual(rooms.pop(own.pk), self.room3.pk)
        self.assertTrue(all(room == self.room2.pk for room in rooms.values()))


class BothPathsTests(QAFixture):
    def test_lms_and_api_give_the_same_result(self):
        group_b, slot_b = self.make_group_b()
        lead = APIClient()
        lead.force_authenticate(self.lead)
        response = lead.put(
            f"/api/v1/groups/{self.group.pk}/academic-config/programs/{self.english_program.pk}/",
            {"teacher": self.aizhan.pk, "subject": self.english.pk,
             "schedule": [{"id": self.english_slot.pk, "day": "sat", "start": "12:00", "end": "13:00", "room": self.room1.pk}]},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        admin = APIClient()
        admin.force_authenticate(self.admin)
        response = admin.patch(f"/api/v1/schedules/{slot_b.pk}/", {"day_of_week": "sat", "start_time": "12:00", "end_time": "13:00"}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["start_time"], "12:00:00")  # the saved slot
        b_rows = list(Lesson.objects.filter(schedule=slot_b).order_by("date").values_list("date", "start_time", "end_time"))
        self.assertEqual(self.english_rows(), b_rows)


class PerformanceTests(QAFixture):
    def build(self, count):
        teacher = make_teacher(f"perf_{count}")
        room = Room.objects.create(name=f"Perf {count}", capacity=10)
        group = Group.objects.create(name=f"Perf {count}", course=self.group.course, start_date=self.start)
        program = GroupTeacher.objects.create(group=group, teacher=teacher, subject=self.english)
        slot = GroupSchedule.objects.create(group=group, teacher=teacher, subject=self.english, day_of_week="mon",
                                            start_time=T(15, 0), end_time=T(16, 0), room=room)
        Lesson.objects.bulk_create([
            Lesson(group=group, group_teacher=program, schedule=slot, teacher=teacher, subject=self.english,
                   date=self.start + dt.timedelta(weeks=week), start_time=T(15, 0), end_time=T(16, 0), room=room,
                   lesson_number=week + 1)
            for week in range(count)
        ])
        return slot

    def queries_for(self, slot):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        before = snapshot(slot)
        slot.start_time, slot.end_time = T(17, 0), T(18, 0)
        slot.save()
        with CaptureQueriesContext(connection) as ctx:
            result = sync_schedule_lessons(slot, before)
        return result.updated, len(ctx.captured_queries)

    def test_query_count_does_not_grow_with_lessons(self):
        small = self.queries_for(self.build(20))
        large = self.queries_for(self.build(600))
        self.assertEqual((small[0], large[0]), (20, 600))
        # bulk_update batches by the backend's variable limit, so allow a couple of extra statements.
        self.assertLessEqual(large[1], small[1] + 3, (small, large))


class ConcurrencyAndIdempotencyTests(QAFixture):
    def test_a_second_editor_starts_from_what_the_first_committed(self):
        stale = GroupTeacher.objects.get(pk=self.english_program.pk)  # opened before the first save
        specs_b = parse_schedule_specs(stale, [
            {"id": self.english_slot.pk, "day": "sun", "start": "13:00", "end": "14:00", "room": self.room1.pk},
        ])
        self.save_english(start="12:00", end="13:00")  # editor A commits first
        save_teaching_program(stale, teacher=self.aizhan, subject=self.english, is_active=True, slots=specs_b)
        self.english_slot.refresh_from_db()
        self.assertEqual(self.english_slot.start_time, T(13, 0))
        self.assertTrue(all((start, end) == (T(13, 0), T(14, 0)) for _date, start, end in self.english_rows()))

    def test_saving_the_same_schedule_twice_moves_nothing_more(self):
        self.save_english(day="sat")
        first = [(lesson.pk, lesson.date, lesson.start_time, lesson.updated_at) for lesson in self.english_lessons()]
        result = self.save_english(day="sat")
        self.assertEqual(result.schedule.lessons_synced, 0)
        self.assertEqual([(lesson.pk, lesson.date, lesson.start_time, lesson.updated_at) for lesson in self.english_lessons()], first)
        admin = APIClient()
        admin.force_authenticate(self.admin)
        admin.patch(f"/api/v1/schedules/{self.english_slot.pk}/", {"day_of_week": "sat", "start_time": "12:00"}, format="json")
        self.assertEqual([(lesson.pk, lesson.date, lesson.start_time, lesson.updated_at) for lesson in self.english_lessons()], first)


class GenerateLessonsTests(QAFixture):
    """«Сгенерировать занятия» after a schedule change: same lessons, current
    times, no duplicates, history and overrides kept."""

    def generate(self):
        from django.test import Client
        from django.urls import reverse

        client = Client()
        client.force_login(self.admin)
        response = client.post(reverse("admin:academy_group_workspace_generate_lessons", args=[self.group.pk]))
        self.assertEqual(response.status_code, 302)

    def lessons_state(self):
        return list(Lesson.objects.filter(group=self.group).order_by("date", "start_time").values_list(
            "pk", "lesson_number", "date", "start_time", "end_time", "status", "teacher_id"))

    def test_change_then_generate_keeps_the_new_time_and_one_lesson_per_date(self):
        self.save_english()  # 10:00 → 12:00
        self.generate()
        rows = self.english_rows()
        self.assertEqual(len(rows), 4)
        self.assertTrue(all((start, end) == (T(12, 0), T(13, 0)) for _date, start, end in rows))
        self.assertEqual(len({date for date, _s, _e in rows}), 4)

    def test_generate_three_times_changes_nothing(self):
        self.save_english()
        self.generate()
        state = self.lessons_state()
        self.generate()
        self.generate()
        self.assertEqual(self.lessons_state(), state)

    def test_overrides_and_completed_survive_generation(self):
        first, second, third, fourth = self.english_lessons()
        Lesson.objects.filter(pk=first.pk).update(status=Lesson.Status.COMPLETED, started_at=timezone.now())
        Lesson.objects.filter(pk=second.pk).update(start_time=T(14, 0), end_time=T(15, 0), schedule_overridden=True)
        self.save_english()
        self.generate()
        rows = {lesson.pk: (lesson.start_time, lesson.status) for lesson in self.english_lessons()}
        self.assertEqual(rows[first.pk], (T(10, 0), Lesson.Status.COMPLETED))
        self.assertEqual(rows[second.pk][0], T(14, 0))
        self.assertEqual(rows[third.pk][0], T(12, 0))
        self.assertEqual(rows[fourth.pk][0], T(12, 0))
        self.assertEqual(len(rows), 4)

    def test_other_schedule_is_not_touched(self):
        it_before = self.it_rows()
        self.save_english()
        self.generate()
        self.assertEqual(self.it_rows(), it_before)

    def test_a_new_plan_row_never_lands_next_to_history_or_in_a_past_week(self):
        first = self.english_lessons()[0]
        Lesson.objects.filter(pk=first.pk).update(status=Lesson.Status.COMPLETED, started_at=timezone.now())
        self.save_english(day="sat")  # weeks 2–4 move to Saturday; week 1 stays (completed, Sunday 10:00)
        course = self.group.course
        CourseLessonPlan.objects.create(course=course, lesson_number=9, subject=self.english, topic="Новая тема")
        type(course).objects.filter(pk=course.pk).update(count_lesson=9)
        self.generate()
        lessons = self.english_lessons()
        self.assertEqual(len(lessons), 5)
        new = next(lesson for lesson in lessons if lesson.lesson_number == 9)
        self.assertGreater(new.date, max(lesson.date for lesson in lessons if lesson.pk != new.pk))  # after the rest
        self.assertEqual((new.date.weekday(), new.start_time), (5, T(12, 0)))  # current slot: Saturday 12:00
        weeks = [lesson.date.isocalendar()[:2] for lesson in lessons]
        self.assertEqual(len(set(weeks)), len(weeks))  # one lesson of the slot per week


class GenerateSyncsStaleLessonsTests(QAFixture):
    """The «Сгенерировать занятия» bug: a slot changed, its lessons did *not*
    follow (here: a plain slot .save(), the path without sync — as if the
    sync never ran), and Generate used to skip every existing lesson. Now
    Generate is create + sync: the open future lessons of *that* slot
    (Lesson.schedule) move onto its current day/time, nothing is
    duplicated, history and hand moves stay."""

    def setUp(self):
        super().setUp()
        self.api = APIClient()
        self.api.force_authenticate(self.admin)

    def change_slot_without_sync(self, **values):
        for name, value in values.items():
            setattr(self.english_slot, name, value)
        self.english_slot.save()

    def generate(self):
        response = self.api.post(f"/api/v1/groups/{self.group.pk}/generate-lessons/")
        self.assertIn(response.status_code, (200, 201), response.content)
        return response.json()

    def preview(self):
        response = self.api.get(f"/api/v1/groups/{self.group.pk}/generate-lessons/preview/")
        self.assertEqual(response.status_code, 200)
        return response.json()

    def per_slot_and_date(self):
        return list(
            Lesson.objects.filter(group=self.group).exclude(status=Lesson.Status.CANCELLED)
            .values("schedule_id", "date").annotate(n=Count("id")).filter(n__gt=1)
        )

    # A — existing future lesson's time changes
    def test_a_existing_future_lessons_take_the_slots_new_time(self):
        before = self.english_rows()
        self.assertTrue(all((s, e) == (T(10, 0), T(11, 0)) for _d, s, e in before))
        self.change_slot_without_sync(start_time=T(12, 0), end_time=T(13, 0))
        self.assertEqual(self.english_rows(), before)  # the bug: still 10:00

        result = self.generate()
        self.assertEqual(result["created_count"], 0)
        self.assertEqual(result["rescheduled_count"], 4)
        after = self.english_rows()
        self.assertEqual([d for d, _s, _e in after], [d for d, _s, _e in before])  # same dates
        self.assertTrue(all((s, e) == (T(12, 0), T(13, 0)) for _d, s, e in after))

    # B — idempotent
    def test_b_generate_three_times_is_idempotent(self):
        self.change_slot_without_sync(start_time=T(12, 0), end_time=T(13, 0))
        first = self.generate()
        state = list(Lesson.objects.filter(group=self.group).order_by("pk").values_list(
            "pk", "date", "start_time", "end_time", "updated_at"))
        second, third = self.generate(), self.generate()
        self.assertEqual(first["rescheduled_count"], 4)
        for again in (second, third):
            self.assertEqual((again["created_count"], again["rescheduled_count"]), (0, 0))
        self.assertEqual(list(Lesson.objects.filter(group=self.group).order_by("pk").values_list(
            "pk", "date", "start_time", "end_time", "updated_at")), state)
        self.assertEqual(len(self.english_lessons()), 4)

    # C — completed (and every other kind of history) unchanged
    def test_c_history_is_never_moved(self):
        first, second, third, fourth = self.english_lessons()
        Lesson.objects.filter(pk=first.pk).update(status=Lesson.Status.COMPLETED, started_at=timezone.now())
        Attendance.objects.create(student=self.student, lesson=second, status=Attendance.Status.PRESENT)
        homework = Homework.objects.create(lesson=third, title="ДЗ")
        HomeworkResult.objects.create(homework=homework, student=self.student, status=HomeworkResult.Status.SUBMITTED)
        Lesson.objects.filter(pk=fourth.pk).update(status=Lesson.Status.CANCELLED)
        self.change_slot_without_sync(start_time=T(12, 0), end_time=T(13, 0))

        result = self.generate()
        self.assertEqual(result["rescheduled_count"], 0)
        rows = {lesson.pk: (lesson.start_time, lesson.status) for lesson in self.english_lessons()}
        self.assertEqual(rows[first.pk], (T(10, 0), Lesson.Status.COMPLETED))
        self.assertEqual(rows[second.pk][0], T(10, 0))
        self.assertEqual(rows[third.pk][0], T(10, 0))
        self.assertEqual(rows[fourth.pk], (T(10, 0), Lesson.Status.CANCELLED))

    def test_c_past_lesson_keeps_its_history(self):
        first = self.english_lessons()[0]
        last_sunday = timezone.localdate() - dt.timedelta(days=timezone.localdate().weekday() + 1)
        Lesson.objects.filter(pk=first.pk).update(date=last_sunday)
        self.change_slot_without_sync(start_time=T(12, 0), end_time=T(13, 0))
        self.generate()
        first.refresh_from_db()
        self.assertEqual((first.date, first.start_time), (last_sunday, T(10, 0)))

    # D — a manual reschedule wins
    def test_d_lesson_moved_by_hand_stays_at_its_own_time(self):
        moved = self.english_lessons()[1]
        response = self.api.patch(f"/api/v1/lessons/{moved.pk}/", {"start_time": "14:00", "end_time": "15:00"}, format="json")
        self.assertEqual(response.status_code, 200, response.content)
        moved.refresh_from_db()
        self.assertTrue(moved.schedule_overridden)
        self.assertFalse(moved.manually_edited)  # content untouched — the plan still syncs it

        self.change_slot_without_sync(start_time=T(12, 0), end_time=T(13, 0))
        self.generate()
        rows = {lesson.pk: (lesson.start_time, lesson.end_time) for lesson in self.english_lessons()}
        self.assertEqual(rows.pop(moved.pk), (T(14, 0), T(15, 0)))
        self.assertTrue(all(value == (T(12, 0), T(13, 0)) for value in rows.values()))

    def test_d_slot_save_also_respects_a_hand_move(self):
        moved = self.english_lessons()[1]
        # Moved to another week but still «Sunday 10:00»: only the flag tells it apart.
        self.api.patch(f"/api/v1/lessons/{moved.pk}/", {"date": str(moved.date + dt.timedelta(days=28))}, format="json")
        self.save_english()  # Sunday 12:00 via the program drawer (synced save)
        moved.refresh_from_db()
        self.assertEqual(moved.start_time, T(10, 0))

    # E — another schedule of the same group is untouched
    def test_e_other_schedule_unchanged(self):
        it_before = self.it_rows()
        it_lessons = list(Lesson.objects.filter(schedule=self.it_slot).values_list("pk", "updated_at"))
        self.change_slot_without_sync(start_time=T(12, 0), end_time=T(13, 0))
        self.generate()
        self.assertEqual(self.it_rows(), it_before)
        self.assertEqual(list(Lesson.objects.filter(schedule=self.it_slot).values_list("pk", "updated_at")), it_lessons)
        self.assertTrue(all(start == T(8, 0) for _d, start, _e, _r in self.it_rows()))

    # F — exactly one lesson per date + schedule
    def test_f_no_duplicates(self):
        count = Lesson.objects.filter(group=self.group).count()
        self.change_slot_without_sync(start_time=T(12, 0), end_time=T(13, 0))
        for _ in range(3):
            self.generate()
        self.assertEqual(Lesson.objects.filter(group=self.group).count(), count)
        self.assertEqual(self.per_slot_and_date(), [])
        dates = [d for d, _s, _e in self.english_rows()]
        self.assertEqual(len(dates), len(set(dates)))

    # G — changed weekday
    def test_g_changed_weekday_moves_within_the_week_without_duplicates(self):
        before = [d for d, _s, _e in self.english_rows()]
        self.change_slot_without_sync(day_of_week="sat", start_time=T(12, 0), end_time=T(13, 0))
        result = self.generate()
        self.assertEqual((result["created_count"], result["rescheduled_count"]), (0, 4))
        after = self.english_rows()
        self.assertEqual([d for d, _s, _e in after], [d - dt.timedelta(days=1) for d in before])  # Sun → Sat, same week
        self.assertTrue(all(d.weekday() == 5 and (s, e) == (T(12, 0), T(13, 0)) for d, s, e in after))
        self.assertEqual(len(after), 4)
        self.assertEqual(self.per_slot_and_date(), [])
        self.assertEqual(self.generate()["rescheduled_count"], 0)

    def test_g_a_clash_keeps_that_lesson_and_reports_it(self):
        it_first = Lesson.objects.filter(schedule=self.it_slot).order_by("date").first()
        english_first = self.english_lessons()[0]
        # IT's first lesson sits on the Wednesday of English's first week, 12:00 — by hand.
        Lesson.objects.filter(pk=it_first.pk).update(
            date=english_first.date - dt.timedelta(days=4), start_time=T(12, 0), end_time=T(13, 0), schedule_overridden=True,
        )
        self.change_slot_without_sync(day_of_week="wed", start_time=T(12, 0), end_time=T(13, 0))
        result = self.generate()
        self.assertEqual(result["rescheduled_count"], 3)
        self.assertTrue(any("у группы уже есть занятие" in warning for warning in result["warnings"]))
        english_first.refresh_from_db()
        self.assertEqual((english_first.date.weekday(), english_first.start_time), (6, T(10, 0)))  # kept
        self.assertEqual(self.per_slot_and_date(), [])

    # Preview == Generate
    def test_preview_shows_the_current_schedule_and_matches_generate(self):
        self.change_slot_without_sync(start_time=T(12, 0), end_time=T(13, 0))
        preview = self.preview()
        english = next(row for row in preview["programs"] if row["program"] == self.english_program.pk)
        self.assertEqual(english["schedule"], ["Вс 12:00–13:00"])
        self.assertEqual((preview["to_create"], preview["to_reschedule"], english["to_reschedule"]), (0, 4, 4))
        self.assertTrue(all(start == T(10, 0) for _d, start, _e in self.english_rows()))  # preview wrote nothing

        result = self.generate()
        self.assertEqual((result["created_count"], result["rescheduled_count"]), (preview["to_create"], preview["to_reschedule"]))
        again = self.preview()
        self.assertEqual((again["to_create"], again["to_reschedule"]), (0, 0))
