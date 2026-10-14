"""Public leaderboard API — /api/v1/public/leaderboard/ (no login).

GET only, no authentication, a closed whitelist of fields (see services).
Per-IP rate limit (scope «public_leaderboard»), a short server cache bumped
on every change of an XP source, and `Cache-Control: public, max-age=…`.

    GET meta/                               periods, years, groups, courses, XP rules
    GET students/?period=year&year=2026     top students
    GET students/?period=month&year=2026&month=10
    GET students/?period=week&week_start=2026-10-12
        &q= &group= &course= (public keys) &order=desc|asc &page= &page_size=
    GET groups/?period=…  &q= &course= &order= &page= &page_size=
"""
from __future__ import annotations

from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import SimpleRateThrottle
from rest_framework.views import APIView

from . import services

TAGS = ["Public leaderboard"]
PERIOD_PARAMS = [
    OpenApiParameter("period", str, enum=list(services.PERIODS), description="year | month | week (по умолчанию month)"),
    OpenApiParameter("year", int),
    OpenApiParameter("month", int),
    OpenApiParameter("week_start", str, description="Понедельник недели, ГГГГ-ММ-ДД"),
    OpenApiParameter("q", str, description="Поиск по имени / названию"),
    OpenApiParameter("course", str, description="Публичный ключ направления"),
    OpenApiParameter("order", str, enum=["desc", "asc"]),
    OpenApiParameter("page", int),
    OpenApiParameter("page_size", int),
]


class PublicLeaderboardThrottle(SimpleRateThrottle):
    """Per client IP (a school often shares one IP — generous)."""

    scope = "public_leaderboard"

    def get_cache_key(self, request, view):
        return self.cache_format % {"scope": self.scope, "ident": self.get_ident(request)}


class PublicView(APIView):
    authentication_classes: list = []  # nobody is "logged in" here — tokens are ignored, never required
    permission_classes = [AllowAny]
    throttle_classes = [PublicLeaderboardThrottle]
    http_method_names = ["get", "head", "options"]

    def respond(self, payload) -> Response:
        response = Response(payload)
        response["Cache-Control"] = f"public, max-age={min(services.config()['cache_seconds'], 60)}"
        return response

    def period(self):
        params = self.request.query_params
        return services.resolve_period(
            params.get("period"), params.get("year"), params.get("month"), params.get("week_start"),
        )


def _key(value) -> str | None:
    """A public key filter: unknown / malformed keys match nothing."""
    value = (value or "").strip().lower()
    if not value:
        return None
    return value if value.isalnum() and len(value) <= 32 else "-"


@extend_schema(tags=TAGS, auth=[], responses={200: dict})
class LeaderboardMetaView(PublicView):
    def get(self, request):
        return self.respond(services.cached("meta", {"day": timezone.localdate()}, services.meta))


@extend_schema(tags=TAGS, auth=[], responses={200: dict},
               parameters=[*PERIOD_PARAMS, OpenApiParameter("group", str, description="Публичный ключ группы")])
class StudentLeaderboardView(PublicView):
    def get(self, request):
        params = request.query_params
        try:
            payload = services.student_board(
                self.period(), q=params.get("q", ""), group=_key(params.get("group")), course=_key(params.get("course")),
                order=params.get("order"), page=params.get("page"), page_size=params.get("page_size"),
            )
        except services.LeaderboardError as exc:
            raise ValidationError({"detail": str(exc)})
        return self.respond(payload)


@extend_schema(tags=TAGS, auth=[], responses={200: dict}, parameters=PERIOD_PARAMS)
class GroupLeaderboardView(PublicView):
    def get(self, request):
        params = request.query_params
        try:
            payload = services.group_board(
                self.period(), q=params.get("q", ""), course=_key(params.get("course")),
                order=params.get("order"), page=params.get("page"), page_size=params.get("page_size"),
            )
        except services.LeaderboardError as exc:
            raise ValidationError({"detail": str(exc)})
        return self.respond(payload)
