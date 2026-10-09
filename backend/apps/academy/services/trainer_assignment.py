"""Assigning a trainer to a group — the Team Lead's one academic write.

The group ↔ trainer link is the Teaching Program (GroupTeacher: group +
trainer + subject; a group has one per subject it teaches, several trainers
possible). Nothing new is stored here:

* **Replace** a program's trainer → services.program_editing.update_teaching_program,
  the same path the admin uses: the program, its weekly slots and its
  future, not yet started lessons move to the new trainer; conducted and past
  lessons stay with the previous one (their history and KPI). So Control,
  Reports and the KPI engine — all keyed on a lesson's effective trainer —
  follow the change from the next lesson on.
* **Assign** a trainer to a subject that has no program yet → a new
  GroupTeacher, validated by GroupTeacher.clean() (active trainer account,
  subject from the group's course) — the same as POST /programs/.

Every change is written to Django's own admin history (LogEntry) for the
program — who, what, before → after, when — which is also what the group
page shows as «Назначил / Дата назначения». No separate audit model.
"""
from __future__ import annotations

from dataclasses import dataclass

from django.contrib.admin.models import ADDITION, CHANGE, LogEntry
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.db import transaction

from apps.users.models import Subject, Teacher, User

from ..models import Group, GroupTeacher
from .program_editing import update_teaching_program
from .trainer_history import acting_user


def available_trainers():
    """Who can be assigned: active trainers with an active Trainer account
    (the same rule as GroupTeacher.clean())."""
    return (
        Teacher.objects.filter(is_active=True, user__is_active=True, user__role=User.Role.TEACHER)
        .select_related("user")
        .prefetch_related("subjects")
        .order_by("user__first_name", "user__last_name")
    )


def _last_change(program: GroupTeacher) -> LogEntry | None:
    content_type = ContentType.objects.get_for_model(GroupTeacher)
    return (
        LogEntry.objects.filter(content_type=content_type, object_id=str(program.pk))
        .select_related("user")
        .order_by("-action_time")
        .first()
    )


def _user_label(user) -> str:
    if user is None:
        return ""
    role = user.get_role_display() if hasattr(user, "get_role_display") else ""
    name = user.get_full_name() or user.username
    return f"{name} ({role})" if role else name


def group_trainer(group: Group, subject: Subject | None = None) -> Teacher | None:
    """The group's trainer for `subject` (its active program for that
    subject); without a subject match, the group's only active trainer if it
    has exactly one. None when it's ambiguous or unassigned."""
    programs = group.teachers.filter(is_active=True).select_related("teacher__user")
    if subject is not None:
        match = programs.filter(subject=subject).first()
        if match is not None:
            return match.teacher
    teachers = {p.teacher_id: p.teacher for p in programs}
    return next(iter(teachers.values())) if len(teachers) == 1 else None


def program_row(program: GroupTeacher) -> dict:
    entry = _last_change(program)
    return {
        "id": program.pk,
        "subject": {"id": program.subject_id, "name": program.subject.name} if program.subject_id else None,
        "teacher": {"id": program.teacher_id, "name": str(program.teacher)},
        "is_active": program.is_active,
        "assigned_by": _user_label(entry.user) if entry else None,
        "assigned_at": entry.action_time if entry else program.updated_at,
    }


def assignment_overview(group: Group) -> dict:
    programs = group.teachers.select_related("teacher__user", "subject").order_by("-is_active", "subject__name", "id")
    return {
        "group": {"id": group.pk, "name": group.name, "course": group.course.name},
        "programs": [program_row(p) for p in programs],
        "subjects": [{"id": s.pk, "name": s.name} for s in group.course.subjects.filter(is_active=True).order_by("name")],
        "trainers": [
            {"id": t.pk, "name": str(t), "subjects": [s.name for s in t.subjects.all()]}
            for t in available_trainers()
        ],
    }


@dataclass
class AssignmentResult:
    program: GroupTeacher
    previous_teacher: Teacher | None
    created: bool
    lessons_reassigned: int = 0


def _log(user, program: GroupTeacher, flag: int, message: str) -> None:
    LogEntry.objects.log_actions(
        user_id=user.pk, queryset=[program], action_flag=flag, change_message=message, single_object=True,
    )


@transaction.atomic
def assign_trainer(group: Group, *, teacher: Teacher, user, subject: Subject | None = None,
                   program: GroupTeacher | None = None) -> AssignmentResult:
    """Replace `program`'s trainer, or (no `program`) give `subject` of
    `group` to `teacher`. Raises ValidationError (field-keyed). The
    previous trainer's assignment is closed and kept as history
    (services.trainer_history), recorded as changed by `user`."""
    with acting_user(user):
        return _assign_trainer(group, teacher=teacher, user=user, subject=subject, program=program)


def _assign_trainer(group: Group, *, teacher: Teacher, user, subject: Subject | None = None,
                    program: GroupTeacher | None = None) -> AssignmentResult:
    if program is not None:
        if program.group_id != group.pk:
            raise ValidationError({"program": "Эта программа относится к другой группе."})
        previous = program.teacher
        if previous.pk == teacher.pk:
            raise ValidationError({"teacher": "Этот тренер уже назначен."})
        change = update_teaching_program(
            program, teacher=teacher, subject=program.subject, is_active=program.is_active,
            reassign_future_lessons=True,
        )
        program.refresh_from_db()
        subject_name = program.subject.name if program.subject_id else "без предмета"
        _log(user, program, CHANGE, f"Заменил тренера группы «{group.name}» ({subject_name}): {previous} → {teacher}.")
        return AssignmentResult(program, previous, created=False, lessons_reassigned=change.lessons_reassigned)

    if subject is None:
        raise ValidationError({"subject": "Выберите предмет."})
    current = group.teachers.filter(subject=subject, is_active=True).select_related("teacher__user").first()
    if current is not None:
        if current.teacher_id == teacher.pk:
            raise ValidationError({"teacher": "Этот тренер уже назначен."})
        # One active trainer per subject is the normal case: replacing is
        # the same as an explicit replace of that program.
        return _assign_trainer(group, teacher=teacher, user=user, program=current)

    existing = group.teachers.filter(subject=subject, teacher=teacher).first()
    if existing is not None:  # an inactive program of the same trainer → reactivate it
        update_teaching_program(existing, teacher=teacher, subject=subject, is_active=True)
        existing.refresh_from_db()
        _log(user, existing, CHANGE, f"Назначил тренера группы «{group.name}» ({subject.name}): {teacher}.")
        return AssignmentResult(existing, None, created=False)

    created = GroupTeacher(group=group, teacher=teacher, subject=subject)
    created.full_clean()
    created.save()
    _log(user, created, ADDITION, f"Назначил тренера группы «{group.name}» ({subject.name}): {teacher}.")
    return AssignmentResult(created, None, created=True)
