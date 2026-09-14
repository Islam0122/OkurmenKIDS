"""The one shared definition of "how many lessons are scheduled/in progress/
completed/cancelled/upcoming/needing attention" for a given (already
filtered) Lesson queryset.

Used by both the Admin dashboard (admin_views.py's `_lesson_status_kpi`) and
the Analytics service (services.analytics.lessons) so the same underlying
data never reports two different numbers in two different places.

Status-based, never date-based: "completed"/"cancelled" reflect the real
`Lesson.status` value only — a lesson is never inferred as completed just
because its date/time has passed, since status requires an explicit
transition (start/complete/cancel — see services.lesson_lifecycle). "Requires
attention" is the one place the past actually matters: a still-scheduled (or
still in-progress) lesson whose slot is already over is something a teacher
forgot to finish, not a completed one.
"""
from __future__ import annotations

import datetime as dt

from django.db.models import Count, Q, QuerySet
from django.utils import timezone

from ..models import Lesson


def attention_q(today: dt.date, now_time: dt.time) -> Q:
    """Still-open (scheduled/in_progress) AND already in the past."""
    return Q(status__in=[Lesson.Status.SCHEDULED, Lesson.Status.IN_PROGRESS]) & (
        Q(date__lt=today) | Q(date=today, end_time__lte=now_time)
    )


def lesson_status_counts(
    lessons_qs: QuerySet,
    *,
    today: dt.date | None = None,
    now_time: dt.time | None = None,
) -> dict:
    """Aggregate, single-query status breakdown of `lessons_qs`.

    `total`/`scheduled`/`in_progress`/`completed`/`cancelled` are plain
    per-status counts; `upcoming` is still-scheduled AND not yet in the past
    (by date only — the shared "advance notice" definition used across the
    app); `attention` is still-open AND already in the past (see
    `attention_q`) — the lessons a teacher started or scheduled but never
    explicitly finished.
    """
    today = today or timezone.localdate()
    now_time = now_time or timezone.localtime().time()

    agg = lessons_qs.aggregate(
        total=Count("id"),
        scheduled=Count("id", filter=Q(status=Lesson.Status.SCHEDULED)),
        in_progress=Count("id", filter=Q(status=Lesson.Status.IN_PROGRESS)),
        completed=Count("id", filter=Q(status=Lesson.Status.COMPLETED)),
        cancelled=Count("id", filter=Q(status=Lesson.Status.CANCELLED)),
        upcoming=Count("id", filter=Q(status=Lesson.Status.SCHEDULED, date__gte=today)),
        attention=Count("id", filter=attention_q(today, now_time)),
    )
    return {key: value or 0 for key, value in agg.items()}
