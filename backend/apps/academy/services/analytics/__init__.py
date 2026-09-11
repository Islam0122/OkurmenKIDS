"""Analytics/KPI dashboard — read-only, calculation-based, nothing persisted.

Public entry point: ``get_dashboard(...)``. See ``dashboard.py`` for the
full parameter list and response shape, ``period.py``/``PERIOD_CHOICES``/
``COMPARE_CHOICES`` for the period+comparison vocabulary, and each domain
module (students/teachers/groups/lessons/attendance/homework/insights/
health) for how its own section is computed.
"""
from .dashboard import get_dashboard
from .health import build as build_health
from .metrics import ComparisonMetric, build_metric
from .period import COMPARE_CHOICES, PERIOD_CHOICES, DateRange, resolve_comparison, resolve_period
from .scope import AnalyticsScope

__all__ = [
    "get_dashboard",
    "build_health",
    "ComparisonMetric",
    "build_metric",
    "COMPARE_CHOICES",
    "PERIOD_CHOICES",
    "DateRange",
    "resolve_comparison",
    "resolve_period",
    "AnalyticsScope",
]
