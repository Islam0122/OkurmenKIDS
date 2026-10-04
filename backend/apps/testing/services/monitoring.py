"""Monitoring for Teachers, Team Leads and Admins: live attempts, results,
violations and analytics over every kind of attempt the testing module
holds — Exam Mode exams (student portal), public trainers (training
portal) and classic /exam/ sessions.

Who sees what (the project's RBAC, apps.users.permissions):
    Admin, Team Lead  everything (can_view_academy)
    Teacher           attempts of sessions held for their groups, and of
                      students of their groups (Group.objects.for_teacher);
                      public trainers (open to anyone, no group) of the
                      subjects they teach or that they own (session.teacher)
Attempts LMS staff take themselves (StudentAttempt.user) are never
counted. Nothing here writes, except closing attempts whose time is up.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, timedelta

from django.db.models import (
    Avg,
    Count,
    DurationField,
    ExpressionWrapper,
    F,
    OuterRef,
    Q,
    QuerySet,
    Subquery,
    Sum,
)
from django.utils import timezone

from apps.academy.models import Group, GroupTeacher, Subject
from apps.users.permissions import can_view_academy

from ..models import (
    AttemptStatus,
    ExamEventType,
    FinishReason,
    SessionParticipant,
    SessionStatus,
    SessionType,
    StudentAttempt,
    TestSession,
)
from .analytics import question_stats
from .attempts import attempt_deadline, result_rows

VIOLATION_TYPES = (
    ExamEventType.TAB_SWITCH,
    ExamEventType.FULLSCREEN_EXIT,
    ExamEventType.COPY_ATTEMPT,
    ExamEventType.PASTE_ATTEMPT,
    ExamEventType.CUT_ATTEMPT,
    ExamEventType.CONTEXT_MENU_ATTEMPT,
    ExamEventType.DEVTOOLS_ATTEMPT,
    ExamEventType.PAGE_LEAVE,
)
CRITICAL_VIOLATIONS = 5

STATUSES = ("in_progress", "completed", "expired", "terminated")


# ---------------------------------------------------------------------------
# Scope
# ---------------------------------------------------------------------------

def _teacher_groups(user):
    teacher = getattr(user, "teacher_profile", None)
    return Group.objects.for_teacher(teacher) if teacher is not None else None


def _teacher_subjects(teacher):
    """Subjects a teacher teaches: their profile plus their group programs."""
    return Subject.objects.filter(
        Q(pk__in=teacher.subjects.values("pk"))
        | Q(pk__in=GroupTeacher.objects.filter(teacher=teacher, subject__isnull=False).values("subject"))
    )


def _public_trainer_q(teacher, prefix: str = "") -> Q:
    """Public trainers belong to nobody's group: a teacher sees those of
    their subjects («направления») and the ones they own."""
    public = Q(**{f"{prefix}is_public": True, f"{prefix}session_type": SessionType.TRAINING})
    mine = Q(**{f"{prefix}test__subject__in": _teacher_subjects(teacher)}) | Q(**{f"{prefix}teacher": teacher})
    return public & mine


def visible_sessions(user) -> QuerySet:
    sessions = TestSession.objects.all()
    if can_view_academy(user):
        return sessions
    groups = _teacher_groups(user)
    if groups is None:
        return sessions.none()
    return sessions.filter(Q(group__in=groups) | _public_trainer_q(user.teacher_profile))


def visible_attempts(user) -> QuerySet:
    attempts = StudentAttempt.objects.filter(user__isnull=True)
    if can_view_academy(user):
        return attempts
    groups = _teacher_groups(user)
    if groups is None:
        return attempts.none()
    # Forward FKs only — no row multiplication, so no distinct() needed.
    return attempts.filter(
        Q(session__group__in=groups) | Q(student__group__in=groups)
        | _public_trainer_q(user.teacher_profile, prefix="session__")
    )


def is_team_view(user) -> bool:
    """Team Lead / Admin pages (teacher performance, all groups)."""
    return can_view_academy(user)


# ---------------------------------------------------------------------------
# Filters
# ---------------------------------------------------------------------------

def _int(value) -> int | None:
    return int(value) if value and str(value).isdigit() else None


def _uuid(value):
    try:
        return uuid.UUID(str(value)) if value else None
    except ValueError:
        return None


def _date(value) -> date | None:
    try:
        return date.fromisoformat(value) if value else None
    except ValueError:
        return None


def status_filter(status: str) -> Q | None:
    return {
        "in_progress": Q(status=AttemptStatus.ACTIVE),
        "completed": Q(status=AttemptStatus.FINISHED) & ~Q(finish_reason=FinishReason.VIOLATIONS),
        "terminated": Q(status=AttemptStatus.FINISHED, finish_reason=FinishReason.VIOLATIONS),
        "expired": Q(status=AttemptStatus.EXPIRED),
    }.get(status)


def filter_attempts(attempts: QuerySet, params) -> QuerySet:
    """Query-string filters; unknown or malformed values are ignored."""
    if group := _int(params.get("group")):
        attempts = attempts.filter(Q(session__group_id=group) | Q(student__group_id=group))
    if teacher := _int(params.get("teacher")):
        attempts = attempts.filter(session__teacher_id=teacher)
    if subject := _int(params.get("subject")):
        attempts = attempts.filter(session__test__subject_id=subject)
    if test := _uuid(params.get("test")):
        attempts = attempts.filter(session__test_id=test)
    if session := _uuid(params.get("session")):
        attempts = attempts.filter(session_id=session)
    mode = params.get("mode")
    if mode == "exam":
        attempts = attempts.filter(session__session_type=SessionType.EXAM)
    elif mode == "training":
        attempts = attempts.filter(session__session_type=SessionType.TRAINING)
    if (q := status_filter(params.get("status", ""))) is not None:
        attempts = attempts.filter(q)
    if day := _date(params.get("date_from")):
        attempts = attempts.filter(started_at__date__gte=day)
    if day := _date(params.get("date_to")):
        attempts = attempts.filter(started_at__date__lte=day)
    if params.get("violations") == "1":
        attempts = attempts.filter(Q(violation_count__gt=0) | Q(tab_switch_count__gt=0))
    if query := (params.get("q") or "").strip()[:100]:
        attempts = attempts.filter(
            Q(student_name__icontains=query) | Q(student__first_name__icontains=query) | Q(student__last_name__icontains=query)
        )
    return attempts


# ---------------------------------------------------------------------------
# Keeping «in progress» honest
# ---------------------------------------------------------------------------

def close_overdue(attempts: QuerySet) -> None:
    """Close Exam Mode and trainer attempts whose time is up (no background
    worker in the project — monitoring reads trigger it, like the pages do)."""
    from . import exam_portal

    overdue = attempts.filter(status=AttemptStatus.ACTIVE, expires_at__lt=timezone.now()).select_related("session__test")
    for attempt in overdue[:200]:
        if attempt.exam_mode:
            exam_portal.ensure_current(attempt)
        elif attempt.session.is_public and attempt.session.session_type == SessionType.TRAINING:
            from apps.training.services import ensure_current

            ensure_current(attempt)


# ---------------------------------------------------------------------------
# Rows
# ---------------------------------------------------------------------------

def annotate_rows(attempts: QuerySet) -> QuerySet:
    live = SessionParticipant.objects.filter(attempt=OuterRef("pk")).values("answered_count")[:1]
    return attempts.select_related("session__test__subject", "session__group", "session__teacher__user", "student__group").annotate(
        answers_total=Count("answers", distinct=True),
        fullscreen_exits=Count("events", filter=Q(events__event_type=ExamEventType.FULLSCREEN_EXIT), distinct=True),
        live_answered=Subquery(live),
    )


def attempt_status(attempt: StudentAttempt) -> str:
    if attempt.status == AttemptStatus.ACTIVE:
        return "in_progress"
    if attempt.status == AttemptStatus.EXPIRED:
        return "expired"
    return "terminated" if attempt.finish_reason == FinishReason.VIOLATIONS else "completed"


def severity(attempt: StudentAttempt) -> str:
    test = attempt.session.test
    limit = test.max_tab_switches
    if (
        attempt.finish_reason == FinishReason.VIOLATIONS
        or attempt.violation_count >= CRITICAL_VIOLATIONS
        or (limit is not None and attempt.tab_switch_count >= limit and attempt.tab_switch_count > 0)
    ):
        return "critical"
    if attempt.violation_count or attempt.tab_switch_count:
        return "warning"
    return "normal"


def _answered(attempt: StudentAttempt) -> int:
    if attempt.status != AttemptStatus.ACTIVE:
        return getattr(attempt, "answers_total", None) or attempt.answers.count()
    drafts = attempt.draft_answers or {}
    from .exam_portal import is_answered

    from_drafts = sum(1 for value in drafts.values() if is_answered(value))
    return from_drafts or (getattr(attempt, "live_answered", None) or 0)


def attempt_row(attempt: StudentAttempt, now=None) -> dict:
    now = now or timezone.now()
    session = attempt.session
    test = session.test
    deadline = attempt_deadline(attempt)
    group = session.group or (attempt.student.group if attempt.student_id else None)
    finished = attempt.status == AttemptStatus.FINISHED
    return {
        "id": str(attempt.pk),
        "student_name": str(attempt.student) if attempt.student_id else attempt.student_name,
        "student_id": attempt.student_id,
        "group": {"id": group.pk, "name": group.name} if group else None,
        "teacher": {"id": session.teacher_id, "name": str(session.teacher)} if session.teacher_id else None,
        "session": {"id": str(session.pk), "title": session.title or test.title},
        "test": {"id": str(test.pk), "title": test.title, "subject": test.subject.name if test.subject_id else ""},
        "mode": "exam" if session.session_type == SessionType.EXAM else "training",
        "exam_mode": attempt.exam_mode,
        "started_at": attempt.started_at,
        "finished_at": attempt.finished_at,
        "expires_at": deadline,
        "remaining_seconds": max(int((deadline - now).total_seconds()), 0) if deadline and attempt.status == AttemptStatus.ACTIVE else None,
        "duration_seconds": int(attempt.duration_seconds) if attempt.duration_seconds is not None else
        (int((now - attempt.started_at).total_seconds()) if attempt.status == AttemptStatus.ACTIVE else None),
        "answered": _answered(attempt),
        "question_total": len(attempt.question_ids or []),
        "status": attempt_status(attempt),
        "score": round(attempt.score) if finished else None,
        "passed": (attempt.score >= test.passing_score) if finished else None,
        "passing_score": test.passing_score,
        "tab_switch_count": attempt.tab_switch_count,
        "fullscreen_exits": getattr(attempt, "fullscreen_exits", 0),
        "violation_count": attempt.violation_count,
        "max_tab_switches": test.max_tab_switches,
        "severity": severity(attempt),
        "finish_reason": attempt.finish_reason,
    }


def attempt_detail(attempt: StudentAttempt) -> dict:
    row = attempt_row(attempt)
    events = list(attempt.events.order_by("timestamp", "id"))
    counts = {kind: 0 for kind in VIOLATION_TYPES}
    for event in events:
        if event.event_type in counts:
            counts[event.event_type] += 1
    if attempt.status == AttemptStatus.ACTIVE:
        drafts = attempt.draft_answers or {}
        from .exam_portal import is_answered

        questions = [
            {"number": n, "question_id": qid, "status": "answered" if is_answered(drafts.get(qid)) else "unanswered"}
            for n, qid in enumerate(attempt.question_ids or [], start=1)
        ]
    else:
        questions = [
            {"number": r["number"], "question_id": str(r["question"].pk), "text": r["question"].text[:200], "status": r["status"]}
            for r in result_rows(attempt)
        ]
    return {
        **row,
        "events": [
            {
                "id": e.pk,
                "type": e.event_type,
                "label": e.get_event_type_display(),
                "severity": e.severity,
                "timestamp": e.timestamp,
                "question": (e.metadata or {}).get("question"),
                "detail": (e.metadata or {}).get("detail", ""),
            }
            for e in events
        ],
        "violations": {kind.value: counts[kind] for kind in VIOLATION_TYPES},
        "questions": questions,
    }


# ---------------------------------------------------------------------------
# Overview
# ---------------------------------------------------------------------------

def _passed_q():
    return Q(status=AttemptStatus.FINISHED, score__gte=F("session__test__passing_score"))


def overview(attempts: QuerySet, sessions: QuerySet) -> dict:
    finished = Q(status=AttemptStatus.FINISHED)
    totals = attempts.aggregate(
        active=Count("pk", filter=Q(status=AttemptStatus.ACTIVE)),
        completed=Count("pk", filter=finished),
        passed=Count("pk", filter=_passed_q()),
        expired=Count("pk", filter=Q(status=AttemptStatus.EXPIRED)),
        terminated=Count("pk", filter=Q(finish_reason=FinishReason.VIOLATIONS)),
        violations=Sum("violation_count"),
        flagged=Count("pk", filter=Q(violation_count__gt=0) | Q(tab_switch_count__gt=0)),
        average=Avg("score", filter=finished),
    )
    active = attempts.filter(status=AttemptStatus.ACTIVE)
    return {
        "active_exams": sessions.filter(
            session_type=SessionType.EXAM, status__in=[SessionStatus.RUNNING, SessionStatus.PAUSED],
        ).filter(pk__in=active.values("session")).count(),
        "active_trainers": active.filter(session__session_type=SessionType.TRAINING).values("session").distinct().count(),
        "active_students": totals["active"],
        "completed": totals["completed"],
        "passed": totals["passed"],
        "failed": totals["completed"] - totals["passed"],
        "expired": totals["expired"],
        "terminated": totals["terminated"],
        "violations": totals["violations"] or 0,
        "flagged_attempts": totals["flagged"],
        "average_score": round(totals["average"]) if totals["average"] is not None else None,
    }


# ---------------------------------------------------------------------------
# Team views (Team Lead / Admin)
# ---------------------------------------------------------------------------

_DURATION = ExpressionWrapper(F("finished_at") - F("started_at"), output_field=DurationField())


def _aggregates():
    finished = Q(status=AttemptStatus.FINISHED)
    return {
        "attempts": Count("pk", distinct=True),
        "students": Count("student_name", distinct=True),
        "active": Count("pk", filter=Q(status=AttemptStatus.ACTIVE), distinct=True),
        "completed": Count("pk", filter=finished, distinct=True),
        "passed": Count("pk", filter=_passed_q(), distinct=True),
        "average": Avg("score", filter=finished),
        "violations": Sum("violation_count"),
        "avg_duration": Avg(_DURATION, filter=finished),
    }


def _stat_row(row: dict) -> dict:
    completed = row["completed"]
    duration = row.get("avg_duration")
    return {
        "attempts": row["attempts"],
        "students": row["students"],
        "active": row["active"],
        "completed": completed,
        "passed": row["passed"],
        "pass_rate": round(row["passed"] / completed * 100) if completed else None,
        "average_score": round(row["average"]) if row["average"] is not None else None,
        "violations": row["violations"] or 0,
        "avg_duration_seconds": int(duration.total_seconds()) if isinstance(duration, timedelta) else None,
    }


def teacher_performance(attempts: QuerySet) -> list[dict]:
    from apps.users.models import Teacher

    rows = attempts.exclude(session__teacher__isnull=True).values("session__teacher").annotate(**_aggregates())
    teachers = {t.pk: t for t in Teacher.objects.select_related("user").filter(pk__in=[r["session__teacher"] for r in rows])}
    result = [
        {"teacher": {"id": r["session__teacher"], "name": str(teachers[r["session__teacher"]])}, **_stat_row(r)}
        for r in rows if r["session__teacher"] in teachers
    ]
    return sorted(result, key=lambda r: r["teacher"]["name"])


def group_stats(attempts: QuerySet) -> list[dict]:
    rows = attempts.exclude(session__group__isnull=True).values("session__group").annotate(**_aggregates())
    groups = {g.pk: g for g in Group.objects.filter(pk__in=[r["session__group"] for r in rows])}
    result = [
        {"group": {"id": r["session__group"], "name": groups[r["session__group"]].name}, **_stat_row(r)}
        for r in rows if r["session__group"] in groups
    ]
    return sorted(result, key=lambda r: r["group"]["name"])


def group_detail(group: Group, attempts: QuerySet, sessions: QuerySet) -> dict:
    attempts = attempts.filter(Q(session__group=group) | Q(student__group=group))
    totals = _stat_row(attempts.aggregate(**_aggregates()))
    students = []
    for row in attempts.values("student_name").annotate(**_aggregates()).order_by("student_name"):
        stats = _stat_row(row)
        stats["failed"] = stats["completed"] - stats["passed"]
        students.append({"student_name": row["student_name"], **stats})
    return {
        "group": {"id": group.pk, "name": group.name},
        **totals,
        "active_exams": sessions.filter(
            group=group, session_type=SessionType.EXAM, status__in=[SessionStatus.RUNNING, SessionStatus.PAUSED],
        ).count(),
        "failed_students": [s["student_name"] for s in students if s["completed"] and not s["passed"]],
        "students_list": students,
    }


@dataclass
class _Difficult:
    number: int
    question_id: str
    text: str
    answered: int
    correct: int
    wrong: int
    rate: int | None


def difficult_questions(session: TestSession, limit: int | None = None) -> list[dict]:
    """Questions of the session's test by success rate, hardest first."""
    questions = session.test.questions.order_by("order", "created_at")
    stats = question_stats([session], questions)
    rows = [
        _Difficult(s.number, str(s.question.pk), s.question.text[:200], s.answered, s.correct, s.wrong, s.rate)
        for s in stats if s.rate is not None
    ]
    rows.sort(key=lambda r: (r.rate, -r.answered))
    rows = rows[:limit] if limit else rows
    return [
        {
            "number": r.number, "question_id": r.question_id, "text": r.text, "answered": r.answered,
            "correct": r.correct, "incorrect": r.wrong, "correct_rate": r.rate, "incorrect_rate": 100 - r.rate,
        }
        for r in rows
    ]


def trainer_stats(sessions: QuerySet, attempts: QuerySet) -> list[dict]:
    rows = attempts.values("session").annotate(**_aggregates())
    by_session = {r["session"]: r for r in rows}
    result = []
    for session in sessions.select_related("test__subject").filter(pk__in=by_session):
        result.append({
            "session": {"id": str(session.pk), "title": session.title or session.test.title},
            "test": {"id": str(session.test_id), "title": session.test.title,
                     "subject": session.test.subject.name if session.test.subject_id else ""},
            "mode": "exam" if session.session_type == SessionType.EXAM else "training",
            "is_public": session.is_public,
            **_stat_row(by_session[session.pk]),
        })
    return sorted(result, key=lambda r: -r["attempts"])
