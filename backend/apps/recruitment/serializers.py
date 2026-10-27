from __future__ import annotations

import re

from django.utils import timezone
from rest_framework import serializers

from apps.users.models import User

from .models import AccountRequest, Application, Candidate, HRActivity, InternalNote, Interview, Vacancy
from .services import hiring, intake, pipeline, vacancies
from .services.common import unique_slug
from .services.reports import activity_brief

PHONE_RE = re.compile(r"^\+?[\d\s()\-]{5,32}$")
SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def person(user) -> dict | None:
    if user is None:
        return None
    return {"id": user.pk, "full_name": user.get_full_name() or user.username, "role_label": user.get_role_display()}


def choices(enum) -> list[dict]:
    return [{"value": value, "label": label} for value, label in enum.choices]


def clean_phone(value: str) -> str:
    value = value.strip()
    if value and not PHONE_RE.match(value):
        raise serializers.ValidationError("Телефон: цифры, пробелы, скобки, дефис и «+».")
    digits = re.sub(r"\D", "", value)
    if value and not 7 <= len(digits) <= 15:
        raise serializers.ValidationError("Проверьте номер телефона: от 7 до 15 цифр.")
    return value


class PersonField(serializers.PrimaryKeyRelatedField):
    """Ответственный или интервьюер — любой активный пользователь LMS."""

    def get_queryset(self):
        return User.objects.filter(is_active=True)


# ---------------------------------------------------------------------------
# Вакансии
# ---------------------------------------------------------------------------

VACANCY_TEXT = ["title", "slug", "department", "summary", "description", "responsibilities", "requirements",
                "nice_to_have", "conditions", "selection_stages", "location", "work_format", "employment_type",
                "salary_min", "salary_max", "salary_currency", "show_salary", "closes_on", "responsible"]


class VacancySerializer(serializers.ModelSerializer):
    responsible_info = serializers.SerializerMethodField()
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    work_format_label = serializers.CharField(source="get_work_format_display", read_only=True)
    employment_type_label = serializers.CharField(source="get_employment_type_display", read_only=True)
    applications_count = serializers.IntegerField(read_only=True, default=0)
    active_count = serializers.IntegerField(read_only=True, default=0)
    new_count = serializers.IntegerField(read_only=True, default=0)
    allowed_statuses = serializers.SerializerMethodField()
    missing_for_publishing = serializers.SerializerMethodField()
    is_accepting = serializers.BooleanField(read_only=True)

    class Meta:
        model = Vacancy
        fields = ["id", *VACANCY_TEXT, "status", "status_label", "work_format_label", "employment_type_label",
                  "responsible_info", "published_at", "closed_at", "archived_at", "applications_count", "active_count",
                  "new_count", "allowed_statuses", "missing_for_publishing", "is_accepting", "created_at",
                  "updated_at"]
        read_only_fields = fields

    def get_responsible_info(self, obj):
        return person(obj.responsible)

    def get_allowed_statuses(self, obj):
        labels = dict(Vacancy.Status.choices)
        return [{"value": value, "label": labels[value]} for value in vacancies.allowed(obj)]

    def get_missing_for_publishing(self, obj):
        return vacancies.missing_for_publishing(obj)


class VacancyWriteSerializer(serializers.ModelSerializer):
    """Поля карточки. Статус меняется только действиями (`/status/`)."""

    responsible = PersonField(allow_null=True, required=False)
    slug = serializers.CharField(max_length=80, required=False, allow_blank=True)

    class Meta:
        model = Vacancy
        fields = VACANCY_TEXT

    def validate_title(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Укажите название вакансии.")
        return value

    def validate_slug(self, value):
        value = value.strip().lower()
        if value and not SLUG_RE.match(value):
            raise serializers.ValidationError("Адрес: латинские буквы, цифры и дефис, например sales-manager.")
        if value:
            qs = Vacancy.objects.filter(slug=value)
            if self.instance is not None:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise serializers.ValidationError("Такой адрес уже занят другой вакансией.")
        return value

    def validate_closes_on(self, value):
        current = getattr(self.instance, "closes_on", None)
        if value and value != current and value < timezone.localdate():
            raise serializers.ValidationError("Дата окончания приёма не может быть в прошлом.")
        return value

    def validate(self, attrs):
        low = attrs.get("salary_min", getattr(self.instance, "salary_min", None))
        high = attrs.get("salary_max", getattr(self.instance, "salary_max", None))
        if low is not None and high is not None and low > high:
            raise serializers.ValidationError({"salary_max": "«До» должно быть не меньше «от»."})
        show = attrs.get("show_salary", getattr(self.instance, "show_salary", False))
        if show and low is None and high is None:
            raise serializers.ValidationError({"show_salary": "Чтобы публиковать зарплату, укажите её."})
        return attrs

    def create(self, validated_data):
        validated_data["slug"] = validated_data.get("slug") or unique_slug(validated_data["title"])
        return super().create(validated_data)

    def update(self, instance, validated_data):
        if "slug" in validated_data and not validated_data["slug"]:
            validated_data.pop("slug")
        return super().update(instance, validated_data)


class VacancyStatusSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=Vacancy.Status.choices)


# ---------------------------------------------------------------------------
# Кандидаты и отклики
# ---------------------------------------------------------------------------

PERSON_FIELDS = ["last_name", "first_name", "middle_name", "phone", "email", "city", "experience", "education",
                 "skills", "portfolio_url"]


class CandidatePersonMixin(serializers.Serializer):
    def validate_phone(self, value):
        return clean_phone(value)

    def _check_person(self, attrs, instance=None):
        merged = {f: attrs.get(f, getattr(instance, f, "")) for f in ("first_name", "phone", "email")}
        errors = {}
        if not (merged["first_name"] or "").strip():
            errors["first_name"] = "Обязательное поле."
        if not (merged["phone"] or merged["email"]):
            errors["phone"] = "Укажите телефон или email."
        if errors:
            raise serializers.ValidationError(errors)


class CandidateWriteSerializer(CandidatePersonMixin, serializers.ModelSerializer):
    class Meta:
        model = Candidate
        fields = PERSON_FIELDS

    def validate(self, attrs):
        self._check_person(attrs, self.instance)
        return attrs


def application_status_options(application) -> list[dict]:
    labels = dict(Application.Status.choices)
    return [{"value": value, "label": labels[value]} for value in pipeline.allowed_manual_statuses(application)]


class ApplicationSerializer(serializers.ModelSerializer):
    candidate_info = serializers.SerializerMethodField()
    vacancy_info = serializers.SerializerMethodField()
    position_label = serializers.CharField(read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    source_label = serializers.CharField(source="get_source_display", read_only=True)
    channel_label = serializers.CharField(source="get_channel_display", read_only=True)
    responsible_info = serializers.SerializerMethodField()
    hired_user_info = serializers.SerializerMethodField()
    allowed_statuses = serializers.SerializerMethodField()
    has_resume = serializers.SerializerMethodField()
    next_interview_at = serializers.DateTimeField(read_only=True, default=None)
    pending_account_request = serializers.SerializerMethodField()

    class Meta:
        model = Application
        fields = ["id", "number", "candidate", "candidate_info", "vacancy", "vacancy_info", "position",
                  "position_label", "channel", "channel_label", "source", "source_label", "source_details",
                  "applied_on", "responsible", "responsible_info", "status", "status_label", "status_changed_at",
                  "cover_letter", "submitted_data", "has_resume", "resume_name", "resume_size", "consent_at",
                  "consent_version", "needs_duplicate_review", "hired_user_info", "allowed_statuses",
                  "next_interview_at", "pending_account_request", "created_at", "updated_at"]
        read_only_fields = fields

    def get_candidate_info(self, obj):
        c = obj.candidate
        return {"id": c.pk, "full_name": c.full_name, "phone": c.phone, "email": c.email,
                "erased": c.erased_at is not None}

    def get_vacancy_info(self, obj):
        if not obj.vacancy_id:
            return None
        v = obj.vacancy
        return {"id": v.pk, "title": v.title, "status": v.status, "status_label": v.get_status_display(),
                "slug": v.slug}

    def get_responsible_info(self, obj):
        return person(obj.responsible)

    def get_hired_user_info(self, obj):
        user = obj.hired_user
        return {"id": user.pk, "username": user.username, "is_active": user.is_active,
                "role_label": user.get_role_display()} if user else None

    def get_allowed_statuses(self, obj):
        return application_status_options(obj)

    def get_has_resume(self, obj):
        return bool(obj.resume)

    def get_pending_account_request(self, obj):
        pending = next((r for r in obj.account_requests.all() if r.status == AccountRequest.Status.PENDING), None)
        if pending is None:
            return None
        return {"id": pending.pk, "username": pending.username, "role": pending.role,
                "role_label": User.Role(pending.role).label, "created_at": timezone.localtime(pending.created_at).isoformat()}


class CandidateSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(read_only=True)
    applications = serializers.SerializerMethodField()
    merged_into_info = serializers.SerializerMethodField()
    possible_duplicates = serializers.SerializerMethodField()

    class Meta:
        model = Candidate
        fields = ["id", *PERSON_FIELDS, "full_name", "merged_into", "merged_into_info", "erased_at", "applications",
                  "possible_duplicates", "created_at", "updated_at"]
        read_only_fields = fields

    def get_applications(self, obj):
        qs = self.context.get("applications")
        if qs is None:
            qs = obj.applications.select_related("candidate", "vacancy", "responsible", "hired_user") \
                .prefetch_related("account_requests")
        return ApplicationSerializer(qs, many=True).data

    def get_merged_into_info(self, obj):
        target = obj.merged_into
        return {"id": target.pk, "full_name": target.full_name} if target else None

    def get_possible_duplicates(self, obj):
        if not self.context.get("with_duplicates") or obj.erased_at or obj.merged_into_id:
            return []
        matches = intake.find_matches(obj.email, obj.phone_digits, exclude=obj.pk)
        return [intake.match_brief(c, obj.email, obj.phone_digits) for c in matches[:10]]


class CandidateListSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(read_only=True)
    applications_count = serializers.IntegerField(read_only=True, default=0)
    active_count = serializers.IntegerField(read_only=True, default=0)
    last_applied_on = serializers.DateField(read_only=True, default=None)

    class Meta:
        model = Candidate
        fields = ["id", "full_name", "phone", "email", "city", "applications_count", "active_count",
                  "last_applied_on", "erased_at", "merged_into", "created_at"]
        read_only_fields = fields


class ApplicationCreateSerializer(CandidatePersonMixin, serializers.Serializer):
    """Отклик, добавленный HR: существующий кандидат (`candidate`) или новый
    человек (поля профиля)."""

    candidate = serializers.PrimaryKeyRelatedField(queryset=Candidate.objects.all(), required=False, allow_null=True)
    last_name = serializers.CharField(max_length=100, required=False, allow_blank=True)
    first_name = serializers.CharField(max_length=100, required=False, allow_blank=True)
    middle_name = serializers.CharField(max_length=100, required=False, allow_blank=True)
    phone = serializers.CharField(max_length=32, required=False, allow_blank=True)
    email = serializers.EmailField(required=False, allow_blank=True)
    city = serializers.CharField(max_length=100, required=False, allow_blank=True)
    experience = serializers.CharField(required=False, allow_blank=True, max_length=5000)
    education = serializers.CharField(required=False, allow_blank=True, max_length=3000)
    skills = serializers.CharField(required=False, allow_blank=True, max_length=3000)
    portfolio_url = serializers.URLField(required=False, allow_blank=True)
    vacancy = serializers.PrimaryKeyRelatedField(queryset=Vacancy.objects.all(), required=False, allow_null=True)
    position = serializers.CharField(max_length=150, required=False, allow_blank=True)
    source = serializers.ChoiceField(choices=Application.Source.choices, default=Application.Source.OTHER)
    source_details = serializers.CharField(max_length=255, required=False, allow_blank=True)
    applied_on = serializers.DateField(required=False)
    responsible = PersonField(allow_null=True, required=False)
    cover_letter = serializers.CharField(required=False, allow_blank=True, max_length=5000)
    confirm_new = serializers.BooleanField(required=False, default=False)

    def validate_applied_on(self, value):
        if value > timezone.localdate():
            raise serializers.ValidationError("Дата отклика не может быть в будущем.")
        return value

    def validate(self, attrs):
        if not attrs.get("candidate"):
            self._check_person(attrs)
        if not attrs.get("vacancy") and not (attrs.get("position") or "").strip():
            raise serializers.ValidationError({"vacancy": "Выберите вакансию или укажите должность."})
        return attrs

    def split(self) -> dict:
        data = dict(self.validated_data)
        candidate = data.pop("candidate", None)
        person_data = {f: data.pop(f).strip() if isinstance(data.get(f), str) else data.pop(f)
                       for f in PERSON_FIELDS if f in data}
        app = {k: v for k, v in data.items() if k != "confirm_new"}
        app.setdefault("applied_on", timezone.localdate())
        return {"candidate": candidate, "person": person_data, "confirm_new": data.get("confirm_new", False), **app}


class ApplicationUpdateSerializer(serializers.ModelSerializer):
    responsible = PersonField(allow_null=True, required=False)

    class Meta:
        model = Application
        fields = ["position", "source", "source_details", "applied_on", "responsible", "cover_letter"]

    def validate_applied_on(self, value):
        if value > timezone.localdate():
            raise serializers.ValidationError("Дата отклика не может быть в будущем.")
        return value


class StatusChangeSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=Application.Status.choices)
    comment = serializers.CharField(required=False, allow_blank=True, max_length=1000)


class NoteSerializer(serializers.ModelSerializer):
    author_info = serializers.SerializerMethodField()
    application_number = serializers.CharField(source="application.number", read_only=True, default=None)

    class Meta:
        model = InternalNote
        fields = ["id", "candidate", "application", "application_number", "text", "author_info", "created_at"]
        read_only_fields = fields

    def get_author_info(self, obj):
        return person(obj.author)


class NoteCreateSerializer(serializers.Serializer):
    text = serializers.CharField(max_length=4000)
    application = serializers.IntegerField(required=False, allow_null=True)

    def validate_text(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Заметка не может быть пустой.")
        return value


class MergeSerializer(serializers.Serializer):
    target = serializers.PrimaryKeyRelatedField(queryset=Candidate.objects.all())


class EraseSerializer(serializers.Serializer):
    confirm = serializers.BooleanField()
    reason = serializers.CharField(required=False, allow_blank=True, max_length=255)

    def validate_confirm(self, value):
        if not value:
            raise serializers.ValidationError("Подтвердите удаление персональных данных.")
        return value


# ---------------------------------------------------------------------------
# Собеседования
# ---------------------------------------------------------------------------

class InterviewSerializer(serializers.ModelSerializer):
    candidate = serializers.IntegerField(source="application.candidate_id", read_only=True)
    candidate_info = serializers.SerializerMethodField()
    application_info = serializers.SerializerMethodField()
    vacancy_info = serializers.SerializerMethodField()
    interviewer_info = serializers.SerializerMethodField()
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    format_label = serializers.CharField(source="get_format_display", read_only=True)
    result_label = serializers.CharField(source="get_result_display", read_only=True)
    next_step_label = serializers.CharField(source="get_next_step_display", read_only=True)
    scheduled_at = serializers.SerializerMethodField()

    class Meta:
        model = Interview
        fields = ["id", "application", "application_info", "candidate", "candidate_info", "vacancy", "vacancy_info",
                  "scheduled_at", "duration_minutes", "format", "format_label", "location", "meeting_url",
                  "interviewer", "interviewer_info", "notes", "status", "status_label", "reschedule_count",
                  "rescheduled_to", "cancel_reason", "cancelled_at", "result", "result_label", "overall_rating",
                  "skills_rating", "strengths", "concerns", "result_comment", "next_step", "next_step_label",
                  "next_step_date", "completed_at", "created_at"]
        read_only_fields = fields

    def get_scheduled_at(self, obj):
        return timezone.localtime(obj.scheduled_at).isoformat()

    def get_candidate_info(self, obj):
        c = obj.application.candidate
        return {"id": c.pk, "full_name": c.full_name}

    def get_application_info(self, obj):
        a = obj.application
        return {"id": a.pk, "number": a.number, "status": a.status, "status_label": a.get_status_display()}

    def get_vacancy_info(self, obj):
        if obj.vacancy_id:
            return {"id": obj.vacancy_id, "title": obj.vacancy.title}
        position = obj.application.position
        return {"id": None, "title": position} if position else None

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
    application = serializers.PrimaryKeyRelatedField(queryset=Application.objects.all())
    interviewer = PersonField()
    confirm = serializers.BooleanField(required=False, default=False, write_only=True)

    class Meta:
        model = Interview
        fields = ["application", "scheduled_at", "duration_minutes", "format", "location", "meeting_url",
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


class NoShowSerializer(serializers.Serializer):
    comment = serializers.CharField(required=False, allow_blank=True, max_length=255)


class ResultSerializer(serializers.Serializer):
    """Оценка обязательна только для состоявшегося собеседования; отмена и
    неявка фиксируются без неё (`cancel/`, `no-show/`)."""

    result = serializers.ChoiceField(choices=Interview.Result.choices)
    next_step = serializers.ChoiceField(choices=Interview.NextStep.choices)
    overall_rating = serializers.IntegerField(min_value=1, max_value=5)
    skills_rating = serializers.IntegerField(min_value=1, max_value=5)
    strengths = serializers.CharField(required=False, allow_blank=True, max_length=4000)
    concerns = serializers.CharField(required=False, allow_blank=True, max_length=4000)
    result_comment = serializers.CharField(required=False, allow_blank=True, max_length=4000)
    next_step_date = serializers.DateField(required=False, allow_null=True)


class AccountRequestSerializer(serializers.ModelSerializer):
    role_label = serializers.SerializerMethodField()
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    requested_by_info = serializers.SerializerMethodField()
    candidate = serializers.SerializerMethodField()

    class Meta:
        model = AccountRequest
        fields = ["id", "application", "candidate", "role", "role_label", "username", "email", "first_name",
                  "last_name", "comment", "status", "status_label", "requested_by_info", "decided_at",
                  "decision_comment", "created_at"]
        read_only_fields = fields

    def get_role_label(self, obj):
        return dict(User.Role.choices).get(obj.role, obj.role)

    def get_requested_by_info(self, obj):
        return person(obj.requested_by)

    def get_candidate(self, obj):
        c = obj.application.candidate
        return {"id": c.pk, "full_name": c.full_name}


class AccountRequestCreateSerializer(serializers.Serializer):
    role = serializers.ChoiceField(choices=hiring.requestable_roles())
    username = serializers.CharField(max_length=150)
    email = serializers.EmailField()
    first_name = serializers.CharField(max_length=100)
    last_name = serializers.CharField(max_length=100, required=False, allow_blank=True)
    comment = serializers.CharField(required=False, allow_blank=True, max_length=2000)

    def validate_username(self, value):
        value = value.strip()
        if not re.match(r"^[\w.@+-]+$", value):
            raise serializers.ValidationError("Логин: буквы, цифры и символы @ . + - _")
        return value


class ActivitySerializer(serializers.ModelSerializer):
    class Meta:
        model = HRActivity
        fields = ["id"]

    def to_representation(self, instance):
        return activity_brief(instance)
