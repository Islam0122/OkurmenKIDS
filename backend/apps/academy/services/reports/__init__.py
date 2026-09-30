"""📊 Reports — Overview / Groups / Teachers, plus PDF and Excel exports.

See `service.py` for how every figure is computed, `kpi.py` for the KPI
formula and its configurable weights, `filters.py` for the period/filter
vocabulary shared by every screen, endpoint and export.
"""
from .filters import PERIOD_CHOICES, ReportFilterError, ReportFilters
from .kpi import kpi_level, kpi_weights, overall_kpi
from .service import (
    build_all_student_rows,
    build_full_report,
    build_group_detail,
    build_group_rows,
    build_overview,
    build_student_rows,
    build_teacher_detail,
    build_teacher_rows,
    describe_filters,
    filter_options,
    group_student_rows,
)

__all__ = [
    "PERIOD_CHOICES",
    "ReportFilterError",
    "ReportFilters",
    "build_all_student_rows",
    "build_full_report",
    "build_group_detail",
    "build_group_rows",
    "build_overview",
    "build_student_rows",
    "build_teacher_detail",
    "build_teacher_rows",
    "describe_filters",
    "filter_options",
    "group_student_rows",
    "kpi_level",
    "kpi_weights",
    "overall_kpi",
]
