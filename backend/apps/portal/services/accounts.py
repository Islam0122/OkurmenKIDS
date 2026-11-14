"""Provisioning and management of Student & Parent Portal accounts.

The only place that creates a STUDENT_PARENT User, sets or resets its
password, renames its login or switches it on / off. Every write:

* runs in one transaction (account + link + audit, or nothing);
* is audited in Django's LogEntry — on the Student (so it shows up in the
  student's history in the Assistant Workspace) and on the User — with who
  did it and what changed. Never the password itself;
* re-validates its target (an existing link, a free login).

Temporary passwords come from `secrets` (CSPRNG), are hashed by the
project's own hasher via `User.set_password`, and are returned to the
caller only as a plain value in memory — the view hands it to the Assistant
once and nothing persists it.
"""
from __future__ import annotations

import dataclasses
import re
import secrets
import unicodedata

from django.contrib.admin.models import ADDITION, CHANGE, LogEntry
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.academy.models import Student
from apps.users.models import User

from ..models import PortalAccount, StudentLink

# Portal accounts have no real e-mail; User.email is unique and required,
# so each gets an address under the reserved `.invalid` TLD (RFC 2606) —
# guaranteed never to be delivered anywhere.
EMAIL_DOMAIN = "portal.okurmenkids.invalid"

LOGIN_RE = re.compile(r"^[a-z0-9](?:[a-z0-9._-]{1,38}[a-z0-9])?$")
LOGIN_MAX = 40

# No look-alikes (0/O, 1/l/I) — the password is read off a screen and typed
# in by a child or a parent.
_LOWER = "abcdefghjkmnpqrstuvwxyz"
_UPPER = "ABCDEFGHJKLMNPQRSTUVWXYZ"
_DIGITS = "23456789"
_ALPHABET = _LOWER + _UPPER + _DIGITS

_TRANSLIT = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e", "ж": "zh", "з": "z", "и": "i",
    "й": "i", "к": "k", "л": "l", "м": "m", "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t",
    "у": "u", "ф": "f", "х": "kh", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "shch", "ъ": "", "ы": "y", "ь": "",
    "э": "e", "ю": "yu", "я": "ya",
    # Кыргызские буквы.
    "ң": "ng", "ө": "o", "ү": "u",
}


@dataclasses.dataclass(frozen=True)
class IssuedCredentials:
    """What the Assistant sees exactly once. Never serialized anywhere else."""

    account: PortalAccount
    login: str
    password: str | None  # None — the student was linked to an existing family account


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def normalize_phone(value: str) -> str:
    return re.sub(r"\D", "", value or "")


def transliterate(value: str) -> str:
    out = []
    for char in (value or "").lower():
        if char in _TRANSLIT:
            out.append(_TRANSLIT[char])
            continue
        ascii_char = unicodedata.normalize("NFKD", char).encode("ascii", "ignore").decode()
        out.append(ascii_char if ascii_char.isalnum() else ("." if char in " -_.'" else ""))
    return re.sub(r"\.+", ".", "".join(out)).strip(".")


def _login_taken(login: str, exclude_pk: int | None = None) -> bool:
    qs = User.objects.filter(username__iexact=login)
    if exclude_pk is not None:
        qs = qs.exclude(pk=exclude_pk)
    return qs.exists() or User.objects.filter(email__iexact=_email(login)).exclude(pk=exclude_pk).exists()


def suggest_login(first_name: str, last_name: str) -> str:
    """`имя.фамилия` in Latin letters, lower case; a number is appended when
    the login is taken (aibek.asanov → aibek.asanov2 → …)."""
    first, last = transliterate(first_name), transliterate(last_name)
    base = ".".join(part for part in (first, last) if part)[:LOGIN_MAX - 4].strip(".") or "student"
    if len(base) < 3:
        base = f"student.{base}"
    candidate, number = base, 1
    while _login_taken(candidate):
        number += 1
        candidate = f"{base}{number}"
    return candidate


def generate_password(user: User | None = None) -> str:
    """12 random characters as three groups of four (e.g. `Hk7m-pQ3x-9tRw`):
    ~68 bits from the OS CSPRNG, with a lower, an upper letter and a digit,
    accepted by the project's AUTH_PASSWORD_VALIDATORS."""
    while True:
        chars = [secrets.choice(_ALPHABET) for _ in range(12)]
        if not (set(chars) & set(_LOWER) and set(chars) & set(_UPPER) and set(chars) & set(_DIGITS)):
            continue
        password = "-".join("".join(chars[i:i + 4]) for i in (0, 4, 8))
        try:
            validate_password(password, user)
        except ValidationError:
            continue
        return password


def _email(login: str) -> str:
    return f"{login}@{EMAIL_DOMAIN}"


def validate_login(login: str, *, exclude_pk: int | None = None) -> str:
    login = (login or "").strip().lower()
    if not LOGIN_RE.match(login):
        raise ValidationError({"login": "Логин: 3–40 символов — латинские буквы, цифры, точка, дефис "
                                        "или подчёркивание; начинается и заканчивается буквой или цифрой."})
    if _login_taken(login, exclude_pk=exclude_pk):
        raise ValidationError({"login": "Этот логин уже занят."})
    return login


def _log(actor, obj, flag: int, message: str) -> None:
    if actor is None or not getattr(actor, "pk", None):
        return
    LogEntry.objects.log_actions(
        user_id=actor.pk, queryset=[obj], action_flag=flag, change_message=message, single_object=True,
    )


def _audit(actor, account: PortalAccount, students, message: str, flag: int = CHANGE) -> None:
    _log(actor, account.user, flag, f"Кабинет ученика: {message}")
    for student in students:
        _log(actor, student, CHANGE, f"Кабинет ученика: {message}")


def account_of(student: Student) -> PortalAccount | None:
    link = StudentLink.objects.filter(student=student).select_related("account__user").order_by("pk").first()
    return link.account if link else None


def family_accounts(parent_phone: str, *, exclude_student: Student | None = None) -> list[PortalAccount]:
    """Existing accounts of the family with this parent phone — where a
    brother's or sister's account can be reused instead of a new one."""
    digits = normalize_phone(parent_phone)
    if len(digits) < 6:
        return []
    qs = PortalAccount.objects.filter(parent_phone=digits).select_related("user").prefetch_related("students")
    accounts = list(qs.order_by("created_at"))
    if exclude_student is not None:
        accounts = [a for a in accounts if exclude_student not in a.students.all()]
    return accounts


# ---------------------------------------------------------------------------
# Writes
# ---------------------------------------------------------------------------

def provision_account(student: Student, *, performed_by, login: str | None = None) -> IssuedCredentials:
    """A new STUDENT_PARENT account linked to `student`, with a temporary
    password that must be changed on first sign-in."""
    with transaction.atomic():
        student = Student.objects.select_for_update().get(pk=student.pk)
        if StudentLink.objects.filter(student=student).exists():
            raise ValidationError({"detail": "У этого студента уже есть аккаунт кабинета."})
        login = validate_login(login) if login else suggest_login(student.first_name, student.last_name)
        user = User(
            username=login, email=_email(login), first_name=student.first_name[:100],
            last_name=student.last_name[:100], role=User.Role.STUDENT_PARENT, is_verified=True, is_active=True,
        )
        password = generate_password(user)
        user.set_password(password)
        try:
            with transaction.atomic():
                user.save()
        except IntegrityError:
            raise ValidationError({"login": "Этот логин уже занят."})
        account = PortalAccount.objects.create(
            user=user, parent_phone=normalize_phone(student.parent_phone), must_change_password=True,
            credentials_issued_at=timezone.now(), created_by=performed_by,
        )
        StudentLink.objects.create(account=account, student=student, created_by=performed_by)
        _log(performed_by, user, ADDITION, f"Кабинет ученика: аккаунт «{login}» создан для студента «{student}».")
        _log(performed_by, student, CHANGE, f"Кабинет ученика: создан аккаунт «{login}», выданы временные данные для входа.")
    return IssuedCredentials(account=account, login=login, password=password)


def link_student(account: PortalAccount, student: Student, *, performed_by) -> PortalAccount:
    """Attach one more child to a family account (no new credentials)."""
    with transaction.atomic():
        account = PortalAccount.objects.select_for_update().select_related("user").get(pk=account.pk)
        if StudentLink.objects.filter(student=student).exists():
            raise ValidationError({"detail": "У этого студента уже есть аккаунт кабинета."})
        StudentLink.objects.create(account=account, student=student, created_by=performed_by)
        if not account.parent_phone and student.parent_phone:
            account.parent_phone = normalize_phone(student.parent_phone)
            account.save(update_fields=["parent_phone", "updated_at"])
        _audit(performed_by, account, [student], f"студент «{student}» привязан к аккаунту «{account.user.username}».")
    return account


def unlink_student(account: PortalAccount, student: Student, *, performed_by) -> None:
    """Detach a child. The last child cannot be detached — deactivate the
    account instead, so a login never stays open with nothing behind it."""
    with transaction.atomic():
        account = PortalAccount.objects.select_for_update().select_related("user").get(pk=account.pk)
        links = StudentLink.objects.filter(account=account)
        if not links.filter(student=student).exists():
            raise ValidationError({"detail": "Этот студент не привязан к аккаунту."})
        if links.count() == 1:
            raise ValidationError({"detail": "Это единственный студент аккаунта — деактивируйте аккаунт вместо отвязки."})
        links.filter(student=student).delete()
        _audit(performed_by, account, [student], f"студент «{student}» отвязан от аккаунта «{account.user.username}».")


def reset_password(account: PortalAccount, *, performed_by) -> IssuedCredentials:
    """New temporary password; the first-login change is required again."""
    with transaction.atomic():
        account = PortalAccount.objects.select_for_update().select_related("user").get(pk=account.pk)
        user = account.user
        password = generate_password(user)
        user.set_password(password)
        user.save(update_fields=["password", "updated_at"])
        account.must_change_password = True
        account.credentials_issued_at = timezone.now()
        account.save(update_fields=["must_change_password", "credentials_issued_at", "updated_at"])
        _audit(performed_by, account, account.students.all(), f"пароль аккаунта «{user.username}» сброшен, выданы новые временные данные.")
    return IssuedCredentials(account=account, login=user.username, password=password)


def change_login(account: PortalAccount, new_login: str, *, performed_by) -> PortalAccount:
    with transaction.atomic():
        account = PortalAccount.objects.select_for_update().select_related("user").get(pk=account.pk)
        user = account.user
        login = validate_login(new_login, exclude_pk=user.pk)
        if login == user.username:
            return account
        old = user.username
        user.username, user.email = login, _email(login)
        try:
            with transaction.atomic():
                user.save(update_fields=["username", "email", "updated_at"])
        except IntegrityError:
            raise ValidationError({"login": "Этот логин уже занят."})
        _audit(performed_by, account, account.students.all(), f"логин изменён: {old} → {login}.")
    return account


def set_active(account: PortalAccount, active: bool, *, performed_by) -> PortalAccount:
    with transaction.atomic():
        account = PortalAccount.objects.select_for_update().select_related("user").get(pk=account.pk)
        if account.user.is_active != active:
            account.user.is_active = active
            account.user.save(update_fields=["is_active", "updated_at"])
            _audit(performed_by, account, account.students.all(),
                   f"аккаунт «{account.user.username}» {'активирован' if active else 'деактивирован'}.")
    return account


def set_payments_visible(account: PortalAccount, visible: bool, *, performed_by) -> PortalAccount:
    with transaction.atomic():
        account = PortalAccount.objects.select_for_update().select_related("user").get(pk=account.pk)
        if account.can_view_payments != visible:
            account.can_view_payments = visible
            account.save(update_fields=["can_view_payments", "updated_at"])
            _audit(performed_by, account, account.students.all(),
                   f"оплата в кабинете {'показана' if visible else 'скрыта'}.")
    return account


def change_own_password(user: User, *, current_password: str, new_password: str) -> None:
    """The account owner replaces the temporary (or current) password."""
    errors = {}
    if not user.check_password(current_password):
        errors["current_password"] = ["Неверный текущий пароль."]
    elif current_password == new_password:
        errors["new_password"] = ["Новый пароль должен отличаться от текущего."]
    else:
        try:
            validate_password(new_password, user)
        except ValidationError as exc:
            errors["new_password"] = exc.messages
    if errors:
        raise ValidationError(errors)
    with transaction.atomic():
        user.set_password(new_password)
        user.save(update_fields=["password", "updated_at"])
        account, _ = PortalAccount.objects.get_or_create(user=user)
        account.must_change_password = False
        account.password_changed_at = timezone.now()
        account.save(update_fields=["must_change_password", "password_changed_at", "updated_at"])
        _log(user, user, CHANGE, "Кабинет ученика: владелец сменил пароль.")
