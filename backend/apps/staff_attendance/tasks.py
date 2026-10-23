from celery import shared_task

from .services.marking import close_stale_sessions


@shared_task(name="staff_attendance.close_stale_sessions")
def close_stale_sessions_task() -> int:
    return close_stale_sessions()
