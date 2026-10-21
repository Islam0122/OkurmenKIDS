"""Сериализаторы оплаты обучения: только представление и валидация ввода,
бизнес-правила — в сервисах. Суммы — строками (Decimal без потерь)."""
from __future__ import annotations

from decimal import Decimal

from rest_framework import serializers

from apps.academy.models import Course, Student
from apps.accounting.models import StudentPayment
from apps.users.models import Subject, User

from .models import (
    BillingContactLog,
    BillingNotification,
    BillingPlan,
    BillingPlanVersion,
    BillingTask,
    BillingTermsChange,
    CreditLedgerEntry,
    DiscountType,
    Invoice,
    InvoiceAdjustment,
    LessonConsumption,
    LessonPackage,
    PaymentAllocation,
    Reservation,
    StudentBillingProfile,
)
from .services.ledger import credit_balance

MONEY = {"max_digits": 14, "decimal_places": 2}


def _name(user) -> str | None:
    return (user.get_full_name() or user.username) if user else None


# ---------------------------------------------------------------------------
# Тарифы
# ---------------------------------------------------------------------------

class PlanVersionSerializer(serializers.ModelSerializer):
    created_by_name = serializers.SerializerMethodField()

    class Meta:
        model = BillingPlanVersion
        fields = ("id", "lessons_per_package", "package_price", "currency", "effective_from", "effective_to", "reason",
                  "created_by_name", "created_at")

    def get_created_by_name(self, obj) -> str | None:
        return _name(obj.created_by)


class PlanSerializer(serializers.ModelSerializer):
    subject_name = serializers.CharField(source="subject.name", read_only=True, default=None)
    course_name = serializers.CharField(source="course.name", read_only=True, default=None)
    current = serializers.SerializerMethodField()
    versions = PlanVersionSerializer(many=True, read_only=True)

    class Meta:
        model = BillingPlan
        fields = ("id", "name", "subject", "subject_name", "course", "course_name", "payment_due_days",
                  "warn_before_end_lessons", "early_invoice_enabled", "early_invoice_after_lessons", "absence_policy",
                  "is_active", "current", "versions", "created_at")

    def get_current(self, obj) -> dict | None:
        from django.utils import timezone

        from .services.pricing import plan_version_on

        try:
            version = plan_version_on(obj, timezone.localdate())
        except Exception:  # noqa: BLE001
            return None
        return {"lessons_per_package": version.lessons_per_package, "package_price": str(version.package_price),
                "effective_from": version.effective_from.isoformat()}


class PlanCreateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=150)
    subject = serializers.PrimaryKeyRelatedField(queryset=Subject.objects.all(), required=False, allow_null=True)
    course = serializers.PrimaryKeyRelatedField(queryset=Course.objects.all(), required=False, allow_null=True)
    lessons_per_package = serializers.IntegerField(min_value=1, max_value=500)
    package_price = serializers.DecimalField(**MONEY, min_value=Decimal("0.01"))
    effective_from = serializers.DateField()
    reason = serializers.CharField(required=False, default="Новый тариф")
    payment_due_days = serializers.IntegerField(min_value=0, max_value=90, required=False, default=5)
    warn_before_end_lessons = serializers.IntegerField(min_value=0, max_value=100, required=False, default=3)
    early_invoice_enabled = serializers.BooleanField(required=False, default=False)
    early_invoice_after_lessons = serializers.IntegerField(min_value=1, required=False, allow_null=True)
    absence_policy = serializers.ChoiceField(choices=BillingPlan._meta.get_field("absence_policy").choices,
                                             required=False, default="ALL_HELD")


class PlanUpdateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=150, required=False)
    payment_due_days = serializers.IntegerField(min_value=0, max_value=90, required=False)
    warn_before_end_lessons = serializers.IntegerField(min_value=0, max_value=100, required=False)
    early_invoice_enabled = serializers.BooleanField(required=False)
    early_invoice_after_lessons = serializers.IntegerField(min_value=1, required=False, allow_null=True)
    absence_policy = serializers.ChoiceField(choices=BillingPlan._meta.get_field("absence_policy").choices,
                                             required=False)
    is_active = serializers.BooleanField(required=False)


class PlanVersionCreateSerializer(serializers.Serializer):
    lessons_per_package = serializers.IntegerField(min_value=1, max_value=500)
    package_price = serializers.DecimalField(**MONEY, min_value=Decimal("0.01"))
    effective_from = serializers.DateField()
    reason = serializers.CharField()


# ---------------------------------------------------------------------------
# Профили
# ---------------------------------------------------------------------------

class TermsInputMixin(serializers.Serializer):
    custom_price = serializers.DecimalField(**MONEY, required=False, allow_null=True, min_value=Decimal("0.01"))
    discount_type = serializers.ChoiceField(choices=DiscountType.choices, required=False, default=DiscountType.NONE)
    discount_value = serializers.DecimalField(**MONEY, required=False, default=Decimal("0"), min_value=Decimal("0"))

    def validate(self, attrs):
        if attrs.get("discount_type") == DiscountType.PERCENT and attrs.get("discount_value", 0) > 100:
            raise serializers.ValidationError({"discount_value": "Скидка не может быть больше 100 %."})
        return attrs


class ProfileCreateSerializer(TermsInputMixin):
    student = serializers.PrimaryKeyRelatedField(queryset=Student.objects.all())
    plan = serializers.PrimaryKeyRelatedField(queryset=BillingPlan.objects.filter(is_active=True))
    subject = serializers.PrimaryKeyRelatedField(queryset=Subject.objects.all(), required=False, allow_null=True)
    start_date = serializers.DateField(required=False, allow_null=True)
    parent_name = serializers.CharField(max_length=150, required=False, allow_blank=True, default="")
    parent_phone = serializers.CharField(max_length=30, required=False, allow_blank=True, default="")
    discount_reason = serializers.CharField(required=False, allow_blank=True, default="")
    special_terms = serializers.CharField(required=False, allow_blank=True, default="")
    responsible_accountant = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.filter(role=User.Role.ACCOUNTANT, is_active=True), required=False, allow_null=True,
    )
    reservation_amount = serializers.DecimalField(**MONEY, required=False, allow_null=True, min_value=Decimal("0.01"))
    reserved_until = serializers.DateField(required=False, allow_null=True)
    reservation_comment = serializers.CharField(required=False, allow_blank=True, default="")


class TermsChangeInputSerializer(TermsInputMixin):
    reason = serializers.CharField(required=False, allow_blank=True, default="")


class ProfileUpdateSerializer(serializers.Serializer):
    parent_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    parent_phone = serializers.CharField(max_length=30, required=False, allow_blank=True)
    special_terms = serializers.CharField(required=False, allow_blank=True)
    responsible_accountant = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.filter(role=User.Role.ACCOUNTANT, is_active=True), required=False, allow_null=True,
    )


class BillingReasonSerializer(serializers.Serializer):
    reason = serializers.CharField()


class StopSerializer(serializers.Serializer):
    reason = serializers.CharField()
    on_date = serializers.DateField(required=False, allow_null=True)


class TermsChangeSerializer(serializers.ModelSerializer):
    requested_by_name = serializers.SerializerMethodField()
    decided_by_name = serializers.SerializerMethodField()
    student_name = serializers.CharField(source="profile.student.__str__", read_only=True)

    class Meta:
        model = BillingTermsChange
        fields = ("id", "profile", "student_name", "custom_price", "discount_type", "discount_value", "reason",
                  "previous_terms", "status", "requested_by_name", "requested_at", "decided_by_name", "decided_at",
                  "decision_comment")

    def get_requested_by_name(self, obj) -> str | None:
        return _name(obj.requested_by)

    def get_decided_by_name(self, obj) -> str | None:
        return _name(obj.decided_by)


class DecisionSerializer(serializers.Serializer):
    approve = serializers.BooleanField()
    comment = serializers.CharField(required=False, allow_blank=True, default="")


class PackageSerializer(serializers.ModelSerializer):
    lessons_remaining = serializers.IntegerField(read_only=True)
    invoice = serializers.SerializerMethodField()

    class Meta:
        model = LessonPackage
        fields = ("id", "profile", "number", "status", "lessons_total", "lessons_used", "lessons_remaining",
                  "base_price", "custom_price", "discount_type", "discount_value", "discount_amount", "final_price",
                  "started_on", "completed_on", "invoice", "created_at")

    def get_invoice(self, obj) -> dict | None:
        inv = next((i for i in obj.invoices.all() if i.status != Invoice.Status.VOID), None)
        if inv is None:
            return None
        return {"id": inv.pk, "number": inv.number, "status": inv.status, "balance": str(inv.balance)}


class ProfileSerializer(serializers.ModelSerializer):
    """Профиль со статусом оплаты — то, что нужно менеджеру для работы."""

    student_name = serializers.CharField(source="student.__str__", read_only=True)
    group = serializers.IntegerField(source="student.group_id", read_only=True)
    group_name = serializers.CharField(source="student.group.name", read_only=True, default=None)
    subject_name = serializers.CharField(source="subject.name", read_only=True, default=None)
    plan_name = serializers.CharField(source="plan.name", read_only=True)
    responsible_accountant_name = serializers.SerializerMethodField()
    discount_assigned_by_name = serializers.SerializerMethodField()
    discount_approved_by_name = serializers.SerializerMethodField()
    payment_status = serializers.SerializerMethodField()
    current_package = serializers.SerializerMethodField()
    pending_terms = serializers.SerializerMethodField()

    class Meta:
        model = StudentBillingProfile
        fields = ("id", "student", "student_name", "group", "group_name", "subject", "subject_name", "plan",
                  "plan_name", "status", "start_date", "parent_name", "parent_phone", "custom_price", "discount_type",
                  "discount_value", "discount_reason", "discount_assigned_by_name", "discount_approved_by_name",
                  "special_terms", "responsible_accountant", "responsible_accountant_name", "stopped_on",
                  "stop_reason", "payment_status", "current_package", "pending_terms", "created_at")

    def get_responsible_accountant_name(self, obj) -> str | None:
        return _name(obj.responsible_accountant)

    def get_discount_assigned_by_name(self, obj) -> str | None:
        return _name(obj.discount_assigned_by)

    def get_discount_approved_by_name(self, obj) -> str | None:
        return _name(obj.discount_approved_by)

    def get_payment_status(self, obj) -> dict:
        unpaid = [i for i in obj.invoices.all() if i.status in Invoice.UNPAID_STATUSES]
        debt = sum((i.balance for i in unpaid), Decimal("0"))
        overdue = any(i.status == Invoice.Status.OVERDUE for i in unpaid)
        state = "overdue" if overdue else ("awaiting" if unpaid else "paid")
        if any(i.status == Invoice.Status.DRAFT for i in obj.invoices.all()):
            state = "draft" if not unpaid else state
        return {"state": state, "debt": str(debt), "unpaid_invoices": len(unpaid),
                "credit": str(credit_balance(obj.pk)),
                "next_due": min((i.due_date for i in unpaid), default=None)}

    def get_current_package(self, obj) -> dict | None:
        package = next((p for p in obj.packages.all() if p.status == LessonPackage.Status.ACTIVE), None)
        if package is None:
            return None
        return {"id": package.pk, "number": package.number, "lessons_used": package.lessons_used,
                "lessons_total": package.lessons_total, "lessons_remaining": package.lessons_remaining}

    def get_pending_terms(self, obj) -> dict | None:
        change = next((c for c in obj.terms_changes.all() if c.status == BillingTermsChange.Status.PENDING), None)
        return None if change is None else TermsChangeSerializer(change).data


class ConsumptionSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source="student.__str__", read_only=True)
    package_number = serializers.IntegerField(source="package.number", read_only=True)

    class Meta:
        model = LessonConsumption
        fields = ("id", "profile", "student", "student_name", "package", "package_number", "lesson", "lesson_ref",
                  "lesson_date", "group", "kind", "status", "reversal_of", "reason", "created_at")


# ---------------------------------------------------------------------------
# Начисления и деньги
# ---------------------------------------------------------------------------

class InvoiceSerializer(serializers.ModelSerializer):
    balance = serializers.DecimalField(**MONEY, read_only=True)
    student = serializers.IntegerField(source="profile.student_id", read_only=True)
    student_name = serializers.CharField(source="profile.student.__str__", read_only=True)
    group_name = serializers.CharField(source="profile.student.group.name", read_only=True, default=None)
    subject_name = serializers.CharField(source="profile.subject.name", read_only=True, default=None)
    package_number = serializers.IntegerField(source="package.number", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = Invoice
        fields = ("id", "number", "profile", "student", "student_name", "group_name", "subject_name", "package",
                  "package_number", "amount", "amount_paid", "amount_adjusted", "balance", "currency", "status",
                  "status_display", "issue_date", "due_date", "snapshot", "paid_at", "void_reason", "created_at")


class AllocationSerializer(serializers.ModelSerializer):
    invoice_number = serializers.CharField(source="invoice.number", read_only=True)

    class Meta:
        model = PaymentAllocation
        fields = ("id", "payment", "invoice", "invoice_number", "profile", "amount", "source", "status", "created_at",
                  "reversed_at", "reverse_reason")


class AdjustmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = InvoiceAdjustment
        fields = ("id", "invoice", "amount", "reason", "status", "created_at", "void_reason")


class InvoiceDetailSerializer(InvoiceSerializer):
    allocations = AllocationSerializer(many=True, read_only=True)
    adjustments = AdjustmentSerializer(many=True, read_only=True)

    class Meta(InvoiceSerializer.Meta):
        fields = InvoiceSerializer.Meta.fields + ("allocations", "adjustments")


class AdjustmentCreateSerializer(serializers.Serializer):
    amount = serializers.DecimalField(**MONEY, min_value=Decimal("0.01"))
    reason = serializers.CharField()


class BillingPaymentSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source="student.__str__", read_only=True)
    unallocated = serializers.SerializerMethodField()
    allocations = AllocationSerializer(source="billing_allocations", many=True, read_only=True)
    created_by_name = serializers.SerializerMethodField()

    class Meta:
        model = StudentPayment
        fields = ("id", "billing_profile", "student", "student_name", "kind", "purpose", "amount", "currency",
                  "received_date", "method", "reference", "comment", "status", "void_reason", "refund_of",
                  "unallocated", "allocations", "created_by_name", "created_at")

    def get_unallocated(self, obj) -> str | None:
        from .services.ledger import payment_unallocated

        if obj.kind != StudentPayment.Kind.PAYMENT:
            return None
        return str(payment_unallocated(obj.pk))

    def get_created_by_name(self, obj) -> str | None:
        return _name(obj.created_by)


class AllocationItemSerializer(serializers.Serializer):
    invoice = serializers.PrimaryKeyRelatedField(queryset=Invoice.objects.all())
    amount = serializers.DecimalField(**MONEY, min_value=Decimal("0.01"))


class PaymentCreateSerializer(serializers.Serializer):
    profile = serializers.PrimaryKeyRelatedField(queryset=StudentBillingProfile.objects.all())
    amount = serializers.DecimalField(**MONEY, min_value=Decimal("0.01"))
    received_date = serializers.DateField()
    method = serializers.ChoiceField(choices=StudentPayment.Method.choices, default=StudentPayment.Method.CASH)
    reference = serializers.CharField(max_length=100, required=False, allow_blank=True, default="")
    comment = serializers.CharField(required=False, allow_blank=True, default="")
    prepay_packages = serializers.IntegerField(min_value=0, max_value=24, required=False, default=0)
    auto_allocate = serializers.BooleanField(required=False, default=True)
    allocations = AllocationItemSerializer(many=True, required=False)
    idempotency_key = serializers.CharField(max_length=64, required=False, allow_blank=True)


class AllocateSerializer(serializers.Serializer):
    allocations = AllocationItemSerializer(many=True)


class RefundSerializer(serializers.Serializer):
    amount = serializers.DecimalField(**MONEY, min_value=Decimal("0.01"))
    reason = serializers.CharField()
    refund_date = serializers.DateField(required=False, allow_null=True)
    idempotency_key = serializers.CharField(max_length=64, required=False, allow_blank=True)


class CreditEntrySerializer(serializers.ModelSerializer):
    kind_display = serializers.CharField(source="get_kind_display", read_only=True)

    class Meta:
        model = CreditLedgerEntry
        fields = ("id", "profile", "kind", "kind_display", "amount", "payment", "allocation", "reservation", "comment",
                  "created_at")


# ---------------------------------------------------------------------------
# Бронь, задачи, контакты, уведомления
# ---------------------------------------------------------------------------

class ReservationSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source="profile.student.__str__", read_only=True)
    paid_amount = serializers.DecimalField(source="payment.amount", **MONEY, read_only=True, default=None)

    class Meta:
        model = Reservation
        fields = ("id", "profile", "student_name", "group", "expected_amount", "reserved_until", "status", "payment",
                  "paid_amount", "comment", "refunded_amount", "retained_amount", "cancel_reason", "cancelled_at",
                  "created_at")


class ReservationCreateSerializer(serializers.Serializer):
    profile = serializers.PrimaryKeyRelatedField(queryset=StudentBillingProfile.objects.all())
    expected_amount = serializers.DecimalField(**MONEY, min_value=Decimal("0.01"))
    reserved_until = serializers.DateField(required=False, allow_null=True)
    comment = serializers.CharField(required=False, allow_blank=True, default="")


class ReservationPaySerializer(serializers.Serializer):
    amount = serializers.DecimalField(**MONEY, min_value=Decimal("0.01"))
    received_date = serializers.DateField()
    method = serializers.ChoiceField(choices=StudentPayment.Method.choices, default=StudentPayment.Method.CASH)
    reference = serializers.CharField(max_length=100, required=False, allow_blank=True, default="")
    idempotency_key = serializers.CharField(max_length=64, required=False, allow_blank=True)


class ReservationCancelSerializer(serializers.Serializer):
    reason = serializers.CharField()
    refund_amount = serializers.DecimalField(**MONEY, required=False, default=Decimal("0"), min_value=Decimal("0"))
    retain_amount = serializers.DecimalField(**MONEY, required=False, default=Decimal("0"), min_value=Decimal("0"))
    refund_date = serializers.DateField(required=False, allow_null=True)


class TaskSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source="profile.student.__str__", read_only=True)
    invoice_number = serializers.CharField(source="invoice.number", read_only=True)
    balance = serializers.DecimalField(source="invoice.balance", **MONEY, read_only=True)
    assignee_name = serializers.SerializerMethodField()

    class Meta:
        model = BillingTask
        fields = ("id", "kind", "status", "profile", "student_name", "invoice", "invoice_number", "balance", "assignee",
                  "assignee_name", "promised_date", "next_contact_date", "last_contact_at", "close_reason",
                  "created_at", "closed_at")

    def get_assignee_name(self, obj) -> str | None:
        return _name(obj.assignee)


class ContactSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source="student.__str__", read_only=True)
    staff_name = serializers.SerializerMethodField()
    invoice_number = serializers.CharField(source="invoice.number", read_only=True, default=None)
    channel_display = serializers.CharField(source="get_channel_display", read_only=True)
    result_display = serializers.CharField(source="get_result_display", read_only=True)

    class Meta:
        model = BillingContactLog
        fields = ("id", "profile", "student", "student_name", "invoice", "invoice_number", "task", "staff",
                  "staff_name", "contacted_at", "channel", "channel_display", "result", "result_display", "comment",
                  "promised_payment_date", "next_contact_date", "created_at")

    def get_staff_name(self, obj) -> str | None:
        return _name(obj.staff)


class ContactCreateSerializer(serializers.Serializer):
    profile = serializers.PrimaryKeyRelatedField(queryset=StudentBillingProfile.objects.all())
    invoice = serializers.PrimaryKeyRelatedField(queryset=Invoice.objects.all(), required=False, allow_null=True)
    channel = serializers.ChoiceField(choices=BillingContactLog.Channel.choices)
    result = serializers.ChoiceField(choices=BillingContactLog.Result.choices)
    comment = serializers.CharField(required=False, allow_blank=True, default="")
    contacted_at = serializers.DateTimeField(required=False, allow_null=True)
    promised_payment_date = serializers.DateField(required=False, allow_null=True)
    next_contact_date = serializers.DateField(required=False, allow_null=True)


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = BillingNotification
        fields = ("id", "kind", "title", "message", "profile", "invoice", "status", "read_at", "created_at")


class ReverseConsumptionSerializer(BillingReasonSerializer):
    pass
