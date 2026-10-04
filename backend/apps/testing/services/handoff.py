"""Opening an LMS account's own attempt on the student test pages (/exam/).

The test-taking UI is the server-rendered /exam/ flow (questions, Назад /
Далее, timer, localStorage autosave, result page). It only shows an attempt
to the browser that started it — the attempt id is remembered in the Django
session. An LMS user (the Team Lead) signs in with a JWT instead, so the LMS
API hands them a short-lived signed link to *their own* attempt; the /exam/
page checks it, remembers the attempt for that browser and drops the token
from the URL. A token names one attempt and its owner: it can't open anyone
else's attempt, and an attempt with no owning account can't be opened at all.
"""
from __future__ import annotations

from django.core import signing
from django.urls import reverse

from ..models import StudentAttempt

SALT = "testing.lms-attempt-handoff"
MAX_AGE_SECONDS = 300


def token_for(attempt: StudentAttempt) -> str:
    if attempt.user_id is None:
        raise ValueError("Only an attempt owned by an LMS account can be handed off.")
    return signing.dumps({"a": str(attempt.pk), "u": attempt.user_id}, salt=SALT)


def take_url(request, attempt: StudentAttempt) -> str:
    return request.build_absolute_uri(f"{reverse('testing_public_take', args=[attempt.pk])}?t={token_for(attempt)}")


def result_url(request, attempt: StudentAttempt) -> str:
    return request.build_absolute_uri(f"{reverse('testing_public_result', args=[attempt.pk])}?t={token_for(attempt)}")


def verified_attempt_id(token: str, attempt_id) -> str | None:
    """The attempt id if ``token`` is a valid, fresh handoff for exactly that
    attempt and its owner still owns it and is active; else None."""
    try:
        data = signing.loads(token, salt=SALT, max_age=MAX_AGE_SECONDS)
    except signing.BadSignature:
        return None
    if not isinstance(data, dict) or data.get("a") != str(attempt_id) or not data.get("u"):
        return None
    owned = StudentAttempt.objects.filter(pk=attempt_id, user_id=data["u"], user__is_active=True).exists()
    return str(attempt_id) if owned else None
