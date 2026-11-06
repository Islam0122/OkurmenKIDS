"""Who sees which group in the attendance matrix, and who may change a cell.

Everything is decided here, on the server — the frontend only hides buttons.

* **Admin** (or superuser) — every group, edits everything.
* **Trainer** — the groups they teach (``Group.objects.for_teacher``); in a
  group the columns are only the lessons they give themselves (a colleague's
  program in the same group stays private, see ``LessonQuerySet.for_teacher``)
  and they edit exactly those.
* **Assistant** — only the groups they are assigned to (``GroupAssistant``).
  ``can_edit`` on the assignment lets them mark attendance/homework;
  otherwise they may only add comments. Never another group.
* **Team Lead** — the groups of their directions (``TeamLeadDirection``; no
  direction assigned — the whole academy, as before). Read-only unless
  ``MatrixSettings.team_lead_can_edit``.
* **Operations director** — the whole academy, read-only unless
  ``MatrixSettings.operations_director_can_edit``.

Anyone else gets 403.
"""
from __future__ import annotations

from django.db.models import Q, QuerySet

from apps.academy.models import Group, Lesson
from apps.academy.services import lesson_lifecycle
from apps.users.models import User

from .models import GroupAssistant, MatrixSettings, TeamLeadDirection

ADMIN = "admin"
TEACHER = "teacher"
ASSISTANT = "assistant"
TEAM_LEAD = "team_lead"
OPERATIONS_DIRECTOR = "operations_director"


def role_of(user) -> str | None:
    """The matrix role of `user`, or None when the matrix is closed to them."""
    if not (user is not None and getattr(user, "is_authenticated", False) and user.is_active):
        return None
    if user.is_superuser or user.role == User.Role.ADMIN:
        return ADMIN
    if user.role == User.Role.TEACHER:
        return TEACHER if getattr(user, "teacher_profile", None) is not None else None
    if user.role == User.Role.ASSISTANT:
        return ASSISTANT
    if user.role == User.Role.TEAM_LEAD:
        return TEAM_LEAD
    if user.role == User.Role.OPERATIONS_DIRECTOR:
        return OPERATIONS_DIRECTOR
    return None


def direction_q(subject_ids, prefix: str = "") -> Q:
    """Groups that belong to any of `subject_ids`: by course, by a subject
    program or by a subject start date."""
    return (
        Q(**{f"{prefix}course__subjects__in": subject_ids})
        | Q(**{f"{prefix}teachers__subject__in": subject_ids})
        | Q(**{f"{prefix}subject_starts__subject__in": subject_ids})
    )


def lead_subject_ids(user) -> list[int]:
    return list(TeamLeadDirection.objects.filter(team_lead=user).values_list("subject_id", flat=True))


def visible_groups(user) -> QuerySet[Group]:
    role = role_of(user)
    qs = Group.objects.all()
    if role in (ADMIN, OPERATIONS_DIRECTOR):
        return qs
    if role == TEAM_LEAD:
        subjects = lead_subject_ids(user)
        if not subjects:
            return qs
        return qs.filter(pk__in=Group.objects.filter(direction_q(subjects)).values("pk"))
    if role == TEACHER:
        return qs.filter(pk__in=Group.objects.for_teacher(user.teacher_profile).values("pk"))
    if role == ASSISTANT:
        return qs.filter(assistant_assignments__assistant=user).distinct()
    return qs.none()


def can_view_group(user, group: Group) -> bool:
    return visible_groups(user).filter(pk=group.pk).exists()


def scoped_lessons(user, group_ids) -> QuerySet[Lesson]:
    """The lessons of `group_ids` that `user` may see as matrix columns."""
    qs = Lesson.objects.filter(group_id__in=group_ids)
    if role_of(user) == TEACHER:
        qs = qs.filter(pk__in=Lesson.objects.for_teacher(user.teacher_profile).values("pk"))
    return qs


def _assistant_assignment(user, group_id) -> GroupAssistant | None:
    return GroupAssistant.objects.filter(assistant=user, group_id=group_id).first()


def group_capabilities(user, group: Group, settings: MatrixSettings | None = None) -> dict:
    """What the UI may offer for `group` — the same rules `edit_level`
    enforces for each lesson."""
    role = role_of(user)
    settings = settings or MatrixSettings.load()
    can_edit = can_comment = False
    if role == ADMIN or role == TEACHER:
        can_edit = can_comment = True
    elif role == ASSISTANT:
        assignment = _assistant_assignment(user, group.pk)
        can_comment = assignment is not None
        can_edit = bool(assignment and assignment.can_edit)
    elif role == TEAM_LEAD:
        can_edit = can_comment = settings.team_lead_can_edit
    elif role == OPERATIONS_DIRECTOR:
        can_edit = can_comment = settings.operations_director_can_edit
    return {
        "role": role,
        "can_edit": can_edit,
        "can_comment": can_comment,
        "can_view_history": role is not None,
        "can_export": role is not None,
    }


FULL = "full"
COMMENT = "comment"
NONE = "none"


def edit_level(user, lesson: Lesson, settings: MatrixSettings | None = None) -> tuple[str, str]:
    """(level, reason) for changing a cell of `lesson`: FULL — attendance,
    reason, comment and homework; COMMENT — the comment only; NONE."""
    role = role_of(user)
    if role is None:
        return NONE, "Нет доступа к посещаемости."
    if role != ADMIN and lesson_lifecycle.attendance_editing_locked(lesson):
        return NONE, "Занятие отменено — посещаемость нельзя изменять."
    if role == ADMIN:
        return FULL, ""
    if role == TEACHER:
        owner = lesson.effective_teacher
        if owner is not None and owner.pk == user.teacher_profile.pk:
            return FULL, ""
        return NONE, "Вы можете отмечать только свои занятия."
    caps = group_capabilities(user, lesson.group, settings)
    if role == ASSISTANT and not caps["can_comment"]:
        return NONE, "Вы не назначены в эту группу."
    if caps["can_edit"]:
        return FULL, ""
    if caps["can_comment"]:
        return COMMENT, ""
    return NONE, "Доступен только просмотр."
