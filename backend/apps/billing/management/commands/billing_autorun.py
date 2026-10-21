"""Ежедневные проверки оплаты обучения без Celery (cron хостинга):

    python manage.py billing_autorun [--date 2026-10-21] [--no-report]

Тот же набор, что `billing.run_daily` в Celery Beat. Повторный запуск
ничего не дублирует.
"""
import datetime as dt
import json

from django.core.management.base import BaseCommand

from apps.billing.tasks import run_daily


class Command(BaseCommand):
    help = "Списание уроков, следующие начисления, просрочки, напоминания и отчёт оплаты обучения."

    def add_arguments(self, parser):
        parser.add_argument("--date", type=dt.date.fromisoformat, default=None)
        parser.add_argument("--no-report", action="store_true")

    def handle(self, *args, **options):
        result = run_daily(on=options["date"], report=not options["no_report"])
        self.stdout.write(json.dumps(result, ensure_ascii=False, indent=2, default=str))
