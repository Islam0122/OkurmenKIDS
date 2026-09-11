"""Group KPIs (spec §3 GROUPS).

Status counts (`active_groups`/`paused_groups`/...) and capacity are
inherently point-in-time snapshots — there is no historical Group.status
trail (and none is being added — spec forbids new models), so both the
current and comparison snapshot read the same live status/roster: when a
comparison period is requested these fields correctly come back "stable"
rather than a fabricated trend (same reasoning as students.py's docstring).
"""
from __future__ import annotations

from django.db.models import Count, Q

from apps.academy.models import Group
from .metrics import build_metric
from .period import DateRange
from .scope import AnalyticsScope

# A group counts as "near capacity" once active students reach this share
# of max_students — mirrors students.CAPACITY_THRESHOLD and insights.py's
# "group close to capacity" alert threshold (a looser, earlier warning).
NEAR_CAPACITY_THRESHOLD = 0.9


def _snapshot(scope: AnalyticsScope, date_range: DateRange) -> dict:
    groups = list(
        scope.groups_qs().annotate(
            _active_students=Count("students", filter=Q(students__is_active=True), distinct=True)
        )
    )
    total = len(groups)
    by_status = {choice: 0 for choice in Group.Status.values}
    for group in groups:
        by_status[group.status] = by_status.get(group.status, 0) + 1

    limited = [g for g in groups if g.max_students]
    near_capacity = sum(1 for g in limited if g._active_students >= g.max_students * NEAR_CAPACITY_THRESHOLD)

    active_students_total = sum(g._active_students for g in groups)
    average_per_group = round(active_students_total / total, 1) if total else 0.0

    return {
        "total": total,
        "active": by_status.get(Group.Status.ACTIVE, 0),
        "paused": by_status.get(Group.Status.PAUSED, 0),
        "completed": by_status.get(Group.Status.COMPLETED, 0),
        "cancelled": by_status.get(Group.Status.CANCELLED, 0),
        "average_students_per_group": average_per_group,
        "near_capacity": near_capacity,
    }


def near_capacity_groups(scope: AnalyticsScope) -> list[dict]:
    """Currently-active Groups at/near capacity right now — used by
    insights.py's "group close to capacity" alert. Deliberately reads the
    live roster (not a period snapshot): capacity is a "right now" concern."""
    groups = (
        scope.groups_qs()
        .filter(status=Group.Status.ACTIVE, max_students__isnull=False)
        .annotate(_active_students=Count("students", filter=Q(students__is_active=True), distinct=True))
    )
    return [
        {
            "group_id": group.id,
            "group_name": group.name,
            "active_students": group._active_students,
            "max_students": group.max_students,
            "fill_percent": round(group._active_students / group.max_students * 100, 1),
        }
        for group in groups
        if group._active_students >= group.max_students * NEAR_CAPACITY_THRESHOLD
    ]


def build(scope: AnalyticsScope, compare_range: DateRange | None) -> dict:
    current = _snapshot(scope, scope.date_range)
    previous = _snapshot(scope, compare_range) if compare_range else None

    def metric(key: str):
        return build_metric(current[key], previous[key] if previous else None)

    return {
        "total_groups": metric("total"),
        "active_groups": metric("active"),
        "paused_groups": metric("paused"),
        "completed_groups": metric("completed"),
        "cancelled_groups": metric("cancelled"),
        "average_students_per_group": metric("average_students_per_group"),
        "groups_near_capacity": metric("near_capacity"),
    }
