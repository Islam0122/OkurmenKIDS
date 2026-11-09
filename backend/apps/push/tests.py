from __future__ import annotations

import base64
import json
from unittest import mock

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.operations.models import Notification, NotificationKind
from apps.operations.services.notifications import notify
from apps.users.models import User

from . import services
from .models import PushPreference, PushSubscription


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _vapid_pair() -> tuple[str, str]:
    key = ec.generate_private_key(ec.SECP256R1())
    public = key.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    return _b64(public), _b64(key.private_numbers().private_value.to_bytes(32, "big"))


def _browser_keys() -> dict:
    """A real browser-side key pair, so pywebpush actually encrypts."""
    key = ec.generate_private_key(ec.SECP256R1())
    public = key.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    return {"p256dh": _b64(public), "auth": _b64(b"0123456789abcdef")}


VAPID_PUBLIC, VAPID_PRIVATE = _vapid_pair()
PUSH_ON = {
    "PUSH_VAPID_PUBLIC_KEY": VAPID_PUBLIC,
    "PUSH_VAPID_PRIVATE_KEY": VAPID_PRIVATE,
    "PUSH_VAPID_SUBJECT": "mailto:admin@okurmen.kg",
}
FCM = "https://fcm.googleapis.com/fcm/send/abc123"
APPLE = "https://web.push.apple.com/QGx1"


def make_user(username: str, role: str = User.Role.TEACHER) -> User:
    return User.objects.create_user(username=username, email=f"{username}@okurmen.kg", password="Str0ngPassw0rd!",
                                    role=role, is_verified=True)


class FakeResponse:
    def __init__(self, status_code: int):
        self.status_code = status_code
        self.text = ""
        self.content = b""
        self.headers = {}
        self.reason = "status"
        self.ok = status_code < 400


class PushApiDisabledTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = make_user("t1")
        self.client.force_authenticate(self.user)

    def test_config_reports_disabled_without_keys(self):
        response = self.client.get("/api/v1/push/config/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"enabled": False, "public_key": ""})

    def test_subscribe_refused_when_disabled(self):
        response = self.client.post("/api/v1/push/subscriptions/", {"endpoint": FCM, "keys": _browser_keys()},
                                    format="json")
        self.assertEqual(response.status_code, 503)
        self.assertFalse(PushSubscription.objects.exists())

    def test_anonymous_is_rejected(self):
        self.assertEqual(APIClient().get("/api/v1/push/config/").status_code, 401)

    def test_signal_does_nothing_when_disabled(self):
        with mock.patch("apps.push.tasks.send_operations_notification.delay") as delay:
            with self.captureOnCommitCallbacks(execute=True):
                notify(self.user, NotificationKind.TASK_ASSIGNED, "k1", "Новая задача")
        delay.assert_not_called()


@override_settings(**PUSH_ON)
class PushApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = make_user("t1")
        self.other = make_user("t2")
        self.client.force_authenticate(self.user)

    def subscribe(self, endpoint=FCM, client=None):
        return (client or self.client).post(
            "/api/v1/push/subscriptions/", {"endpoint": endpoint, "keys": _browser_keys(), "user_agent": "Chrome"},
            format="json",
        )

    def test_config_exposes_only_public_key(self):
        data = self.client.get("/api/v1/push/config/").json()
        self.assertEqual(data, {"enabled": True, "public_key": VAPID_PUBLIC})
        self.assertNotIn(VAPID_PRIVATE, json.dumps(data))

    def test_subscribe_is_idempotent_and_hides_keys(self):
        self.assertEqual(self.subscribe().status_code, 201)
        response = self.subscribe()
        self.assertEqual(response.status_code, 201)
        self.assertEqual(PushSubscription.objects.count(), 1)
        self.assertNotIn("endpoint", response.json())
        listed = self.client.get("/api/v1/push/subscriptions/").json()
        self.assertEqual(len(listed), 1)
        self.assertEqual(set(listed[0]), {"id", "user_agent", "created_at", "last_success_at"})

    def test_rejects_unknown_or_insecure_endpoints(self):
        for endpoint in ("https://evil.example.com/push", "http://fcm.googleapis.com/fcm/send/x",
                         "https://fcm.googleapis.com.evil.com/x", "https://fcm.googleapis.com:8443/x",
                         "https://user@fcm.googleapis.com/x"):
            with self.subTest(endpoint=endpoint):
                self.assertEqual(self.subscribe(endpoint).status_code, 400)
        self.assertFalse(PushSubscription.objects.exists())
        self.assertEqual(self.subscribe("https://wns2-am3p.notify.windows.com/w/?token=1").status_code, 201)

    def test_same_device_moves_to_the_account_that_signed_in(self):
        self.subscribe()
        other_client = APIClient()
        other_client.force_authenticate(self.other)
        self.subscribe(client=other_client)
        self.assertEqual(PushSubscription.objects.get().user, self.other)
        self.assertEqual(self.client.get("/api/v1/push/subscriptions/").json(), [])

    def test_unsubscribe_only_own(self):
        self.subscribe()
        other_client = APIClient()
        other_client.force_authenticate(self.other)
        other_client.post("/api/v1/push/subscriptions/unsubscribe/", {"endpoint": FCM}, format="json")
        self.assertEqual(PushSubscription.objects.count(), 1)
        response = self.client.post("/api/v1/push/subscriptions/unsubscribe/", {"endpoint": FCM}, format="json")
        self.assertEqual(response.status_code, 204)
        self.assertFalse(PushSubscription.objects.exists())

    def test_preferences_default_on_and_patchable(self):
        self.assertEqual(self.client.get("/api/v1/push/preferences/").json(),
                         {"tasks": True, "reports": True, "alerts": True})
        response = self.client.patch("/api/v1/push/preferences/", {"reports": False}, format="json")
        self.assertEqual(response.json(), {"tasks": True, "reports": False, "alerts": True})

    def test_isolated_roles_can_manage_their_devices(self):
        client = APIClient()
        client.force_authenticate(make_user("acc", User.Role.ACCOUNTANT))
        self.assertEqual(client.get("/api/v1/push/config/").status_code, 200)


@override_settings(**PUSH_ON)
class PushDeliveryTests(TestCase):
    def setUp(self):
        self.user = make_user("t1")
        self.sub = services.save_subscription(self.user, FCM, **_browser_keys())

    def test_real_encryption_and_vapid_headers(self):
        with mock.patch("requests.post", return_value=FakeResponse(201)) as post:
            delivered = services.send_to_user(self.user, services.PushMessage("Привет", "Тело", "/tasks/1"))
        self.assertEqual(delivered, 1)
        kwargs = post.call_args.kwargs
        self.assertEqual(post.call_args.args[0], FCM)
        self.assertEqual(kwargs["headers"]["content-encoding"], "aes128gcm")
        self.assertIn("vapid t=", kwargs["headers"]["authorization"])
        self.assertNotIn("Привет".encode(), kwargs["data"])  # encrypted, not plain text
        self.sub.refresh_from_db()
        self.assertIsNotNone(self.sub.last_success_at)

    def test_each_push_service_gets_its_own_audience(self):
        services.save_subscription(self.user, APPLE, **_browser_keys())
        with mock.patch("requests.post", return_value=FakeResponse(201)) as post:
            self.assertEqual(services.send_to_user(self.user, services.PushMessage("x")), 2)
        audiences = set()
        for call in post.call_args_list:
            token = call.kwargs["headers"]["authorization"].split("t=")[1].split(",")[0]
            claims = json.loads(base64.urlsafe_b64decode(token.split(".")[1] + "=="))
            audiences.add(claims["aud"])
        self.assertEqual(audiences, {"https://fcm.googleapis.com", "https://web.push.apple.com"})

    def test_gone_subscription_is_deleted(self):
        with mock.patch("requests.post", return_value=FakeResponse(410)):
            self.assertEqual(services.send_to_user(self.user, services.PushMessage("x")), 0)
        self.assertFalse(PushSubscription.objects.exists())

    def test_repeated_failures_prune_subscription(self):
        with mock.patch("requests.post", return_value=FakeResponse(500)):
            for _ in range(services.MAX_FAILURES - 1):
                services.send_to_user(self.user, services.PushMessage("x"))
            self.assertTrue(PushSubscription.objects.exists())
            services.send_to_user(self.user, services.PushMessage("x"))
        self.assertFalse(PushSubscription.objects.exists())

    def test_preference_off_skips_category(self):
        PushPreference.objects.create(user=self.user, tasks=False)
        with mock.patch("requests.post", return_value=FakeResponse(201)) as post:
            self.assertEqual(services.send_to_user(self.user, services.PushMessage("x"), "tasks"), 0)
            self.assertEqual(services.send_to_user(self.user, services.PushMessage("x"), "reports"), 1)
        self.assertEqual(post.call_count, 1)

    def test_payload_never_carries_external_links(self):
        for url, expected in (("/tasks/5", "/tasks/5"), ("https://evil.com", "/"), ("//evil.com", "/")):
            with self.subTest(url=url):
                self.assertEqual(json.loads(services.PushMessage("t", url=url).payload())["url"], expected)

    @override_settings(PUSH_SHOW_CONTENT=False)
    def test_hidden_content_mode(self):
        payload = json.loads(services.PushMessage("Задача: зарплата Иванова", "секрет").payload())
        self.assertNotIn("Иванова", json.dumps(payload, ensure_ascii=False))
        self.assertNotIn("секрет", json.dumps(payload, ensure_ascii=False))

    def test_operations_notification_is_pushed_after_commit(self):
        with mock.patch("requests.post", return_value=FakeResponse(201)) as post:
            with self.captureOnCommitCallbacks(execute=True):
                notify(self.user, NotificationKind.TASK_ASSIGNED, "task:1:assigned", "Новая задача", "", "/tasks/1")
        self.assertEqual(post.call_count, 1)
        # The outbox's own delivery state is untouched by push.
        self.assertIsNone(Notification.objects.get().delivered_at)
