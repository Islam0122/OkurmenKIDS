"""API кабинета операционного директора — /api/v1/operations/…

Доступ: Операционный директор, Директор, Администратор (`CanOversee`).
Всё — только чтение существующих данных LMS, кроме KPI-целей, проблем и
настроек модуля. Фильтры каждой страницы: period (today / yesterday /
this_week / this_month / last_month / custom + start_date, end_date),
department, role (должность), employee — см. services.period.
"""
from __future__ import annotations

import dataclasses
import datetime as dt

from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.marketing.serializers import can_view_budget
from apps.users.models import Teacher, User

from . import kpi_registry
from .departments import Department, choices as department_choices, roles_of
from .models import (
    ACTIVE_ISSUE_STATUSES,
    EmployeeReport,
    IssueKind,
    IssueStatus,
    KPIPeriod,
    KPITarget,
    OperationalIssue,
    OperationsSettings,
    Priority,
    ReportExport,
    ReportKind,
)
from .permissions import CanOversee
from .serializers import (
    IssueCreateSerializer,
    IssueDetailSerializer,
    IssueEventSerializer,
    IssueSerializer,
    KPITargetSerializer,
    SettingsSerializer,
    person,
)
from .services import academy, exports, issues as issue_service, org, overview, period as period_service, staff
from .task_views import OpsPagination

PERMISSIONS = [IsAuthenticated, CanOversee]
TAGS = ["Operations"]


def _filters(request, default="this_month"):
    return period_service.from_query(request.query_params, default=default)


def _choices(enum) -> list[dict]:
    return [{"value": v, "label": label} for v, label in enum.choices]


class _OpsView(APIView):
    permission_classes = PERMISSIONS


@extend_schema(tags=TAGS, responses=OpenApiTypes.OBJECT)
class MetaView(_OpsView):
    """Справочники кабинета: периоды, отделы, должности, сотрудники, предметы,
    группы, показатели KPI, виды проблем и отчётов."""

    def get(self, request):
        from apps.academy.models import Group
        from apps.users.models import Subject

        return Response({
            "periods": [{"value": v, "label": label} for v, label in period_service.PERIODS],
            "departments": department_choices(),
            "roles": [{"value": v, "label": label, "department": org.department_of(User(role=v))}
                      for v, label in User.Role.choices],
            "employees": [person(u) for u in User.objects.filter(is_active=True).order_by("first_name", "last_name")],
            "subjects": list(Subject.objects.filter(is_active=True).values("id", "name")),
            "groups": list(Group.objects.filter(status=Group.Status.ACTIVE).order_by("name").values("id", "name")),
            "metrics": [kpi_registry.describe(m) for m in kpi_registry.METRICS.values()],
            "kpi_periods": _choices(KPIPeriod),
            "issue_kinds": _choices(IssueKind),
            "issue_statuses": _choices(IssueStatus),
            "priorities": _choices(Priority),
            "report_kinds": [{"value": v, "label": label} for v, label in exports.KINDS],
            "employee_report_kinds": _choices(ReportKind),
            "can_view_finance": can_view_budget(request.user),
            "today": timezone.localdate(),
        })


@extend_schema(tags=TAGS, responses=OpenApiTypes.OBJECT)
class DashboardView(_OpsView):
    def get(self, request):
        return Response(overview.dashboard(_filters(request, "today")))


@extend_schema(tags=TAGS, responses=OpenApiTypes.OBJECT)
class DepartmentsView(_OpsView):
    def get(self, request):
        return Response({"departments": org.department_overview(_filters(request))})


@extend_schema(tags=TAGS, responses=OpenApiTypes.OBJECT)
class DepartmentDetailView(_OpsView):
    """Отдел: сводка, сотрудники (задачи, отчёты, посещаемость), KPI отдела."""

    def get(self, request, key):
        if key not in Department.values:
            return Response({"detail": "Отдел не найден."}, status=status.HTTP_404_NOT_FOUND)
        f = dataclasses.replace(_filters(request), department=key)
        summary = next(d for d in org.department_overview(f) if d["key"] == key)
        kpi = overview.kpi_overview(f, can_see_finance=can_view_budget(request.user))
        return Response({"department": summary, "employees": org.employees(f), "kpi": kpi["departments"][0],
                         "roles": [{"value": r, "label": User.Role(r).label} for r in roles_of(key)]})


@extend_schema(tags=TAGS, responses=OpenApiTypes.OBJECT)
class EmployeesView(_OpsView):
    def get(self, request):
        f = _filters(request)
        rows = org.employees(f, search=request.query_params.get("q", "").strip(),
                             include_inactive=request.query_params.get("inactive") == "1")
        return Response({"filters": f.as_dict(), "employees": rows, "total": len(rows)})


@extend_schema(tags=TAGS, responses=OpenApiTypes.OBJECT)
class EmployeeProfileView(_OpsView):
    def get(self, request, pk):
        user = get_object_or_404(User, pk=pk)
        return Response(org.employee_profile(user, _filters(request)))


def _int_param(request, name):
    value = request.query_params.get(name)
    if value in (None, ""):
        return None
    if not str(value).isdigit():
        raise ValidationError({name: "Ожидается число."})
    return int(value)


@extend_schema(tags=TAGS, responses=OpenApiTypes.OBJECT)
class TrainersView(_OpsView):
    """Все тренеры в одной таблице: журнал, посещаемость, ДЗ, KPI, отчёты,
    задачи и предупреждения. Фильтры: subject, group, kpi_level,
    journal_status, warning, q и период."""

    def get(self, request):
        f = _filters(request)
        rows = academy.trainer_rows(f, subject_id=_int_param(request, "subject"), group_id=_int_param(request, "group"))
        rows = academy.filter_trainer_rows(rows, request.query_params)
        return Response({"filters": f.as_dict(), "summary": academy.trainer_summary(rows), "trainers": rows,
                         "warning_labels": academy.WARNING_LABELS})


@extend_schema(tags=TAGS, responses=OpenApiTypes.OBJECT)
class TrainerDetailView(_OpsView):
    def get(self, request, pk):
        teacher = get_object_or_404(Teacher.objects.select_related("user"), pk=pk)
        return Response(academy.trainer_detail(teacher, _filters(request)))


@extend_schema(tags=TAGS, responses=OpenApiTypes.OBJECT)
class TeamLeadsView(_OpsView):
    def get(self, request):
        f = _filters(request)
        return Response({"filters": f.as_dict(), "team_leads": academy.team_lead_rows(f),
                         "assistants": academy.assistant_rows(f)})


@extend_schema(tags=TAGS, responses=OpenApiTypes.OBJECT)
class AssistantsView(_OpsView):
    def get(self, request):
        f = _filters(request)
        return Response({"filters": f.as_dict(), "assistants": academy.assistant_rows(f),
                         "students": academy.students_overview(f)})


@extend_schema(tags=TAGS, responses=OpenApiTypes.OBJECT)
class ProblemStudentsView(_OpsView):
    def get(self, request):
        f = _filters(request, "this_month")
        group = _int_param(request, "group")
        rows = academy.problem_students_for(f, group_ids=[group] if group else None)
        settings_ = OperationsSettings.load()
        return Response({"filters": f.as_dict(), "students": rows, "summary": academy.students_overview(f),
                         "groups": academy.problem_groups(f, settings_.problem_group_attendance)})


@extend_schema(tags=TAGS, responses=OpenApiTypes.OBJECT)
class SalesView(_OpsView):
    def get(self, request):
        data = org.sales_overview(_filters(request))
        if not can_view_budget(request.user):
            data["department"].pop("revenue", None)
            for row in data["managers"]:
                row["funnel"].pop("revenue", None)
        return Response(data)


@extend_schema(tags=TAGS, responses=OpenApiTypes.OBJECT)
class HeadOfSalesView(_OpsView):
    def get(self, request):
        data = org.head_of_sales(_filters(request))
        if not can_view_budget(request.user):
            data["department"].pop("revenue", None)
            for row in data["managers"]:
                row["funnel"].pop("revenue", None)
        return Response(data)


@extend_schema(tags=TAGS, responses=OpenApiTypes.OBJECT)
class MarketingView(_OpsView):
    def get(self, request):
        return Response(org.marketing_overview(_filters(request), with_budget=can_view_budget(request.user)))


@extend_schema(tags=TAGS, responses=OpenApiTypes.OBJECT)
class HRView(_OpsView):
    def get(self, request):
        return Response(org.hr_overview(_filters(request)))


@extend_schema(tags=TAGS, responses=OpenApiTypes.OBJECT)
class StaffAttendanceView(_OpsView):
    """Посещаемость сотрудников из существующего учёта прихода/ухода по QR:
    строки сотрудник × день, сводка, по отделам и по сотрудникам. Фильтр
    status — present / late / absent / not_checked_out / day_off …"""

    def get(self, request):
        f = _filters(request, "today")
        users = staff.tracked_users(f.users_qs())
        if request.query_params.get("q"):
            q = request.query_params["q"].lower()
            users = [u for u in users if q in (u.get_full_name() or u.username).lower()]
        rows = staff.rows(users, f.start, f.elapsed_end)
        wanted = request.query_params.get("status")
        serialized = [staff.serialize_row(r) for r in rows if not wanted or staff.ops_status(r) == wanted]
        by_department, by_employee = {}, {}
        for r in rows:
            by_department.setdefault(org.department_of(r.user), []).append(r)
            by_employee.setdefault(r.user.pk, []).append(r)
        return Response({
            "filters": f.as_dict(),
            "summary": staff.summarize(rows),
            "rows": sorted(serialized, key=lambda r: (r["date"], r["user"]["full_name"]), reverse=True)[:2000],
            "departments": [{"key": key, "label": Department(key).label, **staff.summarize(items)}
                            for key, items in sorted(by_department.items())],
            "employees": [{"user": staff.serialize_row(items[0])["user"], **staff.summarize(items)}
                          for items in by_employee.values()],
            "statuses": [{"value": k, "label": v} for k, v in staff.LABELS.items()],
            "leave_tracking": False,
        })


@extend_schema(tags=TAGS, responses=OpenApiTypes.OBJECT)
class DailyControlView(_OpsView):
    def get(self, request):
        raw = request.query_params.get("date")
        try:
            day = dt.date.fromisoformat(raw) if raw else timezone.localdate()
        except ValueError:
            raise ValidationError({"date": "Дата в формате ГГГГ-ММ-ДД."})
        if day > timezone.localdate():
            raise ValidationError({"date": "День ещё не наступил."})
        return Response(overview.daily_control(day))


@extend_schema(tags=TAGS, responses=OpenApiTypes.OBJECT)
class KPIOverviewView(_OpsView):
    def get(self, request):
        return Response(overview.kpi_overview(_filters(request), can_see_finance=can_view_budget(request.user)))


@extend_schema(tags=TAGS, responses=OpenApiTypes.OBJECT)
class KPIHistoryView(_OpsView):
    def get(self, request):
        metric = request.query_params.get("metric")
        if metric not in kpi_registry.METRICS:
            raise ValidationError({"metric": "Неизвестный показатель."})
        if kpi_registry.METRICS[metric].financial and not can_view_budget(request.user):
            return Response({"detail": "Финансовый показатель вам недоступен."}, status=status.HTTP_403_FORBIDDEN)
        period = request.query_params.get("period_type") or "monthly"
        if period not in KPIPeriod.values:
            raise ValidationError({"period_type": "daily, weekly или monthly."})
        employee = get_object_or_404(User, pk=_int_param(request, "employee")) if request.query_params.get(
            "employee") else None
        department = request.query_params.get("department") or None
        if department and department not in Department.values:
            raise ValidationError({"department": "Неизвестный отдел."})
        points = min(_int_param(request, "points") or 6, 24)
        return Response({"metric": kpi_registry.describe(kpi_registry.METRICS[metric]), "period_type": period,
                         "history": overview.kpi_history(metric, department=department, employee=employee,
                                                         period=period, points=points)})


@extend_schema(tags=["Operations"])
class KPITargetViewSet(viewsets.ModelViewSet):
    """Цели KPI (отдел или сотрудник, период) — вводит руководство."""

    serializer_class = KPITargetSerializer
    permission_classes = PERMISSIONS
    pagination_class = OpsPagination
    http_method_names = ["get", "post", "patch", "delete"]

    def get_queryset(self):
        qs = KPITarget.objects.select_related("employee")
        p = self.request.query_params
        if p.get("department") in Department.values:
            qs = qs.filter(department=p["department"])
        if p.get("metric"):
            qs = qs.filter(metric=p["metric"])
        if p.get("active") == "1":
            today = timezone.localdate()
            qs = qs.filter(valid_from__lte=today).filter(Q(valid_to__isnull=True) | Q(valid_to__gte=today))
        return qs

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)


@extend_schema(tags=TAGS, responses=OpenApiTypes.OBJECT)
class ReportsView(_OpsView):
    """Отчёты: виды, предпросмотр выбранного вида (те же таблицы, что в
    выгрузке), сданные отчёты сотрудников и история выгрузок."""

    def get(self, request):
        f = _filters(request)
        kind = request.query_params.get("kind") or "monthly"
        if kind not in dict(exports.KINDS):
            raise ValidationError({"kind": "Неизвестный вид отчёта."})
        sheets = exports.build(kind, f, can_see_finance=can_view_budget(request.user))
        submitted = EmployeeReport.objects.filter(period_start__range=(f.start, f.end)).exclude(
            status=EmployeeReport.Status.DRAFT).select_related("author").order_by("-period_start")[:100]
        history = ReportExport.objects.select_related("created_by")[:30]
        return Response({
            "filters": f.as_dict(),
            "kind": kind,
            "kinds": [{"value": v, "label": label} for v, label in exports.KINDS],
            "sheets": [{"title": t, "headers": h, "rows": [[exports._fmt(v) for v in r] for r in rows[:500]],
                        "total": len(rows)} for t, h, rows in sheets],
            "employee_reports": [{"id": r.pk, "author": person(r.author), "kind": r.kind,
                                  "kind_label": r.get_kind_display(), "period_start": r.period_start,
                                  "status": r.status, "status_label": r.get_status_display(),
                                  "submitted_at": r.submitted_at} for r in submitted],
            "history": [{"id": h.pk, "kind": h.kind, "format": h.format, "filters": h.filters, "rows": h.rows,
                         "created_by": person(h.created_by), "created_at": h.created_at} for h in history],
        })


@extend_schema(tags=TAGS, responses={(200, "application/octet-stream"): OpenApiTypes.BINARY})
class ReportExportView(_OpsView):
    def get(self, request):
        f = _filters(request)
        kind = request.query_params.get("kind") or "monthly"
        fmt = request.query_params.get("export_format") or "xlsx"
        if kind not in dict(exports.KINDS):
            raise ValidationError({"kind": "Неизвестный вид отчёта."})
        if fmt not in ("csv", "xlsx"):
            raise ValidationError({"export_format": "csv или xlsx."})
        sheets = exports.build(kind, f, can_see_finance=can_view_budget(request.user))
        title = f"{dict(exports.KINDS)[kind]} · {f.label}"
        ReportExport.objects.create(kind=kind, format=fmt, created_by=request.user,
                                    rows=sum(len(rows) for _t, _h, rows in sheets),
                                    filters={k: str(v) if v is not None else None for k, v in f.as_dict().items()})
        filename = f"okurmen-{kind}-{f.start:%Y%m%d}-{f.end:%Y%m%d}.{fmt}"
        if fmt == "csv":
            response = HttpResponse(exports.to_csv(sheets), content_type="text/csv; charset=utf-8")
        else:
            response = HttpResponse(exports.to_xlsx(sheets, title),
                                    content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response


@extend_schema(tags=TAGS, responses=OpenApiTypes.OBJECT)
class ActivityView(_OpsView):
    def get(self, request):
        department = request.query_params.get("department") or None
        return Response({"events": overview.recent_activity(limit=60, department=department)})


@extend_schema(tags=["Operations"])
class IssueViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.CreateModelMixin,
                   viewsets.GenericViewSet):
    """Attention Required. Фильтры: status (active — открытые и в работе),
    kind, department, priority, responsible, q."""

    permission_classes = PERMISSIONS
    pagination_class = OpsPagination

    def get_queryset(self):
        qs = OperationalIssue.objects.select_related("responsible", "resolved_by")
        p = self.request.query_params
        value = p.get("status") or "active"
        if value == "active":
            qs = qs.filter(status__in=ACTIVE_ISSUE_STATUSES)
        elif value in IssueStatus.values:
            qs = qs.filter(status=value)
        if p.get("kind") in IssueKind.values:
            qs = qs.filter(kind=p["kind"])
        if p.get("department") in Department.values:
            qs = qs.filter(department=p["department"])
        if p.get("priority") in Priority.values:
            qs = qs.filter(priority=p["priority"])
        if (p.get("responsible") or "").isdigit():
            qs = qs.filter(responsible_id=int(p["responsible"]))
        if p.get("repeated") == "1":
            qs = qs.filter(reopen_count__gt=0)
        if p.get("q"):
            qs = qs.filter(Q(title__icontains=p["q"]) | Q(description__icontains=p["q"]))
        if self.action == "retrieve":
            qs = qs.prefetch_related("events__actor")
        rank = {Priority.CRITICAL: 0, Priority.HIGH: 1, Priority.MEDIUM: 2, Priority.LOW: 3}
        from django.db.models import Case, IntegerField, Value, When

        return qs.annotate(priority_rank=Case(*(When(priority=k, then=Value(v)) for k, v in rank.items()),
                                              output_field=IntegerField())).order_by("priority_rank", "-detected_at")

    def get_serializer_class(self):
        if self.action == "create":
            return IssueCreateSerializer
        return IssueDetailSerializer if self.action == "retrieve" else IssueSerializer

    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)
        active = OperationalIssue.objects.filter(status__in=ACTIVE_ISSUE_STATUSES)
        from django.db.models import Count

        response.data["summary"] = {
            "active": active.count(),
            "high": active.filter(priority__in=(Priority.CRITICAL, Priority.HIGH)).count(),
            "repeated": active.filter(reopen_count__gt=0).count(),
            "by_kind": dict(active.values("kind").annotate(n=Count("id")).values_list("kind", "n")),
        }
        return response

    def create(self, request, *args, **kwargs):
        serializer = IssueCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        issue = issue_service.create_manual(request.user, serializer.validated_data)
        return Response(IssueDetailSerializer(issue).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"], url_path="status")
    def set_status(self, request, pk=None):
        issue = issue_service.change_status(request.user, self.get_object(), str(request.data.get("status") or ""),
                                            str(request.data.get("comment") or ""))
        return Response(IssueDetailSerializer(issue).data)

    @action(detail=True, methods=["post"])
    def assign(self, request, pk=None):
        raw = request.data.get("responsible")
        responsible = get_object_or_404(User, pk=raw, is_active=True) if raw else None
        issue = issue_service.assign(request.user, self.get_object(), responsible)
        return Response(IssueDetailSerializer(issue).data)

    @action(detail=True, methods=["post"])
    def comment(self, request, pk=None):
        event = issue_service.comment(request.user, self.get_object(), str(request.data.get("text") or ""))
        return Response(IssueEventSerializer(event).data, status=status.HTTP_201_CREATED)


@extend_schema(tags=TAGS, responses=OpenApiTypes.OBJECT)
class ScanView(_OpsView):
    """Запустить проверку проблем сейчас (обычно — планировщик). Повторный
    запуск не создаёт дублей."""

    def post(self, request):
        return Response(issue_service.scan())


@extend_schema(tags=TAGS, request=SettingsSerializer, responses=SettingsSerializer)
class SettingsView(_OpsView):
    """Настройки модуля. Читать может надзор; менять — директор,
    операционный директор и администратор (тот же круг)."""

    def get(self, request):
        data = SettingsSerializer(OperationsSettings.load()).data
        data["roles"] = [{"value": v, "label": label} for v, label in User.Role.choices]
        data["report_kinds"] = _choices(ReportKind)
        return Response(data)

    def patch(self, request):
        config = OperationsSettings.load()
        serializer = SettingsSerializer(config, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save(updated_by=request.user)
        return Response(serializer.data)
