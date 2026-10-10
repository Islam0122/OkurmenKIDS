"""API бухгалтерии (/api/v1/accounting/). Представления только проверяют
права, валидируют ввод и вызывают сервисы — расчётов здесь нет."""
from __future__ import annotations

from decimal import Decimal

from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.academy.models import Course, Group, Student
from apps.users.models import User

from . import serializers as s
from .filters import filter_payrolls
from .models import (
    EmployeeSalaryProfile,
    Payroll,
    PayrollAdjustment,
    PayrollAuditLog,
    PayrollPayment,
    PayrollPeriod,
    SalaryRule,
    SalaryType,
    StudentPayment,
)
from .permissions import AccountingAccess, CanApprove, CanViewAccounting, capabilities
from .services import AccountingError
from .services import approval_service, payment_service, payroll_calculator, report_service, salary_rules
from .services import student_payments as student_payment_service
from .services.periods import close_period, get_or_create_period
from .services.report_pdf import render_individual_pdf, render_period_pdf
from .services.report_xlsx import render_individual_xlsx, render_period_xlsx

TAG = ["Accounting"]


class AccountingPagination(PageNumberPagination):
    page_size = 50
    page_size_query_param = "page_size"
    max_page_size = 500


def _fail(exc: AccountingError):
    raise ValidationError({"detail": exc.message, "code": exc.code})


def _valid(serializer_class, request, **kwargs):
    serializer = serializer_class(data=request.data, **kwargs)
    serializer.is_valid(raise_exception=True)
    return serializer.validated_data


def _idempotency_key(request, data) -> str | None:
    return data.get("idempotency_key") or request.headers.get("Idempotency-Key")


def _int(value, name):
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        raise ValidationError({name: "Ожидается число."})


def _periods_from_query(request, *, required=True):
    q = request.query_params
    period_id = _int(q.get("period"), "period")
    year, month = _int(q.get("year"), "year"), _int(q.get("month"), "month")
    if not period_id and not (year and month):
        if required:
            raise ValidationError({"detail": "Укажите period или year и month."})
        today = timezone.localdate()
        year, month = today.year, today.month
    return report_service.resolve_periods(
        period_id=period_id, year=year, month=month, period_type=q.get("period_type") or None,
    )


def _str(value):
    """Суммы в JSON — строками, как у сериализаторов DRF (без потерь float)."""
    return None if value is None else str(value)


def _money_str(data: dict) -> dict:
    return {k: str(v) if isinstance(v, Decimal) else v for k, v in data.items()}


def _file(content: bytes, filename: str, content_type: str) -> HttpResponse:
    response = HttpResponse(content, content_type=content_type)
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    response["Cache-Control"] = "no-store"
    return response


PDF = "application/pdf"
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


# ---------------------------------------------------------------------------
# Сводка, справочники
# ---------------------------------------------------------------------------

@extend_schema(tags=TAG)
class MeView(APIView):
    """Права текущего пользователя в бухгалтерии (для интерфейса)."""

    permission_classes = [IsAuthenticated]

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request):
        return Response(capabilities(request.user))


@extend_schema(tags=TAG, parameters=[
    OpenApiParameter("period", int), OpenApiParameter("year", int), OpenApiParameter("month", int),
    OpenApiParameter("period_type", str),
])
class DashboardView(APIView):
    permission_classes = [CanViewAccounting]

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request):
        periods, label = _periods_from_query(request, required=False)
        data = _money_str(report_service.dashboard(periods))
        data["outstanding_debt_all_periods"] = str(report_service.outstanding_debt())
        data["range_label"] = label
        data["periods"] = s.PayrollPeriodSerializer(periods, many=True).data
        return Response(data)


@extend_schema(tags=TAG)
class OptionsView(APIView):
    permission_classes = [CanViewAccounting]

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request):
        users = User.objects.filter(is_active=True).exclude(role=User.Role.ADMIN).order_by("last_name", "first_name")
        return Response({
            "employees": s.UserRefSerializer(users, many=True).data,
            "courses": s.CourseRefSerializer(Course.objects.order_by("name"), many=True).data,
            "groups": s.GroupRefSerializer(Group.objects.order_by("name"), many=True).data,
            "salary_types": [{"value": v, "label": l} for v, l in SalaryType.choices],
            "rule_types": [{"value": v, "label": l} for v, l in SalaryRule.RuleType.choices],
            "methods": {
                rt: [{"value": m, "label": SalaryRule.Method(m).label} for m in methods]
                for rt, methods in SalaryRule.METHODS_BY_TYPE.items()
            },
            "revenue_bases": [{"value": v, "label": l} for v, l in SalaryRule.RevenueBasis.choices],
            "refund_policies": [{"value": v, "label": l} for v, l in SalaryRule.RefundPolicy.choices],
            "payment_methods": [{"value": v, "label": l} for v, l in PayrollPayment.Method.choices],
            "student_payment_methods": [{"value": v, "label": l} for v, l in StudentPayment.Method.choices],
            "adjustment_kinds": [{"value": v, "label": l} for v, l in PayrollAdjustment.Kind.choices],
            "payroll_statuses": [{"value": v, "label": l} for v, l in Payroll.Status.choices],
            **capabilities(request.user),
        })


@extend_schema(tags=TAG, parameters=[OpenApiParameter("search", str)])
class StudentLookupView(APIView):
    permission_classes = [CanViewAccounting]

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request):
        term = (request.query_params.get("search") or "").strip()
        qs = Student.objects.select_related("group")
        for part in term.split():
            qs = qs.filter(Q(first_name__icontains=part) | Q(last_name__icontains=part))
        return Response([
            {"id": st.pk, "name": str(st), "group": st.group_id, "group_name": st.group.name if st.group else None,
             "status": st.status}
            for st in qs.order_by("last_name", "first_name")[:30]
        ])


# ---------------------------------------------------------------------------
# Сотрудники и правила
# ---------------------------------------------------------------------------

@extend_schema(tags=TAG, parameters=[
    OpenApiParameter("period", int), OpenApiParameter("year", int), OpenApiParameter("month", int),
    OpenApiParameter("period_type", str), OpenApiParameter("search", str), OpenApiParameter("salary_type", str),
    OpenApiParameter("program", int), OpenApiParameter("group", int), OpenApiParameter("payment_status", str),
    OpenApiParameter("employee", int),
])
class EmployeeListView(APIView):
    """Список сотрудников с зарплатными настройками и итогами за период."""

    permission_classes = [CanViewAccounting]

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request):
        q = request.query_params
        periods, label = _periods_from_query(request, required=False)
        profiles = EmployeeSalaryProfile.objects.select_related("employee", "employee__teacher_profile").prefetch_related(
            "rules__group", "rules__program",
        )
        if q.get("search"):
            for part in q["search"].split():
                profiles = profiles.filter(Q(employee__first_name__icontains=part) | Q(employee__last_name__icontains=part))
        if q.get("salary_type"):
            profiles = profiles.filter(salary_type=q["salary_type"])
        if q.get("employee"):
            profiles = profiles.filter(employee_id=_int(q["employee"], "employee"))
        if q.get("program"):
            profiles = profiles.filter(Q(rules__program_id=_int(q["program"], "program")) | Q(
                rules__group__course_id=_int(q["program"], "program"))).distinct()
        if q.get("group"):
            profiles = profiles.filter(rules__group_id=_int(q["group"], "group")).distinct()
        payrolls = {
            p.employee_id: p for p in report_service.with_totals(
                Payroll.objects.filter(period__in=periods).exclude(status=Payroll.Status.VOID)
            ).select_related("period")
        } if len(periods) == 1 else {}
        sums: dict[int, dict] = {}
        for p in report_service.with_totals(Payroll.objects.filter(period__in=periods).exclude(status=Payroll.Status.VOID)):
            row = sums.setdefault(p.employee_id, {"accrued": 0, "paid": 0, "due": 0, "statuses": set()})
            row["accrued"] += p.r_accrued + p.r_adjustments
            row["paid"] += p.r_paid
            row["due"] += p.r_accrued + p.r_adjustments - p.r_paid
            row["statuses"].add(p.status)
        result = []
        payment_status = q.get("payment_status")
        for profile in profiles:
            agg = sums.get(profile.employee_id)
            payroll = payrolls.get(profile.employee_id)
            today = timezone.localdate()
            active_rules = [r for r in profile.rules.all()
                            if r.is_active and (r.effective_to is None or r.effective_to >= today)]
            status_value = payroll.status if payroll else (
                "MIXED" if agg and len(agg["statuses"]) > 1 else (next(iter(agg["statuses"])) if agg else None)
            )
            if payment_status and status_value != payment_status:
                continue
            result.append({
                "profile_id": profile.pk,
                "employee": profile.employee_id,
                "employee_name": profile.employee.get_full_name() or profile.employee.username,
                "position": profile.display_position,
                "salary_type": profile.salary_type,
                "salary_type_display": profile.get_salary_type_display(),
                "is_active": profile.is_active,
                "rates": [
                    {"rule_type": r.rule_type, "label": r.get_rule_type_display(),
                     "amount": _str(r.amount), "percentage": _str(r.percentage), "scope": (r.group.name if r.group_id else (r.program.name if r.program_id else ""))}
                    for r in active_rules
                ],
                "active_students": payroll.active_students if payroll else None,
                "payroll_id": payroll.pk if payroll else None,
                "accrued": _str(agg["accrued"]) if agg else None,
                "paid": _str(agg["paid"]) if agg else None,
                "due": _str(agg["due"]) if agg else None,
                "status": status_value,
                "status_display": payroll.get_status_display() if payroll else None,
            })
        return Response({"range_label": label, "results": result})


@extend_schema(tags=TAG)
class SalaryProfileViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.CreateModelMixin,
                           mixins.UpdateModelMixin, viewsets.GenericViewSet):
    pagination_class = AccountingPagination
    permission_classes = [AccountingAccess]
    serializer_class = s.EmployeeSalaryProfileSerializer
    search_fields = ("employee__first_name", "employee__last_name")
    filterset_fields = ("salary_type", "is_active", "employee")

    def get_queryset(self):
        return EmployeeSalaryProfile.objects.select_related("employee", "employee__teacher_profile").prefetch_related(
            "rules__program", "rules__group", "rules__employee_profile__employee", "rules__next_version",
        )

    def perform_create(self, serializer):
        try:
            serializer.instance = salary_rules.save_profile(
                EmployeeSalaryProfile(), actor=self.request.user, data=serializer.validated_data,
            )
        except AccountingError as exc:
            _fail(exc)

    def perform_update(self, serializer):
        try:
            serializer.instance = salary_rules.save_profile(
                serializer.instance, actor=self.request.user, data=serializer.validated_data,
            )
        except AccountingError as exc:
            _fail(exc)


@extend_schema(tags=TAG)
class SalaryRuleViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """Правила не редактируются и не удаляются: создание, новая версия,
    прекращение действия."""

    pagination_class = AccountingPagination
    permission_classes = [AccountingAccess]
    serializer_class = s.SalaryRuleSerializer
    filterset_fields = ("employee_profile", "rule_type", "program", "group", "is_active")

    def get_queryset(self):
        qs = SalaryRule.objects.select_related("program", "group", "employee_profile__employee", "next_version")
        employee = self.request.query_params.get("employee")
        if employee:
            qs = qs.filter(employee_profile__employee_id=_int(employee, "employee"))
        return qs

    @extend_schema(request=s.SalaryRuleCreateSerializer, responses=s.SalaryRuleSerializer)
    def create(self, request):
        data = _valid(s.SalaryRuleCreateSerializer, request)
        try:
            rule = salary_rules.create_rule(actor=request.user, data=data)
        except AccountingError as exc:
            _fail(exc)
        return Response(s.SalaryRuleSerializer(rule).data, status=status.HTTP_201_CREATED)

    @extend_schema(request=s.SalaryRuleVersionSerializer, responses=s.SalaryRuleSerializer)
    @action(detail=True, methods=["post"], url_path="new-version")
    def new_version(self, request, pk=None):
        data = _valid(s.SalaryRuleVersionSerializer, request)
        try:
            rule = salary_rules.new_version(self.get_object(), actor=request.user, changes=data)
        except AccountingError as exc:
            _fail(exc)
        return Response(s.SalaryRuleSerializer(rule).data, status=status.HTTP_201_CREATED)

    @extend_schema(request=s.SalaryRuleDeactivateSerializer, responses=s.SalaryRuleSerializer)
    @action(detail=True, methods=["post"])
    def deactivate(self, request, pk=None):
        data = _valid(s.SalaryRuleDeactivateSerializer, request)
        try:
            rule = salary_rules.deactivate_rule(self.get_object(), actor=request.user, **data)
        except AccountingError as exc:
            _fail(exc)
        return Response(s.SalaryRuleSerializer(rule).data)


# ---------------------------------------------------------------------------
# Платежи студентов
# ---------------------------------------------------------------------------

@extend_schema(tags=TAG)
class StudentPaymentViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    pagination_class = AccountingPagination
    permission_classes = [AccountingAccess]
    serializer_class = s.StudentPaymentSerializer
    filterset_fields = ("student", "group", "course", "kind", "status", "method")
    search_fields = ("student__first_name", "student__last_name", "reference")
    ordering_fields = ("received_date", "amount", "created_at")

    def get_queryset(self):
        qs = StudentPayment.objects.select_related("student", "group", "course", "created_by").prefetch_related("refunds")
        q = self.request.query_params
        if q.get("date_from"):
            qs = qs.filter(received_date__gte=q["date_from"])
        if q.get("date_to"):
            qs = qs.filter(received_date__lte=q["date_to"])
        return qs

    @extend_schema(request=s.StudentPaymentCreateSerializer, responses=s.StudentPaymentSerializer)
    def create(self, request):
        data = _valid(s.StudentPaymentCreateSerializer, request)
        key = _idempotency_key(request, data)
        data.pop("idempotency_key", None)
        try:
            payment, created = student_payment_service.record_payment(actor=request.user, idempotency_key=key, **data)
        except AccountingError as exc:
            _fail(exc)
        return Response(s.StudentPaymentSerializer(payment).data,
                        status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)

    @extend_schema(request=s.ReasonSerializer, responses=s.StudentPaymentSerializer)
    @action(detail=True, methods=["post"])
    def void(self, request, pk=None):
        data = _valid(s.ReasonSerializer, request)
        try:
            payment, affected = student_payment_service.void_student_payment(
                self.get_object(), actor=request.user, reason=data["reason"],
            )
        except AccountingError as exc:
            _fail(exc)
        body = s.StudentPaymentSerializer(payment).data
        body["affected_payrolls"] = affected
        return Response(body)


# ---------------------------------------------------------------------------
# Периоды
# ---------------------------------------------------------------------------

@extend_schema(tags=TAG)
class PayrollPeriodViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    pagination_class = AccountingPagination
    permission_classes = [AccountingAccess]
    serializer_class = s.PayrollPeriodSerializer
    queryset = PayrollPeriod.objects.all()
    filterset_fields = ("year", "month", "period_type", "status")

    @extend_schema(request=s.PayrollPeriodCreateSerializer, responses=s.PayrollPeriodSerializer)
    def create(self, request):
        """Создать период (или вернуть существующий — повторный запрос не создаёт дубликат)."""
        d = _valid(s.PayrollPeriodCreateSerializer, request)
        try:
            period, created = get_or_create_period(d["year"], d["month"], d["period_type"], request.user)
        except AccountingError as exc:
            _fail(exc)
        return Response(s.PayrollPeriodSerializer(period).data,
                        status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)

    @action(detail=True, methods=["post"])
    def calculate(self, request, pk=None):
        """Массовый расчёт по всем сотрудникам с действующими правилами."""
        period = self.get_object()
        if period.status == PayrollPeriod.Status.CLOSED:
            _fail(AccountingError("Период закрыт."))
        result = payroll_calculator.calculate_period(period, request.user)
        return Response({
            "period": s.PayrollPeriodSerializer(PayrollPeriod.objects.get(pk=period.pk)).data,
            "calculated": s.PayrollListSerializer(result["calculated"], many=True).data,
            "skipped": result["skipped"],
            "failed": result["failed"],
        })

    @action(detail=True, methods=["post"], permission_classes=[CanApprove])
    def approve(self, request, pk=None):
        """Утвердить все рассчитанные начисления периода без ошибок."""
        result = approval_service.approve_period(self.get_object(), request.user)
        return Response({
            "approved": [p.pk for p in result["approved"]],
            "failed": result["failed"],
            "period": s.PayrollPeriodSerializer(PayrollPeriod.objects.get(pk=pk)).data,
        })

    @extend_schema(request=s.ReasonSerializer)
    @action(detail=True, methods=["post"], permission_classes=[CanApprove])
    def close(self, request, pk=None):
        try:
            period = close_period(self.get_object(), request.user, reason=request.data.get("reason", ""))
        except AccountingError as exc:
            _fail(exc)
        return Response(s.PayrollPeriodSerializer(period).data)


# ---------------------------------------------------------------------------
# Начисления
# ---------------------------------------------------------------------------

@extend_schema(tags=TAG)
class PayrollViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    pagination_class = AccountingPagination
    permission_classes = [AccountingAccess]
    serializer_class = s.PayrollListSerializer
    filterset_fields = ("period", "employee", "status", "salary_type")
    search_fields = ("employee__first_name", "employee__last_name")
    ordering_fields = ("total_accrued", "amount_due", "employee__last_name")

    def get_queryset(self):
        qs = Payroll.objects.select_related("employee", "period", "approved_by")
        if self.action == "retrieve":
            qs = qs.prefetch_related("lines", "payments__created_by", "adjustments__created_by",
                                     "adjustments__decided_by")
        return filter_payrolls(qs, self.request.query_params)

    def get_serializer_class(self):
        return s.PayrollDetailSerializer if self.action == "retrieve" else s.PayrollListSerializer

    def _detail(self, payroll, code=status.HTTP_200_OK):
        payroll = self.get_queryset().model.objects.select_related("employee", "period", "approved_by").get(pk=payroll.pk)
        return Response(s.PayrollDetailSerializer(payroll).data, status=code)

    @extend_schema(request=None, responses=s.PayrollDetailSerializer)
    @action(detail=False, methods=["post"])
    def calculate(self, request):
        """Рассчитать одного сотрудника: {period, employee}."""
        period = get_object_or_404(PayrollPeriod, pk=_int(request.data.get("period"), "period"))
        employee = get_object_or_404(User, pk=_int(request.data.get("employee"), "employee"))
        try:
            payroll = payroll_calculator.calculate_payroll(period, employee, request.user)
        except AccountingError as exc:
            _fail(exc)
        return self._detail(payroll)

    @extend_schema(request=None, responses=s.PayrollDetailSerializer)
    @action(detail=True, methods=["post"])
    def recalculate(self, request, pk=None):
        payroll = self.get_object()
        try:
            payroll = payroll_calculator.calculate_payroll(payroll.period, payroll.employee, request.user)
        except AccountingError as exc:
            _fail(exc)
        return self._detail(payroll)

    @extend_schema(request=None, responses=s.PayrollDetailSerializer)
    @action(detail=True, methods=["post"], permission_classes=[CanApprove])
    def approve(self, request, pk=None):
        try:
            payroll = approval_service.approve_payroll(self.get_object(), request.user)
        except AccountingError as exc:
            _fail(exc)
        return self._detail(payroll)

    @extend_schema(request=s.ReasonSerializer, responses=s.PayrollDetailSerializer)
    @action(detail=True, methods=["post"], url_path="return", permission_classes=[CanApprove])
    def return_for_fix(self, request, pk=None):
        data = _valid(s.ReasonSerializer, request)
        try:
            payroll = approval_service.return_payroll(self.get_object(), request.user, data["reason"])
        except AccountingError as exc:
            _fail(exc)
        return self._detail(payroll)

    @extend_schema(request=s.ReasonSerializer, responses=s.PayrollDetailSerializer)
    @action(detail=True, methods=["post"], permission_classes=[CanApprove])
    def reopen(self, request, pk=None):
        data = _valid(s.ReasonSerializer, request)
        try:
            payroll = approval_service.reopen_payroll(self.get_object(), request.user, data["reason"])
        except AccountingError as exc:
            _fail(exc)
        return self._detail(payroll)

    @extend_schema(request=s.ReasonSerializer, responses=s.PayrollDetailSerializer)
    @action(detail=True, methods=["post"])
    def void(self, request, pk=None):
        data = _valid(s.ReasonSerializer, request)
        try:
            payroll = approval_service.void_payroll(self.get_object(), request.user, data["reason"])
        except AccountingError as exc:
            _fail(exc)
        return self._detail(payroll)

    @extend_schema(request=s.PayrollPaymentCreateSerializer, responses=s.PayrollPaymentSerializer)
    @action(detail=True, methods=["get", "post"])
    def payments(self, request, pk=None):
        payroll = self.get_object()
        if request.method == "GET":
            return Response(s.PayrollPaymentSerializer(payroll.payments.select_related("created_by"), many=True).data)
        data = _valid(s.PayrollPaymentCreateSerializer, request)
        key = _idempotency_key(request, data)
        data.pop("idempotency_key", None)
        try:
            payment, created = payment_service.register_payment(payroll, actor=request.user, idempotency_key=key, **data)
        except AccountingError as exc:
            _fail(exc)
        return Response(s.PayrollPaymentSerializer(payment).data,
                        status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)

    @extend_schema(request=s.PayrollAdjustmentCreateSerializer, responses=s.PayrollAdjustmentSerializer)
    @action(detail=True, methods=["get", "post"])
    def adjustments(self, request, pk=None):
        payroll = self.get_object()
        if request.method == "GET":
            return Response(s.PayrollAdjustmentSerializer(payroll.adjustments.all(), many=True).data)
        data = _valid(s.PayrollAdjustmentCreateSerializer, request)
        try:
            adjustment = approval_service.create_adjustment(payroll, actor=request.user, **data)
        except AccountingError as exc:
            _fail(exc)
        return Response(s.PayrollAdjustmentSerializer(adjustment).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["get"], url_path="report.pdf")
    def report_pdf(self, request, pk=None):
        report = report_service.build_individual(self.get_object())
        return _file(render_individual_pdf(report), f"payroll-{pk}.pdf", PDF)

    @action(detail=True, methods=["get"], url_path="report.xlsx")
    def report_xlsx(self, request, pk=None):
        report = report_service.build_individual(self.get_object())
        return _file(render_individual_xlsx(report), f"payroll-{pk}.xlsx", XLSX)


@extend_schema(tags=TAG)
class PaymentViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """История выплат сотрудникам."""

    pagination_class = AccountingPagination
    permission_classes = [AccountingAccess]
    serializer_class = s.PayrollPaymentSerializer
    filterset_fields = ("payroll", "status", "payment_method", "payroll__employee", "payroll__period")

    def get_queryset(self):
        return PayrollPayment.objects.select_related("created_by", "payroll").order_by("-payment_date", "-id")

    @extend_schema(request=s.ReasonSerializer, responses=s.PayrollPaymentSerializer)
    @action(detail=True, methods=["post"])
    def void(self, request, pk=None):
        data = _valid(s.ReasonSerializer, request)
        try:
            payment = payment_service.void_payment(self.get_object(), actor=request.user, reason=data["reason"])
        except AccountingError as exc:
            _fail(exc)
        return Response(s.PayrollPaymentSerializer(payment).data)


@extend_schema(tags=TAG)
class AdjustmentViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    pagination_class = AccountingPagination
    permission_classes = [AccountingAccess]
    serializer_class = s.PayrollAdjustmentSerializer
    filterset_fields = ("payroll", "status", "kind", "payroll__period")

    def get_queryset(self):
        return PayrollAdjustment.objects.select_related("created_by", "decided_by")

    @extend_schema(request=s.AdjustmentDecisionSerializer, responses=s.PayrollAdjustmentSerializer)
    @action(detail=True, methods=["post"], permission_classes=[CanApprove])
    def decide(self, request, pk=None):
        data = _valid(s.AdjustmentDecisionSerializer, request)
        try:
            adjustment = approval_service.decide_adjustment(self.get_object(), actor=request.user, **data)
        except AccountingError as exc:
            _fail(exc)
        return Response(s.PayrollAdjustmentSerializer(adjustment).data)

    @extend_schema(request=s.ReasonSerializer, responses=s.PayrollAdjustmentSerializer)
    @action(detail=True, methods=["post"])
    def void(self, request, pk=None):
        data = _valid(s.ReasonSerializer, request)
        try:
            adjustment = approval_service.void_adjustment(self.get_object(), actor=request.user, reason=data["reason"])
        except AccountingError as exc:
            _fail(exc)
        return Response(s.PayrollAdjustmentSerializer(adjustment).data)


@extend_schema(tags=TAG)
class AuditLogViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """Журнал аудита — только чтение для всех ролей."""

    pagination_class = AccountingPagination
    permission_classes = [CanViewAccounting]
    serializer_class = s.PayrollAuditLogSerializer
    filterset_fields = ("entity_type", "entity_id", "action", "actor", "payroll")

    def get_queryset(self):
        return PayrollAuditLog.objects.select_related("actor")


# ---------------------------------------------------------------------------
# Отчёты
# ---------------------------------------------------------------------------

def _report(request):
    periods, label = _periods_from_query(request)
    payrolls = filter_payrolls(Payroll.objects.filter(period__in=periods), request.query_params)
    return report_service.build_report(periods, label=label, payrolls=payrolls)


def _slug(request) -> str:
    q = request.query_params
    if q.get("period"):
        return f"period-{q['period']}"
    return f"{q.get('year')}-{int(q.get('month')):02d}" + (f"-{q['period_type'].lower()}" if q.get("period_type") else "")


@extend_schema(tags=TAG, parameters=[
    OpenApiParameter("period", int), OpenApiParameter("year", int), OpenApiParameter("month", int),
    OpenApiParameter("period_type", str), OpenApiParameter("employee", int), OpenApiParameter("status", str),
])
class PayrollReportPdfView(APIView):
    permission_classes = [CanViewAccounting]

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request):
        return _file(render_period_pdf(_report(request)), f"payroll-{_slug(request)}.pdf", PDF)


@extend_schema(tags=TAG, parameters=[
    OpenApiParameter("period", int), OpenApiParameter("year", int), OpenApiParameter("month", int),
    OpenApiParameter("period_type", str), OpenApiParameter("employee", int), OpenApiParameter("status", str),
])
class PayrollReportXlsxView(APIView):
    permission_classes = [CanViewAccounting]

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request):
        return _file(render_period_xlsx(_report(request)), f"payroll-{_slug(request)}.xlsx", XLSX)


# ---------------------------------------------------------------------------
# Личный кабинет сотрудника — только собственные утверждённые начисления
# ---------------------------------------------------------------------------

@extend_schema(tags=TAG)
class MyPayrollViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    pagination_class = AccountingPagination
    permission_classes = [IsAuthenticated]
    serializer_class = s.OwnPayrollSerializer

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Payroll.objects.none()
        return (
            Payroll.objects.filter(employee=self.request.user, status__in=Payroll.LOCKED_STATUSES)
            .select_related("employee", "period", "approved_by").prefetch_related("lines", "payments", "adjustments")
        )

    def get_serializer_context(self):
        return {**super().get_serializer_context(), "include_audit": False}

    @action(detail=True, methods=["get"], url_path="report.pdf")
    def report_pdf(self, request, pk=None):
        report = report_service.build_individual(self.get_object())
        return _file(render_individual_pdf(report), f"payroll-{pk}.pdf", PDF)
