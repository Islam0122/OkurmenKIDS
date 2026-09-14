"""The Lesson lifecycle: scheduled → in_progress → completed, with cancelled
as a terminal state reachable from either of the first two (see
models.Lesson.Status).

A Lesson is never inferred as completed just because its date/time has
passed — the transitions here are the *only* way `Lesson.status` ever
changes after generation (services.lesson_generator only ever creates a
Lesson as SCHEDULED). Ownership/IDOR protection is deliberately not
duplicated here: the ViewSet actions that call these functions always reach
a Lesson through `get_object()`, which already applies the existing
`for_teacher`-scoped queryset and `IsAdminOrOwningTeacher` object permission
(see apps.academy.views/permissions) — exactly the same guard every other
Lesson/Attendance/Homework write in this app relies on.
"""
from __future__ import annotations

from dataclasses import dataclass

from django.core.exceptions import ValidationError
from django.utils import timezone

from ..models import Attendance, Homework, Lesson


@dataclass(frozen=True)
class CompletionRequirement:
    key: str
    label: str
    satisfied: bool


def attendance_completed(lesson: Lesson) -> bool:
    """Every active student of the lesson's group has an Attendance record.
    The one public definition of "attendance status" — reused by the
    completion checklist and exposed directly on LessonSerializer so the
    frontend never re-derives it from a separate roster fetch."""
    active_count = lesson.group.students.filter(is_active=True).count()
    if active_count == 0:
        return True
    marked_count = Attendance.objects.filter(lesson=lesson, student__is_active=True).count()
    return marked_count >= active_count


def homework_added(lesson: Lesson) -> bool:
    """Whether a real Homework row exists for this lesson — the one public
    definition of "homework status", independent of `homework_not_required`
    (see `homework_satisfied` for the completion-checklist combination of
    the two). Exposed directly on LessonSerializer for the same reason as
    `attendance_completed`."""
    return Homework.objects.filter(lesson=lesson).exists()


def homework_satisfied(lesson: Lesson) -> bool:
    return lesson.homework_not_required or homework_added(lesson)


def completion_requirements(lesson: Lesson) -> list[CompletionRequirement]:
    """The checklist a Trainer sees before completing a lesson — attendance
    marked for every active student, plus either a real Homework row or an
    explicit "homework not required" flag."""
    return [
        CompletionRequirement(
            key="attendance",
            label="Посещаемость отмечена",
            satisfied=attendance_completed(lesson),
        ),
        CompletionRequirement(
            key="homework",
            label="Добавлено домашнее задание или отмечено «ДЗ не требуется»",
            satisfied=homework_satisfied(lesson),
        ),
    ]


def completion_progress(lesson: Lesson) -> dict:
    requirements = completion_requirements(lesson)
    satisfied = sum(1 for r in requirements if r.satisfied)
    total = len(requirements)
    return {
        "satisfied": satisfied,
        "total": total,
        "is_complete": satisfied == total,
    }


def requirements_satisfied(lesson: Lesson) -> bool:
    return all(r.satisfied for r in completion_requirements(lesson))


def can_start(lesson: Lesson) -> bool:
    return lesson.status == Lesson.Status.SCHEDULED


def can_complete(lesson: Lesson) -> bool:
    return lesson.status == Lesson.Status.IN_PROGRESS and requirements_satisfied(lesson)


def can_cancel(lesson: Lesson) -> bool:
    return lesson.status in (Lesson.Status.SCHEDULED, Lesson.Status.IN_PROGRESS)


def start_lesson(lesson: Lesson, user) -> Lesson:
    """SCHEDULED -> IN_PROGRESS. Idempotent: calling it again on an already
    in-progress lesson is a silent no-op, never an error — a double-click or
    a retried request must not fail."""
    if lesson.status == Lesson.Status.IN_PROGRESS:
        return lesson
    if lesson.status != Lesson.Status.SCHEDULED:
        raise ValidationError(
            {"status": [f"Нельзя начать занятие в статусе «{lesson.get_status_display()}»."]}
        )
    lesson.status = Lesson.Status.IN_PROGRESS
    lesson.started_at = timezone.now()
    lesson.save(update_fields=["status", "started_at", "updated_at"])
    return lesson


def complete_lesson(lesson: Lesson, user) -> Lesson:
    """IN_PROGRESS -> COMPLETED, only once every completion requirement is
    met. Idempotent: an already-completed lesson is returned unchanged
    (its original completed_at/completed_by are never overwritten, and its
    requirements are never re-checked) rather than raising, so a repeated
    request from the trainer's own UI can never fail or reset it."""
    if lesson.status == Lesson.Status.COMPLETED:
        return lesson
    if lesson.status == Lesson.Status.CANCELLED:
        raise ValidationError({"status": ["Отменённое занятие нельзя завершить."]})
    if lesson.status != Lesson.Status.IN_PROGRESS:
        raise ValidationError(
            {"status": ["Сначала нужно начать занятие («Начать занятие»), прежде чем его завершать."]}
        )

    requirements = completion_requirements(lesson)
    missing = [r.label for r in requirements if not r.satisfied]
    if missing:
        raise ValidationError({"completion": missing})

    lesson.status = Lesson.Status.COMPLETED
    lesson.completed_at = timezone.now()
    lesson.completed_by = user
    lesson.save(update_fields=["status", "completed_at", "completed_by", "updated_at"])
    return lesson


def cancel_lesson(lesson: Lesson, user, reason: str = "") -> Lesson:
    """SCHEDULED/IN_PROGRESS -> CANCELLED. Idempotent: an already-cancelled
    lesson is returned unchanged. A completed lesson can never be
    cancelled — completion is the one true terminal state a teacher/Admin
    must explicitly reverse by other means, not silently overwrite."""
    if lesson.status == Lesson.Status.CANCELLED:
        return lesson
    if lesson.status == Lesson.Status.COMPLETED:
        raise ValidationError({"status": ["Нельзя отменить уже завершённое занятие."]})

    lesson.status = Lesson.Status.CANCELLED
    lesson.cancellation_reason = reason or lesson.cancellation_reason
    lesson.save(update_fields=["status", "cancellation_reason", "updated_at"])
    return lesson


def set_homework_not_required(lesson: Lesson, value: bool) -> Lesson:
    """Explicit "no homework for this lesson" flag — the only alternative to
    an actual Homework row for satisfying the completion checklist. Only
    meaningful while the lesson is still open; a finished/cancelled lesson's
    checklist no longer matters."""
    if lesson.status not in (Lesson.Status.SCHEDULED, Lesson.Status.IN_PROGRESS):
        raise ValidationError(
            {"status": ["Эту отметку можно менять только для запланированного или текущего занятия."]}
        )
    lesson.homework_not_required = value
    lesson.save(update_fields=["homework_not_required", "updated_at"])
    return lesson


def homework_results_locked(lesson: Lesson) -> bool:
    """Once a lesson is COMPLETED, grading (status/score/comment on its
    HomeworkResult rows) is frozen for a Teacher — the one place this rule
    lives, checked both by the API (views._assert_homework_results_editable)
    and mirrored on HomeworkSerializer.results_editable so the frontend
    never has to re-derive it from a separate Lesson fetch."""
    return lesson.status == Lesson.Status.COMPLETED
