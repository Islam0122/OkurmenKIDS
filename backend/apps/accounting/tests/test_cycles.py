"""Автоматический учёт уроков и начисление процента тренеру по порогам."""
from __future__ import annotations

from apps.academy.models import Lesson
from apps.accounting.models import (
    CourseCycle,
    CycleAccrual,
    Payroll,
    PayrollAdjustment,
    PayrollAuditLog,
    PayrollLine,
    SalaryRule,
    SalaryType,
)
from apps.accounting.services.approval_service import approve_payroll, decide_adjustment
from apps.accounting.services.cycles import sync_all
from apps.accounting.tests.base import FIRST, SECOND, D, AccountingFixture, day

R = SalaryRule.RuleType
Status = CycleAccrual.Status


def days(month, first, last):
    return [day(month, d) for d in range(first, last + 1)]


class AutomaticAccrualTests(AccountingFixture):
    def setUp(self):
        super().setUp()
        self.settings = self.course_settings(price="10000", lessons=12, start=None)
        self.rule(self.profile(salary_type=SalaryType.PERCENT), R.PERCENT, percentage=D("10"))
        for _ in range(10):
            self.student(self.group_a)

    def add_lessons(self, dates, group=None):
        """Сохранение уроков в LMS — учёт идёт сам, по сигналу после коммита."""
        with self.captureOnCommitCallbacks(execute=True):
            self.lessons(group or self.group_a, dates)

    def completed(self, group=None):
        return list(CourseCycle.objects.filter(group=group or self.group_a, status="COMPLETED").order_by("number"))

    def test_reaching_threshold_creates_the_accrual_without_any_calculation(self):
        self.add_lessons(days(9, 1, 11))
        self.assertFalse(CycleAccrual.objects.exists())
        self.add_lessons([day(9, 12)])
        accrual = CycleAccrual.objects.get()
        cycle = accrual.cycle
        self.assertEqual((cycle.group, cycle.course, cycle.number), (self.group_a, self.course, 1))
        self.assertEqual(
            (accrual.lessons, accrual.lessons_total, accrual.completed_on, accrual.student_count,
             accrual.course_price, accrual.percentage, accrual.amount, accrual.status),
            (12, 12, day(9, 12), 10, D("10000"), D("10"), D("10000.00"), Status.ACCRUED),
        )
        self.assertEqual(accrual.employee, self.trainer_user)
        self.assertTrue(PayrollAuditLog.objects.filter(entity_type="cycleaccrual", action="auto_accrue").exists())
        self.assertIsNone(accrual.payroll)

    def test_thresholds_every_interval(self):
        self.add_lessons(days(9, 1, 30))
        self.add_lessons(days(10, 1, 6))  # всего 36 уроков
        self.assertEqual([c.lessons_total for c in self.completed()], [12, 24, 36])
        self.assertEqual([c.completed_on for c in self.completed()], [day(9, 12), day(9, 24), day(10, 6)])
        self.assertEqual(CycleAccrual.objects.count(), 3)

    def test_interval_of_twenty(self):
        self.settings.required_lessons = 20
        self.settings.save()
        self.add_lessons(days(9, 1, 30))
        self.add_lessons(days(10, 1, 10))  # 40 уроков
        self.assertEqual([c.lessons_total for c in self.completed()], [20, 40])

    def test_counting_starts_from_the_first_completed_lesson(self):
        self.add_lessons(days(3, 1, 12))  # без даты начала учёта — с первого урока
        self.assertEqual(self.completed()[0].completed_on, day(3, 12))

    def test_resaving_lessons_and_rerunning_do_not_duplicate(self):
        self.add_lessons(days(9, 1, 12))
        lesson = Lesson.objects.filter(group=self.group_a).last()
        with self.captureOnCommitCallbacks(execute=True):
            lesson.topic = "Повтор"
            lesson.save()
            lesson.save()
        sync_all()
        sync_all()
        self.calc(FIRST)
        self.calc(FIRST)
        self.assertEqual(CourseCycle.objects.filter(status="COMPLETED").count(), 1)
        self.assertEqual(CycleAccrual.objects.count(), 1)
        self.assertEqual(PayrollLine.objects.filter(line_type="PERCENT").count(), 1)

    def test_cancelled_lessons_are_not_counted(self):
        self.add_lessons(days(9, 1, 11))
        with self.captureOnCommitCallbacks(execute=True):
            self.lessons(self.group_a, [day(9, 12)], status=Lesson.Status.CANCELLED)
        self.assertFalse(CycleAccrual.objects.exists())
        self.assertEqual(CourseCycle.objects.get(group=self.group_a).lessons_done, 11)

    def test_threshold_date_picks_the_period(self):
        self.add_lessons(days(9, 4, 15))  # порог 15-го → 1–15
        payroll = self.calc(FIRST)
        self.assertEqual(payroll.total_accrued, D("10000.00"))
        accrual = CycleAccrual.objects.get()
        self.assertEqual((accrual.payroll, accrual.line.payroll), (payroll, payroll))
        self.assertEqual(self.calc(SECOND).total_accrued, D("0"))

    def test_status_follows_approval(self):
        self.add_lessons(days(9, 1, 12))
        payroll = self.calc(FIRST)
        approve_payroll(payroll, self.director)
        self.assertEqual(CycleAccrual.objects.get().status, Status.APPROVED)

    def test_interval_change_applies_to_new_cycles_only(self):
        self.add_lessons(days(9, 1, 12))
        approve_payroll(self.calc(FIRST), self.director)
        self.settings.required_lessons = 20
        self.settings.save()
        self.add_lessons(days(9, 13, 30))
        self.add_lessons(days(10, 1, 14))  # всего 44 = 12 + 20 + 12
        done = self.completed()
        self.assertEqual([(c.required_lessons, c.lessons_total) for c in done], [(12, 12), (20, 32)])
        self.assertEqual(CycleAccrual.objects.get(cycle=done[0]).status, Status.APPROVED)

    def test_fixed_salary_gets_no_interval_accruals(self):
        self.profile_obj = self.trainer_user.salary_profile
        self.profile_obj.salary_type = SalaryType.FIXED
        self.profile_obj.save()
        self.add_lessons(days(9, 1, 12))
        self.assertFalse(CycleAccrual.objects.exists())


class LessonCorrectionTests(AccountingFixture):
    """Урок исправлен после начисления: история не удаляется."""

    def setUp(self):
        super().setUp()
        self.course_settings(price="10000", lessons=12, start=None)
        self.rule(self.profile(salary_type=SalaryType.PERCENT), R.PERCENT, percentage=D("10"))
        for _ in range(10):
            self.student(self.group_a)
        with self.captureOnCommitCallbacks(execute=True):
            self.lessons(self.group_a, days(9, 1, 12))
        self.accrual = CycleAccrual.objects.get()

    def cancel_last_lesson(self):
        lesson = Lesson.objects.filter(group=self.group_a).order_by("-date").first()
        with self.captureOnCommitCallbacks(execute=True):
            lesson.status = Lesson.Status.CANCELLED
            lesson.save()
        self.accrual.refresh_from_db()
        return lesson

    def test_before_approval_the_accrual_is_cancelled(self):
        payroll = self.calc(FIRST)
        self.cancel_last_lesson()
        cycle = CourseCycle.objects.get(pk=self.accrual.cycle_id)
        self.assertEqual(cycle.status, "INVALIDATED")
        self.assertIn("больше не достигнут", cycle.invalidated_reason)
        self.assertEqual(self.accrual.status, Status.CANCELLED)
        payroll.refresh_from_db()
        self.assertEqual(payroll.total_accrued, D("0"))
        self.assertEqual(payroll.lines.count(), 0)
        actions = set(PayrollAuditLog.objects.values_list("action", flat=True))
        self.assertTrue({"invalidate", "cancel"} <= actions)
        self.assertEqual(self.calc(FIRST).total_accrued, D("0"))

    def test_after_approval_a_controlled_correction_is_created(self):
        payroll = approve_payroll(self.calc(FIRST), self.director)
        self.cancel_last_lesson()
        self.assertEqual(self.accrual.status, Status.CORRECTED)
        adjustment = self.accrual.adjustment
        self.assertEqual((adjustment.kind, adjustment.amount, adjustment.status),
                         ("CORRECTION", D("-10000.00"), PayrollAdjustment.Status.PENDING))
        payroll.refresh_from_db()
        # Утверждённая история не тронута, пока директор не утвердит сторно.
        self.assertEqual((payroll.total_accrued, payroll.amount_due), (D("10000.00"), D("10000.00")))
        self.assertTrue(PayrollLine.objects.filter(payroll=payroll, line_type="PERCENT").exists())
        self.assertTrue(PayrollAuditLog.objects.filter(entity_type="payrolladjustment", payroll=payroll).exists())
        decide_adjustment(adjustment, approve=True, actor=self.director)
        payroll.refresh_from_db()
        self.assertEqual(payroll.amount_due, D("0.00"))

    def test_director_can_reject_the_reversal(self):
        approve_payroll(self.calc(FIRST), self.director)
        self.cancel_last_lesson()
        decide_adjustment(self.accrual.adjustment, approve=False, actor=self.director)
        self.accrual.refresh_from_db()
        self.assertEqual(self.accrual.status, Status.APPROVED)

    def test_threshold_reached_again_creates_a_new_cycle_once(self):
        approve_payroll(self.calc(FIRST), self.director)
        self.cancel_last_lesson()
        with self.captureOnCommitCallbacks(execute=True):
            self.lessons(self.group_a, [day(9, 20)])
        live = CourseCycle.objects.filter(group=self.group_a, status="COMPLETED").get()
        self.assertEqual((live.number, live.lessons_total, live.completed_on), (1, 12, day(9, 20)))
        self.assertEqual(CycleAccrual.objects.filter(status=Status.ACCRUED).count(), 1)
        self.assertEqual(self.calc(SECOND).total_accrued, D("10000.00"))

    def test_deleting_a_lesson_is_also_a_correction(self):
        self.calc(FIRST)
        lesson = Lesson.objects.filter(group=self.group_a).order_by("-date").first()
        with self.captureOnCommitCallbacks(execute=True):
            lesson.delete()
        self.accrual.refresh_from_db()
        self.assertEqual(self.accrual.status, Status.CANCELLED)

    def test_reopening_drops_the_pending_reversal(self):
        from apps.accounting.services.approval_service import reopen_payroll

        payroll = approve_payroll(self.calc(FIRST), self.director)
        self.cancel_last_lesson()
        reopen_payroll(payroll, self.director, "уроки исправлены")
        self.accrual.refresh_from_db()
        self.assertEqual(self.accrual.status, Status.CANCELLED)
        self.assertEqual(self.accrual.adjustment.status, PayrollAdjustment.Status.VOID)
        self.assertEqual(self.calc(FIRST).total_accrued, D("0"))
        self.assertFalse(Payroll.objects.get(pk=payroll.pk).adjustments.filter(status="APPLIED").exists())
