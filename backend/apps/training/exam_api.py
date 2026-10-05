"""Exam attempts in the shared test UI (the React portal's test engine).

Training and Exam are one testing system: the same React screen runs both,
with the same response shapes as the training API (training.services.
attempt_state / result_payload), so nothing is drawn twice. The rules are
Exam Mode's own (apps.testing.services.exam_portal): one attempt per student
(no new attempt on refresh, attempt limit), autosave into draft_answers,
the violation policy (Test.max_tab_switches), the server deadline
(ensure_current closes an overdue attempt; auto-submit), required questions
on submit.

Entry: /exam/?key=… (testing.public_views) validates the session key and
the student on the server, starts or resumes the attempt (start_exam) and
redirects to the React page with a signed token in the URL fragment.

Access: the token is bound to the attempt, its student (or none, in a
name-only session) and its session (`exam_token`), and issued only to the
browser that started the attempt. Every request re-checks it against
the stored attempt (owner, session, exam mode) — the browser's copy
(sessionStorage) is never trusted on its own. A bad, expired, altered or
foreign token is 403 before the attempt is even looked up, so attempt ids
can't be probed. A finished attempt stays readable (its result) and
refuses every change (409).

    GET   /api/v1/training/exam-attempts/<id>/                 state (questions, saved answers, position, remaining time)
    PATCH /api/v1/training/exam-attempts/<id>/                 {current_question_id, seq} — where the student is
    PUT   /api/v1/training/exam-attempts/<id>/answers/<qid>/   autosave one answer (+ seq: older saves never win)
    POST  /api/v1/training/exam-attempts/<id>/events/          tab switch / fullscreen exit / …
    POST  /api/v1/training/exam-attempts/<id>/submit/          {timed_out} → result (idempotent)
    GET   /api/v1/training/exam-attempts/<id>/result/          result (by the test's show_result rules)
"""
from __future__ import annotations

from django.core import signing
from django.core.exceptions import ValidationError
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.testing.models import AttemptStatus, SessionStatus, SessionType, StudentAttempt
from apps.testing.services import exam_portal as portal
from apps.testing.services.attempts import AttemptError

from . import services
from .serializers import AnswerSerializer, EventSerializer
from .views import TOKEN_HEADER, TrainingReadThrottle, TrainingWriteThrottle

EXAM_TOKEN_SALT = "exam.attempt"
# Long enough for any exam; the attempt itself closes at its deadline.
EXAM_TOKEN_MAX_AGE = 24 * 3600


# The page's clock (Date.now()) orders autosaves and moves; anything outside
# this range is not a real timestamp.
MAX_SEQ = 2 ** 53


def _token_subject(attempt: StudentAttempt) -> str:
    return f"{attempt.pk}:{attempt.student_id or ''}:{attempt.session_id}"


def exam_token(attempt: StudentAttempt) -> str:
    return signing.TimestampSigner(salt=EXAM_TOKEN_SALT).sign(_token_subject(attempt))


def portal_exam_url(attempt: StudentAttempt) -> str | None:
    """Where the exam portal runs this attempt — None when the portal
    address isn't configured (the legacy /exam/ form is used then)."""
    from .models import PortalSettings

    base = (PortalSettings.load().portal_url or "").rstrip("/")
    if not base:
        return None
    return f"{base}/exam/{attempt.pk}#t={exam_token(attempt)}"


class ExamError(Exception):
    def __init__(self, message: str, code: str, http_status: int):
        super().__init__(message)
        self.message, self.code, self.http_status = message, code, http_status


def _forbidden() -> ExamError:
    return ExamError("Экзаменге кирүүгө уруксат жок.", "forbidden", status.HTTP_403_FORBIDDEN)


def _owned(attempt_id, token: str | None) -> StudentAttempt:
    """The attempt the token was issued for — or 403. The token names the
    attempt, its student and its session; all three must match the stored
    row (an attempt can't be opened with another student's or another
    exam's token, nor a token outlive a change of owner)."""
    try:
        subject = signing.TimestampSigner(salt=EXAM_TOKEN_SALT).unsign(token or "", max_age=EXAM_TOKEN_MAX_AGE)
    except signing.BadSignature:  # includes SignatureExpired
        raise _forbidden()
    if subject.split(":", 1)[0] != str(attempt_id):
        raise _forbidden()  # a valid token, for another attempt id
    attempt = (
        StudentAttempt.objects.select_related("session__test__subject", "student")
        .filter(pk=attempt_id, exam_mode=True, user__isnull=True, session__session_type=SessionType.EXAM).first()
    )
    if attempt is None or _token_subject(attempt) != subject:
        raise _forbidden()  # same answer as a bad token: nothing to learn about other attempts
    return portal.ensure_current(attempt)


def _seq(raw) -> int | None:
    if isinstance(raw, int) and not isinstance(raw, bool) and 0 < raw < MAX_SEQ:
        return raw
    return None


def _closed(attempt: StudentAttempt) -> ExamError:
    return ExamError("Экзамен аяктады.", "closed", status.HTTP_409_CONFLICT)


def exam_state(attempt: StudentAttempt) -> dict:
    """The training payload, with Exam rules: no answer checking, no
    correct answers while the exam runs."""
    state = services.attempt_state(attempt)
    for question in state["questions"]:
        question["checked"] = False
        question["feedback"] = None
    session = attempt.session
    state.update({
        "mode": "exam",
        "current_question_id": str(attempt.current_question_id) if attempt.current_question_id else None,
        "show_explanation": False,
        "paused": session.effective_status == SessionStatus.PAUSED,
        "subject": session.test.subject.name if session.test.subject_id else "",
    })
    return state


class ExamView(APIView):
    permission_classes = [AllowAny]
    authentication_classes: list = []
    throttle_classes = [TrainingReadThrottle]

    def handle_exception(self, exc):
        if isinstance(exc, ExamError):
            return Response({"detail": exc.message, "code": exc.code}, status=exc.http_status)
        if isinstance(exc, portal.AttemptClosed):
            return Response({"detail": "Экзамен аяктады.", "code": "closed"}, status=status.HTTP_409_CONFLICT)
        if isinstance(exc, AttemptError):
            return Response({"detail": exc.messages[0], "code": "invalid"}, status=status.HTTP_400_BAD_REQUEST)
        if isinstance(exc, ValidationError):
            return Response({"detail": exc.messages[0], "code": "invalid"}, status=status.HTTP_400_BAD_REQUEST)
        return super().handle_exception(exc)

    def attempt(self, request, attempt_id):
        return _owned(attempt_id, request.META.get(TOKEN_HEADER))


@extend_schema(tags=["Exam (shared test UI)"])
class ExamAttemptView(ExamView):
    def get(self, request, attempt_id):
        attempt = self.attempt(request, attempt_id)
        return Response(exam_state(attempt))

    def get_throttles(self):
        return [TrainingWriteThrottle()] if self.request.method == "PATCH" else super().get_throttles()

    def patch(self, request, attempt_id):
        """The question the student moved to (debounced by the page)."""
        attempt = self.attempt(request, attempt_id)
        if attempt.status != AttemptStatus.ACTIVE:
            raise _closed(attempt)
        question_id, seq = request.data.get("current_question_id"), _seq(request.data.get("seq"))
        if not isinstance(question_id, str) or seq is None:
            return Response({"detail": "Позициянын форматы туура эмес.", "code": "invalid"}, status=status.HTTP_400_BAD_REQUEST)
        stored = portal.save_position(attempt, question_id, seq, request=request)
        return Response({"saved": stored, "remaining_seconds": services.remaining_seconds(attempt)})


@extend_schema(tags=["Exam (shared test UI)"])
class ExamAnswerView(ExamView):
    throttle_classes = [TrainingWriteThrottle]

    def put(self, request, attempt_id, question_id):
        attempt = self.attempt(request, attempt_id)
        if attempt.status != AttemptStatus.ACTIVE:
            raise _closed(attempt)
        body = AnswerSerializer(data=request.data)
        if not body.is_valid():
            return Response({"detail": "Жооптун форматы туура эмес.", "code": "invalid"}, status=status.HTTP_400_BAD_REQUEST)
        value = {"options": body.validated_data.get("options", []), "text": body.validated_data.get("text", "")}
        order = {qid: n for n, qid in enumerate(attempt.question_ids or [], start=1)}
        seq = _seq(request.data.get("seq"))
        attempt = portal.save_drafts(attempt, {str(question_id): value}, current=order.get(str(question_id)),
                                     seqs={str(question_id): seq} if seq else None, request=request)
        return Response({"saved": True, "remaining_seconds": services.remaining_seconds(attempt)})


@extend_schema(tags=["Exam (shared test UI)"])
class ExamEventView(ExamView):
    throttle_classes = [TrainingWriteThrottle]

    def post(self, request, attempt_id):
        body = EventSerializer(data=request.data)
        if not body.is_valid():
            return Response({"detail": "Окуянын форматы туура эмес.", "code": "invalid"}, status=status.HTTP_400_BAD_REQUEST)
        result = portal.record_event(self.attempt(request, attempt_id), body.validated_data["event_type"],
                                     body.validated_data.get("metadata"), request)
        if result.terminated:
            return Response({"detail": "Экзамен эрежелерди бузуу себебинен аяктады.", "code": "terminated"}, status=status.HTTP_409_CONFLICT)
        attempt = result.attempt
        return Response({"tab_switch_count": attempt.tab_switch_count, "violation_count": attempt.violation_count,
                         "max_tab_switches": attempt.session.test.max_tab_switches})


@extend_schema(tags=["Exam (shared test UI)"])
class ExamSubmitView(ExamView):
    throttle_classes = [TrainingWriteThrottle]

    def post(self, request, attempt_id):
        attempt = self.attempt(request, attempt_id)
        attempt = portal.submit_exam(attempt, {}, timed_out=bool(request.data.get("timed_out")), request=request)
        return Response({**services.result_payload(attempt), "mode": "exam"})


@extend_schema(tags=["Exam (shared test UI)"])
class ExamResultView(ExamView):
    def get(self, request, attempt_id):
        attempt = self.attempt(request, attempt_id)
        return Response({**services.result_payload(attempt), "mode": "exam"})

