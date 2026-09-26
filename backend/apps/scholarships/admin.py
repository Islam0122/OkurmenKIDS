from __future__ import annotations

from django import forms
from django.contrib import admin, messages
from django.db.models import F
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.urls import path, reverse
from django.utils import timezone
from django.utils.html import format_html

from .models import (
    AWARD_DAY_CHOICES,
    EligibilityStatus,
    ScholarshipAward,
    ScholarshipConfiguration,
    ScholarshipEvaluation,
    ScholarshipPeriod,
    ScholarshipRunLog,
    ScholarshipSubjectScore,
    TrainerFeedback,
)
from .permissions import can_manage
from .services import analytics
from .services.feedback import validate_feedback_target
from .services.generation import approve_period, generate_period, recalculate_period
from .services.periods import latest_award_date

_STATUS_COLORS = {
    EligibilityStatus.ELIGIBLE: "success",
    EligibilityStatus.BELOW_THRESHOLD: "muted",
    EligibilityStatus.INCOMPLETE_DATA: "warning",
    EligibilityStatus.NO_DATA: "muted",
    EligibilityStatus.NOT_FULL_PERIOD: "info",
    EligibilityStatus.INACTIVE: "danger",
}


def _score(value) -> str:
    return "—" if value is None else f"{value}"


class ReadOnlyAdminMixin:
    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

@admin.register(ScholarshipConfiguration)
class ScholarshipConfigurationAdmin(admin.ModelAdmin):
    list_display = ("name", "is_active", "award_mode", "max_recipients", "weights", "subject_aggregation", "auto_approve", "updated_at")
    list_filter = ("is_active", "award_mode")
    fieldsets = (
        ("Основное", {"fields": ("name", "is_active", "award_mode", "max_recipients", "award_amount", "auto_approve")}),
        ("Веса (сумма = 1.00)", {"fields": ("attendance_weight", "homework_weight", "feedback_weight")}),
        ("Правила расчёта", {"fields": (
            "subject_aggregation", "late_homework_credit", "min_overall_score", "min_marked_lessons",
            "require_complete_feedback",
        )}),
        ("Системная информация", {"fields": ("created_at", "updated_at"), "classes": ("collapse",)}),
    )
    readonly_fields = ("created_at", "updated_at")

    @admin.display(description="Веса П / ДЗ / Т")
    def weights(self, obj):
        return f"{obj.attendance_weight} / {obj.homework_weight} / {obj.feedback_weight}"


# ---------------------------------------------------------------------------
# Periods — the scholarship dashboard
# ---------------------------------------------------------------------------

class GeneratePeriodForm(forms.Form):
    award_day = forms.TypedChoiceField(choices=AWARD_DAY_CHOICES, coerce=int, label="Цикл")
    award_date = forms.DateField(
        label="Дата начисления",
        widget=forms.DateInput(attrs={"type": "date"}),
        help_text="Должна совпадать с днём цикла и не может быть в будущем.",
    )


@admin.register(ScholarshipPeriod)
class ScholarshipPeriodAdmin(admin.ModelAdmin):
    list_display = (
        "period_label", "award_day", "evaluation_date", "status_badge", "max_recipients",
        "evaluated_count", "eligible_count", "recipients_count", "last_calculated_at",
    )
    list_filter = ("status", "award_day")
    date_hierarchy = "period_start"
    change_form_template = "admin/scholarships/scholarshipperiod/change_form.html"
    change_list_template = "admin/scholarships/scholarshipperiod/change_list.html"
    actions = ["recalculate_action", "approve_action", "export_action"]
    fieldsets = (
        ("Период", {"fields": ("award_day", "period_start", "period_end", "evaluation_date", "status")}),
        ("Параметры расчёта (снимок настроек)", {"fields": (
            "max_recipients", "attendance_weight", "homework_weight", "feedback_weight", "subject_aggregation",
            "late_homework_credit", "min_overall_score", "min_marked_lessons", "require_complete_feedback",
            "award_amount", "configuration",
        )}),
        ("История", {"fields": ("generated_by", "last_calculated_at", "approved_by", "approved_at", "created_at")}),
    )

    def get_readonly_fields(self, request, obj=None):
        fields = [f for fieldset in self.fieldsets for f in fieldset[1]["fields"]]
        if obj is not None and obj.is_draft and can_manage(request.user, "generate"):
            # The one knob an Admin may adjust before approving; takes
            # effect on the next recalculation.
            fields.remove("max_recipients")
        return fields

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return bool(request.user.is_superuser and (obj is None or obj.is_draft))

    # -- list columns ------------------------------------------------------

    def get_queryset(self, request):
        from django.db.models import Count, Q

        return super().get_queryset(request).annotate(
            _evaluated=Count("evaluations", distinct=True),
            _eligible=Count("evaluations", filter=Q(evaluations__eligibility_status=EligibilityStatus.ELIGIBLE), distinct=True),
            _recipients=Count("awards", distinct=True),
        )

    @admin.display(description="Период", ordering="period_start")
    def period_label(self, obj):
        return f"{obj.period_start:%d.%m.%Y} – {obj.period_end:%d.%m.%Y}"

    @admin.display(description="Статус", ordering="status")
    def status_badge(self, obj):
        color = "success" if obj.status == ScholarshipPeriod.Status.APPROVED else "warning"
        return format_html('<span class="ok-badge ok-badge-{}">{}</span>', color, obj.get_status_display())

    @admin.display(description="Оценено")
    def evaluated_count(self, obj):
        return obj._evaluated

    @admin.display(description="Допущено")
    def eligible_count(self, obj):
        return obj._eligible

    @admin.display(description="Стипендий")
    def recipients_count(self, obj):
        return f"{obj._recipients} / {obj.max_recipients}"

    # -- dashboard ---------------------------------------------------------

    def change_view(self, request, object_id, form_url="", extra_context=None):
        period = get_object_or_404(ScholarshipPeriod, pk=object_id)
        extra_context = extra_context or {}
        extra_context.update(
            analytics=analytics.period_analytics(period),
            ranking=list(analytics.ranking_queryset(period)),
            can_generate=can_manage(request.user, "generate"),
            can_approve=can_manage(request.user, "approve"),
            status_colors=_STATUS_COLORS,
        )
        return super().change_view(request, object_id, form_url, extra_context)

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        extra_context.update(
            can_generate=can_manage(request.user, "generate"),
            awards_by_month=analytics.awards_by_month(),
            active_configuration=ScholarshipConfiguration.objects.active(),
        )
        return super().changelist_view(request, extra_context)

    def get_urls(self):
        custom = [
            path("generate/", self.admin_site.admin_view(self.generate_view), name="scholarships_generate"),
            path("<int:period_id>/recalculate/", self.admin_site.admin_view(self.recalculate_view), name="scholarships_recalculate"),
            path("<int:period_id>/approve/", self.admin_site.admin_view(self.approve_view), name="scholarships_approve"),
            path("<int:period_id>/export/", self.admin_site.admin_view(self.export_view), name="scholarships_export"),
        ]
        return custom + super().get_urls()

    def _require(self, request, action_name: str) -> None:
        if not can_manage(request.user, action_name):
            raise PermissionDenied

    def _period_url(self, period):
        return reverse("admin:scholarships_scholarshipperiod_change", args=[period.pk])

    def generate_view(self, request):
        self._require(request, "generate")
        today = timezone.localdate()
        if request.method == "POST":
            form = GeneratePeriodForm(request.POST)
            if form.is_valid():
                try:
                    result = generate_period(
                        form.cleaned_data["award_date"], form.cleaned_data["award_day"],
                        user=request.user, trigger=ScholarshipRunLog.Trigger.ADMIN,
                    )
                except ValidationError as exc:
                    form.add_error(None, exc.messages)
                else:
                    if result.created:
                        messages.success(request, f"Сформировано: {result.period}.")
                    else:
                        messages.warning(request, f"{result.period} уже сформирован — повторно не создаётся.")
                    return HttpResponseRedirect(self._period_url(result.period))
        else:
            form = GeneratePeriodForm(initial={"award_day": 1, "award_date": latest_award_date(1, today)})
        context = {
            **self.admin_site.each_context(request),
            "title": "Сформировать стипендиальный рейтинг",
            "form": form,
            "opts": self.model._meta,
            "today": today,
        }
        return render(request, "admin/scholarships/scholarshipperiod/generate.html", context)

    def _post_only(self, request, period_id):
        if request.method != "POST":
            return None, HttpResponseRedirect(reverse("admin:scholarships_scholarshipperiod_change", args=[period_id]))
        return get_object_or_404(ScholarshipPeriod, pk=period_id), None

    def recalculate_view(self, request, period_id):
        self._require(request, "generate")
        period, redirect = self._post_only(request, period_id)
        if redirect:
            return redirect
        try:
            recalculate_period(period, user=request.user)
            messages.success(request, "Баллы пересчитаны.")
        except ValidationError as exc:
            messages.error(request, "; ".join(exc.messages))
        return HttpResponseRedirect(self._period_url(period))

    def approve_view(self, request, period_id):
        self._require(request, "approve")
        period, redirect = self._post_only(request, period_id)
        if redirect:
            return redirect
        try:
            approve_period(period, user=request.user)
            messages.success(request, "Стипендии утверждены.")
        except ValidationError as exc:
            messages.error(request, "; ".join(exc.messages))
        return HttpResponseRedirect(self._period_url(period))

    def export_view(self, request, period_id):
        period = get_object_or_404(ScholarshipPeriod, pk=period_id)
        return self._csv_response(period)

    @staticmethod
    def _csv_response(period):
        response = HttpResponse(analytics.export_ranking_csv(period), content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="scholarship-{period.period_start}-{period.award_day}.csv"'
        return response

    # -- bulk actions --------------------------------------------------------

    @admin.action(description="Пересчитать баллы")
    def recalculate_action(self, request, queryset):
        self._require(request, "generate")
        for period in queryset:
            try:
                recalculate_period(period, user=request.user)
                messages.success(request, f"{period}: пересчитано.")
            except ValidationError as exc:
                messages.error(request, f"{period}: {'; '.join(exc.messages)}")

    @admin.action(description="Утвердить стипендии")
    def approve_action(self, request, queryset):
        self._require(request, "approve")
        for period in queryset:
            try:
                approve_period(period, user=request.user)
                messages.success(request, f"{period}: утверждено.")
            except ValidationError as exc:
                messages.error(request, f"{period}: {'; '.join(exc.messages)}")

    @admin.action(description="Экспорт рейтинга (CSV)")
    def export_action(self, request, queryset):
        if queryset.count() != 1:
            messages.error(request, "Выберите один период для экспорта.")
            return None
        return self._csv_response(queryset.get())


# ---------------------------------------------------------------------------
# Evaluations — per-student detail with subject breakdown
# ---------------------------------------------------------------------------

class SubjectScoreInline(admin.TabularInline):
    model = ScholarshipSubjectScore
    extra = 0
    can_delete = False
    verbose_name_plural = "Разбивка по предметам"
    fields = (
        "subject_name", "lessons_attended", "lessons_missed", "lessons_excused", "lessons_unmarked",
        "attendance_score", "homework_required", "homework_completed", "homework_score",
        "feedback_received", "feedback_score", "subject_score", "aggregation_weight",
    )
    readonly_fields = fields

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(ScholarshipEvaluation)
class ScholarshipEvaluationAdmin(ReadOnlyAdminMixin, admin.ModelAdmin):
    list_display = (
        "rank_column", "student_name", "group_name", "period", "overall_score", "attendance_score",
        "homework_score", "feedback_score", "eligibility_badge", "award_column",
    )
    list_display_links = ("student_name",)
    list_filter = ("period", "eligibility_status")
    search_fields = ("student_name", "group_name")
    list_select_related = ("period", "award")
    ordering = ("-period__period_start", F("rank").asc(nulls_last=True), F("overall_score").desc(nulls_last=True), "student_name")
    inlines = [SubjectScoreInline]
    change_form_template = "admin/scholarships/scholarshipevaluation/change_form.html"
    fieldsets = (
        ("Студент", {"fields": ("student", "student_name", "group_name", "course_name", "enrollment_date", "active_subjects")}),
        ("Итог", {"fields": (
            "period", "overall_score", "attendance_score", "homework_score", "feedback_score",
            "lessons_count", "subjects_count", "rank", "eligibility_status", "ineligibility_reason",
            "award_status", "warnings",
        )}),
    )
    readonly_fields = [f for fs in fieldsets for f in fs[1]["fields"]]

    @admin.display(description="Место", ordering="rank")
    def rank_column(self, obj):
        return obj.rank or "—"

    @admin.display(description="Допуск", ordering="eligibility_status")
    def eligibility_badge(self, obj):
        return format_html(
            '<span class="ok-badge ok-badge-{}" title="{}">{}</span>',
            _STATUS_COLORS.get(obj.eligibility_status, "muted"),
            obj.ineligibility_reason,
            obj.get_eligibility_status_display(),
        )

    @admin.display(description="Стипендия")
    def award_column(self, obj):
        award = getattr(obj, "award", None)
        return award.get_status_display() if award else "—"

    @admin.display(description="Стипендия")
    def award_status(self, obj):
        return self.award_column(obj)

    @admin.display(description="Предметы за период")
    def active_subjects(self, obj):
        return ", ".join(s.subject_name for s in obj.subject_scores.all()) or "—"

    @admin.display(description="Предупреждения о данных")
    def warnings(self, obj):
        if not obj.data_warnings:
            return "—"
        return format_html("<br>".join(["{}"] * len(obj.data_warnings)), *obj.data_warnings)

    def change_view(self, request, object_id, form_url="", extra_context=None):
        evaluation = get_object_or_404(ScholarshipEvaluation, pk=object_id)
        extra_context = extra_context or {}
        extra_context["history"] = (
            ScholarshipEvaluation.objects.filter(student_id=evaluation.student_id)
            .select_related("period", "award")
            .order_by("-period__period_start", "-period__award_day")
        )
        return super().change_view(request, object_id, form_url, extra_context)


@admin.register(ScholarshipAward)
class ScholarshipAwardAdmin(ReadOnlyAdminMixin, admin.ModelAdmin):
    list_display = ("rank", "student_link", "period", "award_date", "amount", "status", "approved_by", "approved_at")
    list_filter = ("status", "period")
    search_fields = ("evaluation__student_name",)
    list_select_related = ("period", "evaluation", "approved_by")

    @admin.display(description="Студент")
    def student_link(self, obj):
        url = reverse("admin:scholarships_scholarshipevaluation_change", args=[obj.evaluation_id])
        return format_html('<a href="{}">{}</a>', url, obj.evaluation.student_name)


class TrainerFeedbackForm(forms.ModelForm):
    class Meta:
        model = TrainerFeedback
        fields = "__all__"

    def clean(self):
        cleaned = super().clean()
        period, teacher = cleaned.get("period"), cleaned.get("teacher")
        student, subject = cleaned.get("student"), cleaned.get("subject")
        if period and teacher and student and subject:
            validate_feedback_target(period=period, teacher=teacher, student=student, subject=subject)
        return cleaned


@admin.register(TrainerFeedback)
class TrainerFeedbackAdmin(admin.ModelAdmin):
    """Admins review and, if needed, correct trainer feedback. Changes only
    affect a period's ranking after it is recalculated."""

    form = TrainerFeedbackForm

    list_display = ("student", "subject", "teacher", "period", "progress", "participation", "discipline", "understanding", "score_column", "updated_at")
    list_filter = ("period", "subject", "teacher")
    search_fields = ("student__first_name", "student__last_name", "comment")
    autocomplete_fields = ("student",)
    readonly_fields = ("created_by", "updated_by", "created_at", "updated_at")
    list_select_related = ("student", "subject", "teacher__user", "period")

    @admin.display(description="Балл (0–100)")
    def score_column(self, obj):
        return f"{obj.score:.2f}"

    def get_readonly_fields(self, request, obj=None):
        fields = list(super().get_readonly_fields(request, obj))
        if obj is not None and not obj.period.is_draft:
            fields += ["period", "student", "subject", "teacher", "progress", "participation", "discipline", "understanding", "comment"]
        return fields

    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user
        obj.updated_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(ScholarshipRunLog)
class ScholarshipRunLogAdmin(ReadOnlyAdminMixin, admin.ModelAdmin):
    list_display = ("created_at", "action", "trigger", "result", "period", "award_date", "message", "triggered_by")
    list_filter = ("result", "action", "trigger")
