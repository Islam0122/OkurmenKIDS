"""Parallel lessons and payroll: one shared session of four groups is ONE
lesson of each group's cycle (never more) and one conducted lesson of the
trainer; salary rules are unchanged (apps.academy.services.parallel_sessions)."""
from __future__ import annotations

import datetime as dt

from apps.academy.models import Attendance, Lesson, ParallelSession, Room
from apps.academy.services import parallel_sessions as service
from apps.academy.services.monthly_report import compute_monthly_stats
from apps.accounting.models import CourseCycle, CycleAccrual, CycleLesson, SalaryRule, SalaryType
from apps.accounting.tests.base import D, AccountingFixture, day

R = SalaryRule.RuleType


class ParallelSessionPayrollTests(AccountingFixture):
    def setUp(self):
        super().setUp()
        self.group_c = self.group("Group C")
        self.group_d = self.group("Group D")
        self.four = [self.group_a, self.group_b, self.group_c, self.group_d]
        self.settings = self.course_settings(price="10000", lessons=12, start=None)
        self.rule(self.profile(self.trainer_user, SalaryType.PERCENT), R.PERCENT, percentage=D("10"))
        for group in self.four:
            for _ in range(5):
                self.student(group)
        self.room = Room.objects.create(name="101")

    def regular(self, count):
        with self.captureOnCommitCallbacks(execute=True):
            for group in self.four:
                self.lessons(group, [day(9, d) for d in range(1, count + 1)])

    def conduct_session(self, on=day(9, 26)):
        with self.captureOnCommitCallbacks(execute=True):
            session = service.create_session(service.SessionInput(
                teacher=self.trainer, room=self.room, date=on, start_time=dt.time(15), end_time=dt.time(16),
                groups=self.four, subject=self.python,
            ), self.admin)
            for lesson in session.lessons.all():
                Attendance.objects.bulk_create([
                    Attendance(lesson=lesson, student=s, status=Attendance.Status.PRESENT)
                    for s in lesson.group.students.all()
                ])
                lesson.homework_not_required = True
                lesson.save(update_fields=["homework_not_required"])
            service.complete_session(session, self.trainer_user)
        return session

    def test_session_is_one_lesson_of_each_group_cycle(self):
        self.regular(5)
        self.conduct_session()
        for group in self.four:
            cycle = CourseCycle.objects.get(group=group, status=CourseCycle.Status.IN_PROGRESS)
            self.assertEqual(cycle.lessons_done, 6)  # 5 regular + exactly 1 for the session
            self.assertEqual(cycle.teacher_lessons, {str(self.trainer.pk): 6})

    def test_block_completed_by_session_accrues_once_per_group_cycle(self):
        self.regular(11)
        session = self.conduct_session()
        accruals = CycleAccrual.objects.filter(cycle__status=CourseCycle.Status.COMPLETED)
        # One accrual per (group cycle, employee), as before — four groups,
        # four of their own completed blocks; nothing extra for the session.
        self.assertEqual(accruals.count(), 4)
        self.assertEqual(set(accruals.values_list("cycle__group", flat=True)), {g.pk for g in self.four})
        session_lessons = set(session.lessons.values_list("pk", flat=True))
        self.assertEqual(CycleLesson.objects.filter(lesson_id__in=session_lessons).count(), 4)
        for group in self.four:
            links = CycleLesson.objects.filter(cycle__group=group, lesson_id__in=session_lessons)
            self.assertEqual(links.count(), 1)

        # Re-completing / re-saving the session never counts it again.
        before = (CycleLesson.objects.count(), CycleAccrual.objects.count())
        with self.captureOnCommitCallbacks(execute=True):
            service.complete_session(ParallelSession.objects.get(pk=session.pk), self.trainer_user)
            for lesson in session.lessons.all():
                lesson.save()
        self.assertEqual((CycleLesson.objects.count(), CycleAccrual.objects.count()), before)

    def test_trainer_workload_counts_the_session_once(self):
        self.regular(2)
        self.conduct_session()
        stats = compute_monthly_stats(self.trainer, 2026, 9)
        # 2 regular lessons × 4 groups + ONE session (not four).
        self.assertEqual(stats["lessons_completed"], 9)
        self.assertEqual(Lesson.objects.filter(status=Lesson.Status.COMPLETED).count(), 12)
