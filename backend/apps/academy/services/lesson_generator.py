"""Turns a Course's lesson-plan template into real, dated Lesson rows for a Group.

Reads *only* from `Group.schedules` (GroupSchedule) — never from Group's own
teacher/room/start_time/end_time/days_of_week directly. Those legacy fields
still work exactly as before because `services.group_schedule_sync` mirrors
them into GroupSchedule on every Group save (see signals.py), so a Group
that has never touched GroupSchedule directly still ends up with the exact
same schedule slot(s) it always had. GroupSchedule is additive on top of
that: a Group can carry extra slots — different teachers, subjects, days or
time ranges — added explicitly (Admin inline / API), and this generator
treats every active slot the same way regardless of where it came from.
"""
from __future__ import annotations

import datetime as dt
from collections import defaultdict

from django.db import transaction

from ..constants import WEEKDAY_CODES
from ..models import Group, GroupSchedule, Homework, Lesson

# A misconfigured group (an empty days_of_week that somehow bypassed
# validation, say) must never turn this into an infinite loop.
_MAX_DAYS_TO_SCAN = 366 * 5


class LessonGenerationError(Exception):
    """Raised when a group's course/schedule isn't in a state lessons can be generated from."""


def _weekday_slots(group: Group) -> dict[int, list[GroupSchedule]]:
    """Every active GroupSchedule slot of `group`, bucketed by Python weekday
    index (0=Monday) and ordered by start_time within each day — so a day
    with several slots (different subjects/teachers) generates its lessons
    left-to-right through the day, in a stable order."""
    by_weekday: dict[int, list[GroupSchedule]] = defaultdict(list)
    slots = group.schedules.filter(is_active=True).select_related("teacher", "subject", "room")
    for slot in slots:
        if slot.day_of_week in WEEKDAY_CODES:
            by_weekday[WEEKDAY_CODES.index(slot.day_of_week)].append(slot)
    for day_slots in by_weekday.values():
        day_slots.sort(key=lambda s: s.start_time)
    return by_weekday


def _create_homework_if_planned(lesson: Lesson, plan) -> None:
    """Auto-create the plan's standard Homework alongside a newly generated
    Lesson — only when the plan actually declares one. A Teacher/Admin can
    still add further Homework for the same lesson afterwards (Homework is a
    plain ForeignKey to Lesson, so several can coexist)."""
    if plan.homework_title:
        Homework.objects.create(
            lesson=lesson,
            title=plan.homework_title,
            description=plan.homework_description,
        )


@transaction.atomic
def generate_lessons_for_group(group: Group) -> list[Lesson]:
    """Generate Lesson rows for `group` from its course's CourseLessonPlan template.

    Walks forward from ``group.start_date``, and for every calendar day
    whose weekday has one or more active GroupSchedule slots, creates one
    Lesson per slot (in start_time order) from the next not-yet-generated
    CourseLessonPlan row — until every plan row has a Lesson (or
    ``group.end_date`` is reached first). `Lesson.lesson_number` is simply
    that global consumption order (1, 2, 3, ...), which is why the course's
    CourseLessonPlan rows must already be arranged in the same order the
    schedule will actually produce them week over week.

    Idempotent: lesson numbers already generated for this group are never
    touched again, so calling this repeatedly — after adding students, or
    after editing a future part of the schedule — is always safe and never
    creates duplicates. Past/completed/cancelled Lessons are never modified;
    only missing future plan rows are filled in.
    """
    plans = list(group.course.lesson_plans.order_by("lesson_number"))
    if not plans:
        raise LessonGenerationError("У курса нет плана занятий.")

    if len(plans) != group.course.count_lesson:
        raise LessonGenerationError(
            f"Количество занятий в плане курса ({len(plans)}) не совпадает "
            f"с полем count_lesson курса ({group.course.count_lesson})."
        )

    slots_by_weekday = _weekday_slots(group)
    if not slots_by_weekday:
        raise LessonGenerationError("У группы не задано расписание (нет активных слотов).")

    existing_numbers = set(Lesson.objects.filter(group=group).values_list("lesson_number", flat=True))
    plans_to_generate = [p for p in plans if p.lesson_number not in existing_numbers]
    if not plans_to_generate:
        return []

    created: list[Lesson] = []
    current_date = group.start_date
    plan_iter = iter(plans_to_generate)
    plan = next(plan_iter, None)
    scanned = 0

    while plan is not None and scanned < _MAX_DAYS_TO_SCAN:
        if group.end_date and current_date > group.end_date:
            break

        for slot in slots_by_weekday.get(current_date.weekday(), []):
            if plan is None:
                break

            lesson = Lesson.objects.create(
                group=group,
                plan=plan,
                schedule=slot,
                teacher=slot.teacher,
                lesson_number=plan.lesson_number,
                date=current_date,
                start_time=slot.start_time,
                end_time=slot.end_time,
                room=slot.room,
                subject=plan.subject,
                topic=plan.topic,
                description=plan.description,
                youtube_url=plan.youtube_url,
                presentation_urls=plan.presentation_urls,
            )
            created.append(lesson)
            _create_homework_if_planned(lesson, plan)
            plan = next(plan_iter, None)

        current_date += dt.timedelta(days=1)
        scanned += 1

    return created
