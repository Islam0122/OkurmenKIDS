"""Public survey page — server-rendered so it works in WhatsApp/Telegram
in-app browsers and on slow phones without relying on JavaScript (JS only
adds progress and show/hide niceties on top). Validation is always
``services.submission.submit_response``, the same as the JSON API."""
from __future__ import annotations

from django.shortcuts import redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_protect

from .models import Survey, SurveyQuestion, SurveyResponse
from .public import FeedbackSubmitThrottle, has_submitted, mark_submitted, public_context_lines
from .services.submission import UNAVAILABLE_MESSAGES, SubmissionData, SubmissionError, submit_response
from .views import _published_survey

QT = SurveyQuestion.QuestionType
V = SurveyResponse.Visibility

# Rough reading/answering time per question type, for the "≈ N мин" hint.
_SECONDS_PER_QUESTION = {QT.TEXT: 45, QT.SINGLE_CHOICE: 12, QT.MULTIPLE_CHOICE: 18}


def _plural(n: int, one: str, few: str, many: str) -> str:
    mod10, mod100 = n % 10, n % 100
    if mod10 == 1 and mod100 != 11:
        return one
    if 2 <= mod10 <= 4 and not 12 <= mod100 <= 14:
        return few
    return many


def _privacy_mode(survey: Survey, allowed: list[str]) -> str:
    """Which privacy notice the page may honestly show (see models.py):

    "choice"            respondent picks open/anonymous
    "open"              name is shown to the admin
    "anonymous"         no name, no contact data, no IP stored at all
    "anonymous_child"   no respondent name, but a child's name is asked —
                        so we must not call it fully anonymous
    """
    if len(allowed) == 2:
        return "choice"
    if allowed[0] == V.OPEN:
        return "open"
    if survey.child_name_mode_for(V.ANONYMOUS) != Survey.ChildNameMode.NOT_COLLECTED:
        return "anonymous_child"
    return "anonymous"


def _question_rows(survey: Survey, values: dict, errors: dict) -> list[dict]:
    rows = []
    for index, q in enumerate(survey.questions.prefetch_related("options").order_by("order", "id"), start=1):
        key = f"q_{q.id}"
        value = values.get(key)
        selected = {str(v) for v in value} if isinstance(value, list) else ({str(value)} if value else set())
        rows.append(
            {
                "index": index,
                "q": q,
                "name": key,
                "value": value if isinstance(value, str) else "",
                "selected": selected,
                "error": errors.get(key),
                "options": list(q.options.all()),
            }
        )
    return rows


def render_survey_form(request, survey: Survey, *, preview: bool = False, values=None, errors=None, status=200):
    values = values or {}
    errors = errors or {}
    allowed = survey.allowed_visibilities()
    visibility = values.get("visibility") or (allowed[0] if len(allowed) == 1 else "")
    context = {
        "survey": survey,
        "preview": preview,
        "questions": _question_rows(survey, values, errors),
        "context_lines": public_context_lines(survey),
        "allowed_visibilities": allowed,
        "offers_choice": len(allowed) == 2,
        "visibility": visibility,
        "child_mode_open": survey.child_name_mode_for(SurveyResponse.Visibility.OPEN)
        if SurveyResponse.Visibility.OPEN in allowed
        else Survey.ChildNameMode.NOT_COLLECTED,
        "child_mode_anonymous": survey.child_name_mode_for(SurveyResponse.Visibility.ANONYMOUS)
        if SurveyResponse.Visibility.ANONYMOUS in allowed
        else Survey.ChildNameMode.NOT_COLLECTED,
        "asks_child": any(survey.child_name_mode_for(v) != Survey.ChildNameMode.NOT_COLLECTED for v in allowed),
        "anonymous_asks_child": SurveyResponse.Visibility.ANONYMOUS in allowed
        and survey.child_name_mode_for(SurveyResponse.Visibility.ANONYMOUS) != Survey.ChildNameMode.NOT_COLLECTED,
        "values": values,
        "errors": errors,
        "form_error": errors.get("__all__") or errors.get("answers"),
        "required_count": sum(1 for q in survey.questions.all() if q.is_required),
        **_intro_context(survey, allowed),
    }
    return render(request, "feedback/public_form.html", context, status=status)


def _intro_context(survey: Survey, allowed: list[str]) -> dict:
    questions = list(survey.questions.all())
    has_identity_step = len(allowed) == 2 or V.OPEN in allowed or any(
        survey.child_name_mode_for(v) != Survey.ChildNameMode.NOT_COLLECTED for v in allowed
    )
    seconds = sum(_SECONDS_PER_QUESTION[q.question_type] for q in questions) + (20 if has_identity_step else 0)
    count = len(questions)
    return {
        "is_student": survey.audience == Survey.Audience.STUDENT,
        "question_count": count,
        "question_count_label": f"{count} {_plural(count, 'вопрос', 'вопроса', 'вопросов')}",
        "minutes": max(1, -(-seconds // 60)),
        "privacy_mode": _privacy_mode(survey, allowed),
        "has_identity_step": has_identity_step,
    }


def _render_message(request, survey: Survey, *, title: str, message: str, icon: str, status=200, note: str = ""):
    return render(
        request,
        "feedback/public_message.html",
        {"survey": survey, "title": title, "message": message, "icon": icon, "note": note},
        status=status,
    )


def _values_from_post(survey: Survey, post) -> dict:
    values = {
        "visibility": post.get("visibility", ""),
        "respondent_name": post.get("respondent_name", ""),
        "child_name": post.get("child_name", ""),
    }
    for q in survey.questions.all():
        key = f"q_{q.id}"
        values[key] = post.getlist(key) if q.question_type == QT.MULTIPLE_CHOICE else post.get(key, "")
    return values


@never_cache
@csrf_protect
def public_survey_view(request, token):
    survey = _published_survey(token)

    availability = survey.availability()
    if availability != Survey.Availability.AVAILABLE:
        return _render_message(
            request,
            survey,
            title="Опрос недоступен",
            message=UNAVAILABLE_MESSAGES[availability],
            icon="lock",
            note="Если вы считаете, что это ошибка, свяжитесь с администрацией OkurmenKIDS.",
        )
    if not survey.allow_multiple_submissions and has_submitted(request, survey):
        is_student = survey.audience == Survey.Audience.STUDENT
        return _render_message(
            request,
            survey,
            title="Ты уже ответил(а)" if is_student else "Вы уже ответили",
            message="Спасибо! Твой ответ на этот опрос уже получен."
            if is_student
            else "Спасибо! Ваш ответ на этот опрос уже получен.",
            icon="check",
        )

    if request.method != "POST":
        return render_survey_form(request, survey)

    values = _values_from_post(survey, request.POST)
    if not FeedbackSubmitThrottle().allow_request(request, None):
        return render_survey_form(
            request,
            survey,
            values=values,
            errors={"__all__": "Слишком много отправок с этого устройства. Попробуйте позже."},
            status=429,
        )

    data = SubmissionData(
        visibility=values["visibility"] or None,
        respondent_name=values["respondent_name"],
        child_name=values["child_name"],
        answers={k[2:]: v for k, v in values.items() if k.startswith("q_")},
    )
    try:
        submit_response(survey, data)
    except SubmissionError as exc:
        return render_survey_form(request, survey, values=values, errors=exc.errors, status=400)

    response = redirect("feedback_public_done", token=survey.public_token)
    mark_submitted(response, survey)
    return response


@never_cache
def public_survey_done_view(request, token):
    survey = _published_survey(token)
    is_student = survey.audience == Survey.Audience.STUDENT
    return render(
        request,
        "feedback/public_message.html",
        {
            "survey": survey,
            "success": True,
            "icon": "check",
            "title": "Спасибо за отзыв!",
            # The admin-configured confirmation message from the survey.
            "message": survey.confirmation_message or "Ваш ответ отправлен.",
            "note": "Твоё мнение важно для нас — оно поможет сделать занятия ещё интереснее."
            if is_student
            else "Ваш отзыв поможет нам улучшить обучение вашего ребёнка.",
            "footnote": "Ответы видит только администрация OkurmenKIDS.",
        },
    )
