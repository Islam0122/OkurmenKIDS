"""Keep past lessons' «Месяц · Урок» when lessons per month changes.

Whatever changes a group's effective lessons per month — its program's
setting (ProgramCurriculum), the group's own (GroupLessonNumbering), from the
API or Django admin, created, edited or deleted — the sizes are read before
the change and numbering.freeze_history() fixes the months already started.
"""
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
def _remember_sizes(sender, instance, **kwargs):
    instance._numbering_before = numbering.effective_sizes(_groups(instance))


@receiver(post_save, sender=ProgramCurriculum)
@receiver(post_save, sender=GroupLessonNumbering)
@receiver(post_delete, sender=ProgramCurriculum)
@receiver(post_delete, sender=GroupLessonNumbering)
def _freeze_started_months(sender, instance, **kwargs):
    numbering.invalidate()
    before = getattr(instance, "_numbering_before", None)
    if not before:
        return
    after = numbering.effective_sizes(before)
    changed = {group: old for group, old in before.items() if after.get(group) != old}
    if changed:
        numbering.freeze_history(changed, user=getattr(instance, "updated_by", None),
                                 reason=f"Занятий в месяце изменено на {', '.join(sorted({str(after[g]) for g in changed}))}")
