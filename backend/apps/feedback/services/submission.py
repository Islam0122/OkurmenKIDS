"""Public survey submission — the one server-side validator for answers.

Used by both the public HTML page and the public JSON API; client-side
validation is only a convenience and is never trusted. Everything a
respondent sends is checked against the survey as stored in the database:
unknown questions and options that don't belong to the question are
rejected, never silently dropped or accepted.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from django.db import transaction
from django.utils import timezone

from apps.feedback.models import (
    NAME_MAX_LENGTH,
    Survey,
    SurveyAnswer,
    SurveyAnswerOption,
    SurveyQuestion,
    SurveyResponse,
)

QT = SurveyQuestion.QuestionType

UNAVAILABLE_MESSAGES = {
    Survey.Availability.DRAFT: "Опрос ещё не опубликован.",
    Survey.Availability.CLOSED: "Опрос закрыт и больше не принимает ответы.",
    Survey.Availability.NOT_STARTED: "Приём ответов ещё не начался.",
    Survey.Availability.ENDED: "Срок приёма ответов истёк.",
    Survey.Availability.FULL: "Опрос собрал максимальное количество ответов.",
}


class SubmissionError(Exception):
    """Validation failed; `errors` maps a field key to a message.

    Keys: "visibility", "respondent_name", "child_name", "q_<question id>",
    "answers" (malformed/unknown questions) and "__all__" (survey unavailable).
    """

    def __init__(self, errors: dict[str, str]):
        super().__init__(errors)
        self.errors = errors


@dataclass
class SubmissionData:
    visibility: str | None = None
    respondent_name: str = ""
    child_name: str = ""
    # question id -> str (text) | option id (single) | list of option ids (multiple)
    answers: dict[Any, Any] = field(default_factory=dict)


def clean_text(value: Any) -> str:
    """Normalise free text: str only, no NUL bytes, unified line breaks,
    outer whitespace stripped. Rendering is always escaped separately."""
    if value is None:
        return ""
    if not isinstance(value, str):
        value = str(value)
    return value.replace("\x00", "").replace("\r\n", "\n").replace("\r", "\n").strip()


def _to_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None


def _plural_symbols(n: int) -> str:
    mod10, mod100 = n % 10, n % 100
    if mod10 == 1 and mod100 != 11:
        return f"{n} символ"
    if 2 <= mod10 <= 4 and not 12 <= mod100 <= 14:
        return f"{n} символа"
    return f"{n} символов"


def _validate_answer(question: SurveyQuestion, raw: Any, option_ids: set[int]):
    """Returns (error | None, cleaned value | None). A cleaned value of None
    means "not answered" (allowed only for optional questions)."""
    if question.question_type == QT.TEXT:
        if isinstance(raw, (list, dict)):
            return "Некорректный ответ.", None
        text = clean_text(raw)
        if not text:
            return ("Это обязательный вопрос." if question.is_required else None), None
        if len(text) > question.effective_max_length:
            return f"Не длиннее {_plural_symbols(question.effective_max_length)}.", None
        if question.min_length and len(text) < question.min_length:
            return f"Минимум {_plural_symbols(question.min_length)}.", None
        return None, text

    if question.question_type == QT.SINGLE_CHOICE:
        if raw in (None, "", []):
            return ("Выберите один вариант." if question.is_required else None), None
        option_id = _to_int(raw)
        if option_id is None or option_id not in option_ids:
            return "Выбран недопустимый вариант.", None
        return None, [option_id]

    # MULTIPLE_CHOICE
    if raw in (None, ""):
        raw = []
    if not isinstance(raw, (list, tuple)):
        raw = [raw]
    ids = [_to_int(v) for v in raw]
    if any(i is None or i not in option_ids for i in ids):
        return "Выбран недопустимый вариант.", None
    if len(ids) != len(set(ids)):
        return "Вариант выбран несколько раз.", None
    if not ids:
        return ("Выберите хотя бы один вариант." if question.is_required else None), None
    if question.min_selections and len(ids) < question.min_selections:
        return f"Выберите минимум {question.min_selections}.", None
    if question.max_selections and len(ids) > question.max_selections:
        return f"Выберите не больше {question.max_selections}.", None
    return None, ids


def _validate_identity(survey: Survey, data: SubmissionData, errors: dict) -> tuple[str, str, str]:
    allowed = survey.allowed_visibilities()
    visibility = data.visibility or (allowed[0] if len(allowed) == 1 else None)
    if visibility not in allowed:
        errors["visibility"] = "Выберите, как отправить отзыв: открыто или анонимно."
        return "", "", ""

    respondent_name = ""
    if visibility == SurveyResponse.Visibility.OPEN:
        respondent_name = clean_text(data.respondent_name)
        if not respondent_name:
            errors["respondent_name"] = "Укажите ваше имя — это открытый отзыв."
        elif len(respondent_name) > NAME_MAX_LENGTH:
            errors["respondent_name"] = f"Не длиннее {NAME_MAX_LENGTH} символов."

    child_name = ""
    child_mode = survey.child_name_mode_for(visibility)
    if child_mode != Survey.ChildNameMode.NOT_COLLECTED:
        child_name = clean_text(data.child_name)
        if not child_name and child_mode == Survey.ChildNameMode.REQUIRED:
            errors["child_name"] = "Укажите имя ребёнка."
        elif len(child_name) > NAME_MAX_LENGTH:
            errors["child_name"] = f"Не длиннее {NAME_MAX_LENGTH} символов."
    # Anything sent for a field the survey doesn't collect is discarded,
    # never stored — an anonymous response can't smuggle a name in.
    return visibility, respondent_name, child_name


def submit_response(survey: Survey, data: SubmissionData) -> SurveyResponse:
    with transaction.atomic():
        # Row lock serialises concurrent submissions so max_responses can't
        # be overshot (no-op on SQLite, real on PostgreSQL).
        survey = Survey.objects.select_for_update().get(pk=survey.pk)
        availability = survey.availability()
        if availability != Survey.Availability.AVAILABLE:
            raise SubmissionError({"__all__": UNAVAILABLE_MESSAGES[availability]})

        errors: dict[str, str] = {}
        visibility, respondent_name, child_name = _validate_identity(survey, data, errors)

        questions = list(survey.questions.prefetch_related("options").order_by("order", "id"))
        by_id = {q.id: q for q in questions}

        if not isinstance(data.answers, dict):
            raise SubmissionError({"answers": "Некорректный формат ответов."})
        raw_answers: dict[int, Any] = {}
        for key, value in data.answers.items():
            qid = _to_int(key)
            if qid is None or qid not in by_id:
                errors["answers"] = "Ответ содержит неизвестный вопрос."
                continue
            raw_answers[qid] = value

        cleaned: dict[int, Any] = {}
        for q in questions:
            error, value = _validate_answer(q, raw_answers.get(q.id), {o.id for o in q.options.all()})
            if error:
                errors[f"q_{q.id}"] = error
            elif value is not None:
                cleaned[q.id] = value

        if errors:
            raise SubmissionError(errors)

        response = SurveyResponse.objects.create(
            survey=survey,
            visibility=visibility,
            respondent_name=respondent_name,
            child_name=child_name,
            submitted_at=timezone.now(),
        )
        links = []
        for qid, value in cleaned.items():
            q = by_id[qid]
            if q.question_type == QT.TEXT:
                SurveyAnswer.objects.create(response=response, question=q, text_value=value)
            else:
                answer = SurveyAnswer.objects.create(response=response, question=q)
                links.extend(SurveyAnswerOption(answer=answer, option_id=oid) for oid in value)
        SurveyAnswerOption.objects.bulk_create(links)
        return response
