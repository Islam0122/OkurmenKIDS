"""A new operations Notification (tasks, reports, KPI, issues — every staff
role) is also pushed to the recipient's installed devices, after commit.
Independent of OPERATIONS_NOTIFICATION_BACKEND (Telegram etc.): push is a
best-effort extra channel and never touches the outbox's delivery state."""
import logging

from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.operations.models import Notification

from . import services

logger = logging.getLogger(__name__)


def _dispatch(notification_id: int) -> None:
    from .tasks import send_operations_notification

    try:
        send_operations_notification.delay(notification_id)
    except Exception:  # noqa: BLE001 — a push failure must never break the request
        logger.exception("push: could not dispatch notification %s", notification_id)


@receiver(post_save, sender=Notification, dispatch_uid="push_operations_notification")
def push_new_notification(sender, instance, created, **kwargs):
    if created and services.is_enabled():
        transaction.on_commit(lambda: _dispatch(instance.pk))
