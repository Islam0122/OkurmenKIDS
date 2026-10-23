"""Django admin: справочник офисов и настроек; сессии, события и исправления —
только просмотр (исправления делаются через API с обязательной причиной)."""
from django.contrib import admin

from .models import (
    AttendanceAdjustment,
    AttendanceAdminLog,
    AttendanceEvent,
    AttendanceLocation,
    AttendanceSession,
    AttendanceSettings,
    AttendanceWorkSchedule,
)


class ReadOnlyAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(AttendanceLocation)
class AttendanceLocationAdmin(admin.ModelAdmin):
    list_display = ("name", "latitude", "longitude", "radius_m", "is_active", "code")
    list_filter = ("is_active",)
    readonly_fields = ("code", "created_at", "updated_at")

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(AttendanceSettings)
class AttendanceSettingsAdmin(admin.ModelAdmin):
    list_display = ("__str__", "timezone", "work_start", "work_end", "late_grace_minutes", "max_gps_accuracy_m")
    readonly_fields = ("updated_at", "updated_by")

    def has_add_permission(self, request):
        return not AttendanceSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(AttendanceWorkSchedule)
class AttendanceWorkScheduleAdmin(admin.ModelAdmin):
    list_display = ("user", "work_start", "work_end", "work_days", "is_active")
    raw_id_fields = ("user",)
    readonly_fields = ("updated_at", "updated_by")


@admin.register(AttendanceSession)
class AttendanceSessionAdmin(ReadOnlyAdmin):
    list_display = ("user", "work_date", "checked_in_at", "checked_out_at", "status", "late_minutes", "is_adjusted")
    list_filter = ("status", "is_adjusted", "source", "work_date")
    search_fields = ("user__username", "user__first_name", "user__last_name")
    date_hierarchy = "work_date"


@admin.register(AttendanceEvent)
class AttendanceEventAdmin(ReadOnlyAdmin):
    list_display = ("user", "kind", "occurred_at", "location", "distance_m", "accuracy_m")
    list_filter = ("kind",)
    search_fields = ("user__username", "user__first_name", "user__last_name")


@admin.register(AttendanceAdjustment)
class AttendanceAdjustmentAdmin(ReadOnlyAdmin):
    list_display = ("session", "action", "adjusted_by", "created_at")
    search_fields = ("session__user__username", "reason")


@admin.register(AttendanceAdminLog)
class AttendanceAdminLogAdmin(ReadOnlyAdmin):
    list_display = ("action", "object_type", "object_id", "actor", "created_at")
