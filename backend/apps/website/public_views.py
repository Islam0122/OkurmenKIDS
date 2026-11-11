"""Public website API — /api/v1/public/site/ (no login).

    GET  settings/                 hero, contacts, branches, stats, homepage blocks, banners
    GET  home/                     everything the homepage shows, in one request
    GET  courses/  courses/<slug>/
    GET  events/?phase=&category=&page=   events/<slug>/
    POST events/<slug>/register/   registration (only when it is open)
    GET  achievements/?category=&page=    achievements/<slug>/
    GET  team/
    GET  testimonials/?kind=text|photo|video&page=
    POST leads/                    «Записать ребёнка»
    GET  sitemap/                  slugs and dates for sitemap.xml
    GET  preview/<token>/          a draft opened from the LMS editor (signed link)

Every GET takes `?lang=ru|ky|en` (default ru; an empty translation falls back
to Russian). Writes are throttled per IP (`public_site_submit`).
"""
from __future__ import annotations

import datetime as dt
import logging

from django.db import transaction
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers, status
from rest_framework.exceptions import NotFound
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import SimpleRateThrottle
from rest_framework.views import APIView

from . import public
from .markup import phone_digits
from .models import Branch, CoursePage, Event, EventRegistration, Lead, Workflow

logger = logging.getLogger(__name__)
TAGS = ["Public website"]
LANG = OpenApiParameter("lang", str, enum=list(public.LANGS))
DUPLICATE_WINDOW = dt.timedelta(hours=24)


class PublicSiteThrottle(SimpleRateThrottle):
    scope = "public_site"

    def get_cache_key(self, request, view):
        return self.cache_format % {"scope": self.scope, "ident": self.get_ident(request)}


class PublicSiteSubmitThrottle(PublicSiteThrottle):
    scope = "public_site_submit"


class PublicView(APIView):
    authentication_classes: list = []  # a staff token is ignored, never required
    permission_classes = [AllowAny]
    throttle_classes = [PublicSiteThrottle]
    http_method_names = ["get", "head", "options"]

    @property
    def lang(self) -> str:
        return public.lang_of(self.request.query_params.get("lang") or self.request.headers.get("Accept-Language"))

    def respond(self, payload, max_age: int | None = None) -> Response:
        response = Response(payload)
        age = min(public.cache_seconds(), 60) if max_age is None else max_age
        response["Cache-Control"] = f"public, max-age={age}"
        response["Vary"] = "Accept-Language"
        return response


@extend_schema(tags=TAGS, auth=[], parameters=[LANG], responses={200: dict})
class SettingsView(PublicView):
    def get(self, request):
        return self.respond(public.site(self.lang))


@extend_schema(tags=TAGS, auth=[], parameters=[LANG], responses={200: dict})
class HomeView(PublicView):
    def get(self, request):
        return self.respond(public.home(self.lang))


@extend_schema(tags=TAGS, auth=[], parameters=[LANG], responses={200: dict})
class CoursesView(PublicView):
    def get(self, request):
        return self.respond(public.courses(self.lang))


@extend_schema(tags=TAGS, auth=[], parameters=[LANG], responses={200: dict})
class CourseView(PublicView):
    def get(self, request, slug: str):
        record = public.course(slug.lower(), self.lang)
        if record is None:
            raise NotFound("Курс не найден.")
        return self.respond(record)


@extend_schema(tags=TAGS, auth=[], responses={200: dict}, parameters=[
    LANG, OpenApiParameter("phase", str, enum=["all", *public.EVENT_PHASES]),
    OpenApiParameter("category", str), OpenApiParameter("page", int), OpenApiParameter("page_size", int),
])
class EventsView(PublicView):
    def get(self, request):
        p = request.query_params
        return self.respond(public.events(self.lang, phase=p.get("phase", ""), category=p.get("category", ""),
                                          page=p.get("page"), page_size=p.get("page_size")))


@extend_schema(tags=TAGS, auth=[], parameters=[LANG], responses={200: dict})
class EventView(PublicView):
    def get(self, request, slug: str):
        record = public.event(slug.lower(), self.lang)
        if record is None:
            raise NotFound("Мероприятие не найдено.")
        return self.respond(record, max_age=30)


@extend_schema(tags=TAGS, auth=[], responses={200: dict}, parameters=[
    LANG, OpenApiParameter("category", str), OpenApiParameter("page", int), OpenApiParameter("page_size", int),
])
class AchievementsView(PublicView):
    def get(self, request):
        p = request.query_params
        return self.respond(public.achievements(self.lang, category=p.get("category", ""), page=p.get("page"),
                                                page_size=p.get("page_size")))


@extend_schema(tags=TAGS, auth=[], parameters=[LANG], responses={200: dict})
class AchievementView(PublicView):
    def get(self, request, slug: str):
        record = public.achievement(slug.lower(), self.lang)
        if record is None:
            raise NotFound("Достижение не найдено.")
        return self.respond(record)


@extend_schema(tags=TAGS, auth=[], parameters=[LANG], responses={200: dict})
class TeamView(PublicView):
    def get(self, request):
        return self.respond(public.team(self.lang))


@extend_schema(tags=TAGS, auth=[], responses={200: dict}, parameters=[
    OpenApiParameter("kind", str, enum=["all", "text", "photo", "video"]), OpenApiParameter("page", int),
])
class TestimonialsView(PublicView):
    def get(self, request):
        p = request.query_params
        return self.respond(public.testimonials(kind=p.get("kind", ""), page=p.get("page"),
                                                page_size=p.get("page_size")))


@extend_schema(tags=TAGS, auth=[], responses={200: dict})
class SitemapView(PublicView):
    def get(self, request):
        return self.respond(public.sitemap(), max_age=300)


@extend_schema(tags=TAGS, auth=[], parameters=[LANG], responses={200: dict})
class PreviewView(PublicView):
    def get(self, request, token: str):
        record = public.preview(token, self.lang)
        if record is None:
            raise NotFound("Ссылка предпросмотра недействительна или устарела.")
        response = Response(record)
        response["Cache-Control"] = "no-store"
        response["X-Robots-Tag"] = "noindex"
        return response


# ---------------------------------------------------------------------------
# Forms
# ---------------------------------------------------------------------------

class PhoneField(serializers.CharField):
    def to_internal_value(self, data):
        value = super().to_internal_value(data)
        if not 9 <= len(phone_digits(value)) <= 15:
            raise serializers.ValidationError("Проверьте номер телефона.")
        return value


class LeadSerializer(serializers.Serializer):
    parent_name = serializers.CharField(max_length=120, min_length=2)
    phone = PhoneField(max_length=40)
    child_age = serializers.IntegerField(min_value=3, max_value=25)
    course = serializers.SlugField(required=False, allow_blank=True, max_length=220)
    branch = serializers.IntegerField(required=False, allow_null=True)
    contact_method = serializers.ChoiceField(choices=Lead.ContactMethod.choices, default=Lead.ContactMethod.PHONE)
    message = serializers.CharField(required=False, allow_blank=True, max_length=2000)
    language = serializers.CharField(required=False, allow_blank=True, max_length=2)
    source = serializers.CharField(required=False, allow_blank=True, max_length=200)
    utm_source = serializers.CharField(required=False, allow_blank=True, max_length=100)
    utm_medium = serializers.CharField(required=False, allow_blank=True, max_length=100)
    utm_campaign = serializers.CharField(required=False, allow_blank=True, max_length=100)
    # Honeypot: real visitors never see or fill it.
    website = serializers.CharField(required=False, allow_blank=True, max_length=200)

    def validate_course(self, value):
        if not value:
            return None
        page = CoursePage.objects.public().filter(slug=value.lower()).first()
        if page is None:
            raise serializers.ValidationError("Курс не найден.")
        return page

    def validate_branch(self, value):
        if value in (None, ""):
            return None
        branch = Branch.objects.filter(pk=value, is_active=True).first()
        if branch is None:
            raise serializers.ValidationError("Филиал не найден.")
        return branch


class SubmitView(APIView):
    authentication_classes: list = []
    permission_classes = [AllowAny]
    throttle_classes = [PublicSiteSubmitThrottle]
    http_method_names = ["post", "options"]


@extend_schema(tags=TAGS, auth=[], request=LeadSerializer, responses={201: dict, 200: dict, 400: dict})
class LeadView(SubmitView):
    """A repeated request from the same phone within 24 hours does not create
    a second lead: the existing one is updated (`duplicate: true`)."""

    def post(self, request):
        serializer = LeadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        if data.pop("website", ""):
            return Response({"ok": True, "duplicate": False}, status=status.HTTP_201_CREATED)
        digits = phone_digits(data["phone"])
        data["language"] = public.lang_of(data.get("language"))
        with transaction.atomic():
            existing = (Lead.objects.select_for_update()
                        .filter(phone_digits=digits, created_at__gte=timezone.now() - DUPLICATE_WINDOW).first())
            if existing is not None:
                existing.repeat_count += 1
                if data.get("message") and data["message"] not in existing.message:
                    existing.message = f"{existing.message}\n\n{data['message']}".strip()
                for field in ("course", "branch"):
                    if data.get(field) and getattr(existing, f"{field}_id") is None:
                        setattr(existing, field, data[field])
                existing.save()
                return Response({"ok": True, "duplicate": True}, status=status.HTTP_200_OK)
            Lead.objects.create(phone_digits=digits, **data)
        logger.info("website lead received")
        return Response({"ok": True, "duplicate": False}, status=status.HTTP_201_CREATED)


class RegistrationSerializer(serializers.Serializer):
    parent_name = serializers.CharField(max_length=120, min_length=2)
    phone = PhoneField(max_length=40)
    child_name = serializers.CharField(required=False, allow_blank=True, max_length=120)
    child_age = serializers.IntegerField(required=False, allow_null=True, min_value=3, max_value=25)
    comment = serializers.CharField(required=False, allow_blank=True, max_length=1000)
    website = serializers.CharField(required=False, allow_blank=True, max_length=200)


@extend_schema(tags=TAGS, auth=[], request=RegistrationSerializer, responses={201: dict, 200: dict, 400: dict, 409: dict})
class EventRegisterView(SubmitView):
    def post(self, request, slug: str):
        serializer = RegistrationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        if data.pop("website", ""):
            return Response({"ok": True, "duplicate": False}, status=status.HTTP_201_CREATED)
        with transaction.atomic():
            event = (Event.objects.public().select_for_update().filter(slug=slug.lower(), status=Workflow.PUBLISHED)
                     .first())
            if event is None:
                raise NotFound("Мероприятие не найдено.")
            digits = phone_digits(data["phone"])
            if event.registrations.filter(phone_digits=digits).exclude(
                    status=EventRegistration.Status.CANCELLED).exists():
                return Response({"ok": True, "duplicate": True}, status=status.HTTP_200_OK)
            if not event.registration_open():
                return Response({"detail": "Регистрация на это мероприятие закрыта.", "code": "registration_closed"},
                                status=status.HTTP_409_CONFLICT)
            EventRegistration.objects.create(event=event, phone_digits=digits, **data)
        return Response({"ok": True, "duplicate": False}, status=status.HTTP_201_CREATED)
