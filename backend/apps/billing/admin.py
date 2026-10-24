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


class ContractMonthPriceInline(admin.TabularInline):
    model = models.ContractMonthPrice
    extra = 0
    can_delete = False
    fields = ("month_number", "standard_price", "amount", "updated_by", "updated_at")
    readonly_fields = fields
    verbose_name_plural = "План стоимости учебных месяцев (изменяется на странице «План месяцев»)"

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(models.StudentBillingProfile)
class StudentBillingProfileAdmin(ReadOnlyAdmin):
    list_display = ("student", "plan", "status", "payment_mode", "standard_course_price", "final_course_price",
                    "discount_amount", "month_plan_mode", "month_plan_link")
    list_filter = ("status", "plan", "payment_mode", "month_plan_mode")
    search_fields = ("student__first_name", "student__last_name")
    inlines = [ContractMonthPriceInline]

    @admin.display(description="План месяцев")
    def month_plan_link(self, obj):
        from django.urls import reverse
        from django.utils.html import format_html

        if not obj.duration_months:
            return "—"
        return format_html('<a href="{}">План месяцев</a>', reverse("admin:billing_month_plan", args=[obj.pk]))

    def get_urls(self):
        from django.urls import path

        from .admin_views import month_plan_view

        return [
            path("<int:pk>/month-plan/",
                 self.admin_site.admin_view(lambda request, pk: month_plan_view(request, pk, self.admin_site)),
                 name="billing_month_plan"),
            *super().get_urls(),
        ]


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


@admin.register(models.FinancialCorrection)
class FinancialCorrectionAdmin(admin.ModelAdmin):
    """«Неправильные данные»: пункт меню раздела оплаты обучения. Виден и
    открывается только с разрешением `billing.correct_financial_records`
    (проверка — и здесь, и в каждом представлении `admin_corrections`)."""

    def _allowed(self, request):
        from .admin_corrections import allowed

        return allowed(request.user)

    def has_module_permission(self, request):
        return self._allowed(request)

    def has_view_permission(self, request, obj=None):
        return self._allowed(request)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def get_model_perms(self, request):
        return {"view": self._allowed(request)}

    def changelist_view(self, request, extra_context=None):
        from .admin_corrections import index_view

        return index_view(request, self.admin_site)

    def get_urls(self):
        from django.urls import path

        from . import admin_corrections as views

        wrap = self.admin_site.admin_view
        return [
            path("", wrap(lambda request: views.index_view(request, self.admin_site)),
                 name="billing_financialcorrection_changelist"),
            path("journal/", wrap(lambda request: views.journal_view(request, self.admin_site)),
                 name="billing_correction_journal"),
            path("<str:kind>/<int:pk>/", wrap(lambda request, kind, pk: views.correct_view(request, kind, pk,
                                                                                            self.admin_site)),
                 name="billing_correction_edit"),
            path("<str:kind>/<int:pk>/void/", wrap(lambda request, kind, pk: views.void_view(request, kind, pk,
                                                                                              self.admin_site)),
                 name="billing_correction_void"),
        ]
