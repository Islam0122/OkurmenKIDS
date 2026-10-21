"""Уведомления бухгалтерии — transactional outbox.

`notify()` пишет `BillingNotification` в текущей транзакции: откатилась
операция — уведомления нет. Доставка — после коммита
(`transaction.on_commit`) и повторно Celery-задачей для неотправленных.
Повторный запуск не дублирует уведомление: `dedup_key` уникален.

Канал доставки — `BILLING_NOTIFICATION_BACKEND` (путь к функции,
принимающей уведомление). По умолчанию — запись в лог; уведомление в любом
случае видно в разделе оплаты (`GET billing/notifications/`).
"""
from __future__ import annotations

import logging

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone
from django.utils.module_loading import import_string

from ..models import BillingNotification

logger = logging.getLogger(__name__)
MAX_ATTEMPTS = 5


def notify(kind: str, dedup_key: str, title: str, message: str = "", *, recipient=None, profile=None,
           invoice=None, payload=None) -> BillingNotification | None:
    """Создать уведомление (идемпотентно по `dedup_key`). None — уже было."""
    try:
        with transaction.atomic():
            notification = BillingNotification.objects.create(
                kind=kind, dedup_key=dedup_key[:120], title=title[:200], message=message, recipient=recipient,
                profile=profile, invoice=invoice, payload=payload or {},
            )
    except IntegrityError:
        return None
    transaction.on_commit(dispatch_pending_safely)
    return notification


def default_backend(notification: BillingNotification) -> None:
    logger.info("billing notification [%s] %s — %s", notification.kind, notification.title, notification.message)


def _backend():
    path = getattr(settings, "BILLING_NOTIFICATION_BACKEND", "")
    return import_string(path) if path else default_backend


def dispatch_pending(limit: int = 200) -> int:
    """Доставить ожидающие уведомления. Каждое — под своей блокировкой
    (`skip_locked`), поэтому параллельные запуски не отправят дважды."""
    sent = 0
    backend = _backend()
    ids = list(
        BillingNotification.objects.filter(
            status__in=(BillingNotification.Status.PENDING, BillingNotification.Status.FAILED),
            attempts__lt=MAX_ATTEMPTS,
        ).order_by("created_at").values_list("pk", flat=True)[:limit]
    )
    for pk in ids:
        with transaction.atomic():
            notification = (
                BillingNotification.objects.select_for_update(skip_locked=True).filter(pk=pk).first()
            )
            if notification is None or notification.status == BillingNotification.Status.SENT:
                continue
            notification.attempts += 1
            try:
                backend(notification)
            except Exception as exc:  # noqa: BLE001 — канал доставки внешний, ошибка не должна ронять обработку
                notification.status = BillingNotification.Status.FAILED
                notification.last_error = str(exc)[:2000]
            else:
                notification.status = BillingNotification.Status.SENT
                notification.sent_at = timezone.now()
                sent += 1
            notification.save(update_fields=["status", "attempts", "last_error", "sent_at"])
    return sent


def dispatch_pending_safely() -> None:
    try:
        dispatch_pending()
    except Exception:  # noqa: BLE001 — доставку повторит фоновая задача
        logger.exception("billing notifications dispatch failed")
