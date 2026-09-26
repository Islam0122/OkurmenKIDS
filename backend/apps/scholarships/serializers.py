from __future__ import annotations

from rest_framework import serializers

from apps.academy.models import Student
from apps.users.models import Subject, Teacher

from .models import (
    AWARD_DAY_CHOICES,
    ScholarshipAward,
    ScholarshipEvaluation,
    ScholarshipPeriod,
    ScholarshipSubjectScore,
    TrainerFeedback,
)


class ScholarshipPeriodSerializer(serializers.ModelSerializer):
    evaluations_count = serializers.IntegerField(read_only=True, default=None)
    eligible_count = serializers.IntegerField(read_only=True, default=None)
    recipients_count = serializers.IntegerField(read_only=True, default=None)
    approved_count = serializers.IntegerField(read_only=True, default=None)
    average_score = serializers.DecimalField(max_digits=5, decimal_places=2, read_only=True, default=None)
    total_amount = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True, default=None)
    is_manual = serializers.BooleanField(read_only=True)
    is_unlimited = serializers.BooleanField(read_only=True)

    class Meta:
        model = ScholarshipPeriod
        fields = [
            "id", "title", "award_day", "is_manual", "period_start", "period_end", "evaluation_date", "status",
            "max_recipients", "is_unlimited", "attendance_weight", "homework_weight", "feedback_weight",
            "subject_aggregation", "late_homework_credit", "min_overall_score", "min_marked_lessons",
            "require_complete_feedback", "award_amount", "last_calculated_at", "approved_at",
            "evaluations_count", "eligible_count", "recipients_count", "approved_count", "average_score",
            "total_amount", "created_at", "updated_at",
        ]
        read_only_fields = fields


class PeriodWriteSerializer(serializers.Serializer):
    """Create / PATCH a period. `max_recipients: null` = без ограничения."""

    title = serializers.CharField(max_length=150, required=False, allow_blank=True)
    period_start = serializers.DateField()
    period_end = serializers.DateField()
    max_recipients = serializers.IntegerField(min_value=1, max_value=1000, allow_null=True)

    def validate(self, attrs):
        start = attrs.get("period_start", getattr(self.instance, "period_start", None))
        end = attrs.get("period_end", getattr(self.instance, "period_end", None))
        if start and end and end < start:
            raise serializers.ValidationError({"period_end": ["Дата окончания не может быть раньше даты начала."]})
        return attrs


class AwardAddSerializer(serializers.Serializer):
    evaluation = serializers.PrimaryKeyRelatedField(queryset=ScholarshipEvaluation.objects.all())


class TeacherPeriodSerializer(serializers.ModelSerializer):
    """What a Teacher sees of a period: its dates and whether it still
    accepts feedback — none of the ranking/weights."""

    class Meta:
        model = ScholarshipPeriod
        fields = ["id", "title", "award_day", "period_start", "period_end", "evaluation_date", "status"]
        read_only_fields = fields


class GenerateRequestSerializer(serializers.Serializer):
    award_day = serializers.ChoiceField(choices=AWARD_DAY_CHOICES, required=False, default=1)
    award_date = serializers.DateField(
        required=False,
        help_text="Дата начисления цикла (должна совпадать с днём цикла). По умолчанию — последняя наступившая.",
    )


class SubjectScoreSerializer(serializers.ModelSerializer):
    class Meta:
        model = ScholarshipSubjectScore
        fields = [
            "subject", "subject_name", "lessons_attended", "lessons_missed", "lessons_excused", "lessons_unmarked",
            "homework_required", "homework_completed", "feedback_expected", "feedback_received",
            "attendance_score", "homework_score", "feedback_score", "subject_score", "aggregation_weight",
        ]
        read_only_fields = fields


class AwardSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source="evaluation.student_name", read_only=True)

    class Meta:
        model = ScholarshipAward
        fields = [
            "id", "period", "student", "student_name", "evaluation", "rank", "award_date", "amount",
            "status", "approved_by", "approved_at", "created_at",
        ]
        read_only_fields = fields


class EvaluationListSerializer(serializers.ModelSerializer):
    award_status = serializers.SerializerMethodField()

    class Meta:
        model = ScholarshipEvaluation
        fields = [
            "id", "period", "student", "student_name", "group", "group_name", "course_name", "enrollment_date",
            "overall_score", "attendance_score", "homework_score", "feedback_score", "lessons_count",
            "subjects_count", "rank", "eligibility_status", "ineligibility_reason", "award_status",
        ]
        read_only_fields = fields

    def get_award_status(self, obj) -> str | None:
        award = getattr(obj, "award", None)
        return award.status if award else None


class EvaluationDetailSerializer(EvaluationListSerializer):
    subject_scores = SubjectScoreSerializer(many=True, read_only=True)
    period_start = serializers.DateField(source="period.period_start", read_only=True)
    period_end = serializers.DateField(source="period.period_end", read_only=True)

    class Meta(EvaluationListSerializer.Meta):
        fields = EvaluationListSerializer.Meta.fields + [
            "period_start", "period_end", "data_warnings", "subject_scores", "created_at", "updated_at",
        ]
        read_only_fields = fields


class TrainerFeedbackSerializer(serializers.ModelSerializer):
    score = serializers.DecimalField(max_digits=5, decimal_places=2, read_only=True)
    student_name = serializers.CharField(source="student.__str__", read_only=True)
    subject_name = serializers.CharField(source="subject.name", read_only=True)
    teacher_name = serializers.CharField(source="teacher.__str__", read_only=True)
    period = serializers.PrimaryKeyRelatedField(queryset=ScholarshipPeriod.objects.all())
    student = serializers.PrimaryKeyRelatedField(queryset=Student.objects.all())
    subject = serializers.PrimaryKeyRelatedField(queryset=Subject.objects.all())
    teacher = serializers.PrimaryKeyRelatedField(
        queryset=Teacher.objects.all(), required=False,
        help_text="Только для администратора. Тренер всегда пишет оценку от своего имени.",
    )

    class Meta:
        model = TrainerFeedback
        fields = [
            "id", "period", "student", "student_name", "subject", "subject_name", "teacher", "teacher_name",
            "progress", "participation", "discipline", "understanding", "comment", "score",
            "created_at", "updated_at",
        ]
        read_only_fields = ["id", "score", "created_at", "updated_at"]
        # Uniqueness is checked in the view (it depends on the resolved
        # teacher) so a duplicate gets one clear message, not a DRF default.
        validators = []


class RequiredFeedbackSerializer(serializers.Serializer):
    student = serializers.IntegerField(source="student.id")
    student_name = serializers.CharField(source="student.__str__")
    subject = serializers.IntegerField(source="subject.id")
    subject_name = serializers.CharField(source="subject.name")
    is_submitted = serializers.BooleanField()
    feedback = TrainerFeedbackSerializer(allow_null=True)
