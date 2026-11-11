"""CMS API of the bulk import — /api/v1/marketing/site/import/.

    GET  import/template/?file_format=xlsx | ?file_format=csv&type=events   templates
    POST import/preview/   multipart: file, type (CSV only), types=events,news   → batch with validated rows
    GET  import/           history;  GET import/{id}/   batch (rows + results)
    POST import/{id}/commit/  {rows: [key], update: [key], confirm_update: bool, finalize: bool}
    POST import/{id}/cancel/
    GET  import/{id}/errors/   CSV report
"""
from __future__ import annotations

from django.http import HttpResponse
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, parsers, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from ..cms import can_import_content
from ..models import ImportBatch
from . import service, template
from .reader import FileRejected
from .schema import COLUMNS, TYPE_LABEL, TYPES

TAGS = ["Marketing — website CMS"]


class IsContentImporter(BasePermission):
    message = "Массовый импорт доступен администратору и директору."

    def has_permission(self, request, view) -> bool:
        return can_import_content(request.user)


class BatchListSerializer(serializers.ModelSerializer):
    created_by_name = serializers.SerializerMethodField()
    content_type_label = serializers.CharField(source="get_content_type_display", read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    imported_count = serializers.IntegerField(read_only=True)
    error_rows = serializers.SerializerMethodField()

    class Meta:
        model = ImportBatch
        fields = ["id", "file_name", "file_size", "created_by_name", "content_type", "content_type_label", "status",
                  "status_label", "total_rows", "selected_rows", "imported_count", "created_count", "updated_count",
                  "skipped_count", "failed_count", "error_rows", "created_at", "finished_at"]

    def get_created_by_name(self, obj):
        user = obj.created_by
        return (user.get_full_name() or user.username) if user else ""

    def get_error_rows(self, obj):
        return sum(1 for r in obj.rows if r["errors"])


class BatchSerializer(BatchListSerializer):
    rows = serializers.SerializerMethodField()
    results = serializers.SerializerMethodField()
    sheets = serializers.SerializerMethodField()

    class Meta(BatchListSerializer.Meta):
        fields = [*BatchListSerializer.Meta.fields, "sheets", "rows", "results"]

    def get_rows(self, obj):
        # The cleaned values stay on the server; the table needs the summary and the messages.
        keep = ("key", "kind", "row", "title", "category", "category_raw", "date", "languages", "status",
                "status_raw", "cover", "verification_note", "errors", "warnings", "duplicate", "valid")
        return [{k: r.get(k) for k in keep} for r in obj.rows]

    def get_results(self, obj):
        return obj.report.get("rows", {})

    def get_sheets(self, obj):
        return obj.report.get("sheets", {})


class CommitSerializer(serializers.Serializer):
    rows = serializers.ListField(child=serializers.CharField(max_length=40), max_length=5000)
    update = serializers.ListField(child=serializers.CharField(max_length=40), required=False, default=list)
    confirm_update = serializers.BooleanField(required=False, default=False)
    finalize = serializers.BooleanField(required=False, default=True)

    def validate(self, attrs):
        if attrs["update"] and not attrs["confirm_update"]:
            raise ValidationError({"confirm_update": "Подтвердите обновление существующих записей."})
        if not set(attrs["update"]) <= set(attrs["rows"]):
            raise ValidationError({"update": "Обновлять можно только выбранные строки."})
        return attrs


class ImportTemplateView(APIView):
    permission_classes = [IsAuthenticated, IsContentImporter]

    @extend_schema(tags=TAGS, summary="Шаблон импорта (XLSX или CSV)")
    def get(self, request):
        fmt = request.query_params.get("file_format", "xlsx")  # not «format»: DRF reserves it
        if fmt == "xlsx":
            response = HttpResponse(template.xlsx_template(),
                                    content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
            response["Content-Disposition"] = 'attachment; filename="okurmen-content-template.xlsx"'
            return response
        kind = request.query_params.get("type")
        if fmt != "csv" or kind not in TYPES:
            raise ValidationError({"file_format": "file_format=xlsx или file_format=csv&type=events|achievements|news"})
        response = HttpResponse(template.csv_template(kind), content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="okurmen-{kind}-template.csv"'
        return response


class ImportPreviewView(APIView):
    permission_classes = [IsAuthenticated, IsContentImporter]
    parser_classes = [parsers.MultiPartParser]

    @extend_schema(tags=TAGS, summary="Загрузить файл и проверить строки", responses=BatchSerializer)
    def post(self, request):
        upload = request.FILES.get("file")
        if upload is None:
            raise ValidationError({"file": "Выберите файл .xlsx или .csv."})
        kind = request.data.get("type") or None
        if kind and kind not in TYPES:
            raise ValidationError({"type": "Неизвестный тип контента."})
        kinds = [k for k in (request.data.get("types") or "").split(",") if k in TYPES] or None
        try:
            batch = service.preview(upload, request.user, csv_kind=kind, kinds=kinds)
        except (FileRejected, service.ImportRejected) as exc:
            raise ValidationError({"file": str(exc)})
        return Response(BatchSerializer(batch).data, status=status.HTTP_201_CREATED)


class HistoryPagination(PageNumberPagination):
    page_size = 20


class ImportBatchViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    permission_classes = [IsAuthenticated, IsContentImporter]
    queryset = ImportBatch.objects.select_related("created_by")
    pagination_class = HistoryPagination

    def get_queryset(self):
        qs = super().get_queryset()
        if self.action == "list" and self.request.query_params.get("all") != "1":
            # History = files that were imported; abandoned previews are hidden.
            qs = qs.exclude(status__in=[ImportBatch.Status.PREVIEW, ImportBatch.Status.CANCELLED])
        return qs

    def get_serializer_class(self):
        return BatchListSerializer if self.action == "list" else BatchSerializer

    @extend_schema(tags=TAGS, request=CommitSerializer, responses=BatchSerializer, summary="Импортировать строки")
    @action(detail=True, methods=["post"])
    def commit(self, request, pk=None):
        data = CommitSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        try:
            batch = service.commit(self.get_object(), request.user, keys=data.validated_data["rows"],
                                   update_keys=data.validated_data["update"],
                                   finalize=data.validated_data["finalize"])
        except service.ImportRejected as exc:
            raise ValidationError({"detail": str(exc)})
        return Response(BatchSerializer(batch).data)

    @extend_schema(tags=TAGS, request=None, responses=BatchListSerializer, summary="Отменить (не импортировать)")
    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        batch = self.get_object()
        if batch.status != ImportBatch.Status.PREVIEW:
            raise ValidationError({"detail": "Импорт уже начат."})
        batch.status = ImportBatch.Status.CANCELLED
        batch.save(update_fields=["status"])
        return Response(BatchListSerializer(batch).data)

    @extend_schema(tags=TAGS, summary="Отчёт об ошибках (CSV)")
    @action(detail=True, methods=["get"], url_path="errors")
    def errors(self, request, pk=None):
        batch = self.get_object()
        response = HttpResponse(template.error_report_csv(batch), content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="import-{batch.pk}-errors.csv"'
        return response


class ImportMetaView(APIView):
    permission_classes = [IsAuthenticated, IsContentImporter]

    @extend_schema(tags=TAGS, summary="Колонки и ограничения импорта")
    def get(self, request):
        from .reader import MAX_FILE_BYTES, MAX_ROWS_PER_SHEET
        return Response({
            "types": [{"value": k, "label": TYPE_LABEL[k],
                       "columns": [{"key": c.key, "label": c.label, "required": c.required} for c in COLUMNS[k]]}
                      for k in TYPES],
            "max_file_bytes": MAX_FILE_BYTES,
            "max_rows_per_sheet": MAX_ROWS_PER_SHEET,
        })
