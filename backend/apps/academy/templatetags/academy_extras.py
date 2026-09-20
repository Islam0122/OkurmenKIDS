"""Small template-only helpers for the academy admin screens."""
from __future__ import annotations

from django import template

register = template.Library()


@register.filter
def ru_percent(value) -> str:
    """`94.4` -> `94,4%`, `100` -> `100%` — Russian decimal comma, since
    Django's own `floatformat` always uses a period."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return value
    text = f"{number:g}".replace(".", ",")
    return f"{text}%"
