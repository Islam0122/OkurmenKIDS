"""Расчёт показателей одного дня из существующих моделей apps.academy.

Правила (едины для снимков и для «живого» расчёта):

* **Посещаемость** — отметки (Attendance) на занятиях этого дня:
  присутствовал + опоздал от всех отметок (как в apps.academy.services.analytics
  и KPI). Учитываются только активные группы и активные студенты, отменённые
  занятия не учитываются, будущие (ещё не начавшиеся сегодня) — тоже.
* **Домашние задания** — результаты ДЗ (HomeworkResult), внесённые тренером в
  этот день: сдано (в срок, с опозданием или проверено) от всех внесённых
  результатов. Только активные группы и студенты, ДЗ отменённых или будущих
  занятий не учитываются.
* **Активные группы** — статус «Активна»; **активные студенты** — статус
  «Активен» в активной группе. Это состояние «сейчас», поэтому в снимок оно
  попадает только в сам день (см. services.snapshots).

Нет отметок / результатов — процент ``None`` («нет данных»), не 0.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from django.db.models import Count, Q
from django.utils import timezone

from apps.academy.models import Attendance, Group, HomeworkResult, Lesson, Student

ATTENDED_STATUSES = (Attendance.Status.PRESENT, Attendance.Status.LATE)
DONE_HOMEWORK_STATUSES = (
    HomeworkResult.Status.SUBMITTED, HomeworkResult.Status.CHECKED, HomeworkResult.Status.LATE,
)


@dataclass(frozen=True)
class DayRates:
    attendance_marked: int
    attendance_attended: int
    homework_results: int
    homework_done: int
    lessons_count: int

    @property
    def attendance_percent(self) -> Decimal | None:
        return percent(self.attendance_attended, self.attendance_marked)

    @property
    def homework_percent(self) -> Decimal | None:
        return percent(self.homework_done, self.homework_results)


def percent(part: int, total: int) -> Decimal | None:
    if not total:
        return None
    return (Decimal(part) * 100 / Decimal(total)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)


def _day_bounds(day: dt.date) -> tuple[dt.datetime, dt.datetime]:
    tz = timezone.get_current_timezone()
    start = timezone.make_aware(dt.datetime.combine(day, dt.time.min), tz)
    return start, start + dt.timedelta(days=1)


def _held_lessons_q(prefix: str, day: dt.date, now: dt.datetime) -> Q:
    """Неотменённые занятия активных групп не позже `day`; сегодня — только уже начавшиеся."""
    q = (
        Q(**{f"{prefix}date__lte": day})
        & ~Q(**{f"{prefix}status": Lesson.Status.CANCELLED})
        & Q(**{f"{prefix}group__status": Group.Status.ACTIVE})
    )
    local_now = timezone.localtime(now)
    if day >= local_now.date():
        q &= Q(**{f"{prefix}date__lt": local_now.date()}) | Q(**{f"{prefix}start_time__lte": local_now.time()}) | Q(
            **{f"{prefix}status__in": (Lesson.Status.IN_PROGRESS, Lesson.Status.COMPLETED)}
        )
    return q


def compute_rates(day: dt.date, *, now: dt.datetime | None = None) -> DayRates:
    now = now or timezone.now()
    attendance = Attendance.objects.filter(
        _held_lessons_q("lesson__", day, now), lesson__date=day, student__status=Student.Status.ACTIVE,
    ).aggregate(total=Count("id"), attended=Count("id", filter=Q(status__in=ATTENDED_STATUSES)))

    start, end = _day_bounds(day)
    homework = HomeworkResult.objects.filter(
        _held_lessons_q("homework__lesson__", day, now),
        created_at__gte=start, created_at__lt=end, student__status=Student.Status.ACTIVE,
    ).aggregate(total=Count("id"), done=Count("id", filter=Q(status__in=DONE_HOMEWORK_STATUSES)))

    lessons = Lesson.objects.filter(_held_lessons_q("", day, now), date=day).count()
    return DayRates(
        attendance_marked=attendance["total"] or 0,
        attendance_attended=attendance["attended"] or 0,
        homework_results=homework["total"] or 0,
        homework_done=homework["done"] or 0,
        lessons_count=lessons,
    )


def current_counts() -> tuple[int, int]:
    """(активные группы, активные студенты) — на текущий момент."""
    groups = Group.objects.filter(status=Group.Status.ACTIVE).count()
    students = Student.objects.filter(status=Student.Status.ACTIVE, group__status=Group.Status.ACTIVE).count()
    return groups, students
