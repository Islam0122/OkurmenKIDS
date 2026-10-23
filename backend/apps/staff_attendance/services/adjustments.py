"""Ручные исправления посещаемости с полным аудитом.

Каждое исправление сохраняет «было» и «стало», причину, автора и время
(AttendanceAdjustment). Исходные события отметок (AttendanceEvent) не
меняются и не удаляются — по ним всегда видно, что реально фиксировал QR.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.utils import timezone

from ..models import (
    AttendanceAdjustment,
    AttendanceEvent,
    AttendanceLocation,
    AttendanceSession,
    AttendanceSettings,
)
from .marking import AttendanceError, local_date
from .schedule import late_minutes, window_for

logger = logging.getLogger("apps.staff_attendance")

MIN_REASON_LENGTH = 5


def snapshot(session: AttendanceSession) -> dict:
    return {
        "work_date": session.work_date.isoformat() if session.work_date else None,
        "checked_in_at": session.checked_in_at.isoformat() if session.checked_in_at else None,
        "checked_out_at": session.checked_out_at.isoformat() if session.checked_out_at else None,
        "status": session.status,
        "late_minutes": session.late_minutes,
        "location_id": session.location_id,
    }


def _validate(user_id: int, checked_in_at: datetime, checked_out_at: datetime | None, reason: str,
              exclude_pk: int | None = None) -> str:
    reason = (reason or "").strip()
    if len(reason) < MIN_REASON_LENGTH:
        raise AttendanceError("reason_required", "Укажите причину исправления (не короче 5 символов).")
    now = timezone.now()
    if checked_in_at > now + timedelta(minutes=1) or (checked_out_at and checked_out_at > now + timedelta(minutes=1)):
        raise AttendanceError("future_time", "Время прихода и ухода не может быть в будущем.")
    if checked_out_at is not None and checked_out_at < checked_in_at:
        raise AttendanceError("invalid_range", "Уход не может быть раньше прихода.")
    if checked_out_at is not None and checked_out_at - checked_in_at > timedelta(hours=24):
        raise AttendanceError("invalid_range", "Сессия не может длиться больше 24 часов.")
    # Пересечение с другими сессиями того же сотрудника.
    end = checked_out_at or now
    others = AttendanceSession.objects.filter(user_id=user_id, checked_in_at__lt=end)
    if exclude_pk is not None:
        others = others.exclude(pk=exclude_pk)
    for other in others:
        other_end = other.checked_out_at or (now if other.status == AttendanceSession.Status.OPEN
                                             else other.checked_in_at)
        if other_end > checked_in_at:
            raise AttendanceError("overlap", "Время пересекается с другой рабочей сессией этого сотрудника.", 409)
    return reason


def _recompute(session: AttendanceSession, config: AttendanceSettings, late_override: int | None) -> None:
    session.work_date = local_date(session.checked_in_at, config)
    earlier = AttendanceSession.objects.filter(
        user_id=session.user_id, work_date=session.work_date, checked_in_at__lt=session.checked_in_at,
    ).exclude(pk=session.pk).exists()
    window = None if earlier else window_for(session.user, session.work_date, config)
    session.expected_start = window.start if window else None
    session.late_minutes = late_override if late_override is not None else late_minutes(session.checked_in_at, window)


def _status_for(session: AttendanceSession, checked_out_at, today) -> str:
    if checked_out_at is not None:
        return AttendanceSession.Status.CLOSED
    if session.status == AttendanceSession.Status.OPEN and session.work_date >= today:
        return AttendanceSession.Status.OPEN
    return AttendanceSession.Status.MISSING_CHECKOUT


def adjust_session(session_id: int, actor, *, checked_in_at: datetime, checked_out_at: datetime | None,
                   reason: str, location: AttendanceLocation | None = None,
                   late_minutes_override: int | None = None) -> AttendanceAdjustment:
    config = AttendanceSettings.load()
    try:
        with transaction.atomic():
            session = AttendanceSession.objects.select_for_update().select_related("user").get(pk=session_id)
            get_user_model().objects.select_for_update().only("pk").get(pk=session.user_id)
            reason = _validate(session.user_id, checked_in_at, checked_out_at, reason, exclude_pk=session.pk)
            before = snapshot(session)
            session.checked_in_at = checked_in_at
            session.checked_out_at = checked_out_at
            if location is not None:
                session.location = location
            _recompute(session, config, late_minutes_override)
            session.status = _status_for(session, checked_out_at, local_date(timezone.now(), config))
            session.is_adjusted = True
            after = snapshot(session)
            if before == after:
                raise AttendanceError("no_changes", "Новые значения совпадают с текущими.")
            session.save()
            adjustment = AttendanceAdjustment.objects.create(
                session=session, action=AttendanceAdjustment.Action.UPDATE, old_values=before, new_values=after,
                reason=reason, adjusted_by=actor,
            )
    except IntegrityError as exc:
        raise AttendanceError("conflict", "У сотрудника уже есть открытая сессия.", 409) from exc
    logger.info("staff_attendance adjust session=%s by=%s", session.pk, actor.pk)
    return adjustment


def create_manual_session(user, actor, *, checked_in_at: datetime, checked_out_at: datetime | None, reason: str,
                          location: AttendanceLocation | None = None,
                          late_minutes_override: int | None = None) -> AttendanceAdjustment:
    """Сотрудник был на работе, но не отметился: запись создаёт администратор."""
    config = AttendanceSettings.load()
    if checked_out_at is None:
        raise AttendanceError("checkout_required", "Для ручной записи укажите и приход, и уход.")
    with transaction.atomic():
        get_user_model().objects.select_for_update().only("pk").get(pk=user.pk)
        reason = _validate(user.pk, checked_in_at, checked_out_at, reason)
        session = AttendanceSession(
            user=user, location=location, checked_in_at=checked_in_at, checked_out_at=checked_out_at,
            status=AttendanceSession.Status.CLOSED, source=AttendanceSession.Source.MANUAL, is_adjusted=True,
        )
        _recompute(session, config, late_minutes_override)
        session.save()
        AttendanceEvent.objects.create(
            session=session, user=user, kind=AttendanceEvent.Kind.MANUAL_CREATE, occurred_at=timezone.now(),
            location=location, created_by=actor,
        )
        adjustment = AttendanceAdjustment.objects.create(
            session=session, action=AttendanceAdjustment.Action.CREATE, old_values={}, new_values=snapshot(session),
            reason=reason, adjusted_by=actor,
        )
    logger.info("staff_attendance manual session=%s user=%s by=%s", session.pk, user.pk, actor.pk)
    return adjustment
