from django.conf import settings
from django.db import models


class PushSubscription(models.Model):
    """One browser/device that agreed to receive push notifications.

    `endpoint` is the push-service URL the browser handed out; it is unique
    across all users — when another account signs in on the same device and
    subscribes, the row moves to that account (see services.save_subscription).
    `p256dh`/`auth` are the browser's public encryption key and auth secret
    (RFC 8291): they only let the server encrypt messages *to* that browser.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="push_subscriptions",
        verbose_name="Пользователь",
    )
    endpoint = models.URLField(max_length=1024, unique=True, verbose_name="Endpoint")
    p256dh = models.CharField(max_length=255, verbose_name="Ключ p256dh")
    auth = models.CharField(max_length=64, verbose_name="Секрет auth")
    user_agent = models.CharField(max_length=255, blank=True, verbose_name="Устройство")
    failure_count = models.PositiveSmallIntegerField(default=0, verbose_name="Ошибок доставки подряд")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Создана")
    last_success_at = models.DateTimeField(null=True, blank=True, verbose_name="Последняя доставка")

    class Meta:
        verbose_name = "Push-подписка"
        verbose_name_plural = "Push-подписки"
        ordering = ["-created_at", "-id"]

    def __str__(self):
        return f"{self.user} — {self.user_agent[:40] or 'устройство'}"


class PushPreference(models.Model):
    """Which categories of notifications a user wants on their devices.
    Missing row = everything on (the defaults below)."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="push_preference",
        verbose_name="Пользователь",
    )
    tasks = models.BooleanField(default=True, verbose_name="Задачи")
    reports = models.BooleanField(default=True, verbose_name="Отчёты")
    alerts = models.BooleanField(default=True, verbose_name="KPI и проблемы")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Настройки push-уведомлений"
        verbose_name_plural = "Настройки push-уведомлений"

    def __str__(self):
        return str(self.user)
