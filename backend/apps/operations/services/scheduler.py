"""Периодические задачи модуля — один вызов для cron (run_scheduled_tasks) и
Celery Beat. Каждый шаг идемпотентен: повторный запуск не создаёт дублей
задач, проблем и уведомлений (уникальные ключи)."""
from __future__ import annotations

import datetime as dt
import logging

from django.db.models import Q
from django.utils import timezone

from ..models import OPEN_STATUSES, NotificationKind, OperationsSettings, Task
from .issues import scan
from .notifications import dispatch_pending, notify
from .recurrence import generate_all

logger = logging.getLogger(__name__)


def deadline_reminders(now=None) -> dict:
    """«Приближается дедлайн» и «Задача просрочена» — по одному разу на
    дедлайн (ключ содержит дедлайн: перенесли срок — напомним снова)."""
    now = now or timezone.now()
    hours = OperationsSettings.load().deadline_reminder_hours
    soon = overdue = 0
    open_tasks = Task.objects.filter(status__in=OPEN_STATUSES, deadline__isnull=False).select_related(
        "assignee", "created_by")
    for task in open_tasks.filter(deadline__gte=now, deadline__lte=now + dt.timedelta(hours=hours)):
        stamp = int(task.deadline.timestamp())
        if notify(task.assignee, NotificationKind.TASK_DEADLINE, f"task:{task.pk}:soon:{stamp}",
                  f"Приближается дедлайн: {task.title}",
                  f"Срок — {timezone.localtime(task.deadline):%d.%m.%Y %H:%M}.", f"/tasks/{task.pk}"):
            soon += 1
    for task in open_tasks.filter(Q(deadline__lt=now)):
        stamp = int(task.deadline.timestamp())
        for recipient in {task.assignee, task.created_by} - {None}:
            if notify(recipient, NotificationKind.TASK_OVERDUE, f"task:{task.pk}:overdue:{stamp}:{recipient.pk}",
                      f"Задача просрочена: {task.title}",
                      f"Срок был {timezone.localtime(task.deadline):%d.%m.%Y %H:%M}.", f"/tasks/{task.pk}"):
                overdue += 1
    return {"deadline_soon": soon, "overdue": overdue}


def run_periodic(now=None) -> dict:
    now = now or timezone.now()
    result = {}
    for name, step in (("recurring_tasks", lambda: {"created": generate_all(timezone.localtime(now).date())}),
                       ("reminders", lambda: deadline_reminders(now)),
                       ("issues", lambda: scan(now)),
                       ("delivery", lambda: {"sent": dispatch_pending()})):
        try:
            result[name] = step()
        except Exception as exc:  # noqa: BLE001
            logger.exception("operations periodic step %s failed", name)
            result[name] = {"error": str(exc)}
    return result
