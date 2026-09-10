"""Bulk attendance marking for a whole lesson at once — the React "mark the group" screen."""
from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import transaction

from ..models import Attendance, Lesson


@transaction.atomic
def bulk_mark_attendance(lesson: Lesson, entries: list[dict]) -> list[Attendance]:
    """Create or update Attendance for `lesson` from a list of entries.

    Each entry is ``{"student": Student, "status": str, "comment": str}``.
    Validated as all-or-nothing: if any student doesn't belong to the
    lesson's group, nothing is written.
    """
    group_student_ids = set(lesson.group.students.values_list("id", flat=True))

    for entry in entries:
        if entry["student"].id not in group_student_ids:
            raise ValidationError(
                f"Студент «{entry['student']}» не принадлежит группе этого занятия."
            )

    records = []
    for entry in entries:
        record, _ = Attendance.objects.update_or_create(
            lesson=lesson,
            student=entry["student"],
            defaults={
                "status": entry["status"],
                "comment": entry.get("comment", ""),
            },
        )
        records.append(record)
    return records
