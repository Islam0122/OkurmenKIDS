"""Who sees and who changes a student project. Decided here, on the server —
the frontend only hides buttons.

Students build projects on their own and show them to their trainer; the
trainer registers the work in the LMS. So:

* **Trainer** — the only role that *creates* a project, and only for a
  student of a group they teach (``attendance_matrix.access.visible_groups``).
  Sees their own projects (drafts included) and the published projects of
  their groups. Edits and deletes only the projects they registered.
* **Admin** (or superuser) — sees every project and may edit or delete any
  of them (moderation); does not register projects.
* **Team Lead** — reads the published projects of the groups of their
  directions (no direction assigned — the whole academy, as elsewhere).
* **Director / Operations director** — read every published project.

Anyone else gets 403. Students have no LMS account, so there is no student
view here.
"""
from __future__ import annotations

from django.db.models import Q, QuerySet

from apps.academy.models import Student
from apps.attendance_matrix import access as matrix_access
from apps.users.models import User

from .models import StudentProject

READ_ALL_ROLES = (User.Role.DIRECTOR, User.Role.OPERATIONS_DIRECTOR)


def _active(user) -> bool:
    return bool(user is not None and getattr(user, "is_authenticated", False) and user.is_active)


def is_admin(user) -> bool:
    return _active(user) and (user.is_superuser or user.role == User.Role.ADMIN)


def teacher_of(user):
    """The trainer profile of an active trainer account, else None."""
    if not _active(user) or user.role != User.Role.TEACHER:
        return None
    return getattr(user, "teacher_profile", None)


def can_view(user) -> bool:
    if not _active(user):
        return False
    return (is_admin(user) or teacher_of(user) is not None
            or user.role == User.Role.TEAM_LEAD or user.role in READ_ALL_ROLES)


def can_create(user) -> bool:
    return teacher_of(user) is not None


def visible_projects(user) -> QuerySet[StudentProject]:
    qs = StudentProject.objects.all()
    if not can_view(user):
        return qs.none()
    if is_admin(user):
        return qs
    published = Q(status=StudentProject.Status.PUBLISHED)
    if user.role in READ_ALL_ROLES:
        return qs.filter(published)
    groups = matrix_access.visible_groups(user).values("pk")
    if user.role == User.Role.TEAM_LEAD:
        return qs.filter(published, group_id__in=groups)
    # Trainer: everything they registered + the published work of their groups.
    return qs.filter(Q(created_by=user) | (published & Q(group_id__in=groups)))


def can_edit(user, project: StudentProject) -> bool:
    if is_admin(user):
        return True
    return teacher_of(user) is not None and project.created_by_id == user.pk


def selectable_students(user) -> QuerySet[Student]:
    """Students `user` may attach a project to: a trainer — the students of
    their groups; Admin (editing someone's project) — any student."""
    qs = Student.objects.select_related("group")
    if is_admin(user):
        return qs
    if not can_create(user):
        return qs.none()
    return qs.filter(group_id__in=matrix_access.visible_groups(user).values("pk"))
