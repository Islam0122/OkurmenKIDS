"""Права доступа бухгалтерии (по `User.Role`, как во всём проекте).

* Бухгалтер — читает всё в бухгалтерии, рассчитывает, вносит платежи
  студентов, выплаты, корректировки, ведёт зарплатные правила. Не
  утверждает начисления (если это не разрешено настройкой
  ACCOUNTING_ACCOUNTANT_CAN_APPROVE), не меняет роли и настройки.
* Директор — читает всё, утверждает / возвращает / переоткрывает
  начисления, решает по корректировкам утверждённых начислений, закрывает
  периоды.
* Администратор — только просмотр (включая журнал аудита): он управляет
  пользователями и техникой, а не деньгами.
* Любой сотрудник — только свои утверждённые начисления (/my/…).
"""
from __future__ import annotations

from django.conf import settings
from rest_framework.permissions import SAFE_METHODS, BasePermission

from apps.users.models import User
from apps.users.permissions import is_admin_user


def _role(user, role) -> bool:
    return bool(getattr(user, "is_authenticated", False) and user.is_active and getattr(user, "role", None) == role)


def is_accountant(user) -> bool:
    return _role(user, User.Role.ACCOUNTANT)


def is_director(user) -> bool:
    return _role(user, User.Role.DIRECTOR)


def can_view_accounting(user) -> bool:
    if is_accountant(user):
        # Права бухгалтера — из Django-группы `Accountant` (apps.accounting.access).
        return user.has_perm("accounting.view_payroll")
    return is_director(user) or is_admin_user(user)


def can_operate(user) -> bool:
    return is_accountant(user) and user.has_perm("accounting.change_payroll")


def can_approve(user) -> bool:
    return is_director(user) or (is_accountant(user) and getattr(settings, "ACCOUNTING_ACCOUNTANT_CAN_APPROVE", False))


class AccountingAccess(BasePermission):
    """Чтение — бухгалтер, директор, администратор; запись — бухгалтер."""

    message = "Доступ к бухгалтерии запрещён."

    def has_permission(self, request, view) -> bool:
        if request.method in SAFE_METHODS:
            return can_view_accounting(request.user)
        return can_operate(request.user)


class CanApprove(BasePermission):
    message = "Утверждать начисления может только директор."

    def has_permission(self, request, view) -> bool:
        return can_approve(request.user)


class CanViewAccounting(BasePermission):
    message = "Доступ к бухгалтерии запрещён."

    def has_permission(self, request, view) -> bool:
        return can_view_accounting(request.user)


def capabilities(user) -> dict:
    return {
        "can_view": can_view_accounting(user),
        "can_operate": can_operate(user),
        "can_approve": can_approve(user),
    }
