from django.contrib import admin

from .models import BulkCopyItem, BulkCopyOperation


class ReadOnly:
    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class ItemInline(ReadOnly, admin.TabularInline):
    model = BulkCopyItem
    extra = 0
    fields = ("kind", "student", "source_lesson", "target_lesson", "action", "before", "after", "undo_result")
    readonly_fields = fields


@admin.register(BulkCopyOperation)
class BulkCopyOperationAdmin(ReadOnly, admin.ModelAdmin):
    """The audit log. Copying and undo run in the LMS (/app/bulk-copy)."""

    list_display = ("created_at", "source_group_name", "source_subject_name", "target_group_name",
                    "target_subject_name", "copied_count", "overwritten_count", "skipped_count", "status", "created_by")
    list_filter = ("status",)
    search_fields = ("operation_id", "source_group_name", "target_group_name")
    readonly_fields = [f.name for f in BulkCopyOperation._meta.fields]
    inlines = [ItemInline]
