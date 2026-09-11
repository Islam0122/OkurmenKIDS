"""Role-based permissions for the users app.

These permissions rely on ``request.user.role`` (see ``apps.users.models.User``)
rather than Django's group/permission system, since OkurmenKIDS currently has
exactly two roles: ADMIN and TEACHER.
"""
from __future__ import annotations

from rest_framework.permissions import BasePermission

from apps.users.models import User


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
