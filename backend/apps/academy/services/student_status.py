"""Every Student lifecycle transition — the one place `Student.status`/
`is_active` ever changes and a `StudentStatusEvent` history record ever
gets written.

    ACTIVE --deactivate--> WITHDRAWN --reactivate--> ACTIVE
    ACTIVE --pause------->  PAUSED   --continue----->  ACTIVE
    ACTIVE --complete---->  COMPLETED
    PAUSED --complete---->  COMPLETED

Every caller (the Student Detail admin page's modals, the Group Workspace
roster) goes through one of the five functions below — never
`Student.objects.update(...)` directly — so the history log can never
silently fall out of sync with the current status, and a double submit
(double-click, retried request) can never create two events for the same
transition: each function locks the Student row for the duration of its
transaction and re-checks the precondition against the locked row, so a
second concurrent call always sees the already-updated status and fails
cleanly instead of writing a duplicate event.

`is_active` stays in lockstep with `status` (True only for ACTIVE) purely
so every pre-existing "active students" query elsewhere in the app (Group
rosters, Analytics, the KPI dashboard, ...) keeps working unchanged — a
paused or completed student is exactly as "not currently active" as a
withdrawn one always was.
"""
from __future__ import annotations

import datetime as dt

from django.core.exceptions import ValidationError
from django.db import transaction

from ..models import Group, Student, StudentStatusEvent

_REASON_REQUIRED_TYPES = StudentStatusEvent.REASON_REQUIRED_TYPES


def _validate_reason(event_type: str, reason: str, comment: str) -> None:
    if event_type not in _REASON_REQUIRED_TYPES:
        return
    if not reason:
        raise ValidationError({"reason": "Причина обязательна."})
    if reason == StudentStatusEvent.Reason.OTHER and not comment.strip():
        raise ValidationError({"comment": "Для причины «Другая причина» комментарий обязателен."})


def deactivate_student(
    student: Student,
    *,
    reason: str,
    comment: str = "",
    performed_by=None,
) -> StudentStatusEvent:
    """ACTIVE -> WITHDRAWN. Only ever from ACTIVE — a paused or completed
    student has to go through their own explicit action first, never a
    silent side door via "deactivate"."""
    _validate_reason(StudentStatusEvent.EventType.DEACTIVATED, reason, comment)

    with transaction.atomic():
        locked = Student.objects.select_for_update().get(pk=student.pk)
        if locked.status == Student.Status.WITHDRAWN:
            raise ValidationError("Студент уже деактивирован.")
        if locked.status != Student.Status.ACTIVE:
            raise ValidationError("Деактивировать можно только активного студента.")

        event = StudentStatusEvent(
            student=locked,
            event_type=StudentStatusEvent.EventType.DEACTIVATED,
            reason=reason,
            comment=comment,
            group=locked.group,
            event_date=dt.date.today(),
            performed_by=performed_by,
            previous_status=locked.status,
        )
        event.full_clean()
        event.save()

        locked.status = Student.Status.WITHDRAWN
        locked.is_active = False
        locked.save(update_fields=["status", "is_active", "updated_at"])

    student.status = Student.Status.WITHDRAWN
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
    """WITHDRAWN -> ACTIVE — reversing a full deactivation. Deliberately
    distinct from `continue_student` (which reverses a PAUSE): a student who
    left the academy entirely and one who was only on a temporary pause are
    different real-world situations, so they go through different actions
    and produce different event types, never the same one."""
    if group is None:
        raise ValidationError({"group": "Группа обязательна для повторной активации."})
    if event_date is None:
        raise ValidationError({"event_date": "Дата возвращения обязательна."})

    with transaction.atomic():
        locked = Student.objects.select_for_update().get(pk=student.pk)
        if locked.status != Student.Status.WITHDRAWN:
            raise ValidationError("Повторная активация возможна только для деактивированного студента.")

        event = StudentStatusEvent(
            student=locked,
            event_type=StudentStatusEvent.EventType.REACTIVATED,
            comment=comment,
            group=group,
            event_date=event_date,
            performed_by=performed_by,
            previous_status=locked.status,
        )
        event.full_clean()
        event.save()

        locked.status = Student.Status.ACTIVE
        locked.is_active = True
        locked.group = group
        locked.save(update_fields=["status", "is_active", "group", "updated_at"])

    student.status = Student.Status.ACTIVE
    student.is_active = True
    student.group = group
    return event


def pause_student(
    student: Student,
    *,
    reason: str,
    expected_return_date: dt.date | None = None,
    comment: str = "",
    performed_by=None,
) -> StudentStatusEvent:
    """ACTIVE -> PAUSED. Refused for an already-paused student (no double
    pause) and for a completed one ("нельзя поставить паузу завершённому
    студенту без специального разрешения" — no override mechanism exists
    in this project, so it is refused outright rather than fabricated)."""
    _validate_reason(StudentStatusEvent.EventType.PAUSED, reason, comment)

    with transaction.atomic():
        locked = Student.objects.select_for_update().get(pk=student.pk)
        if locked.status == Student.Status.PAUSED:
            raise ValidationError("Студент уже находится на паузе.")
        if locked.status != Student.Status.ACTIVE:
            raise ValidationError("Приостановить можно только активного студента.")

        event = StudentStatusEvent(
            student=locked,
            event_type=StudentStatusEvent.EventType.PAUSED,
            reason=reason,
            comment=comment,
            group=locked.group,
            event_date=dt.date.today(),
            expected_return_date=expected_return_date,
            performed_by=performed_by,
            previous_status=locked.status,
        )
        event.full_clean()
        event.save()

        locked.status = Student.Status.PAUSED
        locked.is_active = False
        locked.save(update_fields=["status", "is_active", "updated_at"])

    student.status = Student.Status.PAUSED
    student.is_active = False
    return event


def continue_student(
    student: Student,
    *,
    group: Group | None = None,
    event_date: dt.date | None = None,
    comment: str = "",
    performed_by=None,
) -> StudentStatusEvent:
    """PAUSED -> ACTIVE — the one and only "return from pause" action in
    this project (no separate enrollment/course-cycle concept exists to
    "renew" independently of a pause — see academy_monthly_report.py's
    docstring for why the Academy Report's "Продолжили обучение" and
    "Вернулись после паузы" both read this same event log). `group`
    defaults to the student's current group when not given (spec: "Выбор
    группы, если необходимо" — optional, not mandatory like reactivation)."""
    with transaction.atomic():
        locked = Student.objects.select_for_update().get(pk=student.pk)
        if locked.status != Student.Status.PAUSED:
            raise ValidationError("Продолжить обучение можно только для студента на паузе.")

        target_group = group if group is not None else locked.group
        event = StudentStatusEvent(
            student=locked,
            event_type=StudentStatusEvent.EventType.CONTINUED,
            comment=comment,
            group=target_group,
            event_date=event_date or dt.date.today(),
            performed_by=performed_by,
            previous_status=locked.status,
        )
        event.full_clean()
        event.save()

        locked.status = Student.Status.ACTIVE
        locked.is_active = True
        locked.group = target_group
        locked.save(update_fields=["status", "is_active", "group", "updated_at"])

    student.status = Student.Status.ACTIVE
    student.is_active = True
    student.group = target_group
    return event


def complete_student(
    student: Student,
    *,
    comment: str = "",
    performed_by=None,
) -> StudentStatusEvent:
    """ACTIVE or PAUSED -> COMPLETED. Refused for an already-completed
    student (no double completion) and for a withdrawn one (they would need
    to be reactivated first — completing someone who already left would
    misrepresent what actually happened)."""
    with transaction.atomic():
        locked = Student.objects.select_for_update().get(pk=student.pk)
        if locked.status == Student.Status.COMPLETED:
            raise ValidationError("Обучение уже завершено.")
        if locked.status not in (Student.Status.ACTIVE, Student.Status.PAUSED):
            raise ValidationError("Завершить обучение можно только для активного студента или студента на паузе.")

        event = StudentStatusEvent(
            student=locked,
            event_type=StudentStatusEvent.EventType.COMPLETED,
            comment=comment,
            group=locked.group,
            event_date=dt.date.today(),
            performed_by=performed_by,
            previous_status=locked.status,
        )
        event.full_clean()
        event.save()

        locked.status = Student.Status.COMPLETED
        locked.is_active = False
        locked.save(update_fields=["status", "is_active", "updated_at"])

    student.status = Student.Status.COMPLETED
    student.is_active = False
    return event
