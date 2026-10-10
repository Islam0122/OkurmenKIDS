from django.conf import settings
from django.db import transaction
from django.db.models.signals import post_delete, post_migrate, post_save
from django.dispatch import receiver

from .access import ensure_accountant_group, sync_accountant_access


@receiver(post_migrate)
def create_accountant_group(sender, **kwargs):
    if getattr(sender, "label", None) == "accounting":
        ensure_accountant_group()


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def sync_accountant_group(sender, instance, raw=False, **kwargs):
    if not raw:
        sync_accountant_access(instance)


def _lesson_changed(instance, raw=False):
    """Урок сохранили или удалили — пересчитать циклы его группы после
    коммита: при достижении порога начисление тренеру создаётся сразу.
    Повторное сохранение того же урока ничего не дублирует."""
    if raw or not instance.group_id:
        return
    from apps.academy.services.trainer_history import _current_user

    from .services.cycles import sync_group_safely

    group_id, actor = instance.group_id, _current_user()
    transaction.on_commit(lambda: sync_group_safely(group_id, actor))


@receiver(post_save, sender="academy.Lesson")
def lesson_saved(sender, instance, raw=False, **kwargs):
    _lesson_changed(instance, raw)


@receiver(post_delete, sender="academy.Lesson")
def lesson_deleted(sender, instance, **kwargs):
    _lesson_changed(instance)
