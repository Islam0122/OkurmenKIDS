"""Role-based permissions for the users app.

These permissions rely on ``request.user.role`` (see ``apps.users.models.User``)
rather than Django's group/permission system. Roles: ADMIN, TEACHER and
TEAM_LEAD.

TEAM_LEAD (руководитель тренеров) sees the whole academy — every trainer,
group, student, lesson, KPI and report — but only *reads*: every write stays
with ADMIN (or with the owning TEACHER, for their own lessons). Views reuse
``can_view_academy`` for read scoping and keep ``is_admin_user`` for writes,
so a Team Lead can never reach a write path through the academy-wide scope.
User management, roles, permissions and Django admin stay ADMIN-only.
"""
from __future__ import annotations

from rest_framework.permissions import SAFE_METHODS, BasePermission

from apps.users.models import User


def is_admin_user(user) -> bool:
    """Admin role or superuser. Safe for AnonymousUser."""
    if not getattr(user, "is_authenticated", False):
        return False
    return bool(user.is_superuser or getattr(user, "role", None) == User.Role.ADMIN)


def is_team_lead(user) -> bool:
    """An active Team Lead account. Safe for AnonymousUser."""
    if not getattr(user, "is_authenticated", False):
        return False
    return bool(user.is_active and getattr(user, "role", None) == User.Role.TEAM_LEAD)


def can_view_academy(user) -> bool:
    """May *read* academy-wide data (every trainer/group/student): Admin or
    Team Lead. Never use this to gate a write — use ``is_admin_user``."""
    return is_admin_user(user) or is_team_lead(user)


class IsAdmin(BasePermission):
    """Allows access only to authenticated users with the ADMIN role."""

    message = "Доступ разрешён только администратору."

    def has_permission(self, request, view) -> bool:
        user = request.user
        return bool(
            user
            and user.is_authenticated
            and (user.is_superuser or user.role == User.Role.ADMIN)
        )


class IsTeacher(BasePermission):
    """Allows access only to authenticated users with the TEACHER role."""

    message = "Доступ разрешён только тренеру."

    def has_permission(self, request, view) -> bool:
        user = request.user
        return bool(
            user
            and user.is_authenticated
            and user.role == User.Role.TEACHER
        )


class IsVerifiedTeacher(BasePermission):
    """Allows access only to teachers whose account is confirmed by Admin.

    Mirrors the login restrictions in ``LoginSerializer`` so the same rules
    apply consistently to any endpoint scoped to verified teachers only.
    """

    message = "Аккаунт тренера ещё не подтверждён."

    def has_permission(self, request, view) -> bool:
        user = request.user
        return bool(
            user
            and user.is_authenticated
            and user.is_active
            and user.role == User.Role.TEACHER
            and user.is_verified
        )


class IsTeamLead(BasePermission):
    """Allows access only to authenticated, active Team Lead accounts."""

    message = "Доступ разрешён только руководителю тренеров (Team Lead)."

    def has_permission(self, request, view) -> bool:
        return is_team_lead(request.user)


class IsAdminOrTeamLeadReadOnly(BasePermission):
    """Admin: any method. Team Lead: safe (read-only) methods only.
    Everyone else: denied."""

    message = "Доступ разрешён администратору; руководителю тренеров — только просмотр."

    def has_permission(self, request, view) -> bool:
        user = request.user
        if is_admin_user(user):
            return True
        return request.method in SAFE_METHODS and is_team_lead(user)


class TeamLeadReadOnly(BasePermission):
    """Combine with a view's own permissions: whatever they allow, a Team
    Lead is limited to safe methods. No effect for other roles."""

    message = "Руководитель тренеров может только просматривать данные."

    def has_permission(self, request, view) -> bool:
        if request.method in SAFE_METHODS:
            return True
        return not is_team_lead(request.user)


class CanManageGroupAcademicConfig(BasePermission):
    """manage_group_academic_config — the Team Lead's academic writes on a
    group, and only those: its trainer(s), subject(s), weekly schedule slots
    (day, time, room) and generating its lessons from that schedule
    (GroupViewSet.academic_config / assign_trainer / generate_lessons).
    Admin may too. Not a «change Group / Trainer / Subject / Room / Student /
    Test» right: deleting or editing those stays Admin-only."""

    message = "Учебную конфигурацию группы может менять только руководитель тренеров или администратор."

    def has_permission(self, request, view) -> bool:
        return is_admin_user(request.user) or is_team_lead(request.user)


# The trainer assignment action is part of the same right.
CanAssignTrainerToGroup = CanManageGroupAcademicConfig
