"""Admin registration for the «Тесты» section.

Only Test is registered: its list, add and change pages are replaced by the
section's own pages (admin_views.py), and every question URL is nested under
its test (/admin/testing/test/<id>/questions/...). Questions and options
have no admin of their own — a question only exists inside a test.

Besides it: sessions, «Результаты тестов» and «Проверка текстовых ответов»
(manual review of text answers — the only place they are graded by hand).
"""
from __future__ import annotations

import uuid

from django import forms
from django.contrib import admin, messages
from django.http import Http404
from django.shortcuts import redirect
from django.template.defaultfilters import linebreaksbr
from django.urls import path, reverse
from django.utils.html import format_html
from django.utils.text import Truncator

from . import admin_views, analytics_admin_views, io_admin_views, session_admin_views
from .admin_views import is_admin_user
from .models import REVIEW_GRADING_STATUSES, GradingStatus, Test, TestResult, TestSession, TextAnswerReview
from .services.grading import answer_points, check_answer
from .services.review import reset_review, review_answer


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


# ---------------------------------------------------------------------------
# «Проверка текстовых ответов» — manual review of text answers (proxy
# TextAnswerReview). The only place text answers are graded by hand;
# saving goes through services.review, which recalculates the attempt.
# ---------------------------------------------------------------------------

REVIEW_PENDING = "pending_review"
REVIEW_DONE = "reviewed"


class ReviewStatusFilter(admin.SimpleListFilter):
    title = "статус проверки"
    parameter_name = "review"

    def lookups(self, request, model_admin):
        return ((REVIEW_PENDING, "Ожидает проверки"), (REVIEW_DONE, "Проверен"))

    def queryset(self, request, queryset):
        if self.value() == REVIEW_PENDING:
            return queryset.filter(grading_status__in=REVIEW_GRADING_STATUSES)
        if self.value() == REVIEW_DONE:
            return queryset.exclude(grading_status__in=REVIEW_GRADING_STATUSES)
        return queryset


class TextAnswerReviewForm(forms.ModelForm):
    class Meta:
        model = TextAnswerReview
        fields = ("points_awarded", "review_comment")
        widgets = {"review_comment": forms.Textarea(attrs={"rows": 4})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        max_points = self.instance.question.points
        field = self.fields["points_awarded"]
        field.required = True
        field.min_value, field.max_value = 0, max_points
        field.widget.attrs.update({"min": 0, "max": max_points, "step": "0.5"})
        field.help_text = f"От 0 до {max_points}."

    def clean_points_awarded(self):
        points = self.cleaned_data["points_awarded"]
        max_points = self.instance.question.points
        if points is None or not 0 <= points <= max_points:
            raise forms.ValidationError(f"Балл должен быть от 0 до {max_points}.")
        return points


@admin.register(TextAnswerReview)
class TextAnswerReviewAdmin(AdminRoleOnly, admin.ModelAdmin):
    form = TextAnswerReviewForm
    list_display = ("student_column", "group_column", "test_column", "question_column", "answer_column",
                    "max_points_column", "points_column", "review_status_column", "answered_at")
    list_display_links = ("student_column", "question_column")
    list_filter = (
        ReviewStatusFilter,
        ("attempt__group", admin.RelatedOnlyFieldListFilter),
        ("question__test", admin.RelatedOnlyFieldListFilter),
        ("attempt__session", admin.RelatedOnlyFieldListFilter),
    )
    search_fields = ("attempt__student_name", "attempt__student__first_name", "attempt__student__last_name")
    date_hierarchy = "answered_at"
    list_select_related = ("attempt__student", "attempt__group", "attempt__session__test", "question")
    ordering = ("-answered_at",)
    actions = ("give_max_points", "give_zero_points", "send_back_to_review")
    readonly_fields = ("student_column", "group_column", "session_column", "question_full", "reference_column",
                       "answer_full", "max_points_column", "review_status_column", "answered_at",
                       "reviewed_by", "reviewed_at", "attempt_score_column")
    fieldsets = (
        ("Ответ", {"fields": ("student_column", "group_column", "session_column", "answered_at")}),
        ("Вопрос и ответ студента", {"fields": ("question_full", "reference_column", "answer_full")}),
        ("Проверка", {"fields": ("max_points_column", "points_awarded", "review_comment", "review_status_column",
                                 "reviewed_by", "reviewed_at", "attempt_score_column")}),
    )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def save_model(self, request, obj, form, change):
        review_answer(obj, form.cleaned_data["points_awarded"], form.cleaned_data["review_comment"], request.user)

    # -- columns ------------------------------------------------------------

    @admin.display(description="Студент", ordering="attempt__student_name")
    def student_column(self, obj):
        return str(obj.attempt.student) if obj.attempt.student_id else obj.attempt.student_name

    @admin.display(description="Группа", ordering="attempt__group__name")
    def group_column(self, obj):
        return obj.attempt.group or "—"

    @admin.display(description="Тест / сессия", ordering="attempt__session__test__title")
    def test_column(self, obj):
        session = obj.attempt.session
        title = obj.attempt.test_title or session.test.title
        return f"{title} / {session.title}" if session.title else title

    @admin.display(description="Тест / сессия")
    def session_column(self, obj):
        return format_html('{} — <a href="{}">попытка</a>', self.test_column(obj),
                           reverse("admin:testing_attempt_detail", args=[obj.attempt_id]))

    @admin.display(description="Вопрос")
    def question_column(self, obj):
        return Truncator(obj.question.text).chars(80)

    @admin.display(description="Ответ студента")
    def answer_column(self, obj):
        return Truncator(obj.answer_text).chars(120) or "—"

    @admin.display(description="Текст вопроса")
    def question_full(self, obj):
        return linebreaksbr(obj.question.text)

    @admin.display(description="Эталонные ответы")
    def reference_column(self, obj):
        accepted = obj.question.correct_answers or []
        if not accepted:
            return "—"
        matches, _ = check_answer(obj.question, obj.answer_text)
        hint = "совпадает с эталоном" if matches else "не совпадает с эталоном"
        return format_html("{}<br><small>Подсказка: ответ {}.</small>", "; ".join(map(str, accepted)), hint)

    @admin.display(description="Ответ студента")
    def answer_full(self, obj):
        return format_html('<div style="white-space: pre-wrap">{}</div>', obj.answer_text or "—")

    @admin.display(description="Макс. балл", ordering="question__points")
    def max_points_column(self, obj):
        return obj.question.points

    @admin.display(description="Текущий балл", ordering="points_awarded")
    def points_column(self, obj):
        if obj.grading_status in REVIEW_GRADING_STATUSES:
            return "—"
        return answer_points(obj, obj.question.points)

    @admin.display(description="Статус проверки", ordering="grading_status")
    def review_status_column(self, obj):
        if obj.grading_status in REVIEW_GRADING_STATUSES:
            return format_html('<span class="badge bg-warning text-dark">{}</span>', "Ожидает проверки")
        label = "Проверен" if obj.grading_status == GradingStatus.MANUAL else "Проверен автоматически"
        return format_html('<span class="badge bg-success">{}</span>', label)

    @admin.display(description="Итог попытки, %")
    def attempt_score_column(self, obj):
        return f"{round(obj.attempt.score, 2)}%"

    # -- bulk actions ---------------------------------------------------------

    def _bulk(self, request, queryset, apply, message):
        done = 0
        for answer in queryset.select_related("question"):
            apply(answer)
            done += 1
        self.message_user(request, f"{message}: {done}.", messages.SUCCESS)

    @admin.action(description="Выставить максимальный балл")
    def give_max_points(self, request, queryset):
        self._bulk(request, queryset, lambda a: review_answer(a, a.question.points, a.review_comment, request.user),
                   "Оценено на максимум")

    @admin.action(description="Выставить 0 баллов")
    def give_zero_points(self, request, queryset):
        self._bulk(request, queryset, lambda a: review_answer(a, 0, a.review_comment, request.user),
                   "Оценено в 0 баллов")

    @admin.action(description="Вернуть на проверку")
    def send_back_to_review(self, request, queryset):
        self._bulk(request, queryset, reset_review, "Возвращено на проверку")
