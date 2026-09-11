"""Student KPIs (spec §3 STUDENTS).

`new_students`/`students_left` are the only two metrics here that are
genuinely period-bound (they read `created_at`/`updated_at` within the
range). `total`/`active`/`inactive`/capacity are inherently point-in-time
snapshots — the Student model has no historical/audit trail (and none is
being added — spec forbids new models), so there is no way to know what
they *were* as of a past date. Rather than fabricate a plausible-looking
history, both the current and comparison snapshot read the same live
`is_active` state: when a comparison period is requested, these fields
correctly come back "stable" (identical value/previous_value) instead of a
misleading trend — an honest limitation, not a bug.

`students_left` is approximated as Students that are currently inactive
and whose `updated_at` falls inside the period — the closest signal the
existing schema can give to "left during this period" (toggling
`is_active` always bumps `updated_at`).
"""
from __future__ import annotations

from django.db.models import Count, Q

from .metrics import build_metric
from .period import DateRange
from .scope import AnalyticsScope

# A group is "near/at capacity" once active students reach this share of
# `max_students` — used by groups_with_free_capacity/groups_at_capacity and
# mirrored by insights.py's "group close to capacity" alert.
CAPACITY_THRESHOLD = 1.0


def _snapshot(scope: AnalyticsScope, date_range: DateRange) -> dict:
    students_qs = scope.students_qs()
    total = students_qs.count()
    active = students_qs.filter(is_active=True).count()
    inactive = total - active

    new_students = students_qs.filter(
        created_at__date__gte=date_range.start, created_at__date__lte=date_range.end
    ).count()
    students_left = students_qs.filter(
        is_active=False, updated_at__date__gte=date_range.start, updated_at__date__lte=date_range.end
    ).count()

    groups = list(
        scope.groups_qs().annotate(
            _active_students=Count("students", filter=Q(students__is_active=True), distinct=True)
        )
    )
    limited_groups = [g for g in groups if g.max_students]
    groups_at_capacity = sum(
        1 for g in limited_groups if g._active_students >= g.max_students * CAPACITY_THRESHOLD
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
