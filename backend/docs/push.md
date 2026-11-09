# Web Push for the PWA (`apps.push`)

Browser push notifications for the installed Okurmen Kids app. Push is
**fully inert** until the VAPID keys are configured: `/push/config/` answers
`enabled: false`, nothing is stored and nothing is sent.

## What gets pushed

Every new `apps.operations.Notification` (tasks, deadlines, reviews, comments,
missing or returned reports, KPI below target, detected issues) is pushed after
commit to the recipient's devices. This covers every staff role. It is
independent of `OPERATIONS_NOTIFICATION_BACKEND` (Telegram), and the outbox's
`delivered_at` is not touched. Push is a best-effort extra channel; the bell in
the LMS remains the source of truth.

Users choose categories on their devices: `tasks`, `reports`, `alerts`
(KPI + issues).

## API (`/api/v1/push/`, authenticated, own data only)

| Method | Path | |
| --- | --- | --- |
| GET | `config/` | `{enabled, public_key}` |
| GET | `subscriptions/` | the caller's devices (no endpoints or keys) |
| POST | `subscriptions/` | `{endpoint, keys: {p256dh, auth}, user_agent}`; idempotent. The same endpoint moves to the account that signs in |
| POST | `subscriptions/unsubscribe/` | `{endpoint}`; only the caller's own |
| GET/PATCH | `preferences/` | `{tasks, reports, alerts}` |
| POST | `test/` | test push to own devices (throttle `push_test`, 10/hour) |

`/api/v1/push/` is open to the isolated roles (accountant, staff-only roles)
through `PERSONAL_WORK_PREFIXES` in `apps.accounting.access`.

## Security

* The VAPID **private** key exists only in server environment variables. The
  frontend only ever receives the public key.
* SSRF protection: subscriptions are accepted and sent only to https push
  services on an allowlist (FCM, Mozilla, Apple, Windows). Override it with
  `PUSH_ALLOWED_ENDPOINT_HOSTS`.
* Payloads are encrypted to the browser (RFC 8291). Notification links are
  forced to same-origin paths. `PUSH_SHOW_CONTENT=False` sends only «У вас новое
  уведомление» to lock screens.
* Dead subscriptions (404/410) are deleted. Five consecutive failures delete
  the row too. Logout in the app unsubscribes the device.
* Admin: subscriptions are read-only and keys are never displayed.

## Configuration

| Variable | Default | |
| --- | --- | --- |
| `PUSH_VAPID_PUBLIC_KEY` | — | base64url public key |
| `PUSH_VAPID_PRIVATE_KEY` | — | base64url private key (**secret**) |
| `PUSH_VAPID_SUBJECT` | — | `mailto:admin@…` or an https URL |
| `PUSH_SHOW_CONTENT` | `True` | show titles/text on the lock screen |
| `PUSH_TTL_SECONDS` | `86400` | how long push services keep undelivered messages |
| `PUSH_ALLOWED_ENDPOINT_HOSTS` | built-in list | comma-separated hosts |
| `PUSH_TEST_RATE` | `10/hour` | throttle for `test/` |

Generate keys once per environment:

```bash
python manage.py generate_vapid_keys
```

Rotating keys invalidates existing subscriptions. Users re-enable push and the
app re-subscribes with the new key automatically.

Deploy: `pip install -r requirements.txt` (adds `pywebpush`), then
`python manage.py migrate`. With a Celery broker, sending runs in the worker;
without one, it runs inline after commit (10 s timeout per device).
