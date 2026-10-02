"""Sessions as a business entity: schedule sync for lists, phase filters,
display helpers. Used by the admin «Сессии» section and the teacher API;
results and their exports live in services/analytics.py."""
from __future__ import annotations

from datetime import datetime

from django.db.models import Q, QuerySet
from django.utils import timezone

from ..models import (
    SessionPhase,
    SessionStatus,
    TestSession,
)

PHASE_FILTERS: dict[str, Q] = {
    SessionPhase.DRAFT: Q(status=SessionStatus.CREATED, scheduled_start__isnull=True),
    SessionPhase.SCHEDULED: Q(status=SessionStatus.CREATED, scheduled_start__isnull=False),
    SessionPhase.ACTIVE: Q(status__in=[SessionStatus.RUNNING, SessionStatus.PAUSED]),
    SessionPhase.FINISHED: Q(status__in=[SessionStatus.FINISHED, SessionStatus.EXPIRED]),
    SessionPhase.CANCELLED: Q(status=SessionStatus.CANCELLED),
}


def sync_due_sessions(queryset: QuerySet | None = None, now=None) -> None:
    """Bring stored statuses up to date before filtering by them: start
    scheduled sessions whose time has come, close those past their end,
    persist lazy expiry. Only rows that need it are touched."""
    now = now or timezone.now()
    sessions = queryset if queryset is not None else TestSession.objects.all()
    due = sessions.filter(
        Q(status=SessionStatus.CREATED, scheduled_start__lte=now)
        | Q(status__in=[SessionStatus.RUNNING, SessionStatus.PAUSED], scheduled_end__lte=now)
        | Q(status=SessionStatus.RUNNING, session_type="exam", expires_at__lte=now)
    ).select_related("test")
    for session in due:
        session.sync_schedule(now)
        if session.status == SessionStatus.RUNNING and session.effective_status_at(now) == SessionStatus.EXPIRED:
            session.expire()


def filter_by_phase(queryset: QuerySet, phase: str) -> QuerySet:
    return queryset.filter(PHASE_FILTERS[phase]) if phase in PHASE_FILTERS else queryset


def session_date(session: TestSession) -> datetime | None:
    """When the session is (scheduled to be) held."""
    return session.scheduled_start or session.started_at or session.created_at


def display_title(session: TestSession) -> str:
    return session.title or session.test.title


# ---------------------------------------------------------------------------
# Display
# ---------------------------------------------------------------------------

def format_duration(seconds: int | None) -> str:
    if seconds is None:
        return "—"
    minutes, sec = divmod(int(seconds), 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours}:{minutes:02d}:{sec:02d}" if hours else f"{minutes}:{sec:02d}"


def subtitle(session: TestSession) -> str:
    parts = [f"Тест: {session.test.title}"]
    if session.group_id:
        parts.append(f"Группа: {session.group.name}")
    when = session_date(session)
    if when:
        parts.append(timezone.localtime(when).strftime("%d.%m.%Y %H:%M"))
    parts.append(f"Ключ: {session.key}")
    return " · ".join(parts)
