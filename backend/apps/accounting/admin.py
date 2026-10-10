"""Django admin бухгалтерии — только просмотр.

Финансовые операции выполняются через API бухгалтерии (сервисный слой
с проверками, транзакциями и аудитом). Здесь администратор может только
посмотреть записи: ни добавить, ни изменить, ни удалить их в обход
сервисов нельзя — в том числе журнал аудита.
"""
from django.contrib import admin

from .models import (
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


@admin.register(StudentPayment)
class StudentPaymentAdmin(ReadOnlyAdmin):
    list_display = ("student", "group", "kind", "amount", "received_date", "status")
    list_filter = ("kind", "status", "method")
    search_fields = ("student__first_name", "student__last_name", "reference")


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
