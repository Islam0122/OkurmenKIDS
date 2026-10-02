"""Generic Export/Import engine driven entirely by a ``ModelAdapter``.

Nothing here knows about Course, CourseLessonPlan or Subject — that logic
lives in ``apps.data_io.adapters.*``. This module is the "validation layer /
import preview / export generation / import execution" pieces from the
architecture: one implementation, reused by every registered adapter.
"""
from __future__ import annotations

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from django.db.models import QuerySet
from django.http import HttpResponse

from apps.users.import_export.formats import build_export_response, read_numbered_rows
from apps.users.import_export.results import ImportPreview, ImportResult, RowError

from .registry import ModelAdapter
from .validation import flatten_validation_error


class ImportValidationError(Exception):
    """Raised when a file fails validation (or a row fails at save-time)."""

    def __init__(self, preview: ImportPreview):
        self.preview = preview
        super().__init__("Import validation failed")


def render_export(
    adapter: ModelAdapter,
    queryset: QuerySet,
    columns: list[dict[str, str]],
    fmt: str,
) -> HttpResponse:
    """Export ``queryset`` using an explicit column layout (a saved template's
    ``columns``, or ``adapter.default_columns()`` for the quick export).
    """
    fmap = adapter.field_map()
    keys = [c["field"] for c in columns if c["field"] in fmap]
    headers = {c["field"]: (c.get("label") or fmap[c["field"]].label) for c in columns if c["field"] in fmap}

    rows = []
    for obj in queryset:
        rows.append({key: fmap[key].get_value(obj) for key in keys})

    base_filename = adapter.key.replace(".", "_")
    return build_export_response(rows, keys, fmt, base_filename, headers)


def build_import_template_file(adapter: ModelAdapter, fmt: str) -> HttpResponse:
    """A blank file with the exact headers ``preview_import``/``commit_import``
    expect back — the "download a template, fill it in" half of the import
    flow.
    """
    fields = adapter.importable_fields()
    keys = [f.key for f in fields]
    headers = {f.key: f.label for f in fields}
    base_filename = f"{adapter.key.replace('.', '_')}_import_template"
    return build_export_response([], keys, fmt, base_filename, headers)


def _normalize_raw_row(adapter: ModelAdapter, raw: dict[str, str]) -> dict[str, str]:
    """Map an uploaded row's headers (the human labels our own template
    downloads use) back to each field's canonical key, so every adapter's
    ``validate_row`` only ever deals with plain keys like ``name`` or
    ``count_lesson``. A header that isn't a known label is passed through
    unchanged — this keeps hand-typed files using the raw field key working
    too.
    """
    label_to_key = {f.label: f.key for f in adapter.fields}
    return {label_to_key.get(header, header): value for header, value in raw.items()}


def _validate_all_rows(adapter: ModelAdapter, numbered_rows: list[tuple[int, dict[str, str]]]):
    """Validate every row. Returns ``(clean_rows, row_errors)`` where each
    clean row is paired with its line number in the file (1 = header), so a
    save-time failure can still be reported against the right line.
    """
    seen: dict = {}
    clean_rows: list[tuple[int, dict]] = []
    row_errors: list[RowError] = []
    for row_number, raw in numbered_rows:
        normalized = _normalize_raw_row(adapter, raw)
        clean, errors = adapter.validate_row(row_number, normalized, seen)
        if errors:
            row_errors.append(RowError(row=row_number, errors=errors))
        else:
            clean_rows.append((row_number, clean))
    return clean_rows, row_errors


def preview_import(adapter: ModelAdapter, uploaded_file) -> ImportPreview:
    numbered_rows = read_numbered_rows(uploaded_file)
    _clean_rows, row_errors = _validate_all_rows(adapter, numbered_rows)
    return ImportPreview(
        total=len(numbered_rows),
        valid=len(numbered_rows) - len(row_errors),
        invalid=len(row_errors),
        errors=row_errors,
    )


def commit_import(adapter: ModelAdapter, uploaded_file) -> ImportResult:
    """Upsert every row through ``adapter.apply_row``.

    All-or-nothing by default: any invalid row raises ``ImportValidationError``
    and nothing is saved. With ``adapter.partial_import`` the valid rows are
    saved, invalid ones are skipped, and every skipped row comes back in
    ``ImportResult.errors``; each row is saved in its own savepoint so a
    save-time failure only drops that one row.
    """
    numbered_rows = read_numbered_rows(uploaded_file)
    clean_rows, row_errors = _validate_all_rows(adapter, numbered_rows)
    if row_errors and not adapter.partial_import:
        raise ImportValidationError(
            ImportPreview(
                total=len(numbered_rows),
                valid=len(numbered_rows) - len(row_errors),
                invalid=len(row_errors),
                errors=row_errors,
            )
        )

    created = 0
    updated = 0
    with transaction.atomic():
        for row_number, clean in clean_rows:
            if not adapter.partial_import:
                _obj, was_created = adapter.apply_row(clean)
            else:
                try:
                    with transaction.atomic():
                        _obj, was_created = adapter.apply_row(clean)
                except DjangoValidationError as exc:
                    row_errors.append(RowError(row=row_number, errors=flatten_validation_error(exc)))
                    continue
                except IntegrityError as exc:
                    row_errors.append(RowError(row=row_number, errors=[f"Ошибка сохранения: {exc}"]))
                    continue
            if was_created:
                created += 1
            else:
                updated += 1

    row_errors.sort(key=lambda error: error.row)
    return ImportResult(
        created=created,
        updated=updated,
        total=created + updated,
        skipped=len(row_errors),
        errors=row_errors,
    )
