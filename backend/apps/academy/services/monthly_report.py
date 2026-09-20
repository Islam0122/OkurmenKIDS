"""Monthly Teacher Report figures — computed on demand for one
(teacher, year, month), never stored (spec: "не создавай дублирующие
модели статистики" — see models.MonthlyTeacherReport, which only holds the
month it's for and the teacher's own comment).

Every figure here is derived from Lesson/Attendance/Homework/HomeworkResult/
Group the same way the Analytics Dashboard is (see .analytics), just scoped
to a single calendar month and a single teacher via `Lesson.objects.for_teacher`
— so a report only ever reflects lessons this teacher actually gives, never
another teacher's Teaching Assignment within a shared Group.
"""
from __future__ import annotations

import calendar
import datetime as dt

from django.db.models import Avg, Count, Q

from apps.users.models import Teacher

from ..models import Attendance, Group, Homework, HomeworkResult, Lesson

_ATTENDED_STATUSES = (Attendance.Status.PRESENT, Attendance.Status.LATE)
_SUBMITTED_STATUSES = (HomeworkResult.Status.SUBMITTED, HomeworkResult.Status.CHECKED, HomeworkResult.Status.LATE)


def month_bounds(year: int, month: int) -> tuple[dt.date, dt.date]:
    """The first and last calendar date of (year, month), inclusive."""
    last_day = calendar.monthrange(year, month)[1]
    return dt.date(year, month, 1), dt.date(year, month, last_day)


def _week_buckets(start: dt.date, end: dt.date) -> list[tuple[dt.date, dt.date]]:
    """The month split into consecutive 7-day windows starting on day 1 —
    "Week 1"/"Week 2"/... as the spec's mock shows them, not ISO weeks (which
    would clip at the month boundary and produce a confusing partial week 0)."""
    buckets = []
    cursor = start
    while cursor <= end:
        bucket_end = min(cursor + dt.timedelta(days=6), end)
        buckets.append((cursor, bucket_end))
        cursor = bucket_end + dt.timedelta(days=1)
    return buckets


def compute_monthly_stats(teacher: Teacher, year: int, month: int) -> dict:
    start, end = month_bounds(year, month)

    lessons_qs = Lesson.objects.for_teacher(teacher).filter(date__gte=start, date__lte=end)
    lessons_total = lessons_qs.count()
    lessons_completed = lessons_qs.filter(status=Lesson.Status.COMPLETED).count()

    attendance_qs = Attendance.objects.filter(lesson__in=lessons_qs)
    attendance_agg = attendance_qs.aggregate(
        total=Count("id"),
        present=Count("id", filter=Q(status=Attendance.Status.PRESENT)),
        late=Count("id", filter=Q(status=Attendance.Status.LATE)),
        absent=Count("id", filter=Q(status=Attendance.Status.ABSENT)),
        excused=Count("id", filter=Q(status=Attendance.Status.EXCUSED)),
    )
    attendance_total = attendance_agg["total"] or 0
    attended = (attendance_agg["present"] or 0) + (attendance_agg["late"] or 0)
    attendance_rate = round(attended / attendance_total * 100, 1) if attendance_total else 0.0

    # "Worked with" a student = actually took attendance for them on one of
    # this teacher's lessons this month — not just "currently enrolled in a
    # group this teacher happens to run" (spec: don't invent figures).
    students_count = attendance_qs.values("student_id").distinct().count()

    group_ids = lessons_qs.values_list("group_id", flat=True).distinct()
    groups_qs = Group.objects.filter(id__in=group_ids)
    groups_count = groups_qs.count()

    homework_qs = Homework.objects.filter(lesson__in=lessons_qs)
    homework_assigned = homework_qs.count()
    results_qs = HomeworkResult.objects.filter(homework__in=homework_qs)
    results_agg = results_qs.aggregate(
        total=Count("id"),
        checked=Count("id", filter=Q(status=HomeworkResult.Status.CHECKED)),
        submitted=Count("id", filter=Q(status__in=_SUBMITTED_STATUSES)),
        avg_score=Avg("score"),
    )
    results_total = results_agg["total"] or 0
    homework_checked = results_agg["checked"] or 0
    homework_submission_rate = round((results_agg["submitted"] or 0) / results_total * 100, 1) if results_total else 0.0
    average_score = round(results_agg["avg_score"], 1) if results_agg["avg_score"] is not None else None

    groups = [
        {
            "id": group.id,
            "name": group.name,
            "students_count": group.students_count,
            "lessons_count": lessons_qs.filter(group_id=group.id).count(),
        }
        for group in groups_qs.order_by("name")
    ]

    weekly_dynamics = []
    for index, (week_start, week_end) in enumerate(_week_buckets(start, end), start=1):
        week_agg = attendance_qs.filter(lesson__date__gte=week_start, lesson__date__lte=week_end).aggregate(
            total=Count("id"), attended=Count("id", filter=Q(status__in=_ATTENDED_STATUSES))
        )
        week_total = week_agg["total"] or 0
        if week_total == 0:
            continue
        weekly_dynamics.append(
            {
                "label": f"Неделя {index}",
                "percent": round((week_agg["attended"] or 0) / week_total * 100, 1),
            }
        )

    lessons_rate = round(lessons_completed / lessons_total * 100, 1) if lessons_total else 0.0
    # `None` — not a fabricated 0.0 — when nobody has a graded homework score
    # yet this month (mirrors `average_score` itself, already nullable):
    # a teacher with no reviewed homework has *no* progress figure to show,
    # which is different from a real 0% progress. Excluded from kpi_components
    # below rather than dragging kpi_total down for missing data (matches
    # services.academy_monthly_report's own handling of this exact metric —
    # both must agree, since academy_monthly_report reuses this function's
    # `kpi.total` for each teacher's row).
    student_progress_rate = round(average_score / 10 * 100, 1) if average_score is not None else None

    has_data = lessons_total > 0 or groups_count > 0
    kpi_components = [attendance_rate, homework_submission_rate, lessons_rate]
    if student_progress_rate is not None:
        kpi_components.append(student_progress_rate)
    kpi_total = round(sum(kpi_components) / len(kpi_components), 1) if has_data else 0.0

    return {
        "period": {"year": year, "month": month, "start_date": start, "end_date": end},
        "has_data": has_data,
        "lessons_total": lessons_total,
        "lessons_completed": lessons_completed,
        "students_count": students_count,
        "groups_count": groups_count,
        "attendance": {
            "total": attendance_total,
            "present": attendance_agg["present"] or 0,
            "late": attendance_agg["late"] or 0,
            "absent": attendance_agg["absent"] or 0,
            "excused": attendance_agg["excused"] or 0,
            "rate": attendance_rate,
        },
        "homework": {
            "assigned": homework_assigned,
            "checked": homework_checked,
            "submission_rate": homework_submission_rate,
            "average_score": average_score,
        },
        "groups": groups,
        "weekly_dynamics": weekly_dynamics,
        "kpi": {
            "attendance": attendance_rate,
            "homework": homework_submission_rate,
            "lessons": lessons_rate,
            "student_progress": student_progress_rate,
            "total": kpi_total,
        },
    }
