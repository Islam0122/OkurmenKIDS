"""Права доступа к оплате обучения — по `User.Role`, как во всём проекте.

Проверяются трижды: DRF-классами в API, `authorize()` в каждом сервисе и
Django permissions (группы `Accountant` и `BillingDirector`, admin модуля —
только просмотр), поэтому скрытая кнопка, прямой запрос к API или вызов
сервиса не обходят ограничений.

* Бухгалтер (`accountant`) — полные полномочия финансового модуля: платежи,
  распределение авансов, начисления в рамках правил (корректировки,
  аннулирование не начатых), чеки, возвраты, сторно, контакты, тарифы и
  программы, согласование скидок сверх лимита менеджера, настройки.
* Менеджер (роль `assistant`) — регистрирует договор: программа, условия,
  итоговая стоимость (скидка сверх `manager_max_discount_percent` — на
  согласование), бронь (ожидаемая сумма); видит статусы оплаты. Не вносит и
  не меняет платежи, не видит денежных операций, не меняет настройки.
* Директор (`director`) — только просмотр: панель, аналитика, отчёты,
  студенты и статусы, поступления, долги, скидки, журнал. Любая запись —
  403 на уровне API и `forbidden` в сервисе.
* Администратор системы (`admin` / суперпользователь) — как бухгалтер.
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


def _active(user) -> bool:
    return bool(getattr(user, "is_authenticated", False) and user.is_active)


def is_system_admin(user) -> bool:
    return _active(user) and is_admin_user(user)


def is_billing_accountant(user) -> bool:
    """Бухгалтер (с правами группы `Accountant`) или администратор системы."""
    if is_system_admin(user):
        return True
    return _is_accountant(user) and user.has_perm("billing.add_paymentallocation")


def is_billing_admin(user) -> bool:
    """Тарифы, настройки, согласование скидок, корректировки начислений —
    бухгалтер (директор только просматривает)."""
    return is_billing_accountant(user)


def is_director(user) -> bool:
    return _active(user) and getattr(user, "role", None) == User.Role.DIRECTOR and not is_admin_user(user)


def is_manager(user) -> bool:
    return is_assistant(user) or is_system_admin(user)


def can_view(user) -> bool:
    return is_billing_accountant(user) or is_director(user) or is_manager(user)


def can_view_money(user) -> bool:
    """Платежи, распределения, аванс, контакты, отчёты: бухгалтер и директор
    (только чтение), не менеджер."""
    return is_billing_accountant(user) or is_director(user)


def is_read_only(user) -> bool:
    return is_director(user)


ACTIONS = {
    # Регистрация и условия
    "create_profile": lambda u: is_manager(u) or is_billing_admin(u),
    "change_terms": lambda u: is_manager(u) or is_billing_admin(u),
    "approve_terms": is_billing_admin,
    "create_reservation": lambda u: is_manager(u) or is_billing_admin(u),
    "stop_profile": lambda u: is_manager(u) or is_billing_accountant(u),
    # Деньги — только бухгалтер
    "record_payment": is_billing_accountant,
    "allocate": is_billing_accountant,
    "reverse_payment": is_billing_accountant,
    "refund": is_billing_accountant,
    "cancel_reservation": is_billing_accountant,
    "reverse_consumption": is_billing_accountant,
    "contact": is_billing_accountant,
    "assign": is_billing_accountant,
    "issue_receipt": is_billing_accountant,
    # Тарифы, настройки, согласования, корректировки — бухгалтер
    "manage_plans": is_billing_admin,
    "manage_settings": is_billing_admin,
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


def manager_discount_limit():
    from .models import BillingSettings

    return BillingSettings.load().manager_max_discount_percent


def check_course_discount(actor, *, standard_price, final_price) -> bool:
    """Итоговая стоимость курса в пределах полномочий актора? Бухгалтер —
    всегда; менеджер — скидка ≤ лимита из настроек, иначе согласование."""
    from decimal import Decimal

    if is_billing_admin(actor):
        return True
    standard = Decimal(standard_price)
    return standard - Decimal(final_price) <= standard * manager_discount_limit() / 100


def check_manager_discount(actor, *, base_price, custom_price, discount_type, discount_value) -> bool:
    """True — условия в пределах полномочий актора (применяются сразу),
    False — нужно согласование бухгалтера."""
    from decimal import Decimal

    if is_billing_admin(actor):
        return True
    limit = manager_discount_limit()
    from .services.pricing import discount_for

    price = Decimal(custom_price) if custom_price is not None else Decimal(base_price)
    total = Decimal(base_price) - price + discount_for(price, discount_type, discount_value)
    return total <= Decimal(base_price) * limit / 100


class BillingAccess(BasePermission):
    """Чтение — всем ролям оплаты; запись решает сервис (`authorize`)."""

    message = "Доступ к оплате обучения запрещён."

    def has_permission(self, request, view) -> bool:
        if request.method not in SAFE_METHODS and is_read_only(request.user):
            return False  # директор — только просмотр, независимо от эндпоинта
        return can_view(request.user)


class MoneyAccess(BasePermission):
    """Финансовые данные (платежи, аванс, контакты, отчёты): бухгалтер и
    администратор оплаты; менеджеру — 403."""

    message = "Финансовые операции доступны только бухгалтерии."

    def has_permission(self, request, view) -> bool:
        if request.method in SAFE_METHODS:
            return can_view_money(request.user)
        return is_billing_accountant(request.user)


def capabilities(user) -> dict:
    role = ("accountant" if is_billing_accountant(user) else "director" if is_director(user)
            else "manager" if is_manager(user) else None)
    return {
        "role": role,
        "read_only": is_read_only(user),
        "can_view": can_view(user),
        "can_view_money": can_view_money(user),
        "is_manager": is_manager(user),
        "is_accountant": is_billing_accountant(user),
        "is_director": is_director(user),
        "is_billing_admin": is_billing_admin(user),
        "can_record_payments": is_billing_accountant(user),
        "can_register": is_manager(user) or is_billing_accountant(user),
        "can_manage_plans": is_billing_admin(user),
        "can_manage_settings": is_billing_admin(user),
        "can_view_audit": can_view_money(user),
        "max_manager_discount_percent": str(manager_discount_limit()),
    }
