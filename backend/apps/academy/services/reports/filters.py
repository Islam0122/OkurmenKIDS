"""Report filters: the period vocabulary plus program/group/teacher/subject.

Period math reuses `analytics.period.resolve_period` (the one place the
Analytics Dashboard already resolves "today"/"this week"/"this month"/...),
adding only the one key the Reports section needs on top of it:
"this_quarter". Every Reports screen, API endpoint and export parses its
query string through `ReportFilters.from_query`, so the same URL always
means the same numbers everywhere.
"""
from __future__ import annotations

import dataclasses
import datetime as dt

from django.utils import timezone

from apps.academy.services.analytics.period import DateRange, resolve_period
from apps.academy.services.analytics.scope import AnalyticsScope

PERIOD_TODAY = "today"
PERIOD_THIS_WEEK = "this_week"
PERIOD_THIS_MONTH = "this_month"
PERIOD_LAST_MONTH = "last_month"
PERIOD_THIS_QUARTER = "this_quarter"
PERIOD_CUSTOM = "custom"

PERIOD_CHOICES = [
    (PERIOD_TODAY, "Сегодня"),
    (PERIOD_THIS_WEEK, "Эта неделя"),
    (PERIOD_THIS_MONTH, "Этот месяц"),
    (PERIOD_LAST_MONTH, "Прошлый месяц"),
    (PERIOD_THIS_QUARTER, "Этот квартал"),
    (PERIOD_CUSTOM, "Свой период"),
]
DEFAULT_PERIOD = PERIOD_THIS_MONTH


class ReportFilterError(ValueError):
    """A query string that can't be turned into a report (e.g. an
    unparseable custom date) — rendered as an error state, never a 500."""


def resolve_report_period(
    period: str, *, today: dt.date, start_date: dt.date | None = None, end_date: dt.date | None = None
) -> DateRange:
    if period == PERIOD_THIS_QUARTER:
        first_month = (today.month - 1) // 3 * 3 + 1
        return DateRange(today.replace(month=first_month, day=1), today)
    return resolve_period(period, today=today, start_date=start_date, end_date=end_date)


def _as_int(params, name: str) -> int | None:
    value = str(params.get(name) or "").strip()
    return int(value) if value.isdigit() else None


def _as_date(params, name: str) -> dt.date | None:
    value = str(params.get(name) or "").strip()
    if not value:
        return None
    try:
        return dt.date.fromisoformat(value)
    except ValueError as exc:
        raise ReportFilterError(f"Некорректная дата: «{value}». Ожидается формат ГГГГ-ММ-ДД.") from exc


@dataclasses.dataclass(frozen=True)
class ReportFilters:
    period: str
    date_range: DateRange
    today: dt.date
    course_id: int | None = None
    group_id: int | None = None
    teacher_id: int | None = None
    subject_id: int | None = None

    @classmethod
    def from_query(cls, params, *, today: dt.date | None = None) -> "ReportFilters":
        today = today or timezone.localdate()
        start = _as_date(params, "start_date")
        end = _as_date(params, "end_date")

        period = str(params.get("period") or "").strip()
        if not period:
            # Explicit dates without a period key mean a custom range.
            period = PERIOD_CUSTOM if (start and end) else DEFAULT_PERIOD
        if period not in dict(PERIOD_CHOICES):
            raise ReportFilterError(f"Неизвестный период: «{period}».")
        if period == PERIOD_CUSTOM and not (start and end):
            raise ReportFilterError("Для своего периода укажите начальную и конечную дату.")

        return cls(
            period=period,
            date_range=resolve_report_period(period, today=today, start_date=start, end_date=end),
            today=today,
            course_id=_as_int(params, "program"),
            group_id=_as_int(params, "group"),
            teacher_id=_as_int(params, "teacher"),
            subject_id=_as_int(params, "subject"),
        )

    @classmethod
    def default(cls, *, today: dt.date | None = None) -> "ReportFilters":
        return cls.from_query({}, today=today)

    @property
    def start(self) -> dt.date:
        return self.date_range.start

    @property
    def end(self) -> dt.date:
        return self.date_range.end

    @property
    def period_label(self) -> str:
        return dict(PERIOD_CHOICES)[self.period]

    def scope(self, **overrides) -> AnalyticsScope:
        """The Analytics Dashboard's own scope — the single place group/
        teacher/course/subject filtering and effective-teacher isolation
        already live (see analytics.scope)."""
        values = {
            "date_range": self.date_range,
            "teacher_id": self.teacher_id,
            "group_id": self.group_id,
            "course_id": self.course_id,
            "subject_id": self.subject_id,
        }
        values.update(overrides)
        return AnalyticsScope(**values)

    def as_query(self) -> dict:
        """Query params that reproduce these filters (links, exports)."""
        query = {"period": self.period}
        if self.period == PERIOD_CUSTOM:
            query["start_date"] = self.start.isoformat()
            query["end_date"] = self.end.isoformat()
        for key, value in (
            ("program", self.course_id),
            ("group", self.group_id),
            ("teacher", self.teacher_id),
            ("subject", self.subject_id),
        ):
            if value:
                query[key] = value
        return query

    def as_dict(self) -> dict:
        return {
            "period": self.period,
            "period_label": self.period_label,
            "start_date": self.start,
            "end_date": self.end,
            "program": self.course_id,
            "group": self.group_id,
            "teacher": self.teacher_id,
            "subject": self.subject_id,
        }
