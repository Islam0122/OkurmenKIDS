"""Утверждение, возврат на исправление, переоткрытие, аннулирование
расчётов и корректировки начислений."""
from __future__ import annotations

from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from ..models import CycleAccrual, Payroll, PayrollAdjustment, PayrollPayment, PayrollPeriod
from . import AccountingError, audit
from .payroll_calculator import refresh_totals
from .periods import sync_period_status

TOTALS = ("status", "total_accrued", "total_adjustments", "total_paid", "amount_due")


def _locked(payroll: Payroll) -> Payroll:
    payroll = Payroll.objects.select_for_update().select_related("period").get(pk=payroll.pk)
    if payroll.period.status == PayrollPeriod.Status.CLOSED:
        raise AccountingError("Период закрыт — расчёты в нём больше не меняются.", code="period_closed")
    return payroll


def _require_reason(reason: str) -> str:
    reason = (reason or "").strip()
    if not reason:
        raise AccountingError("Укажите причину.", code="reason_required")
    return reason


def paid_status(payroll: Payroll) -> str:
    if payroll.total_paid <= 0:
        return Payroll.Status.APPROVED
    return Payroll.Status.PAID if payroll.amount_due <= 0 else Payroll.Status.PARTIALLY_PAID


def approve_payroll(payroll: Payroll, actor) -> Payroll:
    with transaction.atomic():
        payroll = _locked(payroll)
        if payroll.employee_id == actor.pk:
            raise AccountingError("Нельзя утверждать собственное начисление.", code="own_payroll")
        if payroll.status != Payroll.Status.CALCULATED:
            raise AccountingError(
                f"Утвердить можно только рассчитанное начисление (сейчас: «{payroll.get_status_display()}»).",
                code="bad_status",
            )
        if payroll.errors:
            raise AccountingError("В расчёте есть ошибки — исправьте их и пересчитайте.", code="has_errors")
        if payroll.adjustments.filter(status=PayrollAdjustment.Status.PENDING).exists():
            raise AccountingError("Есть корректировки, ожидающие решения.", code="pending_adjustments")
        old = audit.snapshot(payroll, TOTALS)
        refresh_totals(payroll)
        payroll.status = Payroll.Status.APPROVED
        payroll.approved_by = actor
        payroll.approved_at = timezone.now()
        payroll.save()
        CycleAccrual.objects.filter(payroll=payroll, status=CycleAccrual.Status.ACCRUED).update(
            status=CycleAccrual.Status.APPROVED,
        )
        audit.log(actor, payroll, "approve", old=old, new={
            **audit.snapshot(payroll, TOTALS),
            "lines": [
                {"type": l.line_type, "description": l.description, "rate": l.rate, "percentage": l.percentage,
                 "base_amount": l.base_amount, "amount": l.amount, "rule": l.salary_rule_id}
                for l in payroll.lines.all()
            ],
        }, payroll=payroll)
        sync_period_status(payroll.period)
    return payroll


def approve_period(period: PayrollPeriod, actor) -> dict:
    approved, failed = [], []
    for payroll in period.payrolls.filter(status=Payroll.Status.CALCULATED).select_related("employee"):
        try:
            approved.append(approve_payroll(payroll, actor))
        except AccountingError as exc:
            failed.append({"payroll_id": payroll.pk, "employee": str(payroll.employee), "error": exc.message})
    if approved:
        period.refresh_from_db()
        if period.status == PayrollPeriod.Status.APPROVED and period.approved_at is None:
            period.approved_by, period.approved_at = actor, timezone.now()
            period.save(update_fields=["approved_by", "approved_at"])
    return {"approved": approved, "failed": failed}


def return_payroll(payroll: Payroll, actor, reason: str) -> Payroll:
    reason = _require_reason(reason)
    with transaction.atomic():
        payroll = _locked(payroll)
        if payroll.status != Payroll.Status.CALCULATED:
            raise AccountingError("Вернуть на исправление можно только рассчитанное начисление.", code="bad_status")
        old = audit.snapshot(payroll, TOTALS)
        payroll.status = Payroll.Status.RETURNED
        payroll.return_reason = reason
        payroll.save(update_fields=["status", "return_reason", "updated_at"])
        audit.log(actor, payroll, "return", old=old, new={"status": payroll.status}, reason=reason, payroll=payroll)
    return payroll


def reopen_payroll(payroll: Payroll, actor, reason: str) -> Payroll:
    """Контролируемое переоткрытие утверждённого расчёта (без выплат): он
    снова становится рассчитанным и может быть пересчитан. Прежние итоги
    и строки остаются в журнале аудита (запись approve)."""
    reason = _require_reason(reason)
    with transaction.atomic():
        payroll = _locked(payroll)
        if payroll.status != Payroll.Status.APPROVED:
            raise AccountingError("Переоткрыть можно только утверждённое начисление без выплат.", code="bad_status")
        if payroll.payments.filter(status=PayrollPayment.Status.CONFIRMED).exists():
            raise AccountingError("По начислению уже есть выплаты — используйте корректировку.", code="has_payments")
        old = audit.snapshot(payroll, TOTALS)
        payroll.status = Payroll.Status.CALCULATED
        payroll.approved_by = None
        payroll.approved_at = None
        payroll.save()
        CycleAccrual.objects.filter(payroll=payroll, status=CycleAccrual.Status.APPROVED).update(
            status=CycleAccrual.Status.ACCRUED,
        )
        # Ждущее сторно отменённого цикла больше не нужно: после пересчёта
        # строки этого цикла в расчёте просто не будет.
        for accrual in CycleAccrual.objects.filter(
            payroll=payroll, status=CycleAccrual.Status.CORRECTED, adjustment__status=PayrollAdjustment.Status.PENDING,
        ).select_related("adjustment"):
            accrual.adjustment.status = PayrollAdjustment.Status.VOID
            accrual.adjustment.decided_by, accrual.adjustment.decided_at = actor, timezone.now()
            accrual.adjustment.save()
            accrual.status = CycleAccrual.Status.CANCELLED
            accrual.save()
            audit.log(actor, accrual, "cancel", old={"status": CycleAccrual.Status.CORRECTED},
                      new={"status": accrual.status}, reason="Расчёт переоткрыт — сторно не требуется.",
                      payroll=payroll)
        audit.log(actor, payroll, "reopen", old=old, new={"status": payroll.status}, reason=reason, payroll=payroll)
        sync_period_status(payroll.period)
    return payroll


def void_payroll(payroll: Payroll, actor, reason: str) -> Payroll:
    reason = _require_reason(reason)
    with transaction.atomic():
        payroll = _locked(payroll)
        if not payroll.is_editable:
            raise AccountingError("Аннулировать можно только неутверждённое начисление.", code="bad_status")
        old = audit.snapshot(payroll, TOTALS)
        payroll.status = Payroll.Status.VOID
        payroll.save(update_fields=["status", "updated_at"])
        # Начисления за циклы освобождаются и попадут в следующий расчёт.
        CycleAccrual.objects.filter(payroll=payroll, status=CycleAccrual.Status.ACCRUED).update(
            payroll=None, line=None,
        )
        audit.log(actor, payroll, "void", old=old, new={"status": payroll.status}, reason=reason, payroll=payroll)
        sync_period_status(payroll.period)
    return payroll


# ---------------------------------------------------------------------------
# Корректировки
# ---------------------------------------------------------------------------

def _signed(kind: str, amount: Decimal) -> Decimal:
    if kind == PayrollAdjustment.Kind.CORRECTION:
        if amount == 0:
            raise AccountingError("Сумма исправления не может быть нулевой.")
        return amount
    if amount <= 0:
        raise AccountingError("Сумма должна быть больше нуля.")
    return -amount if kind == PayrollAdjustment.Kind.DEDUCTION else amount


def _apply(payroll: Payroll, adjustment: PayrollAdjustment):
    refresh_totals(payroll)
    if payroll.amount_due < 0:
        raise AccountingError(
            "После корректировки остаток станет отрицательным — сумма удержания больше невыплаченной части.",
            code="negative_due",
        )
    if payroll.is_locked:
        payroll.status = paid_status(payroll)
    payroll.save()


def create_adjustment(payroll: Payroll, *, kind: str, amount: Decimal, reason: str, actor) -> PayrollAdjustment:
    reason = _require_reason(reason)
    if kind not in PayrollAdjustment.Kind.values:
        raise AccountingError("Неизвестный тип корректировки.")
    signed = _signed(kind, Decimal(amount))
    with transaction.atomic():
        payroll = _locked(payroll)
        if payroll.employee_id == actor.pk:
            raise AccountingError("Нельзя корректировать собственное начисление.", code="own_payroll")
        if payroll.status == Payroll.Status.VOID:
            raise AccountingError("Начисление аннулировано.", code="bad_status")
        status = PayrollAdjustment.Status.APPLIED if payroll.is_editable else PayrollAdjustment.Status.PENDING
        adjustment = PayrollAdjustment.objects.create(
            payroll=payroll, kind=kind, amount=signed, reason=reason, status=status, created_by=actor,
        )
        if status == PayrollAdjustment.Status.APPLIED:
            _apply(payroll, adjustment)
        audit.log(actor, adjustment, "create", new={"kind": kind, "amount": signed, "status": status},
                  reason=reason, payroll=payroll)
    return adjustment


def decide_adjustment(adjustment: PayrollAdjustment, *, approve: bool, actor, reason: str = "") -> PayrollAdjustment:
    """Решение директора по корректировке утверждённого начисления."""
    with transaction.atomic():
        payroll = _locked(adjustment.payroll)
        adjustment = PayrollAdjustment.objects.select_for_update().get(pk=adjustment.pk)
        if adjustment.status != PayrollAdjustment.Status.PENDING:
            raise AccountingError("Корректировка уже обработана.", code="bad_status")
        if payroll.employee_id == actor.pk:
            raise AccountingError("Нельзя утверждать корректировку собственного начисления.", code="own_payroll")
        old = audit.snapshot(payroll, TOTALS)
        adjustment.status = PayrollAdjustment.Status.APPLIED if approve else PayrollAdjustment.Status.REJECTED
        adjustment.decided_by, adjustment.decided_at = actor, timezone.now()
        adjustment.save()
        if approve:
            _apply(payroll, adjustment)
        else:
            # Директор отклонил автоматическое сторно — начисление за цикл остаётся в силе.
            CycleAccrual.objects.filter(adjustment=adjustment).update(
                status=CycleAccrual.Status.APPROVED, note="Сторно отклонено директором.",
            )
        audit.log(actor, adjustment, "approve" if approve else "reject", old=old,
                  new={"status": adjustment.status, **audit.snapshot(payroll, TOTALS)}, reason=reason, payroll=payroll)
    return adjustment


def void_adjustment(adjustment: PayrollAdjustment, *, actor, reason: str) -> PayrollAdjustment:
    reason = _require_reason(reason)
    with transaction.atomic():
        payroll = _locked(adjustment.payroll)
        adjustment = PayrollAdjustment.objects.select_for_update().get(pk=adjustment.pk)
        if adjustment.status == PayrollAdjustment.Status.PENDING:
            pass
        elif adjustment.status == PayrollAdjustment.Status.APPLIED and payroll.is_editable:
            pass
        else:
            raise AccountingError(
                "Отменить можно ожидающую корректировку или применённую к неутверждённому начислению.",
                code="bad_status",
            )
        old_status = adjustment.status
        adjustment.status = PayrollAdjustment.Status.VOID
        adjustment.decided_by, adjustment.decided_at = actor, timezone.now()
        adjustment.save()
        refresh_totals(payroll)
        payroll.save()
        audit.log(actor, adjustment, "void", old={"status": old_status}, new={"status": adjustment.status},
                  reason=reason, payroll=payroll)
    return adjustment
