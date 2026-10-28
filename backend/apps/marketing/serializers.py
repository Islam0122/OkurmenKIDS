from __future__ import annotations

from django.utils import timezone
from rest_framework import serializers

from apps.users.models import User
from apps.users.permissions import is_admin_user

from .models import Channel, ContentFormat, ContentItem, MarketingTask


def person(user) -> dict | None:
    """Только имя — никаких контактов и персональных данных."""
    if user is None:
        return None
    return {"id": user.pk, "full_name": user.get_full_name() or user.username}


def choices(enum) -> list[dict]:
    return [{"value": value, "label": label} for value, label in enum.choices]


def team_queryset():
    """Кого можно назначить ответственным: активные сотрудники маркетинга."""
    return User.objects.filter(is_active=True, role=User.Role.MARKETING).order_by("first_name", "last_name", "id")


class TeamMemberField(serializers.PrimaryKeyRelatedField):
    default_error_messages = {
        "does_not_exist": "Ответственным можно назначить только активного сотрудника маркетинга.",
    }

    def get_queryset(self):
        return team_queryset()


def can_delete(request, obj) -> bool:
    """Удалить запись может её автор или администратор."""
    user = getattr(request, "user", None)
    return bool(user and (is_admin_user(user) or (obj.created_by_id is not None and obj.created_by_id == user.pk)))


class ContentItemSerializer(serializers.ModelSerializer):
    responsible = TeamMemberField(allow_null=True, required=False)
    responsible_info = serializers.SerializerMethodField()
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    channel_label = serializers.CharField(source="get_channel_display", read_only=True)
    format_label = serializers.CharField(source="get_format_display", read_only=True)
    created_by_info = serializers.SerializerMethodField()
    can_delete = serializers.SerializerMethodField()

    class Meta:
        model = ContentItem
        fields = ["id", "title", "channel", "channel_label", "format", "format_label", "publish_date", "publish_time",
                  "status", "status_label", "responsible", "responsible_info", "description", "post_url",
                  "published_at", "created_by_info", "created_at", "updated_at", "can_delete"]
        read_only_fields = ["published_at", "created_at", "updated_at"]

    def get_responsible_info(self, obj):
        return person(obj.responsible)

    def get_created_by_info(self, obj):
        return person(obj.created_by)

    def get_can_delete(self, obj):
        return can_delete(self.context.get("request"), obj)

    def validate_title(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Укажите тему публикации.")
        return value

    def validate(self, attrs):
        status = attrs.get("status", getattr(self.instance, "status", ContentItem.Status.IDEA))
        publish_date = attrs["publish_date"] if "publish_date" in attrs else getattr(self.instance, "publish_date", None)
        publish_time = attrs["publish_time"] if "publish_time" in attrs else getattr(self.instance, "publish_time", None)
        if status in ContentItem.DATED_STATUSES and publish_date is None:
            raise serializers.ValidationError({"publish_date": "Для статуса «Запланировано» и «Опубликовано» "
                                                               "нужна дата публикации."})
        if publish_time is not None and publish_date is None:
            raise serializers.ValidationError({"publish_time": "Время публикации указывается вместе с датой."})
        # Момент публикации ставит сервер: при переходе в «Опубликовано» —
        # сейчас; при возврате в работу — сбрасывается.
        if status == ContentItem.Status.PUBLISHED:
            if getattr(self.instance, "published_at", None) is None:
                attrs["published_at"] = timezone.now()
        else:
            attrs["published_at"] = None
        return attrs

    def create(self, validated_data):
        validated_data["created_by"] = self.context["request"].user
        return super().create(validated_data)


class MarketingTaskSerializer(serializers.ModelSerializer):
    responsible = TeamMemberField(allow_null=True, required=False)
    responsible_info = serializers.SerializerMethodField()
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    priority_label = serializers.CharField(source="get_priority_display", read_only=True)
    is_overdue = serializers.SerializerMethodField()
    created_by_info = serializers.SerializerMethodField()
    can_delete = serializers.SerializerMethodField()

    class Meta:
        model = MarketingTask
        fields = ["id", "title", "description", "due_date", "priority", "priority_label", "status", "status_label",
                  "is_overdue", "responsible", "responsible_info", "completed_at", "created_by_info", "created_at",
                  "updated_at", "can_delete"]
        read_only_fields = ["completed_at", "created_at", "updated_at"]

    def get_responsible_info(self, obj):
        return person(obj.responsible)

    def get_created_by_info(self, obj):
        return person(obj.created_by)

    def get_is_overdue(self, obj):
        return obj.is_overdue(timezone.localdate())

    def get_can_delete(self, obj):
        return can_delete(self.context.get("request"), obj)

    def validate_title(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Укажите название задачи.")
        return value

    def validate(self, attrs):
        status = attrs.get("status", getattr(self.instance, "status", MarketingTask.Status.TODO))
        if status == MarketingTask.Status.DONE:
            if getattr(self.instance, "completed_at", None) is None:
                attrs["completed_at"] = timezone.now()
        else:
            attrs["completed_at"] = None
        return attrs

    def create(self, validated_data):
        validated_data["created_by"] = self.context["request"].user
        return super().create(validated_data)


def meta_payload(user) -> dict:
    return {
        "channels": choices(Channel),
        "formats": choices(ContentFormat),
        "content_statuses": choices(ContentItem.Status),
        "task_statuses": choices(MarketingTask.Status),
        "priorities": choices(MarketingTask.Priority),
        "team": [person(member) for member in team_queryset()],
        "me": user.pk,
        "today": timezone.localdate().isoformat(),
    }
