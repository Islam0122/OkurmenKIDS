"""Снимки «Общей статистики» вручную:

    python manage.py capture_performance_snapshots                 # как планировщик: сегодня + прошлые дни
    python manage.py capture_performance_snapshots --backfill-from 2026-11-01

`--backfill-from` создаёт снимки для дней без снимка (до вчера включительно):
посещаемость и ДЗ — по записям, количество групп и студентов — неизвестно
(пусто), т. к. состояние прошлых дней не восстанавливается задним числом.
Существующие снимки не меняются; повторный запуск безопасен.
"""
import datetime as dt
import json

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.performance.services.snapshots import backfill, capture


class Command(BaseCommand):
    help = "Ежедневные снимки общей статистики академии."

    def add_arguments(self, parser):
        parser.add_argument("--backfill-from", type=dt.date.fromisoformat, default=None,
                            help="Заполнить пропущенные дни начиная с даты (ГГГГ-ММ-ДД).")

    def handle(self, *args, **options):
        result = {}
        if options["backfill_from"]:
            result["backfilled"] = backfill(options["backfill_from"], timezone.localdate())
        result.update(capture())
        self.stdout.write(json.dumps(result, ensure_ascii=False))
