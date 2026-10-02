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


# ---------------------------------------------------------------------------
# "Check the previous lesson's homework" context.
#
# Homework always stays attached to the lesson it was *set* in (Lesson N ->
# Homework N); it is checked at the next lesson. These helpers only give a
# lesson the context of its predecessor — they never move or reinterpret
# Homework rows. Reusable by anything that needs the same per-lesson view
# (Lesson Detail page today, a parent report later): topic/attendance of
# lesson N, homework to check = homework of lesson N-1, next homework =
# homework of lesson N.
# ---------------------------------------------------------------------------

def previous_lesson(lesson: Lesson) -> Lesson | None:
    """The lesson right before `lesson` within the same Teaching Program —
    same `group_teacher` (and therefore the same group and trainer
    sequence), the highest `lesson_number` below this one, never a
    cancelled lesson (its topic is taught by the make-up lesson, which
    carries the same lesson_number). `None` for the program's first
    lesson, or a lesson with no `group_teacher` (no sequence to look in)."""
    if not lesson.group_teacher_id:
        return None
    return (
        Lesson.objects.filter(
            group_teacher_id=lesson.group_teacher_id,
            group_id=lesson.group_id,
            lesson_number__lt=lesson.lesson_number,
        )
        .exclude(status=Lesson.Status.CANCELLED)
        .order_by("-lesson_number")
        .first()
    )


def lesson_homework(lesson: Lesson) -> Homework | None:
    """The homework set in `lesson` — the newest row if there are several,
    the same one the Lesson Detail page has always shown (`?lesson=` list,
    newest first)."""
    return Homework.objects.filter(lesson=lesson).order_by("-id").first()


def homework_to_check(lesson: Lesson) -> Homework | None:
    """The homework the trainer checks during `lesson`: the one set in the
    previous lesson of the same program, once that lesson is completed —
    completing lesson N is what hands homework N over to lesson N+1. None
    for the first lesson, when the previous lesson set no homework, or
    while it is still open."""
    previous = previous_lesson(lesson)
    if previous is None or previous.status != Lesson.Status.COMPLETED:
        return None
    return lesson_homework(previous)


def homework_results_summary(homework: Homework) -> dict:
    """Checked vs. still-pending among one Homework's recorded results."""
    agg = HomeworkResult.objects.filter(homework=homework).aggregate(
        total=Count("id"),
        checked=Count("id", filter=Q(status=HomeworkResult.Status.CHECKED)),
    )
    total = agg["total"] or 0
    checked = agg["checked"] or 0
    return {"results_total": total, "checked": checked, "pending": max(total - checked, 0)}
