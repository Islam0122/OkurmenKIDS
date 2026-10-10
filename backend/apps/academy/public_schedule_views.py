"""Public schedule API — /api/v1/public/schedule/ (no login).

The only academy endpoints open to anonymous visitors, and only for GET:
the published schedule (services.public_schedule — a closed whitelist of
fields, no personal data, no database ids). Every internal endpoint keeps
its own authentication and permissions.

Per-IP rate limit (scope «public_schedule»), a short server cache bumped on
every lesson change, and `Cache-Control: public, max-age=…` for browsers
and CDNs.
"""
from __future__ import annotations

import datetime as dt

from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import SimpleRateThrottle
from rest_framework.views import APIView

from .services import public_schedule as service

TAGS = ["Public schedule"]


class PublicScheduleThrottle(SimpleRateThrottle):
    """Per client IP (a school / office often shares one IP — generous)."""

    scope = "public_schedule"

    def get_cache_key(self, request, view):
        return self.cache_format % {"scope": self.scope, "ident": self.get_ident(request)}


class PublicView(APIView):
    authentication_classes: list = []  # no tokens, no sessions, no CSRF — nobody is "logged in" here
    permission_classes = [AllowAny]
    throttle_classes = [PublicScheduleThrottle]
    http_method_names = ["get", "head", "options"]

    def respond(self, payload) -> Response:
        response = Response(payload)
        response["Cache-Control"] = f"public, max-age={service.config()['cache_seconds']}"
        return response


def _date(value, default: dt.date, name: str) -> dt.date:
    if not value:
        return default
    try:
        return dt.date.fromisoformat(value)
    except ValueError:
        raise ValidationError({name: "Неверный формат даты (ожидается ГГГГ-ММ-ДД)."})


def _key(value) -> str | None:
    value = (value or "").strip().lower()
    return value if value.isalnum() and len(value) <= 32 else (None if not value else "-")


@extend_schema(tags=TAGS, auth=[], responses={200: dict})
class PublicScheduleOptionsView(PublicView):
    """GET — groups, trainers (if published), rooms (if published) for the filters."""

    def get(self, request):
        return self.respond(service.cached("options", {"day": timezone.localdate()}, service.options))


@extend_schema(tags=TAGS, auth=[], responses={200: dict})
class PublicScheduleView(PublicView):
    """GET ?start=&end= (1–7 days, inside the published window; default
    today) &group= &trainer= &room= (public keys) — the published lessons."""

    def get(self, request):
        today = timezone.localdate()
        start = _date(request.query_params.get("start"), today, "start")
        end = _date(request.query_params.get("end"), start, "end")
        filters = {name: _key(request.query_params.get(name)) for name in ("group", "trainer", "room")}
        try:
            payload = service.cached(
                "lessons", {"start": start, "end": end, **filters},
                lambda: service.lessons(start, end, **filters),
            )
        except service.PublicScheduleError as exc:
            raise ValidationError({"detail": str(exc)})
        return self.respond(payload)
