"""«Катышуу» — the attendance dashboard of ONE student (already authorised
by services.scope). Read-only: the records are the trainer's
`academy.Attendance` marks (one per student and lesson), nothing is stored or
changed here, and the rules are the ones the LMS's KPI already uses
(analytics.student_progress):

* attended = PRESENT + LATE;
* missed   = ABSENT + EXCUSED (excused is shown apart, but it is a miss);
* percent  = attended / marked — over lessons that HAVE a mark; a lesson the
  trainer has not marked is not a miss (it is counted as «unmarked»);
* cancelled lessons count for nothing;
* held lessons = the student's own non-cancelled lessons that have already
  taken place (dated before today, or completed today) — the membership
  timeline decides which of a group's lessons are the student's
  (data.lessons_between).

The streak is read straight off the marks: consecutive marked lessons,
newest first, attended (present or late); the first absent or excused mark
ends it.
"""
from __future__ import annotations

import datetime as dt
from collections import OrderedDict

from apps.academy.models import Attendance, Lesson, Student

from . import data

ATTENDED = (Attendance.Status.PRESENT, Attendance.Status.LATE)
MISSED = (Attendance.Status.ABSENT, Attendance.Status.EXCUSED)
STATUSES = tuple(Attendance.Status.values)
RULES = {
    "attended": list(ATTENDED),
    "missed": list(MISSED),
    "percent": "attended / marked",
    "unmarked_counts_as_missed": False,
    "cancelled_counts": False,
}
TREND_MONTHS = 6
WEEKS = 8


def _records(student: Student, start: dt.date | None = None, end: dt.date | None = None):
    qs = (
        Attendance.objects.filter(student=student)
        .exclude(lesson__status=Lesson.Status.CANCELLED)
        .select_related(*(f"lesson__{rel}" for rel in data.LESSON_RELATED))
    )
    if start is not None:
        qs = qs.filter(lesson__date__gte=start)
    if end is not None:
        qs = qs.filter(lesson__date__lte=end)
    return qs


def _summary(records) -> dict:
    summary = data.attendance_summary(records)
    summary["missed"] = summary["absent"] + summary["excused"]
    return summary


def _held(lesson: Lesson, today: dt.date) -> bool:
    return lesson.status != Lesson.Status.CANCELLED and (
        lesson.date < today or (lesson.date == today and lesson.status == Lesson.Status.COMPLETED)
    )


def _first_day(student: Student, today: dt.date) -> dt.date:
    first = (Attendance.objects.filter(student=student).order_by("lesson__date")
             .values_list("lesson__date", flat=True).first())
    candidates = [d for d in (student.enrollment_date, first) if d]
    return min(candidates) if candidates else today


def _streaks(records) -> dict:
    """Current and best run of attended marked lessons (newest first for the current one)."""
    ordered = sorted(records, key=lambda r: (r.lesson.date, r.lesson.start_time or dt.time.min, r.pk))
    best = run = 0
    for record in ordered:
        run = run + 1 if record.status in ATTENDED else 0
        best = max(best, run)
    current = 0
    for record in reversed(ordered):
        if record.status not in ATTENDED:
            break
        current += 1
    return {"current": current, "best": best}


def _shift_month(year: int, month: int, delta: int) -> tuple[int, int]:
    index = year * 12 + month - 1 + delta
    return index // 12, index % 12 + 1


def overview(student: Student, *, today: dt.date) -> dict:
    records = list(_records(student, end=today))
    summary = _summary(records)
    held = [l for l in data.lessons_between(student, _first_day(student, today), today) if _held(l, today)]
    marked_ids = {r.lesson_id for r in records}
    summary.update({"held": len(held), "unmarked": sum(1 for l in held if l.pk not in marked_ids)})

    months = []
    for delta in range(-(TREND_MONTHS - 1), 1):
        year, month = _shift_month(today.year, today.month, delta)
        start, end = data.month_bounds(year, month)
        months.append({"year": year, "month": month,
                       **_summary([r for r in records if start <= r.lesson.date <= end])})

    by_subject: OrderedDict[str, list] = OrderedDict()
    for record in sorted(records, key=lambda r: r.lesson.subject.name if r.lesson.subject_id else ""):
        name = record.lesson.subject.name if record.lesson.subject_id else ""
        by_subject.setdefault(name, []).append(record)
    subjects = [{"subject": name or None, **_summary(rows)} for name, rows in by_subject.items()]

    monday = today - dt.timedelta(days=today.weekday())
    weeks = []
    for back in range(WEEKS - 1, -1, -1):
        start = monday - dt.timedelta(weeks=back)
        end = start + dt.timedelta(days=6)
        weeks.append({"start": start, "end": end, **_summary([r for r in records if start <= r.lesson.date <= end])})

    return {
        "rules": RULES,
        "summary": summary,
        "streak": _streaks(records),
        "months": months,
        "subjects": subjects,
        "weeks": weeks,
        "since": _first_day(student, today),
    }


def calendar(student: Student, year: int, month: int, *, today: dt.date) -> dict:
    """Every lesson of the month that is the student's (cancelled and future
    ones included), with its mark and a display state:
    present / absent / late / excused (the mark), unmarked (took place, no
    mark yet), future, cancelled."""
    start, end = data.month_bounds(year, month)
    lessons = data.lessons_between(student, start, end)
    marks = data._attendance_map(student, lessons)
    rows = []
    for lesson in lessons:
        mark = marks.get(lesson.pk)
        if lesson.status == Lesson.Status.CANCELLED:
            state = "cancelled"
        elif mark is not None:
            state = mark.status
        elif _held(lesson, today):
            state = "unmarked"
        else:
            state = "future"
        rows.append({
            **data.lesson_row(lesson, mark, student.branch),
            "state": state,
            "comment": mark.comment if mark else "",
            "excuse_reason": mark.excuse_reason if mark else "",
        })
    marked = [marks[l.pk] for l in lessons if l.pk in marks and l.status != Lesson.Status.CANCELLED]
    return {"year": year, "month": month, "today": today, "summary": _summary(marked), "lessons": rows}


def history(student: Student, *, status: str | None, today: dt.date):
    """Marked lessons, newest first (optionally one status) — a queryset for pagination."""
    qs = _records(student, end=today).order_by("-lesson__date", "-lesson__start_time", "-pk")
    if status in STATUSES:
        qs = qs.filter(status=status)
    return qs


def history_row(record: Attendance, branch) -> dict:
    return {
        "id": record.pk,
        "status": record.status,
        "comment": record.comment,
        "excuse_reason": record.excuse_reason,
        "lesson": data.lesson_row(record.lesson, record, branch),
    }
