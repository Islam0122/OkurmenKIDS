from celery import shared_task


@shared_task(name="push.send_operations_notification", ignore_result=True)
def send_operations_notification(notification_id: int) -> int:
    """Push one apps.operations Notification to its recipient's devices."""
    from apps.operations.models import Notification

    from .services import KIND_CATEGORY, PushMessage, send_to_user

    notification = Notification.objects.select_related("recipient").filter(pk=notification_id).first()
    if notification is None or notification.is_read:
        return 0
    message = PushMessage(
        title=notification.title, body=notification.message, url=notification.link or "/",
        tag=f"ops-{notification.kind}-{notification.pk}",
    )
    return send_to_user(notification.recipient, message, KIND_CATEGORY.get(notification.kind))
