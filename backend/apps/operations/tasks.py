from celery import shared_task

from .services.scheduler import run_periodic


@shared_task(name="operations.run_periodic")
def run_periodic_task() -> dict:
    return run_periodic()
