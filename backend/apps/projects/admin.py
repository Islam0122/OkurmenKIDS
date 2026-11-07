from django.contrib import admin

from .models import ProjectImage, StudentProject, Technology


class ProjectImageInline(admin.TabularInline):
    model = ProjectImage
    extra = 0


@admin.register(StudentProject)
class StudentProjectAdmin(admin.ModelAdmin):
    list_display = ("title", "student", "group", "created_by", "project_date", "status", "rating")
    list_filter = ("status", "project_date")
    search_fields = ("title", "student__first_name", "student__last_name")
    autocomplete_fields = ("student",)
    filter_horizontal = ("technologies",)
    readonly_fields = ("created_at", "updated_at")
    inlines = [ProjectImageInline]


@admin.register(Technology)
class TechnologyAdmin(admin.ModelAdmin):
    search_fields = ("name",)
