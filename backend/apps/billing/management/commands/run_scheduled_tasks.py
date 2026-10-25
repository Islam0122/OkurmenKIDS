"""Все периодические задачи LMS одним запуском — для Railway Cron (без Celery):

    python manage.py run_scheduled_tasks [--date 2026-10-21] [--no-report] [--no-staff-attendance]

Что запускается и как защищено от повторов — `apps.billing.services.scheduler`.
Один запуск за раз (аренда в базе): если предыдущий ещё работает — выход 0
без действий («skipped_locked»); миграции не применены — тоже выход 0
(«skipped_migrations»). Сбой хотя бы одной задачи — код выхода 1 (виден в
Railway как неуспешный запуск), остальные задачи при этом выполняются; в базе
нет таблицы миграций (не та база, не задан `DJANGO_ENV`) — код 1 («no_schema»).
Перед выходом соединения с базой закрываются (Railway Cron ждёт завершения
процесса).
Итог — одна строка JSON в stdout (логи Railway)."""
import datetime as dt
import json
import sys

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import connections

from apps.billing.services.scheduler import run_all


class Command(BaseCommand):
    help = "Периодические задачи (оплата обучения, посещаемость сотрудников) — один запуск для cron."

    def add_arguments(self, parser):
        parser.add_argument("--date", type=dt.date.fromisoformat, default=None,
                            help="Дата проверок (по умолчанию — сегодня по часовому поясу проекта).")
        parser.add_argument("--no-report", action="store_true", help="Не строить суточный снимок отчёта.")
        parser.add_argument("--no-staff-attendance", action="store_true",
                            help="Не закрывать открытые сессии посещаемости сотрудников.")

    def handle(self, *args, **options):
        if getattr(settings, "CELERY_BROKER_URL", ""):
            # Расписание должно быть одно: при брокере задачи может запускать Beat.
            self.stderr.write("WARNING: CELERY_BROKER_URL задан — если запущен Celery Beat, отключите один из "
                              "планировщиков (аренда не даст выполнить проверки дважды одновременно).")
        try:
            summary = run_all(on=options["date"], report=not options["no_report"],
                              staff_attendance=not options["no_staff_attendance"])
        finally:
            for connection in connections.all(initialized_only=True):
                if not connection.in_atomic_block:  # в тестах команда идёт внутри транзакции
                    connection.close()
        self.stdout.write(json.dumps(summary, ensure_ascii=False, default=str))
        if summary["failed"]:
            sys.exit(1)
