"""API «Общей статистики» (TV-панель академии).

    GET   /api/v1/monthly-performance/?year=&month=           всё сразу: дни, карточки, графики
    GET   /api/v1/monthly-performance/snapshots/?year=&month= показатели по дням месяца
    PATCH /api/v1/monthly-performance/snapshots/<YYYY-MM-DD>/ ручная корректировка (только с правом)
    GET   /api/v1/monthly-performance/summary/?year=&month=   карточки и изменение за день
    GET   /api/v1/monthly-performance/trends/?year=&month=    динамика посещаемости, ДЗ, групп и студентов

Доступ: сотрудник (JWT) или ключ «только чтение» в заголовке X-Dashboard-Key
(отдельный сайт /monthly-performance, телевизор в офисе) — см. permissions.

Без параметров — текущий месяц по часовому поясу проекта. Все расчёты —
services.dashboard / services.metrics; просмотр — любой сотрудник.
"""
from __future__ import annotations

import datetime as dt

from django.db import transaction
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.settings import api_settings
from rest_framework.views import APIView

from .authentication import DashboardKeyAuthentication

from .models import DailyPerformanceSnapshot
from .permissions import CanEditPerformanceOrReadOnly, CanViewPerformance, can_edit_performance, is_key_access
from .services import dashboard
from .services.snapshots import capture_day

MONTH_PARAMS = [
    OpenApiParameter("year", OpenApiTypes.INT, description="Год (по умолчанию — текущий)"),
    OpenApiParameter("month", OpenApiTypes.INT, description="Месяц 1–12 (по умолчанию — текущий)"),
]


def parse_month(params) -> tuple[int, int]:
    today = timezone.localdate()
    try:
        year = int(params.get("year") or today.year)
        month = int(params.get("month") or today.month)
    except (TypeError, ValueError):
        raise ValidationError({"detail": "Год и месяц должны быть числами."}) from None
    if not 1 <= month <= 12:
        raise ValidationError({"month": "Месяц должен быть от 1 до 12."})
    # Будущий месяц — календарная сетка без показателей (services.dashboard).
    if not 2000 <= year <= today.year + 1:
        raise ValidationError({"year": "Недопустимый год."})
    return year, month


class _MonthView(APIView):
    # Ключ доступа (X-Dashboard-Key) — первым: телевизор не зависит от срока JWT.
    authentication_classes = [DashboardKeyAuthentication, *api_settings.DEFAULT_AUTHENTICATION_CLASSES]
    permission_classes = [CanViewPerformance]

    def payload(self, request) -> dict:
        year, month = parse_month(request.query_params)
        data = dashboard.month_payload(year, month)
        key = is_key_access(request)
        data["can_edit"] = not key and can_edit_performance(request.user)
        data["access"] = (
            {"mode": "key", "name": request.auth.name} if key
            else {"mode": "user", "name": request.user.get_full_name() or request.user.get_username()}
        )
        return data


@extend_schema(tags=["Analytics"], parameters=MONTH_PARAMS, responses={200: OpenApiTypes.OBJECT})
class MonthlyPerformanceView(_MonthView):
    def get(self, request):
        return Response(self.payload(request))


@extend_schema(tags=["Analytics"], parameters=MONTH_PARAMS, responses={200: OpenApiTypes.OBJECT})
class SnapshotListView(_MonthView):
    def get(self, request):
        data = self.payload(request)
        return Response({k: data[k] for k in ("year", "month", "month_label", "generated_at", "can_edit", "access", "days")})


@extend_schema(tags=["Analytics"], parameters=MONTH_PARAMS, responses={200: OpenApiTypes.OBJECT})
class SummaryView(_MonthView):
    def get(self, request):
        data = self.payload(request)
        return Response({k: data[k] for k in ("year", "month", "month_label", "today", "generated_at", "summary")})


@extend_schema(tags=["Analytics"], parameters=MONTH_PARAMS, responses={200: OpenApiTypes.OBJECT})
class TrendsView(_MonthView):
    def get(self, request):
        data = self.payload(request)
        return Response({k: data[k] for k in ("year", "month", "month_label", "generated_at", "trends")})


class CorrectionSerializer(serializers.Serializer):
    scheduled_groups = serializers.IntegerField(min_value=0, required=False, allow_null=True)
    held_groups = serializers.IntegerField(min_value=0, required=False, allow_null=True)
    scheduled_students = serializers.IntegerField(min_value=0, required=False, allow_null=True)
    attended_students = serializers.IntegerField(min_value=0, required=False, allow_null=True)
    attendance_percent = serializers.DecimalField(
        max_digits=4, decimal_places=1, min_value=0, max_value=100, required=False, allow_null=True)
    homework_percent = serializers.DecimalField(
        max_digits=4, decimal_places=1, min_value=0, max_value=100, required=False, allow_null=True)
    # Прежние имена (до учёта расписания дня).
    active_groups = serializers.IntegerField(min_value=0, required=False, allow_null=True, write_only=True)
    active_students = serializers.IntegerField(min_value=0, required=False, allow_null=True, write_only=True)
    comment = serializers.CharField(max_length=255, required=False, allow_blank=True)

    def validate(self, attrs):
        for alias, field in dashboard.ALIASES.items():
            if alias in attrs:
                attrs.setdefault(field, attrs.pop(alias))
        if not any(field in attrs for field in DailyPerformanceSnapshot.EDITABLE_FIELDS):
            raise serializers.ValidationError("Укажите хотя бы один показатель.")
        return attrs


@extend_schema(tags=["Analytics"], request=CorrectionSerializer, responses={200: OpenApiTypes.OBJECT})
class SnapshotCorrectionView(APIView):
    permission_classes = [CanEditPerformanceOrReadOnly]

    def patch(self, request, day: str):
        try:
            date = dt.date.fromisoformat(day)
        except ValueError:
            raise ValidationError({"date": "Дата в формате ГГГГ-ММ-ДД."}) from None
        today = timezone.localdate()
        if date > today:
            raise ValidationError({"date": "Нельзя корректировать будущий день."})
        serializer = CorrectionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data

        capture_day(date)  # снимок дня есть (или создан из записей LMS) — дальше только ручные поля
        with transaction.atomic():
            snapshot = DailyPerformanceSnapshot.objects.select_for_update().get(date=date)
            manual = list(snapshot.manual_fields or [])
            for field in DailyPerformanceSnapshot.EDITABLE_FIELDS:
                if field in values:
                    setattr(snapshot, field, values[field])
                    if field not in manual:
                        manual.append(field)
            snapshot.manual_fields = manual
            snapshot.manual_comment = values.get("comment", snapshot.manual_comment)
            snapshot.corrected_by = request.user
            snapshot.corrected_at = timezone.now()
            snapshot.save()
        row = dashboard.snapshot_row(snapshot)
        return Response({"date": snapshot.date, **row})
