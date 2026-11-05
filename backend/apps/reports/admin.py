from django.contrib import admin

from .models import ParentReport, ParentReportImage


class ParentReportImageInline(admin.TabularInline):
    model = ParentReportImage
    extra = 0
    fields = ["page", "student_name", "width", "height"]
    readonly_fields = fields
    can_delete = False
    show_change_link = False


@admin.register(ParentReport)
class ParentReportAdmin(admin.ModelAdmin):
    list_display = ["id", "group_name", "report_type", "language", "start_date", "end_date", "status", "created_by", "created_at"]
    list_filter = ["report_type", "language", "status", "created_at"]
    search_fields = ["group_name", "course_name"]
    readonly_fields = [field.name for field in ParentReport._meta.fields]
    inlines = [ParentReportImageInline]

    def has_add_permission(self, request):
        return False
