"""Automatic Lesson generation, so Admin never has to click "Generate lessons" by hand.

Business flow: Admin creates Course -> CourseLessonPlan -> Group (with a
schedule — its own primary teacher/room/days_of_week/time, plus optionally
extra GroupSchedule slots for other teachers/subjects/times). Saving the
Group, or saving/removing one of its GroupSchedule rows, fires
`generate_lessons_for_group`, which is idempotent (only fills in missing
lesson_numbers, never touches or duplicates existing Lesson rows). If the
course's lesson plan isn't ready yet (common right after creating a Group),
generation just can't run yet — that's a normal, expected state, not an
error the Admin needs to see, so it's logged and swallowed rather than
raised. The manual "Сгенерировать занятия" action/button stays in place as
an explicit retry once the plan is ready, or after fixing a data issue.

Generation reads *every* active GroupSchedule slot of a group at once (see
services.lesson_generator) — so it deliberately isn't re-run for every
single intermediate save when a Group + several schedule slots are all
being set up together in the same request (the Django admin's Group page,
whose inline schedule rows save *after* the Group itself). Setting
``instance._defer_schedule_sync = True`` before such a batch of saves, and
running `generate_lessons_for_group` explicitly once at the end (see
`GroupAdmin.save_model` / `save_related`), avoids the group's primary slot
alone greedily consuming the *entire* course plan before the rest of the
schedule even exists.
"""
from __future__ import annotations

import logging

from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from .models import Group, GroupSchedule
from .services.group_schedule_sync import sync_legacy_group_schedule
from .services.lesson_generator import LessonGenerationError, generate_lessons_for_group

logger = logging.getLogger(__name__)


def _generate(group: Group, *, source: str) -> None:
    try:
        created = generate_lessons_for_group(group)
    except LessonGenerationError as exc:
        logger.info("[signal:%s] Skipped for group id=%s: %s", source, group.pk, exc)
        return

    if created:
        logger.info(
            "[signal:%s] Generated %s lesson(s) for group id=%s.", source, len(created), group.pk
        )


@receiver(post_save, sender=Group)
def auto_generate_lessons_for_group(sender, instance: Group, **kwargs) -> None:
    if getattr(instance, "_defer_schedule_sync", False):
        return

    # Mirror the group's own teacher/room/time/days_of_week into GroupSchedule
    # *before* generating lessons — the generator reads schedule slots only,
    # never Group's own fields directly (see services.lesson_generator).
    sync_legacy_group_schedule(instance)
    _generate(instance, source="auto_generate_lessons_for_group")


@receiver(post_save, sender=GroupSchedule)
def auto_generate_lessons_for_group_schedule(sender, instance: GroupSchedule, **kwargs) -> None:
    if getattr(instance, "_defer_schedule_sync", False):
        return
    _generate(instance.group, source="auto_generate_lessons_for_group_schedule")


@receiver(post_delete, sender=GroupSchedule)
def regenerate_after_schedule_slot_removed(sender, instance: GroupSchedule, **kwargs) -> None:
    # Removing a slot never touches Lessons already generated from it
    # (Lesson.schedule is SET_NULL, see models.Lesson) — this just re-runs
    # the idempotent generator defensively, in case the group still has
    # plan rows left to fill from its remaining slots.
    _generate(instance.group, source="regenerate_after_schedule_slot_removed")
