"""Bulk homework-result upserts — the React "grade the group" screen."""
from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from ..models import Homework, HomeworkResult


@transaction.atomic
def bulk_upsert_homework_results(homework: Homework, entries: list[dict]) -> list[HomeworkResult]:
    """Create or update HomeworkResult for `homework` from a list of entries.

    Each entry is ``{"student": Student, "status": str, "score": int|None,
    "comment": str}``. Validated as all-or-nothing against the lesson's
    group, same as bulk attendance.
    """
    group_student_ids = set(homework.lesson.group.students.values_list("id", flat=True))

    for entry in entries:
        if entry["student"].id not in group_student_ids:
            raise ValidationError(
                f"Студент «{entry['student']}» не принадлежит группе этого занятия."
            )

    now = timezone.now()
    records = []
    for entry in entries:
        status = entry["status"]
        defaults = {
            "status": status,
            "comment": entry.get("comment", ""),
            "score": entry.get("score"),
        }
        if status in (HomeworkResult.Status.SUBMITTED, HomeworkResult.Status.LATE):
            defaults["submitted_at"] = entry.get("submitted_at") or now
        if status == HomeworkResult.Status.CHECKED:
            defaults["checked_at"] = entry.get("checked_at") or now

        record, _ = HomeworkResult.objects.update_or_create(
            homework=homework,
            student=entry["student"],
            defaults=defaults,
        )
        records.append(record)
    return records
