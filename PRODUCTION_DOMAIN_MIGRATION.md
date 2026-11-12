# Production domain migration: `okurmenkids.com`

This document covers the audit, the code changes on this branch, and the manual
Vercel, Railway and DNS steps for moving Okurmen Kids to its custom domain.

> **Status:** the code changes below are made and checked locally. **Nothing has
> been deployed, and no live check was possible.** The audit sandbox has no
> outbound access to `*.okurmenkids.com`, `*.vercel.app` or `*.up.railway.app`
> (the egress proxy refused every connection). Every item in §9 is still
> **NOT VERIFIED** until someone runs it against the deployed services.

---

## 1. Target architecture and how it maps to this repository

| Service | Production URL | Hosting | Code in this repo |
|---|---|---|---|
| Public website | https://okurmenkids.com | Vercel (own project) | `okurmen-public-website/` |
| WWW redirect | https://www.okurmenkids.com → 308 → apex | Vercel (same project as the website) | **Vercel Domains setting only** (not `vercel.json`, see §6.1) |
| LMS | https://lms.okurmenkids.com | Vercel | `frontend/` |
| Admin dashboard | https://admin.okurmenkids.com | Vercel | `frontend/` (see note below) |
| Backend API | https://api.okurmenkids.com | Railway | `backend/` |
| API docs | https://api.okurmenkids.com/api/docs/ | Railway | `backend/config/urls.py` (new alias) |
| Django admin | https://api.okurmenkids.com/admin/ | Railway | `backend/` (Jazzmin) |

Things the audit found outside that table:

* **There is no separate "admin dashboard" frontend in this repository.** The
  admin, director, accountant, HR, marketing and operations screens are role-gated
  routes inside the single `frontend/` SPA (`src/app/router/index.tsx`,
  `RequireRoles`). So `admin.okurmenkids.com` should be **a second Vercel project
  with Root Directory `frontend`**, the same build and the same env vars as the
  LMS. It is a separate origin, so its `localStorage` (and therefore the JWT
  login) is separate: users sign in on each domain once. If a separate admin
  codebase exists elsewhere, apply the same `VITE_API_BASE_URL` rules to it and
  keep its origin in `FRONTEND_ORIGINS`.
* **`training-portal/`** is a fourth Vercel app (`training-portal-theta.vercel.app`).
  It isn't in the target table, so it stays where it is. Its origin remains allowed
  through `TRAINING_PORTAL_ORIGINS`. To give it a custom domain later (for example
  `train.okurmenkids.com`), set `VITE_API_URL=https://api.okurmenkids.com` and add
  the origin to `TRAINING_PORTAL_ORIGINS`.
* The `frontend/` build also serves the schedule, leaderboard, statistics, careers
  and portal sites through `VITE_APP_MODE`. The README suggests subdomains for
  them. Their CORS origins come from `SCHEDULE_SITE_ORIGINS`,
  `LEADERBOARD_SITE_ORIGINS`, `STATISTICS_SITE_ORIGINS` and `PORTAL_SITE_ORIGINS`,
  which are unchanged.

---

## 2. Audit: problems found

Severity: 🔴 breaks production or a security hole · 🟠 breaks the new domain · 🟡 hygiene or latent risk.

| # | Sev | Where | Problem | Fixed? |
|---|---|---|---|---|
| 1 | 🔴 | `backend/deployment/server-entrypoint.sh` | Every boot created superuser **`admin` / password `admin`** if missing, on a public `/admin/`. | ✅ Only created when `DJANGO_SUPERUSER_PASSWORD` is set. **Manual check needed:** if a user `admin` with password `admin` already exists in production, change that password now (§10). |
| 2 | 🟠 | `settings/production.py` | `ALLOWED_HOSTS = [env.str("ALLOWED_HOST")]` takes one host only. `api.okurmenkids.com` would get **HTTP 400** while the Railway host is set, and the reverse. | ✅ `ALLOWED_HOSTS` list (default `api.okurmenkids.com`), plus the legacy `ALLOWED_HOST`, plus Railway's `RAILWAY_PUBLIC_DOMAIN` and `healthcheck.railway.app`. |
| 3 | 🟠 | `settings/cors.py` | None of the new frontend origins (`okurmenkids.com`, `www`, `lms`, `admin`) was allowed. The LMS origin was hard-coded as `okurmen-kids-drab.vercel.app`, with no env variable to change it. | ✅ New `FRONTEND_ORIGINS` (defaults to the four new origins) and `CORS_EXTRA_ORIGINS`. Legacy origins are kept. |
| 4 | 🔴 | `settings/production.py` | `CSRF_TRUSTED_ORIGINS = ["https://*.railway.app", "https://*.up.railway.app"]` trusted **every app anyone hosts on Railway**, and none of the real origins. | ✅ An exact list: `CSRF_TRUSTED_ORIGINS` env + every `ALLOWED_HOSTS` entry as `https://…` + `FRONTEND_ORIGINS`. |
| 5 | 🟡 | `settings/cors.py` | `http://localhost:*` and `http://127.0.0.1:*` were allowed CORS origins **in production** too. | ✅ Production only allows them when `CORS_ALLOW_LOCALHOST=True`. Dev and tests are unchanged. |
| 6 | 🟡 | `settings/cors.py` | `CORS_ALLOW_CREDENTIALS = True`, but no frontend sends cookies (JWT in `Authorization`, `withCredentials: false`). Once the frontends move to `*.okurmenkids.com` they are the **same site** as the API, so `SameSite=Lax` no longer keeps a Django-admin session cookie off cross-origin XHR from those origins. | ✅ Off by default, `CORS_ALLOW_CREDENTIALS=True` turns it back on. |
| 7 | 🟠 | `settings/production.py` | `SECURE_SSL_REDIRECT=True` with no exemption, so a Railway health check (plain HTTP inside the network) gets a 301 and fails. | ✅ `SECURE_REDIRECT_EXEMPT = [r"^api/v1/$"]`, the existing health view only. |
| 8 | 🟠 | `config/urls.py` | `/api/docs/` didn't exist. The docs were only at `/swagger-ui/`, `/redoc/` and `/schema/`. | ✅ Aliases added: `/api/docs/`, `/api/redoc/`, `/api/schema/`. The old paths still work. |
| 9 | 🟡 | `settings/base.py` + `apps/users/services.py` | `SITE_URL` had no default, so the trainer credentials e-mail showed **"Вход: None"**. | ✅ Falls back to `${LMS_FRONTEND_URL}/login`. |
| 10 | 🟠 | Railway env (`LMS_FRONTEND_URL`, `PUBLIC_WEBSITE_URL`, `SITE_URL`, `ATTENDANCE_QR_BASE_URL`, `FEEDBACK_PUBLIC_BASE_URL`) | The code defaults point at `okurmen-kids-drab.vercel.app` and `okurmen-public-website.vercel.app`. | ⚠️ **Defaults kept on purpose** so nothing points at a domain that isn't live yet. Set the env vars in §5 when cutting over. |
| 11 | 🟡 | `*.env.example`, READMEs | Examples used `okurmenkids.up.railway.app`, `okurmenkids.kg` and `<your-backend>`. | ✅ `.env.example` files updated. |
| 12 | 🟡 | `frontend/src/features/siteCms/SettingsPage.tsx` | SEO preview fallback was `https://okurmenkids.kg`. | ✅ Now `https://okurmenkids.com`. It is only shown when the API returns no `public_site_url`. |
| 13 | 🟠 | `okurmen-public-website/vercel.json` | No www→apex rule. | ✅ Done in the **Vercel Domains UI only** (§6.1). A `vercel.json` host redirect added here first was **removed**: together with the dashboard's default apex→www 307 it caused a redirect loop (see `PUBLIC_WEBSITE_REDIRECT_FIX.md`). |
| 14 | 🟡 | `frontend/src/features/portal/config.ts`, `okurmen-public-website/src/app/config/env.ts` | Launcher defaults hard-code `training-portal-theta.vercel.app`, `okurmen-kids-drab.vercel.app/monthly-performance` and `okurmen-kids-drab.vercel.app/careers`. | ⚠️ Left as defaults because the tests assert them and the targets still exist. Override with `VITE_PORTAL_*_URL` / `VITE_CAREERS_URL` (§6). |
| 15 | 🔴? | `backend/Dockerfile` | `CMD ["python", "manage.py", "runserver", …]`. If the Railway web service has **no custom Start Command**, production runs Django's dev server, with no `collectstatic` and no migrations. | ⚠️ Can't see the Railway dashboard. Check that the Start Command is `sh deployment/server-entrypoint.sh` (§10). |
| 16 | 🟡 | Auth | Logout is client-side only (tokens removed from `localStorage`). `rest_framework_simplejwt.token_blacklist` isn't installed and `BLACKLIST_AFTER_ROTATION=False`, so a refresh token stays valid for up to 7 days after logout. | ⚠️ Not changed: it would need a migration (the brief says no schema changes). Documented as a risk. |
| 17 | 🟡 | Tests | 3 existing failures in `apps.users.tests` (`is_verified` default). They also fail on the untouched code and are unrelated to this work. | ⚠️ Not touched. |

What the audit found to be **correct already, and left unchanged**:

* **Auth** is JWT in the `Authorization: Bearer` header (simplejwt). Access tokens
  last 30 min, refresh tokens 7 days and rotate. Tokens live in `localStorage`
  (`frontend/src/lib/tokenStorage.ts`). On a 401 the axios interceptor makes one
  shared refresh call to `/auth/refresh/`, and if that fails it clears tokens and
  forces logout. `authorization` is in `CORS_ALLOW_HEADERS`. No cookies cross
  origins, so `credentials: include` isn't needed anywhere.
* **Django security headers:** `SECURE_PROXY_SSL_HEADER` is set for Railway's TLS
  edge. HSTS is 1 year with `includeSubDomains` and `preload`; sent from
  `api.okurmenkids.com`, it covers only that host and its subdomains. `nosniff`,
  `X_FRAME_OPTIONS=DENY` (no frontend frames a backend page), and `Secure` +
  `Lax` session and CSRF cookies are all set. The cookies are host-only (no
  `SESSION_COOKIE_DOMAIN`), which is correct.
* **DRF trailing slashes:** every client calls paths with a trailing slash
  (`/auth/login/`, `/public/site/home/`…), and `APPEND_SLASH` is on by default.
* **Error handling:** the LMS has `lib/apiError.ts` and a 401 refresh interceptor.
  The public website's `toApiError` handles network, 404, 400, 409, 429 and 5xx.
  The training portal has `ApiError` with network and config states.
* **SPA fallback:** all three `vercel.json` files rewrite `/(.*)` to `/index.html`,
  and Vercel serves real files before applying rewrites.
* **Media:** serializers build absolute URLs from the request host, so they become
  `https://api.okurmenkids.com/media/…` automatically. The LMS `resolveMediaUrl`
  and the website's `VITE_MEDIA_URL` resolve relative paths against the API.
* **Telegram:** outbound only (`sendMessage` in `apps/operations/services/notifications.py`).
  There is **no inbound Telegram webhook, OAuth callback or WebSocket** in the
  codebase, so none needs re-registering.
* **Celery:** the broker is `CELERY_BROKER_URL` (Railway Redis, private network).
  Without it, tasks run eagerly in the web process. The Railway cron
  (`deployment/railway-cron.json`, `manage.py run_scheduled_tasks` every 30 min)
  doesn't depend on any domain.

---

## 3. Files changed

| File | Change |
|---|---|
| `backend/config/settings/production.py` | Multi-host `ALLOWED_HOSTS`; exact `CSRF_TRUSTED_ORIGINS`; `SECURE_SSL_REDIRECT` env toggle + health-check exemption |
| `backend/config/settings/cors.py` | `FRONTEND_ORIGINS`, `CORS_EXTRA_ORIGINS`, de-duplicated `CORS_ALLOWED_ORIGINS`; localhost only outside production; `CORS_ALLOW_CREDENTIALS` off by default |
| `backend/config/settings/base.py` | `SITE_URL` fallback to the LMS login page |
| `backend/config/urls.py` | `/api/docs/`, `/api/redoc/`, `/api/schema/` aliases |
| `backend/deployment/server-entrypoint.sh` | No built-in `admin/admin` superuser; env-driven bootstrap |
| `okurmen-public-website/vercel.json` | (www redirect added, later removed; redirect lives in Vercel Domains) |
| `frontend/src/features/siteCms/SettingsPage.tsx` | `.kg` → `.com` display fallback |
| `.env.example`, `frontend/.env.example`, `okurmen-public-website/.env.example`, `training-portal/.env.example` | New domains in examples |
| `PRODUCTION_DOMAIN_MIGRATION.md` | This document |

### 3.1 Key code (excerpts)

`backend/config/settings/production.py`

```python
ALLOWED_HOSTS = list(dict.fromkeys(
    h.strip().lower()
    for h in [
        *env.list("ALLOWED_HOSTS", default=["api.okurmenkids.com"]),
        env.str("ALLOWED_HOST", default=""),          # legacy single host
        env.str("RAILWAY_PUBLIC_DOMAIN", default=""), # injected by Railway
        "healthcheck.railway.app",                    # Railway health check Host
    ]
    if h and h.strip()
))

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = env.bool("SECURE_SSL_REDIRECT", default=True)
SECURE_REDIRECT_EXEMPT = [r"^api/v1/$"]   # GET /api/v1/ → {"status": "ok"}

CSRF_TRUSTED_ORIGINS = list(dict.fromkeys(
    o.strip().rstrip("/")
    for o in [
        *env.list("CSRF_TRUSTED_ORIGINS", default=[]),
        *(f"https://{h}" for h in ALLOWED_HOSTS if h != "healthcheck.railway.app"),
        *FRONTEND_ORIGINS,
    ]
    if o and o.strip()
))
```

`backend/config/settings/cors.py`

```python
FRONTEND_ORIGINS = _origins(
    "FRONTEND_ORIGINS",
    "https://okurmenkids.com,https://www.okurmenkids.com,"
    "https://lms.okurmenkids.com,https://admin.okurmenkids.com",
)
CORS_ALLOWED_ORIGINS = list(dict.fromkeys([*FRONTEND_ORIGINS, <legacy + per-site env lists>, *_origins("CORS_EXTRA_ORIGINS")]))
CORS_ALLOW_CREDENTIALS = os.getenv("CORS_ALLOW_CREDENTIALS", "False") in truthy
CORS_ALLOWED_ORIGIN_REGEXES = [localhost, 127.0.0.1] if not production or CORS_ALLOW_LOCALHOST else []
```

`okurmen-public-website/vercel.json`

```json
"redirects": [
  {
    "source": "/:path*",
    "has": [{ "type": "host", "value": "www.okurmenkids.com" }],
    "destination": "https://okurmenkids.com/:path*",
    "permanent": true
  }
]
```

The full diff is `git diff main...claude/youthful-euler-zzckq7`.

### 3.2 Local verification

Run with `DJANGO_ENV=production`, `ALLOWED_HOST=okurmenkids.up.railway.app` and
`RAILWAY_PUBLIC_DOMAIN=okurmenkids.up.railway.app`, using the Django test client
(no database touched):

```
ALLOWED_HOSTS = ['api.okurmenkids.com', 'okurmenkids.up.railway.app', 'healthcheck.railway.app']
CSRF_TRUSTED_ORIGINS = ['https://api.okurmenkids.com', 'https://okurmenkids.up.railway.app',
  'https://okurmenkids.com', 'https://www.okurmenkids.com', 'https://lms.okurmenkids.com', 'https://admin.okurmenkids.com']
CORS_ALLOWED_ORIGINS = ['https://okurmenkids.com', 'https://www.okurmenkids.com', 'https://lms.okurmenkids.com',
  'https://admin.okurmenkids.com', 'https://okurmen-kids-drab.vercel.app', 'https://training-portal-theta.vercel.app',
  'https://okurmen-public-website.vercel.app']
CORS_ALLOWED_ORIGIN_REGEXES = []      CORS_ALLOW_CREDENTIALS = False

GET /api/v1/   Host healthcheck.railway.app, plain HTTP   → 200 (no redirect)
GET /api/v1/   Host api.okurmenkids.com, https            → 200
GET /api/docs/ Host api.okurmenkids.com, plain HTTP       → 301 https://api.okurmenkids.com/api/docs/
GET /api/docs/, /swagger-ui/, /api/schema/ (https)        → 200
GET /api/v1/   Host okurmenkids.up.railway.app            → 200 (old host still works)
GET /api/v1/   Host evil.example                          → 400
OPTIONS /api/v1/auth/login/ preflight from lms / admin / apex / www / old vercel site → 200 + Access-Control-Allow-Origin
OPTIONS preflight from http://localhost:5173, https://evil.up.railway.app            → no ACAO (refused)
GET /admin/login/ (https)                                 → 200
```

Backend tests (`DJANGO_ENV=testing`) for `apps.website`, `apps.users`,
`apps.feedback`, `apps.training`, `apps.staff_attendance` and
`apps.accounting.tests.test_isolation`: 445 run, the same 3 existing failures
with and without these changes (#17), no new failures.

---

## 4. Required Django environment variables

All of these are set in **Railway → backend web service → Variables**. Secrets
(`SECRET_KEY`, DB, email, VAPID, Telegram) stay only in Railway and never go in
the repo or in any `VITE_*` variable.

| Variable | Value | Notes |
|---|---|---|
| `DJANGO_ENV` | `production` | Selects `settings/production.py` |
| `SECRET_KEY` | *(existing secret)* | Don't rotate during the migration: it also signs JWTs, so rotating it logs everyone out |
| `ALLOWED_HOSTS` | `api.okurmenkids.com,okurmenkids.up.railway.app` | Replace the second value with the real Railway host if different. The legacy `ALLOWED_HOST` can stay or be deleted |
| `FRONTEND_ORIGINS` | `https://okurmenkids.com,https://www.okurmenkids.com,https://lms.okurmenkids.com,https://admin.okurmenkids.com` | This is the default, so it can be left unset |
| `PUBLIC_WEBSITE_ORIGINS` | `https://okurmen-public-website.vercel.app` | The default. Keeps the old Vercel URL working |
| `TRAINING_PORTAL_ORIGINS` | `https://training-portal-theta.vercel.app` | The default |
| `CORS_EXTRA_ORIGINS` | *(empty)* | Any other exact origin |
| `CSRF_TRUSTED_ORIGINS` | *(empty)* | Extra exact origins only; the hosts and frontends above are added automatically |
| `CORS_ALLOW_CREDENTIALS` | *(unset → False)* | Set `True` only if a frontend starts using cookies |
| `CORS_ALLOW_LOCALHOST` | *(unset → False)* | Temporary debugging only |
| `LMS_FRONTEND_URL` | `https://lms.okurmenkids.com` | Admin login hint, exam links, staff-attendance QR base |
| `SITE_URL` | `https://lms.okurmenkids.com/login` | Credentials e-mail. Unset falls back to `LMS_FRONTEND_URL/login` |
| `PUBLIC_WEBSITE_URL` | `https://okurmenkids.com` | CMS preview links, SEO settings |
| `ATTENDANCE_QR_BASE_URL` | *(unset → LMS_FRONTEND_URL)* | ⚠️ QR codes **already printed** use the old LMS URL. Keep `okurmen-kids-drab.vercel.app` live until they are reprinted |
| `FEEDBACK_PUBLIC_BASE_URL` | `https://api.okurmenkids.com` *(optional)* | Survey links are served by Django (`/feedback/s/…`). Empty means "the host the admin is using" |
| `SECURE_SSL_REDIRECT` | *(unset → True)* | |
| `MEDIA_ROOT` | `/app/media` | Railway Volume mount path |
| `SERVE_MEDIA` | `True` | |
| `RAILWAY_RUN_UID` | `0` | Needed so the entrypoint can chown the Volume (see the entrypoint) |
| `PGHOST`, `PGPORT`, `PGUSER`, `PGPASSWORD`, `PGDATABASE` | `${{Postgres.PGHOST}}` etc. | Railway reference variables, private network |
| `CELERY_BROKER_URL` | `${{Redis.REDIS_URL}}` | Only if a Redis service and a Celery worker exist. Empty runs tasks eagerly |
| `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD` | *(existing secrets)* | Required by `production.py` |
| `DJANGO_SUPERUSER_USERNAME`, `DJANGO_SUPERUSER_EMAIL`, `DJANGO_SUPERUSER_PASSWORD` | *(only for a fresh DB)* | Delete `DJANGO_SUPERUSER_PASSWORD` after the first deploy |
| `PUSH_VAPID_*`, `OPERATIONS_TELEGRAM_BOT_TOKEN`, … | *(unchanged)* | Not domain-dependent |

Railway's `RAILWAY_PUBLIC_DOMAIN` is injected automatically and added to
`ALLOWED_HOSTS` and `CSRF_TRUSTED_ORIGINS`.

## 5. Railway (backend)

1. **Web service → Settings → Networking → Custom Domain → `api.okurmenkids.com`.**
   Railway shows a **CNAME target** (something like `xxxx.up.railway.app`). Copy it
   exactly into DNS (§7). Wait until Railway shows the domain as verified and the
   certificate as issued.
2. **Keep the `*.up.railway.app` public domain** during the transition. The old
   frontend builds and stored absolute media URLs still point at it.
3. **Start Command** (Settings → Deploy) must be `sh deployment/server-entrypoint.sh`,
   not the Dockerfile's `runserver` (#15).
4. **Health check path** (Settings → Deploy → Healthcheck Path): `/api/v1/`. It is
   allowed host-wise and exempt from the HTTPS redirect.
5. **Variables:** set §4, then redeploy.
6. **Volume** mounted at `/app/media` (uploads), with `RAILWAY_RUN_UID=0`.
7. **Postgres and Redis:** reference them through the private network
   (`${{Postgres.*}}`, `${{Redis.REDIS_URL}}`). **Don't** enable public
   networking (TCP proxy) on Postgres or Redis.
8. **Cron service** (`deployment/railway-cron.json`, `run_scheduled_tasks` every
   30 min): needs the same DB and env vars, and no domain changes.
9. **Celery:** there is no worker or beat service definition in the repo. If one
   exists in Railway, its start commands are `celery -A config worker -l info` and
   `celery -A config beat -l info`, with the same variables and no public domain.

## 6. Vercel (three or four separate projects, not merged)

### 6.1 Public website: project `okurmen-public-website`, Root Directory `okurmen-public-website`

* **Domains:** add `okurmenkids.com` (primary), then `www.okurmenkids.com` with
  **"Redirect to okurmenkids.com"** and status **308 Permanent Redirect**.
  `okurmenkids.com` itself must be **connected to Production with no redirect**.
  Don't add a www rule to `vercel.json`: two redirect sources can point at each
  other and loop. Keep `okurmen-public-website.vercel.app`.
* **Environment variables (Production):**

  | Name | Value |
  |---|---|
  | `VITE_API_URL` | `https://api.okurmenkids.com` *(no `/api/v1`, no trailing slash)* |
  | `VITE_SITE_URL` | `https://okurmenkids.com` |
  | `VITE_MEDIA_URL` | *(empty, uses `VITE_API_URL`)* |
  | `VITE_CAREERS_URL` | `https://lms.okurmenkids.com/careers` |
  | `VITE_USE_MOCKS` | `false` *(or unset)* |

  `middleware.ts` (social previews) and `scripts/generate-sitemap.mjs` read the same
  `VITE_API_URL` and `VITE_SITE_URL` at build and edge time. **Redeploy after
  changing them**, because Vite inlines them at build time.

### 6.2 LMS: Root Directory `frontend`, domain `lms.okurmenkids.com`

| Name | Value |
|---|---|
| `VITE_API_BASE_URL` | `https://api.okurmenkids.com/api/v1` ⚠️ *this app's variable **includes** `/api/v1`* |
| `VITE_APP_MODE` | *(unset → LMS)* |
| `VITE_PORTAL_TRAINING_URL` | current training portal URL *(default `https://training-portal-theta.vercel.app/`)* |
| `VITE_PORTAL_PERFORMANCE_URL` | `https://lms.okurmenkids.com/monthly-performance` *(default is the old Vercel URL)* |
| `VITE_PORTAL_WEBSITE_URL` | `https://okurmenkids.com` |

### 6.3 Admin dashboard: a second project, Root Directory `frontend`, domain `admin.okurmenkids.com`

Same build and the same variables as 6.2. `vercel.json` (SPA rewrite, PWA and
cache headers) applies unchanged. Optional: set the `VITE_PORTAL_*` URLs to the
LMS domain so launcher links don't jump between origins.

### 6.4 Legacy domains

Keep `okurmen-kids-drab.vercel.app` deployed for printed QR codes, installed
PWAs and bookmarks. Its build must also use the new `VITE_API_BASE_URL`, or keep
the Railway host alive.

## 7. DNS records still needed

Create these **at the DNS provider for `okurmenkids.com`**. Values come **only**
from the dashboards, so none are guessed here.

| Type | Host | Value (copy from) | Proxy/CDN |
|---|---|---|---|
| A | `@` | the IP Vercel shows for `okurmenkids.com` (Project → Settings → Domains) | off / DNS only |
| CNAME | `www` | the CNAME Vercel shows for `www.okurmenkids.com` | off |
| CNAME | `lms` | the CNAME Vercel shows for `lms.okurmenkids.com` (LMS project) | off |
| CNAME | `admin` | the CNAME Vercel shows for `admin.okurmenkids.com` (admin project) | off |
| CNAME | `api` | the CNAME target Railway shows for `api.okurmenkids.com` | off |
| TXT | as shown | only if Vercel or Railway asks for ownership verification (`_vercel`, `_railway`…) | — |

Rules:

* **Don't touch MX, SPF (`TXT v=spf1`), DKIM, DMARC** or any other e-mail record.
* Delete any **URL forwarding or parking** rule for `@` or `www` at the registrar.
  It overrides the A or CNAME records and breaks SSL issuance.
* No wildcard `*` record should point elsewhere. If one exists, the explicit
  records above win, but remove it unless it is intentional.
* If the DNS host is Cloudflare, keep these records **DNS-only (grey cloud)**
  until Vercel and Railway have issued certificates. Proxying breaks their ACME
  validation and Railway's domain check.
* Use a TTL of 300 s during the cutover.

## 8. Migration order

1. Merge this branch and deploy the backend. Nothing breaks: the old hosts and
   origins are still allowed, and `ALLOWED_HOSTS` now also accepts `api.okurmenkids.com`.
2. Railway: add the custom domain `api.okurmenkids.com`, then add the `api` CNAME,
   then wait for "verified + certificate".
3. Check `https://api.okurmenkids.com/api/v1/` returns `{"status":"ok"}`, and that `/api/docs/` and `/admin/` load.
4. Vercel: add the domains to each project and create the DNS records, then wait
   for "Valid Configuration" and the certificates.
5. Set the Vercel env vars (§6) and **redeploy** each project.
6. Set the Railway env vars for frontend URLs (`LMS_FRONTEND_URL`, `SITE_URL`,
   `PUBLIC_WEBSITE_URL`), then redeploy.
7. Run §9.
8. Afterwards, when traffic on the old domains is gone: drop the legacy origins
   from `cors.py`, remove the Railway host from `ALLOWED_HOSTS`, and reprint the
   attendance QR codes.

**Rollback:** every change is additive. Revert the Vercel env vars to the Railway
URL and redeploy. The backend keeps answering on the old Railway host.

Users have to **sign in again** on each new domain, because JWTs are stored in
`localStorage` per origin. Installed PWAs keep opening the old origin.

## 9. Production verification checklist

Run each item **after** deploying. Results so far: **none executed**, because the
sandbox couldn't reach the hosts.

```bash
API=https://api.okurmenkids.com
```

| # | Test | Command / action | Expected | Result |
|---|---|---|---|---|
| 1 | Website over HTTPS | `curl -sI https://okurmenkids.com/` | `200`, valid cert | NOT VERIFIED |
| 2 | WWW redirect | `curl -sI https://www.okurmenkids.com/courses` | `308`, `location: https://okurmenkids.com/courses` | NOT VERIFIED |
| 3 | LMS | `curl -sI https://lms.okurmenkids.com/app/dashboard` | `200` (SPA rewrite) | NOT VERIFIED |
| 4 | Admin | `curl -sI https://admin.okurmenkids.com/app/dashboard` | `200` | NOT VERIFIED |
| 5 | Health | `curl -s $API/api/v1/` | `{"status": "ok"}` | NOT VERIFIED |
| 6 | API docs | open `$API/api/docs/` (and `$API/swagger-ui/`) | Swagger UI | NOT VERIFIED |
| 7 | CORS preflight | `curl -si -X OPTIONS $API/api/v1/auth/login/ -H 'Origin: https://lms.okurmenkids.com' -H 'Access-Control-Request-Method: POST' -H 'Access-Control-Request-Headers: authorization,content-type'` | `200`, `access-control-allow-origin: https://lms.okurmenkids.com`, `authorization` in allow-headers. Repeat with `https://admin…`, `https://okurmenkids.com`. `Origin: https://evil.example` gets no ACAO | NOT VERIFIED |
| 8 | GET | `curl -s "$API/api/v1/public/site/home/?lang=ru" -H 'Origin: https://okurmenkids.com' -i` | `200` + ACAO | NOT VERIFIED |
| 9 | POST (public) | Website → Contacts → submit the enrollment form (`POST /api/v1/public/site/leads/`) | 201, lead visible in LMS → Маркетинг → Сайт → Заявки | NOT VERIFIED |
| 10 | JWT login | LMS login, which calls `POST /api/v1/auth/login/` | 200 with `access` and `refresh`; Network tab shows only `api.okurmenkids.com` | NOT VERIFIED |
| 11 | Token refresh | In DevTools, set `localStorage['okurmenkids.access_token']='x'` and reload a page | one `POST /api/v1/auth/refresh/` → 200, the page loads | NOT VERIFIED |
| 12 | Logout | Click «Выйти» | tokens removed from `localStorage`, redirect to `/portal`. Client-side only (#16) | NOT VERIFIED |
| 13 | File upload | LMS → a project → add an image (`POST /api/v1/projects/{id}/images/`), or a trainer photo | 201, file in the Railway Volume | NOT VERIFIED |
| 14 | Images | open the image URL from the response | `https://api.okurmenkids.com/media/…` → 200 | NOT VERIFIED |
| 15 | Admin auth | admin role login on `admin.okurmenkids.com`; Django admin login on `$API/admin/` (CSRF same-origin) | dashboard / Jazzmin loads, no CSRF 403 | NOT VERIFIED |
| 16 | Student auth | Training portal: start a test (`/api/v1/training/…`, `X-Attempt-Token`); exam pages `$API/exam/` | works | NOT VERIFIED |
| 17 | Telegram | trigger an operations notification (requires `OPERATIONS_NOTIFICATION_BACKEND=…telegram_backend`) | message delivered (outbound only, no webhook) | NOT VERIFIED |
| 18 | Celery / cron | Railway logs of the cron service (`run_scheduled_tasks`) and of the worker, if one exists | runs every 30 min without errors | NOT VERIFIED |
| 19 | Mixed content | DevTools console on every site | no `http://` or `localhost` requests | NOT VERIFIED |
| 20 | Social preview | `curl -s -A TelegramBot https://okurmenkids.com/news/<slug>` | `og:url` and `og:image` on the new domains | NOT VERIFIED |
| 21 | Sitemap | `curl -s https://okurmenkids.com/sitemap.xml \| head` | `<loc>https://okurmenkids.com/…` | NOT VERIFIED |

## 10. Remaining manual tasks

- [ ] **Security:** sign in to `/admin/` as `admin` with password `admin`. If it works, change that password immediately; it was created by the old entrypoint (#1).
- [ ] Railway: check the web service Start Command is `sh deployment/server-entrypoint.sh` (#15) and the health check path is `/api/v1/`.
- [ ] Railway: add the custom domain `api.okurmenkids.com` and set the variables in §4.
- [ ] Vercel: create the admin project (Root Directory `frontend`), attach the domains, set the env vars, redeploy all projects.
- [ ] DNS: create the records in §7 with the dashboard values; remove forwarding and parking rules.
- [ ] Run checklist §9 and record the results.
- [ ] Decide whether a server-side logout or blacklist is wanted (#16). It needs `rest_framework_simplejwt.token_blacklist` and its migrations.
- [ ] Later: remove the legacy `*.vercel.app` and Railway origins and hosts, and reprint the attendance QR codes.
- [ ] Optional: HSTS preload for the apex (Vercel) only after every subdomain is confirmed HTTPS-only.
