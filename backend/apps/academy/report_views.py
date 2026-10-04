"""Reports API — /api/v1/reports/...

Admin and Team Lead (`IsAdminOrTeamLeadReadOnly` — every endpoint here is a
GET, so a Team Lead reads all of it), the same gate as the Academy Monthly
Report API: the academy-wide report is management
data, and a Teacher already has their own scoped reports (monthly-reports,
analytics). Every endpoint reads the same query parameters:

    period       today | this_week | this_month (default) | last_month |
                 this_quarter | custom
    start_date   YYYY-MM-DD (with period=custom)
    end_date     YYYY-MM-DD (with period=custom)
    program      Course id
    group        Group id
    teacher      Teacher id
    subject      Subject id

List endpoints also take `q` (search), `sort` (e.g. `-kpi`), `page`,
`page_size`. Nothing is stored — see services.reports.
"""
from __future__ import annotations

from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.users.models import Subject, Teacher
from apps.users.permissions import IsAdminOrTeamLeadReadOnly

from .models import Group
from .services.reports import (
    build_all_student_rows,
    PERIOD_CHOICES,
    ReportFilterError,
    ReportFilters,
    build_full_report,
    build_group_detail,
    build_group_rows,
    build_overview,
    build_subject_detail,
    build_subject_rows,
    build_teacher_detail,
    build_teacher_rows,
    describe_filters,
    filter_options,
    group_student_rows,
    period_options,
)
from .services.reports.service import report_group_ids
from .services.reports.excel import build_reports_excel, excel_filename
from .services.reports.kpi import weights_description
from .services.reports.pdf import build_reports_pdf, pdf_filename
from .services.reports.table import paginate_groups, paginate_students, paginate_subjects, paginate_teachers

_FILTER_PARAMS = [
    OpenApiParameter("period", str, enum=[key for key, _ in PERIOD_CHOICES], description="По умолчанию this_month."),
    OpenApiParameter("start_date", str, description="YYYY-MM-DD, для period=custom."),
    OpenApiParameter("end_date", str, description="YYYY-MM-DD, для period=custom."),
    OpenApiParameter("program", int, description="ID курса (программы)."),
    OpenApiParameter("group", int),
    OpenApiParameter("teacher", int),
    OpenApiParameter("subject", int),
]
_TABLE_PARAMS = [
    OpenApiParameter("q", str, description="Поиск."),
    OpenApiParameter("sort", str, description="Поле сортировки, «-» — по убыванию (например -kpi)."),
    OpenApiParameter("page", int),
    OpenApiParameter("page_size", int),
]


class _ReportsView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrTeamLeadReadOnly]

    def filters(self, request) -> ReportFilters:
        try:
            return ReportFilters.from_query(request.query_params)
        except ReportFilterError as exc:
            raise ValidationError({"detail": str(exc)}) from exc


@extend_schema(tags=["Reports"], parameters=_FILTER_PARAMS)
class ReportsOverviewView(_ReportsView):
    def get(self, request):
        return Response(build_overview(self.filters(request)))


@extend_schema(tags=["Reports"])
class ReportsFilterOptionsView(_ReportsView):
    def get(self, request):
        return Response({
            "periods": [{"key": key, "label": label} for key, label in period_options(timezone.localdate())],
            **filter_options(),
            "kpi_weights": weights_description(),
        })


@extend_schema(
    tags=["Reports"],
    parameters=_FILTER_PARAMS + _TABLE_PARAMS + [
        OpenApiParameter("status", str, enum=["active", "paused", "completed", "cancelled"], description="Статус группы."),
    ],
)
class ReportsGroupsView(_ReportsView):
    def get(self, request):
        filters = self.filters(request)
        page = paginate_groups(build_group_rows(filters), request.query_params)
        return Response({"filters": filters.as_dict(), **page.as_dict()})


@extend_schema(tags=["Reports"], parameters=_FILTER_PARAMS + _TABLE_PARAMS)
class ReportsGroupDetailView(_ReportsView):
    def get(self, request, pk: int):
        group = get_object_or_404(Group.objects.select_related("course"), pk=pk)
        filters = self.filters(request)
        detail = build_group_detail(group, filters)
        page = paginate_students(group_student_rows(group, filters), request.query_params)
        return Response({**detail, "students_list": page.as_dict()})


@extend_schema(tags=["Reports"], parameters=_FILTER_PARAMS + _TABLE_PARAMS)
class ReportsSubjectsView(_ReportsView):
    def get(self, request):
        filters = self.filters(request)
        page = paginate_subjects(build_subject_rows(filters), request.query_params)
        return Response({"filters": filters.as_dict(), **page.as_dict()})


@extend_schema(tags=["Reports"], parameters=_FILTER_PARAMS)
class ReportsSubjectDetailView(_ReportsView):
    def get(self, request, pk: int):
        subject = get_object_or_404(Subject, pk=pk)
        return Response(build_subject_detail(subject, self.filters(request)))


@extend_schema(tags=["Reports"], parameters=_FILTER_PARAMS + _TABLE_PARAMS)
class ReportsStudentsView(_ReportsView):
    """Every student of the groups in the report's scope — attendance,
    homework, average score, progress (same figures as a group's student
    list, academy-wide)."""

    def get(self, request):
        filters = self.filters(request)
        page = paginate_students(build_all_student_rows(filters, report_group_ids(filters)), request.query_params)
        return Response({"filters": filters.as_dict(), **page.as_dict()})


@extend_schema(tags=["Reports"], parameters=_FILTER_PARAMS + _TABLE_PARAMS)
class ReportsTeachersView(_ReportsView):
    def get(self, request):
        filters = self.filters(request)
        page = paginate_teachers(build_teacher_rows(filters), request.query_params)
        return Response({"filters": filters.as_dict(), **page.as_dict()})


@extend_schema(tags=["Reports"], parameters=_FILTER_PARAMS)
class ReportsTeacherDetailView(_ReportsView):
    def get(self, request, pk: int):
        teacher = get_object_or_404(Teacher.objects.select_related("user"), pk=pk)
        return Response(build_teacher_detail(teacher, self.filters(request)))


def _attachment(content: bytes, content_type: str, filename: str) -> HttpResponse:
    response = HttpResponse(content, content_type=content_type)
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


@extend_schema(tags=["Reports"], parameters=_FILTER_PARAMS, responses={200: {"type": "string", "format": "binary"}})
class ReportsExportPdfView(_ReportsView):
    def get(self, request):
        filters = self.filters(request)
        return _attachment(build_reports_pdf(build_full_report(filters)), "application/pdf", pdf_filename(filters))


@extend_schema(tags=["Reports"], parameters=_FILTER_PARAMS, responses={200: {"type": "string", "format": "binary"}})
class ReportsExportExcelView(_ReportsView):
    def get(self, request):
        filters = self.filters(request)
        content = build_reports_excel(build_full_report(filters), describe_filters(filters))
        return _attachment(
            content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", excel_filename(filters)
        )
