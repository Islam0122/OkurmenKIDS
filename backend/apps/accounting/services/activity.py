"""Источники активности для расчёта: когда студент был активен и в какой
группе, когда сотрудник был тренером группы.

Всё считается по истории LMS, а не по текущему состоянию: студент —
по `StudentStatusEvent` (деактивация, пауза, завершение, возврат,
перевод), тренер — по `TrainerAssignment`. Поэтому пересчёт прошлого
периода даёт тот же результат, что и в момент расчёта, даже если с тех пор
студент ушёл или группа сменила тренера.

Правило активного студента (настраивается здесь, одно на весь модуль):
студент считается активным в день D, если на D его статус «Активен» и он
числится в группе. «На паузе», «Завершил обучение», «Деактивирован» —
неактивен; день ухода (дата события) уже не считается активным, день
возврата — считается. Первый активный день — дата начала обучения
(`enrollment_date`, иначе дата создания записи).
"""
from __future__ import annotations

import datetime as dt
from collections import defaultdict
from dataclasses import dataclass

from django.db.models import Q

from apps.academy.models import Group, Student, StudentStatusEvent, TrainerAssignment

ACTIVE = Student.Status.ACTIVE

_STATUS_AFTER = {
    StudentStatusEvent.EventType.DEACTIVATED: Student.Status.WITHDRAWN,
    StudentStatusEvent.EventType.PAUSED: Student.Status.PAUSED,
    StudentStatusEvent.EventType.COMPLETED: Student.Status.COMPLETED,
    StudentStatusEvent.EventType.CONTINUED: Student.Status.ACTIVE,
    StudentStatusEvent.EventType.REACTIVATED: Student.Status.ACTIVE,
}


@dataclass(frozen=True)
class Segment:
    start: dt.date
    end: dt.date | None  # не включительно; None — до сих пор
    status: str
    group_id: int | None

    def days_within(self, lo: dt.date, hi: dt.date):
        start = max(self.start, lo)
        stop = hi if self.end is None else min(hi, self.end - dt.timedelta(days=1))
        day = start
        while day <= stop:
            yield day
            day += dt.timedelta(days=1)


def student_segments(student: Student, events: list[StudentStatusEvent]) -> list[Segment]:
    """История «статус + группа» студента в виде непрерывных отрезков."""
    start = student.enrollment_date or student.created_at.date()
    events = sorted(events, key=lambda e: (e.event_date, e.created_at, e.id))
    if not events:
        return [Segment(start, None, student.status, student.group_id)]

    first = events[0]
    if first.event_type == StudentStatusEvent.EventType.TRANSFERRED:
        status, group_id = first.previous_status or ACTIVE, first.from_group_id
    elif first.event_type in (StudentStatusEvent.EventType.CONTINUED, StudentStatusEvent.EventType.REACTIVATED):
        status = first.previous_status or (
            Student.Status.PAUSED if first.event_type == StudentStatusEvent.EventType.CONTINUED else Student.Status.WITHDRAWN
        )
        group_id = None
    else:
        status, group_id = first.previous_status or ACTIVE, first.group_id

    segments: list[Segment] = []
    cursor = start
    for event in events:
        if event.event_date > cursor:
            segments.append(Segment(cursor, event.event_date, status, group_id))
            cursor = event.event_date
        elif event.event_date < cursor:
            # Событие раньше даты начала обучения (неполные данные) — меняет
            # только состояние, без отрезка в прошлом.
            pass
        if event.event_type == StudentStatusEvent.EventType.TRANSFERRED:
            group_id = event.group_id
        else:
            status = _STATUS_AFTER.get(event.event_type, status)
            if event.event_type in (StudentStatusEvent.EventType.CONTINUED, StudentStatusEvent.EventType.REACTIVATED):
                group_id = event.group_id or group_id
    segments.append(Segment(cursor, None, status, group_id))
    return segments


def active_student_days(start: dt.date, end: dt.date, *, group_ids=None) -> dict[int, dict[dt.date, int]]:
    """{student_id: {день: group_id}} — дни [start, end], когда студент был
    активен, и группа, в которой он числился. `group_ids` — ограничить
    группами (None — все)."""
    candidates = Student.objects.filter(
        Q(enrollment_date__lte=end) | Q(enrollment_date__isnull=True, created_at__date__lte=end)
    )
    if group_ids is not None:
        group_ids = set(group_ids)
        candidates = candidates.filter(
            Q(group_id__in=group_ids)
            | Q(status_events__group_id__in=group_ids)
            | Q(status_events__from_group_id__in=group_ids)
        ).distinct()
    students = list(candidates)
    events_by_student: dict[int, list] = defaultdict(list)
    for event in StudentStatusEvent.objects.filter(student__in=[s.pk for s in students]):
        events_by_student[event.student_id].append(event)

    result: dict[int, dict[dt.date, int]] = {}
    for student in students:
        days: dict[dt.date, int] = {}
        for segment in student_segments(student, events_by_student[student.pk]):
            if segment.status != ACTIVE or segment.group_id is None:
                continue
            if group_ids is not None and segment.group_id not in group_ids:
                continue
            for day in segment.days_within(start, end):
                days[day] = segment.group_id
        if days:
            result[student.pk] = days
    return result


def group_active_days(group: Group, start: dt.date, end: dt.date) -> set[dt.date]:
    """Дни [start, end], когда группа существовала (по датам группы).
    Отменённая группа не учитывается вовсе."""
    if group.status == Group.Status.CANCELLED:
        return set()
    lo = max(start, group.start_date)
    hi = min(end, group.end_date) if group.end_date else end
    return set(_days(lo, hi))


def trainer_days(teacher_id: int | None, start: dt.date, end: dt.date) -> dict[int, set[dt.date]]:
    """{group_id: дни [start, end], когда тренер отвечал за группу} — по
    истории назначений (полуинтервал [start_date, end_date))."""
    result: dict[int, set[dt.date]] = defaultdict(set)
    if teacher_id is None:
        return result
    rows = TrainerAssignment.objects.filter(teacher_id=teacher_id, start_date__lte=end).filter(
        Q(end_date__isnull=True) | Q(end_date__gt=start)
    )
    for row in rows:
        stop = end if row.end_date is None else min(end, row.end_date - dt.timedelta(days=1))
        result[row.group_id].update(_days(max(start, row.start_date), stop))
    return result


def trainer_group_ids_ever(teacher_id: int | None) -> set[int]:
    if teacher_id is None:
        return set()
    return set(TrainerAssignment.objects.filter(teacher_id=teacher_id).values_list("group_id", flat=True))


def _days(lo: dt.date, hi: dt.date):
    day = lo
    while day <= hi:
        yield day
        day += dt.timedelta(days=1)


def days_between(lo: dt.date, hi: dt.date) -> set[dt.date]:
    return set(_days(lo, hi))
