"""Права «Общей статистики».

* Просмотр — любой вошедший активный сотрудник, независимо от должности.
* Ручная корректировка показателей — администратор, директор, операционный
  директор или сотрудник, которому явно выдано Django-право
  ``performance.change_dailyperformancesnapshot``.
"""
from __future__ import annotations

from rest_framework.permissions import SAFE_METHODS, BasePermission

from apps.users.models import User
from apps.users.permissions import is_admin_user

EDITOR_ROLES = (User.Role.DIRECTOR, User.Role.OPERATIONS_DIRECTOR)


def can_edit_performance(user) -> bool:
    if not getattr(user, "is_authenticated", False) or not user.is_active:
        return False
    if is_admin_user(user) or getattr(user, "role", None) in EDITOR_ROLES:
        return True
    return user.has_perm("performance.change_dailyperformancesnapshot")


class CanViewPerformance(BasePermission):
    message = "Войдите в систему, чтобы увидеть общую статистику."

    def has_permission(self, request, view) -> bool:
        user = request.user
        return bool(getattr(user, "is_authenticated", False) and user.is_active)


class CanEditPerformanceOrReadOnly(CanViewPerformance):
    def has_permission(self, request, view) -> bool:
        if not super().has_permission(request, view):
            return False
        if request.method in SAFE_METHODS:
            return True
        self.message = "Недостаточно прав для корректировки показателей."
        return can_edit_performance(request.user)
