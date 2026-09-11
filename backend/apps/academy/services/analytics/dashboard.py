"""The Analytics Dashboard's single entry point — assembles every domain
module's section into one payload. Nothing here is persisted; every call
recomputes from Lesson/Attendance/Homework/HomeworkResult/Student/Group/
Teacher directly (spec: "read-only and calculation-based", "Do NOT create
or restore KPI database models").

Three layers per spec §1, all folded into the one response:
- **Current Snapshot** — every metric's own `value`.
- **Period Comparison** — the same metric's `previous_value`/`change`/
  `change_percent`/`trend` (see metrics.build_metric), present whenever a
  comparison period was requested.
- **Insights/Alerts** — `insights.build`, using both the raw scope and the
  already-computed sections (so a comparison-based rule like "attendance
  decreased" doesn't redo the comparison math).
"""
from __future__ import annotations

import datetime as dt

from django.utils import timezone

from . import attendance, groups, health, homework, insights, lessons, students, teachers
from .period import resolve_comparison, resolve_period
from .scope import AnalyticsScope


def get_dashboard(
    *,
    period: str,
    start_date: dt.date | None = None,
    end_date: dt.date | None = None,
    compare: str | None = None,
    compare_start_date: dt.date | None = None,
    compare_end_date: dt.date | None = None,
    teacher_id: int | None = None,
    group_id: int | None = None,
    course_id: int | None = None,
    subject_id: int | None = None,
    today: dt.date | None = None,
) -> dict:
    today = today or timezone.localdate()
    date_range = resolve_period(period, today=today, start_date=start_date, end_date=end_date)
    compare_range = resolve_comparison(
        date_range, compare, compare_start=compare_start_date, compare_end=compare_end_date
    )

    scope = AnalyticsScope(
        date_range=date_range, teacher_id=teacher_id, group_id=group_id, course_id=course_id, subject_id=subject_id
    )

    sections = {
        "students": students.build(scope, compare_range),
        "teachers": teachers.build(scope, compare_range),
        "groups": groups.build(scope, compare_range),
        "lessons": lessons.build(scope, compare_range, today=today),
        "attendance": attendance.build(scope, compare_range),
        "homework": homework.build(scope, compare_range),
    }

    return {
        "period": {"key": period, "start_date": date_range.start, "end_date": date_range.end},
        "comparison": (
            {"key": compare, "start_date": compare_range.start, "end_date": compare_range.end}
            if compare_range is not None
            else None
        ),
        "filters": {
            "teacher_id": teacher_id,
            "group_id": group_id,
            "course_id": course_id,
            "subject_id": subject_id,
        },
        "health": health.build(sections),
        **sections,
        "insights": insights.build(scope, compare_range, sections, today=today),
    }
