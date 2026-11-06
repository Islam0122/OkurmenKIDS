from django.contrib import admin

from .models import CurriculumMonth, GroupProgressAdjustment, ProgramCurriculum


class CurriculumMonthInline(admin.TabularInline):
    model = CurriculumMonth
    extra = 0


@admin.register(ProgramCurriculum)
class ProgramCurriculumAdmin(admin.ModelAdmin):
    list_display = ("course", "lessons_per_month", "duration_months", "main_subject", "count_mode", "updated_at")
    filter_horizontal = ("extra_subjects",)
    inlines = [CurriculumMonthInline]
    readonly_fields = ("updated_by", "created_at", "updated_at")


@admin.register(GroupProgressAdjustment)
class GroupProgressAdjustmentAdmin(admin.ModelAdmin):
    list_display = ("group", "lessons_before_lms", "updated_by", "updated_at")
    readonly_fields = ("updated_by", "updated_at")
