"""Parent reports API.

    GET  /api/v1/groups/{id}/parent-reports/preview/    statistics + texts, nothing stored
    POST /api/v1/groups/{id}/parent-reports/generate/   new report: snapshot, texts, PNG
    GET  /api/v1/parent-reports/                        history (?group=, ?report_type=)
    GET  /api/v1/parent-reports/{id}/                   details (snapshot, texts, recommendations)
    GET  /api/v1/parent-reports/{id}/download/          PNG (?image=<id>), or a ZIP of every page
    POST /api/v1/parent-reports/{id}/regenerate/        recalculated copy — the original is kept
    POST /api/v1/parent-reports/{id}/text/              save edited text / text in another language

Every number is calculated on the server from the LMS records; nothing the
client sends besides the configuration is used. Access — see permissions.
"""
from __future__ import annotations

import io
import zipfile

from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.users.permissions import can_view_academy

from .models import ParentReport
from .permissions import CanUseParentReports, accessible_groups, accessible_reports, teacher_scope
from .serializers import (
    ParentReportDetailSerializer,
    ParentReportListSerializer,
    ReportRequestSerializer,
    TextUpdateSerializer,
)
from .services import generation, periods, text_generator


def _query_payload(params) -> dict:
    """Query string → plain dict (so a missing boolean means its default, not False)."""
    payload = {key: params.get(key) for key in params if key != "student_ids"}
    if params.getlist("student_ids"):
        payload["student_ids"] = params.getlist("student_ids")
    return payload


class _GroupReportView(APIView):
    permission_classes = [IsAuthenticated, CanUseParentReports]

    def group(self, request, group_id: int):
        # A trainer only ever reaches their own groups: another group is a 404.
        return get_object_or_404(accessible_groups(request.user).select_related("course"), pk=group_id)

    def report_request(self, request, group, data) -> generation.ReportRequest:
        serializer = ReportRequestSerializer(data=data, context={"group": group, "today": timezone.localdate()})
        serializer.is_valid(raise_exception=True)
        return serializer.to_request()


@extend_schema(tags=["Parent reports"], parameters=[ReportRequestSerializer], responses={200: OpenApiTypes.OBJECT})
class GroupReportPreviewView(_GroupReportView):
    def get(self, request, group_id: int):
        group = self.group(request, group_id)
        report_request = self.report_request(request, group, _query_payload(request.query_params))
        teacher = teacher_scope(request.user)
        preview = generation.build_preview(group, report_request, teacher_id=teacher.pk if teacher else None)
        return Response(preview)


@extend_schema(tags=["Parent reports"], request=ReportRequestSerializer, responses={201: ParentReportDetailSerializer})
class GroupReportGenerateView(_GroupReportView):
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "parent_report_generate"

    def post(self, request, group_id: int):
        group = self.group(request, group_id)
        report_request = self.report_request(request, group, request.data)
        report = generation.generate(group, report_request, user=request.user, teacher=teacher_scope(request.user))
        report = accessible_reports(request.user).get(pk=report.pk)
        return Response(ParentReportDetailSerializer(report).data, status=status.HTTP_201_CREATED)


@extend_schema(tags=["Parent reports"])
class ParentReportViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    permission_classes = [IsAuthenticated, CanUseParentReports]
    filterset_fields = ["group", "report_type", "language", "status"]
    search_fields = ["group_name", "course_name"]
    ordering_fields = ["created_at", "start_date"]
    ordering = ["-created_at", "-id"]
    # Used only by `regenerate` (it renders images); reads keep the default throttles.
    throttle_scope = "parent_report_generate"

    def get_queryset(self):
        return accessible_reports(self.request.user)

    def get_serializer_class(self):
        return ParentReportListSerializer if self.action == "list" else ParentReportDetailSerializer

    @extend_schema(
        parameters=[OpenApiParameter("image", int, description="ID изображения; без него — ZIP всех страниц.")],
        responses={200: {"type": "string", "format": "binary"}},
    )
    @action(detail=True, methods=["get"])
    def download(self, request, pk=None):
        report = self.get_object()
        images = list(report.images.all())
        if not images:
            raise NotFound("У этого отчёта нет изображения.")
        image_id = request.query_params.get("image")
        if image_id:
            if not image_id.isdigit():
                raise ValidationError({"image": ["Неверный идентификатор изображения."]})
            image = next((item for item in images if item.pk == int(image_id)), None)
            if image is None:
                raise NotFound("Изображение не найдено.")
            return self._png(report, image)
        if len(images) == 1:
            return self._png(report, images[0])
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            for image in images:
                with image.image.open("rb") as handle:
                    archive.writestr(self._filename(report, image), handle.read())
        response = HttpResponse(buffer.getvalue(), content_type="application/zip")
        response["Content-Disposition"] = f'attachment; filename="okurmenkids-report-{report.pk}.zip"'
        return response

    @staticmethod
    def _filename(report: ParentReport, image) -> str:
        if image.student_id:
            return f"okurmenkids-report-{report.pk}-student-{image.student_id}.png"
        return f"okurmenkids-report-{report.pk}-page-{image.page}.png"

    def _png(self, report: ParentReport, image) -> HttpResponse:
        try:
            with image.image.open("rb") as handle:
                content = handle.read()
        except FileNotFoundError as exc:
            raise NotFound("Файл изображения не найден — перегенерируйте отчёт.") from exc
        response = HttpResponse(content, content_type="image/png")
        response["Content-Disposition"] = f'attachment; filename="{self._filename(report, image)}"'
        response["Cache-Control"] = "private, max-age=3600"
        return response

    @extend_schema(request=None, responses={201: ParentReportDetailSerializer})
    @action(detail=True, methods=["post"], throttle_classes=[ScopedRateThrottle])
    def regenerate(self, request, pk=None):
        """Recalculate the same report (same group, dates and options) from the
        current LMS data. A new report is created; the original stays in history."""
        report = self.get_object()
        if report.group_id is None:
            raise ValidationError({"detail": "Группа этого отчёта удалена — перегенерировать нельзя."})
        group = get_object_or_404(accessible_groups(request.user).select_related("course"), pk=report.group_id)
        try:
            report_request = generation.request_from_report(report, today=timezone.localdate())
        except periods.PeriodError as exc:
            raise ValidationError({exc.field: [str(exc)]}) from exc
        # The same lessons as the original: Admin regenerating a trainer's
        # report keeps that trainer's scope; a trainer only ever has their own.
        teacher = report.teacher_scope if can_view_academy(request.user) else teacher_scope(request.user)
        new_report = generation.generate(
            group, report_request, user=request.user, teacher=teacher, regenerated_from=report,
        )
        new_report = self.get_queryset().get(pk=new_report.pk)
        return Response(ParentReportDetailSerializer(new_report).data, status=status.HTTP_201_CREATED)

    @extend_schema(request=TextUpdateSerializer, responses={200: ParentReportDetailSerializer})
    @action(detail=True, methods=["post"])
    def text(self, request, pk=None):
        """``{"text": "..."}`` saves the trainer's edit of the message
        (``student_id`` — of that student's message); ``{"reset": true}``
        restores the generated one; ``{"language": "ky"}`` returns the message
        in that language, rendered from the stored snapshot (nothing saved)."""
        report = self.get_object()
        data = TextUpdateSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        payload = data.validated_data
        student_id = payload.get("student_id")
        if student_id is not None and str(student_id) not in {str(e["id"]) for e in report.snapshot.get("students", [])}:
            raise ValidationError({"student_id": ["Этого студента нет в отчёте."]})

        if "language" in payload and "text" not in payload and not payload["reset"]:
            request_obj = generation.ReportRequest(
                period=None, report_type=report.report_type, language=payload["language"],
                options={k: report.options.get(k, d) for k, d in generation.DEFAULT_OPTIONS.items()},
            )
            options = request_obj.stored_options()
            if student_id is not None:
                entry = next(e for e in report.snapshot["students"] if str(e["id"]) == str(student_id))
                text = text_generator.student_message(report.snapshot, entry, language=payload["language"], options=options)
            else:
                text = text_generator.group_message(report.snapshot, language=payload["language"], options=options)
            return Response({"language": payload["language"], "student_id": student_id, "text": text})

        if "text" not in payload and not payload["reset"]:
            raise ValidationError({"text": ["Передайте текст, reset или language."]})

        if student_id is not None:
            edited = dict(report.edited_student_texts or {})
            if payload["reset"]:
                edited.pop(str(student_id), None)
            else:
                edited[str(student_id)] = payload["text"]
            report.edited_student_texts = edited
            report.save(update_fields=["edited_student_texts"])
        else:
            report.edited_text = "" if payload["reset"] else payload["text"]
            report.save(update_fields=["edited_text"])
        return Response(ParentReportDetailSerializer(report).data)
