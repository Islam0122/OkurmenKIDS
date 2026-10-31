"""Уведомления сотрудникам — transactional outbox (тот же приём, что
apps.billing.services.notifications).

`notify()` пишет Notification в текущей транзакции: откатилась операция —
уведомления нет. Повтор с тем же `dedup_key` ничего не создаёт, поэтому
повторная проверка дедлайнов или проблем не шлёт дубли. Уведомление всегда
видно в LMS (`GET /api/v1/notifications/`); доставка во внешний канал
(`OPERATIONS_NOTIFICATION_BACKEND`, например Telegram) — после коммита и
повторно планировщиком для неотправленных.
"""
from __future__ import annotations

import json
import logging
import urllib.request

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone
from django.utils.module_loading import import_string

from ..models import Notification, OperationsSettings

logger = logging.getLogger(__name__)
MAX_ATTEMPTS = 5


def notify(recipient, kind: str, dedup_key: str, title: str, message: str = "", link: str = "") -> Notification | None:
    """Создать уведомление (идемпотентно по `dedup_key`). None — уже было
    или получателя нет / он неактивен."""
    if recipient is None or not recipient.is_active:
        return None
    try:
        with transaction.atomic():
            notification = Notification.objects.create(
                recipient=recipient, kind=kind, dedup_key=dedup_key[:160], title=title[:200], message=message,
                link=link[:255],
            )
    except IntegrityError:
        return None
    if getattr(settings, "OPERATIONS_NOTIFICATION_BACKEND", ""):
        transaction.on_commit(dispatch_pending_safely)
    return notification


def _backend():
    path = getattr(settings, "OPERATIONS_NOTIFICATION_BACKEND", "")
    return import_string(path) if path else None


def dispatch_pending(limit: int = 100) -> int:
    """Отправить неотправленные уведомления во внешний канал. Возвращает
    число доставленных. Без настроенного канала — ничего не делает."""
    backend = _backend()
    if backend is None:
        return 0
    if not OperationsSettings.load().notify_telegram and backend is telegram_backend:
        return 0
    sent = 0
    pending = Notification.objects.filter(delivered_at__isnull=True, delivery_attempts__lt=MAX_ATTEMPTS)
    for notification in pending.select_related("recipient").order_by("id")[:limit]:
        try:
            backend(notification)
        except Exception as exc:  # noqa: BLE001 — канал недоступен: повторим позже
            Notification.objects.filter(pk=notification.pk).update(
                delivery_attempts=notification.delivery_attempts + 1, delivery_error=str(exc)[:255],
            )
            continue
        Notification.objects.filter(pk=notification.pk).update(
            delivered_at=timezone.now(), delivery_attempts=notification.delivery_attempts + 1, delivery_error="",
        )
        sent += 1
    return sent


def dispatch_pending_safely() -> None:
    try:
        dispatch_pending()
    except Exception:  # noqa: BLE001 — сбой доставки не должен ронять запрос
        logger.exception("operations: notification dispatch failed")


def telegram_backend(notification: Notification) -> None:
    """Доставка через Telegram Bot API. Нужны токен бота
    (OPERATIONS_TELEGRAM_BOT_TOKEN) и chat_id сотрудника. В LMS chat_id
    сотрудников пока не хранится (вопрос к руководству, docs/operations.md):
    без него уведомление считается доставленным только в LMS."""
    token = getattr(settings, "OPERATIONS_TELEGRAM_BOT_TOKEN", "")
    chat_id = getattr(notification.recipient, "telegram_chat_id", "")
    if not token or not chat_id:
        return
    body = json.dumps({"chat_id": chat_id, "text": f"{notification.title}\n{notification.message}".strip()}).encode()
    request = urllib.request.Request(f"https://api.telegram.org/bot{token}/sendMessage", data=body,
                                     headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=10):  # noqa: S310 — фиксированный https-адрес Bot API
        pass
