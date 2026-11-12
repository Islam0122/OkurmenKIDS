import os


def _origins(name: str, default: str = "") -> list[str]:
    """Comma-separated origins from env, without trailing slashes."""
    return [o.strip().rstrip("/") for o in os.getenv(name, default).split(",") if o.strip()]


# Production frontends on the okurmenkids.com domain (separate Vercel
# projects): the public website (apex + www, which Vercel 308-redirects to
# the apex), the LMS and the admin dashboard. Override with FRONTEND_ORIGINS
# (comma-separated) — e.g. to drop www once the redirect is confirmed.
# Also trusted for CSRF in production (settings/production.py).
FRONTEND_ORIGINS = _origins(
    "FRONTEND_ORIGINS",
    "https://okurmenkids.com,https://www.okurmenkids.com,"
    "https://lms.okurmenkids.com,https://admin.okurmenkids.com",
)

_CORS_ALLOWED_ORIGINS = [
    *FRONTEND_ORIGINS,
    # Legacy *.vercel.app deployments of the LMS and training portal — kept
    # while the custom domains roll out (old bookmarks, installed PWAs,
    # printed QR codes). Remove once nothing uses them.
    "https://okurmen-kids-drab.vercel.app",
    "https://training-portal-theta.vercel.app",
    # The public training portal (training-portal/, React): its deployed
    # origin(s), comma-separated, e.g. https://train.okurmen.kg
    *[o.strip().rstrip("/") for o in os.getenv("TRAINING_PORTAL_ORIGINS", "https://training-portal-theta.vercel.app/").split(",") if o.strip()],
    # The standalone «OkurmenKIDS Schedule» site (the same frontend built with
    # VITE_APP_MODE=schedule), e.g. https://schedule.okurmenkids.com —
    # comma-separated. Public, read-only: it calls GET /api/v1/public/schedule/* only.
    *[o.strip().rstrip("/") for o in os.getenv("SCHEDULE_SITE_ORIGINS", "").split(",") if o.strip()],
    # The public «OkurmenKIDS Leaderboard» site (VITE_APP_MODE=leaderboard),
    # e.g. https://leaderboard.okurmenkids.com — comma-separated. Public,
    # read-only: it calls GET /api/v1/public/leaderboard/* only.
    *[o.strip().rstrip("/") for o in os.getenv("LEADERBOARD_SITE_ORIGINS", "").split(",") if o.strip()],
    # The standalone «OkurmenKIDS — Общая статистика» site (VITE_APP_MODE=statistics),
    # e.g. https://stats.okurmenkids.com — comma-separated. Reads only
    # /api/v1/monthly-performance/* with a staff JWT or a read-only X-Dashboard-Key.
    *[o.strip().rstrip("/") for o in os.getenv("STATISTICS_SITE_ORIGINS", "").split(",") if o.strip()],
    # The «OKURMENKIDS DIGITAL» launcher on its own domain (VITE_APP_MODE=portal),
    # e.g. https://digital.okurmenkids.com — comma-separated. It signs staff in
    # and serves the LMS, schedule and leaderboard from the same build.
    *[o.strip().rstrip("/") for o in os.getenv("PORTAL_SITE_ORIGINS", "").split(",") if o.strip()],
    # The public website (okurmen-public-website/, React), e.g.
    # https://okurmenkids.kg,https://www.okurmenkids.kg — comma-separated.
    # Reads /api/v1/public/site|news|projects/ and posts enrollment leads.
    *[o.strip().rstrip("/") for o in os.getenv("PUBLIC_WEBSITE_ORIGINS", "https://okurmen-public-website.vercel.app").split(",") if o.strip()],
    # Any further exact origins (comma-separated), e.g. a staging frontend.
    *_origins("CORS_EXTRA_ORIGINS"),
]
# Exact origins only (never CORS_ALLOW_ALL_ORIGINS), de-duplicated in order.
CORS_ALLOWED_ORIGINS = list(dict.fromkeys(_CORS_ALLOWED_ORIGINS))

CORS_ALLOW_METHODS = [
    "DELETE",
    "GET",
    "OPTIONS",
    "PATCH",
    "POST",
    "PUT",
]

CORS_ALLOW_HEADERS = [
    "accept",
    "accept-encoding",
    "accept-language",
    "authorization",
    "content-type",
    "dnt",
    "origin",
    "user-agent",
    "x-csrftoken",
    "x-requested-with",
    # Public training API: the signed token of the student's own attempt.
    "x-attempt-token",
    # Accounting: a repeated payment request returns the same payment.
    "idempotency-key",
    # «Общая статистика»: read-only dashboard key (apps.performance).
    "x-dashboard-key",
]

# Every frontend authenticates with a JWT in the Authorization header and
# sends no cookies (no withCredentials / credentials: "include" anywhere), so
# credentialed CORS is not needed. It is off by default because the frontends
# (*.okurmenkids.com) are now the *same site* as the API: with it on, a
# listed origin could make requests that carry a Django-admin session cookie
# (SameSite=Lax does not block same-site requests). Re-enable with
# CORS_ALLOW_CREDENTIALS=True only for a frontend that really uses cookies.
CORS_ALLOW_CREDENTIALS = os.getenv("CORS_ALLOW_CREDENTIALS", "False").strip().lower() in ("1", "true", "yes", "on")

# Local frontends (vite dev / preview) may call the API from any port — in
# development and tests only. In production a page served from the visitor's
# own localhost is not ours, so it is refused unless explicitly allowed with
# CORS_ALLOW_LOCALHOST=True (e.g. debugging a local frontend against prod).
_ALLOW_LOCALHOST = os.getenv("DJANGO_ENV", "development") != "production" or (
    os.getenv("CORS_ALLOW_LOCALHOST", "False").strip().lower() in ("1", "true", "yes", "on")
)
CORS_ALLOWED_ORIGIN_REGEXES = [
    r"^http://127\.0\.0\.1(:\d+)?$",
    r"^http://localhost(:\d+)?$",
] if _ALLOW_LOCALHOST else []