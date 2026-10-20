"""Manual review of text answers — done in the Django admin only
(«Проверка текстовых ответов», TextAnswerReviewAdmin).

The reviewer gives 0…question.points; the answer becomes «Вручную»
(GradingStatus.MANUAL), and the attempt's score and its participant row are
recalculated. Other answers of the attempt are not touched. Saving the
attempt fires its post_save, so the leaderboard cache is refreshed; KPI and
analytics read StudentAttempt.score directly.
"""
from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from ..models import Answer, AttemptStatus, GradingStatus, SessionParticipant, StudentAttempt


def review_answer(answer: Answer, points: float, comment: str = "", user=None) -> Answer:
    """Store a reviewer's points (0…max) and comment, then recalculate the attempt."""
    max_points = answer.question.points
    if points is None or points < 0 or points > max_points:
        raise ValidationError(f"Балл должен быть от 0 до {max_points}.")
    with transaction.atomic():
        locked = Answer.objects.select_for_update().get(pk=answer.pk)
        locked.points_awarded = float(points)
        # «Верно» for counts and result pages: at least half of the points.
        locked.is_correct = points * 2 >= max_points
        locked.grading_status = GradingStatus.MANUAL
        locked.review_comment = comment or ""
        locked.reviewed_by = user if getattr(user, "pk", None) else None
        locked.reviewed_at = timezone.now()
        locked.save(update_fields=[
            "points_awarded", "is_correct", "grading_status", "review_comment", "reviewed_by", "reviewed_at",
        ])
        recalculate_attempt(locked.attempt_id)
    return locked


def reset_review(answer: Answer) -> Answer:
    """Back to «На проверке»: the answer earns nothing until reviewed again."""
    with transaction.atomic():
        locked = Answer.objects.select_for_update().get(pk=answer.pk)
        locked.points_awarded = None
        locked.is_correct = None
        locked.grading_status = GradingStatus.PENDING
        locked.reviewed_by = None
        locked.reviewed_at = None
        locked.save(update_fields=["points_awarded", "is_correct", "grading_status", "reviewed_by", "reviewed_at"])
        recalculate_attempt(locked.attempt_id)
    return locked


def recalculate_attempt(attempt_id) -> StudentAttempt:
    """Re-score a finished attempt from its stored answers and copy the
    score to its participant row (what the session monitor shows)."""
    attempt = StudentAttempt.objects.select_for_update().get(pk=attempt_id)
    if attempt.status != AttemptStatus.FINISHED:
        return attempt
    attempt._recalculate_score()
    attempt.save(update_fields=["score"])
    SessionParticipant.objects.filter(attempt=attempt).update(score=attempt.score)
    return attempt
