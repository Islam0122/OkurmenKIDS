"""Test results in the analytics dashboard and the KPI engine.

A result is a finished StudentAttempt of an LMS student (apps.testing),
attributed by its historical snapshot (group / teacher / subject at the
time of the attempt), dated by when it was finished. Scope follows
AnalyticsScope: the groups in scope, the selected teacher (the result's
teacher) and subject.
"""
from __future__ import annotations

from django.db.models import Avg, Count, F, Q

from .metrics import build_metric
from .period import DateRange
from .scope import AnalyticsScope


def results_qs(scope: AnalyticsScope, date_range: DateRange):
    from apps.testing.models import AttemptStatus, StudentAttempt

    qs = StudentAttempt.objects.filter(
        status=AttemptStatus.FINISHED, student__isnull=False, user__isnull=True,
        group__in=scope.groups_qs(),
        finished_at__date__gte=date_range.start, finished_at__date__lte=date_range.end,
    )
    if scope.teacher_id is not None:
        qs = qs.filter(teacher_id=scope.teacher_id)
    if scope.subject_id is not None:
        qs = qs.filter(subject_id=scope.subject_id)
    return qs


PASSED = Q(score__gte=F("session__test__passing_score"))


def counts(scope: AnalyticsScope, date_range: DateRange) -> dict:
    agg = results_qs(scope, date_range).aggregate(
        attempts=Count("pk"), passed=Count("pk", filter=PASSED), average=Avg("score"),
        students=Count("student", distinct=True),
        students_failed=Count("student", filter=~PASSED, distinct=True),
    )
    return {k: (v or 0) if k != "average" else v for k, v in agg.items()}


def _snapshot(scope: AnalyticsScope, date_range: DateRange) -> dict:
    c = counts(scope, date_range)
    trend_rows = (
        results_qs(scope, date_range).values("finished_at__date")
        .annotate(average=Avg("score")).order_by("finished_at__date")
    )
    return {
        "attempts": c["attempts"],
        "students": c["students"],
        "students_failed": c["students_failed"],
        "average_score": round(c["average"], 1) if c["average"] is not None else 0.0,
        "pass_rate": round(c["passed"] / c["attempts"] * 100, 1) if c["attempts"] else 0.0,
        "trend": [{"date": r["finished_at__date"], "percent": round(r["average"], 1)} for r in trend_rows],
    }


def build(scope: AnalyticsScope, compare_range: DateRange | None) -> dict:
    current = _snapshot(scope, scope.date_range)
    previous = _snapshot(scope, compare_range) if compare_range else None

    def metric(key: str):
        return build_metric(current[key], previous[key] if previous else None)

    return {
        "attempts": metric("attempts"),
        "students_tested": metric("students"),
        "students_below_passing": metric("students_failed"),
        "average_score": metric("average_score"),
        "pass_rate": metric("pass_rate"),
        "average_score_trend": current["trend"],
    }
