"""Import / Export for Groups.

Upsert key: ``Group.name`` — unlike Student, Group already has a real
unique business field (``models.Group.name``), so that's the safe,
stable identifier a row is matched on, exactly per the spec's "use
existing unique fields if available" rule. No invented id-based matching
needed here.

``course`` is imported/exported by name, never by id — the caller looks
up an existing Course by exact name and never creates one implicitly
(same convention as Student's ``group`` column, see ``import_export.py``).
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.db.models import Count, Q, QuerySet
from django.http import HttpResponse

from apps.users.import_export.formats import build_export_response, parse_bool, read_rows
from apps.users.import_export.results import ImportPreview, ImportResult, RowError

from ..models import Course, Group

EXPORT_FIELDS = [
    "name",
    "course",
    "status",
    "start_date",
    "end_date",
    "max_students",
    "description",
    "students_count",
    "created_at",
]

_STATUS_BY_VALUE = {value: value for value, _ in Group.Status.choices}
_STATUS_BY_LABEL = {label.lower(): value for value, label in Group.Status.choices}


class GroupImportValidationError(Exception):
    """Raised when a file fails validation (or a row fails at save-time)."""

    def __init__(self, preview: ImportPreview):
        self.preview = preview
        super().__init__("Group import validation failed")


class _RowSaveFailure(Exception):
    def __init__(self, row_number: int, messages: list[str]):
        self.row_number = row_number
        self.messages = messages
        super().__init__("; ".join(messages))


def export_groups(queryset: QuerySet[Group], fmt: str = "csv") -> HttpResponse:
    rows = []
    for group in queryset.select_related("course").annotate(
        _students_count=Count("students", filter=Q(students__is_active=True), distinct=True)
    ):
        rows.append(
            {
                "name": group.name,
                "course": group.course.name if group.course_id else "",
                "status": group.status,
                "start_date": group.start_date.isoformat() if group.start_date else "",
                "end_date": group.end_date.isoformat() if group.end_date else "",
                "max_students": group.max_students if group.max_students is not None else "",
                "description": group.description,
                "students_count": getattr(group, "_students_count", 0),
                "created_at": group.created_at.isoformat(),
            }
        )
    return build_export_response(rows, EXPORT_FIELDS, fmt, "groups")


@dataclass
class _CleanGroupRow:
    row_number: int
    existing_group: Group | None
    name: str
    course: Course
    status: str
    start_date: dt.date
    end_date: dt.date | None
    max_students: int | None
    description: str


def _parse_status(raw: str) -> tuple[str | None, str | None]:
    """Returns (status, error). Accepts either the stored value or its
    Russian display label, case-insensitively — friendlier for a human
    filling in a spreadsheet than requiring the exact internal value."""
    normalized = raw.strip().lower()
    if normalized in _STATUS_BY_VALUE:
        return normalized, None
    if normalized in _STATUS_BY_LABEL:
        return _STATUS_BY_LABEL[normalized], None
    return None, f'Недопустимый статус «{raw}».'


def _validate_row(row_number: int, raw: dict, seen_names: dict[str, int]) -> tuple[_CleanGroupRow | None, list[str]]:
    errors: list[str] = []

    name = (raw.get("name") or "").strip()
    if not name:
        errors.append("Поле name обязательно.")
    elif name in seen_names:
        errors.append(f"Дублирующееся название группы «{name}» в файле (строка {seen_names[name]}).")
    else:
        seen_names[name] = row_number

    course_name = (raw.get("course") or "").strip()
    course = None
    if not course_name:
        errors.append("Поле course обязательно.")
    else:
        course = Course.objects.filter(name=course_name).first()
        if course is None:
            errors.append(f'Курс "{course_name}" не найден.')

    status_raw = (raw.get("status") or "").strip()
    if status_raw:
        status, status_error = _parse_status(status_raw)
        if status_error:
            errors.append(status_error)
    else:
        status, status_error = Group.Status.ACTIVE, None

    start_date_raw = (raw.get("start_date") or "").strip()
    start_date = None
    if not start_date_raw:
        errors.append("Поле start_date обязательно.")
    else:
        try:
            start_date = dt.date.fromisoformat(start_date_raw)
        except ValueError:
            errors.append(f"Некорректная дата start_date «{start_date_raw}» (ожидается ГГГГ-ММ-ДД).")

    end_date_raw = (raw.get("end_date") or "").strip()
    end_date = None
    if end_date_raw:
        try:
            end_date = dt.date.fromisoformat(end_date_raw)
        except ValueError:
            errors.append(f"Некорректная дата end_date «{end_date_raw}» (ожидается ГГГГ-ММ-ДД).")

    max_students_raw = (raw.get("max_students") or "").strip()
    max_students = None
    if max_students_raw:
        try:
            max_students = int(max_students_raw)
        except ValueError:
            errors.append(f"max_students должно быть целым числом, получено «{max_students_raw}».")
        else:
            if max_students < 1:
                errors.append("max_students должно быть не меньше 1.")

    description = (raw.get("description") or "").strip()

    existing_group = Group.objects.filter(name=name).first() if name else None

    if errors:
        return None, errors

    clean = _CleanGroupRow(
        row_number=row_number,
        existing_group=existing_group,
        name=name,
        course=course,
        status=status,
        start_date=start_date,
        end_date=end_date,
        max_students=max_students,
        description=description,
    )
    return clean, []


def validate_groups_rows(raw_rows: list[dict]) -> tuple[list[_CleanGroupRow], list[RowError]]:
    clean_rows: list[_CleanGroupRow] = []
    row_errors: list[RowError] = []
    seen_names: dict[str, int] = {}

    for index, raw in enumerate(raw_rows, start=2):  # row 1 is the header
        clean, errors = _validate_row(index, raw, seen_names)
        if errors:
            row_errors.append(RowError(row=index, errors=errors))
        else:
            clean_rows.append(clean)

    return clean_rows, row_errors


def preview_groups_import(uploaded_file) -> ImportPreview:
    raw_rows = read_rows(uploaded_file)
    clean_rows, row_errors = validate_groups_rows(raw_rows)
    return ImportPreview(total=len(raw_rows), valid=len(clean_rows), invalid=len(row_errors), errors=row_errors)


def _apply_row(clean: _CleanGroupRow) -> bool:
    """Create/update one Group. Returns True if created."""
    created = clean.existing_group is None
    group = clean.existing_group or Group()

    group.name = clean.name
    group.course = clean.course
    group.status = clean.status
    group.start_date = clean.start_date
    group.end_date = clean.end_date
    group.max_students = clean.max_students
    group.description = clean.description

    try:
        group.full_clean()
    except DjangoValidationError as exc:
        messages = getattr(exc, "messages", None) or [str(exc)]
        raise _RowSaveFailure(clean.row_number, list(messages)) from exc

    group.save()
    return created


def import_groups(uploaded_file) -> ImportResult:
    raw_rows = read_rows(uploaded_file)
    clean_rows, row_errors = validate_groups_rows(raw_rows)
    if row_errors:
        raise GroupImportValidationError(
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
        raise GroupImportValidationError(
            ImportPreview(
                total=len(raw_rows),
                valid=0,
                invalid=1,
                errors=[RowError(row=failure.row_number, errors=failure.messages)],
            )
        ) from failure

    return ImportResult(created=created, updated=updated, total=created + updated)
