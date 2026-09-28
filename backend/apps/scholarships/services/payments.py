"""Scholarship payments — recording that the money was actually handed over.

An award goes through two independent states:

* **начислена** — `ScholarshipAward.status`: pending while the period is a
  draft, approved once the period is approved (services.generation);
* **выдана** — `ScholarshipAward.payment_status`: unpaid → paid, set here.

Rules (the database enforces them too, see ScholarshipAward.Meta):

* only an approved award with a positive amount can be paid, and only
  once — the rows are locked (select_for_update) and the UPDATE is
  conditional on `payment_status = unpaid`, so two admins paying the same
  student at the same moment still produce exactly one payment;
* the amount paid is the award's own amount (never anything from the
  request), the payer is the logged-in user, the time is the server's;
* the payment and its journal entry are one transaction: if the journal
  can't be written, nothing is paid;
* cancelling a payment keeps the original payment (amount, payer, time,
  method) and the reason in the journal.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from decimal import Decimal

from django.db import transaction
from django.db.models import F
from django.utils import timezone

from ..models import PaymentMethod, PaymentStatus, ScholarshipAward, ScholarshipRunLog
from ..templatetags.scholarship_tags import som
from .generation import ScholarshipError, _log

COMMENT_MAX_LENGTH = 500
REASON_MAX_LENGTH = 500


@dataclass
class PaymentResult:
    paid: list[ScholarshipAward] = field(default_factory=list)
    already_paid: list[ScholarshipAward] = field(default_factory=list)
    not_approved: list[ScholarshipAward] = field(default_factory=list)
    no_amount: list[ScholarshipAward] = field(default_factory=list)

    @property
    def skipped(self) -> int:
        return len(self.already_paid) + len(self.not_approved) + len(self.no_amount)

    @property
    def paid_total(self) -> Decimal:
        return sum((a.amount for a in self.paid), Decimal("0"))


def _clean(method: str, comment: str) -> tuple[str, str]:
    if method not in PaymentMethod.values:
        raise ScholarshipError("Выберите способ выплаты.")
    comment = (comment or "").strip()
    if len(comment) > COMMENT_MAX_LENGTH:
        raise ScholarshipError(f"Комментарий — не длиннее {COMMENT_MAX_LENGTH} символов.")
    return method, comment


def _payer(user):
    if not getattr(user, "is_authenticated", False):
        raise ScholarshipError("Выдачу может отметить только вошедший администратор.")
    return user, (str(user) or user.get_username())[:150]


def _when(value) -> str:
    return f"{timezone.localtime(value):%d.%m.%Y %H:%M}" if value else ""


def pay_awards(award_ids, *, method: str, comment: str = "", user=None,
               trigger: str = ScholarshipRunLog.Trigger.ADMIN) -> PaymentResult:
    """Mark the given awards as paid. Awards already paid, not approved yet
    or without money (amount 0) are skipped and reported — never paid."""
    method, comment = _clean(method, comment)
    payer, payer_name = _payer(user)
    ids = sorted({int(pk) for pk in award_ids})
    if not ids:
        raise ScholarshipError("Не выбрано ни одной стипендии.")
    now = timezone.now()
    result = PaymentResult()
    with transaction.atomic():
        awards = list(
            ScholarshipAward.objects.select_for_update().filter(pk__in=ids)
            .select_related("evaluation", "period").order_by("pk")
        )
        if not awards:
            raise ScholarshipError("Стипендии не найдены.")
        payable = []
        for award in awards:
            if award.is_paid:
                result.already_paid.append(award)
            elif award.status != ScholarshipAward.Status.APPROVED:
                result.not_approved.append(award)
            elif award.amount is None or award.amount <= 0:
                result.no_amount.append(award)
            else:
                payable.append(award)
        if not payable:
            return result

        updated = ScholarshipAward.objects.filter(
            pk__in=[a.pk for a in payable],
            payment_status=PaymentStatus.UNPAID,
            status=ScholarshipAward.Status.APPROVED,
            amount__gt=0,
        ).update(
            payment_status=PaymentStatus.PAID, paid_at=now, paid_by=payer, paid_by_name=payer_name,
            paid_amount=F("amount"), payment_method=method, payment_comment=comment, updated_at=now,
        )
        if updated != len(payable):  # pragma: no cover — guarded by the row lock
            raise ScholarshipError("Список стипендий изменился — обновите страницу и повторите.")
        result.paid = payable

        # The journal is part of the payment: if it can't be written, the
        # whole transaction — the payment too — is rolled back.
        by_period = defaultdict(list)
        for award in payable:
            by_period[award.period].append(award)
        label = PaymentMethod(method).label
        for period, rows in by_period.items():
            total = sum((a.amount for a in rows), Decimal("0"))
            _log(
                ScholarshipRunLog.Action.PAYMENT, trigger, ScholarshipRunLog.Result.SUCCESS, period=period, user=user,
                message=(
                    f"Выдано стипендий: {len(rows)} на сумму {som(total)} ({label.lower()}), выдал {payer_name}: "
                    + ", ".join(f"{a.evaluation.student_name} ({som(a.amount)})" for a in rows) + "."
                    + (f" Комментарий: {comment}" if comment else "")
                ),
                details={
                    "event": "payment",
                    "paid_at": now.isoformat(),
                    "paid_by_id": payer.pk,
                    "paid_by": payer_name,
                    "payment_method": method,
                    "comment": comment,
                    "total": str(total),
                    "awards": [
                        {"award_id": a.pk, "student_id": a.student_id, "student": a.evaluation.student_name,
                         "amount": str(a.amount)}
                        for a in rows
                    ],
                },
            )
    return result


def cancel_payment(award: ScholarshipAward, *, reason: str, user=None,
                   trigger: str = ScholarshipRunLog.Trigger.ADMIN) -> ScholarshipAward:
    """Undo a payment recorded by mistake. The award goes back to «Не
    выдано»; the original payment and the reason stay in the journal."""
    reason = (reason or "").strip()
    if not reason:
        raise ScholarshipError("Укажите причину отмены выдачи.")
    if len(reason) > REASON_MAX_LENGTH:
        raise ScholarshipError(f"Причина — не длиннее {REASON_MAX_LENGTH} символов.")
    canceller, canceller_name = _payer(user)
    now = timezone.now()
    with transaction.atomic():
        locked = ScholarshipAward.objects.select_for_update().select_related("evaluation", "period").get(pk=award.pk)
        if not locked.is_paid:
            raise ScholarshipError("Эта стипендия ещё не выдана.")
        original = {
            "award_id": locked.pk,
            "student_id": locked.student_id,
            "student": locked.evaluation.student_name,
            "original_amount": str(locked.paid_amount),
            "original_paid_by_id": locked.paid_by_id,
            "original_paid_by": locked.paid_by_label,
            "original_paid_at": locked.paid_at.isoformat(),
            "original_payment_method": locked.payment_method,
            "original_comment": locked.payment_comment,
        }
        message = (
            f"ВЫДАЧА ОТМЕНЕНА. Ученик: {original['student']}. Сумма: {som(locked.paid_amount)}. "
            f"Выдал: {original['original_paid_by']}, {_when(locked.paid_at)}, "
            f"{locked.get_payment_method_display().lower()}. "
            f"Отменил: {canceller_name}, {_when(now)}. Причина: {reason}"
        )
        locked.payment_status = PaymentStatus.UNPAID
        locked.paid_at = None
        locked.paid_by = None
        locked.paid_by_name = ""
        locked.paid_amount = None
        locked.payment_method = ""
        locked.payment_comment = ""
        locked.save(update_fields=[
            "payment_status", "paid_at", "paid_by", "paid_by_name", "paid_amount", "payment_method",
            "payment_comment", "updated_at",
        ])
        _log(
            ScholarshipRunLog.Action.PAYMENT, trigger, ScholarshipRunLog.Result.SUCCESS, period=locked.period,
            user=user, message=message,
            details={
                "event": "payment_cancelled", **original,
                "cancelled_at": now.isoformat(), "cancelled_by_id": canceller.pk, "cancelled_by": canceller_name,
                "reason": reason,
            },
        )
    return locked
