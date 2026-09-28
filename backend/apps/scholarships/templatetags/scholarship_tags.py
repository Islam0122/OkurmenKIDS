"""Number formatting for the scholarship admin pages."""
from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from django import template

register = template.Library()

_NBSP = " "


@register.filter
def som(value) -> str:
    """52500 → «52 500 сом»; empty → «—»."""
    if value in (None, ""):
        return "—"
    amount = Decimal(value).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return f"{amount:,}".replace(",", _NBSP) + f"{_NBSP}сом"


@register.filter
def score(value) -> str:
    """A 0–100 score with one decimal: 86.456 → «86.5»; empty → «—»."""
    if value in (None, ""):
        return "—"
    return str(Decimal(value).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))


@register.filter
def percent_of(part, whole) -> int:
    """How full the limit is, for the progress bar (0–100)."""
    if not whole:
        return 0
    return max(0, min(100, round((part or 0) * 100 / whole)))


@register.filter
def short_range(period) -> str:
    """A period as «01.08–31.08» for tight table cells."""
    from ..services.report import short_range as _short
    return _short(period.period_start, period.period_end)


@register.filter
def plain_number(value) -> str:
    """A Decimal for a data-* attribute / JS: «1500.00» → «1500»; empty → «0»."""
    if value in (None, ""):
        return "0"
    return str(Decimal(value).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
