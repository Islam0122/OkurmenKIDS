"""Helpers shared by the public HTML page and the public JSON API."""
from __future__ import annotations

from django.conf import settings
from django.core import signing
from django.urls import reverse
from rest_framework.throttling import SimpleRateThrottle

from apps.feedback.models import Survey, SurveyQuestion

_COOKIE_SALT = "feedback.submitted"
_COOKIE_MAX_AGE = 60 * 60 * 24 * 365


class _IPThrottle(SimpleRateThrottle):
    """Per-client-IP rate limit. The IP only ever lives in the cache key
    for the throttle window — it is never written to the database.

    Works with both a DRF Request and a plain Django HttpRequest (it only
    reads request.META), so the HTML page and the API share one bucket."""

    def get_cache_key(self, request, view):
        return self.cache_format % {"scope": self.scope, "ident": self.get_ident(request)}


class FeedbackViewThrottle(_IPThrottle):
    scope = "feedback_view"


class FeedbackSubmitThrottle(_IPThrottle):
    scope = "feedback_submit"


def public_url(request, survey: Survey) -> str:
    path = reverse("feedback_public", args=[survey.public_token])
    base = getattr(settings, "FEEDBACK_PUBLIC_BASE_URL", "")
    if base:
        return base.rstrip("/") + path
    return request.build_absolute_uri(path)


def _cookie_name(survey: Survey) -> str:
    # Keyed on the pk (not the token) so regenerating the link doesn't
    # reset the "already answered" state for people who answered.
    return f"okfb_{survey.pk}"


def has_submitted(request, survey: Survey) -> bool:
    try:
        return request.get_signed_cookie(_cookie_name(survey), salt=_COOKIE_SALT, default=None) == "1"
    except signing.BadSignature:
        return False


def mark_submitted(response, survey: Survey) -> None:
    response.set_signed_cookie(
        _cookie_name(survey),
        "1",
        salt=_COOKIE_SALT,
        max_age=_COOKIE_MAX_AGE,
        httponly=True,
        samesite="Lax",
        secure=getattr(settings, "SESSION_COOKIE_SECURE", False),
    )


def public_context_lines(survey: Survey) -> list[tuple[str, str]]:
    """Admin-chosen context shown to respondents (never respondent data)."""
    lines = []
    if survey.group_id:
        lines.append(("Группа", survey.group.name))
    if survey.teacher_id:
        lines.append(("Тренер", str(survey.teacher)))
    if survey.subject_id:
        lines.append(("Предмет", survey.subject.name))
    return lines


def public_payload(survey: Survey) -> dict:
    """The only survey data a public client ever receives."""
    questions = []
    for q in survey.questions.prefetch_related("options").order_by("order", "id"):
        item = {
            "id": q.id,
            "text": q.text,
            "help_text": q.help_text,
            "question_type": q.question_type,
            "is_required": q.is_required,
        }
        if q.question_type == SurveyQuestion.QuestionType.TEXT:
            item.update(is_multiline=q.is_multiline, min_length=q.min_length, max_length=q.effective_max_length)
        else:
            item["options"] = [{"id": o.id, "text": o.text} for o in q.options.all()]
            if q.question_type == SurveyQuestion.QuestionType.MULTIPLE_CHOICE:
                item.update(min_selections=q.min_selections, max_selections=q.max_selections)
        questions.append(item)

    return {
        "title": survey.title,
        "description": survey.description,
        "audience": survey.audience,
        "allowed_visibilities": survey.allowed_visibilities(),
        "child_name": {v: survey.child_name_mode_for(v) for v in survey.allowed_visibilities()},
        "context": [{"label": label, "value": value} for label, value in public_context_lines(survey)],
        "questions": questions,
    }
