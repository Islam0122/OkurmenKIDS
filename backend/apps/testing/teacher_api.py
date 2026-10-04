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

Team Lead (read-only everywhere else) additionally may — see the views below:

    POST /api/v1/teacher/sessions/                 create a session (SessionForm)
    POST /api/v1/teacher/sessions/{id}/start/      start a session they created
    POST /api/v1/teacher/sessions/{id}/take/       take the test themselves
    GET  /api/v1/teacher/my-attempts/              their own attempts and results

Taking the test uses the same student pages (/exam/), grading and timer; the
attempt is owned by the account (StudentAttempt.user) and opened through a
signed handoff link (services.handoff). Trainers get none of these.

Realtime: the project has no WebSocket infrastructure, so the portal polls
these endpoints (a few seconds while a session is live).
"""
from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers
from rest_framework import status as http
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.generics import ListAPIView, RetrieveAPIView
from rest_framework.permissions import BasePermission
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.academy.models import Group
from apps.users.models import User
from apps.users.permissions import is_team_lead

from .forms import SessionForm
from .models import AttemptStatus, ParticipantStatus, SessionParticipant, SessionPhase, SessionTransitionError, StudentAttempt, TestSession
from .services import handoff
from .services.attempts import (
    SUBMIT_GRACE,
    AttemptError,
    attempt_deadline,
    expire_attempt,
    is_passed,
    join,
    result_rows,
)
from .services.grading import attempt_score
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


def _can_run_sessions(user) -> bool:
    """Create / start / take test sessions in the LMS: Admin and Team Lead.
    Never a Trainer (their sessions are run from the admin section)."""
    return _is_admin(user) or is_team_lead(user)


class IsAdminOrTeamLead(BasePermission):
    message = "Доступно только руководителю тренеров или администратору."

    def has_permission(self, request, view) -> bool:
        return _can_run_sessions(request.user)


def can_start(user, session: TestSession) -> bool:
    """Admin: any session. Team Lead: only a session they created."""
    if _is_admin(user):
        return True
    return is_team_lead(user) and session.created_by_id == user.pk


def sessions_for(user):
    """Every session the user may see — the single scoping rule."""
    sessions = TestSession.objects.select_related(
        "test__subject", "group", "teacher__user", "created_by"
    ).filter(group__isnull=False)
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
        user = self.context.get("user")
        return {
            "subject": test.subject.name if test.subject_id else None,
            "teacher_name": str(session.teacher) if session.teacher_id else None,
            "created_by_name": (session.created_by.get_full_name() or session.created_by.username) if session.created_by_id else None,
            "can_start": bool(user) and can_start(user, session) and session.effective_status_at(now) == "created",
            "can_take": bool(user) and _can_run_sessions(user),
            "max_attempts": session.max_attempts_per_student,
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
        context["user"] = self.request.user
        return context

    def post(self, request):
        """Create a test session for a group — Admin and Team Lead only.

        The same form (and rules) as the admin section's «Создание сессии»:
        test, group (all its active students, or `students`), date + start
        time + end time. End time is optional here: without it the session
        lasts the test's time limit (else 60 min)."""
        if not _can_run_sessions(request.user):
            raise PermissionDenied(IsAdminOrTeamLead.message)
        data = _session_form_data(request.data)
        form = SessionForm(data)
        if not form.is_valid():
            errors = {field: [e["message"] for e in items] for field, items in form.errors.get_json_data().items()}
            return Response(errors, status=http.HTTP_400_BAD_REQUEST)
        try:
            session = form.save(teacher=getattr(request.user, "teacher_profile", None))
        except ValidationError as error:
            return Response({"detail": error.messages}, status=http.HTTP_400_BAD_REQUEST)
        session.created_by = request.user
        fields = ["created_by"]
        if session.teacher_id is None and session.group_id is not None:
            # The group's trainer comes from the existing Group → Trainer link
            # (its program for the test's subject) — never asked for twice.
            from apps.academy.services.trainer_assignment import group_trainer

            session.teacher = group_trainer(session.group, session.test.subject)
            fields.append("teacher")
        session.save(update_fields=fields)
        session = sessions_for(request.user).annotate(questions_total=Count("test__questions", distinct=True)).get(pk=session.pk)
        participants = list(session.participants.select_related("student"))
        return Response(
            TeacherSessionSerializer(session, context={"participants": {session.pk: participants}, "user": request.user}).data,
            status=http.HTTP_201_CREATED,
        )

    def list(self, request, *args, **kwargs):
        page = self.paginate_queryset(self.filter_queryset(self.get_queryset()))
        sessions = list(page if page is not None else self.get_queryset())
        by_session: dict = {}
        for participant in SessionParticipant.objects.filter(session__in=sessions).select_related("student"):
            by_session.setdefault(participant.session_id, []).append(participant)
        serializer = TeacherSessionSerializer(sessions, many=True, context={"participants": by_session, "user": request.user})
        if page is not None:
            return self.get_paginated_response(serializer.data)
        return Response(serializer.data)


class TeacherSessionDetailView(RetrieveAPIView):
    permission_classes = [IsTeacherOrAdmin]
    serializer_class = TeacherSessionSerializer

    def get_serializer_context(self):
        return {**super().get_serializer_context(), "user": self.request.user}

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
            "session": TeacherSessionSerializer(
                session, context={"participants": {session.pk: participants}, "user": request.user}
            ).data,
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


def _session_form_data(raw) -> dict:
    """API body → SessionForm data, with the LMS defaults: exam mode, whole
    group, one attempt, and an end time from the test's time limit when
    only the start is given."""
    from datetime import datetime, timedelta

    from .models import SessionType, Test

    data = {
        "title": str(raw.get("title") or ""),
        "test": str(raw.get("test") or ""),
        "group": str(raw.get("group") or ""),
        "session_type": str(raw.get("session_type") or SessionType.EXAM),
        "date": str(raw.get("date") or ""),
        "start_time": str(raw.get("start_time") or ""),
        "end_time": str(raw.get("end_time") or ""),
        "max_attempts": str(raw.get("max_attempts") if raw.get("max_attempts") not in (None, "") else 1),
    }
    students = raw.get("students") or []
    if isinstance(students, list) and students:
        data["students"] = [str(s) for s in students]
    else:
        data["all_students"] = "on"
    if data["date"] and data["start_time"] and not data["end_time"]:
        try:
            start = datetime.strptime(data["start_time"][:5], "%H:%M")
            test = Test.objects.filter(pk=data["test"]).first()
        except (ValueError, ValidationError):
            start, test = None, None
        if start is not None:
            minutes = (test.time_limit_minutes if test is not None else None) or 60
            data["end_time"] = (start + timedelta(minutes=minutes)).strftime("%H:%M")
    return data


class TeacherSessionStartView(APIView):
    """▶ Запустить: Admin any session; Team Lead only one they created."""

    permission_classes = [IsAdminOrTeamLead]

    def post(self, request, pk):
        session = get_object_or_404(sessions_for(request.user), pk=pk)
        if not can_start(request.user, session):
            raise PermissionDenied("Запустить можно только созданную вами сессию.")
        try:
            session.start()
        except SessionTransitionError as error:
            return Response({"detail": " ".join(error.messages)}, status=http.HTTP_400_BAD_REQUEST)
        session = sessions_for(request.user).annotate(questions_total=Count("test__questions", distinct=True)).get(pk=pk)
        return Response(TeacherSessionSerializer(session, context={"participants": {}, "user": request.user}).data)


def _attempt_payload(request, attempt: StudentAttempt) -> dict:
    finished = attempt.status != AttemptStatus.ACTIVE
    score = attempt_score(attempt) if finished and attempt.question_ids else None
    session = attempt.session
    return {
        "id": str(attempt.pk),
        "session": {
            "id": str(session.pk),
            "title": display_title(session),
            "group": {"id": session.group_id, "name": session.group.name} if session.group_id else None,
        },
        "test": {"id": str(session.test_id), "title": session.test.title, "passing_score": session.test.passing_score},
        "status": attempt.status,
        "status_label": attempt.get_status_display(),
        "started_at": attempt.started_at,
        "finished_at": attempt.finished_at,
        "duration_seconds": attempt.duration_seconds,
        "score": {
            "earned": score.earned,
            "possible": score.possible,
            "percent": score.percent,
            "correct": score.correct,
            "wrong": score.answered - score.correct - score.pending,
            "pending": score.pending,
            "unanswered": score.total_questions - score.answered,
            "total_questions": score.total_questions,
            "passed": is_passed(attempt, score),
        } if score is not None else None,
        # Short-lived signed links to the student test pages (services.handoff).
        "take_url": handoff.take_url(request, attempt) if not finished else None,
        "result_url": handoff.result_url(request, attempt) if finished else None,
    }


class TeacherSessionTakeView(APIView):
    """«Пройти тест»: the Team Lead (or Admin) takes the session's test
    themselves — same join rules, timer and grading as a student; the
    attempt belongs to their account. Returns the link to the test page."""

    permission_classes = [IsAdminOrTeamLead]

    def post(self, request, pk):
        session = get_object_or_404(sessions_for(request.user), pk=pk)
        session.sync_schedule()
        try:
            attempt = join(session, user=request.user)
        except AttemptError as error:
            return Response({"detail": error.messages[0]}, status=http.HTTP_400_BAD_REQUEST)
        return Response(_attempt_payload(request, attempt))


class MyAttemptsView(APIView):
    """«Мои результаты»: only the requesting account's own attempts
    (StudentAttempt.user) — never anyone else's. `?session=` narrows it."""

    permission_classes = [IsAdminOrTeamLead]

    def get(self, request):
        attempts = (
            StudentAttempt.objects.filter(user=request.user)
            .select_related("session__test", "session__group")
            .prefetch_related("answers")
            .order_by("-started_at")
        )
        session_id = request.query_params.get("session")
        if session_id:
            attempts = attempts.filter(session_id=session_id)
        attempts = list(attempts[:100])
        now = timezone.now()
        for attempt in attempts:
            # Same lazy rule as the test pages: an unfinished attempt whose
            # time (or session) is over is expired, not «in progress» forever.
            if attempt.status == AttemptStatus.ACTIVE:
                deadline = attempt_deadline(attempt)
                session_over = attempt.session.effective_status in TestSession.ENDED_STATUSES
                if (deadline and now > deadline + SUBMIT_GRACE) or session_over:
                    expire_attempt(attempt)
        return Response([_attempt_payload(request, attempt) for attempt in attempts])
