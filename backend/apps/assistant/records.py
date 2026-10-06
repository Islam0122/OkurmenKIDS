"""Read-only group records for the Assistant: a group's attendance by
lesson and by student, one lesson's marks and homework, a group's homework
and one homework's results. Same definitions as apps.assistant.activity
(held lesson, attended, done, due, pending review) — nothing is written.
"""
from __future__ import annotations

import datetime as dt
from collections import defaultdict

from django.db.models import Q
from django.utils import timezone

from apps.academy.models import Attendance, Group, Homework, HomeworkResult, Lesson, Student
from apps.academy.services.lesson_status import held_q

from .activity import ATTENDED, DONE, PENDING_REVIEW

LESSON_RELATED = ("group", "teacher__user", "group_teacher__teacher__user", "subject", "room")
ATTENDANCE_STATUSES = {
    "present": Attendance.Status.PRESENT,
    "absent": Attendance.Status.ABSENT,
    "late": Attendance.Status.LATE,
    "excused": Attendance.Status.EXCUSED,
}


def _ref(obj):
    return {"id": obj.pk, "name": str(obj)} if obj is not None else None


def _pct(part: int, whole: int) -> int | None:
    return round(part / whole * 100) if whole else None


def date_range(params, today: dt.date) -> tuple[dt.date | None, dt.date | None]:
    """?period=today|week|month|all|custom (&start=&end=); default — all."""
    period = params.get("period") or "all"
    if period == "today":
        return today, today
    if period == "week":
        return today - dt.timedelta(days=today.weekday()), today
    if period == "month":
        return today.replace(day=1), today
    if period == "custom":
        try:
            start = dt.date.fromisoformat(params.get("start")) if params.get("start") else None
            end = dt.date.fromisoformat(params.get("end")) if params.get("end") else None
        except ValueError:
            return None, None
        return start, end
    return None, None


def _teacher_q(teacher_id, prefix: str = "") -> Q:
    return Q(**{f"{prefix}teacher_id": teacher_id}) | Q(
        **{f"{prefix}teacher__isnull": True, f"{prefix}group_teacher__teacher_id": teacher_id}
    )


def _held_lessons(group: Group, params, today: dt.date):
    qs = (
        Lesson.objects.filter(held_q(today), group=group).exclude(status=Lesson.Status.CANCELLED)
        .select_related(*LESSON_RELATED).order_by("-date", "-start_time")
    )
    start, end = date_range(params, today)
    if start:
        qs = qs.filter(date__gte=start)
    if end:
        qs = qs.filter(date__lte=end)
    if str(params.get("teacher") or "").isdigit():
        qs = qs.filter(_teacher_q(params["teacher"]))
    return list(qs)


def _lesson_head(lesson: Lesson) -> dict:
    return {
        "id": lesson.pk,
        "date": lesson.date,
        "start": lesson.start_time.strftime("%H:%M"),
        "end": lesson.end_time.strftime("%H:%M"),
        "lesson_number": lesson.lesson_number,
        "topic": lesson.topic,
        "subject": _ref(lesson.subject),
        "teacher": _ref(lesson.effective_teacher),
        "status": lesson.status,
        "status_display": lesson.get_status_display(),
        "group": _ref(lesson.group),
    }


# ---------------------------------------------------------------------------
# Attendance
# ---------------------------------------------------------------------------

def group_attendance(group: Group, params) -> dict:
    today = timezone.localdate()
    lessons = _held_lessons(group, params, today)
    student_id = int(params["student"]) if str(params.get("student") or "").isdigit() else None
    roster = list(Student.objects.filter(group=group, status=Student.Status.ACTIVE).order_by("last_name", "first_name"))
    roster_ids = {s.pk for s in roster}

    records = Attendance.objects.filter(lesson__in=lessons).select_related("student")
    if student_id:
        records = records.filter(student_id=student_id)
    by_lesson: dict[int, list[Attendance]] = defaultdict(list)
    for record in records:
        by_lesson[record.lesson_id].append(record)

    rows = []
    for lesson in lessons:
        marks = by_lesson[lesson.pk]
        counts = {key: sum(1 for m in marks if m.status == value) for key, value in ATTENDANCE_STATUSES.items()}
        marked_ids = {m.student_id for m in marks}
        unmarked = (0 if marked_ids else 1) if student_id else len(roster_ids - marked_ids)
        attended = counts["present"] + counts["late"]
        rows.append({
            **_lesson_head(lesson),
            **counts,
            "attended": attended,
            "marked": len(marks),
            "unmarked": unmarked,
            "percent": _pct(attended, len(marks)),
            "student_status": marks[0].status if student_id and marks else None,
        })
    status = params.get("status")
    if status in ATTENDANCE_STATUSES:
        rows = [r for r in rows if r[status]]
    elif status == "unmarked":
        rows = [r for r in rows if r["unmarked"]]

    summary = {key: sum(r[key] for r in rows) for key in ("present", "absent", "late", "excused", "marked", "unmarked")}
    summary["attended"] = summary["present"] + summary["late"]
    summary["percent"] = _pct(summary["attended"], summary["marked"])
    summary["lessons"] = len(rows)

    # Per student over the same lessons: who misses most, and in a row.
    shown = {r["id"] for r in rows}
    per_student: dict[int, list[tuple[Lesson, str]]] = defaultdict(list)
    for lesson in lessons:
        if lesson.pk not in shown:
            continue
        for mark in by_lesson[lesson.pk]:
            per_student[mark.student_id].append((lesson, mark.status))
    students = []
    for s in roster if not student_id else [s for s in roster if s.pk == student_id]:
        marks = per_student[s.pk]  # newest first
        attended = sum(1 for _, st in marks if st in ATTENDED)
        streak = 0
        for _, st in marks:
            if st == Attendance.Status.ABSENT:
                streak += 1
            elif st in ATTENDED:
                break
        students.append({
            "id": s.pk, "name": str(s),
            "attended": attended,
            "absent": sum(1 for _, st in marks if st == Attendance.Status.ABSENT),
            "late": sum(1 for _, st in marks if st == Attendance.Status.LATE),
            "marked": len(marks),
            "percent": _pct(attended, len(marks)),
            "consecutive_absences": streak,
        })
    students.sort(key=lambda r: (r["percent"] if r["percent"] is not None else 101, -r["absent"]))
    return {"summary": summary, "lessons": rows, "students": students}


def lesson_detail(lesson: Lesson) -> dict:
    roster = list(Student.objects.filter(group_id=lesson.group_id, status=Student.Status.ACTIVE).order_by("last_name", "first_name"))
    marks = {a.student_id: a for a in Attendance.objects.filter(lesson=lesson).select_related("student")}
    known = {s.pk for s in roster}
    people = roster + [a.student for sid, a in marks.items() if sid not in known]
    records = [
        {
            "student": {"id": s.pk, "name": str(s)},
            "status": marks[s.pk].status if s.pk in marks else None,
            "status_display": marks[s.pk].get_status_display() if s.pk in marks else "Не отмечен",
            "comment": marks[s.pk].comment if s.pk in marks else "",
        }
        for s in people
    ]
    attended = sum(1 for r in records if r["status"] in ATTENDED)
    marked = sum(1 for r in records if r["status"])
    homeworks = [homework_row(hw, len(roster)) for hw in lesson.homeworks.all().order_by("id")]
    return {
        **_lesson_head(lesson),
        "description": lesson.description,
        "cancellation_reason": lesson.cancellation_reason,
        "attendance": {"attended": attended, "marked": marked, "total": len(records), "percent": _pct(attended, marked)},
        "records": records,
        "homeworks": homeworks,
    }


# ---------------------------------------------------------------------------
# Homework
# ---------------------------------------------------------------------------

def _hw_status(due: bool, done: int, expected: int, pending: int) -> tuple[str, str]:
    if not due:
        return "open", "Принимается"
    # Who did not hand in after the deadline matters more than what waits for a check.
    if not expected or done < expected:
        return "missing", "Есть пропуски"
    if pending:
        return "review", "На проверке"
    return "complete", "Завершено"


def homework_row(hw: Homework, roster_size: int, results: list[HomeworkResult] | None = None) -> dict:
    today = timezone.localdate()
    results = results if results is not None else list(hw.results.all())
    done = sum(1 for r in results if r.status in DONE)
    pending = sum(1 for r in results if r.status in PENDING_REVIEW)
    checked = sum(1 for r in results if r.status == HomeworkResult.Status.CHECKED)
    expected = max(roster_size, len(results))
    due = hw.deadline is None or hw.deadline < today
    status, label = _hw_status(due, done, expected, pending)
    return {
        "id": hw.pk,
        "title": hw.title,
        "lesson": {"id": hw.lesson_id, "number": hw.lesson.lesson_number, "topic": hw.lesson.topic, "date": hw.lesson.date},
        "deadline": hw.deadline,
        "issued": hw.lesson.date,
        "done": done,
        "pending": pending,
        "checked": checked,
        "expected": expected,
        "not_done": max(expected - done, 0) if due else 0,
        "percent": _pct(done, expected),
        "due": due,
        "status": status,
        "status_display": label,
    }


def group_homework(group: Group, params) -> dict:
    today = timezone.localdate()
    lessons = _held_lessons(group, params, today)
    roster_size = Student.objects.filter(group=group, status=Student.Status.ACTIVE).count()
    homeworks = list(
        Homework.objects.filter(lesson__in=lessons).select_related("lesson").order_by("-lesson__date", "-id")
    )
    results: dict[int, list[HomeworkResult]] = defaultdict(list)
    for result in HomeworkResult.objects.filter(homework__in=homeworks):
        results[result.homework_id].append(result)
    rows = [homework_row(hw, roster_size, results[hw.pk]) for hw in homeworks]
    teacher_of = {l.pk: _ref(l.effective_teacher) for l in lessons}
    for row in rows:
        row["teacher"] = teacher_of.get(row["lesson"]["id"])
    status = params.get("status")
    if status == "review":  # same meaning as the KPI: has works waiting for a check
        rows = [r for r in rows if r["pending"]]
    elif status in ("open", "complete", "missing"):
        rows = [r for r in rows if r["status"] == status]
    due_rows = [r for r in rows if r["due"] and r["expected"]]
    return {
        "summary": {
            "total": len(rows),
            "complete": sum(1 for r in rows if r["status"] == "complete"),
            "missing": sum(1 for r in rows if r["status"] == "missing"),
            # Works waiting for the trainer's check, whatever else the homework's status says.
            "review": sum(1 for r in rows if r["pending"]),
            "open": sum(1 for r in rows if r["status"] == "open"),
            "average_percent": round(sum(r["percent"] or 0 for r in due_rows) / len(due_rows)) if due_rows else None,
        },
        "homeworks": rows,
    }


def homework_detail(hw: Homework) -> dict:
    lesson = Lesson.objects.select_related(*LESSON_RELATED).get(pk=hw.lesson_id)
    roster = list(Student.objects.filter(group_id=lesson.group_id, status=Student.Status.ACTIVE).order_by("last_name", "first_name"))
    results = {r.student_id: r for r in HomeworkResult.objects.filter(homework=hw).select_related("student")}
    known = {s.pk for s in roster}
    people = roster + [r.student for sid, r in results.items() if sid not in known]
    row = homework_row(hw, len(roster), list(results.values()))
    students = []
    for s in people:
        r = results.get(s.pk)
        if r is None:
            state, label = ("not_done", "Не сдано") if row["due"] else ("waiting", "Ожидается")
        elif r.status in PENDING_REVIEW:
            state, label = "review", r.get_status_display() + " · на проверке"
        elif r.status == HomeworkResult.Status.CHECKED:
            state, label = "done", "Проверено"
        else:
            state, label = "not_done", r.get_status_display()
        students.append({
            "student": {"id": s.pk, "name": str(s)},
            "state": state,
            "status_display": label,
            "submitted_at": r.submitted_at if r else None,
            "checked_at": r.checked_at if r else None,
            "score": r.score if r else None,
            "comment": r.comment if r else "",
        })
    order = {"not_done": 0, "review": 1, "waiting": 2, "done": 3}
    students.sort(key=lambda x: (order[x["state"]], x["student"]["name"]))
    return {
        **row,
        "description": hw.description,
        "lesson": {**row["lesson"], **_lesson_head(lesson)},
        "teacher": _ref(lesson.effective_teacher),
        "students": students,
    }
