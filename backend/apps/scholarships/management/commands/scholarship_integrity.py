"""Check scholarship awards against the money rules (migration 0006/0007).

    python manage.py scholarship_integrity                            # report only
    python manage.py scholarship_integrity --fix-unpaid-null-amounts  # the one safe fix

Read-only by default. The only change it can make — and only when asked —
is giving an *unpaid* award without an amount (NULL, «стипендия без
денежной суммы») the amount 0, which means exactly that now. Paid awards
and every other problem are listed for a person to decide.

Works before the migrations are applied too (reads only pre-0006 columns).
"""
from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.scholarships.models import ScholarshipAward
from apps.scholarships.services.integrity import describe, find_conflicts


class Command(BaseCommand):
    help = "Проверить стипендии на нарушения правил сумм и выплат (ничего не меняет без флага)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--fix-unpaid-null-amounts", action="store_true",
            help="Невыданным стипендиям без суммы (NULL) поставить сумму 0. Больше ничего не меняет.",
        )

    def handle(self, *args, **options):
        conflicts = find_conflicts(ScholarshipAward)
        if not conflicts:
            self.stdout.write(self.style.SUCCESS("Нарушений нет — миграции можно применять."))
            return
        self.stdout.write(self.style.WARNING(f"Стипендий с нарушениями: {len(conflicts)}"))
        self.stdout.write(describe(conflicts))
        if not options["fix_unpaid_null_amounts"]:
            return

        fixable = [row["pk"] for row in conflicts if row["problems"] == ["amount_null"] and row["payment_status"] == "unpaid"]
        with transaction.atomic():
            fixed = ScholarshipAward.objects.filter(pk__in=fixable, amount__isnull=True, payment_status="unpaid").update(amount=0)
        self.stdout.write(self.style.SUCCESS(f"Невыданным стипендиям без суммы поставлено 0: {fixed}"))
        remaining = find_conflicts(ScholarshipAward)
        if remaining:
            self.stdout.write(self.style.WARNING(f"Осталось исправить вручную: {len(remaining)}"))
            self.stdout.write(describe(remaining))
        else:
            self.stdout.write(self.style.SUCCESS("Нарушений больше нет — миграции можно применять."))
