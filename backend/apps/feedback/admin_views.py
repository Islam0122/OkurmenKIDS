"""Admin pages for feedback surveys (all ADMIN-role only).

Survey workspace: Конструктор (builder) · Ответы · Аналитика, plus the
settings change form, a WYSIWYG preview and the overview analytics page.
The builder page is a thin shell — its question editor is
static/feedback/js/builder.js talking to the admin JSON API
(apps.feedback.views), so there is exactly one write path for questions.
"""
from __future__ import annotations

from urllib.parse import quote

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.paginator import Paginator
from django.db.models import Count, Prefetch
from django.http import HttpResponse, HttpResponseNotAllowed
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme

from apps.academy.models import Group
from apps.users.models import Subject, Teacher, User

from .models import Survey, SurveyAnswer, SurveyResponse
from .public import public_url
from .public_views import render_survey_form
from .services import builder
from .services.analytics import FeedbackFilters, overview, question_stats
from .services.export import export_responses_csv


def is_admin_user(user) -> bool:
    return bool(
        user
        and user.is_authenticated
        and (user.is_superuser or getattr(user, "role", None) == User.Role.ADMIN)
    )


def _require_admin(request) -> None:
    if not is_admin_user(request.user):
        raise PermissionDenied("Опросы доступны только администратору.")


AVAILABILITY_CSS = {
    Survey.Availability.AVAILABLE: "ok-badge-success",
    Survey.Availability.DRAFT: "ok-badge-muted",
    Survey.Availability.CLOSED: "ok-badge-danger",
    Survey.Availability.NOT_STARTED: "ok-badge-warning",
    Survey.Availability.ENDED: "ok-badge-warning",
    Survey.Availability.FULL: "ok-badge-warning",
}


def _workspace_context(request, survey: Survey, active_tab: str) -> dict:
    response_count = survey.responses.count()
    availability = survey.availability(response_count=response_count)
    link = public_url(request, survey)
    share_text = f"{survey.title}\n{link}"
    return {
        **_admin_context(request),
        "survey": survey,
        "active_tab": active_tab,
        "title": survey.title,
        "response_count": response_count,
        "availability": availability,
        "availability_label": Survey.Availability(availability).label,
        "availability_css": AVAILABILITY_CSS[availability],
        "public_url": link,
        "whatsapp_url": "https://wa.me/?text=" + quote(share_text),
        "telegram_url": f"https://t.me/share/url?url={quote(link)}&text={quote(survey.title)}",
        "tabs": [
            {"key": "builder", "label": "Конструктор", "icon": "bi-ui-checks",
             "url": reverse("admin:feedback_survey_builder", args=[survey.pk])},
            {"key": "responses", "label": f"Ответы ({response_count})", "icon": "bi-chat-left-text",
             "url": reverse("admin:feedback_survey_responses", args=[survey.pk])},
            {"key": "analytics", "label": "Аналитика", "icon": "bi-bar-chart-line",
             "url": reverse("admin:feedback_survey_analytics", args=[survey.pk])},
        ],
    }


def _admin_context(request) -> dict:
    from django.contrib import admin

    return {**admin.site.each_context(request), "opts": Survey._meta}


def _get_survey(survey_id: int) -> Survey:
    return get_object_or_404(Survey.objects.select_related("group", "teacher__user", "subject"), pk=survey_id)


# -- Builder / preview --------------------------------------------------------


def builder_view(request, survey_id):
    _require_admin(request)
    survey = _get_survey(survey_id)
    context = _workspace_context(request, survey, "builder")
    context.update(
        {
            "api_base": "/api/v1/feedback/",
            "publish_problems": builder.publish_problems(survey) if survey.status == Survey.Status.DRAFT else [],
        }
    )
    return render(request, "admin/feedback/survey/builder.html", context)


def preview_view(request, survey_id):
    _require_admin(request)
    survey = _get_survey(survey_id)
    return render_survey_form(request, survey, preview=True)


_ACTIONS = {
    "publish": (builder.publish_survey, "Опрос опубликован — ссылка принимает ответы."),
    "close": (builder.close_survey, "Опрос закрыт."),
    "reopen": (builder.reopen_survey, "Опрос снова принимает ответы."),
    "regenerate": (builder.regenerate_link, "Создана новая ссылка. Старая ссылка больше не работает."),
}


def lifecycle_action_view(request, survey_id, action):
    _require_admin(request)
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    survey = _get_survey(survey_id)
    if action == "duplicate":
        copy = builder.duplicate_survey(survey, request.user)
        messages.success(request, "Создана копия опроса (черновик).")
        return redirect("admin:feedback_survey_builder", copy.pk)
    if action not in _ACTIONS:
        raise PermissionDenied("Неизвестное действие.")
    fn, success = _ACTIONS[action]
    try:
        fn(survey, request.user)
    except DjangoValidationError as exc:
        for message in exc.messages:
            messages.error(request, message)
    else:
        messages.success(request, success)
    return redirect("admin:feedback_survey_builder", survey.pk)


# -- Responses ----------------------------------------------------------------


def _survey_filters(request, survey: Survey) -> FeedbackFilters:
    filters = FeedbackFilters.from_query(request.GET)
    filters.survey_id = survey.pk
    return filters


def responses_view(request, survey_id):
    _require_admin(request)
    survey = _get_survey(survey_id)
    filters = _survey_filters(request, survey)
    search = (request.GET.get("search") or "").strip()

    qs = filters.responses(Survey.objects.filter(pk=survey.pk)).prefetch_related(
        Prefetch("answers", queryset=SurveyAnswer.objects.select_related("question").order_by("question__order", "question_id")),
        "answers__option_links__option",
    )
    if search:
        qs = qs.filter(answers__text_value__icontains=search).distinct()
    page = Paginator(qs.order_by("-submitted_at"), 20).get_page(request.GET.get("page"))

    query = request.GET.copy()
    query.pop("page", None)
    context = _workspace_context(request, survey, "responses")
    context.update(
        {
            "page": page,
            "search": search,
            "filters": filters,
            "querystring": query.urlencode(),
            "export_url": reverse("admin:feedback_survey_export", args=[survey.pk]) + (f"?{query.urlencode()}" if query else ""),
            "visibility_choices": SurveyResponse.Visibility.choices,
        }
    )
    return render(request, "admin/feedback/survey/responses.html", context)


def export_view(request, survey_id):
    _require_admin(request)
    survey = _get_survey(survey_id)
    content = export_responses_csv(survey, _survey_filters(request, survey).responses(Survey.objects.filter(pk=survey.pk)))
    builder.log_admin_action(request.user, survey, "Ответы экспортированы в CSV.")
    response = HttpResponse(content, content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="survey-{survey.pk}-responses.csv"'
    return response


def delete_response_view(request, survey_id, response_id):
    """Moderation: remove one response (e.g. spam through a public link)."""
    _require_admin(request)
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    survey = _get_survey(survey_id)
    response = get_object_or_404(SurveyResponse, pk=response_id, survey=survey)
    response.delete()
    builder.log_admin_action(request.user, survey, f"Удалён ответ #{response_id}.")
    messages.success(request, "Ответ удалён.")
    fallback = reverse("admin:feedback_survey_responses", args=[survey.pk])
    next_url = request.POST.get("next") or ""
    safe = next_url.startswith(fallback) and url_has_allowed_host_and_scheme(
        next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    )
    return redirect(next_url if safe else fallback)


# -- Analytics ------------------------------------------------------------------


def survey_analytics_view(request, survey_id):
    _require_admin(request)
    survey = _get_survey(survey_id)
    filters = _survey_filters(request, survey)
    responses = filters.responses(Survey.objects.filter(pk=survey.pk))
    counts = responses.aggregate(total=Count("id"))
    search = (request.GET.get("search") or "").strip()
    context = _workspace_context(request, survey, "analytics")
    context.update(
        {
            "filters": filters,
            "search": search,
            "filtered_total": counts["total"],
            "open_count": responses.filter(visibility=SurveyResponse.Visibility.OPEN).count(),
            "anonymous_count": responses.filter(visibility=SurveyResponse.Visibility.ANONYMOUS).count(),
            "stats": question_stats(survey, responses, text_search=search),
            "visibility_choices": SurveyResponse.Visibility.choices,
        }
    )
    return render(request, "admin/feedback/survey/analytics.html", context)


def overview_analytics_view(request):
    _require_admin(request)
    filters = FeedbackFilters.from_query(request.GET)
    context = {
        **_admin_context(request),
        "title": "Аналитика отзывов",
        "filters": filters,
        "data": overview(filters),
        "all_surveys": Survey.objects.order_by("-created_at").only("id", "title"),
        "groups": Group.objects.filter(feedback_surveys__isnull=False).distinct().order_by("name"),
        "teachers": Teacher.objects.filter(feedback_surveys__isnull=False).distinct().select_related("user"),
        "subjects": Subject.objects.filter(feedback_surveys__isnull=False).distinct().order_by("name"),
        "audience_choices": Survey.Audience.choices,
        "visibility_choices": SurveyResponse.Visibility.choices,
    }
    return render(request, "admin/feedback/overview.html", context)
