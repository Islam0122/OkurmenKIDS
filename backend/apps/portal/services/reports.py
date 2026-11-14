"""Monthly report for parents — one student, one calendar month.

Every figure is the KPI's own per-student computation
(analytics.student_progress.student_progress_detail — held lessons only,
membership-aware, "no data" instead of a fake 0 %), run for each group the
student belonged to that month and pooled. XP is the leaderboard's
(services.data.xp_for), comments are the trainers' own (services.data
.teacher_feedback). Nothing is stored: the same month always gives the same
report, and a corrected mark changes it on the next request.
"""
from __future__ import annotations

import datetime as dt
from collections import OrderedDict

from apps.academy.models import Attendance, Group, HomeworkResult, Student
from apps.academy.services.analytics.student_progress import student_progress_detail

from . import data

_SUMMED = ("lessons_held", "attendance_marked", "attended", "late", "absences", "excused",
           "homework_due", "homework_done", "scored_count", "tests_count")
_DONE = (HomeworkResult.Status.SUBMITTED, HomeworkResult.Status.CHECKED, HomeworkResult.Status.LATE)


def _pct(part, total):
    return round(part / total * 100, 1) if total else None


def _avg(values):
    return round(sum(values) / len(values), 1) if values else None


def _month_detail(student: Student, start: dt.date, end: dt.date, today: dt.date) -> dict:
    """Pooled figures, lessons and tests of the month over all of the
    student's groups."""
    figures = {key: 0 for key in _SUMMED}
    lessons, tests, scores = [], [], []
    for group in Group.objects.filter(pk__in=data._group_ids(student)):
        detail = student_progress_detail(
            group, student.pk, period="custom", start_date=start, end_date=min(end, today), today=today,
        ) if start <= today else None
        if not detail:
            continue
        row = detail["student"]
        for key in _SUMMED:
            figures[key] += row[key] or 0
        for lesson in detail["lessons"]:
            lessons.append({**lesson, "group": group.name})
            scores.extend(hw["score"] for hw in lesson["homework"] if hw["score"] is not None)
        tests.extend(detail["tests"])
    lessons.sort(key=lambda lesson: (lesson["date"], lesson["lesson_number"] or 0))
    tests.sort(key=lambda test: test["date"] or dt.date.min)
    figures.update({
        "attendance_rate": _pct(figures["attended"], figures["attendance_marked"]),
        "homework_rate": _pct(figures["homework_done"], figures["homework_due"]),
        "average_score": _avg(scores),
        "test_average": _avg([t["score"] for t in tests]),
    })
    return {"figures": figures, "lessons": lessons, "tests": tests}


def _subjects(lessons: list[dict]) -> list[dict]:
    by_subject: OrderedDict[str, dict] = OrderedDict()
    for lesson in lessons:
        name = lesson["subject"] or "—"
        row = by_subject.setdefault(name, {"subject": name, "lessons": 0, "marked": 0, "attended": 0,
                                           "homework_due": 0, "homework_done": 0, "scores": []})
        row["lessons"] += 1
        if lesson["attendance"]:
            row["marked"] += 1
            row["attended"] += lesson["attendance"] in (Attendance.Status.PRESENT, Attendance.Status.LATE)
        for hw in lesson["homework"]:
            row["homework_due"] += 1
            row["homework_done"] += hw["status"] in _DONE
            if hw["score"] is not None:
                row["scores"].append(hw["score"])
    return [
        {
            "subject": row["subject"],
            "lessons": row["lessons"],
            "attendance_rate": _pct(row["attended"], row["marked"]),
            "homework_rate": _pct(row["homework_done"], row["homework_due"]),
            "average_score": _avg(row["scores"]),
        }
        for row in by_subject.values()
    ]


def _shift(year: int, month: int, delta: int) -> tuple[int, int]:
    index = year * 12 + (month - 1) + delta
    return index // 12, index % 12 + 1


def monthly_report(student: Student, year: int, month: int, *, today: dt.date) -> dict:
    start, end = data.month_bounds(year, month)
    if start > today:
        from django.core.exceptions import ValidationError

        raise ValidationError({"detail": "Этот месяц ещё не начался."})
    current = _month_detail(student, start, end, today)
    figures = current["figures"]

    trend = []
    for delta in range(-5, 1):
        y, m = _shift(year, month, delta)
        m_start, m_end = data.month_bounds(y, m)
        detail = current if delta == 0 else _month_detail(student, m_start, m_end, today)
        trend.append({
            "year": y, "month": m,
            "attendance_rate": detail["figures"]["attendance_rate"],
            "homework_rate": detail["figures"]["homework_rate"],
            "average_score": detail["figures"]["average_score"],
            "xp": data.xp_for(student, m_start, min(m_end, today))["total"] if m_start <= today else 0,
        })
    previous = trend[-2]

    def change(key):
        now, before = figures[key], previous[key]
        return None if now is None or before is None else round(now - before, 1)

    xp = data.xp_for(student, start, min(end, today))
    return {
        "student": data.student_card(student),
        "period": {"year": year, "month": month, "start": start, "end": end, "is_complete": end < today},
        "attendance": {
            "percent": figures["attendance_rate"],
            "total_lessons": figures["lessons_held"],
            "marked": figures["attendance_marked"],
            "attended": figures["attended"],
            "missed": figures["absences"],
            "late": figures["late"],
            "excused": figures["excused"],
        },
        "homework": {
            "assigned": figures["homework_due"],
            "completed": figures["homework_done"],
            "completion_rate": figures["homework_rate"],
            "average_score": figures["average_score"],
            "scored_count": figures["scored_count"],
        },
        "tests": {"count": len(current["tests"]), "average": figures["test_average"], "items": current["tests"]},
        "progress": {
            "subjects": _subjects(current["lessons"]),
            "change": {key: change(key) for key in ("attendance_rate", "homework_rate", "average_score")},
        },
        "xp": xp,
        "comments": data.teacher_feedback(student, limit=20, start=start, end=end),
        "trend": trend,
        "lessons": current["lessons"],
        "generated_at": dt.datetime.now(dt.timezone.utc),
    }
