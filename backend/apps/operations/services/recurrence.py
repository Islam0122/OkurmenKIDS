"""Генерация повторений из шаблонов TaskRecurrence.

Каждое повторение — обычная Task с `occurrence_date`. Пара (шаблон, дата)
уникальна, поэтому повторный запуск планировщика (cron каждые 30 минут,
Celery Beat раз в час, ручной запуск) не создаёт дубли. Генерируются даты
от `last_generated_on` + 1 (или начала шаблона) до сегодняшней включительно —
пропущенные из-за простоя дни догоняются, но не дальше `CATCH_UP_DAYS` назад.
"""
from __future__ import annotations

import calendar
import datetime as dt
from zoneinfo import ZoneInfo

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from ..models import Recurrence, Task, TaskChecklistItem, TaskHistory, TaskRecurrence
from .tasks import _notify_assigned, log

CATCH_UP_DAYS = 31


def occurs_on(rule: TaskRecurrence, day: dt.date) -> bool:
    if day < rule.starts_on or (rule.ends_on and day > rule.ends_on):
        return False
    if rule.frequency == Recurrence.DAILY:
        return True
    if rule.frequency == Recurrence.WEEKLY:
        return day.weekday() in (rule.weekdays or [])
    last_day = calendar.monthrange(day.year, day.month)[1]
    return day.day == min(rule.month_day or 1, last_day)


def _deadline(rule: TaskRecurrence, day: dt.date):
    when = rule.due_time or dt.time(23, 59)
    return dt.datetime.combine(day, when, tzinfo=ZoneInfo(settings.TIME_ZONE))


def generate_for(rule: TaskRecurrence, today: dt.date) -> list[Task]:
    start = max(rule.starts_on, (rule.last_generated_on + dt.timedelta(days=1)) if rule.last_generated_on
                else rule.starts_on, today - dt.timedelta(days=CATCH_UP_DAYS))
    created = []
    day = start
    while day <= today:
        if occurs_on(rule, day):
            task = _create_occurrence(rule, day)
            if task is not None:
                created.append(task)
        day += dt.timedelta(days=1)
    TaskRecurrence.objects.filter(pk=rule.pk).update(last_generated_on=today)
    return created


def _create_occurrence(rule: TaskRecurrence, day: dt.date) -> Task | None:
    try:
        with transaction.atomic():
            task = Task.objects.create(
                title=rule.title, description=rule.description, department=rule.department, assignee=rule.assignee,
                created_by=rule.created_by, priority=rule.priority, category=rule.category,
                requires_approval=rule.requires_approval, start_date=day, deadline=_deadline(rule, day),
                recurrence=rule, occurrence_date=day,
            )
            for position, text in enumerate(rule.checklist or []):
                TaskChecklistItem.objects.create(task=task, text=str(text)[:255], position=position)
            log(task, None, TaskHistory.Action.CREATED, to_status=task.status,
                changes={"recurrence": rule.pk, "occurrence_date": day.isoformat()})
            _notify_assigned(task, rule.created_by)
    except IntegrityError:
        return None  # это повторение уже создано
    return task


def generate_all(today: dt.date | None = None) -> int:
    today = today or timezone.localdate()
    total = 0
    for rule in TaskRecurrence.objects.filter(is_active=True, assignee__is_active=True).select_related(
            "assignee", "created_by"):
        total += len(generate_for(rule, today))
    return total
