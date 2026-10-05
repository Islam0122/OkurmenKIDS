"""Which group a Student studies in — enrolling a new student into a group,
transferring one to another group, and adding existing students to a group.

The counterpart of services.student_status for `Student.group`: every
change of a student's group made through these functions leaves a
`StudentStatusEvent` (event type TRANSFERRED, `from_group` → `group`) in the
student's one history log, next to their deactivations and returns, so
«PRO-01 → PRO-02» is never lost. The status itself is untouched — a
transfer is not a departure — and a student is never re-created: the same
Student row (with its attendance, homework and scholarship history) simply
points at the new group.

Every write is also recorded in Django's admin history (LogEntry) of the
student, the audit trail the rest of the academy already uses (see
services.group_academic_config).
"""
from __future__ import annotations

import datetime as dt

from django.contrib.admin.models import ADDITION, CHANGE, LogEntry
from django.core.exceptions import ValidationError
from django.db import transaction

from ..models import Group, Student, StudentStatusEvent

# A student can join a group that is running or about to resume — never one
# that is finished or was cancelled.
OPEN_GROUP_STATUSES = (Group.Status.ACTIVE, Group.Status.PAUSED)

# Moving a student between groups is for students who are still studying.
# A withdrawn or completed student comes back through «Активировать»
# (services.student_status.reactivate_student), which picks the group.
TRANSFERABLE_STATUSES = (Student.Status.ACTIVE, Student.Status.PAUSED)


def _log(user, student: Student, flag: int, message: str) -> None:
    if user is None or not getattr(user, "pk", None):
        return
    LogEntry.objects.log_actions(
        user_id=user.pk, queryset=[student], action_flag=flag, change_message=message, single_object=True,
    )


def validate_target_group(group: Group | None, *, adding: int = 1) -> None:
    """`group` can take `adding` more active students."""
    if group is None:
        raise ValidationError({"group": "Выберите группу."})
    if group.status not in OPEN_GROUP_STATUSES:
        raise ValidationError({"group": f"Группа «{group.name}» {group.get_status_display().lower()} — в неё нельзя добавить студента."})
    if group.max_students is not None and group.students_count + adding > group.max_students:
        raise ValidationError({"group": f"В группе «{group.name}» нет мест (максимум {group.max_students})."})


def _today_or(value: dt.date | None) -> dt.date:
    return value or dt.date.today()


@transaction.atomic
def enroll_student(
    *,
    first_name: str,
    last_name: str = "",
    phone: str = "",
    parent_phone: str = "",
    group: Group,
    enrollment_date: dt.date | None = None,
    performed_by=None,
) -> Student:
    """Create a new, active Student studying in `group` from
    `enrollment_date` (today by default — the date scholarship eligibility
    counts from, see Student.enrollment_date)."""
    validate_target_group(group)
    student = Student(
        first_name=first_name.strip(),
        last_name=last_name.strip(),
        phone=phone.strip(),
        parent_phone=parent_phone.strip(),
        group=group,
        enrollment_date=_today_or(enrollment_date),
        status=Student.Status.ACTIVE,
        is_active=True,
    )
    student.full_clean()
    student.save()
    _log(performed_by, student, ADDITION, f"Студент добавлен в группу «{group.name}».")
    return student


def transfer_student(
    student: Student,
    *,
    group: Group,
    event_date: dt.date | None = None,
    comment: str = "",
    performed_by=None,
) -> StudentStatusEvent:
    """Move `student` into `group` (from their current group, or from no
    group at all). The row is locked for the transaction and the
    preconditions re-checked against it, so a double submit can never write
    two transfer events."""
    with transaction.atomic():
        locked = Student.objects.select_for_update().select_related("group").get(pk=student.pk)
        if locked.status not in TRANSFERABLE_STATUSES:
            raise ValidationError(
                f"Студент «{locked}» {locked.get_status_display().lower()} — сначала активируйте его."
            )
        if locked.group_id == getattr(group, "pk", None):
            raise ValidationError({"group": f"Студент «{locked}» уже в группе «{group.name}»."})
        # A paused student keeps their seat logic aside: only active students
        # count towards max_students (Group.students_count).
        validate_target_group(group, adding=1 if locked.status == Student.Status.ACTIVE else 0)

        from_group = locked.group
        event = StudentStatusEvent(
            student=locked,
            event_type=StudentStatusEvent.EventType.TRANSFERRED,
            comment=comment.strip(),
            from_group=from_group,
            group=group,
            event_date=_today_or(event_date),
            performed_by=performed_by,
            previous_status=locked.status,
        )
        event.full_clean()
        event.save()

        locked.group = group
        locked.save(update_fields=["group", "updated_at"])

        route = f"{from_group.name if from_group else 'без группы'} → {group.name}"
        _log(performed_by, locked, CHANGE, f"Перевод: {route}." + (f" {comment.strip()}" if comment.strip() else ""))

    student.group = group
    return event


def add_students_to_group(group: Group, students, *, event_date: dt.date | None = None, comment: str = "",
                          performed_by=None) -> list[StudentStatusEvent]:
    """Bring several existing students into `group` at once — all or
    nothing. Students already in the group are skipped; everyone else goes
    through `transfer_student`, so each one gets their own history event."""
    students = [s for s in students if s.group_id != group.pk]
    with transaction.atomic():
        active = sum(1 for s in students if s.status == Student.Status.ACTIVE)
        validate_target_group(group, adding=active)
        return [
            transfer_student(s, group=group, event_date=event_date, comment=comment, performed_by=performed_by)
            for s in students
        ]
