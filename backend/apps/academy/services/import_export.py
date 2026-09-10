"""Import / Export for Students.

Upsert key: Student has no natural unique business field (first/last name
is not a safe uniqueness key — homonyms happen), so the *only* safe stable
identifier is the primary key. An optional ``id`` column selects an update;
a row without one always creates a new Student. This deliberately avoids
inventing a name-based "uniqueness" the model doesn't actually have (see
task spec §13).

``group`` is imported/exported by name, never by id — the caller looks up
an existing Group by exact name and never creates one implicitly.
"""
from __future__ import annotations

from dataclasses import dataclass

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.db.models import QuerySet
from django.http import HttpResponse

from apps.users.import_export.formats import build_export_response, is_valid_phone, parse_bool, read_rows
from apps.users.import_export.results import ImportPreview, ImportResult, RowError

from ..models import Group, Student

EXPORT_FIELDS = [
    "id",
    "first_name",
    "last_name",
    "phone",
    "parent_phone",
    "group",
    "is_active",
    "created_at",
]


class StudentImportValidationError(Exception):
    """Raised when a file fails validation (or a row fails at save-time)."""

    def __init__(self, preview: ImportPreview):
        self.preview = preview
        super().__init__("Student import validation failed")


class _RowSaveFailure(Exception):
    def __init__(self, row_number: int, messages: list[str]):
        self.row_number = row_number
        self.messages = messages
        super().__init__("; ".join(messages))


def export_students(queryset: QuerySet[Student], fmt: str = "csv") -> HttpResponse:
    rows = []
    for student in queryset.select_related("group"):
        rows.append(
            {
                "id": student.id,
                "first_name": student.first_name,
                "last_name": student.last_name,
                "phone": student.phone,
                "parent_phone": student.parent_phone,
                "group": student.group.name if student.group_id else "",
                "is_active": student.is_active,
                "created_at": student.created_at.isoformat(),
            }
        )
    return build_export_response(rows, EXPORT_FIELDS, fmt, "students")


@dataclass
class _CleanStudentRow:
    row_number: int
    student_id: int | None
    first_name: str
    last_name: str
    phone: str
    parent_phone: str
    group: Group | None
    is_active: bool


def _validate_row(row_number: int, raw: dict) -> tuple[_CleanStudentRow | None, list[str]]:
    errors: list[str] = []

    id_raw = (raw.get("id") or "").strip()
    student_id = None
    if id_raw:
        try:
            student_id = int(id_raw)
        except ValueError:
            errors.append(f"Некорректный id «{id_raw}».")
        else:
            if not Student.objects.filter(pk=student_id).exists():
                errors.append(f"Студент с id={student_id} не найден.")

    first_name = (raw.get("first_name") or "").strip()
    if not first_name:
        errors.append("Поле first_name обязательно.")

    last_name = (raw.get("last_name") or "").strip()

    phone = (raw.get("phone") or "").strip()
    if phone and not is_valid_phone(phone):
        errors.append(f"Некорректный номер телефона «{phone}».")

    parent_phone = (raw.get("parent_phone") or "").strip()
    if parent_phone and not is_valid_phone(parent_phone):
        errors.append(f"Некорректный номер телефона родителя «{parent_phone}».")

    group_name = (raw.get("group") or "").strip()
    group = None
    if group_name:
        group = Group.objects.filter(name=group_name).first()
        if group is None:
            errors.append(f'Группа "{group_name}" не найдена.')

    is_active_raw = raw.get("is_active") or ""
    try:
        is_active = parse_bool(is_active_raw, default=True)
    except ValueError:
        errors.append(f"Некорректное булево значение is_active «{is_active_raw}».")
        is_active = True

    if errors:
        return None, errors

    clean = _CleanStudentRow(
        row_number=row_number,
        student_id=student_id,
        first_name=first_name,
        last_name=last_name,
        phone=phone,
        parent_phone=parent_phone,
        group=group,
        is_active=is_active,
    )
    return clean, []


def validate_students_rows(raw_rows: list[dict]) -> tuple[list[_CleanStudentRow], list[RowError]]:
    clean_rows: list[_CleanStudentRow] = []
    row_errors: list[RowError] = []

    for index, raw in enumerate(raw_rows, start=2):  # row 1 is the header
        clean, errors = _validate_row(index, raw)
        if errors:
            row_errors.append(RowError(row=index, errors=errors))
        else:
            clean_rows.append(clean)

    return clean_rows, row_errors


def preview_students_import(uploaded_file) -> ImportPreview:
    raw_rows = read_rows(uploaded_file)
    clean_rows, row_errors = validate_students_rows(raw_rows)
    return ImportPreview(total=len(raw_rows), valid=len(clean_rows), invalid=len(row_errors), errors=row_errors)


def _apply_row(clean: _CleanStudentRow) -> bool:
    """Create/update one Student. Returns True if created."""
    created = clean.student_id is None
    student = Student.objects.get(pk=clean.student_id) if clean.student_id is not None else Student()

    student.first_name = clean.first_name
    student.last_name = clean.last_name
    student.phone = clean.phone
    student.parent_phone = clean.parent_phone
    student.group = clean.group
    student.is_active = clean.is_active

    try:
        student.full_clean()
    except DjangoValidationError as exc:
        messages = getattr(exc, "messages", None) or [str(exc)]
        raise _RowSaveFailure(clean.row_number, list(messages)) from exc

    student.save()
    return created


def import_students(uploaded_file) -> ImportResult:
    raw_rows = read_rows(uploaded_file)
    clean_rows, row_errors = validate_students_rows(raw_rows)
    if row_errors:
        raise StudentImportValidationError(
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
        raise StudentImportValidationError(
            ImportPreview(
                total=len(raw_rows),
                valid=0,
                invalid=1,
                errors=[RowError(row=failure.row_number, errors=failure.messages)],
            )
        ) from failure

    return ImportResult(created=created, updated=updated, total=created + updated)
