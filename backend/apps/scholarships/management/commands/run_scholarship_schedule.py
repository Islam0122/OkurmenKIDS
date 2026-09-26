"""Generate every due scholarship cycle — meant to run once a day from cron
(this project has no Celery/beat; see docs/scholarships.md → «Автоматизация»).

    python manage.py run_scholarship_schedule            # today (Asia/Bishkek)
    python manage.py run_scholarship_schedule --date 2026-10-01

Idempotent: already generated periods are skipped, so running it daily (or
twice) never creates duplicates, and a missed day is caught up on the next.
"""
from __future__ import annotations

import datetime as dt

from django.core.management.base import BaseCommand, CommandError

from apps.scholarships.services.generation import ScholarshipError, run_schedule


class Command(BaseCommand):
    help = "Сформировать стипендиальные рейтинги для всех наступивших циклов (идемпотентно)."

    def add_arguments(self, parser):
        parser.add_argument("--date", type=dt.date.fromisoformat, default=None, help="Дата запуска (YYYY-MM-DD).")

    def handle(self, *args, date=None, **options):
        try:
            results = run_schedule(today=date)
        except ScholarshipError as exc:
            raise CommandError("; ".join(exc.messages)) from exc
        for result in results:
            verb = "сформирован" if result.created else "уже существует"
            self.stdout.write(f"{result.period}: {verb} (статус: {result.period.get_status_display()})")
