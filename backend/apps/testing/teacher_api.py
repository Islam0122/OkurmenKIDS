"""Teacher portal API: exam sessions of the teacher's own groups, live.

    GET /api/v1/teacher/sessions/?status=all|live|scheduled|finished&today=1
    GET /api/v1/teacher/sessions/{id}/
    GET /api/v1/teacher/sessions/{id}/participants/
    GET /api/v1/teacher/sessions/{id}/participants/{participant_id}/result/

Scoping is done on the backend, in every queryset: a teacher only reaches
sessions whose group is one of theirs (Group.objects.for_teacher — the same
rule as the rest of the portal), so another group's session is a plain 404
whatever its id. Admins and the Team Lead see every session (every view here
is a GET, so the Team Lead stays read-only).

Monitoring shows progress, never answers: no answer content, correctness or
score while a student is still taking the test. The detailed result opens
only after the student has finished.

Realtime: the project has no WebSocket infrastructure, so the portal polls
these endpoints (a few seconds while a session is live).
"""
from __future__ import annotations

from django.db.models import Count, Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers
from rest_framework.exceptions import NotFound
from rest_framework.generics import ListAPIView, RetrieveAPIView
from rest_framework.permissions import BasePermission
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.academy.models import Group
from apps.users.models import User
from apps.users.permissions import is_team_lead

from .models import ParticipantStatus, SessionParticipant, SessionPhase, TestSession
from .services.attempts import result_rows
from .services.participants import session_counts
from .services.sessions import PHASE_FILTERS, display_title, filter_by_phase, sync_due_sessions

STATUS_FILTERS = {
    "live": SessionPhase.ACTIVE,
    "scheduled": SessionPhase.SCHEDULED,
    "finished": SessionPhase.FINISHED,
}


def _is_admin(user) -> bool:
    return bool(user and user.is_authenticated and (user.is_superuser or user.role == User.Role.ADMIN))


class IsTeacherOrAdmin(BasePermission):
    message = "Доступно только тренеру, руководителю тренеров или администратору."

    def has_permission(self, request, view) -> bool:
        user = request.user
        return _is_admin(user) or is_team_lead(user) or getattr(user, "teacher_profile", None) is not None


def sessions_for(user):
    """Every session the user may see — the single scoping rule."""
    sessions = TestSession.objects.select_related("test", "group").filter(group__isnull=False)
    if _is_admin(user) or is_team_lead(user):
        return sessions
    teacher = getattr(user, "teacher_profile", None)
    if teacher is None:
        return sessions.none()
    return sessions.filter(group__in=Group.objects.for_teacher(teacher))


# ---------------------------------------------------------------------------
# Serializers
# ---------------------------------------------------------------------------

def _counts(session, participants=None) -> dict:
    counts = session_counts(session, participants)
    return {
        "total": counts.total,
        "started": counts.started,
        "in_progress": counts.in_progress,
        "disconnected": counts.disconnected,
        "completed": counts.completed,
        "not_started": counts.not_started,
        "expired": counts.expired,
        "average_score": counts.average_score,
    }


class TeacherSessionSerializer(serializers.Serializer):
    def to_representation(self, session: TestSession) -> dict:
        now = timezone.now()
        phase = session.phase_at(now)
        test = session.test
        return {
            "id": str(session.pk),
            "title": display_title(session),
            "key": session.key,
            "session_type": session.session_type,
            "phase": phase,
            "phase_label": SessionPhase(phase).label,
            "is_live": phase == SessionPhase.ACTIVE,
            "is_paused": session.effective_status_at(now) == "paused",
            "test": {
                "id": str(test.pk),
                "title": test.title,
                "level": test.level,
                "level_label": test.get_level_display(),
                "passing_score": test.passing_score,
                "question_count": (
                    session.questions_total if getattr(session, "questions_total", None) is not None
                    else test.questions.count()
                ),
            },
            "group": {"id": session.group_id, "name": session.group.name} if session.group_id else None,
            "scheduled_start": session.scheduled_start,
            "scheduled_end": session.scheduled_end,
            "started_at": session.started_at,
            "ends_at": session.expires_at if session.is_exam else session.scheduled_end,
            "time_limit_minutes": session.effective_time_limit_minutes,
            "counts": _counts(session, self.context.get("participants", {}).get(session.pk)),
        }


class ParticipantSerializer(serializers.Serializer):
    def to_representation(self, participant: SessionParticipant) -> dict:
        now = timezone.now()
        status = participant.live_status_at(now)
        finished = status == ParticipantStatus.COMPLETED
        total = participant.question_total
        return {
            "id": str(participant.pk),
            "student": {"id": participant.student_id, "name": str(participant.student)},
            "status": status,
            "status_label": ParticipantStatus(status).label,
            "current_question": participant.current_question if status != ParticipantStatus.NOT_STARTED else 0,
            "answered_count": participant.answered_count,
            "question_total": total,
            "progress_percent": round(participant.answered_count / total * 100) if total else 0,
            "started_at": participant.started_at,
            "finished_at": participant.finished_at,
            "last_seen_at": participant.last_seen_at,
            "duration_seconds": participant.duration_seconds,
            # Only once the student has finished — never mid-exam.
            "score": participant.score if finished else None,
            "result_available": finished,
        }


# ---------------------------------------------------------------------------
# Views
# ---------------------------------------------------------------------------

class TeacherSessionListView(ListAPIView):
    permission_classes = [IsTeacherOrAdmin]
    serializer_class = TeacherSessionSerializer

    def get_queryset(self):
        sessions = sessions_for(self.request.user)
        sync_due_sessions(sessions)
        status = self.request.query_params.get("status") or "all"
        if status in STATUS_FILTERS:
            sessions = filter_by_phase(sessions, STATUS_FILTERS[status])
        if self.request.query_params.get("today") == "1":
            # Dashboard: today's sessions plus anything running right now.
            sessions = sessions.filter(Q(scheduled_start__date=timezone.localdate()) | PHASE_FILTERS[SessionPhase.ACTIVE])
        return sessions.annotate(questions_total=Count("test__questions", distinct=True)).order_by(
            "-scheduled_start", "-created_at"
        )

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["participants"] = {}
        return context

    def list(self, request, *args, **kwargs):
        page = self.paginate_queryset(self.filter_queryset(self.get_queryset()))
        sessions = list(page if page is not None else self.get_queryset())
        by_session: dict = {}
        for participant in SessionParticipant.objects.filter(session__in=sessions).select_related("student"):
            by_session.setdefault(participant.session_id, []).append(participant)
        serializer = TeacherSessionSerializer(sessions, many=True, context={"participants": by_session})
        if page is not None:
            return self.get_paginated_response(serializer.data)
        return Response(serializer.data)


class TeacherSessionDetailView(RetrieveAPIView):
    permission_classes = [IsTeacherOrAdmin]
    serializer_class = TeacherSessionSerializer

    def get_object(self):
        session = get_object_or_404(
            sessions_for(self.request.user).annotate(questions_total=Count("test__questions", distinct=True)),
            pk=self.kwargs["pk"],
        )
        session.sync_schedule()
        return session


class TeacherParticipantListView(APIView):
    permission_classes = [IsTeacherOrAdmin]

    def get(self, request, pk):
        session = get_object_or_404(sessions_for(request.user), pk=pk)
        session.sync_schedule()
        participants = list(session.participants.select_related("student"))
        for participant in participants:
            participant.session = session
        return Response({
            "session": TeacherSessionSerializer(session, context={"participants": {session.pk: participants}}).data,
            "participants": ParticipantSerializer(participants, many=True).data,
            "server_time": timezone.now(),
        })


class TeacherParticipantResultView(APIView):
    """A finished student's answers, question by question."""

    permission_classes = [IsTeacherOrAdmin]

    def get(self, request, pk, participant_id):
        session = get_object_or_404(sessions_for(request.user), pk=pk)
        participant = get_object_or_404(session.participants.select_related("student", "attempt"), pk=participant_id)
        participant.session = session
        if participant.live_status != ParticipantStatus.COMPLETED or participant.attempt is None:
            raise NotFound("Результат будет доступен, когда студент завершит тест.")
        rows = []
        for row in result_rows(participant.attempt):
            question = row["question"]
            answer = row["answer"]
            rows.append({
                "number": row["number"],
                "text": question.text,
                "image_url": question.image_url or None,
                "question_type": question.question_type,
                "points": question.points,
                "status": row["status"],
                "selected": [o.text or "Изображение" for o in row["selected"]],
                "answer_text": answer.answer_text if answer else "",
                "correct": [o.text or "Изображение" for o in row["correct_options"]] or list(question.correct_answers or []),
            })
        return Response({
            "student": {"id": participant.student_id, "name": str(participant.student)},
            "score": participant.score,
            "finished_at": participant.finished_at,
            "duration_seconds": participant.duration_seconds,
            "passing_score": session.test.passing_score,
            "questions": rows,
        })
