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
    lesson_generator._lesson_is_locked), and not moved by hand
    (Lesson.schedule_overridden — set when its date/time is edited);
  * still ahead: a later date, or today with its start still to come —
    in the project's time zone (settings.TIME_ZONE via timezone.localtime(),
    never the server clock). Today's lesson that already began or ended
    (running now, or forgotten without «Начать») is not moved, and neither
    is one whose new time today would already be past.
COMPLETED / CANCELLED / IN_PROGRESS, past, running and data-carrying lessons
are never touched.

What changes:
  * time — start_time / end_time become the slot's, the date stays;
  * weekday — each lesson moves to the new weekday *of its own week*
    (Monday–Sunday; Sun 19.10 → Sat 18.10, Sat 18.10 → Mon 13.10): a slot
    gives one lesson per week, so lessons keep their week, their order and
    never share a date — the same «one lesson per slot per week» the
    generator relies on (lesson_generator._Occupancy). A lesson whose new day
    in its week is already past stays where it is (reported as kept) rather
    than moving into the past or into another lesson's week;
  * room / teacher — only where the lesson still had the slot's old room /
    teacher (a lesson with its own room or substitute keeps it).
The subject is not synced: a program's subject can only change while it has
no lessons (program_editing.update_teaching_program).

Every moved lesson is checked against the lessons it would overlap — the
same group, the same teacher, the same room — and the group's end date;
any problem raises ValidationError and, inside the caller's transaction,
rolls back the slot change too: never «slot at 12:00, half its lessons at
10:00». Callers take the «before» snapshot from the slot row locked FOR
UPDATE in the same transaction, so two concurrent edits of one slot run one
after the other, each moving the lessons from where the previous one left
them. Real times only (TimeField / DateField) — no timezone arithmetic.
Repeating the same save is a no-op (the slot no longer differs from its
snapshot).

Two entry points, one rule set (lesson_is_open, follows_slot, target_date,
_find_problems, _move):
  * sync_schedule_lessons — a slot save: moves the lessons that followed
    the slot's *old* values; any clash rolls the save back.
  * attach_detached_lessons — a slot was *deleted* (Lesson.schedule set
    to NULL) and replaced by another one: the program's open future
    lessons left without a slot take its current slots, week by week. Run
    by every schedule save (strict) and by «Сгенерировать занятия».
  * align_schedule_lessons — «Сгенерировать занятия» (and its preview):
    no «before» exists, so it moves every open future lesson of the slot
    that is *not* on the slot's current day/time — whatever a slot edit
    left behind (made today, a path without sync, a clash back then). A
    clash here only keeps that lesson in place and is reported.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

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


def local_now(*, now: dt.datetime | None = None, today: dt.date | None = None) -> dt.datetime:
    """«Now» in the project's time zone. `today` (tests, callers that only
    know a date) means the very start of that day."""
    if now is not None:
        return timezone.localtime(now)
    if today is not None:
        return timezone.make_aware(dt.datetime.combine(today, dt.time.min))
    return timezone.localtime()


def is_ahead(date: dt.date, start: dt.time, now_local: dt.datetime) -> bool:
    return date > now_local.date() or (date == now_local.date() and start > now_local.time())


def ahead_q(now_local: dt.datetime) -> Q:
    """Lessons whose start is still to come (see is_ahead)."""
    return Q(date__gt=now_local.date()) | Q(date=now_local.date(), start_time__gt=now_local.time())


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


def target_date(date: dt.date, weekday: int) -> dt.date:
    """`date` moved to `weekday` (0=Monday) of its own Monday–Sunday week."""
    return date + dt.timedelta(days=weekday - date.weekday())


def follows_slot(lesson: Lesson, slot: GroupSchedule | SlotSnapshot) -> bool:
    """The lesson sits exactly where `slot` (or a snapshot of it) puts it:
    on its weekday, at its start and end time."""
    return (
        lesson.date.weekday() == WEEKDAY_CODES.index(slot.day_of_week)
        and lesson.start_time == slot.start_time
        and lesson.end_time == slot.end_time
    )


def lessons_with_data(lesson_ids) -> set[int]:
    """Of `lesson_ids`, the lessons with attendance or homework results."""
    return set(
        Attendance.objects.filter(lesson_id__in=lesson_ids).values_list("lesson_id", flat=True)
    ) | set(
        HomeworkResult.objects.filter(homework__lesson_id__in=lesson_ids).values_list("homework__lesson_id", flat=True)
    )


def lesson_is_open(lesson: Lesson, with_data: set[int]) -> bool:
    """Still free to follow its slot: SCHEDULED, never started, no
    attendance / homework results (lesson_generator._lesson_is_locked's
    «history» rule), and not moved by hand (Lesson.schedule_overridden)."""
    return (
        lesson.status == Lesson.Status.SCHEDULED
        and lesson.started_at is None
        and lesson.pk not in with_data
        and not lesson.schedule_overridden
    )


def _future_lessons(slot: GroupSchedule, now_local: dt.datetime) -> list[Lesson]:
    """`slot`'s own lessons (Lesson.schedule) still ahead, not cancelled,
    locked for the caller's transaction."""
    return list(
        Lesson.objects.select_for_update()
        .filter(schedule=slot)
        .filter(ahead_q(now_local))
        .exclude(status=Lesson.Status.CANCELLED)
        .order_by("date", "start_time", "pk")
    )


def _move(planned, start: dt.time, end: dt.time) -> None:
    """Write the planned (lesson, date, room_id, teacher_id) moves."""
    now = timezone.now()
    for lesson, date, room_id, teacher_id in planned:
        lesson.date = date
        lesson.start_time = start
        lesson.end_time = end
        lesson.room_id = room_id
        lesson.teacher_id = teacher_id
        lesson.updated_at = now
    Lesson.objects.bulk_update(
        [lesson for lesson, *_rest in planned], ["date", "start_time", "end_time", "room", "teacher", "updated_at"],
    )


def sync_schedule_lessons(slot: GroupSchedule, before: SlotSnapshot, *, today: dt.date | None = None,
                          now: dt.datetime | None = None) -> LessonSyncResult:
    """Bring `slot`'s open future lessons in line with the slot as saved now
    (`before` — its values before the edit). Call inside the transaction
    that saved the slot; raises ValidationError on any clash."""
    result = LessonSyncResult()
    after = snapshot(slot)
    if after == before:
        return result
    now_local = local_now(now=now, today=today)
    new_weekday = WEEKDAY_CODES.index(after.day_of_week)

    with transaction.atomic():
        future = _future_lessons(slot, now_local)
        with_data = lessons_with_data([lesson.pk for lesson in future])
        movable = []
        for lesson in future:
            lands_ahead = is_ahead(target_date(lesson.date, new_weekday), after.start_time, now_local)
            if follows_slot(lesson, before) and lesson_is_open(lesson, with_data) and lands_ahead:
                movable.append(lesson)
            else:
                result.kept += 1
        if not movable:
            return result

        planned = [
            (
                lesson,
                target_date(lesson.date, new_weekday),
                after.room_id if lesson.room_id == before.room_id else lesson.room_id,
                after.teacher_id if lesson.teacher_id == before.teacher_id else lesson.teacher_id,
            )
            for lesson in movable
        ]
        problems = _find_problems(slot.group, planned, after.start_time, after.end_time)
        if problems:
            raise ValidationError(_problem_messages(problems, slot.group))
        _move(planned, after.start_time, after.end_time)
        result.updated = len(movable)
    return result


@dataclass
class ScheduleAlignResult:
    """What align_schedule_lessons did to one slot's future lessons."""

    moved: list[Lesson] = field(default_factory=list)
    # Off the slot, but history / started / with data / moved by hand, or
    # their new time would already be past — left where they are.
    kept: int = 0
    # Could not move without a clash (or past the group's end date) — left
    # where they are, one message per problem.
    problems: list[str] = field(default_factory=list)


def align_schedule_lessons(slot: GroupSchedule, *, today: dt.date | None = None,
                           now: dt.datetime | None = None) -> ScheduleAlignResult:
    """«Сгенерировать занятия»'s half of the sync: put every open future
    lesson of `slot` (Lesson.schedule) that is *not* where the slot says —
    a slot edit that didn't move it (made today, saved by a path without
    sync, or a clash at the time) — onto the slot's current weekday of its
    own week and its current start/end time.

    Same rules as sync_schedule_lessons, without a «before» snapshot: a
    lesson already on the slot is left alone (a repeat run is a no-op),
    history / started / data-carrying / hand-moved (schedule_overridden)
    lessons and those whose new time would already be past are kept, room
    and teacher are not touched. Unlike a slot save, a lesson that would
    clash is not fatal: it stays where it is and is reported in `problems`
    while the others move. Call inside the generator's transaction."""
    result = ScheduleAlignResult()
    now_local = local_now(now=now, today=today)
    weekday = WEEKDAY_CODES.index(slot.day_of_week)

    with transaction.atomic():
        future = [lesson for lesson in _future_lessons(slot, now_local) if not follows_slot(lesson, slot)]
        if not future:
            return result
        with_data = lessons_with_data([lesson.pk for lesson in future])
        planned = []
        for lesson in future:
            date = target_date(lesson.date, weekday)
            if lesson_is_open(lesson, with_data) and is_ahead(date, slot.start_time, now_local):
                planned.append((lesson, date, lesson.room_id, lesson.teacher_id))
            else:
                result.kept += 1
        if not planned:
            return result

        problems = _find_problems(slot.group, planned, slot.start_time, slot.end_time)
        if problems:
            blocked = {lesson.pk for lesson, _kind, _message in problems}
            planned = [move for move in planned if move[0].pk not in blocked]
            result.kept += len(blocked)
            result.problems = _problem_messages(problems, slot.group)
            # Moves are within the lesson's own week and a slot gives one
            # lesson per week, so a lesson left in place can't collide with
            # one of the slot's lessons that does move.
        if planned:
            _move(planned, slot.start_time, slot.end_time)
            result.moved = [lesson for lesson, *_rest in planned]
    return result


def attach_detached_lessons(group_teacher, *, strict: bool = False, today: dt.date | None = None,
                            now: dt.datetime | None = None) -> ScheduleAlignResult:
    """Give back a slot to the program's lessons that lost theirs.

    Deleting a slot (the trash icon / removing a day in the editor and
    adding another one instead of editing it) sets Lesson.schedule to NULL
    (SET_NULL): such a lesson belongs to no slot any more, so neither a
    slot save nor align_schedule_lessons would ever move it — it stayed at
    the deleted slot's old day/time forever. Here every open future lesson
    of `group_teacher` without a slot (same lesson_is_open rule, never a
    hand-moved one) is put into one of the program's current active slots
    *in its own week*: a week's detached lessons, in date order, take the
    week's still-free slots in weekday/time order (a slot gives one lesson
    per week — one already used by another lesson of that week, any status,
    is skipped), moving to that slot's day, time and room. A lesson with no
    free slot in its week, or whose new time would already be past, stays
    where it is (counted as kept).

    `strict` (a schedule save): a clash raises ValidationError so the save
    rolls back, like sync_schedule_lessons. Otherwise (generation) a
    clashing lesson just stays detached and is reported in `problems`."""
    result = ScheduleAlignResult()
    if not group_teacher.is_active:
        return result
    now_local = local_now(now=now, today=today)
    with transaction.atomic():
        detached = list(
            Lesson.objects.select_for_update()
            .filter(group_teacher=group_teacher, schedule__isnull=True)
            .filter(ahead_q(now_local))
            .exclude(status=Lesson.Status.CANCELLED)
            .order_by("date", "start_time", "pk")
        )
        if not detached:
            return result
        slots = sorted(
            (slot for slot in group_teacher.schedules.filter(is_active=True) if slot.start_time < slot.end_time),
            key=lambda slot: (WEEKDAY_CODES.index(slot.day_of_week), slot.start_time),
        )
        with_data = lessons_with_data([lesson.pk for lesson in detached])
        weeks = {lesson.date.isocalendar()[:2] for lesson in detached}
        used = {
            (schedule_id, *date.isocalendar()[:2])
            for schedule_id, date in Lesson.objects.filter(schedule__in=slots).values_list("schedule_id", "date")
            if date.isocalendar()[:2] in weeks
        }
        moves = []
        for lesson in detached:
            if not lesson_is_open(lesson, with_data):
                result.kept += 1
                continue
            week = lesson.date.isocalendar()[:2]
            for slot in slots:
                date = target_date(lesson.date, WEEKDAY_CODES.index(slot.day_of_week))
                if (slot.pk, *week) not in used and is_ahead(date, slot.start_time, now_local):
                    used.add((slot.pk, *week))
                    moves.append((
                        lesson, date, slot.start_time, slot.end_time, slot.room_id,
                        lesson.teacher_id or group_teacher.teacher_id, slot,
                    ))
                    break
            else:
                result.kept += 1
        if not moves:
            return result

        group = group_teacher.group
        problems = _find_move_problems(group, [move[:6] for move in moves])
        if problems:
            if strict:
                raise ValidationError(_problem_messages(problems, group))
            blocked = {lesson.pk for lesson, _kind, _message in problems}
            moves = [move for move in moves if move[0].pk not in blocked]
            result.kept += len(blocked)
            result.problems = _problem_messages(problems, group)
        stamp = timezone.now()
        for lesson, date, start, end, room_id, _teacher, slot in moves:
            lesson.date, lesson.start_time, lesson.end_time = date, start, end
            lesson.room_id, lesson.schedule, lesson.updated_at = room_id, slot, stamp
        if moves:
            Lesson.objects.bulk_update(
                [move[0] for move in moves], ["date", "start_time", "end_time", "room", "schedule", "updated_at"],
            )
            result.moved = [move[0] for move in moves]
    return result


_KIND_LATE = "late"


def _find_problems(group, planned, start: dt.time, end: dt.time) -> list[tuple[Lesson, str, str]]:
    """_find_move_problems for moves that all take the same start/end time."""
    return _find_move_problems(
        group, [(lesson, date, start, end, room_id, teacher_id) for lesson, date, room_id, teacher_id in planned],
    )


def _find_move_problems(group, moves) -> list[tuple[Lesson, str, str]]:
    """(lesson, kind, message) for every planned move — (lesson, date,
    start, end, room_id, teacher_id) — that doesn't fit: past the group's
    end date, or overlapping the group's, the teacher's or the room's other
    (non-cancelled, not moving) lessons on its new date."""
    problems: list[tuple[Lesson, str, str]] = []
    if group.end_date:
        problems += [
            (lesson, _KIND_LATE, _fmt(lesson, lesson.date, lesson.start_time))
            for lesson, date, *_rest in moves if date > group.end_date
        ]

    moving_ids = {lesson.pk for lesson, *_rest in moves}
    dates = {date for _lesson, date, *_rest in moves}
    teacher_ids = {teacher for *_rest, teacher in moves if teacher}
    room_ids = {room for *_rest, room, _teacher in moves if room}
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

    for lesson, date, start, end, room_id, teacher_id in moves:
        for other in by_date.get(date, []):
            if not _overlaps(start, end, other.start_time, other.end_time):
                continue
            other_teacher = other.teacher_id or (other.group_teacher.teacher_id if other.group_teacher_id else None)
            label = _fmt(lesson, date, start)
            if other.group_id == group.pk:
                problems.append((lesson, "group", f"{label} — у группы уже есть занятие {other.start_time:%H:%M}"))
            elif teacher_id and other_teacher == teacher_id:
                problems.append((lesson, "teacher", f"{label} — тренер занят в группе «{other.group.name}»"))
            elif room_id and other.room_id == room_id:
                problems.append((lesson, "room", f"{label} — аудитория занята группой «{other.group.name}»"))
    return problems


def _problem_messages(problems: list[tuple[Lesson, str, str]], group) -> list[str]:
    by_kind: dict[str, list[str]] = {_KIND_LATE: [], "group": [], "teacher": [], "room": []}
    for _lesson, kind, message in problems:
        by_kind[kind].append(message)
    messages = []
    late = list(dict.fromkeys(by_kind.pop(_KIND_LATE)))
    if late:
        messages.append(
            f"Занятия выйдут за дату окончания группы ({group.end_date:%d.%m.%Y}): {', '.join(late[:_MAX_LISTED])}."
        )
    for kind_messages in by_kind.values():
        unique = list(dict.fromkeys(kind_messages))
        if unique:
            more = f" и ещё {len(unique) - _MAX_LISTED}" if len(unique) > _MAX_LISTED else ""
            messages.append("Будущие занятия нельзя перенести: " + "; ".join(unique[:_MAX_LISTED]) + more + ".")
    return messages
