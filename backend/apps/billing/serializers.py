"""Сериализаторы оплаты обучения: только представление и валидация ввода,
бизнес-правила — в сервисах. Суммы — строками (Decimal без потерь)."""
from __future__ import annotations

from decimal import Decimal

from django.db import models
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
    PaymentMode,
    Receipt,
    Reservation,
    ReservationAllocation,
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
                  "duration_months", "payment_deadline_lessons", "allow_monthly", "allow_full_prepay", "currency",
                  "is_active", "current", "versions", "created_at")

    def get_current(self, obj) -> dict | None:
        from django.utils import timezone

        from .services.pricing import plan_version_on

        try:
            version = plan_version_on(obj, timezone.localdate())
        except Exception:  # noqa: BLE001
            return None
        return {"lessons_per_package": version.lessons_per_package, "package_price": str(version.package_price),
                "effective_from": version.effective_from.isoformat(),
                "standard_course_price": (str(version.package_price * obj.duration_months)
                                          if obj.duration_months else None)}


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
    duration_months = serializers.IntegerField(min_value=1, max_value=60, required=False, allow_null=True)
    payment_deadline_lessons = serializers.IntegerField(min_value=1, max_value=500, required=False)
    allow_monthly = serializers.BooleanField(required=False)
    allow_full_prepay = serializers.BooleanField(required=False)


class PlanUpdateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=150, required=False)
    payment_due_days = serializers.IntegerField(min_value=0, max_value=90, required=False)
    warn_before_end_lessons = serializers.IntegerField(min_value=0, max_value=100, required=False)
    early_invoice_enabled = serializers.BooleanField(required=False)
    early_invoice_after_lessons = serializers.IntegerField(min_value=1, required=False, allow_null=True)
    absence_policy = serializers.ChoiceField(choices=BillingPlan._meta.get_field("absence_policy").choices,
                                             required=False)
    is_active = serializers.BooleanField(required=False)
    duration_months = serializers.IntegerField(min_value=1, max_value=60, required=False, allow_null=True)
    payment_deadline_lessons = serializers.IntegerField(min_value=1, max_value=500, required=False)
    allow_monthly = serializers.BooleanField(required=False)
    allow_full_prepay = serializers.BooleanField(required=False)



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
    # Договор по программе
    payment_mode = serializers.ChoiceField(choices=PaymentMode.choices, required=False, default=PaymentMode.MONTHLY)
    reservation_allocation = serializers.ChoiceField(choices=ReservationAllocation.choices, required=False,
                                                     default=ReservationAllocation.FIRST_MONTH)
    discount_enabled = serializers.BooleanField(required=False, default=False)
    final_course_price = serializers.DecimalField(**MONEY, required=False, allow_null=True, min_value=Decimal("0"))
    # Деньги, полученные при зачислении (только бухгалтер): бронь и/или первый платёж.
    reservation_received = serializers.BooleanField(required=False, default=False)
    initial_payment = serializers.DecimalField(**MONEY, required=False, allow_null=True, min_value=Decimal("0.01"))
    payment_method = serializers.ChoiceField(choices=StudentPayment.Method.choices, required=False,
                                             default=StudentPayment.Method.CASH)
    payer_name = serializers.CharField(max_length=150, required=False, allow_blank=True, default="")
    # Индивидуальные цены учебных месяцев договора (по одной на месяц) и
    # правило распределения скидки: PROPORTIONAL или MANUAL (`month_amounts`).
    month_prices = serializers.ListField(child=serializers.DecimalField(**MONEY, min_value=Decimal("0.01")),
                                         required=False, allow_empty=False)
    month_plan_mode = serializers.ChoiceField(choices=("PROPORTIONAL", "MANUAL"), required=False, default="")
    month_amounts = serializers.ListField(child=serializers.DecimalField(**MONEY, min_value=Decimal("0")),
                                          required=False, allow_empty=False)
    # Когда деньги при зачислении фактически получены (по умолчанию — сегодня;
    # договор, оформляемый задним числом, — прошлая дата).
    payment_received_date = serializers.DateField(required=False, allow_null=True)
    idempotency_key = serializers.CharField(max_length=64, required=False, allow_blank=True)


class CourseTermsSerializer(serializers.Serializer):
    discount_enabled = serializers.BooleanField()
    final_course_price = serializers.DecimalField(**MONEY, required=False, allow_null=True, min_value=Decimal("0"))
    reason = serializers.CharField(required=False, allow_blank=True, default="")


class PaymentModeSerializer(serializers.Serializer):
    payment_mode = serializers.ChoiceField(choices=PaymentMode.choices)
    reason = serializers.CharField(required=False, allow_blank=True, default="")


class TermsChangeInputSerializer(TermsInputMixin):
    reason = serializers.CharField(required=False, allow_blank=True, default="")


class ProfileUpdateSerializer(serializers.Serializer):
    parent_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    parent_phone = serializers.CharField(max_length=30, required=False, allow_blank=True)
    special_terms = serializers.CharField(required=False, allow_blank=True)
    responsible_accountant = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.filter(role=User.Role.ACCOUNTANT, is_active=True), required=False, allow_null=True,
    )


class MonthPlanSerializer(serializers.Serializer):
    """План стоимости месяцев договора. `dry_run` — только предпросмотр."""

    standard_prices = serializers.ListField(child=serializers.DecimalField(**MONEY, min_value=Decimal("0.01")),
                                            allow_empty=False)
    final_course_price = serializers.DecimalField(**MONEY, min_value=Decimal("0"))
    mode = serializers.ChoiceField(choices=("PROPORTIONAL", "MANUAL"))
    manual_amounts = serializers.ListField(child=serializers.DecimalField(**MONEY, allow_null=True),
                                           required=False, allow_empty=False)
    reason = serializers.CharField(required=False, allow_blank=True, default="")
    reissue_unstarted = serializers.BooleanField(required=False, default=False)
    dry_run = serializers.BooleanField(required=False, default=False)


class StartDateSerializer(serializers.Serializer):
    start_date = serializers.DateField()
    reason = serializers.CharField()


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
        fields = ("id", "profile", "student_name", "custom_price", "discount_type", "discount_value",
                  "discount_enabled", "final_course_price", "discount_amount", "reason", "previous_terms", "status", "requested_by_name", "requested_at", "decided_by_name", "decided_at",
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
        fields = ("id", "profile", "number", "month_number", "status", "lessons_total", "lessons_used",
                  "lessons_remaining", "base_price", "custom_price", "discount_type", "discount_value",
                  "discount_amount", "final_price", "started_on", "completed_on", "invoice", "created_at")

    def get_invoice(self, obj) -> dict | None:
        inv = next((i for i in obj.invoices.all() if i.status != Invoice.Status.VOID), None)
        if inv is None:
            return None
        return {"id": inv.pk, "number": inv.number, "status": inv.status, "balance": str(inv.balance),
                "amount": str(inv.amount), "kind": inv.kind}


class ProfileSerializer(serializers.ModelSerializer):
    """Профиль со статусом оплаты — то, что нужно менеджеру для работы."""

    student_name = serializers.CharField(source="student.__str__", read_only=True)
    group = serializers.IntegerField(source="student.group_id", read_only=True)
    group_name = serializers.CharField(source="student.group.name", read_only=True, default=None)
    subject_name = serializers.CharField(source="subject.name", read_only=True, default=None)
    plan_name = serializers.CharField(source="plan.name", read_only=True)
    program_name = serializers.CharField(source="plan.course.name", read_only=True, default=None)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    payment_mode_display = serializers.CharField(source="get_payment_mode_display", read_only=True)
    reservation_allocation_display = serializers.CharField(source="get_reservation_allocation_display",
                                                           read_only=True)
    is_course = serializers.BooleanField(read_only=True)
    responsible_accountant_name = serializers.SerializerMethodField()
    discount_assigned_by_name = serializers.SerializerMethodField()
    discount_approved_by_name = serializers.SerializerMethodField()
    payment_status = serializers.SerializerMethodField()
    current_package = serializers.SerializerMethodField()
    pending_terms = serializers.SerializerMethodField()

    class Meta:
        model = StudentBillingProfile
        fields = ("id", "student", "student_name", "group", "group_name", "subject", "subject_name", "plan",
                  "plan_name", "program_name", "status", "status_display", "start_date", "parent_name", "parent_phone",
                  "payment_mode", "payment_mode_display", "reservation_allocation", "reservation_allocation_display",
                  "duration_months", "lessons_per_month", "deadline_lessons", "month_price", "standard_course_price",
                  "final_course_price", "discount_enabled", "discount_amount", "is_course", "custom_price",
                  "discount_type",
                  "discount_value", "discount_reason", "discount_assigned_by_name", "discount_approved_by_name",
                  "special_terms", "responsible_accountant", "responsible_accountant_name", "stopped_on",
                  "stop_reason", "payment_status", "current_package", "pending_terms", "month_plan_mode",
                  "month_prices", "created_at")

    month_prices = serializers.SerializerMethodField()

    def get_month_prices(self, obj) -> list[dict]:
        return [{"month_number": r.month_number, "standard_price": str(r.standard_price), "amount": str(r.amount)}
                for r in obj.month_prices.all()] if obj.month_plan_mode else []

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
                "next_due": min((i.due_date for i in unpaid if not i.due_lesson), default=None)}

    def get_current_package(self, obj) -> dict | None:
        package = next((p for p in obj.packages.all() if p.status == LessonPackage.Status.ACTIVE), None)
        if package is None:
            return None
        return {"id": package.pk, "number": package.number, "month_number": package.month_number,
                "lessons_used": package.lessons_used,
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
    month_number = serializers.IntegerField(source="package.month_number", read_only=True, default=None)
    lessons_used = serializers.IntegerField(source="package.lessons_used", read_only=True)
    lessons_total = serializers.IntegerField(source="package.lessons_total", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    kind_display = serializers.CharField(source="get_kind_display", read_only=True)
    stage = serializers.SerializerMethodField()

    class Meta:
        model = Invoice
        fields = ("id", "number", "profile", "student", "student_name", "group_name", "subject_name", "package",
                  "package_number", "month_number", "lessons_used", "lessons_total", "kind", "kind_display",
                  "amount", "amount_paid", "amount_adjusted", "balance", "currency", "status", "status_display",
                  "stage", "issue_date", "period_date", "due_date", "due_lesson", "due_reached_on", "overdue_since", "snapshot",
                  "paid_at", "void_reason", "created_at")

    def get_stage(self, obj) -> str:
        from .services.contracts import payment_stage

        return payment_stage(obj)


class AllocationSerializer(serializers.ModelSerializer):
    invoice_number = serializers.CharField(source="invoice.number", read_only=True)
    invoice_period_date = serializers.DateField(source="invoice.period_date", read_only=True)

    class Meta:
        model = PaymentAllocation
        fields = ("id", "payment", "invoice", "invoice_number", "invoice_period_date", "profile", "amount", "source",
                  "status", "created_at", "reversed_at", "reverse_reason")


class AdjustmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = InvoiceAdjustment
        fields = ("id", "invoice", "amount", "reason", "status", "effective_date", "created_at", "void_reason")


class InvoiceDetailSerializer(InvoiceSerializer):
    allocations = AllocationSerializer(many=True, read_only=True)
    adjustments = AdjustmentSerializer(many=True, read_only=True)

    class Meta(InvoiceSerializer.Meta):
        fields = InvoiceSerializer.Meta.fields + ("allocations", "adjustments")


class AdjustmentCreateSerializer(serializers.Serializer):
    amount = serializers.DecimalField(**MONEY, min_value=Decimal("0.01"))
    reason = serializers.CharField()
    effective_date = serializers.DateField(required=False, allow_null=True)


class InvoicePeriodSerializer(serializers.Serializer):
    period_date = serializers.DateField()
    reason = serializers.CharField()


class PeriodReviewApplySerializer(serializers.Serializer):
    invoices = serializers.ListField(child=serializers.IntegerField(min_value=1), required=False, allow_empty=False)


class BillingPaymentSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source="student.__str__", read_only=True)
    unallocated = serializers.SerializerMethodField()
    allocations = AllocationSerializer(source="billing_allocations", many=True, read_only=True)
    created_by_name = serializers.SerializerMethodField()
    group_name = serializers.CharField(source="group.name", read_only=True)
    program_name = serializers.CharField(source="course.name", read_only=True)
    method_display = serializers.CharField(source="get_method_display", read_only=True)
    purpose_display = serializers.CharField(source="get_purpose_display", read_only=True)
    receipt = serializers.SerializerMethodField()

    class Meta:
        model = StudentPayment
        fields = ("id", "billing_profile", "student", "student_name", "group_name", "program_name", "kind",
                  "purpose", "purpose_display", "amount", "currency", "received_date", "method", "method_display",
                  "reference", "comment", "status", "void_reason", "refund_of", "unallocated", "allocations",
                  "receipt", "created_by_name", "created_at", "replaces", "replaced_by", "voided_at")

    replaces = serializers.SerializerMethodField()
    replaced_by = serializers.SerializerMethodField()

    def get_replaces(self, obj) -> list[int]:
        """Сторнированные платежи, взамен которых внесён этот (цепочка исправления)."""
        return [link.original_id for link in obj.replaces_links.all()]

    def get_replaced_by(self, obj) -> list[int]:
        return [link.replacement_id for link in obj.replaced_by_links.all()]

    def get_receipt(self, obj) -> dict | None:
        receipt = getattr(obj, "receipt", None)
        return None if receipt is None else {"id": receipt.pk, "number": receipt.number, "status": receipt.status}

    def get_unallocated(self, obj) -> str | None:
        from .services.ledger import payment_unallocated

        from apps.accounting.services.money import money

        if obj.kind != StudentPayment.Kind.PAYMENT:
            return None
        return str(money(payment_unallocated(obj.pk)))

    def get_created_by_name(self, obj) -> str | None:
        return _name(obj.created_by)


class AllocationItemSerializer(serializers.Serializer):
    invoice = serializers.PrimaryKeyRelatedField(queryset=Invoice.objects.all())
    amount = serializers.DecimalField(**MONEY, min_value=Decimal("0.01"))


class PaymentCreateSerializer(serializers.Serializer):
    profile = serializers.PrimaryKeyRelatedField(queryset=StudentBillingProfile.objects.all())
    amount = serializers.DecimalField(**MONEY, min_value=Decimal("0.01"))
    # Дата ФАКТИЧЕСКОГО поступления денег: можно прошлую (платёж, полученный в
    # сентябре, вносится в октябре сентябрём); время записи — `created_at`.
    received_date = serializers.DateField()
    method = serializers.ChoiceField(choices=StudentPayment.Method.choices, default=StudentPayment.Method.CASH)
    # Назначение: оплата обучения или предоплата / аванс (бронь — отдельной операцией брони).
    purpose = serializers.ChoiceField(choices=(StudentPayment.Purpose.TUITION, StudentPayment.Purpose.PREPAYMENT),
                                      required=False)
    reference = serializers.CharField(max_length=100, required=False, allow_blank=True, default="")
    comment = serializers.CharField(required=False, allow_blank=True, default="")
    prepay_packages = serializers.IntegerField(min_value=0, max_value=24, required=False, default=0)
    auto_allocate = serializers.BooleanField(required=False, default=True)
    allocations = AllocationItemSerializer(many=True, required=False)
    idempotency_key = serializers.CharField(max_length=64, required=False, allow_blank=True)
    # Назначение: auto — по начислениям по порядку; invoice — на выбранное
    # начисление (остаток — аванс); advance — предоплата / аванс целиком.
    mode = serializers.ChoiceField(choices=("auto", "invoice", "advance"), required=False, default="auto")
    invoice = serializers.PrimaryKeyRelatedField(queryset=Invoice.objects.all(), required=False, allow_null=True)
    payer_name = serializers.CharField(max_length=150, required=False, allow_blank=True, default="")
    # Платёж вносится взамен сторнированного (связь в цепочке исправления).
    replaces = serializers.PrimaryKeyRelatedField(queryset=StudentPayment.objects.filter(status="void"),
                                                  required=False, allow_null=True)


class PaymentPreviewSerializer(serializers.Serializer):
    profile = serializers.PrimaryKeyRelatedField(queryset=StudentBillingProfile.objects.all())
    amount = serializers.DecimalField(**MONEY, min_value=Decimal("0.01"))
    mode = serializers.ChoiceField(choices=("auto", "invoice", "advance"), required=False, default="auto")
    invoice = serializers.PrimaryKeyRelatedField(queryset=Invoice.objects.all(), required=False, allow_null=True)


class AllocateSerializer(serializers.Serializer):
    allocations = AllocationItemSerializer(many=True)


class CorrectPaymentSerializer(serializers.Serializer):
    """Исправление проведённого платежа: передаются только меняемые поля."""

    reason = serializers.CharField()
    received_date = serializers.DateField(required=False)
    amount = serializers.DecimalField(**MONEY, min_value=Decimal("0.01"), required=False)
    method = serializers.ChoiceField(choices=StudentPayment.Method.choices, required=False)
    reference = serializers.CharField(max_length=100, required=False, allow_blank=True)
    comment = serializers.CharField(required=False, allow_blank=True)
    purpose = serializers.ChoiceField(choices=(StudentPayment.Purpose.TUITION, StudentPayment.Purpose.PREPAYMENT),
                                      required=False)
    profile = serializers.PrimaryKeyRelatedField(queryset=StudentBillingProfile.objects.all(), required=False)
    allocations = AllocationItemSerializer(many=True, required=False)
    confirm_closed_period = serializers.BooleanField(required=False, default=False)


class CreatedAtSerializer(serializers.Serializer):
    created_at = serializers.DateTimeField()
    reason = serializers.CharField()


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
    """Бронь — не отдельные деньги: оплаченная бронь ссылается на платёж
    (`payment`), и в «получено» считается только он. `paid_used` — сколько
    из этого платежа уже распределено на начисления, `paid_unused` — сколько
    осталось авансом."""

    student_name = serializers.CharField(source="profile.student.__str__", read_only=True)
    paid_amount = serializers.DecimalField(source="payment.amount", **MONEY, read_only=True, default=None)
    paid_date = serializers.DateField(source="payment.received_date", read_only=True, default=None)
    payment_status = serializers.CharField(source="payment.status", read_only=True, default=None)
    receipt_number = serializers.SerializerMethodField()
    paid_used = serializers.SerializerMethodField()
    paid_unused = serializers.SerializerMethodField()

    class Meta:
        model = Reservation
        fields = ("id", "profile", "student_name", "group", "expected_amount", "reserved_until", "status", "payment",
                  "paid_amount", "paid_date", "payment_status", "receipt_number", "paid_used", "paid_unused",
                  "comment", "refunded_amount", "retained_amount", "cancel_reason", "cancelled_at", "created_at")

    def get_receipt_number(self, obj) -> str | None:
        receipt = getattr(obj.payment, "receipt", None) if obj.payment_id else None
        return receipt.number if receipt else None

    def get_paid_used(self, obj) -> str | None:
        if not obj.payment_id:
            return None
        used = obj.payment.billing_allocations.filter(status="ACTIVE").aggregate(s=models.Sum("amount"))["s"]
        from apps.accounting.services.money import money

        return str(money(used or Decimal("0.00")))

    def get_paid_unused(self, obj) -> str | None:
        if not obj.payment_id or obj.payment.status != StudentPayment.Status.CONFIRMED:
            return None
        from .services.ledger import payment_unallocated

        from apps.accounting.services.money import money

        return str(money(payment_unallocated(obj.payment_id)))


class ReservationEditSerializer(serializers.Serializer):
    expected_amount = serializers.DecimalField(**MONEY, min_value=Decimal("0.01"), required=False)
    reserved_until = serializers.DateField(required=False, allow_null=True)
    reason = serializers.CharField()


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
    payer_name = serializers.CharField(max_length=150, required=False, allow_blank=True, default="")


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


class BulkRegisterSerializer(serializers.Serializer):
    plan = serializers.PrimaryKeyRelatedField(queryset=BillingPlan.objects.filter(is_active=True))
    students = serializers.PrimaryKeyRelatedField(queryset=Student.objects.all(), many=True, required=False)
    group = serializers.IntegerField(required=False, allow_null=True)
    all_active = serializers.BooleanField(required=False, default=False)
    start_date = serializers.DateField(required=False, allow_null=True)
    responsible_accountant = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.filter(role=User.Role.ACCOUNTANT, is_active=True), required=False, allow_null=True,
    )
    prepaid_first_package = serializers.BooleanField(required=False, default=False)
    prepaid_reason = serializers.CharField(required=False, allow_blank=True, default="")

    def validate(self, attrs):
        if not attrs.get("students") and not attrs.get("group") and not attrs.get("all_active"):
            raise serializers.ValidationError({"students": "Выберите студентов, группу или «все активные»."})
        return attrs


# ---------------------------------------------------------------------------
# Чеки и настройки
# ---------------------------------------------------------------------------

class ReceiptSerializer(serializers.ModelSerializer):
    kind_display = serializers.CharField(source="get_kind_display", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    issued_by_name = serializers.SerializerMethodField()
    student_name = serializers.CharField(source="payment.student.__str__", read_only=True)
    amount = serializers.DecimalField(source="payment.amount", **MONEY, read_only=True)
    received_date = serializers.DateField(source="payment.received_date", read_only=True)
    payment_status = serializers.CharField(source="payment.status", read_only=True)
    rows = serializers.SerializerMethodField()
    academy = serializers.SerializerMethodField()

    class Meta:
        model = Receipt
        fields = ("id", "number", "payment", "profile", "student_name", "kind", "kind_display", "status",
                  "status_display", "amount", "received_date", "payment_status", "payer_name", "snapshot",
                  "issued_at", "issued_by_name", "print_count", "last_printed_at", "cancelled_at", "cancel_reason",
                  "rows", "academy")

    def get_issued_by_name(self, obj) -> str | None:
        return _name(obj.issued_by)

    def get_rows(self, obj) -> list:
        from .services.receipt_pdf import receipt_rows

        return [{"label": k, "value": v} for k, v in receipt_rows(obj)]

    def get_academy(self, obj) -> dict:
        from .models import BillingSettings

        cfg = BillingSettings.load()
        return {"name": cfg.academy_name, "details": cfg.academy_details, "footer": cfg.receipt_footer}


class BillingSettingsSerializer(serializers.Serializer):
    manager_max_discount_percent = serializers.DecimalField(max_digits=5, decimal_places=2, min_value=Decimal("0"),
                                                            max_value=Decimal("100"), required=False)
    due_soon_lessons = serializers.IntegerField(min_value=0, max_value=100, required=False)
    default_deadline_lessons = serializers.IntegerField(min_value=1, max_value=100, required=False)
    accountant_refund_limit = serializers.DecimalField(**MONEY, required=False, allow_null=True,
                                                       min_value=Decimal("0"))
    academy_name = serializers.CharField(max_length=150, required=False)
    academy_details = serializers.CharField(required=False, allow_blank=True)
    receipt_footer = serializers.CharField(required=False, allow_blank=True)
    updated_at = serializers.DateTimeField(read_only=True)
