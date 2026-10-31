"""Периодические задачи операционного модуля вручную или по cron:

    python manage.py run_operations

Повторные задачи, напоминания о дедлайнах, поиск проблем, доставка
уведомлений. Повторный запуск безопасен (идемпотентно)."""
import json

from django.core.management.base import BaseCommand

from apps.operations.services.scheduler import run_periodic


class Command(BaseCommand):
    help = "Операционный модуль: повторяющиеся задачи, напоминания, проблемы, уведомления."

    def handle(self, *args, **options):
        self.stdout.write(json.dumps(run_periodic(), ensure_ascii=False, default=str))
