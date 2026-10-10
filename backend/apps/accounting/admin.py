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
