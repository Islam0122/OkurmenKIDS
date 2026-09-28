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

        result = mock.seed_mock_data()
        if result.payer is None:
            self.stdout.write(self.style.WARNING(
                "Нет администратора — «Выдал» у выплат пустой. Создайте superuser и запустите команду снова."
            ))
        self._report(result)

    def _report(self, result):
        stats = mock.statistics(result.periods)
        t = stats["totals"]
        out = self.stdout.write
        out("")
        out(LINE)
        out("SCHOLARSHIP MOCK DATA")
        out(LINE)
        out("")
        for label, value in (
            ("Periods created:", len(result.periods)),
            ("Groups used:", len(result.groups)),
            ("Students used:", result.students),
            ("Scholarships:", t["total"]),
            ("", ""),
            ("Paid:", t["paid"]),
            ("Pending:", t["pending"]),
            ("Cash / bank:", f"{t['cash']} / {t['bank']}"),
            ("", ""),
            ("Total amount:", som(t["accrued"] or 0)),
            ("Paid amount:", som(t["paid_sum"] or 0)),
            ("Remaining:", som(t["remaining"] or 0)),
            ("", ""),
            ("Paid by:", str(result.payer) if result.payer else "—"),
        ):
            out(f"{label:<18}{value!s:>18}" if label else "")
        out("")
        out(LINE)
        out("PERIODS")
        out(LINE)
        out("")
        for period, agg in stats["rows"]:
            dates = f"{period.period_start:%d.%m} — {period.period_end:%d.%m}"
            of = agg["total"] if agg["total"] else period.max_recipients
            state = "" if period.status == period.Status.APPROVED else "  (не утверждён)"
            out(f"{dates}   {agg['paid']:>2} / {of:<2} paid   {som(agg['paid_sum'] or 0):>12} из {som(agg['accrued'] or 0)}{state}")
        out("")
        out(LINE)
        for reason in result.skipped:
            self.stdout.write(self.style.WARNING(reason))
