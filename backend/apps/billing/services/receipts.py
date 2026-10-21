"""Чеки Okurmen Kids (внутренние, не фискальные).

Чек создаётся в той же транзакции, что и операция (платёж, оплата брони,
возврат): нет операции — нет чека, и наоборот. Номер уникален
(`OK-ГГГГ-NNNNNN`). Суммы фиксируются на момент операции (`snapshot`):
уплачено ранее, остаток долга по договору, свободный аванс. Повторная
печать читает снимок — ни платежа, ни нового чека она не создаёт, только
увеличивает счётчик печати (с записью в журнал). Отмена платежа или
возврата — чек «Аннулирован», запись остаётся.
"""
from __future__ import annotations

from django.db import transaction
from django.db.models import F
from django.utils import timezone

from apps.accounting.models import StudentPayment
from apps.accounting.services import audit
from apps.accounting.services.money import money

from ..models import PaymentAllocation, Receipt
from . import BillingError
from .contracts import current_month, money_summary
from .receipt_pdf import som

PURPOSE_LABEL = dict(StudentPayment.Purpose.choices)


def _purpose_lines(payment: StudentPayment) -> list[str]:
    lines = []
    allocations = PaymentAllocation.objects.filter(payment=payment, status=PaymentAllocation.Status.ACTIVE)
    for a in allocations.select_related("invoice__package").order_by("invoice__package__number"):
        package = a.invoice.package
        what = ("Весь курс" if a.invoice.kind == a.invoice.Kind.COURSE
                else f"Учебный месяц №{package.month_number}" if package.month_number
                else f"Пакет уроков №{package.number}")
        lines.append(f"{what} ({a.invoice.number}): {som(a.amount)}")
    return lines


def _snapshot(payment: StudentPayment, *, payer_name: str) -> dict:
    profile = payment.billing_profile
    summary = money_summary(profile)
    month = current_month(profile)
    student = payment.student
    sign = -1 if payment.kind == StudentPayment.Kind.REFUND else 1
    unallocated = payment.amount - sum(
        (a.amount for a in PaymentAllocation.objects.filter(payment=payment, status=PaymentAllocation.Status.ACTIVE)),
        0,
    ) if payment.kind == StudentPayment.Kind.PAYMENT else 0
    lines = _purpose_lines(payment) if payment.kind == StudentPayment.Kind.PAYMENT else []
    if payment.kind == StudentPayment.Kind.PAYMENT and unallocated > 0:
        label = "Бронь" if payment.purpose == StudentPayment.Purpose.RESERVATION else "Аванс (предоплата)"
        lines.append(f"{label}: {som(unallocated)}")
    if payment.kind == StudentPayment.Kind.REFUND:
        lines.append(f"Возврат по платежу от {payment.refund_of.received_date:%d.%m.%Y}: {som(payment.amount)}")
    return {
        "student": f"{student.last_name} {student.first_name}".strip(),
        "student_id": student.pk,
        "program": profile.plan.course.name if profile.plan.course_id else profile.plan.name,
        "plan": profile.plan.name,
        "group": payment.group.name,
        "subject": str(profile.subject) if profile.subject_id else None,
        "payer": payer_name or profile.parent_name,
        "parent_phone": profile.parent_phone,
        "kind": payment.kind,
        "purpose": PURPOSE_LABEL.get(payment.purpose, "Оплата обучения"),
        "purpose_lines": lines,
        "amount": str(money(payment.amount)),
        "previously_paid": str(money(summary["paid_total"] - sign * payment.amount)),
        "paid_total": str(summary["paid_total"]),
        "outstanding": str(summary["outstanding"]),
        "due_now": str(summary["due_now"]),
        "credit": str(summary["credit"]),
        "final_course_price": None if summary["final_course_price"] is None else str(summary["final_course_price"]),
        "month_number": getattr(month, "month_number", None),
        "duration_months": profile.duration_months,
        "method": payment.method,
        "method_display": payment.get_method_display(),
        "reference": payment.reference,
        "received_date": payment.received_date.isoformat(),
        "staff": (payment.created_by.get_full_name() or payment.created_by.username) if payment.created_by_id else "",
        "currency": payment.currency,
    }


def issue_receipt(payment: StudentPayment, *, actor, payer_name: str = "") -> Receipt:
    """Чек на операцию (идемпотентно: у операции один чек). Вызывается
    внутри транзакции операции, под блокировкой профиля."""
    existing = Receipt.objects.filter(payment=payment).first()
    if existing is not None:
        return existing
    receipt = Receipt.objects.create(
        payment=payment, profile_id=payment.billing_profile_id,
        kind=Receipt.Kind.REFUND if payment.kind == StudentPayment.Kind.REFUND else Receipt.Kind.PAYMENT,
        payer_name=(payer_name or "").strip()[:150],
        snapshot=_snapshot(payment, payer_name=(payer_name or "").strip()),
        issued_by=actor if getattr(actor, "is_authenticated", False) else None,
    )
    receipt.number = f"OK-{timezone.localdate():%Y}-{receipt.pk:06d}"
    receipt.save(update_fields=["number"])
    audit.log(actor, receipt, "billing_receipt_issue", new={"payment": payment.pk, "number": receipt.number,
                                                            "amount": payment.amount})
    return receipt


def cancel_receipt(payment: StudentPayment, *, actor, reason: str) -> None:
    receipt = Receipt.objects.select_for_update().filter(payment=payment).first()
    if receipt is None or receipt.status == Receipt.Status.CANCELLED:
        return
    receipt.status, receipt.cancelled_at, receipt.cancel_reason = Receipt.Status.CANCELLED, timezone.now(), reason
    receipt.save(update_fields=["status", "cancelled_at", "cancel_reason"])
    audit.log(actor, receipt, "billing_receipt_cancel", old={"status": Receipt.Status.ISSUED},
              new={"status": receipt.status}, reason=reason)


def ensure_receipt(payment: StudentPayment, *, actor) -> Receipt:
    """Чек для операции без чека (выдача бухгалтером) — без новой операции."""
    from ..permissions import authorize

    authorize(actor, "issue_receipt")
    if payment.billing_profile_id is None:
        raise BillingError("Операция не относится к оплате обучения.", code="not_billing")
    from .invoices import lock_profile

    with transaction.atomic():
        lock_profile(payment.billing_profile_id)
        return issue_receipt(payment, actor=actor)


def mark_printed(receipt: Receipt, *, actor) -> Receipt:
    """Повторная печать / скачивание: только счётчик и журнал."""
    Receipt.objects.filter(pk=receipt.pk).update(print_count=F("print_count") + 1, last_printed_at=timezone.now())
    audit.log(actor, receipt, "billing_receipt_print", new={"number": receipt.number})
    receipt.refresh_from_db()
    return receipt
