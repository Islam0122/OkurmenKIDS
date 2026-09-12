"""Generic Export/Import engine driven entirely by a ``ModelAdapter``.

Nothing here knows about Course, CourseLessonPlan or Subject — that logic
lives in ``apps.data_io.adapters.*``. This module is the "validation layer /
import preview / export generation / import execution" pieces from the
architecture: one implementation, reused by every registered adapter.
"""
from __future__ import annotations

from django.db import transaction
from django.db.models import QuerySet
from django.http import HttpResponse

from apps.users.import_export.formats import build_export_response, read_rows
from apps.users.import_export.results import ImportPreview, ImportResult, RowError

from .registry import ModelAdapter


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


def _validate_all_rows(adapter: ModelAdapter, raw_rows: list[dict[str, str]]):
    seen: dict = {}
    clean_rows = []
    row_errors: list[RowError] = []
    for index, raw in enumerate(raw_rows, start=2):  # row 1 is the header
        normalized = _normalize_raw_row(adapter, raw)
        clean, errors = adapter.validate_row(index, normalized, seen)
        if errors:
            row_errors.append(RowError(row=index, errors=errors))
        else:
            clean_rows.append(clean)
    return clean_rows, row_errors


def preview_import(adapter: ModelAdapter, uploaded_file) -> ImportPreview:
    raw_rows = read_rows(uploaded_file)
    _clean_rows, row_errors = _validate_all_rows(adapter, raw_rows)
    return ImportPreview(
        total=len(raw_rows),
        valid=len(raw_rows) - len(row_errors),
        invalid=len(row_errors),
        errors=row_errors,
    )


def commit_import(adapter: ModelAdapter, uploaded_file) -> ImportResult:
    raw_rows = read_rows(uploaded_file)
    clean_rows, row_errors = _validate_all_rows(adapter, raw_rows)
    if row_errors:
        raise ImportValidationError(
            ImportPreview(
                total=len(raw_rows),
                valid=len(raw_rows) - len(row_errors),
                invalid=len(row_errors),
                errors=row_errors,
            )
        )

    created = 0
    updated = 0
    with transaction.atomic():
        for clean in clean_rows:
            _obj, was_created = adapter.apply_row(clean)
            if was_created:
                created += 1
            else:
                updated += 1

    return ImportResult(created=created, updated=updated, total=created + updated)
