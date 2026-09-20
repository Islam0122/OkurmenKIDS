"""Student deactivation/reactivation — the one place `Student.is_active`
ever flips and a `StudentStatusEvent` history record ever gets written.

Every caller (the Student Detail admin page's modal, the Group Workspace
roster) goes through `deactivate_student`/`reactivate_student` — never
`Student.objects.update(is_active=...)` directly — so the history log can
never silently fall out of sync with the current status, and a double
submit (double-click, retried request) can never create two events for the
same transition.
"""
from __future__ import annotations

import datetime as dt

from django.core.exceptions import ValidationError
from django.db import transaction

from ..models import Group, Student, StudentStatusEvent


def deactivate_student(
    student: Student,
    *,
    reason: str,
    comment: str = "",
    performed_by=None,
) -> StudentStatusEvent:
    """Marks `student` inactive and records why.

    Idempotent under concurrent/duplicate submission: the row is locked for
    the duration of the transaction, and an already-inactive student raises
    `ValidationError` instead of writing a second event for the same
    departure — a retried request (double-click, network retry) is a no-op
    error, not a duplicate history row.
    """
    if not reason:
        raise ValidationError({"reason": "Причина обязательна для деактивации."})
    if reason == StudentStatusEvent.Reason.OTHER and not comment.strip():
        raise ValidationError({"comment": "Для причины «Другая причина» комментарий обязателен."})

    with transaction.atomic():
        locked = Student.objects.select_for_update().get(pk=student.pk)
        if not locked.is_active:
            raise ValidationError("Студент уже деактивирован.")

        event = StudentStatusEvent(
            student=locked,
            event_type=StudentStatusEvent.EventType.DEACTIVATED,
            reason=reason,
            comment=comment,
            group=locked.group,
            event_date=dt.date.today(),
            performed_by=performed_by,
        )
        event.full_clean()
        event.save()

        locked.is_active = False
        locked.save(update_fields=["is_active", "updated_at"])

    student.is_active = False
    return event


def reactivate_student(
    student: Student,
    *,
    group: Group | None,
    event_date: dt.date,
    comment: str = "",
    performed_by=None,
) -> StudentStatusEvent:
    """Marks `student` active again in the given `group` — a separate history
    event from the deactivation it follows; the earlier event (and any
    earlier cycle) is never touched or removed, so several
    deactivate/reactivate cycles all stay on the record.
    """
    if group is None:
        raise ValidationError({"group": "Группа обязательна для повторной активации."})
    if event_date is None:
        raise ValidationError({"event_date": "Дата возвращения обязательна."})

    with transaction.atomic():
        locked = Student.objects.select_for_update().get(pk=student.pk)
        if locked.is_active:
            raise ValidationError("Студент уже активен.")

        event = StudentStatusEvent(
            student=locked,
            event_type=StudentStatusEvent.EventType.REACTIVATED,
            comment=comment,
            group=group,
            event_date=event_date,
            performed_by=performed_by,
        )
        event.full_clean()
        event.save()

        locked.is_active = True
        locked.group = group
        locked.save(update_fields=["is_active", "group", "updated_at"])

    student.is_active = True
    student.group = group
    return event
