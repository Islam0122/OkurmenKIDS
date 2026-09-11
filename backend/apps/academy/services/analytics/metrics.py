"""The one place `{value, previous_value, change, change_percent, trend}` is
built — every comparable KPI in every analytics module goes through
`build_metric`, so the shape (and the rounding/zero-division rules) is
identical everywhere and lives only on the backend (spec: "Do not calculate
percentages in React. Backend must be authoritative.").

`trend` is a plain numeric direction ("up"/"down"/"stable") — it does NOT
encode whether that direction is good or bad for this particular metric
(e.g. a rising `cancelled_lessons` is "up" but bad news). That judgement is
a presentation concern the frontend makes per metric (spec §8), not
something baked into the API.
"""
from __future__ import annotations

from typing import TypedDict


class ComparisonMetric(TypedDict):
    value: float | int
    previous_value: float | int | None
    change: float | int | None
    change_percent: float | None
    trend: str  # "up" | "down" | "stable"


def build_metric(value: float | int, previous_value: float | int | None) -> ComparisonMetric:
    """`previous_value=None` means "no comparison period requested" — not
    "previous period had zero" (see the explicit zero-handling below)."""
    if previous_value is None:
        return {
            "value": value,
            "previous_value": None,
            "change": None,
            "change_percent": None,
            "trend": "stable",
        }

    change = value - previous_value
    if previous_value:
        change_percent = round(change / abs(previous_value) * 100, 1)
    else:
        # Previous period was genuinely zero: report a full swing rather
        # than an undefined/infinite percentage. Zero-to-zero is stable.
        change_percent = 100.0 if value else 0.0

    if change > 0:
        trend = "up"
    elif change < 0:
        trend = "down"
    else:
        trend = "stable"

    return {
        "value": value,
        "previous_value": previous_value,
        "change": change,
        "change_percent": change_percent,
        "trend": trend,
    }
