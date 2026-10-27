from __future__ import annotations

import re

from django.utils import timezone
from rest_framework import serializers

from apps.users.models import User

from .models import Candidate, HRActivity, Interview, Vacancy
from .services import pipeline
from .services.reports import activity_brief

PHONE_RE = re.compile(r"^\+?[\d\s()\-]{5,32}$")


def person(user) -> dict | None:
    if user is None:
        return None
    return {"id": user.pk, "full_name": user.get_full_name() or user.username, "role_label": user.get_role_display()}


class PersonField(serializers.PrimaryKeyRelatedField):
    """Ответственный или интервьюер — любой активный пользователь LMS."""

    def get_queryset(self):
        return User.objects.filter(is_active=True)


# ---------------------------------------------------------------------------
# Вакансии
# ---------------------------------------------------------------------------

class VacancySerializer(serializers.ModelSerializer):
    responsible = PersonField(allow_null=True, required=False)
    responsible_info = serializers.SerializerMethodField()
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    candidates_count = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = Vacancy
        fields = ["id", "title", "description", "department", "status", "status_label", "responsible",
                  "responsible_info", "candidates_count", "created_at", "updated_at"]
        read_only_fields = ["created_at", "updated_at"]

    def get_responsible_info(self, obj):
        return person(obj.responsible)

    def validate_title(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Укажите название вакансии.")
        return value


# ---------------------------------------------------------------------------
# Кандидаты
# ---------------------------------------------------------------------------

class CandidateSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    source_label = serializers.CharField(source="get_source_display", read_only=True)
    position_label = serializers.CharField(read_only=True)
    vacancy_info = serializers.SerializerMethodField()
    responsible_info = serializers.SerializerMethodField()
    hired_user_info = serializers.SerializerMethodField()
    allowed_statuses = serializers.SerializerMethodField()
    next_interview_at = serializers.DateTimeField(read_only=True, default=None)

    class Meta:
        model = Candidate
        fields = ["id", "last_name", "first_name", "middle_name", "full_name", "phone", "email", "vacancy",
                  "vacancy_info", "position", "position_label", "source", "source_label", "source_details",
                  "added_on", "responsible", "responsible_info", "notes", "status", "status_label",
                  "status_changed_at", "hired_user_info", "allowed_statuses", "next_interview_at", "created_at",
                  "updated_at"]
        read_only_fields = fields

    def get_vacancy_info(self, obj):
        if not obj.vacancy_id:
            return None
        return {"id": obj.vacancy_id, "title": obj.vacancy.title, "status": obj.vacancy.status}

    def get_responsible_info(self, obj):
        return person(obj.responsible)

    def get_hired_user_info(self, obj):
        user = obj.hired_user
        return {"id": user.pk, "username": user.username, "is_active": user.is_active} if user else None

    def get_allowed_statuses(self, obj):
        labels = dict(Candidate.Status.choices)
        return [{"value": value, "label": labels[value]} for value in pipeline.allowed_manual_statuses(obj)]


class CandidateWriteSerializer(serializers.ModelSerializer):
    vacancy = serializers.PrimaryKeyRelatedField(queryset=Vacancy.objects.all(), allow_null=True, required=False)
    responsible = PersonField(allow_null=True, required=False)

    class Meta:
        model = Candidate
        fields = ["last_name", "first_name", "middle_name", "phone", "email", "vacancy", "position", "source",
                  "source_details", "added_on", "responsible", "notes"]

    def validate_phone(self, value):
        value = value.strip()
        if value and not PHONE_RE.match(value):
            raise serializers.ValidationError("Телефон: цифры, пробелы, скобки, дефис и «+».")
        return value

    def validate_added_on(self, value):
        if value > timezone.localdate():
            raise serializers.ValidationError("Дата добавления не может быть в будущем.")
        return value

    def validate_vacancy(self, value):
        current = getattr(self.instance, "vacancy_id", None)
        if value is not None and value.pk != current and value.status != Vacancy.Status.OPEN:
            raise serializers.ValidationError("Кандидата можно добавить только на открытую вакансию.")
        return value

    def validate(self, attrs):
        merged = {field: attrs.get(field, getattr(self.instance, field, None)) for field in
                  ("first_name", "last_name", "phone", "email", "vacancy", "position")}
        errors = {}
        for field in ("first_name", "last_name"):
            if not (merged[field] or "").strip():
                errors[field] = "Обязательное поле."
        if not (merged["phone"] or merged["email"]):
            errors["phone"] = "Укажите телефон или email."
        if not merged["vacancy"] and not (merged["position"] or "").strip():
            errors["vacancy"] = "Выберите вакансию или укажите должность."
        if errors:
            raise serializers.ValidationError(errors)
        return attrs


class StatusChangeSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=Candidate.Status.choices)
    comment = serializers.CharField(required=False, allow_blank=True, max_length=1000)


class NoteSerializer(serializers.Serializer):
    text = serializers.CharField(max_length=4000)

    def validate_text(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Заметка не может быть пустой.")
        return value


# ---------------------------------------------------------------------------
# Собеседования
# ---------------------------------------------------------------------------

class InterviewSerializer(serializers.ModelSerializer):
    candidate_info = serializers.SerializerMethodField()
    vacancy_info = serializers.SerializerMethodField()
    interviewer_info = serializers.SerializerMethodField()
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    format_label = serializers.CharField(source="get_format_display", read_only=True)
    result_label = serializers.CharField(source="get_result_display", read_only=True)
    next_step_label = serializers.CharField(source="get_next_step_display", read_only=True)
    scheduled_at = serializers.SerializerMethodField()

    class Meta:
        model = Interview
        fields = ["id", "candidate", "candidate_info", "vacancy", "vacancy_info", "scheduled_at", "duration_minutes",
                  "format", "format_label", "location", "meeting_url", "interviewer", "interviewer_info", "notes",
                  "status", "status_label", "reschedule_count", "cancel_reason", "cancelled_at", "result",
                  "result_label", "result_comment", "next_step", "next_step_label", "next_step_date", "completed_at",
                  "created_at"]
        read_only_fields = fields

    def get_scheduled_at(self, obj):
        return timezone.localtime(obj.scheduled_at).isoformat()

    def get_candidate_info(self, obj):
        c = obj.candidate
        return {"id": c.pk, "full_name": c.full_name, "status": c.status, "status_label": c.get_status_display()}

    def get_vacancy_info(self, obj):
        if obj.vacancy_id:
            return {"id": obj.vacancy_id, "title": obj.vacancy.title}
        return {"id": None, "title": obj.candidate.position} if obj.candidate.position else None

    def get_interviewer_info(self, obj):
        return person(obj.interviewer)


class _InterviewDetailsMixin(serializers.Serializer):
    def _check_place(self, attrs, instance=None):
        fmt = attrs.get("format", getattr(instance, "format", Interview.Format.IN_PERSON))
        url = attrs.get("meeting_url", getattr(instance, "meeting_url", ""))
        location = attrs.get("location", getattr(instance, "location", ""))
        if fmt == Interview.Format.ONLINE and not url:
            raise serializers.ValidationError({"meeting_url": "Для онлайн-собеседования укажите ссылку на встречу."})
        if fmt == Interview.Format.IN_PERSON and not (location or "").strip():
            raise serializers.ValidationError({"location": "Укажите место проведения."})


class InterviewCreateSerializer(_InterviewDetailsMixin, serializers.ModelSerializer):
    candidate = serializers.PrimaryKeyRelatedField(queryset=Candidate.objects.all())
    vacancy = serializers.PrimaryKeyRelatedField(queryset=Vacancy.objects.all(), allow_null=True, required=False)
    interviewer = PersonField()
    confirm = serializers.BooleanField(required=False, default=False, write_only=True)

    class Meta:
        model = Interview
        fields = ["candidate", "vacancy", "scheduled_at", "duration_minutes", "format", "location", "meeting_url",
                  "interviewer", "notes", "confirm"]

    def validate(self, attrs):
        self._check_place(attrs)
        return attrs


class InterviewUpdateSerializer(_InterviewDetailsMixin, serializers.ModelSerializer):
    interviewer = PersonField(required=False)
    confirm = serializers.BooleanField(required=False, default=False, write_only=True)

    class Meta:
        model = Interview
        fields = ["scheduled_at", "duration_minutes", "format", "location", "meeting_url", "interviewer", "notes",
                  "confirm"]

    def validate(self, attrs):
        self._check_place(attrs, self.instance)
        return attrs


class CancelSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=255)

    def validate_reason(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Укажите причину отмены.")
        return value


class ResultSerializer(serializers.Serializer):
    result = serializers.ChoiceField(choices=Interview.Result.choices)
    next_step = serializers.ChoiceField(choices=Interview.NextStep.choices)
    result_comment = serializers.CharField(required=False, allow_blank=True, max_length=4000)
    next_step_date = serializers.DateField(required=False, allow_null=True)


class ActivitySerializer(serializers.ModelSerializer):
    class Meta:
        model = HRActivity
        fields = ["id"]

    def to_representation(self, instance):
        return activity_brief(instance)
