from __future__ import annotations

from django.db.models import Exists, OuterRef
from drf_spectacular.utils import extend_schema
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import News, NewsRead
from .permissions import IsTeacher
from .serializers import NewsSerializer


@extend_schema(tags=["News"])
class TeacherNewsViewSet(viewsets.ReadOnlyModelViewSet):
    """Teacher-facing News feed.

    GET  /teacher/news/                 — active News visible to the caller,
                                           newest first, each with `is_read`.
    GET  /teacher/news/unread-count/    — {"count": N} of those not yet read.
    POST /teacher/news/<id>/read/       — mark one as read (idempotent).
    """

    serializer_class = NewsSerializer
    permission_classes = [IsAuthenticated, IsTeacher]

    def _teacher(self):
        return getattr(self.request.user, "teacher_profile", None)

    def get_queryset(self):
        teacher = self._teacher()
        if teacher is None:
            return News.objects.none()

        is_read = NewsRead.objects.filter(news=OuterRef("pk"), teacher=teacher)
        return News.objects.visible_to(teacher).annotate(is_read=Exists(is_read))

    @action(detail=False, methods=["get"], url_path="unread-count")
    def unread_count(self, request):
        teacher = self._teacher()
        if teacher is None:
            return Response({"count": 0})

        count = News.objects.visible_to(teacher).exclude(reads__teacher=teacher).count()
        return Response({"count": count})

    @action(detail=True, methods=["post"], url_path="read")
    def mark_read(self, request, pk=None):
        # get_object() runs against get_queryset() above, so a News item
        # that isn't visible to this Teacher (unpublished, expired, or
        # addressed to other teachers) 404s here rather than being markable.
        news = self.get_object()
        NewsRead.objects.get_or_create(news=news, teacher=self._teacher())
        return Response({"success": True})
