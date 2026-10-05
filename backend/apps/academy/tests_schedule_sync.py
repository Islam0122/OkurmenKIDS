"""A changed weekly slot moves its open future lessons (and nothing else) —
services.schedule_lesson_sync, through every path that edits a slot:
save_teaching_program (the LMS «Изменить расписание» / the admin drawer)
and PATCH /schedules/:id/. Absolute imports only (see apps/academy/tests.py)."""
from __future__ import annotations

import datetime as dt

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.academy.models import (
    Attendance, Course, CourseLessonPlan, Group, GroupSchedule, GroupTeacher, Lesson, Room, Student,
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
    def test_each_lesson_moves_forward_to_the_new_weekday(self):
        dates = [lesson.date for lesson in self.english_lessons()]
        sync_schedule_lessons(self.english_slot, self.edit_slot(day_of_week="sat", start_time=T(12, 0), end_time=T(13, 0)))
        moved = self.english_lessons()
        self.assertEqual([lesson.date for lesson in moved], [date + dt.timedelta(days=6) for date in dates])
        self.assertTrue(all(lesson.date.weekday() == 5 for lesson in moved))
        self.assertEqual([lesson.lesson_number for lesson in moved], sorted(lesson.lesson_number for lesson in moved))


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
