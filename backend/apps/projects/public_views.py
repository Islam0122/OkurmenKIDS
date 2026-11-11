"""Public student projects API — /api/v1/public/projects/ (no login).

GET only, no authentication (a staff token is ignored, never required), a
closed whitelist of fields (see public.py), a per-IP rate limit (scope
«public_projects») and `Cache-Control: public`.

    GET /                ?q= &category=all|html-css|javascript|react|python|other &page= &page_size=
    GET /<key>/          one published project (404 for drafts and unknown keys)
"""
from __future__ import annotations

from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.exceptions import NotFound
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import SimpleRateThrottle
from rest_framework.views import APIView

from . import public

TAGS = ["Public projects"]


class PublicProjectsThrottle(SimpleRateThrottle):
    """Per client IP (a school often shares one IP — generous)."""

    scope = "public_projects"

    def get_cache_key(self, request, view):
        return self.cache_format % {"scope": self.scope, "ident": self.get_ident(request)}


class PublicView(APIView):
    authentication_classes: list = []
    permission_classes = [AllowAny]
    throttle_classes = [PublicProjectsThrottle]
    http_method_names = ["get", "head", "options"]

    def respond(self, payload) -> Response:
        response = Response(payload)
        response["Cache-Control"] = f"public, max-age={min(public.config()['cache_seconds'], 60)}"
        return response


@extend_schema(
    tags=TAGS, auth=[], responses={200: dict},
    parameters=[
        OpenApiParameter("q", str, description="Поиск: название, описание, технология, группа, студент"),
        OpenApiParameter("category", str, enum=["all", *public.CATEGORY_IDS]),
        OpenApiParameter("technology", str, description="Точное название технологии (без учёта регистра)"),
        OpenApiParameter("page", int),
        OpenApiParameter("page_size", int),
    ],
)
class PublicProjectListView(PublicView):
    def get(self, request):
        params = request.query_params
        return self.respond(public.gallery(
            q=params.get("q", ""), category=params.get("category", ""), technology=params.get("technology", ""),
            page=params.get("page"), page_size=params.get("page_size"),
        ))


@extend_schema(tags=TAGS, auth=[], responses={200: dict})
class PublicProjectDetailView(PublicView):
    def get(self, request, key: str):
        record = public.detail(key)
        if record is None:
            raise NotFound("Проект не найден или не опубликован.")
        return self.respond(record)
