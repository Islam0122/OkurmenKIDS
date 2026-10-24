"""Проверка исторических периодов начислений.

По умолчанию только показывает (ничего не меняет): начисления, период
которых, вероятно, записан днём оформления договора, а не его началом
(договор оформлен в октябре задним числом с сентября — до появления
`Invoice.period_date`). У каждой строки — основание; неоднозначные
(`ambiguous`) — для ручной проверки бухгалтером.

`--apply` исправляет ТОЛЬКО строки с проверяемым основанием (начало договора
и первый засчитанный урок — в одном месяце): меняется лишь `period_date`,
суммы, оплаты, даты выставления и создания не трогаются; каждое исправление
— в журнале аудита (`billing_invoice_period`). Повторный запуск ничего не
меняет. Можно ограничить списком: `--invoice 12 --invoice 15`."""
import json

from django.core.management.base import BaseCommand

from apps.billing.services.periods import apply_period_review, period_review


class Command(BaseCommand):
    help = "Список начислений с сомнительным периодом; --apply — исправить те, у которых есть основание (с аудитом)."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true", help="Исправить строки с проверяемым основанием.")
        parser.add_argument("--invoice", type=int, action="append", help="Только эти начисления (id).")

    def handle(self, *args, **options):
        rows = period_review()
        if options["invoice"]:
            rows = [r for r in rows if r["invoice"] in options["invoice"]]
        report = {
            "total": len(rows),
            "with_basis": [r for r in rows if r["proposed"]],
            "manual_review": [r for r in rows if r["ambiguous"]],
        }
        if options["apply"]:
            changed = apply_period_review(invoice_ids=options["invoice"])
            report["applied"] = [{"invoice": r["invoice"], "from": r["period_date"], "to": r["proposed"]} for r in changed]
        self.stdout.write(json.dumps(report, ensure_ascii=False, indent=2, default=str))
