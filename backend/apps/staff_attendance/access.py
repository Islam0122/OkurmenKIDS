"""Кто что видит в учёте прихода и ухода.

Права в проекте задаёт роль (`User.role`, apps.users.permissions); Django
permissions модели AttendanceSession позволяют дополнительно выдать доступ
конкретному человеку (например, HR) без новой роли:

* отметка прихода/ухода и своя история — любой активный сотрудник, чья роль
  отмечена в настройках (по умолчанию — все роли LMS). Только свои данные.
* отчёты — Администратор и Директор (все сотрудники), Team Lead (только
  тренеры — он руководит тренерами), либо право `view_attendance_reports`.
* исправления записей — Администратор или право `adjust_attendance`.
* офисы, QR-коды, настройки, личные расписания — Администратор или право
  `manage_attendance`.
"""
from __future__ import annotations

from django.db.models import Q
from rest_framework.permissions import BasePermission

from apps.users.models import User
from apps.users.permissions import is_admin_user

from .models import AttendanceSettings

PERM_REPORTS = "staff_attendance.view_attendance_reports"
PERM_ADJUST = "staff_attendance.adjust_attendance"
PERM_MANAGE = "staff_attendance.manage_attendance"


def _active(user) -> bool:
    return bool(getattr(user, "is_authenticated", False) and user.is_active)


def can_check_in(user, config: AttendanceSettings | None = None) -> bool:
    if not _active(user):
        return False
    config = config or AttendanceSettings.load()
    return user.role in (config.tracked_roles or [])


def report_scope(user) -> Q | None:
    """Фильтр пользователей, чьи отчёты доступны `user`; None — никаких."""
    if not _active(user):
        return None
    if is_admin_user(user) or user.role == User.Role.DIRECTOR or user.has_perm(PERM_REPORTS):
        return Q()
    if user.role == User.Role.TEAM_LEAD:
        return Q(role=User.Role.TEACHER)
    return None


def can_view_reports(user) -> bool:
    return report_scope(user) is not None


def can_adjust(user) -> bool:
    return _active(user) and (is_admin_user(user) or user.has_perm(PERM_ADJUST))


def can_manage(user) -> bool:
    return _active(user) and (is_admin_user(user) or user.has_perm(PERM_MANAGE))


class CanCheckIn(BasePermission):
    message = "Ваша роль не отмечает приход и уход."

    def has_permission(self, request, view) -> bool:
        return can_check_in(request.user)


class CanViewReports(BasePermission):
    message = "Отчёты посещаемости сотрудников вам недоступны."

    def has_permission(self, request, view) -> bool:
        return can_view_reports(request.user)


class CanAdjust(BasePermission):
    message = "Исправлять записи посещаемости может только уполномоченный администратор."

    def has_permission(self, request, view) -> bool:
        return can_adjust(request.user)


class CanManage(BasePermission):
    message = "Управлять офисами и настройками посещаемости может только администратор."

    def has_permission(self, request, view) -> bool:
        return can_manage(request.user)
