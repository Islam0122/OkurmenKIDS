"""Отчёт о переходе на договоры по программам (только чтение).

Запускать до и после `migrate`: количества записей и суммы денег не должны
измениться (миграции добавляют поля и чеки, но не создают, не удаляют и не
пересчитывают платежи и начисления). Показывает, что нельзя перевести
автоматически: старые профили без программы с продолжительностью остаются
по пакетам уроков (срок оплаты — по дате), их переводит бухгалтер, оформив
новый договор."""
import json

from django.core.management.base import BaseCommand
from django.db.models import Count, Sum

from apps.accounting.models import StudentPayment
from apps.billing.models import Invoice, PaymentAllocation, Receipt, StudentBillingProfile
from apps.billing.services.reports import reconcile


def _s(value):
    return str(value or 0)


class Command(BaseCommand):
    help = "Количества и суммы финансовых данных оплаты обучения + записи, требующие ручного перевода."

    def handle(self, *args, **options):
        payments = StudentPayment.objects.filter(billing_profile__isnull=False)
        confirmed = payments.filter(status=StudentPayment.Status.CONFIRMED)
        report = {
            "profiles": StudentBillingProfile.objects.count(),
            "contracts_by_program": StudentBillingProfile.objects.filter(duration_months__isnull=False).count(),
            "legacy_profiles_without_program": list(
                StudentBillingProfile.objects.filter(duration_months__isnull=True)
                .exclude(status__in=StudentBillingProfile.CLOSED_STATUSES)
                .values("pk", "student__last_name", "student__first_name", "plan__name")[:500]
            ),
            "payments": payments.count(),
            "payments_received_sum": _s(confirmed.filter(kind="payment").aggregate(s=Sum("amount"))["s"]),
            "refunds_sum": _s(confirmed.filter(kind="refund").aggregate(s=Sum("amount"))["s"]),
            "payments_without_receipt": payments.exclude(pk__in=Receipt.objects.values("payment_id")).count(),
            "receipts": Receipt.objects.count(),
            "invoices": dict(Invoice.objects.values_list("status").annotate(n=Count("pk")).order_by()),
            "invoices_amount_sum": _s(Invoice.objects.exclude(status="VOID").aggregate(s=Sum("amount"))["s"]),
            "allocations_active_sum": _s(PaymentAllocation.objects.filter(status="ACTIVE").aggregate(s=Sum("amount"))["s"]),
            "reconcile_problems": reconcile(),
        }
        self.stdout.write(json.dumps(report, ensure_ascii=False, indent=2, default=str))
