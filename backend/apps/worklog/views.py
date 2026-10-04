from __future__ import annotations

from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import status as http
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.academy.models import Group, Student
from apps.users.models import Teacher

from .models import OPEN_STATUSES, Priority, TaskStatus, TeamLeadReport, WorkLogEntry, WorkType
from .permissions import WorkLogAccess
from .schemas import kinds_payload
from .serializers import TeamLeadReportSerializer, WorkLogEntrySerializer, refresh_metrics


def _date(value):
    from datetime import date

    try:
        return date.fromisoformat(value) if value else None
    except ValueError:
        return None


@extend_schema(tags=["Work log"])
class WorkLogEntryViewSet(viewsets.ModelViewSet):
    """«Рабочий журнал» records and tasks. Filters: date_from, date_to,
    work_type, status (incl. «overdue», computed), priority, entry_kind,
    group, teacher, student, report, mine=1, open=1 (still waiting)."""

    serializer_class = WorkLogEntrySerializer
    permission_classes = [WorkLogAccess]
    filter_backends = [SearchFilter, OrderingFilter]
    search_fields = ["title", "description", "result", "problem", "next_action", "responsible", "with_whom"]
    ordering_fields = ["date", "deadline", "priority", "created_at"]

    def get_queryset(self):
        qs = WorkLogEntry.objects.select_related("author", "group", "teacher__user", "student")
        p = self.request.query_params
        today = timezone.localdate()
        if (d := _date(p.get("date_from"))):
            qs = qs.filter(date__gte=d)
        if (d := _date(p.get("date_to"))):
            qs = qs.filter(date__lte=d)
        for field in ("work_type", "priority", "entry_kind"):
            if p.get(field):
                qs = qs.filter(**{field: p[field]})
        for field in ("group", "teacher", "student", "report"):
            if (p.get(field) or "").isdigit():
                qs = qs.filter(**{f"{field}_id": int(p[field])})
        if p.get("mine") == "1":
            qs = qs.filter(author=self.request.user)
        overdue_q = Q(status__in=OPEN_STATUSES, deadline__lt=today)
        status = p.get("status")
        if status == TaskStatus.OVERDUE:
            qs = qs.filter(overdue_q)
        elif status in (TaskStatus.NEW, TaskStatus.IN_PROGRESS):
            qs = qs.filter(status=status).exclude(overdue_q)
        elif status:
            qs = qs.filter(status=status)
        if p.get("open") == "1":
            qs = qs.filter(status__in=OPEN_STATUSES)
        return qs.order_by("-date", "-time_from", "-id")

    def perform_create(self, serializer):
        serializer.save(author=self.request.user)

    @action(detail=False, methods=["get"], url_path="summary")
    def summary(self, request):
        """For the page header: open / overdue tasks, today's records."""
        today = timezone.localdate()
        mine = WorkLogEntry.objects.filter(author=request.user)
        open_qs = mine.filter(status__in=OPEN_STATUSES).exclude(next_action="", entry_kind=WorkLogEntry.Kind.LOG)
        return Response({
            "today": mine.filter(date=today, entry_kind=WorkLogEntry.Kind.LOG).count(),
            "open": open_qs.count(),
            "overdue": open_qs.filter(deadline__lt=today).count(),
            "due_today": open_qs.filter(deadline=today).count(),
        })


@extend_schema(tags=["Work log"])
class TeamLeadReportViewSet(viewsets.ModelViewSet):
    """Team Lead reports (daily … monthly). LMS figures are computed on
    create into `metrics`; POST {id}/recalculate/ refreshes them."""

    serializer_class = TeamLeadReportSerializer
    permission_classes = [WorkLogAccess]
    filter_backends = [OrderingFilter]
    ordering_fields = ["date", "created_at"]

    def get_queryset(self):
        qs = TeamLeadReport.objects.select_related("author", "group", "teacher__user", "student", "lesson")
        p = self.request.query_params
        if p.get("kind"):
            qs = qs.filter(kind=p["kind"])
        if p.get("status"):
            qs = qs.filter(status=p["status"])
        for field in ("group", "teacher", "student"):
            if (p.get(field) or "").isdigit():
                qs = qs.filter(**{f"{field}_id": int(p[field])})
        if p.get("mine") == "1":
            qs = qs.filter(author=self.request.user)
        return qs.order_by("-date", "-id")

    def get_serializer_context(self):
        return {**super().get_serializer_context(), "detail": self.action != "list"}

    def perform_create(self, serializer):
        report = serializer.save(author=self.request.user)
        refresh_metrics(report)

    def perform_update(self, serializer):
        report = serializer.save()
        # Changing what the report is about changes its figures.
        if {"period_start", "period_end", "date", "teacher", "student", "lesson"} & set(serializer.validated_data):
            refresh_metrics(report)

    @action(detail=True, methods=["post"], url_path="recalculate")
    def recalculate(self, request, pk=None):
        report = self.get_object()
        if report.author_id != request.user.pk:
            return Response({"detail": "Пересчитать может только автор отчёта."}, status=http.HTTP_403_FORBIDDEN)
        refresh_metrics(report)
        return Response(self.get_serializer(report).data)


@extend_schema(tags=["Work log"])
class WorkLogOptionsView(APIView):
    """The choices of every form: report kinds with their fields, work
    types, statuses, priorities."""

    permission_classes = [WorkLogAccess]

    def get(self, request):
        return Response({
            "report_kinds": kinds_payload(),
            "work_types": [{"value": v, "label": label} for v, label in WorkType.choices],
            "statuses": [{"value": v, "label": label} for v, label in TaskStatus.choices],
            "priorities": [{"value": v, "label": label} for v, label in Priority.choices],
            # Pickers of the forms (journal «с кем», report links).
            "groups": [
                {"id": g.pk, "name": g.name, "status": g.status}
                for g in Group.objects.order_by("-status", "name")
            ],
            "teachers": [
                {"id": t.pk, "name": str(t), "is_active": t.is_active}
                for t in Teacher.objects.select_related("user").order_by("-is_active", "user__first_name", "user__last_name")
            ],
            "students": [
                {"id": s.pk, "name": str(s), "group": s.group_id}
                for s in Student.objects.filter(status=Student.Status.ACTIVE).order_by("last_name", "first_name")
            ],
        })
