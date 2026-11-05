from django.contrib import admin, messages
from django.utils import timezone

from .models import DailyPerformanceSnapshot, DashboardAccessKey
from .services.access_keys import issue_key


@admin.register(DailyPerformanceSnapshot)
class DailyPerformanceSnapshotAdmin(admin.ModelAdmin):
    list_display = (
        "date", "attendance_percent", "homework_percent", "active_groups", "active_students",
        "lessons_count", "status", "manual_fields",
    )
    list_filter = ("status",)
    date_hierarchy = "date"
    ordering = ("-date",)
    readonly_fields = (
        "date", "attendance_marked", "attendance_attended", "homework_results", "homework_done",
        "lessons_count", "status", "manual_fields", "corrected_by", "corrected_at", "computed_at",
        "created_at", "updated_at",
    )
    fields = (
        "date", "status",
        ("attendance_percent", "attendance_marked", "attendance_attended"),
        ("homework_percent", "homework_results", "homework_done"),
        ("active_groups", "active_students", "lessons_count"),
        "manual_comment", "manual_fields", "corrected_by", "corrected_at", "computed_at", "created_at", "updated_at",
    )

    def has_add_permission(self, request):
        return False  # снимки создаёт только планировщик (одна строка на дату)

    def save_model(self, request, obj, form, change):
        # Изменённые вручную поля больше не пересчитываются автоматически.
        changed = [f for f in DailyPerformanceSnapshot.EDITABLE_FIELDS if f in form.changed_data]
        if changed:
            obj.manual_fields = sorted({*(obj.manual_fields or []), *changed})
            obj.corrected_by = request.user
            obj.corrected_at = timezone.now()
        super().save_model(request, obj, form, change)


@admin.register(DashboardAccessKey)
class DashboardAccessKeyAdmin(admin.ModelAdmin):
    list_display = ("name", "prefix", "is_active", "expires_at", "last_used_at", "created_by", "created_at")
    list_filter = ("is_active",)
    fields = ("name", "is_active", "expires_at", "prefix", "last_used_at", "created_by", "created_at")
    readonly_fields = ("prefix", "last_used_at", "created_by", "created_at")

    def save_model(self, request, obj, form, change):
        if change:
            return super().save_model(request, obj, form, change)
        # Новый ключ: показываем один раз — в базе остаётся только хеш.
        key, raw = issue_key(obj.name, created_by=request.user, expires_at=obj.expires_at)
        obj.pk = key.pk
        obj.key_hash, obj.prefix = key.key_hash, key.prefix
        messages.warning(
            request,
            f"Ключ создан. Сохраните его — он больше не будет показан: {raw} . "
            f"Адрес для телевизора: <сайт>/monthly-performance?key={raw}",
        )
