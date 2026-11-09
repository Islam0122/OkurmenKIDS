from django.contrib import admin

from .models import PushPreference, PushSubscription


@admin.register(PushSubscription)
class PushSubscriptionAdmin(admin.ModelAdmin):
    """Read-only: subscriptions are created by browsers. Keys are never shown."""

    list_display = ("user", "user_agent", "created_at", "last_success_at", "failure_count")
    list_select_related = ("user",)
    search_fields = ("user__username", "user__first_name", "user__last_name")
    fields = ("user", "user_agent", "created_at", "last_success_at", "failure_count")
    readonly_fields = fields

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(PushPreference)
class PushPreferenceAdmin(admin.ModelAdmin):
    list_display = ("user", "tasks", "reports", "alerts", "updated_at")
    list_select_related = ("user",)
    search_fields = ("user__username",)
