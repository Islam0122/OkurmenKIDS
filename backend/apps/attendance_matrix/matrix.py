"""The attendance & homework matrix: students × lessons for a period.

Definitions (the same as the rest of the academy — apps.assistant.activity):

* **Columns** — the group's lessons in the period, never a cancelled one
  (it never happened). Weekends and days without a lesson simply have no
  column, so they never touch the statistics.
* **Attendance** — ``Attendance.status``: PRESENT / LATE = присутствовал,
  EXCUSED = уважительная причина, ABSENT = без причины, no row = нет данных.
* **Homework** — ``HomeworkResult`` of the lesson's homework, kept apart
  from attendance: «done» once every homework of the lesson is SUBMITTED /
  CHECKED / LATE; «missed» when one is NOT_SUBMITTED or due (deadline
  passed; without a deadline — the lesson is held) with no result;
  «pending» while not due yet; «none» when the lesson has no homework.
* **Cell colour** (``code``): ``done`` (attended + homework done or not
  set), ``partial`` (attended, homework not handed in), ``excused``,
  ``absent``, ``empty`` (held, not marked), ``planned`` (a future lesson),
  ``no_lesson`` (the student was not in the group yet / any more).
* **Percent** — attended / marked (EXCUSED counts as marked), as everywhere
  in the academy's analytics.
"""
from __future__ import annotations

import calendar
import datetime as dt
from collections import defaultdict
from dataclasses import dataclass, field

from django.db.models import Q
from django.utils import timezone

from apps.academy.models import Attendance, Group, Homework, HomeworkResult, Lesson, Student, StudentStatusEvent
from apps.assistant.activity import join_dates

from . import access
from .models import MatrixSettings

ATTENDED = (Attendance.Status.PRESENT, Attendance.Status.LATE)
HW_DONE = (HomeworkResult.Status.SUBMITTED, HomeworkResult.Status.CHECKED, HomeworkResult.Status.LATE)

CELL_CODES = ("done", "partial", "excused", "absent", "empty", "planned", "no_lesson")
CELL_LABELS = {
    "done": "Присутствовал + сдал ДЗ",
    "partial": "Присутствовал (без ДЗ)",
    "excused": "Уважительная причина",
    "absent": "Не пришёл без причины",
    "empty": "Нет данных",
    "planned": "Занятие ещё не прошло",
    "no_lesson": "Нет занятия",
}
HW_LABELS = {"done": "Сдано", "missed": "Не сдано", "pending": "Ещё не срок", "none": "ДЗ не задано"}
MONTHS = (
    "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
    "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь",
)
WEEKDAYS = ("Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс")
PERIODS = ("day", "week", "month")


class MatrixError(ValueError):
    pass


def pct(part: int, whole: int) -> int | None:
    return round(part / whole * 100) if whole else None


# ---------------------------------------------------------------------------
# Period
# ---------------------------------------------------------------------------

def period_bounds(period: str, anchor: dt.date) -> tuple[dt.date, dt.date]:
    if period == "day":
        return anchor, anchor
    if period == "week":
        start = anchor - dt.timedelta(days=anchor.weekday())
        return start, start + dt.timedelta(days=6)
    if period == "month":
        start = anchor.replace(day=1)
        return start, start.replace(day=calendar.monthrange(start.year, start.month)[1])
    raise MatrixError("Неверный период.")


def parse_period(params) -> tuple[str, dt.date, dt.date]:
    """?period=day|week|month&date=YYYY-MM-DD, or ?year=&month= (a month)."""
    period = params.get("period") or "month"
    if period not in PERIODS:
        raise MatrixError("Неверный период.")
    try:
        if params.get("date"):
            anchor = dt.date.fromisoformat(params["date"])
        elif params.get("year") and params.get("month"):
            anchor = dt.date(int(params["year"]), int(params["month"]), 1)
        else:
            anchor = timezone.localdate()
    except (TypeError, ValueError):
        raise MatrixError("Неверная дата.") from None
    if not 2000 <= anchor.year <= 2100:
        raise MatrixError("Неверная дата.")
    start, end = period_bounds(period, anchor)
    return period, start, end


def period_label(period: str, start: dt.date, end: dt.date) -> str:
    if period == "month":
        return f"{MONTHS[start.month - 1]} {start.year}"
    if period == "week":
        return f"{start:%d.%m} – {end:%d.%m.%Y}"
    return f"{start:%d.%m.%Y}"


# ---------------------------------------------------------------------------
# Building blocks
# ---------------------------------------------------------------------------

def is_held(lesson: Lesson, today: dt.date) -> bool:
    return lesson.date < today or (
        lesson.date == today and lesson.status in (Lesson.Status.IN_PROGRESS, Lesson.Status.COMPLETED)
    )


def homework_status(lesson: Lesson, homeworks: list[Homework], results: dict, student_id: int, today: dt.date) -> str:
    if lesson.homework_not_required or not homeworks:
        return "none"
    statuses = []
    for hw in homeworks:
        result = results.get((hw.pk, student_id))
        if result is not None and result.status in HW_DONE:
            statuses.append("done")
            continue
        due = hw.deadline < today if hw.deadline else is_held(lesson, today)
        if (result is not None and result.status == HomeworkResult.Status.NOT_SUBMITTED) or due:
            statuses.append("missed")
        else:
            statuses.append("pending")
    if "missed" in statuses:
        return "missed"
    if "pending" in statuses:
        return "pending"
    return "done"


def cell_code(attendance: Attendance | None, hw: str, *, held: bool, editable_day: bool, enrolled: bool) -> str:
    if attendance is not None:
        if attendance.status in ATTENDED:
            return "done" if hw in ("done", "none") else "partial"
        if attendance.status == Attendance.Status.EXCUSED:
            return "excused"
        return "absent"
    if not enrolled:
        return "no_lesson"
    if held or editable_day:
        return "empty"
    return "planned"


def teacher_name(lesson: Lesson) -> str:
    teacher = lesson.effective_teacher
    return str(teacher) if teacher is not None else ""


@dataclass
class StudentStats:
    present: int = 0
    late: int = 0
    excused: int = 0
    absent: int = 0
    unmarked: int = 0
    lessons: int = 0
    hw_done: int = 0
    hw_missed: int = 0
    hw_due: int = 0
    done_cells: int = 0
    max_absence_streak: int = 0
    _streak: int = field(default=0, repr=False)

    @property
    def marked(self) -> int:
        return self.present + self.excused + self.absent

    @property
    def percent(self) -> int | None:
        return pct(self.present, self.marked)

    @property
    def hw_percent(self) -> int | None:
        return pct(self.hw_done, self.hw_due)

    def as_dict(self) -> dict:
        return {
            "present": self.present,
            "late": self.late,
            "excused": self.excused,
            "absent": self.absent,
            "unmarked": self.unmarked,
            "marked": self.marked,
            "lessons": self.lessons,
            "percent": self.percent,
            "hw_done": self.hw_done,
            "hw_missed": self.hw_missed,
            "hw_due": self.hw_due,
            "hw_percent": self.hw_percent,
            "done_cells": self.done_cells,
            "consecutive_absences": self.max_absence_streak,
        }


def warnings_for(stats: StudentStats, settings: MatrixSettings) -> list[dict]:
    out = []
    if stats.absent >= settings.monthly_absences_critical:
        out.append({"code": "absences_critical", "level": "critical", "label": f"{stats.absent} пропусков — критично"})
    elif stats.absent >= settings.monthly_absences_attention:
        out.append({"code": "absences_attention", "level": "attention", "label": f"{stats.absent} пропуска — обратить внимание"})
    if stats.max_absence_streak >= settings.consecutive_absences_warning:
        out.append({"code": "absences_in_row", "level": "warning", "label": f"{stats.max_absence_streak} пропуска подряд"})
    if stats.hw_missed >= settings.missed_homework_warning:
        out.append({"code": "homework_missed", "level": "warning", "label": f"{stats.hw_missed} несданных ДЗ"})
    return out


LEVEL_ORDER = {"critical": 3, "attention": 2, "warning": 1}


def level_of(warnings: list[dict]) -> str | None:
    if not warnings:
        return None
    return max(warnings, key=lambda w: LEVEL_ORDER[w["level"]])["level"]


def thresholds(settings: MatrixSettings) -> dict:
    return {
        "consecutive_absences_warning": settings.consecutive_absences_warning,
        "monthly_absences_attention": settings.monthly_absences_attention,
        "monthly_absences_critical": settings.monthly_absences_critical,
        "missed_homework_warning": settings.missed_homework_warning,
    }


# ---------------------------------------------------------------------------
# Core: several groups at once (bulk queries) — the matrix, the overview and
# the exports all go through here, so their numbers can never disagree.
# ---------------------------------------------------------------------------

LESSON_RELATED = ("group", "subject", "teacher__user", "group_teacher__teacher__user")


def _rosters(groups: list[Group], lessons_by_group: dict, marks_students: dict) -> dict[int, list[Student]]:
    """A group's students for the matrix: its current active / paused
    students, plus anyone with a mark or a homework result on one of its
    lessons in the period (left or transferred since — shown read-only)."""
    group_ids = [g.pk for g in groups]
    current = Student.objects.filter(group_id__in=group_ids, status__in=(Student.Status.ACTIVE, Student.Status.PAUSED))
    extra_ids = {sid for ids in marks_students.values() for sid in ids}
    students = {s.pk: s for s in current}
    for s in Student.objects.filter(pk__in=extra_ids - set(students)):
        students[s.pk] = s
    rosters: dict[int, list[Student]] = defaultdict(list)
    for s in students.values():
        for gid in group_ids:
            if s.group_id == gid or s.pk in marks_students.get(gid, ()):
                rosters[gid].append(s)
    for gid in rosters:
        rosters[gid].sort(key=lambda s: (s.last_name.lower(), s.first_name.lower()))
    return rosters


_LEAVE_EVENTS = (StudentStatusEvent.EventType.DEACTIVATED, StudentStatusEvent.EventType.COMPLETED)


def _left_dates(students: list[Student], group_id: int) -> dict[int, dt.date]:
    """The day a student stopped studying in `group_id`: transferred out of
    it, or (still listed in it) deactivated / finished — the latest such day.
    Their later lessons are «нет занятия», never «нет данных»."""
    out: dict[int, dt.date] = {}
    gone = [s for s in students if s.group_id == group_id
            and s.status in (Student.Status.WITHDRAWN, Student.Status.COMPLETED)]
    events = StudentStatusEvent.objects.filter(
        Q(student__in=students, event_type=StudentStatusEvent.EventType.TRANSFERRED, from_group_id=group_id)
        | Q(student__in=gone, event_type__in=_LEAVE_EVENTS)
    ).values("student_id", "event_date")
    for e in events:
        if e["event_date"] > out.get(e["student_id"], dt.date.min):
            out[e["student_id"]] = e["event_date"]
    return out


def compute(groups: list[Group], lessons_qs, *, today: dt.date | None = None, settings: MatrixSettings | None = None) -> dict[int, dict]:
    """{group_id: {"lessons", "students", "rows", "columns", "summary"}}."""
    today = today or timezone.localdate()
    settings = settings or MatrixSettings.load()
    lessons = list(
        lessons_qs.exclude(status=Lesson.Status.CANCELLED).select_related(*LESSON_RELATED).order_by("date", "start_time", "pk")
    )
    lessons_by_group: dict[int, list[Lesson]] = defaultdict(list)
    for lesson in lessons:
        lessons_by_group[lesson.group_id].append(lesson)

    attendance = {(a.lesson_id, a.student_id): a for a in Attendance.objects.filter(lesson__in=lessons)}
    homeworks: dict[int, list[Homework]] = defaultdict(list)
    for hw in Homework.objects.filter(lesson__in=lessons).order_by("pk"):
        homeworks[hw.lesson_id].append(hw)
    results = {
        (r.homework_id, r.student_id): r
        for r in HomeworkResult.objects.filter(homework__lesson__in=lessons).only("homework_id", "student_id", "status")
    }
    lesson_group = {lesson.pk: lesson.group_id for lesson in lessons}
    hw_lesson = {hw.pk: hw.lesson_id for items in homeworks.values() for hw in items}
    marks_students: dict[int, set[int]] = defaultdict(set)
    for (lesson_id, student_id) in attendance:
        marks_students[lesson_group[lesson_id]].add(student_id)
    for (hw_id, student_id) in results:
        marks_students[lesson_group[hw_lesson[hw_id]]].add(student_id)

    rosters = _rosters(groups, lessons_by_group, marks_students)
    out = {}
    for group in groups:
        out[group.pk] = _group_matrix(
            group, lessons_by_group.get(group.pk, []), rosters.get(group.pk, []),
            attendance, homeworks, results, today, settings,
        )
    return out


def _group_matrix(group, lessons, students, attendance, homeworks, results, today, settings) -> dict:
    joined = join_dates(students, {s.pk: group.pk for s in students}) if students else {}
    left = _left_dates(students, group.pk) if students else {}

    columns = []
    col_stats = []
    for lesson in lessons:
        held = is_held(lesson, today)
        columns.append({
            "lesson_id": lesson.pk,
            "date": lesson.date,
            "weekday": WEEKDAYS[lesson.date.weekday()],
            "start": lesson.start_time.strftime("%H:%M"),
            "end": lesson.end_time.strftime("%H:%M"),
            "lesson_number": lesson.lesson_number,
            "topic": lesson.topic,
            "subject": lesson.subject.name if lesson.subject_id else "",
            "teacher": teacher_name(lesson),
            "teacher_id": getattr(lesson.effective_teacher, "pk", None),
            "status": lesson.status,
            "held": held,
            "editable_day": lesson.date <= today,
            "has_homework": bool(homeworks.get(lesson.pk)) and not lesson.homework_not_required,
        })
        col_stats.append({"present": 0, "excused": 0, "absent": 0, "unmarked": 0, "hw_missed": 0})

    rows = []
    for student in students:
        stats = StudentStats()
        cells = []
        join = joined.get(student.pk)
        out_day = left.get(student.pk)
        for i, lesson in enumerate(lessons):
            mark = attendance.get((lesson.pk, student.pk))
            enrolled = (join is None or lesson.date >= join) and (out_day is None or lesson.date < out_day)
            if student.group_id != group.pk and mark is None:
                enrolled = enrolled and out_day is not None
            hw = homework_status(lesson, homeworks.get(lesson.pk, []), results, student.pk, today)
            if not enrolled and mark is None:
                hw = "none"
            held = columns[i]["held"]
            code = cell_code(mark, hw, held=held, editable_day=columns[i]["editable_day"], enrolled=enrolled)
            cells.append({
                "lesson_id": lesson.pk,
                "code": code,
                "attendance": mark.status if mark else None,
                "homework": hw,
                "has_comment": bool(mark and (mark.comment or mark.excuse_reason)),
            })
            # Statistics: only real lessons of this student.
            if code in ("no_lesson", "planned"):
                continue
            stats.lessons += 1
            cs = col_stats[i]
            if mark is None:
                stats.unmarked += 1
                cs["unmarked"] += 1
            elif mark.status in ATTENDED:
                stats.present += 1
                cs["present"] += 1
                if mark.status == Attendance.Status.LATE:
                    stats.late += 1
                stats._streak = 0
            elif mark.status == Attendance.Status.EXCUSED:
                stats.excused += 1
                cs["excused"] += 1
            else:
                stats.absent += 1
                cs["absent"] += 1
                stats._streak += 1
                stats.max_absence_streak = max(stats.max_absence_streak, stats._streak)
            if code == "done":
                stats.done_cells += 1
            if hw in ("done", "missed"):
                stats.hw_due += 1
                if hw == "done":
                    stats.hw_done += 1
                else:
                    stats.hw_missed += 1
                    cs["hw_missed"] += 1
        warnings = warnings_for(stats, settings)
        rows.append({
            "student": {
                "id": student.pk,
                "name": str(student),
                "status": student.status,
                "status_display": student.get_status_display(),
                "in_group": student.group_id == group.pk,
            },
            "cells": cells,
            "stats": stats.as_dict(),
            "warnings": warnings,
            "level": level_of(warnings),
        })

    for col, cs in zip(columns, col_stats):
        marked = cs["present"] + cs["excused"] + cs["absent"]
        col["stats"] = {**cs, "marked": marked, "percent": pct(cs["present"], marked)}

    return {"columns": columns, "rows": rows, "summary": summarize(rows)}


def summarize(rows: list[dict]) -> dict:
    keys = ("present", "late", "excused", "absent", "unmarked", "hw_done", "hw_missed", "hw_due", "done_cells", "lessons")
    total = {k: sum(r["stats"][k] for r in rows) for k in keys}
    marked = total["present"] + total["excused"] + total["absent"]
    return {
        **total,
        "marked": marked,
        "students": len(rows),
        "percent": pct(total["present"], marked),
        "hw_percent": pct(total["hw_done"], total["hw_due"]),
        "cards": {
            "done": {"count": total["done_cells"], "percent": pct(total["done_cells"], marked)},
            "excused": {"count": total["excused"], "percent": pct(total["excused"], marked)},
            "absent": {"count": total["absent"], "percent": pct(total["absent"], marked)},
            "hw_missed": {"count": total["hw_missed"], "percent": pct(total["hw_missed"], total["hw_due"])},
        },
        "warnings": {
            level: sum(1 for r in rows if r["level"] == level) for level in ("critical", "attention", "warning")
        },
    }


def ranking(rows: list[dict], limit: int = 10) -> list[dict]:
    ranked = [r for r in rows if r["stats"]["marked"]]
    ranked.sort(key=lambda r: (-(r["stats"]["percent"] or 0), r["stats"]["absent"], r["student"]["name"]))
    return [
        {"place": i + 1, "student": r["student"], "percent": r["stats"]["percent"],
         "present": r["stats"]["present"], "absent": r["stats"]["absent"], "hw_percent": r["stats"]["hw_percent"]}
        for i, r in enumerate(ranked[:limit])
    ]


# ---------------------------------------------------------------------------
# Public: one group's matrix
# ---------------------------------------------------------------------------

def filter_rows(rows: list[dict], params) -> list[dict]:
    student = params.get("student")
    if str(student or "").isdigit():
        rows = [r for r in rows if r["student"]["id"] == int(student)]
    query = (params.get("search") or "").strip().lower()
    if query:
        rows = [r for r in rows if query in r["student"]["name"].lower()]
    status = params.get("status")
    if status in CELL_CODES:
        rows = [r for r in rows if any(c["code"] == status for c in r["cells"])]
    homework = params.get("homework")
    if homework in ("done", "missed"):
        rows = [r for r in rows if any(c["homework"] == homework for c in r["cells"])]
    level = params.get("level")
    if level in LEVEL_ORDER:
        rows = [r for r in rows if r["level"] and LEVEL_ORDER[r["level"]] >= LEVEL_ORDER[level]]
    return rows


def group_matrix(user, group: Group, params) -> dict:
    period, start, end = parse_period(params)
    settings = MatrixSettings.load()
    lessons = access.scoped_lessons(user, [group.pk]).filter(date__gte=start, date__lte=end)
    teacher = params.get("teacher")
    if str(teacher or "").isdigit():
        from apps.academy.services.trainer_history import taught_by_q

        lessons = lessons.filter(taught_by_q(int(teacher)))
    data = compute([group], lessons, settings=settings)[group.pk]
    rows = filter_rows(data["rows"], params)
    caps = access.group_capabilities(user, group, settings)
    if access.role_of(user) == access.TEACHER and caps["can_edit"]:
        own = user.teacher_profile.pk
        for col in data["columns"]:
            col["can_edit"] = col["teacher_id"] == own
    else:
        for col in data["columns"]:
            col["can_edit"] = caps["can_edit"]
    for col in data["columns"]:
        if col["status"] == Lesson.Status.CANCELLED:
            col["can_edit"] = False

    prev_anchor = start - dt.timedelta(days=1)
    next_anchor = end + dt.timedelta(days=1)
    return {
        "group": {
            "id": group.pk,
            "name": group.name,
            "status": group.status,
            "status_display": group.get_status_display(),
            "course": group.course.name if group.course_id else "",
            "students_count": sum(1 for r in data["rows"] if r["student"]["in_group"] and r["student"]["status"] == Student.Status.ACTIVE),
        },
        "period": {
            "kind": period,
            "start": start,
            "end": end,
            "label": period_label(period, start, end),
            "prev": period_bounds(period, prev_anchor)[0],
            "next": period_bounds(period, next_anchor)[0],
        },
        "columns": data["columns"],
        "rows": rows,
        "summary": data["summary"],
        "ranking": ranking(data["rows"]),
        "thresholds": thresholds(settings),
        "capabilities": caps,
        "legend": [{"code": code, "label": CELL_LABELS[code]} for code in CELL_CODES],
        "filtered": len(rows) != len(data["rows"]),
    }


# ---------------------------------------------------------------------------
# Overview: many groups (Team Lead / Operations director / Admin)
# ---------------------------------------------------------------------------

def overview(user, params) -> dict:
    period, start, end = parse_period({**params.dict(), "period": "month"} if hasattr(params, "dict") else {**params, "period": "month"})
    settings = MatrixSettings.load()
    groups_qs = access.visible_groups(user).select_related("course")
    subject = params.get("subject")
    if str(subject or "").isdigit():
        groups_qs = groups_qs.filter(pk__in=Group.objects.filter(access.direction_q([int(subject)])).values("pk"))
    group_id = params.get("group")
    if str(group_id or "").isdigit():
        groups_qs = groups_qs.filter(pk=int(group_id))
    teacher = params.get("teacher")
    lessons = access.scoped_lessons(user, groups_qs.values("pk")).filter(date__gte=start, date__lte=end)
    if str(teacher or "").isdigit():
        from apps.academy.services.trainer_history import taught_by_q

        lessons = lessons.filter(taught_by_q(int(teacher)))
    groups_with_lessons = set(lessons.values_list("group_id", flat=True))
    groups = [g for g in groups_qs.order_by("name") if g.pk in groups_with_lessons]
    data = compute(groups, lessons, settings=settings)

    group_rows, problems, all_rows = [], [], []
    trainers: dict[int, dict] = {}
    for group in groups:
        d = data[group.pk]
        all_rows.extend(d["rows"])
        s = d["summary"]
        names = sorted({c["teacher"] for c in d["columns"] if c["teacher"]})
        group_rows.append({
            "id": group.pk,
            "name": group.name,
            "course": group.course.name if group.course_id else "",
            "status": group.status,
            "status_display": group.get_status_display(),
            "trainers": names,
            "students": s["students"],
            "lessons": sum(1 for c in d["columns"] if c["held"]),
            "percent": s["percent"],
            "hw_percent": s["hw_percent"],
            "present": s["present"],
            "excused": s["excused"],
            "absent": s["absent"],
            "unmarked": s["unmarked"],
            "hw_missed": s["hw_missed"],
            "warnings": s["warnings"],
        })
        for r in d["rows"]:
            if r["level"] in ("critical", "attention") or (r["level"] == "warning"):
                problems.append({
                    "student": r["student"],
                    "group": {"id": group.pk, "name": group.name},
                    "stats": r["stats"],
                    "warnings": r["warnings"],
                    "level": r["level"],
                })
        # Trainers: their own columns only.
        for i, col in enumerate(d["columns"]):
            tid = col["teacher_id"]
            if tid is None:
                continue
            t = trainers.setdefault(tid, {"id": tid, "name": col["teacher"], "groups": set(), "lessons": 0,
                                          "present": 0, "excused": 0, "absent": 0, "unmarked": 0,
                                          "hw_done": 0, "hw_due": 0})
            t["groups"].add(group.name)
            if col["held"]:
                t["lessons"] += 1
            for r in d["rows"]:
                cell = r["cells"][i]
                if cell["code"] in ("no_lesson", "planned"):
                    continue
                att = cell["attendance"]
                if att is None:
                    t["unmarked"] += 1
                elif att in ATTENDED:
                    t["present"] += 1
                elif att == Attendance.Status.EXCUSED:
                    t["excused"] += 1
                else:
                    t["absent"] += 1
                if cell["homework"] in ("done", "missed"):
                    t["hw_due"] += 1
                    t["hw_done"] += cell["homework"] == "done"
    trainer_rows = []
    for t in trainers.values():
        marked = t["present"] + t["excused"] + t["absent"]
        trainer_rows.append({
            **{k: v for k, v in t.items() if k != "groups"},
            "groups": sorted(t["groups"]),
            "percent": pct(t["present"], marked),
            "hw_percent": pct(t["hw_done"], t["hw_due"]),
            "fill_rate": pct(marked, marked + t["unmarked"]),
        })
    trainer_rows.sort(key=lambda t: t["name"])
    problems.sort(key=lambda p: (-LEVEL_ORDER[p["level"]], -p["stats"]["absent"], -p["stats"]["hw_missed"], p["student"]["name"]))
    group_rows.sort(key=lambda g: (g["percent"] if g["percent"] is not None else 101, g["name"]))

    summary = summarize(all_rows)
    summary["groups"] = len(groups)
    return {
        "period": {"kind": "month", "start": start, "end": end, "label": period_label("month", start, end),
                   "prev": period_bounds("month", start - dt.timedelta(days=1))[0],
                   "next": period_bounds("month", end + dt.timedelta(days=1))[0]},
        "summary": summary,
        "groups": group_rows,
        "trainers": trainer_rows,
        "problem_students": problems,
        "ranking": ranking(all_rows),
        "trend": trend(user, groups_qs, end, teacher=int(teacher) if str(teacher or "").isdigit() else None),
        "thresholds": thresholds(settings),
    }


def trend(user, groups_qs, end: dt.date, months: int = 6, teacher: int | None = None) -> list[dict]:
    """Attendance percent per month for the last `months` months up to `end`."""
    first = end.replace(day=1)
    for _ in range(months - 1):
        first = (first - dt.timedelta(days=1)).replace(day=1)
    lessons = access.scoped_lessons(user, groups_qs.values("pk")).filter(date__gte=first, date__lte=end).exclude(
        status=Lesson.Status.CANCELLED)
    if teacher:
        from apps.academy.services.trainer_history import taught_by_q

        lessons = lessons.filter(taught_by_q(teacher))
    buckets: dict[tuple[int, int], dict] = {}
    cursor = first
    while cursor <= end:
        buckets[(cursor.year, cursor.month)] = {"present": 0, "marked": 0, "absent": 0}
        cursor = (cursor.replace(day=28) + dt.timedelta(days=4)).replace(day=1)
    for row in Attendance.objects.filter(lesson__in=lessons).values("lesson__date", "status"):
        b = buckets.get((row["lesson__date"].year, row["lesson__date"].month))
        if b is None:
            continue
        b["marked"] += 1
        if row["status"] in ATTENDED:
            b["present"] += 1
        elif row["status"] == Attendance.Status.ABSENT:
            b["absent"] += 1
    return [
        {"year": y, "month": m, "label": f"{MONTHS[m - 1][:3]} {y}", "percent": pct(b["present"], b["marked"]),
         "marked": b["marked"], "absent": b["absent"]}
        for (y, m), b in buckets.items()
    ]


def overview_meta(user) -> dict:
    """Options for the overview filters — only what `user` can see."""
    from apps.academy.models import GroupTeacher
    from apps.users.models import Subject

    groups = access.visible_groups(user).order_by("name")
    group_ids = list(groups.values_list("pk", flat=True))
    subject_ids = set(
        Subject.objects.filter(
            Q(courses__groups__in=group_ids) | Q(group_assignments__group__in=group_ids) | Q(group_starts__group__in=group_ids)
        ).values_list("pk", flat=True)
    ) if group_ids else set()
    if access.role_of(user) == access.TEAM_LEAD:
        own = access.lead_subject_ids(user)
        if own:
            subject_ids &= set(own)
    teachers = (
        GroupTeacher.objects.filter(group__in=group_ids, is_active=True)
        .select_related("teacher__user").order_by("teacher__user__first_name")
    )
    seen = {}
    for gt in teachers:
        seen.setdefault(gt.teacher_id, str(gt.teacher))
    return {
        "role": access.role_of(user),
        "groups": [{"id": g.pk, "name": g.name, "status": g.status} for g in groups],
        "subjects": [{"id": s.pk, "name": s.name} for s in Subject.objects.filter(pk__in=subject_ids).order_by("name")],
        "teachers": [{"id": pk, "name": name} for pk, name in sorted(seen.items(), key=lambda x: x[1])],
    }
