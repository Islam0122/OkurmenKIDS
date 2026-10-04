"""Who may see Control, and how much of it.

The project's RBAC has three roles (User.Role ADMIN / TEACHER / TEAM_LEAD)
plus Django's own permissions for staff accounts. So:

* Admin role or superuser — every trainer.
* Team Lead role (User.Role.TEAM_LEAD) — every trainer (Control is
  read-only, so the Team Lead's read-only rule holds here by construction).
* A manager: any account granted `MANAGER_PERMISSION` through Django admin
  (the same permission that already gates «Отчёт академии» and «Отчёты»
  in the sidebar) — every trainer. There is no model linking a manager to
  a subset of trainers, so a manager is never scoped narrower than that.
* A trainer (has a Teacher profile) — only their own lessons.
* Anyone else — no access.
"""
from __future__ import annotations

from apps.users.models import Teacher, User
from apps.users.permissions import is_team_lead

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
    if is_team_lead(user):
        return None
    if user.has_perm(MANAGER_PERMISSION):
        return None
    teacher = getattr(user, "teacher_profile", None)
    if teacher is not None:
        return teacher
    raise ControlAccessDenied
