"""Разбор «Остатка предоплаты» по договору до исходных записей (только чтение).

    manage.py billing_prepayment_audit --profile 123
    manage.py billing_prepayment_audit --student "Фамилия"
    manage.py billing_prepayment_audit --all          # все строки страницы, только с замечаниями

Вывод — JSON: строка страницы, сводка договора, платежи (с возвратами и сторно),
начисления с действующими и сторнированными распределениями, журнал аванса по
видам, другие договоры ученика и замечания. Данные не меняются.
"""
import json

from django.core.management.base import BaseCommand, CommandError

from apps.billing.models import StudentBillingProfile
from apps.billing.services.prepayment_audit import explain


class Command(BaseCommand):
    help = "Разбор остатка предоплаты по договору (только чтение)."

    def add_arguments(self, parser):
        parser.add_argument("--profile", type=int)
        parser.add_argument("--student", help="Часть фамилии / имени.")
        parser.add_argument("--all", action="store_true", help="Все договоры; вывести только с замечаниями.")

    def handle(self, *args, **o):
        qs = StudentBillingProfile.objects.select_related("student", "plan")
        if o["profile"]:
            qs = qs.filter(pk=o["profile"])
        elif o["student"]:
            for part in o["student"].split():
                qs = qs.filter(student__last_name__icontains=part) | qs.filter(student__first_name__icontains=part)
        elif not o["all"]:
            raise CommandError("Укажите --profile, --student или --all.")
        results = [explain(p) for p in qs.order_by("pk")]
        if o["all"]:
            results = [r for r in results if r["findings"]]
        self.stdout.write(json.dumps(results, ensure_ascii=False, indent=2))
