"""Исправление неправильных данных начислений и брони (Django Admin →
«Неправильные данные»). Платежи исправляет `corrections.correct_payment`.

Каждая операция — одна транзакция под блокировкой договора(ов), с причиной и
записью в журнале аудита (старые и новые значения, связанные записи).
Записи не удаляются: ошибочное начисление аннулируется (`void_invoice`),
ошибочный платёж — сторнируется (`reverse_payment`).

Начисление:
* сумма — не меньше уже оплаченного и скорректированного (без переплаты);
  статус пересчитывается, при увеличении применяется свободный аванс;
* срок оплаты — дата (не раньше даты начисления) или урок месяца;
* период — `invoices.correct_invoice_period`;
* договор — только для не начатого и не оплаченного начисления: на старом
  договоре аннулируется, на правильном выставляется заново на ту же сумму и
  период (новый номер, ссылка на исходное — в снимке и журнале);
* примечание — в снимке начисления (`snapshot.note`).

Бронь:
* сумма и срок неоплаченной — `reservations.update_reservation`; дата и
  сумма оплаченной — это её платёж (`correct_payment`);
* перенос на другой договор (вместе с платежом, если оплачена);
* условие зачёта (в первый месяц / в общую стоимость курса) — поле договора.
"""
from __future__ import annotations

import datetime as dt
from decimal import Decimal

from django.db import transaction
from django.db.models import Max

from apps.accounting.services import audit

from ..models import (
    Invoice,
    InvoiceAdjustment,
    LessonConsumption,
    LessonPackage,
    PaymentAllocation,
    Reservation,
    ReservationAllocation,
    StudentBillingProfile,
)
from . import BillingError
from .invoices import lock_profile

ZERO = Decimal("0.00")


def _reason(reason: str) -> str:
    reason = (reason or "").strip()
    if not reason:
        raise BillingError("Укажите причину исправления.", code="reason_required")
    return reason


def _authorize(actor) -> None:
    from ..permissions import authorize

    authorize(actor, "adjust_invoice")


def correct_invoice(invoice: Invoice, *, actor, reason: str, amount=None, due_date: dt.date | None = None,
                    due_lesson: int | None = None, period_date: dt.date | None = None, note: str | None = None) -> dict:
    """Исправить сумму, срок, период и примечание начисления."""
    from .invoices import calculate_invoice_balance, correct_invoice_period, refresh_invoice
    from .payments import apply_available_credit

    _authorize(actor)
    reason = _reason(reason)
    with transaction.atomic():
        profile = lock_profile(invoice.profile_id)
        invoice = Invoice.objects.select_for_update().select_related("package").get(pk=invoice.pk)
        if invoice.status == Invoice.Status.VOID:
            raise BillingError("Начисление аннулировано — исправлять нечего.", code="bad_status")
        old = {"amount": invoice.amount, "due_date": invoice.due_date, "due_lesson": invoice.due_lesson,
               "period_date": invoice.period_date, "note": invoice.snapshot.get("note", "")}
        changed = []
        if amount not in (None, "") and Decimal(str(amount)) != invoice.amount:
            amount = Decimal(str(amount))
            sums = calculate_invoice_balance(invoice)
            if amount < sums["paid"] + sums["adjusted"]:
                raise BillingError(f"Сумма меньше уже оплаченного и скорректированного "
                                   f"({sums['paid'] + sums['adjusted']}) — сначала сторнируйте распределение.",
                                   code="below_paid")
            if amount < 0:
                raise BillingError("Сумма не может быть отрицательной.", code="invalid_amount")
            invoice.amount = amount
            invoice.package.final_price = amount
            invoice.package.save(update_fields=["final_price", "updated_at"])
            changed.append("amount")
        if due_date is not None and due_date != invoice.due_date:
            if due_date < invoice.issue_date:
                raise BillingError("Срок оплаты раньше даты начисления.", code="bad_date")
            invoice.due_date = due_date
            changed.append("due_date")
        if due_lesson is not None and due_lesson != invoice.due_lesson:
            if due_lesson < 1:
                raise BillingError("Срок — номер урока месяца (от 1).", code="invalid")
            invoice.due_lesson = due_lesson
            changed.append("due_lesson")
        if note is not None and note.strip() != old["note"]:
            invoice.snapshot = {**invoice.snapshot, "note": note.strip()}
            changed.append("note")
        if changed:
            invoice.save()
        if period_date is not None and period_date != invoice.period_date:
            correct_invoice_period(invoice, actor=actor, period_date=period_date, reason=reason, system=True)
            changed.append("period_date")
        if not changed:
            return {"invoice": invoice, "changed": []}
        invoice = refresh_invoice(invoice)
        if "amount" in changed:
            apply_available_credit(profile, actor=actor, locked=True, system=True)
            invoice = refresh_invoice(invoice)
        audit.log(actor, invoice, "billing_invoice_correct", old=old, new={
            "amount": invoice.amount, "due_date": invoice.due_date, "due_lesson": invoice.due_lesson,
            "period_date": invoice.period_date, "note": invoice.snapshot.get("note", ""), "status": invoice.status,
            "changed": changed, "profile": profile.pk,
        }, reason=reason)
    return {"invoice": invoice, "changed": changed}


def move_invoice(invoice: Invoice, *, actor, profile: StudentBillingProfile, reason: str) -> Invoice:
    """Начисление выставлено не тому договору: аннулировать на старом и
    выставить на правильном (сумма и период те же). Только если по нему нет
    оплат, корректировок и уроков."""
    from .invoices import _after_invoice_created, _create_invoice, void_invoice

    _authorize(actor)
    reason = _reason(reason)
    if profile.pk == invoice.profile_id:
        raise BillingError("Это тот же договор.", code="invalid")
    with transaction.atomic():
        for pk in sorted({invoice.profile_id, profile.pk}):
            lock_profile(pk)
        invoice = Invoice.objects.select_for_update().select_related("package").get(pk=invoice.pk)
        target = StudentBillingProfile.objects.select_related("plan", "student").get(pk=profile.pk)
        if invoice.status == Invoice.Status.VOID:
            raise BillingError("Начисление аннулировано.", code="bad_status")
        if target.status in StudentBillingProfile.CLOSED_STATUSES:
            raise BillingError("Правильный договор закрыт.", code="profile_inactive")
        package = invoice.package
        if (invoice.allocations.filter(status=PaymentAllocation.Status.ACTIVE).exists()
                or invoice.adjustments.filter(status=InvoiceAdjustment.Status.APPLIED).exists()
                or package.lessons_used or LessonConsumption.objects.filter(package=package).exists()):
            raise BillingError("По начислению есть оплата, корректировка или уроки — перенос невозможен: "
                               "сторнируйте оплату или оформите корректировку.", code="package_started")
        void_invoice(invoice, actor=actor, reason=f"Перенос на договор #{target.pk}: {reason}", system=True)
        number = (target.packages.aggregate(m=Max("number"))["m"] or 0) + 1
        month = None
        if target.is_course and package.month_number:
            month = (target.packages.exclude(status=LessonPackage.Status.CANCELLED)
                     .aggregate(m=Max("month_number"))["m"] or 0) + 1
        has_active = target.packages.filter(status=LessonPackage.Status.ACTIVE).exists()
        new_package = LessonPackage.objects.create(
            profile=target, number=number, month_number=month,
            status=LessonPackage.Status.PLANNED if has_active else LessonPackage.Status.ACTIVE,
            lessons_total=package.lessons_total, plan_version=package.plan_version, base_price=package.base_price,
            custom_price=package.custom_price, discount_type=package.discount_type, discount_value=package.discount_value,
            discount_amount=package.discount_amount, final_price=invoice.amount,
            pricing_snapshot={**package.pricing_snapshot, "moved_from_invoice": invoice.number},
            created_by=actor if getattr(actor, "is_authenticated", False) else None,
        )
        created = _create_invoice(target, new_package, amount=invoice.amount, kind=invoice.kind,
                                  on_date=invoice.issue_date, period_date=invoice.period_date, actor=actor,
                                  snapshot={**invoice.snapshot, "moved_from_invoice": invoice.number,
                                            "package_number": number})
        created = _after_invoice_created(target, created, actor=actor)
        audit.log(actor, created, "billing_invoice_move", old={"invoice": invoice.number, "profile": invoice.profile_id},
                  new={"invoice": created.number, "profile": target.pk}, reason=reason)
    return created


def transfer_reservation(reservation: Reservation, *, actor, profile: StudentBillingProfile, reason: str) -> Reservation:
    """Бронь оформлена не тому студенту / договору: перенести (оплаченную — с
    её платежом: распределения сторнируются, деньги переходят на правильный
    договор и распределяются там)."""
    from .corrections import correct_payment

    _authorize(actor)
    reason = _reason(reason)
    with transaction.atomic():
        for pk in sorted({reservation.profile_id, profile.pk}):
            lock_profile(pk)
        reservation = Reservation.objects.select_for_update().get(pk=reservation.pk)
        if reservation.profile_id == profile.pk:
            raise BillingError("Это тот же договор.", code="invalid")
        if reservation.status == Reservation.Status.CANCELLED:
            raise BillingError("Бронь отменена.", code="bad_status")
        if Reservation.objects.filter(profile=profile, status__in=(Reservation.Status.PENDING,
                                                                   Reservation.Status.PAID)).exists():
            raise BillingError("У правильного договора уже есть действующая бронь.", code="duplicate")
        old_profile = reservation.profile_id
        if reservation.payment_id:
            correct_payment(reservation.payment, actor=actor, reason=f"Перенос брони: {reason}", profile=profile,
                            with_reservation=True)
        reservation.profile = profile
        reservation.save(update_fields=["profile", "updated_at"])
        audit.log(actor, reservation, "billing_reservation_transfer", old={"profile": old_profile},
                  new={"profile": profile.pk, "payment": reservation.payment_id}, reason=reason)
    return reservation


def change_reservation_allocation(profile: StudentBillingProfile, *, actor, mode: str, reason: str) -> StudentBillingProfile:
    """Условие зачёта брони договора. Уже сделанные распределения не меняются;
    при переходе на «в первый месяц» свободный депозит брони применяется к
    неоплаченным начислениям."""
    from .payments import apply_available_credit

    _authorize(actor)
    reason = _reason(reason)
    if mode not in ReservationAllocation.values:
        raise BillingError("Неизвестное условие зачёта брони.", code="invalid")
    with transaction.atomic():
        profile = lock_profile(profile)
        if profile.reservation_allocation == mode:
            return profile
        old = profile.reservation_allocation
        profile.reservation_allocation = mode
        profile.save(update_fields=["reservation_allocation", "updated_at"])
        applied = apply_available_credit(profile, actor=actor, locked=True, system=True)
        audit.log(actor, profile, "billing_reservation_allocation", old={"reservation_allocation": old},
                  new={"reservation_allocation": mode, "allocations": [a.pk for a in applied]}, reason=reason)
    return profile
