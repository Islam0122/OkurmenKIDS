"""Real, backend-calculated "how did this lesson go" numbers — attendance
breakdown and homework-results breakdown — the one place these are
computed, for the API's LessonSerializer (the completed Lesson Detail
page's "Итоги занятия" KPI section) to read from.

Every count here comes from an actual query against Attendance/HomeworkResult
rows; nothing is invented or estimated client-side. `total_students` reuses
`Group.students_count` (the same active-student count already used
everywhere else in the app) rather than a second definition of it.
"""
from __future__ import annotations

from django.db.models import Avg, Count, Q

from ..models import Attendance, Homework, HomeworkResult, Lesson


def attendance_summary(lesson: Lesson) -> dict:
    """Present/absent/late/excused among this lesson's *active* students,
    plus the attendance rate (present+late, out of however many are
    actually marked) — `None` when nothing has been marked yet, rather than
    a misleading 0%."""
    total_students = lesson.group.students_count
    agg = Attendance.objects.filter(lesson=lesson, student__is_active=True).aggregate(
        present=Count("id", filter=Q(status=Attendance.Status.PRESENT)),
        absent=Count("id", filter=Q(status=Attendance.Status.ABSENT)),
        late=Count("id", filter=Q(status=Attendance.Status.LATE)),
        excused=Count("id", filter=Q(status=Attendance.Status.EXCUSED)),
        marked=Count("id"),
    )
    present = agg["present"] or 0
    late = agg["late"] or 0
    marked = agg["marked"] or 0
    attendance_rate = round(100 * (present + late) / marked, 1) if marked else None
    return {
        "total_students": total_students,
        "present": present,
        "absent": agg["absent"] or 0,
        "late": late,
        "excused": agg["excused"] or 0,
        "attendance_rate": attendance_rate,
    }


def homework_summary(lesson: Lesson) -> dict | None:
    """`None` when this lesson has no Homework at all (nothing to summarize —
    the frontend shows "ДЗ не требуется"/"не добавлено" from the Lesson's
    own `homework_not_required`/`homework_added` fields instead). Otherwise
    the real per-student grading breakdown across all of this lesson's
    Homework rows (in practice always one) — checked vs. still-pending
    among the results actually recorded, and the average score among the
    ones that have one."""
    if not Homework.objects.filter(lesson=lesson).exists():
        return None

    agg = HomeworkResult.objects.filter(homework__lesson=lesson).aggregate(
        total=Count("id"),
        checked=Count("id", filter=Q(status=HomeworkResult.Status.CHECKED)),
        avg_score=Avg("score"),
    )
    total = agg["total"] or 0
    checked = agg["checked"] or 0
    avg_score = agg["avg_score"]
    return {
        "results_total": total,
        "checked": checked,
        "pending": max(total - checked, 0),
        "average_score": round(avg_score, 1) if avg_score is not None else None,
    }
