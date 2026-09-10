"""Import / Export for Teachers (User + Teacher profile + Subjects).

Upsert key: ``username`` or ``email`` — both are already unique fields on
``User``, so no invented identifier is needed here (unlike Student, see
``apps.academy.services.import_export``). A row is an *update* whenever an
existing User matches by either field; otherwise it's a *create*.

Never exported: password / password hash. On create, a password from the
file is hashed via ``set_password()``; if the file has none, a random one
is generated. Passwords are never echoed back in any response.
"""
from __future__ import annotations

import datetime as dt
import secrets
import string
from dataclasses import dataclass

from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.validators import validate_email
from django.db import transaction
from django.db.models import QuerySet
from django.http import HttpResponse

from apps.users.models import Subject, Teacher, User

from .formats import build_export_response, is_valid_phone, parse_bool, read_rows
from .results import ImportPreview, ImportResult, RowError

EXPORT_FIELDS = [
    "username",
    "email",
    "first_name",
    "last_name",
    "role",
    "is_active",
    "is_verified",
    "phone",
    "position",
    "experience_years",
    "bio",
    "hire_date",
    "subjects",
]


class TeacherImportValidationError(Exception):
    """Raised when a file fails validation (or a row fails at save-time)."""

    def __init__(self, preview: ImportPreview):
        self.preview = preview
        super().__init__("Teacher import validation failed")


class _RowSaveFailure(Exception):
    def __init__(self, row_number: int, messages: list[str]):
        self.row_number = row_number
        self.messages = messages
        super().__init__("; ".join(messages))


def export_teachers(queryset: QuerySet[Teacher], fmt: str = "csv") -> HttpResponse:
    rows = []
    for teacher in queryset.select_related("user").prefetch_related("subjects"):
        user = teacher.user
        rows.append(
            {
                "username": user.username,
                "email": user.email,
                "first_name": user.first_name,
                "last_name": user.last_name,
                "role": user.role,
                "is_active": user.is_active,
                "is_verified": user.is_verified,
                "phone": teacher.phone,
                "position": teacher.position,
                "experience_years": teacher.experience_years,
                "bio": teacher.bio,
                "hire_date": teacher.hire_date.isoformat() if teacher.hire_date else "",
                "subjects": ", ".join(subject.name for subject in teacher.subjects.all()),
            }
        )
    return build_export_response(rows, EXPORT_FIELDS, fmt, "teachers")


def _generate_password() -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(12))


@dataclass
class _CleanTeacherRow:
    row_number: int
    username: str
    email: str
    first_name: str
    last_name: str
    phone: str
    position: str
    experience_years: int
    bio: str
    hire_date: dt.date | None
    is_active: bool
    is_verified: bool | None
    subjects: list[Subject]
    password: str | None
    existing_user: User | None


def _validate_row(
    row_number: int,
    raw: dict,
    seen_usernames: dict[str, int],
    seen_emails: dict[str, int],
) -> tuple[_CleanTeacherRow | None, list[str]]:
    errors: list[str] = []

    username = (raw.get("username") or "").strip()
    # Not lower-cased: email local-parts are case-sensitive per RFC 5321, and
    # Django doesn't normalize them either — matching on the exact value from
    # the file keeps this consistent with how existing User rows were stored.
    email = (raw.get("email") or "").strip()
    first_name = (raw.get("first_name") or "").strip()
    last_name = (raw.get("last_name") or "").strip()
    phone = (raw.get("phone") or "").strip()
    position = (raw.get("position") or "").strip() or "Тренер"
    bio = (raw.get("bio") or "").strip()
    role_raw = (raw.get("role") or "").strip().lower()

    if not username:
        errors.append("Поле username обязательно.")
    if not email:
        errors.append("Поле email обязательно.")
    else:
        try:
            validate_email(email)
        except DjangoValidationError:
            errors.append(f"Некорректный email: «{email}».")
    if not first_name:
        errors.append("Поле first_name обязательно.")
    if phone and not is_valid_phone(phone):
        errors.append(f"Некорректный номер телефона «{phone}».")
    if role_raw and role_raw not in ("teacher", "тренер"):
        errors.append(
            f"Недопустимая роль «{raw.get('role')}» — через импорт тренеров можно создавать только тренеров."
        )

    experience_years_raw = (raw.get("experience_years") or "").strip()
    experience_years = 0
    if experience_years_raw:
        try:
            experience_years = int(experience_years_raw)
        except ValueError:
            errors.append(f"experience_years должно быть целым числом, получено «{experience_years_raw}».")
        else:
            if experience_years < 0 or experience_years > 60:
                errors.append("experience_years должно быть от 0 до 60.")

    hire_date_raw = (raw.get("hire_date") or "").strip()
    hire_date = None
    if hire_date_raw:
        try:
            hire_date = dt.date.fromisoformat(hire_date_raw)
        except ValueError:
            errors.append(f"Некорректная дата hire_date «{hire_date_raw}» (ожидается ГГГГ-ММ-ДД).")

    is_active_raw = raw.get("is_active") or ""
    try:
        is_active = parse_bool(is_active_raw, default=True)
    except ValueError:
        errors.append(f"Некорректное булево значение is_active «{is_active_raw}».")
        is_active = True

    is_verified_raw = (raw.get("is_verified") or "").strip()
    is_verified = None
    if is_verified_raw:
        try:
            is_verified = parse_bool(is_verified_raw)
        except ValueError:
            errors.append(f"Некорректное булево значение is_verified «{is_verified_raw}».")

    subjects_raw = (raw.get("subjects") or "").strip()
    subjects: list[Subject] = []
    if subjects_raw:
        for name in [part.strip() for part in subjects_raw.split(",") if part.strip()]:
            subject = Subject.objects.filter(name__iexact=name).first()
            if subject is None:
                errors.append(f'Предмет "{name}" не найден.')
            else:
                subjects.append(subject)

    if username:
        if username in seen_usernames:
            errors.append(f"Дублирующийся username «{username}» в файле (строка {seen_usernames[username]}).")
        else:
            seen_usernames[username] = row_number
    if email:
        if email in seen_emails:
            errors.append(f"Дублирующийся email «{email}» в файле (строка {seen_emails[email]}).")
        else:
            seen_emails[email] = row_number

    user_by_username = User.objects.filter(username=username).first() if username else None
    user_by_email = User.objects.filter(email=email).first() if email else None

    existing_user = None
    if user_by_username and user_by_email and user_by_username.pk != user_by_email.pk:
        errors.append(
            f"username «{username}» и email «{email}» принадлежат разным существующим пользователям."
        )
    else:
        existing_user = user_by_username or user_by_email

    if existing_user is not None and existing_user.role != User.Role.TEACHER:
        errors.append(
            f"Пользователь «{existing_user.username}» уже существует с ролью "
            f"«{existing_user.get_role_display()}» — импорт тренеров не может изменить роль пользователя."
        )

    password_raw = raw.get("password")
    password = password_raw.strip() if password_raw else None

    if errors:
        return None, errors

    clean = _CleanTeacherRow(
        row_number=row_number,
        username=username,
        email=email,
        first_name=first_name,
        last_name=last_name,
        phone=phone,
        position=position,
        experience_years=experience_years,
        bio=bio,
        hire_date=hire_date,
        is_active=is_active,
        is_verified=is_verified,
        subjects=subjects,
        password=password,
        existing_user=existing_user,
    )
    return clean, []


def validate_teachers_rows(raw_rows: list[dict]) -> tuple[list[_CleanTeacherRow], list[RowError]]:
    clean_rows: list[_CleanTeacherRow] = []
    row_errors: list[RowError] = []
    seen_usernames: dict[str, int] = {}
    seen_emails: dict[str, int] = {}

    for index, raw in enumerate(raw_rows, start=2):  # row 1 is the header
        clean, errors = _validate_row(index, raw, seen_usernames, seen_emails)
        if errors:
            row_errors.append(RowError(row=index, errors=errors))
        else:
            clean_rows.append(clean)

    return clean_rows, row_errors


def preview_teachers_import(uploaded_file) -> ImportPreview:
    raw_rows = read_rows(uploaded_file)
    clean_rows, row_errors = validate_teachers_rows(raw_rows)
    return ImportPreview(total=len(raw_rows), valid=len(clean_rows), invalid=len(row_errors), errors=row_errors)


def _apply_row(clean: _CleanTeacherRow) -> bool:
    """Create/update the User + Teacher for one validated row. Returns True if created."""
    created = clean.existing_user is None

    try:
        if clean.existing_user is not None:
            user = clean.existing_user
            user.username = clean.username
            user.email = clean.email
            user.first_name = clean.first_name
            user.last_name = clean.last_name
            user.is_active = clean.is_active
            if clean.is_verified is not None:
                user.is_verified = clean.is_verified
            user.full_clean(exclude=["password"])
            user.save()
            teacher, _ = Teacher.objects.get_or_create(user=user)
        else:
            user = User(
                username=clean.username,
                email=clean.email,
                first_name=clean.first_name,
                last_name=clean.last_name,
                role=User.Role.TEACHER,
                is_verified=clean.is_verified if clean.is_verified is not None else False,
                is_active=clean.is_active,
            )
            user.set_password(clean.password or _generate_password())
            user.full_clean(exclude=["password"])
            user.save()
            teacher = Teacher(user=user)

        teacher.phone = clean.phone
        teacher.position = clean.position
        teacher.experience_years = clean.experience_years
        teacher.bio = clean.bio
        teacher.hire_date = clean.hire_date
        teacher.is_active = clean.is_active
        teacher.full_clean()
        teacher.save()
        teacher.subjects.set(clean.subjects)
    except DjangoValidationError as exc:
        messages = getattr(exc, "messages", None) or [str(exc)]
        raise _RowSaveFailure(clean.row_number, list(messages)) from exc

    return created


def import_teachers(uploaded_file) -> ImportResult:
    raw_rows = read_rows(uploaded_file)
    clean_rows, row_errors = validate_teachers_rows(raw_rows)
    if row_errors:
        raise TeacherImportValidationError(
            ImportPreview(total=len(raw_rows), valid=len(clean_rows), invalid=len(row_errors), errors=row_errors)
        )

    created = 0
    updated = 0
    try:
        with transaction.atomic():
            for clean in clean_rows:
                if _apply_row(clean):
                    created += 1
                else:
                    updated += 1
    except _RowSaveFailure as failure:
        raise TeacherImportValidationError(
            ImportPreview(
                total=len(raw_rows),
                valid=0,
                invalid=1,
                errors=[RowError(row=failure.row_number, errors=failure.messages)],
            )
        ) from failure

    return ImportResult(created=created, updated=updated, total=created + updated)
