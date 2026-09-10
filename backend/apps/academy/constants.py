"""Canonical Mon-Sun weekday codes, as stored in `Group.days_of_week`.

Every place that needs to map a code <-> a calendar date (lesson
generation, the admin schedule grid, the Group schedule API) must import
these from here rather than redefining its own list or labels — one
mapping, used everywhere, keeps "mon"/"tue"/... meaning the same thing
across the whole app.

Always resolve a `datetime.date` to its code via `date.weekday()`
(0=Monday..6=Sunday, locale-independent) — never `strftime("%a")`/`"%A"`,
which can come back localized (e.g. Russian) depending on the server's
locale setting and would silently break the mon/tue/... matching.
"""
from __future__ import annotations

import datetime as dt

WEEKDAY_CODES = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]

WEEKDAY_LABELS_SHORT = {
    "mon": "Пн",
    "tue": "Вт",
    "wed": "Ср",
    "thu": "Чт",
    "fri": "Пт",
    "sat": "Сб",
    "sun": "Вс",
}

WEEKDAY_LABELS_FULL = {
    "mon": "Понедельник",
    "tue": "Вторник",
    "wed": "Среда",
    "thu": "Четверг",
    "fri": "Пятница",
    "sat": "Суббота",
    "sun": "Воскресенье",
}


def weekday_code_for_date(value: dt.date) -> str:
    """The stable mon/tue/.../sun code for `value` — via `.weekday()`, never locale-dependent."""
    return WEEKDAY_CODES[value.weekday()]
