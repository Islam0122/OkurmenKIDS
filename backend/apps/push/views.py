from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from . import services
from .models import PushSubscription
from .serializers import (
    PreferenceSerializer,
    SubscribeSerializer,
    SubscriptionSerializer,
    UnsubscribeSerializer,
)

TAG = ["Push"]


class PushConfigView(APIView):
    """GET /push/config/ — whether push is configured and the VAPID public key."""

    permission_classes = [IsAuthenticated]

    @extend_schema(tags=TAG)
    def get(self, request):
        return Response({"enabled": services.is_enabled(), "public_key": services.public_key()})


class SubscriptionsView(APIView):
    """GET  /push/subscriptions/ — the caller's devices (no endpoints/keys).
    POST /push/subscriptions/ — save the browser's subscription (idempotent)."""

    permission_classes = [IsAuthenticated]

    @extend_schema(tags=TAG, responses=SubscriptionSerializer(many=True))
    def get(self, request):
        devices = PushSubscription.objects.filter(user=request.user)
        return Response(SubscriptionSerializer(devices, many=True).data)

    @extend_schema(tags=TAG, request=SubscribeSerializer, responses=SubscriptionSerializer)
    def post(self, request):
        if not services.is_enabled():
            return Response({"detail": "Push-уведомления не настроены на сервере."},
                            status=status.HTTP_503_SERVICE_UNAVAILABLE)
        serializer = SubscribeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        subscription = services.save_subscription(
            request.user, data["endpoint"], data["keys"]["p256dh"], data["keys"]["auth"],
            data.get("user_agent") or request.META.get("HTTP_USER_AGENT", ""),
        )
        return Response(SubscriptionSerializer(subscription).data, status=status.HTTP_201_CREATED)


class UnsubscribeView(APIView):
    """POST /push/subscriptions/unsubscribe/ {endpoint} — forget this device
    (only the caller's own; unknown endpoints are a no-op)."""

    permission_classes = [IsAuthenticated]

    @extend_schema(tags=TAG, request=UnsubscribeSerializer, responses={204: None})
    def post(self, request):
        serializer = UnsubscribeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        PushSubscription.objects.filter(user=request.user, endpoint=serializer.validated_data["endpoint"]).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class PreferencesView(APIView):
    """GET/PATCH /push/preferences/ — which categories reach the caller's devices."""

    permission_classes = [IsAuthenticated]

    @extend_schema(tags=TAG, responses=PreferenceSerializer)
    def get(self, request):
        return Response(PreferenceSerializer(services.preferences_for(request.user)).data)

    @extend_schema(tags=TAG, request=PreferenceSerializer, responses=PreferenceSerializer)
    def patch(self, request):
        serializer = PreferenceSerializer(services.preferences_for(request.user), data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class TestPushView(APIView):
    """POST /push/test/ — send a test notification to the caller's own devices."""

    permission_classes = [IsAuthenticated]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "push_test"

    @extend_schema(tags=TAG, request=None, responses={200: None})
    def post(self, request):
        if not services.is_enabled():
            return Response({"detail": "Push-уведомления не настроены на сервере."},
                            status=status.HTTP_503_SERVICE_UNAVAILABLE)
        delivered = services.send_to_user(
            request.user,
            services.PushMessage(title="OkurmenKids", body="Уведомления работают на этом устройстве.",
                                 url="/", tag="push-test"),
        )
        return Response({"delivered": delivered})
