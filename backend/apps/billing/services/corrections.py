"""Исправление проведённых платежей бухгалтером (контролируемые корректировки).

Платёж (`accounting.StudentPayment`) не редактируется в обход сервисов:
каждая корректировка — одна транзакция под блокировкой договора(ов) и
платежа, с проверками и записью в журнал аудита (старые и новые значения,
основание, связанные распределения и чек).

Что можно исправить (`correct_payment`):

* дату фактического поступления (`received_date`) — отчёты по поступлениям
  сразу считаются по новой дате; период начисления (`Invoice.period_date`)
  НЕ меняется; номер чека не меняется (в снимке чека — новая дата, прежний
  снимок — в его истории);
* сумму — разница проводится записью журнала аванса PAYMENT_ADJUST (исходная
  запись PAYMENT_IN не меняется); уменьшение — не больше нераспределённого
  остатка (или вместе с новым распределением); чек перевыпускается;
* способ оплаты, номер документа, комментарий, назначение (кроме брони);
* договор / студента (платёж привязан не к тому студенту) — распределения
  сторнируются, деньги переходят записями PAYMENT_ADJUST (− у старого
  договора, + у нового) и распределяются по новому договору; чек
  перевыпускается;
* распределение между начислениями (`allocations`) — действующие
  распределения платежа сторнируются, создаются указанные (остаток — аванс).

Дата создания записи (`created_at`) — только отдельной корректировкой
`correct_created_at` (обычно не нужна: отчёты её не используют).

Аннулирование — `payments.reverse_payment` (VOID, распределения сторнируются,
чек «Аннулирован»); физическое удаление платежей финансовая модель не
допускает (`ImmutableQuerySet`), повторное аннулирование запрещено.

Платёж в утверждённом / закрытом расчётном периоде бухгалтерии
(`PayrollPeriod` APPROVED / CLOSED) исправляется только с явным
подтверждением (`confirm_closed_period`), предупреждение — в журнале.
Повторная отправка той же формы ничего не меняет (нет изменений — нет записи).
"""
from __future__ import annotations

import datetime as dt
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from apps.accounting.models import PayrollPeriod, StudentPayment
from apps.accounting.services import audit

from ..models import CreditLedgerEntry, Invoice, PaymentAllocation, Receipt, StudentBillingProfile
from . import BillingError
from .invoices import lock_profile
from .ledger import credit_balance, payment_unallocated

ZERO = Decimal("0.00")
FIELDS = ("amount", "received_date", "method", "reference", "comment", "purpose", "billing_profile_id", "student_id",
          "group_id", "course_id", "status")


def closed_periods(*days: dt.date) -> list[dict]:
    """Утверждённые / закрытые расчётные периоды бухгалтерии, в которые попадают даты."""
    rows = []
    for day in sorted(set(filter(None, days))):
        for period in PayrollPeriod.objects.filter(
                status__in=(PayrollPeriod.Status.APPROVED, PayrollPeriod.Status.CLOSED),
                start_date__lte=day, end_date__gte=day):
            rows.append({"date": day.isoformat(), "period": str(period), "status": period.status})
    return rows


def _adjust(profile, amount: Decimal, *, payment, actor, comment: str) -> None:
    if amount:
        CreditLedgerEntry.objects.create(
            profile=profile, kind=CreditLedgerEntry.Kind.PAYMENT_ADJUST, amount=amount, payment=payment,
            comment=comment, created_by=actor if getattr(actor, "is_authenticated", False) else None,
        )


def _current_allocations(payment) -> dict[int, Decimal]:
    result: dict[int, Decimal] = {}
    for a in payment.billing_allocations.filter(status=PaymentAllocation.Status.ACTIVE):
        result[a.invoice_id] = result.get(a.invoice_id, ZERO) + a.amount
    return result


def _reverse_all(payment, *, actor, reason) -> list[int]:
    from .payments import reverse_allocation_locked

    ids = []
    for allocation in payment.billing_allocations.filter(status=PaymentAllocation.Status.ACTIVE):
        reverse_allocation_locked(allocation, actor=actor, reason=f"Исправление платежа: {reason}")
        ids.append(allocation.pk)
    return ids


def refresh_receipt(payment: StudentPayment, *, actor, reason: str, reissue: bool) -> Receipt | None:
    """Обновить чек после исправления. Без перевыпуска — номер прежний, в
    снимке новые данные операции; с перевыпуском (сумма, студент) — новый
    номер. Прежние номер и снимок сохраняются в `snapshot["history"]` и в
    журнале аудита."""
    from .receipts import _snapshot

    receipt = Receipt.objects.select_for_update().filter(payment=payment).first()
    if receipt is None:
        return None
    previous = {k: v for k, v in receipt.snapshot.items() if k != "history"}
    history = [*receipt.snapshot.get("history", []), {
        "number": receipt.number, "snapshot": previous, "changed_at": timezone.now().isoformat(), "reason": reason,
    }]
    fresh = _snapshot(payment, payer_name=receipt.payer_name)
    old_number = receipt.number
    if reissue:
        # Суммы и состояние договора — на момент перевыпуска.
        receipt.snapshot = {**fresh, "history": history, "reissued": True}
        receipt.number = f"{old_number.split('/')[0]}/{len(history)}"[:30]
    else:
        # Обычное исправление (дата, способ, документ): номер и суммы чека
        # прежние, меняются только реквизиты операции.
        receipt.snapshot = {**previous, **{k: fresh[k] for k in ("received_date", "method", "method_display",
                                                                 "reference", "purpose")},
                            "history": history}
    receipt.profile_id = payment.billing_profile_id
    receipt.save(update_fields=["snapshot", "number", "profile"])
    audit.log(actor, receipt, "billing_receipt_reissue" if reissue else "billing_receipt_update",
              old={"number": old_number, "snapshot": previous},
              new={"number": receipt.number, "payment": payment.pk}, reason=reason)
    return receipt


def correct_payment(payment: StudentPayment, *, actor, reason: str, received_date: dt.date | None = None,
                    amount=None, method: str | None = None, reference: str | None = None, comment: str | None = None,
                    purpose: str | None = None, profile: StudentBillingProfile | None = None,
                    allocations: list[tuple[Invoice, Decimal]] | None = None,
                    confirm_closed_period: bool = False, with_reservation: bool = False) -> dict:
    """Исправить проведённый платёж (см. модуль). Возвращает
    {"payment", "changed": [поля], "warnings": [...], "audit": id | None}."""
    from ..permissions import authorize
    from .payments import _allocate_locked, _amount, _distribute_locked, _payment_group

    authorize(actor, "correct_payment")
    reason = (reason or "").strip()
    if not reason:
        raise BillingError("Укажите причину корректировки.", code="reason_required")
    if payment.billing_profile_id is None:
        raise BillingError("Платёж не относится к оплате обучения.", code="not_billing")
    new_amount = _amount(amount) if amount not in (None, "") else None
    with transaction.atomic():
        # Оба договора (при переносе) блокируются в одном порядке — без взаимоблокировок.
        for pk in sorted({payment.billing_profile_id, getattr(profile, "pk", None)} - {None}):
            lock_profile(pk)
        payment = StudentPayment.objects.select_for_update().get(pk=payment.pk)
        if payment.status != StudentPayment.Status.CONFIRMED:
            raise BillingError("Платёж аннулирован — исправлять нечего.", code="bad_status")
        old_profile = StudentBillingProfile.objects.get(pk=payment.billing_profile_id)
        is_refund = payment.kind == StudentPayment.Kind.REFUND
        old = audit.snapshot(payment, FIELDS) | {"created_at": payment.created_at.isoformat(),
                                                 "allocations": {str(k): str(v) for k, v in
                                                                 _current_allocations(payment).items()}}
        changed: list[str] = []
        warnings: list[dict] = []

        transfer = profile is not None and profile.pk != payment.billing_profile_id
        amount_changes = new_amount is not None and new_amount != payment.amount
        if is_refund and (amount_changes or transfer or allocations is not None or purpose):
            raise BillingError("У возврата исправляются только дата, способ, документ и комментарий; "
                               "иначе — отмените возврат и оформите заново.", code="invalid")
        if allocations is not None:
            desired: dict[int, Decimal] = {}
            for invoice, part in allocations:
                desired[invoice.pk] = desired.get(invoice.pk, ZERO) + _amount(part)
            if desired == _current_allocations(payment) and not transfer:
                allocations = None  # то же распределение — повтор формы

        # Дата поступления денег.
        if received_date is not None and received_date != payment.received_date:
            if received_date > timezone.localdate():
                raise BillingError("Дата поступления не может быть в будущем.", code="bad_date")
            if is_refund and received_date < payment.refund_of.received_date:
                raise BillingError("Дата возврата раньше даты платежа.", code="bad_date")
            first_refund = payment.refunds.filter(status=StudentPayment.Status.CONFIRMED).order_by("received_date").first()
            if first_refund is not None and received_date > first_refund.received_date:
                raise BillingError("По платежу есть возврат раньше новой даты.", code="bad_date")
            warnings += closed_periods(payment.received_date, received_date)
            payment.received_date = received_date
            changed.append("received_date")
        if amount_changes:
            warnings += closed_periods(payment.received_date)
        if warnings and not confirm_closed_period:
            raise BillingError(
                "Платёж относится к утверждённому / закрытому расчётному периоду ("
                + ", ".join(f"{w['period']} — {w['status']}" for w in warnings)
                + "). Подтвердите исправление явно.", code="closed_period",
            )

        if method is not None and method != payment.method:
            if method not in StudentPayment.Method.values:
                raise BillingError("Неизвестный способ оплаты.", code="invalid_method")
            payment.method = method
            changed.append("method")
        if reference is not None and reference.strip() != payment.reference:
            reference = reference.strip()
            if reference and StudentPayment.objects.filter(
                billing_profile_id=getattr(profile, "pk", payment.billing_profile_id), reference=reference,
                status=StudentPayment.Status.CONFIRMED, kind=payment.kind,
            ).exclude(pk=payment.pk).exists():
                raise BillingError("Платёж с этим номером документа уже зарегистрирован.", code="duplicate_reference")
            payment.reference = reference
            changed.append("reference")
        if comment is not None and comment != payment.comment:
            payment.comment = comment
            changed.append("comment")
        reclassified = None
        if purpose and purpose != payment.purpose:
            if purpose == StudentPayment.Purpose.RESERVATION:
                raise BillingError("Платёж не становится бронью задним числом — оформите бронь.", code="invalid")
            if purpose not in StudentPayment.Purpose.values:
                raise BillingError("Неизвестное назначение платежа.", code="invalid")
            if payment.purpose == StudentPayment.Purpose.RESERVATION:
                # Деньги, принятые как «оплата брони», на самом деле — оплата
                # обучения / предоплата (например, весь курс внесён через бронь):
                # бронь закрывается без возврата и удержания, деньги и их
                # распределения остаются, ограничения брони больше не действуют.
                reclassified = getattr(payment, "reservation", None)
            payment.purpose = purpose
            changed.append("purpose")

        reversed_ids: list[int] = []
        if transfer and (payment.refunds.filter(status=StudentPayment.Status.CONFIRMED).exists()
                         or payment.credit_entries.filter(kind=CreditLedgerEntry.Kind.RETENTION).exists()):
            raise BillingError("По платежу есть возврат или удержание — сначала отмените их.", code="has_refunds")
        if amount_changes and allocations is None and not transfer \
                and payment.amount - new_amount > payment_unallocated(payment.pk):
            raise BillingError("Новая сумма меньше уже распределённой — укажите новое распределение.",
                               code="exceeds_payment")
        if transfer or allocations is not None:
            reversed_ids = _reverse_all(payment, actor=actor, reason=reason)

        target = old_profile
        if transfer:
            # Оплата брони переносится только вместе с бронью
            # (`record_corrections.transfer_reservation` передаёт with_reservation).
            if getattr(payment, "reservation", None) is not None and not with_reservation:
                raise BillingError("Оплата брони переносится через бронь.", code="invalid")
            if profile.status in StudentBillingProfile.CLOSED_STATUSES:
                raise BillingError("Новый договор закрыт.", code="profile_inactive")
            target = StudentBillingProfile.objects.select_related("student").get(pk=profile.pk)
            free = payment_unallocated(payment.pk)
            _adjust(old_profile, -free, payment=payment, actor=actor, comment=f"Перенос на договор #{target.pk}: {reason}")
            _adjust(target, free, payment=payment, actor=actor, comment=f"Перенос с договора #{old_profile.pk}: {reason}")
            group = _payment_group(target)
            payment.billing_profile, payment.student_id = target, target.student_id
            payment.group, payment.course_id = group, group.course_id
            changed += ["billing_profile", "student"]
        if amount_changes:
            diff = new_amount - payment.amount
            if diff < 0 and -diff > payment_unallocated(payment.pk):
                raise BillingError("Новая сумма меньше уже распределённой.", code="exceeds_payment")
            _adjust(target, diff, payment=payment, actor=actor, comment=f"Исправление суммы: {reason}")
            payment.amount = new_amount
            changed.append("amount")
        if not changed and allocations is None:
            return {"payment": payment, "changed": [], "warnings": [], "audit": None}
        payment.save()
        if reclassified is not None and reclassified.status != reclassified.Status.CANCELLED:
            from ..models import Reservation

            reservation = Reservation.objects.select_for_update().get(pk=reclassified.pk)
            old_status = reservation.status
            reservation.status, reservation.cancelled_at = Reservation.Status.CANCELLED, timezone.now()
            reservation.cancel_reason = f"Платёж переквалифицирован в «{payment.get_purpose_display()}»: {reason}"
            reservation.cancelled_by = actor if getattr(actor, "is_authenticated", False) else None
            reservation.save()
            audit.log(actor, reservation, "billing_reservation_reclassify", old={"status": old_status},
                      new={"status": reservation.status, "payment": payment.pk, "purpose": payment.purpose},
                      reason=reason)

        created_ids: list[int] = []
        if allocations is not None:
            for invoice, part in allocations:
                if invoice.profile_id != target.pk:
                    raise BillingError(f"Начисление {invoice.number} — другого договора.", code="wrong_profile")
                created_ids.append(_allocate_locked(payment, invoice, _amount(part), actor=actor,
                                                    source=PaymentAllocation.Source.MANUAL).pk)
            changed.append("allocations")
        elif transfer or (amount_changes and new_amount > Decimal(old["amount"])):
            # Новые деньги на договоре — как при поступлении: на открытые начисления, остаток — аванс.
            created_ids = [a.pk for a in _distribute_locked(target, [payment], actor=actor,
                                                            source=PaymentAllocation.Source.PAYMENT)]
        for checked in {old_profile.pk, target.pk}:
            if credit_balance(checked) < 0:
                raise BillingError("Исправление увело аванс договора в минус — сначала сторнируйте распределения.",
                                   code="negative_credit")
        if payment_unallocated(payment.pk) < 0:
            raise BillingError("Распределено больше суммы платежа.", code="exceeds_payment")

        printed = {"received_date", "method", "reference", "purpose", "amount", "billing_profile", "allocations"}
        receipt = (refresh_receipt(payment, actor=actor, reason=reason, reissue=transfer or amount_changes)
                   if printed & set(changed) else Receipt.objects.filter(payment=payment).first())
        new = audit.snapshot(payment, FIELDS) | {"allocations": {str(k): str(v) for k, v in
                                                                 _current_allocations(payment).items()}}
        entry = audit.log(actor, payment, "billing_payment_correct", old=old, new={
            **new, "changed": changed, "receipt": receipt.number if receipt else None,
            "receipt_id": receipt.pk if receipt else None, "allocations_reversed": reversed_ids,
            "allocations_created": created_ids, "closed_period_warnings": warnings,
        }, reason=reason)
    return {"payment": payment, "changed": changed, "warnings": warnings, "audit": entry.pk}


def correct_created_at(payment: StudentPayment, *, actor, created_at: dt.datetime, reason: str) -> StudentPayment:
    """Отдельная административная корректировка даты создания записи (аудит).
    Отчёты её не используют — для денег важна `received_date`."""
    from ..permissions import authorize

    authorize(actor, "correct_payment")
    reason = (reason or "").strip()
    if not reason:
        raise BillingError("Укажите причину корректировки.", code="reason_required")
    if timezone.is_naive(created_at):
        created_at = timezone.make_aware(created_at)
    if created_at > timezone.now():
        raise BillingError("Дата создания не может быть в будущем.", code="bad_date")
    with transaction.atomic():
        payment = StudentPayment.objects.select_for_update().get(pk=payment.pk)
        if payment.created_at == created_at:
            return payment
        old = payment.created_at
        StudentPayment.objects.filter(pk=payment.pk).update(created_at=created_at)
        payment.refresh_from_db()
        audit.log(actor, payment, "billing_payment_created_at", old={"created_at": old.isoformat()},
                  new={"created_at": created_at.isoformat()}, reason=reason)
    return payment


def payment_history(payment: StudentPayment) -> list[dict]:
    """Журнал аудита по платежу, его чеку и распределениям (только чтение)."""
    from apps.accounting.models import PayrollAuditLog
    from django.db.models import Q

    receipt_ids = list(Receipt.objects.filter(payment=payment).values_list("pk", flat=True))
    allocation_ids = list(PaymentAllocation.objects.filter(payment=payment).values_list("pk", flat=True))
    rows = PayrollAuditLog.objects.filter(
        Q(entity_type="studentpayment", entity_id=payment.pk)
        | Q(entity_type="receipt", entity_id__in=receipt_ids)
        | Q(entity_type="paymentallocation", entity_id__in=allocation_ids),
    ).select_related("actor").order_by("created_at", "pk")
    return [{
        "id": r.pk, "created_at": r.created_at.isoformat(), "actor": str(r.actor) if r.actor_id else "система",
        "action": r.action, "entity_type": r.entity_type, "entity_id": r.entity_id,
        "old_values": r.old_values, "new_values": r.new_values, "reason": r.reason,
    } for r in rows]
