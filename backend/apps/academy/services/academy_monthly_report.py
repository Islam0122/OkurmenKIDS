"""Academy Monthly Report figures — computed on demand for one (year, month)
across the *whole* academy, never stored (see models.AcademyMonthlyReport,
which only holds the month it's for and the Admin's own comment — same
reasoning as models.MonthlyTeacherReport / services.monthly_report).

Every number here is built on top of the existing Analytics Dashboard
building blocks (services.analytics) and the Monthly Teacher Report's own
KPI formula (services.monthly_report) — never a second, independent
implementation of "what counts as active/completed/KPI/...". Where a figure
the spec asks for has no real backing data in the current schema (a lesson
"reschedule" status), the corresponding field is `None` rather than a
fabricated number — callers (serializer/PDF/frontend) render that as "Нет
данных". "Завершили обучение" *does* have real backing data (Student.status
+ StudentStatusEvent — see services.student_status) and is always
`{"count": int, "supported": True}`, never `None`: 0 real completions this
month is a fact, not missing data, and must never render as "Нет
данных"/"не поддерживается". Pausing studies remains a real, working
Student lifecycle action (services.student_status.pause_student/
continue_student) — it is simply not one of this report's metrics any
more, by design, not because the feature was removed.

Group counts (total/active/completed groups, and how many students
currently sit in each) reuse `services.analytics.groups._snapshot` — the
one existing computation of "what is a Group's current status/roster" —
rather than a second implementation here; they are always a live,
point-in-time count of the current database state (spec: "не хранить
устаревшие данные"), never scoped to the selected month.
"""
from __future__ import annotations

import datetime as dt

from django.db.models import Avg, Count, Q
from django.db.models.functions import Coalesce
from django.utils import timezone

from apps.users.models import Teacher

from ..models import Attendance, Group, HomeworkResult, StudentStatusEvent
from .analytics import homework as homework_analytics
from .analytics import insights as insights_analytics
from .analytics.attendance import build as build_attendance_section
from .analytics.groups import _snapshot as _groups_snapshot
from .analytics.homework import build as build_homework_section
from .analytics.lessons import build as build_lessons_section
from .analytics.period import DateRange
from .analytics.scope import AnalyticsScope
from .analytics.students import build as build_students_section
from .analytics.teachers import build as build_teachers_section
from .monthly_report import _week_buckets, compute_monthly_stats, month_bounds

_ATTENDED_STATUSES = (Attendance.Status.PRESENT, Attendance.Status.LATE)


def _group_attendance_rate(group_id: int, date_range: DateRange) -> float:
    agg = Attendance.objects.filter(
        lesson__group_id=group_id, lesson__date__gte=date_range.start, lesson__date__lte=date_range.end
    ).aggregate(total=Count("id"), attended=Count("id", filter=Q(status__in=_ATTENDED_STATUSES)))
    total = agg["total"] or 0
    return round((agg["attended"] or 0) / total * 100, 1) if total else 0.0


def _groups_breakdown(scope: AnalyticsScope, date_range: DateRange) -> list[dict]:
    active_group_ids = list(
        scope.lessons_qs(date_range=date_range).values_list("group_id", flat=True).distinct()
    )
    groups = Group.objects.filter(id__in=active_group_ids).order_by("name")

    rows = []
    for group in groups:
        lessons_count = scope.lessons_qs(date_range=date_range).filter(group_id=group.id).count()
        rows.append(
            {
                "id": group.id,
                "name": group.name,
                "students_count": group.students_count,
                "lessons_count": lessons_count,
                "attendance_rate": _group_attendance_rate(group.id, date_range),
                "status": group.status,
                "status_display": group.get_status_display(),
            }
        )
    return rows


def _teachers_breakdown(scope: AnalyticsScope, date_range: DateRange, year: int, month: int) -> list[dict]:
    rows = (
        scope.lessons_qs(date_range=date_range)
        .annotate(eff_teacher=Coalesce("teacher_id", "group_teacher__teacher_id"))
        .values_list("eff_teacher", flat=True)
        .distinct()
    )
    teacher_ids = [teacher_id for teacher_id in rows if teacher_id is not None]
    teachers = Teacher.objects.filter(id__in=teacher_ids).select_related("user")

    result = []
    for teacher in teachers:
        stats = compute_monthly_stats(teacher, year, month)
        result.append(
            {
                "id": teacher.id,
                "name": str(teacher),
                "lessons_completed": stats["lessons_completed"],
                "students_count": stats["students_count"],
                "attendance_rate": stats["attendance"]["rate"],
                # No comparative ranking (spec: never "best/worst teacher") —
                # a plain per-teacher figure, `None` only when this teacher
                # genuinely has no data this month.
                "kpi_total": stats["kpi"]["total"] if stats["has_data"] else None,
            }
        )
    result.sort(key=lambda row: row["name"])
    return result


def _weekly_dynamics(start: dt.date, end: dt.date) -> list[dict]:
    weeks = []
    for index, (week_start, week_end) in enumerate(_week_buckets(start, end), start=1):
        agg = Attendance.objects.filter(lesson__date__gte=week_start, lesson__date__lte=week_end).aggregate(
            total=Count("id"), attended=Count("id", filter=Q(status__in=_ATTENDED_STATUSES))
        )
        total = agg["total"] or 0
        if total == 0:
            continue
        weeks.append({"label": f"Неделя {index}", "percent": round((agg["attended"] or 0) / total * 100, 1)})
    return weeks


def _homework_checked_rate(scope: AnalyticsScope, date_range: DateRange) -> tuple[int, float | None, float | None]:
    """`(pending_review, checked_rate)` — computed directly (not read off
    `homework.build()`'s already-rounded figures) so a month with zero
    HomeworkResult rows can honestly report `checked_rate=None` ("Нет
    данных") instead of a misleading 0%."""
    results_qs = homework_analytics._results_qs(scope, date_range)
    agg = results_qs.aggregate(
        total=Count("id"),
        checked=Count("id", filter=Q(status=HomeworkResult.Status.CHECKED)),
        submitted=Count("id", filter=Q(status=HomeworkResult.Status.SUBMITTED)),
        late=Count("id", filter=Q(status=HomeworkResult.Status.LATE)),
        avg_score=Avg("score"),
    )
    total = agg["total"] or 0
    pending_review = (agg["submitted"] or 0) + (agg["late"] or 0)
    checked_rate = round((agg["checked"] or 0) / total * 100, 1) if total else None
    average_score = round(agg["avg_score"], 1) if agg["avg_score"] is not None else None
    return pending_review, checked_rate, average_score


def _attention_items(
    scope: AnalyticsScope, date_range: DateRange, lessons_section: dict, pending_review: int
) -> list[dict]:
    """Neutral, count-based "requires attention" bullets — reusing the
    Analytics Dashboard's own established thresholds (never invented here):
    `insights.LOW_GROUP_ATTENDANCE_THRESHOLD`/`CONSECUTIVE_ABSENCE_THRESHOLD`.
    Each bullet only appears when its count is greater than zero."""
    items: list[dict] = []

    low_attendance_groups = insights_analytics._groups_with_low_attendance(scope, date_range)
    if low_attendance_groups:
        n = len(low_attendance_groups)
        items.append(
            {
                "type": "attendance",
                "message": (
                    f"{n} "
                    + _pluralize_group(n)
                    + f" имеют посещаемость ниже установленного порога ({insights_analytics.LOW_GROUP_ATTENDANCE_THRESHOLD:g}%)."
                ),
            }
        )

    if pending_review:
        items.append(
            {"type": "homework", "message": f"{pending_review} домашних заданий ожидают проверки."}
        )

    streak_students = insights_analytics._students_with_consecutive_absences(scope, date_range)
    if streak_students:
        n = len(streak_students)
        items.append(
            {
                "type": "attendance",
                "message": f"{n} " + _pluralize_student(n) + " отсутствовали на нескольких занятиях подряд.",
            }
        )

    cancelled = lessons_section["lessons_cancelled"]["value"]
    if cancelled:
        items.append(
            {"type": "lessons", "message": f"{cancelled} " + _pluralize_lesson(cancelled) + " имеют статус «Отменено»."}
        )

    return items


def _pluralize_group(n: int) -> str:
    mod10, mod100 = n % 10, n % 100
    if mod10 == 1 and mod100 != 11:
        return "группа"
    if 2 <= mod10 <= 4 and not (10 <= mod100 <= 20):
        return "группы"
    return "групп"


def _pluralize_student(n: int) -> str:
    mod10, mod100 = n % 10, n % 100
    if mod10 == 1 and mod100 != 11:
        return "студент"
    if 2 <= mod10 <= 4 and not (10 <= mod100 <= 20):
        return "студента"
    return "студентов"


def _reason_label(reason: str) -> str:
    return dict(StudentStatusEvent.Reason.choices).get(reason, reason or "—")


def _departures(date_range: DateRange) -> tuple[int, list[dict]]:
    """`(left_count, reason_breakdown)` — from confirmed StudentStatusEvent
    deactivation records only (spec §7: "Считать только подтверждённые
    deactivation events"), using the event's own `event_date` (spec: "Реальную
    дату события"), never `Student.updated_at` (which a group change or any
    other edit also bumps).

    `left_count` is distinct students (spec: "не считать одного студента
    несколько раз в одной метрике"); the breakdown counts distinct students
    per reason too, so a student who left and came back and left again for a
    *different* reason within the same month is never silently folded into
    one bucket — an edge case, not the common path, but still never a
    fabricated total.
    """
    events = StudentStatusEvent.objects.filter(
        event_type=StudentStatusEvent.EventType.DEACTIVATED,
        event_date__gte=date_range.start,
        event_date__lte=date_range.end,
    )
    left_count = events.values("student_id").distinct().count()

    reason_rows = events.values("reason").annotate(n=Count("student_id", distinct=True)).order_by("-n")
    breakdown = [
        {
            "reason": row["reason"],
            "reason_display": _reason_label(row["reason"]),
            "count": row["n"],
            "percent": round(row["n"] / left_count * 100, 1) if left_count else 0.0,
        }
        for row in reason_rows
    ]
    return left_count, breakdown


def _distinct_students_with_event(event_type: str, date_range: DateRange) -> int:
    return (
        StudentStatusEvent.objects.filter(
            event_type=event_type,
            event_date__gte=date_range.start,
            event_date__lte=date_range.end,
        )
        .values("student_id")
        .distinct()
        .count()
    )


def _completed_count(date_range: DateRange) -> dict:
    """Students who completed their education *this month* — real
    StudentStatusEvent-backed data (see services.student_status), never
    inferred from a Group's own status (spec: "не считай завершившими всех
    студентов завершённой группы без проверки существующего правила"; this
    project's actual completion rule is the explicit "Завершить обучение"
    action, independent of any Group.status change). `{"count", "supported"}`:
    `supported` is always True (a real, working action backs this), `count`
    is 0 — not `None` — when nobody completed this month; "0" and "not
    supported" must never be confused."""
    completed = _distinct_students_with_event(StudentStatusEvent.EventType.COMPLETED, date_range)
    return {"count": completed, "supported": True}


def _group_stats(scope: AnalyticsScope, date_range: DateRange) -> dict:
    """Total/active/completed groups and how many students currently sit in
    each — always the *current* database state (spec: "текущие метрики —
    не за месяц"), reusing `analytics.groups._snapshot` rather than a second
    group-counting implementation. A completed group is never counted as
    active: each group contributes to exactly one status bucket."""
    snapshot = _groups_snapshot(scope, date_range)
    return {
        "total": snapshot["total"],
        "active": snapshot["active"],
        "completed": snapshot["completed"],
        "students_active": snapshot["students_in_active_groups"],
        "students_completed": snapshot["students_in_completed_groups"],
    }


def _pluralize_lesson(n: int) -> str:
    mod10, mod100 = n % 10, n % 100
    if mod10 == 1 and mod100 != 11:
        return "занятие"
    if 2 <= mod10 <= 4 and not (10 <= mod100 <= 20):
        return "занятия"
    return "занятий"


def compute_academy_monthly_stats(year: int, month: int) -> dict:
    start, end = month_bounds(year, month)
    date_range = DateRange(start, end)
    scope = AnalyticsScope(date_range=date_range)
    today = timezone.localdate()

    students_section = build_students_section(scope, None)
    teachers_section = build_teachers_section(scope, None)
    lessons_section = build_lessons_section(scope, None, today=today)
    attendance_section = build_attendance_section(scope, None)
    homework_section = build_homework_section(scope, None)

    active_groups_count = (
        scope.lessons_qs(date_range=date_range).values_list("group_id", flat=True).distinct().count()
    )
    lessons_completed = lessons_section["lessons_completed"]["value"]
    lessons_total = scope.lessons_qs(date_range=date_range).count()

    pending_review, checked_rate, avg_score = _homework_checked_rate(scope, date_range)

    has_data = lessons_total > 0 or active_groups_count > 0

    attendance_rate = attendance_section["attendance_rate"]["value"]
    homework_submission_rate = homework_section["submission_rate"]["value"]
    lessons_rate = round(lessons_completed / lessons_total * 100, 1) if lessons_total else 0.0
    student_progress_rate = round(avg_score / 10 * 100, 1) if avg_score is not None else None

    kpi_components = [attendance_rate, homework_submission_rate, lessons_rate]
    if student_progress_rate is not None:
        kpi_components.append(student_progress_rate)
    kpi_total = round(sum(kpi_components) / len(kpi_components), 1) if has_data else 0.0

    attention = _attention_items(scope, date_range, lessons_section, pending_review)
    left_count, reason_breakdown = _departures(date_range)
    completed = _completed_count(date_range)
    group_stats = _group_stats(scope, date_range)

    return {
        "period": {"year": year, "month": month, "start_date": start, "end_date": end},
        "has_data": has_data,
        "students_count": students_section["active_students"]["value"],
        "groups_count": active_groups_count,
        "teachers_count": teachers_section["teachers_with_lessons"]["value"],
        "lessons_completed": lessons_completed,
        "attendance": {
            "total": (
                attendance_section["present_count"]["value"]
                + attendance_section["absent_count"]["value"]
                + attendance_section["late_count"]["value"]
                + attendance_section["excused_count"]["value"]
            ),
            "rate": attendance_rate,
            "present": attendance_section["present_count"]["value"],
            "absent": attendance_section["absent_count"]["value"],
            "late": attendance_section["late_count"]["value"],
            "excused": attendance_section["excused_count"]["value"],
        },
        "students": {
            "active": students_section["active_students"]["value"],
            "new": students_section["new_students"]["value"],
            "left": left_count,
            "completed": completed["count"],
        },
        "group_stats": group_stats,
        "groups": _groups_breakdown(scope, date_range),
        "teachers": _teachers_breakdown(scope, date_range, year, month),
        "lessons": {
            "scheduled": lessons_section["lessons_scheduled"]["value"],
            "completed": lessons_completed,
            "cancelled": lessons_section["lessons_cancelled"]["value"],
            "rescheduled": None,
            "attendance_rate": attendance_rate,
        },
        "homework": {
            "assigned": homework_section["homework_count"]["value"],
            "checked": homework_section["checked_count"]["value"],
            "pending_review": pending_review,
            "checked_rate": checked_rate,
        },
        "weekly_dynamics": _weekly_dynamics(start, end),
        "kpi": {
            "attendance": attendance_rate,
            "homework": homework_submission_rate,
            "lessons": lessons_rate,
            "student_progress": student_progress_rate,
            "total": kpi_total,
        },
        "movement": {
            "left": left_count,
            "completed": completed,
            "active_groups": group_stats["active"],
            "completed_groups": group_stats["completed"],
            "reasons": reason_breakdown,
        },
        "attention": attention,
    }
