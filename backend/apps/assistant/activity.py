"""Read-only activity analytics for the Assistant: attendance, homework and
«Контроль активности» (who is dropping out), built on the academy's own
data and definitions — nothing here is stored:

* **Held lesson** — `services.lesson_status.held_q` (an earlier date, or
  today once started/completed), never a cancelled one.
* **Attended** — Attendance PRESENT or LATE (the analytics definition,
  services.analytics.attendance). **Absence** — ABSENT. EXCUSED is a mark
  but neither an attendance nor a «пропуск». A lesson without a mark for
  the student is «не отмечен» and never counts against them.
* **Homework done** — a HomeworkResult in SUBMITTED / CHECKED / LATE
  (services.analytics.homework); «на проверке» — SUBMITTED / LATE, handed
  in but not checked yet (services.control.rules). **Due** — the deadline
  has passed; without a deadline, once its lesson is held (the same
  «overdue» rule as Control). A homework that is not due yet never counts
  as missed.
* **Whose lessons** — only the student's current stint in their current
  group: lessons on or after the later of their enrollment date and the
  day they last joined that group (transfer / reactivation / return from
  pause, from StudentStatusEvent). Lessons from before a transfer, or of a
  group they left, are not theirs.
* **Who is analysed** — active students of active groups that have
  started. Withdrawn, paused, completed students and students without a
  group are never «problems».

Thresholds live in `settings.ASSISTANT_CONTROL_THRESHOLDS` (defaults
below), so changing them needs no code change.
"""
from __future__ import annotations

import datetime as dt
from collections import defaultdict
from dataclasses import asdict, dataclass, field

from django.conf import settings
from django.db.models import Q
from django.utils import timezone

from apps.academy.models import Attendance, Group, Homework, HomeworkResult, Lesson, Student, StudentStatusEvent
from apps.academy.services.lesson_status import held_q

ATTENDED = (Attendance.Status.PRESENT, Attendance.Status.LATE)
DONE = (HomeworkResult.Status.SUBMITTED, HomeworkResult.Status.CHECKED, HomeworkResult.Status.LATE)
PENDING_REVIEW = (HomeworkResult.Status.SUBMITTED, HomeworkResult.Status.LATE)
JOIN_EVENTS = (
    StudentStatusEvent.EventType.TRANSFERRED,
    StudentStatusEvent.EventType.REACTIVATED,
    StudentStatusEvent.EventType.CONTINUED,
)

DEFAULT_THRESHOLDS = {
    # «Норма»: attendance ≥ normal_attendance AND homework ≥ normal_homework.
    "normal_attendance": 80,
    "normal_homework": 70,
    # «Низкая активность»: attendance < low_attendance OR homework < low_homework.
    "low_attendance": 60,
    "low_homework": 40,
    # «В зоне риска»: attendance < risk_attendance AND homework < risk_homework.
    "risk_attendance": 50,
    "risk_homework": 30,
    # N absences / missed homeworks in a row — at least «Требует внимания».
    "consecutive_absences": 3,
    "consecutive_missed_homework": 3,
    # «Часто пропускают»: this many absences in the period.
    "frequent_absences": 3,
    # «Давно не сдавали ДЗ»: nothing handed in for this many days while homework was due.
    "stale_homework_days": 14,
    # Too little data to judge: fewer marked lessons / due homeworks than this.
    "min_marked_lessons": 2,
    "min_due_homework": 1,
}

STATUS_NORMAL = "normal"
STATUS_ATTENTION = "attention"
STATUS_LOW = "low"
STATUS_RISK = "risk"
STATUS_NO_DATA = "no_data"
STATUS_LABELS = {
    STATUS_NORMAL: "Норма",
    STATUS_ATTENTION: "Требует внимания",
    STATUS_LOW: "Низкая активность",
    STATUS_RISK: "В зоне риска",
    STATUS_NO_DATA: "Нет данных",
}
STATUS_ORDER = {STATUS_RISK: 0, STATUS_LOW: 1, STATUS_ATTENTION: 2, STATUS_NORMAL: 3, STATUS_NO_DATA: 4}

CATEGORIES = {
    "not_attending": "Не ходят",
    "no_homework": "Не делают ДЗ",
    "both": "Не ходят + не делают ДЗ",
    "frequent_absence": "Часто пропускают",
    "stale_homework": "Давно не сдавали ДЗ",
    "low_activity": "Низкая активность",
    "risk": "В зоне риска",
}

PERIODS = ("7d", "14d", "30d", "month", "all")


def thresholds() -> dict:
    return {**DEFAULT_THRESHOLDS, **getattr(settings, "ASSISTANT_CONTROL_THRESHOLDS", {})}


def period_start(period: str, today: dt.date) -> dt.date | None:
    if period == "7d":
        return today - dt.timedelta(days=6)
    if period == "14d":
        return today - dt.timedelta(days=13)
    if period == "month":
        return today.replace(day=1)
    if period == "all":
        return None
    return today - dt.timedelta(days=29)


def _pct(part: int, whole: int) -> int | None:
    return round(part / whole * 100) if whole else None


def _teacher_name(lesson: Lesson) -> str:
    teacher = lesson.effective_teacher
    return str(teacher) if teacher is not None else ""


def join_dates(students: list[Student]) -> dict[int, dt.date | None]:
    """The day each student started their current stint in their current group."""
    by_pk = {s.pk: s for s in students}
    latest: dict[int, dt.date] = {}
    for event in StudentStatusEvent.objects.filter(student__in=students, event_type__in=JOIN_EVENTS).values(
        "student_id", "group_id", "event_date",
    ):
        if event["group_id"] != by_pk[event["student_id"]].group_id:
            continue
        if event["event_date"] > latest.get(event["student_id"], dt.date.min):
            latest[event["student_id"]] = event["event_date"]
    joined = {}
    for s in students:
        dates = [d for d in (latest.get(s.pk), s.enrollment_date) if d is not None]
        joined[s.pk] = max(dates) if dates else None
    return joined


@dataclass
class StudentActivity:
    student_id: int
    name: str
    group: dict | None
    attendance: int | None = None
    attended: int = 0
    absent: int = 0
    late: int = 0
    excused: int = 0
    marked: int = 0
    lessons: int = 0
    consecutive_absences: int = 0
    homework: int | None = None
    homework_done: int = 0
    homework_due: int = 0
    homework_missed: int = 0
    homework_pending: int = 0
    consecutive_missed_homework: int = 0
    last_attended: dt.date | None = None
    last_lesson: dt.date | None = None
    last_teacher: str = ""
    last_homework_done: dt.date | None = None
    last_homework_done_title: str = ""
    last_homework_given: dt.date | None = None
    last_activity: dt.date | None = None
    status: str = STATUS_NO_DATA
    status_label: str = STATUS_LABELS[STATUS_NO_DATA]
    categories: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return asdict(self)


def _judge(row: StudentActivity, t: dict, today: dt.date) -> None:
    att = row.attendance if row.marked >= t["min_marked_lessons"] else None
    hw = row.homework if row.homework_due >= t["min_due_homework"] else None
    if att is None and hw is None:
        status = STATUS_NO_DATA
    elif att is not None and hw is not None and att < t["risk_attendance"] and hw < t["risk_homework"]:
        status = STATUS_RISK
    elif (att is not None and att < t["low_attendance"]) or (hw is not None and hw < t["low_homework"]):
        status = STATUS_LOW
    elif (
        (att is not None and att < t["normal_attendance"])
        or (hw is not None and hw < t["normal_homework"])
        or row.consecutive_absences >= t["consecutive_absences"]
        or row.consecutive_missed_homework >= t["consecutive_missed_homework"]
    ):
        status = STATUS_ATTENTION
    else:
        status = STATUS_NORMAL
    row.status, row.status_label = status, STATUS_LABELS[status]

    not_attending = (att is not None and att < t["low_attendance"]) or row.consecutive_absences >= t["consecutive_absences"]
    no_homework = (hw is not None and hw < t["low_homework"]) or row.consecutive_missed_homework >= t["consecutive_missed_homework"]
    stale_since = today - dt.timedelta(days=t["stale_homework_days"])
    stale = row.homework_due >= t["min_due_homework"] and (row.last_homework_done is None or row.last_homework_done < stale_since) \
        and row.last_homework_given is not None and row.last_homework_given >= stale_since
    categories = []
    if not_attending:
        categories.append("not_attending")
    if no_homework:
        categories.append("no_homework")
    if not_attending and no_homework:
        categories.append("both")
    if row.absent >= t["frequent_absences"]:
        categories.append("frequent_absence")
    if stale:
        categories.append("stale_homework")
    if status in (STATUS_LOW, STATUS_RISK):
        categories.append("low_activity")
    if status == STATUS_RISK:
        categories.append("risk")
    row.categories = categories


def analyse_students(students: list[Student], *, start: dt.date | None, today: dt.date | None = None,
                     with_timeline: bool = False, until: dt.date | None = None,
                     ) -> tuple[list[StudentActivity], dict[int, list[dict]]]:
    """Activity of `students` (each in their current group) from `start`
    (None — all time) to today — or only lessons up to `until` (a closed
    month); a homework still counts once its deadline passed before today.
    Returns the rows and, when asked, each student's timeline (newest first)."""
    today = today or timezone.localdate()
    t = thresholds()
    students = [s for s in students if s.group_id]
    joins = join_dates(students)
    group_ids = {s.group_id for s in students}

    lessons_qs = (
        Lesson.objects.filter(held_q(today), group_id__in=group_ids)
        .exclude(status=Lesson.Status.CANCELLED)
        .select_related("teacher__user", "group_teacher__teacher__user", "subject")
        .order_by("-date", "-start_time")
    )
    if start is not None:
        lessons_qs = lessons_qs.filter(date__gte=start)
    if until is not None:
        lessons_qs = lessons_qs.filter(date__lte=until)
    lessons = list(lessons_qs)
    lessons_by_group: dict[int, list[Lesson]] = defaultdict(list)
    for lesson in lessons:
        lessons_by_group[lesson.group_id].append(lesson)
    marks = {
        (a.lesson_id, a.student_id): a.status
        for a in Attendance.objects.filter(lesson__in=lessons, student__in=students).only("lesson_id", "student_id", "status")
    }
    homeworks = [
        hw for hw in Homework.objects.filter(lesson__in=lessons).select_related("lesson").order_by("-lesson__date", "-id")
        if hw.deadline is None or hw.deadline < today
    ]
    homeworks_by_group: dict[int, list[Homework]] = defaultdict(list)
    for hw in homeworks:
        homeworks_by_group[hw.lesson.group_id].append(hw)
    results = {
        (r.homework_id, r.student_id): r
        for r in HomeworkResult.objects.filter(homework__in=homeworks, student__in=students)
    }

    rows, timelines = [], {}
    for student in students:
        joined = joins.get(student.pk)
        row = StudentActivity(student_id=student.pk, name=str(student),
                              group={"id": student.group_id, "name": student.group.name})
        timeline = []
        own_lessons = [l for l in lessons_by_group[student.group_id] if joined is None or l.date >= joined]
        row.lessons = len(own_lessons)
        if own_lessons:
            row.last_lesson = own_lessons[0].date
            row.last_teacher = _teacher_name(own_lessons[0])
        streak_open = True
        for lesson in own_lessons:
            status = marks.get((lesson.pk, student.pk))
            if status is None:
                continue
            row.marked += 1
            if status in ATTENDED:
                row.attended += 1
                row.late += status == Attendance.Status.LATE
                row.last_attended = row.last_attended or lesson.date
                streak_open = False
            elif status == Attendance.Status.ABSENT:
                row.absent += 1
                if streak_open:
                    row.consecutive_absences += 1
            else:
                row.excused += 1
            if with_timeline:
                timeline.append({
                    "date": lesson.date, "kind": "attendance", "ok": status in ATTENDED,
                    "text": {Attendance.Status.PRESENT: "Был на уроке", Attendance.Status.LATE: "Опоздал",
                             Attendance.Status.ABSENT: "Не пришёл", Attendance.Status.EXCUSED: "Уважительная причина"}[status],
                    "detail": f"№{lesson.lesson_number} {lesson.subject.name if lesson.subject_id else ''}".strip(),
                    "neutral": status == Attendance.Status.EXCUSED,
                })
        row.attendance = _pct(row.attended, row.marked)

        own_homeworks = [hw for hw in homeworks_by_group[student.group_id] if joined is None or hw.lesson.date >= joined]
        row.homework_due = len(own_homeworks)
        if own_homeworks:
            row.last_homework_given = own_homeworks[0].lesson.date
        streak_open = True
        for hw in own_homeworks:
            result = results.get((hw.pk, student.pk))
            done = result is not None and result.status in DONE
            if done:
                row.homework_done += 1
                row.homework_pending += result.status in PENDING_REVIEW
                done_on = timezone.localtime(result.submitted_at).date() if result.submitted_at else hw.lesson.date
                if row.last_homework_done is None or done_on > row.last_homework_done:
                    row.last_homework_done, row.last_homework_done_title = done_on, hw.title
                streak_open = False
            else:
                row.homework_missed += 1
                if streak_open:
                    row.consecutive_missed_homework += 1
            if with_timeline:
                timeline.append({
                    "date": (timezone.localtime(result.submitted_at).date() if done and result.submitted_at else hw.deadline or hw.lesson.date),
                    "kind": "homework", "ok": done, "neutral": False,
                    "text": ("ДЗ сдано" if result.status != HomeworkResult.Status.LATE else "ДЗ сдано с опозданием") if done else "ДЗ не сдано",
                    "detail": hw.title,
                })
        row.homework = _pct(row.homework_done, row.homework_due)
        row.last_activity = max((d for d in (row.last_attended, row.last_homework_done) if d), default=None)
        _judge(row, t, today)
        rows.append(row)
        if with_timeline:
            timelines[student.pk] = sorted(timeline, key=lambda e: e["date"], reverse=True)
    return rows, timelines


def control_students(group_id: int | None = None):
    """Who «Контроль» looks at: active students of started, active groups."""
    today = timezone.localdate()
    qs = Student.objects.filter(
        status=Student.Status.ACTIVE, group__status=Group.Status.ACTIVE, group__start_date__lte=today,
    ).select_related("group")
    if group_id:
        qs = qs.filter(group_id=group_id)
    return list(qs)


SORTS = {
    "risk": lambda r: (STATUS_ORDER[r.status], r.attendance if r.attendance is not None else 101, r.homework if r.homework is not None else 101),
    "attendance": lambda r: (r.attendance if r.attendance is not None else 101, STATUS_ORDER[r.status]),
    "homework": lambda r: (r.homework if r.homework is not None else 101, STATUS_ORDER[r.status]),
    "absences": lambda r: (-r.consecutive_absences, -r.absent),
    "missed_homework": lambda r: (-r.consecutive_missed_homework, -r.homework_missed),
    "last_activity": lambda r: (r.last_activity or dt.date.min,),
}


def control_overview(params) -> dict:
    today = timezone.localdate()
    period = params.get("period") if params.get("period") in PERIODS else "30d"
    group = params.get("group")
    rows, _ = analyse_students(control_students(int(group) if str(group or "").isdigit() else None),
                               start=period_start(period, today), today=today)
    kpis = {key: sum(1 for r in rows if key in r.categories) for key in CATEGORIES}
    category = params.get("category")
    if category in CATEGORIES:
        rows = [r for r in rows if category in r.categories]
    sort = params.get("sort") if params.get("sort") in SORTS else "risk"
    rows.sort(key=SORTS[sort])
    return {
        "period": period,
        "thresholds": thresholds(),
        "kpis": kpis,
        "categories": [{"key": k, "label": v, "count": kpis[k]} for k, v in CATEGORIES.items()],
        "students": [r.as_dict() for r in rows],
        "total": len(rows),
    }


def student_profile(student: Student, period: str) -> dict:
    today = timezone.localdate()
    period = period if period in PERIODS else "30d"
    if student.group_id is None:
        return {"student": {"id": student.pk, "name": str(student)}, "activity": None, "timeline": [],
                "note": "Студент не в группе — активность не анализируется."}
    rows, timelines = analyse_students([student], start=period_start(period, today), today=today, with_timeline=True)
    note = ""
    if student.status != Student.Status.ACTIVE:
        note = f"Студент — {student.get_status_display().lower()}: в контроле не участвует."
    return {
        "student": {"id": student.pk, "name": str(student), "status": student.status, "status_display": student.get_status_display()},
        "period": period,
        "activity": rows[0].as_dict(),
        "timeline": timelines.get(student.pk, [])[:40],
        "note": note,
    }
