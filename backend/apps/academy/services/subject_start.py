"""Each subject of a group starts on its own date ("IT from 10.10, English
from 12.10") — models.GroupSubject.

* **Effective start** of a subject in a group: its GroupSubject row's date,
  never earlier than Group.start_date; a subject without a row starts with
  the group — how every group worked before per-subject dates existed.
* **Generation** (services.lesson_generator) never places a subject's lesson
  before that date.
* **Changing a date** (set_subject_start_date — the only writer, used by the
  Team Lead / Assistant API and the admin) touches that one subject only:
  never Group.start_date, never another subject. It refuses to move the
  start past a lesson that is already history (conducted, started, with
  attendance or homework results, or part of a cancel/make-up pair) — those
  stay where and as they are. The subject's not-yet-conducted lessons are
  *moved* (same rows, same numbers, topics and homework — nothing deleted or
  recreated) onto its slots' occurrences from the new date on, in their
  existing order, never onto an occurrence the group, the trainer or the
  room is already busy at. If they don't all fit before the group's end
  date nothing is changed.
* **KPI** (analytics.scope.AnalyticsScope.lessons_qs) leaves out any lesson
  dated before its subject's start (before_subject_start_q) — a safety net:
  the rules above already keep such lessons from existing.
"""
from __future__ import annotations

import datetime as dt
from collections import defaultdict, deque
from dataclasses import dataclass

from django.contrib.admin.models import CHANGE, LogEntry
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Exists, OuterRef, Q
from django.utils import timezone

from apps.users.models import Subject

from ..models import Group, GroupSchedule, GroupSubject, Lesson

STATUS_NOT_STARTED = "not_started"
STATUS_IN_PROGRESS = "in_progress"
STATUS_COMPLETED = "completed"
STATUS_LABELS = {
    STATUS_NOT_STARTED: "Не начался",
    STATUS_IN_PROGRESS: "Идёт обучение",
    STATUS_COMPLETED: "Завершён",
}

_MAX_LISTED = 5


# ---------------------------------------------------------------------------
# Reading
# ---------------------------------------------------------------------------

def subject_start_dates(group: Group) -> dict[int, dt.date]:
    """subject_id -> effective start date, for every subject that has an
    explicit GroupSubject row (callers fall back to group.start_date for
    the rest)."""
    return {
        subject_id: max(start, group.start_date)
        for subject_id, start in GroupSubject.objects.filter(group=group).values_list("subject_id", "start_date")
    }


def effective_start(group: Group, subject_id: int | None) -> dt.date:
    if subject_id is None:
        return group.start_date
    return subject_start_dates(group).get(subject_id, group.start_date)


def before_subject_start_q(prefix: str = "") -> Q:
    """Lessons (reached via `prefix`, e.g. "lesson__") dated before their
    subject's own start date in their group. Lessons of a subject without a
    GroupSubject row never match — their group's history stays as it was."""
    return Q(Exists(
        GroupSubject.objects.filter(
            group_id=OuterRef(f"{prefix}group_id"),
            subject_id=OuterRef(f"{prefix}subject_id"),
            start_date__gt=OuterRef(f"{prefix}date"),
        )
    ))


def subject_status(start: dt.date, today: dt.date, *, has_lessons: bool, open_lessons: int,
                   group_status: str) -> str:
    """«Не начался» before the start date; «Завершён» when the group is
    completed, or the subject has lessons and none of them is still to be
    given; otherwise «Идёт обучение»."""
    if today < start:
        return STATUS_NOT_STARTED
    if group_status == Group.Status.COMPLETED or (has_lessons and not open_lessons):
        return STATUS_COMPLETED
    return STATUS_IN_PROGRESS


def overview(group: Group, *, today: dt.date | None = None) -> dict:
    """Every subject of the group's course with its start date, where that
    date comes from, its status and lesson counts — the Team Lead's «Даты
    старта предметов» table."""
    today = today or timezone.localdate()
    rows = {row.subject_id: row for row in GroupSubject.objects.filter(group=group).select_related("updated_by")}
    lessons: dict[int, dict] = defaultdict(lambda: {"total": 0, "open": 0, "first": None})
    for subject_id, status, date in (
        Lesson.objects.filter(group=group, subject__isnull=False)
        .exclude(status=Lesson.Status.CANCELLED)
        .values_list("subject_id", "status", "date")
    ):
        info = lessons[subject_id]
        info["total"] += 1
        if status in (Lesson.Status.SCHEDULED, Lesson.Status.IN_PROGRESS):
            info["open"] += 1
        if info["first"] is None or date < info["first"]:
            info["first"] = date

    subjects = []
    for subject in group.course.subjects.order_by("name"):
        row = rows.get(subject.pk)
        start = max(row.start_date, group.start_date) if row else group.start_date
        info = lessons.get(subject.pk, {"total": 0, "open": 0, "first": None})
        status = subject_status(
            start, today, has_lessons=bool(info["total"]), open_lessons=info["open"], group_status=group.status,
        )
        subjects.append({
            "subject": {"id": subject.pk, "name": subject.name},
            "start_date": start,
            "is_custom": row is not None,
            "status": status,
            "status_display": STATUS_LABELS[status],
            "lessons_total": info["total"],
            "lessons_open": info["open"],
            "first_lesson_date": info["first"],
            "updated_by": _user_label(row.updated_by) if row and row.updated_by_id else None,
            "updated_at": row.updated_at if row else None,
        })
    return {
        "group": {
            "id": group.pk, "name": group.name, "course": group.course.name, "status": group.status,
            "start_date": group.start_date, "end_date": group.end_date,
        },
        "today": today,
        "subjects": subjects,
    }


def _user_label(user) -> str:
    return user.get_full_name() or user.username


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def validate_start_date(group: Group, subject: Subject, start_date: dt.date) -> None:
    errors = []
    if not group.course.subjects.filter(pk=subject.pk).exists():
        errors.append("Предмет не входит в курс этой группы.")
    if start_date < group.start_date:
        errors.append(
            f"Дата старта предмета не может быть раньше даты начала группы ({group.start_date:%d.%m.%Y})."
        )
    if group.end_date and start_date > group.end_date:
        errors.append(
            f"Дата старта предмета не может быть позже даты окончания группы ({group.end_date:%d.%m.%Y})."
        )
    if errors:
        raise ValidationError({"start_date": errors})


def check_lesson_date(lesson: Lesson, date: dt.date) -> None:
    """A lesson may not be put (moved by hand, edited) before its subject's
    start date in its group."""
    if not (lesson.group_id and lesson.subject_id):
        return
    start = GroupSubject.objects.filter(group_id=lesson.group_id, subject_id=lesson.subject_id).values_list(
        "start_date", flat=True,
    ).first()
    if start and date < start:
        raise ValidationError({
            "date": f"Предмет «{lesson.subject.name}» начинается {start:%d.%m.%Y} — занятие не может быть раньше."
        })


# ---------------------------------------------------------------------------
# Writing
# ---------------------------------------------------------------------------

@dataclass
class StartDateChange:
    subject_start: GroupSubject
    previous: dt.date
    moved: int


def _fmt(lesson: Lesson) -> str:
    return f"№{lesson.lesson_number} ({lesson.date:%d.%m.%Y})"


def set_subject_start_date(group: Group, subject: Subject, start_date: dt.date, *, user=None,
                           today: dt.date | None = None) -> StartDateChange:
    """Set `subject`'s start date in `group` (see module docstring)."""
    from .schedule_lesson_sync import lessons_with_data

    with transaction.atomic():
        # Same lock as lesson generation: the two never interleave.
        group = Group.objects.select_for_update().select_related("course").get(pk=group.pk)
        validate_start_date(group, subject, start_date)
        previous = effective_start(group, subject.pk)

        lessons = list(
            Lesson.objects.select_for_update()
            .filter(group=group, subject=subject)
            .exclude(status=Lesson.Status.CANCELLED)
            .select_related("schedule", "rescheduled_to", "group_teacher")
            .order_by("date", "start_time", "lesson_number", "pk")
        )
        with_data = lessons_with_data([lesson.pk for lesson in lessons])

        def is_history(lesson: Lesson) -> bool:
            return (
                lesson.status != Lesson.Status.SCHEDULED
                or lesson.started_at is not None
                or lesson.pk in with_data
            )

        def has_makeup(lesson: Lesson) -> bool:
            try:
                return lesson.rescheduled_to is not None
            except Lesson.DoesNotExist:
                return False

        fixed = [lesson for lesson in lessons if is_history(lesson) or lesson.rescheduled_from_id or has_makeup(lesson)]
        blocking = [lesson for lesson in fixed if lesson.date < start_date]
        if blocking:
            listed = ", ".join(_fmt(lesson) for lesson in blocking[:_MAX_LISTED])
            more = f" и ещё {len(blocking) - _MAX_LISTED}" if len(blocking) > _MAX_LISTED else ""
            raise ValidationError({"start_date": [
                f"У предмета «{subject.name}» уже есть проведённые или перенесённые занятия раньше этой даты: "
                f"{listed}{more}. Дата старта не может быть позже них."
            ]})

        fixed_ids = {lesson.pk for lesson in fixed}
        movable = [
            lesson for lesson in lessons
            if lesson.pk not in fixed_ids
            # A lesson moved by hand keeps its place unless it is now too early.
            and (not lesson.schedule_overridden or lesson.date < start_date)
        ]
        history = [lesson for lesson in fixed if is_history(lesson)]
        # Lessons that precede the new start must move; when nothing of the
        # subject has been given yet, the whole subject follows its start
        # (earlier or later). Once it is running, an earlier date only
        # records the start — the given lessons and the rest stay put.
        replan = any(lesson.date < start_date for lesson in movable) or (
            not history and movable and start_date != previous
        )
        moved = _replan(group, movable, start_date) if replan else 0

        subject_start, _created = GroupSubject.objects.update_or_create(
            group=group, subject=subject,
            defaults={"start_date": start_date, "updated_by": user if getattr(user, "pk", None) else None},
        )
        if user is not None and getattr(user, "pk", None):
            LogEntry.objects.log_actions(
                user_id=user.pk, queryset=[group], action_flag=CHANGE,
                change_message=(
                    f"Дата старта предмета «{subject.name}»: {previous:%d.%m.%Y} → {start_date:%d.%m.%Y}. "
                    f"Перенесено ещё не проведённых занятий: {moved}."
                ),
                single_object=True,
            )
    return StartDateChange(subject_start=subject_start, previous=previous, moved=moved)


def _replan(group: Group, movable: list[Lesson], start_date: dt.date) -> int:
    """Put `movable` (one subject's open lessons, in their current order)
    onto their programs' active slot occurrences from `start_date` on — the
    generator's own walk rules: one lesson per slot per week, never where the
    group, the lesson's trainer or the slot's room is already busy. Rows are
    updated in place. ValidationError (nothing written) if they don't fit."""
    from .lesson_generator import _MAX_DAYS_TO_SCAN, _Occupancy, _weekday_slots

    if not movable:
        return 0
    active_slots = [
        slot for slot in GroupSchedule.objects.filter(group=group, is_active=True).select_related("room")
        if slot.start_time < slot.end_time
    ]
    slots_by_program: dict[int, list[GroupSchedule]] = defaultdict(list)
    for slot in active_slots:
        slots_by_program[slot.group_teacher_id].append(slot)

    # A lesson stays with the program whose slots it was generated into
    # (its slot's program — a legacy shared slot included), or, without a
    # slot, with its own program.
    queues: dict[int, deque] = defaultdict(deque)
    for lesson in movable:
        program_id = lesson.schedule.group_teacher_id if lesson.schedule_id and lesson.schedule.is_active else None
        program_id = program_id or lesson.group_teacher_id
        if not slots_by_program.get(program_id):
            raise ValidationError({"start_date": [
                f"Занятие {_fmt(lesson)} нельзя перенести: у его программы нет активного расписания."
            ]})
        queues[program_id].append(lesson)

    used_slots = [slot for program_id in queues for slot in slots_by_program[program_id]]
    teacher_ids = {
        lesson.teacher_id or (lesson.group_teacher.teacher_id if lesson.group_teacher_id else None) for lesson in movable
    } - {None}
    occupancy = _Occupancy(
        group=group, teacher_ids=teacher_ids, room_ids={slot.room_id for slot in used_slots if slot.room_id},
        exclude_ids={lesson.pk for lesson in movable},
    )
    by_weekday = _weekday_slots(used_slots)

    before = {lesson.pk: (lesson.date, lesson.start_time, lesson.schedule_id) for lesson in movable}
    placed: list[Lesson] = []
    current, scanned = start_date, 0
    while any(queues.values()) and scanned < _MAX_DAYS_TO_SCAN:
        if group.end_date and current > group.end_date:
            break
        for slot in by_weekday.get(current.weekday(), []):
            queue = queues.get(slot.group_teacher_id)
            if not queue:
                continue
            if occupancy.group_busy(current, slot.start_time, slot.end_time) or occupancy.slot_week_taken(slot, current):
                continue
            lesson = queue[0]
            teacher_id = lesson.teacher_id or (lesson.group_teacher.teacher_id if lesson.group_teacher_id else None)
            if teacher_id and occupancy.teacher_busy(teacher_id, current, slot.start_time, slot.end_time):
                continue
            if slot.room_id and occupancy.room_busy(slot.room_id, current, slot.start_time, slot.end_time):
                continue
            queue.popleft()
            lesson.date, lesson.start_time, lesson.end_time = current, slot.start_time, slot.end_time
            lesson.schedule, lesson.room_id, lesson.schedule_overridden = slot, slot.room_id, False
            occupancy.add(lesson)
            placed.append(lesson)
        current += dt.timedelta(days=1)
        scanned += 1

    left = [lesson for queue in queues.values() for lesson in queue]
    if left:
        period = f"до даты окончания группы ({group.end_date:%d.%m.%Y})" if group.end_date else "в расписание"
        raise ValidationError({"start_date": [
            f"С этой даты не помещаются {len(left)} занятий предмета {period}. Ничего не изменено."
        ]})

    changed = [lesson for lesson in placed if before[lesson.pk] != (lesson.date, lesson.start_time, lesson.schedule_id)]
    stamp = timezone.now()
    for lesson in placed:
        lesson.updated_at = stamp
    Lesson.objects.bulk_update(
        placed, ["date", "start_time", "end_time", "schedule", "room", "schedule_overridden", "updated_at"],
    )
    return len(changed)
