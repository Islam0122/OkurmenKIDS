"""A weekly slot (GroupSchedule) changed → its future lessons follow.

The slot is the source of truth for the lessons it generated
(Lesson.schedule). When its day, time, room or teacher change, the lessons
of *that slot only* that are still open take the new values; history never
moves.

Which lessons move — all of:
  * Lesson.schedule is this slot (never "every lesson of the group": a
    group's other programs / subjects / trainers have their own slots);
  * still following the slot: on the slot's old weekday at its old
    start/end time (a lesson someone moved by hand, or a make-up placed
    elsewhere, is left alone);
  * open: status SCHEDULED, never started, no attendance and no homework
    results (the same «history» rule as the generator's sync —
    lesson_generator._lesson_is_locked), dated today or later.
COMPLETED / CANCELLED / IN_PROGRESS, past and data-carrying lessons are
never touched.

What changes:
  * time — start_time / end_time become the slot's, the date stays;
  * weekday — each lesson moves forward to the next new weekday on or after
    its own date (Sun 19.10 → Sat 25.10): every lesson shifts by the same
    0–6 days, so their order is kept, none lands in the past and no two
    collide;
  * room / teacher — only where the lesson still had the slot's old room /
    teacher (a lesson with its own room or substitute keeps it).
The subject is not synced: a program's subject can only change while it has
no lessons (program_editing.update_teaching_program).

Every moved lesson is checked against the lessons it would overlap — the
same group, the same teacher, the same room — and the group's end date;
any problem raises ValidationError and, inside the caller's transaction,
rolls back the slot change too: never «slot at 12:00, half its lessons at
10:00». Real times only (TimeField / DateField) — no timezone arithmetic.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from ..constants import WEEKDAY_CODES
from ..models import Attendance, GroupSchedule, HomeworkResult, Lesson

_MAX_LISTED = 5


@dataclass(frozen=True)
class SlotSnapshot:
    """A slot's lesson-relevant values before an edit."""

    day_of_week: str
    start_time: dt.time
    end_time: dt.time
    room_id: int | None
    teacher_id: int | None


def snapshot(slot: GroupSchedule) -> SlotSnapshot:
    return SlotSnapshot(slot.day_of_week, slot.start_time, slot.end_time, slot.room_id, slot.teacher_id)


@dataclass
class LessonSyncResult:
    updated: int = 0
    # Future lessons of the slot left as they are (history, started, with
    # data, or moved by hand) — reported, never changed.
    kept: int = 0


def _overlaps(a_start, a_end, b_start, b_end) -> bool:
    return a_start < b_end and b_start < a_end


def _fmt(lesson: Lesson, date: dt.date, start: dt.time) -> str:
    return f"№{lesson.lesson_number} {date:%d.%m.%Y} {start:%H:%M}"


def sync_schedule_lessons(slot: GroupSchedule, before: SlotSnapshot, *, today: dt.date | None = None) -> LessonSyncResult:
    """Bring `slot`'s open future lessons in line with the slot as saved now
    (`before` — its values before the edit). Call inside the transaction
    that saved the slot; raises ValidationError on any clash."""
    result = LessonSyncResult()
    after = snapshot(slot)
    if after == before:
        return result
    today = today or timezone.localdate()
    old_weekday = WEEKDAY_CODES.index(before.day_of_week)
    shift = dt.timedelta(days=(WEEKDAY_CODES.index(after.day_of_week) - old_weekday) % 7)

    with transaction.atomic():
        future = list(
            Lesson.objects.select_for_update()
            .filter(schedule=slot, date__gte=today)
            .exclude(status=Lesson.Status.CANCELLED)
            .order_by("date", "start_time", "pk")
        )
        ids = [lesson.pk for lesson in future]
        with_data = set(
            Attendance.objects.filter(lesson_id__in=ids).values_list("lesson_id", flat=True)
        ) | set(
            HomeworkResult.objects.filter(homework__lesson_id__in=ids).values_list("homework__lesson_id", flat=True)
        )
        movable = []
        for lesson in future:
            following = (
                lesson.date.weekday() == old_weekday
                and lesson.start_time == before.start_time
                and lesson.end_time == before.end_time
            )
            open_ = lesson.status == Lesson.Status.SCHEDULED and lesson.started_at is None and lesson.pk not in with_data
            if following and open_:
                movable.append(lesson)
            else:
                result.kept += 1
        if not movable:
            return result

        group = slot.group
        planned = []
        for lesson in movable:
            planned.append((
                lesson,
                lesson.date + shift,
                after.room_id if lesson.room_id == before.room_id else lesson.room_id,
                after.teacher_id if lesson.teacher_id == before.teacher_id else lesson.teacher_id,
            ))
        _validate(group, slot, planned, after, {lesson.pk for lesson in movable})

        now = timezone.now()
        for lesson, date, room_id, teacher_id in planned:
            lesson.date = date
            lesson.start_time = after.start_time
            lesson.end_time = after.end_time
            lesson.room_id = room_id
            lesson.teacher_id = teacher_id
            lesson.updated_at = now
        Lesson.objects.bulk_update(movable, ["date", "start_time", "end_time", "room", "teacher", "updated_at"])
        result.updated = len(movable)
    return result


def _validate(group, slot, planned, after: SlotSnapshot, moving_ids: set[int]) -> None:
    """Every moved lesson must fit: within the group's period and free of
    the group's, the teacher's and the room's other (non-cancelled)
    lessons on its new date."""
    problems = []
    if group.end_date:
        late = [lesson for lesson, date, _room, _teacher in planned if date > group.end_date]
        if late:
            listed = ", ".join(_fmt(lesson, lesson.date, lesson.start_time) for lesson in late[:_MAX_LISTED])
            problems.append(f"Занятия выйдут за дату окончания группы ({group.end_date:%d.%m.%Y}): {listed}.")

    dates = {date for _lesson, date, _room, _teacher in planned}
    teacher_ids = {teacher for *_rest, teacher in planned if teacher}
    room_ids = {room for _lesson, _date, room, _teacher in planned if room}
    others = list(
        Lesson.objects.filter(date__in=dates)
        .exclude(pk__in=moving_ids)
        .exclude(status=Lesson.Status.CANCELLED)
        .filter(
            Q(group=group)
            | Q(teacher_id__in=teacher_ids)
            | Q(teacher__isnull=True, group_teacher__teacher_id__in=teacher_ids)
            | Q(room_id__in=room_ids)
        )
        .select_related("group", "group_teacher")
    )
    by_date: dict[dt.date, list[Lesson]] = {}
    for other in others:
        by_date.setdefault(other.date, []).append(other)

    clashes = {"group": [], "teacher": [], "room": []}
    for lesson, date, room_id, teacher_id in planned:
        for other in by_date.get(date, []):
            if not _overlaps(after.start_time, after.end_time, other.start_time, other.end_time):
                continue
            other_teacher = other.teacher_id or (other.group_teacher.teacher_id if other.group_teacher_id else None)
            label = _fmt(lesson, date, after.start_time)
            if other.group_id == group.pk:
                clashes["group"].append(f"{label} — у группы уже есть занятие {other.start_time:%H:%M}")
            elif teacher_id and other_teacher == teacher_id:
                clashes["teacher"].append(f"{label} — тренер занят в группе «{other.group.name}»")
            elif room_id and other.room_id == room_id:
                clashes["room"].append(f"{label} — аудитория занята группой «{other.group.name}»")
    for messages in clashes.values():
        unique = list(dict.fromkeys(messages))
        if unique:
            more = f" и ещё {len(unique) - _MAX_LISTED}" if len(unique) > _MAX_LISTED else ""
            problems.append("Будущие занятия нельзя перенести: " + "; ".join(unique[:_MAX_LISTED]) + more + ".")
    if problems:
        raise ValidationError(problems)
