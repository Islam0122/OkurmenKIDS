"""Настройки Django для демо-среды видео: отдельная SQLite-база вне
репозитория, письма — в консоль. Production-база не используется."""
import os

os.environ.setdefault("EMAIL_HOST_USER", "demo@example.com")
os.environ.setdefault("EMAIL_HOST_PASSWORD", "")

from config.settings.development import *  # noqa: E402,F401,F403

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": os.environ.get("MARKETING_DEMO_DB", "/tmp/okurmen_marketing_demo.sqlite3"),
    }
}
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
