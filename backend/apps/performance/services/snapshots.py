"""Ежедневные снимки «Общей статистики»: создание, пересчёт, фиксация.

`capture()` запускают Celery Beat (`performance.capture_daily_snapshots`) и
Railway Cron (`manage.py run_scheduled_tasks`); каждый запуск идемпотентен:

1. Снимок за сегодня создаётся (одна строка на дату — уникальный индекс) или
   обновляется: проценты + количество активных групп и студентов.
2. Предварительные снимки прошлых дней: пересчитываются только проценты
   (отметки, внесённые с опозданием), количество групп и студентов остаётся
   тем, что было в тот день. Старше ``PERFORMANCE_FINALIZE_DELAY_DAYS`` —
   фиксируются (``final``) и больше не меняются.
3. Пропущенные дни (планировщик не работал) заполняются процентами по
   записям; количество групп и студентов для них неизвестно — ``None``,
   а не подставленное «сегодняшнее» значение.

Поля из ``manual_fields`` (ручная корректировка) никогда не перезаписываются.
"""
from __future__ import annotations

import datetime as dt

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from ..models import DailyPerformanceSnapshot
from .metrics import compute_rates, current_counts

# Насколько далеко назад заполнять пропуски автоматически.
MAX_GAP_DAYS = 31


def finalize_delay() -> int:
    return max(0, int(getattr(settings, "PERFORMANCE_FINALIZE_DELAY_DAYS", 1)))


def _apply(snapshot: DailyPerformanceSnapshot, values: dict) -> None:
    manual = set(snapshot.manual_fields or [])
    for field, value in values.items():
        if field not in manual:
            setattr(snapshot, field, value)


def _rate_values(day: dt.date, now: dt.datetime) -> dict:
    rates = compute_rates(day, now=now)
    return {
        "attendance_percent": rates.attendance_percent,
        "attendance_marked": rates.attendance_marked,
        "attendance_attended": rates.attendance_attended,
        "homework_percent": rates.homework_percent,
        "homework_results": rates.homework_results,
        "homework_done": rates.homework_done,
        "lessons_count": rates.lessons_count,
    }


def _status_for(day: dt.date, today: dt.date) -> str:
    if day < today - dt.timedelta(days=finalize_delay()):
        return DailyPerformanceSnapshot.Status.FINAL
    return DailyPerformanceSnapshot.Status.PROVISIONAL


def _get_or_create(day: dt.date) -> tuple[DailyPerformanceSnapshot, bool]:
    try:
        with transaction.atomic():
            return DailyPerformanceSnapshot.objects.select_for_update().get_or_create(date=day)
    except IntegrityError:  # параллельный запуск успел создать строку
        return DailyPerformanceSnapshot.objects.get(date=day), False


@transaction.atomic
def capture_today(now: dt.datetime | None = None) -> DailyPerformanceSnapshot:
    now = now or timezone.now()
    today = timezone.localdate(now)
    snapshot, _ = _get_or_create(today)
    snapshot = DailyPerformanceSnapshot.objects.select_for_update().get(pk=snapshot.pk)
    groups, students = current_counts()
    _apply(snapshot, {**_rate_values(today, now), "active_groups": groups, "active_students": students})
    snapshot.status = _status_for(today, today)
    snapshot.computed_at = now
    snapshot.save()
    return snapshot


def refresh_past(now: dt.datetime | None = None) -> dict:
    """Пересчитать предварительные прошлые дни и зафиксировать старые."""
    now = now or timezone.now()
    today = timezone.localdate(now)
    refreshed = finalized = 0
    pending = DailyPerformanceSnapshot.objects.filter(
        date__lt=today, status=DailyPerformanceSnapshot.Status.PROVISIONAL,
    ).values_list("pk", flat=True)
    for pk in list(pending):
        with transaction.atomic():
            snapshot = DailyPerformanceSnapshot.objects.select_for_update().get(pk=pk)
            if snapshot.is_final:
                continue
            _apply(snapshot, _rate_values(snapshot.date, now))  # количество групп/студентов — не трогаем
            snapshot.status = _status_for(snapshot.date, today)
            snapshot.computed_at = now
            snapshot.save()
            refreshed += 1
            finalized += snapshot.is_final
    return {"refreshed": refreshed, "finalized": finalized}


def backfill(start: dt.date, end: dt.date, now: dt.datetime | None = None) -> int:
    """Создать снимки для дней [start, end] (не позже вчера), которых нет.
    Существующие не меняются. Количество групп и студентов — неизвестно."""
    now = now or timezone.now()
    today = timezone.localdate(now)
    end = min(end, today - dt.timedelta(days=1))
    existing = set(DailyPerformanceSnapshot.objects.filter(date__range=(start, end)).values_list("date", flat=True))
    created = 0
    day = start
    while day <= end:
        if day not in existing:
            try:
                with transaction.atomic():
                    DailyPerformanceSnapshot.objects.create(
                        date=day, status=_status_for(day, today), computed_at=now, **_rate_values(day, now),
                    )
                created += 1
            except IntegrityError:
                pass
        day += dt.timedelta(days=1)
    return created


def fill_gaps(now: dt.datetime | None = None) -> int:
    """Пропуски между последним снимком и сегодняшним днём (не дальше MAX_GAP_DAYS)."""
    now = now or timezone.now()
    today = timezone.localdate(now)
    last = (DailyPerformanceSnapshot.objects.filter(date__lt=today).order_by("-date")
            .values_list("date", flat=True).first())
    if last is None:
        return 0  # первый запуск: историю заполняет команда backfill явно
    start = max(last + dt.timedelta(days=1), today - dt.timedelta(days=MAX_GAP_DAYS))
    return backfill(start, today - dt.timedelta(days=1), now=now)


def capture(now: dt.datetime | None = None) -> dict:
    """Один запуск планировщика (см. модуль)."""
    now = now or timezone.now()
    gaps = fill_gaps(now)
    past = refresh_past(now)
    snapshot = capture_today(now)
    return {"date": snapshot.date.isoformat(), "gaps_filled": gaps, **past}
