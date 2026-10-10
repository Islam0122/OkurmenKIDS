"""Денежная арифметика: только Decimal, одно правило округления."""
from __future__ import annotations

import datetime as dt
from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings

ZERO = Decimal("0.00")


def quantum() -> Decimal:
    """Шаг округления сумм (по умолчанию — тыйын, 0.01 сома)."""
    return Decimal(str(getattr(settings, "ACCOUNTING_ROUNDING_QUANTUM", "0.01")))


def money(value) -> Decimal:
    """Округление денежной суммы: половина — вверх (ROUND_HALF_UP)."""
    return Decimal(value).quantize(quantum(), rounding=ROUND_HALF_UP)


def allocate_by_days(amount: Decimal, start: dt.date, end: dt.date, part_start: dt.date, part_end: dt.date) -> Decimal:
    """Доля суммы `amount`, распределённой поровну по дням [start, end],
    приходящаяся на дни [part_start, part_end].

    Используется накопительное округление: доля = round(сумма до конца
    части) − round(сумма до начала части). Поэтому доли всех периодов в
    сумме всегда дают ровно `amount`, без «потерянных» тыйынов.
    """
    lo, hi = max(start, part_start), min(end, part_end)
    if lo > hi:
        return ZERO
    total_days = (end - start).days + 1
    before = (lo - start).days
    through = (hi - start).days + 1
    return money(amount * through / total_days) - money(amount * before / total_days)
