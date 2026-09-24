"""Turns a lesson-plan template into real, dated Lesson rows for a Group.

Three sources of truth are combined here — and only here:

* **The lesson plan** decides *what* each lesson is: its number, subject,
  topic, materials and homework (the group's shared CourseLessonPlan, or a
  program's own GroupTeacherLessonPlan).
* **The program (GroupTeacher)** decides *who*: one trainer teaching one
  subject in the group ("Islam — IT", "Нуриса — Soft Skills").
* **The program's schedule** (its GroupSchedule slots) decides *when/where*.

Shared course plan (one course, e.g. 144 rows = IT 48 + Soft Skills 48 +
English 48): the rows are split **by subject**, and each subject's rows fill
**only that subject's own program slots**, in lesson_number order — IT's 48
rows go into the IT program's Mon/Wed/Fri 08:00 slots with Islam, Soft
Skills' 48 rows into the Soft Skills program's Mon/Wed/Fri 09:00 slots with
Нуриса. A subject never takes another subject's slots or rows, so 144 means
144 for the whole group, never 144 per program. See _SubjectRouting:

1. The subject has slots of its own (a program with that subject) → its
   rows go there; each lesson belongs to that slot's program and trainer.
2. Otherwise the subject is taught in the group's legacy subject-less
   slots, if any (migrated from the old Group.teacher/start_time fields):
   by its assigned trainer when the group has a subject assignment for it,
   else by the slot's own trainer — unchanged legacy behaviour.
3. The subject's program uses its own individual plan → the shared plan's
   rows for it are not used (reported).
4. Otherwise the subject has no schedule at all → its rows are *not*
   created and are reported; nobody else's slots or trainer are borrowed.

A row that can't be created in its slot occurrence (the trainer or room is
already busy at that exact date/time, an ambiguous legacy assignment) still
*reserves* that occurrence: the subject's calendar is not shifted, and a
warning names the lesson. The next generation run, after the cause is
fixed, places exactly that lesson on exactly that date.

Individual plan: a program with its own GroupTeacherLessonPlan rows walks
only its own slots, numbered 1..N independently of every other program.

Generation is **explicit** (the "Сгенерировать занятия" button, the admin
action, or `POST /groups/{id}/generate-lessons/`) — never triggered by
saving a single schedule slot. See signals.py.

Idempotent: only missing lesson_numbers are filled in, into slot
occurrences no existing lesson of the group already occupies; existing
Lesson rows (and their attendance/homework) are never modified or
duplicated, whatever their status.
"""
from __future__ import annotations

import datetime as dt
import logging
from collections import defaultdict, deque
from dataclasses import dataclass, field

from django.db import transaction
from django.db.models import Count, Q

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
    # subject name -> lesson numbers not created because no program schedule teaches the subject
    unscheduled: dict[str, list[int]] = field(default_factory=lambda: defaultdict(list))
    # subject name -> shared-plan lesson numbers left out because the subject's program has an individual plan
    individual_skipped: dict[str, list[int]] = field(default_factory=lambda: defaultdict(list))
    # subject name -> lesson numbers not created because several teachers are assigned to it
    ambiguous: dict[str, list[int]] = field(default_factory=lambda: defaultdict(list))
    busy: list[str] = field(default_factory=list)
    not_fitting: list[str] = field(default_factory=list)
    # Lessons without a program removed before generating (see find_orphan_lessons)
    orphans_deleted: list[str] = field(default_factory=list)
    # Lessons without a program that were deliberately kept, with why
    orphans_kept: list[str] = field(default_factory=list)
    inactive_assignments: list[str] = field(default_factory=list)

    def warnings(self) -> list[str]:
        messages = []
        for subject, numbers in sorted(self.unscheduled.items()):
            messages.append(
                f"Предмет «{subject}»: нет программы с расписанием (тренер + слоты этого предмета) — "
                f"не создано занятий: {len(numbers)} ({_format_numbers(numbers)}). Добавьте учебную "
                "программу предмета с расписанием и запустите генерацию ещё раз."
            )
        for subject, numbers in sorted(self.individual_skipped.items()):
            messages.append(
                f"Предмет «{subject}» ведётся по индивидуальному плану программы — {len(numbers)} "
                f"строк общего плана курса не используются ({_format_numbers(numbers)})."
            )
        for subject, numbers in sorted(self.ambiguous.items()):
            messages.append(
                f"Предмет «{subject}»: назначено несколько тренеров, и ни один из них не ведёт слот «без предмета» — "
                f"не создано занятий: {len(numbers)} ({_format_numbers(numbers)}). "
                "Оставьте одно активное назначение на предмет."
            )
        messages.extend(self.inactive_assignments)
        messages.extend(self.orphans_kept)
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
    """Deterministic identity: `(group_teacher, lesson_number)` among
    non-cancelled lessons — the exact pair the database's own
    `unique_active_group_teacher_lesson_number` constraint enforces (see
    models.Lesson.Meta.constraints; a cancelled lesson and its make-up share
    a lesson_number, see services.lesson_reschedule) — is the one and only
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
    return Lesson.objects.exclude(status=Lesson.Status.CANCELLED).get_or_create(defaults=defaults, **lookup)


def _walk_and_generate(*, group: Group, slots_by_weekday, take_next, remaining, lesson_kwargs_for,
                       occupancy: _Occupancy, run: _GenerationRun, label: str,
                       not_before: dt.date | None = None) -> None:
    """Shared walk-forward-by-calendar-day loop, from `group.start_date` up to
    `group.end_date` (or a hard scan cap), visiting every slot occurrence in
    weekday/start_time order.

    `take_next(slot)` pops the next plan row *this slot* may carry (the
    head of its own subject's queue — see _SubjectRouting), or returns None
    when the slot has nothing left to teach. `remaining()` lists the plan
    rows no slot has taken yet; the walk stops as soon as it is empty.
    `lesson_kwargs_for(slot, plan, date)` returns the concrete Lesson
    identity/content, or None when the row can't be given a teacher (it has
    then already recorded why on `run`).

    An occurrence the group already has a lesson in is skipped without
    taking a plan row; an occurrence whose row can't be created (no/
    ambiguous teacher, teacher or room busy that day) is *reserved* for
    that row — see the module docstring. `not_before` (repair_group_lessons
    only) starts the walk later than the group's start date, so a rebuild of
    the remaining plan never back-fills dates that have already passed.
    """
    current_date = max(group.start_date, not_before) if not_before else group.start_date
    scanned = 0

    while remaining() and scanned < _MAX_DAYS_TO_SCAN:
        if group.end_date and current_date > group.end_date:
            break

        for slot in slots_by_weekday.get(current_date.weekday(), []):
            if occupancy.group_busy(current_date, slot.start_time, slot.end_time):
                continue
            plan = take_next(slot)
            if plan is None:
                continue

            kwargs = lesson_kwargs_for(slot, plan, current_date)
            if kwargs is None:
                continue
            problem = _lesson_level_conflict(kwargs, occupancy)
            if problem:
                run.lesson_conflicts += 1
                run.busy.append(
                    f"Занятие №{plan.lesson_number} ({current_date:%d.%m.%Y} "
                    f"{slot.start_time:%H:%M}) не создано: {problem}"
                )
                logger.warning("[lesson_generator] %s: lesson #%s not created — %s", label, plan.lesson_number, problem)
                continue
            lesson, was_created = _get_or_create_lesson(kwargs)
            if was_created:
                run.created.append(lesson)
                _create_homework_if_planned(lesson, plan)
            occupancy.add(lesson)

        current_date += dt.timedelta(days=1)
        scanned += 1

    left = remaining()
    if left:
        numbers = sorted(p.lesson_number for p in left)
        period = f"до {group.end_date:%d.%m.%Y}" if group.end_date else "в допустимый период генерации"
        run.not_fitting.append(
            f"{label}: {len(numbers)} занятий плана не поместились в расписание {period} "
            f"({_format_numbers(numbers)})."
        )


def _lesson_level_conflict(kwargs: dict, occupancy: _Occupancy) -> str | None:
    teacher = kwargs["teacher"]
    slot = kwargs["schedule"]
    date, start, end = kwargs["date"], kwargs["start_time"], kwargs["end_time"]
    if teacher.pk != slot.teacher_id:
        # The slot-level checks in _without_conflicting_slots only vetted the
        # slot's *own* teacher; a subject-assigned teacher teaching in a
        # legacy subject-less slot may have a recurring slot of their own
        # elsewhere at this time.
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


def _subject_assignments(group_teachers: list[GroupTeacher], run: _GenerationRun | None = None) -> dict[int, list[GroupTeacher]]:
    """subject_id -> the active GroupTeacher assignments for it. An
    assignment whose Teacher account was deactivated is ignored (and
    reported) rather than silently handed new lessons."""
    by_subject: dict[int, list[GroupTeacher]] = defaultdict(list)
    for gt in group_teachers:
        if gt.subject_id is None:
            continue
        if not gt.teacher.is_active:
            if run is not None:
                run.inactive_assignments.append(f"Назначение «{gt}» не используется: тренер деактивирован.")
            continue
        by_subject[gt.subject_id].append(gt)
    return by_subject


ROUTE_DEDICATED = "dedicated"
ROUTE_LEGACY = "legacy"
ROUTE_INDIVIDUAL = "individual"
ROUTE_UNSCHEDULED = "unscheduled"


@dataclass
class _SubjectRouting:
    """Where each subject of the shared course plan is taught.

    * ``dedicated`` — the subject has its own active slots (its program's
      schedule, e.g. Soft Skills Mon/Wed/Fri 09:00–09:30). Its plan rows go
      into those slots only, never into another subject's slots.
    * ``legacy`` — no dedicated slot, but the group has subject-less legacy
      slots (migrated from the old Group.teacher/start_time fields): those
      keep running "whatever the plan says", as they always did.
    * ``individual`` — the subject's program has its own individual plan
      (GroupTeacherLessonPlan); the shared plan's rows for it are not used.
    * ``unscheduled`` — nowhere to put it: its rows are not generated.
    """

    route: dict[int, str]
    dedicated_slots: dict[int, list[GroupSchedule]]
    legacy_slots: list[GroupSchedule]
    assignments: dict[int, list[GroupTeacher]]

    def owners(self, subject_id: int) -> list[GroupTeacher]:
        """The program(s) a subject's rows are expected to belong to."""
        route = self.route.get(subject_id)
        if route == ROUTE_DEDICATED:
            owners = [slot.group_teacher for slot in self.dedicated_slots[subject_id]]
        elif route == ROUTE_LEGACY:
            owners = self.assignments.get(subject_id) or [slot.group_teacher for slot in self.legacy_slots]
        else:
            owners = []
        return list({gt.pk: gt for gt in owners}.values())


def _route_subjects(plans, slots: list[GroupSchedule], assignments, individual_subject_ids: set[int]) -> _SubjectRouting:
    dedicated: dict[int, list[GroupSchedule]] = defaultdict(list)
    legacy: list[GroupSchedule] = []
    for slot in slots:
        if slot.subject_id is None:
            legacy.append(slot)
        else:
            dedicated[slot.subject_id].append(slot)

    route: dict[int, str] = {}
    for plan in plans:
        subject_id = plan.subject_id
        if subject_id in route:
            continue
        if subject_id in dedicated:
            route[subject_id] = ROUTE_DEDICATED
        elif subject_id in individual_subject_ids:
            route[subject_id] = ROUTE_INDIVIDUAL
        elif legacy:
            route[subject_id] = ROUTE_LEGACY
        else:
            route[subject_id] = ROUTE_UNSCHEDULED
    return _SubjectRouting(route=route, dedicated_slots=dedicated, legacy_slots=legacy, assignments=assignments)


def _resolve_legacy_program(slot: GroupSchedule, subject_id: int, assignments: dict[int, list[GroupTeacher]]):
    """Program for a row taught in a legacy subject-less slot: the subject's
    assigned trainer if there is exactly one, the slot's own trainer if
    they are one of several, otherwise the slot's own trainer when nobody
    is assigned at all (unchanged legacy behaviour). (None, "ambiguous")
    when several trainers are assigned and the slot's isn't one of them."""
    assigned = assignments.get(subject_id, [])
    if len(assigned) == 1:
        return assigned[0], None
    if len(assigned) > 1:
        for gt in assigned:
            if gt.teacher_id == slot.teacher_id:
                return gt, None
        return None, "ambiguous"
    return slot.group_teacher, None


def _shared_plan_setup(group: Group, group_teachers: list[GroupTeacher], individual_group_teachers: list[GroupTeacher],
                       run: _GenerationRun | None = None, *, label: str = ""):
    """(plans, clean slots, routing) for the shared course plan — the single
    place both generation and the per-program counters (see
    planned_lessons_by_program) derive "which rows belong to which program"."""
    plans = list(group.course.lesson_plans.select_related("subject").order_by("lesson_number"))
    slots = list(
        GroupSchedule.objects.filter(group_teacher__in=group_teachers, is_active=True)
        .select_related("teacher", "subject", "room", "group", "group_teacher")
    )
    if run is not None:
        slots = _without_conflicting_slots(slots, label=label, run=run)
    assignments = _subject_assignments(group_teachers, run)
    individual_subject_ids = {gt.subject_id for gt in individual_group_teachers if gt.subject_id}
    return plans, slots, _route_subjects(plans, slots, assignments, individual_subject_ids)


def _generate_from_course_plan(group: Group, group_teachers: list[GroupTeacher], run: _GenerationRun,
                               not_before: dt.date | None = None,
                               individual_group_teachers: list[GroupTeacher] | None = None) -> None:
    """Shared path: the course plan's rows are split by subject, and each
    subject's rows (in lesson_number order) fill only that subject's own
    program slots — see _SubjectRouting. IT's 48 rows go to the IT slots,
    Soft Skills' 48 rows to the Soft Skills slots, and so on; no subject
    ever consumes another subject's rows or slots."""
    label = f"Группа «{group.name}» (общий план курса)"
    plans, slots, routing = _shared_plan_setup(
        group, group_teachers, individual_group_teachers or [], run, label=label,
    )
    if not plans:
        raise LessonGenerationError("У курса нет плана занятий.")
    if len(plans) != group.course.count_lesson:
        raise LessonGenerationError(
            f"Количество занятий в плане курса ({len(plans)}) не совпадает "
            f"с полем count_lesson курса ({group.course.count_lesson})."
        )
    if not slots:
        raise LessonGenerationError("У группы не задано расписание (нет активных слотов).")

    # Only shared-plan lessons count here — a teacher with an individual
    # plan numbers their own lessons 1..N independently (see
    # _generate_from_individual_plan), and those numbers must not mask the
    # shared plan's rows with the same numbers.
    existing_numbers = set(
        Lesson.objects.filter(group=group, individual_plan__isnull=True).values_list("lesson_number", flat=True)
    )

    queues: dict[int, deque] = defaultdict(deque)
    for plan in plans:
        if plan.lesson_number in existing_numbers:
            continue
        route = routing.route[plan.subject_id]
        if route == ROUTE_UNSCHEDULED:
            run.unscheduled[plan.subject.name].append(plan.lesson_number)
        elif route == ROUTE_INDIVIDUAL:
            run.individual_skipped[plan.subject.name].append(plan.lesson_number)
        else:
            queues[plan.subject_id].append(plan)
    if not queues:
        return

    legacy_subject_ids = [sid for sid, route in routing.route.items() if route == ROUTE_LEGACY]

    def take_next(slot: GroupSchedule):
        if slot.subject_id is not None:
            queue = queues.get(slot.subject_id)
            return queue.popleft() if queue else None
        # A legacy subject-less slot serves every subject without slots of
        # its own, in plan order — exactly the old single-teacher behaviour.
        heads = [queues[sid] for sid in legacy_subject_ids if queues.get(sid)]
        if not heads:
            return None
        return min(heads, key=lambda q: q[0].lesson_number).popleft()

    def remaining():
        return [plan for queue in queues.values() for plan in queue]

    slots_by_weekday = _weekday_slots(slots)
    teacher_ids = {slot.teacher_id for slot in slots} | {
        gt.teacher_id for gts in routing.assignments.values() for gt in gts
    }
    room_ids = {slot.room_id for slot in slots if slot.room_id}
    occupancy = _Occupancy(group=group, teacher_ids=teacher_ids, room_ids=room_ids)

    def lesson_kwargs_for(slot: GroupSchedule, plan, date):
        if slot.subject_id is not None:
            program = slot.group_teacher
        else:
            program, reason = _resolve_legacy_program(slot, plan.subject_id, routing.assignments)
            if program is None:
                run.ambiguous[plan.subject.name].append(plan.lesson_number)
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
        group=group, slots_by_weekday=slots_by_weekday, take_next=take_next, remaining=remaining,
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
    queue = deque(p for p in plans if p.lesson_number not in existing_numbers)
    if not queue:
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
        group=group, slots_by_weekday=slots_by_weekday,
        take_next=lambda slot: queue.popleft() if queue else None, remaining=lambda: list(queue),
        lesson_kwargs_for=lesson_kwargs_for, occupancy=occupancy, run=run, label=label, not_before=not_before,
    )


def planned_lessons_by_program(group: Group) -> dict[int, int]:
    """GroupTeacher id -> how many plan rows that program is responsible
    for: its own individual plan, or its subject's share of the shared
    course plan (e.g. 48 of 144) — by the very same routing generation uses.
    Powers the "План занятий N/N" counters, instead of showing the whole
    course plan's size on every program card."""
    group_teachers = list(group.teachers.filter(is_active=True).select_related("teacher", "subject"))
    individual = [gt for gt in group_teachers if gt.lesson_plans.exists()]
    individual_ids = {gt.pk for gt in individual}
    shared = [gt for gt in group_teachers if gt.pk not in individual_ids]

    planned: dict[int, int] = defaultdict(int)
    for gt in individual:
        planned[gt.pk] = gt.lesson_plans.count()
    if shared:
        plans, _slots, routing = _shared_plan_setup(group, shared, individual)
        rows_by_subject: dict[int, int] = defaultdict(int)
        for plan in plans:
            rows_by_subject[plan.subject_id] += 1
        for subject_id, count in rows_by_subject.items():
            for gt in routing.owners(subject_id):
                planned[gt.pk] += count
        # A program with a subject but no slots yet is still responsible
        # for that subject's rows — it just can't generate them yet.
        for gt in shared:
            if gt.subject_id and gt.pk not in planned and routing.route.get(gt.subject_id) == ROUTE_UNSCHEDULED:
                planned[gt.pk] = rows_by_subject.get(gt.subject_id, 0)
    return dict(planned)


ORPHAN_NO_PROGRAM = "no_program"
ORPHAN_LEGACY_SUPERSEDED = "legacy_superseded"

_ORPHAN_REASONS = {
    ORPHAN_NO_PROGRAM: "нет программы",
    ORPHAN_LEGACY_SUPERSEDED: "старая программа «без предмета», предмет теперь ведёт своя программа",
}


@dataclass
class OrphanScan:
    """Lessons of a group that show "—" as their program and that the
    current generation would not own. `deletable` are safe to remove and
    regenerate; `kept` pairs a lesson with the reason it must stay."""

    deletable: list[Lesson] = field(default_factory=list)
    kept: list[tuple[Lesson, str]] = field(default_factory=list)
    reasons: dict[int, str] = field(default_factory=dict)


def _orphan_label(lesson: Lesson) -> str:
    subject = lesson.subject.name if lesson.subject_id else "без предмета"
    return f"№{lesson.lesson_number} {lesson.date:%d.%m.%Y} «{lesson.topic or '—'}» ({subject})"


def find_orphan_lessons(group: Group) -> OrphanScan:
    """Read-only: which of `group`'s lessons are orphans, and which of those
    are safe to delete. Never looks outside `group`.

    Orphan (shows "—" in the Program column): a non-cancelled lesson whose
    `group_teacher` is NULL (its program was deleted — Lesson.group_teacher
    is SET_NULL), or whose program is a legacy one without a subject while
    the lesson's plan subject is now taught by a real subject program with
    its own slots (see _SubjectRouting). Both kinds block regeneration: the
    generator treats their lesson_number as already taken, so the real
    program never gets that plan row.

    Deletable only if the lesson is also *untouched and reproducible*:
    status "Запланирован", never started, no attendance, no homework
    results, no homework beyond the one auto-created from its plan row, not
    part of a cancel/reschedule pair, and generated from a plan row (so the
    generator can recreate it in the right program). Everything else —
    conducted/started lessons, lessons with any student data, hand-made
    lessons without a plan row — is kept and reported for a manual decision.
    Cancelled lessons are history and are not touched or reported.
    """
    scan = OrphanScan()
    candidates = list(
        Lesson.objects.filter(group=group)
        .exclude(status=Lesson.Status.CANCELLED)
        .filter(Q(group_teacher__isnull=True) | Q(group_teacher__subject__isnull=True))
        .select_related("subject", "plan", "group_teacher", "rescheduled_to")
        .annotate(
            _attendance_count=Count("attendance_records", distinct=True),
            _result_count=Count("homeworks__results", distinct=True),
            _homework_count=Count("homeworks", distinct=True),
        )
        .order_by("date", "start_time", "pk")
    )
    if not candidates:
        return scan

    dedicated_subject_ids: set[int] = set()
    if any(lesson.group_teacher_id for lesson in candidates):
        group_teachers = list(group.teachers.filter(is_active=True).select_related("teacher", "subject"))
        individual = [gt for gt in group_teachers if gt.lesson_plans.exists()]
        shared = [gt for gt in group_teachers if gt not in individual]
        if shared:
            _plans, _slots, routing = _shared_plan_setup(
                group, shared, individual, _GenerationRun(), label=f"Группа «{group.name}» (проверка)",
            )
            dedicated_subject_ids = {sid for sid, route in routing.route.items() if route == ROUTE_DEDICATED}

    for lesson in candidates:
        if lesson.group_teacher_id is None:
            reason = ORPHAN_NO_PROGRAM
        elif lesson.plan_id and lesson.plan.subject_id in dedicated_subject_ids:
            reason = ORPHAN_LEGACY_SUPERSEDED
        else:
            continue  # a legacy program that still legitimately teaches this lesson
        scan.reasons[lesson.pk] = reason

        auto_homework = 1 if lesson.plan_id and lesson.plan.homework_title else 0
        try:
            has_makeup = lesson.rescheduled_to is not None
        except Lesson.DoesNotExist:
            has_makeup = False
        if lesson.status != Lesson.Status.SCHEDULED or lesson.started_at is not None:
            scan.kept.append((lesson, f"статус «{lesson.get_status_display()}»"))
        elif lesson._attendance_count or lesson._result_count:
            scan.kept.append((lesson, "есть посещаемость или результаты ДЗ"))
        elif lesson._homework_count > auto_homework:
            scan.kept.append((lesson, "добавлено домашнее задание вручную"))
        elif lesson.rescheduled_from_id or has_makeup:
            scan.kept.append((lesson, "связано с переносом отменённого занятия"))
        elif not lesson.plan_id and not lesson.individual_plan_id:
            scan.kept.append((lesson, "создано вручную, без строки учебного плана"))
        else:
            scan.deletable.append(lesson)
    return scan


def _remove_orphan_lessons(group: Group, run: _GenerationRun, not_before: dt.date | None = None) -> None:
    """Delete find_orphan_lessons()'s `deletable` lessons (their auto-created
    homework cascades with them; by construction they have no attendance or
    results) and log each one. Runs inside _run_generation's transaction,
    under its group row lock. With `not_before` (repair_group_lessons
    --from-date) earlier lessons are kept, as that command promises."""
    scan = find_orphan_lessons(group)
    if not_before:
        earlier = [lesson for lesson in scan.deletable if lesson.date < not_before]
        scan.deletable = [lesson for lesson in scan.deletable if lesson.date >= not_before]
        scan.kept += [(lesson, f"дата раньше {not_before:%d.%m.%Y}") for lesson in earlier]
    for lesson, why in scan.kept:
        run.orphans_kept.append(
            f"Занятие без программы оставлено: {_orphan_label(lesson)} — {why}. Проверьте его вручную."
        )
    if not scan.deletable:
        return
    for lesson in scan.deletable:
        label = _orphan_label(lesson)
        run.orphans_deleted.append(label)
        logger.warning(
            "[lesson_generator] Group id=%s: deleting orphan lesson id=%s %s — %s.",
            group.pk, lesson.pk, label, _ORPHAN_REASONS[scan.reasons[lesson.pk]],
        )
    Lesson.objects.filter(pk__in=[lesson.pk for lesson in scan.deletable], group=group).delete()


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
    _remove_orphan_lessons(group, run, not_before)

    if shared_group_teachers:
        try:
            _generate_from_course_plan(group, shared_group_teachers, run, not_before, individual_group_teachers)
        except LessonGenerationError as exc:
            run.errors.append(str(exc))

    for group_teacher in individual_group_teachers:
        try:
            _generate_from_individual_plan(group, group_teacher, run, not_before)
        except LessonGenerationError as exc:
            run.errors.append(str(exc))

    if run.errors and not run.created:
        logger.info("[lesson_generator] Nothing generated for group id=%s: %s", group.pk, " ".join(run.errors))
        if run.orphans_deleted:
            # Generation failed outright: don't leave the group with its
            # orphans deleted but nothing regenerated in their place.
            transaction.set_rollback(True)
            logger.warning(
                "[lesson_generator] Group id=%s: rolled back deletion of %s orphan lesson(s).",
                group.pk, len(run.orphans_deleted),
            )
            run.orphans_deleted = []
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
    orphans_deleted: list[str] = field(default_factory=list)


def _expected_lesson_count(group: Group) -> int:
    """How many lessons the group's plan(s) call for: every shared course
    plan row (unless its subject's program uses an individual plan) plus
    every individual plan row."""
    return sum(planned_lessons_by_program(group).values()) + _unowned_shared_rows(group)


def _unowned_shared_rows(group: Group) -> int:
    """Shared plan rows no program owns yet (a subject with no program at
    all) — still part of what the group is expected to have."""
    group_teachers = list(group.teachers.filter(is_active=True).select_related("teacher", "subject"))
    individual = [gt for gt in group_teachers if gt.lesson_plans.exists()]
    shared = [gt for gt in group_teachers if gt not in individual]
    if not shared:
        return 0
    plans, _slots, routing = _shared_plan_setup(group, shared, individual)
    owned_subjects = {gt.subject_id for gt in shared if gt.subject_id}
    return sum(
        1 for plan in plans
        if routing.route.get(plan.subject_id) == ROUTE_UNSCHEDULED and plan.subject_id not in owned_subjects
    )


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
        orphans_deleted=list(run.orphans_deleted),
    )
