"""API оплаты обучения (/api/v1/accounting/billing/). Представления только
проверяют права, валидируют ввод и вызывают сервисы. Права проверяются и
здесь (DRF), и в каждом сервисе (`permissions.authorize`)."""
from __future__ import annotations

import datetime as dt
from decimal import Decimal

from django.db import transaction
from django.db.models import Prefetch, Q, Sum
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounting.models import PayrollAuditLog, StudentPayment

from . import serializers as s
from .models import (
    BillingContactLog,
    BillingNotification,
    BillingPlan,
    BillingTask,
    BillingTermsChange,
    CreditLedgerEntry,
    Invoice,
    LessonConsumption,
    LessonPackage,
    PaymentAllocation,
    PaymentMode,
    Receipt,
    Reservation,
    ReservationAllocation,
    StudentBillingProfile,
)
from .permissions import (
    BillingAccess,
    MoneyAccess,
    can_view_money,
    capabilities,
    is_billing_accountant,
    is_manager,
)
from .services import (
    BillingError,
    analytics,
    contacts,
    contracts,
    corrections,
    invoices,
    lessons,
    payments,
    periods,
    pricing,
    profiles,
    queues,
    receipts,
    reports,
    reservations,
)
from .services import settings as billing_settings

from apps.accounting.services.money import money

TAG = ["Billing"]


class BillingPagination(PageNumberPagination):
    page_size = 50
    page_size_query_param = "page_size"
    max_page_size = 500


def _fail(exc: BillingError):
    if exc.code == "forbidden":
        raise PermissionDenied({"detail": exc.message, "code": exc.code})
    raise ValidationError({"detail": exc.message, "code": exc.code})


def _valid(serializer_class, request, **kwargs):
    serializer = serializer_class(data=request.data, **kwargs)
    serializer.is_valid(raise_exception=True)
    return serializer.validated_data


def _call(func, *args, **kwargs):
    try:
        return func(*args, **kwargs)
    except BillingError as exc:
        _fail(exc)


def _idempotency_key(request, data) -> str | None:
    return (data.get("idempotency_key") or request.headers.get("Idempotency-Key") or "").strip() or None


def _int(value, name):
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        raise ValidationError({name: "Ожидается число."})


def _date(value, name):
    if value in (None, ""):
        return None
    try:
        return dt.date.fromisoformat(value)
    except ValueError:
        raise ValidationError({name: "Ожидается дата ГГГГ-ММ-ДД."})


def filters_from(request, *, invoice_status: bool = True) -> dict:
    """Фильтры панели из запроса. `invoice_status=False` — у списка свой
    `status` (профиля, пакета, платежа), он идёт в filterset, а не сюда."""
    q = request.query_params
    status_value = (q.get("status") or None) if invoice_status else None
    if status_value and status_value not in Invoice.Status.values:
        raise ValidationError({"status": "Неизвестный статус начисления."})
    result = {
        "group": _int(q.get("group"), "group"), "subject": _int(q.get("subject"), "subject"),
        "student": _int(q.get("student"), "student"), "accountant": _int(q.get("accountant"), "accountant"),
        "plan": _int(q.get("plan"), "plan"), "status": status_value,
        "date_from": _date(q.get("date_from"), "date_from"), "date_to": _date(q.get("date_to"), "date_to"),
    }
    if result["date_from"] and result["date_to"] and result["date_from"] > result["date_to"]:
        raise ValidationError({"date_from": "Начало периода позже конца."})
    return result


@extend_schema(tags=TAG)
class MeView(APIView):
    permission_classes = [BillingAccess]

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request):
        return Response(capabilities(request.user))


# ---------------------------------------------------------------------------
# Тарифы
# ---------------------------------------------------------------------------

@extend_schema(tags=TAG)
class PlanViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    permission_classes = [BillingAccess]
    serializer_class = s.PlanSerializer
    pagination_class = BillingPagination
    filterset_fields = ("subject", "course", "is_active")
    search_fields = ("name",)

    def get_queryset(self):
        return BillingPlan.objects.select_related("subject", "course").prefetch_related("versions")

    @extend_schema(request=s.PlanCreateSerializer, responses=s.PlanSerializer)
    def create(self, request):
        data = dict(_valid(s.PlanCreateSerializer, request))
        plan = _call(pricing.create_plan, actor=request.user, **data)
        return Response(s.PlanSerializer(plan).data, status=status.HTTP_201_CREATED)

    @extend_schema(request=s.PlanUpdateSerializer, responses=s.PlanSerializer)
    def partial_update(self, request, pk=None):
        data = _valid(s.PlanUpdateSerializer, request)
        plan = _call(pricing.update_plan_settings, self.get_object(), actor=request.user, **data)
        return Response(s.PlanSerializer(plan).data)

    @extend_schema(request=s.PlanVersionCreateSerializer, responses=s.PlanVersionSerializer)
    @action(detail=True, methods=["post"])
    def versions(self, request, pk=None):
        data = _valid(s.PlanVersionCreateSerializer, request)
        version = _call(pricing.add_plan_version, self.get_object(), actor=request.user, **data)
        return Response(s.PlanVersionSerializer(version).data, status=status.HTTP_201_CREATED)


# ---------------------------------------------------------------------------
# Профили
# ---------------------------------------------------------------------------

def _profile_qs():
    return StudentBillingProfile.objects.select_related(
        "student__group", "subject", "plan", "responsible_accountant", "discount_assigned_by", "discount_approved_by",
    ).prefetch_related("invoices", "packages", "terms_changes")


@extend_schema(tags=TAG, parameters=[
    OpenApiParameter("group", int), OpenApiParameter("subject", int), OpenApiParameter("student", int),
    OpenApiParameter("accountant", int), OpenApiParameter("plan", int), OpenApiParameter("debt", bool),
])
class ProfileViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    permission_classes = [BillingAccess]
    serializer_class = s.ProfileSerializer
    pagination_class = BillingPagination
    search_fields = ("student__first_name", "student__last_name", "parent_phone", "parent_name")
    filterset_fields = ("status",)

    def get_queryset(self):
        qs = reports.filter_profiles(_profile_qs(), filters_from(self.request, invoice_status=False))
        if self.request.query_params.get("debt") in ("1", "true"):
            qs = qs.filter(invoices__status__in=Invoice.UNPAID_STATUSES).distinct()
        return qs

    @extend_schema(request=s.ProfileCreateSerializer, responses=s.ProfileSerializer)
    def create(self, request):
        """Оформить договор. Бухгалтер может сразу провести полученные деньги
        (оплату брони и первый платёж) — в одной транзакции с договором."""
        data = dict(_valid(s.ProfileCreateSerializer, request))
        key = _idempotency_key(request, data)
        data.pop("idempotency_key", None)
        reservation_received = data.pop("reservation_received")
        initial_payment = data.pop("initial_payment", None)
        method, payer = data.pop("payment_method"), data.pop("payer_name")
        received_on = data.pop("payment_received_date", None)
        if (reservation_received or initial_payment) and not is_billing_accountant(request.user):
            raise PermissionDenied({"detail": "Деньги регистрирует бухгалтер.", "code": "forbidden"})
        if reservation_received and not data.get("reservation_amount"):
            raise ValidationError({"reservation_amount": "Укажите сумму брони."})
        # Дата поступления денег — выбранная бухгалтером (договор задним числом),
        # иначе сегодня; будущая дата отклоняется сервисом платежей.
        today = received_on or timezone.localdate()
        try:
            with transaction.atomic():
                profile = profiles.create_student_billing_profile(actor=request.user, **data)
                if reservation_received:
                    reservations.record_reservation_payment(
                        profile.reservations.get(status=Reservation.Status.PENDING), actor=request.user,
                        amount=data["reservation_amount"], received_date=today, method=method, payer_name=payer,
                        idempotency_key=f"{key}:res" if key else None,
                    )
                if initial_payment:
                    payments.record_payment(
                        profile=profile, amount=initial_payment, received_date=today, actor=request.user,
                        method=method, payer_name=payer, idempotency_key=f"{key}:pay" if key else None,
                    )
        except BillingError as exc:
            _fail(exc)
        return Response(s.ProfileSerializer(_profile_qs().get(pk=profile.pk)).data, status=status.HTTP_201_CREATED)

    @extend_schema(responses=OpenApiTypes.OBJECT)
    @action(detail=True, methods=["get"])
    def card(self, request, pk=None):
        """Карточка договора: условия, учебные месяцы, начисления, деньги,
        чеки, бронь, контакты. Менеджер — без денежных операций."""
        profile = self.get_object()
        return Response(contract_card(profile, with_money=can_view_money(request.user)))

    @extend_schema(responses=OpenApiTypes.OBJECT)
    @action(detail=True, methods=["get"])
    def lessons(self, request, pk=None):
        """Посещения студента и какие из них засчитаны в учебные месяцы — с
        причиной для каждого незасчитанного урока (только чтение)."""
        return Response(lessons.lesson_breakdown(self.get_object()))

    @extend_schema(request=s.StartDateSerializer, responses=OpenApiTypes.OBJECT)
    @action(detail=True, methods=["post"], url_path="start-date", permission_classes=[MoneyAccess])
    def start_date(self, request, pk=None):
        """Исправить ошибочную дату начала договора (основание, аудит) и
        засчитать уроки приоритетного предмета с новой даты."""
        data = _valid(s.StartDateSerializer, request)
        result = _call(profiles.change_start_date, self.get_object(), actor=request.user, **data)
        return Response({**result, "lessons": lessons.lesson_breakdown(StudentBillingProfile.objects.get(pk=pk))})

    @extend_schema(request=s.CourseTermsSerializer, responses=s.TermsChangeSerializer)
    @action(detail=True, methods=["post"], url_path="course-terms")
    def course_terms(self, request, pk=None):
        data = _valid(s.CourseTermsSerializer, request)
        change = _call(profiles.request_course_terms_change, self.get_object(), actor=request.user, **data)
        return Response(s.TermsChangeSerializer(change).data, status=status.HTTP_201_CREATED)

    @extend_schema(request=s.PaymentModeSerializer, responses=s.ProfileSerializer)
    @action(detail=True, methods=["post"], url_path="payment-mode")
    def payment_mode(self, request, pk=None):
        data = _valid(s.PaymentModeSerializer, request)
        _call(profiles.change_payment_mode, self.get_object(), actor=request.user, **data)
        return Response(s.ProfileSerializer(_profile_qs().get(pk=pk)).data)

    @extend_schema(request=s.ProfileUpdateSerializer, responses=s.ProfileSerializer)
    def partial_update(self, request, pk=None):
        data = _valid(s.ProfileUpdateSerializer, request)
        profile = _call(profiles.update_profile, self.get_object(), actor=request.user, **data)
        return Response(s.ProfileSerializer(_profile_qs().get(pk=profile.pk)).data)

    @extend_schema(request=s.BulkRegisterSerializer, responses=OpenApiTypes.OBJECT)
    @action(detail=False, methods=["post"])
    def bulk(self, request):
        """Подключить к оплате выбранных студентов, группу или всех активных."""
        from apps.academy.models import Student

        data = _valid(s.BulkRegisterSerializer, request)
        if data.get("students"):
            students = data["students"]
        else:
            qs = Student.objects.filter(status=Student.Status.ACTIVE).order_by("last_name", "first_name")
            students = list(qs.filter(group_id=data["group"]) if data.get("group") else qs)
        result = _call(
            profiles.register_students, actor=request.user, plan=data["plan"], students=students,
            start_date=data.get("start_date"), responsible_accountant=data.get("responsible_accountant"),
            prepaid_first_package=data["prepaid_first_package"], prepaid_reason=data["prepaid_reason"],
        )
        return Response({"created": len(result["created"]), "skipped": result["skipped"]})

    @extend_schema(request=s.TermsChangeInputSerializer, responses=s.TermsChangeSerializer)
    @action(detail=True, methods=["post"])
    def terms(self, request, pk=None):
        data = _valid(s.TermsChangeInputSerializer, request)
        change = _call(profiles.request_terms_change, self.get_object(), actor=request.user, **data)
        return Response(s.TermsChangeSerializer(change).data, status=status.HTTP_201_CREATED)

    @extend_schema(request=s.StopSerializer, responses=s.ProfileSerializer)
    @action(detail=True, methods=["post"])
    def deactivate(self, request, pk=None):
        data = _valid(s.StopSerializer, request)
        _call(profiles.deactivate_billing_profile, self.get_object(), actor=request.user,
              reason=data["reason"], on_date=data.get("on_date"))
        return Response(s.ProfileSerializer(_profile_qs().get(pk=pk)).data)

    @extend_schema(request=s.BillingReasonSerializer, responses=s.ProfileSerializer)
    @action(detail=True, methods=["post"])
    def resume(self, request, pk=None):
        data = _valid(s.BillingReasonSerializer, request)
        _call(profiles.resume_billing_profile, self.get_object(), actor=request.user, reason=data["reason"])
        return Response(s.ProfileSerializer(_profile_qs().get(pk=pk)).data)

    @extend_schema(request=None, responses=s.AllocationSerializer(many=True))
    @action(detail=True, methods=["post"], url_path="apply-credit", permission_classes=[MoneyAccess])
    def apply_credit(self, request, pk=None):
        allocations = _call(payments.apply_available_credit, self.get_object(), actor=request.user)
        return Response(s.AllocationSerializer(allocations, many=True).data)

    @extend_schema(responses=s.CreditEntrySerializer(many=True))
    @action(detail=True, methods=["get"], permission_classes=[MoneyAccess])
    def credit(self, request, pk=None):
        profile = self.get_object()
        entries = CreditLedgerEntry.objects.filter(profile=profile).order_by("-created_at", "-id")
        from .services.ledger import credit_balance

        return Response({"balance": str(credit_balance(profile.pk)),
                         "entries": s.CreditEntrySerializer(entries[:500], many=True).data})


def _profile_summary(profile) -> dict:
    invoices_all = list(profile.invoices.all())
    unpaid = [i for i in invoices_all if i.status in Invoice.UNPAID_STATUSES]
    debt = sum((i.balance for i in unpaid), Decimal("0"))
    if any(i.status == Invoice.Status.OVERDUE for i in unpaid):
        state = "overdue"
    elif unpaid:
        state = "awaiting"
    elif any(i.status == Invoice.Status.DRAFT for i in invoices_all):
        state = "draft"
    else:
        state = "paid"
    package = next((p for p in profile.packages.all() if p.status == LessonPackage.Status.ACTIVE), None)
    return {
        "id": profile.pk, "status": profile.status, "subject_name": profile.subject.name if profile.subject_id else None,
        "plan_name": profile.plan.name, "payment_state": state, "debt": str(money(debt)),
        "unpaid_invoices": len(unpaid), "credit": str(money(profile.credit or Decimal("0.00"))),
        "next_due": min((i.due_date for i in unpaid if not i.due_lesson), default=None),
        "package": None if package is None else {
            "number": package.number, "month_number": package.month_number, "used": package.lessons_used,
            "total": package.lessons_total,
        },
    }


@extend_schema(tags=TAG, parameters=[
    OpenApiParameter("group", int), OpenApiParameter("search", str), OpenApiParameter("registered", str),
    OpenApiParameter("state", str), OpenApiParameter("all", bool),
], responses=OpenApiTypes.OBJECT)
class StudentsView(APIView):
    """Все студенты LMS (по умолчанию активные) и их оплата: подключён ли
    к учёту, долг, аванс, текущий пакет. Для бухгалтера — только то, что
    нужно для работы с оплатой (ФИО, группа, телефон родителя)."""

    permission_classes = [BillingAccess]

    def get(self, request):
        from apps.academy.models import Student

        q = request.query_params
        qs = Student.objects.select_related("group").order_by("last_name", "first_name", "pk")
        if q.get("all") not in ("1", "true"):
            qs = qs.filter(status=Student.Status.ACTIVE)
        if q.get("group"):
            qs = qs.filter(group_id=_int(q["group"], "group"))
        for part in (q.get("search") or "").split():
            qs = qs.filter(Q(first_name__icontains=part) | Q(last_name__icontains=part) | Q(parent_phone__icontains=part))
        live_ids = StudentBillingProfile.objects.exclude(
            status__in=StudentBillingProfile.CLOSED_STATUSES).values("student_id")
        if q.get("registered") == "yes":
            qs = qs.filter(pk__in=live_ids)
        elif q.get("registered") == "no":
            qs = qs.exclude(pk__in=live_ids)
        if q.get("state") == "debt":
            qs = qs.filter(billing_profiles__invoices__status__in=Invoice.UNPAID_STATUSES).distinct()
        elif q.get("state") == "overdue":
            qs = qs.filter(billing_profiles__invoices__status=Invoice.Status.OVERDUE).distinct()
        profiles = (
            StudentBillingProfile.objects.exclude(status__in=StudentBillingProfile.CLOSED_STATUSES)
            .select_related("plan", "subject")
            .annotate(credit=Sum("credit_entries__amount"))
            .prefetch_related("invoices", "packages")
        )
        qs = qs.prefetch_related(Prefetch("billing_profiles", queryset=profiles, to_attr="live_profiles"))
        paginator = BillingPagination()
        page = paginator.paginate_queryset(qs, request, view=self)
        return paginator.get_paginated_response([
            {
                "id": st.pk, "name": str(st), "group": st.group_id, "group_name": st.group.name if st.group_id else None,
                "status": st.status, "status_display": st.get_status_display(), "parent_phone": st.parent_phone,
                "profiles": [_profile_summary(p) for p in st.live_profiles],
            }
            for st in page
        ])


@extend_schema(tags=TAG)
class TermsChangeViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    permission_classes = [BillingAccess]
    serializer_class = s.TermsChangeSerializer
    pagination_class = BillingPagination
    filterset_fields = ("status", "profile")

    def get_queryset(self):
        return BillingTermsChange.objects.select_related("profile__student", "requested_by", "decided_by")

    @extend_schema(request=s.DecisionSerializer, responses=s.TermsChangeSerializer)
    @action(detail=True, methods=["post"])
    def decide(self, request, pk=None):
        data = _valid(s.DecisionSerializer, request)
        change = _call(profiles.decide_terms_change, self.get_object(), actor=request.user, **data)
        return Response(s.TermsChangeSerializer(change).data)


# ---------------------------------------------------------------------------
# Пакеты и списания
# ---------------------------------------------------------------------------

@extend_schema(tags=TAG)
class PackageViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    permission_classes = [BillingAccess]
    serializer_class = s.PackageSerializer
    pagination_class = BillingPagination
    filterset_fields = ("profile", "status")

    def get_queryset(self):
        qs = LessonPackage.objects.select_related("profile").prefetch_related("invoices")
        return reports.filter_profiles(qs, filters_from(self.request, invoice_status=False), "profile__")


@extend_schema(tags=TAG)
class ConsumptionViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    permission_classes = [BillingAccess]
    serializer_class = s.ConsumptionSerializer
    pagination_class = BillingPagination
    filterset_fields = ("profile", "package", "kind", "status", "lesson_ref")

    def get_queryset(self):
        qs = LessonConsumption.objects.select_related("student", "package")
        return reports.filter_profiles(qs, filters_from(self.request, invoice_status=False), "profile__")

    @extend_schema(request=s.ReverseConsumptionSerializer, responses=s.ConsumptionSerializer)
    @action(detail=True, methods=["post"], permission_classes=[MoneyAccess])
    def reverse(self, request, pk=None):
        data = _valid(s.ReverseConsumptionSerializer, request)
        reversal = _call(lessons.reverse_consumption, self.get_object(), actor=request.user, reason=data["reason"])
        return Response(s.ConsumptionSerializer(reversal).data, status=status.HTTP_201_CREATED)


# ---------------------------------------------------------------------------
# Начисления
# ---------------------------------------------------------------------------

@extend_schema(tags=TAG, parameters=[
    OpenApiParameter("group", int), OpenApiParameter("subject", int), OpenApiParameter("student", int),
    OpenApiParameter("accountant", int), OpenApiParameter("status", str), OpenApiParameter("date_from", str),
    OpenApiParameter("date_to", str), OpenApiParameter("due_from", str), OpenApiParameter("due_to", str),
])
class InvoiceViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    permission_classes = [BillingAccess]
    pagination_class = BillingPagination
    filterset_fields = ("profile", "package")
    search_fields = ("number", "profile__student__first_name", "profile__student__last_name")
    ordering_fields = ("due_date", "issue_date", "period_date", "amount")

    def get_serializer_class(self):
        return s.InvoiceDetailSerializer if self.action == "retrieve" else s.InvoiceSerializer

    def get_queryset(self):
        f = filters_from(self.request)
        qs = reports.invoices_qs(f).select_related("profile__student__group", "profile__subject", "package")
        # Период — по периоду начисления (к какому месяцу относится долг), не по
        # дате выставления; дата выставления — issue_from / issue_to.
        if f["date_from"]:
            qs = qs.filter(period_date__gte=f["date_from"])
        if f["date_to"]:
            qs = qs.filter(period_date__lte=f["date_to"])
        q = self.request.query_params
        if q.get("issue_from"):
            qs = qs.filter(issue_date__gte=_date(q["issue_from"], "issue_from"))
        if q.get("issue_to"):
            qs = qs.filter(issue_date__lte=_date(q["issue_to"], "issue_to"))
        if q.get("due_from"):
            qs = qs.filter(due_date__gte=_date(q["due_from"], "due_from"))
        if q.get("due_to"):
            qs = qs.filter(due_date__lte=_date(q["due_to"], "due_to"))
        if q.get("unpaid") in ("1", "true"):
            qs = qs.filter(status__in=Invoice.UNPAID_STATUSES)
        if self.action == "retrieve":
            qs = qs.prefetch_related("allocations__invoice", "adjustments")
        return qs

    @extend_schema(request=s.BillingReasonSerializer, responses=s.InvoiceSerializer)
    @action(detail=True, methods=["post"], permission_classes=[MoneyAccess])
    def void(self, request, pk=None):
        data = _valid(s.BillingReasonSerializer, request)
        invoice = _call(invoices.void_invoice, self.get_object(), actor=request.user, reason=data["reason"])
        return Response(s.InvoiceSerializer(invoice).data)

    @extend_schema(request=s.AdjustmentCreateSerializer, responses=s.AdjustmentSerializer)
    @action(detail=True, methods=["post"], permission_classes=[MoneyAccess])
    def adjustments(self, request, pk=None):
        data = _valid(s.AdjustmentCreateSerializer, request)
        adjustment = _call(invoices.adjust_invoice, self.get_object(), actor=request.user, **data)
        return Response(s.AdjustmentSerializer(adjustment).data, status=status.HTTP_201_CREATED)

    @extend_schema(request=s.InvoicePeriodSerializer, responses=s.InvoiceSerializer)
    @action(detail=True, methods=["post"], permission_classes=[MoneyAccess])
    def period(self, request, pk=None):
        """Контролируемое исправление периода начисления (с основанием, в аудите)."""
        data = _valid(s.InvoicePeriodSerializer, request)
        invoice = _call(invoices.correct_invoice_period, self.get_object(), actor=request.user, **data)
        return Response(s.InvoiceSerializer(invoice).data)

    @extend_schema(responses=OpenApiTypes.OBJECT)
    @action(detail=True, methods=["get"])
    def balance(self, request, pk=None):
        sums = invoices.calculate_invoice_balance(self.get_object())
        return Response({k: str(v) for k, v in sums.items()})


# ---------------------------------------------------------------------------
# Платежи и распределения
# ---------------------------------------------------------------------------

@extend_schema(tags=TAG)
class PaymentViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    permission_classes = [MoneyAccess]
    serializer_class = s.BillingPaymentSerializer
    pagination_class = BillingPagination
    filterset_fields = ("billing_profile", "student", "kind", "status", "purpose", "method")
    search_fields = ("student__first_name", "student__last_name", "reference", "receipt__number")

    def get_queryset(self):
        f = filters_from(self.request, invoice_status=False)
        qs = StudentPayment.objects.filter(billing_profile__isnull=False).select_related(
            "student", "created_by", "group", "course", "receipt",
        )
        qs = reports.filter_profiles(qs, f, "billing_profile__").prefetch_related(
            Prefetch("billing_allocations", queryset=PaymentAllocation.objects.select_related("invoice")),
        )
        if f["date_from"]:
            qs = qs.filter(received_date__gte=f["date_from"])
        if f["date_to"]:
            qs = qs.filter(received_date__lte=f["date_to"])
        q = self.request.query_params
        if q.get("program"):
            qs = qs.filter(billing_profile__plan__course_id=_int(q["program"], "program"))
        if q.get("month"):  # месяц поступления денег: ГГГГ-ММ
            first, last = _call(periods.month_bounds, q["month"])
            qs = qs.filter(received_date__gte=first, received_date__lte=last)
        if q.get("number"):  # номер платежа (id) или чека
            number = q["number"].strip()
            qs = qs.filter(Q(pk=int(number)) | Q(receipt__number__icontains=number) if number.isdigit()
                           else Q(receipt__number__icontains=number))
        return qs.order_by("-received_date", "-id")

    @extend_schema(request=s.PaymentCreateSerializer, responses=s.BillingPaymentSerializer,
                   parameters=[OpenApiParameter("Idempotency-Key", str, OpenApiParameter.HEADER)])
    def create(self, request):
        data = dict(_valid(s.PaymentCreateSerializer, request))
        key = _idempotency_key(request, data)
        data.pop("idempotency_key", None)
        items = [(row["invoice"], row["amount"]) for row in data.pop("allocations", None) or []]
        mode, invoice = data.pop("mode"), data.pop("invoice", None)
        if mode == "advance":
            # Предоплата: сначала закрывает уже выставленные начисления
            # (например, «Весь курс»), остаток — аванс на будущие месяцы.
            data.setdefault("purpose", StudentPayment.Purpose.PREPAYMENT)
        elif mode == "invoice":
            if invoice is None:
                raise ValidationError({"invoice": "Выберите начисление."})
            items = [(invoice, min(data["amount"], invoice.balance))] if invoice.balance > 0 else []
            if not items:
                raise ValidationError({"invoice": "Начисление уже оплачено."})
        payment, created = _call(
            payments.record_payment, profile=data.pop("profile"), actor=request.user, idempotency_key=key,
            allocations=items or None, **data,
        )
        payment = self.get_queryset().get(pk=payment.pk)
        return Response(s.BillingPaymentSerializer(payment).data,
                        status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)

    @extend_schema(request=s.PaymentPreviewSerializer, responses=OpenApiTypes.OBJECT)
    @action(detail=False, methods=["post"])
    def preview(self, request):
        """Что будет после сохранения — без записи (обязательство, оплачено,
        остаток после платежа, аванс после операции)."""
        data = _valid(s.PaymentPreviewSerializer, request)
        return Response(_call(payments.preview_payment, data["profile"], amount=data["amount"],
                              invoice=data.get("invoice"), mode=data["mode"]))

    @extend_schema(request=None, responses=s.ReceiptSerializer)
    @action(detail=True, methods=["post"])
    def receipt(self, request, pk=None):
        """Чек операции (если его нет — выдать; повтор возвращает тот же)."""
        receipt = _call(receipts.ensure_receipt, self.get_object(), actor=request.user)
        return Response(s.ReceiptSerializer(receipt).data)

    @extend_schema(request=s.AllocateSerializer, responses=s.AllocationSerializer(many=True))
    @action(detail=True, methods=["post"])
    def allocate(self, request, pk=None):
        data = _valid(s.AllocateSerializer, request)
        items = [(row["invoice"], row["amount"]) for row in data["allocations"]]
        allocations = _call(payments.allocate_payment, self.get_object(), actor=request.user, items=items)
        return Response(s.AllocationSerializer(allocations, many=True).data, status=status.HTTP_201_CREATED)

    @extend_schema(request=s.BillingReasonSerializer, responses=s.BillingPaymentSerializer)
    @action(detail=True, methods=["post"])
    def reverse(self, request, pk=None):
        data = _valid(s.BillingReasonSerializer, request)
        payment = self.get_object()
        if payment.kind == StudentPayment.Kind.REFUND:
            _call(payments.reverse_refund, payment, actor=request.user, reason=data["reason"])
        else:
            _call(payments.reverse_payment, payment, actor=request.user, reason=data["reason"])
        return Response(s.BillingPaymentSerializer(self.get_queryset().get(pk=pk)).data)

    @extend_schema(request=s.CorrectPaymentSerializer, responses=OpenApiTypes.OBJECT)
    @action(detail=True, methods=["post"])
    def correct(self, request, pk=None):
        """Исправить проведённый платёж (дата, сумма, способ, договор,
        назначение, распределение) — с причиной и аудитом. Повтор той же
        формы ничего не меняет."""
        data = dict(_valid(s.CorrectPaymentSerializer, request))
        if "allocations" in data:
            data["allocations"] = [(row["invoice"], row["amount"]) for row in data["allocations"]]
        result = _call(corrections.correct_payment, self.get_object(), actor=request.user, **data)
        return Response({"payment": s.BillingPaymentSerializer(self.get_queryset().get(pk=pk)).data,
                         "changed": result["changed"], "warnings": result["warnings"], "audit": result["audit"]})

    @extend_schema(request=s.CreatedAtSerializer, responses=s.BillingPaymentSerializer)
    @action(detail=True, methods=["post"], url_path="created-at")
    def created_at(self, request, pk=None):
        """Административная корректировка даты создания записи (аудит)."""
        data = _valid(s.CreatedAtSerializer, request)
        _call(corrections.correct_created_at, self.get_object(), actor=request.user, **data)
        return Response(s.BillingPaymentSerializer(self.get_queryset().get(pk=pk)).data)

    @extend_schema(responses=OpenApiTypes.OBJECT)
    @action(detail=True, methods=["get"])
    def history(self, request, pk=None):
        """История изменений платежа, его чека и распределений (только чтение)."""
        return Response(corrections.payment_history(self.get_object()))

    @extend_schema(request=s.RefundSerializer, responses=s.BillingPaymentSerializer)
    @action(detail=True, methods=["post"])
    def refund(self, request, pk=None):
        data = dict(_valid(s.RefundSerializer, request))
        key = _idempotency_key(request, data)
        data.pop("idempotency_key", None)
        refund = _call(payments.refund_payment, self.get_object(), actor=request.user, idempotency_key=key, **data)
        return Response(s.BillingPaymentSerializer(self.get_queryset().get(pk=refund.pk)).data,
                        status=status.HTTP_201_CREATED)


@extend_schema(tags=TAG)
class AllocationViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    permission_classes = [MoneyAccess]
    serializer_class = s.AllocationSerializer
    pagination_class = BillingPagination
    filterset_fields = ("payment", "invoice", "profile", "status", "source")

    def get_queryset(self):
        return PaymentAllocation.objects.select_related("invoice")

    @extend_schema(request=s.BillingReasonSerializer, responses=s.AllocationSerializer)
    @action(detail=True, methods=["post"])
    def reverse(self, request, pk=None):
        data = _valid(s.BillingReasonSerializer, request)
        allocation = _call(payments.reverse_allocation, self.get_object(), actor=request.user, reason=data["reason"])
        return Response(s.AllocationSerializer(allocation).data)


# ---------------------------------------------------------------------------
# Бронь
# ---------------------------------------------------------------------------

@extend_schema(tags=TAG)
class ReservationViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    permission_classes = [BillingAccess]
    serializer_class = s.ReservationSerializer
    pagination_class = BillingPagination
    filterset_fields = ("profile", "status")

    def get_queryset(self):
        return Reservation.objects.select_related("profile__student", "payment")

    @extend_schema(request=s.ReservationCreateSerializer, responses=s.ReservationSerializer)
    def create(self, request):
        data = dict(_valid(s.ReservationCreateSerializer, request))
        reservation = _call(reservations.create_reservation, data.pop("profile"), actor=request.user, **data)
        return Response(s.ReservationSerializer(reservation).data, status=status.HTTP_201_CREATED)

    @extend_schema(request=s.ReservationPaySerializer, responses=s.ReservationSerializer)
    @action(detail=True, methods=["post"], permission_classes=[MoneyAccess])
    def pay(self, request, pk=None):
        data = dict(_valid(s.ReservationPaySerializer, request))
        key = _idempotency_key(request, data)
        data.pop("idempotency_key", None)
        reservation, _payment, created = _call(
            reservations.record_reservation_payment, self.get_object(), actor=request.user, idempotency_key=key, **data,
        )
        reservation.refresh_from_db()
        return Response(s.ReservationSerializer(reservation).data,
                        status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)

    @extend_schema(request=s.ReservationCancelSerializer, responses=s.ReservationSerializer)
    @action(detail=True, methods=["post"], permission_classes=[MoneyAccess])
    def cancel(self, request, pk=None):
        data = _valid(s.ReservationCancelSerializer, request)
        reservation = _call(reservations.cancel_reservation, self.get_object(), actor=request.user, **data)
        return Response(s.ReservationSerializer(reservation).data)


# ---------------------------------------------------------------------------
# Работа бухгалтера
# ---------------------------------------------------------------------------

@extend_schema(tags=TAG)
class TaskViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    permission_classes = [MoneyAccess]
    serializer_class = s.TaskSerializer
    pagination_class = BillingPagination
    filterset_fields = ("status", "assignee", "profile", "invoice")

    def get_queryset(self):
        qs = BillingTask.objects.select_related("profile__student", "invoice", "assignee")
        q = self.request.query_params
        if q.get("live") in ("1", "true"):
            qs = qs.filter(status__in=BillingTask.LIVE_STATUSES)
        if q.get("due") in ("1", "true"):
            qs = qs.filter(status__in=BillingTask.LIVE_STATUSES, next_contact_date__lte=timezone.localdate())
        return qs


@extend_schema(tags=TAG)
class ContactViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    permission_classes = [MoneyAccess]
    serializer_class = s.ContactSerializer
    pagination_class = BillingPagination
    filterset_fields = ("profile", "invoice", "student", "staff", "channel", "result")

    def get_queryset(self):
        f = filters_from(self.request, invoice_status=False)
        qs = reports.filter_profiles(BillingContactLog.objects.all(), f, "profile__").select_related(
            "student", "staff", "invoice",
        )
        if f["date_from"]:
            qs = qs.filter(contacted_at__date__gte=f["date_from"])
        if f["date_to"]:
            qs = qs.filter(contacted_at__date__lte=f["date_to"])
        return qs

    @extend_schema(request=s.ContactCreateSerializer, responses=s.ContactSerializer)
    def create(self, request):
        data = dict(_valid(s.ContactCreateSerializer, request))
        log = _call(contacts.register_billing_contact, actor=request.user, **data)
        return Response(s.ContactSerializer(log).data, status=status.HTTP_201_CREATED)


@extend_schema(tags=TAG)
class NotificationViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    permission_classes = [MoneyAccess]
    serializer_class = s.NotificationSerializer
    pagination_class = BillingPagination
    filterset_fields = ("kind",)

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return BillingNotification.objects.none()
        qs = BillingNotification.objects.filter(Q(recipient__isnull=True) | Q(recipient=self.request.user))
        if self.request.query_params.get("unread") in ("1", "true"):
            qs = qs.filter(read_at__isnull=True)
        return qs

    @extend_schema(request=None, responses=s.NotificationSerializer)
    @action(detail=True, methods=["post"])
    def read(self, request, pk=None):
        notification = get_object_or_404(self.get_queryset(), pk=pk)
        if notification.read_at is None:
            notification.read_at = timezone.now()
            notification.save(update_fields=["read_at"])
        return Response(s.NotificationSerializer(notification).data)


# ---------------------------------------------------------------------------
# Панель, долги, отчёты
# ---------------------------------------------------------------------------

FILTER_PARAMS = [
    OpenApiParameter("group", int), OpenApiParameter("subject", int), OpenApiParameter("student", int),
    OpenApiParameter("accountant", int), OpenApiParameter("status", str), OpenApiParameter("date_from", str),
    OpenApiParameter("date_to", str),
]


@extend_schema(tags=TAG, parameters=FILTER_PARAMS, responses=OpenApiTypes.OBJECT)
class DashboardView(APIView):
    permission_classes = [MoneyAccess]

    def get(self, request):
        return Response(reports.dashboard(filters_from(request)))


@extend_schema(tags=TAG, parameters=FILTER_PARAMS, responses=OpenApiTypes.OBJECT)
class DebtorsView(APIView):
    """Очередь должников бухгалтера. Менеджер — 403 (видит статус оплаты в
    профиле студента)."""

    permission_classes = [MoneyAccess]

    def get(self, request):
        rows = reports.debtors(filters_from(request))
        return Response({"count": len(rows), "results": rows})


@extend_schema(tags=TAG, parameters=FILTER_PARAMS, responses=OpenApiTypes.OBJECT)
class FinancialReportView(APIView):
    permission_classes = [MoneyAccess]

    def get(self, request):
        f = filters_from(request)
        today = timezone.localdate()
        return Response(reports.financial_report(
            f, date_from=f["date_from"] or today.replace(day=1), date_to=f["date_to"] or today,
        ))


def _period_from(request) -> tuple[dt.date, dt.date]:
    """Период запроса: `month=ГГГГ-ММ` или `date_from`/`date_to` (произвольный
    диапазон); по умолчанию — текущий месяц целиком."""
    q = request.query_params
    if q.get("month"):
        return _call(periods.month_bounds, q["month"])
    date_from, date_to = _date(q.get("date_from"), "date_from"), _date(q.get("date_to"), "date_to")
    if date_from is None and date_to is None:
        return periods.month_bounds(f"{timezone.localdate():%Y-%m}")
    if date_from is None or date_to is None:
        raise ValidationError({"date_from": "Укажите начало и конец периода."})
    if date_from > date_to:
        raise ValidationError({"date_from": "Начало периода позже конца."})
    return date_from, date_to


@extend_schema(tags=TAG, responses=OpenApiTypes.OBJECT)
class PeriodsView(APIView):
    """Месяцы для переключателя периода финансового раздела."""

    permission_classes = [MoneyAccess]

    def get(self, request):
        return Response(periods.available_periods())


@extend_schema(tags=TAG, responses=OpenApiTypes.OBJECT, parameters=[
    OpenApiParameter("month", str), *FILTER_PARAMS,
])
class PeriodReportView(APIView):
    """Отчёт за выбранный период: поступления по дате денег (и за какие
    периоды), начисления по периоду начисления, долг на начало / конец и
    погашение долгов периода позже."""

    permission_classes = [MoneyAccess]

    def get(self, request):
        date_from, date_to = _period_from(request)
        f = filters_from(request)
        f.pop("date_from"), f.pop("date_to"), f.pop("status")
        return Response(_call(periods.period_report, f, date_from=date_from, date_to=date_to))


@extend_schema(tags=TAG, responses=OpenApiTypes.OBJECT)
class PeriodReviewView(APIView):
    """Начисления, период которых требует проверки (записаны днём оформления
    договора, а не его началом). POST — исправить те, у которых есть
    проверяемое основание; каждое исправление — в журнале аудита."""

    permission_classes = [MoneyAccess]

    def get(self, request):
        rows = periods.period_review()
        return Response({"count": len(rows), "results": rows})

    @extend_schema(request=s.PeriodReviewApplySerializer, responses=OpenApiTypes.OBJECT)
    def post(self, request):
        data = _valid(s.PeriodReviewApplySerializer, request)
        from .permissions import authorize

        _call(authorize, request.user, "adjust_invoice")
        changed = _call(periods.apply_period_review, actor=request.user, invoice_ids=data.get("invoices"))
        return Response({"changed": len(changed), "results": changed})


@extend_schema(tags=TAG, responses=OpenApiTypes.OBJECT)
class OptionsView(APIView):
    """Справочники для форм: тарифы, направления, группы, бухгалтеры."""

    permission_classes = [BillingAccess]

    def get(self, request):
        from apps.academy.models import Course, Group
        from apps.users.models import Subject, User

        return Response({
            "plans": [
                {"id": p.pk, "name": p.name, "subject": p.subject_id, "course": p.course_id,
                 "duration_months": p.duration_months, "allow_monthly": p.allow_monthly,
                 "allow_full_prepay": p.allow_full_prepay}
                for p in BillingPlan.objects.filter(is_active=True)
            ],
            "programs": [{"id": c.pk, "name": c.name} for c in Course.objects.only("id", "name").order_by("name")],
            "payment_methods": [{"value": v, "label": label} for v, label in StudentPayment.Method.choices],
            "payment_modes": [{"value": v, "label": label} for v, label in PaymentMode.choices],
            "reservation_modes": [{"value": v, "label": label} for v, label in ReservationAllocation.choices],
            "contract_statuses": [{"value": v, "label": label} for v, label in StudentBillingProfile.Status.choices],
            "subjects": [{"id": x.pk, "name": x.name} for x in Subject.objects.filter(is_active=True)],
            "groups": [{"id": g.pk, "name": g.name} for g in Group.objects.only("id", "name").order_by("name")]
            if (is_manager(request.user) or can_view_money(request.user)) else [],
            "accountants": [
                {"id": u.pk, "name": u.get_full_name() or u.username}
                for u in User.objects.filter(role=User.Role.ACCOUNTANT, is_active=True)
            ],
            "invoice_statuses": [{"value": v, "label": label} for v, label in Invoice.Status.choices],
            "contact_channels": [{"value": v, "label": label} for v, label in BillingContactLog.Channel.choices],
            "contact_results": [{"value": v, "label": label} for v, label in BillingContactLog.Result.choices],
        })


@extend_schema(tags=TAG, responses=OpenApiTypes.OBJECT)
class AuditView(APIView):
    """Журнал аудита операций оплаты (общий журнал бухгалтерии, записи billing_*)."""

    permission_classes = [MoneyAccess]

    def get(self, request):
        qs = PayrollAuditLog.objects.filter(action__startswith="billing_").select_related("actor")
        q = request.query_params
        if q.get("action"):
            qs = qs.filter(action=q["action"])
        if q.get("actor"):
            qs = qs.filter(actor_id=_int(q["actor"], "actor"))
        if q.get("date_from"):
            qs = qs.filter(created_at__date__gte=_date(q["date_from"], "date_from"))
        if q.get("date_to"):
            qs = qs.filter(created_at__date__lte=_date(q["date_to"], "date_to"))
        if q.get("search"):
            qs = qs.filter(Q(reason__icontains=q["search"]) | Q(action__icontains=q["search"]))
        if request.query_params.get("entity_type"):
            qs = qs.filter(entity_type=request.query_params["entity_type"])
        if request.query_params.get("entity_id"):
            qs = qs.filter(entity_id=_int(request.query_params["entity_id"], "entity_id"))
        paginator = BillingPagination()
        page = paginator.paginate_queryset(qs, request, view=self)
        return paginator.get_paginated_response([
            {"id": r.pk, "created_at": r.created_at.isoformat(),
             "actor": (r.actor.get_full_name() or r.actor.username) if r.actor_id else "Система",
             "action_display": AUDIT_LABELS.get(r.action, r.action),
             "entity_type": r.entity_type, "entity_id": r.entity_id, "action": r.action, "old_values": r.old_values,
             "new_values": r.new_values, "reason": r.reason}
            for r in page
        ])


AUDIT_LABELS = {
    "billing_plan_create": "Создана программа / тариф", "billing_plan_update": "Изменены настройки тарифа",
    "billing_plan_price": "Новая цена тарифа", "billing_profile_create": "Оформлен договор",
    "billing_profile_update": "Изменены данные договора", "billing_profile_stop": "Начисления остановлены",
    "billing_profile_pause": "Договор приостановлен", "billing_profile_resume": "Договор возобновлён",
    "billing_contract_complete": "Курс завершён", "billing_terms_apply": "Применены условия / скидка",
    "billing_terms_request": "Скидка на согласовании", "billing_terms_decide": "Решение по скидке",
    "billing_payment_mode": "Изменён способ оплаты", "billing_month_create": "Начат учебный месяц",
    "billing_package_complete": "Учебный месяц завершён", "billing_invoice_create": "Начисление",
    "billing_invoice_issue": "Начисление выставлено", "billing_invoice_void": "Начисление аннулировано",
    "billing_adjustment": "Корректировка начисления", "billing_adjustment_void": "Отмена корректировки",
    "billing_payment": "Платёж", "billing_payment_reverse": "Сторно платежа", "billing_allocate": "Распределение",
    "billing_allocation_reverse": "Сторно распределения", "billing_refund": "Возврат",
    "billing_refund_reverse": "Отмена возврата", "billing_reservation_create": "Бронь",
    "billing_reservation_paid": "Оплата брони", "billing_reservation_cancel": "Отмена брони",
    "billing_consumption_reverse": "Сторно списания урока", "billing_contact": "Контакт с родителем",
    "billing_receipt_issue": "Выдан чек", "billing_receipt_print": "Печать чека",
    "billing_receipt_cancel": "Чек аннулирован", "billing_settings_update": "Изменены настройки",
}


def _paginate(request, rows: list) -> dict:
    page = max(_int(request.query_params.get("page"), "page") or 1, 1)
    size = min(max(_int(request.query_params.get("page_size"), "page_size") or 25, 1), 200)
    start = (page - 1) * size
    return {"count": len(rows), "page": page, "page_size": size, "results": rows[start:start + size]}


def queue_filters(request) -> dict:
    q = request.query_params
    return {
        "search": (q.get("search") or "").strip(), "group": _int(q.get("group"), "group"),
        "plan": _int(q.get("plan"), "plan"), "program": _int(q.get("program"), "program"),
        "accountant": _int(q.get("accountant"), "accountant"), "ordering": q.get("ordering") or None,
        "contract_status": q.get("contract_status") or None,
    }


def contract_card(profile: StudentBillingProfile, *, with_money: bool) -> dict:
    from .services.ledger import credit_balance

    profile = queues.base_queryset().get(pk=profile.pk)
    summary = contracts.money_summary(profile)
    months = [s.PackageSerializer(p).data for p in profile.packages.all().prefetch_related("invoices")]
    data = {
        "contract": s.ProfileSerializer(_profile_qs().get(pk=profile.pk)).data,
        "row": queues.contract_row(profile, with_next=True),
        "summary": {k: (None if v is None else str(v)) for k, v in summary.items()},
        "months": months,
        "invoices": s.InvoiceSerializer(profile.invoices.exclude(status=Invoice.Status.VOID)
                                        .select_related("package", "profile__student__group", "profile__subject"),
                                        many=True).data,
        "reservations": s.ReservationSerializer(profile.reservations.select_related("payment", "profile__student"),
                                                many=True).data,
    }
    if with_money:
        payments_qs = StudentPayment.objects.filter(billing_profile=profile).select_related(
            "student", "created_by", "group", "course", "receipt").prefetch_related(
            Prefetch("billing_allocations", queryset=PaymentAllocation.objects.select_related("invoice")))
        data.update({
            "payments": s.BillingPaymentSerializer(payments_qs.order_by("-received_date", "-id"), many=True).data,
            "contacts": s.ContactSerializer(BillingContactLog.objects.filter(profile=profile)
                                            .select_related("student", "staff", "invoice")[:100], many=True).data,
            "credit": str(credit_balance(profile.pk)),
        })
    return data


@extend_schema(tags=TAG, responses=OpenApiTypes.OBJECT, parameters=[
    OpenApiParameter("search", str), OpenApiParameter("group", int), OpenApiParameter("program", int),
    OpenApiParameter("plan", int), OpenApiParameter("ordering", str), OpenApiParameter("page", int),
])
class QueueView(APIView):
    """Рабочие списки: to_pay («К оплате»), soon («Скоро оплата»), overdue
    («Просроченные»), all (все договоры). Денежные — бухгалтер и директор;
    «all» — также менеджеру (статусы без денежных операций)."""

    permission_classes = [BillingAccess]

    def get(self, request, queue: str):
        if queue not in queues.QUEUES:
            raise ValidationError({"queue": "Неизвестный список."})
        if queue != "all" and not can_view_money(request.user):
            raise PermissionDenied({"detail": "Финансовые списки доступны только бухгалтерии.", "code": "forbidden"})
        return Response(_paginate(request, queues.queue_rows(queue, queue_filters(request))))


@extend_schema(tags=TAG, responses=OpenApiTypes.OBJECT)
class QueueCountsView(APIView):
    """Бейджи sidebar: сколько студентов в «К оплате», «Скоро», «Просроченные»."""

    permission_classes = [MoneyAccess]

    def get(self, request):
        return Response(queues.counts(queue_filters(request)))


@extend_schema(tags=TAG, responses=OpenApiTypes.OBJECT, parameters=[
    OpenApiParameter("date_from", str), OpenApiParameter("date_to", str), OpenApiParameter("program", int),
    OpenApiParameter("group", int), OpenApiParameter("method", str), OpenApiParameter("status", str),
])
class AnalyticsView(APIView):
    permission_classes = [MoneyAccess]

    def get(self, request):
        q = request.query_params
        today = timezone.localdate()
        date_from = _date(q.get("date_from"), "date_from") or today.replace(day=1)
        date_to = _date(q.get("date_to"), "date_to") or today
        if date_from > date_to:
            raise ValidationError({"date_from": "Начало периода позже конца."})
        if q.get("status") and q["status"] not in Invoice.Status.values:
            raise ValidationError({"status": "Неизвестный статус начисления."})
        if q.get("method") and q["method"] not in StudentPayment.Method.values:
            raise ValidationError({"method": "Неизвестный способ оплаты."})
        f = {"program": _int(q.get("program"), "program"), "group": _int(q.get("group"), "group"),
             "plan": _int(q.get("plan"), "plan"), "method": q.get("method") or None, "status": q.get("status") or None}
        return Response(analytics.finance_analytics(f, date_from=date_from, date_to=date_to))


@extend_schema(tags=TAG)
class ReceiptViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """Чеки: список, просмотр, PDF (A4 или компактный). Повторная печать не
    создаёт ни платежа, ни чека."""

    permission_classes = [MoneyAccess]
    serializer_class = s.ReceiptSerializer
    pagination_class = BillingPagination
    filterset_fields = ("profile", "kind", "status")
    search_fields = ("number", "payment__student__first_name", "payment__student__last_name", "payer_name")

    def get_queryset(self):
        qs = Receipt.objects.select_related("payment__student", "issued_by", "profile")
        q = self.request.query_params
        if q.get("date_from"):
            qs = qs.filter(issued_at__date__gte=_date(q["date_from"], "date_from"))
        if q.get("date_to"):
            qs = qs.filter(issued_at__date__lte=_date(q["date_to"], "date_to"))
        return qs

    @extend_schema(responses={(200, "application/pdf"): OpenApiTypes.BINARY},
                   parameters=[OpenApiParameter("format", str, description="a4 | compact")])
    @action(detail=True, methods=["get"])
    def pdf(self, request, pk=None):
        from .services.receipt_pdf import render_receipt_pdf

        receipt = self.get_object()
        compact = request.query_params.get("size") == "compact"
        content = render_receipt_pdf(receipt, compact=compact)
        receipts.mark_printed(receipt, actor=request.user)
        response = HttpResponse(content, content_type="application/pdf")
        response["Content-Disposition"] = f'inline; filename="receipt-{receipt.number}.pdf"'
        return response

    @extend_schema(request=None, responses=s.ReceiptSerializer)
    @action(detail=True, methods=["post"])
    def printed(self, request, pk=None):
        """Отметить печать HTML-версии (счётчик и журнал)."""
        return Response(s.ReceiptSerializer(receipts.mark_printed(self.get_object(), actor=request.user)).data)


@extend_schema(tags=TAG, request=s.BillingSettingsSerializer, responses=s.BillingSettingsSerializer)
class SettingsView(APIView):
    """Настройки оплаты: читать — бухгалтер и директор, менять — бухгалтер."""

    permission_classes = [MoneyAccess]

    def get(self, request):
        from .models import BillingSettings

        return Response(s.BillingSettingsSerializer(BillingSettings.load()).data)

    def patch(self, request):
        data = _valid(s.BillingSettingsSerializer, request, partial=True)
        obj = _call(billing_settings.update_settings, actor=request.user, **data)
        return Response(s.BillingSettingsSerializer(obj).data)
