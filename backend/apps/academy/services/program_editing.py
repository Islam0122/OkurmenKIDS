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
  if asked, so do its future *scheduled* lessons (never started, dated
  today or later; each must not clash with a lesson the new teacher
  already gives). Conducted/cancelled/past lessons keep their trainer:
  they are history, and the old trainer's KPI.
* **Subject** — only while the program has no lessons at all: a lesson's
  subject is copied from the plan row it was generated from, so renaming
  the subject of a program that already has lessons would split the
  program from its own history.
* **Status** — `is_active`; an inactive program is ignored by generation
  and conflict checks (see GroupTeacher.is_active), nothing else changes.

Also home to build_schedule_slots(), the shared "one slot per selected
weekday, all validated before any is saved" step of the Workspace's
add-program and add-schedule forms.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from ..models import GroupSchedule, GroupTeacher, Lesson
from .group_schedule_conflicts import find_schedule_teacher_conflict

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


def future_lessons(group_teacher: GroupTeacher, *, today: dt.date | None = None):
    """The program's lessons a teacher change may move to the new teacher:
    still scheduled, never started, today or later."""
    today = today or timezone.localdate()
    return Lesson.objects.filter(
        group_teacher=group_teacher,
        status=Lesson.Status.SCHEDULED,
        started_at__isnull=True,
        date__gte=today,
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
