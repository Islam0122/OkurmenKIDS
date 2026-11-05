"""Данные страницы «Общая статистика» за месяц — всё считается здесь, на сервере.

* Прошлые дни — только из снимков (DailyPerformanceSnapshot): история не
  меняется задним числом.
* Сегодняшний день — «живой» расчёт (services.metrics) с учётом ручных
  корректировок сегодняшнего снимка, чтобы панель на телевизоре была
  актуальной и до очередного запуска планировщика.
* Будущие дни месяца — без значений (``is_future``).
"""
from __future__ import annotations

import calendar
import datetime as dt
from decimal import Decimal

from django.db.models import Min
from django.utils import timezone

from apps.academy.models import Lesson

from ..models import DailyPerformanceSnapshot
from .metrics import compute_rates, current_counts, percent

MONTHS_NOMINATIVE = (
    "", "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
    "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь",
)
METRICS = ("attendance_percent", "homework_percent", "active_groups", "active_students")


def _num(value):
    if value is None:
        return None
    if isinstance(value, Decimal):
        return float(value)
    return value


def snapshot_row(snapshot: DailyPerformanceSnapshot) -> dict:
    return {
        "attendance_percent": _num(snapshot.attendance_percent),
        "attendance_marked": snapshot.attendance_marked,
        "attendance_attended": snapshot.attendance_attended,
        "homework_percent": _num(snapshot.homework_percent),
        "homework_results": snapshot.homework_results,
        "homework_done": snapshot.homework_done,
        "lessons_count": snapshot.lessons_count,
        "active_groups": snapshot.active_groups,
        "active_students": snapshot.active_students,
        "status": snapshot.status,
        "manual_fields": list(snapshot.manual_fields or []),
        "manual_comment": snapshot.manual_comment,
        "computed_at": snapshot.computed_at,
    }


def _live_row(day: dt.date, now: dt.datetime, snapshot: DailyPerformanceSnapshot | None) -> dict:
    rates = compute_rates(day, now=now)
    groups, students = current_counts()
    row = {
        "attendance_percent": _num(rates.attendance_percent),
        "attendance_marked": rates.attendance_marked,
        "attendance_attended": rates.attendance_attended,
        "homework_percent": _num(rates.homework_percent),
        "homework_results": rates.homework_results,
        "homework_done": rates.homework_done,
        "lessons_count": rates.lessons_count,
        "active_groups": groups,
        "active_students": students,
        "status": "live",
        "manual_fields": [],
        "manual_comment": "",
        "computed_at": now,
    }
    if snapshot is not None:
        for field in snapshot.manual_fields or []:
            row[field] = _num(getattr(snapshot, field))
        row["manual_fields"] = list(snapshot.manual_fields or [])
        row["manual_comment"] = snapshot.manual_comment
    return row


def _empty_row(status: str) -> dict:
    return {
        "attendance_percent": None, "attendance_marked": 0, "attendance_attended": 0,
        "homework_percent": None, "homework_results": 0, "homework_done": 0, "lessons_count": 0,
        "active_groups": None, "active_students": None,
        "status": status, "manual_fields": [], "manual_comment": "", "computed_at": None,
    }


def month_days(year: int, month: int, *, now: dt.datetime | None = None) -> list[dict]:
    """Каждый день месяца (28–31) с показателями; нет данных — None."""
    now = now or timezone.now()
    today = timezone.localdate(now)
    last = calendar.monthrange(year, month)[1]
    first_day, last_day = dt.date(year, month, 1), dt.date(year, month, last)
    snapshots = {s.date: s for s in DailyPerformanceSnapshot.objects.filter(date__range=(first_day, last_day))}
    rows = []
    for number in range(1, last + 1):
        day = dt.date(year, month, number)
        if day > today:
            row = _empty_row("future")
        elif day == today:
            row = _live_row(day, now, snapshots.get(day))
        elif day in snapshots:
            row = snapshot_row(snapshots[day])
        else:
            row = _empty_row("missing")
        rows.append({"date": day, "day": number, "weekday": day.isoweekday(), "is_today": day == today,
                     "is_future": day > today, **row})
    return rows


def _latest_with_value(days: list[dict], field: str, before: int | None = None) -> dict | None:
    candidates = [d for d in days if not d["is_future"] and d[field] is not None]
    if before is not None:
        candidates = [d for d in candidates if d["day"] < before]
    return candidates[-1] if candidates else None


def _card(days: list[dict], field: str) -> dict:
    current = _latest_with_value(days, field)
    previous = _latest_with_value(days, field, before=current["day"]) if current else None
    value = current[field] if current else None
    prev_value = previous[field] if previous else None
    change = None
    if value is not None and prev_value is not None:
        change = round(value - prev_value, 1)  # int - int остаётся int
    return {
        "value": value,
        "date": current["date"] if current else None,
        "previous_value": prev_value,
        "previous_date": previous["date"] if previous else None,
        "change": change,
    }


def summary(days: list[dict]) -> dict:
    """Карточки: последнее известное значение месяца и изменение к предыдущему дню с данными;
    для процентов — также средний процент за месяц (взвешенный по числу отметок/результатов)."""
    marked = sum(d["attendance_marked"] for d in days if "attendance_percent" not in d["manual_fields"])
    attended = sum(d["attendance_attended"] for d in days if "attendance_percent" not in d["manual_fields"])
    hw_total = sum(d["homework_results"] for d in days if "homework_percent" not in d["manual_fields"])
    hw_done = sum(d["homework_done"] for d in days if "homework_percent" not in d["manual_fields"])
    cards = {field: _card(days, field) for field in METRICS}
    cards["attendance_percent"]["month_average"] = _num(percent(attended, marked))
    cards["homework_percent"]["month_average"] = _num(percent(hw_done, hw_total))
    return cards


def trends(days: list[dict]) -> dict:
    def series(field):
        return [{"date": d["date"], "day": d["day"], "value": d[field]} for d in days if not d["is_future"]]

    def average(field):
        values = [d[field] for d in days if not d["is_future"] and d[field] is not None]
        return round(sum(values) / len(values), 1) if values else None

    return {
        "attendance": {"points": series("attendance_percent"), "average": average("attendance_percent")},
        "homework": {"points": series("homework_percent"), "average": average("homework_percent")},
        "groups": {"points": series("active_groups"), "average": average("active_groups")},
        "students": {"points": series("active_students"), "average": average("active_students")},
    }


def available_years(now: dt.datetime | None = None) -> list[int]:
    today = timezone.localdate(now or timezone.now())
    first_snapshot = DailyPerformanceSnapshot.objects.aggregate(first=Min("date"))["first"]
    first_lesson = Lesson.objects.aggregate(first=Min("date"))["first"]
    starts = [d.year for d in (first_snapshot, first_lesson) if d and d <= today]
    start = min(starts) if starts else today.year
    return list(range(today.year, start - 1, -1))


def month_payload(year: int, month: int, *, now: dt.datetime | None = None) -> dict:
    now = now or timezone.now()
    days = month_days(year, month, now=now)
    return {
        "year": year,
        "month": month,
        "month_label": MONTHS_NOMINATIVE[month],
        "today": timezone.localdate(now),
        "is_current_month": (year, month) == (timezone.localdate(now).year, timezone.localdate(now).month),
        "generated_at": now,
        "timezone": timezone.get_current_timezone_name(),
        "days": days,
        "summary": summary(days),
        "trends": trends(days),
        "available_years": available_years(now),
    }
