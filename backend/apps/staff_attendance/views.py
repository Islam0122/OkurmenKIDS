"""API учёта прихода и ухода сотрудников (/api/v1/staff-attendance/).

me/…    — личный кабинет: только данные самого пользователя (request.user),
          чужой id не принимается ни в одном личном эндпоинте.
admin/… — отчёты, исправления, офисы и настройки; доступ — apps.staff_attendance.access.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta

from django.db import transaction
from django.forms.models import model_to_dict
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import status as http
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.users.models import User

from . import access
from .models import (
    AttendanceAdjustment,
    AttendanceAdminLog,
    AttendanceEvent,
    AttendanceLocation,
    AttendanceSession,
    AttendanceSettings,
    AttendanceWorkSchedule,
)
from .serializers import (
    AdjustmentSerializer,
    AdjustSerializer,
    AdminLogSerializer,
    EventSerializer,
    LocationSerializer,
    ManualSessionSerializer,
    MarkSerializer,
    SettingsSerializer,
    WorkScheduleSerializer,
    employee_brief,
    local_iso,
    row_payload,
    session_payload,
)
from .services import adjustments as adjust_service
from .services import marking, reports
from .services.export import rows_to_csv
from .services.network import client_ip
from .services.qr import qr_svg, scan_url

logger = logging.getLogger("apps.staff_attendance")

TAGS = ["Staff attendance"]


def error_response(exc: marking.AttendanceError) -> Response:
    return Response({"detail": exc.message, "code": exc.code, **exc.extra}, status=exc.status)


def _date(value: str | None, default: date | None = None) -> date | None:
    if not value:
        return default
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _bad(message: str) -> Response:
    return Response({"detail": message, "code": "invalid_params"}, status=http.HTTP_400_BAD_REQUEST)


def _today(config: AttendanceSettings) -> date:
    return timezone.localtime(timezone.now(), config.tzinfo).date()


def _log(actor, action: str, obj, changes: dict) -> None:
    AttendanceAdminLog.objects.create(actor=actor, action=action, object_type=type(obj).__name__,
                                      object_id=str(obj.pk or ""), changes=changes)
    logger.info("staff_attendance admin action=%s object=%s#%s by=%s", action, type(obj).__name__, obj.pk, actor.pk)


def _diff(before: dict, after: dict) -> dict:
    return {k: {"old": str(before.get(k)), "new": str(after.get(k))} for k in after if before.get(k) != after.get(k)}


class StandardPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100


# ---------------------------------------------------------------------------
# Личный кабинет
# ---------------------------------------------------------------------------

class MeStatusView(APIView):
    """Текущее состояние рабочего дня: ещё не пришёл / на работе / день завершён."""

    permission_classes = [access.CanCheckIn]

    @extend_schema(tags=TAGS, responses=OpenApiTypes.OBJECT)
    def get(self, request):
        config = AttendanceSettings.load()
        tz = config.tzinfo
        now = timezone.now()
        today = _today(config)
        user = User.objects.select_related("teacher_profile").get(pk=request.user.pk)
        row = reports.day_rows(config, [user], today, now=now)[0]
        open_session = AttendanceSession.objects.select_related("location").filter(
            user=user, status=AttendanceSession.Status.OPEN,
        ).first()
        stale = open_session if open_session and open_session.work_date < today else None
        if open_session and not stale:
            state = "at_work"
        elif row.sessions:
            state = "day_finished"
        else:
            state = "not_arrived"
        return Response({
            "employee": employee_brief(user),
            "state": state,
            "next_action": "check_out" if state == "at_work" else "check_in",
            "server_time": local_iso(now, tz),
            "timezone": config.timezone,
            "today": row_payload(row, tz, now),
            "open_session": session_payload(open_session, tz, now) if open_session and not stale else None,
            "stale_session": session_payload(stale, tz, now) if stale else None,
            "access": {
                "can_view_reports": access.can_view_reports(request.user),
                "can_adjust": access.can_adjust(request.user),
                "can_manage": access.can_manage(request.user),
            },
        })


class MeLocationView(APIView):
    """Проверка отсканированного QR-кода: существует ли офис и активен ли он.
    Отметку не делает."""

    permission_classes = [access.CanCheckIn]

    @extend_schema(tags=TAGS, responses=OpenApiTypes.OBJECT)
    def get(self, request, code: str):
        try:
            location = marking.resolve_location(code)
        except marking.AttendanceError as exc:
            return error_response(exc)
        return Response({"code": location.code, "name": location.name, "address": location.address,
                         "radius_m": location.radius_m})


class _MarkView(APIView):
    permission_classes = [access.CanCheckIn]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "staff_attendance_mark"
    action_func = None

    @extend_schema(tags=TAGS, request=MarkSerializer, responses=OpenApiTypes.OBJECT)
    def post(self, request):
        serializer = MarkSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({"detail": "Некорректные данные отметки.", "code": "invalid", "errors": serializer.errors},
                            status=http.HTTP_400_BAD_REQUEST)
        data = serializer.validated_data
        position = marking.Position(data.get("latitude"), data.get("longitude"), data.get("accuracy"))
        try:
            result = type(self).action_func(
                request.user, data["location_code"], position, idempotency_key=data.get("idempotency_key"),
                ip=client_ip(request), user_agent=request.META.get("HTTP_USER_AGENT", ""),
            )
        except marking.AttendanceError as exc:
            logger.info("staff_attendance rejected user=%s code=%s", request.user.pk, exc.code)
            return error_response(exc)
        config = AttendanceSettings.load()
        tz = config.tzinfo
        session = result.session
        user = request.user
        return Response({
            "event": result.event.kind,
            "replayed": result.replayed,
            "employee": employee_brief(user),
            "occurred_at": local_iso(result.event.occurred_at, tz),
            "timezone": config.timezone,
            "location": {"name": session.location.name if session.location_id else None},
            "distance_m": result.event.distance_m,
            "session": session_payload(session, tz),
            "closed_stale_session": session_payload(result.closed_stale, tz) if result.closed_stale else None,
        }, status=http.HTTP_200_OK if result.replayed else http.HTTP_201_CREATED)


class MeCheckInView(_MarkView):
    action_func = staticmethod(marking.check_in)


class MeCheckOutView(_MarkView):
    action_func = staticmethod(marking.check_out)


class MeHistoryView(APIView):
    """Свои сессии за период (по умолчанию — последние 31 день)."""

    permission_classes = [access.CanCheckIn]

    @extend_schema(tags=TAGS, responses=OpenApiTypes.OBJECT)
    def get(self, request):
        config = AttendanceSettings.load()
        today = _today(config)
        date_to = _date(request.query_params.get("date_to"), today)
        date_from = _date(request.query_params.get("date_from"), (date_to or today) - timedelta(days=30))
        if date_from is None or date_to is None or date_from > date_to:
            return _bad("Неверный период.")
        qs = AttendanceSession.objects.select_related("location").filter(
            user=request.user, work_date__range=(date_from, date_to),
        ).order_by("-checked_in_at", "-id")
        paginator = StandardPagination()
        page = paginator.paginate_queryset(qs, request, view=self)
        now = timezone.now()
        return paginator.get_paginated_response([session_payload(s, config.tzinfo, now) for s in page])


class MeStatsView(APIView):
    """Своя месячная статистика: ?month=YYYY-MM (по умолчанию — текущий)."""

    permission_classes = [access.CanCheckIn]

    @extend_schema(tags=TAGS, responses=OpenApiTypes.OBJECT)
    def get(self, request):
        config = AttendanceSettings.load()
        today = _today(config)
        raw = request.query_params.get("month")
        try:
            year, month = (int(p) for p in raw.split("-")) if raw else (today.year, today.month)
            date(year, month, 1)
        except (ValueError, TypeError):
            return _bad("Месяц в формате ГГГГ-ММ.")
        return Response(reports.month_stats(config, request.user, year, month))


# ---------------------------------------------------------------------------
# Отчёты (руководство, администраторы)
# ---------------------------------------------------------------------------

class _ReportMixin:
    def report_params(self, request):
        config = AttendanceSettings.load()
        scope = access.report_scope(request.user)
        p = request.query_params
        role = p.get("role", "")
        if role and role not in dict(User.Role.choices):
            raise ValueError("Неизвестная роль.")
        users = list(reports.employees(config, scope, search=p.get("search", "").strip()[:100], role=role))
        location = p.get("location", "")
        if location and not location.isdigit():
            raise ValueError("Неверный офис.")
        return config, users, (int(location) if location else None)

    @staticmethod
    def filter_rows(rows, status: str, location: int | None):
        if status and status not in reports.STATUS_LABELS:
            raise ValueError("Неизвестный статус.")
        rows = [r for r in rows if r.matches(status)]
        if location:
            rows = [r for r in rows if any(s.location_id == location for s in r.sessions)]
        return rows


class AdminMetaView(APIView):
    permission_classes = [access.CanViewReports]

    @extend_schema(tags=TAGS, responses=OpenApiTypes.OBJECT)
    def get(self, request):
        config = AttendanceSettings.load()
        scope = access.report_scope_name(request.user)
        # HR видит в фильтре только роли в своём ведении; у остальных — как было.
        allowed = access.report_roles(request.user) if scope == "hr" else None
        return Response({
            "timezone": config.timezone,
            "today": _today(config).isoformat(),
            "roles": [{"value": v, "label": label} for v, label in User.Role.choices
                      if v in config.tracked_roles and (allowed is None or v in allowed)],
            "statuses": [{"value": v, "label": label} for v, label in reports.STATUS_LABELS.items()],
            "locations": [{"id": loc.id, "name": loc.name, "is_active": loc.is_active}
                          for loc in AttendanceLocation.objects.all()],
            "access": {
                "can_view_reports": True,
                "can_adjust": access.can_adjust(request.user),
                "can_manage": access.can_manage(request.user),
                "scope": scope,
            },
        })


class AdminOverviewView(_ReportMixin, APIView):
    """Карточки статистики за день (?date=YYYY-MM-DD, по умолчанию сегодня)."""

    permission_classes = [access.CanViewReports]

    @extend_schema(tags=TAGS, responses=OpenApiTypes.OBJECT)
    def get(self, request):
        try:
            config, users, location = self.report_params(request)
            day = _date(request.query_params.get("date"), _today(config))
            if day is None:
                raise ValueError("Неверная дата.")
            rows = self.filter_rows(reports.day_rows(config, users, day), "", location)
        except ValueError as exc:
            return _bad(str(exc))
        return Response({"date": day.isoformat(), **reports.overview(rows)})


class AdminRecordsView(_ReportMixin, APIView):
    """Таблица: сотрудник × день. Фильтры: date (или date_from/date_to),
    search, role, status, location; ordering; серверная пагинация."""

    permission_classes = [access.CanViewReports]

    def rows(self, request):
        config, users, location = self.report_params(request)
        p = request.query_params
        today = _today(config)
        if p.get("date_from") or p.get("date_to"):
            date_from, date_to = _date(p.get("date_from")), _date(p.get("date_to"))
            if date_from is None or date_to is None or date_from > date_to:
                raise ValueError("Неверный период.")
            if (date_to - date_from).days >= reports.MAX_RANGE_DAYS:
                raise ValueError(f"Период не длиннее {reports.MAX_RANGE_DAYS} дней.")
            rows = reports.range_rows(config, users, date_from, date_to)
        else:
            day = _date(p.get("date"), today)
            if day is None:
                raise ValueError("Неверная дата.")
            rows = reports.day_rows(config, users, day)
        rows = self.filter_rows(rows, p.get("status", ""), location)
        return config, reports.sort_rows(rows, p.get("ordering", "name"))

    @extend_schema(tags=TAGS, responses=OpenApiTypes.OBJECT)
    def get(self, request):
        try:
            config, rows = self.rows(request)
        except ValueError as exc:
            return _bad(str(exc))
        paginator = StandardPagination()
        page = paginator.paginate_queryset(rows, request, view=self)
        now = timezone.now()
        return paginator.get_paginated_response([row_payload(r, config.tzinfo, now) for r in page])


class AdminExportView(AdminRecordsView):
    """Та же выборка, что и таблица, — CSV (все страницы)."""

    @extend_schema(tags=TAGS, responses=OpenApiTypes.OBJECT)
    def get(self, request):
        try:
            config, rows = self.rows(request)
        except ValueError as exc:
            return _bad(str(exc))
        p = request.query_params
        suffix = p.get("date") or f"{p.get('date_from', '')}_{p.get('date_to', '')}".strip("_") or "today"
        response = HttpResponse(rows_to_csv(rows, config.tzinfo), content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="staff-attendance-{suffix}.csv"'
        logger.info("staff_attendance export by=%s rows=%s", request.user.pk, len(rows))
        return response


class AdminEmployeeView(APIView):
    """Карточка сотрудника: сессии, события, исправления за период."""

    permission_classes = [access.CanViewReports]

    @extend_schema(tags=TAGS, responses=OpenApiTypes.OBJECT)
    def get(self, request, user_id: int):
        config = AttendanceSettings.load()
        scope = access.report_scope(request.user)
        user = get_object_or_404(User.objects.filter(scope).select_related("teacher_profile"), pk=user_id)
        today = _today(config)
        date_to = _date(request.query_params.get("date_to"), today)
        date_from = _date(request.query_params.get("date_from"), (date_to or today) - timedelta(days=30))
        if date_from is None or date_to is None or date_from > date_to:
            return _bad("Неверный период.")
        if (date_to - date_from).days >= reports.MAX_RANGE_DAYS:
            return _bad(f"Период не длиннее {reports.MAX_RANGE_DAYS} дней.")
        tz = config.tzinfo
        now = timezone.now()
        rows = [r for r in reports.range_rows(config, [user], date_from, date_to, now=now)
                if r.sessions or r.status in (reports.Status.NO_CHECK_IN, reports.Status.NO_CHECK_OUT)]
        rows.reverse()
        sessions = AttendanceSession.objects.filter(user=user, work_date__range=(date_from, date_to))
        events = AttendanceEvent.objects.select_related("location", "created_by").filter(session__in=sessions)
        adjustments = AttendanceAdjustment.objects.select_related("adjusted_by", "session__user").filter(
            session__in=sessions)
        stats = {
            "days_present": sum(1 for r in rows if r.sessions),
            "late_days": sum(1 for r in rows if r.is_late),
            "late_minutes_total": sum(r.late_minutes for r in rows),
            "no_check_in_days": sum(1 for r in rows if r.status == reports.Status.NO_CHECK_IN),
            "no_check_out_days": sum(1 for r in rows if r.status == reports.Status.NO_CHECK_OUT),
            "total_seconds": sum(r.duration_seconds for r in rows),
        }
        return Response({
            "employee": {**employee_brief(user), "email": user.email, "is_active": user.is_active},
            "date_from": date_from.isoformat(),
            "date_to": date_to.isoformat(),
            "stats": stats,
            "days": [row_payload(r, tz, now) for r in rows],
            "events": EventSerializer(events, many=True).data,
            "adjustments": AdjustmentSerializer(adjustments, many=True).data,
        })


# ---------------------------------------------------------------------------
# Исправления
# ---------------------------------------------------------------------------

class AdminAdjustSessionView(APIView):
    permission_classes = [access.CanAdjust]

    @extend_schema(tags=TAGS, request=AdjustSerializer, responses=OpenApiTypes.OBJECT)
    def post(self, request, session_id: int):
        scope = access.report_scope(request.user)
        get_object_or_404(AttendanceSession.objects.filter(user__in=User.objects.filter(scope)), pk=session_id)
        serializer = AdjustSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            adjustment = adjust_service.adjust_session(
                session_id, request.user, checked_in_at=data["checked_in_at"],
                checked_out_at=data.get("checked_out_at"), reason=data["reason"], location=data.get("location"),
                late_minutes_override=data.get("late_minutes"),
            )
        except marking.AttendanceError as exc:
            return error_response(exc)
        return Response(AdjustmentSerializer(adjustment).data, status=http.HTTP_200_OK)


class AdminManualSessionView(APIView):
    permission_classes = [access.CanAdjust]

    @extend_schema(tags=TAGS, request=ManualSessionSerializer, responses=OpenApiTypes.OBJECT)
    def post(self, request):
        serializer = ManualSessionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        if not User.objects.filter(access.report_scope(request.user), pk=data["user"].pk).exists():
            return Response({"detail": "Сотрудник недоступен.", "code": "forbidden"}, status=http.HTTP_403_FORBIDDEN)
        try:
            adjustment = adjust_service.create_manual_session(
                data["user"], request.user, checked_in_at=data["checked_in_at"],
                checked_out_at=data.get("checked_out_at"), reason=data["reason"], location=data.get("location"),
                late_minutes_override=data.get("late_minutes"),
            )
        except marking.AttendanceError as exc:
            return error_response(exc)
        return Response(AdjustmentSerializer(adjustment).data, status=http.HTTP_201_CREATED)


class AdminAdjustmentsView(APIView):
    """Журнал исправлений (?user=…)."""

    permission_classes = [access.CanViewReports]

    @extend_schema(tags=TAGS, responses=OpenApiTypes.OBJECT)
    def get(self, request):
        qs = AttendanceAdjustment.objects.select_related("adjusted_by", "session__user").filter(
            session__user__in=User.objects.filter(access.report_scope(request.user)))
        user_id = request.query_params.get("user", "")
        if user_id.isdigit():
            qs = qs.filter(session__user_id=int(user_id))
        paginator = StandardPagination()
        page = paginator.paginate_queryset(qs, request, view=self)
        return paginator.get_paginated_response(AdjustmentSerializer(page, many=True).data)


# ---------------------------------------------------------------------------
# Офисы, QR, настройки, расписания
# ---------------------------------------------------------------------------

class LocationListView(APIView):
    permission_classes = [access.CanManage]

    @extend_schema(tags=TAGS, responses=OpenApiTypes.OBJECT, operation_id="staff_attendance_locations_list")
    def get(self, request):
        return Response(LocationSerializer(AttendanceLocation.objects.all(), many=True).data)

    @extend_schema(tags=TAGS, request=LocationSerializer, responses=OpenApiTypes.OBJECT)
    def post(self, request):
        serializer = LocationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            location = serializer.save()
            _log(request.user, "location_create", location, serializer.data)
        return Response(LocationSerializer(location).data, status=http.HTTP_201_CREATED)


class LocationDetailView(APIView):
    permission_classes = [access.CanManage]

    @extend_schema(tags=TAGS, responses=OpenApiTypes.OBJECT)
    def get(self, request, pk: int):
        return Response(LocationSerializer(get_object_or_404(AttendanceLocation, pk=pk)).data)

    @extend_schema(tags=TAGS, request=LocationSerializer, responses=OpenApiTypes.OBJECT)
    def patch(self, request, pk: int):
        location = get_object_or_404(AttendanceLocation, pk=pk)
        before = model_to_dict(location)
        serializer = LocationSerializer(location, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            location = serializer.save()
            _log(request.user, "location_update", location, _diff(before, model_to_dict(location)))
        return Response(LocationSerializer(location).data)


class LocationQRView(APIView):
    permission_classes = [access.CanManage]

    @extend_schema(tags=TAGS, responses=OpenApiTypes.OBJECT)
    def get(self, request, pk: int):
        location = get_object_or_404(AttendanceLocation, pk=pk)
        response = HttpResponse(qr_svg(location), content_type="image/svg+xml")
        response["Content-Disposition"] = f'inline; filename="office-qr-{location.pk}.svg"'
        response["X-QR-URL"] = scan_url(location)
        return response


class SettingsView(APIView):
    def get_permissions(self):
        # Читать настройки (часовой пояс, расписание) могут все, кто видит отчёты.
        if self.request.method == "GET":
            return [access.CanViewReports()]
        return [access.CanManage()]

    @extend_schema(tags=TAGS, responses=OpenApiTypes.OBJECT)
    def get(self, request):
        return Response(SettingsSerializer(AttendanceSettings.load()).data)

    @extend_schema(tags=TAGS, request=SettingsSerializer, responses=OpenApiTypes.OBJECT)
    def patch(self, request):
        config = AttendanceSettings.load()
        before = model_to_dict(config)
        serializer = SettingsSerializer(config, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            config = serializer.save(updated_by=request.user)
            _log(request.user, "settings_update", config, _diff(before, model_to_dict(config)))
        return Response(SettingsSerializer(config).data)


class ScheduleListView(APIView):
    permission_classes = [access.CanManage]

    @extend_schema(tags=TAGS, responses=OpenApiTypes.OBJECT)
    def get(self, request):
        qs = AttendanceWorkSchedule.objects.select_related("user__teacher_profile").order_by(
            "user__last_name", "user__first_name")
        return Response(WorkScheduleSerializer(qs, many=True).data)


class EmployeeScheduleView(APIView):
    permission_classes = [access.CanManage]

    @extend_schema(tags=TAGS, request=WorkScheduleSerializer, responses=OpenApiTypes.OBJECT)
    def put(self, request, user_id: int):
        user = get_object_or_404(User, pk=user_id, is_active=True)
        instance = AttendanceWorkSchedule.objects.filter(user=user).first()
        before = model_to_dict(instance) if instance else {}
        serializer = WorkScheduleSerializer(instance, data=request.data, partial=instance is not None)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            schedule = serializer.save(user=user, updated_by=request.user)
            _log(request.user, "schedule_update", schedule, _diff(before, model_to_dict(schedule)))
        return Response(WorkScheduleSerializer(schedule).data)

    @extend_schema(tags=TAGS, responses=OpenApiTypes.OBJECT)
    def delete(self, request, user_id: int):
        schedule = get_object_or_404(AttendanceWorkSchedule, user_id=user_id)
        with transaction.atomic():
            _log(request.user, "schedule_delete", schedule, _diff({}, model_to_dict(schedule)))
            schedule.delete()
        return Response(status=http.HTTP_204_NO_CONTENT)


class AdminLogView(APIView):
    permission_classes = [access.CanManage]

    @extend_schema(tags=TAGS, responses=OpenApiTypes.OBJECT)
    def get(self, request):
        paginator = StandardPagination()
        page = paginator.paginate_queryset(AttendanceAdminLog.objects.select_related("actor"), request, view=self)
        return paginator.get_paginated_response(AdminLogSerializer(page, many=True).data)
