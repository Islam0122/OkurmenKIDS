from rest_framework import serializers

from .models import PushPreference, PushSubscription
from .services import endpoint_allowed


class SubscriptionKeysSerializer(serializers.Serializer):
    p256dh = serializers.CharField(max_length=255)
    auth = serializers.CharField(max_length=64)


class SubscribeSerializer(serializers.Serializer):
    """The browser's `PushSubscription.toJSON()` plus an optional device label."""

    endpoint = serializers.URLField(max_length=1024)
    keys = SubscriptionKeysSerializer()
    user_agent = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")

    def validate_endpoint(self, value):
        if not endpoint_allowed(value):
            raise serializers.ValidationError("Неизвестный push-сервис.")
        return value


class UnsubscribeSerializer(serializers.Serializer):
    endpoint = serializers.URLField(max_length=1024)


class SubscriptionSerializer(serializers.ModelSerializer):
    """A device as the owner sees it — never the endpoint or the keys."""

    class Meta:
        model = PushSubscription
        fields = ("id", "user_agent", "created_at", "last_success_at")


class PreferenceSerializer(serializers.ModelSerializer):
    class Meta:
        model = PushPreference
        fields = ("tasks", "reports", "alerts")
