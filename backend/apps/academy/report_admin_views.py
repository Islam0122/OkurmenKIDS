"""Reports — the Admin Panel's Reports section: Overview, Groups, Teachers
and their detail pages.

Thin views: every number comes from services.reports (the same functions
the /api/v1/reports/ endpoints and the PDF/Excel exports use), these only
parse the query string, paginate and render. Admin-only, enforced here on
the backend (`_require_admin`), not just by hiding the sidebar entry.
"""
from __future__ import annotations

from django.contrib import admin
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils.http import urlencode

from apps.users.models import Teacher

from .admin_views import _is_admin_user
from .models import Group
from .services.reports import (
    ReportFilterError,
    ReportFilters,
    build_group_detail,
    build_group_rows,
    build_overview,
    build_teacher_detail,
    build_teacher_rows,
    filter_options,
    group_student_rows,
    period_options,
)
from .services.reports.kpi import weights_description
from .services.reports.table import paginate_groups, paginate_students, paginate_teachers

# (key, label, Lucide icon, url name)
TABS = [
    ("overview", "Обзор", "chart-column", "admin:academy_reports_overview"),
    ("groups", "Группы", "layers", "admin:academy_reports_groups"),
    ("teachers", "Тренеры", "graduation-cap", "admin:academy_reports_teachers"),
]


def _require_admin(request) -> None:
    if not _is_admin_user(request.user):
        raise PermissionDenied("Раздел «Отчёты» доступен только администратору.")


def _parse_filters(request) -> tuple[ReportFilters, str | None]:
    try:
        return ReportFilters.from_query(request.GET), None
    except ReportFilterError as exc:
        return ReportFilters.default(), str(exc)


def _context(request, filters: ReportFilters, *, tab: str, title: str, error: str | None = None) -> dict:
    query = filters.as_query()
    qs = urlencode(query)
    return {
        **admin.site.each_context(request),
        "title": title,
        "tab": tab,
        "tabs": [
            {"key": key, "label": label, "icon": icon, "url": f"{reverse(name)}?{qs}", "active": key == tab}
            for key, label, icon, name in TABS
        ],
        "filters": filters,
        "filter_query": qs,
        "active_filters": sum(
            1 for value in (filters.course_id, filters.group_id, filters.teacher_id, filters.subject_id) if value
        ),
        "selected": {key: str(value) for key, value in query.items()},
        "period_choices": period_options(filters.today),
        "options": filter_options(),
        "kpi_weights": weights_description(),
        "pdf_url": f"{reverse('reports-export-pdf')}?{qs}",
        "excel_url": f"{reverse('reports-export-excel')}?{qs}",
        "error": error,
    }


def _kpi_components(metrics: dict) -> list[dict]:
    """KPI components in display order with their configured weight."""
    return [{**w, "value": metrics[w["key"]]} for w in weights_description()]


def reports_overview_view(request):
    _require_admin(request)
    filters, error = _parse_filters(request)
    context = _context(request, filters, tab="overview", title="Отчёты академии", error=error)
    if not error:
        context["overview"] = build_overview(filters)
    return render(request, "admin/academy/reports/overview.html", context)


def reports_groups_view(request):
    _require_admin(request)
    filters, error = _parse_filters(request)
    context = _context(request, filters, tab="groups", title="Отчёт по группам", error=error)
    context["group_statuses"] = Group.Status.choices
    context["selected_status"] = request.GET.get("status", "")
    if not error:
        context["page"] = paginate_groups(build_group_rows(filters), request.GET)
    return render(request, "admin/academy/reports/groups.html", context)


def reports_group_detail_view(request, group_id: int):
    _require_admin(request)
    group = get_object_or_404(Group.objects.select_related("course"), pk=group_id)
    filters, error = _parse_filters(request)
    context = _context(request, filters, tab="groups", title=f"Группа: {group.name}", error=error)
    context["group_obj"] = group
    if not error:
        context["detail"] = build_group_detail(group, filters)
        context["kpi_components"] = _kpi_components(context["detail"]["metrics"])
        context["page"] = paginate_students(group_student_rows(group, filters), request.GET)
    return render(request, "admin/academy/reports/group_detail.html", context)


def reports_teachers_view(request):
    _require_admin(request)
    filters, error = _parse_filters(request)
    context = _context(request, filters, tab="teachers", title="Отчёт по тренерам", error=error)
    if not error:
        context["page"] = paginate_teachers(build_teacher_rows(filters), request.GET)
    return render(request, "admin/academy/reports/teachers.html", context)


def reports_teacher_detail_view(request, teacher_id: int):
    _require_admin(request)
    teacher = get_object_or_404(Teacher.objects.select_related("user"), pk=teacher_id)
    filters, error = _parse_filters(request)
    context = _context(request, filters, tab="teachers", title=f"Тренер: {teacher}", error=error)
    context["teacher_obj"] = teacher
    if not error:
        context["detail"] = build_teacher_detail(teacher, filters)
        context["kpi_components"] = _kpi_components(context["detail"]["metrics"])
    return render(request, "admin/academy/reports/teacher_detail.html", context)
