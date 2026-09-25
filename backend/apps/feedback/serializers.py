from __future__ import annotations

from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from apps.academy.models import Group
from apps.users.models import Subject, Teacher

from .models import (
    NAME_MAX_LENGTH,
    OPTION_TEXT_MAX_LENGTH,
    QUESTION_TEXT_MAX_LENGTH,
    TEXT_ANSWER_MAX_LENGTH,
    QuestionOption,
    Survey,
    SurveyQuestion,
    SurveyResponse,
)
from .public import public_url


class QuestionOptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = QuestionOption
        fields = ["id", "text", "order"]


class SurveyQuestionSerializer(serializers.ModelSerializer):
    options = QuestionOptionSerializer(many=True, read_only=True)
    has_answers = serializers.SerializerMethodField()

    class Meta:
        model = SurveyQuestion
        fields = [
            "id",
            "text",
            "help_text",
            "question_type",
            "is_required",
            "order",
            "is_multiline",
            "min_length",
            "max_length",
            "min_selections",
            "max_selections",
            "options",
            "has_answers",
        ]

    def get_has_answers(self, obj) -> bool:
        # A question with answers is locked (see services.builder).
        return obj.answers.exists()


class OptionInputSerializer(serializers.Serializer):
    id = serializers.IntegerField(required=False, allow_null=True)
    text = serializers.CharField(max_length=OPTION_TEXT_MAX_LENGTH, allow_blank=True, trim_whitespace=True)


class QuestionInputSerializer(serializers.Serializer):
    """Shape/type checks only — business rules live in services.builder."""

    text = serializers.CharField(max_length=QUESTION_TEXT_MAX_LENGTH, allow_blank=True)
    help_text = serializers.CharField(max_length=300, allow_blank=True, required=False, default="")
    question_type = serializers.ChoiceField(choices=SurveyQuestion.QuestionType.choices)
    is_required = serializers.BooleanField(required=False, default=True)
    is_multiline = serializers.BooleanField(required=False, default=True)
    min_length = serializers.IntegerField(required=False, allow_null=True, min_value=0, max_value=TEXT_ANSWER_MAX_LENGTH)
    max_length = serializers.IntegerField(required=False, allow_null=True, min_value=1, max_value=TEXT_ANSWER_MAX_LENGTH)
    min_selections = serializers.IntegerField(required=False, allow_null=True, min_value=0)
    max_selections = serializers.IntegerField(required=False, allow_null=True, min_value=1)
    options = OptionInputSerializer(many=True, required=False, default=list)


class ReorderSerializer(serializers.Serializer):
    order = serializers.ListField(child=serializers.IntegerField(), allow_empty=False)


class SurveySerializer(serializers.ModelSerializer):
    """Admin survey settings. `status`, `public_token` and audit fields are
    read-only here — they change only through the explicit lifecycle
    actions (publish/close/reopen/regenerate-link), never by mass assignment."""

    group = serializers.PrimaryKeyRelatedField(queryset=Group.objects.all(), required=False, allow_null=True)
    teacher = serializers.PrimaryKeyRelatedField(queryset=Teacher.objects.all(), required=False, allow_null=True)
    subject = serializers.PrimaryKeyRelatedField(queryset=Subject.objects.all(), required=False, allow_null=True)
    public_url = serializers.SerializerMethodField()
    availability = serializers.SerializerMethodField()
    question_count = serializers.IntegerField(read_only=True, required=False)
    response_count = serializers.IntegerField(read_only=True, required=False)

    class Meta:
        model = Survey
        fields = [
            "id",
            "title",
            "description",
            "audience",
            "visibility_mode",
            "status",
            "availability",
            "starts_at",
            "ends_at",
            "max_responses",
            "allow_multiple_submissions",
            "child_name_mode",
            "ask_child_name_when_anonymous",
            "group",
            "teacher",
            "subject",
            "confirmation_message",
            "public_url",
            "question_count",
            "response_count",
            "published_at",
            "closed_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["status", "published_at", "closed_at", "created_at", "updated_at"]

    def get_public_url(self, obj) -> str | None:
        request = self.context.get("request")
        return public_url(request, obj) if request else None

    def get_availability(self, obj) -> str:
        return obj.availability()

    def validate(self, attrs):
        instance = Survey(**{**self._current_values(), **attrs})
        try:
            instance.clean()
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.message_dict)
        return attrs

    def _current_values(self) -> dict:
        if self.instance is None:
            return {}
        return {f: getattr(self.instance, f) for f in ("starts_at", "ends_at", "group", "teacher", "subject")}


class SurveyDetailSerializer(SurveySerializer):
    questions = SurveyQuestionSerializer(many=True, read_only=True)

    class Meta(SurveySerializer.Meta):
        fields = SurveySerializer.Meta.fields + ["questions"]


class AdminAnswerSerializer(serializers.Serializer):
    question_id = serializers.IntegerField()
    question = serializers.CharField()
    question_type = serializers.CharField()
    text = serializers.CharField(allow_blank=True)
    options = serializers.ListField(child=serializers.CharField())


class SurveyResponseSerializer(serializers.ModelSerializer):
    """Admin view of one response. An anonymous response has no stored
    identity at all, so there is nothing to hide beyond showing "Аноним"."""

    respondent = serializers.CharField(source="display_name")
    child_name_self_reported = serializers.CharField(source="child_name")
    answers = serializers.SerializerMethodField()

    class Meta:
        model = SurveyResponse
        fields = ["id", "visibility", "respondent", "child_name_self_reported", "submitted_at", "answers"]

    def get_answers(self, obj) -> list[dict]:
        rows = []
        for answer in sorted(obj.answers.all(), key=lambda a: (a.question.order, a.question_id)):
            rows.append(
                {
                    "question_id": answer.question_id,
                    "question": answer.question.text,
                    "question_type": answer.question.question_type,
                    "text": answer.text_value,
                    "options": [link.option.text for link in answer.option_links.all()],
                }
            )
        return rows


class PublicSubmissionSerializer(serializers.Serializer):
    visibility = serializers.ChoiceField(choices=SurveyResponse.Visibility.choices, required=False, allow_null=True)
    respondent_name = serializers.CharField(max_length=NAME_MAX_LENGTH, required=False, allow_blank=True, default="")
    child_name = serializers.CharField(max_length=NAME_MAX_LENGTH, required=False, allow_blank=True, default="")
    answers = serializers.DictField(child=serializers.JSONField(), required=False, default=dict)
