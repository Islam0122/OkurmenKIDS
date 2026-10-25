"""Периодические задачи для Railway Cron (`run_scheduled_tasks`) и Beat
(`billing.run_daily`): один запуск за раз (аренда в базе), истёкшая аренда
перехватывается, повтор не дублирует финансовые записи, отчёт раз в сутки,
сбой задачи — код выхода 1 (остальные выполняются), миграции не применены —
пропуск, посещаемость сотрудников закрывается."""
from __future__ import annotations

import datetime as dt
import json
import uuid
from io import StringIO
from unittest import mock

from django.core.management import call_command
from django.utils import timezone

from apps.billing.models import (
    BillingEvent,
    BillingNotification,
    BillingTask,
    Invoice,
    LessonConsumption,
    LessonPackage,
)
from apps.billing.services import scheduler
from apps.billing.tasks import run_daily
from apps.billing.tests.base import BillingFixture


def run_command(*args) -> tuple[dict, int]:
    out = StringIO()
    try:
        call_command("run_scheduled_tasks", *args, stdout=out, stderr=StringIO())
        code = 0
    except SystemExit as exc:
        code = exc.code
    return json.loads(out.getvalue().strip().splitlines()[-1]), code


class SchedulerTests(BillingFixture):
    def snapshot(self):
        return (Invoice.objects.count(), list(Invoice.objects.order_by("pk").values_list("status", "amount_paid")),
                LessonConsumption.objects.count(), LessonPackage.objects.count(), BillingNotification.objects.count(),
                BillingTask.objects.count())

    def test_runs_all_tasks_and_repeat_does_not_duplicate(self):
        profile = self.profile()
        self.lesson(day=self.today - dt.timedelta(days=2))  # проведён, сигнал «не дошёл»
        summary, code = run_command()
        self.assertEqual((summary["status"], summary["failed"], code), ("done", False, 0))
        for name in ("process_completed_lessons", "mark_overdue_invoices", "apply_credit_to_due_invoices",
                     "notify_accountants", "build_financial_report", "staff_attendance_close_stale"):
            self.assertIn(name, summary["tasks"])
        self.assertEqual(summary["tasks"]["process_completed_lessons"]["consumed"], 1)
        before = self.snapshot()
        again, code = run_command()
        self.assertEqual((again["status"], code), ("done", 0))
        self.assertEqual(self.snapshot(), before)  # повтор — без новых списаний, начислений, уведомлений
        self.assertNotIn("build_financial_report", again["tasks"])  # отчёт уже построен сегодня
        lock = BillingEvent.objects.get(key=scheduler.LOCK_KEY)
        self.assertEqual(lock.status, BillingEvent.Status.DONE)
        self.assertTrue(profile.invoices.exists())

    def test_concurrent_run_is_skipped_and_stale_lease_is_taken_over(self):
        other = uuid.uuid4()
        self.assertTrue(scheduler.acquire(other))  # «первый» запуск ещё работает
        with mock.patch("apps.billing.tasks.run_daily_tasks") as daily:
            summary, code = run_command()
        self.assertEqual((summary["status"], code), ("skipped_locked", 0))
        daily.assert_not_called()
        # Процесс упал, аренда не снята: через LEASE её перехватывает следующий запуск.
        BillingEvent.objects.filter(key=scheduler.LOCK_KEY).update(
            updated_at=timezone.now() - scheduler.LEASE - dt.timedelta(minutes=1))
        summary, code = run_command("--no-report")
        self.assertEqual((summary["status"], code), ("done", 0))

    def test_beat_and_cron_share_the_lease(self):
        self.assertTrue(scheduler.acquire(uuid.uuid4()))  # cron работает
        with mock.patch("apps.billing.tasks.run_daily_tasks") as daily:
            self.assertEqual(run_daily(report=False)["status"], "skipped_locked")
        daily.assert_not_called()

    def test_failed_task_gives_exit_code_1_and_others_still_run(self):
        self.profile()
        with mock.patch("apps.billing.services.invoices.mark_overdue_invoices", side_effect=RuntimeError("boom")):
            summary, code = run_command("--no-report")
        self.assertEqual(code, 1)
        self.assertTrue(summary["failed"])
        self.assertEqual(summary["tasks"]["mark_overdue_invoices"], {"error": "boom"})
        self.assertIn("notify_accountants", summary["tasks"])  # следующие задачи выполнены
        lock = BillingEvent.objects.get(key=scheduler.LOCK_KEY)
        self.assertEqual((lock.status, lock.error), (BillingEvent.Status.FAILED, "mark_overdue_invoices"))
        summary, code = run_command("--no-report")  # аренда снята — следующий запуск идёт
        self.assertEqual((summary["status"], code), ("done", 0))

    def test_pending_migrations_skip_the_run(self):
        with mock.patch.object(scheduler, "pending_migrations", return_value=["billing.0099_new"]), \
                mock.patch("apps.billing.tasks.run_daily_tasks") as daily:
            summary, code = run_command()
        self.assertEqual((summary["status"], summary["pending"], code), ("skipped_migrations", ["billing.0099_new"], 0))
        daily.assert_not_called()
        self.assertEqual(scheduler.pending_migrations(), [])  # в тестовой базе всё применено

    def test_billing_autorun_still_works_without_staff_attendance(self):
        out = StringIO()
        call_command("billing_autorun", "--no-report", stdout=out)
        result = json.loads(out.getvalue())
        self.assertEqual(result["status"], "done")
        self.assertIn("mark_overdue_invoices", result)
        self.assertNotIn("staff_attendance_close_stale", result)
