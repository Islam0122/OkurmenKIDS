"""Платежи студентов и возвраты — исходные данные для процента тренера.

Платёж не редактируется и не удаляется: ошибочный отменяется с причиной
(в журнале остаются обе версии), новый вносится заново. Отменить платёж,
уже вошедший в утверждённое начисление, можно — но начисление от этого не
меняется (оно заморожено); бухгалтер видит предупреждение и при
необходимости оформляет корректировку.
"""
from __future__ import annotations

import datetime as dt
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.db.models import Sum
from django.utils import timezone

from apps.academy.models import Group, Student

from ..models import Payroll, PayrollLine, StudentPayment
from . import AccountingError, audit

FIELDS = ("kind", "amount", "received_date", "service_start", "service_end", "student", "group", "status")


def _refunded(payment: StudentPayment) -> Decimal:
    return payment.refunds.filter(status=StudentPayment.Status.CONFIRMED).aggregate(s=Sum("amount"))["s"] or Decimal("0")


def record_payment(
    *,
    student: Student,
    amount: Decimal,
    received_date: dt.date,
    actor,
    group: Group | None = None,
    service_start: dt.date | None = None,
    service_end: dt.date | None = None,
    method: str = StudentPayment.Method.CASH,
    reference: str = "",
    comment: str = "",
    refund_of: StudentPayment | None = None,
    idempotency_key: str | None = None,
) -> tuple[StudentPayment, bool]:
    amount = Decimal(amount)
    key = (idempotency_key or "").strip() or None
    if key:
        existing = StudentPayment.objects.filter(idempotency_key=key).first()
        if existing:
            if existing.student_id != student.pk or existing.amount != amount:
                raise AccountingError("Ключ запроса уже использован для другого платежа.", code="idempotency_conflict")
            return existing, False
    if amount <= 0:
        raise AccountingError("Сумма должна быть больше нуля.", code="invalid_amount")
    if method not in StudentPayment.Method.values:
        raise AccountingError("Неизвестный способ оплаты.")

    if refund_of is not None:
        if refund_of.kind != StudentPayment.Kind.PAYMENT or refund_of.status != StudentPayment.Status.CONFIRMED:
            raise AccountingError("Возврат оформляется только по подтверждённому платежу.")
        if refund_of.student_id != student.pk:
            raise AccountingError("Возврат должен относиться к платежу того же студента.")
        if received_date < refund_of.received_date:
            raise AccountingError("Дата возврата не может быть раньше даты платежа.")
        group, service_start, service_end = refund_of.group, refund_of.service_start, refund_of.service_end
        kind = StudentPayment.Kind.REFUND
    else:
        kind = StudentPayment.Kind.PAYMENT
        group = group or student.group
        if group is None:
            raise AccountingError("Укажите группу — студент сейчас не состоит в группе.")
        if service_start is None or service_end is None:
            raise AccountingError("Укажите период обучения, за который внесена оплата.")
        if service_end < service_start:
            raise AccountingError("Окончание периода обучения раньше его начала.")

    try:
        with transaction.atomic():
            if refund_of is not None:
                original = StudentPayment.objects.select_for_update().get(pk=refund_of.pk)
                if amount > original.amount - _refunded(original):
                    raise AccountingError("Сумма возврата больше невозвращённой части платежа.", code="exceeds_payment")
            payment = StudentPayment.objects.create(
                student=student, group=group, course_id=group.course_id, kind=kind, amount=amount,
                received_date=received_date, service_start=service_start, service_end=service_end,
                refund_of=refund_of, method=method, reference=reference.strip(), comment=comment,
                idempotency_key=key, created_by=actor,
            )
            audit.log(actor, payment, "create", new=audit.snapshot(payment, FIELDS))
    except IntegrityError:
        if key:
            return StudentPayment.objects.get(idempotency_key=key), False
        raise
    return payment, True


def used_in_locked_payrolls(payment: StudentPayment) -> list[int]:
    """ID утверждённых расчётов, в базу которых вошёл этот платёж."""
    ids = []
    lines = PayrollLine.objects.filter(
        payroll__status__in=Payroll.LOCKED_STATUSES,
        line_type__in=(PayrollLine.LineType.REVENUE_PERCENT, PayrollLine.LineType.REFUND_CORRECTION),
    ).only("payroll_id", "metadata", "source_type", "source_id")
    for line in lines:
        if line.source_type == "student_payment" and line.source_id == payment.pk:
            ids.append(line.payroll_id)
        elif any(row.get("id") == payment.pk for row in line.metadata.get("payments", [])):
            ids.append(line.payroll_id)
    return sorted(set(ids))


def void_student_payment(payment: StudentPayment, *, actor, reason: str) -> tuple[StudentPayment, list[int]]:
    reason = (reason or "").strip()
    if not reason:
        raise AccountingError("Укажите причину отмены.", code="reason_required")
    with transaction.atomic():
        payment = StudentPayment.objects.select_for_update().get(pk=payment.pk)
        if payment.status == StudentPayment.Status.VOID:
            raise AccountingError("Платёж уже отменён.")
        if payment.refunds.filter(status=StudentPayment.Status.CONFIRMED).exists():
            raise AccountingError("Сначала отмените возвраты по этому платежу.")
        old = audit.snapshot(payment, FIELDS)
        payment.status = StudentPayment.Status.VOID
        payment.void_reason = reason
        payment.voided_by, payment.voided_at = actor, timezone.now()
        payment.save()
        affected = used_in_locked_payrolls(payment)
        audit.log(actor, payment, "void", old=old, new={"status": payment.status, "affected_payrolls": affected},
                  reason=reason)
    return payment, affected
