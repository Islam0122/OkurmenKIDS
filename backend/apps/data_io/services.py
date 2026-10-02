"""Generic Export/Import engine driven entirely by a ``ModelAdapter``.

Nothing here knows about Course, CourseLessonPlan or Subject — that logic
lives in ``apps.data_io.adapters.*``. This module is the "validation layer /
import preview / export generation / import execution" pieces from the
architecture: one implementation, reused by every registered adapter.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from django.db.models import QuerySet
from django.http import HttpResponse

from apps.users.import_export.formats import build_export_response, read_numbered_rows
from apps.users.import_export.results import ImportPreview, RowError

from .registry import ModelAdapter
from .validation import flatten_validation_error


@dataclass
class ImportSummary:
    """What a committed import did. Rows with errors are skipped (and listed
    in ``errors``); every other row is created or updated."""

    created: int = 0
    updated: int = 0
    skipped: int = 0
    errors: list[RowError] = field(default_factory=list)

    @property
    def error_count(self) -> int:
        return len(self.errors)

    @property
    def total(self) -> int:
        return self.created + self.updated + self.skipped


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


def _validate_all_rows(adapter: ModelAdapter, raw_rows: list[tuple[int, dict[str, str]]]):
    """``raw_rows`` / ``clean_rows`` are ``(row_number, row)`` pairs — the
    row's real line in the file (1 = header), so reported rows match the
    spreadsheet even when blank rows were skipped."""
    seen: dict = {}
    clean_rows = []
    row_errors: list[RowError] = []
    for index, raw in raw_rows:
        normalized = _normalize_raw_row(adapter, raw)
        clean, errors = adapter.validate_row(index, normalized, seen)
        if errors:
            row_errors.append(RowError(row=index, errors=errors))
        else:
            clean_rows.append((index, clean))
    return clean_rows, row_errors


def preview_import(adapter: ModelAdapter, uploaded_file) -> ImportPreview:
    raw_rows = read_numbered_rows(uploaded_file)
    _clean_rows, row_errors = _validate_all_rows(adapter, raw_rows)
    return ImportPreview(
        total=len(raw_rows),
        valid=len(raw_rows) - len(row_errors),
        invalid=len(row_errors),
        errors=row_errors,
    )


def commit_import(adapter: ModelAdapter, uploaded_file) -> ImportSummary:
    """Upsert every valid row (the adapter decides create vs. update); rows
    with errors are skipped and reported, never half-saved — each row is
    saved in its own savepoint, so a row that still fails at save-time
    (e.g. a constraint) rolls back alone."""
    raw_rows = read_numbered_rows(uploaded_file)
    clean_rows, row_errors = _validate_all_rows(adapter, raw_rows)

    summary = ImportSummary(errors=list(row_errors))
    with transaction.atomic():
        for row_number, clean in clean_rows:
            try:
                with transaction.atomic():
                    _obj, was_created = adapter.apply_row(clean)
            except DjangoValidationError as exc:
                summary.errors.append(RowError(row=row_number, errors=flatten_validation_error(exc)))
            except IntegrityError as exc:
                summary.errors.append(RowError(row=row_number, errors=[f"Ошибка сохранения: {exc}"]))
            else:
                if was_created:
                    summary.created += 1
                else:
                    summary.updated += 1

    summary.errors.sort(key=lambda error: error.row)
    summary.skipped = len(summary.errors)
    return summary
