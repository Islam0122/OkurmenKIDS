"""Read side of the Student & Parent Portal — plain dicts built from the
existing academy records for ONE student (already authorised by
services.scope). Nothing here is stored or computed anew:

* lessons, attendance and homework come from academy.Lesson / Attendance /
  Homework / HomeworkResult;
* which of a group's lessons are the student's is decided by the same
  membership timeline the KPI uses (analytics.student_progress.membership:
  enrollment date + transfers / pauses / returns) — a lesson before the
  student joined, or after they left, is never theirs; a lesson they have a
  record for always is;
* XP is the public leaderboard's own computation (leaderboard.student_xp);
* money is billing's own summary (billing.services.archive.student_finance).

Texts are not built here: notifications and statuses go out as codes plus
parameters, so the frontend renders them in Russian or Kyrgyz.
"""
from __future__ import annotations

import datetime as dt

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.academy.models import Attendance, Homework, HomeworkResult, Lesson, Student, StudentStatusEvent
from apps.academy.services.analytics.student_progress import membership

ATTENDED = (Attendance.Status.PRESENT, Attendance.Status.LATE)
DONE = (HomeworkResult.Status.SUBMITTED, HomeworkResult.Status.CHECKED, HomeworkResult.Status.LATE)
LESSON_RELATED = ("group__course", "subject", "room", "teacher__user", "group_teacher__teacher__user")
MAX_RANGE_DAYS = 62

# Homework states as the portal shows them (derived, never stored).
HW_CHECKED = "checked"
HW_SUBMITTED = "submitted"
HW_LATE = "late"
HW_OVERDUE = "overdue"
HW_PENDING = "pending"
HW_STATES = (HW_PENDING, HW_OVERDUE, HW_SUBMITTED, HW_LATE, HW_CHECKED)
HW_OPEN_STATES = (HW_PENDING, HW_OVERDUE)


def _hm(value) -> str | None:
    return value.strftime("%H:%M") if value else None


def _ref(obj) -> dict | None:
    return None if obj is None else {"id": obj.pk, "name": str(obj)}


def _media(file) -> str | None:
    try:
        return file.url if file else None
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# The student
# ---------------------------------------------------------------------------

def student_card(student: Student) -> dict:
    group = student.group
    return {
        "id": student.pk,
        "first_name": student.first_name,
        "last_name": student.last_name,
        "full_name": str(student),
        "photo": _media(student.photo),
        "birth_date": student.birth_date,
        "status": student.status,
        "group": _ref(group),
        "course": _ref(group.course) if group is not None else None,
        "branch": {"id": student.branch.pk, "name": student.branch.name, "name_ky": student.branch.name_ky,
                   "address": student.branch.address, "phone": student.branch.phone}
        if student.branch_id else None,
        "enrollment_date": student.enrollment_date,
    }


def _timeline(student: Student):
    return membership(Student.objects.prefetch_related("status_events").get(pk=student.pk))


def _group_ids(student: Student) -> set[int]:
    ids = set(
        StudentStatusEvent.objects.filter(student=student).values_list("group_id", flat=True)
    ) | set(StudentStatusEvent.objects.filter(student=student).values_list("from_group_id", flat=True))
    if student.group_id:
        ids.add(student.group_id)
    ids.discard(None)
    return ids


def _own_lessons(student: Student, lessons, timeline, recorded: set[int]) -> list[Lesson]:
    return [
        lesson for lesson in lessons
        if lesson.pk in recorded or timeline.group_on(lesson.date) == lesson.group_id
    ]


def lessons_between(student: Student, start: dt.date, end: dt.date) -> list[Lesson]:
    """The student's lessons dated in [start, end] (cancelled ones included,
    so the family sees that a lesson was called off)."""
    recorded = set(
        Attendance.objects.filter(student=student, lesson__date__range=(start, end)).values_list("lesson_id", flat=True)
    )
    qs = (
        Lesson.objects.filter(Q(group_id__in=_group_ids(student)) | Q(pk__in=recorded), date__range=(start, end))
        .select_related(*LESSON_RELATED)
        .order_by("date", "start_time", "pk")
    )
    return _own_lessons(student, qs, _timeline(student), recorded)


def _attendance_map(student: Student, lessons) -> dict[int, Attendance]:
    return {
        a.lesson_id: a for a in Attendance.objects.filter(student=student, lesson__in=[l.pk for l in lessons])
    }


def lesson_row(lesson: Lesson, attendance: Attendance | None, branch=None) -> dict:
    teacher = lesson.effective_teacher
    return {
        "id": lesson.pk,
        "date": lesson.date,
        "start": _hm(lesson.start_time),
        "end": _hm(lesson.end_time),
        "subject": _ref(lesson.subject),
        "teacher": _ref(teacher),
        "group": _ref(lesson.group),
        "course": _ref(lesson.group.course) if lesson.group_id else None,
        "room": _ref(lesson.room),
        "branch": _ref(branch),
        "topic": lesson.topic,
        "lesson_number": lesson.lesson_number,
        "status": lesson.status,
        "cancellation_reason": lesson.cancellation_reason if lesson.status == Lesson.Status.CANCELLED else "",
        "attendance": attendance.status if attendance else None,
    }


def parse_range(start, end, *, today: dt.date) -> tuple[dt.date, dt.date]:
    try:
        start = dt.date.fromisoformat(start) if start else today - dt.timedelta(days=today.weekday())
        end = dt.date.fromisoformat(end) if end else start + dt.timedelta(days=6)
    except ValueError:
        raise ValidationError({"detail": "Неверный формат даты (ожидается ГГГГ-ММ-ДД)."})
    if end < start:
        raise ValidationError({"detail": "Конец периода раньше начала."})
    if (end - start).days > MAX_RANGE_DAYS:
        raise ValidationError({"detail": f"Период не может быть длиннее {MAX_RANGE_DAYS} дней."})
    return start, end


def schedule(student: Student, start: dt.date, end: dt.date) -> dict:
    lessons = lessons_between(student, start, end)
    marks = _attendance_map(student, lessons)
    return {
        "start": start,
        "end": end,
        "lessons": [lesson_row(l, marks.get(l.pk), student.branch) for l in lessons],
    }


# ---------------------------------------------------------------------------
# Homework
# ---------------------------------------------------------------------------

def _homework_qs(student: Student):
    return (
        Homework.objects.filter(
            Q(lesson__group_id__in=_group_ids(student)) | Q(results__student=student)
        )
        .exclude(lesson__status=Lesson.Status.CANCELLED)
        .select_related(*(f"lesson__{rel}" for rel in LESSON_RELATED))
        .distinct()
    )


def visible_homework(student: Student) -> list[tuple[Homework, HomeworkResult | None]]:
    """Every homework given on one of the student's lessons, newest first,
    with the student's result (if any)."""
    homeworks = list(_homework_qs(student))
    results = {r.homework_id: r for r in HomeworkResult.objects.filter(student=student, homework__in=homeworks)}
    timeline = _timeline(student)
    own = [
        hw for hw in homeworks
        if hw.pk in results or timeline.group_on(hw.lesson.date) == hw.lesson.group_id
    ]
    own.sort(key=lambda hw: (hw.deadline or hw.lesson.date, hw.lesson.date, hw.pk), reverse=True)
    return [(hw, results.get(hw.pk)) for hw in own]


def homework_state(homework: Homework, result: HomeworkResult | None, today: dt.date) -> str:
    if result is not None and result.status == HomeworkResult.Status.CHECKED:
        return HW_CHECKED
    if result is not None and result.status == HomeworkResult.Status.LATE:
        return HW_LATE
    if result is not None and result.status == HomeworkResult.Status.SUBMITTED:
        return HW_SUBMITTED
    if homework.deadline is not None and homework.deadline < today:
        return HW_OVERDUE
    return HW_PENDING


def _attachments(lesson: Lesson) -> list[dict]:
    items = []
    if lesson.youtube_url:
        items.append({"kind": "video", "url": lesson.youtube_url})
    for url in lesson.presentation_urls or []:
        if isinstance(url, str) and url.strip():
            items.append({"kind": "presentation", "url": url.strip()})
    return items


def homework_row(homework: Homework, result: HomeworkResult | None, today: dt.date, *, full: bool = False) -> dict:
    lesson = homework.lesson
    state = homework_state(homework, result, today)
    row = {
        "id": homework.pk,
        "title": homework.title,
        "deadline": homework.deadline,
        "days_left": (homework.deadline - today).days if homework.deadline else None,
        "state": state,
        "is_open": state in HW_OPEN_STATES,
        "lesson": {"id": lesson.pk, "date": lesson.date, "topic": lesson.topic, "lesson_number": lesson.lesson_number},
        "subject": _ref(lesson.subject),
        "teacher": _ref(lesson.effective_teacher),
        "score": result.score if result else None,
        "has_feedback": bool(result and result.comment),
        "submitted_at": result.submitted_at if result else None,
        "checked_at": result.checked_at if result else None,
        "created_at": homework.created_at,
    }
    if full:
        row.update({
            "description": homework.description,
            "attachments": _attachments(lesson),
            "feedback": result.comment if result else "",
            "submission": {"text": result.submission_text, "link": result.submission_link} if result else None,
            "can_submit": state != HW_CHECKED,
        })
    return row


def homework_list(student: Student, *, state: str | None = None, today: dt.date) -> list[dict]:
    rows = [homework_row(hw, result, today) for hw, result in visible_homework(student)]
    if state == "open":
        rows = [r for r in rows if r["is_open"]]
    elif state == "done":
        rows = [r for r in rows if r["state"] in (HW_SUBMITTED, HW_LATE, HW_CHECKED)]
    elif state in HW_STATES:
        rows = [r for r in rows if r["state"] == state]
    if state in ("open", HW_PENDING, HW_OVERDUE):
        # Open work: the nearest deadline first, undated last.
        rows.sort(key=lambda r: (r["deadline"] is None, r["deadline"] or dt.date.max))
    return rows


def homework_for(student: Student, homework_id) -> tuple[Homework, HomeworkResult | None]:
    for homework, result in visible_homework(student):
        if str(homework.pk) == str(homework_id):
            return homework, result
    from django.http import Http404

    raise Http404


def submit_homework(student: Student, homework_id, *, text: str, link: str, user) -> tuple[Homework, HomeworkResult]:
    """The student hands in their work. Writes the student's own
    HomeworkResult — the row the trainer grades — as SUBMITTED, or LATE
    after the deadline. A result the trainer already checked is final."""
    text, link = (text or "").strip(), (link or "").strip()
    if not text and not link:
        raise ValidationError({"detail": "Добавьте ответ или ссылку на работу."})
    homework, _ = homework_for(student, homework_id)
    today = timezone.localdate()
    with transaction.atomic():
        result = HomeworkResult.objects.select_for_update().filter(homework=homework, student=student).first()
        if result is not None and result.status == HomeworkResult.Status.CHECKED:
            raise ValidationError({"detail": "Работа уже проверена тренером — изменить её нельзя."})
        if result is None:
            result = HomeworkResult(homework=homework, student=student)
        late = homework.deadline is not None and homework.deadline < today
        result.status = HomeworkResult.Status.LATE if late else HomeworkResult.Status.SUBMITTED
        result.submission_text = text
        result.submission_link = link
        result.submitted_at = timezone.now()
        # Field validation only: HomeworkResult.clean() compares the student's
        # *current* group with the lesson's, which a transferred student no
        # longer matches — the visibility check above already proved the link.
        result.clean_fields(exclude=["homework", "student"])
        result.save()
        from django.contrib.admin.models import CHANGE, LogEntry

        LogEntry.objects.log_actions(
            user_id=user.pk, queryset=[result], action_flag=CHANGE, single_object=True,
            change_message="Кабинет ученика: работа сдана" + (" с опозданием." if late else "."),
        )
    return homework, result


# ---------------------------------------------------------------------------
# Attendance
# ---------------------------------------------------------------------------

def month_bounds(year: int, month: int) -> tuple[dt.date, dt.date]:
    start = dt.date(year, month, 1)
    following = dt.date(year + (month == 12), month % 12 + 1, 1)
    return start, following - dt.timedelta(days=1)


def parse_month(params, *, today: dt.date) -> tuple[int, int]:
    try:
        year = int(params.get("year") or today.year)
        month = int(params.get("month") or today.month)
    except (TypeError, ValueError):
        raise ValidationError({"detail": "Неверный месяц."})
    if not (2000 <= year <= today.year + 1 and 1 <= month <= 12):
        raise ValidationError({"detail": "Неверный месяц."})
    return year, month


def attendance_summary(records) -> dict:
    counts = {status: 0 for status in Attendance.Status.values}
    for record in records:
        counts[record.status] += 1
    marked = sum(counts.values())
    attended = counts[Attendance.Status.PRESENT] + counts[Attendance.Status.LATE]
    return {
        "marked": marked,
        "present": counts[Attendance.Status.PRESENT],
        "late": counts[Attendance.Status.LATE],
        "absent": counts[Attendance.Status.ABSENT],
        "excused": counts[Attendance.Status.EXCUSED],
        "attended": attended,
        "percent": round(attended / marked * 100, 1) if marked else None,
    }


def attendance_month(student: Student, year: int, month: int) -> dict:
    start, end = month_bounds(year, month)
    records = list(
        Attendance.objects.filter(student=student, lesson__date__range=(start, end))
        .exclude(lesson__status=Lesson.Status.CANCELLED)
        .select_related(*(f"lesson__{rel}" for rel in LESSON_RELATED))
        .order_by("lesson__date", "lesson__start_time")
    )
    return {
        "year": year,
        "month": month,
        "summary": attendance_summary(records),
        "records": [
            {
                "id": r.pk,
                "status": r.status,
                "comment": r.comment,
                "excuse_reason": r.excuse_reason,
                "lesson": lesson_row(r.lesson, r, student.branch),
            }
            for r in records
        ],
    }


# ---------------------------------------------------------------------------
# XP & achievements
# ---------------------------------------------------------------------------

def xp_for(student: Student, start: dt.date, end: dt.date) -> dict:
    from apps.leaderboard.services import Period, student_xp

    parts = student_xp(Period("custom", start, end), student_ids=[student.pk]).get(student.pk) or {
        "attendance": 0, "homework": 0, "tests": 0,
    }
    return {**parts, "total": sum(parts.values())}


# XP levels: every level needs 100 XP more than the one before it
# (0, 100, 300, 600, 1000 …) — a presentation of the leaderboard's XP, not new points.
def level_for(total_xp: int) -> dict:
    level, floor, step = 1, 0, 100
    while total_xp >= floor + step:
        floor += step
        level += 1
        step += 100
    return {"level": level, "floor": floor, "next": floor + step, "progress": round((total_xp - floor) / step * 100)}


def achievements(student: Student, *, today: dt.date) -> list[dict]:
    """Earned badges, each backed by a real record."""
    from apps.scholarships.models import ScholarshipAward

    badges = []
    for award in ScholarshipAward.objects.filter(student=student, status=ScholarshipAward.Status.APPROVED) \
            .select_related("period").order_by("-award_date")[:6]:
        badges.append({"code": "scholarship", "date": award.award_date, "params": {"rank": award.rank}})

    # A full month without a miss (at least 4 marked lessons) — the last 6 months.
    year, month = today.year, today.month
    for _ in range(6):
        year, month = (year, month - 1) if month > 1 else (year - 1, 12)
        start, end = month_bounds(year, month)
        records = list(Attendance.objects.filter(student=student, lesson__date__range=(start, end))
                       .exclude(lesson__status=Lesson.Status.CANCELLED).only("status"))
        summary = attendance_summary(records)
        if summary["marked"] >= 4 and summary["attended"] == summary["marked"]:
            badges.append({"code": "perfect_attendance", "date": end, "params": {"year": year, "month": month}})

    checked = HomeworkResult.objects.filter(student=student, score__isnull=False)
    top = checked.filter(score=10).count()
    for threshold in (25, 10, 1):
        if top >= threshold:
            badges.append({"code": "top_homework", "date": None, "params": {"count": threshold}})
            break
    done = HomeworkResult.objects.filter(student=student, status__in=DONE).count()
    for threshold in (100, 50, 20, 5):
        if done >= threshold:
            badges.append({"code": "homework_streak", "date": None, "params": {"count": threshold}})
            break

    total = xp_for(student, dt.date(2000, 1, 1), today)["total"]
    level = level_for(total)["level"]
    if level >= 2:
        badges.append({"code": "level", "date": None, "params": {"level": level}})
    return badges


# ---------------------------------------------------------------------------
# Feedback & notifications
# ---------------------------------------------------------------------------

def teacher_feedback(student: Student, *, limit: int = 10, start: dt.date | None = None,
                     end: dt.date | None = None) -> list[dict]:
    """Trainers' own words about this student: homework comments,
    attendance comments and scholarship evaluations (TrainerFeedback)."""
    from apps.scholarships.models import TrainerFeedback

    items = []
    results = HomeworkResult.objects.filter(student=student).exclude(comment="") \
        .select_related("homework__lesson__subject", "homework__lesson__teacher__user",
                        "homework__lesson__group_teacher__teacher__user")
    attendance = Attendance.objects.filter(student=student).exclude(comment="") \
        .select_related("lesson__subject", "lesson__teacher__user", "lesson__group_teacher__teacher__user")
    feedback = TrainerFeedback.objects.filter(student=student).exclude(comment="") \
        .select_related("subject", "teacher__user", "period")
    if start and end:
        results = results.filter(homework__lesson__date__range=(start, end))
        attendance = attendance.filter(lesson__date__range=(start, end))
        feedback = feedback.filter(period__period_start__lte=end, period__period_end__gte=start)
    for r in results.order_by("-updated_at")[:limit]:
        lesson = r.homework.lesson
        items.append({"kind": "homework", "date": lesson.date, "text": r.comment, "score": r.score,
                      "title": r.homework.title, "subject": _ref(lesson.subject), "teacher": _ref(lesson.effective_teacher)})
    for a in attendance.order_by("-updated_at")[:limit]:
        items.append({"kind": "lesson", "date": a.lesson.date, "text": a.comment, "score": None,
                      "title": a.lesson.topic, "subject": _ref(a.lesson.subject), "teacher": _ref(a.lesson.effective_teacher)})
    for f in feedback.order_by("-updated_at")[:limit]:
        items.append({"kind": "evaluation", "date": f.period.period_end, "text": f.comment, "score": None,
                      "title": "", "subject": _ref(f.subject), "teacher": _ref(f.teacher),
                      "criteria": {"progress": f.progress, "participation": f.participation,
                                   "discipline": f.discipline, "understanding": f.understanding}})
    items.sort(key=lambda item: item["date"] or dt.date.min, reverse=True)
    return items[:limit]


def notifications(student: Student, *, today: dt.date, can_view_payments: bool) -> list[dict]:
    """What needs the family's attention, derived from the records (never
    stored): codes + parameters, rendered by the frontend in ru / ky."""
    items = []
    for homework, result in visible_homework(student):
        state = homework_state(homework, result, today)
        base = {"homework_id": homework.pk, "title": homework.title}
        if state == HW_OVERDUE and (today - homework.deadline).days <= 30:
            items.append({"kind": "homework_overdue", "date": homework.deadline, "params": base, "priority": 1})
        elif state == HW_PENDING and homework.deadline and 0 <= (homework.deadline - today).days <= 2:
            items.append({"kind": "homework_due", "date": homework.deadline,
                          "params": {**base, "days_left": (homework.deadline - today).days}, "priority": 2})
        elif state == HW_PENDING and timezone.localdate(homework.created_at) >= today - dt.timedelta(days=7):
            items.append({"kind": "homework_new", "date": timezone.localdate(homework.created_at), "params": base,
                          "priority": 3})
        if state == HW_CHECKED and result.checked_at and timezone.localdate(result.checked_at) >= today - dt.timedelta(days=14):
            items.append({"kind": "homework_checked", "date": timezone.localdate(result.checked_at),
                          "params": {**base, "score": result.score}, "priority": 3})
    for lesson in lessons_between(student, today, today + dt.timedelta(days=14)):
        if lesson.status == Lesson.Status.CANCELLED:
            items.append({"kind": "lesson_cancelled", "date": lesson.date,
                          "params": {"lesson_id": lesson.pk, "subject": lesson.subject.name if lesson.subject_id else "",
                                     "start": _hm(lesson.start_time)}, "priority": 1})
    if can_view_payments:
        finance = payments_summary(student)
        if finance and finance["has_debt"]:
            items.append({"kind": "payment_due", "date": today, "params": {"amount": finance["due_now"] or finance["debt"]},
                          "priority": 1})
    items.sort(key=lambda item: (item["priority"], -(item["date"] or today).toordinal()))
    for index, item in enumerate(items):
        item["id"] = f"{item['kind']}-{item['params'].get('homework_id') or item['params'].get('lesson_id') or index}"
    return items


# ---------------------------------------------------------------------------
# Payments
# ---------------------------------------------------------------------------

def payments_summary(student: Student) -> dict | None:
    from apps.billing.models import StudentBillingProfile
    from apps.billing.services.archive import student_finance

    profiles = list(StudentBillingProfile.objects.filter(student=student).select_related("subject", "plan"))
    if not profiles:
        return None
    return student_finance(student, profiles)


def payments(student: Student) -> dict:
    from apps.accounting.models import StudentPayment
    from apps.billing.models import Invoice

    summary = payments_summary(student)
    history = (
        StudentPayment.objects.filter(student=student, status=StudentPayment.Status.CONFIRMED)
        .order_by("-received_date", "-pk")[:24]
    )
    invoices = (
        Invoice.objects.filter(profile__student=student, status__in=Invoice.UNPAID_STATUSES)
        .select_related("profile__subject").order_by("due_reached_on", "pk")[:12]
    )
    return {
        "summary": summary,
        "currency": "KGS",
        "open_invoices": [
            {"id": i.pk, "number": i.number, "kind": i.kind, "status": i.status, "amount": str(i.amount),
             "balance": str(i.balance), "overdue_since": i.overdue_since,
             "subject": i.profile.subject.name if i.profile.subject_id else None}
            for i in invoices
        ],
        "history": [
            {"id": p.pk, "kind": p.kind, "amount": str(p.amount), "date": p.received_date, "method": p.method,
             "service_start": p.service_start, "service_end": p.service_end}
            for p in history
        ],
    }


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

def dashboard(student: Student, *, today: dt.date, can_view_payments: bool) -> dict:
    week_lessons = lessons_between(student, today, today + dt.timedelta(days=21))
    marks = _attendance_map(student, week_lessons)
    upcoming = [l for l in week_lessons if l.status != Lesson.Status.CANCELLED and l.date > today][:5]
    todays = [l for l in week_lessons if l.date == today]

    homework = [homework_row(hw, r, today) for hw, r in visible_homework(student)]
    # What to do next first (nearest deadline), then the most recent overdue work.
    pending = sorted((h for h in homework if h["state"] == HW_PENDING),
                     key=lambda h: (h["deadline"] is None, h["deadline"] or dt.date.max))
    overdue = sorted((h for h in homework if h["state"] == HW_OVERDUE), key=lambda h: h["deadline"], reverse=True)
    open_hw = pending + overdue

    month_start, month_end = month_bounds(today.year, today.month)
    month_records = list(Attendance.objects.filter(student=student, lesson__date__range=(month_start, month_end))
                         .exclude(lesson__status=Lesson.Status.CANCELLED).only("status"))
    all_records = list(Attendance.objects.filter(student=student).exclude(lesson__status=Lesson.Status.CANCELLED)
                       .only("status"))
    scores = [h["score"] for h in homework if h["score"] is not None]
    recent_scores = [h["score"] for h in homework if h["score"] is not None and h["lesson"]["date"] >= month_start]
    assigned = [h for h in homework if h["deadline"] is None or h["deadline"] <= today or not h["is_open"]]
    done = [h for h in assigned if not h["is_open"]]

    xp_month = xp_for(student, month_start, today)
    xp_total = xp_for(student, dt.date(2000, 1, 1), today)

    data = {
        "student": student_card(student),
        "today": today,
        "today_lessons": [lesson_row(l, marks.get(l.pk), student.branch) for l in todays],
        "upcoming_lessons": [lesson_row(l, marks.get(l.pk), student.branch) for l in upcoming],
        "homework": {
            "open": open_hw[:6],
            "open_count": len(open_hw),
            "overdue_count": sum(1 for h in open_hw if h["state"] == HW_OVERDUE),
            "next_deadline": next((h["deadline"] for h in open_hw if h["deadline"] and h["deadline"] >= today), None),
        },
        "attendance": {"month": attendance_summary(month_records), "overall": attendance_summary(all_records)},
        "performance": {
            "average_score": round(sum(scores) / len(scores), 1) if scores else None,
            "month_average_score": round(sum(recent_scores) / len(recent_scores), 1) if recent_scores else None,
            "homework_rate": round(len(done) / len(assigned) * 100, 1) if assigned else None,
            "scored_count": len(scores),
        },
        "xp": {"month": xp_month, "total": xp_total["total"], "level": level_for(xp_total["total"])},
        "achievements": achievements(student, today=today),
        "feedback": teacher_feedback(student, limit=4),
        "notifications": notifications(student, today=today, can_view_payments=can_view_payments)[:6],
        "payments": payments_summary(student) if can_view_payments else None,
    }
    return data
