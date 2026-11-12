from .base import *

DEBUG = False

# Hostnames this API answers to. ALLOWED_HOSTS (comma-separated) is the
# preferred variable, e.g. "api.okurmenkids.com,okurmenkids.up.railway.app"
# (default when unset: api.okurmenkids.com).
# The legacy single ALLOWED_HOST still works so an existing Railway service
# keeps booting unchanged. Railway's own public domain (RAILWAY_PUBLIC_DOMAIN,
# injected by Railway) is always added, so the *.up.railway.app address keeps
# answering during and after the move to the custom domain. Railway's
# deployment health check sends "Host: healthcheck.railway.app".
ALLOWED_HOSTS = list(dict.fromkeys(
    h.strip().lower()
    for h in [
        *env.list("ALLOWED_HOSTS", default=["api.okurmenkids.com"]),
        env.str("ALLOWED_HOST", default=""),
        env.str("RAILWAY_PUBLIC_DOMAIN", default=""),
        "healthcheck.railway.app",
    ]
    if h and h.strip()
))

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "HOST": env("PGHOST", default="db"),
        "USER": env("PGUSER", default="postgres"),
        "NAME": env("PGDATABASE", default="postgres"),
        "PASSWORD": env("PGPASSWORD", default="postgres"),
        "PORT": env("PGPORT", default=5432),
        "CONN_MAX_AGE": 60,
        "OPTIONS": {
            "connect_timeout": 10,
        },
    }
}

# Uploaded files (Teacher.image etc.) must live on the Railway Volume mounted
# at this path — the container's own filesystem is wiped on every redeploy.
MEDIA_ROOT = Path(env("MEDIA_ROOT", default="/app/media"))

# WhiteNoise only serves collected static files, never uploads, so Django
# serves MEDIA_URL itself (django.views.static.serve, see config/urls.py).
# Set SERVE_MEDIA=False once media moves to external storage (R2/S3).
SERVE_MEDIA = env.bool("SERVE_MEDIA", default=True)

# Django's default LOGGING only mails 500 tracebacks to ADMINS (empty here)
# when DEBUG is off, so they never reached the Railway logs. Send them —
# and every other WARNING+ record — to stderr, which gunicorn passes through.
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {
        "console": {"class": "logging.StreamHandler"},
    },
    "root": {
        "handlers": ["console"],
        "level": env("LOG_LEVEL", default="WARNING"),
    },
}

EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = env("EMAIL_HOST", default="smtp.gmail.com")
EMAIL_PORT = env.int("EMAIL_PORT", default=587)
EMAIL_USE_TLS = True
EMAIL_HOST_USER = env("EMAIL_HOST_USER")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD")
DEFAULT_FROM_EMAIL = EMAIL_HOST_USER

# Railway terminates TLS at its edge and forwards plain HTTP with
# X-Forwarded-Proto; the edge overwrites that header, so it can be trusted.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = env.bool("SECURE_SSL_REDIRECT", default=True)
# Railway's health check calls the container directly over plain HTTP (no
# X-Forwarded-Proto) — a 301 to HTTPS would fail it. Exempt only the
# health endpoint (GET /api/v1/ → {"status": "ok"}, apps.users.views.health).
SECURE_REDIRECT_EXEMPT = [r"^api/v1/$"]

SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True

SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"

SESSION_COOKIE_SECURE = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SECURE = True
CSRF_COOKIE_HTTPONLY = False
CSRF_COOKIE_SAMESITE = "Lax"


# Origins allowed to send unsafe (POST/PUT/PATCH/DELETE) requests that carry
# the Django session/CSRF cookies. Same-origin forms on the API host itself
# (Django admin, /exam/, /feedback/s/) pass Django's Origin == Host check
# without being listed. The SPAs authenticate with a JWT in the
# Authorization header (no cookies), so CSRF never applies to them — they
# are listed only so a session-authenticated request from them is not
# rejected. The former "https://*.railway.app" wildcard trusted every app
# hosted on Railway (anyone's), so it is replaced by this exact list.
CSRF_TRUSTED_ORIGINS = list(dict.fromkeys(
    o.strip().rstrip("/")
    for o in [
        *env.list("CSRF_TRUSTED_ORIGINS", default=[]),
        *(f"https://{h}" for h in ALLOWED_HOSTS if h != "healthcheck.railway.app"),
        *FRONTEND_ORIGINS,
    ]
    if o and o.strip()
))