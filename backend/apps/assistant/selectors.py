"""Read side of the Assistant Workspace: plain dicts built from the existing
academy models — nothing here is stored or computed anew. Every list is
built with a fixed number of queries (annotations / prefetch), so a page
of 20 groups or students costs the same as a page of 2.

Deliberately no KPI, trainer performance or analytics here: the Assistant
sees operational facts only (who studies where, what happens today, what
needs attention).
"""
from __future__ import annotations

import datetime as dt
from collections import defaultdict

from django.contrib.admin.models import LogEntry
from django.contrib.contenttypes.models import ContentType
from django.db.models import Count, Prefetch, Q
from django.utils import timezone

from apps.academy.constants import WEEKDAY_CODES, WEEKDAY_LABELS_FULL, WEEKDAY_LABELS_SHORT
from apps.academy.models import (
    Attendance,
    Course,
    Group,
    GroupSchedule,
    GroupTeacher,
    HomeworkResult,
    Lesson,
    Room,
    Student,
    StudentStatusEvent,
)
from apps.academy.services.group_schedule_conflicts import overlapping_groups
from apps.academy.services.trainer_assignment import available_trainers
from apps.scholarships.models import ScholarshipAward

OPEN_GROUP_STATUSES = (Group.Status.ACTIVE, Group.Status.PAUSED)
ARCHIVED_GROUP_STATUSES = (Group.Status.COMPLETED, Group.Status.CANCELLED)
ATTENDED = (Attendance.Status.PRESENT, Attendance.Status.LATE)

# Student list tabs → Student.status. «Неактивные» are the withdrawn ones,
# «Архив» — those who completed their education.
STUDENT_STATUS_FILTERS = {
    "active": Student.Status.ACTIVE,
    "paused": Student.Status.PAUSED,
    "inactive": Student.Status.WITHDRAWN,
    "archived": Student.Status.COMPLETED,
}


def _name(obj) -> str:
    return str(obj) if obj is not None else ""


def _ref(obj, label=None) -> dict | None:
    if obj is None:
        return None
    return {"id": obj.pk, "name": label if label is not None else str(obj)}


def _hm(value) -> str:
    return value.strftime("%H:%M") if value else ""


# ---------------------------------------------------------------------------
# Groups
# ---------------------------------------------------------------------------

def _active_slots(group: Group) -> list[GroupSchedule]:
    """Uses the `active_slots` prefetch when present."""
    slots = getattr(group, "active_slots", None)
    if slots is None:
        slots = list(group.schedules.filter(is_active=True).select_related("teacher__user", "subject", "room"))
    return sorted(slots, key=lambda s: (WEEKDAY_CODES.index(s.day_of_week), s.start_time))


def schedule_label(slots: list[GroupSchedule]) -> str:
    """«Пн / Ср / Пт — 16:00–17:30» (one entry per distinct time range)."""
    by_time: dict[tuple, list[str]] = defaultdict(list)
    for slot in slots:
        key = (slot.start_time, slot.end_time)
        if slot.day_of_week not in by_time[key]:
            by_time[key].append(slot.day_of_week)
    parts = []
    for (start, end), days in sorted(by_time.items()):
        days = sorted(days, key=WEEKDAY_CODES.index)
        parts.append(f"{' / '.join(WEEKDAY_LABELS_SHORT[d] for d in days)} — {_hm(start)}–{_hm(end)}")
    return "; ".join(parts)


def _teacher_names(group: Group) -> list[str]:
    programs = getattr(group, "active_programs", None)
    if programs is None:
        programs = list(group.teachers.filter(is_active=True).select_related("teacher__user"))
    names: list[str] = []
    for program in programs:
        name = str(program.teacher)
        if name not in names:
            names.append(name)
    return names


def groups_queryset():
    return (
        Group.objects.select_related("course")
        .annotate(active_students=Count("students", filter=Q(students__status=Student.Status.ACTIVE), distinct=True))
        .prefetch_related(
            Prefetch(
                "schedules",
                queryset=GroupSchedule.objects.filter(is_active=True).select_related("teacher__user", "subject", "room"),
                to_attr="active_slots",
            ),
            Prefetch(
                "teachers",
                queryset=GroupTeacher.objects.filter(is_active=True).select_related("teacher__user", "subject"),
                to_attr="active_programs",
            ),
        )
    )


def filter_groups(qs, params):
    status = params.get("status") or "active"
    if status == "active":
        qs = qs.filter(status__in=OPEN_GROUP_STATUSES)
    elif status == "archived":
        qs = qs.filter(status__in=ARCHIVED_GROUP_STATUSES)
    search = (params.get("search") or "").strip()
    if search:
        qs = qs.filter(Q(name__icontains=search) | Q(course__name__icontains=search))
    if (course := params.get("course")) and str(course).isdigit():
        qs = qs.filter(course_id=course)
    if (teacher := params.get("teacher")) and str(teacher).isdigit():
        qs = qs.filter(
            Q(schedules__teacher_id=teacher, schedules__is_active=True)
            | Q(teachers__teacher_id=teacher, teachers__is_active=True)
        ).distinct()
    return qs.order_by("name")


def group_card(group: Group) -> dict:
    return {
        "id": group.pk,
        "name": group.name,
        "course": _ref(group.course),
        "status": group.status,
        "status_display": group.get_status_display(),
        "students_count": group.active_students if hasattr(group, "active_students") else group.students_count,
        "max_students": group.max_students,
        "teachers": _teacher_names(group),
        "schedule": schedule_label(_active_slots(group)),
        "start_date": group.start_date,
        "end_date": group.end_date,
    }


def _slot_row(slot: GroupSchedule) -> dict:
    return {
        "id": slot.pk,
        "day": slot.day_of_week,
        "day_label": WEEKDAY_LABELS_FULL.get(slot.day_of_week, slot.day_of_week),
        "start": _hm(slot.start_time),
        "end": _hm(slot.end_time),
        "room": _ref(slot.room),
    }


def _program_row(program: GroupTeacher) -> dict:
    slots = sorted(
        (s for s in program.schedules.all() if s.is_active),
        key=lambda s: (WEEKDAY_CODES.index(s.day_of_week), s.start_time),
    )
    return {
        "id": program.pk,
        "teacher": _ref(program.teacher),
        "subject": _ref(program.subject),
        "is_active": program.is_active,
        "slots": [_slot_row(s) for s in slots],
    }


def student_row(student: Student) -> dict:
    attended = getattr(student, "attended_count", None)
    marked = getattr(student, "marked_count", None)
    percent = round(attended / marked * 100) if marked else None
    group = student.group
    return {
        "id": student.pk,
        "first_name": student.first_name,
        "last_name": student.last_name,
        "full_name": str(student),
        "phone": student.phone,
        "parent_phone": student.parent_phone,
        "group": _ref(group),
        "course": _ref(group.course) if group is not None else None,
        "status": student.status,
        "status_display": student.get_status_display(),
        "enrollment_date": student.enrollment_date,
        "attendance_percent": percent,
    }


def students_queryset():
    return Student.objects.select_related("group__course").annotate(
        attended_count=Count("attendance_records", filter=Q(attendance_records__status__in=ATTENDED)),
        marked_count=Count("attendance_records"),
    )


def filter_students(qs, params):
    status = params.get("status") or "all"
    if status in STUDENT_STATUS_FILTERS:
        qs = qs.filter(status=STUDENT_STATUS_FILTERS[status])
    search = (params.get("search") or "").strip()
    if search:
        for word in search.split():
            qs = qs.filter(
                Q(first_name__icontains=word) | Q(last_name__icontains=word)
                | Q(phone__icontains=word) | Q(parent_phone__icontains=word)
            )
    if (group := params.get("group")) and str(group).isdigit():
        qs = qs.filter(group_id=group)
    if (course := params.get("course")) and str(course).isdigit():
        qs = qs.filter(group__course_id=course)
    if (teacher := params.get("teacher")) and str(teacher).isdigit():
        qs = qs.filter(group__in=Group.objects.filter(
            Q(schedules__teacher_id=teacher, schedules__is_active=True)
            | Q(teachers__teacher_id=teacher, teachers__is_active=True)
        ))
    if params.get("no_group") in ("1", "true"):
        qs = qs.filter(group__isnull=True)
    return qs.order_by("last_name", "first_name", "pk")


def _status_event_row(event: StudentStatusEvent) -> dict:
    if event.event_type == StudentStatusEvent.EventType.TRANSFERRED:
        title = (
            f"Перевод: {event.from_group.name} → {event.group.name if event.group else '—'}"
            if event.from_group else f"Зачисление в группу {event.group.name if event.group else '—'}"
        )
    else:
        title = event.get_event_type_display()
    return {
        "id": f"event-{event.pk}",
        "kind": event.event_type,
        "title": title,
        "reason": event.get_reason_display() if event.reason else "",
        "comment": event.comment,
        "group": _ref(event.group),
        "from_group": _ref(event.from_group),
        "date": event.event_date,
        "created_at": event.created_at,
        "performed_by": _name(event.performed_by),
    }


def _log_rows(model, object_ids) -> list[dict]:
    content_type = ContentType.objects.get_for_model(model)
    entries = (
        LogEntry.objects.filter(content_type=content_type, object_id__in=[str(pk) for pk in object_ids])
        .select_related("user")
        .order_by("-action_time")[:50]
    )
    return [
        {
            "id": f"log-{entry.pk}",
            "kind": "log",
            "title": entry.get_change_message() or entry.object_repr,
            "date": timezone.localtime(entry.action_time).date(),
            "created_at": entry.action_time,
            "performed_by": _name(entry.user),
        }
        for entry in entries
    ]


def _sorted_history(rows: list[dict]) -> list[dict]:
    return sorted(rows, key=lambda row: row["created_at"], reverse=True)


def _lesson_row(lesson: Lesson, students_count: int | None = None) -> dict:
    teacher = lesson.effective_teacher
    return {
        "id": lesson.pk,
        "date": lesson.date,
        "start": _hm(lesson.start_time),
        "end": _hm(lesson.end_time),
        "group": _ref(lesson.group),
        "subject": _ref(lesson.subject),
        "teacher": _ref(teacher),
        "room": _ref(lesson.room),
        "topic": lesson.topic,
        "lesson_number": lesson.lesson_number,
        "status": lesson.status,
        "status_display": lesson.get_status_display(),
        "students_count": students_count,
        "schedule_overridden": lesson.schedule_overridden,
    }


LESSON_RELATED = ("group__course", "teacher__user", "group_teacher__teacher__user", "room", "subject")


def group_detail(group: Group) -> dict:
    today = timezone.localdate()
    programs = list(
        group.teachers.select_related("teacher__user", "subject")
        .prefetch_related(Prefetch("schedules", queryset=GroupSchedule.objects.select_related("room")))
        .order_by("-is_active", "subject__name", "id")
    )
    students = list(
        students_queryset().filter(group=group).order_by("status", "last_name", "first_name")
    )
    lessons = Lesson.objects.filter(group=group).select_related(*LESSON_RELATED)
    upcoming = list(lessons.filter(date__gte=today).exclude(status=Lesson.Status.CANCELLED).order_by("date", "start_time")[:10])
    recent = list(lessons.filter(date__lt=today).order_by("-date", "-start_time")[:10])
    active_count = sum(1 for s in students if s.status == Student.Status.ACTIVE)

    group_events = StudentStatusEvent.objects.filter(Q(group=group) | Q(from_group=group)).select_related(
        "student", "group", "from_group", "performed_by"
    ).order_by("-created_at")[:50]
    history = [
        {**_status_event_row(e), "title": f"{e.student}: {_status_event_row(e)['title']}"} for e in group_events
    ] + _log_rows(Group, [group.pk]) + _log_rows(GroupTeacher, [p.pk for p in programs])

    from apps.feedback.models import Survey
    from apps.testing.models import TestSession

    exams = TestSession.objects.filter(group=group).select_related("test").order_by("-created_at")[:20]
    surveys = Survey.objects.filter(group=group).order_by("-created_at")[:20]

    marked = Attendance.objects.filter(lesson__group=group)
    attended = marked.filter(status__in=ATTENDED).count()
    marked_total = marked.count()

    card = group_card(group)
    card["students_count"] = active_count
    return {
        **card,
        "description": group.description,
        "created_at": group.created_at,
        "programs": [_program_row(p) for p in programs],
        "students": [student_row(s) for s in students],
        "upcoming_lessons": [_lesson_row(l, active_count) for l in upcoming],
        "recent_lessons": [_lesson_row(l, active_count) for l in recent],
        "lessons_total": lessons.count(),
        "attendance": {
            "attended": attended,
            "marked": marked_total,
            "percent": round(attended / marked_total * 100) if marked_total else None,
        },
        "exams": [
            {
                "id": s.pk,
                "title": s.title or (s.test.title if s.test_id else ""),
                "status": s.status,
                "status_display": s.get_status_display(),
                "created_at": s.created_at,
            }
            for s in exams
        ],
        "surveys": [
            {"id": s.pk, "title": s.title, "status": s.status, "status_display": s.get_status_display(),
             "created_at": s.created_at}
            for s in surveys
        ],
        "history": _sorted_history(history)[:50],
    }


# ---------------------------------------------------------------------------
# Students
# ---------------------------------------------------------------------------

def student_detail(student: Student) -> dict:
    student = students_queryset().get(pk=student.pk)
    group = student.group
    programs = []
    if group is not None:
        programs = list(
            group.teachers.filter(is_active=True).select_related("teacher__user", "subject")
            .prefetch_related(Prefetch("schedules", queryset=GroupSchedule.objects.select_related("room")))
        )

    attendance = list(
        Attendance.objects.filter(student=student)
        .select_related("lesson__group", "lesson__subject")
        .order_by("-lesson__date", "-lesson__start_time")[:30]
    )
    homework = list(
        HomeworkResult.objects.filter(student=student)
        .select_related("homework__lesson__group", "homework__lesson__subject")
        .order_by("-homework__lesson__date")[:30]
    )
    awards = list(
        ScholarshipAward.objects.filter(student=student).select_related("period").order_by("-award_date")
    )
    from apps.feedback.models import Survey
    from apps.testing.models import AttemptStatus

    attempts = list(
        student.test_attempts.filter(status=AttemptStatus.FINISHED).select_related("subject").order_by("-finished_at")[:20]
    )
    surveys = list(Survey.objects.filter(group=group).order_by("-created_at")[:20]) if group is not None else []

    events = student.status_events.select_related("group", "from_group", "performed_by").order_by("-created_at")
    history = [_status_event_row(e) for e in events] + _log_rows(Student, [student.pk])

    teachers = []
    for program in programs:
        name = str(program.teacher)
        if name not in teachers:
            teachers.append(name)

    return {
        **student_row(student),
        "created_at": student.created_at,
        "teachers": teachers,
        "group_status": group.get_status_display() if group is not None else None,
        "schedule": [
            {**_slot_row(slot), "teacher": _ref(program.teacher), "subject": _ref(program.subject)}
            for program in programs
            for slot in sorted(
                (s for s in program.schedules.all() if s.is_active),
                key=lambda s: (WEEKDAY_CODES.index(s.day_of_week), s.start_time),
            )
        ],
        "attendance": {
            "attended": student.attended_count,
            "marked": student.marked_count,
            "records": [
                {
                    "id": a.pk,
                    "date": a.lesson.date,
                    "group": a.lesson.group.name,
                    "subject": a.lesson.subject.name if a.lesson.subject_id else "",
                    "status": a.status,
                    "status_display": a.get_status_display(),
                    "comment": a.comment,
                }
                for a in attendance
            ],
        },
        "homework": [
            {
                "id": r.pk,
                "title": r.homework.title,
                "date": r.homework.lesson.date,
                "subject": r.homework.lesson.subject.name if r.homework.lesson.subject_id else "",
                "status": r.status,
                "status_display": r.get_status_display(),
                "score": r.score,
            }
            for r in homework
        ],
        "exams": [
            {
                "id": str(a.pk),
                "title": a.test_title,
                "subject": a.subject.name if a.subject_id else "",
                "score": round(a.score, 1),
                "finished_at": a.finished_at,
            }
            for a in attempts
        ],
        "scholarships": [
            {
                "id": a.pk,
                "period": str(a.period),
                "period_start": a.period.period_start,
                "period_end": a.period.period_end,
                "award_date": a.award_date,
                "rank": a.rank,
                "amount": str(a.amount),
                "status": a.status,
                "status_display": a.get_status_display(),
                "payment_status": a.payment_status,
                "payment_status_display": a.get_payment_status_display(),
            }
            for a in awards
        ],
        "surveys": [
            {"id": s.pk, "title": s.title, "status": s.status, "status_display": s.get_status_display(),
             "public_token": s.public_token if s.status == s.Status.PUBLISHED else None}
            for s in surveys
        ],
        "history": _sorted_history(history)[:50],
    }


# ---------------------------------------------------------------------------
# Schedule
# ---------------------------------------------------------------------------

def lessons_between(start: dt.date, end: dt.date, params) -> list[dict]:
    qs = Lesson.objects.filter(date__gte=start, date__lte=end).select_related(*LESSON_RELATED)
    if (group := params.get("group")) and str(group).isdigit():
        qs = qs.filter(group_id=group)
    if (teacher := params.get("teacher")) and str(teacher).isdigit():
        qs = qs.filter(Q(teacher_id=teacher) | Q(teacher__isnull=True, group_teacher__teacher_id=teacher))
    if params.get("include_cancelled") not in ("1", "true"):
        qs = qs.exclude(status=Lesson.Status.CANCELLED)
    lessons = list(qs.order_by("date", "start_time", "group__name"))
    counts = dict(
        Student.objects.filter(group_id__in={l.group_id for l in lessons}, status=Student.Status.ACTIVE)
        .values_list("group_id").annotate(n=Count("id")).values_list("group_id", "n")
    )
    return [_lesson_row(l, counts.get(l.group_id, 0)) for l in lessons]


def schedule_conflicts() -> list[dict]:
    """Weekly slots that put one trainer, room or group in two places at
    once — the same overlap rule as GroupSchedule.clean() and the admin's
    schedule conflict report (services.group_schedule_conflicts)."""
    slots = list(
        GroupSchedule.objects.filter(is_active=True, group__status__in=OPEN_GROUP_STATUSES)
        .select_related("group", "teacher__user", "room")
    )
    buckets: dict[tuple, list] = defaultdict(list)
    for slot in slots:
        buckets[("teacher", slot.teacher_id, slot.day_of_week)].append(slot)
        buckets[("group", slot.group_id, slot.day_of_week)].append(slot)
        if slot.room_id:
            buckets[("room", slot.room_id, slot.day_of_week)].append(slot)
    labels = {"teacher": "Тренер", "group": "Группа", "room": "Аудитория"}
    conflicts = []
    for (kind, _pk, day), items in buckets.items():
        for component in overlapping_groups(items):
            first = component[0]
            subject = {"teacher": first.teacher, "group": first.group, "room": first.room}[kind]
            conflicts.append({
                "kind": kind,
                "kind_label": labels[kind],
                "name": str(subject),
                "day": day,
                "day_label": WEEKDAY_LABELS_FULL[day],
                "slots": [
                    {"group": _ref(s.group), "teacher": _ref(s.teacher), "start": _hm(s.start_time), "end": _hm(s.end_time)}
                    for s in component
                ],
            })
    return sorted(conflicts, key=lambda c: (WEEKDAY_CODES.index(c["day"]), c["kind"], c["name"]))


# ---------------------------------------------------------------------------
# Attendance
# ---------------------------------------------------------------------------

def attendance_for_day(day: dt.date, params) -> list[dict]:
    qs = Lesson.objects.filter(date=day).exclude(status=Lesson.Status.CANCELLED).select_related(*LESSON_RELATED)
    if (group := params.get("group")) and str(group).isdigit():
        qs = qs.filter(group_id=group)
    lessons = list(qs.order_by("start_time", "group__name"))
    if not lessons:
        return []
    roster: dict[int, list[Student]] = defaultdict(list)
    for student in Student.objects.filter(
        group_id__in={l.group_id for l in lessons}, status=Student.Status.ACTIVE
    ).order_by("last_name", "first_name"):
        roster[student.group_id].append(student)
    marks: dict[int, dict[int, Attendance]] = defaultdict(dict)
    for record in Attendance.objects.filter(lesson__in=lessons):
        marks[record.lesson_id][record.student_id] = record

    result = []
    for lesson in lessons:
        lesson_marks = marks[lesson.pk]
        # Everyone on the roster, plus anyone already marked who has since
        # left the group (their mark is history and stays visible).
        students = list(roster[lesson.group_id])
        known = {s.pk for s in students}
        extra = [r.student for r in lesson_marks.values() if r.student_id not in known]
        rows = [
            {
                "student": {"id": s.pk, "name": str(s)},
                "status": lesson_marks[s.pk].status if s.pk in lesson_marks else None,
                "comment": lesson_marks[s.pk].comment if s.pk in lesson_marks else "",
            }
            for s in students + extra
        ]
        present = sum(1 for r in rows if r["status"] in ATTENDED)
        absent = sum(1 for r in rows if r["status"] in (Attendance.Status.ABSENT, Attendance.Status.EXCUSED))
        result.append({
            **_lesson_row(lesson, len(students)),
            "present": present,
            "absent": absent,
            "unmarked": sum(1 for r in rows if r["status"] is None),
            "records": rows,
        })
    return result


# ---------------------------------------------------------------------------
# Dashboard & options
# ---------------------------------------------------------------------------

def dashboard() -> dict:
    today = timezone.localdate()
    month_ago = today - dt.timedelta(days=30)
    todays = lessons_between(today, today, {})
    conflicts = schedule_conflicts()

    withdrawn_recent = StudentStatusEvent.objects.filter(
        event_type=StudentStatusEvent.EventType.DEACTIVATED, event_date__gte=month_ago,
        student__status=Student.Status.WITHDRAWN,
    ).values("student_id").distinct().count()
    paused = Student.objects.filter(status=Student.Status.PAUSED).count()
    without_group = Student.objects.filter(status=Student.Status.ACTIVE, group__isnull=True).count()
    pending_awards = ScholarshipAward.objects.filter(status=ScholarshipAward.Status.PENDING).count()

    attention = [
        {"key": "inactive", "count": withdrawn_recent, "label": "деактивированы за 30 дней",
         "to": "/assistant/students?status=inactive", "tone": "warning"},
        {"key": "paused", "count": paused, "label": "студентов на паузе",
         "to": "/assistant/students?status=paused", "tone": "info"},
        {"key": "conflicts", "count": len(conflicts), "label": "конфликтов в расписании",
         "to": "/assistant/schedule?conflicts=1", "tone": "danger"},
        {"key": "without_group", "count": without_group, "label": "активных студентов без группы",
         "to": "/assistant/students?status=active&no_group=1", "tone": "warning"},
        {"key": "pending_scholarships", "count": pending_awards, "label": "стипендий ждут утверждения",
         "to": "/assistant/scholarships", "tone": "info"},
    ]

    return {
        "date": today,
        "cards": {
            "active_groups": Group.objects.filter(status=Group.Status.ACTIVE).count(),
            "active_students": Student.objects.filter(status=Student.Status.ACTIVE).count(),
            "todays_lessons": len(todays),
            "new_students": Student.objects.filter(enrollment_date__gte=month_ago, enrollment_date__lte=today).count(),
        },
        "today": todays,
        "attention": [item for item in attention if item["count"]],
    }


def options() -> dict:
    courses = Course.objects.prefetch_related("subjects").order_by("name")
    return {
        "courses": [
            {"id": c.pk, "name": c.name, "count_lesson": c.count_lesson,
             "subjects": [{"id": s.pk, "name": s.name} for s in c.subjects.all() if s.is_active]}
            for c in courses
        ],
        "teachers": [
            {"id": t.pk, "name": str(t), "subjects": [s.pk for s in t.subjects.all()]}
            for t in available_trainers()
        ],
        "rooms": [{"id": r.pk, "name": r.name, "capacity": r.capacity} for r in Room.objects.filter(is_active=True)],
        "groups": [
            {"id": g.pk, "name": g.name, "course": g.course.name, "status": g.status,
             "students_count": g.active_students, "max_students": g.max_students}
            for g in Group.objects.filter(status__in=OPEN_GROUP_STATUSES).select_related("course")
            .annotate(active_students=Count("students", filter=Q(students__status=Student.Status.ACTIVE)))
            .order_by("name")
        ],
        "weekdays": [{"code": code, "label": WEEKDAY_LABELS_FULL[code], "short": WEEKDAY_LABELS_SHORT[code]}
                     for code in WEEKDAY_CODES],
        "deactivation_reasons": [{"value": v, "label": l} for v, l in StudentStatusEvent.Reason.choices],
        "group_statuses": [{"value": v, "label": l} for v, l in Group.Status.choices],
    }
