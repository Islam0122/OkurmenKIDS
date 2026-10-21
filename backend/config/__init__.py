# Celery необязателен: без пакета celery проект работает как раньше,
# фоновые задачи оплаты запускаются командой `billing_autorun`.
try:
    from .celery import app as celery_app
except ImportError:  # pragma: no cover
    celery_app = None

__all__ = ("celery_app",)
