"""Who may see Control, and how much of it.

The project's RBAC has two roles (User.Role ADMIN / TEACHER) plus Django's
own permissions for staff accounts — there is no separate Director/Manager
role. So:

* Admin role or superuser — every trainer.
* A manager: any account granted `MANAGER_PERMISSION` through Django admin
  (the same permission that already gates «Отчёт академии» and «Отчёты»
  in the sidebar) — every trainer. There is no model linking a manager to
  a subset of trainers, so a manager is never scoped narrower than that.
* A trainer (has a Teacher profile) — only their own lessons.
* Anyone else — no access.
"""
from __future__ import annotations

from apps.users.models import Teacher, User

MANAGER_PERMISSION = "academy.view_academymonthlyreport"


class ControlAccessDenied(Exception):
    pass


def control_scope(user) -> Teacher | None:
    """None = the whole academy; a Teacher = only that trainer's lessons.
    Raises ControlAccessDenied for an account with neither."""
    if not (user and user.is_authenticated and user.is_active):
        raise ControlAccessDenied
    if user.is_superuser or getattr(user, "role", None) == User.Role.ADMIN:
        return None
    if user.has_perm(MANAGER_PERMISSION):
        return None
    teacher = getattr(user, "teacher_profile", None)
    if teacher is not None:
        return teacher
    raise ControlAccessDenied
