"""Ежедневные проверки оплаты обучения без Celery (cron хостинга):

    python manage.py billing_autorun [--date 2026-10-21] [--no-report]

Только задачи оплаты обучения (`billing.run_daily`) — через ту же аренду, что
`run_scheduled_tasks`: два запуска одновременно не выполнят проверки дважды.
Для Railway Cron используйте `run_scheduled_tasks` (ещё и посещаемость
сотрудников). Сбой хотя бы одной проверки — код выхода 1.
"""
import datetime as dt
import json
import sys

from django.core.management.base import BaseCommand

from apps.billing.services.scheduler import run_all


class Command(BaseCommand):
    help = "Списание уроков, следующие начисления, просрочки, напоминания и отчёт оплаты обучения."

    def add_arguments(self, parser):
        parser.add_argument("--date", type=dt.date.fromisoformat, default=None)
        parser.add_argument("--no-report", action="store_true")

    def handle(self, *args, **options):
        summary = run_all(on=options["date"], report=not options["no_report"], staff_attendance=False)
        self.stdout.write(json.dumps({"status": summary["status"], **summary["tasks"]}, ensure_ascii=False,
                                     indent=2, default=str))
        if summary["failed"]:
            sys.exit(1)
