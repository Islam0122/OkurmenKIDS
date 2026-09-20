"""Shared Y-axis domain/tick math for the weekly-dynamics chart.

Used by both the PDF's line chart (monthly_report_pdf.py) and the Django
admin's inline SVG chart (admin_views.py) so a narrow band of real values
(e.g. 89.8-95.9%) always reads as visible variation — never flattened
against a fixed 0-100% scale, which is what made the old bar chart look
almost static for a strong month.
"""
from __future__ import annotations


def nice_domain(values: list[float]) -> tuple[float, float]:
    """A [lo, hi] range, rounded to multiples of 5 and at least 10 points
    wide, that comfortably contains every value — the chart's Y-axis."""
    if not values:
        return 0.0, 100.0
    lo = max(0.0, (min(values) // 5) * 5)
    hi = min(100.0, -(-max(values) // 5) * 5)  # ceil to nearest 5
    if hi - lo < 10:
        lo = max(0.0, lo - 5)
        hi = min(100.0, hi + 5)
        if hi - lo < 10:
            hi = min(100.0, lo + 10)
    return lo, hi


def nice_ticks(lo: float, hi: float) -> list[float]:
    """Evenly-spaced Y-axis tick values (5% or 10% steps) across [lo, hi]."""
    span = hi - lo
    step = 5 if span <= 25 else 10
    ticks = []
    value = lo
    while value <= hi + 1e-6:
        ticks.append(round(value))
        value += step
    return ticks


def ratio_in_domain(value: float, lo: float, hi: float) -> float:
    """`value`'s position within [lo, hi] as 0..1 — 0.5 when the domain is degenerate (lo == hi)."""
    if hi <= lo:
        return 0.5
    return (value - lo) / (hi - lo)
