"""Admin registration for the «Тесты» section.

Only Test is registered: its list, add and change pages are replaced by the
section's own pages (admin_views.py), and every question URL is nested under
its test (/admin/testing/test/<id>/questions/...). Questions and options
have no admin of their own — a question only exists inside a test.
"""
from __future__ import annotations

import uuid

from django.contrib import admin
from django.http import Http404
from django.shortcuts import redirect
from django.urls import path, reverse

from . import admin_views, analytics_admin_views, io_admin_views, session_admin_views
from .admin_views import is_admin_user
from .models import Test, TestResult, TestSession


@admin.register(Test)
class TestAdmin(admin.ModelAdmin):
    # Used by Django's own delete confirmation and history pages only.
    search_fields = ("title",)

    # ADMIN role only (not every staff account) — same rule as surveys.
    def has_module_permission(self, request):
        return is_admin_user(request.user)

    def has_view_permission(self, request, obj=None):
        return is_admin_user(request.user)

    def has_add_permission(self, request):
        return is_admin_user(request.user)

    def has_change_permission(self, request, obj=None):
        return is_admin_user(request.user)

    def has_delete_permission(self, request, obj=None):
        return is_admin_user(request.user)

    def changelist_view(self, request, extra_context=None):
        return admin_views.tests_list_view(request)

    def add_view(self, request, form_url="", extra_context=None):
        return admin_views.test_create_view(request)

    def change_view(self, request, object_id, form_url="", extra_context=None):
        return admin_views.test_overview_view(request, object_id)

    def get_urls(self):
        view = self.admin_site.admin_view
        test = "<uuid:test_id>/"
        question = test + "questions/<uuid:question_id>/"
        urls = [
            path("export/", view(io_admin_views.tests_export_view), name="testing_test_export"),
            path("import/", view(io_admin_views.tests_import_view), name="testing_test_import"),
            path("import/template/", view(io_admin_views.tests_import_template_view), name="testing_test_import_template"),
            path(test + "duplicate/", view(io_admin_views.test_duplicate_view), name="testing_test_duplicate"),
            path(test + "questions/export/", view(io_admin_views.questions_export_view), name="testing_questions_export"),
            path(test + "questions/import/", view(io_admin_views.questions_import_view), name="testing_questions_import"),
            path(
                test + "questions/import/template/",
                view(io_admin_views.questions_import_template_view),
                name="testing_questions_import_template",
            ),
            path(test + "settings/", view(admin_views.test_settings_view), name="testing_test_settings"),
            path(test + "publish/", view(admin_views.test_publish_view), name="testing_test_publish"),
            path(test + "stats/", view(admin_views.test_stats_view), name="testing_test_stats"),
            path(test + "preview/", view(admin_views.test_preview_view), name="testing_test_preview"),
            path(test + "status/<str:action>/", view(admin_views.test_status_action_view), name="testing_test_status"),
            path(test + "questions/add/", view(admin_views.question_editor_view), name="testing_question_add"),
            path(test + "questions/reorder/", view(admin_views.questions_reorder_view), name="testing_questions_reorder"),
            path(question, view(admin_views.question_editor_view), name="testing_question_change"),
            path(question + "<str:action>/", view(admin_views.question_action_view), name="testing_question_action"),
        ]
        return urls + super().get_urls()


class AdminRoleOnly:
    """ADMIN role only (not every staff account) — same rule as surveys."""

    def has_module_permission(self, request):
        return is_admin_user(request.user)

    def has_view_permission(self, request, obj=None):
        return is_admin_user(request.user)

    def has_add_permission(self, request):
        return is_admin_user(request.user)

    def has_change_permission(self, request, obj=None):
        return is_admin_user(request.user)

    def has_delete_permission(self, request, obj=None):
        return is_admin_user(request.user)


@admin.register(TestSession)
class TestSessionAdmin(AdminRoleOnly, admin.ModelAdmin):
    """«Сессии» — its own section, separate from «Тесты». Its list, add and
    change pages are the section's pages (session_admin_views.py)."""

    search_fields = ("title", "key")

    def changelist_view(self, request, extra_context=None):
        return session_admin_views.sessions_list_view(request)

    def add_view(self, request, form_url="", extra_context=None):
        return session_admin_views.session_create_view(request)

    def change_view(self, request, object_id, form_url="", extra_context=None):
        try:
            uuid.UUID(str(object_id))
        except ValueError:
            raise Http404("Сессия не найдена.")
        return session_admin_views.session_overview_view(request, object_id)

    def get_urls(self):
        view = self.admin_site.admin_view
        session = "<uuid:session_id>/"
        urls = [
            path(session + "participants/", view(session_admin_views.session_participants_view), name="testing_session_participants"),
            path(session + "questions/", view(analytics_admin_views.session_questions_view), name="testing_session_questions"),
            path(session + "analytics/", view(analytics_admin_views.session_analytics_view), name="testing_session_analytics"),
            path(session + "analytics/export.<str:fmt>", view(analytics_admin_views.session_export_view), name="testing_session_export"),
            path(session + "results/", view(analytics_admin_views.session_results_view), name="testing_session_results"),
            path("attempts/<uuid:attempt_id>/", view(analytics_admin_views.attempt_detail_view), name="testing_attempt_detail"),
            path("analytics/", view(analytics_admin_views.analytics_tree_view), name="testing_analytics"),
            path("analytics/groups/<int:group_id>/", view(analytics_admin_views.group_analytics_view), name="testing_analytics_group"),
            path("analytics/subjects/<int:subject_id>/", view(analytics_admin_views.subject_analytics_view), name="testing_analytics_subject"),
            path("analytics/tests/<uuid:test_id>/", view(analytics_admin_views.test_analytics_view), name="testing_analytics_test"),
            path(session + "activity/", view(session_admin_views.session_activity_view), name="testing_session_activity"),
            path(session + "settings/", view(session_admin_views.session_settings_view), name="testing_session_settings"),
            path(session + "action/<str:action>/", view(session_admin_views.session_action_view), name="testing_session_action"),
            path("exam-monitoring/", view(session_admin_views.exam_monitoring_view), name="testing_exam_monitoring"),
            path("group-students/<int:group_id>/", view(session_admin_views.group_students_view), name="testing_session_group_students"),
        ]
        return urls + super().get_urls()


# /admin/tests/ and /admin/sessions/ — the sections' short addresses.
_original_get_urls = admin.site.get_urls


def _get_urls_with_tests_shortcut():
    shortcuts = [
        path("tests/", admin.site.admin_view(lambda request: redirect("admin:testing_test_changelist")), name="testing_tests"),
        path(
            "sessions/",
            admin.site.admin_view(lambda request: redirect("admin:testing_testsession_changelist")),
            name="testing_sessions",
        ),
    ]
    return [*shortcuts, *_original_get_urls()]


admin.site.get_urls = _get_urls_with_tests_shortcut


# ---------------------------------------------------------------------------
# «Результаты тестов» — finished attempts of LMS students (proxy TestResult).
# Group / teacher / subject / test are the result's historical snapshot.
# ---------------------------------------------------------------------------

class ResultStatusFilter(admin.SimpleListFilter):
    title = "статус"
    parameter_name = "result"

    def lookups(self, request, model_admin):
        return (("passed", "Сдал"), ("failed", "Не сдал"))

    def queryset(self, request, queryset):
        from django.db.models import F

        passed = queryset.filter(score__gte=F("session__test__passing_score"))
        if self.value() == "passed":
            return passed
        if self.value() == "failed":
            return queryset.exclude(pk__in=passed.values("pk"))
        return queryset


class ScoreRangeFilter(admin.SimpleListFilter):
    title = "балл"
    parameter_name = "score_range"
    RANGES = {"0-49": (0, 49.999), "50-74": (50, 74.999), "75-89": (75, 89.999), "90-100": (90, 100)}

    def lookups(self, request, model_admin):
        return [(key, f"{key}%") for key in self.RANGES]

    def queryset(self, request, queryset):
        if self.value() in self.RANGES:
            low, high = self.RANGES[self.value()]
            return queryset.filter(score__gte=low, score__lte=high)
        return queryset


@admin.register(TestResult)
class TestResultAdmin(AdminRoleOnly, admin.ModelAdmin):
    list_display = ("student_column", "group", "teacher", "test_column", "subject", "score_column", "status_column",
                    "finished_at", "open_link")
    list_filter = (
        ResultStatusFilter, ScoreRangeFilter,
        ("group", admin.RelatedOnlyFieldListFilter), ("teacher", admin.RelatedOnlyFieldListFilter),
        ("subject", admin.RelatedOnlyFieldListFilter), ("session__test", admin.RelatedOnlyFieldListFilter),
        ("student", admin.RelatedOnlyFieldListFilter),
    )
    search_fields = ("student_name", "student__first_name", "student__last_name", "test_title", "session__test__title",
                     "group__name")
    date_hierarchy = "finished_at"
    list_select_related = ("student", "group", "teacher__user", "subject", "session__test")
    ordering = ("-finished_at",)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.display(description="Студент", ordering="student_name")
    def student_column(self, obj):
        return str(obj.student) if obj.student_id else obj.student_name

    @admin.display(description="Тест", ordering="test_title")
    def test_column(self, obj):
        return obj.test_title or obj.session.test.title

    @admin.display(description="Балл, %", ordering="score")
    def score_column(self, obj):
        return f"{round(obj.score)}%"

    @admin.display(description="Статус")
    def status_column(self, obj):
        from django.utils.html import format_html

        passed = obj.score >= obj.session.test.passing_score
        return format_html('<span class="badge bg-{}">{}</span>', "success" if passed else "danger",
                           "Сдал" if passed else "Не сдал")

    @admin.display(description="")
    def open_link(self, obj):
        from django.utils.html import format_html

        return format_html('<a href="{}">Подробнее</a>', reverse("admin:testing_attempt_detail", args=[obj.pk]))
