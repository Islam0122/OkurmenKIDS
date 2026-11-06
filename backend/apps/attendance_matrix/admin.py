from django.contrib import admin

from .models import AttendanceChangeLog, GroupAssistant, MatrixSettings, TeamLeadDirection


@admin.register(GroupAssistant)
class GroupAssistantAdmin(admin.ModelAdmin):
    list_display = ("group", "assistant", "can_edit", "created_at")
    list_filter = ("can_edit",)
    search_fields = ("group__name", "assistant__first_name", "assistant__last_name", "assistant__username")
    autocomplete_fields = ("group",)
    list_select_related = ("group", "assistant")


@admin.register(TeamLeadDirection)
class TeamLeadDirectionAdmin(admin.ModelAdmin):
    list_display = ("team_lead", "subject")
    list_filter = ("subject",)
    list_select_related = ("team_lead", "subject")


@admin.register(MatrixSettings)
class MatrixSettingsAdmin(admin.ModelAdmin):
    list_display = ("__str__", "consecutive_absences_warning", "monthly_absences_attention", "monthly_absences_critical",
                    "missed_homework_warning", "team_lead_can_edit", "operations_director_can_edit", "updated_at")
    readonly_fields = ("updated_by", "updated_at")

    def has_add_permission(self, request):
        return not MatrixSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(AttendanceChangeLog)
class AttendanceChangeLogAdmin(admin.ModelAdmin):
    list_display = ("created_at", "student", "lesson", "actor", "actor_role")
    list_filter = ("actor_role",)
    search_fields = ("student__first_name", "student__last_name", "lesson__group__name")
    list_select_related = ("student", "lesson__group", "actor")
    readonly_fields = ("lesson", "student", "attendance", "actor", "actor_role", "changes", "created_at")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
