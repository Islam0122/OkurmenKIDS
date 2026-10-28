"""API кабинета маркетинга (/api/v1/marketing/…): контент-план, задачи,
главная и отчёты.

Только сотрудники маркетинга и администратор (`IsMarketingTeam`). Ни зарплат,
ни персональных данных здесь нет: о людях — только имя ответственного.
Изоляция ролей с базовым доступом пропускает сюда весь префикс
(apps.accounting.access.STAFF_ONLY_ALLOWED_PREFIXES), а права каждого запроса
проверяет `IsMarketingTeam` — остальным ролям 403.
"""
from __future__ import annotations

from datetime import date, timedelta

from django.db.models import Case, F, IntegerField, Value, When
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import status, viewsets
from rest_framework.exceptions import PermissionDenied
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.users.permissions import IsMarketingTeam

from . import reports
from .models import Channel, ContentItem, MarketingTask
from .serializers import ContentItemSerializer, MarketingTaskSerializer, can_delete, meta_payload

TAGS = ["Marketing"]
PERMISSIONS = [IsAuthenticated, IsMarketingTeam]
# Календарь контент-плана загружает диапазон целиком (до 6 недель).
RANGE_MAX_DAYS = 62


class MarketingPagination(PageNumberPagination):
    page_size = 50
    page_size_query_param = "page_size"
    max_page_size = 200


def parse_date(value: str | None) -> date | None:
    try:
        return date.fromisoformat(value) if value else None
    except ValueError:
        return None


def bad_request(message: str) -> Response:
    return Response({"detail": message, "code": "invalid_params"}, status=status.HTTP_400_BAD_REQUEST)


class _DeleteByAuthorMixin:
    def perform_destroy(self, instance):
        if not can_delete(self.request, instance):
            raise PermissionDenied("Удалить запись может только её автор или администратор.")
        instance.delete()


@extend_schema(tags=TAGS)
class ContentItemViewSet(_DeleteByAuthorMixin, viewsets.ModelViewSet):
    """Публикации контент-плана. Фильтры: status, channel, responsible,
    mine=1, date_from / date_to (по дате выхода), no_date=1 (без даты),
    search. Сортировка: publish_date (по умолчанию), updated_at, title."""

    serializer_class = ContentItemSerializer
    permission_classes = PERMISSIONS
    pagination_class = MarketingPagination
    http_method_names = ["get", "post", "patch", "delete"]
    filter_backends = [SearchFilter, OrderingFilter]
    search_fields = ["title", "description"]
    ordering_fields = ["publish_date", "updated_at", "created_at", "title"]

    def get_queryset(self):
        qs = ContentItem.objects.select_related("responsible", "created_by")
        p = self.request.query_params
        statuses = [s for s in p.get("status", "").split(",") if s in ContentItem.Status.values]
        if statuses:
            qs = qs.filter(status__in=statuses)
        if p.get("channel") in Channel.values:
            qs = qs.filter(channel=p["channel"])
        if (p.get("responsible") or "").isdigit():
            qs = qs.filter(responsible_id=int(p["responsible"]))
        if p.get("mine") == "1":
            qs = qs.filter(responsible=self.request.user)
        if (d := parse_date(p.get("date_from"))):
            qs = qs.filter(publish_date__gte=d)
        if (d := parse_date(p.get("date_to"))):
            qs = qs.filter(publish_date__lte=d)
        if p.get("no_date") == "1":
            qs = qs.filter(publish_date__isnull=True)
        return qs.order_by(F("publish_date").asc(nulls_last=True), F("publish_time").asc(nulls_first=True), "id")

    def list(self, request, *args, **kwargs):
        p = request.query_params
        start, end = parse_date(p.get("date_from")), parse_date(p.get("date_to"))
        if (p.get("date_from") and not start) or (p.get("date_to") and not end):
            return bad_request("Даты указываются в формате ГГГГ-ММ-ДД.")
        if start and end and (end < start or (end - start).days > RANGE_MAX_DAYS):
            return bad_request(f"Период — от 1 до {RANGE_MAX_DAYS} дней.")
        return super().list(request, *args, **kwargs)


@extend_schema(tags=TAGS)
class MarketingTaskViewSet(_DeleteByAuthorMixin, viewsets.ModelViewSet):
    """Задачи отдела. Фильтры: status (todo / in_progress / done, а также
    open — не выполнено, overdue — просрочено), priority, responsible,
    mine=1, due (today / week / overdue / none), search. Сортировка:
    due_date (по умолчанию — сначала ближайший срок), priority, created_at."""

    serializer_class = MarketingTaskSerializer
    permission_classes = PERMISSIONS
    pagination_class = MarketingPagination
    http_method_names = ["get", "post", "patch", "delete"]
    filter_backends = [SearchFilter, OrderingFilter]
    search_fields = ["title", "description"]
    ordering_fields = ["due_date", "created_at", "updated_at", "title"]

    def get_queryset(self):
        qs = MarketingTask.objects.select_related("responsible", "created_by")
        p = self.request.query_params
        today = timezone.localdate()
        value = p.get("status")
        if value == "open":
            qs = qs.filter(status__in=MarketingTask.OPEN_STATUSES)
        elif value == "overdue":
            qs = qs.filter(status__in=MarketingTask.OPEN_STATUSES, due_date__lt=today)
        elif value in MarketingTask.Status.values:
            qs = qs.filter(status=value)
        if p.get("priority") in MarketingTask.Priority.values:
            qs = qs.filter(priority=p["priority"])
        if (p.get("responsible") or "").isdigit():
            qs = qs.filter(responsible_id=int(p["responsible"]))
        if p.get("mine") == "1":
            qs = qs.filter(responsible=self.request.user)
        due = p.get("due")
        if due == "today":
            qs = qs.filter(due_date=today)
        elif due == "week":
            qs = qs.filter(due_date__range=(today, today + timedelta(days=6)))
        elif due == "overdue":
            qs = qs.filter(due_date__lt=today).exclude(status=MarketingTask.Status.DONE)
        elif due == "none":
            qs = qs.filter(due_date__isnull=True)
        # Выполненные — в конце; среди остальных — ближайший срок, затем важность.
        return qs.annotate(
            done_rank=Case(When(status=MarketingTask.Status.DONE, then=Value(1)), default=Value(0),
                           output_field=IntegerField()),
            priority_rank=Case(When(priority=MarketingTask.Priority.HIGH, then=Value(0)),
                               When(priority=MarketingTask.Priority.MEDIUM, then=Value(1)), default=Value(2),
                               output_field=IntegerField()),
        ).order_by("done_rank", F("due_date").asc(nulls_last=True), "priority_rank", "-created_at")


@extend_schema(tags=TAGS, responses=OpenApiTypes.OBJECT)
class MetaView(APIView):
    """Справочники: каналы, форматы, статусы, приоритеты и команда (только имена)."""

    permission_classes = PERMISSIONS

    def get(self, request):
        return Response(meta_payload(request.user))


@extend_schema(tags=TAGS, responses=OpenApiTypes.OBJECT)
class DashboardView(APIView):
    """Главная: сводка задач и контент-плана, ближайшие задачи и публикации.
    Период (date_from / date_to) — по умолчанию текущий месяц."""

    permission_classes = PERMISSIONS

    def get(self, request):
        today = timezone.localdate()
        default_from, default_to = reports.month_bounds(today)
        start = parse_date(request.query_params.get("date_from")) or default_from
        end = parse_date(request.query_params.get("date_to")) or default_to
        if end < start or (end - start).days > 366:
            return bad_request("Период — не длиннее года, конец не раньше начала.")
        data = reports.dashboard(request.user, today, start, end)
        context = {"request": request}
        data["upcoming_tasks"] = MarketingTaskSerializer(data["upcoming_tasks"], many=True, context=context).data
        data["upcoming_content"] = ContentItemSerializer(data["upcoming_content"], many=True, context=context).data
        return Response(data)


@extend_schema(tags=TAGS, responses=OpenApiTypes.OBJECT)
class ReportView(APIView):
    """Отчёт за неделю (period=week, пн–вс) или месяц (period=month), в
    который попадает дата `date` (по умолчанию — сегодня)."""

    permission_classes = PERMISSIONS

    def get(self, request):
        kind = request.query_params.get("period", "month")
        if kind not in ("week", "month"):
            return bad_request("Период отчёта: week или month.")
        raw = request.query_params.get("date")
        anchor = parse_date(raw)
        if raw and anchor is None:
            return bad_request("Дата указывается в формате ГГГГ-ММ-ДД.")
        today = timezone.localdate()
        start, end = (reports.week_bounds if kind == "week" else reports.month_bounds)(anchor or today)
        return Response(reports.report(kind, start, end, today))
