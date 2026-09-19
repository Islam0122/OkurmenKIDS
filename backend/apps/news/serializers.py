from __future__ import annotations

from rest_framework import serializers

from .models import News


class NewsSerializer(serializers.ModelSerializer):
    """Teacher-facing read-only representation.

    `is_read` is never computed per-instance here — it must come from an
    `is_read` annotation already applied to the queryset (see
    TeacherNewsViewSet.get_queryset), so listing many News rows costs one
    query, not one per row.
    """

    type_label = serializers.CharField(source="get_type_display", read_only=True)
    is_read = serializers.BooleanField(read_only=True)

    class Meta:
        model = News
        fields = [
            "id",
            "title",
            "text",
            "type",
            "type_label",
            "created_at",
            "expires_at",
            "is_read",
        ]
        read_only_fields = fields
