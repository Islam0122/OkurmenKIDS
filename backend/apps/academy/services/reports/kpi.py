"""The Reports section's KPI: the project's existing KPI components, with
their weights made explicit and configurable.

The KPI already exists in this project (services.monthly_report /
services.academy_monthly_report) as the plain average of four
components, each computed straight from the database:

* attendance — (present + late) / every attendance record;
* homework   — (submitted + checked + late) / every homework result;
* activity   — conducted lessons / lessons in the period (the existing
               KPI's "lessons" component);
* progress   — average homework score (0–10) scaled to % (the existing
               KPI's "student_progress" component).

Reports compute exactly those components (see services.reports.service)
and combine them here as a weighted average. The default weights are
equal (0.25 each), which reproduces the existing formula exactly; a
deployment may set `REPORTS_KPI_WEIGHTS` in settings, e.g.
``{"attendance": 0.40, "homework": 0.30, "activity": 0.20, "progress": 0.10}``.

A component with no underlying data (no attendance marked, no homework
results, no lessons due, no graded homework) is `None` — "no data", not a
fabricated 0% — and is left out, with the remaining weights renormalised
(the same rule the existing KPI already applies to `student_progress`).
"""
from __future__ import annotations

from django.conf import settings

COMPONENTS = ("attendance", "homework", "activity", "progress")

DEFAULT_WEIGHTS = {"attendance": 0.25, "homework": 0.25, "activity": 0.25, "progress": 0.25}

COMPONENT_LABELS = {
    "attendance": "Посещаемость",
    "homework": "Домашние задания",
    "activity": "Активность (проведённые занятия)",
    "progress": "Прогресс (средний балл ДЗ)",
}

COMPONENT_SHORT_LABELS = {
    "attendance": "Attendance",
    "homework": "Homework",
    "activity": "Activity",
    "progress": "Progress",
}

# KPI badge thresholds (spec: 🟢 90–100%, 🟡 75–89%, 🔴 <75%).
LEVEL_GOOD = 90
LEVEL_WARNING = 75


def kpi_weights() -> dict[str, float]:
    configured = getattr(settings, "REPORTS_KPI_WEIGHTS", None) or DEFAULT_WEIGHTS
    weights = {name: float(configured.get(name, 0) or 0) for name in COMPONENTS}
    if sum(weights.values()) <= 0:
        return dict(DEFAULT_WEIGHTS)
    return weights


def rate(part: int, total: int) -> float | None:
    return round(part / total * 100, 1) if total else None


def overall_kpi(components: dict[str, float | None], weights: dict[str, float] | None = None) -> float | None:
    """Weighted average of the components that have data; None if none do."""
    weights = weights or kpi_weights()
    present = {name: value for name, value in components.items() if value is not None and weights.get(name)}
    total_weight = sum(weights[name] for name in present)
    if not total_weight:
        return None
    return round(sum(value * weights[name] for name, value in present.items()) / total_weight, 1)


def kpi_level(value: float | None) -> str:
    """"good" / "warning" / "bad" / "none" — drives the 🟢/🟡/🔴 badges."""
    if value is None:
        return "none"
    if value >= LEVEL_GOOD:
        return "good"
    if value >= LEVEL_WARNING:
        return "warning"
    return "bad"


def weights_description(weights: dict[str, float] | None = None) -> list[dict]:
    weights = weights or kpi_weights()
    total = sum(weights.values())
    return [
        {
            "key": name,
            "label": COMPONENT_LABELS[name],
            "short": COMPONENT_SHORT_LABELS[name],
            "weight": round(weights[name] / total * 100, 1),
        }
        for name in COMPONENTS
    ]
