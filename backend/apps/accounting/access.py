"""Бухгалтерия — отдельная зона доступа внутри проекта.

Бухгалтер не пользователь LMS: ему не нужны ни студенты, ни группы, ни
занятия, ни Django admin. Поэтому:

* `AccountingIsolationMiddleware` на сервере пропускает изолированную роль
  (по умолчанию — только `accountant`, настройка ACCOUNTING_ISOLATED_ROLES)
  лишь к API бухгалтерии и к входу в систему; любой другой URL — 403, как бы
  к нему ни пришли (меню, прямая ссылка, API-запрос, подставленный id).
  Проверка не зависит от `permission_classes` отдельных представлений LMS,
  поэтому новый эндпоинт LMS тоже закрыт для бухгалтера автоматически.
* Права выдаются только через Django-группу `Accountant` с разрешениями на
  финансовые модели (без удаления и без изменения журнала аудита).
  Принадлежность к группе следует из роли: при сохранении пользователя
  бухгалтер получает ровно эту группу, а личные разрешения снимаются.
"""
from __future__ import annotations

from django.conf import settings
from django.http import HttpResponseForbidden, JsonResponse

ACCOUNTANT_GROUP = "Accountant"

# Только финансовые модели: просмотр всего, добавление/изменение операций.
# Ни одного `delete_*`, журнал аудита — только просмотр.
_VIEW = ("studentpayment", "employeesalaryprofile", "salaryrule", "payrollperiod", "payroll", "payrollline",
         "payrolladjustment", "payrollpayment", "payrollauditlog")
_WRITE = ("studentpayment", "employeesalaryprofile", "salaryrule", "payrollperiod", "payroll", "payrollline",
          "payrolladjustment", "payrollpayment")
ACCOUNTANT_PERMISSIONS = tuple(
    [f"view_{m}" for m in _VIEW] + [f"add_{m}" for m in _WRITE] + [f"change_{m}" for m in _WRITE]
)

# Что изолированной роли можно открыть. Всё остальное — 403.
ALLOWED_PREFIXES = (
    "/api/v1/accounting/",
    "/api/v1/auth/login/",
    "/api/v1/auth/refresh/",
    "/api/v1/auth/me/",
)


def isolated_roles() -> tuple[str, ...]:
    return tuple(getattr(settings, "ACCOUNTING_ISOLATED_ROLES", ("accountant",)))


def is_isolated(user) -> bool:
    return bool(user is not None and getattr(user, "is_authenticated", False)
                and getattr(user, "role", None) in isolated_roles())


def ensure_accountant_group():
    """Создать/обновить группу `Accountant` с точным набором разрешений."""
    from django.contrib.auth.models import Group, Permission

    group, _ = Group.objects.get_or_create(name=ACCOUNTANT_GROUP)
    perms = Permission.objects.filter(content_type__app_label="accounting", codename__in=ACCOUNTANT_PERMISSIONS)
    group.permissions.set(perms)
    return group


def sync_accountant_access(user) -> None:
    """Права бухгалтера — только группа `Accountant`; у остальных её нет."""
    from django.contrib.auth.models import Group

    if user.pk is None:
        return
    if user.role == user.Role.ACCOUNTANT:
        group = Group.objects.filter(name=ACCOUNTANT_GROUP).first() or ensure_accountant_group()
        if set(user.groups.values_list("pk", flat=True)) != {group.pk}:
            user.groups.set([group])
        if user.user_permissions.exists():
            user.user_permissions.clear()
    else:
        user.groups.remove(*user.groups.filter(name=ACCOUNTANT_GROUP))


def _request_user(request):
    """Пользователь запроса: по сессии или по JWT (DRF аутентифицирует JWT
    только внутри представления, поэтому здесь токен разбирается заранее)."""
    user = getattr(request, "user", None)
    if user is not None and user.is_authenticated:
        return user
    if not request.headers.get("Authorization"):
        return None
    from rest_framework_simplejwt.authentication import JWTAuthentication

    try:
        result = JWTAuthentication().authenticate(request)
    except Exception:  # noqa: BLE001 — неверный токен отклонит само представление
        return None
    return result[0] if result else None


class AccountingIsolationMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path
        static = "/" + settings.STATIC_URL.lstrip("/")
        if not path.startswith(ALLOWED_PREFIXES) and not path.startswith(static):
            user = _request_user(request)
            if is_isolated(user):
                message = "Раздел недоступен: бухгалтерия работает только в /accounting/."
                if path.startswith("/api/"):
                    return JsonResponse({"detail": message, "code": "accounting_only"}, status=403)
                return HttpResponseForbidden(message)
        return self.get_response(request)
