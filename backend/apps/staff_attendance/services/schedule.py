"""Ожидаемое рабочее время сотрудника в конкретный день.

Порядок источников:
1. Личное расписание (AttendanceWorkSchedule), если оно включено.
2. Для тренера — занятия LMS этого дня, если в настройках включено
   `teacher_schedule_from_lessons` (начало первого занятия минус «прийти
   заранее», конец последнего). День без занятий — не рабочий.
3. Общее расписание из настроек.

Результат — интервал в часовом поясе офиса или None (выходной: опоздание и
«нет прихода» в этот день не считаются).
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from django.db.models import Q

from ..models import AttendanceSettings, AttendanceWorkSchedule


@dataclass(frozen=True)
class WorkWindow:
    start: datetime
    end: datetime
    grace_minutes: int
    source: str  # personal | lessons | default

    @property
    def late_after(self) -> datetime:
        return self.start + timedelta(minutes=self.grace_minutes)


class ScheduleResolver:
    """Считает окна для многих сотрудников за один день, не делая запрос на
    каждого: личные расписания и занятия тренеров загружаются пачкой."""

    def __init__(self, config: AttendanceSettings, users, day: date):
        self.config = config
        self.day = day
        self.tz = config.tzinfo
        ids = [u.pk for u in users]
        self.personal = {
            s.user_id: s for s in AttendanceWorkSchedule.objects.filter(user_id__in=ids, is_active=True)
        }
        self.lessons: dict[int, tuple] = {}
        if config.teacher_schedule_from_lessons:
            self.lessons = _teacher_lesson_bounds(ids, day)

    def window(self, user) -> WorkWindow | None:
        personal = self.personal.get(user.pk)
        if personal is not None:
            if self.day.weekday() not in (personal.work_days or []):
                return None
            grace = personal.late_grace_minutes
            return self._make(personal.work_start, personal.work_end,
                              self.config.late_grace_minutes if grace is None else grace, "personal")
        if self.config.teacher_schedule_from_lessons and user.role == "teacher":
            bounds = self.lessons.get(user.pk)
            if not bounds:
                return None
            start, end = bounds
            win = self._make(start, end, self.config.late_grace_minutes, "lessons")
            before = timedelta(minutes=self.config.teacher_arrival_before_lesson_minutes)
            return WorkWindow(win.start - before, win.end, win.grace_minutes, win.source)
        if self.day.weekday() not in (self.config.work_days or []):
            return None
        return self._make(self.config.work_start, self.config.work_end, self.config.late_grace_minutes, "default")

    def _make(self, start, end, grace, source) -> WorkWindow:
        return WorkWindow(
            start=datetime.combine(self.day, start, tzinfo=self.tz),
            end=datetime.combine(self.day, end, tzinfo=self.tz),
            grace_minutes=int(grace or 0),
            source=source,
        )


def _teacher_lesson_bounds(user_ids, day: date) -> dict[int, tuple]:
    """{user_id: (первое начало, последний конец)} проведённых/плановых
    занятий дня. Тренер занятия — Lesson.teacher, иначе тренер GroupTeacher
    (как Lesson.effective_teacher)."""
    from apps.academy.models import Lesson

    rows = (
        Lesson.objects.filter(date=day)
        .exclude(status=Lesson.Status.CANCELLED)
        .filter(Q(teacher__user_id__in=user_ids)
                | Q(teacher__isnull=True, group_teacher__teacher__user_id__in=user_ids))
        .values_list("teacher__user_id", "group_teacher__teacher__user_id", "start_time", "end_time")
    )
    bounds: dict[int, tuple] = {}
    for own, via_group, start, end in rows:
        uid = own or via_group
        if uid is None or start is None or end is None:
            continue
        lo, hi = bounds.get(uid, (start, end))
        bounds[uid] = (min(lo, start), max(hi, end))
    return bounds


def window_for(user, day: date, config: AttendanceSettings) -> WorkWindow | None:
    return ScheduleResolver(config, [user], day).window(user)


def late_minutes(checked_in_at: datetime, window: WorkWindow | None) -> int:
    """Опоздание считается от начала дня, но только если приход позже
    льготного времени: 09:00 + 10 мин льготы, приход 09:25 → 25 минут
    (неполная минута не округляется вверх)."""
    if window is None or checked_in_at <= window.late_after:
        return 0
    return math.floor((checked_in_at - window.start).total_seconds() / 60)
