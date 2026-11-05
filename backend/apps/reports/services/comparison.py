"""Current vs previous period — the change of each *rate* metric.

Only rates and averages are compared (attendance %, homework %, average
score, test average): they are comparable between periods of the same kind
even when one of them is still running. Raw counts (lessons, absences) are
never compared — a running month would always look «worse» than a full one.
Missing data on either side → None, never a fabricated change.
"""
from __future__ import annotations

COMPARED_METRICS = ("attendance_rate", "homework_rate", "average_score", "test_average")

# Change smaller than this is «без изменений» (percentage points; score points for the 0–10 score).
STABLE_THRESHOLD = {"attendance_rate": 2.0, "homework_rate": 2.0, "average_score": 0.3, "test_average": 2.0}


def delta(current: float | None, previous: float | None) -> float | None:
    if current is None or previous is None:
        return None
    return round(current - previous, 1)


def trend(metric: str, change: float | None) -> str:
    if change is None:
        return "no_data"
    if abs(change) < STABLE_THRESHOLD.get(metric, 0):
        return "stable"
    return "up" if change > 0 else "down"


def compare(current: dict, previous: dict | None) -> dict:
    """``{metric: {"current", "previous", "change", "trend"}}`` for every compared metric."""
    result = {}
    for metric in COMPARED_METRICS:
        prev = previous.get(metric) if previous else None
        change = delta(current.get(metric), prev)
        result[metric] = {"current": current.get(metric), "previous": prev, "change": change, "trend": trend(metric, change)}
    return result
