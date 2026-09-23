import tempfile

from .base import *

DEBUG = False

ALLOWED_HOSTS = ["testserver", "localhost", "127.0.0.1"]

# In-memory SQLite by default (fast, zero setup). SQLite silently ignores
# select_for_update(), so row-locking code only really runs on PostgreSQL —
# set TEST_DATABASE_URL (e.g. postgres://user:pass@127.0.0.1:5432/okurmen) to
# run the suite against it; the concurrency tests in apps.academy.tests are
# skipped on SQLite.
DATABASES = {
    "default": env.db("TEST_DATABASE_URL", default="sqlite://:memory:"),
}

EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.dummy.DummyCache",
    }
}

PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.MD5PasswordHasher",
]

MEDIA_ROOT = tempfile.mkdtemp()