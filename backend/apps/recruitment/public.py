"""Публичный карьерный сайт — /api/v1/public/careers/ (без входа).

Единственные эндпоинты подбора, открытые посетителям:

* список опубликованных вакансий с поиском, фильтрами, сортировкой и
  страницами, фильтры для формы поиска;
* страница вакансии по адресу (slug): закрытая или приостановленная вакансия,
  которая была на сайте, отвечает 410 только с названием; черновик и
  несуществующий адрес — 404;
* отклик на вакансию (multipart с резюме).

Отдаются только поля для посетителя — белый список ниже: ни id, ни
ответственных, ни числа откликов, ни внутренних статусов. Токены и сессии не
принимаются (`authentication_classes = []`), частота запросов ограничена по IP
(`careers_read`, `careers_apply`).
"""
from __future__ import annotations

from django.db.models import Case, F, Q, When
from django.db.models.functions import Coalesce
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import serializers, status
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import SimpleRateThrottle
from rest_framework.views import APIView

from .models import Application, Vacancy
from .serializers import clean_phone
from .services import files, intake
from .services.common import RecruitmentError

TAGS = ["Public careers"]
PAGE_SIZE = 12
MAX_PAGE_SIZE = 50
CACHE_SECONDS = 60

ORDERINGS = {
    "newest": ["-published_at", "-id"],
    "oldest": ["published_at", "id"],
    "salary_desc": [F("salary_sort").desc(nulls_last=True), "-published_at"],
    "salary_asc": [F("salary_sort").asc(nulls_last=True), "-published_at"],
    "title": ["title", "id"],
}

# Источники, которые посетитель может выбрать в вопросе «Откуда вы узнали о вакансии».
PUBLIC_SOURCES = [Application.Source.COMPANY_SITE, Application.Source.JOB_SITE, Application.Source.SOCIAL,
                  Application.Source.REFERRAL, Application.Source.OTHER]


class _IPThrottle(SimpleRateThrottle):
    def get_cache_key(self, request, view):
        return self.cache_format % {"scope": self.scope, "ident": self.get_ident(request)}


class CareersReadThrottle(_IPThrottle):
    scope = "careers_read"


class CareersApplyThrottle(_IPThrottle):
    scope = "careers_apply"


class PublicView(APIView):
    authentication_classes: list = []  # никто здесь не «вошёл»: ни токенов, ни сессий, ни CSRF
    permission_classes = [AllowAny]
    throttle_classes = [CareersReadThrottle]
    http_method_names = ["get", "head", "options"]

    def respond(self, payload, code=status.HTTP_200_OK) -> Response:
        response = Response(payload, status=code)
        response["Cache-Control"] = f"public, max-age={CACHE_SECONDS}"
        return response


def _lines(text: str) -> list[str]:
    return [line.strip(" •-–—\t") for line in (text or "").splitlines() if line.strip(" •-–—\t")]


def salary(vacancy: Vacancy) -> dict | None:
    if not vacancy.show_salary or (vacancy.salary_min is None and vacancy.salary_max is None):
        return None
    return {"min": vacancy.salary_min, "max": vacancy.salary_max, "currency": vacancy.salary_currency,
            "currency_label": vacancy.get_salary_currency_display()}


def vacancy_card(vacancy: Vacancy) -> dict:
    return {
        "slug": vacancy.slug,
        "title": vacancy.title,
        "department": vacancy.department,
        "location": vacancy.location,
        "work_format": vacancy.work_format,
        "work_format_label": vacancy.get_work_format_display(),
        "employment_type": vacancy.employment_type,
        "employment_type_label": vacancy.get_employment_type_display(),
        "salary": salary(vacancy),
        "summary": vacancy.summary,
        "published_at": timezone.localtime(vacancy.published_at).date().isoformat() if vacancy.published_at else None,
        "closes_on": vacancy.closes_on.isoformat() if vacancy.closes_on else None,
        "is_open": vacancy.is_accepting,
    }


def vacancy_page(vacancy: Vacancy) -> dict:
    return {
        **vacancy_card(vacancy),
        "description": vacancy.description,
        "responsibilities": _lines(vacancy.responsibilities),
        "requirements": _lines(vacancy.requirements),
        "nice_to_have": _lines(vacancy.nice_to_have),
        "conditions": _lines(vacancy.conditions),
        "selection_stages": _lines(vacancy.selection_stages),
    }


def _gone(vacancy: Vacancy) -> Response:
    message = ("Приём откликов на эту вакансию приостановлен." if vacancy.status == Vacancy.Status.PAUSED
               else "Вакансия закрыта и больше не принимает отклики.")
    response = Response({"detail": message, "code": "vacancy_closed", "title": vacancy.title},
                        status=status.HTTP_410_GONE)
    response["Cache-Control"] = f"public, max-age={CACHE_SECONDS}"
    return response


def _not_found() -> Response:
    return Response({"detail": "Вакансия не найдена.", "code": "not_found"}, status=status.HTTP_404_NOT_FOUND)


def _lookup(slug: str):
    """(вакансия, ответ-ошибка): посетитель видит только то, что было на сайте."""
    vacancy = Vacancy.objects.filter(slug=slug).first()
    if vacancy is None or vacancy.published_at is None or vacancy.status == Vacancy.Status.DRAFT:
        return None, _not_found()
    if not vacancy.is_accepting:
        return vacancy, _gone(vacancy)
    return vacancy, None


@extend_schema(tags=TAGS, auth=[], responses=OpenApiTypes.OBJECT)
class FiltersView(PublicView):
    """GET — значения фильтров по опубликованным вакансиям."""

    def get(self, request):
        qs = Vacancy.objects.public()
        formats = dict(Vacancy.WorkFormat.choices)
        types = dict(Vacancy.EmploymentType.choices)
        present_formats = set(qs.values_list("work_format", flat=True))
        present_types = set(qs.values_list("employment_type", flat=True))
        return self.respond({
            "total": qs.count(),
            "departments": sorted(set(qs.exclude(department="").values_list("department", flat=True))),
            "locations": sorted(set(qs.exclude(location="").values_list("location", flat=True))),
            "work_formats": [{"value": v, "label": formats[v]} for v in formats if v in present_formats],
            "employment_types": [{"value": v, "label": types[v]} for v in types if v in present_types],
            "sources": [{"value": s.value, "label": s.label} for s in PUBLIC_SOURCES],
            "resume_max_mb": files.max_bytes() // (1024 * 1024),
        })


@extend_schema(tags=TAGS, auth=[], responses=OpenApiTypes.OBJECT)
class VacancyListView(PublicView):
    """GET ?search&department&location&work_format&employment_type
    &ordering=newest|oldest|salary_desc|salary_asc|title&page&page_size (до 50)."""

    def get(self, request):
        p = request.query_params
        qs = Vacancy.objects.public()
        search = (p.get("search") or "").strip()[:100]
        if search:
            qs = qs.filter(Q(title__icontains=search) | Q(summary__icontains=search) | Q(department__icontains=search)
                           | Q(description__icontains=search) | Q(requirements__icontains=search))
        for key in ("department", "location"):
            if p.get(key):
                qs = qs.filter(**{key: p[key][:150]})
        if p.get("work_format") in Vacancy.WorkFormat.values:
            qs = qs.filter(work_format=p["work_format"])
        if p.get("employment_type") in Vacancy.EmploymentType.values:
            qs = qs.filter(employment_type=p["employment_type"])
        ordering = ORDERINGS.get(p.get("ordering") or "newest", ORDERINGS["newest"])
        # Зарплата для сортировки — только опубликованная: скрытая не влияет на порядок.
        qs = qs.annotate(salary_sort=Case(When(show_salary=True, then=Coalesce("salary_max", "salary_min")),
                                          default=None)).order_by(*ordering)
        try:
            page = max(int(p.get("page") or 1), 1)
            size = min(max(int(p.get("page_size") or PAGE_SIZE), 1), MAX_PAGE_SIZE)
        except ValueError:
            return Response({"detail": "Страница — целое число.", "code": "invalid_params"}, status=400)
        total = qs.count()
        items = list(qs[(page - 1) * size: page * size])
        return self.respond({"count": total, "page": page, "page_size": size,
                             "results": [vacancy_card(v) for v in items]})


@extend_schema(tags=TAGS, auth=[], responses=OpenApiTypes.OBJECT)
class VacancyDetailView(PublicView):
    def get(self, request, slug):
        vacancy, error = _lookup(slug)
        return error or self.respond(vacancy_page(vacancy))


class ApplySerializer(serializers.Serializer):
    """Только то, что нужно для первичного рассмотрения. Обязательны ФИО,
    телефон, email и согласие на обработку данных."""

    submission_token = serializers.UUIDField()
    full_name = serializers.CharField(max_length=200)
    phone = serializers.CharField(max_length=32)
    email = serializers.EmailField(max_length=254)
    city = serializers.CharField(max_length=100, required=False, allow_blank=True)
    experience = serializers.CharField(max_length=3000, required=False, allow_blank=True)
    education = serializers.CharField(max_length=2000, required=False, allow_blank=True)
    skills = serializers.CharField(max_length=2000, required=False, allow_blank=True)
    cover_letter = serializers.CharField(max_length=5000, required=False, allow_blank=True)
    portfolio_url = serializers.URLField(max_length=200, required=False, allow_blank=True)
    source = serializers.ChoiceField(choices=[(s.value, s.label) for s in PUBLIC_SOURCES], required=False,
                                     allow_blank=True)
    consent = serializers.BooleanField()
    # Ловушка для ботов: поле скрыто от людей и должно остаться пустым.
    website = serializers.CharField(required=False, allow_blank=True, max_length=200)
    resume = serializers.FileField(required=False, allow_null=True)

    def validate_full_name(self, value):
        value = " ".join(value.split())
        if len(value) < 2 or not any(ch.isalpha() for ch in value):
            raise serializers.ValidationError("Укажите фамилию и имя.")
        return value

    def validate_phone(self, value):
        value = clean_phone(value)
        if not value:
            raise serializers.ValidationError("Укажите телефон.")
        return value

    def validate_portfolio_url(self, value):
        if value and not value.lower().startswith(("http://", "https://")):
            raise serializers.ValidationError("Ссылка должна начинаться с http:// или https://.")
        return value

    def validate_consent(self, value):
        if not value:
            raise serializers.ValidationError("Нужно согласие на обработку персональных данных.")
        return value

    def validate_resume(self, value):
        if value is not None:
            try:
                files.validate_resume(value)
            except RecruitmentError as exc:
                raise serializers.ValidationError(exc.message) from exc
        return value

    def validate(self, attrs):
        if attrs.get("website"):
            raise serializers.ValidationError({"detail": "Не удалось отправить заявку. Попробуйте ещё раз."})
        return attrs


@extend_schema(tags=TAGS, auth=[], request=ApplySerializer, responses=OpenApiTypes.OBJECT)
class ApplyView(APIView):
    """POST (multipart или JSON) — отклик на вакансию. 201 — заявка создана;
    200 — эта же форма уже была отправлена (тот же submission_token)."""

    authentication_classes: list = []
    permission_classes = [AllowAny]
    throttle_classes = [CareersApplyThrottle]
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    http_method_names = ["post", "options"]

    def post(self, request, slug):
        vacancy, error = _lookup(slug)
        if error:
            return error
        serializer = ApplySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        resume = data.pop("resume", None)
        data.pop("website", None)
        data.pop("consent")
        try:
            application, created = intake.submit_public(vacancy, data, resume)
        except RecruitmentError as exc:
            return Response({"detail": exc.message, "code": exc.code}, status=exc.status)
        return Response(
            {"number": application.number, "vacancy": {"title": vacancy.title, "slug": vacancy.slug},
             "message": "Заявка отправлена. HR рассмотрит её и свяжется с вами по указанным контактам."},
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )
