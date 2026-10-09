"""Retention analytics of the monthly report: inactive students, departures
and why they happen, month-over-month and the
retention advice. Read only; every number comes from existing records.

Kept apart on purpose:

* **Inactive** — a student still *active* on the month's last day (status
  rebuilt from the ledger, see history.py) who shows no real activity:
  no attended lesson (present / late) and no handed-in homework for N days,
  while marked absent from lessons held meanwhile (an unmarked lesson or a
  group without lessons is no inactivity). Inactive is not «ушёл».
* **Departed** — a DEACTIVATED event dated in the month (one per student
  even if they left twice). Completion (COMPLETED) and pause are counted
  separately — a graduate or a paused student did not churn.
* **Returned** — a later REACTIVATED event of the same student.

Day thresholds: `settings.ASSISTANT_INACTIVITY_DAYS` (default 7 / 14 / 30).
"""
from __future__ import annotations

import datetime as dt
from collections import Counter, defaultdict

from django.conf import settings
from django.db.models import Max, OuterRef, Q, Subquery
from django.utils import timezone

from apps.academy.models import Attendance, GroupTeacher, HomeworkResult, Lesson, Student, StudentStatusEvent
from apps.academy.services.lesson_status import held_q

from . import activity
from .history import StudentOn

E = StudentStatusEvent.EventType
REASON_LABELS = dict(StudentStatusEvent.Reason.choices)
UNKNOWN = StudentStatusEvent.UNKNOWN_REASON_LABEL
DEFAULT_INACTIVITY_DAYS = (7, 14, 30)

# What the academy can do about a reason — advice only where an action exists.
REASON_ADVICE = {
    "financial_issues": "Обсудить с руководством варианты для семей с финансовыми трудностями.",
    "transport": "Предлагать при записи группу ближе к дому или удобную по времени дороги.",
    "schedule": "Проверить расписание групп, откуда уходят из-за времени занятий; предлагать перевод в другую группу.",
    "disliked_classes": "Разобрать с тренерами содержание занятий в группах, откуда уходят.",
    "disliked_teacher": "Передать Team Lead отзывы о работе тренера в этих группах.",
    "no_interest": "Проводить беседы со студентами, у которых падает активность, — до ухода.",
    "low_motivation": "Раньше реагировать на пропуски: звонок родителям после 2–3 пропусков подряд.",
    "other_academy": "Выяснять у ушедших, чем привлекла другая академия.",
}


def inactivity_days() -> tuple[int, int, int]:
    days = tuple(getattr(settings, "ASSISTANT_INACTIVITY_DAYS", DEFAULT_INACTIVITY_DAYS))
    return days if len(days) == 3 else DEFAULT_INACTIVITY_DAYS


def _pct(part: int, whole: int) -> int | None:
    return round(part / whole * 100) if whole else None


def _students_word(n: int) -> str:
    tail = "студент" if n % 10 == 1 and n % 100 != 11 else (
        "студента" if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14 else "студентов")
    return f"{n} {tail}"


NO_GROUP = "Без группы"
WATCH_ONLY = ("Наблюдать", "Наблюдать, напомнить о занятиях")


def reason_label(code: str) -> str:
    return REASON_LABELS.get(code) or UNKNOWN


def trainers_by_group(group_ids, until: dt.date, since: dt.date | None = None) -> dict[int, str]:
    """Who taught each group around `until`: the trainers of its held lessons
    in [since, until] (default: the 60 days before), else its assigned ones."""
    group_ids = set(group_ids)
    since = since or until - dt.timedelta(days=60)
    names: dict[int, list[str]] = defaultdict(list)
    lessons = (
        Lesson.objects.filter(held_q(until + dt.timedelta(days=1)), group_id__in=group_ids, date__gte=since, date__lte=until)
        .exclude(status=Lesson.Status.CANCELLED)
        .select_related("teacher__user", "group_teacher__teacher__user").order_by("-date")
    )
    for lesson in lessons:
        teacher = lesson.effective_teacher
        if teacher is not None and str(teacher) not in names[lesson.group_id]:
            names[lesson.group_id].append(str(teacher))
    missing = group_ids - set(names)
    if missing:
        for gt in GroupTeacher.objects.filter(group_id__in=missing, is_active=True).select_related("teacher__user"):
            if str(gt.teacher) not in names[gt.group_id]:
                names[gt.group_id].append(str(gt.teacher))
    return {gid: ", ".join(sorted(n)) for gid, n in names.items()}


def teacher_group_ids(teacher_id: int, start: dt.date, end: dt.date) -> set[int]:
    """Groups a trainer taught in the period (their lessons) or is assigned to."""
    lesson_groups = Lesson.objects.filter(date__gte=start, date__lte=end).filter(
        Q(teacher_id=teacher_id) | Q(teacher__isnull=True, group_teacher__teacher_id=teacher_id),
    ).values_list("group_id", flat=True)
    assigned = GroupTeacher.objects.filter(teacher_id=teacher_id).values_list("group_id", flat=True)
    return set(lesson_groups) | set(assigned)


# ---------------------------------------------------------------------------
# Inactive students
# ---------------------------------------------------------------------------

def last_activity(student_ids, until: dt.date) -> tuple[dict[int, dt.date], dict[int, dt.date]]:
    """Last attended held lesson and last handed-in homework of each student, up to `until`."""
    attended = dict(
        Attendance.objects.filter(
            student_id__in=student_ids, status__in=activity.ATTENDED, lesson__date__lte=until,
        ).exclude(lesson__status=Lesson.Status.CANCELLED)
        .values_list("student_id").annotate(d=Max("lesson__date"))
    )
    submitted = dict(
        HomeworkResult.objects.filter(
            student_id__in=student_ids, status__in=activity.DONE, submitted_at__date__lte=until,
        ).values_list("student_id").annotate(d=Max("submitted_at__date"))
    )
    return attended, submitted


def _action(row: dict, days: tuple[int, int, int]) -> str:
    short, mid, long = days
    idle = row["days_inactive"]
    if idle is not None and idle >= long:
        return "Связаться с родителями: уточнить, продолжит ли обучение"
    if row["activity_status"] == activity.STATUS_RISK:
        return "Звонок родителям и разговор с тренером: план возвращения"
    if row["no_attendance"]:
        return "Позвонить родителям: выяснить причину пропусков"
    if idle is not None and idle >= mid:
        return "Позвонить студенту или родителям"
    if row["no_homework"]:
        return "Напомнить о ДЗ, сообщить родителям"
    if idle is not None and idle >= short:
        return "Наблюдать, напомнить о занятиях"
    return "Наблюдать"


def inactivity(rows: list[activity.StudentActivity], roster: dict[int, StudentOn], until: dt.date,
               trainers: dict[int, str]) -> dict:
    """Section «Неактивные студенты»: students active on the month's last day."""
    days = inactivity_days()
    short, mid, long = days
    ids = [r.student_id for r in rows]
    attended, submitted = last_activity(ids, until)
    joined = activity.join_dates([roster[i].student for i in ids], {i: roster[i].group_id for i in ids}, until)
    # Recorded absences (one query): silence counts only while the student was
    # marked absent — an unmarked lesson never counts against them.
    absences: dict[int, list[dt.date]] = defaultdict(list)
    for student_id, day in (
        Attendance.objects.filter(student_id__in=ids, status=Attendance.Status.ABSENT, lesson__date__lte=until)
        .exclude(lesson__status=Lesson.Status.CANCELLED).values_list("student_id", "lesson__date")
    ):
        absences[student_id].append(day)

    students, counts = [], Counter()
    for r in rows:
        last = max((d for d in (attended.get(r.student_id), submitted.get(r.student_id)) if d), default=None)
        since = last or joined.get(r.student_id)
        missed = sum(1 for d in absences[r.student_id] if since is None or d > since)
        # Days without activity — counted only when the student missed marked lessons meanwhile.
        idle = (until - since).days if since and missed else None
        row = {
            "student_id": r.student_id, "name": r.name, "group": r.group,
            "trainer": trainers.get((r.group or {}).get("id"), ""),
            "last_attended": attended.get(r.student_id), "last_homework": submitted.get(r.student_id),
            "absent": r.absent, "attendance": r.attendance, "homework": r.homework,
            "days_inactive": idle, "never_active": last is None, "absences_since": missed,
            "status": "Активен", "activity_status": r.status, "activity_label": r.status_label,
            "no_attendance": bool(r.marked and not r.attended),
            "no_homework": bool(r.homework_due and not r.homework_done),
        }
        row["action"] = _action(row, days)
        counts["total"] += 1
        if idle is not None and idle >= mid:
            counts["inactive"] += 1
        else:
            counts["active"] += 1
        if idle is not None and idle >= long:
            counts["long_inactive"] += 1
        for bucket in days:
            if idle is not None and idle >= bucket:
                counts[f"idle_{bucket}"] += 1
        counts["no_attendance"] += row["no_attendance"]
        counts["no_homework"] += row["no_homework"]
        counts["risk"] += r.status == activity.STATUS_RISK
        flagged = (idle is not None and idle >= short) or row["no_attendance"] or row["no_homework"] \
            or r.status == activity.STATUS_RISK
        if flagged:
            students.append(row)
    students.sort(key=lambda x: (-(x["days_inactive"] or 0), x["name"]))
    return {
        "thresholds": list(days),
        "counts": {k: counts[k] for k in ("total", "active", "inactive", "long_inactive", "no_attendance",
                                          "no_homework", "risk", *(f"idle_{d}" for d in days))},
        "students": students,
    }


# ---------------------------------------------------------------------------
# Departures and reasons
# ---------------------------------------------------------------------------

def _returned_on():
    return Subquery(
        StudentStatusEvent.objects.filter(
            student_id=OuterRef("student_id"), event_type=E.REACTIVATED, event_date__gte=OuterRef("event_date"),
        ).order_by("event_date").values("event_date")[:1]
    )


def departure_events(start: dt.date, end: dt.date) -> list[StudentStatusEvent]:
    """One departure per student in the period — their last one (left twice → counted once)."""
    events = list(
        StudentStatusEvent.objects.filter(event_type=E.DEACTIVATED, event_date__gte=start, event_date__lte=end)
        .select_related("student", "group", "performed_by").annotate(returned_on=_returned_on())
        .order_by("student_id", "-event_date", "-created_at")
    )
    seen, unique = set(), []
    for event in events:
        if event.student_id not in seen:
            seen.add(event.student_id)
            unique.append(event)
    return sorted(unique, key=lambda e: (e.event_date, str(e.student)))


def departures(start: dt.date, end: dt.date, filters: dict) -> dict:
    """Sections «Деактивированные студенты» and «Причины ухода»."""
    events = departure_events(start, end)
    group_ids = {e.group_id for e in events if e.group_id}
    # The group's trainers around the month (its held lessons), one query for all groups.
    trainers = trainers_by_group(group_ids, end, start - dt.timedelta(days=60)) if group_ids else {}

    if filters.get("group"):
        events = [e for e in events if e.group_id == filters["group"]]
    if filters.get("teacher"):
        allowed = teacher_group_ids(filters["teacher"], start - dt.timedelta(days=60), end)
        events = [e for e in events if e.group_id in allowed]
    all_filtered = events
    if filters.get("reason"):
        wanted = "" if filters["reason"] == "unknown" else filters["reason"]
        events = [e for e in events if (e.reason or "") == wanted]

    rows = [{
        "event_id": e.pk, "student_id": e.student_id, "name": str(e.student),
        "group": {"id": e.group_id, "name": e.group.name} if e.group_id else None,
        "trainer": trainers.get(e.group_id, ""),
        "date": e.event_date, "reason": e.reason or "unknown", "reason_label": reason_label(e.reason),
        "comment": e.comment, "performed_by": e.performed_by.get_full_name() or e.performed_by.username if e.performed_by else "",
        "last_activity": e.last_activity_date, "study_days": e.study_days, "returned_on": e.returned_on,
    } for e in events]

    total = len(events)
    by_reason = Counter(r["reason"] for r in rows)
    by_group = Counter((r["group"] or {}).get("name", NO_GROUP) for r in rows)
    by_trainer = Counter()
    for r in rows:
        for name in (r["trainer"] or "Не определён").split(", "):
            by_trainer[name] += 1
    returned = sum(1 for r in rows if r["returned_on"])

    def share(counter):
        return [{"key": k, "label": k, "count": c, "percent": _pct(c, total)} for k, c in counter.most_common()]

    completed = StudentStatusEvent.objects.filter(event_type=E.COMPLETED, event_date__gte=start, event_date__lte=end) \
        .values("student_id").distinct().count()
    paused = StudentStatusEvent.objects.filter(event_type=E.PAUSED, event_date__gte=start, event_date__lte=end) \
        .values("student_id").distinct().count()
    labels = []
    if filters.get("group"):
        from apps.academy.models import Group
        labels.append("группа " + (Group.objects.filter(pk=filters["group"]).values_list("name", flat=True).first() or "—"))
    if filters.get("teacher"):
        from apps.users.models import Teacher
        teacher = Teacher.objects.select_related("user").filter(pk=filters["teacher"]).first()
        labels.append(f"тренер {teacher}" if teacher else "тренер —")
    if filters.get("reason"):
        labels.append("причина: " + reason_label("" if filters["reason"] == "unknown" else filters["reason"]))
    return {
        "filters": {k: v for k, v in filters.items() if v},
        "filters_label": ", ".join(labels),
        "total": total,
        "total_unfiltered": len(all_filtered) if filters.get("reason") else total,
        "rows": rows,
        "returned": returned,
        "returned_percent": _pct(returned, total),
        "unknown": by_reason.get("unknown", 0),
        "by_reason": [{"key": k, "label": reason_label("" if k == "unknown" else k), "count": c, "percent": _pct(c, total)}
                      for k, c in by_reason.most_common()],
        "by_group": share(by_group),
        "by_trainer": share(by_trainer),
        "completed": completed,
        "paused": paused,
        "group_ids": sorted(group_ids),
    }


def departed_count(start: dt.date, end: dt.date) -> int:
    return StudentStatusEvent.objects.filter(event_type=E.DEACTIVATED, event_date__gte=start, event_date__lte=end) \
        .values("student_id").distinct().count()


# ---------------------------------------------------------------------------
# Month over month, advice, summary
# ---------------------------------------------------------------------------

# (key, label, higher is better)
COMPARE = (
    ("attendance", "Средняя посещаемость, %", True),
    ("homework", "Выполнение ДЗ, %", True),
    ("active", "Активные студенты на конец месяца", True),
    ("new", "Новые студенты", True),
    ("departed", "Ушли (деактивированы)", False),
    ("risk", "В зоне риска", False),
    ("inactive", "Неактивны 14+ дней", False),
    ("survey", "Средняя оценка в опросах", True),
)


def comparison(current: dict, previous: dict | None, previous_title: str) -> dict:
    rows = []
    for key, label, higher_better in COMPARE:
        now, before = current.get(key), (previous or {}).get(key)
        delta = round(now - before, 1) if now is not None and before is not None else None
        trend = None
        if delta:
            trend = "better" if (delta > 0) == higher_better else "worse"
        elif delta == 0:
            trend = "same"
        rows.append({"key": key, "label": label, "current": now, "previous": before, "delta": delta, "trend": trend})
    return {"previous_title": previous_title, "available": previous is not None, "rows": rows}


def recommendations(report: dict) -> list[str]:
    advice = []
    inactive = report["inactive"]
    long_days = inactive["thresholds"][2]
    contacts = [s for s in inactive["students"] if (s["days_inactive"] or 0) >= inactive["thresholds"][1]
                or s["activity_status"] == activity.STATUS_RISK]
    if contacts:
        advice.append(f"Связаться с семьями: {_students_word(len(contacts))} без активности {inactive['thresholds'][1]}+ дней "
                      f"или в зоне риска (список — в разделе «Неактивные студенты»).")
    if inactive["counts"]["long_inactive"]:
        advice.append(f"Уточнить, продолжают ли обучение: {_students_word(inactive['counts']['long_inactive'])} "
                      f"без активности {long_days}+ дней.")
    for row in report["departures"]["by_reason"]:
        tip = REASON_ADVICE.get(row["key"])
        if tip:
            advice.append(f"«{row['label']}» ({row['count']}): {tip}")
    for name in report["conclusions"]["groups"]:
        advice.append(f"Обсудить с тренером группы {name} посещаемость и ДЗ.")
    if report["departures"]["unknown"]:
        advice.append(f"Указывать причину при деактивации — уходов без причины: {report['departures']['unknown']}.")
    if report["homework"]["pending"]:
        advice.append(f"Напомнить тренерам проверить работы по ДЗ: {report['homework']['pending']}.")
    return advice


def management_summary(report: dict) -> dict:
    comp = report["comparison"]["rows"]
    improved = [f"{r['label']}: {r['previous']} → {r['current']}" for r in comp if r["trend"] == "better"]
    worsened = [f"{r['label']}: {r['previous']} → {r['current']}" for r in comp if r["trend"] == "worse"]
    groups = list(report["conclusions"]["groups"])
    for row in report["departures"]["by_group"]:
        if row["count"] >= 2 and row["label"] not in groups and row["label"] != NO_GROUP:
            groups.append(f"{row['label']} (ушли {row['count']})")
    reasons = [f"{r['label']} — {r['count']}" for r in report["departures"]["by_reason"][:3]]
    contact_ids = {s["student_id"] for s in report["inactive"]["students"] if s["action"] not in WATCH_ONLY}
    contact_ids |= {s["student_id"] for s in report["students"]["risk"]}
    return {
        "improved": improved,
        "worsened": worsened,
        "groups": groups,
        "top_reasons": reasons,
        "contacts": len(contact_ids),
        "next_month": report["recommendations"][:6],
    }


def month_core(start: dt.date, end: dt.date, today: dt.date) -> dict:
    """The few numbers month-over-month compares — the same calculations as
    the full report, for the previous month."""
    from . import monthly
    until = min(end, today)
    state = monthly.month_state(start, until, today)
    att = monthly._attendance(state["lessons"], state["roster_counts"])
    hw = monthly._homework(state["lessons"], state["roster_counts"])
    rows = state["activity_rows"]
    insights = inactivity(rows, state["roster"], until, {})
    surveys = monthly._surveys(start, end)
    return {
        "attendance": att["percent"], "homework": hw["percent"],
        "active": state["active_count"],
        "new": Student.objects.filter(enrollment_date__gte=start, enrollment_date__lte=end).count(),
        "departed": departed_count(start, end),
        "risk": sum(1 for r in rows if r.status == activity.STATUS_RISK),
        "inactive": insights["counts"]["inactive"],
        "survey": surveys["average"],
    }
