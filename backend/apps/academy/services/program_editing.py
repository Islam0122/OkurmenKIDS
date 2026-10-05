"""Editing an existing Teaching Program (GroupTeacher) in place.

A program's teacher/subject are copied onto every one of its GroupSchedule
slots (GroupSchedule.teacher/subject, from which GroupSchedule.save()
derives `group_teacher`) and onto its Lessons (Lesson.teacher, used by
LessonQuerySet.for_teacher for access and by the individual-plan
generator). Changing only `GroupTeacher.teacher` — which a plain model
form does — leaves those copies behind: the program's slots keep booking
the old trainer, the next slot save get_or_creates a *second* program for
the old (group, teacher, subject), and the old trainer keeps teaching the
program's future lessons. This module is the one place a program is
edited so all three stay in lockstep, validated up front and applied in
one transaction:

* **Teacher** — the program's slots move to the new teacher (their
  recurring slots must not clash with the new teacher's other slots), and,
  if asked, so do its future *scheduled* lessons that still follow its
  slots (never started, no attendance / homework results, start still
  ahead — see future_lessons; each must not clash with a lesson the new
  teacher already gives). Conducted/cancelled/past/running lessons keep
  their trainer: they are history, and the old trainer's KPI; so does a
  lesson moved by hand away from its slot (an individual arrangement).
* **Subject** — only while the program has no lessons at all: a lesson's
  subject is copied from the plan row it was generated from, so renaming
  the subject of a program that already has lessons would split the
  program from its own history.
* **Status** — `is_active`; an inactive program is ignored by generation
  and conflict checks (see GroupTeacher.is_active), nothing else changes.

Also home to build_schedule_slots(), the shared "one slot per selected
weekday, all validated before any is saved" step of the Workspace's
add-program and add-schedule forms, and to save_teaching_program(), which
applies the program drawer's "Сохранить": program fields plus the drawer's
whole locally-edited list of weekly slots (created / changed / removed) in
one transaction — "Добавить слоты" and the trash icon only change the list
in the browser; nothing reaches the database before "Сохранить".
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

from django.core.exceptions import ValidationError
from django.db import transaction

from ..constants import WEEKDAY_CODES, WEEKDAY_LABELS_SHORT
from django.db.models import Q

from ..models import Attendance, GroupSchedule, GroupTeacher, HomeworkResult, Lesson, Room
from .group_schedule_conflicts import find_schedule_teacher_conflict
from .schedule_lesson_sync import (
    SlotSnapshot,
    ahead_q,
    attach_detached_lessons,
    local_now,
    snapshot,
    sync_schedule_lessons,
)

# How many clashing lessons one validation error lists before "…".
_MAX_LISTED = 5


@dataclass
class ProgramChange:
    teacher_changed: bool = False
    subject_changed: bool = False
    status_changed: bool = False
    lessons_reassigned: int = 0

    @property
    def changed(self) -> bool:
        return self.teacher_changed or self.subject_changed or self.status_changed


def _django_week_day(day_of_week: str) -> int:
    """GroupSchedule's "mon".."sun" → Django's __week_day (1 = Sunday … 7 = Saturday)."""
    return (WEEKDAY_CODES.index(day_of_week) + 1) % 7 + 1


def future_lessons(group_teacher: GroupTeacher, *, today: dt.date | None = None, now: dt.datetime | None = None):
    """The program's lessons a teacher change may move to the new teacher —
    the same «open future lesson» rule as schedule_lesson_sync: still
    scheduled, never started, no attendance / homework results, start still
    ahead (project time zone), and still following one of the program's
    slots (its weekday and start/end; a lesson moved by hand keeps its
    trainer)."""
    now_local = local_now(now=now, today=today)
    following = Q(pk__in=[])
    for slot in group_teacher.schedules.all():
        following |= (Q(schedule=slot) | Q(schedule__isnull=True)) & Q(
            start_time=slot.start_time, end_time=slot.end_time, date__week_day=_django_week_day(slot.day_of_week),
        )
    return (
        Lesson.objects.filter(group_teacher=group_teacher, status=Lesson.Status.SCHEDULED, started_at__isnull=True)
        .filter(ahead_q(now_local))
        .filter(following)
        .exclude(pk__in=Attendance.objects.values("lesson_id"))
        .exclude(pk__in=HomeworkResult.objects.values("homework__lesson_id"))
    )


def _teacher_lesson_clashes(teacher, lessons) -> list[str]:
    """Lessons of `lessons` that overlap a non-cancelled lesson `teacher`
    already gives (any group)."""
    lessons = list(lessons)
    if not lessons:
        return []
    ids = [lesson.pk for lesson in lessons]
    dates = {lesson.date for lesson in lessons}
    busy: dict[dt.date, list[tuple]] = {}
    for row in (
        Lesson.objects.for_teacher(teacher)
        .filter(date__in=dates)
        .exclude(status=Lesson.Status.CANCELLED)
        .exclude(pk__in=ids)
        .values("date", "start_time", "end_time")
    ):
        busy.setdefault(row["date"], []).append((row["start_time"], row["end_time"]))
    clashes = []
    for lesson in sorted(lessons, key=lambda item: (item.date, item.start_time)):
        if any(lesson.start_time < end and start < lesson.end_time for start, end in busy.get(lesson.date, [])):
            clashes.append(f"№{lesson.lesson_number} {lesson.date:%d.%m.%Y} {lesson.start_time:%H:%M}")
    return clashes


def _listed(items: list[str]) -> str:
    return ", ".join(items[:_MAX_LISTED]) + (", …" if len(items) > _MAX_LISTED else "")


def validate_program_change(group_teacher: GroupTeacher, *, teacher, subject, reassign_future_lessons: bool = True,
                            today: dt.date | None = None) -> None:
    """Raise ValidationError (field-keyed) if the change can't be applied.
    Never writes anything."""
    errors: dict[str, list[str]] = {}

    def add(field_name: str, message: str) -> None:
        errors.setdefault(field_name, []).append(message)

    candidate = GroupTeacher(pk=group_teacher.pk, group=group_teacher.group, teacher=teacher, subject=subject)
    try:
        candidate.clean()
    except ValidationError as exc:
        for field_name, messages in exc.message_dict.items():
            for message in messages:
                add(field_name, message)

    teacher_changed = teacher.pk != group_teacher.teacher_id
    subject_id = subject.pk if subject is not None else None
    subject_changed = subject_id != group_teacher.subject_id

    if (teacher_changed or subject_changed) and (
        GroupTeacher.objects.filter(group_id=group_teacher.group_id, teacher=teacher, subject_id=subject_id)
        .exclude(pk=group_teacher.pk)
        .exists()
    ):
        add(
            "teacher",
            f"У тренера «{teacher}» уже есть программа по предмету "
            f"«{subject.name if subject else 'без предмета'}» в этой группе — измените её вместо этой.",
        )

    if subject_changed and Lesson.objects.filter(group_teacher=group_teacher).exists():
        add(
            "subject",
            "Предмет нельзя изменить: у программы уже есть занятия этого предмета. "
            "Создайте для нового предмета отдельную программу.",
        )

    if teacher_changed and not errors.get("teacher"):
        for slot in group_teacher.schedules.filter(is_active=True).select_related("group"):
            conflict = find_schedule_teacher_conflict(
                teacher=teacher, day_of_week=slot.day_of_week, start_time=slot.start_time,
                end_time=slot.end_time, exclude_schedule_id=slot.pk,
            )
            if conflict is not None:
                add(
                    "teacher",
                    f"Тренер «{teacher}» занят в {slot.get_day_of_week_display().lower()} "
                    f"{slot.start_time:%H:%M}–{slot.end_time:%H:%M} (группа «{conflict.group.name}»).",
                )
        if reassign_future_lessons:
            clashes = _teacher_lesson_clashes(teacher, future_lessons(group_teacher, today=today))
            if clashes:
                add(
                    "teacher",
                    f"У тренера «{teacher}» уже есть занятия в это время: {_listed(clashes)}. "
                    "Перенесите их или не передавайте будущие занятия.",
                )

    if errors:
        raise ValidationError(errors)


@transaction.atomic
def update_teaching_program(group_teacher: GroupTeacher, *, teacher, subject, is_active: bool,
                            reassign_future_lessons: bool = True, today: dt.date | None = None) -> ProgramChange:
    """Validate (validate_program_change) and apply the change — program,
    its slots and (optionally) its future lessons together, or nothing."""
    group_teacher = GroupTeacher.objects.select_for_update().select_related("group__course").get(pk=group_teacher.pk)
    validate_program_change(
        group_teacher, teacher=teacher, subject=subject,
        reassign_future_lessons=reassign_future_lessons, today=today,
    )

    change = ProgramChange(
        teacher_changed=teacher.pk != group_teacher.teacher_id,
        subject_changed=(subject.pk if subject else None) != group_teacher.subject_id,
        status_changed=bool(is_active) != group_teacher.is_active,
    )
    if not change.changed:
        return change

    if change.teacher_changed and reassign_future_lessons:
        change.lessons_reassigned = future_lessons(group_teacher, today=today).update(teacher=teacher)

    group_teacher.teacher = teacher
    group_teacher.subject = subject
    group_teacher.is_active = bool(is_active)
    group_teacher.save(update_fields=["teacher", "subject", "is_active", "updated_at"])

    if change.teacher_changed or change.subject_changed:
        # The slots' (group, teacher, subject) now equals this program's
        # own, so their derived group_teacher stays correct; their conflicts
        # with the new teacher were validated above.
        GroupSchedule.objects.filter(group_teacher=group_teacher).update(teacher=teacher, subject=subject)
    return change


def build_schedule_slots(*, group, teacher, subject, days, start_time, end_time, room) -> list[GroupSchedule]:
    """One unsaved, fully validated GroupSchedule per weekday in `days`.
    Raises ValidationError listing every day's problems (prefixed with the
    day's name) so the admin sees all of them at once; the caller saves
    the returned slots in one transaction."""
    day_labels = dict(GroupSchedule.DAY_CHOICES)
    slots, problems = [], []
    for day in days:
        slot = GroupSchedule(
            group=group, teacher=teacher, subject=subject,
            day_of_week=day, start_time=start_time, end_time=end_time, room=room,
        )
        try:
            slot.full_clean()
        except ValidationError as exc:
            problems.extend(f"{day_labels.get(day, day)}: {message}" for message in exc.messages)
        else:
            slots.append(slot)
    if problems:
        raise ValidationError(problems)
    # Two of the selected days can't clash with each other (different
    # weekdays), so validating each against the saved schedule is enough.
    return slots


@dataclass(frozen=True)
class SlotSpec:
    """One weekly slot as the drawer wants it after "Сохранить": `id` is
    an existing slot of the program, None a new one."""

    id: int | None
    day_of_week: str
    start_time: dt.time
    end_time: dt.time
    room_id: int | None

    @property
    def label(self) -> str:
        return (
            f"{WEEKDAY_LABELS_SHORT.get(self.day_of_week, self.day_of_week)} "
            f"{self.start_time:%H:%M}–{self.end_time:%H:%M}"
        )


@dataclass
class ScheduleChange:
    created: int = 0
    updated: int = 0
    deleted: int = 0
    # Future lessons moved with their changed slots / left as history.
    lessons_synced: int = 0
    lessons_kept: int = 0

    @property
    def changed(self) -> bool:
        return bool(self.created or self.updated or self.deleted)


@dataclass
class ProgramSaveResult:
    program: ProgramChange = field(default_factory=ProgramChange)
    schedule: ScheduleChange = field(default_factory=ScheduleChange)


def _parse_time(value) -> dt.time | None:
    if not isinstance(value, str):
        return None
    try:
        return dt.time.fromisoformat(value.strip()[:5])
    except ValueError:
        return None


def parse_schedule_specs(group_teacher: GroupTeacher, items) -> list[SlotSpec]:
    """Validate the shape of the drawer's slot list (a decoded JSON list of
    {id, day, start, end, room}) and turn it into SlotSpecs. Checks what
    can be checked without the database state of other programs: known
    weekday, times, end after start, the room exists, ids are this
    program's own slots, and no two of the program's slots overlap.
    Teacher / room / group conflicts are left to save_teaching_program()."""
    if not isinstance(items, list):
        raise ValidationError("Некорректные данные расписания.")
    own_slots = {slot.pk: slot for slot in group_teacher.schedules.all()} if group_teacher.pk else {}
    room_ids = set(Room.objects.values_list("pk", flat=True))
    specs, problems, seen_ids = [], [], set()
    for item in items:
        if not isinstance(item, dict):
            raise ValidationError("Некорректные данные расписания.")
        slot_id, room_id = item.get("id"), item.get("room")
        day = item.get("day")
        start, end = _parse_time(item.get("start")), _parse_time(item.get("end"))
        if slot_id is not None and (not isinstance(slot_id, int) or slot_id not in own_slots or slot_id in seen_ids):
            raise ValidationError("Слот расписания не найден — обновите страницу и попробуйте снова.")
        if room_id is not None and (not isinstance(room_id, int) or room_id not in room_ids):
            problems.append("Выбранный кабинет не найден.")
            continue
        if day not in WEEKDAY_CODES or start is None or end is None:
            problems.append("Укажите день недели, время начала и окончания для каждого слота.")
            continue
        spec = SlotSpec(id=slot_id, day_of_week=day, start_time=start, end_time=end, room_id=room_id)
        if end <= start:
            problems.append(f"{spec.label}: время окончания должно быть позже времени начала.")
            continue
        if slot_id is not None:
            seen_ids.add(slot_id)
        specs.append(spec)

    # The program's own slots can't overlap each other — the database
    # checks below only see the slots of *other* programs correctly while
    # this list is being applied.
    by_day: dict[str, list[SlotSpec]] = {}
    for spec in specs:
        if spec.id is not None and not own_slots[spec.id].is_active:
            continue
        by_day.setdefault(spec.day_of_week, []).append(spec)
    for day in WEEKDAY_CODES:
        day_specs = sorted(by_day.get(day, []), key=lambda s: s.start_time)
        for prev, nxt in zip(day_specs, day_specs[1:]):
            if nxt.start_time < prev.end_time:
                problems.append(f"Слоты {prev.label} и {nxt.label} пересекаются.")
    if problems:
        raise ValidationError(list(dict.fromkeys(problems)))
    return sorted(specs, key=lambda s: (WEEKDAY_CODES.index(s.day_of_week), s.start_time))


def _apply_schedule(group_teacher: GroupTeacher, specs: list[SlotSpec], removed_ids: set[int],
                    changed: list[SlotSpec], was_active: dict[int, bool],
                    before: dict[int, SlotSnapshot] | None = None, today: dt.date | None = None) -> ScheduleChange:
    """Write the created/changed slots (the removed ones are already gone
    and the changed ones parked inactive by the caller). Every slot is
    fully validated — teacher, room and group conflicts — and every
    problem is collected before raising, so the admin sees all of them.
    A changed slot's open future lessons follow its new day / time / room
    (services.schedule_lesson_sync) in the same transaction."""
    change = ScheduleChange(deleted=len(removed_ids))
    slots_by_id = {slot.pk: slot for slot in group_teacher.schedules.filter(pk__in=[s.id for s in changed])}
    problems = []
    for spec in specs:
        if spec.id is None:
            slot = GroupSchedule(group=group_teacher.group, is_active=True)
        elif spec in changed:
            slot = slots_by_id[spec.id]
            slot.is_active = was_active[spec.id]
        else:
            continue
        slot.teacher = group_teacher.teacher
        slot.subject = group_teacher.subject
        slot.day_of_week = spec.day_of_week
        slot.start_time = spec.start_time
        slot.end_time = spec.end_time
        slot.room_id = spec.room_id
        try:
            slot.full_clean()
        except ValidationError as exc:
            problems.extend(f"{spec.label}: {message}" for message in exc.messages)
            continue
        slot.save()
        if spec.id is None:
            change.created += 1
        else:
            change.updated += 1
            if before and spec.id in before:
                try:
                    synced = sync_schedule_lessons(slot, before[spec.id], today=today)
                except ValidationError as exc:
                    problems.extend(f"{spec.label}: {message}" for message in exc.messages)
                    continue
                change.lessons_synced += synced.updated
                change.lessons_kept += synced.kept
    if not problems:
        # A deleted slot left its lessons without one (Lesson.schedule is
        # SET_NULL): they take the program's current slots, week by week —
        # removing a day and adding another moves the lessons like editing
        # the day would have. Strict (a clash rolls the save back) when this
        # save itself replaced slots; otherwise it only picks up lessons an
        # earlier deletion left behind, and a clash just leaves them be.
        try:
            attached = attach_detached_lessons(
                group_teacher, strict=bool(removed_ids or change.created), today=today,
            )
        except ValidationError as exc:
            problems.extend(exc.messages)
        else:
            change.lessons_synced += len(attached.moved)
            change.lessons_kept += attached.kept
    if problems:
        raise ValidationError({"schedule": list(dict.fromkeys(problems))})
    return change


@transaction.atomic
def save_teaching_program(group_teacher: GroupTeacher, *, teacher, subject, is_active: bool,
                          reassign_future_lessons: bool = True, slots: list[SlotSpec] | None = None,
                          today: dt.date | None = None) -> ProgramSaveResult:
    """The program drawer's "Сохранить": update_teaching_program() plus,
    when `slots` is given, bring the program's weekly slots to exactly that
    list — existing slots missing from it are deleted, changed ones
    updated, new ones created. All or nothing: any error (program fields
    or any slot's teacher / room / group conflict) rolls everything back;
    slot errors are raised under the "schedule" key.

    Order matters for conflict checks: removed slots are deleted and
    changed ones parked inactive (conflict checks ignore inactive slots)
    first, so neither blocks the program's own new layout; the teacher
    change is then validated against the slots that stay as they are, and
    the created/changed slots are validated last, already under the new
    teacher."""
    result = ProgramSaveResult()
    # One editor of this program at a time: the program row and its slots
    # are locked before anything is read, so a concurrent save waits and
    # then starts from what this one committed (no stale «before»).
    group_teacher = GroupTeacher.objects.select_for_update().get(pk=group_teacher.pk)
    if slots is not None:
        current = {slot.pk: slot for slot in GroupSchedule.objects.select_for_update().filter(group_teacher=group_teacher)}
        wanted_ids = {spec.id for spec in slots if spec.id is not None}
        removed_ids = set(current) - wanted_ids
        changed = [
            spec for spec in slots
            if spec.id is not None and (
                current[spec.id].day_of_week, current[spec.id].start_time,
                current[spec.id].end_time, current[spec.id].room_id,
            ) != (spec.day_of_week, spec.start_time, spec.end_time, spec.room_id)
        ]
        was_active = {spec.id: current[spec.id].is_active for spec in changed}
        before = {spec.id: snapshot(current[spec.id]) for spec in changed}
        if removed_ids:
            GroupSchedule.objects.filter(pk__in=removed_ids).delete()
        if changed:
            GroupSchedule.objects.filter(pk__in=[spec.id for spec in changed]).update(is_active=False)

    result.program = update_teaching_program(
        group_teacher, teacher=teacher, subject=subject, is_active=is_active,
        reassign_future_lessons=reassign_future_lessons, today=today,
    )

    if slots is not None:
        group_teacher.refresh_from_db()
        result.schedule = _apply_schedule(group_teacher, slots, removed_ids, changed, was_active, before, today)
    return result
