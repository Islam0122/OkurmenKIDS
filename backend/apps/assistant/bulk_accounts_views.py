"""Bulk generation of student portal accounts — /api/v1/assistant/bulk-accounts/.

Thin views over apps.portal.services.bulk_accounts. Admin or an active
Assistant may create and run batches (IsAdminOrAssistant, like the rest of the
Assistant Workspace). The one-time XLSX of a batch — which contains
temporary passwords — is only released to the person who started the batch
or to an Admin, and never cached.
"""
from __future__ import annotations

from django.core.exceptions import PermissionDenied
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Count
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import serializers, status
from rest_framework.exceptions import APIException
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.response import Response

from apps.portal.models import BulkAccountRun, BulkAccountRunItem
from apps.portal.services import bulk_accounts as service

from .views import AssistantView, _drf_error, _no_store

TAGS = ["Assistant"]
RUN_LIST_LIMIT = 20
FAILED_LIMIT = 300
CREATED_LIMIT = 1000
EXPORT_STATE_LABELS = {
    BulkAccountRun.ExportState.NONE: "Нет учётных данных",
    BulkAccountRun.ExportState.READY: "Готов к выгрузке",
    BulkAccountRun.ExportState.DOWNLOADED: "Выгружен",
    BulkAccountRun.ExportState.EXPIRED: "Срок выгрузки истёк",
}


class RunConflictError(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_code = "run_in_progress"


class PreviewQuerySerializer(serializers.Serializer):
    scope = serializers.ChoiceField(choices=BulkAccountRun.Scope.choices, default=BulkAccountRun.Scope.ALL)
    group_ids = serializers.CharField(required=False, allow_blank=True, default="")

    def validate_group_ids(self, value: str) -> list[int]:
        try:
            return [int(part) for part in value.split(",") if part.strip()]
        except ValueError:
            raise serializers.ValidationError("Неверный список групп.")


class RunCreateSerializer(serializers.Serializer):
    scope = serializers.ChoiceField(choices=BulkAccountRun.Scope.choices)
    group_ids = serializers.ListField(child=serializers.IntegerField(min_value=1), required=False, default=list)
    confirm = serializers.BooleanField()

    def validate_confirm(self, value: bool) -> bool:
        if not value:
            raise serializers.ValidationError("Подтвердите создание аккаунтов.")
        return value


class ProcessSerializer(serializers.Serializer):
    limit = serializers.IntegerField(min_value=1, max_value=service.BATCH_MAX, required=False, default=10)


def run_payload(run: BulkAccountRun, user) -> dict:
    counts = {
        row["status"]: row["n"]
        for row in run.items.order_by().values("status").annotate(n=Count("pk"))
    }
    total = sum(counts.values())
    pending = counts.get(BulkAccountRunItem.Status.PENDING, 0)
    created = counts.get(BulkAccountRunItem.Status.CREATED, 0)
    existing = counts.get(BulkAccountRunItem.Status.EXISTING, 0)
    failed = counts.get(BulkAccountRunItem.Status.FAILED, 0)
    failed_rows = run.items.filter(status=BulkAccountRunItem.Status.FAILED).order_by("pk")[:FAILED_LIMIT]
    created_rows = run.items.filter(status=BulkAccountRunItem.Status.CREATED).order_by("pk")[:CREATED_LIMIT]
    downloadable = run.export_state == BulkAccountRun.ExportState.READY and service.can_download(run, user)
    return {
        "id": run.pk,
        "scope": run.scope,
        "scope_label": service._scope_label(run),
        "group_names": run.group_names,
        "status": run.status,
        "status_display": run.get_status_display(),
        "created_at": run.created_at,
        "finished_at": run.finished_at,
        "created_by": run.created_by.get_full_name() or run.created_by.username if run.created_by else None,
        "retry_of": run.retry_of_id,
        "counts": {
            "total": total, "existing": existing, "created": created, "failed": failed, "pending": pending,
        },
        "progress": 100 if total == 0 else round((total - pending) * 100 / total),
        "export": {
            "state": run.export_state,
            "label": EXPORT_STATE_LABELS[run.export_state],
            "downloadable": downloadable,
            "expires_at": run.secrets_expire_at if run.export_state == BulkAccountRun.ExportState.READY else None,
            "exported_at": run.exported_at,
        },
        "failed": [
            {"id": item.pk, "student_id": item.student_id, "full_name": item.student_name,
             "group": item.group_name, "reason": item.error}
            for item in failed_rows
        ],
        "created": [
            {"student_id": item.student_id, "full_name": item.student_name, "group": item.group_name,
             "login": item.login}
            for item in created_rows
        ],
    }


def _run_response(run: BulkAccountRun, request, http_status=status.HTTP_200_OK) -> Response:
    run.refresh_from_db()
    return _no_store(Response(run_payload(run, request.user), status=http_status))


def _run_or_404(pk: int) -> BulkAccountRun:
    return get_object_or_404(BulkAccountRun.objects.select_related("created_by"), pk=pk)


@extend_schema(tags=TAGS, responses={200: dict})
class BulkAccountPreviewView(AssistantView):
    """What a batch would do right now — nothing is written."""

    def get(self, request):
        params = PreviewQuerySerializer(data=request.query_params)
        params.is_valid(raise_exception=True)
        data = params.validated_data
        try:
            result = service.preview(data["scope"], data["group_ids"])
        except DjangoValidationError as exc:
            raise _drf_error(exc)
        return _no_store(Response(result))


@extend_schema(tags=TAGS, responses={200: dict})
class BulkAccountRunListView(AssistantView):
    def get(self, request):
        service.purge_all_expired()
        runs = BulkAccountRun.objects.select_related("created_by")[:RUN_LIST_LIMIT]
        return _no_store(Response({"results": [run_payload(run, request.user) for run in runs]}))

    def post(self, request):
        data = self.body(RunCreateSerializer)
        try:
            run = service.create_run(data["scope"], data.get("group_ids") or [], performed_by=request.user)
        except service.RunConflict as exc:
            raise RunConflictError(str(exc))
        except DjangoValidationError as exc:
            raise _drf_error(exc)
        return _run_response(run, request, status.HTTP_201_CREATED)


@extend_schema(tags=TAGS, responses={200: dict})
class BulkAccountRunDetailView(AssistantView):
    def get(self, request, pk):
        run = _run_or_404(pk)
        service.purge_expired_secrets(run)
        return _run_response(run, request)


@extend_schema(tags=TAGS, request=ProcessSerializer, responses={200: dict})
class BulkAccountRunProcessView(AssistantView):
    """Creates the next batch of accounts of the run. The client calls it
    until `counts.pending` is 0 — each call is short and resumable."""

    def post(self, request, pk):
        run = _run_or_404(pk)
        data = self.body(ProcessSerializer)
        service.process_batch(run, performed_by=request.user, limit=data["limit"])
        return _run_response(run, request)


@extend_schema(tags=TAGS, responses={201: dict})
class BulkAccountRunRetryView(AssistantView):
    """A new run with only the failed students who still have no account."""

    def post(self, request, pk):
        run = _run_or_404(pk)
        try:
            retry = service.create_retry_run(run, performed_by=request.user)
        except service.RunConflict as exc:
            raise RunConflictError(str(exc))
        except DjangoValidationError as exc:
            raise _drf_error(exc)
        return _run_response(retry, request, status.HTTP_201_CREATED)


@extend_schema(tags=TAGS, responses={200: bytes})
class BulkAccountRunExportView(AssistantView):
    """One-time XLSX of the run's new credentials. Starting person or Admin only."""

    def get(self, request, pk):
        run = _run_or_404(pk)
        if not service.can_download(run, request.user):
            raise PermissionDenied("Выгрузить учётные данные может только тот, кто запустил пакет, или администратор.")
        try:
            data = service.export_xlsx(run.pk, performed_by=request.user)
        except DjangoValidationError as exc:
            raise _drf_error(exc)
        response = HttpResponse(
            data, content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        response["Content-Disposition"] = f'attachment; filename="{service.export_filename(run)}"'
        response["X-Content-Type-Options"] = "nosniff"
        response["Cache-Control"] = "no-store, private"
        response["Pragma"] = "no-cache"
        return response
