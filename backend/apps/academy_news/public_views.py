"""Public academy news API — /api/v1/public/news/ (no login, GET only).

    GET /          ?q= &category=all|events|achievements|competitions|education|announcements|activities &page= &page_size=
    GET /<slug>/   one article with its photos and related news (404 for drafts, scheduled and unknown)
"""
from __future__ import annotations

from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.exceptions import NotFound
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import SimpleRateThrottle
from rest_framework.views import APIView

from . import public

TAGS = ["Public news"]


class PublicNewsThrottle(SimpleRateThrottle):
    scope = "public_news"

    def get_cache_key(self, request, view):
        return self.cache_format % {"scope": self.scope, "ident": self.get_ident(request)}


class PublicView(APIView):
    authentication_classes: list = []  # a staff token is ignored, never required
    permission_classes = [AllowAny]
    throttle_classes = [PublicNewsThrottle]
    http_method_names = ["get", "head", "options"]

    def respond(self, payload) -> Response:
        response = Response(payload)
        response["Cache-Control"] = f"public, max-age={min(public.cache_seconds(), 60)}"
        return response


@extend_schema(
    tags=TAGS, auth=[], responses={200: dict},
    parameters=[
        OpenApiParameter("q", str, description="Поиск по заголовку и тексту"),
        OpenApiParameter("category", str, enum=["all", *public.CATEGORY_IDS]),
        OpenApiParameter("page", int),
        OpenApiParameter("page_size", int),
        OpenApiParameter("lang", str, enum=list(public.LANGS)),
    ],
)
class PublicNewsListView(PublicView):
    def get(self, request):
        params = request.query_params
        return self.respond(public.listing(q=params.get("q", ""), category=params.get("category", ""),
                                           page=params.get("page"), page_size=params.get("page_size"),
                                           lang=params.get("lang", "")))


@extend_schema(tags=TAGS, auth=[], responses={200: dict})
class PublicArticleView(PublicView):
    def get(self, request, slug: str):
        record = public.article(slug, request.query_params.get("lang", ""))
        if record is None:
            raise NotFound("Новость не найдена или ещё не опубликована.")
        return self.respond(record)
