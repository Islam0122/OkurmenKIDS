"""Admin registration for the «Тесты» section.

Only Test is registered: its list, add and change pages are replaced by the
section's own pages (admin_views.py), and every question URL is nested under
its test (/admin/testing/test/<id>/questions/...). Questions and options
have no admin of their own — a question only exists inside a test.
"""
from __future__ import annotations

import uuid

from django import forms
from django.contrib import admin, messages
from django.http import Http404
from django.shortcuts import redirect, render
from django.urls import path, reverse

from . import admin_views, analytics_admin_views, io_admin_views, session_admin_views
from .admin_views import is_admin_user
from .models import StudentPortalAccess, Test, TestSession


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


class IssueGroupCodesForm(forms.Form):
    group = forms.ModelChoiceField(label="Группа", queryset=None, empty_label="— Выберите группу —")

    def __init__(self, *args, **kwargs):
        from apps.academy.models import Group

        super().__init__(*args, **kwargs)
        self.fields["group"].queryset = Group.objects.order_by("name")
        self.fields["group"].widget.attrs["class"] = "form-control"


@admin.register(StudentPortalAccess)
class StudentPortalAccessAdmin(AdminRoleOnly, admin.ModelAdmin):
    """«Доступ студентов» — personal codes for the student portal (/student/).
    A code is generated on save; give it to the student. Regenerating or
    deactivating a code signs the student out on their next request."""

    list_display = ("student", "group_column", "code", "is_active", "last_login_at", "created_at")
    list_filter = ("is_active", "student__group")
    search_fields = ("student__first_name", "student__last_name", "code")
    autocomplete_fields = ("student",)
    readonly_fields = ("code", "created_at", "last_login_at")
    fields = ("student", "code", "is_active", "created_at", "last_login_at")
    actions = ["regenerate_codes", "activate", "deactivate"]
    change_list_template = "admin/testing/studentportalaccess/change_list.html"
    list_select_related = ("student__group",)

    @admin.display(description="Группа", ordering="student__group__name")
    def group_column(self, obj):
        return obj.student.group.name if obj.student.group_id else "—"

    def get_readonly_fields(self, request, obj=None):
        # The student is chosen once; a code belongs to that student only.
        return (*self.readonly_fields, "student") if obj else self.readonly_fields

    @admin.action(description="Перевыпустить коды (старые перестанут работать)")
    def regenerate_codes(self, request, queryset):
        for access in queryset:
            access.regenerate_code()
        messages.success(request, f"Новые коды выданы: {queryset.count()}.")

    @admin.action(description="Включить доступ")
    def activate(self, request, queryset):
        messages.success(request, f"Доступ включён: {queryset.update(is_active=True)}.")

    @admin.action(description="Отключить доступ")
    def deactivate(self, request, queryset):
        messages.success(request, f"Доступ отключён: {queryset.update(is_active=False)}.")

    def get_urls(self):
        urls = [
            path(
                "issue-group/",
                self.admin_site.admin_view(self.issue_group_view),
                name="testing_studentportalaccess_issue_group",
            ),
        ]
        return urls + super().get_urls()

    def issue_group_view(self, request):
        """Codes for every active student of a group who has none yet."""
        if not self.has_add_permission(request):
            raise Http404
        from apps.academy.models import Student

        form = IssueGroupCodesForm(request.POST or None)
        if request.method == "POST" and form.is_valid():
            group = form.cleaned_data["group"]
            students = Student.objects.filter(group=group, is_active=True, portal_access__isnull=True)
            created = 0
            for student in students:
                StudentPortalAccess.objects.create(student=student)
                created += 1
            messages.success(request, f"Группа «{group.name}»: выдано новых кодов — {created}.")
            return redirect(f"{reverse('admin:testing_studentportalaccess_changelist')}?student__group__id__exact={group.pk}")
        return render(request, "admin/testing/studentportalaccess/issue_group.html", {
            **self.admin_site.each_context(request),
            "title": "Выдать коды группе",
            "form": form,
            "opts": self.model._meta,
        })


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
