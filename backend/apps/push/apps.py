from django.apps import AppConfig


class PushConfig(AppConfig):
    """Web Push (PWA) notifications: browser subscriptions per user, delivery
    preferences, and delivery of apps.operations notifications to installed
    devices. Fully inert until the VAPID keys are configured (docs/push.md)."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.push"
    verbose_name = "Push-уведомления (PWA)"

    def ready(self):
        from . import signals  # noqa: F401 — operations.Notification → push
