"""Django admin операционного модуля — для администратора (просмотр и
исправление). Сотрудники работают в LMS: /operations, /tasks, /work-reports."""
from __future__ import annotations

from django.contrib import admin

from .models import (
    EmployeeReport,
    KPITarget,
    Notification,
    OperationalIssue,
    OperationsSettings,
    Task,
    TaskHistory,
    TaskRecurrence,
)


class ReadOnlyHistory(admin.TabularInline):
    model = TaskHistory
    extra = 0
    can_delete = False
    readonly_fields = ("actor", "action", "from_status", "to_status", "changes", "comment", "created_at")

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ("title", "department", "assignee", "status", "priority", "deadline", "created_by")
    list_filter = ("status", "department", "priority", "category")
    search_fields = ("title", "description")
    raw_id_fields = ("assignee", "created_by", "reviewer", "recurrence")
    inlines = [ReadOnlyHistory]


@admin.register(TaskRecurrence)
class TaskRecurrenceAdmin(admin.ModelAdmin):
    list_display = ("title", "assignee", "frequency", "is_active", "last_generated_on")
    list_filter = ("frequency", "is_active")
    raw_id_fields = ("assignee", "created_by")


@admin.register(EmployeeReport)
class EmployeeReportAdmin(admin.ModelAdmin):
    list_display = ("author", "kind", "period_start", "status", "department")
    list_filter = ("kind", "status", "department")
    raw_id_fields = ("author", "reviewed_by")


@admin.register(KPITarget)
class KPITargetAdmin(admin.ModelAdmin):
    list_display = ("metric", "department", "employee", "period", "target_value", "valid_from", "valid_to")
    list_filter = ("department", "period")
    raw_id_fields = ("employee", "created_by")


@admin.register(OperationalIssue)
class OperationalIssueAdmin(admin.ModelAdmin):
    list_display = ("title", "kind", "status", "priority", "department", "responsible", "detected_at")
    list_filter = ("kind", "status", "priority", "department")
    search_fields = ("title", "fingerprint")
    raw_id_fields = ("responsible", "resolved_by")


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("title", "recipient", "kind", "is_read", "created_at", "delivered_at")
    list_filter = ("kind", "is_read")
    raw_id_fields = ("recipient",)


admin.site.register(OperationsSettings)
