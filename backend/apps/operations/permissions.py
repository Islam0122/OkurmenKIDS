"""Права операционного модуля. Всё проверяется здесь, на сервере; фронтенд
лишь не показывает лишнее.

Кто что видит:

* Надзор (`can_oversee`): Администратор, Директор, Операционный директор —
  все отделы, сотрудники, задачи, отчёты, KPI и проблемы. Зарплаты и
  бухгалтерия сюда не входят: операционный модуль их не читает.
* Руководитель отдела (`departments.led_department`): Team Lead — академия
  (тренеры, ассистенты), РОП / ДОП — продажи. Видит задачи и отчёты своего
  отдела, ставит задачи его сотрудникам, проверяет их отчёты.
* Любой сотрудник: свои задачи (исполнитель, автор, проверяющий, задача
  своего отдела без исполнителя) и свои отчёты. Может поставить задачу себе.

Чужая задача, отчёт, вложение или уведомление — 404 (не 403), чтобы по id
нельзя было узнать о существовании записи (IDOR).
"""
from __future__ import annotations

from django.db.models import Q
from rest_framework.permissions import BasePermission

from apps.users.models import User
from apps.users.permissions import is_admin_user

from .departments import department_of, led_department, roles_of

OVERSIGHT_ROLES = (User.Role.DIRECTOR, User.Role.OPERATIONS_DIRECTOR)


def _active(user) -> bool:
    return bool(user is not None and getattr(user, "is_authenticated", False) and user.is_active)


def is_operations_director(user) -> bool:
    return _active(user) and user.role == User.Role.OPERATIONS_DIRECTOR


def can_oversee(user) -> bool:
    """Весь операционный контур: администратор, директор, операционный директор."""
    return _active(user) and (is_admin_user(user) or user.role in OVERSIGHT_ROLES)


def manageable_roles(user) -> list[str] | None:
    """Кому `user` может ставить задачи: None — любому сотруднику."""
    if can_oversee(user):
        return None
    department = led_department(user)
    return roles_of(department) if department else []


def can_assign_to(user, target) -> bool:
    if target is None or not target.is_active:
        return False
    if target.pk == user.pk:
        return True
    roles = manageable_roles(user)
    return roles is None or target.role in roles


def can_assign_department(user, department: str) -> bool:
    return can_oversee(user) or led_department(user) == department or department_of(user) == department


# --- Задачи ------------------------------------------------------------------

def task_scope(user) -> Q | None:
    """Фильтр задач, которые видит `user`. Q() — все; None — никаких."""
    if not _active(user):
        return None
    if can_oversee(user):
        return Q()
    own = (Q(assignee=user) | Q(created_by=user) | Q(reviewer=user)
           | Q(assignee__isnull=True, department=department_of(user)))
    department = led_department(user)
    if department:
        own |= Q(department=department) | Q(assignee__role__in=roles_of(department))
    return own


def is_task_manager(user, task) -> bool:
    """Может менять условия задачи, переназначать и отменять: автор, надзор
    или руководитель отдела задачи."""
    return bool(can_oversee(user) or task.created_by_id == user.pk or led_department(user) == task.department)


def can_review(user, task) -> bool:
    return bool(task.effective_reviewer_id == user.pk or can_oversee(user) or led_department(user) == task.department)


def is_executor(user, task) -> bool:
    """Исполняет задачу: назначенный сотрудник; задачу отдела без исполнителя —
    любой сотрудник этого отдела."""
    if task.assignee_id is not None:
        return task.assignee_id == user.pk
    return department_of(user) == task.department


# --- Отчёты ------------------------------------------------------------------

def report_scope(user) -> Q | None:
    if not _active(user):
        return None
    if can_oversee(user):
        return Q()
    q = Q(author=user)
    department = led_department(user)
    if department:
        q |= Q(department=department)
    return q


def can_review_report(user, report) -> bool:
    if report.author_id == user.pk:
        return False
    return can_oversee(user) or led_department(user) == report.department


# --- DRF ---------------------------------------------------------------------

class CanOversee(BasePermission):
    message = "Раздел доступен операционному директору, директору и администратору."

    def has_permission(self, request, view) -> bool:
        return can_oversee(request.user)


class IsActiveEmployee(BasePermission):
    message = "Требуется активная учётная запись сотрудника."

    def has_permission(self, request, view) -> bool:
        return _active(request.user)
