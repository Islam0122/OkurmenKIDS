"""Exam Mode: the attempt lifecycle of the exam portal (/exam/?key=… → the
React exam, apps.training.exam_api) — start, autosave, the current
question, violation events, submit, expiry.

Built on services/attempts.py (join, grading, deadlines) and the existing
models; nothing here trusts the browser. Every action re-reads the attempt,
its status and deadline (ownership is the token's, checked by exam_api),
and an attempt whose time is up is closed here with the answers saved so
far — whatever the page's own timer says.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import validate_ipv46_address
from django.db import transaction
from django.utils import timezone

from ..models import (
    EXAM_VIOLATION_EVENTS,
    AttemptStatus,
    ExamAttemptEvent,
    ExamEventType,
    FinishReason,
    QuestionType,
    SessionStatus,
    StudentAttempt,
    TestSession,
)
from . import participants as participant_events
from .attempts import (
    AttemptError,
    SubmittedAnswer,
    attempt_deadline,
    attempt_questions,
    expire_attempt,
    grade_and_finish,
    join,
)

# Network tolerance for an autosave or the auto-submit sent at 00:00: the
# request may arrive a moment after the deadline. Past it the attempt is
# closed with what was saved.
ANSWER_GRACE = timedelta(seconds=5)
# An auto-submit (timed_out) skips the required-question check only this
# close to the deadline — otherwise it is an ordinary submit.
TIMED_OUT_WINDOW = timedelta(seconds=15)

MAX_TEXT_ANSWER = 5_000
MAX_CODE_ANSWER = 20_000
# A misbehaving page can't flood the log: past this, events still update
# the counters but are no longer stored one by one.
MAX_EVENTS_PER_ATTEMPT = 2_000

VIOLATION_EVENTS = EXAM_VIOLATION_EVENTS
# Logged for the timeline (back on the page, fullscreen restored) — never violations.
INFO_EVENTS = frozenset({ExamEventType.TAB_RETURN, ExamEventType.FULLSCREEN_ENTER})
CLIENT_EVENTS = VIOLATION_EVENTS | INFO_EVENTS | {ExamEventType.PAGE_LEAVE}


class AttemptClosed(Exception):
    """The attempt no longer takes answers (submitted, expired, terminated)."""

    def __init__(self, attempt: StudentAttempt):
        super().__init__("Экзамен уже завершён.")
        self.attempt = attempt


# ---------------------------------------------------------------------------
# Event log
# ---------------------------------------------------------------------------

def _client_ip(request) -> str | None:
    if request is None or not getattr(settings, "EXAM_EVENTS_STORE_IP", True):
        return None
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    ip = (forwarded.split(",")[0].strip() if forwarded else "") or request.META.get("REMOTE_ADDR", "")
    try:
        validate_ipv46_address(ip)
    except ValidationError:
        return None
    return ip


def _clean_metadata(raw) -> dict:
    """Only small, known fields — never answers or free-form page data."""
    if not isinstance(raw, dict):
        return {}
    clean = {}
    question = raw.get("question")
    if isinstance(question, int) and not isinstance(question, bool) and 0 < question <= 1000:
        clean["question"] = question
    for key, limit in (("detail", 80), ("key", 24)):
        value = raw.get(key)
        if isinstance(value, str) and value.strip():
            clean[key] = value.strip()[:limit]
    return clean


def log_event(attempt: StudentAttempt, event_type: str, request=None, metadata: dict | None = None) -> None:
    if event_type in CLIENT_EVENTS and attempt.events.count() >= MAX_EVENTS_PER_ATTEMPT:
        return
    ExamAttemptEvent.objects.create(
        attempt=attempt,
        event_type=event_type,
        metadata=metadata or {},
        user_agent=(request.META.get("HTTP_USER_AGENT", "") if request is not None else "")[:255],
        ip_address=_client_ip(request),
    )


# ---------------------------------------------------------------------------
# Attempt lifecycle
# ---------------------------------------------------------------------------

def active_attempts(session: TestSession, student=None, student_name: str = ""):
    """The unfinished attempts join() would resume: a roster student's, or —
    a session without a roster — those under the same name."""
    attempts = session.attempts.filter(status=AttemptStatus.ACTIVE)
    if student is not None:
        return attempts.filter(student=student)
    return attempts.filter(student__isnull=True, user__isnull=True, student_name=(student_name or "").strip())


def start_exam(session: TestSession, student=None, request=None, *, student_name: str = "") -> StudentAttempt:
    """Start (or resume) an Exam Mode attempt — a roster student's, or by
    name in a session without a roster. join() applies the session state,
    the test's availability, the roster and the attempt limit; an overdue
    attempt is closed first (graded with what was saved)."""
    for current in active_attempts(session, student, student_name):
        ensure_current(current, request)
    attempt = join(session, student_name=student_name, student=student)
    if not attempt.exam_mode:
        # A new attempt, or one opened on the legacy /exam/ form before.
        attempt.exam_mode = True
        fields = ["exam_mode"]
        if attempt.expires_at is None and (limit := session.effective_time_limit_minutes):
            attempt.expires_at = attempt.started_at + timedelta(minutes=limit)
            fields.append("expires_at")
        attempt.save(update_fields=fields)
        log_event(attempt, ExamEventType.EXAM_STARTED, request, {"detail": f"{len(attempt.question_ids)} вопросов"})
    return attempt


def drafts_as_answers(attempt: StudentAttempt) -> dict[str, SubmittedAnswer]:
    answers = {}
    for question_id, value in (attempt.draft_answers or {}).items():
        if isinstance(value, dict):
            answers[str(question_id)] = SubmittedAnswer(
                text=str(value.get("text") or ""),
                options=[str(o) for o in value.get("options") or []],
            )
    return answers


def close_attempt(attempt: StudentAttempt, reason: str, *, answers: dict[str, SubmittedAnswer] | None = None,
                  request=None) -> StudentAttempt:
    """Finish an active attempt with its saved answers (plus ``answers``).
    Idempotent and race-safe: the row is locked, a second call sees it closed.
    Time ran out on a test without auto-submit → closed as expired, ungraded."""
    with transaction.atomic():
        locked = StudentAttempt.objects.select_for_update().select_related("session__test").get(pk=attempt.pk)
        if locked.status != AttemptStatus.ACTIVE:
            return locked
        deadline = attempt_deadline(locked)
        locked.finish_reason = reason
        locked.save(update_fields=["finish_reason"])
        if reason == FinishReason.TIME_EXPIRED and not locked.session.test.auto_submit:
            expire_attempt(locked)
            log_event(locked, ExamEventType.TIME_EXPIRED, request, {"detail": "без автоотправки"})
            return locked
        merged = drafts_as_answers(locked)
        merged.update(answers or {})
        grade_and_finish(locked, merged)
        if reason == FinishReason.TIME_EXPIRED and deadline and locked.finished_at > deadline:
            # Time spent ends at the deadline, not when the page came back.
            locked.finished_at = deadline
            locked.save(update_fields=["finished_at"])
        event = {
            FinishReason.TIME_EXPIRED: ExamEventType.TIME_EXPIRED,
            FinishReason.VIOLATIONS: ExamEventType.EXAM_TERMINATED,
        }.get(reason, ExamEventType.EXAM_SUBMITTED)
        log_event(locked, event, request, {"detail": FinishReason(reason).label})
    return locked


def ensure_current(attempt: StudentAttempt, request=None) -> StudentAttempt:
    """Close the attempt if its time is up or its session has ended; return
    it as stored now. Called before anything reads or changes an attempt."""
    if attempt.status != AttemptStatus.ACTIVE:
        return attempt
    now = timezone.now()
    session = attempt.session
    session.sync_schedule(now)
    deadline = attempt_deadline(attempt)
    if deadline and now >= deadline + ANSWER_GRACE:
        return close_attempt(attempt, FinishReason.TIME_EXPIRED, request=request)
    status = session.effective_status_at(now)
    if status in TestSession.ENDED_STATUSES and now >= (session.ended_at or now) + ANSWER_GRACE:
        return close_attempt(attempt, FinishReason.SESSION_CLOSED, request=request)
    return attempt


def close_overdue_attempts(queryset=None) -> None:
    """Close abandoned Exam Mode attempts whose time is up (the admin
    monitoring page calls this — there is no background worker)."""
    queryset = queryset if queryset is not None else StudentAttempt.objects.all()
    for attempt in queryset.filter(exam_mode=True, status=AttemptStatus.ACTIVE).select_related("session__test"):
        ensure_current(attempt)


def _open_attempt(attempt: StudentAttempt, request=None) -> StudentAttempt:
    attempt = ensure_current(attempt, request)
    if attempt.status != AttemptStatus.ACTIVE:
        raise AttemptClosed(attempt)
    if attempt.session.effective_status == SessionStatus.PAUSED:
        raise AttemptError("Сессия на паузе — дождитесь, пока преподаватель её продолжит.")
    return attempt


def _clean_answers(attempt: StudentAttempt, raw) -> dict[str, dict]:
    """Validate an autosave payload against the attempt's own questions."""
    if not isinstance(raw, dict):
        raise ValidationError("Неверный формат ответов.")
    questions = {str(q.pk): q for q in attempt_questions(attempt)}
    if len(raw) > len(questions):
        raise ValidationError("Слишком много ответов.")
    clean = {}
    for question_id, value in raw.items():
        question = questions.get(str(question_id))
        if question is None:
            raise ValidationError("Вопрос не относится к этой попытке.")
        if not isinstance(value, dict):
            raise ValidationError("Неверный формат ответа.")
        if question.question_type in (QuestionType.SINGLE_CHOICE, QuestionType.MULTIPLE_CHOICE):
            options = value.get("options") or []
            if not isinstance(options, list) or not all(isinstance(o, str) for o in options):
                raise ValidationError("Неверный формат вариантов ответа.")
            valid = {str(o.pk) for o in question.display_options}
            options = list(dict.fromkeys(options))
            if any(o not in valid for o in options):
                raise ValidationError("Вариант ответа не относится к вопросу.")
            if question.question_type == QuestionType.SINGLE_CHOICE and len(options) > 1:
                raise ValidationError("В этом вопросе можно выбрать только один вариант.")
            clean[str(question.pk)] = {"options": options}
        else:
            text = value.get("text", "")
            if not isinstance(text, str):
                raise ValidationError("Неверный формат ответа.")
            limit = MAX_CODE_ANSWER if question.question_type == QuestionType.CODE else MAX_TEXT_ANSWER
            if len(text) > limit:
                raise ValidationError(f"Ответ слишком длинный (максимум {limit} символов).")
            clean[str(question.pk)] = {"text": text}
    return clean


def _is_answered(value) -> bool:
    return isinstance(value, dict) and (bool((value.get("text") or "").strip()) or bool(value.get("options")))


# Shared with the public training portal (apps.training), which keeps its
# answers in the same draft format and validates them the same way.
clean_answers = _clean_answers
is_answered = _is_answered


def save_drafts(attempt: StudentAttempt, raw_answers, *, current: int | None = None, seqs: dict[str, int] | None = None,
                request=None) -> StudentAttempt:
    """Autosave: merge validated answers into the attempt's draft.

    ``seqs``: the page's clock when each answer was given (the shared test
    UI). Two saves of one question may arrive out of order (or from two
    tabs); a save older than the stored one is ignored, never written over
    the newer answer. Without a seq (the server-rendered page) the save is
    applied as before."""
    attempt = _open_attempt(attempt, request)
    clean = _clean_answers(attempt, raw_answers)
    with transaction.atomic():
        locked = StudentAttempt.objects.select_for_update().select_related("session__test").get(pk=attempt.pk)
        if locked.status != AttemptStatus.ACTIVE:
            raise AttemptClosed(locked)
        drafts = dict(locked.draft_answers or {})
        for question_id, seq in (seqs or {}).items():
            if question_id not in clean:
                continue
            stored = drafts.get(question_id)
            if isinstance(stored, dict) and isinstance(stored.get("seq"), int) and stored["seq"] > seq:
                del clean[question_id]  # stale: a newer answer is already saved
            else:
                clean[question_id] = {**clean[question_id], "seq": seq}
        drafts.update(clean)
        locked.draft_answers = drafts
        locked.draft_saved_at = timezone.now()
        locked.save(update_fields=["draft_answers", "draft_saved_at"])
        if clean:
            order = {qid: n for n, qid in enumerate(locked.question_ids, start=1)}
            numbers = sorted(order[qid] for qid in clean if qid in order)
            log_event(locked, ExamEventType.ANSWER_SAVED, request, {"detail": "вопросы " + ", ".join(map(str, numbers))})
    answered = sum(1 for value in drafts.values() if _is_answered(value))
    participant_events.attempt_progress(locked, current=current, answered=answered)
    return locked


def save_position(attempt: StudentAttempt, question_id: str, seq: int, request=None) -> bool:
    """The question the student is on (restored after a reload). One
    conditional UPDATE: only an active attempt, only a newer position —
    a late request from before can't move the student back. Returns whether
    it was stored."""
    attempt = _open_attempt(attempt, request)
    order = {qid: n for n, qid in enumerate(attempt.question_ids or [], start=1)}
    if str(question_id) not in order:
        raise ValidationError("Вопрос не относится к этой попытке.")
    stored = StudentAttempt.objects.filter(
        pk=attempt.pk, status=AttemptStatus.ACTIVE, position_seq__lt=seq,
    ).update(current_question_id=question_id, position_seq=seq)
    if stored:
        participant_events.attempt_progress(attempt, current=order[str(question_id)])
    return bool(stored)


@dataclass
class EventResult:
    attempt: StudentAttempt
    terminated: bool


def record_event(attempt: StudentAttempt, event_type: str, metadata=None, request=None) -> EventResult:
    """A violation (or page-leave) reported by the Exam Mode page."""
    if event_type not in CLIENT_EVENTS:
        raise ValidationError("Неизвестное событие.")
    attempt = ensure_current(attempt, request)
    if attempt.status != AttemptStatus.ACTIVE:
        raise AttemptClosed(attempt)
    test = attempt.session.test
    with transaction.atomic():
        locked = StudentAttempt.objects.select_for_update().get(pk=attempt.pk)
        if locked.status != AttemptStatus.ACTIVE:
            raise AttemptClosed(locked)
        fields = []
        tracked_tab = event_type == ExamEventType.TAB_SWITCH and test.track_tab_switches
        if tracked_tab:
            locked.tab_switch_count += 1
            fields.append("tab_switch_count")
        counted = event_type in VIOLATION_EVENTS and not (
            (event_type == ExamEventType.FULLSCREEN_EXIT and not test.require_fullscreen)
            or (event_type == ExamEventType.TAB_SWITCH and not test.track_tab_switches)
        )
        if counted:
            locked.violation_count += 1
            fields.append("violation_count")
        if fields:
            locked.save(update_fields=fields)
        log_event(locked, event_type, request, _clean_metadata(metadata))
    if event_type == ExamEventType.PAGE_LEAVE:
        participant_events.attempt_progress(locked, left=True)
    limit = test.max_tab_switches
    if tracked_tab and limit is not None and locked.tab_switch_count > limit:
        return EventResult(close_attempt(locked, FinishReason.VIOLATIONS, request=request), terminated=True)
    return EventResult(locked, terminated=False)


def _posted_answers(attempt: StudentAttempt, posted: dict[str, SubmittedAnswer]) -> dict[str, SubmittedAnswer]:
    """Final form answers: only the attempt's questions, texts capped. Option
    ids are filtered against the question again by grade_and_finish().

    Empty fields don't wipe the autosaved draft (a form without a field — an
    unticked checkbox group, a page without JS — says nothing); the page
    flushes pending autosaves, including cleared answers, before it submits."""
    questions = {str(q.pk): q for q in attempt_questions(attempt)}
    clean = {}
    for question_id, answer in posted.items():
        question = questions.get(question_id)
        if question is None or answer.is_empty:
            continue
        limit = MAX_CODE_ANSWER if question.question_type == QuestionType.CODE else MAX_TEXT_ANSWER
        clean[question_id] = SubmittedAnswer(text=answer.text[:limit], options=answer.options)
    return clean


def submit_exam(attempt: StudentAttempt, posted: dict[str, SubmittedAnswer], *, timed_out: bool = False,
                request=None) -> StudentAttempt:
    """«Завершить экзамен» (or the page's auto-submit at 00:00)."""
    attempt = ensure_current(attempt, request)
    if attempt.status != AttemptStatus.ACTIVE:
        return attempt  # already closed — the result page shows how
    if attempt.session.effective_status == SessionStatus.PAUSED:
        raise AttemptError("Сессия на паузе — экзамен можно завершить после продолжения.")
    deadline = attempt_deadline(attempt)
    near_deadline = bool(timed_out and deadline and timezone.now() >= deadline - TIMED_OUT_WINDOW)
    posted_clean = _posted_answers(attempt, posted)
    answers = drafts_as_answers(attempt)
    answers.update(posted_clean)
    if not near_deadline:
        missing = [
            str(number) for number, q in enumerate(attempt_questions(attempt), start=1)
            if q.is_required and answers.get(str(q.pk), SubmittedAnswer()).is_empty
        ]
        if missing:
            raise AttemptError(f"Ответьте на обязательные вопросы: {', '.join(missing)}.")
    reason = FinishReason.TIME_EXPIRED if near_deadline else FinishReason.SUBMITTED
    # Only the posted answers: close_attempt() merges the drafts as stored
    # under its row lock — the copy read above may be older than an
    # autosave that committed meanwhile, and must not overwrite it.
    return close_attempt(attempt, reason, answers=posted_clean, request=request)


def remaining_seconds(attempt: StudentAttempt, now=None) -> int | None:
    deadline = attempt_deadline(attempt)
    if deadline is None:
        return None
    return max(int((deadline - (now or timezone.now())).total_seconds()), 0)
