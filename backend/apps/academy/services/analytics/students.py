"""Student KPIs (spec §3 STUDENTS).

`total`/`active`/`inactive` and the per-group capacity figures are the
roster *of the period* — enrolled students with the group and status they
had on the period's last day (services.student_roster, rebuilt from the
StudentStatusEvent ledger), never today's live `is_active` state: a past
month must show its own students, not the current ones (regression: the
September report showed October's student count). A comparison period
gets its own roster, so a real trend shows up.

`new_students` counts records created inside the range. `students_left`
is approximated as Students that are currently inactive and whose
`updated_at` falls inside the period — the closest signal the existing
schema can give to "left during this period" (toggling `is_active` always
bumps `updated_at`).
"""
from __future__ import annotations

from apps.academy.services import student_roster

from .metrics import build_metric
from .period import DateRange
from .scope import AnalyticsScope

# A group is "near/at capacity" once active students reach this share of
# `max_students` — used by groups_with_free_capacity/groups_at_capacity and
# mirrored by insights.py's "group close to capacity" alert.
CAPACITY_THRESHOLD = 1.0


def _snapshot(scope: AnalyticsScope, date_range: DateRange) -> dict:
    students_qs = scope.students_qs()
    groups = list(scope.groups_qs())
    roster = student_roster.roster_on(
        student_roster.roster_date(date_range.end), group_ids=[g.id for g in groups]
    )
    by_group = student_roster.counts_by_group(roster, date_range.start, date_range.end)
    total = len(roster)
    active = sum(1 for entry in roster.values() if entry.is_active)
    inactive = total - active

    new_students = students_qs.filter(
        created_at__date__gte=date_range.start, created_at__date__lte=date_range.end
    ).count()
    students_left = students_qs.filter(
        is_active=False, updated_at__date__gte=date_range.start, updated_at__date__lte=date_range.end
    ).count()

    limited_groups = [g for g in groups if g.max_students]
    groups_at_capacity = sum(
        1 for g in limited_groups
        if by_group.get(g.id, {}).get("active", 0) >= g.max_students * CAPACITY_THRESHOLD
    )
    groups_with_free_capacity = len(groups) - groups_at_capacity

    average_per_group = round(active / len(groups), 1) if groups else 0.0

    return {
        "total": total,
        "active": active,
        "inactive": inactive,
        "new": new_students,
        "left": students_left,
        "average_per_group": average_per_group,
        "groups_with_free_capacity": groups_with_free_capacity,
        "groups_at_capacity": groups_at_capacity,
    }


def build(scope: AnalyticsScope, compare_range: DateRange | None) -> dict:
    current = _snapshot(scope, scope.date_range)
    previous = _snapshot(scope, compare_range) if compare_range else None

    def metric(key: str):
        return build_metric(current[key], previous[key] if previous else None)

    return {
        "total_students": metric("total"),
        "active_students": metric("active"),
        "inactive_students": metric("inactive"),
        "new_students": metric("new"),
        "students_left": metric("left"),
        "average_students_per_group": metric("average_per_group"),
        "groups_with_free_capacity": metric("groups_with_free_capacity"),
        "groups_at_capacity": metric("groups_at_capacity"),
    }
