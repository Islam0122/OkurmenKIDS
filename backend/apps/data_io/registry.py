"""Model-adapter registry for the Import/Export Template system.

The generic services in ``apps.data_io.services`` (render an export, build a
blank import file, validate an uploaded file, commit an import) never know
about Course, CourseLessonPlan or Subject directly — they only talk to a
``ModelAdapter``. Adding a new section (Teacher, Student, Group, ...) later
means writing one adapter module and registering it here; no change to the
services, admin mixin, or templates.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from django.db.models import QuerySet


@dataclass(frozen=True)
class FieldSpec:
    """One column an adapter knows how to export and/or import.

    ``get_value`` turns a model instance into the value written to a cell
    (export). ``importable`` marks a column that ``ModelAdapter.validate_row``
    actually reads back out of an uploaded file's row dict, keyed by this
    spec's ``key`` (the import services normalize uploaded headers — which
    show the human ``label`` — back to ``key`` before an adapter ever sees
    the row, see ``services._normalize_raw_row``).
    """

    key: str
    label: str
    get_value: Callable[[Any], Any]
    importable: bool = False
    required: bool = False
    help_text: str = ""


@dataclass
class ModelAdapter:
    key: str
    label: str
    fields: list[FieldSpec]
    prepare_queryset: Callable[[QuerySet], QuerySet]
    validate_row: Callable[[int, dict[str, str], dict], tuple[dict | None, list[str]]]
    apply_row: Callable[[dict], tuple[Any, bool]]
    default_fields: list[str] | None = None
    import_notes: str = ""

    def field_map(self) -> dict[str, FieldSpec]:
        return {f.key: f for f in self.fields}

    def default_columns(self) -> list[dict[str, str]]:
        fmap = self.field_map()
        keys = self.default_fields or list(fmap.keys())
        return [{"field": key, "label": fmap[key].label} for key in keys if key in fmap]

    def importable_fields(self) -> list[FieldSpec]:
        return [f for f in self.fields if f.importable]


_REGISTRY: dict[str, ModelAdapter] = {}


def register(adapter: ModelAdapter) -> None:
    _REGISTRY[adapter.key] = adapter


def get_adapter(key: str) -> ModelAdapter:
    return _REGISTRY[key]


def all_adapters() -> list[ModelAdapter]:
    return list(_REGISTRY.values())
