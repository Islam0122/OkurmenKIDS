"""Automatic Lesson generation, so Admin never has to click "Generate lessons" by hand.

Business flow: Admin creates Course -> CourseLessonPlan -> Group (with
teacher/room/days_of_week/time). The moment a Group is saved — created, or
its schedule/course edited — this fires `generate_lessons_for_group`, which
is idempotent (only fills in missing lesson_numbers, never touches or
duplicates existing Lesson rows). If the course's lesson plan isn't ready
yet (common right after creating a Group), generation just can't run yet —
that's a normal, expected state, not an error the Admin needs to see, so
it's logged and swallowed rather than raised. The manual "Сгенерировать
занятия" action/button stays in place as an explicit retry once the plan is
ready, or after fixing a data issue.
"""
from __future__ import annotations

import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Group
from .services.lesson_generator import LessonGenerationError, generate_lessons_for_group

logger = logging.getLogger(__name__)


@receiver(post_save, sender=Group)
def auto_generate_lessons_for_group(sender, instance: Group, **kwargs) -> None:
    try:
        created = generate_lessons_for_group(instance)
    except LessonGenerationError as exc:
        logger.info(
            "[signal:auto_generate_lessons_for_group] Skipped for group id=%s: %s",
            instance.pk,
            exc,
        )
        return

    if created:
        logger.info(
            "[signal:auto_generate_lessons_for_group] Generated %s lesson(s) for group id=%s.",
            len(created),
            instance.pk,
        )
