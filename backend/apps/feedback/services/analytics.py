"""Feedback analytics — plain counts with explicit denominators.

Deliberately *not* computed here:

* A response rate: a public link can be forwarded anywhere, so there is no
  honest "number of people asked" to divide by.
* Any overall/teacher score: questions are free-form, so averaging unrelated
  questions into one number would be meaningless.

Percentages for a choice question are always "of the respondents who
answered this question" (optional questions can be skipped). For multiple
choice the per-option percentages can therefore add up to more than 100%.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from django.db.models import Count, Q, QuerySet

from apps.feedback.models import Survey, SurveyAnswer, SurveyAnswerOption, SurveyQuestion, SurveyResponse

QT = SurveyQuestion.QuestionType


@dataclass
class FeedbackFilters:
    survey_id: int | None = None
    audience: str | None = None
    group_id: int | None = None
    teacher_id: int | None = None
    subject_id: int | None = None
    date_from: dt.date | None = None
    date_to: dt.date | None = None
    visibility: str | None = None

    @classmethod
    def from_query(cls, params) -> "FeedbackFilters":
        def as_int(key):
            value = params.get(key)
            return int(value) if value and str(value).isdigit() else None

        def as_date(key):
            try:
                return dt.date.fromisoformat(params.get(key) or "")
            except ValueError:
                return None

        audience = params.get("audience")
        visibility = params.get("visibility")
        return cls(
            survey_id=as_int("survey"),
            audience=audience if audience in Survey.Audience.values else None,
            group_id=as_int("group"),
            teacher_id=as_int("teacher"),
            subject_id=as_int("subject"),
            date_from=as_date("date_from"),
            date_to=as_date("date_to"),
            visibility=visibility if visibility in SurveyResponse.Visibility.values else None,
        )

    def surveys(self) -> QuerySet[Survey]:
        qs = Survey.objects.all()
        if self.survey_id:
            qs = qs.filter(pk=self.survey_id)
        if self.audience:
            qs = qs.filter(audience=self.audience)
        if self.group_id:
            qs = qs.filter(group_id=self.group_id)
        if self.teacher_id:
            qs = qs.filter(teacher_id=self.teacher_id)
        if self.subject_id:
            qs = qs.filter(subject_id=self.subject_id)
        return qs

    def responses(self, surveys: QuerySet[Survey] | None = None) -> QuerySet[SurveyResponse]:
        qs = SurveyResponse.objects.filter(survey__in=surveys if surveys is not None else self.surveys())
        if self.date_from:
            qs = qs.filter(submitted_at__date__gte=self.date_from)
        if self.date_to:
            qs = qs.filter(submitted_at__date__lte=self.date_to)
        if self.visibility:
            qs = qs.filter(visibility=self.visibility)
        return qs


def _pct(part: int, whole: int) -> float | None:
    return round(part * 100 / whole, 1) if whole else None


def overview(filters: FeedbackFilters) -> dict:
    surveys = filters.surveys()
    responses = filters.responses(surveys)
    counts = responses.aggregate(
        total=Count("id"),
        open=Count("id", filter=Q(visibility=SurveyResponse.Visibility.OPEN)),
        anonymous=Count("id", filter=Q(visibility=SurveyResponse.Visibility.ANONYMOUS)),
    )
    accepting = sum(1 for s in surveys.filter(status=Survey.Status.PUBLISHED) if s.availability() == "available")
    per_survey = list(
        surveys.annotate(
            response_count=Count("responses", filter=Q(responses__in=responses)),
        ).order_by("-created_at")
    )
    return {
        "total_surveys": surveys.count(),
        "published_surveys": surveys.filter(status=Survey.Status.PUBLISHED).count(),
        "accepting_surveys": accepting,
        "total_responses": counts["total"],
        "open_responses": counts["open"],
        "anonymous_responses": counts["anonymous"],
        "open_pct": _pct(counts["open"], counts["total"]),
        "anonymous_pct": _pct(counts["anonymous"], counts["total"]),
        "surveys": per_survey,
    }


def question_stats(survey: Survey, responses: QuerySet[SurveyResponse], *, text_search: str = "",
                   text_limit: int = 50) -> list[dict]:
    """One entry per question, in survey order."""
    questions = list(survey.questions.prefetch_related("options").order_by("order", "id"))
    # An answer row is only ever created for a question that was actually
    # answered (see services.submission), so a plain count is "answered".
    answered = dict(
        SurveyAnswer.objects.filter(response__in=responses, question__survey=survey)
        .values_list("question_id")
        .annotate(c=Count("id"))
    )
    option_counts = dict(
        SurveyAnswerOption.objects.filter(answer__response__in=responses, option__question__survey=survey)
        .values_list("option_id")
        .annotate(c=Count("id"))
    )

    result = []
    for index, q in enumerate(questions, start=1):
        n = answered.get(q.id, 0)
        entry = {
            "index": index,
            "question": q,
            "id": q.id,
            "text": q.text,
            "question_type": q.question_type,
            "answered": n,
        }
        if q.is_choice:
            options = [
                {"id": o.id, "text": o.text, "count": option_counts.get(o.id, 0), "pct": _pct(option_counts.get(o.id, 0), n)}
                for o in q.options.all()
            ]
            entry["options"] = options
            entry["denominator_note"] = (
                "% от ответивших на вопрос; можно выбрать несколько вариантов, поэтому сумма может быть больше 100%"
                if q.question_type == QT.MULTIPLE_CHOICE
                else "% от ответивших на вопрос"
            )
        else:
            texts = SurveyAnswer.objects.filter(response__in=responses, question=q).exclude(text_value="")
            if text_search:
                texts = texts.filter(text_value__icontains=text_search)
            entry["text_total"] = texts.count()
            entry["texts"] = [
                {"text": a.text_value, "submitted_at": a.response.submitted_at}
                for a in texts.select_related("response").order_by("-response__submitted_at")[:text_limit]
            ]
        result.append(entry)
    return result
