"""Role-based permissions for the academy app.

Academy has no roles of its own — it reuses ``apps.users.models.User.Role``
(ADMIN / TEACHER). Admin has full access; a Teacher may only read or write
data that belongs to their own groups. Object-level scoping here is a second
line of defence — ``get_queryset()`` in each viewset already excludes other
teachers' data, so a Teacher normally gets 404, not 403.
"""
from __future__ import annotations

from rest_framework.permissions import SAFE_METHODS, BasePermission

from apps.users.models import User


def _is_admin(user) -> bool:
    return bool(user and user.is_authenticated and (user.is_superuser or user.role == User.Role.ADMIN))


def _teacher_profile(user):
    return getattr(user, "teacher_profile", None)


class IsAdminOrReadOnly(BasePermission):
    """Any authenticated user may read; only Admin may write.

    Used for reference/scheduling data that only Admin manages through the
    API (Room, Group, Student, Schedule) — teachers still see their own
    slice of it via the viewset's queryset.
    """

    message = "Изменять эти данные может только администратор."

    def has_permission(self, request, view) -> bool:
        user = request.user
        if not (user and user.is_authenticated):
            return False
        if request.method in SAFE_METHODS:
            return True
        return _is_admin(user)


class IsAdminOrOwningTeacher(BasePermission):
    """Admin has full access; a Teacher may write only within their own groups."""

    message = "Вы можете работать только со своими группами."

    def has_permission(self, request, view) -> bool:
        user = request.user
        return bool(user and user.is_authenticated)

    def has_object_permission(self, request, view, obj) -> bool:
        user = request.user
        if _is_admin(user):
            return True
        if request.method in SAFE_METHODS:
            return True

        teacher = _teacher_profile(user)
        group = getattr(obj, "group", None)
        return bool(teacher and group and group.teacher_id == teacher.id)
