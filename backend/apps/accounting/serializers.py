from __future__ import annotations

from decimal import Decimal

from rest_framework import serializers

from apps.academy.models import Course, Group, Student
from apps.users.models import User

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
from .services.report_service import period_label


def _name(user) -> str:
    if user is None:
        return ""
    return user.get_full_name() or user.username


class UserRefSerializer(serializers.ModelSerializer):
    full_name = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ("id", "full_name", "role")

    def get_full_name(self, obj) -> str:
        return _name(obj)


# ---------------------------------------------------------------------------
# Платежи студентов
# ---------------------------------------------------------------------------

class StudentPaymentSerializer(serializers.ModelSerializer):
    student_name = serializers.SerializerMethodField()
    group_name = serializers.CharField(source="group.name", read_only=True)
    course_name = serializers.CharField(source="course.name", read_only=True)
    kind_display = serializers.CharField(source="get_kind_display", read_only=True)
    method_display = serializers.CharField(source="get_method_display", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    created_by_name = serializers.SerializerMethodField()
    refunded_amount = serializers.SerializerMethodField()

    class Meta:
        model = StudentPayment
        fields = (
            "id", "student", "student_name", "group", "group_name", "course", "course_name", "kind", "kind_display",
            "amount", "currency", "received_date", "service_start", "service_end", "refund_of", "refunded_amount",
            "method", "method_display", "reference", "comment", "status", "status_display", "void_reason",
            "created_by_name", "created_at", "voided_at",
        )

    def get_student_name(self, obj) -> str:
        return str(obj.student)

    def get_created_by_name(self, obj) -> str:
        return _name(obj.created_by)

    def get_refunded_amount(self, obj) -> str | None:
        if obj.kind != StudentPayment.Kind.PAYMENT:
            return None
        return str(sum((r.amount for r in obj.refunds.all() if r.status == StudentPayment.Status.CONFIRMED), Decimal("0")))


class StudentPaymentCreateSerializer(serializers.Serializer):
    student = serializers.PrimaryKeyRelatedField(queryset=Student.objects.all())
    group = serializers.PrimaryKeyRelatedField(queryset=Group.objects.all(), required=False, allow_null=True)
    amount = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=Decimal("0.01"))
    received_date = serializers.DateField()
    service_start = serializers.DateField(required=False, allow_null=True)
    service_end = serializers.DateField(required=False, allow_null=True)
    method = serializers.ChoiceField(choices=StudentPayment.Method.choices, default=StudentPayment.Method.CASH)
    reference = serializers.CharField(required=False, allow_blank=True, max_length=100, default="")
    comment = serializers.CharField(required=False, allow_blank=True, default="")
    refund_of = serializers.PrimaryKeyRelatedField(
        queryset=StudentPayment.objects.all(), required=False, allow_null=True,
    )
    idempotency_key = serializers.CharField(required=False, allow_blank=True, max_length=64)


class ReasonSerializer(serializers.Serializer):
    reason = serializers.CharField()


# ---------------------------------------------------------------------------
# Профили и правила
# ---------------------------------------------------------------------------

class SalaryRuleSerializer(serializers.ModelSerializer):
    rule_type_display = serializers.CharField(source="get_rule_type_display", read_only=True)
    calculation_method_display = serializers.CharField(source="get_calculation_method_display", read_only=True)
    revenue_basis_display = serializers.CharField(source="get_revenue_basis_display", read_only=True)
    refund_policy_display = serializers.CharField(source="get_refund_policy_display", read_only=True)
    program_name = serializers.CharField(source="program.name", read_only=True, default=None)
    group_name = serializers.CharField(source="group.name", read_only=True, default=None)
    employee = serializers.IntegerField(source="employee_profile.employee_id", read_only=True)
    employee_name = serializers.SerializerMethodField()
    next_version = serializers.SerializerMethodField()

    class Meta:
        model = SalaryRule
        fields = (
            "id", "employee_profile", "employee", "employee_name", "rule_type", "rule_type_display", "amount",
            "percentage", "program", "program_name", "group", "group_name", "calculation_method",
            "calculation_method_display", "first_half_share", "revenue_basis", "revenue_basis_display",
            "refund_policy", "refund_policy_display", "description", "effective_from", "effective_to", "is_active",
            "previous_version", "next_version", "created_at",
        )
        read_only_fields = ("is_active", "previous_version", "created_at")

    def get_employee_name(self, obj) -> str:
        return _name(obj.employee_profile.employee)

    def get_next_version(self, obj) -> int | None:
        nxt = getattr(obj, "next_version", None)
        return nxt.pk if nxt else None


class SalaryRuleCreateSerializer(serializers.ModelSerializer):
    calculation_method = serializers.ChoiceField(choices=SalaryRule.Method.choices, required=False, allow_blank=True)

    class Meta:
        model = SalaryRule
        fields = (
            "employee_profile", "rule_type", "amount", "percentage", "program", "group", "calculation_method",
            "first_half_share", "revenue_basis", "refund_policy", "description", "effective_from", "effective_to",
        )


class SalaryRuleVersionSerializer(serializers.Serializer):
    effective_from = serializers.DateField()
    amount = serializers.DecimalField(max_digits=14, decimal_places=2, required=False, allow_null=True)
    percentage = serializers.DecimalField(max_digits=5, decimal_places=2, required=False, allow_null=True)
    calculation_method = serializers.ChoiceField(choices=SalaryRule.Method.choices, required=False)
    first_half_share = serializers.DecimalField(max_digits=5, decimal_places=2, required=False)
    revenue_basis = serializers.ChoiceField(choices=SalaryRule.RevenueBasis.choices, required=False)
    refund_policy = serializers.ChoiceField(choices=SalaryRule.RefundPolicy.choices, required=False)
    description = serializers.CharField(required=False, allow_blank=True)


class SalaryRuleDeactivateSerializer(serializers.Serializer):
    effective_to = serializers.DateField()
    reason = serializers.CharField(required=False, allow_blank=True, default="")


class EmployeeSalaryProfileSerializer(serializers.ModelSerializer):
    employee_name = serializers.SerializerMethodField()
    employee_role = serializers.CharField(source="employee.role", read_only=True)
    salary_type_display = serializers.CharField(source="get_salary_type_display", read_only=True)
    display_position = serializers.CharField(read_only=True)
    rules = SalaryRuleSerializer(many=True, read_only=True)

    class Meta:
        model = EmployeeSalaryProfile
        fields = (
            "id", "employee", "employee_name", "employee_role", "position", "display_position", "salary_type",
            "salary_type_display", "currency", "is_active", "effective_from", "effective_to", "rules",
            "created_at", "updated_at",
        )
        read_only_fields = ("currency", "created_at", "updated_at")

    def get_employee_name(self, obj) -> str:
        return _name(obj.employee)

    def validate_employee(self, value):
        if self.instance is not None and value != self.instance.employee:
            raise serializers.ValidationError("Сотрудника профиля изменить нельзя.")
        return value


# ---------------------------------------------------------------------------
# Периоды и расчёты
# ---------------------------------------------------------------------------

class PayrollPeriodSerializer(serializers.ModelSerializer):
    period_type_display = serializers.CharField(source="get_period_type_display", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    label = serializers.SerializerMethodField()

    class Meta:
        model = PayrollPeriod
        fields = (
            "id", "year", "month", "period_type", "period_type_display", "start_date", "end_date", "status",
            "status_display", "label", "created_at", "approved_at",
        )
        read_only_fields = ("start_date", "end_date", "status", "created_at", "approved_at")

    def get_label(self, obj) -> str:
        return period_label(obj)


class PayrollPeriodCreateSerializer(serializers.Serializer):
    year = serializers.IntegerField(min_value=2000, max_value=2100)
    month = serializers.IntegerField(min_value=1, max_value=12)
    period_type = serializers.ChoiceField(choices=PayrollPeriod.PeriodType.choices)


class PayrollLineSerializer(serializers.ModelSerializer):
    line_type_display = serializers.CharField(source="get_line_type_display", read_only=True)
    metadata = serializers.SerializerMethodField()

    class Meta:
        model = PayrollLine
        fields = (
            "id", "line_type", "line_type_display", "description", "source_type", "source_id", "salary_rule",
            "quantity", "rate", "percentage", "base_amount", "amount", "metadata",
        )

    def get_metadata(self, obj) -> dict:
        """Активные студенты — только агрегатом (число и студенто-дни):
        поимённый список студентов из API бухгалтерии не отдаётся."""
        return {k: v for k, v in obj.metadata.items() if k != "students"}


class PayrollPaymentSerializer(serializers.ModelSerializer):
    payment_method_display = serializers.CharField(source="get_payment_method_display", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    created_by_name = serializers.SerializerMethodField()

    class Meta:
        model = PayrollPayment
        fields = (
            "id", "payroll", "amount", "payment_date", "payment_method", "payment_method_display", "reference",
            "comment", "is_advance", "status", "status_display", "void_reason", "created_by_name", "created_at",
            "voided_at",
        )

    def get_created_by_name(self, obj) -> str:
        return _name(obj.created_by)


class PayrollPaymentCreateSerializer(serializers.Serializer):
    amount = serializers.DecimalField(max_digits=14, decimal_places=2)
    payment_date = serializers.DateField()
    payment_method = serializers.ChoiceField(choices=PayrollPayment.Method.choices, default=PayrollPayment.Method.BANK)
    reference = serializers.CharField(required=False, allow_blank=True, max_length=100, default="")
    comment = serializers.CharField(required=False, allow_blank=True, default="")
    is_advance = serializers.BooleanField(required=False, default=False)
    idempotency_key = serializers.CharField(required=False, allow_blank=True, max_length=64)


class PayrollAdjustmentSerializer(serializers.ModelSerializer):
    kind_display = serializers.CharField(source="get_kind_display", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    created_by_name = serializers.SerializerMethodField()
    decided_by_name = serializers.SerializerMethodField()

    class Meta:
        model = PayrollAdjustment
        fields = (
            "id", "payroll", "kind", "kind_display", "amount", "reason", "status", "status_display",
            "created_by_name", "decided_by_name", "decided_at", "created_at",
        )

    def get_created_by_name(self, obj) -> str:
        return _name(obj.created_by)

    def get_decided_by_name(self, obj) -> str:
        return _name(obj.decided_by)


class PayrollAdjustmentCreateSerializer(serializers.Serializer):
    kind = serializers.ChoiceField(choices=PayrollAdjustment.Kind.choices)
    amount = serializers.DecimalField(max_digits=14, decimal_places=2)
    reason = serializers.CharField()


class AdjustmentDecisionSerializer(serializers.Serializer):
    approve = serializers.BooleanField()
    reason = serializers.CharField(required=False, allow_blank=True, default="")


class PayrollAuditLogSerializer(serializers.ModelSerializer):
    actor_name = serializers.SerializerMethodField()

    class Meta:
        model = PayrollAuditLog
        fields = (
            "id", "actor", "actor_name", "entity_type", "entity_id", "action", "old_values", "new_values", "reason",
            "payroll", "created_at",
        )

    def get_actor_name(self, obj) -> str:
        return _name(obj.actor) or "система"


class PayrollListSerializer(serializers.ModelSerializer):
    employee_name = serializers.SerializerMethodField()
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    salary_type_display = serializers.CharField(source="get_salary_type_display", read_only=True)
    period_label = serializers.SerializerMethodField()
    period_type = serializers.CharField(source="period.period_type", read_only=True)
    total = serializers.SerializerMethodField()
    has_errors = serializers.SerializerMethodField()

    class Meta:
        model = Payroll
        fields = (
            "id", "period", "period_label", "period_type", "employee", "employee_name", "position", "salary_type",
            "salary_type_display", "status", "status_display", "active_students", "total_accrued",
            "total_adjustments", "total", "total_paid", "amount_due", "warnings", "errors", "has_errors",
            "calculated_at", "approved_at",
        )

    def get_employee_name(self, obj) -> str:
        return _name(obj.employee)

    def get_period_label(self, obj) -> str:
        return period_label(obj.period)

    def get_total(self, obj) -> str:
        return str(obj.total_accrued + obj.total_adjustments)

    def get_has_errors(self, obj) -> bool:
        return bool(obj.errors)


class PayrollDetailSerializer(PayrollListSerializer):
    lines = PayrollLineSerializer(many=True, read_only=True)
    payments = PayrollPaymentSerializer(many=True, read_only=True)
    adjustments = PayrollAdjustmentSerializer(many=True, read_only=True)
    approved_by_name = serializers.SerializerMethodField()
    period_detail = PayrollPeriodSerializer(source="period", read_only=True)
    rules = serializers.SerializerMethodField()
    audit = serializers.SerializerMethodField()

    class Meta(PayrollListSerializer.Meta):
        fields = PayrollListSerializer.Meta.fields + (
            "lines", "payments", "adjustments", "approved_by_name", "period_detail", "rules", "audit",
            "return_reason",
        )

    def get_approved_by_name(self, obj) -> str:
        return _name(obj.approved_by)

    def get_rules(self, obj) -> list:
        ids = {line.salary_rule_id for line in obj.lines.all() if line.salary_rule_id}
        return SalaryRuleSerializer(SalaryRule.objects.filter(pk__in=ids).select_related(
            "program", "group", "employee_profile__employee"), many=True).data

    def get_audit(self, obj) -> list:
        if not self.context.get("include_audit", True):
            return []
        return PayrollAuditLogSerializer(obj.audit_entries.select_related("actor")[:200], many=True).data


class OwnPayrollSerializer(PayrollDetailSerializer):
    """Сотрудник видит свои строки и выплаты, но не журнал и не ошибки."""

    class Meta(PayrollDetailSerializer.Meta):
        fields = tuple(
            f for f in PayrollDetailSerializer.Meta.fields if f not in ("audit", "warnings", "errors", "has_errors")
        )


class CourseRefSerializer(serializers.ModelSerializer):
    class Meta:
        model = Course
        fields = ("id", "name")


class GroupRefSerializer(serializers.ModelSerializer):
    class Meta:
        model = Group
        fields = ("id", "name", "course", "status")
