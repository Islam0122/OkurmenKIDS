# Okurmen Kids — Production Audit

**Date:** 2026-11-12 · **Type:** audit only. No code, DNS, environment variables or deployments were changed.
**Method:** read the code in `Islam0122/OkurmenKIDS` (`master` @ `0f4adb7`), ran live read-only checks from a cloud sandbox (DNS over HTTPS, `curl`, headless Chromium), checked GitHub commit statuses, and ran `npm audit` and `pip-audit`.
**Not available:** the Vercel dashboard, Railway dashboard, Porkbun DNS panel and Google Search Console. Anything that needs them is marked **NOT VERIFIED**.
**Not attempted, on purpose:** logins with real or default credentials, form submissions, uploads, writes of any kind.

Statuses: **PASS** verified working · **WARNING** works but carries a risk · **FAIL** confirmed problem · **NOT VERIFIED** not enough access or evidence.

---

## 1. Executive summary

The backend, the LMS and the public website are up on their new domains with
valid TLS, and all three frontends call `https://api.okurmenkids.com`.
**Production isn't fully healthy.** Two problems are confirmed and are
visible to users or to Google right now:

1. **FAIL · CRITICAL: the Training Portal is broken.** On
   `https://training.okurmenkids.com` every API call is blocked by CORS (seen in
   Chromium: *"No 'Access-Control-Allow-Origin' header"*). Tests, videos,
   links, the leaderboard and portal settings don't load. The backend doesn't
   allow the origin `https://training.okurmenkids.com`.
2. **FAIL · HIGH: the canonical domain is inverted.** `https://okurmenkids.com/` returns
   **307 → `https://www.okurmenkids.com/`** (set in the Vercel Domains settings), while
   `sitemap.xml` and `robots.txt` list `https://okurmenkids.com/...`. The pages declare
   `<link rel="canonical" href="https://www.okurmenkids.com/...">`. So Google gets
   sitemap URLs that **temporarily redirect** to pages whose canonical is a third
   variant.

Other serious risks: the backend falls back to the publicly known
`SECRET_KEY` default if the env var is ever lost; **93 known vulnerabilities**
across Django, DRF, PyJWT and Pillow; **no verified database or media backups**;
no CI. The repository is **public**.

---

## 2. Production architecture (verified live)

| Service | URL | Hosting (evidence) | Live status |
|---|---|---|---|
| Public website | https://okurmenkids.com | Vercel project `okurmen-public-website` | **WARNING**: served on **www**; the root domain 307-redirects to www |
| LMS | https://lms.okurmenkids.com | Vercel project `okurmen-kids` | **PASS**: 200 |
| Training portal | https://training.okurmenkids.com | Vercel project `training-portal` | **FAIL**: page shell 200, every API call blocked by CORS |
| Backend API | https://api.okurmenkids.com | Railway (`server: railway-hikari`, CNAME `4e9r72ip.up.railway.app`) | **PASS**: `GET /api/v1/` → `{"status": "ok"}` |
| Django admin | https://api.okurmenkids.com/admin/ | Railway | **PASS**: `/admin/` → 302 → `/admin/login/` 200, static CSS 200 |

Vercel project names are taken from the GitHub commit statuses on PR #318 (`Vercel – okurmen-public-website`, `Vercel – okurmen-kids`, `Vercel – training-portal`). All three reported "Deployment has completed".

---

## 3. Repository inventory

There's one monorepo, **`Islam0122/OkurmenKIDS`** (visibility **public**), with four apps. No shared library package was found; each app has its own `package.json`.

| App | Dir | Framework (verified in code) | Entry | Build | Deploy config | API variable |
|---|---|---|---|---|---|---|
| Public website | `okurmen-public-website/` | React 19 + Vite 6 SPA, TanStack Query, axios, Vercel Routing Middleware (`middleware.ts`) | `src/main.tsx` | `tsc -b && vite build && node scripts/generate-sitemap.mjs` → `dist` | `vercel.json` (framework vite, `npm ci`, SPA rewrite, headers) | `VITE_API_URL` (origin only, no `/api/v1`) |
| LMS | `frontend/` | React 19 + Vite 6 SPA, axios, PWA service worker (`pwa/sw.js`), `VITE_APP_MODE` multi-site | `src/main.tsx` | `tsc -b && vite build` → `dist` | `vercel.json` (SPA rewrite, SW/manifest headers) | `VITE_API_BASE_URL` (**includes `/api/v1`**) |
| Training portal | `training-portal/` | React 19 + Vite 6 SPA, plain `fetch` | `src/main.tsx` | `tsc -b && vite build` → `dist` | `vercel.json` (SPA rewrite) | `VITE_API_URL` (origin only) |
| Backend | `backend/` | Django 6.1, DRF 3.18, simplejwt, Celery 5.5, gunicorn, WhiteNoise | `config/wsgi.py` | `Dockerfile` (python:3.12-slim + Playwright Chromium) | `deployment/server-entrypoint.sh`, `deployment/railway-cron.json` | — |

* **Production branch:** `master` (the GitHub default branch). The live
  public-website HTML contains the `favicon.ico` link merged in PR #318, so
  `master` is what's deployed. **PASS**. Each project's Production Branch setting
  in Vercel: **NOT VERIFIED**.
* Other repos on the account (`OkurmenKidsTEST`, `cover-studio-okurmenkids`,
  `Okurmen_Mentor`, `Okurmen_studio`, `okurmenpro/okurmen-web`): no link to these
  production domains was found. They weren't audited.
* **No CI** (`.github/` doesn't exist). Tests run only on developers' machines.
  **WARNING**.
* The repo's own docs (`PRODUCTION_DOMAIN_MIGRATION.md`) still describe an
  `admin.okurmenkids.com` project and don't mention `training.okurmenkids.com`.
  They're **out of date** against this architecture.

---

## 4. Domain & DNS health

DNS host: **Porkbun** (NS `*.ns.porkbun.com`). Records were read with public DNS (dns.google); the registrar panel wasn't seen.

| Host | Record (live) | TLS (live) | HTTP (live) | Status |
|---|---|---|---|---|
| `okurmenkids.com` | A `76.76.21.21` (Vercel) | Let's Encrypt, valid to 2027-02-10, SAN matches | **307 → https://www.okurmenkids.com/** | **FAIL** (wrong direction, temporary code) |
| `www.okurmenkids.com` | CNAME `d1826565557f4d92.vercel-dns-017.com` | LE, valid to 2027-02-10 | 200, `/logo.png` 200, no loop | **WARNING**: works, but it's the canonical by accident |
| `lms.okurmenkids.com` | CNAME `e2af74c212eb6eb5.vercel-dns-017.com` | LE, valid to 2027-02-10 | 200 | **PASS** |
| `training.okurmenkids.com` | CNAME `b31c3fee28062ad0.vercel-dns-017.com` | LE, valid to 2027-02-10 | 200 (shell) | **PASS** (DNS/TLS) |
| `api.okurmenkids.com` | CNAME `4e9r72ip.up.railway.app` | LE, valid to 2027-02-10 | `/api/v1/` 200, `/` 404 (no route) | **PASS** |

* **Redirect loop** (from the previous incident): **gone.** www returns 200 with
  no redirects for HTML, assets, manifest and logo. **PASS**
* **Mixed content:** none on 12 pages loaded in Chromium. **PASS**
* **HTTP→HTTPS:** **NOT VERIFIED**, because the sandbox proxy only carries
  HTTPS. Vercel and Railway redirect HTTP by default, and Django has
  `SECURE_SSL_REDIRECT=True`. HSTS is sent on all hosts (Vercel 2 years, API 1 year
  with `includeSubDomains; preload`). **PASS** (HSTS)
* **Wildcard DNS:** none (a probe name returns NXDOMAIN). **PASS**
* **Email:** MX `fwd1/fwd2.porkbun.com` (forwarding), SPF `v=spf1 include:_spf.porkbun.com ~all` present. **No DMARC** record (`_dmarc` is NXDOMAIN). **WARNING · LOW**
* **CAA:** none, **DNSSEC:** not validated (AD=false). **WARNING · LOW**
* **Google verification:** TXT `google-site-verification=…` exists on the apex, so a Search Console *Domain property* was probably set up. Its state: **NOT VERIFIED**.
* **Legacy hosts still live:** `okurmen-kids-drab.vercel.app`, `okurmen-public-website.vercel.app` and `training-portal-theta.vercel.app` all return 200, and `okurmenkids.up.railway.app/api/v1/` returns 200. They serve duplicate content without redirecting to the new domains. **WARNING** (SEO duplicates, and a larger surface).

---

## 5. Vercel health

| Check | Public website | LMS | Training portal |
|---|---|---|---|
| Latest deployment (GitHub status, PR #318, 2026-11-12 05:51–05:52) | success | success | success |
| Root directory / preset / output | `vercel.json`: vite, `dist`. Root dir **NOT VERIFIED** | same | same |
| API URL baked into the production bundle (live JS) | `https://api.okurmenkids.com` **PASS** | `https://api.okurmenkids.com/api/v1` **PASS** | `https://api.okurmenkids.com` **PASS** |
| `VITE_SITE_URL` | **FAIL**: not set. The live canonical is `window.location.origin` (www), and the live sitemap has only the 30 static URLs although the API lists 20 content pages (3 achievements, 6 team, 5 news, 6 projects), so 60 URLs are missing | n/a | n/a |
| Other env leftovers in the bundle | `VITE_CAREERS_URL` unset → "join the team" links to `okurmen-kids-drab.vercel.app/careers` | the portal launcher links "Training" to `training-portal-theta.vercel.app` and "Monthly performance" to `okurmen-kids-drab.vercel.app/monthly-performance` | — |
| Custom domain config | **FAIL**: apex set to redirect to www (307) | PASS | PASS |
| SPA refresh on nested routes (Chromium, reload) | `/en/team`, `/events`, `/courses`, `/contacts` **PASS** | `/login`, `/portal`, `/schedule/day` **PASS** | `/leaderboard` renders the shell; data fails (CORS) |
| Console errors | none | none | **CORS errors on every API call** |
| Deployment history, rollback ("Instant Rollback"), runtime logs, build logs, env var values | **NOT VERIFIED** (dashboard) | NOT VERIFIED | NOT VERIFIED |

**Independent deploys:** **PASS**. These are three separate Vercel projects with
separate statuses on the same commit. Note that every push to `master` rebuilds
all three, even when only one app changed (there are no "Ignored Build Step" or
path filters in the repo). **WARNING · LOW**

---

## 6. Railway health

| Check | Evidence | Status |
|---|---|---|
| Custom domain + SSL | `api.okurmenkids.com` → CNAME `4e9r72ip.up.railway.app`, valid LE cert | **PASS** |
| Service up | `/api/v1/` 200 JSON; `/admin/login/` 200; `/static/admin/css/base.css` 200 (WhiteNoise / collectstatic ran) | **PASS** |
| Latest backend code deployed | `/api/docs/` and `/api/schema/` (added in PR #317) answer 200; localhost and unknown origins are refused; no `Access-Control-Allow-Credentials` header | **PASS** |
| Start command (gunicorn vs `runserver`) | The Dockerfile `CMD` is `manage.py runserver`. `collectstatic` evidence suggests the entrypoint runs, but the `server` header is replaced by Railway's edge | **NOT VERIFIED**: check Railway → Deploy → Start Command = `sh deployment/server-entrypoint.sh` |
| Health check config | `/api/v1/` exists and is exempt from the SSL redirect in code | Railway setting **NOT VERIFIED** |
| PostgreSQL | API returns DB-backed content (public site home, sitemap, schedule), so the DB is reachable | **PASS**; plan, region, public TCP proxy **NOT VERIFIED** |
| Redis | No Redis URL can be seen; `CELERY_BROKER_URL` empty means tasks run eagerly | **NOT VERIFIED** |
| Celery worker / beat | No worker or beat service defined in the repo. The cron service `run_scheduled_tasks` every 30 min is in `railway-cron.json` | **NOT VERIFIED** (whether these services exist and their last runs) |
| Media | Images under `/media/projects/...` and `/media/site/achievement/...` return 200 from `api.okurmenkids.com` | **PASS**; volume mount and size **NOT VERIFIED** |
| Logs | `LOGGING` sends WARNING+ to stderr (code) | code **PASS**; content **NOT VERIFIED** |
| Replicas, region, resource limits, usage and billing alerts | — | **NOT VERIFIED** |

---

## 7. Django configuration (code + live behaviour)

| Setting | Finding | Status |
|---|---|---|
| `DEBUG` | `False` in `production.py`; a live 404 is Django's plain "Not Found" page, not the debug page | **PASS** |
| `ALLOWED_HOSTS` | `api.okurmenkids.com` + `ALLOWED_HOST` + `RAILWAY_PUBLIC_DOMAIN` + `healthcheck.railway.app`; both API hostnames answer live | **PASS** |
| `CORS_ALLOWED_ORIGINS` | Live preflight on `POST /api/v1/auth/login/`: **allowed:** `okurmenkids.com`, `www.okurmenkids.com`, `lms.okurmenkids.com`, `training-portal-theta.vercel.app`, `okurmen-kids-drab.vercel.app`. **Refused:** **`training.okurmenkids.com`** ❌, `localhost`, `evil.example` | **FAIL** (training) |
| Root cause of the training CORS failure | `cors.py`: the default `FRONTEND_ORIGINS` contains apex, www, lms and `admin.okurmenkids.com`, but **not training**, and `TRAINING_PORTAL_ORIGINS` defaults to the old `training-portal-theta.vercel.app`. The Railway env evidently doesn't add the new origin | established |
| `CSRF_TRUSTED_ORIGINS` | Exact list built from hosts + `FRONTEND_ORIGINS` (no wildcards). Training is missing here too, which only matters for cookie-based requests (not used) | **PASS** / LOW |
| `admin.okurmenkids.com` in the default origins | Allowed but unused, and outside the target architecture | **WARNING · LOW** (remove) |
| `SECRET_KEY` | `env("SECRET_KEY", default="django-insecure-change-me")`. **Production doesn't refuse to start without it.** It also signs JWTs (`SIGNING_KEY`), so if the variable is ever removed or renamed, anyone can forge admin tokens with the public default | **WARNING · HIGH** |
| HTTPS / proxy | `SECURE_PROXY_SSL_HEADER`, `SECURE_SSL_REDIRECT`, HSTS 1 year + `includeSubDomains` + preload, `nosniff`, `X-Frame-Options: DENY`, COOP `same-origin` all seen live | **PASS** |
| Cookies | Live `csrftoken`: `Secure; SameSite=Lax`; session cookie `Secure`, `HttpOnly`, `Lax` (code) | **PASS** |
| Static | WhiteNoise, `collectstatic` in the entrypoint, served live | **PASS** |
| Media | `SERVE_MEDIA=True` (Django serves the Railway volume, single instance); private resumes directory blocked in `serve_public_media` | **PASS** / scalability WARNING |
| Throttling | DRF default `anon 100/hour`, `user 1000/hour`, plus per-endpoint public scopes (e.g. leads `10/hour`) | **PASS** (code) |
| API schema | `/api/schema/` and `/api/docs/` are public (`AllowAny`), listing every endpoint. The repo is public anyway | **WARNING · LOW** |
| Superuser bootstrap | The entrypoint no longer creates `admin/admin` (PR #317). **Whether an `admin/admin` account created earlier still exists: NOT VERIFIED** (no login attempted) | **NOT VERIFIED · CRITICAL to check** |

---

## 8. Frontend integration

| | Public website | LMS | Training portal |
|---|---|---|---|
| Client | axios, `baseURL ${VITE_API_URL}/api/v1/public`, **timeout 15 s**, `withCredentials:false` | axios, `baseURL VITE_API_BASE_URL`, **no timeout set** (axios default: infinite) | `fetch`, no timeout / AbortController (except caller signals) |
| Live API origin | `api.okurmenkids.com` ✔ | `api.okurmenkids.com/api/v1` ✔ | `api.okurmenkids.com` ✔ but **CORS-blocked** |
| Auth | none (public only) | JWT Bearer in `localStorage`, single-flight refresh on 401 | no user auth; signed `X-Attempt-Token` per attempt |
| Error handling | `toApiError`: network / 404 / 400 / 409 / 429 / 5xx / config | `lib/apiError.ts` + forced logout when refresh fails | `ApiError` with network and config states; Kyrgyz messages |
| Media URLs | `VITE_MEDIA_URL` or the API origin; images loaded 200 live | `resolveMediaUrl` against the API origin | — |
| Old URLs in the live bundle | `okurmen-kids-drab.vercel.app/careers` | `training-portal-theta.vercel.app/`, `okurmen-kids-drab.vercel.app/monthly-performance` | none |
| localhost in production | none (live bundles scanned) | none | none |
| Status | **WARNING** (canonical, careers link) | **WARNING** (old launcher links, no timeout) | **FAIL** (CORS) |

File uploads weren't exercised live (that would write production data). The code
validates them per endpoint (e.g. `RECRUITMENT_RESUME_MAX_MB=5`,
`OPERATIONS_ATTACHMENT_MAX_MB=10`, Pillow image fields). **NOT VERIFIED**

---

## 9. Authentication

| Check | Evidence | Status |
|---|---|---|
| Login endpoint reachable and CORS-allowed from LMS | `OPTIONS /api/v1/auth/login/` from `lms.okurmenkids.com` → 200 + ACAO, `authorization` allowed | **PASS** |
| Protected endpoints refuse anonymous access | `GET /api/v1/auth/me/` and `/api/v1/trainers/` → **401** | **PASS** |
| LMS login page | `/` → `/login` renders ("OkurmenKids Digital — Вход") with no console errors | **PASS** |
| Login, refresh, logout with real credentials | not performed (would need a production account) | **NOT VERIFIED** |
| JWT lifetimes | access 30 min, refresh 7 days, rotation on, **no blacklist** (`token_blacklist` not installed) | **WARNING · MEDIUM**: logout doesn't revoke a stolen refresh token for up to 7 days |
| Token storage | `localStorage` (any XSS can read it) | **WARNING · MEDIUM** (accepted trade-off; there's no CSP on the LMS) |
| Django admin | Public `/admin/`, username + password only: no 2FA, no IP allowlist, no login-attempt lockout (DRF throttles don't apply to admin) | **WARNING · HIGH** |
| Default demo passwords | `seed_demo_data` (`admin12345`), `seed_dev_data` and `generate_mock_data` refuse to run under `DJANGO_ENV=production` (guards present) | **PASS** |

---

## 10. SEO & Google indexing

| Check | Evidence | Status |
|---|---|---|
| Canonical host | Live pages: `canonical = https://www.okurmenkids.com/...`; sitemap and robots say `https://okurmenkids.com`; the apex redirects to www with **307** (temporary) | **FAIL · HIGH** |
| robots.txt (public site) | 200 `text/plain`; disallows `/preview/` (3 languages); `Sitemap: https://okurmenkids.com/sitemap.xml` | **PASS** (but the sitemap URL itself 307-redirects) |
| sitemap.xml | 200 `application/xml`, well-formed, 30 URLs, no duplicates, hreflang ru/ky/en/x-default | **WARNING**: only static pages, 60 content URLs missing (no `VITE_SITE_URL` at build) |
| Titles and descriptions | Per page via `<Seo>` (e.g. "События — Okurmen Kids"); static fallback in `index.html` | **PASS** |
| Open Graph | Set at runtime; bot middleware for detail pages; static `og:image` absolute | **PASS** |
| Indexable pages | public pages `index, follow`; 404 and preview pages `noindex` (code) | **PASS** |
| Search Console | DNS verification TXT present; property state, coverage and sitemap submission | **NOT VERIFIED** |
| **LMS** (`lms.okurmenkids.com`) | **No `robots.txt`** (the path returns the SPA's HTML), **no `noindex`** meta or `X-Robots-Tag`. The login, portal and public schedule pages can be indexed. Private data stays behind the API's JWT check (verified 401) | **WARNING · MEDIUM** |
| **Training portal** | No `robots.txt` (HTML fallback), no meta robots or canonical | **WARNING · LOW** (decide whether it should be indexed) |
| **API host** | `/robots.txt` 404. `/api/docs/` and `/admin/login/` have no `X-Robots-Tag: noindex` | **WARNING · LOW** |
| Legacy `*.vercel.app` duplicates | serve the same content with 200, no redirect, no canonical to the new domain (LMS/training) | **WARNING · MEDIUM** |
| Broken links | none found in nav pages; the Contacts Google-Maps embed failed only because the sandbox blocks it | **PASS** (limited crawl) |

---

## 11. Security

| Area | Finding | Status |
|---|---|---|
| Secrets in git | No `.env`, keys, tokens or private keys tracked or ever added (history scanned). `.gitignore` covers `backend/.env`, `*.pem`, `*.key` | **PASS** |
| Repository visibility | **Public**: the full backend, infrastructure scripts and API surface are readable by anyone | **WARNING · MEDIUM** (fine if intended; it raises the stakes of every other item) |
| Frontend env exposure | Only public `VITE_*` URLs and modes in the bundles; no keys found | **PASS** |
| `SECRET_KEY` fallback | see §7 | **WARNING · HIGH** |
| CORS | exact origins, no wildcard, no credentials, localhost refused | **PASS** (except the missing training origin = FAIL in §7) |
| CSRF | exact trusted origins; `Secure` + `Lax` cookies | **PASS** |
| Admin protection | see §9 | **WARNING · HIGH** |
| Rate limiting | DRF throttles (code); throttle state is per-process cache (no Redis cache configured) | **PASS** / LOW |
| Database exposure | whether Railway Postgres has a public TCP proxy enabled | **NOT VERIFIED** |
| HTTPS | HSTS everywhere; valid certificates on all five hosts | **PASS** |
| Security headers | API: strong. Public site: nosniff, XFO, Referrer-Policy, Permissions-Policy. **LMS: only HSTS** (no nosniff, XFO, Referrer-Policy or CSP) while it holds JWTs in localStorage | **WARNING · MEDIUM** |
| **Python dependencies** (`pip-audit`, `backend/requirements.txt`) | **93 known vulns in 4 packages:** Django 6.1 (1, fixed in 6.1.1), DRF 3.18.0 (3, fixed in 3.18.2), **PyJWT 2.13.0 (15, fixed in 2.14/2.15; it is the JWT library)**, Pillow 11.3.0 (74, fixed in 13.0.0; it processes uploaded images) | **FAIL · HIGH** |
| npm (prod deps) | public website: zod (high, memory exhaustion); LMS: zod + follow-redirects (high); training portal: 0 | **WARNING · MEDIUM** |
| Runtime mismatch | `runtime.txt` says python-3.11, the Dockerfile uses 3.12 | **WARNING · LOW** |

---

## 12. Database & backups

| Item | Finding | Status |
|---|---|---|
| Automated Postgres backups | Nothing in the repo. Railway backup schedule and retention can't be seen | **NOT VERIFIED**: treat as **absent until proven** |
| Off-platform backup (dump stored outside Railway) | None found (no `pg_dump` job; `pg_dump` appears only in a manual `reset_accounting` safeguard) | **FAIL · HIGH** (no evidence one exists) |
| Media volume backup | Uploads live on one Railway Volume (`/app/media`) with no copy in the repo or elsewhere | **NOT VERIFIED** → likely single copy |
| Restore drill | none documented | **FAIL · MEDIUM** |
| Migrations | `migrate_with_lock` (advisory lock) before gunicorn | **PASS** |

---

## 13. Plan B & disaster recovery

Recovery estimates assume someone with dashboard access. Confidence is noted for each.

| Scenario | Current recovery path | Est. time | Gaps |
|---|---|---|---|
| Bad Vercel deploy | Vercel "Instant Rollback" to the previous production deployment, per project | 2–5 min | Rollback availability and plan limits NOT VERIFIED; no runbook; nobody alerted (no uptime monitoring found) |
| A frontend project deleted or unavailable | Recreate the project from the monorepo (root dir + env vars + domain) | 30–60 min | **Env vars aren't documented per project in the repo for this architecture**; the legacy `*.vercel.app` projects still run and could serve temporarily |
| Railway outage | None: single provider, single region, no standby | hours (wait for Railway) | No secondary host, no tested Docker run elsewhere, no status page |
| Postgres lost or corrupted | Railway backups **if enabled** | unknown | **No verified backup and no restore test**: potential **permanent data loss** (students, attendance, payroll) |
| Redis fails | If `CELERY_BROKER_URL` is unset, tasks run inline (no impact); if set, async tasks stop | minutes | Which mode production uses: NOT VERIFIED |
| Env var accidentally changed | Railway and Vercel keep deployment history, but env values have no history in the repo | 10–30 min if someone knows the right values | `SECRET_KEY` removal **silently** falls back to a public key (security incident, not an outage); `CORS`/`ALLOWED_HOSTS` mistakes break all frontends at once (as the training portal shows now) |
| DNS broken | Porkbun panel; records documented in this report (§4) | 5–60 min + propagation | No exported zone file; no registrar 2FA or lock state verified; no monitoring |

**What Plan B is missing:** verified Postgres backups plus an off-site dump; a
media backup; a written restore procedure that has actually been tested; uptime
monitoring and alerts for the five URLs; a secret and env inventory (names, which
service, where the value is kept, e.g. a password manager), never values in git;
an exported DNS zone; a production-boot guard for `SECRET_KEY`; a runbook for
rollback on Vercel and Railway; a named owner and on-call contact.

---

## 14. Critical issues

| # | Service | Issue | Evidence | Root cause | Business impact | Fix (proposed, not applied) | Priority |
|---|---|---|---|---|---|---|---|
| C1 | Training portal + backend | All training API calls blocked by CORS | Chromium console on `training.okurmenkids.com`: "blocked by CORS policy" for `/training/tests/`, `/videos/`, `/links/`, `/leaderboard/`, `/portal/`; preflight returns no ACAO | Origin `https://training.okurmenkids.com` isn't in `CORS_ALLOWED_ORIGINS` (not in the `FRONTEND_ORIGINS` default; `TRAINING_PORTAL_ORIGINS` still the old vercel.app) | Students can't practise or take training tests on the official URL | Railway env `TRAINING_PORTAL_ORIGINS=https://training.okurmenkids.com,https://training-portal-theta.vercel.app` and redeploy; then fix the code default (replace `admin.` with `training.` in `FRONTEND_ORIGINS`) | **CRITICAL** |
| C2 | Django admin | Possible `admin`/`admin` superuser left over from the old entrypoint | The old `server-entrypoint.sh` created it on every boot until PR #317 | Old bootstrap script | Full takeover of all data if that account still exists | The owner logs in privately and checks; change the password or deactivate the account; review the superuser list | **CRITICAL** (until checked) |
| H1 | Public website / Vercel Domains | Apex 307 → www, the opposite of the canonical target | `curl -I https://okurmenkids.com/` → 307 `location: https://www.okurmenkids.com/` | Vercel Domains: apex set to "redirect to www" | Google sees sitemap URLs that temporarily redirect; signals split between hosts | In Vercel: apex → *Connect to Production* (no redirect); www → *Redirect to okurmenkids.com, 308* | **HIGH** |
| H2 | Public website build | `VITE_SITE_URL` not set | Live canonical = www origin; live sitemap has 30 URLs vs 20 content items × 3 languages available | Missing Production env var | Wrong canonicals; 60 news, team, project and achievement pages missing from the sitemap | Set `VITE_SITE_URL=https://okurmenkids.com` (+ `VITE_CAREERS_URL`) and redeploy, after H1 | **HIGH** |
| H3 | Backend | 93 known vulnerabilities (PyJWT, Pillow, DRF, Django) | `pip-audit` output (§11) | Pinned old versions | JWT and upload-handling exposure on a public API | Upgrade to Django 6.1.1+, DRF 3.18.2+, PyJWT 2.15+, Pillow 13+; run tests; deploy | **HIGH** |
| H4 | Backend | `SECRET_KEY` silently falls back to a public default | `base.py` `default="django-insecure-change-me"` | No production guard | If the env var is lost, JWTs can be forged, which means admin takeover | Make `production.py` refuse to boot without a strong `SECRET_KEY` | **HIGH** |
| H5 | Data | No verified database or media backups | nothing in repo; dashboards not visible | — | Permanent loss of business data in an incident | Verify or enable Railway backups; add a scheduled off-site `pg_dump` and media sync; restore drill | **HIGH** |
| H6 | Django admin | Public admin with no 2FA, lockout or IP restriction | `/admin/login/` 200 publicly | — | Credential-stuffing target on a public codebase | Add login throttling or lockout and 2FA, or restrict by IP | **HIGH** |

---

## 15. Recommended improvements

* **MEDIUM:** add `robots.txt` (`Disallow: /`) and `X-Robots-Tag: noindex` to the LMS (keep `/schedule` and `/leaderboard` indexable if they're meant to be public); add `X-Robots-Tag: noindex` to `/admin/` and `/api/docs/` on the API.
* **MEDIUM:** redirect or add canonicals on the legacy `*.vercel.app` deployments (careful with printed attendance QR codes that point at `okurmen-kids-drab.vercel.app`).
* **MEDIUM:** LMS security headers (`nosniff`, `Referrer-Policy`, `X-Frame-Options`, then a CSP), because it holds JWTs in `localStorage`.
* **MEDIUM:** JWT blacklist on logout (`rest_framework_simplejwt.token_blacklist`; this needs a migration).
* **MEDIUM:** update the LMS launcher URLs (`VITE_PORTAL_TRAINING_URL=https://training.okurmenkids.com`, `VITE_PORTAL_PERFORMANCE_URL=https://lms.okurmenkids.com/monthly-performance`) and the public website's `VITE_CAREERS_URL`.
* **MEDIUM:** set an axios timeout in the LMS and a fetch timeout in the training portal.
* **MEDIUM:** CI on GitHub (backend tests and the three frontend builds, tests and lint on every PR); enable branch protection on `master`.
* **MEDIUM:** uptime monitoring for the five URLs plus `/api/v1/`, with alerts.
* **LOW:** remove `admin.okurmenkids.com` from the default origins; update `PRODUCTION_DOMAIN_MIGRATION.md` to this architecture; DMARC record; CAA; Vercel "Ignored Build Step" per app; align `runtime.txt` with the Dockerfile; fix the 3 failing `apps.users` tests; upgrade zod and follow-redirects.

---

## 16. Prioritized action plan (awaiting your approval)

| Step | Action | Who | Effort |
|---|---|---|---|
| 1 | **C2:** check privately whether `admin`/`admin` works on `/admin/`; change it if so | owner | 5 min |
| 2 | **C1:** set `TRAINING_PORTAL_ORIGINS` on Railway, redeploy, re-test the training portal | owner (env), then code follow-up | 10 min |
| 3 | **H1:** fix Vercel Domains (apex = Production, www → 308 → apex) | owner (dashboard) | 5 min |
| 4 | **H2:** set `VITE_SITE_URL` and `VITE_CAREERS_URL` on the public website, and the launcher URLs on the LMS; redeploy; resubmit the sitemap | owner | 15 min |
| 5 | **H5:** confirm or enable Railway Postgres backups; take a manual `pg_dump` now and store it off-platform; copy `/app/media` | owner | 30–60 min |
| 6 | **H4 + H3:** code PR: `SECRET_KEY` boot guard, dependency upgrades, default-origin fix (training in, admin out) | me, after approval | 1–2 h + review |
| 7 | **H6:** admin login throttling or 2FA | me, after approval | 2–4 h |
| 8 | Monitoring, CI, backup and restore runbook, env inventory, LMS noindex and headers | me + owner | 1–2 days |

### Dashboard checks that must be done manually (I had no access)
Vercel, for each of the 3 projects: Root Directory, Production Branch = `master`, env var
names, Domains, deployment history and an available Instant Rollback, build and
runtime logs. Railway: Start Command, Healthcheck Path, replicas and region,
Volume mount and size, **Postgres backups (schedule and retention)**, Postgres
public networking off, Redis service, Celery worker and beat services,
cron last runs, variables (`SECRET_KEY` present, `TRAINING_PORTAL_ORIGINS`,
`LMS_FRONTEND_URL`, `PUBLIC_WEBSITE_URL`). Porkbun: registrar lock, account
2FA, URL forwarding rules off. Google Search Console: property verified,
sitemap submitted, coverage errors.
