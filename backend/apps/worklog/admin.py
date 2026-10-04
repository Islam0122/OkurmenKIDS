from django.contrib import admin

from .models import TeamLeadReport, WorkLogEntry


@admin.register(WorkLogEntry)
class WorkLogEntryAdmin(admin.ModelAdmin):
    list_display = ("date", "entry_kind", "work_type", "title", "author", "responsible", "deadline", "status")
    list_filter = ("entry_kind", "work_type", "status", "priority")
    search_fields = ("title", "description", "result", "responsible")
    date_hierarchy = "date"


@admin.register(TeamLeadReport)
class TeamLeadReportAdmin(admin.ModelAdmin):
    list_display = ("date", "kind", "author", "teacher", "student", "status")
    list_filter = ("kind", "status")
    readonly_fields = ("metrics", "metrics_calculated_at", "created_at", "updated_at")
    date_hierarchy = "date"
