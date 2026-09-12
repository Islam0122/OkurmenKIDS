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

import datetime as dt
import io
from dataclasses import dataclass, field

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.db.models import QuerySet
from django.http import HttpResponse
from django.utils import timezone
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

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

EXPORT_HEADERS = {
    "id": "ID",
    "first_name": "Имя",
    "last_name": "Фамилия",
    "phone": "Телефон",
    "parent_phone": "Телефон родителя",
    "group": "Группа",
    "is_active": "Статус",
    "created_at": "Дата создания",
}

# Import/template columns deliberately omit "id" (used only for export/upsert
# round-tripping, not something an admin fills in by hand) — matches exactly
# the fields the model actually has (see models.Student), nothing invented.
TEMPLATE_COLUMNS = ["first_name", "last_name", "phone", "parent_phone", "group", "is_active"]


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
    fmt = (fmt or "csv").strip().lower()
    if fmt == "xlsx":
        return _build_students_xlsx(rows)
    # CSV keeps raw field names as its header row (no EXPORT_HEADERS) — the
    # API's export/import round trip (see StudentImportExportAPITests) reads
    # an exported CSV straight back in, and read_rows()/_validate_row() key
    # off these exact names (first_name, group, is_active, ...).
    return build_export_response(rows, EXPORT_FIELDS, fmt, "students")


def _build_students_xlsx(rows: list[dict]) -> HttpResponse:
    """A styled export sheet — bold header, frozen header row, autofilter and
    sane column widths — kept as its own builder (rather than extending the
    shared, plain ``build_export_response``) so this styling stays scoped to
    Students and doesn't change every other model's XLSX export."""
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Студенты"

    header_labels = [EXPORT_HEADERS[name] for name in EXPORT_FIELDS]
    sheet.append(header_labels)
    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill(start_color="2F8F5B", end_color="2F8F5B", fill_type="solid")
    for col_index in range(1, len(header_labels) + 1):
        cell = sheet.cell(row=1, column=col_index)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center", vertical="center")

    for row in rows:
        values = []
        for field_name in EXPORT_FIELDS:
            value = row.get(field_name, "")
            if field_name == "is_active":
                value = "Активен" if value else "Неактивен"
            elif field_name == "created_at" and value:
                value = dt.datetime.fromisoformat(value).strftime("%d.%m.%Y %H:%M")
            values.append(value)
        sheet.append(values)

    sheet.freeze_panes = "A2"
    sheet.auto_filter.ref = f"A1:{get_column_letter(len(header_labels))}{sheet.max_row}"

    column_widths = {"id": 8, "first_name": 18, "last_name": 18, "phone": 16, "parent_phone": 18,
                      "group": 24, "is_active": 12, "created_at": 18}
    for col_index, field_name in enumerate(EXPORT_FIELDS, start=1):
        sheet.column_dimensions[get_column_letter(col_index)].width = column_widths.get(field_name, 16)

    buffer = io.BytesIO()
    workbook.save(buffer)
    filename = f"okurmenkids_students_{timezone.now():%Y-%m-%d}.xlsx"
    response = HttpResponse(
        buffer.getvalue(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


def build_student_import_template() -> HttpResponse:
    """okurmenkids_students_template.xlsx — a blank sheet with exactly the
    columns the import reads (see TEMPLATE_COLUMNS/_validate_row), plus a
    second "Инструкция" sheet explaining how to fill it in."""
    workbook = Workbook()

    sheet = workbook.active
    sheet.title = "Студенты"
    header_labels = [EXPORT_HEADERS[name] for name in TEMPLATE_COLUMNS]
    sheet.append(header_labels)
    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill(start_color="2F8F5B", end_color="2F8F5B", fill_type="solid")
    for col_index in range(1, len(header_labels) + 1):
        cell = sheet.cell(row=1, column=col_index)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center", vertical="center")
    # One example row, so the expected format is obvious at a glance.
    sheet.append(["Аружан", "Медерова", "+996700123456", "+996700654321", "Python Beginner", "true"])
    for col_index in range(1, len(header_labels) + 1):
        sheet.column_dimensions[get_column_letter(col_index)].width = 20
    sheet.freeze_panes = "A2"

    instructions = workbook.create_sheet("Инструкция")
    instructions.column_dimensions["A"].width = 34
    instructions.column_dimensions["B"].width = 80
    instructions.append(["Колонка", "Описание"])
    for col in ("A1", "B1"):
        cell = instructions[col]
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill(start_color="2F8F5B", end_color="2F8F5B", fill_type="solid")
    rows = [
        ("first_name", "Обязательное поле. Имя студента."),
        ("last_name", "Необязательное поле. Фамилия студента."),
        ("phone", "Необязательное поле. Телефон студента, формат: цифры, +, -, пробелы, скобки."),
        ("parent_phone", "Необязательное поле. Телефон родителя, тот же формат, что и phone."),
        (
            "group",
            "Необязательное поле. Точное название уже существующей группы. "
            "Группа не создаётся автоматически — если название не найдено, строка отклоняется.",
        ),
        (
            "is_active",
            "Необязательное поле, по умолчанию — true. Допустимые значения: "
            "true/false, 1/0, да/нет, yes/no.",
        ),
    ]
    for name, description in rows:
        instructions.append([name, description])
    instructions.append([])
    instructions.append(["Важно", "Не изменяйте названия колонок в первой строке листа «Студенты»."])
    instructions.append(["Пример", "Строка 2 листа «Студенты» — пример корректно заполненной записи."])

    buffer = io.BytesIO()
    workbook.save(buffer)
    response = HttpResponse(
        buffer.getvalue(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    response["Content-Disposition"] = 'attachment; filename="okurmenkids_students_template.xlsx"'
    return response


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


@dataclass
class StudentRowPreview:
    """One row of the *full* import preview table — every uploaded row, not
    just the failing ones (contrast ``RowError``/``ImportPreview`` above,
    which only ever list failures). Used solely to render the row-by-row
    preview grid the Excel import screen shows before committing."""

    row_number: int
    first_name: str
    last_name: str
    phone: str
    group_name: str
    is_active_raw: str
    ok: bool
    errors: list[str] = field(default_factory=list)


def preview_students_import_rows(uploaded_file) -> tuple[list[StudentRowPreview], ImportPreview]:
    """Like ``preview_students_import``, but also returns every raw row
    (valid or not) so the import screen can render a full "row / имя /
    телефон / группа / статус / результат" table instead of just an error
    list."""
    raw_rows = read_rows(uploaded_file)
    clean_rows, row_errors = validate_students_rows(raw_rows)
    errors_by_row = {error.row: error.errors for error in row_errors}
    clean_by_row = {clean.row_number: clean for clean in clean_rows}

    row_previews: list[StudentRowPreview] = []
    for index, raw in enumerate(raw_rows, start=2):  # row 1 is the header
        errors = errors_by_row.get(index, [])
        clean = clean_by_row.get(index)
        row_previews.append(
            StudentRowPreview(
                row_number=index,
                first_name=(raw.get("first_name") or "").strip(),
                last_name=(raw.get("last_name") or "").strip(),
                phone=(raw.get("phone") or "").strip(),
                group_name=(raw.get("group") or "").strip(),
                is_active_raw=(raw.get("is_active") or "").strip(),
                ok=clean is not None,
                errors=errors,
            )
        )

    preview = ImportPreview(total=len(raw_rows), valid=len(clean_rows), invalid=len(row_errors), errors=row_errors)
    return row_previews, preview


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
