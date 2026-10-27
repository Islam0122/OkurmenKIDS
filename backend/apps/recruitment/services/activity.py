"""Запись в журнал кадровых событий (HRActivity). Пароли и другие секреты
сюда не попадают — только факт действия и человекочитаемое описание."""
from __future__ import annotations

import logging

from django.utils import timezone

from ..models import HRActivity

logger = logging.getLogger("apps.recruitment")


def log(kind: str, actor, *, employee=None, candidate=None, application=None, interview=None, vacancy=None,
        from_status: str = "", to_status: str = "", message: str = "") -> HRActivity:
    if application is not None and candidate is None:
        candidate = application.candidate
    entry = HRActivity.objects.create(
        kind=kind, actor=actor, employee=employee, candidate=candidate, application=application, interview=interview,
        vacancy=vacancy, from_status=from_status, to_status=to_status, message=message, created_at=timezone.now(),
    )
    logger.info(
        "hr activity kind=%s actor=%s employee=%s candidate=%s application=%s interview=%s vacancy=%s",
        kind, getattr(actor, "pk", None), getattr(employee, "pk", None), getattr(candidate, "pk", None),
        getattr(application, "pk", None), getattr(interview, "pk", None), getattr(vacancy, "pk", None),
    )
    return entry
