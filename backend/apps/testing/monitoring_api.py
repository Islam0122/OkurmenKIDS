"""Monitoring API for Teachers, Team Leads and Admins — mounted under
/api/v1/monitoring/ (JWT, like the rest of the LMS API).

    GET overview/                       counters (cards)
    GET attempts/                       live + finished attempts, filtered, paginated
    GET attempts/<id>/                  one attempt: progress, score, violations, event timeline
    GET teachers/                       teacher performance          (Team Lead / Admin)
    GET groups/  ·  groups/<id>/        group analytics
    GET trainers/  ·  trainers/<id>/    per trainer / exam session analytics (+ difficult questions)
    GET questions/?session=<id>         question success rates, hardest first
    GET filters/                        options for the filter bar (only what the user may see)

Every queryset starts from services.monitoring.visible_* — the backend
decides who sees what; the React page only renders it. Clients poll
(every 10–15 s); the views are cheap and read-only.
"""
from __future__ import annotations

from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework.exceptions import PermissionDenied
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.academy.models import Group

from .services import monitoring
from .teacher_api import IsTeacherOrAdmin


class _Pages(PageNumberPagination):
    page_size = 25
    page_size_query_param = "page_size"
    max_page_size = 100


class MonitoringView(APIView):
    permission_classes = [IsTeacherOrAdmin]

    def attempts(self, request, *, close=True):
        attempts = monitoring.visible_attempts(request.user)
        if close:
            monitoring.close_overdue(attempts)
        return monitoring.filter_attempts(attempts, request.query_params)

    def require_team_view(self, request):
        if not monitoring.is_team_view(request.user):
            raise PermissionDenied("Доступно руководителю тренеров и администратору.")


@extend_schema(tags=["Monitoring"])
class OverviewView(MonitoringView):
    def get(self, request):
        sessions = monitoring.visible_sessions(request.user)
        return Response(monitoring.overview(self.attempts(request), sessions))


@extend_schema(tags=["Monitoring"])
class AttemptListView(MonitoringView):
    def get(self, request):
        attempts = monitoring.annotate_rows(self.attempts(request)).order_by("-started_at")
        if request.query_params.get("status") == "in_progress" or request.query_params.get("live") == "1":
            attempts = attempts.order_by("started_at")
        paginator = _Pages()
        page = paginator.paginate_queryset(attempts, request, view=self)
        return paginator.get_paginated_response([monitoring.attempt_row(a) for a in page])


@extend_schema(tags=["Monitoring"])
class AttemptDetailView(MonitoringView):
    def get(self, request, attempt_id):
        visible = monitoring.visible_attempts(request.user)
        get_object_or_404(visible, pk=attempt_id)  # someone else's attempt: 404
        monitoring.close_overdue(visible.filter(pk=attempt_id))
        return Response(monitoring.attempt_detail(monitoring.annotate_rows(visible).get(pk=attempt_id)))


@extend_schema(tags=["Monitoring"])
class TeacherPerformanceView(MonitoringView):
    def get(self, request):
        self.require_team_view(request)
        return Response(monitoring.teacher_performance(self.attempts(request, close=False)))


@extend_schema(tags=["Monitoring"])
class GroupListView(MonitoringView):
    def get(self, request):
        return Response(monitoring.group_stats(self.attempts(request, close=False)))


@extend_schema(tags=["Monitoring"])
class GroupDetailView(MonitoringView):
    def get(self, request, group_id):
        groups = Group.objects.all() if monitoring.is_team_view(request.user) else (
            monitoring._teacher_groups(request.user) or Group.objects.none()
        )
        group = get_object_or_404(groups, pk=group_id)
        return Response(monitoring.group_detail(
            group, self.attempts(request, close=False), monitoring.visible_sessions(request.user),
        ))


@extend_schema(tags=["Monitoring"])
class TrainerListView(MonitoringView):
    def get(self, request):
        return Response(monitoring.trainer_stats(
            monitoring.visible_sessions(request.user), self.attempts(request, close=False),
        ))


def _visible_session(request, session_id):
    return get_object_or_404(monitoring.visible_sessions(request.user).select_related("test"), pk=session_id)


@extend_schema(tags=["Monitoring"])
class TrainerDetailView(MonitoringView):
    def get(self, request, session_id):
        session = _visible_session(request, session_id)
        attempts = self.attempts(request, close=False).filter(session=session)
        stats = monitoring.trainer_stats(monitoring.visible_sessions(request.user).filter(pk=session.pk), attempts)
        return Response({
            "session": {"id": str(session.pk), "title": session.title or session.test.title},
            "stats": stats[0] if stats else None,
            "difficult_questions": monitoring.difficult_questions(session, limit=10),
        })


@extend_schema(tags=["Monitoring"])
class QuestionStatsView(MonitoringView):
    def get(self, request):
        session_id = request.query_params.get("session")
        if not session_id:
            return Response({"detail": "Укажите session."}, status=400)
        return Response(monitoring.difficult_questions(_visible_session(request, session_id)))


@extend_schema(tags=["Monitoring"])
class FilterOptionsView(MonitoringView):
    """Only options inside the user's own scope."""

    def get(self, request):
        sessions = monitoring.visible_sessions(request.user).select_related("test__subject", "group", "teacher__user")
        groups = {s.group_id: s.group.name for s in sessions if s.group_id}
        subjects = {s.test.subject_id: s.test.subject.name for s in sessions if s.test.subject_id}
        teachers = {s.teacher_id: str(s.teacher) for s in sessions if s.teacher_id}
        return Response({
            "groups": [{"id": k, "name": v} for k, v in sorted(groups.items(), key=lambda kv: kv[1])],
            "subjects": [{"id": k, "name": v} for k, v in sorted(subjects.items(), key=lambda kv: kv[1])],
            "teachers": [{"id": k, "name": v} for k, v in sorted(teachers.items(), key=lambda kv: kv[1])]
            if monitoring.is_team_view(request.user) else [],
            "sessions": [
                {"id": str(s.pk), "title": s.title or s.test.title, "mode": "exam" if s.is_exam else "training"}
                for s in sessions.order_by("-created_at")[:200]
            ],
            "team_view": monitoring.is_team_view(request.user),
        })
