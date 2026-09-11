"""Attendance KPIs (spec §3 ATTENDANCE).

`students_with_repeated_absences` here is a *frequency* metric — students
with 3+ ABSENT records anywhere in the period, not necessarily on
consecutive Lessons. The *pattern*-based version ("3+ Lessons in a row"),
which is what spec §6 lists as an insight example, lives in insights.py —
the two intentionally answer different questions (see that module's
docstring).
"""
from __future__ import annotations

from django.db.models import Count, Q

from apps.academy.models import Attendance
from .metrics import build_metric
from .period import DateRange
from .scope import AnalyticsScope

_ATTENDED_STATUSES = (Attendance.Status.PRESENT, Attendance.Status.LATE)

# 3+ absences anywhere in the period counts as "repeated" — mirrors the
# "3+ consecutive absences" threshold insights.py uses for the stricter,
# pattern-based alert.
REPEATED_ABSENCE_THRESHOLD = 3


def _attendance_qs(scope: AnalyticsScope, date_range: DateRange):
    qs = Attendance.objects.filter(
        lesson__group__in=scope.groups_qs(), lesson__date__gte=date_range.start, lesson__date__lte=date_range.end
    )
    teacher_q = scope.lesson_teacher_q("lesson__")
    if teacher_q is not None:
        qs = qs.filter(teacher_q)
    if scope.subject_id is not None:
        qs = qs.filter(lesson__subject_id=scope.subject_id)
    return qs


def _snapshot(scope: AnalyticsScope, date_range: DateRange) -> dict:
    qs = _attendance_qs(scope, date_range)
    agg = qs.aggregate(
        total=Count("id"),
        present=Count("id", filter=Q(status=Attendance.Status.PRESENT)),
        absent=Count("id", filter=Q(status=Attendance.Status.ABSENT)),
        late=Count("id", filter=Q(status=Attendance.Status.LATE)),
        excused=Count("id", filter=Q(status=Attendance.Status.EXCUSED)),
    )
    total = agg["total"] or 0
    attended = (agg["present"] or 0) + (agg["late"] or 0)

    by_date_rows = (
        qs.values("lesson__date")
        .annotate(total=Count("id"), attended=Count("id", filter=Q(status__in=_ATTENDED_STATUSES)))
        .order_by("lesson__date")
    )
    trend = [
        {
            "date": row["lesson__date"],
            "percent": round(row["attended"] / row["total"] * 100, 1) if row["total"] else 0.0,
        }
        for row in by_date_rows
    ]

    repeated_absences = (
        qs.filter(status=Attendance.Status.ABSENT)
        .values("student_id")
        .annotate(absences=Count("id"))
        .filter(absences__gte=REPEATED_ABSENCE_THRESHOLD)
        .count()
    )

    return {
        "total": total,
        "present": agg["present"] or 0,
        "absent": agg["absent"] or 0,
        "late": agg["late"] or 0,
        "excused": agg["excused"] or 0,
        "rate": round(attended / total * 100, 1) if total else 0.0,
        "repeated_absences": repeated_absences,
        "trend": trend,
    }


def build(scope: AnalyticsScope, compare_range: DateRange | None) -> dict:
    current = _snapshot(scope, scope.date_range)
    previous = _snapshot(scope, compare_range) if compare_range else None

    def metric(key: str):
        return build_metric(current[key], previous[key] if previous else None)

    return {
        "attendance_rate": metric("rate"),
        "present_count": metric("present"),
        "absent_count": metric("absent"),
        "late_count": metric("late"),
        "excused_count": metric("excused"),
        "students_with_repeated_absences": metric("repeated_absences"),
        # Not comparison-wrapped: a day-by-day series, not a scalar.
        "attendance_trend": current["trend"],
    }
