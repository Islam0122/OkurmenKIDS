"""Survey builder rules — the one place questions/options are written.

Both the admin JSON API (apps.feedback.views) and the Django admin pages go
through these functions, so every structural rule is enforced once:

* Editing is allowed while a survey is published, but a question that
  already has answers is *locked*: its type can't change, it can't be
  deleted, and none of its existing options can be removed. Wording can
  still be fixed and new options/questions added — historical responses are
  never silently re-pointed or corrupted. For a real redesign, duplicate the
  survey (``duplicate_survey``) and publish the copy.
* A survey can only be published once it is complete (``publish_problems``).
"""
from __future__ import annotations

from dataclasses import dataclass

from django.contrib.admin.models import CHANGE, LogEntry
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import F, Max
from django.utils import timezone

from apps.feedback.models import (
    MAX_OPTIONS_PER_QUESTION,
    MAX_QUESTIONS_PER_SURVEY,
    OPTION_TEXT_MAX_LENGTH,
    QUESTION_TEXT_MAX_LENGTH,
    TEXT_ANSWER_MAX_LENGTH,
    QuestionOption,
    Survey,
    SurveyQuestion,
    generate_public_token,
)

QT = SurveyQuestion.QuestionType


def log_admin_action(user, obj, message: str) -> None:
    """Audit trail for sensitive admin actions, in Django's own admin log
    (visible in the object's "История"). Never includes respondent text."""
    if user is None or not getattr(user, "is_authenticated", False):
        return
    LogEntry.objects.log_actions(user.pk, [obj], CHANGE, change_message=message, single_object=True)


# -- Questions ----------------------------------------------------------------


@dataclass
class QuestionData:
    text: str
    question_type: str
    is_required: bool = True
    help_text: str = ""
    is_multiline: bool = True
    min_length: int | None = None
    max_length: int | None = None
    min_selections: int | None = None
    max_selections: int | None = None
    # [{"id": int | None, "text": str}] in display order
    options: list[dict] | None = None

    @classmethod
    def from_dict(cls, data: dict) -> "QuestionData":
        return cls(
            text=(data.get("text") or "").strip(),
            question_type=data.get("question_type") or QT.SINGLE_CHOICE,
            is_required=bool(data.get("is_required", True)),
            help_text=(data.get("help_text") or "").strip(),
            is_multiline=bool(data.get("is_multiline", True)),
            min_length=data.get("min_length"),
            max_length=data.get("max_length"),
            min_selections=data.get("min_selections"),
            max_selections=data.get("max_selections"),
            options=list(data.get("options") or []),
        )


def _validate_question_data(data: QuestionData, question: SurveyQuestion | None) -> None:
    errors: dict[str, str] = {}
    if not data.text:
        errors["text"] = "Введите текст вопроса."
    elif len(data.text) > QUESTION_TEXT_MAX_LENGTH:
        errors["text"] = f"Не длиннее {QUESTION_TEXT_MAX_LENGTH} символов."
    if len(data.help_text) > 300:
        errors["help_text"] = "Не длиннее 300 символов."
    if data.question_type not in QT.values:
        errors["question_type"] = "Неизвестный тип вопроса."

    if question is not None and question.answers.exists() and data.question_type != question.question_type:
        errors["question_type"] = "На вопрос уже есть ответы — тип вопроса изменить нельзя."

    if data.question_type == QT.TEXT:
        lo, hi = data.min_length, data.max_length
        if hi is not None and not 1 <= hi <= TEXT_ANSWER_MAX_LENGTH:
            errors["max_length"] = f"От 1 до {TEXT_ANSWER_MAX_LENGTH}."
        if lo is not None and not 0 <= lo <= TEXT_ANSWER_MAX_LENGTH:
            errors["min_length"] = f"От 0 до {TEXT_ANSWER_MAX_LENGTH}."
        if lo is not None and hi is not None and lo > hi:
            errors["min_length"] = "Минимальная длина больше максимальной."
    elif data.question_type in (QT.SINGLE_CHOICE, QT.MULTIPLE_CHOICE):
        texts = [(o.get("text") or "").strip() for o in data.options or []]
        if any(not t for t in texts):
            errors["options"] = "У каждого варианта должен быть текст."
        elif any(len(t) > OPTION_TEXT_MAX_LENGTH for t in texts):
            errors["options"] = f"Вариант не длиннее {OPTION_TEXT_MAX_LENGTH} символов."
        elif len({t.casefold() for t in texts}) != len(texts):
            errors["options"] = "Варианты ответа не должны повторяться."
        elif len(texts) > MAX_OPTIONS_PER_QUESTION:
            errors["options"] = f"Не больше {MAX_OPTIONS_PER_QUESTION} вариантов."
        if data.question_type == QT.MULTIPLE_CHOICE:
            lo, hi = data.min_selections, data.max_selections
            if lo is not None and lo < 0:
                errors["min_selections"] = "Не может быть отрицательным."
            if hi is not None and hi < 1:
                errors["max_selections"] = "Минимум 1."
            if lo is not None and hi is not None and lo > hi:
                errors["min_selections"] = "Минимум больше максимума."
            if "options" not in errors and texts:
                if lo is not None and lo > len(texts):
                    errors["min_selections"] = "Минимум больше числа вариантов."
                if hi is not None and hi > len(texts):
                    errors["max_selections"] = "Максимум больше числа вариантов."
    if errors:
        raise ValidationError(errors)


def _sync_options(question: SurveyQuestion, options: list[dict]) -> None:
    existing = {o.id: o for o in question.options.all()}
    keep_ids: set[int] = set()
    for item in options:
        raw_id = item.get("id")
        if raw_id in (None, ""):
            continue
        try:
            option_id = int(raw_id)
        except (TypeError, ValueError):
            raise ValidationError({"options": "Некорректный вариант ответа."})
        if option_id not in existing:
            raise ValidationError({"options": "Вариант ответа не принадлежит этому вопросу."})
        keep_ids.add(option_id)

    removed = [o for oid, o in existing.items() if oid not in keep_ids]
    if any(o.answer_links.exists() for o in removed):
        raise ValidationError(
            {"options": "Нельзя удалить вариант, который уже выбирали респонденты. Можно изменить его текст."}
        )
    for o in removed:
        o.delete()

    for position, item in enumerate(options):
        text = item["text"].strip()
        raw_id = item.get("id")
        if raw_id in (None, ""):
            QuestionOption.objects.create(question=question, text=text, order=position)
        else:
            option = existing[int(raw_id)]
            if option.text != text or option.order != position:
                option.text, option.order = text, position
                option.save(update_fields=["text", "order"])


def _apply_question_fields(question: SurveyQuestion, data: QuestionData) -> None:
    question.text = data.text
    question.help_text = data.help_text
    question.question_type = data.question_type
    question.is_required = data.is_required
    is_text = data.question_type == QT.TEXT
    is_multi = data.question_type == QT.MULTIPLE_CHOICE
    # Settings of the other types are cleared so they can never leak into
    # validation after a type change.
    question.is_multiline = data.is_multiline if is_text else True
    question.min_length = data.min_length if is_text else None
    question.max_length = data.max_length if is_text else None
    question.min_selections = data.min_selections if is_multi else None
    question.max_selections = data.max_selections if is_multi else None


@transaction.atomic
def create_question(survey: Survey, raw: dict, *, position: int | None = None) -> SurveyQuestion:
    data = QuestionData.from_dict(raw)
    _validate_question_data(data, None)
    if survey.questions.count() >= MAX_QUESTIONS_PER_SURVEY:
        raise ValidationError({"text": f"В опросе не может быть больше {MAX_QUESTIONS_PER_SURVEY} вопросов."})

    if position is None:
        order = (survey.questions.aggregate(m=Max("order"))["m"] or 0) + 1
    else:
        survey.questions.filter(order__gte=position).update(order=F("order") + 1)
        order = position
    question = SurveyQuestion(survey=survey, order=order)
    _apply_question_fields(question, data)
    question.save()
    if data.question_type != QT.TEXT:
        _sync_options(question, data.options or [])
    return question


@transaction.atomic
def update_question(question: SurveyQuestion, raw: dict) -> SurveyQuestion:
    question = SurveyQuestion.objects.select_for_update().get(pk=question.pk)
    data = QuestionData.from_dict(raw)
    _validate_question_data(data, question)
    _apply_question_fields(question, data)
    question.save()
    _sync_options(question, [] if data.question_type == QT.TEXT else (data.options or []))
    return question


@transaction.atomic
def delete_question(question: SurveyQuestion) -> None:
    if question.answers.exists():
        raise ValidationError(
            "На этот вопрос уже есть ответы — удалить его нельзя. Сделайте копию опроса, если нужна другая структура."
        )
    survey = question.survey
    question.delete()
    normalize_order(survey)


@transaction.atomic
def duplicate_question(question: SurveyQuestion) -> SurveyQuestion:
    raw = {
        "text": question.text,
        "help_text": question.help_text,
        "question_type": question.question_type,
        "is_required": question.is_required,
        "is_multiline": question.is_multiline,
        "min_length": question.min_length,
        "max_length": question.max_length,
        "min_selections": question.min_selections,
        "max_selections": question.max_selections,
        "options": [{"text": o.text} for o in question.options.all()],
    }
    normalize_order(question.survey)
    question.refresh_from_db()
    return create_question(question.survey, raw, position=question.order + 1)


@transaction.atomic
def reorder_questions(survey: Survey, ordered_ids: list) -> None:
    try:
        ids = [int(i) for i in ordered_ids]
    except (TypeError, ValueError):
        raise ValidationError("Некорректный порядок вопросов.")
    current = set(survey.questions.values_list("id", flat=True))
    if len(ids) != len(set(ids)) or set(ids) != current:
        raise ValidationError("Порядок должен содержать каждый вопрос опроса ровно один раз.")
    for position, qid in enumerate(ids, start=1):
        SurveyQuestion.objects.filter(pk=qid, survey=survey).update(order=position)


def normalize_order(survey: Survey) -> None:
    for position, q in enumerate(survey.questions.order_by("order", "id"), start=1):
        if q.order != position:
            SurveyQuestion.objects.filter(pk=q.pk).update(order=position)


# -- Survey lifecycle -------------------------------------------------------


def publish_problems(survey: Survey) -> list[str]:
    """Everything that stops `survey` from being published, human-readable."""
    problems = []
    questions = list(survey.questions.prefetch_related("options"))
    if not questions:
        problems.append("Добавьте хотя бы один вопрос.")
    for index, q in enumerate(questions, start=1):
        if q.is_choice:
            count = len(q.options.all())
            if count < 2:
                problems.append(f"Вопрос {index}: нужно минимум два варианта ответа.")
            if q.question_type == QT.MULTIPLE_CHOICE and (q.min_selections or 0) > count:
                problems.append(f"Вопрос {index}: минимум выбранных больше числа вариантов.")
    if survey.ends_at and survey.ends_at <= timezone.now():
        problems.append("Дата окончания уже прошла — измените её в настройках.")
    return problems


@transaction.atomic
def publish_survey(survey: Survey, user=None) -> Survey:
    problems = publish_problems(survey)
    if problems:
        raise ValidationError(problems)
    was = survey.get_status_display()
    survey.status = Survey.Status.PUBLISHED
    survey.published_at = survey.published_at or timezone.now()
    survey.closed_at = None
    survey.save(update_fields=["status", "published_at", "closed_at", "updated_at"])
    log_admin_action(user, survey, f"Опрос опубликован (был: {was}).")
    return survey


@transaction.atomic
def close_survey(survey: Survey, user=None) -> Survey:
    if survey.status != Survey.Status.PUBLISHED:
        raise ValidationError("Закрыть можно только опубликованный опрос.")
    survey.status = Survey.Status.CLOSED
    survey.closed_at = timezone.now()
    survey.save(update_fields=["status", "closed_at", "updated_at"])
    log_admin_action(user, survey, "Опрос закрыт — ссылка больше не принимает ответы.")
    return survey


def reopen_survey(survey: Survey, user=None) -> Survey:
    if survey.status != Survey.Status.CLOSED:
        raise ValidationError("Открыть заново можно только закрытый опрос.")
    return publish_survey(survey, user)


@transaction.atomic
def regenerate_link(survey: Survey, user=None) -> Survey:
    survey.public_token = generate_public_token()
    survey.save(update_fields=["public_token", "updated_at"])
    log_admin_action(user, survey, "Сгенерирована новая ссылка — старая ссылка больше не работает.")
    return survey


@transaction.atomic
def duplicate_survey(survey: Survey, user=None) -> Survey:
    copy = Survey.objects.create(
        title=f"{survey.title} (копия)"[:200],
        description=survey.description,
        audience=survey.audience,
        visibility_mode=survey.visibility_mode,
        max_responses=survey.max_responses,
        allow_multiple_submissions=survey.allow_multiple_submissions,
        child_name_mode=survey.child_name_mode,
        ask_child_name_when_anonymous=survey.ask_child_name_when_anonymous,
        group=survey.group,
        teacher=survey.teacher,
        subject=survey.subject,
        confirmation_message=survey.confirmation_message,
        created_by=user if getattr(user, "is_authenticated", False) else None,
    )
    for q in survey.questions.prefetch_related("options"):
        new_q = SurveyQuestion.objects.create(
            survey=copy,
            text=q.text,
            help_text=q.help_text,
            question_type=q.question_type,
            is_required=q.is_required,
            order=q.order,
            is_multiline=q.is_multiline,
            min_length=q.min_length,
            max_length=q.max_length,
            min_selections=q.min_selections,
            max_selections=q.max_selections,
        )
        QuestionOption.objects.bulk_create(
            [QuestionOption(question=new_q, text=o.text, order=o.order) for o in q.options.all()]
        )
    log_admin_action(user, copy, f"Создан как копия опроса #{survey.pk}.")
    return copy
