"""Найм: учётная запись сотрудника для принятого кандидата.

* Роли из `User.HR_MANAGEABLE_ROLES` (РОП, менеджер по продажам, маркетинг)
  HR оформляет сам — тем же механизмом, что и раздел «Сотрудники»
  (`HREmployeeCreateSerializer`): обычный пользователь без прав
  администратора, уникальные логин и email.
* Для остальных непривилегированных ролей HR создаёт запрос
  (AccountRequest); учётную запись создаёт администратор в Django admin
  (действие «Одобрить»). Обходить ограничения HR нельзя.
* Администратор и директор через найм не назначаются никогда.
* Отклик и анкета после найма остаются; повторно принять кандидата — по этому
  или другому его отклику — нельзя (OneToOne + проверка под блокировкой).
"""
from __future__ import annotations

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from ..models import AccountRequest, Application, HRActivity
from . import activity
from .common import RecruitmentError
from .pipeline import S

User = get_user_model()

PRIVILEGED_ROLES = (User.Role.ADMIN, User.Role.DIRECTOR)


def requestable_roles() -> list[tuple[str, str]]:
    """Роли, которые выдаются только через согласование администратора."""
    return [(value, label) for value, label in User.Role.choices
            if value not in User.HR_MANAGEABLE_ROLES and value not in PRIVILEGED_ROLES]


def _lock(application: Application) -> Application:
    # Только строка отклика: вакансия — nullable FK (LEFT OUTER JOIN), а
    # PostgreSQL не блокирует nullable-сторону внешнего соединения.
    return Application.objects.select_for_update(of=("self",)).select_related("candidate", "vacancy") \
        .get(pk=application.pk)


def check_hireable(application: Application) -> None:
    if application.hired_user_id:
        raise RecruitmentError("Кандидат уже принят: учётная запись сотрудника создана.", "already_hired", status=409)
    if Application.objects.filter(candidate=application.candidate, hired_user__isnull=False) \
            .exclude(pk=application.pk).exists():
        raise RecruitmentError("Кандидат уже принят на работу по другому отклику — вторая учётная запись не нужна.",
                               "already_hired", status=409)
    if application.status != S.OFFER:
        raise RecruitmentError("Принять на работу можно кандидата на этапе «Предложение о работе».", "offer_required")
    if application.account_requests.filter(status=AccountRequest.Status.PENDING).exists():
        raise RecruitmentError("Запрос на учётную запись уже ждёт решения администратора.", "request_pending",
                               status=409)


def _link(application: Application, user, actor, how: str) -> Application:
    old = application.status
    application.hired_user = user
    application.status = S.HIRED
    application.status_changed_at = timezone.now()
    application.save(update_fields=["hired_user", "status", "status_changed_at", "updated_at"])
    activity.log(HRActivity.Kind.EMPLOYEE_CREATED, actor, employee=user, application=application,
                 message=f"Учётная запись «{user.username}» ({user.get_role_display()}) {how}")
    activity.log(HRActivity.Kind.CANDIDATE_STATUS, actor, application=application, employee=user,
                 vacancy=application.vacancy, from_status=old, to_status=S.HIRED,
                 message=f"{S(old).label} → {S.HIRED.label}")
    activity.log(HRActivity.Kind.CANDIDATE_HIRED, actor, application=application, employee=user,
                 vacancy=application.vacancy, message=f"Принят на работу: {user.get_role_display()}")
    return application


@transaction.atomic
def hire(application: Application, actor, create_account) -> Application:
    """Принять на работу: `create_account()` — обычное создание сотрудника HR.
    Строка отклика блокируется, поэтому два одновременных запроса не создадут
    двух сотрудников."""
    application = _lock(application)
    check_hireable(application)
    user = create_account()
    return _link(application, user, actor, "создана при найме")


def _check_account_data(username: str, email: str, exclude_request: int | None = None) -> None:
    errors = {}
    if User.objects.filter(username__iexact=username).exists():
        errors["username"] = "Пользователь с таким логином уже существует."
    if User.objects.filter(email__iexact=email).exists():
        errors["email"] = "Пользователь с таким email уже существует."
    pending = AccountRequest.objects.filter(status=AccountRequest.Status.PENDING)
    if exclude_request:
        pending = pending.exclude(pk=exclude_request)
    if pending.filter(username__iexact=username).exists():
        errors.setdefault("username", "Этот логин уже указан в другом запросе.")
    if pending.filter(email__iexact=email).exists():
        errors.setdefault("email", "Этот email уже указан в другом запросе.")
    if errors:
        raise RecruitmentError("Учётная запись с такими данными уже есть.", "duplicate_account", extra={"errors": errors})


@transaction.atomic
def request_account(application: Application, actor, *, role: str, username: str, email: str, first_name: str,
                    last_name: str = "", comment: str = "") -> AccountRequest:
    application = _lock(application)
    check_hireable(application)
    if role not in dict(requestable_roles()):
        raise RecruitmentError("Эту роль нельзя назначить при найме.", "role_forbidden", status=403)
    _check_account_data(username, email)
    request = AccountRequest.objects.create(
        application=application, role=role, username=username, email=email, first_name=first_name,
        last_name=last_name, comment=comment, requested_by=actor,
    )
    activity.log(HRActivity.Kind.ACCOUNT_REQUESTED, actor, application=application,
                 message=f"Запрошена учётная запись «{username}» ({User.Role(role).label}) — ждёт администратора")
    return request


@transaction.atomic
def approve_request(request: AccountRequest, admin) -> AccountRequest:
    """Администратор создаёт учётную запись по запросу HR. Пароль задаёт
    администратор (Django admin → пользователь → «Изменить пароль»)."""
    request = AccountRequest.objects.select_for_update().get(pk=request.pk)
    if request.status != AccountRequest.Status.PENDING:
        raise RecruitmentError("Запрос уже рассмотрен.", "not_pending")
    if request.role in PRIVILEGED_ROLES or request.role not in dict(User.Role.choices):
        raise RecruitmentError("Эту роль нельзя назначить при найме.", "role_forbidden", status=403)
    application = _lock(request.application)
    if application.hired_user_id or application.status != S.OFFER:
        raise RecruitmentError("Отклик больше не на этапе «Предложение о работе».", "offer_required")
    _check_account_data(request.username, request.email, exclude_request=request.pk)
    user = User(username=request.username, email=request.email, first_name=request.first_name,
                last_name=request.last_name, role=request.role, is_verified=True)
    user.set_unusable_password()
    user.save()
    request.status = AccountRequest.Status.APPROVED
    request.decided_by = admin
    request.decided_at = timezone.now()
    request.save(update_fields=["status", "decided_by", "decided_at"])
    _link(application, user, admin, "создана администратором по запросу HR")
    activity.log(HRActivity.Kind.ACCOUNT_REQUEST_DONE, admin, application=application, employee=user,
                 message=f"Запрос одобрен: «{user.username}» ({user.get_role_display()})")
    return request


@transaction.atomic
def reject_request(request: AccountRequest, admin, comment: str = "") -> AccountRequest:
    request = AccountRequest.objects.select_for_update().get(pk=request.pk)
    if request.status != AccountRequest.Status.PENDING:
        raise RecruitmentError("Запрос уже рассмотрен.", "not_pending")
    request.status = AccountRequest.Status.REJECTED
    request.decided_by = admin
    request.decided_at = timezone.now()
    request.decision_comment = comment[:255]
    request.save(update_fields=["status", "decided_by", "decided_at", "decision_comment"])
    activity.log(HRActivity.Kind.ACCOUNT_REQUEST_DONE, admin, application=request.application,
                 message="Запрос отклонён" + (f": {comment}" if comment else ""))
    return request
