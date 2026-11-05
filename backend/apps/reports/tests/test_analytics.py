"""Report analytics (apps.reports.services.analytics) against real LMS records."""
from __future__ import annotations

import datetime as dt

from apps.academy.models import Group, GroupTeacher, Lesson, StudentStatusEvent
from apps.academy.services.student_status import deactivate_student
from apps.reports.services import analytics, i18n, periods
from apps.testing.models import Answer, GradingStatus, Question, QuestionType
from apps.users.models import Subject, Teacher, User

from .base import TODAY, OctoberFixture, ReportFixture, make_user


class GroupCalculationTests(OctoberFixture):
    def test_group_statistics(self):
        stats = self.data()["group_stats"]
        self.assertEqual(stats["active_students"], 2)
        # l1, l2, l3 conducted; the cancelled and the still-open lesson are not.
        self.assertEqual(stats["conducted_lessons"], 3)
        self.assertEqual(stats["planned_lessons"], 4)
        self.assertEqual(stats["cancelled_lessons"], 1)
        # Attendance pooled over marked lessons: Anna 3/3, Bek 1/3 → 4/6.
        self.assertEqual((stats["attended"], stats["attendance_marked"], stats["attendance_rate"]), (4, 6, 66.7))
        self.assertEqual(stats["absences"], 2)
        # Homework: Anna 2/2, Bek 1/2 → 3/4. Missing score is not a zero: (9 + 6) / 2.
        self.assertEqual((stats["homework_done"], stats["homework_due"], stats["homework_rate"]), (3, 4, 75.0))
        self.assertEqual((stats["average_score"], stats["scored_count"]), (7.5, 2))
        self.assertIsNone(stats["test_average"])
        self.assertEqual((stats["excellent_count"], stats["attention_count"]), (1, 1))

    def test_snapshot_metadata(self):
        data = self.data()
        self.assertEqual(data["group"]["name"], "PY-01")
        self.assertEqual(data["group"]["course"], "Python для детей")
        self.assertEqual((data["period"]["start"], data["period"]["end"]), ("2026-10-01", "2026-10-31"))
        self.assertTrue(data["period"]["monthly"])
        self.assertEqual(data["comparison_period"], {"start": "2026-09-01", "end": "2026-09-30"})


class IndividualCalculationTests(OctoberFixture):
    def test_individual_figures(self):
        anna = self.entry(self.data(), self.anna)
        self.assertEqual(anna["name"], "Анна Алиева")
        self.assertEqual((anna["lessons_held"], anna["attended"], anna["absences"]), (3, 3, 0))
        self.assertEqual(anna["attendance_rate"], 100.0)
        self.assertEqual((anna["homework_done"], anna["homework_due"], anna["homework_rate"]), (2, 2, 100.0))
        self.assertEqual(anna["average_score"], 9.0)
        self.assertEqual(anna["status"], analytics.STATUS_EXCELLENT)

        bek = self.entry(self.data(), self.bek)
        self.assertEqual((bek["attended"], bek["absences"], bek["attendance_rate"]), (1, 2, 33.3))
        self.assertEqual((bek["homework_done"], bek["homework_due"], bek["homework_rate"]), (1, 2, 50.0))
        # Attendance below 50% → support whatever the grades.
        self.assertEqual(bek["status"], analytics.STATUS_SUPPORT)

    def test_unmarked_lesson_is_not_an_absence(self):
        self.l3.attendance_records.filter(student=self.bek).delete()
        bek = self.entry(self.data(), self.bek)
        self.assertEqual((bek["lessons_held"], bek["attendance_marked"], bek["absences"]), (3, 2, 2))
        self.assertEqual(bek["attendance_rate"], 0.0)

    def test_previous_period_comparison(self):
        data = self.data()
        anna = self.entry(data, self.anna)
        # September: Anna 1/2 attended, homework 1/1, score 7.
        self.assertEqual(anna["previous"], {"attendance_rate": 50.0, "homework_rate": 100.0, "average_score": 7.0, "test_average": None})
        self.assertEqual(anna["comparison"]["attendance_rate"]["change"], 50.0)
        self.assertEqual(anna["comparison"]["attendance_rate"]["trend"], "up")
        self.assertEqual(anna["comparison"]["homework_rate"]["trend"], "stable")
        self.assertEqual(anna["comparison"]["average_score"]["change"], 2.0)
        # No tests in either period → no change, never 0.
        self.assertIsNone(anna["comparison"]["test_average"]["change"])
        self.assertEqual(anna["comparison"]["test_average"]["trend"], "no_data")

        group = data["group_comparison"]
        self.assertEqual(group["attendance_rate"]["previous"], 75.0)  # 3 of 4 in September
        self.assertEqual(group["attendance_rate"]["change"], -8.3)
        self.assertEqual(group["homework_rate"]["change"], -25.0)

    def test_no_previous_data_means_no_comparison(self):
        Lesson.objects.filter(date__month=9).delete()
        data = self.data()
        self.assertIsNone(self.entry(data, self.anna)["previous"])
        self.assertIsNone(data["previous_group_stats"])
        self.assertIsNone(data["group_comparison"]["attendance_rate"]["change"])


class LessonRuleTests(ReportFixture):
    def test_future_and_cancelled_lessons_are_not_conducted(self):
        done = self.lesson(dt.date(2026, 11, 2))
        self.mark(done, self.anna, "present")
        future = self.lesson(dt.date(2026, 11, 20), status=Lesson.Status.SCHEDULED)
        self.homework(future, {self.anna: ("not_submitted", None)})
        # A lesson wrongly marked completed in the future is still not conducted.
        wrong = self.lesson(dt.date(2026, 11, 25), status=Lesson.Status.COMPLETED)
        self.mark(wrong, self.bek, "absent")
        cancelled = self.lesson(dt.date(2026, 11, 3), status=Lesson.Status.CANCELLED)
        self.mark(cancelled, self.bek, "absent")

        data = self.data("custom", start_date=dt.date(2026, 11, 1), end_date=dt.date(2026, 11, 30))
        stats = data["group_stats"]
        self.assertEqual(stats["conducted_lessons"], 1)
        self.assertEqual(stats["cancelled_lessons"], 1)
        self.assertEqual(stats["homework_due"], 0)
        self.assertIsNone(stats["homework_rate"])
        anna = self.entry(data, self.anna)
        self.assertEqual((anna["lessons_held"], anna["attendance_rate"]), (1, 100.0))
        bek = self.entry(data, self.bek)
        self.assertEqual(bek["absences"], 0)
        self.assertIsNone(bek["attendance_rate"])

    def test_other_trainers_lessons_are_excluded_for_a_trainer(self):
        english, _ = Subject.objects.get_or_create(name="English")
        other = Teacher.objects.create(user=make_user("other", User.Role.TEACHER))
        other_program = GroupTeacher.objects.create(group=self.group, teacher=other, subject=english)
        mine = self.lesson(dt.date(2026, 10, 6))
        theirs = self.lesson(dt.date(2026, 10, 7), teacher=other, program=other_program)
        self.mark(mine, self.anna, "present")
        self.mark(theirs, self.anna, "absent")

        whole = self.data()
        self.assertEqual(whole["group_stats"]["conducted_lessons"], 2)
        self.assertEqual(self.entry(whole, self.anna)["attendance_rate"], 50.0)

        own = self.data(teacher_id=self.trainer.pk)
        self.assertEqual(own["group_stats"]["conducted_lessons"], 1)
        self.assertEqual(self.entry(own, self.anna)["attendance_rate"], 100.0)
        self.assertEqual(own["group"]["trainers"], [str(self.trainer)])


class MissingDataTests(ReportFixture):
    def test_no_records_means_no_data_not_zero(self):
        data = self.data()
        stats = data["group_stats"]
        for key in ("attendance_rate", "homework_rate", "average_score", "test_average"):
            self.assertIsNone(stats[key], key)
        anna = self.entry(data, self.anna)
        self.assertEqual(anna["status"], analytics.STATUS_NO_DATA)
        self.assertEqual((anna["lessons_held"], anna["attendance_marked"]), (0, 0))
        self.assertEqual(i18n.percent(anna["attendance_rate"], "ru"), "Нет данных")
        self.assertEqual(i18n.percent(anna["homework_rate"], "ky"), "Маалымат жок")

    def test_no_homework_assigned_is_no_data(self):
        lesson = self.lesson(dt.date(2026, 10, 5))
        self.mark(lesson, self.anna, "present")
        anna = self.entry(self.data(), self.anna)
        self.assertEqual(anna["attendance_rate"], 100.0)
        self.assertEqual(anna["homework_due"], 0)
        self.assertIsNone(anna["homework_rate"])
        self.assertIsNone(anna["average_score"])

    def test_homework_without_scores_keeps_score_empty(self):
        lesson = self.lesson(dt.date(2026, 10, 5))
        self.homework(lesson, {self.anna: ("submitted", None), self.bek: ("not_submitted", None)})
        data = self.data()
        self.assertEqual(self.entry(data, self.anna)["homework_rate"], 100.0)
        self.assertEqual(self.entry(data, self.bek)["homework_rate"], 0.0)
        self.assertIsNone(data["group_stats"]["average_score"])


class StudentScopeTests(OctoberFixture):
    def test_deactivated_student_is_excluded(self):
        deactivate_student(self.bek, reason=StudentStatusEvent.Reason.OTHER, comment="Переезд", event_date=dt.date(2026, 10, 20))
        data = self.data()
        self.assertEqual([entry["id"] for entry in data["students"]], [self.anna.pk])
        stats = data["group_stats"]
        self.assertEqual(stats["active_students"], 1)
        # Only Anna's records count: 3 of 3.
        self.assertEqual(stats["attendance_rate"], 100.0)
        self.assertEqual(stats["homework_rate"], 100.0)

    def test_student_deactivated_after_the_period_stays_in_it(self):
        deactivate_student(self.bek, reason=StudentStatusEvent.Reason.OTHER, comment="Переезд", event_date=dt.date(2026, 11, 2))
        data = self.data()
        self.assertEqual({entry["id"] for entry in data["students"]}, {self.anna.pk, self.bek.pk})
        # …but not in a report of the current month.
        november = self.data("this_month")
        self.assertEqual([entry["id"] for entry in november["students"]], [self.anna.pk])

    def test_students_of_other_groups_are_not_counted(self):
        other = Group.objects.create(name="PY-02", course=self.course, teacher=self.trainer, start_date=dt.date(2026, 8, 1))
        stranger = self.student("Чужой", "Студент", group=other)
        lesson = self.lesson(dt.date(2026, 10, 6), group=other)
        self.mark(lesson, stranger, "absent")
        self.attempt(stranger, 10.0, dt.date(2026, 10, 9), group=other)
        data = self.data()
        self.assertNotIn(stranger.pk, {entry["id"] for entry in data["students"]})
        self.assertEqual(data["group_stats"]["conducted_lessons"], 3)
        self.assertEqual(data["group_stats"]["attendance_marked"], 6)
        self.assertIsNone(data["group_stats"]["test_average"])

    def test_selected_students_only(self):
        period = self.period()
        data = analytics.build_report_data(self.group, period, today=TODAY, student_ids=[self.bek.pk])
        self.assertEqual([entry["id"] for entry in data["students"]], [self.bek.pk])


class TestResultsTests(OctoberFixture):
    def test_tests_average_and_missing_tests(self):
        self.attempt(self.anna, 80.0, dt.date(2026, 10, 10))
        self.attempt(self.anna, 50.0, dt.date(2026, 10, 20))
        data = self.data()
        anna = self.entry(data, self.anna)
        self.assertEqual((anna["tests_count"], anna["test_average"]), (2, 65.0))
        self.assertEqual([test["score"] for test in anna["tests"]], [80.0, 50.0])
        self.assertEqual([test["passed"] for test in anna["tests"]], [True, False])
        bek = self.entry(data, self.bek)
        self.assertIsNone(bek["test_average"])
        self.assertEqual(data["group_stats"]["test_average"], 65.0)

    def test_attempt_waiting_for_review_is_not_a_result(self):
        self.attempt(self.anna, 90.0, dt.date(2026, 10, 10))
        pending = self.attempt(self.anna, 20.0, dt.date(2026, 10, 11))
        question = Question.objects.create(test=self._test, text="Explain", question_type=QuestionType.TEXT)
        Answer.objects.create(attempt=pending, question=question, grading_status=GradingStatus.PENDING)
        anna = self.entry(self.data(), self.anna)
        self.assertEqual((anna["tests_count"], anna["test_average"]), (1, 90.0))


class PeriodTests(ReportFixture):
    def test_quick_periods_and_equivalent_comparison(self):
        this_month = periods.resolve("this_month", today=TODAY)
        self.assertEqual((this_month.current.start, this_month.current.end), (dt.date(2026, 11, 1), TODAY))
        # The same days of the previous month.
        self.assertEqual((this_month.previous.start, this_month.previous.end), (dt.date(2026, 10, 1), dt.date(2026, 10, 5)))
        week = periods.resolve("last_week", today=TODAY)
        self.assertEqual((week.current.start, week.previous.start), (dt.date(2026, 10, 26), dt.date(2026, 10, 19)))
        seven = periods.resolve("last_7_days", today=TODAY)
        self.assertEqual((seven.previous.start, seven.previous.end), (dt.date(2026, 10, 23), dt.date(2026, 10, 29)))
        custom = periods.resolve("custom", today=TODAY, start_date=dt.date(2026, 10, 10), end_date=dt.date(2026, 10, 19))
        self.assertEqual((custom.previous.start, custom.previous.end), (dt.date(2026, 9, 30), dt.date(2026, 10, 9)))

    def test_invalid_periods(self):
        with self.assertRaisesMessage(periods.PeriodError, "позже"):
            periods.resolve("custom", today=TODAY, start_date=dt.date(2026, 10, 10), end_date=dt.date(2026, 10, 1))
        with self.assertRaisesMessage(periods.PeriodError, "ещё не начался"):
            periods.resolve("custom", today=TODAY, start_date=dt.date(2026, 12, 1), end_date=dt.date(2026, 12, 31))
        with self.assertRaisesMessage(periods.PeriodError, "одного года"):
            periods.resolve("custom", today=TODAY, start_date=dt.date(2024, 1, 1), end_date=dt.date(2026, 1, 1))
        with self.assertRaises(periods.PeriodError):
            periods.resolve("custom", today=TODAY, start_date=dt.date(2026, 10, 1))
        with self.assertRaises(periods.PeriodError):
            periods.resolve("forever", today=TODAY)


class StatusTests(ReportFixture):
    def test_status_thresholds(self):
        status = analytics.student_status
        self.assertEqual(status({"attendance_rate": 100, "homework_rate": 90, "average_score": 9, "test_average": None}), "excellent")
        self.assertEqual(status({"attendance_rate": 80, "homework_rate": 70, "average_score": 7, "test_average": None}), "good")
        self.assertEqual(status({"attendance_rate": 70, "homework_rate": 50, "average_score": 6, "test_average": None}), "attention")
        self.assertEqual(status({"attendance_rate": 60, "homework_rate": 30, "average_score": 4, "test_average": 40}), "support")
        self.assertEqual(status({"attendance_rate": 40, "homework_rate": 100, "average_score": 10, "test_average": 100}), "support")
        self.assertEqual(status({"attendance_rate": None, "homework_rate": None, "average_score": None, "test_average": None}), "no_data")
