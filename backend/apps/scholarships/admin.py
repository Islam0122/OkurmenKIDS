from __future__ import annotations

from django import forms
from django.contrib import admin, messages
from django.db.models import F
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils import timezone
from django.utils.html import format_html
from django.utils.http import urlencode

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
from .services.generation import (
    add_award,
    approve_period,
    create_period,
    generate_period,
    limit_label,
    recalculate_period,
    remove_award,
    update_period,
)
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
# Periods — the main container: cards list, dashboard, report
# ---------------------------------------------------------------------------

class GeneratePeriodForm(forms.Form):
    award_day = forms.TypedChoiceField(choices=AWARD_DAY_CHOICES, coerce=int, label="Цикл")
    award_date = forms.DateField(
        label="Дата начисления",
        widget=forms.DateInput(attrs={"type": "date"}),
        help_text="Должна совпадать с днём цикла и не может быть в будущем.",
    )


LIMIT_PRESETS = (10, 20, 30)


class PeriodForm(forms.Form):
    """Create / edit a scholarship period. The same rules are enforced again
    by services.generation (create_period / update_period) — this form only
    gives the Admin the errors next to the right field."""

    title = forms.CharField(
        label="Название", max_length=150, initial="Стипендия",
        widget=forms.TextInput(attrs={"placeholder": "Стипендия"}),
    )
    period_start = forms.DateField(label="Дата начала", widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"))
    period_end = forms.DateField(label="Дата окончания", widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"))
    limit_enabled = forms.BooleanField(label="Ограничить количество студентов", required=False, initial=True)
    max_recipients = forms.IntegerField(
        label="Максимальное количество", required=False, min_value=1, max_value=1000,
        error_messages={"min_value": "Количество студентов должно быть больше 0."},
        widget=forms.NumberInput(attrs={"min": 1, "max": 1000, "inputmode": "numeric"}),
    )

    def __init__(self, *args, period: ScholarshipPeriod | None = None, awarded: int = 0, **kwargs):
        super().__init__(*args, **kwargs)
        self.period = period
        self.awarded = awarded
        self.dates_locked = period is not None and (not period.is_manual or not period.is_draft or period.is_calculated)
        self.limit_locked = period is not None and not period.is_draft
        for name in ("period_start", "period_end"):
            self.fields[name].disabled = self.dates_locked
        for name in ("limit_enabled", "max_recipients"):
            self.fields[name].disabled = self.limit_locked
        if awarded:
            self.fields["max_recipients"].widget.attrs["min"] = awarded

    def clean(self):
        cleaned = super().clean()
        start, end = cleaned.get("period_start"), cleaned.get("period_end")
        if start and end and end < start:
            self.add_error("period_end", "Дата окончания не может быть раньше даты начала.")
        if cleaned.get("limit_enabled"):
            limit = cleaned.get("max_recipients")
            if limit is None and "max_recipients" not in self.errors:
                self.add_error("max_recipients", "Укажите количество стипендиатов (больше 0) или снимите ограничение.")
            elif limit is not None and limit < self.awarded:
                self.add_error(
                    "max_recipients",
                    f"Сейчас стипендию получают {self.awarded} студентов — лимит не может быть меньше. "
                    "Сначала уберите лишних студентов.",
                )
            cleaned["limit"] = limit
        else:
            cleaned["limit"] = None
        return cleaned


# Ranking filter chips on the period dashboard: ?show=<key>.
_ROW_FILTERS = {
    "all": "Все",
    "awarded": "Стипендиаты",
    "eligible": "Допущены",
    "not_eligible": "Не допущены",
}


def _row_state(evaluation) -> tuple[str, str, str]:
    """(label, badge colour, hint) of one student's outcome in a period."""
    award = getattr(evaluation, "award", None)
    if award is not None:
        if award.status == ScholarshipAward.Status.APPROVED:
            return "Получил", "success", ""
        return "Назначена", "success", "Ожидает утверждения периода"
    if evaluation.is_eligible:
        return "Без стипендии", "muted", "Допущен, но не вошёл в список стипендиатов"
    return (
        evaluation.get_eligibility_status_display(),
        _STATUS_COLORS.get(evaluation.eligibility_status, "muted"),
        evaluation.ineligibility_reason,
    )


@admin.register(ScholarshipPeriod)
class ScholarshipPeriodAdmin(admin.ModelAdmin):
    list_display = (
        "period_label", "award_day", "evaluation_date", "status_badge", "max_recipients",
        "evaluated_count", "eligible_count", "recipients_count", "last_calculated_at",
    )
    list_filter = ("status",)
    list_per_page = 24
    change_list_template = "admin/scholarships/scholarshipperiod/change_list.html"
    actions = ["recalculate_action", "approve_action", "export_action"]

    def has_add_permission(self, request):
        # Periods are created through the dedicated "Создать период" form
        # (create_view), which goes through services.generation.
        return False

    def has_delete_permission(self, request, obj=None):
        return bool(request.user.is_superuser and (obj is None or obj.is_draft))

    # -- list columns ------------------------------------------------------

    def get_queryset(self, request):
        return analytics.annotate_periods(super().get_queryset(request))

    @admin.display(description="Период", ordering="period_start")
    def period_label(self, obj):
        return f"{obj.title} {obj.date_range}"

    @admin.display(description="Статус", ordering="status")
    def status_badge(self, obj):
        color = "success" if obj.status == ScholarshipPeriod.Status.APPROVED else "warning"
        return format_html('<span class="ok-badge ok-badge-{}">{}</span>', color, obj.get_status_display())

    @admin.display(description="Оценено")
    def evaluated_count(self, obj):
        return obj.evaluations_count or 0

    @admin.display(description="Допущено")
    def eligible_count(self, obj):
        return obj.eligible_count or 0

    @admin.display(description="Стипендий")
    def recipients_count(self, obj):
        return f"{obj.recipients_count or 0} / {limit_label(obj)}"

    # -- list: period cards --------------------------------------------------

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        extra_context.update(
            title="Стипендиальные периоды",
            can_generate=can_manage(request.user, "generate"),
            can_approve=can_manage(request.user, "approve"),
            active_configuration=ScholarshipConfiguration.objects.active(),
            today=timezone.localdate(),
        )
        return super().changelist_view(request, extra_context)

    # -- dashboard -----------------------------------------------------------

    def change_view(self, request, object_id, form_url="", extra_context=None):
        period = get_object_or_404(self.get_queryset(request), pk=object_id)
        if not self.has_view_permission(request, period):
            raise PermissionDenied

        ranking = analytics.ranking_queryset(period)
        row_filter = request.GET.get("show", "all")
        if row_filter == "awarded":
            ranking = ranking.filter(award__isnull=False)
        elif row_filter == "eligible":
            ranking = ranking.filter(eligibility_status=EligibilityStatus.ELIGIBLE)
        elif row_filter == "not_eligible":
            ranking = ranking.exclude(eligibility_status=EligibilityStatus.ELIGIBLE)
        else:
            row_filter = "all"

        stats = analytics.period_analytics(period)
        can_generate = can_manage(request.user, "generate")
        rows = [(ev, *_row_state(ev)) for ev in ranking]
        context = {
            **self.admin_site.each_context(request),
            "opts": self.model._meta,
            "title": f"{period.title} · {period.date_range}",
            "period": period,
            "original": period,
            "analytics": stats,
            "rows": rows,
            "row_filter": row_filter,
            "row_filters": _ROW_FILTERS,
            "can_generate": can_generate,
            "can_approve": can_manage(request.user, "approve"),
            "can_delete": self.has_delete_permission(request, period),
            "can_edit_awards": can_generate and period.is_draft and period.is_calculated,
            "today": timezone.localdate(),
            "has_ended": period.evaluation_date <= timezone.localdate(),
            "feedback_count": period.feedback.count(),
            "run_logs": period.run_logs.select_related("triggered_by")[:30],
            "limit_message": (
                f"Лимит стипендиатов достигнут: {stats['total_recipients']} из {period.max_recipients}."
                if stats["limit_reached"] else ""
            ),
        }
        return TemplateResponse(request, "admin/scholarships/scholarshipperiod/dashboard.html", context)

    # -- urls ----------------------------------------------------------------

    def get_urls(self):
        view = self.admin_site.admin_view
        custom = [
            path("create/", view(self.create_view), name="scholarships_create"),
            path("report/", view(self.report_view), name="scholarships_report"),
            path("generate/", view(self.generate_view), name="scholarships_generate"),
            path("<int:period_id>/edit/", view(self.edit_view), name="scholarships_edit"),
            path("<int:period_id>/recalculate/", view(self.recalculate_view), name="scholarships_recalculate"),
            path("<int:period_id>/approve/", view(self.approve_view), name="scholarships_approve"),
            path("<int:period_id>/export/", view(self.export_view), name="scholarships_export"),
            path("<int:period_id>/awards/add/", view(self.award_add_view), name="scholarships_award_add"),
            path(
                "<int:period_id>/awards/<int:award_id>/remove/", view(self.award_remove_view),
                name="scholarships_award_remove",
            ),
        ]
        return custom + super().get_urls()

    def _require(self, request, action_name: str) -> None:
        if not can_manage(request.user, action_name):
            raise PermissionDenied

    def _require_view(self, request) -> None:
        if not self.has_view_permission(request):
            raise PermissionDenied

    def _period_url(self, period, **query):
        url = reverse("admin:scholarships_scholarshipperiod_change", args=[period.pk])
        return f"{url}?{urlencode(query)}" if query else url

    def _page(self, request, template, title, **context):
        return render(request, template, {
            **self.admin_site.each_context(request),
            "opts": self.model._meta,
            "title": title,
            **context,
        })

    # -- create / edit -------------------------------------------------------

    def create_view(self, request):
        self._require(request, "generate")
        config = ScholarshipConfiguration.objects.active()
        if request.method == "POST":
            form = PeriodForm(request.POST)
            if form.is_valid():
                data = form.cleaned_data
                try:
                    period = create_period(
                        title=data["title"], period_start=data["period_start"], period_end=data["period_end"],
                        max_recipients=data["limit"], user=request.user,
                    )
                except ValidationError as exc:
                    form.add_error(None, exc.messages)
                else:
                    messages.success(request, f"Период создан: {period.title} {period.date_range}.")
                    return HttpResponseRedirect(self._period_url(period))
        else:
            form = PeriodForm(initial={
                "title": "Стипендия",
                "limit_enabled": True,
                "max_recipients": config.max_recipients if config else 20,
            })
        return self._page(
            request, "admin/scholarships/scholarshipperiod/period_form.html", "Создать стипендиальный период",
            form=form, limit_presets=LIMIT_PRESETS, active_configuration=config, is_create=True,
        )

    def edit_view(self, request, period_id):
        self._require(request, "generate")
        period = get_object_or_404(ScholarshipPeriod, pk=period_id)
        awarded = period.awards.count()
        if request.method == "POST":
            form = PeriodForm(request.POST, period=period, awarded=awarded, initial=self._form_initial(period))
            if form.is_valid():
                data = form.cleaned_data
                changes = {"title": data["title"]}
                if not form.dates_locked:
                    changes.update(period_start=data["period_start"], period_end=data["period_end"])
                if not form.limit_locked:
                    changes["max_recipients"] = data["limit"]
                try:
                    update_period(period, user=request.user, **changes)
                except ValidationError as exc:
                    form.add_error(None, exc.messages)
                else:
                    messages.success(request, "Период сохранён.")
                    return HttpResponseRedirect(self._period_url(period))
        else:
            form = PeriodForm(period=period, awarded=awarded, initial=self._form_initial(period))
        return self._page(
            request, "admin/scholarships/scholarshipperiod/period_form.html", "Изменить стипендиальный период",
            form=form, period=period, awarded=awarded, limit_presets=LIMIT_PRESETS, is_create=False,
        )

    @staticmethod
    def _form_initial(period):
        return {
            "title": period.title,
            "period_start": period.period_start,
            "period_end": period.period_end,
            "limit_enabled": not period.is_unlimited,
            "max_recipients": period.max_recipients,
        }

    # -- report --------------------------------------------------------------

    def report_view(self, request):
        self._require_view(request)
        periods = list(analytics.annotate_periods(ScholarshipPeriod.objects.all()))
        for period in periods:
            period.not_awarded = (period.eligible_count or 0) - (period.recipients_count or 0)
        selected = None
        period_id = request.GET.get("period")
        if period_id and period_id.isdigit():
            selected = next((p for p in periods if p.pk == int(period_id)), None)
        if selected is None and periods:
            # The newest period that has numbers; a running one is still empty.
            selected = next((p for p in periods if p.is_calculated), periods[0])
        totals = {
            "periods": len(periods),
            "recipients": sum(p.recipients_count or 0 for p in periods),
            "approved": sum(p.approved_count or 0 for p in periods),
            "amount": sum((p.total_amount or 0) for p in periods) if any(p.total_amount for p in periods) else None,
        }
        return self._page(
            request, "admin/scholarships/scholarshipperiod/report.html", "Отчёты по стипендиям",
            periods=periods, selected=selected,
            report=analytics.period_analytics(selected) if selected else None,
            totals=totals, awards_by_month=analytics.awards_by_month(), today=timezone.localdate(),
        )

    # -- cycle generation (automatic schedule, run by hand) -------------------

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
        return self._page(
            request, "admin/scholarships/scholarshipperiod/generate.html", "Сформировать ежемесячный цикл",
            form=form, today=today,
        )

    # -- POST actions --------------------------------------------------------

    def _post_only(self, request, period_id):
        if request.method != "POST":
            return None, HttpResponseRedirect(reverse("admin:scholarships_scholarshipperiod_change", args=[period_id]))
        return get_object_or_404(ScholarshipPeriod, pk=period_id), None

    def _run(self, request, success_message, func, *args, **kwargs):
        try:
            func(*args, user=request.user, **kwargs)
            messages.success(request, success_message)
        except ValidationError as exc:
            messages.error(request, "; ".join(exc.messages))

    def _back(self, request, period):
        """Return to the dashboard, keeping its ranking filter."""
        show = request.POST.get("show")
        return HttpResponseRedirect(self._period_url(period, **({"show": show} if show in _ROW_FILTERS else {})))

    def recalculate_view(self, request, period_id):
        self._require(request, "generate")
        period, redirect = self._post_only(request, period_id)
        if redirect:
            return redirect
        self._run(request, "Баллы рассчитаны.", recalculate_period, period)
        return self._back(request, period)

    def approve_view(self, request, period_id):
        self._require(request, "approve")
        period, redirect = self._post_only(request, period_id)
        if redirect:
            return redirect
        self._run(request, "Стипендии утверждены.", approve_period, period)
        return self._back(request, period)

    def award_add_view(self, request, period_id):
        self._require(request, "generate")
        period, redirect = self._post_only(request, period_id)
        if redirect:
            return redirect
        evaluation = get_object_or_404(ScholarshipEvaluation, pk=request.POST.get("evaluation") or 0, period=period)
        self._run(request, f"{evaluation.student_name}: стипендия назначена.", add_award, period, evaluation)
        return self._back(request, period)

    def award_remove_view(self, request, period_id, award_id):
        self._require(request, "generate")
        period, redirect = self._post_only(request, period_id)
        if redirect:
            return redirect
        award = get_object_or_404(ScholarshipAward.objects.select_related("evaluation"), pk=award_id, period=period)
        self._run(request, f"{award.evaluation.student_name}: стипендия убрана.", remove_award, period, award)
        return self._back(request, period)

    def export_view(self, request, period_id):
        self._require_view(request)
        period = get_object_or_404(ScholarshipPeriod, pk=period_id)
        return self._csv_response(period)

    @staticmethod
    def _csv_response(period):
        response = HttpResponse(analytics.export_ranking_csv(period), content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="scholarship-{period.period_start}-{period.period_end}.csv"'
        return response

    # -- bulk actions (Django changelist actions) ----------------------------

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
