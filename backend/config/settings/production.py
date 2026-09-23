from .base import *

DEBUG = False

ALLOWED_HOSTS = [env.str("ALLOWED_HOST")]

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

EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = env("EMAIL_HOST", default="smtp.gmail.com")
EMAIL_PORT = env.int("EMAIL_PORT", default=587)
EMAIL_USE_TLS = True
EMAIL_HOST_USER = env("EMAIL_HOST_USER")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD")
DEFAULT_FROM_EMAIL = EMAIL_HOST_USER

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = True

SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True

SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"

SESSION_COOKIE_SECURE = True
SESSION_COOKIE_SAMESITE = "Strict"

CSRF_COOKIE_SECURE = True
CSRF_COOKIE_HTTPONLY = True
CSRF_COOKIE_SAMESITE = "Strict"

CSRF_TRUSTED_ORIGINS = [
    "https://*.railway.app",
    "https://*.up.railway.app",
]