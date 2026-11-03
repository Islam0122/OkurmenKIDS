"""Разрешения «Отпросился»: создание и отмена с аудитом.

Права проверяет вызывающий код (access.can_grant_permissions); здесь —
проверка данных (AttendancePermission.clean: вид, интервал, пересечения) и
запись в журнал AttendanceAdminLog. Отметки по QR не трогаются: разрешение
влияет на расчёт через ScheduleResolver (services/schedule.py).
"""
from __future__ import annotations

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from ..models import AttendanceAdminLog, AttendancePermission


def _audit(actor, action: str, perm: AttendancePermission, changes: dict) -> None:
    AttendanceAdminLog.objects.create(actor=actor, action=action, object_type="AttendancePermission",
                                      object_id=str(perm.pk), changes=changes)


def _snapshot(perm: AttendancePermission) -> dict:
    return {
        "user": perm.user_id, "kind": perm.kind, "starts_at": perm.starts_at.isoformat(),
        "ends_at": perm.ends_at.isoformat(), "reason": perm.reason, "comment": perm.comment, "status": perm.status,
    }


def create(actor, *, user, kind: str, starts_at, ends_at, reason: str, comment: str = "") -> AttendancePermission:
    """Создаёт и сразу утверждает разрешение от имени `actor`."""
    now = timezone.now()
    with transaction.atomic():
        # Блокировка сотрудника: два одновременных запроса не создадут
        # пересекающиеся разрешения (на PostgreSQL; SQLite блокирует базу целиком).
        get_user_model().objects.select_for_update().filter(pk=user.pk).first()
        perm = AttendancePermission(
            user=user, kind=kind, starts_at=starts_at, ends_at=ends_at, reason=(reason or "").strip(),
            comment=(comment or "").strip(), status=AttendancePermission.Status.APPROVED,
            created_by=actor, approved_by=actor, approved_at=now,
        )
        perm.full_clean(exclude=["created_by"])
        perm.save()
        _audit(actor, "permission_create", perm, {k: {"old": None, "new": v} for k, v in _snapshot(perm).items()})
    return perm


def cancel(actor, perm: AttendancePermission, reason: str) -> AttendancePermission:
    reason = (reason or "").strip()
    if not reason:
        raise ValidationError({"reason": "Укажите причину отмены."})
    with transaction.atomic():
        perm = AttendancePermission.objects.select_for_update().get(pk=perm.pk)
        if perm.status != AttendancePermission.Status.APPROVED:
            raise ValidationError({"status": "Разрешение уже отменено."})
        perm.status = AttendancePermission.Status.CANCELLED
        perm.cancelled_by, perm.cancelled_at, perm.cancel_reason = actor, timezone.now(), reason
        perm.save(update_fields=["status", "cancelled_by", "cancelled_at", "cancel_reason"])
        _audit(actor, "permission_cancel", perm, {
            "status": {"old": AttendancePermission.Status.APPROVED, "new": perm.status},
            "cancel_reason": {"old": None, "new": reason},
        })
    return perm
