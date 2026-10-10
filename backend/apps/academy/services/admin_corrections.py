"""Admin corrections of a lesson's records — attendance, homework results
and the homework itself — from Django Admin, also after the lesson is
completed.

A completed (or cancelled) lesson is locked for its Trainer: the API refuses
any change (views._assert_lesson_editable / lesson_lifecycle
.lesson_editing_locked). That lock stays exactly as it is. These functions
are the one trusted server-side path around it, for Admin only:

* the caller must be an administrator — a superuser or the ADMIN role, the
  project's own rule (apps.users.permissions.is_admin_user; access comes
  from the role, never from Django model permissions). Checked here, not
  only in the view, so no other entry point can reuse them for a Trainer;
* the values are validated like everywhere else (model choices / validators,
  the student belongs to the lesson's group);
* every correction is written to the record's Django admin history
  (LogEntry): who, when, what it was and what it became.

KPI, attendance statistics, reports and analytics read Attendance and
HomeworkResult live, so a correction shows there at once — nothing to
recalculate.
"""
from __future__ import annotations

from django.contrib.admin.models import CHANGE, LogEntry
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from apps.users.permissions import is_admin_user

from ..models import Attendance, Homework, HomeworkResult, Lesson

ADMIN_ONLY = "Исправлять посещаемость и домашние задания вручную может только администратор."


def _require_admin(user) -> None:
    if not is_admin_user(user):
        raise PermissionDenied(ADMIN_ONLY)


def _lesson_note(lesson: Lesson) -> str:
    if lesson.status == Lesson.Status.COMPLETED:
        return " (занятие уже проведено — исправление администратора)"
    return ""


def _log(user, obj, changes: list[str], lesson: Lesson) -> None:
    LogEntry.objects.log_actions(
        user_id=user.pk, queryset=[obj], action_flag=CHANGE,
        change_message="Исправлено: " + "; ".join(changes) + _lesson_note(lesson) + ".",
        single_object=True,
    )


def _label(choices, value) -> str:
    return dict(choices).get(value, value or "—")


@transaction.atomic
def correct_attendance(record: Attendance, *, status: str, comment: str = "", user) -> Attendance:
    """Set one student's attendance status / comment on any lesson that took
    place (completed included). A cancelled lesson has no attendance —
    same rule as the Assistant Workspace."""
    _require_admin(user)
    record = Attendance.objects.select_for_update().select_related("lesson", "student").get(pk=record.pk)
    if record.lesson.status == Lesson.Status.CANCELLED:
        raise ValidationError({"status": "Занятие отменено — посещаемость не отмечается."})
    if status not in Attendance.Status.values:
        raise ValidationError({"status": "Выберите статус из списка."})
    comment = (comment or "").strip()

    changes = []
    if record.status != status:
        changes.append(f"статус: {_label(Attendance.Status.choices, record.status)} → {_label(Attendance.Status.choices, status)}")
    if record.comment != comment:
        changes.append(f"комментарий: «{record.comment}» → «{comment}»")
    if not changes:
        return record
    record.status, record.comment = status, comment
    record.full_clean()
    record.save(update_fields=["status", "comment", "updated_at"])
    _log(user, record, changes, record.lesson)
    return record


@transaction.atomic
def correct_homework_result(result: HomeworkResult, *, status: str, score, comment: str = "", user) -> HomeworkResult:
    """Set one student's homework status / score / comment, with the same
    submitted_at / checked_at rules as the trainer's own grading
    (services.homework_service.bulk_upsert_homework_results)."""
    _require_admin(user)
    result = HomeworkResult.objects.select_for_update().select_related("homework__lesson", "student").get(pk=result.pk)
    if status not in HomeworkResult.Status.values:
        raise ValidationError({"status": "Выберите статус из списка."})
    if score in ("", None):
        score = None
    else:
        try:
            score = int(score)
        except (TypeError, ValueError):
            raise ValidationError({"score": "Оценка — целое число."})
    comment = (comment or "").strip()

    changes = []
    if result.status != status:
        changes.append(f"статус: {_label(HomeworkResult.Status.choices, result.status)} → {_label(HomeworkResult.Status.choices, status)}")
    if result.score != score:
        changes.append(f"оценка: {result.score if result.score is not None else '—'} → {score if score is not None else '—'}")
    if result.comment != comment:
        changes.append(f"комментарий: «{result.comment}» → «{comment}»")
    if not changes:
        return result

    now = timezone.now()
    result.status, result.score, result.comment = status, score, comment
    if status in (HomeworkResult.Status.SUBMITTED, HomeworkResult.Status.LATE) and result.submitted_at is None:
        result.submitted_at = now
    if status == HomeworkResult.Status.CHECKED and result.checked_at is None:
        result.checked_at = now
    result.full_clean()
    result.save()
    _log(user, result, changes, result.homework.lesson)
    return result


@transaction.atomic
def correct_homework(homework: Homework, *, title: str, description: str = "", deadline=None, user) -> Homework:
    """Fix the homework assignment itself (title / description / deadline)."""
    _require_admin(user)
    homework = Homework.objects.select_for_update().select_related("lesson").get(pk=homework.pk)
    title = (title or "").strip()
    description = (description or "").strip()
    if not title:
        raise ValidationError({"title": "Укажите название задания."})

    changes = []
    if homework.title != title:
        changes.append(f"название: «{homework.title}» → «{title}»")
    if homework.description != description:
        changes.append("описание")
    if homework.deadline != deadline:
        changes.append(f"срок: {homework.deadline or '—'} → {deadline or '—'}")
    if not changes:
        return homework
    homework.title, homework.description, homework.deadline = title, description, deadline
    homework.full_clean()
    homework.save()
    _log(user, homework, changes, homework.lesson)
    return homework
