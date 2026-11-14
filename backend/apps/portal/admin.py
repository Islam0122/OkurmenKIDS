from django.contrib import admin

from .models import PortalAccount, StudentLink


class StudentLinkInline(admin.TabularInline):
    model = StudentLink
    extra = 0
    raw_id_fields = ("student",)
    readonly_fields = ("created_by", "created_at")


@admin.register(PortalAccount)
class PortalAccountAdmin(admin.ModelAdmin):
    """Read-mostly: accounts are provisioned and their credentials reset by
    the Assistant (apps.assistant → apps.portal.services.accounts), which
    also writes the audit trail. No password is ever shown here."""

    list_display = ("user", "parent_phone", "must_change_password", "can_view_payments", "credentials_issued_at")
    list_filter = ("must_change_password", "can_view_payments")
    search_fields = ("user__username", "parent_phone", "students__first_name", "students__last_name")
    readonly_fields = ("user", "credentials_issued_at", "password_changed_at", "created_by", "created_at", "updated_at")
    inlines = [StudentLinkInline]
