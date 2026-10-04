"""Public training portal: tests, attempts by name, answers, feedback,
results and the leaderboard — on top of the testing module.

A «test» here is a running training session marked public
(TestSession.is_public). An attempt is a StudentAttempt with only a name
(no LMS Student, no account). Answers are kept as a draft on the attempt
(StudentAttempt.draft_answers — the Exam Mode format) and graded into
Answer rows by the testing module's own grading when the attempt is
submitted or its time runs out. Nothing the browser says is trusted: the
attempt is found by its id *and* a signed token, every answer is validated
against the attempt's own questions, and the deadline is checked here.
"""
from __future__ import annotations

import re
import unicodedata
from datetime import timedelta

from django.core import signing
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.testing.models import (
    AttemptStatus,
    ExamEventType,
    FinishReason,
    SessionStatus,
    SessionType,
    StudentAttempt,
    TestSession,
    TestStatus,
)
from apps.testing.services.attempts import (
    attempt_deadline,
    attempt_questions,
    grade_and_finish,
    is_passed,
    pick_question_ids,
    result_rows,
    session_error,
)
from apps.testing.services.exam_portal import (
    ANSWER_GRACE,
    CLIENT_EVENTS,
    VIOLATION_EVENTS,
    _clean_metadata,
    clean_answers,
    drafts_as_answers,
    is_answered,
)
from apps.testing.services.exam_portal import log_event as _log_exam_event
from apps.testing.services.grading import attempt_score, check_answer
from apps.testing.services.sessions import sync_due_sessions

NAME_MIN = 2
NAME_MAX = 50
# Letters (any script) and digits, inner spaces, dots, hyphens, apostrophes.
_NAME_RE = re.compile(r"^[^\W_](?:[\w .'’\-]*[^\W_.])?$")
TOKEN_SALT = "training.attempt"
LEADERBOARD_MAX = 100


class TrainingError(Exception):
    """A student-facing reason; ``status`` is the HTTP status to answer with."""

    def __init__(self, message: str, status: int = 400, code: str = "invalid"):
        super().__init__(message)
        self.message = message
        self.status = status
        self.code = code


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def _natural(text: str) -> list:
    """«Month 2» before «Month 10»."""
    return [int(part) if part.isdigit() else part.casefold() for part in re.split(r"(\d+)", text)]


def public_sessions():
    """Running public training sessions of published tests, grouped by their
    category (the test's Subject) and naturally ordered by title inside it;
    trainers without a subject come last."""
    candidates = TestSession.objects.filter(is_public=True, session_type=SessionType.TRAINING)
    sync_due_sessions(candidates)
    sessions = (
        candidates.filter(status=SessionStatus.RUNNING, test__status=TestStatus.ACTIVE)
        .select_related("test__subject")
        .order_by("created_at")
    )
    visible = [s for s in sessions if s.test.availability_error() is None]
    return sorted(visible, key=lambda s: (
        s.test.subject_id is None,
        _natural(s.test.subject.name) if s.test.subject_id else [],
        _natural(s.title or s.test.title),
    ))


def category_of(test) -> dict | None:
    """A trainer's category is its test's Subject (IT, English, Soft Skills, …)."""
    subject = test.subject if test.subject_id else None
    if subject is None:
        return None
    from django.utils.text import slugify

    return {"id": subject.pk, "name": subject.name, "slug": slugify(subject.name) or f"subject-{subject.pk}"}


def get_public_session(session_id) -> TestSession:
    for session in public_sessions():
        if str(session.pk) == str(session_id):
            return session
    raise TrainingError("Тест табылган жок.", status=404, code="not_found")


def question_count(test) -> int:
    total = test.questions.count()
    if test.questions_per_attempt and test.questions_per_attempt < total:
        return test.questions_per_attempt
    return total


# ---------------------------------------------------------------------------
# Attempts
# ---------------------------------------------------------------------------

def clean_student_name(raw) -> str:
    if not isinstance(raw, str):
        raise TrainingError("Атыңызды жазыңыз.", code="name_required")
    name = unicodedata.normalize("NFC", " ".join(raw.split()))
    if not name:
        raise TrainingError("Атыңызды жазыңыз.", code="name_required")
    if len(name) < NAME_MIN:
        raise TrainingError(f"Аты кеминде {NAME_MIN} белгиден турушу керек.", code="name_too_short")
    if len(name) > NAME_MAX:
        raise TrainingError(f"Аты {NAME_MAX} белгиден ашпашы керек.", code="name_too_long")
    if not _NAME_RE.match(name):
        raise TrainingError("Атта тамгалар, сандар, боштук, дефис жана апостроф гана болушу мүмкүн.", code="name_invalid")
    return name


def start_attempt(session: TestSession, student_name: str, request=None) -> StudentAttempt:
    name = clean_student_name(student_name)
    error = session_error(session)
    if error:
        raise TrainingError(error, status=409, code="unavailable")
    test = session.test
    if not test.questions.exists():
        raise TrainingError("Бул тестте азырынча суроолор жок.", status=409, code="no_questions")
    if not session.can_student_attempt(student_name=name):
        raise TrainingError("Бул тест үчүн аракеттердин саны бүттү.", status=409, code="attempt_limit")
    if not test.allow_retry and session.attempts.filter(
        student_name__iexact=name, status=AttemptStatus.FINISHED,
    ).exists():
        raise TrainingError("Бул тренажёрду кайра өтүүгө болбойт.", status=409, code="retry_disabled")
    with transaction.atomic():
        attempt = StudentAttempt.objects.create(session=session, student_name=name)
        attempt.question_ids = pick_question_ids(test, seed=attempt.pk.int)
        limit = session.effective_time_limit_minutes
        attempt.expires_at = attempt.started_at + timedelta(minutes=limit) if limit else None
        attempt.save(update_fields=["question_ids", "expires_at"])
        log_event(attempt, ExamEventType.TRAINING_STARTED, request, {"detail": f"{len(attempt.question_ids)} суроо"})
    return attempt


def log_event(attempt: StudentAttempt, event_type: str, request=None, metadata: dict | None = None) -> None:
    """Participants of the public trainer are anonymous visitors: only the
    event itself is kept — no IP address, no browser string."""
    _log_exam_event(attempt, event_type, None, metadata)


def attempt_token(attempt: StudentAttempt) -> str:
    return signing.dumps(str(attempt.pk), salt=TOKEN_SALT)


def _portal_attempts():
    return StudentAttempt.objects.select_related("session__test__subject").filter(
        session__is_public=True, session__session_type=SessionType.TRAINING,
        student__isnull=True, user__isnull=True,
    )


def get_attempt(attempt_id) -> StudentAttempt:
    """Read access (the result page): the attempt id is a random UUID."""
    attempt = _portal_attempts().filter(pk=attempt_id).first()
    if attempt is None:
        raise TrainingError("Аракет табылган жок.", status=404, code="not_found")
    return attempt


def get_owned_attempt(attempt_id, token: str | None) -> StudentAttempt:
    """Write access: the id plus the token handed out when it started."""
    try:
        valid = signing.loads(token or "", salt=TOKEN_SALT) == str(attempt_id)
    except signing.BadSignature:
        valid = False
    if not valid:
        raise TrainingError("Аракетке кирүүгө уруксат жок.", status=403, code="forbidden")
    return ensure_current(get_attempt(attempt_id))


def finish_attempt(attempt: StudentAttempt, reason: str = FinishReason.SUBMITTED, request=None) -> StudentAttempt:
    """Grade the saved answers and finish. Locked and idempotent."""
    with transaction.atomic():
        locked = StudentAttempt.objects.select_for_update().select_related("session__test").get(pk=attempt.pk)
        if locked.status != AttemptStatus.ACTIVE:
            return locked
        deadline = attempt_deadline(locked)
        locked.finish_reason = reason
        locked.save(update_fields=["finish_reason"])
        grade_and_finish(locked, drafts_as_answers(locked))
        if reason == FinishReason.TIME_EXPIRED and deadline and locked.finished_at > deadline:
            locked.finished_at = deadline  # time spent ends at the deadline
            locked.save(update_fields=["finished_at"])
        event = {
            FinishReason.TIME_EXPIRED: ExamEventType.TIME_EXPIRED,
            FinishReason.VIOLATIONS: ExamEventType.EXAM_TERMINATED,
        }.get(reason, ExamEventType.TRAINING_SUBMITTED)
        log_event(locked, event, request, {"detail": FinishReason(reason).label})
    return locked


def ensure_current(attempt: StudentAttempt) -> StudentAttempt:
    """Finish an attempt whose time is up or whose session has ended."""
    if attempt.status != AttemptStatus.ACTIVE:
        return attempt
    now = timezone.now()
    deadline = attempt_deadline(attempt)
    if deadline and now >= deadline + ANSWER_GRACE:
        return finish_attempt(attempt, FinishReason.TIME_EXPIRED)
    if attempt.session.effective_status_at(now) in TestSession.ENDED_STATUSES:
        return finish_attempt(attempt, FinishReason.SESSION_CLOSED)
    return attempt


def _open(attempt: StudentAttempt) -> StudentAttempt:
    if attempt.status != AttemptStatus.ACTIVE:
        raise TrainingError("Тренировка аяктаган.", status=409, code="closed")
    if attempt.session.effective_status == SessionStatus.PAUSED:
        raise TrainingError("Тренировка убактылуу токтотулган.", status=409, code="paused")
    return attempt


def save_answer(attempt: StudentAttempt, question_id: str, payload, request=None) -> StudentAttempt:
    _open(attempt)
    if not isinstance(payload, dict):
        raise TrainingError("Жооптун форматы туура эмес.")
    value = {k: payload[k] for k in ("options", "text") if k in payload}
    try:
        clean = clean_answers(attempt, {str(question_id): value})
    except ValidationError as exc:
        raise TrainingError(exc.messages[0])
    with transaction.atomic():
        locked = StudentAttempt.objects.select_for_update().select_related("session__test").get(pk=attempt.pk)
        _open(locked)
        drafts = dict(locked.draft_answers or {})
        if (drafts.get(str(question_id)) or {}).get("checked"):
            raise TrainingError("Бул суроонун жообу текшерилген — аны өзгөртүүгө болбойт.", status=409, code="locked")
        drafts.update(clean)
        locked.draft_answers = drafts
        locked.draft_saved_at = timezone.now()
        locked.save(update_fields=["draft_answers", "draft_saved_at"])
        number = (locked.question_ids.index(str(question_id)) + 1) if str(question_id) in locked.question_ids else None
        log_event(locked, ExamEventType.ANSWER_SAVED, request, {"question": number} if number else {})
    return locked


def _question(attempt: StudentAttempt, question_id: str):
    for question in attempt_questions(attempt):
        if str(question.pk) == str(question_id):
            return question
    raise TrainingError("Суроо бул аракетке тиешелүү эмес.", status=404, code="not_found")


def feedback(question, draft: dict) -> dict:
    """Training feedback for one checked answer."""
    is_correct, _ = check_answer(question, draft.get("text", ""), draft.get("options", []))
    status = "pending" if is_correct is None else ("correct" if is_correct else "incorrect")
    return {
        "status": status,
        "correct_option_ids": [str(o.pk) for o in question.display_options if o.is_correct],
        "correct_answers": list(question.correct_answers or []) if question.question_type == "text" else [],
        "code_examples": list(question.code_tests or [])[:3] if question.question_type == "code" else [],
        "explanation": (question.metadata or {}).get("explanation", ""),
    }


def check_question(attempt: StudentAttempt, question_id: str) -> dict:
    """«Текшерүү»: lock the answer and return the feedback (only when the
    test shows correct answers — Test.show_correct_answers)."""
    _open(attempt)
    if not attempt.session.test.show_correct_answers:
        raise TrainingError("Бул тестте жоопторду дароо текшерүү өчүрүлгөн.", status=403, code="feedback_disabled")
    question = _question(attempt, question_id)
    with transaction.atomic():
        locked = StudentAttempt.objects.select_for_update().get(pk=attempt.pk)
        _open(locked)
        drafts = dict(locked.draft_answers or {})
        draft = dict(drafts.get(str(question_id)) or {})
        if not is_answered(draft):
            raise TrainingError("Адегенде жооп бериңиз.", code="unanswered")
        if not draft.get("checked"):
            draft["checked"] = True
            drafts[str(question_id)] = draft
            locked.draft_answers = drafts
            locked.save(update_fields=["draft_answers"])
    return feedback(question, draft)


def record_event(attempt: StudentAttempt, event_type: str, metadata=None, request=None) -> tuple[StudentAttempt, bool]:
    """An event reported by the portal's exam layout (tab switch, fullscreen
    exit, copy attempt, …). Counted on the attempt per the test's security
    settings; tab switches past Test.max_tab_switches end the attempt.
    Returns (attempt, terminated)."""
    if event_type not in CLIENT_EVENTS:
        raise TrainingError("Белгисиз окуя.", code="unknown_event")
    _open(attempt)
    test = attempt.session.test
    with transaction.atomic():
        locked = StudentAttempt.objects.select_for_update().get(pk=attempt.pk)
        _open(locked)
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
    limit = test.max_tab_switches
    if tracked_tab and limit is not None and locked.tab_switch_count > limit:
        return finish_attempt(locked, FinishReason.VIOLATIONS, request), True
    return locked, False


def security_settings(session: TestSession) -> dict:
    test = session.test
    return {
        "require_fullscreen": test.require_fullscreen,
        "track_tab_switches": test.track_tab_switches,
        "max_tab_switches": test.max_tab_switches,
        "block_copy_paste": test.block_copy_paste,
    }


def exam_url_for(session: TestSession) -> str:
    """The trainer's own exam link, else the portal's."""
    from .models import PortalSettings

    return session.exam_url or PortalSettings.load().exam_url


# ---------------------------------------------------------------------------
# What the API returns
# ---------------------------------------------------------------------------

def remaining_seconds(attempt: StudentAttempt) -> int | None:
    deadline = attempt_deadline(attempt)
    if deadline is None or attempt.status != AttemptStatus.ACTIVE:
        return None if deadline is None else 0
    return max(int((deadline - timezone.now()).total_seconds()), 0)


def attempt_state(attempt: StudentAttempt) -> dict:
    test = attempt.session.test
    drafts = attempt.draft_answers or {}
    show_feedback = test.show_correct_answers
    questions = []
    for question in attempt_questions(attempt):
        draft = drafts.get(str(question.pk)) or {}
        checked = bool(draft.get("checked"))
        questions.append({
            "id": str(question.pk),
            "type": question.question_type,
            "text": question.text,
            "image_url": question.image_url or None,
            "hint": question.hint,
            "language": question.language or None,
            "starter_code": question.starter_code if question.question_type == "code" else "",
            "points": question.points,
            "is_required": question.is_required,
            "options": [
                {"id": str(o.pk), "text": o.text, "image_url": o.image_url or None} for o in question.display_options
            ],
            "answer": {"options": draft.get("options", []), "text": draft.get("text", "")} if is_answered(draft) else None,
            "checked": checked,
            "feedback": feedback(question, draft) if checked and show_feedback else None,
        })
    return {
        **attempt_summary(attempt),
        "status": attempt.status,
        "remaining_seconds": remaining_seconds(attempt),
        "show_explanation": show_feedback,
        "security": security_settings(attempt.session),
        "tab_switch_count": attempt.tab_switch_count,
        "violation_count": attempt.violation_count,
        "questions": questions,
    }


def attempt_summary(attempt: StudentAttempt) -> dict:
    session = attempt.session
    return {
        "attempt_id": str(attempt.pk),
        "test_id": str(session.pk),
        "test_title": session.title or session.test.title,
        "student_name": attempt.student_name,
        "started_at": attempt.started_at,
        "expires_at": attempt_deadline(attempt),
    }


def result_payload(attempt: StudentAttempt) -> dict:
    test = attempt.session.test
    finished = attempt.status == AttemptStatus.FINISHED
    payload = {
        **attempt_summary(attempt),
        "status": "completed" if finished else attempt.status,
        "finish_reason": attempt.finish_reason,
        "finished_at": attempt.finished_at,
        "duration_seconds": int(attempt.duration_seconds) if attempt.duration_seconds is not None else None,
        "show_result": test.show_result,
        "passing_score": test.passing_score,
    }
    if not finished:
        return payload
    if not test.show_result:
        return {**payload, "review": []}
    score = attempt_score(attempt)
    payload.update({
        "score": score.earned,
        "max_score": score.possible,
        "percentage": round(attempt.score),
        "total": score.total_questions,
        "correct": score.correct,
        "incorrect": score.answered - score.correct - score.pending,
        "skipped": score.total_questions - score.answered,
        "pending": score.pending,
        "passed": is_passed(attempt, score),
        "review": _review(attempt) if test.show_correct_answers else [],
    })
    return payload


def _review(attempt: StudentAttempt) -> list[dict]:
    rows = []
    for row in result_rows(attempt):
        question, answer = row["question"], row["answer"]
        rows.append({
            "number": row["number"],
            "question_id": str(question.pk),
            "type": question.question_type,
            "text": question.text,
            "status": row["status"],
            "selected": [o.text for o in row["selected"]],
            "answer_text": answer.answer_text if answer else "",
            "correct": [o.text for o in row["correct_options"]] or list(question.correct_answers or []),
            "explanation": (question.metadata or {}).get("explanation", ""),
        })
    return rows


def leaderboard(session: TestSession | None = None, limit: int = 50) -> list[dict]:
    """Best finished result per name (per test), best first: score, then
    time. Only names and scores — nothing else about the student."""
    attempts = (
        _portal_attempts()
        .filter(status=AttemptStatus.FINISHED, finished_at__isnull=False, session__test__show_result=True)
        .order_by("-finished_at")
    )
    if session is not None:
        attempts = attempts.filter(session=session)
    best: dict[tuple, StudentAttempt] = {}
    for attempt in attempts[:5000]:
        key = (attempt.session_id, attempt.student_name.casefold())
        current = best.get(key)
        if current is None or _rank_key(attempt) < _rank_key(current):
            best[key] = attempt
    ranked = sorted(best.values(), key=_rank_key)[: min(limit, LEADERBOARD_MAX)]
    return [
        {
            "rank": index,
            "student_name": attempt.student_name,
            "score": round(attempt.score),
            "duration_seconds": int(attempt.duration_seconds or 0),
            "finished_at": attempt.finished_at,
            "test_id": str(attempt.session_id),
            "test_title": attempt.session.title or attempt.session.test.title,
        }
        for index, attempt in enumerate(ranked, start=1)
    ]


def _rank_key(attempt: StudentAttempt):
    return (-attempt.score, attempt.duration_seconds or 0, attempt.finished_at)
