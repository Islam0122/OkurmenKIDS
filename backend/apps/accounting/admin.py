"""Django admin бухгалтерии — только просмотр (плюс отдельная страница
очистки данных для суперпользователя, см. admin_views).

Финансовые операции выполняются через API бухгалтерии (сервисный слой
с проверками, транзакциями и аудитом). Здесь администратор может только
посмотреть записи: ни добавить, ни изменить, ни удалить их в обход
сервисов нельзя — в том числе журнал аудита.
"""
from django.contrib import admin
from django.urls import path

from .models import (
    CourseCycle,
    CoursePayrollSettings,
    CoursePriceVersion,
    CycleAccrual,
    CycleLesson,
    EmployeeSalaryProfile,
    Payroll,
    PayrollAdjustment,
    PayrollAuditLog,
    PayrollLine,
    PayrollPayment,
    PayrollPeriod,
    SalaryRule,
    StudentPayment,
)


class ReadOnlyAdmin(admin.ModelAdmin):
    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class ReceivedMonthFilter(admin.SimpleListFilter):
    """Месяц ФАКТИЧЕСКОГО поступления денег (не дата записи)."""

    title = "месяц поступления"
    parameter_name = "received_month"

    def lookups(self, request, model_admin):
        months = StudentPayment.objects.dates("received_date", "month", order="DESC")
        return [(f"{m:%Y-%m}", f"{m:%m.%Y}") for m in months[:36]]

    def queryset(self, request, queryset):
        if self.value():
            year, month = self.value().split("-")
            return queryset.filter(received_date__year=int(year), received_date__month=int(month))
        return queryset


@admin.register(StudentPayment)
class StudentPaymentAdmin(ReadOnlyAdmin):
    """Платежи: просмотр, фильтры и поиск; изменения — на странице
    «Управление платежом» (оплата обучения), которая вызывает сервисы с
    проверкой прав, блокировками и аудитом. Обычная форма — только чтение."""

    list_display = ("id", "receipt_number", "student", "kind", "amount", "received_date", "method", "status",
                    "created_at", "manage_link")
    list_filter = ("status", "kind", "method", "purpose", ReceivedMonthFilter)
    date_hierarchy = "received_date"
    search_fields = ("student__first_name", "student__last_name", "reference", "receipt__number")
    list_select_related = ("student", "receipt")

    def get_search_results(self, request, queryset, search_term):
        qs, distinct = super().get_search_results(request, queryset, search_term)
        term = search_term.strip().lstrip("№#")
        if term.isdigit():  # номер платежа
            qs |= queryset.filter(pk=int(term))
        return qs, distinct

    @admin.display(description="Чек")
    def receipt_number(self, obj):
        receipt = getattr(obj, "receipt", None)
        return receipt.number if receipt else "—"

    @admin.display(description="Действия")
    def manage_link(self, obj):
        from django.urls import reverse
        from django.utils.html import format_html

        if not obj.billing_profile_id:
            return "—"
        return format_html('<a href="{}">Открыть / исправить / аннулировать</a>',
                           reverse("admin:billing_payment_manage", args=[obj.pk]))

    def get_urls(self):
        from apps.billing.admin_views import manage_payment_view

        return [
            path("<int:pk>/manage/",
                 self.admin_site.admin_view(lambda request, pk: manage_payment_view(request, pk, self.admin_site)),
                 name="billing_payment_manage"),
            *super().get_urls(),
        ]


@admin.register(EmployeeSalaryProfile)
class EmployeeSalaryProfileAdmin(ReadOnlyAdmin):
    list_display = ("employee", "salary_type", "is_active", "effective_from", "effective_to")


@admin.register(SalaryRule)
class SalaryRuleAdmin(ReadOnlyAdmin):
    list_display = ("employee_profile", "rule_type", "amount", "percentage", "effective_from", "effective_to")
    list_filter = ("rule_type",)


@admin.register(PayrollPeriod)
class PayrollPeriodAdmin(ReadOnlyAdmin):
    list_display = ("__str__", "period_type", "status")


class PayrollLineInline(admin.TabularInline):
    model = PayrollLine
    extra = 0
    can_delete = False
    fields = ("line_type", "description", "quantity", "rate", "percentage", "base_amount", "amount")
    readonly_fields = fields

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Payroll)
class PayrollAdmin(ReadOnlyAdmin):
    list_display = ("employee", "period", "status", "total_accrued", "total_adjustments", "total_paid", "amount_due")
    list_filter = ("status", "period")
    inlines = [PayrollLineInline]


@admin.register(PayrollPayment)
class PayrollPaymentAdmin(ReadOnlyAdmin):
    list_display = ("payroll", "amount", "payment_date", "payment_method", "status")
    list_filter = ("status",)


@admin.register(PayrollAdjustment)
class PayrollAdjustmentAdmin(ReadOnlyAdmin):
    list_display = ("payroll", "kind", "amount", "status")


@admin.register(PayrollAuditLog)
class PayrollAuditLogAdmin(ReadOnlyAdmin):
    list_display = ("created_at", "actor", "action", "entity_type", "entity_id")
    list_filter = ("action", "entity_type")

    def get_urls(self):
        from .admin_views import purge_view

        # Обслуживание базы данных → Очистка данных (только суперпользователь —
        # проверка в самом представлении).
        return [
            path("maintenance/purge/", self.admin_site.admin_view(lambda request: purge_view(request, self.admin_site)),
                 name="accounting_maintenance_purge"),
            *super().get_urls(),
        ]


@admin.register(CoursePayrollSettings)
class CoursePayrollSettingsAdmin(ReadOnlyAdmin):
    list_display = ("course", "price_per_student", "required_lessons", "count_lessons_from", "is_active")


@admin.register(CourseCycle)
class CourseCycleAdmin(ReadOnlyAdmin):
    list_display = ("group", "subject", "course", "number", "status", "lessons_done", "required_lessons",
                    "completed_on", "student_count", "course_price", "per_subject")
    list_filter = ("status", "course", "subject", "per_subject")
    exclude = ("student_ids",)


@admin.register(CycleAccrual)
class CycleAccrualAdmin(ReadOnlyAdmin):
    list_display = ("cycle", "employee", "payroll", "student_count", "course_price", "percentage", "amount")


@admin.register(CoursePriceVersion)
class CoursePriceVersionAdmin(ReadOnlyAdmin):
    list_display = ("course", "price_per_student", "effective_from", "effective_to", "created_by", "is_migrated")
    list_filter = ("course", "is_migrated")


@admin.register(CycleLesson)
class CycleLessonAdmin(ReadOnlyAdmin):
    list_display = ("cycle", "position", "lesson_date", "lesson_ref", "teacher", "is_live", "backfilled")
    list_filter = ("is_live", "backfilled")
