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
from django.db.models import Q
from django.http import HttpResponseForbidden, JsonResponse

ACCOUNTANT_GROUP = "Accountant"

# Только финансовые модели: просмотр всего, добавление/изменение операций.
# Ни одного `delete_*`, журнал аудита — только просмотр.
_VIEW = ("studentpayment", "employeesalaryprofile", "salaryrule", "payrollperiod", "payroll", "payrollline",
         "payrolladjustment", "payrollpayment", "payrollauditlog", "coursepayrollsettings", "coursecycle",
         "cycleaccrual", "coursepriceversion", "cyclelesson", "payoutplan", "payoutplanline", "deductionrule",
         "applieddeduction", "deductionallocation", "expensecategory", "expense", "recurringexpense")
_WRITE = ("studentpayment", "employeesalaryprofile", "salaryrule", "payrollperiod", "payroll", "payrollline",
          "payrolladjustment", "payrollpayment", "coursepayrollsettings", "coursepriceversion", "cycleaccrual",
          "payoutplan", "payoutplanline", "deductionrule", "expensecategory", "expense", "recurringexpense")
ACCOUNTANT_PERMISSIONS = tuple(
    [f"view_{m}" for m in _VIEW] + [f"add_{m}" for m in _WRITE] + [f"change_{m}" for m in _WRITE]
)

# Оплата обучения (apps.billing): бухгалтер — полные полномочия модуля
# (деньги, начисления в рамках правил, чеки, тарифы, настройки). Ни одного
# `delete_*`: ошибки исправляются корректирующими операциями.
_BILLING_VIEW = ("billingplan", "billingplanversion", "studentbillingprofile", "billingtermschange", "lessonpackage",
                 "lessonconsumption", "invoice", "invoiceadjustment", "paymentallocation", "creditledgerentry",
                 "reservation", "billingtask", "billingcontactlog", "billingnotification", "billingevent", "receipt",
                 "billingsettings")
_BILLING_WRITE = ("billingplan", "billingplanversion", "studentbillingprofile", "billingtermschange",
                  "lessonconsumption", "invoice", "invoiceadjustment", "paymentallocation", "creditledgerentry",
                  "reservation", "billingtask", "billingcontactlog", "billingnotification", "receipt", "billingsettings")
BILLING_ACCOUNTANT_PERMISSIONS = tuple(
    [f"view_{m}" for m in _BILLING_VIEW] + [f"add_{m}" for m in _BILLING_WRITE]
    + [f"change_{m}" for m in _BILLING_WRITE]
)

# Директор в оплате обучения — только просмотр (группа `BillingDirector`).
BILLING_DIRECTOR_GROUP = "BillingDirector"
BILLING_DIRECTOR_PERMISSIONS = tuple(f"view_{m}" for m in _BILLING_VIEW)

# Личные задачи, отчёты и уведомления есть у каждого сотрудника (apps.operations):
# чужие записи представления не отдают (404).
PERSONAL_WORK_PREFIXES = (
    "/api/v1/tasks/",
    "/api/v1/work-reports/",
    "/api/v1/notifications/",
)

# Что изолированной роли можно открыть. Всё остальное — 403.
ALLOWED_PREFIXES = (
    "/api/v1/accounting/",
    "/api/v1/auth/login/",
    "/api/v1/auth/refresh/",
    "/api/v1/auth/me/",
    # Личная отметка прихода/ухода бухгалтера (только свои данные; отчёты
    # посещаемости — admin/… — остаются закрыты).
    "/api/v1/staff-attendance/me/",
    # Публичный карьерный сайт — открыт всем, в том числе вошедшим сотрудникам.
    "/api/v1/public/careers/",
    # Свои задачи, отчёты и уведомления (apps.operations; права — в представлениях).
    *PERSONAL_WORK_PREFIXES,
)


# Сотрудники с базовым доступом (User.STAFF_ONLY_ROLES: ДОП, РОП,
# операционный директор, HR, продажи, маркетинг) изолированы тем же
# middleware: вход, учёт прихода и ухода, свои задачи и отчёты и кабинет
# своей роли (у кого он есть: HR, маркетинг, операционный директор). Отчёты посещаемости (admin/…) сами проверяют права
# (apps.staff_attendance.access): без явно выданного права — 403.
STAFF_ONLY_ALLOWED_PREFIXES = (
    "/api/v1/auth/login/",
    "/api/v1/auth/refresh/",
    "/api/v1/auth/me/",
    "/api/v1/staff-attendance/",
    # HR-кабинет: права проверяют apps.users.hr и apps.recruitment (IsHRManager).
    "/api/v1/hr/",
    # Кабинет маркетинга: права проверяет apps.marketing (IsMarketingTeam).
    "/api/v1/marketing/",
    # Публичный карьерный сайт — открыт всем, в том числе вошедшим сотрудникам.
    "/api/v1/public/careers/",
    # Кабинет операционного директора: права проверяет apps.operations (CanOversee).
    "/api/v1/operations/",
    *PERSONAL_WORK_PREFIXES,
)


# Ролям со своим кабинетом (HR-менеджер, маркетинг) дополнительно открыта
# «Моя зарплата»: /accounting/my/ — только собственные начисления и выплаты,
# только чтение (сотрудник — request.user). Остальная бухгалтерия для них
# закрыта правами представлений (403); прочие роли с базовым доступом
# изолированы, как раньше.
OWN_SALARY_PREFIXES = ("/api/v1/accounting/my/",)


def own_salary_roles() -> tuple[str, ...]:
    from apps.users.models import User

    return (User.Role.HR_MANAGER, User.Role.MARKETING)


def is_staff_only(user) -> bool:
    from apps.users.models import User

    return bool(user is not None and getattr(user, "is_authenticated", False)
                and getattr(user, "role", None) in User.STAFF_ONLY_ROLES)


def isolated_roles() -> tuple[str, ...]:
    return tuple(getattr(settings, "ACCOUNTING_ISOLATED_ROLES", ("accountant",)))


def is_isolated(user) -> bool:
    return bool(user is not None and getattr(user, "is_authenticated", False)
                and getattr(user, "role", None) in isolated_roles())


def ensure_accountant_group():
    """Создать/обновить группу `Accountant` с точным набором разрешений."""
    from django.contrib.auth.models import Group, Permission

    group, _ = Group.objects.get_or_create(name=ACCOUNTANT_GROUP)
    perms = Permission.objects.filter(
        Q(content_type__app_label="accounting", codename__in=ACCOUNTANT_PERMISSIONS)
        | Q(content_type__app_label="billing", codename__in=BILLING_ACCOUNTANT_PERMISSIONS)
    )
    group.permissions.set(perms)
    return group


def ensure_billing_director_group():
    """Группа директора: только `view_*` моделей оплаты — ни добавления, ни
    изменения, ни удаления (Django permissions, admin и API согласованы)."""
    from django.contrib.auth.models import Group, Permission

    group, _ = Group.objects.get_or_create(name=BILLING_DIRECTOR_GROUP)
    group.permissions.set(Permission.objects.filter(
        content_type__app_label="billing", codename__in=BILLING_DIRECTOR_PERMISSIONS,
    ))
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
    if user.role == user.Role.DIRECTOR:
        group = Group.objects.filter(name=BILLING_DIRECTOR_GROUP).first() or ensure_billing_director_group()
        user.groups.add(group)
    else:
        user.groups.remove(*user.groups.filter(name=BILLING_DIRECTOR_GROUP))


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
        if path.startswith(static):
            return self.get_response(request)
        accounting_allowed = path.startswith(ALLOWED_PREFIXES)
        staff_allowed = path.startswith(STAFF_ONLY_ALLOWED_PREFIXES)
        if not (accounting_allowed and staff_allowed):
            user = _request_user(request)
            if not accounting_allowed and is_isolated(user):
                message = "Раздел недоступен: бухгалтерия работает только в /accounting/."
                if path.startswith("/api/"):
                    return JsonResponse({"detail": message, "code": "accounting_only"}, status=403)
                return HttpResponseForbidden(message)
            if not staff_allowed and is_staff_only(user) and not (
                    path.startswith(OWN_SALARY_PREFIXES) and user.role in own_salary_roles()):
                message = "Раздел недоступен: ваш личный кабинет находится в разработке."
                if path.startswith("/api/"):
                    return JsonResponse({"detail": message, "code": "staff_only"}, status=403)
                return HttpResponseForbidden(message)
        return self.get_response(request)
