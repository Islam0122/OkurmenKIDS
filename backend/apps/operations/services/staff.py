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
    VACATION         отпуск (исключение из графика)
    SICK_LEAVE       больничный (исключение из графика)
    EXCUSED_ABSENCE  «Отсутствует по разрешению»: весь рабочий день отпущен
    PERMITTED_LATE   «Разрешено опоздать»: пришёл не позже сдвинутого начала
    PERMITTED_EARLY  «Разрешён ранний уход»
    PERMITTED_PARTIAL «Отпросился»: отпущен на часть дня
    EXCLUDED         суперпользователь исключил сотрудника из расчётов
    NOT_TRACKED      учёт ещё не вёлся

Разрешения «Отпросился» учитываются в staff_attendance (ScheduleResolver):
сдвигают ожидаемый приход/уход, полный день — не отсутствие; опоздание
пересчитывается тем же правилом. Статусы «по разрешению» засчитываются как
присутствие вовремя: в посещаемость, пунктуальность и KPI — без штрафа.

Отпуска, больничные и отгулы — исключения из графика
(staff_attendance.AttendanceScheduleException). Удалённой работы в LMS нет.

«По графику» (`schedule` в строке) — план дня из того же ScheduleResolver,
по которому при отметке по QR считается опоздание: время прихода, льготные
минуты и источник (личный график / общий / по занятиям / исключение).
"""
from __future__ import annotations

import datetime as dt

from django.utils.timezone import localtime

from apps.staff_attendance.models import AttendanceSettings
from apps.staff_attendance.services import reports as sa
from apps.staff_attendance.services.schedule import PlanKind
from apps.users.models import User

from ..departments import Department, department_of

PRESENT, LATE, ABSENT, NOT_CHECKED_OUT, NOT_ARRIVED, DAY_OFF, NOT_TRACKED = (
    "present", "late", "absent", "not_checked_out", "not_arrived", "day_off", "not_tracked")
VACATION, SICK_LEAVE = PlanKind.VACATION, PlanKind.SICK_LEAVE
EXCUSED_ABSENCE, PERMITTED_LATE, PERMITTED_EARLY, PERMITTED_PARTIAL, EXCLUDED = (
    "excused_absence", "permitted_late", "permitted_early_leave", "permitted_partial", "excluded")
PERMITTED = (PERMITTED_LATE, PERMITTED_EARLY, PERMITTED_PARTIAL)

LABELS = {
    PRESENT: "Присутствует", LATE: "Опоздание", ABSENT: "Отсутствует", NOT_CHECKED_OUT: "Нет отметки ухода",
    NOT_ARRIVED: "Ещё не пришёл", DAY_OFF: "Выходной", VACATION: "Отпуск", SICK_LEAVE: "Больничный",
    EXCUSED_ABSENCE: "Отсутствует по разрешению", PERMITTED_LATE: "Разрешено опоздать",
    PERMITTED_EARLY: "Разрешён ранний уход", PERMITTED_PARTIAL: "Отпросился",
    EXCLUDED: "Не учитывается", NOT_TRACKED: "Учёт не вёлся",
}

SOURCE_LABELS = {
    "personal": "Личный график", "default": "Общий график", "lessons": "По занятиям", "exception": "Исключение",
}
MAX_RANGE_DAYS = sa.MAX_RANGE_DAYS


def ops_status(row: sa.DayRow) -> str:
    if row.status == sa.Status.EXCLUDED:
        return EXCLUDED
    if row.status == sa.Status.EXCUSED:
        return EXCUSED_ABSENCE
    if row.status == sa.Status.DAY_OFF:
        kind = row.plan.kind if row.plan else None
        return kind if kind in (VACATION, SICK_LEAVE) else DAY_OFF
    if row.status == sa.Status.NOT_TRACKED:
        return NOT_TRACKED
    if row.status == sa.Status.NO_CHECK_IN:
        return ABSENT
    if row.status == sa.Status.NOT_ARRIVED:
        return NOT_ARRIVED
    if row.status == sa.Status.NO_CHECK_OUT:
        return NOT_CHECKED_OUT
    if row.is_late:
        return LATE
    return _permission_status(row) or PRESENT


def _permission_status(row: sa.DayRow) -> str | None:
    """Пришёл вовремя по графику с учётом разрешения — какое разрешение
    сработало. Нарушения (опоздание сверх разрешённого, нет ухода, нет
    прихода) разрешение не скрывает."""
    plan = row.plan
    if plan is None or not plan.permissions or plan.base_window is None or plan.window is None:
        return None
    base, win = plan.base_window, plan.window
    if win.start > base.start:
        return PERMITTED_LATE
    if win.end < base.end:
        return PERMITTED_EARLY
    return PERMITTED_PARTIAL


def tracked_users(qs=None) -> list:
    config = AttendanceSettings.load()
    qs = qs if qs is not None else User.objects.staff()
    return list(qs.filter(is_active=True, role__in=config.tracked_roles or [])
                .exclude(attendance_profile__tracking_enabled=False)  # учёт выключен суперпользователем
                .order_by("first_name", "last_name"))


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
                 "department": department_of(row.user),
                 "department_label": Department(department_of(row.user)).label},
        "date": row.day.isoformat(),
        "status": status,
        "status_label": LABELS[status],
        "check_in": row.first_in,
        "check_out": row.last_out,
        "worked_minutes": row.duration_seconds // 60,
        "late_minutes": row.late_minutes,
        "expected_start": row.window.start if row.window else None,
        "expected_end": row.window.end if row.window else None,
        "schedule": schedule_info(row),
        "location": location.name if location else None,
        # Геозона проверена сервером при отметке (иначе отметку бы не приняли);
        # для ручных записей администратора проверки не было.
        "geo_verified": bool(row.sessions) and all(getattr(s, "source", "") != "manual" for s in row.sessions),
        "distance_m": distance,
        "adjusted": row.is_adjusted,
        "permissions": [permission_brief(p, _office_tz(row)) for p in (row.plan.permissions if row.plan else ())],
    }


def _office_tz(row: sa.DayRow):
    # Пояс офиса приходит с планом дня — без запроса настроек на каждую строку.
    tz = row.plan.tz if row.plan else None
    return tz or AttendanceSettings.load().tzinfo


def permission_brief(perm, tz=None) -> dict:
    tz = tz or AttendanceSettings.load().tzinfo
    start, end = localtime(perm.starts_at, tz), localtime(perm.ends_at, tz)
    return {
        "id": perm.pk,
        "kind": perm.kind,
        "kind_label": perm.get_kind_display(),
        "starts_at": start.isoformat(),
        "ends_at": end.isoformat(),
        "period_label": _period_label(perm.kind, start, end),
        "reason": perm.reason,
        "comment": perm.comment,
        "approved_by": str(perm.approved_by) if perm.approved_by_id else None,
    }


def _period_label(kind: str, start, end) -> str:
    if kind == "full_day":
        last = (end - dt.timedelta(minutes=1)).date()
        return f"{start:%d.%m}" if last == start.date() else f"{start:%d.%m}–{last:%d.%m}"
    return f"{start:%d.%m} {start:%H:%M}–{end:%H:%M}" if end.time() != dt.time(0, 0) else f"{start:%d.%m} {start:%H:%M}–24:00"


def schedule_info(row: sa.DayRow) -> dict:
    """«По графику»: когда сотрудник должен прийти в этот день. Время — в
    часовом поясе офиса (строкой, чтобы браузер не пересчитывал его в свой
    пояс). kind: work | day_off | vacation | sick_leave | not_set."""
    plan = row.plan
    window = plan.window if plan else None
    kind = plan.kind if plan else PlanKind.NOT_SET
    exception = plan.exception if plan else None
    source = plan.source if plan else None
    if window is not None:
        label = f"{window.start:%H:%M}"
    else:
        label = PlanKind.LABELS.get(kind, "Не задано")
    hint = SOURCE_LABELS.get(source, "")
    if source == "lessons" and window is None:
        hint = "Нет занятий"
    if exception is not None:
        if kind in (VACATION, SICK_LEAVE):
            hint = exception.note  # «Отпуск» / «Больничный» уже в label
        else:
            hint = exception.get_kind_display() + (f": {exception.note}" if exception.note else "")
    if kind == PlanKind.EXCUSED and plan.permissions:
        hint = "Отпросился: " + plan.permissions[0].reason
    base = plan.base_window if plan else None
    return {
        "kind": kind,
        "label": label,
        # До учёта разрешения «Отпросился» (если оно сдвинуло часы), иначе null.
        "base_expected_start": f"{base.start:%H:%M}" if base else None,
        "base_expected_end": f"{base.end:%H:%M}" if base else None,
        "expected_start": f"{window.start:%H:%M}" if window else None,
        "expected_end": f"{window.end:%H:%M}" if window else None,
        "grace_minutes": window.grace_minutes if window else None,
        "late_after": f"{window.late_after:%H:%M}" if window else None,
        "source": source,
        "source_label": hint,
    }


def summarize(day_rows: list[sa.DayRow]) -> dict:
    """Сводка. Дни «по разрешению» засчитываются как присутствие вовремя,
    полный день по разрешению, отпуск и больничный — не рабочие дни;
    исключённые из расчётов сотрудники не влияют ни на что."""
    counts = {key: 0 for key in LABELS}
    worked = late = 0
    for row in day_rows:
        status = ops_status(row)
        counts[status] += 1
        if status == EXCLUDED:
            continue
        worked += row.duration_seconds
        late += row.late_minutes
    permitted = sum(counts[k] for k in PERMITTED)
    expected = counts[PRESENT] + counts[LATE] + counts[ABSENT] + counts[NOT_CHECKED_OUT] + permitted
    attended = counts[PRESENT] + counts[LATE] + counts[NOT_CHECKED_OUT] + permitted
    return {
        "counts": counts,
        "expected_days": expected,
        "attended_days": attended,
        "attendance_rate": round(attended / expected * 100, 1) if expected else None,
        "punctuality_rate": round((counts[PRESENT] + permitted) / attended * 100, 1) if attended else None,
        "worked_hours": round(worked / 3600, 1),
        "late_minutes": late,
    }
