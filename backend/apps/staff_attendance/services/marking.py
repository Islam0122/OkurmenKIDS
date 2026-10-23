"""Приход и уход по QR-коду — вся бизнес-логика на сервере.

* Нет открытой сессии → приход разрешён; есть → уход разрешён.
* Повторный приход при открытой сессии и уход без прихода — отказ.
* Время события — только серверное (UTC в БД), время устройства не
  принимается вовсе.
* Параллельные запросы одного сотрудника сериализуются блокировкой его
  строки в users_user (SELECT … FOR UPDATE); последняя линия защиты —
  частичный уникальный индекс «одна открытая сессия на сотрудника».
* Повтор того же запроса (тот же idempotency_key) не создаёт второе событие,
  а возвращает результат первого.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.utils import timezone

from ..models import AttendanceEvent, AttendanceLocation, AttendanceSession, AttendanceSettings
from .geo import haversine_m, within_radius
from .network import ip_in_networks
from .schedule import late_minutes, window_for

logger = logging.getLogger("apps.staff_attendance")


class AttendanceError(Exception):
    """Отказ в отметке: понятное сообщение, машинный код и HTTP-статус."""

    def __init__(self, code: str, message: str, status: int = 400, **extra):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status
        self.extra = extra


@dataclass
class Position:
    latitude: float | None
    longitude: float | None
    accuracy: float | None


@dataclass
class MarkResult:
    session: AttendanceSession
    event: AttendanceEvent
    replayed: bool = False
    closed_stale: AttendanceSession | None = None


def resolve_location(code: str) -> AttendanceLocation:
    location = AttendanceLocation.objects.filter(code=code).first() if code else None
    if location is None:
        raise AttendanceError("location_not_found", "QR-код не относится ни к одному офису OkurmenKIDS.", 404)
    if not location.is_active:
        raise AttendanceError("location_inactive", "Этот офис отключён — отметка в нём недоступна.", 400)
    return location


def check_position(location: AttendanceLocation, position: Position, config: AttendanceSettings) -> float:
    """Расстояние до центра геозоны, если отметка допустима; иначе отказ."""
    if position.latitude is None or position.longitude is None:
        raise AttendanceError(
            "geolocation_required",
            "Не удалось получить геолокацию. Разрешите доступ к местоположению и повторите попытку.",
        )
    if position.accuracy is None:
        raise AttendanceError("accuracy_required", "Браузер не сообщил точность геолокации. Повторите попытку.")
    if position.accuracy > config.max_gps_accuracy_m:
        raise AttendanceError(
            "low_accuracy",
            f"Геолокация слишком неточная (±{round(position.accuracy)} м, допустимо ±{config.max_gps_accuracy_m} м). "
            "Включите GPS / точное местоположение и повторите попытку.",
            accuracy_m=round(position.accuracy, 1), max_accuracy_m=config.max_gps_accuracy_m,
        )
    distance = haversine_m(location.latitude, location.longitude, position.latitude, position.longitude)
    if not within_radius(distance, location.radius_m):
        raise AttendanceError(
            "out_of_range",
            f"Вы находитесь в {round(distance)} м от офиса «{location.name}». "
            f"Отметка возможна только в радиусе {location.radius_m} м.",
            distance_m=round(distance, 1), radius_m=location.radius_m,
        )
    return distance


def check_network(config: AttendanceSettings, ip: str | None) -> None:
    if config.network_check_enabled and not ip_in_networks(ip, config.office_networks):
        raise AttendanceError("network_mismatch", "Отметка возможна только из офисной сети Wi-Fi.", 403)


def _lock_user(user_id: int) -> None:
    # Все отметки одного сотрудника идут друг за другом. На SQLite (тесты)
    # select_for_update — no-op, там остаётся уникальный индекс.
    get_user_model().objects.select_for_update().only("pk").get(pk=user_id)


def _replay(user, key: uuid.UUID | None, kind: str) -> MarkResult | None:
    if key is None:
        return None
    event = AttendanceEvent.objects.select_related("session", "session__location").filter(
        user=user, idempotency_key=key,
    ).first()
    if event is None:
        return None
    if event.kind != kind:
        raise AttendanceError("idempotency_conflict", "Этот запрос уже был обработан как другая отметка.", 409)
    return MarkResult(session=event.session, event=event, replayed=True)


def local_date(moment: datetime, config: AttendanceSettings):
    return timezone.localtime(moment, config.tzinfo).date()


def _close_stale(session: AttendanceSession, now: datetime) -> None:
    """Сессия прошлого дня, где не отметили уход: закрыть без времени ухода.
    Время ухода не выдумывается — запись остаётся «Нет ухода» до исправления."""
    session.status = AttendanceSession.Status.MISSING_CHECKOUT
    session.save(update_fields=["status", "updated_at"])
    AttendanceEvent.objects.create(
        session=session, user_id=session.user_id, kind=AttendanceEvent.Kind.AUTO_CLOSE, occurred_at=now,
        location=session.location,
    )


def check_in(user, location_code: str, position: Position, *, idempotency_key: uuid.UUID | None = None,
             ip: str | None = None, user_agent: str = "") -> MarkResult:
    config = AttendanceSettings.load()
    try:
        with transaction.atomic():
            _lock_user(user.pk)
            if (replayed := _replay(user, idempotency_key, AttendanceEvent.Kind.CHECK_IN)) is not None:
                return replayed
            location = resolve_location(location_code)
            check_network(config, ip)
            distance = check_position(location, position, config)

            now = timezone.now()
            today = local_date(now, config)
            closed_stale = None
            open_session = (
                AttendanceSession.objects.select_for_update()
                .filter(user=user, status=AttendanceSession.Status.OPEN).first()
            )
            if open_session is not None:
                if open_session.work_date >= today:
                    raise AttendanceError(
                        "already_checked_in",
                        f"Приход уже отмечен в {timezone.localtime(open_session.checked_in_at, config.tzinfo):%H:%M}. "
                        "Сейчас можно отметить только уход.",
                        409,
                    )
                _close_stale(open_session, now)
                closed_stale = open_session

            first_today = not AttendanceSession.objects.filter(user=user, work_date=today).exists()
            window = window_for(user, today, config) if first_today else None
            session = AttendanceSession.objects.create(
                user=user, location=location, work_date=today, checked_in_at=now,
                status=AttendanceSession.Status.OPEN, source=AttendanceSession.Source.QR,
                expected_start=window.start if window else None,
                late_minutes=late_minutes(now, window),
                check_in_distance_m=round(distance, 1), check_in_accuracy_m=round(position.accuracy, 1),
            )
            event = AttendanceEvent.objects.create(
                session=session, user=user, kind=AttendanceEvent.Kind.CHECK_IN, occurred_at=now,
                location=location, distance_m=round(distance, 1), accuracy_m=round(position.accuracy, 1),
                idempotency_key=idempotency_key, ip_address=ip, user_agent=(user_agent or "")[:255],
            )
    except IntegrityError:
        # Параллельный запрос успел первым (уникальный индекс): тот же ключ —
        # вернуть его результат, иначе это повторный приход.
        if (replayed := _replay(user, idempotency_key, AttendanceEvent.Kind.CHECK_IN)) is not None:
            return replayed
        raise AttendanceError("already_checked_in", "Приход уже отмечен. Сейчас можно отметить только уход.", 409)
    logger.info("staff_attendance check_in user=%s session=%s distance=%.1f", user.pk, session.pk, distance)
    return MarkResult(session=session, event=event, closed_stale=closed_stale)


def check_out(user, location_code: str, position: Position, *, idempotency_key: uuid.UUID | None = None,
              ip: str | None = None, user_agent: str = "") -> MarkResult:
    config = AttendanceSettings.load()
    try:
        with transaction.atomic():
            _lock_user(user.pk)
            if (replayed := _replay(user, idempotency_key, AttendanceEvent.Kind.CHECK_OUT)) is not None:
                return replayed
            location = resolve_location(location_code)
            check_network(config, ip)
            distance = check_position(location, position, config)

            now = timezone.now()
            session = (
                AttendanceSession.objects.select_for_update()
                .filter(user=user, status=AttendanceSession.Status.OPEN).first()
            )
            if session is None:
                raise AttendanceError("not_checked_in", "Приход ещё не отмечен — сначала отметьте приход.", 409)
            if session.work_date < local_date(now, config):
                raise AttendanceError(
                    "stale_session",
                    f"Уход за {session.work_date:%d.%m.%Y} не был отмечен. Отметьте приход за сегодня, "
                    "а прошлую смену исправит администратор.",
                    409,
                )
            session.checked_out_at = now
            session.status = AttendanceSession.Status.CLOSED
            session.check_out_distance_m = round(distance, 1)
            session.check_out_accuracy_m = round(position.accuracy, 1)
            session.save(update_fields=["checked_out_at", "status", "check_out_distance_m",
                                        "check_out_accuracy_m", "updated_at"])
            event = AttendanceEvent.objects.create(
                session=session, user=user, kind=AttendanceEvent.Kind.CHECK_OUT, occurred_at=now,
                location=location, distance_m=round(distance, 1), accuracy_m=round(position.accuracy, 1),
                idempotency_key=idempotency_key, ip_address=ip, user_agent=(user_agent or "")[:255],
            )
    except IntegrityError:
        if (replayed := _replay(user, idempotency_key, AttendanceEvent.Kind.CHECK_OUT)) is not None:
            return replayed
        raise AttendanceError("not_checked_in", "Уход уже отмечен.", 409)
    logger.info("staff_attendance check_out user=%s session=%s distance=%.1f", user.pk, session.pk, distance)
    return MarkResult(session=session, event=event)


def close_stale_sessions(now: datetime | None = None) -> int:
    """Закрыть открытые сессии прошлых дней как «Нет ухода» (по расписанию).
    Повторный запуск безопасен."""
    config = AttendanceSettings.load()
    now = now or timezone.now()
    today = local_date(now, config)
    closed = 0
    for session_id in AttendanceSession.objects.filter(
        status=AttendanceSession.Status.OPEN, work_date__lt=today,
    ).values_list("pk", flat=True):
        with transaction.atomic():
            session = AttendanceSession.objects.select_for_update().filter(
                pk=session_id, status=AttendanceSession.Status.OPEN,
            ).first()
            if session is not None:
                _close_stale(session, now)
                closed += 1
    return closed
