"""«Контроль тренеров» — the Admin Panel section: every trainer at a glance,
one trainer's groups and unfilled lessons, and Excel/PDF exports.

Thin views: every number, status and label comes from services.control
(ControlService); these only parse the query string and render. Access is
decided on the backend by services.control.access (Admin / superuser /
manager with the Reports permission see everyone; a trainer only
themselves), not just by the sidebar entry.
"""
from __future__ import annotations

import dataclasses

from django.contrib import admin
from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils.http import urlencode

from apps.users.models import Teacher

from .services.control import FILTERABLE_STATUSES, STATUS_LABELS, ControlQuery, ControlService
from .services.control.access import ControlAccessDenied, control_scope
from .services.control.export import build_control_excel, build_control_pdf, excel_filename, pdf_filename
from .services.reports import ReportFilterError, ReportFilters, period_options

SORT_OPTIONS = [
    ("status", "Сначала проблемы"),
    ("name", "По имени"),
    ("-groups", "По количеству групп"),
    ("-unfilled", "По незаполненным урокам"),
    ("attendance", "По посещаемости"),
    ("homework", "По ДЗ"),
    ("grades", "По баллам"),
]


def _viewer(request) -> Teacher | None:
    try:
        return control_scope(request.user)
    except ControlAccessDenied:
        raise PermissionDenied("Раздел «Контроль тренеров» доступен администратору и руководителю.")


def _service(request, restrict: Teacher | None) -> tuple[ControlService, str | None]:
    error = None
    try:
        filters = ReportFilters.from_query(request.GET)
    except ReportFilterError as exc:
        filters, error = ReportFilters.default(), str(exc)
    if restrict is not None:
        filters = dataclasses.replace(filters, teacher_id=None)
    status = (request.GET.get("status") or "").strip() or None
    if status is not None and status not in FILTERABLE_STATUSES:
        status, error = None, error or f"Неизвестный статус: «{status}»."
    return ControlService(ControlQuery(filters=filters, status=status), restrict_teacher=restrict), error


def _context(request, service: ControlService, *, title: str, error: str | None) -> dict:
    filters = service.filters
    query = filters.as_query()
    if service.query.status:
        query["status"] = service.query.status
    qs = urlencode(query)
    sort = request.GET.get("sort") or "status"
    export_qs = urlencode({**query, "sort": sort})
    return {
        **admin.site.each_context(request),
        "title": title,
        "filters": filters,
        "filter_query": qs,
        "selected": {key: str(value) for key, value in query.items()},
        "active_filters": sum(
            1 for value in (filters.group_id, filters.teacher_id, filters.subject_id, service.query.status) if value
        ),
        "period_choices": period_options(filters.today),
        "options": service.options(),
        "status_choices": [(key, STATUS_LABELS[key]) for key in FILTERABLE_STATUSES],
        "sort": sort,
        "sort_options": SORT_OPTIONS,
        "is_own_scope": service.restrict_teacher is not None,
        "excel_url": f"{reverse('admin:academy_control_export_excel')}?{export_qs}",
        "pdf_url": f"{reverse('admin:academy_control_export_pdf')}?{export_qs}",
        "error": error,
    }


def control_teachers_view(request):
    restrict = _viewer(request)
    service, error = _service(request, restrict)
    context = _context(request, service, title="Контроль тренеров", error=error)
    if not error:
        context["data"] = service.build_teachers(sort=context["sort"])
    return render(request, "admin/academy/control/teachers.html", context)


def control_teacher_detail_view(request, teacher_id: int):
    restrict = _viewer(request)
    if restrict is not None and restrict.id != teacher_id:
        raise Http404
    teacher = get_object_or_404(Teacher.objects.select_related("user"), pk=teacher_id)
    service, error = _service(request, restrict)
    context = _context(request, service, title=f"Контроль: {teacher}", error=error)
    context["teacher_obj"] = teacher
    if not error:
        context["detail"] = service.build_teacher_detail(teacher)
    return render(request, "admin/academy/control/teacher_detail.html", context)


def _export(request, build, content_type: str, filename) -> HttpResponse:
    restrict = _viewer(request)
    service, error = _service(request, restrict)
    if error:
        return HttpResponse(error, status=400, content_type="text/plain; charset=utf-8")
    content = build(service.export_data(sort=request.GET.get("sort") or "status"))
    response = HttpResponse(content, content_type=content_type)
    response["Content-Disposition"] = f'attachment; filename="{filename(service.filters)}"'
    return response


def control_export_excel_view(request):
    return _export(request, build_control_excel,
                   "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", excel_filename)


def control_export_pdf_view(request):
    return _export(request, build_control_pdf, "application/pdf", pdf_filename)
