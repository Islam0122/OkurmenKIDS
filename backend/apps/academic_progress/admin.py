from django.contrib import admin

from . import numbering
from .models import CurriculumMonth, GroupLessonNumbering, GroupProgressAdjustment, NumberingFreeze, ProgramCurriculum


class CurriculumMonthInline(admin.TabularInline):
    model = CurriculumMonth
    extra = 0


@admin.register(ProgramCurriculum)
class ProgramCurriculumAdmin(admin.ModelAdmin):
    list_display = ("course", "lessons_per_month", "duration_months", "main_subject", "count_mode", "updated_at")
    filter_horizontal = ("extra_subjects",)
    inlines = [CurriculumMonthInline]
    readonly_fields = ("updated_by", "created_at", "updated_at")

    def changeform_view(self, request, object_id=None, form_url="", extra_context=None):
        """The settings and their study months are saved in one form: lessons
        already held keep their «месяц · урок» (numbering.preserving)."""
        if request.method != "POST":
            return super().changeform_view(request, object_id, form_url, extra_context)
        course_id = (ProgramCurriculum.objects.filter(pk=object_id).values_list("course_id", flat=True).first()
                     if object_id else request.POST.get("course"))
        groups = numbering.groups_of_course(int(course_id)) if str(course_id or "").isdigit() else []
        with numbering.preserving(groups, user=request.user):
            return super().changeform_view(request, object_id, form_url, extra_context)


@admin.register(GroupProgressAdjustment)
class GroupProgressAdjustmentAdmin(admin.ModelAdmin):
    list_display = ("group", "lessons_before_lms", "updated_by", "updated_at")
    readonly_fields = ("updated_by", "updated_at")


@admin.register(GroupLessonNumbering)
class GroupLessonNumberingAdmin(admin.ModelAdmin):
    list_display = ("group", "lessons_per_month", "updated_by", "updated_at")
    autocomplete_fields = ("group",)
    readonly_fields = ("updated_by", "updated_at")

    def save_model(self, request, obj, form, change):
        obj.updated_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(NumberingFreeze)
class NumberingFreezeAdmin(admin.ModelAdmin):
    """Read-only: written automatically so a change never renumbers held lessons."""

    list_display = ("group", "subject", "first_lesson", "last_lesson", "first_month", "lessons_per_month", "created_at")
    list_filter = ("lessons_per_month", "subject")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
