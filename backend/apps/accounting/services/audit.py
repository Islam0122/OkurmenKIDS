"""Запись в журнал аудита — единственная точка, через которую сервисы
фиксируют финансовые действия."""
from __future__ import annotations

import datetime as dt
from decimal import Decimal

from django.db import models

from ..models import PayrollAuditLog


def _jsonable(value):
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (dt.date, dt.datetime)):
        return value.isoformat()
    if isinstance(value, models.Model):
        return value.pk
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    return value


def snapshot(instance: models.Model, fields) -> dict:
    return {name: _jsonable(getattr(instance, name)) for name in fields}


def log(actor, instance: models.Model, action: str, *, old=None, new=None, reason: str = "", payroll=None):
    return PayrollAuditLog.objects.create(
        actor=actor if getattr(actor, "is_authenticated", False) else None,
        entity_type=instance._meta.model_name,
        entity_id=instance.pk,
        action=action,
        old_values=_jsonable(old or {}),
        new_values=_jsonable(new or {}),
        reason=reason,
        payroll=payroll,
    )
