from __future__ import annotations

from django import forms
from django.contrib import admin
from django.db.models import Count
from django.http import HttpResponseRedirect
from django.urls import path, reverse
from django.utils.html import format_html

from apps.academy.models import Group
from apps.users.models import Subject, Teacher

from . import admin_views
from .admin_views import is_admin_user
from .models import Survey


def _badge(css: str, label: str) -> str:
    return format_html('<span class="ok-badge {}"><span class="ok-badge-dot"></span>{}</span>', css, label)


STATUS_BADGE = {
    Survey.Status.DRAFT: "ok-badge-muted",
    Survey.Status.PUBLISHED: "ok-badge-success",
    Survey.Status.CLOSED: "ok-badge-danger",
}


class SurveyAdminForm(forms.ModelForm):
    class Meta:
        model = Survey
        fields = [
            "title",
            "description",
            "audience",
            "visibility_mode",
            "child_name_mode",
            "ask_child_name_when_anonymous",
            "starts_at",
            "ends_at",
            "max_responses",
            "allow_multiple_submissions",
            "group",
            "teacher",
            "subject",
            "confirmation_message",
        ]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 3}),
            "confirmation_message": forms.Textarea(attrs={"rows": 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["group"].queryset = Group.objects.filter(status=Group.Status.ACTIVE).order_by("name")
        self.fields["teacher"].queryset = Teacher.objects.filter(is_active=True).select_related("user")
        self.fields["subject"].queryset = Subject.objects.filter(is_active=True)
        # Keep an already-linked but since deactivated target selectable.
        instance = self.instance
        for name, model in (("group", Group), ("teacher", Teacher), ("subject", Subject)):
            current = getattr(instance, f"{name}_id", None)
            if current:
                self.fields[name].queryset = (self.fields[name].queryset | model.objects.filter(pk=current)).distinct()


@admin.register(Survey)
class SurveyAdmin(admin.ModelAdmin):
    form = SurveyAdminForm
    list_display = (
        "title_link",
        "audience_badge",
        "visibility_badge",
        "status_badge",
        "question_count",
        "response_count",
        "created_at",
    )
    list_filter = ("audience", "status", "visibility_mode", "created_at")
    search_fields = ("title", "description")
    ordering = ("-created_at",)
    list_display_links = None
    fieldsets = (
        ("Опрос", {"fields": ("title", "description", "audience")}),
        (
            "Приватность",
            {
                "fields": ("visibility_mode", "child_name_mode", "ask_child_name_when_anonymous"),
                "description": (
                    "Анонимный ответ не сохраняет имя, телефон или IP-адрес. Имя ребёнка в анонимном отзыве "
                    "косвенно раскрывает родителя — включайте это только если действительно нужно."
                ),
            },
        ),
        ("Приём ответов", {"fields": ("starts_at", "ends_at", "max_responses", "allow_multiple_submissions")}),
        (
            "Привязка (необязательно)",
            {
                "fields": ("group", "teacher", "subject"),
                "description": "Показывается респонденту как контекст и используется в фильтрах аналитики.",
            },
        ),
        ("После отправки", {"fields": ("confirmation_message",)}),
    )

    # Survey management and responses are ADMIN-role only (not every staff
    # account) — the same rule as the academy workspace pages.
    def has_module_permission(self, request):
        return is_admin_user(request.user)

    def has_view_permission(self, request, obj=None):
        return is_admin_user(request.user)

    def has_add_permission(self, request):
        return is_admin_user(request.user)

    def has_change_permission(self, request, obj=None):
        return is_admin_user(request.user)

    def has_delete_permission(self, request, obj=None):
        if not is_admin_user(request.user):
            return False
        return obj is None or not obj.has_responses()

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .annotate(q_count=Count("questions", distinct=True), r_count=Count("responses", distinct=True))
        )

    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)

    def response_add(self, request, obj, post_url_continue=None):
        return HttpResponseRedirect(reverse("admin:feedback_survey_builder", args=[obj.pk]))

    def response_change(self, request, obj):
        if "_continue" in request.POST:
            return super().response_change(request, obj)
        return HttpResponseRedirect(reverse("admin:feedback_survey_builder", args=[obj.pk]))

    @admin.display(description="Опрос", ordering="title")
    def title_link(self, obj):
        return format_html('<a href="{}"><strong>{}</strong></a>', reverse("admin:feedback_survey_builder", args=[obj.pk]), obj.title)

    @admin.display(description="Аудитория", ordering="audience")
    def audience_badge(self, obj):
        return _badge("ok-badge-info" if obj.is_parent_survey else "ok-badge-success", obj.get_audience_display())

    @admin.display(description="Тип отзыва", ordering="visibility_mode")
    def visibility_badge(self, obj):
        return _badge("ok-badge-muted", obj.get_visibility_mode_display())

    @admin.display(description="Статус", ordering="status")
    def status_badge(self, obj):
        availability = obj.availability(response_count=obj.r_count)
        if obj.status == Survey.Status.PUBLISHED and availability != Survey.Availability.AVAILABLE:
            return _badge("ok-badge-warning", Survey.Availability(availability).label)
        return _badge(STATUS_BADGE[obj.status], obj.get_status_display())

    @admin.display(description="Вопросов", ordering="q_count")
    def question_count(self, obj):
        return obj.q_count

    @admin.display(description="Ответов", ordering="r_count")
    def response_count(self, obj):
        return obj.r_count

    def get_urls(self):
        view = self.admin_site.admin_view
        custom = [
            path("analytics/", view(admin_views.overview_analytics_view), name="feedback_analytics"),
            path("<int:survey_id>/builder/", view(admin_views.builder_view), name="feedback_survey_builder"),
            path("<int:survey_id>/preview/", view(admin_views.preview_view), name="feedback_survey_preview"),
            path("<int:survey_id>/responses/", view(admin_views.responses_view), name="feedback_survey_responses"),
            path(
                "<int:survey_id>/responses/export/",
                view(admin_views.export_view),
                name="feedback_survey_export",
            ),
            path(
                "<int:survey_id>/responses/<int:response_id>/delete/",
                view(admin_views.delete_response_view),
                name="feedback_survey_response_delete",
            ),
            path("<int:survey_id>/analytics/", view(admin_views.survey_analytics_view), name="feedback_survey_analytics"),
            path(
                "<int:survey_id>/action/<str:action>/",
                view(admin_views.lifecycle_action_view),
                name="feedback_survey_action",
            ),
        ]
        return custom + super().get_urls()
