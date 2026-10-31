"""Посещаемость сотрудников — только чтение из apps.staff_attendance (QR,
геозона, общее и личное расписание, льготные минуты, выходные). Второй
системы отметки нет: здесь лишь сводка в терминах операционного кабинета.

Статусы кабинета ← статусы staff_attendance:

    PRESENT          пришёл вовремя (на работе или день завершён)
    LATE             пришёл позже окна с учётом льготных минут
    ABSENT           рабочий день закончился, прихода нет
    NOT_CHECKED_OUT  пришёл, но не отметил уход (прошлые дни)
    NOT_ARRIVED      сегодня, рабочее время ещё идёт — не нарушение
    DAY_OFF          нерабочий день по расписанию
    NOT_TRACKED      учёт ещё не вёлся

ON_LEAVE и REMOTE: в LMS нет учёта отпусков и удалённой работы — вопрос к
руководству (docs/operations.md); до появления данных такие дни выглядят
как обычные рабочие.
"""
from __future__ import annotations

import datetime as dt

from apps.staff_attendance.models import AttendanceSettings
from apps.staff_attendance.services import reports as sa
from apps.users.models import User

from ..departments import department_of

PRESENT, LATE, ABSENT, NOT_CHECKED_OUT, NOT_ARRIVED, DAY_OFF, NOT_TRACKED = (
    "present", "late", "absent", "not_checked_out", "not_arrived", "day_off", "not_tracked")

LABELS = {
    PRESENT: "Присутствует", LATE: "Опоздание", ABSENT: "Отсутствует", NOT_CHECKED_OUT: "Нет отметки ухода",
    NOT_ARRIVED: "Ещё не пришёл", DAY_OFF: "Выходной", NOT_TRACKED: "Учёт не вёлся",
}
MAX_RANGE_DAYS = sa.MAX_RANGE_DAYS


def ops_status(row: sa.DayRow) -> str:
    if row.status == sa.Status.DAY_OFF:
        return DAY_OFF
    if row.status == sa.Status.NOT_TRACKED:
        return NOT_TRACKED
    if row.status == sa.Status.NO_CHECK_IN:
        return ABSENT
    if row.status == sa.Status.NOT_ARRIVED:
        return NOT_ARRIVED
    if row.status == sa.Status.NO_CHECK_OUT:
        return NOT_CHECKED_OUT
    return LATE if row.is_late else PRESENT


def tracked_users(qs=None) -> list:
    config = AttendanceSettings.load()
    qs = qs if qs is not None else User.objects.all()
    return list(qs.filter(is_active=True, role__in=config.tracked_roles or []).order_by("first_name", "last_name"))


def rows(users: list, start: dt.date, end: dt.date, *, now=None) -> list[sa.DayRow]:
    if not users:
        return []
    return sa.range_rows(AttendanceSettings.load(), users, start, end, now=now)


def serialize_row(row: sa.DayRow) -> dict:
    status = ops_status(row)
    location = next((s.location for s in row.sessions if getattr(s, "location_id", None)), None)
    distance = next((s.check_in_distance_m for s in row.sessions
                     if getattr(s, "check_in_distance_m", None) is not None), None)
    return {
        "user": {"id": row.user.pk, "full_name": row.user.get_full_name() or row.user.username,
                 "role": row.user.role, "role_label": row.user.get_role_display(),
                 "department": department_of(row.user)},
        "date": row.day.isoformat(),
        "status": status,
        "status_label": LABELS[status],
        "check_in": row.first_in,
        "check_out": row.last_out,
        "worked_minutes": row.duration_seconds // 60,
        "late_minutes": row.late_minutes,
        "expected_start": row.window.start if row.window else None,
        "expected_end": row.window.end if row.window else None,
        "location": location.name if location else None,
        # Геозона проверена сервером при отметке (иначе отметку бы не приняли);
        # для ручных записей администратора проверки не было.
        "geo_verified": bool(row.sessions) and all(getattr(s, "source", "") != "manual" for s in row.sessions),
        "distance_m": distance,
        "adjusted": row.is_adjusted,
    }


def summarize(day_rows: list[sa.DayRow]) -> dict:
    counts = {key: 0 for key in LABELS}
    worked = late = 0
    for row in day_rows:
        counts[ops_status(row)] += 1
        worked += row.duration_seconds
        late += row.late_minutes
    expected = counts[PRESENT] + counts[LATE] + counts[ABSENT] + counts[NOT_CHECKED_OUT]
    attended = counts[PRESENT] + counts[LATE] + counts[NOT_CHECKED_OUT]
    return {
        "counts": counts,
        "expected_days": expected,
        "attended_days": attended,
        "attendance_rate": round(attended / expected * 100, 1) if expected else None,
        "punctuality_rate": round(counts[PRESENT] / attended * 100, 1) if attended else None,
        "worked_hours": round(worked / 3600, 1),
        "late_minutes": late,
    }
