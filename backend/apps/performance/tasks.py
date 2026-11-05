import logging

from celery import shared_task

from .services.snapshots import capture

logger = logging.getLogger(__name__)


@shared_task(name="performance.capture_daily_snapshots")
def capture_daily_snapshots_task() -> dict:
    """Снимок «Общей статистики» за сегодня + закрытие прошлых дней (идемпотентно).

    Пока деплой не применил миграции (Beat успел стартовать раньше), задача
    пропускает запуск — как `manage.py run_scheduled_tasks`, — а не падает на
    отсутствующей колонке."""
    from apps.billing.services.scheduler import pending_migrations

    pending = [name for name in pending_migrations() if name.startswith("performance.")]
    if pending:
        logger.warning("performance snapshots: migrations pending, skip: %s", pending)
        return {"status": "skipped_migrations", "pending": pending}
    return capture()
