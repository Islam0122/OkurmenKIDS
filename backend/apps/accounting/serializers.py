from __future__ import annotations

from decimal import Decimal

from rest_framework import serializers

from apps.academy.models import Course, Group, Student
from apps.users.models import Subject, User

from .models import (
    ALLOWED_SALARY_TYPES,
    CourseCycle,
    CoursePayrollSettings,
    CoursePriceVersion,
    CycleAccrual,
    DeductionRule,
    Department,
    EmployeeSalaryProfile,
    PayoutPlan,
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
    usage = serializers.SerializerMethodField()

    class Meta:
        model = SalaryRule
        fields = (
            "id", "employee_profile", "employee", "employee_name", "rule_type", "rule_type_display", "amount",
            "percentage", "program", "program_name", "group", "group_name", "calculation_method",
            "calculation_method_display", "first_half_share", "revenue_basis", "revenue_basis_display",
            "refund_policy", "refund_policy_display", "description", "effective_from", "effective_to", "is_active",
            "previous_version", "next_version", "usage", "created_at",
        )
        read_only_fields = ("is_active", "previous_version", "created_at")

    def get_usage(self, obj) -> dict:
        """Можно ли исправить правило на месте или только заменить с даты."""
        from .services.salary_rules import rule_usage

        usage = rule_usage(obj)
        usage["used_until"] = usage["used_until"].isoformat() if usage["used_until"] else None
        return usage

    def get_employee_name(self, obj) -> str:
        return _name(obj.employee_profile.employee)

    def get_next_version(self, obj) -> int | None:
        nxt = getattr(obj, "next_version", None)
        return nxt.pk if nxt else None


class SalaryRuleCreateSerializer(serializers.ModelSerializer):
    rule_type = serializers.ChoiceField(choices=[(t.value, t.label) for t in SalaryRule.ACTIVE_TYPES])
    calculation_method = serializers.ChoiceField(choices=SalaryRule.Method.choices, required=False, allow_blank=True)

    class Meta:
        model = SalaryRule
        fields = (
            "employee_profile", "rule_type", "amount", "percentage", "program", "group", "calculation_method",
            "first_half_share", "description", "effective_from", "effective_to",
        )


class SalaryRuleVersionSerializer(serializers.Serializer):
    effective_from = serializers.DateField()
    amount = serializers.DecimalField(max_digits=14, decimal_places=2, required=False, allow_null=True)
    percentage = serializers.DecimalField(max_digits=5, decimal_places=2, required=False, allow_null=True)
    calculation_method = serializers.ChoiceField(choices=SalaryRule.Method.choices, required=False)
    first_half_share = serializers.DecimalField(max_digits=5, decimal_places=2, required=False)
    description = serializers.CharField(required=False, allow_blank=True)


class _RuleBodySerializer(serializers.Serializer):
    rule_type = serializers.ChoiceField(choices=[(t.value, t.label) for t in SalaryRule.ACTIVE_TYPES], required=False)
    amount = serializers.DecimalField(max_digits=14, decimal_places=2, required=False, allow_null=True,
                                      min_value=Decimal("0"))
    percentage = serializers.DecimalField(max_digits=5, decimal_places=2, required=False, allow_null=True,
                                          min_value=Decimal("0"), max_value=Decimal("100"))
    program = serializers.PrimaryKeyRelatedField(queryset=Course.objects.all(), required=False, allow_null=True)
    group = serializers.PrimaryKeyRelatedField(queryset=Group.objects.all(), required=False, allow_null=True)
    description = serializers.CharField(required=False, allow_blank=True, max_length=255)
    effective_to = serializers.DateField(required=False, allow_null=True)
    reason = serializers.CharField()


class SalaryRuleCorrectSerializer(_RuleBodySerializer):
    """Исправление ошибочного правила (только пока не использовано в
    утверждённых начислениях)."""

    calculation_method = serializers.ChoiceField(choices=SalaryRule.Method.choices, required=False)
    effective_from = serializers.DateField(required=False)


class SalaryRuleReplaceSerializer(_RuleBodySerializer):
    """Замена правила с даты (для правил, уже попавших в утверждённые начисления)."""

    effective_from = serializers.DateField()


class SalaryRuleDeactivateSerializer(serializers.Serializer):
    effective_to = serializers.DateField()
    reason = serializers.CharField(required=False, allow_blank=True, default="")


class EmployeeSalaryProfileSerializer(serializers.ModelSerializer):
    employee_name = serializers.SerializerMethodField()
    employee_role = serializers.CharField(source="employee.role", read_only=True)
    salary_type_display = serializers.CharField(source="get_salary_type_display", read_only=True)
    display_position = serializers.CharField(read_only=True)
    effective_department = serializers.CharField(read_only=True)
    department_display = serializers.SerializerMethodField()
    rules = SalaryRuleSerializer(many=True, read_only=True)

    class Meta:
        model = EmployeeSalaryProfile
        fields = (
            "id", "employee", "employee_name", "employee_role", "position", "display_position", "salary_type",
            "salary_type_display", "department", "effective_department", "department_display", "currency",
            "is_active", "effective_from", "effective_to", "rules", "created_at", "updated_at",
        )
        read_only_fields = ("currency", "created_at", "updated_at")

    def get_employee_name(self, obj) -> str:
        return _name(obj.employee)

    def get_department_display(self, obj) -> str:
        from .models import Department

        return Department(obj.effective_department).label

    def validate_salary_type(self, value):
        if value not in ALLOWED_SALARY_TYPES:
            raise serializers.ValidationError("Допустимы только «Фиксированный оклад» и «Процент от стоимости курса».")
        return value

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
            "voided_at", "payout_plan_line",
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
    planned_payment_date = serializers.DateField(read_only=True)
    department_display = serializers.CharField(source="get_department_display", read_only=True)

    class Meta:
        model = Payroll
        fields = (
            "id", "period", "period_label", "period_type", "employee", "employee_name", "position", "salary_type",
            "salary_type_display", "department", "department_display", "status", "status_display",
            "active_students", "total_accrued", "total_adjustments", "total", "total_deductions", "total_paid",
            "amount_due",
            "planned_payment_date", "warnings", "errors", "has_errors", "calculated_at", "approved_at",
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
    open_cycles = serializers.SerializerMethodField()
    payments = PayrollPaymentSerializer(many=True, read_only=True)
    adjustments = PayrollAdjustmentSerializer(many=True, read_only=True)
    approved_by_name = serializers.SerializerMethodField()
    period_detail = PayrollPeriodSerializer(source="period", read_only=True)
    rules = serializers.SerializerMethodField()
    audit = serializers.SerializerMethodField()
    deductions = serializers.SerializerMethodField()

    class Meta(PayrollListSerializer.Meta):
        fields = PayrollListSerializer.Meta.fields + (
            "lines", "payments", "adjustments", "approved_by_name", "period_detail", "rules", "audit",
            "return_reason", "open_cycles", "deductions",
        )

    def get_deductions(self, obj) -> list:
        from .services.deductions import payroll_deductions

        return [{k: str(v) if isinstance(v, Decimal) else v for k, v in row.items()}
                for row in payroll_deductions(obj)]

    def get_open_cycles(self, obj) -> list:
        """Незавершённые циклы — отдельно: за них процент ещё не начисляется."""
        if obj.salary_type != "PERCENT":
            return []
        from .services.cycles import open_cycles_for

        return [
            {"id": c.pk, "group_name": c.group.name, "course_name": c.course.name, "number": c.number,
             "lessons_done": c.lessons_done, "required_lessons": c.required_lessons}
            for c in open_cycles_for(obj.employee)
        ]

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


class CoursePayrollSettingsSerializer(serializers.ModelSerializer):
    """`price_per_student` задаётся при создании (первая версия тарифа);
    дальше стоимость меняется только через `pricing/` — с датой и причиной."""

    course_name = serializers.CharField(source="course.name", read_only=True)
    course_count_lesson = serializers.IntegerField(source="course.count_lesson", read_only=True)
    student_count_rule_display = serializers.CharField(source="get_student_count_rule_display", read_only=True)
    counted_subjects = serializers.PrimaryKeyRelatedField(queryset=Subject.objects.all(), many=True, required=False)
    counted_subjects_names = serializers.SerializerMethodField()
    trainer_split_rule_display = serializers.CharField(source="get_trainer_split_rule_display", read_only=True)
    current_price = serializers.SerializerMethodField()
    price_effective_from = serializers.DateField(write_only=True, required=False)
    price_reason = serializers.CharField(write_only=True, required=False, allow_blank=True)

    class Meta:
        model = CoursePayrollSettings
        fields = (
            "id", "course", "course_name", "course_count_lesson", "price_per_student", "current_price",
            "price_effective_from", "price_reason", "required_lessons", "count_lessons_from", "student_count_rule",
            "student_count_rule_display", "counted_subjects", "counted_subjects_names", "trainer_split_rule",
            "trainer_split_rule_display", "is_active", "updated_at",
        )
        read_only_fields = ("updated_at",)

    def validate_course(self, value):
        if self.instance is not None and value != self.instance.course:
            raise serializers.ValidationError("Курс изменить нельзя.")
        return value

    def get_counted_subjects_names(self, obj) -> list[str]:
        return [s.name for s in obj.counted_subjects.all()] if obj.pk else []

    def get_current_price(self, obj) -> str | None:
        from django.utils import timezone

        from .services.pricing import price_on

        return str(price_on(obj, timezone.localdate())) if obj.pk else None


class CoursePriceVersionSerializer(serializers.ModelSerializer):
    course_name = serializers.CharField(source="course.name", read_only=True)
    created_by_name = serializers.SerializerMethodField()
    is_current = serializers.SerializerMethodField()

    class Meta:
        model = CoursePriceVersion
        fields = (
            "id", "course", "course_name", "price_per_student", "currency", "effective_from", "effective_to",
            "reason", "previous_version", "is_migrated", "is_current", "created_by", "created_by_name", "created_at",
        )

    def get_created_by_name(self, obj) -> str:
        return _name(obj.created_by) or "система (перенос данных)"

    def get_is_current(self, obj) -> bool:
        from django.utils import timezone

        today = timezone.localdate()
        return obj.effective_from <= today and (obj.effective_to is None or obj.effective_to >= today)


class CoursePriceCreateSerializer(serializers.Serializer):
    course = serializers.PrimaryKeyRelatedField(queryset=Course.objects.all())
    price_per_student = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=Decimal("0.01"))
    effective_from = serializers.DateField()
    reason = serializers.CharField()


class CycleAccrualSerializer(serializers.ModelSerializer):
    employee_name = serializers.SerializerMethodField()
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    group = serializers.IntegerField(source="cycle.group_id", read_only=True)
    group_name = serializers.CharField(source="cycle.group.name", read_only=True)
    course_name = serializers.CharField(source="cycle.course.name", read_only=True)
    cycle_number = serializers.IntegerField(source="cycle.number", read_only=True)
    subject_name = serializers.SerializerMethodField()
    planned_payment_date = serializers.DateField(read_only=True)
    reviewed_by_name = serializers.SerializerMethodField()

    class Meta:
        model = CycleAccrual
        fields = (
            "id", "cycle", "cycle_number", "group", "group_name", "course_name", "subject_name", "employee",
            "employee_name", "status", "status_display", "lessons", "lessons_taught", "share", "lessons_total", "completed_on", "student_count", "course_price",
            "percentage", "amount", "planned_payment_date", "payroll", "review_reasons", "note", "reviewed_by_name",
            "reviewed_at", "created_at",
        )

    def get_employee_name(self, obj) -> str:
        return _name(obj.employee)

    def get_subject_name(self, obj) -> str:
        return obj.cycle.subject.name if obj.cycle.subject_id else ""

    def get_reviewed_by_name(self, obj) -> str:
        return _name(obj.reviewed_by)


class CycleAccrualReviewSerializer(serializers.Serializer):
    confirm = serializers.BooleanField()
    reason = serializers.CharField()


class CourseCycleSerializer(serializers.ModelSerializer):
    """Цикл предмета группы — только агрегаты: число студентов, без списка
    студентов; тренеры — по фактически проведённым урокам цикла."""

    group_name = serializers.CharField(source="group.name", read_only=True)
    course_name = serializers.CharField(source="course.name", read_only=True)
    subject_name = serializers.SerializerMethodField()
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    base_amount = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)
    lessons_remaining = serializers.SerializerMethodField()
    progress_percent = serializers.SerializerMethodField()
    subject_plan_lessons = serializers.SerializerMethodField()
    trainers = serializers.SerializerMethodField()
    trainer_lessons = serializers.SerializerMethodField()
    accruals = serializers.SerializerMethodField()
    warnings = serializers.SerializerMethodField()
    lessons_linked = serializers.SerializerMethodField()

    class Meta:
        model = CourseCycle
        fields = (
            "id", "group", "group_name", "course", "course_name", "subject", "subject_name", "per_subject",
            "number", "status", "status_display", "required_lessons", "lessons_done", "lessons_remaining",
            "progress_percent", "lessons_total", "subject_plan_lessons", "start_date", "completed_on",
            "student_count", "course_price", "base_amount", "trainers", "trainer_lessons", "accruals", "warnings",
            "invalidated_reason", "lessons_linked",
        )

    def get_subject_name(self, obj) -> str:
        if not obj.per_subject:
            return "Все предметы (до предметного учёта)"
        return obj.subject.name if obj.subject_id else "Без предмета"

    def get_lessons_remaining(self, obj) -> int:
        return max(obj.required_lessons - obj.lessons_done, 0)

    def get_progress_percent(self, obj) -> int:
        return min(100, round(obj.lessons_done * 100 / obj.required_lessons)) if obj.required_lessons else 0

    def get_subject_plan_lessons(self, obj) -> int | None:
        """Уроков предмета в учебном плане курса (например, IT — 48 из 144)."""
        if not obj.subject_id:
            return None
        from apps.academy.models import CourseLessonPlan

        cache = self.context.setdefault("_plan_counts", {})
        key = (obj.course_id, obj.subject_id)
        if key not in cache:
            cache[key] = CourseLessonPlan.objects.filter(course_id=obj.course_id, subject_id=obj.subject_id).count()
        return cache[key] or None

    def _names(self, obj) -> dict[int, str]:
        from .services.cycles import teacher_names

        return teacher_names(int(k) for k in obj.teacher_lessons)

    def get_trainer_lessons(self, obj) -> list:
        names = self._names(obj)
        return [{"teacher": int(k), "name": names.get(int(k), "—"), "lessons": v}
                for k, v in sorted(obj.teacher_lessons.items(), key=lambda kv: -kv[1])]

    def get_trainers(self, obj) -> list:
        if not obj.per_subject:
            from datetime import date

            from .services.cycles import responsible_teacher_names

            return responsible_teacher_names(obj.group_id, obj.completed_on or date.today())
        if obj.teacher_lessons:
            return [t["name"] for t in self.get_trainer_lessons(obj)]
        from .services.cycles import current_subject_teacher_ids, teacher_names

        return sorted(teacher_names(current_subject_teacher_ids(obj.group_id, obj.subject_id)).values())

    def get_warnings(self, obj) -> list[str]:
        """Уроки тренеров без правила «Процент» в завершённом цикле — их доля
        не начислена (и не перераспределена другим)."""
        if obj.status != CourseCycle.Status.COMPLETED or not obj.per_subject:
            return []
        paid = {a.employee_id for a in obj.accruals.all()}
        from apps.users.models import Teacher

        teachers = Teacher.objects.filter(pk__in=[int(k) for k in obj.teacher_lessons]).select_related("user")
        return [f"{t}: {obj.teacher_lessons[str(t.pk)]} ур. без правила «Процент» — доля не начислена."
                for t in teachers if t.user_id not in paid]

    def get_lessons_linked(self, obj) -> int:
        return obj.cycle_lessons.filter(is_live=True).count()

    def get_accruals(self, obj) -> list:
        return [
            {"id": a.pk, "employee": a.employee_id, "employee_name": _name(a.employee),
             "percentage": str(a.percentage), "amount": str(a.amount), "lessons_taught": a.lessons_taught,
             "share": str(a.share), "status": a.status,
             "status_display": a.get_status_display(), "note": a.note, "payroll": a.payroll_id,
             "payroll_status": a.payroll.status if a.payroll else None,
             "payroll_status_display": a.payroll.get_status_display() if a.payroll else None,
             "period_label": period_label(a.payroll.period) if a.payroll else None,
             "adjustment": a.adjustment_id, "review_reasons": a.review_reasons,
             "planned_payment_date": a.planned_payment_date.isoformat()}
            for a in obj.accruals.select_related("employee", "payroll__period")
        ]


# ---------------------------------------------------------------------------
# План выплат
# ---------------------------------------------------------------------------

class PayoutPlanSerializer(serializers.ModelSerializer):
    """План с итогами (суммы считает сервис `payout_plans.totals`)."""

    created_by_name = serializers.SerializerMethodField()
    approved_by_name = serializers.SerializerMethodField()
    cancelled_by_name = serializers.SerializerMethodField()
    totals = serializers.SerializerMethodField()

    class Meta:
        model = PayoutPlan
        fields = (
            "id", "title", "year", "month", "payout_date", "prepared_amount", "comment", "state", "cancel_reason",
            "version", "created_by_name", "created_at", "updated_at", "approved_by_name", "approved_at",
            "cancelled_by_name", "cancelled_at", "totals",
        )

    def get_created_by_name(self, obj) -> str:
        return _name(obj.created_by)

    def get_approved_by_name(self, obj) -> str:
        return _name(obj.approved_by)

    def get_cancelled_by_name(self, obj) -> str:
        return _name(obj.cancelled_by)

    def get_totals(self, obj) -> dict:
        from .services.payout_plans import totals

        return {k: str(v) if isinstance(v, Decimal) else v for k, v in totals(obj).as_dict().items()}


class PayoutPlanLineInputSerializer(serializers.Serializer):
    payroll = serializers.PrimaryKeyRelatedField(queryset=Payroll.objects.all())
    amount = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=Decimal("0.01"), required=False,
                                      allow_null=True, help_text="Пусто — весь свободный остаток начисления.")
    comment = serializers.CharField(required=False, allow_blank=True, default="")


class PayoutPlanCreateSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=200)
    year = serializers.IntegerField(min_value=2000, max_value=2100)
    month = serializers.IntegerField(min_value=1, max_value=12)
    payout_date = serializers.DateField()
    prepared_amount = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=Decimal("0"), default=Decimal("0"))
    comment = serializers.CharField(required=False, allow_blank=True, default="")
    lines = PayoutPlanLineInputSerializer(many=True, required=False, default=list)


class PayoutPlanUpdateSerializer(serializers.Serializer):
    version = serializers.IntegerField(required=False)
    reason = serializers.CharField(required=False, allow_blank=True, default="")
    title = serializers.CharField(max_length=200, required=False)
    year = serializers.IntegerField(min_value=2000, max_value=2100, required=False)
    month = serializers.IntegerField(min_value=1, max_value=12, required=False)
    payout_date = serializers.DateField(required=False)
    prepared_amount = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=Decimal("0"), required=False)
    comment = serializers.CharField(required=False, allow_blank=True)


class PayoutPlanVersionSerializer(serializers.Serializer):
    version = serializers.IntegerField(required=False)


class PayoutPlanCancelSerializer(PayoutPlanVersionSerializer):
    reason = serializers.CharField()


class PayoutPlanAddLinesSerializer(PayoutPlanVersionSerializer):
    lines = PayoutPlanLineInputSerializer(many=True, allow_empty=False)


class PayoutPlanLineUpdateSerializer(PayoutPlanVersionSerializer):
    amount = serializers.DecimalField(max_digits=14, decimal_places=2, required=False)
    comment = serializers.CharField(required=False, allow_blank=True)
    remove = serializers.BooleanField(required=False, default=False)
    reason = serializers.CharField(required=False, allow_blank=True, default="")


class PayoutPlanPaySerializer(serializers.Serializer):
    amount = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=Decimal("0.01"))
    payment_date = serializers.DateField()
    payment_method = serializers.ChoiceField(choices=PayrollPayment.Method.choices, default=PayrollPayment.Method.BANK)
    reference = serializers.CharField(required=False, allow_blank=True, max_length=100, default="")
    comment = serializers.CharField(required=False, allow_blank=True, default="")
    idempotency_key = serializers.CharField(required=False, allow_blank=True, max_length=64)


# ---------------------------------------------------------------------------
# Налоги и удержания
# ---------------------------------------------------------------------------

class DeductionRuleSerializer(serializers.ModelSerializer):
    kind_display = serializers.CharField(source="get_kind_display", read_only=True)
    calc_type_display = serializers.CharField(source="get_calc_type_display", read_only=True)
    frequency_display = serializers.CharField(source="get_frequency_display", read_only=True)
    scope_display = serializers.CharField(source="get_scope_display", read_only=True)
    department_display = serializers.CharField(source="get_department_display", read_only=True)
    employee_name = serializers.SerializerMethodField()
    created_by_name = serializers.SerializerMethodField()
    next_version = serializers.SerializerMethodField()
    usage = serializers.SerializerMethodField()

    class Meta:
        model = DeductionRule
        fields = (
            "id", "series", "name", "kind", "kind_display", "calc_type", "calc_type_display", "amount", "frequency",
            "frequency_display", "scope", "scope_display", "employee", "employee_name", "department",
            "department_display", "effective_from", "effective_to", "is_active", "description", "previous_version",
            "next_version", "usage", "created_by_name", "created_at", "updated_at",
        )

    def get_employee_name(self, obj) -> str:
        return _name(obj.employee)

    def get_created_by_name(self, obj) -> str:
        return _name(obj.created_by)

    def get_next_version(self, obj) -> int | None:
        nxt = getattr(obj, "next_version", None)
        return nxt.pk if nxt else None

    def get_usage(self, obj) -> dict:
        from .services.deductions import usage

        data = usage(obj)
        data["used_until"] = data["used_until"].isoformat() if data["used_until"] else None
        return data


class DeductionRuleInputSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=100)
    kind = serializers.ChoiceField(choices=DeductionRule.Kind.choices, default=DeductionRule.Kind.OTHER)
    calc_type = serializers.ChoiceField(choices=DeductionRule.CalcType.choices, default=DeductionRule.CalcType.FIXED)
    amount = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=Decimal("0.01"))
    frequency = serializers.ChoiceField(choices=DeductionRule.Frequency.choices, default=DeductionRule.Frequency.MONTHLY)
    scope = serializers.ChoiceField(choices=DeductionRule.Scope.choices, default=DeductionRule.Scope.EMPLOYEE)
    employee = serializers.PrimaryKeyRelatedField(queryset=User.objects.all(), required=False, allow_null=True)
    department = serializers.ChoiceField(choices=Department.choices, required=False, allow_blank=True, default="")
    effective_from = serializers.DateField()
    effective_to = serializers.DateField(required=False, allow_null=True)
    is_active = serializers.BooleanField(required=False, default=True)
    description = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")


class DeductionRuleChangeSerializer(serializers.Serializer):
    """Изменение правила: только переданные поля + обязательная причина."""

    reason = serializers.CharField()
    name = serializers.CharField(max_length=100, required=False)
    kind = serializers.ChoiceField(choices=DeductionRule.Kind.choices, required=False)
    amount = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=Decimal("0.01"), required=False)
    frequency = serializers.ChoiceField(choices=DeductionRule.Frequency.choices, required=False)
    scope = serializers.ChoiceField(choices=DeductionRule.Scope.choices, required=False)
    employee = serializers.PrimaryKeyRelatedField(queryset=User.objects.all(), required=False, allow_null=True)
    department = serializers.ChoiceField(choices=Department.choices, required=False, allow_blank=True)
    effective_from = serializers.DateField(required=False)
    effective_to = serializers.DateField(required=False, allow_null=True)
    is_active = serializers.BooleanField(required=False)
    description = serializers.CharField(max_length=255, required=False, allow_blank=True)
