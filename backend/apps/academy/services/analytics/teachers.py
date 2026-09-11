"""Teacher KPIs (spec §3 TEACHERS).

`teachers_with_lessons`/`teachers_without_lessons`/workload are all keyed
on each Lesson's *effective* teacher (its own `teacher`, or — for
older/legacy lessons with none — its group's own `teacher`; see
Lesson.effective_teacher), via `Coalesce`, never a Group's single legacy
`teacher` field alone — a Group can have several teachers, each running
their own independent Teaching Assignment (models.GroupTeacher), and their
figures must never be mixed together (spec: Teaching Assignment isolation).
"""
from __future__ import annotations

from django.db.models import Count
from django.db.models.functions import Coalesce

from .metrics import build_metric
from .period import DateRange
from .scope import AnalyticsScope


def _workload(scope: AnalyticsScope, date_range: DateRange) -> list[dict]:
    teachers = {t.id: str(t) for t in scope.teachers_qs().select_related("user")}
    if not teachers:
        return []

    rows = (
        scope.lessons_qs(date_range=date_range)
        .annotate(eff_teacher=Coalesce("teacher_id", "group__teacher_id"))
        .values("eff_teacher")
        .annotate(lessons=Count("id"))
        .order_by("-lessons")
    )
    workload = [
        {"teacher_id": row["eff_teacher"], "teacher_name": teachers[row["eff_teacher"]], "lessons": row["lessons"]}
        for row in rows
        if row["eff_teacher"] in teachers
    ]
    return workload


def _snapshot(scope: AnalyticsScope, date_range: DateRange) -> dict:
    teachers_qs = scope.teachers_qs()
    total = teachers_qs.count()
    active = teachers_qs.filter(is_active=True).count()
    scoped_active_ids = set(teachers_qs.filter(is_active=True).values_list("id", flat=True))

    workload = _workload(scope, date_range)
    teacher_ids_with_lessons = {row["teacher_id"] for row in workload}
    lessons_total = sum(row["lessons"] for row in workload)

    teachers_with_lessons = len(teacher_ids_with_lessons)
    teachers_without_lessons = len(scoped_active_ids - teacher_ids_with_lessons)
    average_lessons_per_teacher = (
        round(lessons_total / teachers_with_lessons, 1) if teachers_with_lessons else 0.0
    )

    return {
        "total": total,
        "active": active,
        "with_lessons": teachers_with_lessons,
        "without_lessons": teachers_without_lessons,
        "average_lessons": average_lessons_per_teacher,
        "workload": workload,
    }


def build(scope: AnalyticsScope, compare_range: DateRange | None) -> dict:
    current = _snapshot(scope, scope.date_range)
    previous = _snapshot(scope, compare_range) if compare_range else None

    def metric(key: str):
        return build_metric(current[key], previous[key] if previous else None)

    return {
        "total_teachers": metric("total"),
        "active_teachers": metric("active"),
        "teachers_with_lessons": metric("with_lessons"),
        "teachers_without_lessons": metric("without_lessons"),
        "average_lessons_per_teacher": metric("average_lessons"),
        # Not comparison-wrapped: a per-teacher distribution, not a scalar.
        "teacher_workload": current["workload"],
    }
