"""API оплаты обучения (/api/v1/accounting/billing/). Представления только
проверяют права, валидируют ввод и вызывают сервисы. Права проверяются и
здесь (DRF), и в каждом сервисе (`permissions.authorize`)."""
from __future__ import annotations

import datetime as dt
from decimal import Decimal

from django.db.models import Prefetch, Q, Sum
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
    Reservation,
    StudentBillingProfile,
)
from .permissions import BillingAccess, MoneyAccess, can_view_money, capabilities, is_manager
from .services import BillingError, contacts, invoices, lessons, payments, pricing, profiles, reports, reservations

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
        data = dict(_valid(s.ProfileCreateSerializer, request))
        profile = _call(profiles.create_student_billing_profile, actor=request.user, **data)
        return Response(s.ProfileSerializer(_profile_qs().get(pk=profile.pk)).data, status=status.HTTP_201_CREATED)

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
        "plan_name": profile.plan.name, "payment_state": state, "debt": str(debt),
        "unpaid_invoices": len(unpaid), "credit": str(profile.credit or Decimal("0.00")),
        "next_due": min((i.due_date for i in unpaid), default=None),
        "package": None if package is None else {
            "number": package.number, "used": package.lessons_used, "total": package.lessons_total,
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
        live = ~Q(billing_profiles__status=StudentBillingProfile.Status.INACTIVE)
        if q.get("registered") == "yes":
            qs = qs.filter(billing_profiles__isnull=False).filter(live).distinct()
        elif q.get("registered") == "no":
            qs = qs.exclude(pk__in=StudentBillingProfile.objects.exclude(
                status=StudentBillingProfile.Status.INACTIVE).values("student_id"))
        if q.get("state") == "debt":
            qs = qs.filter(billing_profiles__invoices__status__in=Invoice.UNPAID_STATUSES).distinct()
        elif q.get("state") == "overdue":
            qs = qs.filter(billing_profiles__invoices__status=Invoice.Status.OVERDUE).distinct()
        profiles = (
            StudentBillingProfile.objects.exclude(status=StudentBillingProfile.Status.INACTIVE)
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
    ordering_fields = ("due_date", "issue_date", "amount")

    def get_serializer_class(self):
        return s.InvoiceDetailSerializer if self.action == "retrieve" else s.InvoiceSerializer

    def get_queryset(self):
        f = filters_from(self.request)
        qs = reports.invoices_qs(f).select_related("profile__student__group", "profile__subject", "package")
        if f["date_from"]:
            qs = qs.filter(issue_date__gte=f["date_from"])
        if f["date_to"]:
            qs = qs.filter(issue_date__lte=f["date_to"])
        q = self.request.query_params
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
    filterset_fields = ("billing_profile", "kind", "status", "purpose", "method")
    search_fields = ("student__first_name", "student__last_name", "reference")

    def get_queryset(self):
        f = filters_from(self.request, invoice_status=False)
        qs = StudentPayment.objects.filter(billing_profile__isnull=False).select_related("student", "created_by")
        qs = reports.filter_profiles(qs, f, "billing_profile__").prefetch_related(
            Prefetch("billing_allocations", queryset=PaymentAllocation.objects.select_related("invoice")),
        )
        if f["date_from"]:
            qs = qs.filter(received_date__gte=f["date_from"])
        if f["date_to"]:
            qs = qs.filter(received_date__lte=f["date_to"])
        return qs.order_by("-received_date", "-id")

    @extend_schema(request=s.PaymentCreateSerializer, responses=s.BillingPaymentSerializer,
                   parameters=[OpenApiParameter("Idempotency-Key", str, OpenApiParameter.HEADER)])
    def create(self, request):
        data = dict(_valid(s.PaymentCreateSerializer, request))
        key = _idempotency_key(request, data)
        data.pop("idempotency_key", None)
        items = [(row["invoice"], row["amount"]) for row in data.pop("allocations", None) or []]
        payment, created = _call(
            payments.record_payment, profile=data.pop("profile"), actor=request.user, idempotency_key=key,
            allocations=items or None, **data,
        )
        payment = self.get_queryset().get(pk=payment.pk)
        return Response(s.BillingPaymentSerializer(payment).data,
                        status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)

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


@extend_schema(tags=TAG, responses=OpenApiTypes.OBJECT)
class OptionsView(APIView):
    """Справочники для форм: тарифы, направления, группы, бухгалтеры."""

    permission_classes = [BillingAccess]

    def get(self, request):
        from apps.academy.models import Group
        from apps.users.models import Subject, User

        return Response({
            "plans": [{"id": p.pk, "name": p.name, "subject": p.subject_id} for p in BillingPlan.objects.filter(is_active=True)],
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
        if request.query_params.get("entity_type"):
            qs = qs.filter(entity_type=request.query_params["entity_type"])
        if request.query_params.get("entity_id"):
            qs = qs.filter(entity_id=_int(request.query_params["entity_id"], "entity_id"))
        paginator = BillingPagination()
        page = paginator.paginate_queryset(qs, request, view=self)
        return paginator.get_paginated_response([
            {"id": r.pk, "created_at": r.created_at.isoformat(), "actor": str(r.actor) if r.actor_id else None,
             "entity_type": r.entity_type, "entity_id": r.entity_id, "action": r.action, "old_values": r.old_values,
             "new_values": r.new_values, "reason": r.reason}
            for r in page
        ])
