"""«Прогресс студентов» in the group KPI — per-student figures for a period
(services.analytics.student_progress, GET /groups/{id}/student-progress/).

Absolute imports only — see the note at the top of apps/academy/tests.py.
"""
from __future__ import annotations

import datetime as dt

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APIClient

from apps.academy.models import (
    Attendance, Course, Group, GroupTeacher, Homework, HomeworkResult, Lesson, Student, StudentStatusEvent,
)
from apps.academy.services.analytics import student_progress
from apps.testing.models import AttemptStatus, StudentAttempt, Test, TestSession
from apps.users.models import Subject, Teacher, User

PASSWORD = "Str0ngPassw0rd!"
TODAY = dt.date(2026, 10, 20)  # a Tuesday


def make_user(username, role, **extra):
    return User.objects.create_user(username=username, email=f"{username}@okurmen.kg", password=PASSWORD,
                                    first_name=username.capitalize(), role=role, is_verified=True, **extra)


class ProgressFixture(TestCase):
    def setUp(self):
        self.python, _ = Subject.objects.get_or_create(name="Python")
        self.course = Course.objects.create(name="Prog", count_lesson=30)
        self.course.subjects.set([self.python])
        self.trainer = Teacher.objects.create(user=make_user("trainer", User.Role.TEACHER))
        self.group = Group.objects.create(name="PRO-01", course=self.course, teacher=self.trainer,
                                          start_date=dt.date(2026, 8, 1))
        self.program = GroupTeacher.objects.create(group=self.group, teacher=self.trainer, subject=self.python)
        self.anna = self.student("Анна", "Алиева")
        self.bek = self.student("Бек", "Бекова")
        self.number = 0

    def student(self, first, last, group=None, enrolled=dt.date(2026, 8, 1)):
        return Student.objects.create(first_name=first, last_name=last, group=group or self.group, enrollment_date=enrolled)

    def lesson(self, day, status=Lesson.Status.COMPLETED, group=None, teacher=None):
        self.number += 1
        return Lesson.objects.create(
            group=group or self.group, group_teacher=self.program if group is None else None,
            teacher=teacher or self.trainer, subject=self.python, lesson_number=self.number, date=day,
            start_time=dt.time(10), end_time=dt.time(11), status=status, topic=f"Тема {self.number}",
        )

    def mark(self, lesson, student, status):
        return Attendance.objects.create(lesson=lesson, student=student, status=status)

    def homework(self, lesson, **results):
        homework = Homework.objects.create(lesson=lesson, title=f"ДЗ {lesson.lesson_number}")
        for student, (status, score) in results.items():
            HomeworkResult.objects.create(homework=homework, student=getattr(self, student), status=status, score=score)
        return homework

    def progress(self, period="this_month", teacher_id=None, today=TODAY, **dates):
        return student_progress.group_student_progress(self.group, period=period, teacher_id=teacher_id, today=today, **dates)

    def row(self, data, student):
        return next(row for row in data["students"] if row["id"] == student.pk)


class CalculationTests(ProgressFixture):
    def setUp(self):
        super().setUp()
        self.l1 = self.lesson(dt.date(2026, 10, 5))
        self.l2 = self.lesson(dt.date(2026, 10, 8))
        self.l3 = self.lesson(dt.date(2026, 10, 12))
        self.cancelled = self.lesson(dt.date(2026, 10, 15), status=Lesson.Status.CANCELLED)
        self.future = self.lesson(dt.date(2026, 10, 26), status=Lesson.Status.SCHEDULED)
        self.open_past = self.lesson(dt.date(2026, 10, 19), status=Lesson.Status.SCHEDULED)
        for lesson, anna, bek in ((self.l1, "present", "absent"), (self.l2, "late", "excused"), (self.l3, "present", "present")):
            self.mark(lesson, self.anna, anna)
            self.mark(lesson, self.bek, bek)
        # The future lesson has its homework generated already — it isn't due yet.
        self.homework(self.l1, anna=("checked", 9), bek=("not_submitted", None))
        self.homework(self.l2, anna=("submitted", None), bek=("late", 6))
        self.homework(self.future, anna=("not_submitted", None))
        # l3: no homework planned — nothing to fail.

    def test_figures_per_student(self):
        data = self.progress()
        self.assertEqual(data["period"]["start_date"], dt.date(2026, 10, 1))
        self.assertEqual(data["lessons_held"], 3)
        anna = self.row(data, self.anna)
        self.assertEqual(anna["name"], "Анна Алиева")
        self.assertEqual((anna["lessons_held"], anna["attended"], anna["absences"], anna["late"]), (3, 3, 0, 1))
        self.assertEqual(anna["attendance_rate"], 100.0)
        self.assertEqual((anna["homework_due"], anna["homework_done"], anna["homework_rate"]), (2, 2, 100.0))
        # A missing score is not a zero: only the 9 counts.
        self.assertEqual((anna["average_score"], anna["scored_count"]), (9.0, 1))

        bek = self.row(data, self.bek)
        self.assertEqual((bek["attended"], bek["absences"], bek["excused"]), (1, 2, 1))
        self.assertEqual(bek["attendance_rate"], 33.3)
        self.assertEqual((bek["homework_due"], bek["homework_done"], bek["homework_rate"]), (2, 1, 50.0))
        self.assertEqual(bek["average_score"], 6.0)

    def test_cancelled_and_future_lessons_are_not_counted(self):
        for row in self.progress()["students"]:
            self.assertEqual(row["lessons_held"], 3)
            self.assertEqual(row["homework_due"], 2)

    def test_unmarked_lesson_is_not_an_absence(self):
        Attendance.objects.filter(lesson=self.l3, student=self.bek).delete()
        bek = self.row(self.progress(), self.bek)
        self.assertEqual((bek["lessons_held"], bek["attendance_marked"], bek["absences"]), (3, 2, 2))
        self.assertEqual(bek["attendance_rate"], 0.0)

    def test_detail_lists_lessons_with_attendance_and_homework(self):
        detail = student_progress.student_progress_detail(self.group, self.bek.pk, period="this_month", today=TODAY)
        self.assertEqual([l["id"] for l in detail["lessons"]], [self.l1.pk, self.l2.pk, self.l3.pk])
        first = detail["lessons"][0]
        self.assertEqual((first["date"], first["attendance"], first["attendance_display"]), (self.l1.date, "absent", "Отсутствовал"))
        self.assertEqual(first["homework"][0]["status"], "not_submitted")
        self.assertEqual(detail["lessons"][1]["homework"][0]["score"], 6)
        self.assertEqual(detail["lessons"][2]["homework"], [])
        self.assertEqual(detail["student"]["homework_rate"], 50.0)

    def test_tests_average_and_detail(self):
        test = Test.objects.create(title="Python Basics", passing_score=60)
        session = TestSession.objects.create(test=test, group=self.group, teacher=self.trainer)
        for score in (80.0, 50.0):
            attempt = StudentAttempt.objects.create(session=session, student=self.anna, group=self.group, teacher=self.trainer,
                                                    student_name="Анна", test_title="Python Basics")
            StudentAttempt.objects.filter(pk=attempt.pk).update(
                status=AttemptStatus.FINISHED, score=score,
                finished_at=timezone.make_aware(dt.datetime(2026, 10, 10, 12)),
            )
        anna = self.row(self.progress(), self.anna)
        self.assertEqual((anna["tests_count"], anna["test_average"]), (2, 65.0))
        self.assertIsNone(self.row(self.progress(), self.bek)["test_average"])
        detail = student_progress.student_progress_detail(self.group, self.anna.pk, period="this_month", today=TODAY)
        self.assertEqual(sorted(t["passed"] for t in detail["tests"]), [False, True])


class PeriodTests(ProgressFixture):
    def setUp(self):
        super().setUp()
        self.september = self.lesson(dt.date(2026, 9, 15))
        self.early_october = self.lesson(dt.date(2026, 10, 2))
        self.last_week = self.lesson(dt.date(2026, 10, 16))
        for lesson, status in ((self.september, "absent"), (self.early_october, "present"), (self.last_week, "present")):
            self.mark(lesson, self.anna, status)

    def test_each_period_picks_its_own_lessons(self):
        cases = {
            "this_month": 2, "last_month": 1, "last_7_days": 1, "last_week": 1, "this_week": 0, "today": 0,
        }
        for period, held in cases.items():
            with self.subTest(period=period):
                self.assertEqual(self.row(self.progress(period), self.anna)["lessons_held"], held)
        custom = self.progress("custom", start_date=dt.date(2026, 9, 1), end_date=dt.date(2026, 10, 31))
        self.assertEqual(self.row(custom, self.anna)["lessons_held"], 3)

    def test_last_month_is_the_full_previous_calendar_month(self):
        data = self.progress("last_month")
        self.assertEqual((data["period"]["start_date"], data["period"]["end_date"]), (dt.date(2026, 9, 1), dt.date(2026, 9, 30)))
        self.assertEqual(self.row(data, self.anna)["attendance_rate"], 0.0)

    def test_dynamics_against_the_previous_period(self):
        anna = self.row(self.progress("this_month"), self.anna)
        self.assertEqual(self.progress("this_month")["comparison"]["start_date"], dt.date(2026, 9, 1))
        self.assertEqual(anna["previous"]["attendance_rate"], 0.0)
        self.assertEqual(anna["change"]["attendance_rate"], 100.0)
        # No homework on either side → no change to report, not a fake 0.
        self.assertIsNone(anna["change"]["homework_rate"])

    def test_no_previous_data_means_no_dynamics(self):
        bek = self.row(self.progress("last_month"), self.bek)
        self.assertIsNone(bek["previous"])
        self.assertEqual(bek["change"], {"attendance_rate": None, "homework_rate": None, "average_score": None, "test_average": None})


class MissingDataTests(ProgressFixture):
    def test_no_lessons_gives_no_data_not_zero(self):
        data = self.progress()
        self.assertEqual(data["lessons_held"], 0)
        self.assertEqual(len(data["students"]), 2)
        for row in data["students"]:
            self.assertEqual(row["lessons_held"], 0)
            for key in ("attendance_rate", "homework_rate", "average_score", "test_average"):
                self.assertIsNone(row[key])

    def test_lesson_without_homework_or_marks(self):
        self.lesson(dt.date(2026, 10, 5))
        anna = self.row(self.progress(), self.anna)
        self.assertEqual((anna["lessons_held"], anna["homework_due"]), (1, 0))
        self.assertIsNone(anna["attendance_rate"])
        self.assertIsNone(anna["homework_rate"])


class MembershipTests(ProgressFixture):
    def setUp(self):
        super().setUp()
        self.other = Group.objects.create(name="PRO-02", course=self.course, start_date=dt.date(2026, 8, 1))
        self.l1 = self.lesson(dt.date(2026, 10, 5))
        self.l2 = self.lesson(dt.date(2026, 10, 12))

    def test_joined_mid_period_counts_from_enrollment(self):
        newcomer = self.student("Нур", "Новая", enrolled=dt.date(2026, 10, 10))
        self.assertEqual(self.row(self.progress(), newcomer)["lessons_held"], 1)

    def test_joined_after_the_period_is_not_listed(self):
        late = self.student("Поздний", "Студент", enrolled=dt.date(2026, 10, 1))
        ids = [row["id"] for row in self.progress("last_month")["students"]]
        self.assertNotIn(late.pk, ids)

    def test_transferred_out_counts_only_before_the_transfer(self):
        StudentStatusEvent.objects.create(student=self.bek, event_type="transferred", from_group=self.group,
                                          group=self.other, event_date=dt.date(2026, 10, 8))
        Student.objects.filter(pk=self.bek.pk).update(group=self.other)
        bek = self.row(self.progress(), self.bek)
        self.assertEqual(bek["lessons_held"], 1)
        self.assertFalse(bek["in_group_now"])

    def test_transferred_in_counts_only_after_the_transfer(self):
        mover = self.student("Мурат", "Переведённый", group=self.other)
        StudentStatusEvent.objects.create(student=mover, event_type="transferred", from_group=self.other,
                                          group=self.group, event_date=dt.date(2026, 10, 8))
        Student.objects.filter(pk=mover.pk).update(group=self.group)
        self.assertEqual(self.row(self.progress(), mover)["lessons_held"], 1)

    def test_paused_time_is_not_counted(self):
        StudentStatusEvent.objects.create(student=self.anna, event_type="paused", reason="health",
                                          group=self.group, event_date=dt.date(2026, 10, 1))
        StudentStatusEvent.objects.create(student=self.anna, event_type="continued",
                                          group=self.group, event_date=dt.date(2026, 10, 10))
        self.assertEqual(self.row(self.progress(), self.anna)["lessons_held"], 1)

    def test_a_record_always_counts(self):
        late = self.student("Нур", "Новая", enrolled=dt.date(2026, 10, 10))
        self.mark(self.l1, late, "present")  # was there before the recorded enrollment date
        self.assertEqual(self.row(self.progress(), late)["lessons_held"], 2)

    def test_other_groups_lessons_never_count(self):
        foreign = self.lesson(dt.date(2026, 10, 6), group=self.other)
        stranger = self.student("Чужой", "Студент", group=self.other)
        self.mark(foreign, stranger, "present")
        ids = [row["id"] for row in self.progress()["students"]]
        self.assertNotIn(stranger.pk, ids)
        self.assertEqual(self.row(self.progress(), self.anna)["lessons_held"], 2)


class QueryCountTests(ProgressFixture):
    def test_queries_do_not_grow_with_students(self):
        lessons = [self.lesson(dt.date(2026, 10, day)) for day in (5, 8)]
        for lesson in lessons:
            self.homework(lesson, anna=("checked", 8))

        def count():
            with CaptureQueriesContext(connection) as ctx:
                self.progress()
            return len(ctx.captured_queries)

        before = count()
        for i in range(6):
            extra = self.student(f"S{i}", "Extra")
            for lesson in lessons:
                self.mark(lesson, extra, "present")
            StudentStatusEvent.objects.create(student=extra, event_type="paused", reason="health",
                                              group=self.group, event_date=dt.date(2026, 10, 30))
        self.assertEqual(count(), before)


class ApiAccessTests(ProgressFixture):
    def setUp(self):
        super().setUp()
        self.today = timezone.localdate()
        self.lesson_today = self.lesson(self.today)
        self.mark(self.lesson_today, self.anna, "present")
        self.api = APIClient()

    def url(self, group=None, student=None):
        base = f"/api/v1/groups/{(group or self.group).pk}/student-progress/"
        return f"{base}{student.pk}/" if student else base

    def test_trainer_sees_own_group(self):
        self.api.force_authenticate(self.trainer.user)
        response = self.api.get(self.url(), {"period": "today"})
        self.assertEqual(response.status_code, 200)
        anna = next(row for row in response.data["students"] if row["id"] == self.anna.pk)
        self.assertEqual(anna["attendance_rate"], 100.0)
        detail = self.api.get(self.url(student=self.anna), {"period": "today"})
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.data["lessons"][0]["attendance"], "present")

    def test_trainer_cannot_open_another_group(self):
        stranger = Teacher.objects.create(user=make_user("stranger", User.Role.TEACHER))
        other = Group.objects.create(name="PRO-09", course=self.course, teacher=stranger, start_date=dt.date(2026, 8, 1))
        self.api.force_authenticate(self.trainer.user)
        self.assertEqual(self.api.get(self.url(other), {"period": "today"}).status_code, 404)
        self.assertEqual(self.api.get(self.url(other, self.anna), {"period": "today"}).status_code, 404)

    def test_student_outside_the_group_is_404(self):
        outsider = Student.objects.create(first_name="X", group=None)
        self.api.force_authenticate(self.trainer.user)
        self.assertEqual(self.api.get(self.url(student=outsider), {"period": "today"}).status_code, 404)

    def test_trainer_sees_only_own_lessons_in_a_shared_group(self):
        colleague = Teacher.objects.create(user=make_user("colleague", User.Role.TEACHER))
        theirs = self.lesson(self.today, teacher=colleague)
        self.mark(theirs, self.anna, "absent")
        self.api.force_authenticate(self.trainer.user)
        anna = next(r for r in self.api.get(self.url(), {"period": "today"}).data["students"] if r["id"] == self.anna.pk)
        self.assertEqual((anna["lessons_held"], anna["attendance_rate"]), (1, 100.0))
        admin = make_user("boss", User.Role.ADMIN)
        self.api.force_authenticate(admin)
        anna = next(r for r in self.api.get(self.url(), {"period": "today"}).data["students"] if r["id"] == self.anna.pk)
        self.assertEqual((anna["lessons_held"], anna["attendance_rate"]), (2, 50.0))

    def test_anonymous_and_bad_period_are_refused(self):
        self.assertIn(self.api.get(self.url()).status_code, (401, 403))
        self.api.force_authenticate(self.trainer.user)
        self.assertEqual(self.api.get(self.url(), {"period": "forever"}).status_code, 400)

    def test_group_kpi_is_unchanged(self):
        self.api.force_authenticate(self.trainer.user)
        dashboard = self.api.get("/api/v1/analytics/dashboard/", {"period": "today", "group": self.group.pk})
        self.assertEqual(dashboard.status_code, 200)
        self.assertEqual(dashboard.data["attendance"]["attendance_rate"]["value"], 100.0)


class CustomRangeTests(ProgressFixture):
    """The manual «С — По» range (period=custom): inclusive, in the project's
    time zone, compared with the interval of the same length right before it."""

    def setUp(self):
        super().setUp()
        self.before = self.lesson(dt.date(2026, 9, 30))
        self.first_day = self.lesson(dt.date(2026, 10, 1))
        self.middle = self.lesson(dt.date(2026, 10, 5))
        self.last_day = self.lesson(dt.date(2026, 10, 10))
        self.after = self.lesson(dt.date(2026, 10, 11))
        self.cancelled = self.lesson(dt.date(2026, 10, 6), status=Lesson.Status.CANCELLED)
        for lesson in (self.before, self.first_day, self.middle, self.last_day, self.after):
            self.mark(lesson, self.anna, "present")
        self.mark(self.before, self.bek, "present")
        for lesson in (self.first_day, self.middle, self.last_day):
            self.mark(lesson, self.bek, "absent")

    def custom(self, start, end, today=TODAY):
        return self.progress("custom", start_date=start, end_date=end, today=today)

    def test_both_boundary_days_are_included(self):
        data = self.custom(dt.date(2026, 10, 1), dt.date(2026, 10, 10))
        self.assertEqual((data["period"]["start_date"], data["period"]["end_date"]), (dt.date(2026, 10, 1), dt.date(2026, 10, 10)))
        self.assertEqual(data["lessons_held"], 3)
        self.assertEqual(self.row(data, self.anna)["lessons_held"], 3)
        bek = self.row(data, self.bek)
        self.assertEqual((bek["absences"], bek["attendance_rate"]), (3, 0.0))
        detail = student_progress.student_progress_detail(
            self.group, self.bek.pk, period="custom", start_date=dt.date(2026, 10, 1), end_date=dt.date(2026, 10, 10), today=TODAY,
        )
        self.assertEqual([l["date"] for l in detail["lessons"]], [dt.date(2026, 10, 1), dt.date(2026, 10, 5), dt.date(2026, 10, 10)])

    def test_single_day_range(self):
        data = self.custom(dt.date(2026, 10, 10), dt.date(2026, 10, 10))
        self.assertEqual(self.row(data, self.anna)["lessons_held"], 1)

    def test_comparison_is_the_same_length_right_before(self):
        data = self.custom(dt.date(2026, 10, 1), dt.date(2026, 10, 10))
        self.assertEqual((data["comparison"]["start_date"], data["comparison"]["end_date"]), (dt.date(2026, 9, 21), dt.date(2026, 9, 30)))
        bek = self.row(data, self.bek)
        self.assertEqual(bek["previous"]["attendance_rate"], 100.0)
        self.assertEqual(bek["change"]["attendance_rate"], -100.0)

    def test_future_part_of_the_range_is_not_held(self):
        upcoming = self.lesson(dt.date(2026, 10, 22), status=Lesson.Status.SCHEDULED)
        Homework.objects.create(lesson=upcoming, title="Будущее ДЗ")
        data = self.custom(dt.date(2026, 10, 1), dt.date(2026, 10, 31))
        anna = self.row(data, self.anna)
        self.assertEqual((anna["lessons_held"], anna["homework_due"]), (4, 0))

    def test_empty_range(self):
        data = self.custom(dt.date(2026, 10, 14), dt.date(2026, 10, 18))
        self.assertEqual(data["lessons_held"], 0)
        for row in data["students"]:
            self.assertEqual(row["lessons_held"], 0)
            self.assertIsNone(row["attendance_rate"])

    def test_tests_on_the_boundary_follow_the_project_time_zone(self):
        test = Test.objects.create(title="Boundary", passing_score=50)
        session = TestSession.objects.create(test=test, group=self.group, teacher=self.trainer)
        bishkek = timezone.get_current_timezone()
        for local, score in ((dt.datetime(2026, 10, 10, 23, 30), 90.0), (dt.datetime(2026, 10, 11, 0, 30), 10.0),
                             (dt.datetime(2026, 10, 1, 0, 15), 70.0)):
            attempt = StudentAttempt.objects.create(session=session, student=self.anna, group=self.group, teacher=self.trainer,
                                                    student_name="Анна", test_title="Boundary")
            StudentAttempt.objects.filter(pk=attempt.pk).update(
                status=AttemptStatus.FINISHED, score=score, finished_at=timezone.make_aware(local, bishkek),
            )
        anna = self.row(self.custom(dt.date(2026, 10, 1), dt.date(2026, 10, 10)), self.anna)
        # 23:30 on the last day and 00:15 on the first day (both still "yesterday" in UTC) count; 00:30 next day doesn't.
        self.assertEqual((anna["tests_count"], anna["test_average"]), (2, 80.0))


class CustomRangeApiTests(ProgressFixture):
    def setUp(self):
        super().setUp()
        self.api = APIClient()
        self.api.force_authenticate(self.trainer.user)
        self.today = timezone.localdate()
        self.day = self.today - dt.timedelta(days=3)
        self.mark(self.lesson(self.day), self.anna, "present")

    def get(self, start, end):
        return self.api.get(f"/api/v1/groups/{self.group.pk}/student-progress/",
                            {"period": "custom", "start_date": str(start), "end_date": str(end)})

    def test_custom_range_through_the_api(self):
        response = self.get(self.day, self.day)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["period"]["start_date"], self.day)
        anna = next(row for row in response.data["students"] if row["id"] == self.anna.pk)
        self.assertEqual(anna["attendance_rate"], 100.0)
        detail = self.api.get(f"/api/v1/groups/{self.group.pk}/student-progress/{self.anna.pk}/",
                              {"period": "custom", "start_date": str(self.day), "end_date": str(self.day)})
        self.assertEqual(len(detail.data["lessons"]), 1)
        outside = self.get(self.day + dt.timedelta(days=1), self.today)
        self.assertEqual(outside.data["lessons_held"], 0)

    def test_start_after_end_is_refused(self):
        response = self.get(self.today, self.day)
        self.assertEqual(response.status_code, 400)
        self.assertIn("start_date", response.data)

    def test_custom_needs_both_dates(self):
        response = self.api.get(f"/api/v1/groups/{self.group.pk}/student-progress/", {"period": "custom", "start_date": str(self.day)})
        self.assertEqual(response.status_code, 400)

    def test_group_kpi_accepts_the_same_range(self):
        response = self.api.get("/api/v1/analytics/dashboard/", {
            "period": "custom", "start_date": str(self.day), "end_date": str(self.day), "group": self.group.pk,
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["lessons"]["lessons_total"]["value"], 1)
        self.assertEqual(response.data["attendance"]["attendance_rate"]["value"], 100.0)
