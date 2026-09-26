from __future__ import annotations

import datetime as dt
import threading
from decimal import Decimal
from io import StringIO
from unittest import mock, skipUnless

from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import IntegrityError, connection, transaction
from django.test import TransactionTestCase
from django.utils import timezone

from apps.academy.models import Attendance
from apps.scholarships.models import (
    AwardMode,
    EligibilityStatus,
    ScholarshipAward,
    ScholarshipConfiguration,
    ScholarshipEvaluation,
    ScholarshipPeriod,
    ScholarshipRunLog,
)
from apps.scholarships.services.generation import (
    ScholarshipError,
    approve_period,
    generate_period,
    recalculate_period,
    run_schedule,
)

from .base import OCT_1, SEP_1, ScholarshipFixture, make_teacher

D = Decimal


class RankingTests(ScholarshipFixture):
    def setUp(self):
        super().setUp()
        self.configure(require_complete_feedback=False)

    def make_students(self, attendance_pattern):
        """One student per (attended, missed) pair, Python only."""
        students = []
        for index, (attended, missed) in enumerate(attendance_pattern):
            student = self.student(f"S{index:02d}")
            self.study(student, self.python, self.t_python, attended=attended, missed=missed)
            students.append(student)
        return students

    def ranks(self, period):
        return list(period.evaluations.filter(rank__isnull=False).order_by("rank").values_list("student_id", flat=True))

    def test_ranked_by_overall_score(self):
        low, high, mid = self.make_students([(1, 3), (4, 0), (2, 2)])
        period = self.generate()
        self.assertEqual(self.ranks(period), [high.id, mid.id, low.id])

    def test_limit_is_applied(self):
        self.configure(max_recipients=2)
        students = self.make_students([(4, 0), (3, 1), (2, 2)])
        period = self.generate()
        self.assertEqual(period.max_recipients, 2)
        self.assertEqual(list(period.awards.order_by("rank").values_list("student_id", flat=True)), [s.id for s in students[:2]])
        # The third student is still ranked, just without an award.
        self.assertEqual(self.evaluation(period, students[2]).rank, 3)

    def test_default_limit_is_twenty_with_more_eligible_students(self):
        self.assertEqual(self.config.max_recipients, 20)
        self.make_students([(4, i % 4) for i in range(23)])
        period = self.generate()
        self.assertEqual(period.evaluations.filter(eligibility_status=EligibilityStatus.ELIGIBLE).count(), 23)
        self.assertEqual(period.awards.count(), 20)
        self.assertEqual(sorted(period.awards.values_list("rank", flat=True)), list(range(1, 21)))

    def test_fewer_eligible_students_than_the_limit(self):
        self.make_students([(4, 0), (3, 1)])
        self.student("NoData")
        period = self.generate()
        self.assertEqual(period.awards.count(), 2)

    def test_ineligible_students_never_get_ranks_or_awards(self):
        good = self.make_students([(4, 0)])[0]
        late = self.student("Late", enrolled=dt.date(2026, 9, 15))
        self.study(late, self.python, self.t_python)
        period = self.generate()
        self.assertEqual(self.ranks(period), [good.id])
        self.assertFalse(period.awards.filter(student=late).exists())

    def test_tie_break_by_attendance_then_homework(self):
        self.configure(attendance_weight=D("0.50"), homework_weight=D("0.50"), feedback_weight=D("0"))
        # A: attendance 100, homework 50 → 75. B: attendance 50, homework 100 → 75.
        a = self.student("A")
        self.study(a, self.python, self.t_python, attended=2, homework_total=2, homework_done=1)
        b = self.student("B")
        self.study(b, self.python, self.t_python, attended=1, missed=1, homework_total=2, homework_done=2)
        period = self.generate()
        self.assertEqual(self.evaluation(period, a).overall_score, self.evaluation(period, b).overall_score)
        self.assertEqual(self.ranks(period), [a.id, b.id])

    def test_full_tie_break_by_enrollment_date_then_id(self):
        later = self.student("Later", enrolled=dt.date(2026, 5, 1))
        earlier = self.student("Earlier", enrolled=dt.date(2026, 2, 1))
        same_a = self.student("SameA", enrolled=dt.date(2026, 6, 1))
        same_b = self.student("SameB", enrolled=dt.date(2026, 6, 1))
        for s in (later, earlier, same_a, same_b):
            self.study(s, self.python, self.t_python)
        period = self.generate()
        self.assertEqual(self.ranks(period), [earlier.id, later.id, same_a.id, same_b.id])

    def test_results_are_deterministic_across_recalculation(self):
        self.make_students([(4, 0), (3, 1), (3, 1), (2, 2), (4, 0)])
        period = self.generate()
        first = self.ranks(period)
        for _ in range(3):
            recalculate_period(period)
            self.assertEqual(self.ranks(period), first)

    def test_recalculation_picks_up_new_data(self):
        self.configure(require_complete_feedback=True)
        student = self.student()
        self.study(student, self.python, self.t_python)
        period = self.generate()
        self.assertEqual(self.evaluation(period, student).eligibility_status, EligibilityStatus.INCOMPLETE_DATA)
        self.feedback(period, student, self.python, self.t_python)
        recalculate_period(period)
        self.assertEqual(self.evaluation(period, student).eligibility_status, EligibilityStatus.ELIGIBLE)
        self.assertEqual(period.awards.count(), 1)


class DuplicateProtectionTests(ScholarshipFixture):
    def setUp(self):
        super().setUp()
        self.configure(require_complete_feedback=False)
        self.s = self.student()
        self.study(self.s, self.python, self.t_python)

    def test_repeated_generation_is_a_no_op(self):
        first = generate_period(OCT_1, 1, today=OCT_1)
        second = generate_period(OCT_1, 1, today=OCT_1)
        self.assertTrue(first.created)
        self.assertFalse(second.created)
        self.assertEqual(first.period.pk, second.period.pk)
        self.assertEqual(ScholarshipPeriod.objects.count(), 1)
        self.assertEqual(ScholarshipAward.objects.filter(student=self.s).count(), 1)
        self.assertTrue(ScholarshipRunLog.objects.filter(result=ScholarshipRunLog.Result.SKIPPED).exists())

    def test_database_rejects_duplicate_award(self):
        period = self.generate()
        award = period.awards.get()
        with self.assertRaises(IntegrityError), transaction.atomic():
            ScholarshipAward.objects.create(
                period=period, student=self.s, evaluation=award.evaluation, rank=99, award_date=OCT_1,
            )

    def test_database_rejects_duplicate_evaluation_and_period(self):
        period = self.generate()
        with self.assertRaises(IntegrityError), transaction.atomic():
            ScholarshipEvaluation.objects.create(
                period=period, student=self.s, student_name="x", eligibility_status=EligibilityStatus.NO_DATA,
            )
        fields = {f: getattr(period, f) for f in (
            "award_day", "period_start", "period_end", "evaluation_date", "max_recipients", "attendance_weight",
            "homework_weight", "feedback_weight", "subject_aggregation", "late_homework_credit",
            "min_overall_score", "min_marked_lessons", "require_complete_feedback",
        )}
        with self.assertRaises(IntegrityError), transaction.atomic():
            ScholarshipPeriod.objects.create(**fields)

    def test_approved_period_is_locked(self):
        period = self.generate()
        approve_period(period, user=self.admin)
        period.refresh_from_db()
        self.assertEqual(period.status, ScholarshipPeriod.Status.APPROVED)
        award = period.awards.get()
        self.assertEqual((award.status, award.approved_by), (ScholarshipAward.Status.APPROVED, self.admin))
        with self.assertRaises(ScholarshipError):
            recalculate_period(period)
        with self.assertRaises(ScholarshipError):
            approve_period(period)
        self.assertEqual(period.awards.count(), 1)

    def test_same_student_can_win_independent_cycles(self):
        self.configure(award_mode=AwardMode.TWICE_MONTHLY)
        self.attend(self.s, self.lesson(self.python, self.t_python, dt.date(2026, 10, 2)))
        generate_period(OCT_1, 1, today=dt.date(2026, 10, 15))
        generate_period(dt.date(2026, 10, 15), 15, today=dt.date(2026, 10, 15))
        self.assertEqual(ScholarshipAward.objects.filter(student=self.s).count(), 2)
        self.assertEqual(ScholarshipAward.objects.values("period").distinct().count(), 2)


class ScheduleTests(ScholarshipFixture):
    def setUp(self):
        super().setUp()
        self.configure(require_complete_feedback=False)
        self.s = self.student()
        self.study(self.s, self.python, self.t_python)

    def test_first_of_month_generates_previous_month(self):
        [result] = run_schedule(today=OCT_1)
        self.assertTrue(result.created)
        self.assertEqual((result.period.period_start, result.period.period_end), (SEP_1, dt.date(2026, 9, 30)))
        self.assertEqual(result.period.status, ScholarshipPeriod.Status.DRAFT)

    def test_fifteenth_in_monthly_mode_awards_nothing_new(self):
        run_schedule(today=OCT_1)
        [result] = run_schedule(today=dt.date(2026, 10, 15))
        self.assertFalse(result.created)
        self.assertEqual(ScholarshipPeriod.objects.count(), 1)
        self.assertEqual(ScholarshipAward.objects.count(), 1)

    def test_missed_run_is_caught_up(self):
        [result] = run_schedule(today=dt.date(2026, 10, 3))
        self.assertTrue(result.created)
        self.assertEqual(result.period.evaluation_date, OCT_1)

    def test_twice_monthly_generates_the_fifteenth_cycle(self):
        self.configure(award_mode=AwardMode.TWICE_MONTHLY)
        run_schedule(today=OCT_1)
        results = run_schedule(today=dt.date(2026, 10, 15))
        self.assertEqual([r.created for r in results], [False, True])
        fifteenth = results[1].period
        self.assertEqual((fifteenth.period_start, fifteenth.period_end), (dt.date(2026, 9, 15), dt.date(2026, 10, 14)))

    def test_run_uses_academy_timezone(self):
        # 2026-09-30 19:00 UTC is already 2026-10-01 01:00 in Asia/Bishkek.
        utc_evening = dt.datetime(2026, 9, 30, 19, 0, tzinfo=dt.timezone.utc)
        with mock.patch("django.utils.timezone.now", return_value=utc_evening):
            self.assertEqual(timezone.localdate(), OCT_1)
            [result] = run_schedule()
        self.assertEqual(result.period.period_start, SEP_1)

    def test_before_the_first_cycle_date_it_uses_last_month(self):
        # On Sep 30 the latest due cycle is Sep 1 (evaluating August).
        [result] = run_schedule(today=dt.date(2026, 9, 30))
        self.assertEqual(result.period.period_start, dt.date(2026, 8, 1))

    def test_auto_approve(self):
        self.configure(auto_approve=True)
        [result] = run_schedule(today=OCT_1)
        self.assertEqual(result.period.status, ScholarshipPeriod.Status.APPROVED)
        self.assertEqual(result.period.awards.get().status, ScholarshipAward.Status.APPROVED)

    def test_failed_run_is_logged(self):
        ScholarshipConfiguration.objects.update(is_active=False)
        with self.assertRaises(ScholarshipError):
            run_schedule(today=OCT_1)
        log = ScholarshipRunLog.objects.get()
        self.assertEqual(log.result, ScholarshipRunLog.Result.FAILED)
        self.assertIn("Нет активной конфигурации", log.message)

    def test_disabled_cycle_is_refused(self):
        with self.assertRaises(ScholarshipError):
            generate_period(dt.date(2026, 10, 15), 15, today=dt.date(2026, 10, 15))
        self.assertEqual(ScholarshipRunLog.objects.get().result, ScholarshipRunLog.Result.FAILED)

    def test_management_command(self):
        out = StringIO()
        call_command("run_scholarship_schedule", "--date", "2026-10-01", stdout=out)
        self.assertIn("сформирован", out.getvalue())
        call_command("run_scholarship_schedule", "--date", "2026-10-02", stdout=out)
        self.assertIn("уже существует", out.getvalue())
        self.assertEqual(ScholarshipPeriod.objects.count(), 1)

    def test_management_command_reports_errors(self):
        ScholarshipConfiguration.objects.update(is_active=False)
        with self.assertRaises(CommandError):
            call_command("run_scholarship_schedule", "--date", "2026-10-01", stdout=StringIO())

    def test_only_one_active_configuration(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            ScholarshipConfiguration.objects.create(name="Second", is_active=True)


class EnrollmentBackfillTests(ScholarshipFixture):
    def test_backfill_uses_the_earliest_provable_date(self):
        import importlib

        from django.apps import apps as django_apps

        migration = importlib.import_module("apps.academy.migrations.0017_student_enrollment_date")
        student = self.student(enrolled=None)
        self.attend(student, self.lesson(self.python, self.t_python, dt.date(2025, 12, 1)))
        fresh = self.student("Fresh", enrolled=None)
        migration.backfill_enrollment_date(django_apps, None)
        student.refresh_from_db()
        fresh.refresh_from_db()
        self.assertEqual(student.enrollment_date, dt.date(2025, 12, 1))
        self.assertEqual(fresh.enrollment_date, timezone.localdate(fresh.created_at))


@skipUnless(connection.vendor == "postgresql", "needs real concurrent transactions (PostgreSQL)")
class ConcurrentGenerationTests(TransactionTestCase):
    def test_simultaneous_generation_creates_one_period(self):
        from apps.academy.models import Course, Group, Lesson, Student
        from apps.users.models import Subject

        ScholarshipConfiguration.objects.all().delete()
        ScholarshipConfiguration.objects.create(name="Test", require_complete_feedback=False)
        subject = Subject.objects.create(name="Python-concurrency")
        teacher = make_teacher("concurrent")
        course = Course.objects.create(name="C", count_lesson=10)
        course.subjects.set([subject])
        group = Group.objects.create(name="G", course=course, start_date=dt.date(2026, 1, 1))
        student = Student.objects.create(first_name="A", group=group, enrollment_date=dt.date(2026, 1, 1))
        lesson = Lesson.objects.create(
            group=group, teacher=teacher, subject=subject, lesson_number=1, date=dt.date(2026, 9, 3),
            start_time=dt.time(10), end_time=dt.time(11), status=Lesson.Status.COMPLETED,
        )
        Attendance.objects.create(student=student, lesson=lesson, status=Attendance.Status.PRESENT)

        barrier = threading.Barrier(2)
        results, errors = [], []

        def worker():
            try:
                barrier.wait(timeout=10)
                results.append(generate_period(OCT_1, 1, today=OCT_1))
            except Exception as exc:  # surfaced by the assertions below
                errors.append(exc)
            finally:
                connection.close()

        threads = [threading.Thread(target=worker) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)

        self.assertEqual(errors, [])
        self.assertEqual(sorted(r.created for r in results), [False, True])
        self.assertEqual(ScholarshipPeriod.objects.count(), 1)
        self.assertEqual(ScholarshipAward.objects.count(), 1)
        self.assertEqual(ScholarshipEvaluation.objects.count(), 1)

    def test_concurrent_approve_and_recalculate_leave_consistent_state(self):
        ScholarshipConfiguration.objects.all().delete()
        ScholarshipConfiguration.objects.create(name="Test", require_complete_feedback=False)
        period = generate_period(OCT_1, 1, today=OCT_1).period
        barrier = threading.Barrier(2)
        errors = []

        def run(fn):
            try:
                barrier.wait(timeout=10)
                fn(ScholarshipPeriod.objects.get(pk=period.pk))
            except ScholarshipError as exc:
                errors.append(exc)
            finally:
                connection.close()

        threads = [threading.Thread(target=run, args=(fn,)) for fn in (approve_period, recalculate_period)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)
        period.refresh_from_db()
        self.assertEqual(period.status, ScholarshipPeriod.Status.APPROVED)
        # Either recalculation ran first (no error) or it was refused after approval.
        self.assertLessEqual(len(errors), 1)
