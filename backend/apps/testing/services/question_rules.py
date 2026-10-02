"""What makes a question valid for its type — one place, used by the admin
question editor and by the REST API, so both accept exactly the same data.

A question is described by plain data (no model instances), so the rules
can run before anything is saved:

    QuestionData(question_type="single_choice", text="…",
                 options=[OptionData("Python", True), OptionData("Java", False)])
"""
from __future__ import annotations

from dataclasses import dataclass, field

from django.core.exceptions import ValidationError

from ..models import IMAGE_URL_MAX_LENGTH, QuestionType, validate_image_url

CHOICE_TYPES = (QuestionType.SINGLE_CHOICE, QuestionType.MULTIPLE_CHOICE)


@dataclass
class OptionData:
    text: str
    is_correct: bool = False
    id: str | None = None  # existing QuestionOption, kept so old answers still point at it
    image_url: str = ""  # an option may be a picture only (then text may be blank)

    @property
    def is_blank(self) -> bool:
        return not (self.text or "").strip() and not (self.image_url or "").strip()


@dataclass
class CodeTestData:
    input: str = ""
    expected_output: str = ""


@dataclass
class QuestionData:
    question_type: str
    text: str
    image_url: str = ""
    language: str = ""
    correct_answers: list[str] = field(default_factory=list)
    options: list[OptionData] = field(default_factory=list)
    code_tests: list[CodeTestData] = field(default_factory=list)


def normalize(data: QuestionData) -> QuestionData:
    """Trim text, drop blank options / accepted answers / empty test rows."""
    return QuestionData(
        question_type=data.question_type,
        text=(data.text or "").strip(),
        image_url=(data.image_url or "").strip(),
        language=(data.language or "").strip(),
        correct_answers=_unique([a.strip() for a in data.correct_answers if a and a.strip()]),
        options=[
            OptionData((o.text or "").strip(), bool(o.is_correct), o.id or None, (o.image_url or "").strip())
            for o in data.options
            if not o.is_blank
        ],
        code_tests=[
            CodeTestData((t.input or "").rstrip(), (t.expected_output or "").rstrip())
            for t in data.code_tests
            if (t.input or "").strip() or (t.expected_output or "").strip()
        ],
    )


def validate(data: QuestionData) -> QuestionData:
    """Return the normalized data or raise ValidationError({field: [...]})."""
    data = normalize(data)
    errors: dict[str, list[str]] = {}

    def add(key: str, message: str) -> None:
        errors.setdefault(key, []).append(message)

    if data.question_type not in QuestionType.values:
        add("question_type", "Неизвестный тип вопроса.")
    if not data.text:
        add("text", "Введите текст вопроса.")
    if (message := image_url_error(data.image_url)):
        add("image_url", message)

    if data.question_type in CHOICE_TYPES:
        if len(data.options) < 2:
            add("options", "Добавьте минимум два варианта ответа.")
        correct = sum(1 for o in data.options if o.is_correct)
        if data.options and not correct:
            add("options", "Отметьте правильный вариант.")
        if data.question_type == QuestionType.SINGLE_CHOICE and correct > 1:
            add("options", "Для типа «Один вариант» правильным может быть только один вариант.")
        texts = [o.text.casefold() for o in data.options if o.text]
        if len(texts) != len(set(texts)):
            add("options", "Варианты ответа не должны повторяться.")
        for number, option in enumerate(data.options, start=1):
            if (message := image_url_error(option.image_url)):
                add("options", f"Вариант {number}: {message}")
    elif data.options:
        add("options", "У этого типа вопроса нет вариантов ответа.")

    if data.question_type == QuestionType.TEXT and not data.correct_answers:
        add("correct_answers", "Укажите правильный ответ.")

    if data.question_type == QuestionType.CODE:
        if not data.language:
            add("language", "Для вопроса с кодом обязателен язык.")
        for number, test in enumerate(data.code_tests, start=1):
            if not test.expected_output.strip():
                add("code_tests", f"Тест {number}: укажите ожидаемый вывод.")

    if errors:
        raise ValidationError(errors)
    return data


def image_url_error(value: str) -> str | None:
    """None if ``value`` is empty or a valid http(s) URL, else the message."""
    if not value:
        return None
    if len(value) > IMAGE_URL_MAX_LENGTH:
        return f"Ссылка на изображение длиннее {IMAGE_URL_MAX_LENGTH} символов."
    try:
        validate_image_url(value)
    except ValidationError as error:
        return error.messages[0]
    return None


def _unique(items: list[str]) -> list[str]:
    seen, result = set(), []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result
