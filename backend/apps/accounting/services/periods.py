"""Расчётные периоды: 1–15 и 16–последний день месяца."""
from __future__ import annotations

from django.db import IntegrityError, transaction

from ..models import Payroll, PayrollPeriod
from . import AccountingError, audit


def get_or_create_period(year: int, month: int, period_type: str, actor) -> tuple[PayrollPeriod, bool]:
    if period_type not in PayrollPeriod.PeriodType.values:
        raise AccountingError("Неизвестный тип периода.")
    if not 1 <= month <= 12:
        raise AccountingError("Месяц должен быть от 1 до 12.")
    existing = PayrollPeriod.objects.filter(year=year, month=month, period_type=period_type).first()
    if existing:
        return existing, False
    try:
        with transaction.atomic():
            period = PayrollPeriod.objects.create(year=year, month=month, period_type=period_type, created_by=actor)
    except IntegrityError:
        return PayrollPeriod.objects.get(year=year, month=month, period_type=period_type), False
    audit.log(actor, period, "create", new={"year": year, "month": month, "period_type": period_type})
    return period, True


def sync_period_status(period: PayrollPeriod) -> None:
    """Период «Утверждён», когда утверждены все его расчёты (кроме аннулированных)."""
    if period.status == PayrollPeriod.Status.CLOSED:
        return
    payrolls = period.payrolls.exclude(status=Payroll.Status.VOID)
    if not payrolls.exists():
        return
    all_locked = not payrolls.exclude(status__in=Payroll.LOCKED_STATUSES).exists()
    target = PayrollPeriod.Status.APPROVED if all_locked else PayrollPeriod.Status.CALCULATED
    if period.status != target:
        period.status = target
        period.save(update_fields=["status"])


def close_period(period: PayrollPeriod, actor, reason: str = "") -> PayrollPeriod:
    with transaction.atomic():
        period = PayrollPeriod.objects.select_for_update().get(pk=period.pk)
        if period.status == PayrollPeriod.Status.CLOSED:
            raise AccountingError("Период уже закрыт.")
        open_rows = period.payrolls.exclude(status__in=(Payroll.Status.PAID, Payroll.Status.VOID))
        if open_rows.exists():
            raise AccountingError(
                "Закрыть можно только период, где все расчёты выплачены или аннулированы "
                f"(не завершено: {open_rows.count()})."
            )
        old = {"status": period.status}
        period.status = PayrollPeriod.Status.CLOSED
        period.save(update_fields=["status"])
        audit.log(actor, period, "close", old=old, new={"status": period.status}, reason=reason)
    return period
