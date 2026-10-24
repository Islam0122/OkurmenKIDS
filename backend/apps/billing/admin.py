"""Django Admin оплаты обучения — только просмотр: все изменения идут
через сервисы (API, страница «Управление платежом» — `admin_views`), иначе
обходятся проверки, блокировки и журнал."""
from django.contrib import admin

from . import models


class ReadOnlyAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(models.BillingPlan)
class BillingPlanAdmin(ReadOnlyAdmin):
    list_display = ("name", "subject", "course", "payment_due_days", "early_invoice_enabled", "is_active")


@admin.register(models.BillingPlanVersion)
class BillingPlanVersionAdmin(ReadOnlyAdmin):
    list_display = ("plan", "lessons_per_package", "package_price", "effective_from", "effective_to")


@admin.register(models.StudentBillingProfile)
class StudentBillingProfileAdmin(ReadOnlyAdmin):
    list_display = ("student", "subject", "plan", "status", "start_date", "discount_type", "discount_value")
    list_filter = ("status", "plan")
    search_fields = ("student__first_name", "student__last_name")


@admin.register(models.LessonPackage)
class LessonPackageAdmin(ReadOnlyAdmin):
    list_display = ("profile", "number", "status", "lessons_used", "lessons_total", "final_price")
    list_filter = ("status",)


@admin.register(models.Invoice)
class InvoiceAdmin(ReadOnlyAdmin):
    list_display = ("number", "profile", "amount", "amount_paid", "status", "issue_date", "due_date")
    list_filter = ("status",)
    search_fields = ("number",)


for model in (models.BillingTermsChange, models.LessonConsumption, models.InvoiceAdjustment, models.PaymentAllocation,
              models.CreditLedgerEntry, models.Reservation, models.BillingTask, models.BillingContactLog,
              models.BillingNotification, models.BillingEvent):
    admin.site.register(model, ReadOnlyAdmin)


@admin.register(models.Receipt)
class ReceiptAdmin(ReadOnlyAdmin):
    """Чеки (внутренние, не фискальные): просмотр, ссылка на платёж и
    повторную печать (на странице платежа — без новой операции)."""

    list_display = ("number", "kind", "status", "payment_link", "profile", "issued_at", "print_count")
    list_filter = ("status", "kind")
    search_fields = ("number", "profile__student__first_name", "profile__student__last_name")

    @admin.display(description="Платёж")
    def payment_link(self, obj):
        from django.urls import reverse
        from django.utils.html import format_html

        return format_html('<a href="{}">№{}</a>', reverse("admin:billing_payment_manage", args=[obj.payment_id]),
                           obj.payment_id)
