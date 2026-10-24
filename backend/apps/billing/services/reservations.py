"""Бронь места — отдельная от оплаты обучения операция.

1. Менеджер оформляет бронь (ожидаемая сумма, срок) — денег ещё нет.
2. Бухгалтер регистрирует фактически полученную сумму
   (`record_reservation_payment`) — это платёж с назначением «Бронь»,
   сумма становится авансом профиля. Пакет обучения бронь не оплачивает.
3. Договор по программе: бронь сразу засчитывается по условию договора —
   «в первый месяц» (уменьшает доплату за месяц 1) или «в общую стоимость
   курса» (депозит, закрывает последний месяц); одни и те же деньги — один
   платёж брони, поэтому вычесть их дважды невозможно (распределения
   платежа ≤ его суммы). Тариф без срока: аванс применяется к начислению
   при платёжном событии: создании
   начисления, наступлении срока оплаты (фоновая задача) или по решению
   бухгалтера. Остаток аванса сохраняется для будущих пакетов.
4. Отмена брони: неиспользованная часть возвращается и/или удерживается
   по решению бухгалтера с основанием (правила академии); что не
   возвращено и не удержано — остаётся авансом.
"""
from __future__ import annotations

import datetime as dt
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.accounting.models import StudentPayment
from apps.accounting.services import audit

from ..models import CreditLedgerEntry, Reservation, StudentBillingProfile
from . import BillingError
from .invoices import lock_profile
from .ledger import add_entry, payment_unallocated
from .payments import _amount, record_payment, refund_payment

ZERO = Decimal("0.00")


def create_reservation(profile: StudentBillingProfile, *, actor, expected_amount, reserved_until: dt.date | None = None,
                       comment: str = "", group=None) -> Reservation:
    from ..permissions import authorize

    authorize(actor, "create_reservation")
    amount = _amount(expected_amount)
    try:
        with transaction.atomic():
            profile = lock_profile(profile)
            if profile.status in StudentBillingProfile.CLOSED_STATUSES:
                raise BillingError("Начисления по профилю остановлены.", code="profile_inactive")
            reservation = Reservation.objects.create(
                profile=profile, group=group or profile.student.group, expected_amount=amount,
                reserved_until=reserved_until, comment=comment or "", created_by=actor,
            )
            audit.log(actor, reservation, "billing_reservation_create", new={
                "profile": profile.pk, "expected_amount": amount, "reserved_until": reserved_until,
            })
    except IntegrityError:
        raise BillingError("У студента уже есть действующая бронь.", code="duplicate")
    return reservation


def record_reservation_payment(reservation: Reservation, *, actor, amount, received_date: dt.date,
                               method: str = StudentPayment.Method.CASH, reference: str = "",
                               idempotency_key: str | None = None, payer_name: str = ""):
    """Регистрация фактически полученной суммы брони → аванс профиля.
    Возвращает (бронь, платёж, создан)."""
    from ..permissions import authorize

    authorize(actor, "record_payment")
    with transaction.atomic():
        lock_profile(reservation.profile_id)
        reservation = Reservation.objects.select_for_update().get(pk=reservation.pk)
        if reservation.status == Reservation.Status.PAID and reservation.payment_id:
            payment = reservation.payment
            if idempotency_key and payment.idempotency_key == idempotency_key:
                return reservation, payment, False
            raise BillingError("Бронь уже оплачена.", code="already_paid")
        if reservation.status != Reservation.Status.PENDING:
            raise BillingError("Бронь отменена.", code="bad_status")
        payment, created = record_payment(
            profile=reservation.profile, amount=amount, received_date=received_date, actor=actor, method=method,
            reference=reference, comment="Оплата брони", idempotency_key=idempotency_key,
            purpose=StudentPayment.Purpose.RESERVATION, auto_allocate=reservation.profile.is_course,
            reservation=reservation, payer_name=payer_name,
        )
        reservation.payment, reservation.status = payment, Reservation.Status.PAID
        reservation.save(update_fields=["payment", "status", "updated_at"])
        audit.log(actor, reservation, "billing_reservation_paid", new={"payment": payment.pk, "amount": payment.amount})
    return reservation, payment, created


def cancel_reservation(reservation: Reservation, *, actor, reason: str, refund_amount=ZERO,
                       retain_amount=ZERO, refund_date: dt.date | None = None) -> Reservation:
    """Отмена брони. Для оплаченной — `refund_amount` возвращается родителю,
    `retain_amount` удерживается (основание обязательно); сумма — не больше
    неиспользованного остатка платежа брони. Остальное остаётся авансом."""
    from ..permissions import authorize

    authorize(actor, "cancel_reservation")
    reason = (reason or "").strip()
    if not reason:
        raise BillingError("Укажите основание отмены брони.", code="reason_required")
    refund_amount = Decimal(str(refund_amount or 0))
    retain_amount = Decimal(str(retain_amount or 0))
    if refund_amount < 0 or retain_amount < 0:
        raise BillingError("Суммы не могут быть отрицательными.", code="invalid_amount")
    with transaction.atomic():
        profile = lock_profile(reservation.profile_id)
        reservation = Reservation.objects.select_for_update().get(pk=reservation.pk)
        if reservation.status == Reservation.Status.CANCELLED:
            raise BillingError("Бронь уже отменена.", code="bad_status")
        if reservation.status == Reservation.Status.PAID:
            available = payment_unallocated(reservation.payment_id)
            if refund_amount + retain_amount > available:
                raise BillingError(
                    f"Неиспользованный остаток брони — {available} сом (часть уже оплатила обучение).",
                    code="exceeds_payment",
                )
            if refund_amount > 0:
                refund_payment(reservation.payment, actor=actor, amount=refund_amount, reason=f"Отмена брони: {reason}",
                               refund_date=refund_date, reservation=reservation)
            if retain_amount > 0:
                add_entry(profile, CreditLedgerEntry.Kind.RETENTION, retain_amount, payment=reservation.payment,
                          reservation=reservation, actor=actor, comment=f"Удержание брони: {reason}")
        elif refund_amount or retain_amount:
            raise BillingError("Бронь не оплачена — возвращать нечего.", code="not_paid")
        reservation.status = Reservation.Status.CANCELLED
        reservation.refunded_amount, reservation.retained_amount = refund_amount, retain_amount
        reservation.cancel_reason, reservation.cancelled_at, reservation.cancelled_by = reason, timezone.now(), actor
        reservation.save()
        audit.log(actor, reservation, "billing_reservation_cancel", new={
            "refunded": refund_amount, "retained": retain_amount,
        }, reason=reason)
    return reservation


def update_reservation(reservation: Reservation, *, actor, reason: str, expected_amount=None,
                       reserved_until=None, clear_reserved_until: bool = False) -> Reservation:
    """Исправить неоплаченную бронь: ожидаемую сумму и срок. У оплаченной
    брони сумма и дата — это платёж: исправляются через
    `corrections.correct_payment` (дата поступления, сумма, назначение)."""
    from ..permissions import authorize

    authorize(actor, "cancel_reservation")
    reason = (reason or "").strip()
    if not reason:
        raise BillingError("Укажите причину.", code="reason_required")
    with transaction.atomic():
        lock_profile(reservation.profile_id)
        reservation = Reservation.objects.select_for_update().get(pk=reservation.pk)
        if reservation.status != Reservation.Status.PENDING:
            raise BillingError("Оплаченная бронь исправляется через её платёж; отменённая — не меняется.",
                               code="bad_status")
        old = {"expected_amount": reservation.expected_amount, "reserved_until": reservation.reserved_until}
        if expected_amount not in (None, ""):
            amount = Decimal(str(expected_amount))
            if amount <= 0:
                raise BillingError("Сумма брони должна быть больше нуля.", code="invalid_amount")
            reservation.expected_amount = amount
        if reserved_until is not None or clear_reserved_until:
            reservation.reserved_until = reserved_until
        new = {"expected_amount": reservation.expected_amount, "reserved_until": reservation.reserved_until}
        if new == old:
            return reservation
        reservation.save()
        audit.log(actor, reservation, "billing_reservation_update", old=old, new=new, reason=reason)
    return reservation
