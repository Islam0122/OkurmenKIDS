"""Сверка оплаты обучения (только чтение). Код выхода 1 при расхождениях."""
import json
import sys

from django.core.management.base import BaseCommand

from apps.billing.services.reports import reconcile


class Command(BaseCommand):
    help = "Сверка: кеш начислений, аванс, счётчики пакетов."

    def handle(self, *args, **options):
        problems = reconcile()
        self.stdout.write(json.dumps({"problems": problems}, ensure_ascii=False, indent=2))
        if problems:
            sys.exit(1)
