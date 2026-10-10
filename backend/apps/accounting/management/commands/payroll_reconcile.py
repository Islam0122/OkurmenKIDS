"""Сверка финансовых данных бухгалтерии (только чтение):

    python manage.py payroll_reconcile [--json]

Код выхода 1 — если найдены расхождения итогов или противоречивые записи.
Запускайте до и после `migrate` на staging, затем на production.
"""
import json
import sys

from django.core.management.base import BaseCommand

from apps.accounting.services import reconcile


class Command(BaseCommand):
    help = "Сверка начислений, выплат, циклов и тарифов; отчёт о несопоставленных данных."

    def add_arguments(self, parser):
        parser.add_argument("--json", action="store_true")

    def handle(self, *args, **options):
        report = reconcile.run()
        if options["json"]:
            self.stdout.write(json.dumps(report, ensure_ascii=False, indent=2, default=str))
        else:
            for key, value in report.items():
                if isinstance(value, list):
                    self.stdout.write(f"{key}: {len(value)}")
                    for item in value[:20]:
                        self.stdout.write(f"    {item}")
                else:
                    self.stdout.write(f"{key}: {value}")
        problems = reconcile.problems_count(report)
        self.stdout.write(f"Расхождений: {problems}")
        if problems:
            sys.exit(1)
