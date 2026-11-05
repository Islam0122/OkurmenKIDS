"""Данные сайта «Общая статистика» за месяц — всё считается здесь, на сервере.

* Каждый день месяца — от 1-го до последнего (28–31), прошедшие не скрываются.
* Прошлые дни со снимком — из снимка (DailyPerformanceSnapshot): прошлое не
  пересчитывается по текущему состоянию.
* Прошлые дни без снимка (планировщик ещё не дошёл) — восстанавливаются из
  записей LMS тем же расчётом (services.metrics: расписание дня + состав групп
  на тот день), если в этом месяце вообще были занятия; иначе — «Нет данных».
* Сегодня — «живой» расчёт с учётом ручных корректировок.
* Будущие дни (и будущие месяцы) — календарная сетка без значений.
"""
from __future__ import annotations

import calendar
import datetime as dt
from decimal import Decimal

from django.db.models import Min
from django.utils import timezone

from apps.academy.models import Lesson

from ..models import DailyPerformanceSnapshot
from .metrics import DayStats, compute_days, percent

MONTHS_NOMINATIVE = (
    "", "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
    "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь",
)
VALUE_FIELDS = (
    "scheduled_groups", "held_groups", "scheduled_students", "attended_students", "expected_students",
    "attendance_percent", "homework_percent", "homework_results", "homework_done",
    "lessons_count", "held_lessons_count",
)
# Карточки сайта: проценты + количество по расписанию дня.
METRICS = ("attendance_percent", "homework_percent", "scheduled_groups", "scheduled_students")
# Старые имена полей API (до учёта расписания) — те же значения «по расписанию дня».
ALIASES = {"active_groups": "scheduled_groups", "active_students": "scheduled_students"}


def _num(value):
    if isinstance(value, Decimal):
        return float(value)
    return value


def _with_aliases(row: dict) -> dict:
    for alias, field in ALIASES.items():
        row[alias] = row.get(field)
    return row


def snapshot_row(snapshot: DailyPerformanceSnapshot) -> dict:
    row = {field: _num(getattr(snapshot, field)) for field in VALUE_FIELDS}
    row.update({
        "status": snapshot.status,
        "manual_fields": list(snapshot.manual_fields or []),
        "manual_comment": snapshot.manual_comment,
        "computed_at": snapshot.computed_at,
    })
    return _with_aliases(row)


def _computed_row(stats: DayStats, status: str, now: dt.datetime, snapshot: DailyPerformanceSnapshot | None) -> dict:
    row = {field: _num(value) for field, value in stats.as_values().items()}
    row.update({"status": status, "manual_fields": [], "manual_comment": "", "computed_at": now})
    if snapshot is not None:  # ручные корректировки действуют и для «живого» дня
        for field in snapshot.manual_fields or []:
            row[field] = _num(getattr(snapshot, field))
        row["manual_fields"] = list(snapshot.manual_fields or [])
        row["manual_comment"] = snapshot.manual_comment
    return _with_aliases(row)


def _empty_row(status: str) -> dict:
    row = {field: None for field in VALUE_FIELDS}
    row.update({"status": status, "manual_fields": [], "manual_comment": "", "computed_at": None})
    return _with_aliases(row)


def month_days(year: int, month: int, *, now: dt.datetime | None = None) -> list[dict]:
    """Каждый день месяца с показателями; нет данных — None (не 0)."""
    now = now or timezone.now()
    today = timezone.localdate(now)
    last = calendar.monthrange(year, month)[1]
    first_day, last_day = dt.date(year, month, 1), dt.date(year, month, last)
    snapshots = {s.date: s for s in DailyPerformanceSnapshot.objects.filter(date__range=(first_day, last_day))}

    # Что считать на лету: сегодня и прошедшие дни без снимка.
    to_compute = [d for d in (first_day + dt.timedelta(days=i) for i in range(last))
                  if d <= today and (d == today or d not in snapshots)]
    computed: dict[dt.date, DayStats] = {}
    if to_compute:
        has_records = snapshots or Lesson.objects.filter(date__range=(first_day, min(last_day, today))).exists()
        if has_records:
            computed = compute_days(to_compute[0], to_compute[-1], now=now)

    rows = []
    for number in range(1, last + 1):
        day = dt.date(year, month, number)
        if day > today:
            row = _empty_row("future")
        elif day == today and day in computed:
            row = _computed_row(computed[day], "live", now, snapshots.get(day))
        elif day in snapshots:
            row = snapshot_row(snapshots[day])
        elif day in computed:
            row = _computed_row(computed[day], "computed", now, None)
        else:
            row = _empty_row("missing")
        has_data = row["status"] not in ("future", "missing")
        rows.append({
            "date": day, "day": number, "weekday": day.isoweekday(), "is_today": day == today,
            "is_future": day > today, "has_data": has_data,
            "no_lessons": has_data and not row["lessons_count"],
            **row,
        })
    return rows


def _latest(days: list[dict], field: str, *, before: int | None = None, study_days: bool = False) -> dict | None:
    candidates = [
        d for d in days
        if d["has_data"] and d[field] is not None and (not study_days or d["lessons_count"])
        and (before is None or d["day"] < before)
    ]
    return candidates[-1] if candidates else None


def _card(days: list[dict], field: str, *, study_days: bool, extra: str | None = None) -> dict:
    """Последний день месяца с данными и изменение к предыдущему такому дню.
    Количество — по учебным дням (дни без занятий не сравниваются с учебными)."""
    current = _latest(days, field, study_days=study_days)
    previous = _latest(days, field, before=current["day"], study_days=study_days) if current else None
    value = current[field] if current else None
    prev_value = previous[field] if previous else None
    change = round(value - prev_value, 1) if value is not None and prev_value is not None else None
    card = {
        "value": value,
        "date": current["date"] if current else None,
        "previous_value": prev_value,
        "previous_date": previous["date"] if previous else None,
        "change": change,
    }
    if extra:
        card[extra] = current[extra] if current else None
    return card


def summary(days: list[dict]) -> dict:
    """Карточки + средний процент за месяц (взвешенный по студентам / результатам ДЗ)."""
    usable = [d for d in days if d["has_data"]]
    expected = sum(d["expected_students"] or 0 for d in usable if "attendance_percent" not in d["manual_fields"])
    attended = sum(d["attended_students"] or 0 for d in usable if "attendance_percent" not in d["manual_fields"])
    hw_total = sum(d["homework_results"] or 0 for d in usable if "homework_percent" not in d["manual_fields"])
    hw_done = sum(d["homework_done"] or 0 for d in usable if "homework_percent" not in d["manual_fields"])
    cards = {
        "attendance_percent": _card(days, "attendance_percent", study_days=False),
        "homework_percent": _card(days, "homework_percent", study_days=False),
        "scheduled_groups": _card(days, "scheduled_groups", study_days=True, extra="held_groups"),
        "scheduled_students": _card(days, "scheduled_students", study_days=True, extra="attended_students"),
    }
    cards["attendance_percent"]["month_average"] = _num(percent(attended, expected))
    cards["homework_percent"]["month_average"] = _num(percent(hw_done, hw_total))
    for alias, field in ALIASES.items():
        cards[alias] = cards[field]
    return cards


def trends(days: list[dict]) -> dict:
    def series(field, study_days=False):
        return [{"date": d["date"], "day": d["day"],
                 "value": d[field] if d["has_data"] and (not study_days or d["lessons_count"]) else None}
                for d in days if not d["is_future"]]

    def average(field, study_days=False):
        values = [d[field] for d in days if d["has_data"] and d[field] is not None
                  and (not study_days or d["lessons_count"])]
        return round(sum(values) / len(values), 1) if values else None

    return {
        "attendance": {"points": series("attendance_percent"), "average": average("attendance_percent")},
        "homework": {"points": series("homework_percent"), "average": average("homework_percent")},
        # Количество — по учебным дням: дни без занятий (0 в таблице) не рисуются
        # провалами на графике и не занижают среднее.
        "groups": {"points": series("scheduled_groups", True), "average": average("scheduled_groups", True)},
        "students": {"points": series("scheduled_students", True), "average": average("scheduled_students", True)},
    }


def available_years(now: dt.datetime | None = None) -> list[int]:
    today = timezone.localdate(now or timezone.now())
    first_snapshot = DailyPerformanceSnapshot.objects.aggregate(first=Min("date"))["first"]
    first_lesson = Lesson.objects.aggregate(first=Min("date"))["first"]
    starts = [d.year for d in (first_snapshot, first_lesson) if d and d <= today]
    start = min(starts) if starts else today.year
    return list(range(today.year + 1, start - 1, -1))


def month_payload(year: int, month: int, *, now: dt.datetime | None = None) -> dict:
    now = now or timezone.now()
    today = timezone.localdate(now)
    days = month_days(year, month, now=now)
    return {
        "year": year,
        "month": month,
        "month_label": MONTHS_NOMINATIVE[month],
        "today": today,
        "is_current_month": (year, month) == (today.year, today.month),
        "is_future_month": (year, month) > (today.year, today.month),
        "generated_at": now,
        "timezone": timezone.get_current_timezone_name(),
        "days": days,
        "summary": summary(days),
        "trends": trends(days),
        "available_years": available_years(now),
    }
