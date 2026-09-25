"""CSV export of a survey's responses (UTF-8 with BOM so Excel opens it)."""
from __future__ import annotations

import csv
import io

from django.db.models import QuerySet
from django.utils import timezone

from apps.feedback.models import Survey, SurveyResponse

# Spreadsheet apps execute cells starting with these as formulas — free text
# from a public form must never be able to do that (CSV injection).
_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def _safe(value: str) -> str:
    value = value or ""
    return "'" + value if value.startswith(_FORMULA_PREFIXES) else value


def export_responses_csv(survey: Survey, responses: QuerySet[SurveyResponse]) -> str:
    questions = list(survey.questions.order_by("order", "id"))
    buffer = io.StringIO()
    buffer.write("﻿")
    writer = csv.writer(buffer)
    header = ["Дата", "Тип отзыва", "Имя респондента"]
    if survey.is_parent_survey:
        header.append("Имя ребёнка (со слов родителя)")
    writer.writerow(header + [_safe(q.text) for q in questions])

    responses = responses.prefetch_related("answers__option_links__option").order_by("submitted_at")
    for response in responses:
        by_question = {a.question_id: a for a in response.answers.all()}
        row = [
            timezone.localtime(response.submitted_at).strftime("%d.%m.%Y %H:%M"),
            response.get_visibility_display(),
            _safe(response.display_name),
        ]
        if survey.is_parent_survey:
            row.append(_safe(response.child_name))
        for q in questions:
            answer = by_question.get(q.id)
            if answer is None:
                row.append("")
            elif q.is_choice:
                row.append(_safe("; ".join(link.option.text for link in answer.option_links.all())))
            else:
                row.append(_safe(answer.text_value))
        writer.writerow(row)
    return buffer.getvalue()
