"""Answer checking and attempt scoring.

Choice questions are checked exactly as in the legacy app (the selected set
must equal the set of correct options). check_answer() checks text questions
against the accepted answers (exact or case-insensitive, whitespace-
normalised) — that is the training portal's instant feedback and the
reviewer's hint. A stored LMS test result (grade_answer) sends every non-empty
text answer to manual review in the admin (services.review). Legacy text
questions without accepted answers, and every code question, stay «На
проверке» for a teacher — the project has no code execution engine.

Score of an attempt with its own question list = earned points / possible
points · 100, where a pending answer earns nothing until it is graded and a
reviewed answer earns the points the reviewer gave (Answer.points_awarded).
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from ..models import AnswerMatch, GradingStatus, QuestionType, REVIEW_GRADING_STATUSES, SessionType

_SPACES = re.compile(r"\s+")


def _normalize_text(value: str, match: str) -> str:
    value = _SPACES.sub(" ", (value or "").strip())
    return value.casefold() if match == AnswerMatch.IGNORE_CASE else value


def check_answer(question, answer_text: str = "", selected_options=()) -> tuple[bool | None, str]:
    """(is_correct, grading_status) for one answer. ``question.options``
    may be prefetched; option ids are compared as strings."""
    selected = {str(option_id) for option_id in selected_options or ()}

    if question.question_type in (QuestionType.SINGLE_CHOICE, QuestionType.MULTIPLE_CHOICE):
        correct = {str(option.id) for option in question.options.all() if option.is_correct}
        if question.question_type == QuestionType.SINGLE_CHOICE and len(selected) != 1:
            return False, GradingStatus.AUTO
        return selected == correct, GradingStatus.AUTO

    if question.question_type == QuestionType.TEXT and question.correct_answers:
        if not (answer_text or "").strip():
            return False, GradingStatus.AUTO
        given = _normalize_text(answer_text, question.answer_match)
        accepted = {_normalize_text(a, question.answer_match) for a in question.correct_answers}
        return given in accepted, GradingStatus.AUTO

    if not (answer_text or "").strip():
        # Nothing to review: an empty text/code answer is simply wrong.
        return False, GradingStatus.AUTO
    return None, GradingStatus.PENDING


def reviews_text_manually(session) -> bool:
    """Text answers of LMS sessions are graded by hand in the admin. The
    public training portal (anonymous practice with instant feedback) keeps
    checking them against the accepted answers."""
    return not (session.is_public and session.session_type == SessionType.TRAINING)


def grade_answer(question, answer_text: str = "", selected_options=(), manual_text: bool = True) -> tuple[bool | None, str]:
    """(is_correct, grading_status) stored for a submitted answer: as
    check_answer(), except that with ``manual_text`` a non-empty text answer
    waits for manual review."""
    if manual_text and question.question_type == QuestionType.TEXT and (answer_text or "").strip():
        return None, GradingStatus.PENDING
    return check_answer(question, answer_text, selected_options)


def answer_points(answer, max_points: int) -> float:
    """Points one graded answer earns: the reviewer's score (capped at the
    question's points), else all or nothing by is_correct."""
    if answer.points_awarded is not None:
        return min(max(answer.points_awarded, 0.0), float(max_points))
    return max_points if answer.is_correct else 0


@dataclass
class AttemptScore:
    earned: float
    possible: int
    correct: int
    answered: int
    pending: int
    total_questions: int

    @property
    def percent(self) -> float:
        return round(self.earned / self.possible * 100, 2) if self.possible else 0.0


def attempt_score(attempt) -> AttemptScore:
    """Score over the attempt's own question list (``attempt.question_ids``)."""
    from ..models import Question

    ids = [str(i) for i in attempt.question_ids]
    points = dict(Question.objects.filter(pk__in=ids).values_list("id", "points"))
    points = {str(k): v for k, v in points.items()}
    answers = {str(a.question_id): a for a in attempt.answers.all()}

    earned = correct = pending = answered = 0
    for question_id in ids:
        answer = answers.get(question_id)
        if answer is None:
            continue
        answered += 1
        if answer.grading_status in REVIEW_GRADING_STATUSES:
            pending += 1
        else:
            correct += bool(answer.is_correct)
            earned += answer_points(answer, points.get(question_id, 0))
    earned = round(earned, 2)
    return AttemptScore(
        earned=int(earned) if earned == int(earned) else earned,
        possible=sum(points.get(i, 0) for i in ids),
        correct=correct,
        answered=answered,
        pending=pending,
        total_questions=len(ids),
    )
