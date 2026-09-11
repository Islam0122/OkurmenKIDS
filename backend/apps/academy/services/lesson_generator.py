"""Turns a lesson-plan template into real, dated Lesson rows for a Group.

A Group can have several GroupTeacher assignments (one per distinct
teacher/subject combination — see models.GroupTeacher), each with its own
active GroupSchedule slots. This module generates lessons independently
*per GroupTeacher*, so each one gets its own lesson_number sequence starting
at 1 — Islam's lesson #1 and Aizada's lesson #1 in the same group are two
different, unrelated Lesson rows.

Two plan sources are supported, chosen per GroupTeacher:

* **Individual plan** — the GroupTeacher has its own GroupTeacherLessonPlan
  rows. Lessons are generated from those, walking only that teacher's own
  active schedule slots, numbered 1..N independently of every other teacher
  in the group.

* **Legacy/shared plan** — the GroupTeacher has no GroupTeacherLessonPlan of
  its own. Falls back to the group's shared `Course.lesson_plans` template,
  exactly as every group generated lessons before GroupTeacher existed: all
  such teachers' active slots are walked together in one combined
  day-by-day, start-time-order pass, consuming the *same* global
  lesson_number cursor. This is a pure behavioural no-op for every group
  that predates individual per-teacher plans — nothing about an existing
  group changes until an admin explicitly gives one of its teachers their
  own GroupTeacherLessonPlan.

Both paths are idempotent (only fill in missing lesson_numbers, never touch
or duplicate existing Lesson rows) and never touch past/completed/cancelled
Lessons — only missing future plan rows are filled in.
"""
from __future__ import annotations

import datetime as dt
from collections import defaultdict

from django.db import transaction

from ..constants import WEEKDAY_CODES
from ..models import Group, GroupSchedule, GroupTeacher, Homework, Lesson

# A misconfigured group (an empty days_of_week that somehow bypassed
# validation, say) must never turn this into an infinite loop.
_MAX_DAYS_TO_SCAN = 366 * 5


class LessonGenerationError(Exception):
    """Raised when a group teacher's course/schedule isn't in a state lessons can be generated from."""


def _weekday_slots(schedule_qs) -> dict[int, list[GroupSchedule]]:
    """Every slot of `schedule_qs`, bucketed by Python weekday index
    (0=Monday) and ordered by start_time within each day — so a day with
    several slots (different subjects/teachers) generates its lessons
    left-to-right through the day, in a stable order."""
    by_weekday: dict[int, list[GroupSchedule]] = defaultdict(list)
    for slot in schedule_qs.select_related("teacher", "subject", "room"):
        if slot.day_of_week in WEEKDAY_CODES:
            by_weekday[WEEKDAY_CODES.index(slot.day_of_week)].append(slot)
    for day_slots in by_weekday.values():
        day_slots.sort(key=lambda s: s.start_time)
    return by_weekday


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


def _walk_and_generate(*, group: Group, slots_by_weekday, plans_to_generate, lesson_kwargs_for) -> list[Lesson]:
    """Shared walk-forward-by-calendar-day loop: consumes `plans_to_generate`
    in order, one per active slot encountered (in weekday/start_time order),
    from `group.start_date` up to `group.end_date` (or a hard scan cap).
    `lesson_kwargs_for(slot, plan, date)` builds the concrete Lesson.objects.create()
    kwargs for one (slot, plan) pairing — the two generation modes below only
    differ in that.
    """
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

            lesson = Lesson.objects.create(**lesson_kwargs_for(slot, plan, current_date))
            created.append(lesson)
            _create_homework_if_planned(lesson, plan)
            plan = next(plan_iter, None)

        current_date += dt.timedelta(days=1)
        scanned += 1

    return created


def _generate_from_course_plan(group: Group, group_teachers: list[GroupTeacher]) -> list[Lesson]:
    """Legacy/shared path: every one of `group_teachers`' active slots
    consumes the *same* shared `group.course.lesson_plans` cursor, exactly
    as `generate_lessons_for_group` always worked before GroupTeacher
    existed — see this module's docstring."""
    plans = list(group.course.lesson_plans.order_by("lesson_number"))
    if not plans:
        raise LessonGenerationError("У курса нет плана занятий.")

    if len(plans) != group.course.count_lesson:
        raise LessonGenerationError(
            f"Количество занятий в плане курса ({len(plans)}) не совпадает "
            f"с полем count_lesson курса ({group.course.count_lesson})."
        )

    slots = GroupSchedule.objects.filter(group_teacher__in=group_teachers, is_active=True)
    slots_by_weekday = _weekday_slots(slots)
    if not slots_by_weekday:
        raise LessonGenerationError("У группы не задано расписание (нет активных слотов).")

    existing_numbers = set(Lesson.objects.filter(group=group).values_list("lesson_number", flat=True))
    plans_to_generate = [p for p in plans if p.lesson_number not in existing_numbers]
    if not plans_to_generate:
        return []

    def lesson_kwargs_for(slot: GroupSchedule, plan, date):
        return dict(
            group=group,
            group_teacher=slot.group_teacher,
            plan=plan,
            schedule=slot,
            teacher=slot.teacher,
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

    return _walk_and_generate(
        group=group, slots_by_weekday=slots_by_weekday,
        plans_to_generate=plans_to_generate, lesson_kwargs_for=lesson_kwargs_for,
    )


def _generate_from_individual_plan(group: Group, group_teacher: GroupTeacher) -> list[Lesson]:
    """Individual path: `group_teacher`'s own plan and own slots only, own
    lesson_number sequence starting at 1 — independent of every other
    teacher in the same group."""
    plans = list(group_teacher.lesson_plans.order_by("lesson_number"))
    if not plans:
        return []

    slots = group_teacher.schedules.filter(is_active=True)
    slots_by_weekday = _weekday_slots(slots)
    if not slots_by_weekday:
        raise LessonGenerationError(f"У тренера «{group_teacher}» нет активного расписания.")

    existing_numbers = set(
        Lesson.objects.filter(group_teacher=group_teacher).values_list("lesson_number", flat=True)
    )
    plans_to_generate = [p for p in plans if p.lesson_number not in existing_numbers]
    if not plans_to_generate:
        return []

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

    return _walk_and_generate(
        group=group, slots_by_weekday=slots_by_weekday,
        plans_to_generate=plans_to_generate, lesson_kwargs_for=lesson_kwargs_for,
    )


@transaction.atomic
def generate_lessons_for_group(group: Group) -> list[Lesson]:
    """Generate every missing Lesson for `group`, across all of its active
    GroupTeacher assignments (see module docstring for the two plan
    sources). Idempotent and safe to call repeatedly — already-generated
    lesson_numbers (per GroupTeacher) are never touched again, and
    past/completed/cancelled Lessons are never modified.

    Raises LessonGenerationError only if *nothing at all* could be
    generated — a partial failure (one teacher's plan not ready yet, say)
    still returns whatever the other teachers' assignments produced, so one
    misconfigured teacher never blocks the rest of the group.
    """
    group_teachers = list(group.teachers.filter(is_active=True).select_related("teacher", "subject"))
    if not group_teachers:
        raise LessonGenerationError("У группы нет ни одного тренера.")

    legacy_group_teachers = [gt for gt in group_teachers if not gt.lesson_plans.exists()]
    individual_group_teachers = [gt for gt in group_teachers if gt.lesson_plans.exists()]

    created: list[Lesson] = []
    errors: list[str] = []

    if legacy_group_teachers:
        try:
            created += _generate_from_course_plan(group, legacy_group_teachers)
        except LessonGenerationError as exc:
            errors.append(str(exc))

    for group_teacher in individual_group_teachers:
        try:
            created += _generate_from_individual_plan(group, group_teacher)
        except LessonGenerationError as exc:
            errors.append(str(exc))

    if errors and not created:
        raise LessonGenerationError(" ".join(errors))

    return created
