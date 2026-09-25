"""Scholarship access rules — reusing the project's ADMIN/TEACHER roles.

* Rankings, evaluations, awards, analytics: Admin only (private student
  results). A Teacher gets 403 on every one of them, enforced here on the
  backend, never by a hidden frontend button.
* Generate / recalculate / approve: Admin with the matching model permission
  (a superuser or ADMIN role always has it — see `can_manage`).
* Trainer feedback: a Teacher reads/writes only their own feedback, for
  students they actually taught (see services.feedback).

There are no student accounts in this LMS (users are ADMIN or TEACHER
only), so there is no student-facing access path to guard.
"""
from __future__ import annotations

from rest_framework.permissions import SAFE_METHODS, BasePermission

from apps.users.models import User


def is_admin(user) -> bool:
    return bool(user and user.is_authenticated and (user.is_superuser or user.role == User.Role.ADMIN))


def teacher_profile(user):
    if not (user and user.is_authenticated) or user.role != User.Role.TEACHER:
        return None
    return getattr(user, "teacher_profile", None)


def can_manage(user, action: str) -> bool:
    """`action` is "generate" or "approve"."""
    return is_admin(user) or bool(user and user.is_authenticated and user.has_perm(f"scholarships.{action}_scholarshipperiod"))


class IsScholarshipAdmin(BasePermission):
    message = "Стипендиальные данные доступны только администратору."

    def has_permission(self, request, view) -> bool:
        return is_admin(request.user)


class IsAdminOrTeacherReadOnly(BasePermission):
    """Periods list: Teachers may read (to know which periods need their
    feedback); every write and admin-only action is gated separately."""

    message = "Изменять стипендиальные периоды может только администратор."

    def has_permission(self, request, view) -> bool:
        user = request.user
        if is_admin(user):
            return True
        return request.method in SAFE_METHODS and teacher_profile(user) is not None


class IsAdminOrTeacher(BasePermission):
    message = "Доступно только администратору или тренеру."

    def has_permission(self, request, view) -> bool:
        return is_admin(request.user) or teacher_profile(request.user) is not None
