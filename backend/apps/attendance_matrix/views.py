"""API of the attendance matrix — /api/v1/attendance-matrix/.

Every endpoint checks access on the server (apps.attendance_matrix.access);
a group the user may not see answers 404, an action they may not take 403.
"""
from __future__ import annotations

from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.academy.models import Group

from . import access, cells, export, matrix
from .models import MatrixSettings

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


class HasMatrixAccess(BasePermission):
    message = "Раздел посещаемости вам недоступен."

    def has_permission(self, request, view) -> bool:
        return access.role_of(request.user) is not None


class _View(APIView):
    permission_classes = [IsAuthenticated, HasMatrixAccess]

    def _group(self, request, pk) -> Group:
        group = get_object_or_404(access.visible_groups(request.user).select_related("course"), pk=pk)
        return group


def _error(exc) -> Response:
    return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)


def _xlsx(content: bytes, filename: str) -> HttpResponse:
    response = HttpResponse(content, content_type=XLSX)
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


class MetaView(_View):
    """Filters' options and the user's role: groups, directions, trainers."""

    def get(self, request):
        return Response(matrix.overview_meta(request.user))


class GroupMatrixView(_View):
    def get(self, request, pk):
        group = self._group(request, pk)
        try:
            return Response(matrix.group_matrix(request.user, group, request.query_params))
        except matrix.MatrixError as exc:
            return _error(exc)


class GroupExportView(_View):
    def get(self, request, pk):
        group = self._group(request, pk)
        try:
            data = matrix.group_matrix(request.user, group, request.query_params)
        except matrix.MatrixError as exc:
            return _error(exc)
        start = data["period"]["start"]
        filename = f"attendance_{group.pk}_{start:%Y_%m_%d}_{data['period']['kind']}.xlsx"
        return _xlsx(export.group_workbook(data), filename)


class CellView(_View):
    """GET ?lesson=&student= — the cell with its history; PUT — change it."""

    def _resolve(self, request, source):
        return cells.resolve(request.user, source.get("lesson"), source.get("student"))

    def get(self, request):
        try:
            lesson, student = self._resolve(request, request.query_params)
            return Response(cells.detail(request.user, lesson, student))
        except cells.CellError as exc:
            return Response({"detail": exc.message}, status=exc.status)

    def put(self, request):
        try:
            lesson, student = self._resolve(request, request.data)
            return Response(cells.update(request.user, lesson, student, request.data))
        except cells.CellError as exc:
            return Response({"detail": exc.message}, status=exc.status)

    patch = put


class OverviewView(_View):
    """Many groups for one month: Team Lead (their directions), Operations
    director and Admin (the academy); a trainer / assistant — their groups."""

    def get(self, request):
        try:
            return Response(matrix.overview(request.user, request.query_params))
        except matrix.MatrixError as exc:
            return _error(exc)


class OverviewExportView(_View):
    def get(self, request):
        try:
            data = matrix.overview(request.user, request.query_params)
        except matrix.MatrixError as exc:
            return _error(exc)
        role = access.role_of(request.user)
        title = "Посещаемость академии" if role in (access.ADMIN, access.OPERATIONS_DIRECTOR) else "Посещаемость групп"
        start = data["period"]["start"]
        return _xlsx(export.overview_workbook(data, title), f"attendance_overview_{start:%Y_%m}.xlsx")


THRESHOLD_FIELDS = ("consecutive_absences_warning", "monthly_absences_attention", "monthly_absences_critical",
                    "missed_homework_warning")
PERMISSION_FIELDS = ("team_lead_can_edit", "operations_director_can_edit")


def _settings_payload(settings: MatrixSettings, user) -> dict:
    role = access.role_of(user)
    return {
        **{f: getattr(settings, f) for f in THRESHOLD_FIELDS + PERMISSION_FIELDS},
        "updated_at": settings.updated_at,
        "can_edit_thresholds": role in (access.ADMIN, access.OPERATIONS_DIRECTOR),
        "can_edit_permissions": role == access.ADMIN,
    }


class SettingsView(_View):
    """Thresholds: Admin and Operations director change them; who besides
    trainers may edit marks — Admin only."""

    def get(self, request):
        return Response(_settings_payload(MatrixSettings.load(), request.user))

    def patch(self, request):
        role = access.role_of(request.user)
        if role not in (access.ADMIN, access.OPERATIONS_DIRECTOR):
            return Response({"detail": "Изменять настройки может администратор или операционный директор."}, status=403)
        settings = MatrixSettings.load()
        errors = {}
        for f in THRESHOLD_FIELDS:
            if f in request.data:
                try:
                    value = int(request.data[f])
                except (TypeError, ValueError):
                    errors[f] = "Введите число."
                    continue
                if not 1 <= value <= 50:
                    errors[f] = "От 1 до 50."
                    continue
                setattr(settings, f, value)
        for f in PERMISSION_FIELDS:
            if f in request.data:
                if role != access.ADMIN:
                    return Response({"detail": "Права на изменение отметок назначает администратор."}, status=403)
                setattr(settings, f, bool(request.data[f]))
        if settings.monthly_absences_critical < settings.monthly_absences_attention:
            errors["monthly_absences_critical"] = "Критический порог не может быть меньше порога внимания."
        if errors:
            return Response(errors, status=400)
        settings.updated_by = request.user
        settings.save()
        return Response(_settings_payload(settings, request.user))
