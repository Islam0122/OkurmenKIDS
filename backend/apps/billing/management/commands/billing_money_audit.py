"""Аудит денег договоров оплаты обучения (по умолчанию — только чтение).

Показывает по договору все платежи (дата денег и дата записи, кто принял,
распределено, аванс, чек), все начисления (включая аннулированные — видно,
какое чем заменено), распределения (включая сторнированные), журнал аванса,
сводку карточки и несогласованности: свободный аванс рядом с неоплаченным
начислением, одинаковые суммы (возможный повтор регистрации), чек не той
операции, начислено больше стоимости курса, предоплата курса вместе с
начислениями месяцев, уроки приоритетного предмета до начала договора.

    manage.py billing_money_audit --receipt OK-2026-000005 --receipt OK-2026-000008 \\
                                  --invoice INV-2026-000081 --invoice INV-2026-000083
    manage.py billing_money_audit --student "Абдыбеков Бекнур"
    manage.py billing_money_audit                   # все договоры с проблемами

Исправления — только явно и только после подтверждения (`--confirm`; без
него — dry-run: что будет сделано, без записи):

    --apply                       распределить свободный аванс на неоплаченные
                                  начисления (credit_unapplied), корректирующая
                                  операция с аудитом;
    --reverse-payment ID --reason ТЕКСТ
                                  сторно платежа, зарегистрированного повторно
                                  (распределения сторнируются, платёж и чек —
                                  «Отменён / Аннулирован», записи не удаляются).
"""
import json

from django.core.management.base import BaseCommand, CommandError

from apps.accounting.models import StudentPayment
from apps.billing.services import BillingError
from apps.billing.services.money_audit import apply_safe_fixes, find_profiles, lookup_numbers, profile_money_audit


class Command(BaseCommand):
    help = "Аудит денег договоров; исправления — только с --confirm (иначе dry-run)."

    def add_arguments(self, parser):
        parser.add_argument("--profile", type=int)
        parser.add_argument("--student", help="Часть фамилии / имени студента.")
        parser.add_argument("--receipt", action="append", help="Номер чека (можно несколько).")
        parser.add_argument("--invoice", action="append", help="Номер начисления (можно несколько).")
        parser.add_argument("--apply", action="store_true", help="Распределить свободный аванс (credit_unapplied).")
        parser.add_argument("--reverse-payment", type=int, help="id платежа, зарегистрированного повторно.")
        parser.add_argument("--reason", default="", help="Основание сторно.")
        parser.add_argument("--confirm", action="store_true", help="Записать изменения (без флага — dry-run).")

    def handle(self, *args, **o):
        output = {"dry_run": not o["confirm"]}
        if o["reverse_payment"]:
            output["reverse_payment"] = self._reverse(o)
        targeted = bool(o["profile"] or o["student"] or o["receipt"] or o["invoice"])
        if o["receipt"] or o["invoice"]:
            output["lookup"] = lookup_numbers(receipts=o["receipt"], invoices=o["invoice"])
        results = []
        for profile in find_profiles(profile_id=o["profile"], student=o["student"], receipts=o["receipt"],
                                     invoices=o["invoice"]):
            report = profile_money_audit(profile)
            if not targeted and not report["problems"]:
                continue
            fixable = [p for p in report["problems"] if p["fix"] == "apply_credit"]
            if o["apply"] and fixable:
                if o["confirm"]:
                    report["applied"] = apply_safe_fixes(profile)
                    report["after"] = profile_money_audit(profile)["summary"]
                else:
                    report["would_apply"] = fixable
            results.append(report)
        output.update({"profiles": len(results), "results": results})
        self.stdout.write(json.dumps(output, ensure_ascii=False, indent=2, default=str))

    def _reverse(self, o) -> dict:
        from apps.billing.services.payments import reverse_payment

        payment = StudentPayment.objects.filter(pk=o["reverse_payment"], billing_profile__isnull=False).first()
        if payment is None:
            raise CommandError("Платёж оплаты обучения не найден.")
        if not o["reason"].strip():
            raise CommandError("Укажите --reason: на каком основании платёж считается повторной регистрацией.")
        plan = {"payment": payment.pk, "amount": str(payment.amount), "received_date": str(payment.received_date),
                "status": payment.status, "allocations": list(payment.billing_allocations.filter(status="ACTIVE")
                                                              .values_list("invoice__number", "amount"))}
        if not o["confirm"]:
            return {**plan, "would_reverse": True}
        try:
            reverse_payment(payment, actor=None, reason=f"Аудит: {o['reason'].strip()}", system=True)
        except BillingError as exc:
            raise CommandError(exc.message)
        payment.refresh_from_db()
        return {**plan, "reversed": True, "status_after": payment.status}
