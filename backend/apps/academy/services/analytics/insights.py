"""Dynamic insights/alerts (spec §6) — every rule here reads live data
through the same `AnalyticsScope` (and the same Teaching-Assignment
isolation) as the rest of the dashboard; nothing is stored or scheduled,
each call recomputes from scratch.

Each insight is ``{type, title, message, metric, severity}`` — `type` is
"warning"/"critical"/"info", `severity` is "low"/"medium"/"high". A rule
that needs a comparison period (spikes/decreases) simply produces nothing
when `compare_range` is None, rather than guessing a baseline.

`students_with_3plus_consecutive_absences` here is the *pattern*-based
sibling of attendance.py's `students_with_repeated_absences` metric (which
counts 3+ absences anywhere in the period, not necessarily back-to-back) —
see that module's docstring for why the two are kept separate.
"""
from __future__ import annotations

import datetime as dt

from django.db.models import Count, Q
from django.db.models.functions import Coalesce

from apps.academy.models import Attendance, Homework, HomeworkResult, Lesson
from .attendance import _attendance_qs
from .groups import near_capacity_groups
from .period import DateRange
from .scope import AnalyticsScope

CONSECUTIVE_ABSENCE_THRESHOLD = 3
LOW_GROUP_ATTENDANCE_THRESHOLD = 60.0
LOW_GROUP_ATTENDANCE_MIN_SAMPLE = 5
LOW_TEACHER_COMPLETION_THRESHOLD = 70.0
LOW_TEACHER_COMPLETION_MIN_LESSONS = 3
CANCELLED_SPIKE_MIN_COUNT = 2
CANCELLED_SPIKE_CHANGE_PERCENT = 50.0
SIGNIFICANT_DECREASE_CHANGE_PERCENT = -5.0
SEVERE_DECREASE_CHANGE_PERCENT = -15.0


def _insight(*, type_: str, title: str, message: str, metric: str, severity: str) -> dict:
    return {"type": type_, "title": title, "message": message, "metric": metric, "severity": severity}


def _students_with_consecutive_absences(scope: AnalyticsScope, date_range: DateRange) -> list[dict]:
    qs = (
        _attendance_qs(scope, date_range)
        .select_related("student")
        .order_by("student_id", "lesson__date", "lesson__start_time")
    )

    flagged: list[dict] = []
    current_student = None
    current_name = ""
    run = 0
    max_run = 0

    def _flush():
        if current_student is not None and max_run >= CONSECUTIVE_ABSENCE_THRESHOLD:
            flagged.append({"student_id": current_student, "student_name": current_name, "streak": max_run})

    for record in qs:
        if record.student_id != current_student:
            _flush()
            current_student = record.student_id
            current_name = str(record.student)
            run = 0
            max_run = 0
        if record.status == Attendance.Status.ABSENT:
            run += 1
            max_run = max(max_run, run)
        else:
            run = 0
    _flush()
    return flagged


def _groups_with_low_attendance(scope: AnalyticsScope, date_range: DateRange) -> list[dict]:
    rows = (
        _attendance_qs(scope, date_range)
        .values("lesson__group_id", "lesson__group__name")
        .annotate(
            total=Count("id"),
            attended=Count("id", filter=Q(status__in=(Attendance.Status.PRESENT, Attendance.Status.LATE))),
        )
    )
    results = []
    for row in rows:
        if row["total"] < LOW_GROUP_ATTENDANCE_MIN_SAMPLE:
            continue
        percent = round(row["attended"] / row["total"] * 100, 1)
        if percent < LOW_GROUP_ATTENDANCE_THRESHOLD:
            results.append(
                {"group_id": row["lesson__group_id"], "group_name": row["lesson__group__name"], "attendance_percent": percent}
            )
    return results


def _teachers_with_low_completion(scope: AnalyticsScope, date_range: DateRange) -> list[dict]:
    teachers = {t.id: str(t) for t in scope.teachers_qs().select_related("user")}
    rows = (
        scope.lessons_qs(date_range=date_range)
        .annotate(eff_teacher=Coalesce("teacher_id", "group__teacher_id"))
        .values("eff_teacher")
        .annotate(
            total=Count("id"),
            completed=Count("id", filter=Q(status=Lesson.Status.COMPLETED)),
        )
    )
    results = []
    for row in rows:
        teacher_id = row["eff_teacher"]
        if teacher_id not in teachers or row["total"] < LOW_TEACHER_COMPLETION_MIN_LESSONS:
            continue
        percent = round(row["completed"] / row["total"] * 100, 1) if row["total"] else 0.0
        if percent < LOW_TEACHER_COMPLETION_THRESHOLD:
            results.append({"teacher_id": teacher_id, "teacher_name": teachers[teacher_id], "completion_rate": percent})
    return results


def _overdue_homework(scope: AnalyticsScope, today: dt.date) -> int:
    qs = Homework.objects.filter(
        lesson__group__in=scope.groups_qs(), deadline__isnull=False, deadline__lt=today,
        results__status=HomeworkResult.Status.NOT_SUBMITTED,
    )
    teacher_q = scope.lesson_teacher_q("lesson__")
    if teacher_q is not None:
        qs = qs.filter(teacher_q)
    if scope.subject_id is not None:
        qs = qs.filter(lesson__subject_id=scope.subject_id)
    return qs.distinct().count()


def build(scope: AnalyticsScope, compare_range: DateRange | None, sections: dict, *, today: dt.date) -> list[dict]:
    insights: list[dict] = []

    # -- Pattern-based: consecutive absences -----------------------------
    for row in _students_with_consecutive_absences(scope, scope.date_range):
        insights.append(
            _insight(
                type_="warning",
                title="Ученик систематически пропускает занятия",
                message=f"{row['student_name']} пропустил {row['streak']} занятий подряд.",
                metric="attendance",
                severity="high" if row["streak"] >= CONSECUTIVE_ABSENCE_THRESHOLD + 2 else "medium",
            )
        )

    # -- Groups close to capacity -----------------------------------------
    for row in near_capacity_groups(scope):
        insights.append(
            _insight(
                type_="info" if row["fill_percent"] < 100 else "warning",
                title="Группа близка к заполнению",
                message=f"«{row['group_name']}»: {row['active_students']} из {row['max_students']} мест ({row['fill_percent']}%).",
                metric="groups",
                severity="low" if row["fill_percent"] < 100 else "medium",
            )
        )

    # -- Groups with low attendance ----------------------------------------
    for row in _groups_with_low_attendance(scope, scope.date_range):
        insights.append(
            _insight(
                type_="warning",
                title="Низкая посещаемость в группе",
                message=f"«{row['group_name']}»: посещаемость {row['attendance_percent']}% за период.",
                metric="attendance_rate",
                severity="high" if row["attendance_percent"] < 40 else "medium",
            )
        )

    # -- Overdue homework -----------------------------------------------
    overdue = _overdue_homework(scope, today)
    if overdue:
        insights.append(
            _insight(
                type_="warning",
                title="Есть просроченные домашние задания",
                message=f"Домашних заданий с истёкшим сроком и несданными работами: {overdue}.",
                metric="homework",
                severity="high" if overdue >= 5 else "medium",
            )
        )

    # -- Teachers with unusually low lesson completion ----------------------
    for row in _teachers_with_low_completion(scope, scope.date_range):
        insights.append(
            _insight(
                type_="warning",
                title="Низкая доля проведённых занятий у тренера",
                message=f"{row['teacher_name']}: проведено {row['completion_rate']}% запланированных занятий.",
                metric="lesson_completion_rate",
                severity="medium",
            )
        )

    # -- Comparison-based rules (need a baseline) ---------------------------
    if compare_range is not None:
        cancelled = sections["lessons"]["lessons_cancelled"]
        if (
            cancelled["value"] >= CANCELLED_SPIKE_MIN_COUNT
            and cancelled["change_percent"] is not None
            and cancelled["change_percent"] >= CANCELLED_SPIKE_CHANGE_PERCENT
        ):
            insights.append(
                _insight(
                    type_="warning",
                    title="Рост числа отменённых занятий",
                    message=f"Отменённых занятий: {cancelled['value']} (+{cancelled['change_percent']}% к прошлому периоду).",
                    metric="lessons_cancelled",
                    severity="high" if cancelled["change_percent"] >= 100 else "medium",
                )
            )

        attendance_rate = sections["attendance"]["attendance_rate"]
        if attendance_rate["change_percent"] is not None and attendance_rate["change_percent"] <= SIGNIFICANT_DECREASE_CHANGE_PERCENT:
            insights.append(
                _insight(
                    type_="warning",
                    title="Посещаемость снизилась",
                    message=f"Посещаемость упала на {abs(attendance_rate['change_percent'])}% по сравнению с прошлым периодом.",
                    metric="attendance_rate",
                    severity="high" if attendance_rate["change_percent"] <= SEVERE_DECREASE_CHANGE_PERCENT else "medium",
                )
            )

        submission_rate = sections["homework"]["submission_rate"]
        if submission_rate["change_percent"] is not None and submission_rate["change_percent"] <= SIGNIFICANT_DECREASE_CHANGE_PERCENT:
            insights.append(
                _insight(
                    type_="warning",
                    title="Сдача домашних заданий снизилась",
                    message=f"Доля сданных ДЗ упала на {abs(submission_rate['change_percent'])}% по сравнению с прошлым периодом.",
                    metric="submission_rate",
                    severity="high" if submission_rate["change_percent"] <= SEVERE_DECREASE_CHANGE_PERCENT else "medium",
                )
            )

    return insights
