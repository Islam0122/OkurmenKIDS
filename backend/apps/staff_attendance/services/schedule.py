"""Ожидаемое рабочее время сотрудника в конкретный день.

Порядок источников:
0. Исключение из графика (AttendanceScheduleException) на эту дату: отпуск,
   больничный, выходной — день нерабочий; «Особые часы» — свои часы дня.
1. Личное расписание (AttendanceWorkSchedule), если оно включено и день
   попадает в период его действия. Часы берутся для конкретного дня недели
   (`hours_for`): базовые или отдельные часы этого дня.
2. Для тренера — занятия LMS этого дня, если в настройках включено
   `teacher_schedule_from_lessons` (начало первого занятия минус «прийти
   заранее», конец последнего). День без занятий — не рабочий.
3. Общее расписание из настроек.

Поверх плана рабочего дня — утверждённые разрешения «Отпросился»
(AttendancePermission): интервал, покрывающий начало дня, сдвигает
ожидаемый приход на свой конец; покрывающий конец дня — ожидаемый уход на
своё начало; весь рабочий день — день «по разрешению», не отсутствие.
Несколько разрешений, идущих встык, складываются. Отметки по QR не меняются.

`ScheduleResolver.plan()` — полный ответ «что по графику в этот день»
(`DayPlan`: рабочий день / выходной / отпуск / больничный / не задано и
почему); `window()` — только окно рабочего времени в часовом поясе офиса
или None (нерабочий день: опоздание и «нет прихода» не считаются).

Данные для многих сотрудников и дней загружаются пачкой (`ScheduleData`):
несколько запросов на весь период, а не на сотрудника или день.
"""
from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, replace
from datetime import date, datetime, time, timedelta

from django.db.models import Q
from django.utils import timezone

from ..models import (
    AttendanceEmployeeSettings,
    AttendancePermission,
    AttendanceScheduleException,
    AttendanceSettings,
    AttendanceWorkSchedule,
)


@dataclass(frozen=True)
class WorkWindow:
    start: datetime
    end: datetime
    grace_minutes: int
    source: str  # personal | lessons | default | exception
    # Перерыв — только справочно (личное расписание); опоздание от него не зависит.
    break_start: datetime | None = None
    break_end: datetime | None = None

    @property
    def late_after(self) -> datetime:
        return self.start + timedelta(minutes=self.grace_minutes)


class PlanKind:
    WORK = "work"
    DAY_OFF = "day_off"
    VACATION = "vacation"
    SICK_LEAVE = "sick_leave"
    NOT_SET = "not_set"  # ни одного источника графика (общий график без рабочих дней)
    EXCUSED = "excused"  # весь рабочий день покрыт разрешением «Отпросился»

    LABELS = {DAY_OFF: "Выходной", VACATION: "Отпуск", SICK_LEAVE: "Больничный", NOT_SET: "Не задано",
              EXCUSED: "По разрешению"}


@dataclass(frozen=True)
class DayPlan:
    kind: str
    window: WorkWindow | None = None
    # personal | lessons | default | exception | None
    source: str | None = None
    exception: AttendanceScheduleException | None = None
    # Утверждённые разрешения, затрагивающие этот день, и окно до их учёта.
    permissions: tuple = ()
    base_window: WorkWindow | None = None
    # Часовой пояс офиса (заполнен, когда есть разрешения): для вывода их времени без запроса настроек.
    tz: object = None

    @property
    def is_working(self) -> bool:
        return self.window is not None


_EXCEPTION_KIND = {
    AttendanceScheduleException.Kind.VACATION: PlanKind.VACATION,
    AttendanceScheduleException.Kind.SICK_LEAVE: PlanKind.SICK_LEAVE,
    AttendanceScheduleException.Kind.DAY_OFF: PlanKind.DAY_OFF,
}


class ScheduleData:
    """Личные расписания, исключения и занятия тренеров для `users` за
    период [start, end] — по одному запросу на источник."""

    def __init__(self, config: AttendanceSettings, users, start: date, end: date):
        ids = [u.pk for u in users]
        self.personal: dict[int, AttendanceWorkSchedule] = {
            s.user_id: s
            for s in AttendanceWorkSchedule.objects.filter(user_id__in=ids, is_active=True).filter(
                Q(valid_from__isnull=True) | Q(valid_from__lte=end),
                Q(valid_until__isnull=True) | Q(valid_until__gte=start),
            )
        }
        self.exceptions: dict[int, list[AttendanceScheduleException]] = defaultdict(list)
        for exc in AttendanceScheduleException.objects.filter(user_id__in=ids, date_from__lte=end, date_to__gte=start):
            self.exceptions[exc.user_id].append(exc)
        self.lessons: dict[tuple[int, date], tuple] = {}
        if config.teacher_schedule_from_lessons:
            self.lessons = _teacher_lesson_bounds(ids, start, end)
        tz = config.tzinfo
        range_start = datetime.combine(start, time(0, 0), tzinfo=tz)
        range_end = datetime.combine(end, time(0, 0), tzinfo=tz) + timedelta(days=1)
        self.permissions: dict[int, list[AttendancePermission]] = defaultdict(list)
        for perm in (AttendancePermission.objects.filter(
                user_id__in=ids, status=AttendancePermission.Status.APPROVED,
                starts_at__lt=range_end, ends_at__gt=range_start)
                .select_related("created_by", "approved_by").order_by("starts_at", "pk")):
            self.permissions[perm.user_id].append(perm)
        self.excluded: set[int] = set(AttendanceEmployeeSettings.objects.filter(
            user_id__in=ids, excluded_from_calculations=True).values_list("user_id", flat=True))


class ScheduleResolver:
    """План дня для многих сотрудников без запроса на каждого. Для отчёта за
    период передайте общий `data` (ScheduleData за весь период)."""

    def __init__(self, config: AttendanceSettings, users, day: date, data: ScheduleData | None = None):
        self.config = config
        self.day = day
        self.tz = config.tzinfo
        self.data = data if data is not None else ScheduleData(config, users, day, day)

    def window(self, user) -> WorkWindow | None:
        return self.plan(user).window

    def plan(self, user) -> DayPlan:
        return self._with_permissions(self._base_plan(user), user)

    def _with_permissions(self, plan: DayPlan, user) -> DayPlan:
        day_start = datetime.combine(self.day, time(0, 0), tzinfo=self.tz)
        day_end = day_start + timedelta(days=1)
        perms = tuple(p for p in self.data.permissions.get(user.pk, ())
                      if p.starts_at < day_end and p.ends_at > day_start)
        if not perms:
            return plan
        win = plan.window
        if win is None:
            return replace(plan, permissions=perms, tz=self.tz)
        start, end = adjust_window(win.start, win.end, [(p.starts_at, p.ends_at) for p in perms])
        if start is None:
            return replace(plan, kind=PlanKind.EXCUSED, window=None, permissions=perms, base_window=win, tz=self.tz)
        adjusted = replace(win, start=timezone.localtime(start, self.tz), end=timezone.localtime(end, self.tz))
        return replace(plan, window=adjusted, permissions=perms, base_window=win, tz=self.tz)

    def _base_plan(self, user) -> DayPlan:
        config, day = self.config, self.day
        personal = self.data.personal.get(user.pk)
        if personal is not None and not personal.is_effective_on(day):
            personal = None
        grace = config.late_grace_minutes
        if personal is not None and personal.late_grace_minutes is not None:
            grace = personal.late_grace_minutes

        exception = next((e for e in self.data.exceptions.get(user.pk, ()) if e.covers(day)), None)
        if exception is not None:
            if exception.kind == AttendanceScheduleException.Kind.CUSTOM_HOURS:
                if exception.work_start and exception.work_end:
                    return DayPlan(PlanKind.WORK, self._make(exception.work_start, exception.work_end, grace,
                                                             "exception"), "exception", exception)
            else:
                return DayPlan(_EXCEPTION_KIND[exception.kind], None, "exception", exception)

        if personal is not None:
            hours = personal.hours_for(day.weekday())
            if hours is None:
                return DayPlan(PlanKind.DAY_OFF, None, "personal")
            win = self._make(hours.start, hours.end, grace, "personal")
            if hours.break_start and hours.break_end:
                win = replace(win, break_start=self._at(hours.break_start), break_end=self._at(hours.break_end))
            return DayPlan(PlanKind.WORK, win, "personal")

        if config.teacher_schedule_from_lessons and user.role == "teacher":
            bounds = self.data.lessons.get((user.pk, day))
            if not bounds:
                return DayPlan(PlanKind.DAY_OFF, None, "lessons")
            start, end = bounds
            win = self._make(start, end, config.late_grace_minutes, "lessons")
            before = timedelta(minutes=config.teacher_arrival_before_lesson_minutes)
            return DayPlan(PlanKind.WORK, WorkWindow(win.start - before, win.end, win.grace_minutes, win.source),
                           "lessons")

        if not config.work_days:
            return DayPlan(PlanKind.NOT_SET)
        if day.weekday() not in config.work_days:
            return DayPlan(PlanKind.DAY_OFF, None, "default")
        return DayPlan(PlanKind.WORK, self._make(config.work_start, config.work_end, config.late_grace_minutes,
                                                 "default"), "default")

    def _at(self, moment) -> datetime:
        return datetime.combine(self.day, moment, tzinfo=self.tz)

    def _make(self, start, end, grace, source) -> WorkWindow:
        return WorkWindow(
            start=datetime.combine(self.day, start, tzinfo=self.tz),
            end=datetime.combine(self.day, end, tzinfo=self.tz),
            grace_minutes=int(grace or 0),
            source=source,
        )


def adjust_window(start: datetime, end: datetime, intervals) -> tuple[datetime | None, datetime | None]:
    """Окно рабочего дня [start, end) с учётом отпущенных интервалов.

    Интервалы объединяются (пересекающиеся и встык); объединённый интервал,
    содержащий начало дня, сдвигает начало на свой конец, содержащий конец
    дня — конец на своё начало. Интервал в середине дня окно не меняет.
    (None, None) — отпущен весь рабочий день."""
    clipped = sorted((max(a, start), min(b, end)) for a, b in intervals if a < end and b > start)
    merged: list[list[datetime]] = []
    for a, b in clipped:
        if merged and a <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], b)
        else:
            merged.append([a, b])
    new_start, new_end = start, end
    for a, b in merged:
        if a <= new_start < b:
            new_start = b
    for a, b in reversed(merged):
        if a < new_end <= b:
            new_end = a
    if new_start >= new_end:
        return None, None
    return new_start, new_end


def _teacher_lesson_bounds(user_ids, start: date, end: date) -> dict[tuple[int, date], tuple]:
    """{(user_id, день): (первое начало, последний конец)} проведённых/плановых
    занятий. Тренер занятия — Lesson.teacher, иначе тренер GroupTeacher
    (как Lesson.effective_teacher)."""
    from apps.academy.models import Lesson

    rows = (
        Lesson.objects.filter(date__range=(start, end))
        .exclude(status=Lesson.Status.CANCELLED)
        .filter(Q(teacher__user_id__in=user_ids)
                | Q(teacher__isnull=True, group_teacher__teacher__user_id__in=user_ids))
        .values_list("teacher__user_id", "group_teacher__teacher__user_id", "date", "start_time", "end_time")
    )
    bounds: dict[tuple[int, date], tuple] = {}
    for own, via_group, day, lesson_start, lesson_end in rows:
        uid = own or via_group
        if uid is None or lesson_start is None or lesson_end is None:
            continue
        lo, hi = bounds.get((uid, day), (lesson_start, lesson_end))
        bounds[(uid, day)] = (min(lo, lesson_start), max(hi, lesson_end))
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
