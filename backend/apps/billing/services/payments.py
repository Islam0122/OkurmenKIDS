"""Платежи, распределение и аванс.

Платёж — `accounting.StudentPayment` (фактически полученные деньги; его
сумма никогда не меняется). Поступление целиком зачисляется в аванс
(`CreditLedgerEntry.PAYMENT_IN`), а оплата начисления — это распределение
(`PaymentAllocation`) с одновременным списанием из аванса. Поэтому:

* полная оплата: начисление 4 000, платёж 4 000 → остаток 0, PAID;
* частичная: платёж 2 500 → остаток 1 500, PARTIALLY_PAID;
* несколько пакетов: `prepay_packages` создаёт следующие пакеты с
  начислениями, деньги распределяются по ним по порядку, неиспользованное
  остаётся авансом, а при завершении пакета новое начисление не создаётся —
  следующий пакет уже есть;
* бронь: деньги — аванс, применяется к начислению при наступлении
  платёжного события (новое начисление, наступление срока, решение бухгалтера).

Ошибки исправляются сторно: распределения (деньги возвращаются в аванс),
платежа целиком (`reverse_payment`) или возвратом денег (`refund_payment`).
Повторная отправка платежа с тем же `Idempotency-Key` возвращает тот же
платёж.
"""
from __future__ import annotations

import datetime as dt
from decimal import Decimal, InvalidOperation

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.accounting.models import StudentPayment
from apps.accounting.services import audit

from ..models import CreditLedgerEntry, Invoice, LessonConsumption, PaymentAllocation, StudentBillingProfile
from . import BillingError
from .invoices import ensure_future_packages, lock_profile, refresh_invoice
from .ledger import add_entry, credit_balance, payment_unallocated

ZERO = Decimal("0.00")
Kind = CreditLedgerEntry.Kind
PAYMENT_FIELDS = ("kind", "amount", "received_date", "student", "group", "status", "purpose", "billing_profile")


def _amount(value) -> Decimal:
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise BillingError("Некорректная сумма.", code="invalid_amount")
    if amount <= 0:
        raise BillingError("Сумма должна быть больше нуля.", code="invalid_amount")
    if amount != amount.quantize(Decimal("0.01")):
        raise BillingError("Сумма — не точнее тыйына (0.01).", code="invalid_amount")
    return amount


def _payment_group(profile: StudentBillingProfile):
    """Группа платежа (`StudentPayment.group` обязательна): текущая группа
    студента, иначе группа последнего списанного урока."""
    if profile.student.group_id:
        return profile.student.group
    last = LessonConsumption.objects.filter(profile=profile, group__isnull=False).order_by("-lesson_date").first()
    if last is not None:
        return last.group
    raise BillingError("Студент не состоит в группе — платёж не к чему привязать.", code="no_group")


def unpaid_invoices(profile) -> list[Invoice]:
    """Открытые начисления профиля в порядке оплаты: по номеру месяца
    (пакета), затем по сроку — сначала текущий долг, потом будущие месяцы."""
    return list(
        Invoice.objects.select_for_update().filter(profile=profile, status__in=Invoice.UNPAID_STATUSES)
        .select_related("package").order_by("package__number", "due_date", "pk")
    )


# ---------------------------------------------------------------------------
# Распределение
# ---------------------------------------------------------------------------

def _allocate_locked(payment: StudentPayment, invoice: Invoice, amount: Decimal, *, actor, source: str) -> PaymentAllocation:
    """Распределить часть платежа на начисление. Профиль уже заблокирован."""
    invoice = Invoice.objects.select_for_update().get(pk=invoice.pk)
    if invoice.profile_id != payment.billing_profile_id:
        raise BillingError("Начисление другого студента.", code="wrong_profile")
    if invoice.status not in Invoice.UNPAID_STATUSES:
        raise BillingError(f"Начисление {invoice.number} не ожидает оплаты ({invoice.get_status_display()}).",
                           code="bad_status")
    if payment.status != StudentPayment.Status.CONFIRMED or payment.kind != StudentPayment.Kind.PAYMENT:
        raise BillingError("Платёж отменён.", code="bad_status")
    if amount > invoice.balance:
        raise BillingError(f"Сумма больше остатка начисления ({invoice.balance} сом).", code="exceeds_balance")
    if amount > payment_unallocated(payment.pk):
        raise BillingError("Сумма больше нераспределённого остатка платежа.", code="exceeds_payment")
    allocation = PaymentAllocation.objects.create(
        payment=payment, invoice=invoice, profile_id=payment.billing_profile_id, amount=amount, source=source,
        created_by=actor if getattr(actor, "is_authenticated", False) else None,
    )
    add_entry(invoice.profile, Kind.ALLOCATION, amount, payment=payment, allocation=allocation, actor=actor,
              comment=f"Оплата {invoice.number}")
    audit.log(actor, allocation, "billing_allocate", new={
        "payment": payment.pk, "invoice": invoice.pk, "amount": amount, "source": source,
    })
    refresh_invoice(invoice)
    return allocation


def _distribute_locked(profile, payments, *, actor, source: str) -> list[PaymentAllocation]:
    """FIFO: деньги платежей (по дате поступления) — на начисления по порядку.
    Бронь в режиме «в общую стоимость курса» идёт только на последний месяц
    (`contracts.may_fund`)."""
    from .contracts import may_fund

    allocations = []
    pool = [[p, payment_unallocated(p.pk)] for p in payments]
    pool = [item for item in pool if item[1] > 0]
    for invoice in unpaid_invoices(profile):
        need = invoice.balance
        for item in pool:
            if need <= 0:
                break
            payment, free = item
            if free <= 0 or not may_fund(profile, payment, invoice):
                continue
            part = min(need, free)
            allocations.append(_allocate_locked(payment, invoice, part, actor=actor, source=source))
            item[1] -= part
            need -= part
        if all(item[1] <= 0 for item in pool):
            break
    return allocations


def _credit_payments(profile):
    return list(
        StudentPayment.objects.filter(
            billing_profile=profile, kind=StudentPayment.Kind.PAYMENT, status=StudentPayment.Status.CONFIRMED,
        ).order_by("received_date", "pk")
    )


def apply_available_credit(profile, *, actor=None, locked: bool = False, system: bool = False) -> list[PaymentAllocation]:
    """Применить доступный аванс к неоплаченным начислениям (по порядку).
    `system` — вызов внутри системного события (создание начисления по
    регистрации или завершению пакета), а не действие пользователя."""
    from ..permissions import authorize

    if not system:
        authorize(actor, "allocate")
    with transaction.atomic():
        profile = profile if locked else lock_profile(profile)
        if credit_balance(profile.pk) <= 0:
            return []
        return _distribute_locked(profile, _credit_payments(profile), actor=actor, source=PaymentAllocation.Source.CREDIT)


def allocate_payment(payment: StudentPayment, *, actor, items: list[tuple[Invoice, Decimal]]) -> list[PaymentAllocation]:
    """Ручное распределение бухгалтером: [(начисление, сумма), …] из
    нераспределённого остатка платежа."""
    from ..permissions import authorize

    authorize(actor, "allocate")
    if payment.billing_profile_id is None:
        raise BillingError("Платёж не относится к оплате обучения по пакетам.", code="not_billing")
    with transaction.atomic():
        lock_profile(payment.billing_profile_id)
        payment = StudentPayment.objects.select_for_update().get(pk=payment.pk)
        return [
            _allocate_locked(payment, invoice, _amount(amount), actor=actor, source=PaymentAllocation.Source.MANUAL)
            for invoice, amount in items
        ]


def reverse_allocation_locked(allocation: PaymentAllocation, *, actor, reason: str) -> PaymentAllocation:
    allocation = PaymentAllocation.objects.select_for_update().get(pk=allocation.pk)
    if allocation.status != PaymentAllocation.Status.ACTIVE:
        raise BillingError("Распределение уже сторнировано.", code="bad_status")
    allocation.status = PaymentAllocation.Status.REVERSED
    allocation.reversed_at, allocation.reverse_reason = timezone.now(), reason
    allocation.reversed_by = actor if getattr(actor, "is_authenticated", False) else None
    allocation.save()
    add_entry(allocation.profile, Kind.ALLOCATION_REVERSAL, allocation.amount, payment=allocation.payment,
              allocation=allocation, actor=actor, comment=reason)
    audit.log(actor, allocation, "billing_allocation_reverse", new={"amount": allocation.amount}, reason=reason)
    refresh_invoice(allocation.invoice)
    return allocation


def reverse_allocation(allocation: PaymentAllocation, *, actor, reason: str) -> PaymentAllocation:
    """Сторно распределения: деньги возвращаются в аванс, начисление снова
    ждёт оплаты. Сам платёж не меняется."""
    from ..permissions import authorize

    authorize(actor, "allocate")
    reason = (reason or "").strip()
    if not reason:
        raise BillingError("Укажите причину.", code="reason_required")
    with transaction.atomic():
        lock_profile(allocation.profile_id)
        return reverse_allocation_locked(allocation, actor=actor, reason=reason)


# ---------------------------------------------------------------------------
# Платежи
# ---------------------------------------------------------------------------

def record_payment(*, profile: StudentBillingProfile, amount, received_date: dt.date, actor,
                   method: str = StudentPayment.Method.CASH, reference: str = "", comment: str = "",
                   idempotency_key: str | None = None, purpose: str = StudentPayment.Purpose.TUITION,
                   auto_allocate: bool = True, prepay_packages: int = 0,
                   allocations: list[tuple[Invoice, Decimal]] | None = None, reservation=None,
                   payer_name: str = "", replaces: StudentPayment | None = None):
    """Зарегистрировать фактически полученные деньги. Возвращает (платёж,
    создан). Сумма зачисляется в аванс и (по умолчанию) сразу распределяется
    по неоплаченным начислениям; остаток — аванс."""
    from ..permissions import authorize

    authorize(actor, "record_payment")
    amount = _amount(amount)
    key = (idempotency_key or "").strip()[:64] or None
    if key:
        existing = StudentPayment.objects.filter(idempotency_key=key).first()
        if existing is not None:
            if existing.billing_profile_id != profile.pk or existing.amount != amount:
                raise BillingError("Ключ запроса уже использован для другого платежа.", code="idempotency_conflict")
            return existing, False
    if purpose not in StudentPayment.Purpose.values:
        raise BillingError("Неизвестное назначение платежа.", code="invalid")
    if method not in StudentPayment.Method.values:
        raise BillingError("Неизвестный способ оплаты.", code="invalid_method")
    if received_date > timezone.localdate():
        raise BillingError("Дата поступления не может быть в будущем.", code="bad_date")
    if allocations and prepay_packages:
        raise BillingError("Укажите либо распределение, либо число пакетов вперёд.", code="invalid")
    reference = (reference or "").strip()
    try:
        with transaction.atomic():
            profile = lock_profile(profile)
            if reference and StudentPayment.objects.filter(
                billing_profile=profile, reference=reference, status=StudentPayment.Status.CONFIRMED,
                kind=StudentPayment.Kind.PAYMENT,
            ).exists():
                raise BillingError("Платёж с этим номером документа уже зарегистрирован.", code="duplicate_reference")
            group = _payment_group(profile)
            payment = StudentPayment.objects.create(
                student=profile.student, group=group, course_id=group.course_id, kind=StudentPayment.Kind.PAYMENT,
                amount=amount, received_date=received_date, method=method, reference=reference, comment=comment,
                idempotency_key=key, created_by=actor, billing_profile=profile, purpose=purpose,
            )
            if profile.status in StudentBillingProfile.CLOSED_STATUSES and purpose != StudentPayment.Purpose.TUITION:
                raise BillingError("Договор закрыт — принимается только погашение долга.", code="profile_inactive")
            add_entry(profile, Kind.PAYMENT_IN, amount, payment=payment, actor=actor, reservation=reservation,
                      comment="Бронь" if purpose == StudentPayment.Purpose.RESERVATION else "Поступление")
            audit.log(actor, payment, "billing_payment", new=audit.snapshot(payment, PAYMENT_FIELDS))
            if prepay_packages:
                ensure_future_packages(profile, int(prepay_packages), actor=actor, on_date=received_date)
            if allocations:
                for invoice, part in allocations:
                    _allocate_locked(payment, invoice, _amount(part), actor=actor, source=PaymentAllocation.Source.PAYMENT)
            if auto_allocate:
                # Деньги не лежат «свободным авансом» рядом с выставленным
                # неоплаченным начислением того же договора: сначала выбранное
                # начисление (если указано), остаток — на остальные по порядку,
                # затем аванс. Иначе карточка показывает одну сумму и долгом
                # («к оплате»), и авансом (бронь «в общую стоимость» держит
                # `contracts.may_fund`). `auto_allocate=False` — явное решение
                # оставить деньги авансом до платёжного события.
                _distribute_locked(profile, [payment], actor=actor, source=PaymentAllocation.Source.PAYMENT)
            from .receipts import issue_receipt

            issue_receipt(payment, actor=actor, payer_name=payer_name)
            if replaces is not None:
                # Деньги вносятся взамен сторнированного платежа — связь в цепочке исправления.
                from .payment_chain import link_replacement

                link_replacement(replaces, [payment], actor=actor, system=True,
                                 reason=f"Внесён взамен сторнированного платежа №{replaces.pk}")
    except IntegrityError:
        if key:
            existing = StudentPayment.objects.filter(idempotency_key=key).first()
            if existing is not None:
                return existing, False
        raise
    return payment, True


def reverse_payment(payment: StudentPayment, *, actor, reason: str, system: bool = False) -> StudentPayment:
    """Сторно ошибочно внесённого платежа: все его распределения
    сторнируются (начисления снова ждут оплаты), платёж отменяется (VOID) с
    причиной; записи не удаляются. Если по платежу был возврат — сначала
    отмените возврат."""
    from ..permissions import authorize

    if not system:  # system — сторно по итогам аудита из консоли (`billing_money_audit`)
        authorize(actor, "reverse_payment")
    reason = (reason or "").strip()
    if not reason:
        raise BillingError("Укажите причину отмены.", code="reason_required")
    if payment.billing_profile_id is None:
        raise BillingError("Платёж не относится к оплате обучения по пакетам.", code="not_billing")
    with transaction.atomic():
        profile = lock_profile(payment.billing_profile_id)
        payment = StudentPayment.objects.select_for_update().get(pk=payment.pk)
        if payment.status == StudentPayment.Status.VOID:
            raise BillingError("Платёж уже отменён.", code="bad_status")
        if payment.kind != StudentPayment.Kind.PAYMENT:
            raise BillingError("Возврат отменяется отдельно.", code="bad_status")
        if payment.refunds.filter(status=StudentPayment.Status.CONFIRMED).exists():
            raise BillingError("По платежу есть возврат — сначала отмените возврат.", code="has_refunds")
        if payment.credit_entries.filter(kind=Kind.RETENTION).exists():
            raise BillingError("Часть платежа удержана по брони — отмена невозможна.", code="has_retention")
        for allocation in payment.billing_allocations.filter(status=PaymentAllocation.Status.ACTIVE):
            reverse_allocation_locked(allocation, actor=actor, reason=f"Отмена платежа: {reason}")
        from .receipts import cancel_receipt

        cancel_receipt(payment, actor=actor, reason=reason)
        left = payment_unallocated(payment.pk)
        if left > 0:
            add_entry(profile, Kind.PAYMENT_VOID, left, payment=payment, actor=actor, comment=reason)
        old = audit.snapshot(payment, PAYMENT_FIELDS)
        payment.status = StudentPayment.Status.VOID
        payment.void_reason, payment.voided_by, payment.voided_at = reason, actor, timezone.now()
        payment.save()
        from ..models import Reservation

        reservation = Reservation.objects.select_for_update().filter(payment=payment).first()
        if reservation is not None and reservation.status == Reservation.Status.PAID:
            # Ошибочная оплата брони аннулирована — бронь снова ждёт оплаты
            # (её можно отменить отдельно); связь с платежом — в журнале.
            reservation.status, reservation.payment = Reservation.Status.PENDING, None
            reservation.save(update_fields=["status", "payment", "updated_at"])
            audit.log(actor, reservation, "billing_reservation_payment_void",
                      old={"status": Reservation.Status.PAID, "payment": payment.pk},
                      new={"status": reservation.status}, reason=reason)
        audit.log(actor, payment, "billing_payment_reverse", old=old, new={"status": payment.status}, reason=reason)
        if credit_balance(profile.pk) < 0:
            raise BillingError("Отмена увела аванс в минус — проверьте журнал.", code="negative_credit")
    return payment


def refund_payment(payment: StudentPayment, *, actor, amount, reason: str, refund_date: dt.date | None = None,
                   method: str | None = None, reservation=None, idempotency_key: str | None = None) -> StudentPayment:
    """Возврат денег из нераспределённого остатка платежа (аванса).
    Оформляется как `StudentPayment(kind=REFUND, refund_of=…)`, аванс
    уменьшается записью REFUND. Ограничение бухгалтера —
    `BILLING_ACCOUNTANT_REFUND_LIMIT` (пусто — без ограничения)."""
    from ..permissions import authorize, is_system_admin

    authorize(actor, "refund")
    amount = _amount(amount)
    reason = (reason or "").strip()
    if not reason:
        raise BillingError("Укажите основание возврата.", code="reason_required")
    from ..models import BillingSettings

    limit = BillingSettings.load().accountant_refund_limit
    if limit is not None and amount > limit and not is_system_admin(actor):
        raise BillingError(f"Возврат больше {limit} сом — нужно решение администратора системы.", code="refund_limit")
    if payment.billing_profile_id is None:
        raise BillingError("Платёж не относится к оплате обучения по пакетам.", code="not_billing")
    refund_date = refund_date or timezone.localdate()
    key = (idempotency_key or "").strip()[:64] or None
    if key:
        existing = StudentPayment.objects.filter(idempotency_key=key).first()
        if existing is not None:
            if existing.refund_of_id != payment.pk or existing.amount != amount:
                raise BillingError("Ключ запроса уже использован.", code="idempotency_conflict")
            return existing
    with transaction.atomic():
        profile = lock_profile(payment.billing_profile_id)
        payment = StudentPayment.objects.select_for_update().get(pk=payment.pk)
        if payment.status != StudentPayment.Status.CONFIRMED or payment.kind != StudentPayment.Kind.PAYMENT:
            raise BillingError("Возврат — только по подтверждённому платежу.", code="bad_status")
        if refund_date < payment.received_date:
            raise BillingError("Дата возврата раньше даты платежа.", code="bad_date")
        if amount > payment_unallocated(payment.pk):
            raise BillingError(
                "Сумма больше нераспределённого остатка платежа — сначала сторнируйте распределение.",
                code="exceeds_payment",
            )
        refund = StudentPayment.objects.create(
            student=payment.student, group=payment.group, course=payment.course, kind=StudentPayment.Kind.REFUND,
            amount=amount, received_date=refund_date, refund_of=payment, method=method or payment.method,
            comment=reason, created_by=actor, billing_profile=profile, purpose=payment.purpose, idempotency_key=key,
        )
        add_entry(profile, Kind.REFUND, amount, payment=payment, actor=actor, reservation=reservation, refund=refund,
                  comment=reason)
        audit.log(actor, refund, "billing_refund", new={"refund_of": payment.pk, "amount": amount}, reason=reason)
        from .receipts import issue_receipt

        issue_receipt(refund, actor=actor)
    return refund


def reverse_refund(refund: StudentPayment, *, actor, reason: str) -> StudentPayment:
    """Отмена ошибочно оформленного возврата: деньги снова в авансе."""
    from ..permissions import authorize

    authorize(actor, "refund")
    reason = (reason or "").strip()
    if not reason:
        raise BillingError("Укажите причину.", code="reason_required")
    with transaction.atomic():
        profile = lock_profile(refund.billing_profile_id)
        refund = StudentPayment.objects.select_for_update().get(pk=refund.pk)
        if refund.kind != StudentPayment.Kind.REFUND or refund.status != StudentPayment.Status.CONFIRMED:
            raise BillingError("Это не действующий возврат.", code="bad_status")
        refund.status = StudentPayment.Status.VOID
        refund.void_reason, refund.voided_by, refund.voided_at = reason, actor, timezone.now()
        refund.save()
        # Компенсирующая запись: возврат отменён — деньги снова в авансе.
        add_entry(profile, Kind.REFUND_REVERSAL, refund.amount, payment=refund.refund_of, refund=refund, actor=actor,
                  comment=f"Отмена возврата: {reason}")
        from .receipts import cancel_receipt

        cancel_receipt(refund, actor=actor, reason=reason)
        audit.log(actor, refund, "billing_refund_reverse", reason=reason)
    return refund


# ---------------------------------------------------------------------------
# Предпросмотр платежа (без записи)
# ---------------------------------------------------------------------------

def preview_payment(profile: StudentBillingProfile, *, amount, invoice: Invoice | None = None,
                    mode: str = "auto") -> dict:
    """Что произойдёт при сохранении платежа — ничего не записывая.

    `mode`: auto и advance (предоплата) — на выставленные неоплаченные
    начисления по порядку, остаток — аванс на будущие месяцы; invoice —
    сначала на выбранное начисление, остаток — на остальные по порядку, затем
    аванс (так же, как `record_payment`)."""
    from .contracts import money_summary

    amount = _amount(amount)
    summary = money_summary(profile)
    unpaid = list(
        Invoice.objects.filter(profile=profile, status__in=Invoice.UNPAID_STATUSES)
        .select_related("package").order_by("package__number", "due_date", "pk")
    )
    if mode == "invoice":
        if invoice is None or invoice.profile_id != profile.pk:
            raise BillingError("Выберите начисление этого студента.", code="wrong_profile")
        first = [invoice] if invoice.status in Invoice.UNPAID_STATUSES else []
        targets = first + [inv for inv in unpaid if inv.pk != invoice.pk]
    else:
        targets = unpaid
    left, rows = amount, []
    for inv in targets:
        if left <= 0:
            break
        part = min(left, inv.balance)
        left -= part
        rows.append({
            "invoice": inv.pk, "number": inv.number, "kind": inv.kind,
            "month_number": inv.package.month_number, "package_number": inv.package.number,
            "obligation": str(inv.amount), "paid_before": str(inv.amount_paid + inv.amount_adjusted),
            "payment": str(part), "balance_after": str(inv.balance - part),
        })
    obligation = sum((inv.amount for inv in targets), ZERO) if targets else ZERO
    paid_before = sum((inv.amount_paid + inv.amount_adjusted for inv in targets), ZERO) if targets else ZERO
    due_after = summary["due_now"] - (amount - left)
    outstanding_after = summary["outstanding"] - amount if summary["final_course_price"] is not None else due_after
    return {
        "amount": str(amount), "mode": mode, "obligation": str(obligation), "paid_before": str(paid_before),
        "obligation_balance_after": str(max(obligation - paid_before - (amount - left), ZERO)),
        "allocations": rows, "to_credit": str(left),
        "due_now_before": str(summary["due_now"]), "due_now_after": str(max(due_after, ZERO)),
        "credit_before": str(summary["credit"]), "credit_after": str(summary["credit"] + left),
        "outstanding_before": str(summary["outstanding"]), "outstanding_after": str(max(outstanding_after, ZERO)),
    }
