"""Bulk homework-result upserts — the React "grade the group" screen."""
from __future__ import annotations

import logging

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from ..models import Homework, HomeworkResult

# TEMP DEBUG («Мини-отчёт родителям» shows old results): remove once diagnosed.
debug_log = logging.getLogger("okurmen.mini_report_debug")


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
    before = {
        r.student_id: (r.status, r.score)
        for r in HomeworkResult.objects.filter(homework=homework, student__in=[e["student"] for e in entries])
    }
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

    lesson = homework.lesson
    debug_log.warning(
        "[MINI-REPORT DEBUG] HOMEWORK RESULT SAVE homework_id=%s title=%r lesson_id=%s lesson_number=%s "
        "lesson_date=%s group_teacher_id=%s rows=%s",
        homework.pk, homework.title, lesson.pk, lesson.lesson_number, lesson.date, lesson.group_teacher_id, len(entries),
    )
    for entry in entries:
        old_status, old_score = before.get(entry["student"].id, (None, None))
        debug_log.warning(
            "[MINI-REPORT DEBUG]   student_id=%s old_status=%s new_status=%s old_score=%s new_score=%s",
            entry["student"].id, old_status, entry["status"], old_score, entry.get("score"),
        )

    def _after_commit():
        saved = HomeworkResult.objects.filter(homework=homework).values_list("student_id", "status", "score")
        debug_log.warning("[MINI-REPORT DEBUG] AFTER COMMIT homework_id=%s rows=%s", homework.pk, sorted(saved))

    transaction.on_commit(_after_commit)
    return records
