"""Exam Mode JSON endpoints, used by static/testing/js/exam_mode.js.

    GET   /student/api/exam-attempts/<id>/state/     server clock, status, counters
    PATCH /student/api/exam-attempts/<id>/answers/   autosave (JSON body)
    POST  /student/api/exam-attempts/<id>/events/    a violation / page-leave

Authentication is the student portal's Django session (student_auth);
CSRF is enforced (header X-CSRFToken, or the form field for sendBeacon).
Only the signed-in student's own Exam Mode attempt is found — anyone
else's is a 404. A closed attempt answers 409 with the result URL.
"""
from __future__ import annotations

import json

from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_http_methods

from .models import StudentAttempt
from .services import exam_portal as portal
from .services.attempts import AttemptError
from .student_auth import student_required_api

MAX_BODY_BYTES = 512 * 1024


def _attempt(request, attempt_id) -> StudentAttempt | None:
    return (
        StudentAttempt.objects.select_related("session__test")
        .filter(pk=attempt_id, student=request.student, exam_mode=True)
        .first()
    )


def _not_found() -> JsonResponse:
    return JsonResponse({"error": "Попытка не найдена."}, status=404)


def _closed(attempt: StudentAttempt, **extra) -> JsonResponse:
    return JsonResponse({
        **portal.attempt_state(attempt),
        "error": "Экзамен уже завершён.",
        "closed": True,
        "result_url": reverse("student_exam_result", args=[attempt.session_id, attempt.pk]),
        **extra,
    }, status=409)


def _json_body(request) -> dict:
    if len(request.body) > MAX_BODY_BYTES:
        raise ValidationError("Слишком большой запрос.")
    if request.content_type == "application/json":
        try:
            data = json.loads(request.body or b"{}")
        except (ValueError, UnicodeDecodeError):
            raise ValidationError("Неверный JSON.")
        if not isinstance(data, dict):
            raise ValidationError("Неверный JSON.")
        return data
    # sendBeacon from the page-leave handler: form data with the CSRF token.
    data = {"event_type": request.POST.get("event_type", "")}
    if request.POST.get("question", "").isdigit():
        data["metadata"] = {"question": int(request.POST["question"])}
    return data


def _int_or_none(value) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


@never_cache
@require_http_methods(["GET"])
@student_required_api
def state_view(request, attempt_id):
    attempt = _attempt(request, attempt_id)
    if attempt is None:
        return _not_found()
    attempt = portal.ensure_current(attempt, request)
    if attempt.status != "active":
        return _closed(attempt)
    return JsonResponse(portal.attempt_state(attempt))


@csrf_protect
@require_http_methods(["PATCH"])
@student_required_api
def answers_view(request, attempt_id):
    attempt = _attempt(request, attempt_id)
    if attempt is None:
        return _not_found()
    try:
        body = _json_body(request)
        attempt = portal.save_drafts(
            attempt, body.get("answers") or {}, current=_int_or_none(body.get("current")), request=request,
        )
    except portal.AttemptClosed as closed:
        return _closed(closed.attempt)
    except AttemptError as exc:
        return JsonResponse({"error": exc.messages[0], "paused": True}, status=409)
    except ValidationError as exc:
        return JsonResponse({"error": exc.messages[0]}, status=400)
    return JsonResponse({**portal.attempt_state(attempt), "saved": True})


@csrf_protect
@require_http_methods(["POST"])
@student_required_api
def events_view(request, attempt_id):
    attempt = _attempt(request, attempt_id)
    if attempt is None:
        return _not_found()
    try:
        body = _json_body(request)
        result = portal.record_event(attempt, str(body.get("event_type", "")), body.get("metadata"), request)
    except portal.AttemptClosed as closed:
        return _closed(closed.attempt)
    except ValidationError as exc:
        return JsonResponse({"error": exc.messages[0]}, status=400)
    if result.terminated:
        return _closed(
            result.attempt, terminated=True,
            error="Экзамен завершён из-за превышения допустимого количества нарушений.",
        )
    return JsonResponse({**portal.attempt_state(result.attempt), "terminated": False})
