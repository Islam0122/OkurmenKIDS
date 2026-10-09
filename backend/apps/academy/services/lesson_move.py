"""Moving one lesson to another date/time by hand (the Assistant
Workspace's «Перенести» on the schedule), with the same double-booking rules
the weekly schedule has (services.group_schedule_conflicts): the lesson's
trainer, its group and its room must each be free at the new time. Touching
ends (14:00–15:30 and 15:30–17:00) are not an overlap.

A moved lesson is marked `schedule_overridden`, exactly like a hand edit of
its date/time through the lessons API: neither a slot edit nor «Сгенерировать
занятия» moves it back (services.schedule_lesson_sync). Every move is written
to Django's admin history (LogEntry) of the lesson.
"""
from __future__ import annotations

import datetime as dt

from django.contrib.admin.models import CHANGE, LogEntry
from django.core.exceptions import ValidationError
from django.db import transaction

from ..models import Lesson
from .schedule_board import lesson_conflicts


def find_lesson_conflicts(lesson: Lesson, *, date: dt.date, start_time: dt.time, end_time: dt.time) -> list[str]:
    """Human-readable clashes of `lesson` placed at date/start–end with any
    other live (not cancelled) lesson: same trainer, same group, same room
    (services.schedule_board.find_conflicts — the schedule board's check)."""
    return [c["message"] for c in lesson_conflicts(lesson, date=date, start_time=start_time, end_time=end_time)]


def move_lesson(lesson: Lesson, *, date: dt.date, start_time: dt.time, end_time: dt.time, user=None) -> Lesson:
    if lesson.status != Lesson.Status.SCHEDULED:
        raise ValidationError("Перенести можно только запланированное занятие.")
    if end_time <= start_time:
        raise ValidationError({"end_time": "Время окончания должно быть позже времени начала."})
    problems = find_lesson_conflicts(lesson, date=date, start_time=start_time, end_time=end_time)
    if problems:
        raise ValidationError({"conflicts": problems})

    before = f"{lesson.date:%d.%m.%Y} {lesson.start_time:%H:%M}–{lesson.end_time:%H:%M}"
    with transaction.atomic():
        lesson.date, lesson.start_time, lesson.end_time = date, start_time, end_time
        lesson.schedule_overridden = True
        lesson.save(update_fields=["date", "start_time", "end_time", "schedule_overridden", "updated_at"])
        if user is not None and getattr(user, "pk", None):
            LogEntry.objects.log_actions(
                user_id=user.pk, queryset=[lesson], action_flag=CHANGE,
                change_message=f"Занятие перенесено: {before} → {date:%d.%m.%Y} {start_time:%H:%M}–{end_time:%H:%M}.",
                single_object=True,
            )
    return lesson
