"""Writing questions of a test: create/update with their options, copy,
move and reorder. Used by the admin test workspace and the REST API."""
from __future__ import annotations

import uuid

from django.db import transaction
from django.db.models import F, Max

from ..models import Question, QuestionOption, QuestionType
from .question_rules import CHOICE_TYPES, QuestionData, validate

# Fields copied as-is from the editor/API onto the Question row.
EXTRA_FIELDS = ("hint", "points", "is_required", "answer_match", "starter_code", "difficulty")


def next_order(test) -> int:
    return (test.questions.aggregate(last=Max("order"))["last"] or 0) + 1


@transaction.atomic
def save_question(test, data: QuestionData, *, question: Question | None = None, **extra) -> Question:
    """Validate ``data`` for its type and write the question + its options.

    Options are synced by id: rows that keep their id are updated in place
    (past answers store option ids), new rows are created, missing rows are
    deleted. Type-specific fields that don't apply to the new type are
    cleared, so switching a question's type never leaves stale data behind.
    """
    data = validate(data)
    question = question or Question(test=test, order=next_order(test))
    question.question_type = data.question_type
    question.text = data.text
    question.language = data.language
    question.correct_answers = data.correct_answers if data.question_type == QuestionType.TEXT else []
    question.code_tests = (
        [{"input": t.input, "expected_output": t.expected_output} for t in data.code_tests]
        if data.question_type == QuestionType.CODE else []
    )
    for name in EXTRA_FIELDS:
        if name in extra and extra[name] is not None:
            setattr(question, name, extra[name])
    if data.question_type != QuestionType.CODE:
        question.starter_code = ""
    question.full_clean()
    question.save()

    existing = {str(o.pk): o for o in question.options.all()}
    keep = set()
    if data.question_type in CHOICE_TYPES:
        for position, option in enumerate(data.options, start=1):
            row = existing.get(str(option.id)) if option.id else None
            if row is None:
                row = QuestionOption(question=question)
            row.text, row.is_correct, row.order = option.text, option.is_correct, position
            row.save()
            keep.add(str(row.pk))
    question.options.exclude(pk__in=keep).delete()
    return question


@transaction.atomic
def duplicate_question(question: Question) -> Question:
    """Copy right after the original; the text gets a «(копия)» suffix to
    keep (test, text) unique."""
    test = question.test
    text = f"{question.text} (копия)"
    number = 2
    while test.questions.filter(text=text).exists():
        text = f"{question.text} (копия {number})"
        number += 1
    options = list(question.options.all())
    renumber(test)
    question.refresh_from_db(fields=["order"])
    test.questions.filter(order__gt=question.order).update(order=F("order") + 1)
    copy = Question.objects.get(pk=question.pk)
    copy.id = uuid.uuid4()
    copy._state.adding = True
    copy.text = text
    copy.order = question.order + 1
    copy.save()
    QuestionOption.objects.bulk_create(
        QuestionOption(question=copy, text=o.text, is_correct=o.is_correct, order=o.order) for o in options
    )
    return copy


def renumber(test) -> None:
    """Make Question.order = 1..n in the current display order."""
    questions = list(test.questions.order_by("order", "created_at"))
    changed = []
    for position, question in enumerate(questions, start=1):
        if question.order != position:
            question.order = position
            changed.append(question)
    Question.objects.bulk_update(changed, ["order"])


@transaction.atomic
def move_question(question: Question, direction: str) -> None:
    """Swap with the neighbour above (``up``) or below (``down``)."""
    test = question.test
    renumber(test)
    ordered = list(test.questions.select_for_update().order_by("order", "created_at"))
    index = next(i for i, q in enumerate(ordered) if q.pk == question.pk)
    target = index - 1 if direction == "up" else index + 1
    if not 0 <= target < len(ordered):
        return
    ordered[index], ordered[target] = ordered[target], ordered[index]
    _apply_order(ordered)


@transaction.atomic
def reorder_questions(test, ids: list[str]) -> bool:
    """Persist a full new order. False if ``ids`` is not exactly the test's
    current question set (a stale page must not drop or misplace any)."""
    questions = {str(q.pk): q for q in test.questions.select_for_update()}
    if len(ids) != len(set(ids)) or set(ids) != set(questions):
        return False
    _apply_order([questions[i] for i in ids])
    return True


def _apply_order(ordered: list[Question]) -> None:
    for position, question in enumerate(ordered, start=1):
        question.order = position
    Question.objects.bulk_update(ordered, ["order"])

