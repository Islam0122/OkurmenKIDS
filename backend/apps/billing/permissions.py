"""Права доступа к оплате обучения — по `User.Role`, как во всём проекте.

Проверяются дважды: DRF-классами в API и `authorize()` в каждом сервисе,
поэтому скрытая кнопка или прямой вызов сервиса не обходят ограничений.

* Менеджер (роль `assistant`, ведёт студентов и группы) — регистрирует
  платёжный профиль, назначает тариф, бронь и скидку в пределах
  `BILLING_MANAGER_MAX_DISCOUNT_PERCENT`; видит статус оплаты. Не вносит
  платежи, не распределяет деньги, ничего не отменяет.
* Бухгалтер (`accountant`) — начисления, долги, платежи, распределение,
  авансы, возвраты (в пределах `BILLING_ACCOUNTANT_REFUND_LIMIT`), контакты
  с родителями.
* Администратор оплаты (`BILLING_ADMIN_ROLES`, по умолчанию директор и
  администратор) — тарифы, согласование скидок сверх полномочий
  менеджера, корректировки и аннулирование начислений, отчёты и аудит.
* Системные операции (`actor=None`: списание уроков, начисления, просрочки
  из сигналов и Celery) разрешены только для действий из SYSTEM_ACTIONS.
"""
from __future__ import annotations

from django.conf import settings
from rest_framework.permissions import SAFE_METHODS, BasePermission

from apps.accounting.permissions import is_accountant as _is_accountant
from apps.users.models import User
from apps.users.permissions import is_admin_user, is_assistant

from .services import BillingError


class BillingPermissionError(BillingError):
    def __init__(self, message="Недостаточно прав для этой операции."):
        super().__init__(message, code="forbidden")


def admin_roles() -> tuple[str, ...]:
    return tuple(getattr(settings, "BILLING_ADMIN_ROLES", (User.Role.DIRECTOR, User.Role.ADMIN)))


def is_billing_accountant(user) -> bool:
    return _is_accountant(user) and user.has_perm("billing.add_paymentallocation")


def is_billing_admin(user) -> bool:
    if not getattr(user, "is_authenticated", False) or not user.is_active:
        return False
    if getattr(user, "role", None) in admin_roles():
        return True
    return User.Role.ADMIN in admin_roles() and is_admin_user(user)


def is_manager(user) -> bool:
    return is_assistant(user) or is_admin_user(user)


def can_view(user) -> bool:
    return is_billing_accountant(user) or is_billing_admin(user) or is_manager(user)


def can_view_money(user) -> bool:
    """Платежи, распределения, аванс, контакты, отчёты — не менеджеру."""
    return is_billing_accountant(user) or is_billing_admin(user)


ACTIONS = {
    # Регистрация и условия
    "create_profile": lambda u: is_manager(u) or is_billing_admin(u),
    "change_terms": lambda u: is_manager(u) or is_billing_admin(u),
    "approve_terms": is_billing_admin,
    "create_reservation": lambda u: is_manager(u) or is_billing_admin(u),
    "stop_profile": lambda u: is_manager(u) or is_billing_admin(u) or is_billing_accountant(u),
    # Деньги — только бухгалтер
    "record_payment": is_billing_accountant,
    "allocate": is_billing_accountant,
    "reverse_payment": is_billing_accountant,
    "refund": is_billing_accountant,
    "cancel_reservation": is_billing_accountant,
    "reverse_consumption": is_billing_accountant,
    "contact": is_billing_accountant,
    "assign": lambda u: is_billing_accountant(u) or is_billing_admin(u),
    # Администратор оплаты
    "manage_plans": is_billing_admin,
    "adjust_invoice": is_billing_admin,
    "void_invoice": is_billing_admin,
    "view_reports": can_view_money,
}

# Что могут выполнять сигналы и фоновые задачи (без пользователя).
SYSTEM_ACTIONS = {"consume", "create_invoice", "stop_profile", "allocate", "overdue"}


def authorize(actor, action: str) -> None:
    if actor is None:
        if action in SYSTEM_ACTIONS:
            return
        raise BillingPermissionError("Операция требует пользователя.")
    check = ACTIONS.get(action)
    if check is None or not check(actor):
        raise BillingPermissionError()


def check_manager_discount(actor, *, base_price, custom_price, discount_type, discount_value) -> bool:
    """True — условия в пределах полномочий актора (применяются сразу),
    False — нужно согласование администратора оплаты."""
    from decimal import Decimal

    if is_billing_admin(actor):
        return True
    limit = Decimal(str(getattr(settings, "BILLING_MANAGER_MAX_DISCOUNT_PERCENT", 10)))
    from .services.pricing import discount_for

    price = Decimal(custom_price) if custom_price is not None else Decimal(base_price)
    total = Decimal(base_price) - price + discount_for(price, discount_type, discount_value)
    return total <= Decimal(base_price) * limit / 100


class BillingAccess(BasePermission):
    """Чтение — всем ролям оплаты; запись решает сервис (`authorize`)."""

    message = "Доступ к оплате обучения запрещён."

    def has_permission(self, request, view) -> bool:
        return can_view(request.user)


class MoneyAccess(BasePermission):
    """Финансовые данные (платежи, аванс, контакты, отчёты): бухгалтер и
    администратор оплаты; менеджеру — 403."""

    message = "Финансовые операции доступны только бухгалтерии."

    def has_permission(self, request, view) -> bool:
        if request.method in SAFE_METHODS:
            return can_view_money(request.user)
        return is_billing_accountant(request.user) or is_billing_admin(request.user)


def capabilities(user) -> dict:
    return {
        "can_view": can_view(user),
        "can_view_money": can_view_money(user),
        "is_manager": is_manager(user),
        "is_accountant": is_billing_accountant(user),
        "is_billing_admin": is_billing_admin(user),
        "can_record_payments": is_billing_accountant(user),
        "can_manage_plans": is_billing_admin(user),
        "max_manager_discount_percent": str(getattr(settings, "BILLING_MANAGER_MAX_DISCOUNT_PERCENT", 10)),
    }
