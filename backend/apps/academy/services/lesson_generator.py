"""Turns a lesson-plan template into real, dated Lesson rows for a Group.

Three independent sources of truth are combined here — and only here:

* **The lesson plan** decides *what* each lesson is: its number, subject,
  topic, materials and homework (CourseLessonPlan, or a GroupTeacher's own
  GroupTeacherLessonPlan).
* **The group's schedule** decides *when/where*: weekday, time range, room
  (every active GroupSchedule slot of the group).
* **The subject → teacher assignment** decides *who*: an active GroupTeacher
  row (group, teacher, subject) says "this teacher teaches this subject in
  this group". A lesson's teacher is resolved from the *plan row's subject*,
  never from "whoever happens to own the time slot" — so a group whose three
  weekly slots all belong to its IT trainer still gets its Soft Skills and
  English lessons assigned to the Soft Skills/English trainers.

Teacher resolution for one (slot, plan row with subject S) pair, in order —
see `_resolve_program`:

1. The slot is dedicated to S (`slot.subject == S`) → the slot's own teacher.
2. The group has an active assignment for S → that teacher. Several
   different teachers assigned to S → the slot's own teacher if they are
   one of them, otherwise the lesson is ambiguous and is *not* created.
3. The slot has no fixed subject (a legacy slot migrated from the old
   Group.teacher field — "this teacher runs whatever the plan puts here")
   and nobody is assigned to S → the slot's teacher. This keeps every
   pre-existing single-teacher group generating exactly as before.
4. Otherwise S has no teacher → the lesson is *not* created. There is no
   hidden fallback to "the group's main teacher".

A plan row that can't be created (rule 4, an ambiguous assignment, or the
resolved teacher/room is already busy at that exact date/time) still
*reserves* its slot occurrence: the calendar is not shifted, and a warning
names the subject/lesson numbers. Once the admin fixes the cause (assigns a
teacher, resolves the clash) the next generation run places exactly those
lessons into exactly those reserved dates — every other lesson keeps its
date.

Two plan sources are supported, chosen per GroupTeacher:

* **Individual plan** — the GroupTeacher has its own GroupTeacherLessonPlan
  rows. Lessons are generated from those, walking only that teacher's own
  active schedule slots, numbered 1..N independently of every other teacher
  in the group.

* **Shared plan** — the GroupTeacher has no GroupTeacherLessonPlan of its
  own. The group's shared `Course.lesson_plans` template is walked in
  lesson_number order across all such teachers' active slots together, one
  plan row per slot occurrence (day by day, by start time), with the teacher
  of each lesson resolved per subject as described above.

Generation is **explicit** (the "Сгенерировать занятия" button, the admin
action, or `POST /groups/{id}/generate-lessons/`) — never triggered by
saving a single schedule slot: walking the plan against a half-configured
timetable (e.g. only the Monday slot saved so far) would greedily spread
all 144 plan rows over Mondays alone, years past the group's real period.
See signals.py.

Both paths are idempotent: only missing lesson_numbers are filled in, into
slot occurrences no existing lesson of the group already occupies; existing
Lesson rows (and their attendance/homework) are never modified or
duplicated, whatever their status.
"""
from __future__ import annotations

import datetime as dt
import logging
from collections import defaultdict
from dataclasses import dataclass, field

from django.db import transaction
from django.db.models import Q

from ..constants import WEEKDAY_CODES
from ..models import Group, GroupSchedule, GroupTeacher, Homework, Lesson
from .group_schedule_conflicts import (
    find_schedule_group_conflict,
    find_schedule_room_conflict,
    find_schedule_teacher_conflict,
)

logger = logging.getLogger(__name__)

# A misconfigured group (an empty days_of_week that somehow bypassed
# validation, say) must never turn this into an infinite loop.
_MAX_DAYS_TO_SCAN = 366 * 5

# How many individual lesson numbers a single aggregated warning lists
# before summarising the rest as "…".
_MAX_NUMBERS_IN_WARNING = 10


class LessonGenerationError(Exception):
    """Raised when a group teacher's course/schedule isn't in a state lessons can be generated from."""


@dataclass
class _GenerationRun:
    """Everything one generation call observed, collected directly (never
    scraped back out of log output) so the report built from it is exact."""

    created: list[Lesson] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    slot_conflicts: int = 0
    slot_skips: int = 0
    lesson_conflicts: int = 0
    # subject name -> lesson numbers not created because nobody teaches it
    unassigned: dict[str, list[int]] = field(default_factory=lambda: defaultdict(list))
    # subject name -> lesson numbers not created because several teachers are assigned to it
    ambiguous: dict[str, list[int]] = field(default_factory=lambda: defaultdict(list))
    busy: list[str] = field(default_factory=list)
    not_fitting: list[str] = field(default_factory=list)
    inactive_assignments: list[str] = field(default_factory=list)

    def warnings(self) -> list[str]:
        messages = []
        for subject, numbers in sorted(self.unassigned.items()):
            messages.append(
                f"Предмет «{subject}»: тренер не назначен — не создано занятий: {len(numbers)} "
                f"({_format_numbers(numbers)}). Назначьте тренера на предмет и запустите генерацию ещё раз."
            )
        for subject, numbers in sorted(self.ambiguous.items()):
            messages.append(
                f"Предмет «{subject}»: назначено несколько тренеров, и ни один из них не ведёт этот слот — "
                f"не создано занятий: {len(numbers)} ({_format_numbers(numbers)}). "
                "Оставьте одно активное назначение на предмет."
            )
        messages.extend(self.inactive_assignments)
        messages.extend(self.busy)
        messages.extend(self.not_fitting)
        return messages


def _format_numbers(numbers: list[int]) -> str:
    shown = ", ".join(f"№{n}" for n in numbers[:_MAX_NUMBERS_IN_WARNING])
    return shown + (", …" if len(numbers) > _MAX_NUMBERS_IN_WARNING else "")


def _without_conflicting_slots(slots: list[GroupSchedule], *, label: str, run: _GenerationRun) -> list[GroupSchedule]:
    """Defense-in-depth against invalid or double-booked slots.

    `GroupSchedule.clean()` already rejects a conflicting or invalid slot —
    but only when something actually calls `full_clean()` (a ModelForm or a
    DRF serializer). A slot persisted via a raw `.save()`/`bulk_create` (data
    migrations, `services.group_schedule_sync`, fixtures), or one that
    became invalid *after* being saved (a Teacher/Room deactivated later),
    can reach generation unchecked. Rather than trust every slot blindly,
    re-verify each one here and skip — with a logged warning, never a hard
    failure — any slot that currently:

    - clashes with another active GroupSchedule row on the same teacher,
      room, *or group* (a Group cannot physically attend two programs at
      once, even with different teachers/rooms — see
      find_schedule_group_conflict); or
    - references a Teacher/Room that is no longer active; or
    - has an invalid time range (end <= start).

    One bad slot is dropped; the rest of the Teacher Program's schedule
    still generates normally.
    """
    clean_slots = []
    for slot in slots:
        if slot.end_time <= slot.start_time:
            run.slot_skips += 1
            logger.warning(
                "[lesson_generator] %s: skipping schedule slot id=%s — invalid time range (%s-%s).",
                label, slot.pk, slot.start_time, slot.end_time,
            )
            continue

        if not slot.teacher.is_active:
            run.slot_skips += 1
            logger.warning(
                "[lesson_generator] %s: skipping schedule slot id=%s — teacher %r is not active.",
                label, slot.pk, str(slot.teacher),
            )
            continue

        if slot.room_id and not slot.room.is_active:
            run.slot_skips += 1
            logger.warning(
                "[lesson_generator] %s: skipping schedule slot id=%s — room %r is not active.",
                label, slot.pk, str(slot.room),
            )
            continue

        conflict = find_schedule_teacher_conflict(
            teacher=slot.teacher,
            day_of_week=slot.day_of_week,
            start_time=slot.start_time,
            end_time=slot.end_time,
            exclude_schedule_id=slot.pk,
        )
        if conflict is not None:
            run.slot_conflicts += 1
            logger.warning(
                "[lesson_generator] %s: skipping schedule slot id=%s — teacher %r already "
                "booked at this time by group %r (schedule id=%s).",
                label, slot.pk, str(slot.teacher), conflict.group.name, conflict.pk,
            )
            continue

        if slot.room_id:
            conflict = find_schedule_room_conflict(
                room=slot.room,
                day_of_week=slot.day_of_week,
                start_time=slot.start_time,
                end_time=slot.end_time,
                exclude_schedule_id=slot.pk,
            )
            if conflict is not None:
                run.slot_conflicts += 1
                logger.warning(
                    "[lesson_generator] %s: skipping schedule slot id=%s — room %r already "
                    "booked at this time by group %r (schedule id=%s).",
                    label, slot.pk, str(slot.room), conflict.group.name, conflict.pk,
                )
                continue

        conflict = find_schedule_group_conflict(
            group=slot.group,
            day_of_week=slot.day_of_week,
            start_time=slot.start_time,
            end_time=slot.end_time,
            exclude_schedule_id=slot.pk,
        )
        if conflict is not None:
            run.slot_conflicts += 1
            logger.warning(
                "[lesson_generator] %s: skipping schedule slot id=%s — group %r already has an "
                "overlapping program at this time (schedule id=%s, program %r).",
                label, slot.pk, str(slot.group), conflict.pk, str(conflict.group_teacher),
            )
            continue

        clean_slots.append(slot)
    return clean_slots


def _weekday_slots(slots: list[GroupSchedule]) -> dict[int, list[GroupSchedule]]:
    """Every slot in `slots`, bucketed by Python weekday index (0=Monday) and
    ordered by start_time within each day — so a day with several slots
    (different subjects/teachers) generates its lessons left-to-right
    through the day, in a stable order."""
    by_weekday: dict[int, list[GroupSchedule]] = defaultdict(list)
    for slot in slots:
        if slot.day_of_week in WEEKDAY_CODES:
            by_weekday[WEEKDAY_CODES.index(slot.day_of_week)].append(slot)
    for day_slots in by_weekday.values():
        day_slots.sort(key=lambda s: s.start_time)
    return by_weekday


class _Occupancy:
    """Concrete, dated Lessons already on the calendar — of this group (any
    status: a cancelled lesson's occurrence is used up, not refilled with a
    different plan row), and of every teacher/room this run may book
    (non-cancelled only, any group).

    Loaded in one query up front and extended with every lesson this run
    creates, so the walk below never double-books the group, a teacher or a
    room on a specific date — including against lessons that were moved by
    hand away from their recurring slot, which the slot-level checks in
    `_without_conflicting_slots` can't see.
    """

    def __init__(self, *, group: Group, teacher_ids: set[int], room_ids: set[int]):
        self._group: dict[dt.date, list[tuple]] = defaultdict(list)
        self._teacher: dict[tuple[int, dt.date], list[tuple]] = defaultdict(list)
        self._room: dict[tuple[int, dt.date], list[tuple]] = defaultdict(list)
        self._recurring: dict[tuple[int, int], GroupSchedule | None] = {}
        self._group_id = group.pk

        busy_elsewhere = Q(teacher_id__in=teacher_ids) | Q(teacher__isnull=True, group_teacher__teacher_id__in=teacher_ids)
        if room_ids:
            busy_elsewhere |= Q(room_id__in=room_ids)
        qs = Lesson.objects.filter(date__gte=group.start_date).filter(
            Q(group_id=group.pk) | (~Q(status=Lesson.Status.CANCELLED) & busy_elsewhere)
        )
        if group.end_date:
            qs = qs.filter(date__lte=group.end_date)

        for row in qs.values(
            "group_id", "date", "start_time", "end_time", "teacher_id", "group_teacher__teacher_id", "room_id", "status",
        ):
            span = (row["start_time"], row["end_time"])
            if row["group_id"] == self._group_id:
                self._group[row["date"]].append(span)
            if row["status"] == Lesson.Status.CANCELLED:
                continue
            teacher_id = row["teacher_id"] or row["group_teacher__teacher_id"]
            if teacher_id:
                self._teacher[(teacher_id, row["date"])].append(span)
            if row["room_id"]:
                self._room[(row["room_id"], row["date"])].append(span)

    @staticmethod
    def _overlaps(spans: list[tuple], start, end) -> bool:
        return any(start < other_end and other_start < end for other_start, other_end in spans)

    def group_busy(self, date: dt.date, start, end) -> bool:
        return self._overlaps(self._group.get(date, []), start, end)

    def teacher_busy(self, teacher_id: int, date: dt.date, start, end) -> bool:
        return self._overlaps(self._teacher.get((teacher_id, date), []), start, end)

    def room_busy(self, room_id: int, date: dt.date, start, end) -> bool:
        return self._overlaps(self._room.get((room_id, date), []), start, end)

    def recurring_teacher_conflict(self, teacher, slot: GroupSchedule) -> GroupSchedule | None:
        """Another active GroupSchedule slot `teacher` has at `slot`'s
        weekday/time — cached per (teacher, slot): the answer is the same
        for every week of the walk."""
        key = (teacher.pk, slot.pk)
        if key not in self._recurring:
            self._recurring[key] = find_schedule_teacher_conflict(
                teacher=teacher, day_of_week=slot.day_of_week, start_time=slot.start_time,
                end_time=slot.end_time, exclude_schedule_id=slot.pk,
            )
        return self._recurring[key]

    def add(self, lesson: Lesson) -> None:
        span = (lesson.start_time, lesson.end_time)
        self._group[lesson.date].append(span)
        if lesson.teacher_id:
            self._teacher[(lesson.teacher_id, lesson.date)].append(span)
        if lesson.room_id:
            self._room[(lesson.room_id, lesson.date)].append(span)


def _create_homework_if_planned(lesson: Lesson, plan) -> None:
    """Auto-create the plan's standard Homework alongside a newly generated
    Lesson — only when the plan actually declares one. A Teacher/Admin can
    still add further Homework for the same lesson afterwards (Homework is a
    plain ForeignKey to Lesson, so several can coexist). Works the same way
    for a CourseLessonPlan row or a GroupTeacherLessonPlan row — both expose
    the same homework_title/homework_description fields."""
    if plan.homework_title:
        Homework.objects.create(
            lesson=lesson,
            title=plan.homework_title,
            description=plan.homework_description,
        )


def _get_or_create_lesson(kwargs: dict) -> tuple[Lesson, bool]:
    """Deterministic identity: `(group_teacher, lesson_number)` — the exact
    pair the database's own `unique_group_teacher_lesson_number` constraint
    enforces (see models.Lesson.Meta.constraints) — is the one and only
    thing that identifies "this Lesson" for idempotency purposes.

    Using `get_or_create` (backed by that constraint) instead of a blind
    `create()` means a repeat call, a race between two simultaneous
    generation requests (a double-click, two open tabs), or a retry after a
    partial failure all safely resolve to the *same* row instead of raising
    or duplicating — `get_or_create` already opens its own savepoint around
    the INSERT and falls back to a plain re-fetch on `IntegrityError`, so a
    lost race never poisons the outer (already-atomic) generation call.
    """
    lookup = {"group_teacher": kwargs["group_teacher"], "lesson_number": kwargs["lesson_number"]}
    defaults = {key: value for key, value in kwargs.items() if key not in lookup}
    return Lesson.objects.get_or_create(defaults=defaults, **lookup)


def _walk_and_generate(*, group: Group, slots_by_weekday, plans_to_generate, lesson_kwargs_for,
                       occupancy: _Occupancy, run: _GenerationRun, label: str,
                       not_before: dt.date | None = None) -> None:
    """Shared walk-forward-by-calendar-day loop: consumes `plans_to_generate`
    in order, one per free slot occurrence encountered (in weekday/start_time
    order), from `group.start_date` up to `group.end_date` (or a hard scan
    cap).

    `lesson_kwargs_for(slot, plan, date)` returns the concrete Lesson
    identity/content for one (slot, plan) pairing, or None when that plan row
    can't be given a teacher (it has then already recorded why on `run`).
    An occurrence the group already has a lesson in is skipped without
    consuming a plan row; an occurrence whose plan row can't be created
    (no/ambiguous teacher, teacher or room busy that day) is *reserved* for
    that row — see the module docstring. `not_before` (repair_group_lessons
    only) starts the walk later than the group's start date, so a rebuild of
    the remaining plan never back-fills dates that have already passed.
    """
    current_date = max(group.start_date, not_before) if not_before else group.start_date
    plan_iter = iter(plans_to_generate)
    plan = next(plan_iter, None)
    scanned = 0

    while plan is not None and scanned < _MAX_DAYS_TO_SCAN:
        if group.end_date and current_date > group.end_date:
            break

        for slot in slots_by_weekday.get(current_date.weekday(), []):
            if plan is None:
                break
            if occupancy.group_busy(current_date, slot.start_time, slot.end_time):
                continue

            kwargs = lesson_kwargs_for(slot, plan, current_date)
            if kwargs is not None:
                problem = _lesson_level_conflict(kwargs, occupancy)
                if problem:
                    run.lesson_conflicts += 1
                    run.busy.append(
                        f"Занятие №{plan.lesson_number} ({current_date:%d.%m.%Y} "
                        f"{slot.start_time:%H:%M}) не создано: {problem}"
                    )
                    logger.warning("[lesson_generator] %s: lesson #%s not created — %s", label, plan.lesson_number, problem)
                else:
                    lesson, was_created = _get_or_create_lesson(kwargs)
                    if was_created:
                        run.created.append(lesson)
                        _create_homework_if_planned(lesson, plan)
                    occupancy.add(lesson)
            plan = next(plan_iter, None)

        current_date += dt.timedelta(days=1)
        scanned += 1

    remaining = ([plan] if plan is not None else []) + list(plan_iter)
    if remaining:
        numbers = [p.lesson_number for p in remaining]
        period = f"до {group.end_date:%d.%m.%Y}" if group.end_date else "в допустимый период генерации"
        run.not_fitting.append(
            f"{label}: {len(numbers)} занятий плана не поместились в расписание группы {period} "
            f"({_format_numbers(numbers)})."
        )


def _lesson_level_conflict(kwargs: dict, occupancy: _Occupancy) -> str | None:
    teacher = kwargs["teacher"]
    slot = kwargs["schedule"]
    date, start, end = kwargs["date"], kwargs["start_time"], kwargs["end_time"]
    if teacher.pk != slot.teacher_id:
        # The slot-level checks in _without_conflicting_slots only vetted the
        # slot's *own* teacher; a subject-assigned teacher teaching in it may
        # have a recurring slot of their own elsewhere at this time.
        conflict = occupancy.recurring_teacher_conflict(teacher, slot)
        if conflict is not None:
            return (
                f"тренер «{teacher}» в это время по расписанию ведёт занятия в группе "
                f"«{conflict.group.name}»."
            )
    if occupancy.teacher_busy(teacher.pk, date, start, end):
        return f"тренер «{teacher}» уже ведёт другое занятие в это время."
    room = kwargs.get("room")
    if room is not None and occupancy.room_busy(room.pk, date, start, end):
        return f"аудитория «{room.name}» уже занята в это время."
    return None


def _subject_assignments(group_teachers: list[GroupTeacher], run: _GenerationRun) -> dict[int, list[GroupTeacher]]:
    """subject_id -> the active GroupTeacher assignments for it. An
    assignment whose Teacher account was deactivated is ignored (and
    reported) rather than silently handed new lessons."""
    by_subject: dict[int, list[GroupTeacher]] = defaultdict(list)
    for gt in group_teachers:
        if gt.subject_id is None:
            continue
        if not gt.teacher.is_active:
            run.inactive_assignments.append(
                f"Назначение «{gt}» не используется: тренер деактивирован."
            )
            continue
        by_subject[gt.subject_id].append(gt)
    return by_subject


def _resolve_program(slot: GroupSchedule, plan, assignments: dict[int, list[GroupTeacher]]):
    """(GroupTeacher, None) for the program that teaches `plan` in `slot`,
    or (None, reason) — "unassigned"/"ambiguous". See module docstring."""
    subject_id = plan.subject_id
    if slot.subject_id is not None and slot.subject_id == subject_id:
        return slot.group_teacher, None

    assigned = assignments.get(subject_id, [])
    if len(assigned) == 1:
        return assigned[0], None
    if len(assigned) > 1:
        for gt in assigned:
            if gt.teacher_id == slot.teacher_id:
                return gt, None
        return None, "ambiguous"

    if slot.subject_id is None:
        return slot.group_teacher, None
    return None, "unassigned"


def _generate_from_course_plan(group: Group, group_teachers: list[GroupTeacher], run: _GenerationRun,
                               not_before: dt.date | None = None) -> None:
    """Shared path: every one of `group_teachers`' active slots consumes the
    *same* shared `group.course.lesson_plans` cursor, with each lesson's
    teacher resolved from its subject — see this module's docstring."""
    plans = list(group.course.lesson_plans.select_related("subject").order_by("lesson_number"))
    if not plans:
        raise LessonGenerationError("У курса нет плана занятий.")

    if len(plans) != group.course.count_lesson:
        raise LessonGenerationError(
            f"Количество занятий в плане курса ({len(plans)}) не совпадает "
            f"с полем count_lesson курса ({group.course.count_lesson})."
        )

    slots = list(
        GroupSchedule.objects.filter(group_teacher__in=group_teachers, is_active=True)
        .select_related("teacher", "subject", "room", "group", "group_teacher")
    )
    label = f"Группа «{group.name}» (общий план курса)"
    slots = _without_conflicting_slots(slots, label=label, run=run)
    slots_by_weekday = _weekday_slots(slots)
    if not slots_by_weekday:
        raise LessonGenerationError("У группы не задано расписание (нет активных слотов).")

    assignments = _subject_assignments(group_teachers, run)

    # Only shared-plan lessons count here — a teacher with an individual
    # plan numbers their own lessons 1..N independently (see
    # _generate_from_individual_plan), and those numbers must not mask the
    # shared plan's rows with the same numbers.
    existing_numbers = set(
        Lesson.objects.filter(group=group, individual_plan__isnull=True).values_list("lesson_number", flat=True)
    )
    plans_to_generate = [p for p in plans if p.lesson_number not in existing_numbers]
    if not plans_to_generate:
        return

    teacher_ids = {slot.teacher_id for slot in slots} | {
        gt.teacher_id for gts in assignments.values() for gt in gts
    }
    room_ids = {slot.room_id for slot in slots if slot.room_id}
    occupancy = _Occupancy(group=group, teacher_ids=teacher_ids, room_ids=room_ids)

    def lesson_kwargs_for(slot: GroupSchedule, plan, date):
        program, reason = _resolve_program(slot, plan, assignments)
        if program is None:
            bucket = run.unassigned if reason == "unassigned" else run.ambiguous
            bucket[plan.subject.name].append(plan.lesson_number)
            return None
        return dict(
            group=group,
            group_teacher=program,
            plan=plan,
            schedule=slot,
            teacher=program.teacher,
            lesson_number=plan.lesson_number,
            date=date,
            start_time=slot.start_time,
            end_time=slot.end_time,
            room=slot.room,
            subject=plan.subject,
            topic=plan.topic,
            description=plan.description,
            youtube_url=plan.youtube_url,
            presentation_urls=plan.presentation_urls,
        )

    _walk_and_generate(
        group=group, slots_by_weekday=slots_by_weekday, plans_to_generate=plans_to_generate,
        lesson_kwargs_for=lesson_kwargs_for, occupancy=occupancy, run=run, label=label, not_before=not_before,
    )


def _generate_from_individual_plan(group: Group, group_teacher: GroupTeacher, run: _GenerationRun,
                                   not_before: dt.date | None = None) -> None:
    """Individual path: `group_teacher`'s own plan and own slots only, own
    lesson_number sequence starting at 1 — independent of every other
    teacher in the same group."""
    plans = list(group_teacher.lesson_plans.order_by("lesson_number"))
    if not plans:
        return

    slots = list(
        group_teacher.schedules.filter(is_active=True).select_related("teacher", "subject", "room", "group")
    )
    label = f"Программа «{group_teacher}»"
    slots = _without_conflicting_slots(slots, label=label, run=run)
    slots_by_weekday = _weekday_slots(slots)
    if not slots_by_weekday:
        raise LessonGenerationError(f"У тренера «{group_teacher}» нет активного расписания.")

    existing_numbers = set(
        Lesson.objects.filter(group_teacher=group_teacher).values_list("lesson_number", flat=True)
    )
    plans_to_generate = [p for p in plans if p.lesson_number not in existing_numbers]
    if not plans_to_generate:
        return

    occupancy = _Occupancy(
        group=group,
        teacher_ids={group_teacher.teacher_id},
        room_ids={slot.room_id for slot in slots if slot.room_id},
    )

    def lesson_kwargs_for(slot: GroupSchedule, plan, date):
        return dict(
            group=group,
            group_teacher=group_teacher,
            individual_plan=plan,
            schedule=slot,
            teacher=slot.teacher,
            lesson_number=plan.lesson_number,
            date=date,
            start_time=slot.start_time,
            end_time=slot.end_time,
            room=slot.room,
            subject=group_teacher.subject,
            topic=plan.topic,
            description=plan.description,
            youtube_url=plan.youtube_url,
            presentation_urls=plan.presentation_urls,
        )

    _walk_and_generate(
        group=group, slots_by_weekday=slots_by_weekday, plans_to_generate=plans_to_generate,
        lesson_kwargs_for=lesson_kwargs_for, occupancy=occupancy, run=run, label=label, not_before=not_before,
    )


@transaction.atomic
def _run_generation(group: Group, not_before: dt.date | None = None) -> _GenerationRun:
    # Serialise concurrent generation of the same group (a double-click,
    # two admins) on databases that support row locks — the second call
    # then sees the first one's lessons as existing. get_or_create in
    # _get_or_create_lesson stays the last line of defence either way.
    group = Group.objects.select_for_update().get(pk=group.pk)

    if group.status == Group.Status.CANCELLED:
        raise LessonGenerationError(f"Группа «{group.name}» отменена — занятия не генерируются.")

    group_teachers = list(group.teachers.filter(is_active=True).select_related("teacher", "subject"))
    if not group_teachers:
        raise LessonGenerationError("У группы нет ни одного тренера.")

    individual_ids = set(
        GroupTeacher.objects.filter(pk__in=[gt.pk for gt in group_teachers], lesson_plans__isnull=False)
        .values_list("pk", flat=True)
    )
    shared_group_teachers = [gt for gt in group_teachers if gt.pk not in individual_ids]
    individual_group_teachers = [gt for gt in group_teachers if gt.pk in individual_ids]

    run = _GenerationRun()

    if shared_group_teachers:
        try:
            _generate_from_course_plan(group, shared_group_teachers, run, not_before)
        except LessonGenerationError as exc:
            run.errors.append(str(exc))

    for group_teacher in individual_group_teachers:
        try:
            _generate_from_individual_plan(group, group_teacher, run, not_before)
        except LessonGenerationError as exc:
            run.errors.append(str(exc))

    if run.errors and not run.created:
        logger.info("[lesson_generator] Nothing generated for group id=%s: %s", group.pk, " ".join(run.errors))
    elif run.errors:
        logger.warning(
            "[lesson_generator] Group id=%s: %s lesson(s) created, but %s program(s) failed: %s",
            group.pk, len(run.created), len(run.errors), " | ".join(run.errors),
        )
    for message in run.warnings():
        logger.warning("[lesson_generator] Group id=%s: %s", group.pk, message)
    if run.created:
        logger.info(
            "[lesson_generator] Group id=%s: %s lesson(s) created across %s active program(s).",
            group.pk, len(run.created), len(group_teachers),
        )
    return run


def generate_lessons_for_group(group: Group) -> list[Lesson]:
    """Generate every missing Lesson for `group`, across all of its active
    GroupTeacher assignments (see module docstring). Idempotent and safe to
    call repeatedly — already-generated lesson_numbers are never touched
    again, and existing Lessons are never modified.

    Raises LessonGenerationError only if *nothing at all* could be
    generated because of an error — a partial failure (one teacher's plan
    not ready yet, say) still returns whatever the other teachers'
    assignments produced, so one misconfigured teacher never blocks the rest
    of the group. Lessons skipped for a missing teacher assignment are
    warnings, not errors — use generate_lessons_for_group_with_report() to
    see them.
    """
    run = _run_generation(group)
    if run.errors and not run.created:
        raise LessonGenerationError(" ".join(run.errors))
    return run.created


@dataclass
class LessonGenerationReport:
    """Human-readable summary of one generation call, for the Group
    Workspace's "Сгенерировать занятия" button and the API.

    `conflicts` counts slots/lessons skipped because a teacher, room or the
    group itself is already booked; `skipped` counts every other slot
    precondition skip (an inactive teacher/room, an invalid time range).
    `warnings` explains every plan row that was *not* turned into a lesson
    (no teacher assigned to its subject, several teachers, a clash, or the
    group's period ended first) — see `missing`.
    """

    created: int
    already_existed: int
    skipped: int
    conflicts: int
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    expected: int = 0
    missing: int = 0
    created_lessons: list[Lesson] = field(default_factory=list)


def _expected_lesson_count(group: Group) -> int:
    course_plan = group.course.lesson_plans.count()
    shared_in_use = group.teachers.filter(is_active=True, lesson_plans__isnull=True).exists()
    individual = sum(
        gt.lesson_plans.count() for gt in group.teachers.filter(is_active=True, lesson_plans__isnull=False).distinct()
    )
    return (course_plan if shared_in_use else 0) + individual


def generate_lessons_for_group_with_report(group: Group, *, not_before: dt.date | None = None) -> LessonGenerationReport:
    """Same generation as generate_lessons_for_group() — this only adds the
    Created / Already existed / Skipped / Conflicts / Warnings / Errors
    summary on top, so there's exactly one place the actual generation
    algorithm lives. `not_before` is for the repair_group_lessons command:
    place missing lessons only on or after that date."""
    already_existed = Lesson.objects.filter(group=group).count()

    try:
        run = _run_generation(group, not_before)
    except LessonGenerationError as exc:
        return LessonGenerationReport(
            created=0, already_existed=already_existed, skipped=0, conflicts=0, errors=[str(exc)],
            expected=_expected_lesson_count(group), missing=0,
        )

    expected = _expected_lesson_count(group)
    total = Lesson.objects.filter(group=group).count()
    return LessonGenerationReport(
        created=len(run.created),
        already_existed=already_existed,
        skipped=run.slot_skips,
        conflicts=run.slot_conflicts + run.lesson_conflicts,
        errors=list(run.errors),
        warnings=run.warnings(),
        expected=expected,
        missing=max(expected - total, 0),
        created_lessons=list(run.created),
    )
