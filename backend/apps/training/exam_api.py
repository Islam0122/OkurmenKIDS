"""Exam attempts in the shared test UI (the React portal's test engine).

Training and Exam are one testing system: the same React screen runs both,
with the same response shapes as the training API (training.services.
attempt_state / result_payload), so nothing is drawn twice. The rules are
Exam Mode's own (apps.testing.services.exam_portal): one attempt per student
(no new attempt on refresh, attempt limit), autosave into draft_answers,
the violation policy (Test.max_tab_switches), the server deadline
(ensure_current closes an overdue attempt; auto-submit), required questions
on submit.

Access: a signed token bound to the attempt id, issued only to the signed-in
student by the student portal (`exam_token`) — the portal hands it to the
React page in the URL fragment. Anonymous visitors, Team Leads and Trainers
have no way to get one.

    GET  /api/v1/training/exam-attempts/<id>/                 state (questions, saved answers, remaining time)
    PUT  /api/v1/training/exam-attempts/<id>/answers/<qid>/   autosave one answer
    POST /api/v1/training/exam-attempts/<id>/events/          tab switch / fullscreen exit / …
    POST /api/v1/training/exam-attempts/<id>/submit/          {timed_out} → result
    GET  /api/v1/training/exam-attempts/<id>/result/          result (by the test's show_result rules)
"""
from __future__ import annotations

from django.core import signing
from django.core.exceptions import ValidationError
from django.urls import reverse
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.testing.models import AttemptStatus, SessionStatus, StudentAttempt
from apps.testing.services import exam_portal as portal
from apps.testing.services.attempts import AttemptError

from . import services
from .serializers import AnswerSerializer, EventSerializer
from .views import TOKEN_HEADER, TrainingReadThrottle, TrainingWriteThrottle

EXAM_TOKEN_SALT = "exam.attempt"
# Long enough for any exam; the attempt itself closes at its deadline.
EXAM_TOKEN_MAX_AGE = 24 * 3600


def exam_token(attempt: StudentAttempt) -> str:
    return signing.TimestampSigner(salt=EXAM_TOKEN_SALT).sign(str(attempt.pk))


def portal_exam_url(attempt: StudentAttempt) -> str | None:
    """Where the shared test UI runs this attempt — None when the portal
    address isn't configured (the student portal's own page is used then)."""
    from .models import PortalSettings

    base = (PortalSettings.load().portal_url or "").rstrip("/")
    if not base:
        return None
    return f"{base}/exam/{attempt.pk}#t={exam_token(attempt)}"


class ExamError(Exception):
    def __init__(self, message: str, code: str, http_status: int):
        super().__init__(message)
        self.message, self.code, self.http_status = message, code, http_status


def _owned(attempt_id, token: str | None) -> StudentAttempt:
    try:
        valid = signing.TimestampSigner(salt=EXAM_TOKEN_SALT).unsign(token or "", max_age=EXAM_TOKEN_MAX_AGE) == str(attempt_id)
    except signing.BadSignature:
        valid = False
    if not valid:
        raise ExamError("Экзаменге кирүүгө уруксат жок.", "forbidden", status.HTTP_403_FORBIDDEN)
    attempt = (
        StudentAttempt.objects.select_related("session__test__subject", "student")
        .filter(pk=attempt_id, exam_mode=True, student__isnull=False).first()
    )
    if attempt is None:
        raise ExamError("Экзамен табылган жок.", "not_found", status.HTTP_404_NOT_FOUND)
    return portal.ensure_current(attempt)


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
        "show_explanation": False,
        "paused": session.effective_status == SessionStatus.PAUSED,
        "subject": session.test.subject.name if session.test.subject_id else "",
    })
    return state


def _back_url(request) -> str:
    return request.build_absolute_uri(reverse("student_portal_dashboard"))


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
        return Response({**exam_state(attempt), "back_url": _back_url(request)})


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
        attempt = portal.save_drafts(attempt, {str(question_id): value}, current=order.get(str(question_id)), request=request)
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
        return Response({**services.result_payload(attempt), "mode": "exam", "back_url": _back_url(request)})


@extend_schema(tags=["Exam (shared test UI)"])
class ExamResultView(ExamView):
    def get(self, request, attempt_id):
        attempt = self.attempt(request, attempt_id)
        return Response({**services.result_payload(attempt), "mode": "exam", "back_url": _back_url(request)})

