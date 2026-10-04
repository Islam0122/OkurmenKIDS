"""Control API — /api/v1/control/...

"Did the responsible trainer fill in everything their lessons require?" —
see services.control. Every endpoint reads the Reports filter vocabulary
(`period`, `start_date`, `end_date`, `program`, `group`, `teacher`,
`subject`; see services.reports.filters) plus `status`.

Access (services.control.access): Admin, superuser, Team Lead or a manager
with the Reports permission sees the whole academy. A Trainer is
always scoped to the lessons they are responsible for — a `teacher` param
from a Trainer is ignored, the same rule the Analytics dashboard applies —
and a lesson that isn't theirs is a 404. Any other account gets 403.
"""
from __future__ import annotations

import dataclasses

from django.shortcuts import get_object_or_404
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Lesson
from .services.control import FILTERABLE_STATUSES, ControlQuery, ControlService, lesson_check
from .services.control.access import ControlAccessDenied, control_scope
from .services.reports import ReportFilterError, ReportFilters
from .services.reports.filters import PERIOD_CHOICES

_PARAMS = [
    OpenApiParameter("period", str, enum=[key for key, _ in PERIOD_CHOICES], description="По умолчанию this_month."),
    OpenApiParameter("start_date", str, description="YYYY-MM-DD, для period=custom."),
    OpenApiParameter("end_date", str, description="YYYY-MM-DD, для period=custom."),
    OpenApiParameter("program", int, description="ID курса."),
    OpenApiParameter("group", int),
    OpenApiParameter("teacher", str, description="ID тренера (для детализации — «none»: занятия без тренера)."),
    OpenApiParameter("subject", int),
    OpenApiParameter("status", str, enum=list(FILTERABLE_STATUSES)),
]


class _ControlView(APIView):
    permission_classes = [IsAuthenticated]

    def viewer_teacher(self, request):
        """None for Admin/manager; the Trainer's own profile otherwise."""
        try:
            return control_scope(request.user)
        except ControlAccessDenied:
            raise PermissionDenied("Раздел «Контроль» доступен администратору, руководителю и тренерам.")

    def service(self, request) -> ControlService:
        teacher = self.viewer_teacher(request)
        try:
            filters = ReportFilters.from_query(request.query_params)
        except ReportFilterError as exc:
            raise ValidationError({"detail": str(exc)}) from exc
        if teacher is not None:
            filters = dataclasses.replace(filters, teacher_id=None)

        status = str(request.query_params.get("status") or "").strip() or None
        if status is not None and status not in FILTERABLE_STATUSES:
            raise ValidationError({"status": [f"Неизвестный статус: «{status}»."]})
        return ControlService(ControlQuery(filters=filters, status=status), restrict_teacher=teacher)


@extend_schema(tags=["Control"], parameters=_PARAMS, responses=OpenApiTypes.OBJECT)
class ControlOverviewView(_ControlView):
    """Summary + one row per (responsible trainer, group), problems first."""

    def get(self, request):
        service = self.service(request)
        return Response({**service.build(), "options": service.options()})


@extend_schema(tags=["Control"], parameters=_PARAMS, responses=OpenApiTypes.OBJECT)
class ControlDetailView(_ControlView):
    """One trainer×group row and every lesson behind it (newest first).
    Needs `group`; `teacher` is a Teacher id or «none»."""

    def get(self, request):
        service = self.service(request)
        group_id = str(request.query_params.get("group") or "").strip()
        if not group_id.isdigit():
            raise ValidationError({"group": ["Укажите группу."]})

        if service.restrict_teacher is not None:
            teacher_id = service.restrict_teacher.id
        else:
            raw = str(request.query_params.get("teacher") or "").strip()
            if raw == "none":
                teacher_id = None
            elif raw.isdigit():
                teacher_id = int(raw)
            else:
                raise ValidationError({"teacher": ["Укажите тренера (ID или «none»)."]})
            # `teacher` picks the row here — not an extra filter on top of it.
            service.filters = dataclasses.replace(service.filters, teacher_id=None)

        detail = service.build_detail(group_id=int(group_id), teacher_id=teacher_id)
        if detail is None:
            return Response({"detail": "За выбранный период занятий нет."}, status=404)
        return Response(detail)


@extend_schema(tags=["Control"], responses=OpenApiTypes.OBJECT)
class ControlLessonView(_ControlView):
    """One lesson's full check: who is responsible, what is filled, which
    students are still missing attendance or a score."""

    def get(self, request, pk: int):
        teacher = self.viewer_teacher(request)
        qs = Lesson.objects.all() if teacher is None else Lesson.objects.for_teacher(teacher)
        lesson = get_object_or_404(qs, pk=pk)
        return Response(lesson_check(lesson))
