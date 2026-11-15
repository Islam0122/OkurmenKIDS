"""Keep past lessons' «месяц · урок» when numbering settings are saved
outside an explicit numbering.preserving() block (the program API and the
Django admin form wrap their whole save in one): e.g. a group's own lessons
per month, or a curriculum saved in code."""
from __future__ import annotations

from django.db.models.signals import post_delete, post_save, pre_delete, pre_save
from django.dispatch import receiver

from . import numbering
from .models import GroupLessonNumbering, ProgramCurriculum


def _groups(instance) -> list[int]:
    if isinstance(instance, ProgramCurriculum):
        return numbering.groups_of_course(instance.course_id) if instance.course_id else []
    return [instance.group_id] if instance.group_id else []


@receiver(pre_save, sender=ProgramCurriculum)
@receiver(pre_save, sender=GroupLessonNumbering)
@receiver(pre_delete, sender=ProgramCurriculum)
@receiver(pre_delete, sender=GroupLessonNumbering)
def _before(sender, instance, **kwargs):
    instance._numbering_state = None if numbering._preserving.get() else numbering.begin(_groups(instance))


@receiver(post_save, sender=ProgramCurriculum)
@receiver(post_save, sender=GroupLessonNumbering)
@receiver(post_delete, sender=ProgramCurriculum)
@receiver(post_delete, sender=GroupLessonNumbering)
def _after(sender, instance, **kwargs):
    state = getattr(instance, "_numbering_state", None)
    instance._numbering_state = None
    if state is None:
        numbering.invalidate()
        return
    numbering.finish(state, user=getattr(instance, "updated_by", None), reason="Изменено число занятий в учебном месяце")
