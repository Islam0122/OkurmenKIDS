"""Reports-side view of the KPI — a thin adapter over services.kpi_engine.

The formula, weights, rounding and status thresholds all live in
services.kpi_engine; this module only adds the short labels the Reports
templates show and keeps the import names the Reports code already uses.
"""
from __future__ import annotations

from apps.academy.services.kpi_engine import (
    COMPONENTS,
    METRIC_LABELS,
    STATUS_LABELS,
    kpi_status,
    kpi_weights,
    round1,
    total_kpi,
)
from apps.academy.services.kpi_engine import ratio as _exact_ratio
from apps.academy.services.kpi_engine import weights_description as _engine_weights_description

COMPONENT_LABELS = {name: METRIC_LABELS[name] for name in COMPONENTS}

COMPONENT_SHORT_LABELS = {
    "attendance": "Посещаемость",
    "homework": "Домашние задания",
    "lesson_completion": "Активность",
    "progress": "Прогресс",
}

LEVEL_LABELS = STATUS_LABELS


def kpi_level(value: float | None) -> str:
    """"good" / "attention" / "low" / "no_data" — see kpi_engine.kpi_status."""
    return kpi_status(value)


def rate(part: int, total: int) -> float | None:
    """Display percentage (rounded to 0.1). KPI totals never use this — they
    are computed from the exact values in kpi_engine."""
    return round1(_exact_ratio(part, total))


def overall_kpi(components: dict[str, float | None], weights: dict[str, float] | None = None) -> float | None:
    return round1(total_kpi(components, weights))


def weights_description(weights: dict[str, float] | None = None) -> list[dict]:
    return [{**item, "short": COMPONENT_SHORT_LABELS[item["key"]]} for item in _engine_weights_description(weights)]


__all__ = [
    "COMPONENTS",
    "COMPONENT_LABELS",
    "COMPONENT_SHORT_LABELS",
    "LEVEL_LABELS",
    "kpi_level",
    "kpi_weights",
    "overall_kpi",
    "rate",
    "weights_description",
]
