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
from collections import defaultdict

from django.db.models import Avg, Count, Q
from django.db.models.functions import Coalesce
from django.utils import timezone

from apps.users.models import Teacher

from ..models import Attendance, Group, HomeworkResult, Lesson, StudentStatusEvent
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
    """Per-group row for the month's "Группы" table. `lessons_count` and
    `students_count` must use the *same* definitions the report's summary
    cards do (`lessons_completed` / `students_count` above), or the table's
    totals silently disagree with the header — same reasoning as
    services.monthly_report.compute_monthly_stats's own `groups` list:
    `lessons_count` counts only COMPLETED lessons this period (never every
    Lesson regardless of status), and `students_count` is the distinct
    students who actually have an Attendance record on one of this group's
    lessons this period — never `Group.students_count` (that property is
    the group's *current* active roster, live and un-scoped by period, so
    it can disagree with what actually happened this month in either
    direction)."""
    lessons_in_range = scope.lessons_qs(date_range=date_range)
    active_group_ids = list(lessons_in_range.values_list("group_id", flat=True).distinct())
    groups = Group.objects.filter(id__in=active_group_ids).order_by("name")

    completed_lessons_by_group = dict(
        lessons_in_range.filter(status=Lesson.Status.COMPLETED)
        .values("group_id")
        .annotate(n=Count("id"))
        .values_list("group_id", "n")
    )
    students_by_group: dict[int, set] = defaultdict(set)
    for group_id, student_id in Attendance.objects.filter(lesson__in=lessons_in_range).values_list(
        "lesson__group_id", "student_id"
    ).distinct():
        students_by_group[group_id].add(student_id)

    rows = []
    for group in groups:
        rows.append(
            {
                "id": group.id,
                "name": group.name,
                "students_count": len(students_by_group.get(group.id, ())),
                "lessons_count": completed_lessons_by_group.get(group.id, 0),
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
    """`(pending_review, checked_rate, student_progress_rate)` — computed
    directly (not read off `homework.build()`'s already-rounded figures) so
    a month with zero HomeworkResult rows can honestly report
    `checked_rate=None` ("Нет данных") instead of a misleading 0%.

    `checked_rate`'s denominator is `submitted_total` (checked + submitted +
    late) — the same population `pending_review` is drawn from — never the
    full `total` (which also includes NOT_SUBMITTED rows). "Процент
    проверки" sits next to "Ожидают проверки" in the report and answers "of
    the homework that actually came in, how much has been reviewed"; a
    student who never submitted is a submission problem, not a review
    backlog, and must not silently deflate the review-completion figure by
    inflating its denominator.

    `student_progress_rate` is derived from the raw (unrounded)
    `Avg("score")` — never from a display-rounded average first (regression:
    rounding the average to one decimal *before* scaling it to a percentage
    can shift the result by a full point, e.g. a raw average of 8.26 scales
    to 82.6%, but rounding it to "8.3" first and *then* scaling gives
    round(8.3/10*100,1) = 83.0% — the two must never be chained). Round
    only once, at the very end, straight from the raw aggregate.
    """
    results_qs = homework_analytics._results_qs(scope, date_range)
    agg = results_qs.aggregate(
        checked=Count("id", filter=Q(status=HomeworkResult.Status.CHECKED)),
        submitted=Count("id", filter=Q(status=HomeworkResult.Status.SUBMITTED)),
        late=Count("id", filter=Q(status=HomeworkResult.Status.LATE)),
        avg_score=Avg("score"),
    )
    checked = agg["checked"] or 0
    pending_review = (agg["submitted"] or 0) + (agg["late"] or 0)
    submitted_total = checked + pending_review
    checked_rate = round(checked / submitted_total * 100, 1) if submitted_total else None
    raw_avg_score = agg["avg_score"]
    student_progress_rate = round(raw_avg_score / 10 * 100, 1) if raw_avg_score is not None else None
    return pending_review, checked_rate, student_progress_rate


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
    несколько раз в одной метрике"). The breakdown is a true partition of
    that same `left_count` — each departed student is attributed to exactly
    one reason bucket, their *most recent* deactivation this period — never
    grouped by (student, reason) pairs: a student who left, was reactivated,
    and left again for a *different* reason within the same month is a real
    but rare case, and counting them under both reasons would make
    `sum(breakdown[*].count) > left_count` and percentages sum past 100%,
    silently misrepresenting how many students actually left. Their final
    reason for the month is the one that describes their current departure.
    """
    events = list(
        StudentStatusEvent.objects.filter(
            event_type=StudentStatusEvent.EventType.DEACTIVATED,
            event_date__gte=date_range.start,
            event_date__lte=date_range.end,
        )
        .order_by("student_id", "-event_date", "-created_at")
        .values("student_id", "reason")
    )
    latest_reason_by_student: dict[int, str] = {}
    for event in events:
        # Ordered latest-first per student — the first row seen for a given
        # student_id is their most recent departure this period.
        latest_reason_by_student.setdefault(event["student_id"], event["reason"])

    left_count = len(latest_reason_by_student)

    reason_counts: dict[str, int] = {}
    for reason in latest_reason_by_student.values():
        reason_counts[reason] = reason_counts.get(reason, 0) + 1

    breakdown = [
        {
            "reason": reason,
            "reason_display": _reason_label(reason),
            "count": count,
            "percent": round(count / left_count * 100, 1) if left_count else 0.0,
        }
        for reason, count in sorted(reason_counts.items(), key=lambda item: -item[1])
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
    """Total/active/paused/completed/cancelled groups and how many students
    currently sit in active vs. completed ones — always the *current*
    database state (spec: "текущие метрики — не за месяц"), reusing
    `analytics.groups._snapshot` rather than a second group-counting
    implementation. Every group contributes to exactly one status bucket,
    and `total` always equals `active + paused + completed + cancelled`
    (regression: this used to report only `active`/`completed`, silently
    dropping paused/cancelled groups from the breakdown even though
    `_snapshot` already counted them — `total` then looked unreconcilable
    against the two buckets actually shown, e.g. 30 total vs. 25 active + 1
    completed with no visible home for the other 4)."""
    snapshot = _groups_snapshot(scope, date_range)
    return {
        "total": snapshot["total"],
        "active": snapshot["active"],
        "paused": snapshot["paused"],
        "completed": snapshot["completed"],
        "cancelled": snapshot["cancelled"],
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

    pending_review, checked_rate, student_progress_rate = _homework_checked_rate(scope, date_range)

    has_data = lessons_total > 0 or active_groups_count > 0

    attendance_rate = attendance_section["attendance_rate"]["value"]
    homework_submission_rate = homework_section["submission_rate"]["value"]
    lessons_rate = round(lessons_completed / lessons_total * 100, 1) if lessons_total else 0.0

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
            # `assigned` counts distinct Homework rows (one per lesson that
            # got a homework assignment this month); `checked`/`pending_review`
            # count individual HomeworkResult rows (one per enrolled student
            # per Homework) — `checked` legitimately exceeding `assigned` is
            # expected once one Homework fans out to several students, not a
            # data error (spec §9: don't assume a mismatch is a bug before
            # checking the models).
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
