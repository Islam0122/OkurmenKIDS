"""Opening a new group in one step: the group itself, who teaches it and
when (its Teaching Programs with their weekly slots), and its first
students — the Assistant Workspace's «Создать группу» wizard.

Nothing here is new business logic; it only chains the existing pieces in
one transaction, so a problem in any step (a schedule conflict, a full
group, an inactive trainer) leaves nothing half-created:

* the group — `Group.full_clean()` (unique name, end date after start);
* each program — services.group_academic_config.save_program_config, the
  Team Lead's «Учебная конфигурация» save: trainer / subject checks and every
  slot validated by GroupSchedule.clean() (trainer, room and group overlaps);
* students — services.student_enrollment.add_students_to_group, which
  writes a history event per student.

Lessons are *not* generated here: that stays the explicit «Сгенерировать
занятия» step (services.lesson_generator), run right after by the caller
when asked to.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

from django.contrib.admin.models import ADDITION, LogEntry
from django.core.exceptions import ValidationError
from django.db import transaction

from apps.users.models import Subject, Teacher

from ..models import Course, Group, Student
from .group_academic_config import save_program_config
from .student_enrollment import add_students_to_group


@dataclass
class ProgramSpec:
    teacher: Teacher
    subject: Subject | None
    slots: list = field(default_factory=list)


def _prefixed(exc: ValidationError, prefix: str) -> ValidationError:
    """Keep field errors readable when several programs are saved at once."""
    if hasattr(exc, "error_dict"):
        return ValidationError({key: [f"{prefix}: {m}" for m in ValidationError(msgs).messages]
                                for key, msgs in exc.error_dict.items()})
    return ValidationError([f"{prefix}: {m}" for m in exc.messages])


@transaction.atomic
def create_group(
    *,
    name: str,
    course: Course,
    start_date: dt.date,
    end_date: dt.date | None = None,
    max_students: int | None = None,
    description: str = "",
    programs: list[ProgramSpec] = (),
    students: list[Student] = (),
    user=None,
) -> Group:
    group = Group(
        name=name.strip(),
        course=course,
        start_date=start_date,
        end_date=end_date,
        max_students=max_students,
        description=description,
        status=Group.Status.ACTIVE,
    )
    group.full_clean()
    group.save()

    for spec in programs:
        label = f"{spec.subject.name if spec.subject else 'Программа'} ({spec.teacher})"
        try:
            save_program_config(group, user=user, teacher=spec.teacher, subject=spec.subject, slot_items=spec.slots)
        except ValidationError as exc:
            raise _prefixed(exc, label)

    if students:
        add_students_to_group(group, students, event_date=start_date if start_date <= dt.date.today() else None,
                              comment=f"Зачислен при создании группы «{group.name}».", performed_by=user)

    if user is not None and getattr(user, "pk", None):
        LogEntry.objects.log_actions(
            user_id=user.pk, queryset=[group], action_flag=ADDITION,
            change_message=f"Группа создана: курс «{course.name}», программ: {len(programs)}, студентов: {len(students)}.",
            single_object=True,
        )
    return group
