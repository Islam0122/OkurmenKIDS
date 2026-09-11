"""Homework KPIs (spec §3 HOMEWORK).

Every count here is over HomeworkResult rows that already exist (mirrors
the pre-redesign AnalyticsService's `homework` section) — `submission_rate`
answers "of the results that came in, how many were actually turned in",
not "of every student who could have submitted, how many did" (that
denominator question belongs to `homework_completion_percent`-style group
figures, deliberately not duplicated here to keep this module about the
Homework/HomeworkResult tables themselves).
"""
from __future__ import annotations

from django.db.models import Avg, Count, Q

from apps.academy.models import Homework, HomeworkResult
from .metrics import build_metric
from .period import DateRange
from .scope import AnalyticsScope

_SUBMITTED_STATUSES = (HomeworkResult.Status.SUBMITTED, HomeworkResult.Status.CHECKED, HomeworkResult.Status.LATE)


def _homeworks_qs(scope: AnalyticsScope, date_range: DateRange):
    qs = Homework.objects.filter(
        lesson__group__in=scope.groups_qs(), lesson__date__gte=date_range.start, lesson__date__lte=date_range.end
    )
    teacher_q = scope.lesson_teacher_q("lesson__")
    if teacher_q is not None:
        qs = qs.filter(teacher_q)
    if scope.subject_id is not None:
        qs = qs.filter(lesson__subject_id=scope.subject_id)
    return qs


def _results_qs(scope: AnalyticsScope, date_range: DateRange):
    qs = HomeworkResult.objects.filter(
        homework__lesson__group__in=scope.groups_qs(),
        homework__lesson__date__gte=date_range.start,
        homework__lesson__date__lte=date_range.end,
    )
    teacher_q = scope.lesson_teacher_q("homework__lesson__")
    if teacher_q is not None:
        qs = qs.filter(teacher_q)
    if scope.subject_id is not None:
        qs = qs.filter(homework__lesson__subject_id=scope.subject_id)
    return qs


def _snapshot(scope: AnalyticsScope, date_range: DateRange) -> dict:
    homeworks_qs = _homeworks_qs(scope, date_range)
    results_qs = _results_qs(scope, date_range)

    agg = results_qs.aggregate(
        total=Count("id"),
        submitted=Count("id", filter=Q(status=HomeworkResult.Status.SUBMITTED)),
        checked=Count("id", filter=Q(status=HomeworkResult.Status.CHECKED)),
        late=Count("id", filter=Q(status=HomeworkResult.Status.LATE)),
        not_submitted=Count("id", filter=Q(status=HomeworkResult.Status.NOT_SUBMITTED)),
        avg_score=Avg("score"),
    )
    total_results = agg["total"] or 0
    submitted_total = (agg["submitted"] or 0) + (agg["checked"] or 0) + (agg["late"] or 0)

    by_date_rows = (
        results_qs.values("homework__lesson__date")
        .annotate(total=Count("id"), submitted=Count("id", filter=Q(status__in=_SUBMITTED_STATUSES)))
        .order_by("homework__lesson__date")
    )
    trend = [
        {
            "date": row["homework__lesson__date"],
            "percent": round(row["submitted"] / row["total"] * 100, 1) if row["total"] else 0.0,
        }
        for row in by_date_rows
    ]

    return {
        "count": homeworks_qs.count(),
        "submitted": agg["submitted"] or 0,
        "not_submitted": agg["not_submitted"] or 0,
        "checked": agg["checked"] or 0,
        "late": agg["late"] or 0,
        "submission_rate": round(submitted_total / total_results * 100, 1) if total_results else 0.0,
        "average_score": round(agg["avg_score"], 1) if agg["avg_score"] is not None else 0.0,
        "trend": trend,
    }


def build(scope: AnalyticsScope, compare_range: DateRange | None) -> dict:
    current = _snapshot(scope, scope.date_range)
    previous = _snapshot(scope, compare_range) if compare_range else None

    def metric(key: str):
        return build_metric(current[key], previous[key] if previous else None)

    return {
        "homework_count": metric("count"),
        "submitted_count": metric("submitted"),
        "not_submitted_count": metric("not_submitted"),
        "checked_count": metric("checked"),
        "late_count": metric("late"),
        "submission_rate": metric("submission_rate"),
        "average_score": metric("average_score"),
        # Not comparison-wrapped: a day-by-day series, not a scalar.
        "homework_completion_trend": current["trend"],
    }
