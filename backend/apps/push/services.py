"""Web Push delivery (RFC 8030 / 8291 / 8292 via pywebpush).

Everything here is a no-op until PUSH_VAPID_PUBLIC_KEY, PUSH_VAPID_PRIVATE_KEY
and PUSH_VAPID_SUBJECT are set (and pywebpush is installed): `is_enabled()`
is the single switch the API, the signal and the frontend all read.

Security notes:
* The server only POSTs to endpoints on known push services
  (PUSH_ALLOWED_ENDPOINT_HOSTS) over https — a subscription is user input, so
  an arbitrary URL would otherwise turn the backend into an SSRF proxy.
* Payloads are encrypted end-to-end to the browser, but they are shown on a
  lock screen: with PUSH_SHOW_CONTENT=False only a generic text is sent.
* A 404/410 from the push service means the browser dropped the
  subscription — the row is deleted, so stale devices never pile up.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from urllib.parse import urlsplit

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .models import PushPreference, PushSubscription

logger = logging.getLogger(__name__)

# Delete a subscription after this many consecutive non-404/410 failures.
MAX_FAILURES = 5

# operations.NotificationKind → preference field.
KIND_CATEGORY = {
    "task_assigned": "tasks",
    "task_deadline": "tasks",
    "task_overdue": "tasks",
    "task_rejected": "tasks",
    "task_approved": "tasks",
    "task_review": "tasks",
    "task_comment": "tasks",
    "report_missing": "reports",
    "report_returned": "reports",
    "kpi_below_target": "alerts",
    "issue_detected": "alerts",
}
CATEGORIES = ("tasks", "reports", "alerts")

DEFAULT_ALLOWED_HOSTS = (
    "fcm.googleapis.com",  # Chrome, Edge (Android), Opera, Samsung Internet
    "android.googleapis.com",
    "updates.push.services.mozilla.com",  # Firefox
    "push.services.mozilla.com",
    "web.push.apple.com",  # Safari macOS 13+, iOS/iPadOS 16.4+ (installed PWA)
    "api.push.apple.com",
    "notify.windows.com",  # Edge on Windows (wns2-*.notify.windows.com)
)


def _setting(name: str, default=""):
    return getattr(settings, name, default)


def _webpush():
    try:
        from pywebpush import WebPushException, webpush
    except ImportError:  # pragma: no cover — optional dependency
        return None, None
    return webpush, WebPushException


def is_enabled() -> bool:
    return bool(
        _setting("PUSH_VAPID_PUBLIC_KEY") and _setting("PUSH_VAPID_PRIVATE_KEY") and _setting("PUSH_VAPID_SUBJECT")
        and _webpush()[0] is not None
    )


def public_key() -> str:
    return _setting("PUSH_VAPID_PUBLIC_KEY") if is_enabled() else ""


def endpoint_allowed(endpoint: str) -> bool:
    try:
        parts = urlsplit(endpoint)
    except ValueError:
        return False
    if parts.scheme != "https" or not parts.hostname or parts.port not in (None, 443) or parts.username:
        return False
    host = parts.hostname.lower()
    allowed = tuple(_setting("PUSH_ALLOWED_ENDPOINT_HOSTS", ()) or DEFAULT_ALLOWED_HOSTS)
    return any(host == item or host.endswith("." + item) for item in allowed)


def save_subscription(user, endpoint: str, p256dh: str, auth: str, user_agent: str = "") -> PushSubscription:
    """Create or take over the subscription for this endpoint (same device,
    another account signed in → it now belongs to `user` only)."""
    with transaction.atomic():
        subscription, _ = PushSubscription.objects.update_or_create(
            endpoint=endpoint,
            defaults={"user": user, "p256dh": p256dh, "auth": auth, "user_agent": user_agent[:255],
                      "failure_count": 0},
        )
    return subscription


def preferences_for(user) -> PushPreference:
    preference, _ = PushPreference.objects.get_or_create(user=user)
    return preference


@dataclass(frozen=True)
class PushMessage:
    title: str
    body: str = ""
    url: str = "/"
    tag: str = ""

    def payload(self) -> str:
        show = _setting("PUSH_SHOW_CONTENT", True)
        url = self.url if self.url.startswith("/") and not self.url.startswith("//") else "/"
        data = {
            "title": self.title[:120] if show else "OkurmenKids",
            "body": self.body[:240] if show else "У вас новое уведомление.",
            "url": url,
            "tag": self.tag[:64],
        }
        return json.dumps(data, ensure_ascii=False)


def send_to_user(user, message: PushMessage, category: str | None = None) -> int:
    """Deliver `message` to every device of `user`. Returns the number of
    devices the push service accepted. Never raises."""
    if not is_enabled() or user is None or not user.is_active:
        return 0
    if category in CATEGORIES:
        preference = PushPreference.objects.filter(user=user).first()
        if preference is not None and not getattr(preference, category):
            return 0

    webpush, WebPushException = _webpush()
    payload = message.payload()
    delivered = 0
    for subscription in PushSubscription.objects.filter(user=user):
        if not endpoint_allowed(subscription.endpoint):
            subscription.delete()
            continue
        try:
            webpush(
                subscription_info={"endpoint": subscription.endpoint,
                                   "keys": {"p256dh": subscription.p256dh, "auth": subscription.auth}},
                data=payload,
                ttl=int(_setting("PUSH_TTL_SECONDS", 60 * 60 * 24)),
                timeout=10,
                vapid_private_key=_setting("PUSH_VAPID_PRIVATE_KEY"),
                # A fresh dict per device: pywebpush fills in "aud" (the push
                # service's origin) on it, which differs between services.
                vapid_claims={"sub": _setting("PUSH_VAPID_SUBJECT")},
            )
        except WebPushException as exc:
            status = getattr(getattr(exc, "response", None), "status_code", None)
            if status in (404, 410):
                subscription.delete()
                continue
            _record_failure(subscription, f"push service {status}")
            continue
        except Exception as exc:  # noqa: BLE001 — network etc.: one device never breaks the rest
            _record_failure(subscription, type(exc).__name__)
            continue
        PushSubscription.objects.filter(pk=subscription.pk).update(failure_count=0, last_success_at=timezone.now())
        delivered += 1
    return delivered


def _record_failure(subscription: PushSubscription, reason: str) -> None:
    logger.warning("push: delivery to subscription %s failed: %s", subscription.pk, reason)
    if subscription.failure_count + 1 >= MAX_FAILURES:
        subscription.delete()
        return
    PushSubscription.objects.filter(pk=subscription.pk).update(failure_count=subscription.failure_count + 1)
