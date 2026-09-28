"""MOCK data for testing scholarship payments and the accounting report.

    python manage.py seed_scholarships            # create / refresh mock data
    python manage.py seed_scholarships --clear    # delete all mock data, then create it again
    python manage.py seed_scholarships --remove   # delete all mock data and exit

Idempotent: a second run rebuilds the same 8 periods in place, with no
duplicates. Only rows carrying the mock marker are ever changed or
deleted (see apps/scholarships/demo/mock_payments.py). Refuses to run
with DJANGO_ENV=production.
"""
from __future__ import annotations

import os

from django.core.management.base import BaseCommand, CommandError

from apps.scholarships.demo import mock_payments as mock
from apps.scholarships.templatetags.scholarship_tags import som

LINE = "=" * 44


class Command(BaseCommand):
    help = "Создать mock-данные стипендий (периоды, стипендиаты, выплаты) для проверки UI и отчётов."

    def add_arguments(self, parser):
        parser.add_argument("--clear", action="store_true", help="Удалить все mock-данные и создать заново.")
        parser.add_argument("--remove", action="store_true", help="Только удалить mock-данные.")

    def handle(self, *args, **options):
        if os.environ.get("DJANGO_ENV", "development") == "production":
            raise CommandError("DJANGO_ENV=production — mock-данные в production не создаются и не удаляются.")

        if options["clear"] or options["remove"]:
            try:
                counts = mock.clear_mock_data()
            except ValueError as exc:
                raise CommandError(str(exc)) from exc
            self.stdout.write("Удалено (только mock-данные):")
            for label, count in counts.items():
                self.stdout.write(f"  {label:<26}{count:>6}")
            if options["remove"]:
                return

        try:
            result = mock.seed_mock_data()
        except mock.NoPayer as exc:
            raise CommandError(str(exc)) from exc
        self._report(result)

    def _report(self, result):
        try:
            overall = mock.verify_finances(result.checks)
        except mock.FinanceMismatch as exc:
            raise CommandError(f"Проверка сумм не прошла: {exc}") from exc
        out = self.stdout.write
        out("")
        out(LINE)
        out("SCHOLARSHIP MOCK FINANCIAL DATA")
        out(LINE)
        for label, value in (
            ("Periods:", len(result.periods)),
            ("Groups used:", len(result.groups)),
            ("Students used:", result.students),
            (None, None),
            ("Total awards:", overall["awards"]),
            ("Total amount:", kgs(overall["total"])),
            (None, None),
            ("Paid awards:", overall["paid"]),
            ("Paid amount:", kgs(overall["paid_amount"])),
            (None, None),
            ("Pending awards:", overall["pending"]),
            ("Pending amount:", kgs(overall["pending_amount"])),
            (None, None),
            ("Balance:", kgs(overall["balance"])),
            ("Cash / bank:", f"{overall['cash']} / {overall['bank']}"),
            ("Paid by:", str(result.payer) if result.payer else "—"),
        ):
            out(f"{label:<18}{value!s:>22}" if label else "")
        out("")
        out(LINE)
        out("PERIODS")
        out(LINE)
        for check in result.checks:
            f, period = check.figures, check.period
            state = "" if period.status == period.Status.APPROVED else " · не утверждён"
            out("")
            out(f"{period.period_start:%d.%m} — {period.period_end:%d.%m}   {check.plan.scenario}{state}")
            out(f"  Awards:  {f['awards']:<4} Total:           {kgs(f['total']):>16}")
            out(f"  Paid:    {f['paid']:<4} Paid amount:     {kgs(f['paid_amount']):>16}")
            out(f"  Pending: {f['pending']:<4} Pending amount:  {kgs(f['pending_amount']):>16}")
            out(f"                Remaining:       {kgs(f['balance']):>16}")
        out("")
        out(LINE)
        out(self.style.SUCCESS(
            "✓ Суммы сверены: построчный пересчёт = план = итоги «Стипендии» = отчёт бухгалтерии (Excel/PDF)."
        ))
        for reason in result.skipped:
            self.stdout.write(self.style.WARNING(reason))


def kgs(value) -> str:
    return som(value or 0).replace("сом", "KGS")
