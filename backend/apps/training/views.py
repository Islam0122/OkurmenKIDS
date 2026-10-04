"""Public training API — no login. Mounted under /api/v1/training/.

    GET   portal/                                    hero texts, exam link
    GET   tests/                                     public training tests
    GET   tests/<id>/                                one test
    POST  attempts/                                  {test_id, student_name} → attempt + token
    GET   attempts/<id>/                             questions, saved answers   (X-Attempt-Token)
    PUT   attempts/<id>/answers/<question_id>/       save an answer             (X-Attempt-Token)
    POST  attempts/<id>/answers/<question_id>/check/ lock + feedback            (X-Attempt-Token)
    POST  attempts/<id>/submit/                      finish → result            (X-Attempt-Token)
    GET   attempts/<id>/result/                      result (by the random attempt id)
    GET   leaderboard/?test=<id>                     best result per name
    GET   videos/  ·  links/                         published content

Only published content is returned, every write needs the attempt's
signed token, input is validated, and each client IP is rate-limited.
"""
from __future__ import annotations

from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import PortalSettings, TrainingLink, TrainingVideo
from .serializers import (
    AnswerSerializer,
    PortalSettingsSerializer,
    StartAttemptSerializer,
    TrainingLinkSerializer,
    TrainingTestSerializer,
    TrainingVideoSerializer,
)
from . import services
from .throttles import TrainingReadThrottle, TrainingStartThrottle, TrainingWriteThrottle

TOKEN_HEADER = "HTTP_X_ATTEMPT_TOKEN"


def error_response(error: services.TrainingError) -> Response:
    return Response({"detail": error.message, "code": error.code}, status=error.status)


class PublicView(APIView):
    permission_classes = [AllowAny]
    authentication_classes: list = []
    throttle_classes = [TrainingReadThrottle]

    def handle_exception(self, exc):
        if isinstance(exc, services.TrainingError):
            return error_response(exc)
        return super().handle_exception(exc)

    def owned_attempt(self, request, attempt_id):
        return services.get_owned_attempt(attempt_id, request.META.get(TOKEN_HEADER))


@extend_schema(tags=["Training portal"])
class PortalView(PublicView):
    def get(self, request):
        return Response(PortalSettingsSerializer(PortalSettings.load()).data)


@extend_schema(tags=["Training portal"])
class TestListView(PublicView):
    def get(self, request):
        return Response(TrainingTestSerializer(services.public_sessions(), many=True).data)


@extend_schema(tags=["Training portal"])
class TestDetailView(PublicView):
    def get(self, request, test_id):
        return Response(TrainingTestSerializer(services.get_public_session(test_id)).data)


@extend_schema(tags=["Training portal"], request=StartAttemptSerializer)
class AttemptStartView(PublicView):
    throttle_classes = [TrainingStartThrottle]

    def post(self, request):
        body = StartAttemptSerializer(data=request.data)
        if not body.is_valid():
            return Response({"detail": "Маалымат туура эмес.", "errors": body.errors}, status=status.HTTP_400_BAD_REQUEST)
        session = services.get_public_session(body.validated_data["test_id"])
        attempt = services.start_attempt(session, body.validated_data["student_name"])
        return Response(
            {**services.attempt_summary(attempt), "token": services.attempt_token(attempt)},
            status=status.HTTP_201_CREATED,
        )


@extend_schema(tags=["Training portal"])
class AttemptView(PublicView):
    def get(self, request, attempt_id):
        return Response(services.attempt_state(self.owned_attempt(request, attempt_id)))


@extend_schema(tags=["Training portal"], request=AnswerSerializer)
class AnswerView(PublicView):
    throttle_classes = [TrainingWriteThrottle]

    def put(self, request, attempt_id, question_id):
        body = AnswerSerializer(data=request.data)
        if not body.is_valid():
            return Response({"detail": "Жооптун форматы туура эмес.", "errors": body.errors}, status=status.HTTP_400_BAD_REQUEST)
        attempt = services.save_answer(self.owned_attempt(request, attempt_id), str(question_id), body.validated_data)
        return Response({"saved": True, "remaining_seconds": services.remaining_seconds(attempt)})


@extend_schema(tags=["Training portal"])
class AnswerCheckView(PublicView):
    throttle_classes = [TrainingWriteThrottle]

    def post(self, request, attempt_id, question_id):
        return Response(services.check_question(self.owned_attempt(request, attempt_id), str(question_id)))


@extend_schema(tags=["Training portal"])
class AttemptSubmitView(PublicView):
    throttle_classes = [TrainingWriteThrottle]

    def post(self, request, attempt_id):
        attempt = services.finish_attempt(self.owned_attempt(request, attempt_id))
        return Response(services.result_payload(attempt))


@extend_schema(tags=["Training portal"])
class AttemptResultView(PublicView):
    def get(self, request, attempt_id):
        attempt = services.ensure_current(services.get_attempt(attempt_id))
        return Response(services.result_payload(attempt))


@extend_schema(tags=["Training portal"])
class LeaderboardView(PublicView):
    def get(self, request):
        test_id = request.query_params.get("test")
        session = services.get_public_session(test_id) if test_id else None
        try:
            limit = max(1, min(int(request.query_params.get("limit", 50)), services.LEADERBOARD_MAX))
        except ValueError:
            limit = 50
        return Response(services.leaderboard(session, limit))


@extend_schema(tags=["Training portal"])
class VideoListView(PublicView):
    def get(self, request):
        return Response(TrainingVideoSerializer(TrainingVideo.objects.published(), many=True).data)


@extend_schema(tags=["Training portal"])
class LinkListView(PublicView):
    def get(self, request):
        return Response(TrainingLinkSerializer(TrainingLink.objects.published(), many=True).data)
