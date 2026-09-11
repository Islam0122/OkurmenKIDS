"""Period + comparison-period resolution — pure date-range math, no queries.

Given a period key (or explicit custom dates) plus an optional comparison
mode, resolves two concrete date ranges: the requested period and the
period it should be compared against. Everything downstream (see
``scope.AnalyticsScope``) treats both ranges identically — a "comparison"
is just running the same calculation twice, once per range (see
``dashboard.get_dashboard``).
"""
from __future__ import annotations

import dataclasses
import datetime as dt

PERIOD_CHOICES = (
    "today",
    "yesterday",
    "last_7_days",
    "this_week",
    "last_week",
    "this_month",
    "last_month",
    "custom",
)

COMPARE_CHOICES = (
    "previous_period",
    "previous_month",
    "previous_week",
    "custom",
)


@dataclasses.dataclass(frozen=True)
class DateRange:
    """An inclusive [start, end] date range."""

    start: dt.date
    end: dt.date

    def __post_init__(self) -> None:
        if self.end < self.start:
            raise ValueError(f"DateRange end ({self.end}) is before start ({self.start}).")

    @property
    def days(self) -> int:
        return (self.end - self.start).days + 1


def _week_start(day: dt.date) -> dt.date:
    """Monday of `day`'s week — locale-independent (`.weekday()`, never
    `strftime`), same convention as apps.academy.constants."""
    return day - dt.timedelta(days=day.weekday())


def resolve_period(
    period: str,
    *,
    today: dt.date,
    start_date: dt.date | None = None,
    end_date: dt.date | None = None,
) -> DateRange:
    """Turn a period key into a concrete DateRange, anchored on `today`."""
    if period == "today":
        return DateRange(today, today)
    if period == "yesterday":
        yesterday = today - dt.timedelta(days=1)
        return DateRange(yesterday, yesterday)
    if period == "last_7_days":
        return DateRange(today - dt.timedelta(days=6), today)
    if period == "this_week":
        start = _week_start(today)
        return DateRange(start, start + dt.timedelta(days=6))
    if period == "last_week":
        start = _week_start(today) - dt.timedelta(days=7)
        return DateRange(start, start + dt.timedelta(days=6))
    if period == "this_month":
        start = today.replace(day=1)
        return DateRange(start, today)
    if period == "last_month":
        this_month_start = today.replace(day=1)
        end = this_month_start - dt.timedelta(days=1)
        return DateRange(end.replace(day=1), end)
    if period == "custom":
        if start_date is None or end_date is None:
            raise ValueError("period='custom' requires both start_date and end_date.")
        if end_date < start_date:
            start_date, end_date = end_date, start_date
        return DateRange(start_date, end_date)
    raise ValueError(f"Unknown period: {period!r}")


def resolve_comparison(
    range_: DateRange,
    compare: str | None,
    *,
    compare_start: dt.date | None = None,
    compare_end: dt.date | None = None,
) -> DateRange | None:
    """The DateRange `range_` should be compared against, or None for no
    comparison at all.

    - "previous_period": the same number of days immediately before `range_`
      (e.g. a 7-day range compares against the 7 days before it).
    - "previous_week"/"previous_month": `range_` shifted back exactly one
      week/calendar month. For "previous_month" the comparison range starts
      on the 1st of the previous calendar month and runs for the same
      number of days as `range_` (capped to that month's last day) — so
      "this_month" (Sep 1 -> today) compares against "Aug 1 -> same day
      count", matching the spec's "September 2026 vs August 2026" example
      when `range_` is a full calendar month.
    - "custom": an explicit, caller-supplied range.
    """
    if compare is None:
        return None
    if compare == "custom":
        if compare_start is None or compare_end is None:
            raise ValueError("compare='custom' requires both compare_start and compare_end.")
        if compare_end < compare_start:
            compare_start, compare_end = compare_end, compare_start
        return DateRange(compare_start, compare_end)
    if compare == "previous_period":
        end = range_.start - dt.timedelta(days=1)
        start = end - dt.timedelta(days=range_.days - 1)
        return DateRange(start, end)
    if compare == "previous_week":
        return DateRange(range_.start - dt.timedelta(days=7), range_.end - dt.timedelta(days=7))
    if compare == "previous_month":
        prev_month_end = range_.start.replace(day=1) - dt.timedelta(days=1)
        prev_month_start = prev_month_end.replace(day=1)
        end = min(prev_month_start + dt.timedelta(days=range_.days - 1), prev_month_end)
        return DateRange(prev_month_start, end)
    raise ValueError(f"Unknown compare mode: {compare!r}")
