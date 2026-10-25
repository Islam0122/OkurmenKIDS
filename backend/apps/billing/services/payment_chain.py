"""Цепочка исправления платежа: сторнированный платёж и платежи, внесённые
взамен него (`PaymentReplacement`).

Сторно (`payments.reverse_payment`) отменяет операцию в учёте — это не
возврат денег родителю (возврат — `refund_payment`). Если те же деньги
внесены заново (например, одной записью 38 000 вместо 19 000 на начисления
+ 19 000 аванса — что правильнее делать одним платежом через исправление
распределения), связь «исходный → заменяющие» делает историю прослеживаемой.
В «получено» исходный (VOID) не входит, заменяющие входят — одно
поступление считается один раз.
"""
from __future__ import annotations

import datetime as dt
from decimal import Decimal

from django.db import transaction
from django.db.models import Sum

from apps.accounting.models import StudentPayment
from apps.accounting.services import audit

from ..models import PaymentReplacement
from . import BillingError

ZERO = Decimal("0.00")


def link_replacement(original: StudentPayment, replacements: list[StudentPayment], *, actor, reason: str,
                     system: bool = False) -> list[PaymentReplacement]:
    """Связать сторнированный платёж с заменяющими. Идемпотентно (уже
    связанные пропускаются). Проверки: исходный — сторнирован, заменяющие —
    проведённые платежи того же студента, не заменяют другой платёж, сумма
    заменяющих не больше исходного."""
    from ..permissions import authorize

    if not system:
        authorize(actor, "correct_payment")
    reason = (reason or "").strip()
    if not reason:
        raise BillingError("Укажите основание связи.", code="reason_required")
    with transaction.atomic():
        original = StudentPayment.objects.select_for_update().get(pk=original.pk)
        if original.status != StudentPayment.Status.VOID or original.kind != StudentPayment.Kind.PAYMENT:
            raise BillingError("Исходный платёж должен быть сторнирован.", code="bad_status")
        created = []
        total = (PaymentReplacement.objects.filter(original=original)
                 .aggregate(s=Sum("replacement__amount"))["s"] or ZERO)
        for payment in replacements:
            payment = StudentPayment.objects.select_for_update().get(pk=payment.pk)
            if PaymentReplacement.objects.filter(original=original, replacement=payment).exists():
                continue
            if payment.pk == original.pk:
                raise BillingError("Платёж не может заменять сам себя.", code="invalid")
            if payment.status != StudentPayment.Status.CONFIRMED or payment.kind != StudentPayment.Kind.PAYMENT:
                raise BillingError(f"Платёж №{payment.pk} не проведён.", code="bad_status")
            if payment.student_id != original.student_id:
                raise BillingError(f"Платёж №{payment.pk} — другого студента.", code="wrong_profile")
            if PaymentReplacement.objects.filter(replacement=payment).exists():
                raise BillingError(f"Платёж №{payment.pk} уже заменяет другой платёж.", code="duplicate")
            total += payment.amount
            if total > original.amount:
                raise BillingError(f"Заменяющие платежи ({total}) больше исходного ({original.amount}).",
                                   code="exceeds_payment")
            link = PaymentReplacement.objects.create(
                original=original, replacement=payment, reason=reason,
                created_by=actor if getattr(actor, "is_authenticated", False) else None,
            )
            created.append(link)
        if created:
            audit.log(actor, original, "billing_payment_replacement", new={
                "original": original.pk, "replacements": [link.replacement_id for link in created],
                "replacements_total": total,
            }, reason=reason)
    return created


def chain(payment: StudentPayment) -> dict:
    """{"replaces": [...], "replaced_by": [...]} — id и суммы связанных платежей."""
    return {
        "replaces": [{"id": link.original_id, "amount": str(link.original.amount)}
                     for link in PaymentReplacement.objects.filter(replacement=payment).select_related("original")],
        "replaced_by": [{"id": link.replacement_id, "amount": str(link.replacement.amount)}
                        for link in PaymentReplacement.objects.filter(original=payment).select_related("replacement")],
    }


def unlinked_replacements(profile, *, days: int = 90) -> list[dict]:
    """Кандидаты на связь (только чтение): сторнированный платёж без связи и
    проведённые платежи того же студента, внесённые после его сторно, сумма
    которых равна исходному. Решение принимает бухгалтер."""
    rows = []
    linked = set(PaymentReplacement.objects.values_list("replacement_id", flat=True))
    voided = (StudentPayment.objects.filter(billing_profile=profile, status=StudentPayment.Status.VOID,
                                            kind=StudentPayment.Kind.PAYMENT)
              .exclude(replaced_by_links__isnull=False).order_by("voided_at", "pk"))
    for original in voided:
        since = original.voided_at or original.created_at
        candidates = list(StudentPayment.objects.filter(
            student_id=original.student_id, billing_profile__isnull=False, status=StudentPayment.Status.CONFIRMED,
            kind=StudentPayment.Kind.PAYMENT, created_at__gte=since - dt.timedelta(minutes=5),
            created_at__lte=since + dt.timedelta(days=days),
        ).exclude(pk__in=linked).order_by("created_at", "pk"))
        picked, total = [], ZERO
        for payment in candidates:
            if total + payment.amount <= original.amount:
                picked.append(payment)
                total += payment.amount
            if total == original.amount:
                break
        if picked and total == original.amount:
            rows.append({"original": original.pk, "amount": str(original.amount),
                         "void_reason": original.void_reason, "candidates": [p.pk for p in picked],
                         "candidates_total": str(total)})
    return rows
