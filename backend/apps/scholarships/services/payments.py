"""Scholarship payments — recording that the money was actually handed over.

An award goes through two independent states:

* **начислена** — `ScholarshipAward.status`: pending while the period is a
  draft, approved once the period is approved (services.generation);
* **выдана** — `ScholarshipAward.payment_status`: unpaid → paid, set here.

Only an approved award can be paid (a draft period's list can still be
recalculated, which would drop the award), and only once: the UPDATE is
conditional on `payment_status = unpaid`, so two admins paying the same
student at the same moment still produce exactly one payment. A database
check constraint backs this up.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from django.db import transaction
from django.db.models import F
from django.utils import timezone

from ..models import PaymentMethod, PaymentStatus, ScholarshipAward, ScholarshipRunLog
from .generation import ScholarshipError, _log

COMMENT_MAX_LENGTH = 500


@dataclass
class PaymentResult:
    paid: list[ScholarshipAward] = field(default_factory=list)
    already_paid: list[ScholarshipAward] = field(default_factory=list)
    not_approved: list[ScholarshipAward] = field(default_factory=list)

    @property
    def skipped(self) -> int:
        return len(self.already_paid) + len(self.not_approved)


def _clean(method: str, comment: str) -> tuple[str, str]:
    if method not in PaymentMethod.values:
        raise ScholarshipError("Выберите способ выплаты.")
    comment = (comment or "").strip()
    if len(comment) > COMMENT_MAX_LENGTH:
        raise ScholarshipError(f"Комментарий — не длиннее {COMMENT_MAX_LENGTH} символов.")
    return method, comment


def pay_awards(award_ids, *, method: str, comment: str = "", user=None,
               trigger: str = ScholarshipRunLog.Trigger.ADMIN) -> PaymentResult:
    """Mark the given awards as paid. Awards that are already paid or not
    approved yet are skipped (and reported), never paid twice."""
    method, comment = _clean(method, comment)
    ids = sorted({int(pk) for pk in award_ids})
    if not ids:
        raise ScholarshipError("Не выбрано ни одной стипендии.")
    payer = user if getattr(user, "is_authenticated", False) else None
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
            else:
                payable.append(award)
        if payable:
            updated = ScholarshipAward.objects.filter(
                pk__in=[a.pk for a in payable],
                payment_status=PaymentStatus.UNPAID,
                status=ScholarshipAward.Status.APPROVED,
            ).update(
                payment_status=PaymentStatus.PAID, paid_at=now, paid_by=payer, paid_amount=F("amount"),
                payment_method=method, payment_comment=comment, updated_at=now,
            )
            if updated != len(payable):  # pragma: no cover — guarded by the row lock
                raise ScholarshipError("Список стипендий изменился — обновите страницу и повторите.")
            result.paid = payable

    by_period = defaultdict(list)
    for award in result.paid:
        by_period[award.period].append(award.evaluation.student_name)
    label = PaymentMethod(method).label.lower()
    for period, names in by_period.items():
        _log(
            ScholarshipRunLog.Action.PAYMENT, trigger, ScholarshipRunLog.Result.SUCCESS, period=period, user=user,
            message=f"Выдано стипендий: {len(names)} ({label}): {', '.join(names)}."
            + (f" Комментарий: {comment}" if comment else ""),
        )
    return result


def cancel_payment(award: ScholarshipAward, *, user=None,
                   trigger: str = ScholarshipRunLog.Trigger.ADMIN) -> ScholarshipAward:
    """Undo a payment recorded by mistake. The previous payment details go
    to the run log, so nothing is lost silently."""
    with transaction.atomic():
        locked = ScholarshipAward.objects.select_for_update().select_related("evaluation", "period").get(pk=award.pk)
        if not locked.is_paid:
            raise ScholarshipError("Эта стипендия ещё не выдана.")
        details = (
            f"{locked.evaluation.student_name}: отменена выдача от "
            f"{timezone.localtime(locked.paid_at):%d.%m.%Y %H:%M} ({locked.get_payment_method_display().lower()})."
        )
        locked.payment_status = PaymentStatus.UNPAID
        locked.paid_at = None
        locked.paid_by = None
        locked.paid_amount = None
        locked.payment_method = ""
        locked.payment_comment = ""
        locked.save(update_fields=[
            "payment_status", "paid_at", "paid_by", "paid_amount", "payment_method", "payment_comment", "updated_at",
        ])
    _log(ScholarshipRunLog.Action.PAYMENT, trigger, ScholarshipRunLog.Result.SUCCESS, period=locked.period,
         message=details, user=user)
    return locked
