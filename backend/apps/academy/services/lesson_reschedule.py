"""Cancelling a lesson without losing its topic: the cancelled topic moves
to the program's next lesson date, and every later topic of the program
shifts one lesson date forward.

Example (IT program, Mon/Wed/Fri 08:00), cancelling 21.09 "Домен и DNS":

    21.09  Домен и DNS          cancelled   ← stays as history, untouched
    23.09  Домен и DNS          scheduled   ← new make-up lesson (rescheduled_from = 21.09)
    25.09  HTTP и HTTPS         scheduled   ← was 23.09
    28.09  Персональные данные  scheduled   ← was 25.09
    …      (last topic)         scheduled   ← moved to the program's next free slot

How: the *topics* never move between Lesson rows — each lesson keeps its
own lesson_number/plan/topic/homework/attendance. Instead the program's
still-open lessons after the cancelled one (the "chain": status
SCHEDULED, never started, same GroupTeacher) each take the date/time/room
of the next one in the chain; the last one takes the program's next free
slot occurrence (see _next_free_occurrence); and the cancelled topic gets
a new make-up Lesson on the chain's first date. Consequences:

* COMPLETED / IN_PROGRESS lessons are never touched (not in the chain),
  and neither is the cancelled lesson itself — its attendance, homework
  results, cancellation reason and date stay exactly as they were.
* Homework that belongs to the moved topics moves with them (it is
  attached to their Lesson rows); the cancelled lesson's own planned
  homework — only rows without any results — moves to its make-up lesson,
  so students see it on the day the topic is actually taught.
* The make-up lesson has the same lesson_number as the cancelled one:
  models.Lesson's unique constraint deliberately ignores cancelled rows.
* `Lesson.rescheduled_from` is a OneToOneField: one cancelled lesson can
  have at most one make-up lesson, so running the reschedule again (a
  double click, a retried request, two admins at once) can never shift
  the program twice. The group row is locked first, the same lock lesson
  generation takes, so reschedule and generation never interleave.

Only dates are compared — never `now()`/`today()` — so no time-zone
arithmetic is involved; a lesson's status is never inferred from its date.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Q

from ..models import Group, Homework, Lesson
from . import lesson_lifecycle
from .lesson_generator import _MAX_DAYS_TO_SCAN, _Occupancy, _weekday_slots


@dataclass
class RescheduleResult:
    makeup: Lesson | None
    shifted: int = 0
    created: bool = False
    warning: str = ""


_POSITION_FIELDS = ("date", "start_time", "end_time", "room_id", "schedule_id")


def _position(lesson: Lesson) -> dict:
    return {name: getattr(lesson, name) for name in _POSITION_FIELDS}


def _next_free_occurrence(lesson: Lesson, after: Lesson) -> dict | None:
    """The first occurrence of `lesson`'s program's own active slots strictly
    after `after`'s date/time where neither the group, nor the slot's
    teacher, nor its room already has a (non-cancelled, for teacher/room)
    lesson — within the group's end date. None if there is none."""
    group = lesson.group
    slots = list(
        lesson.group_teacher.schedules.filter(is_active=True, teacher__is_active=True)
        .select_related("room")
        .exclude(room__is_active=False)
    )
    if not slots:
        return None
    occupancy = _Occupancy(
        group=group,
        teacher_ids={slot.teacher_id for slot in slots},
        room_ids={slot.room_id for slot in slots if slot.room_id},
    )
    slots_by_weekday = _weekday_slots(slots)

    current = after.date
    for _ in range(_MAX_DAYS_TO_SCAN):
        if group.end_date and current > group.end_date:
            return None
        for slot in slots_by_weekday.get(current.weekday(), []):
            if current == after.date and slot.start_time <= after.start_time:
                continue
            if occupancy.group_busy(current, slot.start_time, slot.end_time):
                continue
            if occupancy.teacher_busy(slot.teacher_id, current, slot.start_time, slot.end_time):
                continue
            if slot.room_id and occupancy.room_busy(slot.room_id, current, slot.start_time, slot.end_time):
                continue
            return {
                "date": current, "start_time": slot.start_time, "end_time": slot.end_time,
                "room_id": slot.room_id, "schedule_id": slot.pk,
            }
        current += dt.timedelta(days=1)
    return None


def reschedule_cancelled_lesson(lesson: Lesson) -> RescheduleResult:
    """Move a cancelled lesson's topic to the program's next lesson date and
    shift every later open lesson of the program one date forward — see the
    module docstring. Idempotent: if the lesson already has a make-up
    lesson, it is returned unchanged and nothing moves again.

    Returns a result with `makeup=None` and a `warning` (and changes
    nothing) when the program has no free slot left for its last topic
    before the group's end date, no active schedule at all, or the lesson
    has no program (group_teacher is NULL). Raises ValidationError only if
    the lesson isn't cancelled."""
    with transaction.atomic():
        Group.objects.select_for_update().get(pk=lesson.group_id)
        # of=("self",): lock only the lesson row. Lesson.group_teacher is a
        # nullable FK, so select_related() turns it into a LEFT OUTER JOIN,
        # and a bare FOR UPDATE would try to lock that join's nullable side
        # too — which PostgreSQL rejects ("FOR UPDATE cannot be applied to
        # the nullable side of an outer join"). The group row is already
        # locked just above; the program row is only read here.
        lesson = (
            Lesson.objects.select_for_update(of=("self",))
            .select_related("group", "group_teacher")
            .get(pk=lesson.pk)
        )

        if lesson.status != Lesson.Status.CANCELLED:
            raise ValidationError({"status": ["Перенести можно только отменённое занятие."]})
        existing = Lesson.objects.filter(rescheduled_from=lesson).first()
        if existing is not None:
            return RescheduleResult(makeup=existing)
        if lesson.group_teacher_id is None:
            # A lesson whose program was deleted (Lesson.group_teacher is
            # SET_NULL) has no schedule to move its topic into. Reported like
            # "no free slot" — never raised: raising here would roll back the
            # surrounding cancel_and_reschedule() transaction and make such a
            # lesson impossible to cancel at all.
            return RescheduleResult(
                makeup=None,
                warning=(
                    f"Тема «{lesson.topic}» не перенесена: у занятия нет учебной программы "
                    "(программа удалена), поэтому нет расписания для переноса."
                ),
            )

        chain = list(
            Lesson.objects.select_for_update()
            .filter(group_teacher_id=lesson.group_teacher_id, status=Lesson.Status.SCHEDULED, started_at__isnull=True)
            .filter(Q(date__gt=lesson.date) | Q(date=lesson.date, start_time__gt=lesson.start_time))
            .order_by("date", "start_time", "pk")
        )
        tail = _next_free_occurrence(lesson, after=chain[-1] if chain else lesson)
        if tail is None:
            period = f" до {lesson.group.end_date:%d.%m.%Y}" if lesson.group.end_date else ""
            return RescheduleResult(
                makeup=None,
                warning=(
                    f"Тема «{lesson.topic}» не перенесена: у программы нет свободного слота расписания"
                    f"{period}. Добавьте слот или продлите группу и повторите перенос."
                ),
            )

        positions = [_position(item) for item in chain] + [tail]

        # Latest first, so no two open lessons of the program ever sit on
        # the same date/time mid-way through the shift.
        for index in range(len(chain) - 1, -1, -1):
            item = chain[index]
            for name, value in positions[index + 1].items():
                setattr(item, name, value)
            item.save(update_fields=[*_POSITION_FIELDS, "updated_at"])

        try:
            with transaction.atomic():
                makeup = Lesson.objects.create(
                    group_id=lesson.group_id,
                    group_teacher_id=lesson.group_teacher_id,
                    plan_id=lesson.plan_id,
                    individual_plan_id=lesson.individual_plan_id,
                    teacher_id=lesson.teacher_id,
                    subject_id=lesson.subject_id,
                    lesson_number=lesson.lesson_number,
                    topic=lesson.topic,
                    description=lesson.description,
                    youtube_url=lesson.youtube_url,
                    presentation_urls=lesson.presentation_urls,
                    homework_not_required=lesson.homework_not_required,
                    status=Lesson.Status.SCHEDULED,
                    rescheduled_from=lesson,
                    **positions[0],
                )
        except IntegrityError:
            raise ValidationError(
                {"lesson_number": ["Для этой темы уже есть активное занятие — перенос не требуется."]}
            )

        # Planned homework (no results yet) follows the topic to the day it
        # is actually taught; anything already graded stays with its lesson.
        Homework.objects.filter(lesson=lesson, results__isnull=True).update(lesson=makeup)

        return RescheduleResult(makeup=makeup, shifted=len(chain), created=True)


def cancel_and_reschedule(lesson: Lesson, user, reason: str = "", reschedule: bool = True) -> tuple[Lesson, RescheduleResult | None]:
    """The "Отменить занятие" action: cancel (services.lesson_lifecycle
    rules — a completed lesson can never be cancelled, cancelling twice is a
    no-op) and, unless `reschedule` is False, move its topic forward — both
    in one transaction. Repeating the call never shifts anything twice."""
    with transaction.atomic():
        # Same lock order as reschedule_cancelled_lesson and lesson
        # generation (group row first), so they can never deadlock.
        Group.objects.select_for_update().get(pk=lesson.group_id)
        lesson = Lesson.objects.select_for_update().get(pk=lesson.pk)
        lesson = lesson_lifecycle.cancel_lesson(lesson, user, reason=reason)
        result = reschedule_cancelled_lesson(lesson) if reschedule else None
    return lesson, result
