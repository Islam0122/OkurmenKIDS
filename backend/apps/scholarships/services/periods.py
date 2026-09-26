"""Evaluation-period arithmetic — pure date functions, no database access.

Policy (see docs/scholarships.md → «Период оценки»): the cycle awarded on
day D of a month evaluates the one-month window that ended the day before:

    award date 2026-10-01 (D=1)  → 2026-09-01 … 2026-09-30  (previous calendar month)
    award date 2026-10-15 (D=15) → 2026-09-15 … 2026-10-14

D is always 1 or 15, so "day D of the previous month" always exists and
February/leap years need no special handling beyond what `date` already
does. The period always ends strictly before the award date, so the
current, still-running month can never be evaluated as completed.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from ..models import AWARD_DAYS_BY_MODE, AwardMode


@dataclass(frozen=True)
class CycleWindow:
    award_day: int
    award_date: dt.date
    period_start: dt.date
    period_end: dt.date


def _previous_month(year: int, month: int) -> tuple[int, int]:
    return (year - 1, 12) if month == 1 else (year, month - 1)


def cycle_window(award_day: int, award_date: dt.date) -> CycleWindow:
    """The completed period evaluated by the cycle awarded on `award_date`."""
    valid_days = {day for days in AWARD_DAYS_BY_MODE.values() for day in days}
    if award_day not in valid_days:
        raise ValueError(f"Неподдерживаемый день начисления: {award_day}.")
    if award_date.day != award_day:
        raise ValueError(
            f"Дата начисления {award_date:%d.%m.%Y} не совпадает с днём цикла ({award_day}-е число)."
        )
    year, month = _previous_month(award_date.year, award_date.month)
    period_start = dt.date(year, month, award_day)
    period_end = award_date - dt.timedelta(days=1)
    return CycleWindow(award_day, award_date, period_start, period_end)


def latest_award_date(award_day: int, today: dt.date) -> dt.date:
    """The most recent date (<= today) on which the `award_day` cycle ran."""
    if today.day >= award_day:
        return dt.date(today.year, today.month, award_day)
    year, month = _previous_month(today.year, today.month)
    return dt.date(year, month, award_day)


def due_cycles(award_mode: str, today: dt.date) -> list[CycleWindow]:
    """Every configured cycle whose latest award date has arrived.

    Returning the *latest* window for each configured day (rather than only
    "today's") makes the daily scheduled run self-healing: if the job did
    not run on the 1st, the next day's run still generates the missed
    period, and generation itself is idempotent, so re-running is harmless.
    """
    days = AWARD_DAYS_BY_MODE[AwardMode(award_mode)]
    return [cycle_window(day, latest_award_date(day, today)) for day in days]
