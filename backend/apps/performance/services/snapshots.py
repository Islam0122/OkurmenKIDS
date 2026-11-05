"""Ежедневные снимки «Общей статистики»: создание, пересчёт, фиксация.

`capture()` запускают Celery Beat (`performance.capture_daily_snapshots`) и
Railway Cron (`manage.py run_scheduled_tasks`); каждый запуск идемпотентен
(одна строка на дату — уникальный индекс):

1. Снимок за сегодня создаётся или обновляется.
2. Предварительные снимки прошлых дней пересчитываются (посещаемость и ДЗ,
   внесённые с опозданием). Состав групп берётся *на тот день* (журнал
   StudentStatusEvent), расписание — занятия того дня, поэтому пересчёт не
   подставляет сегодняшнее состояние в прошлое. Старше
   ``PERFORMANCE_FINALIZE_DELAY_DAYS`` — снимок фиксируется (``final``) и
   больше не меняется.
3. Пропущенные дни (планировщик не работал; первый запуск — с начала
   прошлого месяца) восстанавливаются из записей LMS тем же расчётом.

Поля из ``manual_fields`` (ручная корректировка) никогда не перезаписываются.
"""
from __future__ import annotations

import datetime as dt

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from ..models import DailyPerformanceSnapshot
from .metrics import DayStats, compute_days

# Насколько далеко назад заполнять пропуски автоматически.
MAX_GAP_DAYS = 62


def finalize_delay() -> int:
    return max(0, int(getattr(settings, "PERFORMANCE_FINALIZE_DELAY_DAYS", 7)))


def _status_for(day: dt.date, today: dt.date) -> str:
    if day < today - dt.timedelta(days=finalize_delay()):
        return DailyPerformanceSnapshot.Status.FINAL
    return DailyPerformanceSnapshot.Status.PROVISIONAL


def _apply(snapshot: DailyPerformanceSnapshot, stats: DayStats) -> None:
    manual = set(snapshot.manual_fields or [])
    for field, value in stats.as_values().items():
        if field not in manual:
            setattr(snapshot, field, value)


def _save_day(day: dt.date, stats: DayStats, *, now: dt.datetime, today: dt.date, create_only: bool = False) -> str:
    """Создать/обновить снимок дня. Зафиксированные не трогает. Возвращает, что произошло."""
    with transaction.atomic():
        snapshot = DailyPerformanceSnapshot.objects.select_for_update().filter(date=day).first()
        if snapshot is None:
            snapshot = DailyPerformanceSnapshot(date=day)
            outcome = "created"
        elif create_only or snapshot.is_final:
            return "kept"
        else:
            outcome = "updated"
        _apply(snapshot, stats)
        snapshot.status = _status_for(day, today)
        snapshot.computed_at = now
        try:
            with transaction.atomic():
                snapshot.save()
        except IntegrityError:  # параллельный запуск успел создать строку
            return "kept"
    return outcome


def capture_day(day: dt.date, now: dt.datetime | None = None) -> DailyPerformanceSnapshot:
    """Снимок одного дня (не будущего): создать или пересчитать, если он не зафиксирован."""
    now = now or timezone.now()
    today = timezone.localdate(now)
    stats = compute_days(day, day, now=now).get(day, DayStats())
    _save_day(day, stats, now=now, today=today)
    return DailyPerformanceSnapshot.objects.get(date=day)


def backfill(start: dt.date, end: dt.date, now: dt.datetime | None = None) -> int:
    """Создать снимки для дней [start, end] (не позже вчера), которых нет.
    Существующие не меняются."""
    now = now or timezone.now()
    today = timezone.localdate(now)
    end = min(end, today - dt.timedelta(days=1))
    existing = set(DailyPerformanceSnapshot.objects.filter(date__range=(start, end)).values_list("date", flat=True))
    missing = [d for d in _days(start, end) if d not in existing]
    if not missing:
        return 0
    stats = compute_days(missing[0], missing[-1], now=now)
    return sum(
        _save_day(day, stats[day], now=now, today=today, create_only=True) == "created" for day in missing
    )


def _days(start: dt.date, end: dt.date):
    day = start
    while day <= end:
        yield day
        day += dt.timedelta(days=1)


def _first_day_of_previous_month(today: dt.date) -> dt.date:
    return (today.replace(day=1) - dt.timedelta(days=1)).replace(day=1)


def capture(now: dt.datetime | None = None) -> dict:
    """Один запуск планировщика (см. модуль)."""
    now = now or timezone.now()
    today = timezone.localdate(now)
    snapshots = DailyPerformanceSnapshot.objects.filter(date__lte=today)
    last = snapshots.filter(date__lt=today).order_by("-date").values_list("date", flat=True).first()
    oldest_provisional = (snapshots.filter(status=DailyPerformanceSnapshot.Status.PROVISIONAL, date__lt=today)
                          .order_by("date").values_list("date", flat=True).first())
    start = _first_day_of_previous_month(today) if last is None else last + dt.timedelta(days=1)
    if oldest_provisional is not None:
        start = min(start, oldest_provisional)
    start = max(start, today - dt.timedelta(days=MAX_GAP_DAYS))

    stats = compute_days(start, today, now=now)
    counts = {"created": 0, "updated": 0, "kept": 0}
    for day in _days(start, today):
        counts[_save_day(day, stats.get(day, DayStats()), now=now, today=today)] += 1
    finalized = DailyPerformanceSnapshot.objects.filter(
        date__gte=start, status=DailyPerformanceSnapshot.Status.FINAL, computed_at=now,
    ).count()
    return {"date": today.isoformat(), "from": start.isoformat(), **counts, "finalized": finalized}
