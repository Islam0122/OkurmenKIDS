"""Reporting period + its comparable previous period.

The quick filters are the same keys as the group KPI (services.analytics.
period.resolve_period), so a report for «Этот месяц» covers exactly the
dates the KPI tab shows. The previous period is the *equivalent* one —
the same mapping the per-student progress table already uses
(student_progress._COMPARE_FOR_PERIOD): a month against the previous month
(same number of days), a week against the previous week, a custom or
rolling range against the same number of days right before it.
"""
from __future__ import annotations

import dataclasses
import datetime as dt

from apps.academy.services.analytics.period import DateRange, resolve_comparison, resolve_period
from apps.academy.services.analytics.student_progress import _COMPARE_FOR_PERIOD

PERIOD_KEYS = ("today", "last_7_days", "this_week", "last_week", "this_month", "last_month", "custom")
MONTHLY_KEYS = ("this_month", "last_month")
MAX_RANGE_DAYS = 366
EARLIEST_DATE = dt.date(2015, 1, 1)


class PeriodError(ValueError):
    """Invalid period request — the message is shown to the user as is."""

    def __init__(self, message: str, field: str = "period"):
        super().__init__(message)
        self.field = field


@dataclasses.dataclass(frozen=True)
class ReportPeriod:
    key: str
    current: DateRange
    previous: DateRange

    @property
    def is_monthly(self) -> bool:
        if self.key in MONTHLY_KEYS:
            return True
        # A custom range that is exactly one calendar month.
        start, end = self.current.start, self.current.end
        next_month = (end.replace(day=28) + dt.timedelta(days=4)).replace(day=1)
        return self.key == "custom" and start.day == 1 and end == next_month - dt.timedelta(days=1)


def resolve(
    key: str, *, today: dt.date, start_date: dt.date | None = None, end_date: dt.date | None = None,
) -> ReportPeriod:
    if key not in PERIOD_KEYS:
        raise PeriodError("Неизвестный период.")
    if key == "custom":
        if start_date is None or end_date is None:
            raise PeriodError("Укажите даты начала и окончания периода.", "start_date")
        if start_date > end_date:
            raise PeriodError("Дата начала не может быть позже даты окончания.", "start_date")
        if start_date < EARLIEST_DATE:
            raise PeriodError("Слишком ранняя дата начала периода.", "start_date")
        if (end_date - start_date).days + 1 > MAX_RANGE_DAYS:
            raise PeriodError("Период отчёта не может быть длиннее одного года.", "end_date")
    current = resolve_period(key, today=today, start_date=start_date, end_date=end_date)
    if current.start > today:
        raise PeriodError("Период ещё не начался — отчёт строится только по прошедшим занятиям.", "start_date")
    previous = resolve_comparison(current, _COMPARE_FOR_PERIOD.get(key, "previous_period"))
    return ReportPeriod(key=key, current=current, previous=previous)
