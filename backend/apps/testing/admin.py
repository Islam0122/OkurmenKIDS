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
from django.urls import path

from . import admin_views, session_admin_views
from .admin_views import is_admin_user
from .models import Test, TestSession


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
            path(session + "results/", view(session_admin_views.session_results_view), name="testing_session_results"),
            path(session + "results/export.<str:fmt>", view(session_admin_views.session_export_view), name="testing_session_export"),
            path(session + "activity/", view(session_admin_views.session_activity_view), name="testing_session_activity"),
            path(session + "settings/", view(session_admin_views.session_settings_view), name="testing_session_settings"),
            path(session + "action/<str:action>/", view(session_admin_views.session_action_view), name="testing_session_action"),
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
