"""Lesson KPIs (spec §3 LESSONS).

`lessons_today` is anchored on the real calendar "today", not the selected
period's date range — it's a live, always-current figure (like a
dashboard's "what's happening right now" line), scoped by the same
teacher/group/course/subject filters as everything else.
"""
from __future__ import annotations

import datetime as dt

from django.db.models import Count, Q
from django.db.models.functions import Coalesce

from apps.academy.models import Lesson
from .metrics import build_metric
from .period import DateRange
from .scope import AnalyticsScope


def _by_teacher(scope: AnalyticsScope, date_range: DateRange) -> list[dict]:
    teachers = {t.id: str(t) for t in scope.teachers_qs().select_related("user")}
    rows = (
        scope.lessons_qs(date_range=date_range)
        .annotate(eff_teacher=Coalesce("teacher_id", "group_teacher__teacher_id"))
        .values("eff_teacher")
        .annotate(lessons=Count("id"))
        .order_by("-lessons")
    )
    return [
        {"teacher_id": row["eff_teacher"], "teacher_name": teachers[row["eff_teacher"]], "lessons": row["lessons"]}
        for row in rows
        if row["eff_teacher"] in teachers
    ]


def _by_subject(scope: AnalyticsScope, date_range: DateRange) -> list[dict]:
    rows = (
        scope.lessons_qs(date_range=date_range)
        .exclude(subject__isnull=True)
        .values("subject_id", "subject__name")
        .annotate(lessons=Count("id"))
        .order_by("-lessons")
    )
    return [
        {"subject_id": row["subject_id"], "subject_name": row["subject__name"], "lessons": row["lessons"]}
        for row in rows
    ]


def _snapshot(scope: AnalyticsScope, date_range: DateRange) -> dict:
    agg = scope.lessons_qs(date_range=date_range).aggregate(
        total=Count("id"),
        completed=Count("id", filter=Q(status=Lesson.Status.COMPLETED)),
        cancelled=Count("id", filter=Q(status=Lesson.Status.CANCELLED)),
        planned=Count("id", filter=Q(status=Lesson.Status.PLANNED)),
    )
    total = agg["total"] or 0
    completed = agg["completed"] or 0
    return {
        "total": total,
        "completed": completed,
        "cancelled": agg["cancelled"] or 0,
        "planned": agg["planned"] or 0,
        "completion_rate": round(completed / total * 100, 1) if total else 0.0,
        "by_teacher": _by_teacher(scope, date_range),
        "by_subject": _by_subject(scope, date_range),
    }


def build(scope: AnalyticsScope, compare_range: DateRange | None, *, today: dt.date | None = None) -> dict:
    today = today or dt.date.today()
    current = _snapshot(scope, scope.date_range)
    previous = _snapshot(scope, compare_range) if compare_range else None

    def metric(key: str):
        return build_metric(current[key], previous[key] if previous else None)

    lessons_today = scope.lessons_qs(date_range=DateRange(today, today)).count()

    return {
        "lessons_today": build_metric(lessons_today, None),
        "lessons_scheduled": metric("planned"),
        "lessons_completed": metric("completed"),
        "lessons_cancelled": metric("cancelled"),
        "lesson_completion_rate": metric("completion_rate"),
        # Not comparison-wrapped: distributions, not scalars.
        "lessons_by_teacher": current["by_teacher"],
        "lessons_by_subject": current["by_subject"],
    }
