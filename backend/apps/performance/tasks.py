from celery import shared_task

from .services.snapshots import capture


@shared_task(name="performance.capture_daily_snapshots")
def capture_daily_snapshots_task() -> dict:
    """Снимок «Общей статистики» за сегодня + закрытие прошлых дней (идемпотентно)."""
    return capture()
