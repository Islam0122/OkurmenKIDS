from __future__ import annotations

from django.utils import timezone
from rest_framework import serializers

from .models import ParentReport, ParentReportImage
from .services import analytics, generation, periods


class ReportRequestSerializer(serializers.Serializer):
    """Report configuration — the same fields for preview (query string) and generate (JSON body)."""

    period = serializers.ChoiceField(choices=periods.PERIOD_KEYS, default="this_month")
    start_date = serializers.DateField(required=False, allow_null=True)
    end_date = serializers.DateField(required=False, allow_null=True)
    report_type = serializers.ChoiceField(choices=ParentReport.ReportType.choices, default=ParentReport.ReportType.GROUP)
    language = serializers.ChoiceField(choices=ParentReport.Language.choices, default=ParentReport.Language.RU)
    output_format = serializers.ChoiceField(
        choices=ParentReport.OutputFormat.choices, default=ParentReport.OutputFormat.BOTH,
    )
    include_table = serializers.BooleanField(default=True)
    include_group_stats = serializers.BooleanField(default=True)
    include_recommendations = serializers.BooleanField(default=True)
    include_comparison = serializers.BooleanField(default=True)
    student_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1), required=False, allow_empty=False, max_length=200,
    )

    def validate(self, attrs):
        today = self.context.get("today") or timezone.localdate()
        try:
            period = periods.resolve(
                attrs["period"], today=today, start_date=attrs.get("start_date"), end_date=attrs.get("end_date"),
            )
        except periods.PeriodError as exc:
            raise serializers.ValidationError({exc.field: [str(exc)]}) from exc
        attrs["resolved_period"] = period

        student_ids = attrs.get("student_ids")
        group = self.context.get("group")
        if student_ids and group is not None:
            allowed = {student.pk for student in analytics.active_students(group, period, today)}
            unknown = sorted(set(student_ids) - allowed)
            if unknown:
                raise serializers.ValidationError(
                    {"student_ids": [f"Студенты не являются активными студентами группы в этот период: {unknown}."]}
                )
        return attrs

    def to_request(self) -> generation.ReportRequest:
        data = self.validated_data
        return generation.ReportRequest(
            period=data["resolved_period"],
            report_type=data["report_type"],
            language=data["language"],
            output_format=data["output_format"],
            options={key: data[key] for key in generation.DEFAULT_OPTIONS},
            student_ids=sorted(set(data["student_ids"])) if data.get("student_ids") else None,
        )


class TextUpdateSerializer(serializers.Serializer):
    """POST /parent-reports/{id}/text/ — save an edited text, or get the text
    in another language (rendered from the stored snapshot, never recomputed)."""

    text = serializers.CharField(required=False, allow_blank=True, max_length=20000, trim_whitespace=False)
    student_id = serializers.IntegerField(required=False, min_value=1)
    language = serializers.ChoiceField(choices=ParentReport.Language.choices, required=False)
    reset = serializers.BooleanField(default=False)


class ParentReportImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ParentReportImage
        fields = ["id", "page", "student", "student_name", "width", "height"]


class ParentReportListSerializer(serializers.ModelSerializer):
    report_type_display = serializers.CharField(source="get_report_type_display", read_only=True)
    language_display = serializers.CharField(source="get_language_display", read_only=True)
    output_format_display = serializers.CharField(source="get_output_format_display", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    created_by_name = serializers.SerializerMethodField()
    images = ParentReportImageSerializer(many=True, read_only=True)
    final_text = serializers.CharField(read_only=True)
    students_count = serializers.SerializerMethodField()

    class Meta:
        model = ParentReport
        fields = [
            "id", "group", "group_name", "course_name", "report_type", "report_type_display",
            "language", "language_display", "output_format", "output_format_display",
            "period_key", "start_date", "end_date", "compare_start_date", "compare_end_date",
            "status", "status_display", "error", "final_text", "images", "students_count",
            "created_by_name", "created_at", "regenerated_from",
        ]

    def get_created_by_name(self, obj) -> str:
        return str(obj.created_by) if obj.created_by_id else ""

    def get_students_count(self, obj) -> int:
        return len((obj.snapshot or {}).get("students", []))


class ParentReportDetailSerializer(ParentReportListSerializer):
    recommendations = serializers.SerializerMethodField()

    class Meta(ParentReportListSerializer.Meta):
        fields = ParentReportListSerializer.Meta.fields + [
            "options", "text", "edited_text", "student_texts", "edited_student_texts", "snapshot", "recommendations",
        ]

    def get_recommendations(self, obj) -> dict:
        request = generation.ReportRequest(
            period=None, report_type=obj.report_type, language=obj.language,
            options={key: obj.options.get(key, default) for key, default in generation.DEFAULT_OPTIONS.items()},
        )
        if not obj.snapshot:
            return {}
        return generation.recommendations_for(obj.snapshot, request)
