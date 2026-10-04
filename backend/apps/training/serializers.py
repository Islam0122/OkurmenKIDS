"""Shapes of the public training API (read-only content + request bodies)."""
from rest_framework import serializers

from apps.testing.models import TestSession

from .models import PortalSettings, TrainingLink, TrainingVideo
from .services import category_of, exam_url_for, question_count, security_settings


class PortalSettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = PortalSettings
        fields = ("hero_title", "hero_subtitle", "start_button_label", "exam_button_label", "exam_url", "exam_open_in_new_tab")


class EventSerializer(serializers.Serializer):
    event_type = serializers.CharField(max_length=32)
    metadata = serializers.DictField(required=False)


class TrainingTestSerializer(serializers.Serializer):
    """A public training session, described by its test's settings."""

    def to_representation(self, session: TestSession) -> dict:
        test = session.test
        return {
            "id": str(session.pk),
            "title": session.title or test.title,
            "description": test.description,
            "subject": test.subject.name if test.subject_id else "",
            "category": category_of(test),
            "level": test.level,
            "level_display": test.get_level_display(),
            "image_url": test.image_url or None,
            "duration": session.effective_time_limit_minutes,
            "questions_count": question_count(test),
            "max_attempts": session.max_attempts_per_student,
            "passing_score": test.passing_score,
            "show_explanation": test.show_correct_answers,
            "show_result": test.show_result,
            "allow_retry": test.allow_retry,
            "course": session.course.name if session.course_id else "",
            "exam_url": exam_url_for(session),
            "security": security_settings(session),
            "published": True,
        }


class TrainingVideoSerializer(serializers.ModelSerializer):
    class Meta:
        model = TrainingVideo
        fields = ("id", "title", "description", "video_url", "thumbnail_url", "category", "duration", "order")


class TrainingLinkSerializer(serializers.ModelSerializer):
    class Meta:
        model = TrainingLink
        fields = ("id", "title", "description", "url", "category", "icon", "order")


class StartAttemptSerializer(serializers.Serializer):
    test_id = serializers.UUIDField()
    student_name = serializers.CharField(max_length=200, trim_whitespace=True, allow_blank=True)


class AnswerSerializer(serializers.Serializer):
    options = serializers.ListField(child=serializers.CharField(max_length=64), required=False, max_length=50)
    text = serializers.CharField(required=False, allow_blank=True, trim_whitespace=False, max_length=20000)
