"""Control — "did the responsible trainer fill in everything their lessons
require?" (attendance, homework, checking, scores, closing the lesson).

Operational completeness only — never a KPI; see `rules.py` for every rule
and where it comes from, `service.py` for how a period is loaded.
"""
from .rules import FILTERABLE_STATUSES, STATUS_LABELS
from .service import ControlQuery, ControlService, lesson_check, lesson_payload

__all__ = [
    "FILTERABLE_STATUSES",
    "STATUS_LABELS",
    "ControlQuery",
    "ControlService",
    "lesson_check",
    "lesson_payload",
]
