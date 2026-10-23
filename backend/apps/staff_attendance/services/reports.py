"""Дневные строки посещаемости, сводка и месячная статистика — только из
реальных сессий в БД.

Строка = сотрудник × день. Несколько сессий за день (вышел и вернулся)
сводятся в одну строку: первый приход, последний уход, сумма длительностей,
опоздание — по первой сессии дня.

Отсутствие отметки не считается отсутствием сотрудника, пока не закончилось
его рабочее время: сегодня до конца окна — «Ещё не пришёл», после — «Нет
прихода»; в нерабочий для него день — «Выходной».
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from datetime import timezone as dt_timezone

from django.contrib.auth import get_user_model
from django.db.models import Q, QuerySet
from django.utils import timezone

from ..models import AttendanceSession, AttendanceSettings
from .schedule import ScheduleResolver, WorkWindow


class Status:
    NOT_ARRIVED = "not_arrived"
    AT_WORK = "at_work"
    DAY_FINISHED = "day_finished"
    NO_CHECK_IN = "no_check_in"
    NO_CHECK_OUT = "no_check_out"
    DAY_OFF = "day_off"
    # До начала учёта (запуск модуля или дата регистрации сотрудника).
    NOT_TRACKED = "not_tracked"
    # Флаги-фильтры (у строки одновременно с основным статусом).
    LATE = "late"
    ADJUSTED = "adjusted"


STATUS_LABELS = {
    Status.NOT_ARRIVED: "Ещё не пришёл",
    Status.AT_WORK: "На работе",
    Status.DAY_FINISHED: "День завершён",
    Status.NO_CHECK_IN: "Нет прихода",
    Status.NO_CHECK_OUT: "Нет ухода",
    Status.DAY_OFF: "Выходной",
    Status.NOT_TRACKED: "Учёт не вёлся",
    Status.LATE: "Опоздание",
    Status.ADJUSTED: "Исправлена запись",
}

MAX_RANGE_DAYS = 93


@dataclass
class DayRow:
    user: object
    day: date
    sessions: list = field(default_factory=list)
    window: WorkWindow | None = None
    status: str = Status.NOT_ARRIVED
    first_in: datetime | None = None
    last_out: datetime | None = None
    duration_seconds: int = 0
    late_minutes: int = 0
    is_adjusted: bool = False

    @property
    def is_late(self) -> bool:
        return self.late_minutes > 0

    def matches(self, status: str | None) -> bool:
        if not status:
            return True
        if status == Status.LATE:
            return self.is_late
        if status == Status.ADJUSTED:
            return self.is_adjusted
        return self.status == status


def employees(config: AttendanceSettings, scope: Q, *, search: str = "", role: str = "") -> QuerySet:
    qs = get_user_model().objects.filter(is_active=True, role__in=config.tracked_roles or []).filter(scope)
    if role:
        qs = qs.filter(role=role)
    if search:
        for word in search.split()[:4]:
            qs = qs.filter(Q(first_name__icontains=word) | Q(last_name__icontains=word)
                           | Q(username__icontains=word) | Q(email__icontains=word))
    return qs.select_related("teacher_profile").order_by("last_name", "first_name", "username", "pk")


def _session_seconds(session: AttendanceSession, now: datetime) -> int:
    if session.checked_out_at is not None:
        return int((session.checked_out_at - session.checked_in_at).total_seconds())
    if session.status == AttendanceSession.Status.OPEN:
        return max(0, int((now - session.checked_in_at).total_seconds()))
    return 0  # «Нет ухода»: длительность неизвестна и не выдумывается


def tracked_since(config: AttendanceSettings, user) -> date:
    """С какого дня у сотрудника вообще есть учёт: не раньше запуска модуля
    и не раньше регистрации сотрудника в LMS."""
    joined = getattr(user, "date_joined", None)
    joined_day = timezone.localtime(joined, config.tzinfo).date() if joined else config.tracking_started_on
    return max(config.tracking_started_on, joined_day)


def build_row(user, day: date, sessions: list, window: WorkWindow | None, now: datetime, today: date,
              since: date | None = None) -> DayRow:
    if since is not None and day < since and not sessions:
        return DayRow(user=user, day=day, status=Status.NOT_TRACKED)
    row = DayRow(user=user, day=day, sessions=sessions, window=window)
    if sessions:
        ordered = sorted(sessions, key=lambda s: (s.checked_in_at, s.pk))
        row.sessions = ordered
        row.first_in = ordered[0].checked_in_at
        outs = [s.checked_out_at for s in ordered if s.checked_out_at]
        row.last_out = max(outs) if outs else None
        row.duration_seconds = sum(_session_seconds(s, now) for s in ordered)
        row.late_minutes = ordered[0].late_minutes
        row.is_adjusted = any(s.is_adjusted for s in ordered)
        statuses = {s.status for s in ordered}
        if AttendanceSession.Status.OPEN in statuses:
            row.status = Status.AT_WORK if day >= today else Status.NO_CHECK_OUT
            if day >= today:
                row.last_out = None
        elif AttendanceSession.Status.MISSING_CHECKOUT in statuses:
            row.status = Status.NO_CHECK_OUT
        else:
            row.status = Status.DAY_FINISHED
        return row
    if window is None:
        row.status = Status.DAY_OFF
    elif day > today or (day == today and now < window.end):
        row.status = Status.NOT_ARRIVED
    else:
        row.status = Status.NO_CHECK_IN
    return row


def day_rows(config: AttendanceSettings, users: list, day: date, *, now: datetime | None = None) -> list[DayRow]:
    now = now or timezone.now()
    today = timezone.localtime(now, config.tzinfo).date()
    by_user = defaultdict(list)
    for session in AttendanceSession.objects.filter(user__in=users, work_date=day).select_related("location"):
        by_user[session.user_id].append(session)
    resolver = ScheduleResolver(config, users, day)
    return [build_row(u, day, by_user.get(u.pk, []), resolver.window(u), now, today, tracked_since(config, u))
            for u in users]


def range_rows(config: AttendanceSettings, users: list, date_from: date, date_to: date,
               *, now: datetime | None = None) -> list[DayRow]:
    rows = []
    day = date_from
    while day <= date_to:
        rows.extend(day_rows(config, users, day, now=now))
        day += timedelta(days=1)
    return rows


def overview(rows: list[DayRow]) -> dict:
    return {
        "total_employees": len(rows),
        "arrived": sum(1 for r in rows if r.sessions),
        "at_work": sum(1 for r in rows if r.status == Status.AT_WORK),
        "late": sum(1 for r in rows if r.is_late),
        "finished": sum(1 for r in rows if r.status == Status.DAY_FINISHED),
        "not_arrived": sum(1 for r in rows if r.status == Status.NOT_ARRIVED),
        "no_check_in": sum(1 for r in rows if r.status == Status.NO_CHECK_IN),
        "no_check_out": sum(1 for r in rows if r.status == Status.NO_CHECK_OUT),
        "day_off": sum(1 for r in rows if r.status == Status.DAY_OFF),
        "not_tracked": sum(1 for r in rows if r.status == Status.NOT_TRACKED),
        "adjusted": sum(1 for r in rows if r.is_adjusted),
    }


_MIN = datetime.min.replace(tzinfo=dt_timezone.utc)

SORT_KEYS = {
    "name": lambda r: ((r.user.last_name or "").lower(), (r.user.first_name or "").lower(), r.user.pk),
    "role": lambda r: (r.user.role, (r.user.last_name or "").lower()),
    "date": lambda r: (r.day, (r.user.last_name or "").lower()),
    "check_in": lambda r: (r.first_in is None, r.first_in or _MIN),
    "check_out": lambda r: (r.last_out is None, r.last_out or _MIN),
    "duration": lambda r: r.duration_seconds,
    "late": lambda r: r.late_minutes,
    "status": lambda r: r.status,
}


def sort_rows(rows: list[DayRow], ordering: str) -> list[DayRow]:
    desc = ordering.startswith("-")
    key = SORT_KEYS.get(ordering.lstrip("-"), SORT_KEYS["name"])
    return sorted(rows, key=key, reverse=desc)


def month_bounds(year: int, month: int) -> tuple[date, date]:
    first = date(year, month, 1)
    nxt = date(year + (month == 12), month % 12 + 1, 1)
    return first, nxt - timedelta(days=1)


def month_stats(config: AttendanceSettings, user, year: int, month: int, *, now: datetime | None = None) -> dict:
    """Месячная статистика одного сотрудника: по дням до сегодняшнего
    включительно (будущие дни не считаются ни пропусками, ни выходными)."""
    now = now or timezone.now()
    today = timezone.localtime(now, config.tzinfo).date()
    first, last = month_bounds(year, month)
    last = min(last, today)
    rows = range_rows(config, [user], first, last, now=now) if first <= last else []
    worked = [r for r in rows if r.sessions]
    return {
        "year": year,
        "month": month,
        "days_present": len(worked),
        "work_days": sum(1 for r in rows if r.window is not None),
        "late_days": sum(1 for r in rows if r.is_late),
        "late_minutes_total": sum(r.late_minutes for r in rows),
        "no_check_in_days": sum(1 for r in rows if r.status == Status.NO_CHECK_IN),
        "no_check_out_days": sum(1 for r in rows if r.status == Status.NO_CHECK_OUT),
        "adjusted_days": sum(1 for r in rows if r.is_adjusted),
        "total_seconds": sum(r.duration_seconds for r in worked),
        "average_seconds": int(sum(r.duration_seconds for r in worked) / len(worked)) if worked else 0,
    }
