"""REST serializers of the test bank (admin API, api_views.py)."""
from __future__ import annotations

from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from .models import DifficultyLevel, Question, Test
from .services import questions as question_service
from .services.question_rules import CodeTestData, OptionData, QuestionData


class TestSerializer(serializers.ModelSerializer):
    subject_name = serializers.CharField(source="subject.name", read_only=True, default=None)
    level_display = serializers.CharField(source="get_level_display", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    question_count = serializers.IntegerField(read_only=True, source="questions_total", default=None)
    attempt_count = serializers.IntegerField(read_only=True, source="attempts_total", default=None)

    class Meta:
        model = Test
        fields = (
            "id", "title", "description", "subject", "subject_name", "level", "level_display",
            "status", "status_display", "time_limit_minutes", "max_attempts", "passing_score",
            "questions_per_attempt", "shuffle_questions", "shuffle_options", "show_result",
            "show_correct_answers", "allow_retry", "available_from", "available_until",
            "question_count", "attempt_count", "created_at", "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")

    def validate(self, attrs):
        start = attrs.get("available_from", getattr(self.instance, "available_from", None))
        end = attrs.get("available_until", getattr(self.instance, "available_until", None))
        if start and end and start >= end:
            raise serializers.ValidationError({"available_until": "Дата окончания должна быть позже даты начала."})
        if attrs.get("status") == "active" and (self.instance is None or not self.instance.questions.exists()):
            raise serializers.ValidationError({"status": "Нельзя опубликовать тест без вопросов."})
        return attrs


class OptionSerializer(serializers.Serializer):
    id = serializers.UUIDField(required=False, allow_null=True)
    text = serializers.CharField(allow_blank=True, max_length=1024)
    is_correct = serializers.BooleanField(default=False)
    order = serializers.IntegerField(read_only=True)


class CodeTestSerializer(serializers.Serializer):
    input = serializers.CharField(allow_blank=True, required=False, default="", trim_whitespace=False)
    expected_output = serializers.CharField(allow_blank=True, trim_whitespace=False)


class QuestionSerializer(serializers.ModelSerializer):
    """A question with its options. Writes go through
    services.questions.save_question — the same rules as the admin editor
    (services/question_rules.py)."""

    options = OptionSerializer(many=True, required=False)
    code_tests = CodeTestSerializer(many=True, required=False)
    correct_answers = serializers.ListField(child=serializers.CharField(allow_blank=True), required=False)
    question_type_display = serializers.CharField(source="get_question_type_display", read_only=True)

    class Meta:
        model = Question
        fields = (
            "id", "test", "order", "question_type", "question_type_display", "text", "hint", "points",
            "is_required", "difficulty", "language", "answer_match", "correct_answers",
            "starter_code", "code_tests", "options", "created_at",
        )
        read_only_fields = ("id", "test", "order", "created_at")

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data["options"] = [
            {"id": str(o.pk), "text": o.text, "is_correct": o.is_correct, "order": o.order}
            for o in instance.options.order_by("order", "pk")
        ]
        return data

    def _value(self, attrs, name, default):
        if name in attrs:
            return attrs[name]
        if self.instance is not None:
            if name == "options":
                return [{"id": o.pk, "text": o.text, "is_correct": o.is_correct} for o in self.instance.options.order_by("order", "pk")]
            return getattr(self.instance, name)
        return default

    def _save(self, test, attrs, question=None) -> Question:
        question_type = self._value(attrs, "question_type", "single_choice")
        data = QuestionData(
            question_type=question_type,
            text=self._value(attrs, "text", ""),
            language=self._value(attrs, "language", ""),
            correct_answers=list(self._value(attrs, "correct_answers", [])),
            options=[
                OptionData(o.get("text", ""), o.get("is_correct", False), str(o["id"]) if o.get("id") else None)
                for o in self._value(attrs, "options", [])
            ] if question_type in ("single_choice", "multiple_choice") else [],
            code_tests=[CodeTestData(t.get("input", ""), t.get("expected_output", "")) for t in self._value(attrs, "code_tests", [])],
        )
        extra = {
            name: attrs[name]
            for name in ("hint", "points", "is_required", "answer_match", "starter_code", "difficulty")
            if name in attrs
        }
        if question is None:
            extra.setdefault("difficulty", DifficultyLevel.MEDIUM)
        try:
            return question_service.save_question(test, data, question=question, **extra)
        except DjangoValidationError as error:
            raise serializers.ValidationError(error.message_dict if hasattr(error, "error_dict") else error.messages)

    def create(self, validated_data):
        return self._save(self.context["test"], validated_data)

    def update(self, instance, validated_data):
        return self._save(instance.test, validated_data, question=instance)
