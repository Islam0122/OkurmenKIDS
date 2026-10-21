"""Журнал аванса. Каждая запись ссылается на платёж — источник денег,
поэтому видно и общий аванс профиля, и нераспределённый остаток каждого
платежа (FIFO при оплате из аванса):

    аванс профиля          = Σ записей профиля
    нераспределено платежа = Σ записей платежа
                           = сумма − действующие распределения − возвраты − удержания
"""
from __future__ import annotations

from decimal import Decimal

from django.db.models import Sum

from ..models import CreditLedgerEntry

ZERO = Decimal("0.00")
Kind = CreditLedgerEntry.Kind


def credit_balance(profile_id: int) -> Decimal:
    total = CreditLedgerEntry.objects.filter(profile_id=profile_id).aggregate(s=Sum("amount"))["s"]
    return total or ZERO


def payment_unallocated(payment_id: int) -> Decimal:
    total = CreditLedgerEntry.objects.filter(payment_id=payment_id).aggregate(s=Sum("amount"))["s"]
    return total or ZERO


def add_entry(profile, kind: str, amount: Decimal, *, payment, actor=None, allocation=None, reservation=None,
              refund=None, comment: str = "") -> CreditLedgerEntry:
    """Добавить запись; `amount` — модуль суммы, знак задаёт вид записи.
    Вызывается только под блокировкой профиля."""
    amount = Decimal(amount)
    if amount <= 0:
        raise ValueError("ledger amount must be positive")
    return CreditLedgerEntry.objects.create(
        profile=profile, kind=kind, amount=amount * CreditLedgerEntry.SIGN[kind], payment=payment,
        allocation=allocation, reservation=reservation, refund=refund, comment=comment,
        created_by=actor if getattr(actor, "is_authenticated", False) else None,
    )
