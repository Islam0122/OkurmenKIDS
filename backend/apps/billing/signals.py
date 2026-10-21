"""Связь с LMS: сигналы только передают событие в сервисы после коммита
транзакции LMS — бизнес-логики здесь нет.

* урок сохранён / удалён, посещаемость изменена — `lessons.sync_lesson`
  (списание проведённого урока, сторно при отмене / удалении);
* событие статуса студента — `profiles.on_student_status_event`
  (остановка, пауза, возобновление начислений);
* после `migrate` — права группы `Accountant` на модели оплаты.
"""
from django.db import transaction
from django.db.models.signals import post_delete, post_migrate, post_save
from django.dispatch import receiver


def _sync_lesson_later(lesson_id):
    from .services.lessons import sync_lesson_safely

    transaction.on_commit(lambda: sync_lesson_safely(lesson_id))


@receiver(post_save, sender="academy.Lesson")
def lesson_saved(sender, instance, raw=False, **kwargs):
    if not raw:
        _sync_lesson_later(instance.pk)


@receiver(post_delete, sender="academy.Lesson")
def lesson_deleted(sender, instance, **kwargs):
    _sync_lesson_later(instance.pk)


@receiver(post_save, sender="academy.Attendance")
def attendance_saved(sender, instance, raw=False, **kwargs):
    if not raw and instance.lesson_id:
        _sync_lesson_later(instance.lesson_id)


@receiver(post_save, sender="academy.StudentStatusEvent")
def student_status_changed(sender, instance, created=False, raw=False, **kwargs):
    if raw or not created:
        return
    from .services.profiles import on_student_status_event

    event_id = instance.pk
    transaction.on_commit(lambda: on_student_status_event(event_id))


@receiver(post_migrate)
def accountant_billing_permissions(sender, **kwargs):
    if getattr(sender, "label", None) == "billing":
        from apps.accounting.access import ensure_accountant_group, ensure_billing_director_group

        ensure_accountant_group()
        ensure_billing_director_group()
