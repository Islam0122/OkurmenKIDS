"""Session roster and live participation state (SessionParticipant).

The roster is who a session is for (a whole group or chosen students). The
live state is what the teacher monitors; it is updated at the moments the
student flow already has (services/attempts.py, public_views.py):

    start / resume   → IN_PROGRESS, started_at, question_total
    heartbeat        → last_seen_at, current_question, answered_count
    page closed      → left_at            (shown as «Нет соединения»)
    submit           → COMPLETED, finished_at, score
    time ran out     → EXPIRED

PAUSED and DISCONNECTED are derived on read (SessionParticipant.live_status_at).
Nothing here stores answers or their correctness — monitoring shows progress,
not answers.
"""
from __future__ import annotations

from dataclasses import dataclass

from django.db import transaction
from django.utils import timezone

from ..models import ParticipantStatus, SessionParticipant, StudentAttempt, TestSession


@transaction.atomic
def set_roster(session: TestSession, students) -> None:
    """Make the session's roster exactly ``students``. Students who already
    started keep their row (and history) even if unticked."""
    wanted = {s.pk: s for s in students}
    existing = {p.student_id: p for p in session.participants.all()}
    removable = [
        p.pk for sid, p in existing.items()
        if sid not in wanted and p.status == ParticipantStatus.NOT_STARTED
    ]
    session.participants.filter(pk__in=removable).delete()
    SessionParticipant.objects.bulk_create(
        [SessionParticipant(session=session, student=s) for sid, s in wanted.items() if sid not in existing]
    )


def roster_students(session: TestSession):
    """Who may join: the roster if the session has one, else (legacy
    group sessions) every active student of the group."""
    from apps.academy.models import Student

    if session.participants.exists():
        return Student.objects.filter(test_participations__session=session).order_by("first_name", "last_name")
    if session.group_id:
        return Student.objects.filter(group=session.group, status=Student.Status.ACTIVE).order_by("first_name", "last_name")
    return Student.objects.none()


def _participant(attempt: StudentAttempt) -> SessionParticipant | None:
    if attempt.student_id is None:
        return None
    participant, _ = SessionParticipant.objects.get_or_create(session=attempt.session, student_id=attempt.student_id)
    return participant


def attempt_started(attempt: StudentAttempt) -> None:
    participant = _participant(attempt)
    if participant is None:
        return
    now = timezone.now()
    if participant.attempt_id != attempt.pk:
        participant.attempt = attempt
        participant.started_at = attempt.started_at or now
        participant.finished_at = None
        participant.score = None
        participant.current_question = 1
        participant.answered_count = 0
    participant.status = ParticipantStatus.IN_PROGRESS
    participant.question_total = len(attempt.question_ids)
    participant.last_seen_at = now
    participant.left_at = None
    participant.save()


def attempt_progress(attempt: StudentAttempt, *, current: int | None = None, answered: int | None = None,
                     left: bool = False) -> None:
    """Heartbeat from the student page (or its page-closed beacon)."""
    if attempt.status != "active":
        return
    participant = SessionParticipant.objects.filter(attempt=attempt).first()
    if participant is None:
        return
    now = timezone.now()
    total = participant.question_total or len(attempt.question_ids)
    if current is not None:
        participant.current_question = max(1, min(int(current), total or 1))
    if answered is not None:
        participant.answered_count = max(0, min(int(answered), total))
    if left:
        participant.left_at = now
    else:
        participant.last_seen_at = now
        participant.left_at = None
    participant.save(update_fields=["current_question", "answered_count", "last_seen_at", "left_at"])


def attempt_finished(attempt: StudentAttempt) -> None:
    participant = SessionParticipant.objects.filter(attempt=attempt).first() or _participant(attempt)
    if participant is None:
        return
    now = timezone.now()
    participant.attempt = attempt
    participant.status = ParticipantStatus.COMPLETED
    participant.finished_at = attempt.finished_at or now
    participant.score = attempt.score
    participant.answered_count = attempt.answers.count()
    participant.question_total = len(attempt.question_ids) or participant.question_total
    participant.current_question = participant.question_total
    participant.last_seen_at = now
    participant.save()


def attempt_expired(attempt: StudentAttempt) -> None:
    participant = SessionParticipant.objects.filter(attempt=attempt).first()
    if participant is None:
        return
    participant.status = ParticipantStatus.EXPIRED
    participant.save(update_fields=["status"])


# ---------------------------------------------------------------------------
# Read side: counters for monitoring pages and the teacher API
# ---------------------------------------------------------------------------

@dataclass
class SessionCounts:
    total: int = 0
    not_started: int = 0
    in_progress: int = 0       # incl. paused / disconnected — they are mid-exam
    disconnected: int = 0
    completed: int = 0
    expired: int = 0
    average_score: float | None = None

    @property
    def started(self) -> int:
        return self.total - self.not_started


def session_counts(session: TestSession, participants=None, now=None) -> SessionCounts:
    now = now or timezone.now()
    participants = list(participants if participants is not None else session.participants.all())
    counts = SessionCounts(total=len(participants))
    scores = []
    for participant in participants:
        participant.session = session  # avoid a query per row in live_status_at
        status = participant.live_status_at(now)
        if status == ParticipantStatus.NOT_STARTED:
            counts.not_started += 1
        elif status == ParticipantStatus.COMPLETED:
            counts.completed += 1
            if participant.score is not None:
                scores.append(participant.score)
        elif status == ParticipantStatus.EXPIRED:
            counts.expired += 1
        else:
            counts.in_progress += 1
            if status == ParticipantStatus.DISCONNECTED:
                counts.disconnected += 1
    if scores:
        counts.average_score = round(sum(scores) / len(scores), 1)
    return counts
