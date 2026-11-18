"""Who may run a bulk copy, and over which lessons.

* **Administrator** (ADMIN role or superuser, apps.users.permissions.is_admin_user)
  — any group, any lesson.
* **Staff explicitly given `bulk_copy.run_bulk_copy`** — only within their
  existing rights, reused from the attendance matrix (apps.attendance_matrix
  .access): the source group must be one they can see, and every target
  lesson one they may fully edit (`edit_level == FULL` — a trainer only their
  own lessons, an assistant / team lead per their group capabilities).
* Everyone else — trainers without the permission included — 403. Student &
  Parent Portal accounts never (they are also stopped earlier by
  apps.portal.access.PortalIsolationMiddleware).
"""
from __future__ import annotations

from apps.attendance_matrix import access as matrix_access
from apps.attendance_matrix.models import MatrixSettings
from apps.users.models import User
from apps.users.permissions import is_admin_user

PERMISSION = "bulk_copy.run_bulk_copy"


def _active(user) -> bool:
    return bool(user is not None and getattr(user, "is_authenticated", False) and user.is_active)


def can_use(user) -> bool:
    if not _active(user) or getattr(user, "role", None) in User.PORTAL_ROLES:
        return False
    if is_admin_user(user):
        return True
    return user.has_perm(PERMISSION) and matrix_access.role_of(user) is not None


def is_unrestricted(user) -> bool:
    return is_admin_user(user)


def can_read_group(user, group) -> bool:
    if is_unrestricted(user):
        return True
    return matrix_access.visible_groups(user).filter(pk=group.pk).exists()


class LessonGate:
    """Per-request cache of «may this user write into this lesson»."""

    def __init__(self, user):
        self.user = user
        self.unrestricted = is_unrestricted(user)
        self.settings = None if self.unrestricted else MatrixSettings.load()

    def write_problem(self, lesson) -> str | None:
        if self.unrestricted:
            return None
        level, reason = matrix_access.edit_level(self.user, lesson, self.settings)
        if level != matrix_access.FULL:
            return reason or "Нет прав на изменение этого занятия."
        return None


def actor_role(user) -> str:
    return matrix_access.role_of(user) or ""
