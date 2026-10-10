"""Выплаты сотрудникам: полные, частичные, авансы; отмена с причиной.

Остаток = утверждённое начисление + применённые корректировки −
подтверждённые выплаты (корректировки уже входят в сумму к выплате и
второй раз не прибавляются).
"""
from __future__ import annotations

import datetime as dt
from decimal import Decimal

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from ..models import Payroll, PayrollPayment
from . import AccountingError, audit
from .approval_service import TOTALS, _locked, _require_reason, paid_status
from .payroll_calculator import refresh_totals


def overpayment_allowed() -> bool:
    return bool(getattr(settings, "ACCOUNTING_ALLOW_OVERPAYMENT", False))


def register_payment(
    payroll: Payroll,
    *,
    amount: Decimal,
    payment_date: dt.date,
    actor,
    payment_method: str = PayrollPayment.Method.BANK,
    reference: str = "",
    comment: str = "",
    is_advance: bool = False,
    idempotency_key: str | None = None,
) -> tuple[PayrollPayment, bool]:
    """Зарегистрировать выплату. Возвращает (выплата, создана ли новая).

    Повторный запрос с тем же ключом идемпотентности возвращает уже
    созданную выплату, а не вторую такую же."""
    amount = Decimal(amount)
    key = (idempotency_key or "").strip() or None
    if key:
        existing = PayrollPayment.objects.filter(idempotency_key=key).first()
        if existing:
            if existing.payroll_id != payroll.pk or existing.amount != amount:
                raise AccountingError("Ключ запроса уже использован для другой выплаты.", code="idempotency_conflict")
            return existing, False
    if amount <= 0:
        raise AccountingError("Сумма выплаты должна быть больше нуля.", code="invalid_amount")
    if payment_method not in PayrollPayment.Method.values:
        raise AccountingError("Неизвестный способ выплаты.")
    try:
        with transaction.atomic():
            payroll = _locked(payroll)
            if payroll.employee_id == actor.pk:
                raise AccountingError("Нельзя регистрировать выплату самому себе.", code="own_payroll")
            if payroll.status not in (Payroll.Status.APPROVED, Payroll.Status.PARTIALLY_PAID, Payroll.Status.PAID):
                raise AccountingError("Выплата возможна только по утверждённому начислению.", code="not_approved")
            refresh_totals(payroll)
            if amount > payroll.amount_due and not overpayment_allowed():
                raise AccountingError(
                    f"Сумма выплаты {amount} сом больше остатка {payroll.amount_due} сом.", code="exceeds_due",
                )
            reference = reference.strip()
            if reference and payroll.payments.filter(
                status=PayrollPayment.Status.CONFIRMED, reference=reference,
            ).exists():
                raise AccountingError("Выплата с таким номером документа уже зарегистрирована.", code="duplicate")
            old = audit.snapshot(payroll, TOTALS)
            payment = PayrollPayment.objects.create(
                payroll=payroll, amount=amount, payment_date=payment_date, payment_method=payment_method,
                reference=reference, comment=comment, is_advance=is_advance, idempotency_key=key, created_by=actor,
            )
            refresh_totals(payroll)
            payroll.status = paid_status(payroll)
            payroll.save()
            audit.log(actor, payment, "create", old=old, new={
                "amount": amount, "payment_date": payment_date, "method": payment_method, "reference": reference,
                "is_advance": is_advance, **audit.snapshot(payroll, TOTALS),
            }, payroll=payroll)
    except IntegrityError:
        # Тот же ключ идемпотентности пришёл параллельно — отдаём ту выплату.
        if key:
            return PayrollPayment.objects.get(idempotency_key=key), False
        raise
    return payment, True


def void_payment(payment: PayrollPayment, *, actor, reason: str) -> PayrollPayment:
    reason = _require_reason(reason)
    with transaction.atomic():
        payroll = _locked(payment.payroll)
        payment = PayrollPayment.objects.select_for_update().get(pk=payment.pk)
        if payment.status == PayrollPayment.Status.VOID:
            raise AccountingError("Выплата уже отменена.", code="bad_status")
        old = audit.snapshot(payroll, TOTALS)
        payment.status = PayrollPayment.Status.VOID
        payment.void_reason = reason
        payment.voided_by, payment.voided_at = actor, timezone.now()
        payment.save()
        refresh_totals(payroll)
        payroll.status = paid_status(payroll)
        payroll.save()
        audit.log(actor, payment, "void", old=old, new=audit.snapshot(payroll, TOTALS), reason=reason, payroll=payroll)
    return payment
