"""Turns a Course's lesson-plan template into real, dated Lesson rows for a Group."""
from __future__ import annotations

import datetime as dt

from django.db import transaction

from ..constants import WEEKDAY_CODES
from ..models import Group, Lesson

# A misconfigured group (an empty days_of_week that somehow bypassed
# validation, say) must never turn this into an infinite loop.
_MAX_DAYS_TO_SCAN = 366 * 5


class LessonGenerationError(Exception):
    """Raised when a group's course isn't in a state lessons can be generated from."""


@transaction.atomic
def generate_lessons_for_group(group: Group) -> list[Lesson]:
    """Generate Lesson rows for `group` from its course's CourseLessonPlan template.

    Walks forward from ``group.start_date`` over ``group.days_of_week``,
    creating one Lesson per matching calendar day — in plan order — until
    every plan row has a Lesson (or ``group.end_date`` is reached first).
    Idempotent: lesson numbers already generated for this group are skipped,
    so calling this again after adding students, say, is always safe.
    """
    plans = list(group.course.lesson_plans.order_by("lesson_number"))
    if not plans:
        raise LessonGenerationError("У курса нет плана занятий.")

    if len(plans) != group.course.count_lesson:
        raise LessonGenerationError(
            f"Количество занятий в плане курса ({len(plans)}) не совпадает "
            f"с полем count_lesson курса ({group.course.count_lesson})."
        )

    if not group.days_of_week:
        raise LessonGenerationError("У группы не заданы дни недели.")

    weekday_indexes = {WEEKDAY_CODES.index(day) for day in group.days_of_week if day in WEEKDAY_CODES}
    if not weekday_indexes:
        raise LessonGenerationError("Дни недели группы указаны некорректно.")

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

        if current_date.weekday() in weekday_indexes:
            lesson = Lesson.objects.create(
                group=group,
                plan=plan,
                lesson_number=plan.lesson_number,
                date=current_date,
                start_time=group.start_time,
                end_time=group.end_time,
                room=group.room,
                subject=plan.subject,
                topic=plan.topic,
                description=plan.description,
                youtube_url=plan.youtube_url,
                presentation_urls=plan.presentation_urls,
            )
            created.append(lesson)
            plan = next(plan_iter, None)

        current_date += dt.timedelta(days=1)
        scanned += 1

    return created
