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
from apps.users.models import Subject, User

from . import serializers as s
from .filters import filter_payrolls
from .models import (
    ALLOWED_SALARY_TYPES,
    CourseCycle,
    CoursePayrollSettings,
    CoursePriceVersion,
    CycleAccrual,
    Department,
    EmployeeSalaryProfile,
    Payroll,
    PayrollAdjustment,
    PayrollAuditLog,
    PayrollPayment,
    PayrollPeriod,
    SalaryRule,
    StudentPayment,
)
from .permissions import AccountingAccess, CanApprove, CanViewAccounting, capabilities
from .services import AccountingError
from .services import approval_service, cycles, payment_service, payroll_calculator, report_service, salary_rules
from .services import student_payments as student_payment_service
from .services.periods import close_period, get_or_create_period
from .services import analytics, estimates, my_salary, pricing
from .services.report_pdf import (
    render_individual_pdf,
    render_my_salary_pdf,
    render_period_pdf,
    render_teacher_report_pdf,
)
from .services.report_xlsx import render_individual_xlsx, render_period_xlsx, render_teacher_report_xlsx

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
        data["open_cycles"] = CourseCycle.objects.filter(status=CourseCycle.Status.IN_PROGRESS).count()
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
            "salary_types": [{"value": t.value, "label": t.label} for t in ALLOWED_SALARY_TYPES],
            "rule_types": [{"value": t.value, "label": t.label} for t in SalaryRule.ACTIVE_TYPES],
            "methods": {
                rt: [{"value": m, "label": SalaryRule.Method(m).label} for m in SalaryRule.METHODS_BY_TYPE[rt]]
                for rt in SalaryRule.ACTIVE_TYPES
            },
            "student_count_rules": [
                {"value": v, "label": l} for v, l in CoursePayrollSettings.StudentCountRule.choices
            ],
            "payment_methods": [{"value": v, "label": l} for v, l in PayrollPayment.Method.choices],
            "student_payment_methods": [{"value": v, "label": l} for v, l in StudentPayment.Method.choices],
            "adjustment_kinds": [{"value": v, "label": l} for v, l in PayrollAdjustment.Kind.choices],
            "payroll_statuses": [{"value": v, "label": l} for v, l in Payroll.Status.choices],
            "departments": [{"value": v, "label": l} for v, l in Department.choices],
            "subjects": [{"id": sub.pk, "name": sub.name} for sub in Subject.objects.order_by("name")],
            **capabilities(request.user),
        })


@extend_schema(tags=TAG, parameters=[OpenApiParameter("search", str)])
class StudentLookupView(APIView):
    permission_classes = [CanViewAccounting]

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request):
        # Только то, что нужно, чтобы привязать платёж: id, ФИО, группа.
        # Без телефонов, статусов и прочего профиля; минимум 2 символа запроса.
        term = (request.query_params.get("search") or "").strip()
        if len(term) < 2:
            return Response([])
        qs = Student.objects.only("id", "first_name", "last_name", "group_id", "group__name").select_related("group")
        for part in term.split():
            qs = qs.filter(Q(first_name__icontains=part) | Q(last_name__icontains=part))
        return Response([
            {"id": st.pk, "name": str(st), "group": st.group_id, "group_name": st.group.name if st.group else None}
            for st in qs.order_by("last_name", "first_name")[:20]
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
        department = q.get("department")
        if q.get("employee"):
            profiles = profiles.filter(employee_id=_int(q["employee"], "employee"))
        if q.get("program"):
            profiles = profiles.filter(Q(rules__program_id=_int(q["program"], "program")) | Q(
                rules__group__course_id=_int(q["program"], "program"))).distinct()
        if q.get("group"):
            profiles = profiles.filter(rules__group_id=_int(q["group"], "group")).distinct()
        # Ссылка на расчёт — когда у сотрудника в выбранном диапазоне он один
        # (половина месяца у процента или месячный период у оклада).
        by_employee: dict[int, list] = {}
        for p in Payroll.objects.filter(period__in=periods).exclude(status=Payroll.Status.VOID).select_related("period"):
            by_employee.setdefault(p.employee_id, []).append(p)
        payrolls = {emp: rows[0] for emp, rows in by_employee.items() if len(rows) == 1}
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
            if department and profile.effective_department != department:
                continue
            result.append({
                "profile_id": profile.pk,
                "employee": profile.employee_id,
                "employee_name": profile.employee.get_full_name() or profile.employee.username,
                "position": profile.display_position,
                "salary_type": profile.salary_type,
                "salary_type_display": profile.get_salary_type_display(),
                "department": profile.effective_department,
                "department_display": Department(profile.effective_department).label,
                # Оклад — в месячном периоде, процент — в половинах месяца.
                "calc_period": "MONTH" if profile.salary_type == "FIXED" else "HALF",
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
# Курсы: стоимость за студента, уроков в цикле; циклы групп
# ---------------------------------------------------------------------------

@extend_schema(tags=TAG)
class CoursePayrollSettingsViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.CreateModelMixin,
                                   mixins.UpdateModelMixin, viewsets.GenericViewSet):
    pagination_class = AccountingPagination
    permission_classes = [AccountingAccess]
    serializer_class = s.CoursePayrollSettingsSerializer
    queryset = CoursePayrollSettings.objects.select_related("course")

    def perform_create(self, serializer):
        try:
            serializer.instance = salary_rules.save_course_settings(
                CoursePayrollSettings(), actor=self.request.user, data=serializer.validated_data,
            )
        except AccountingError as exc:
            _fail(exc)

    def perform_update(self, serializer):
        try:
            serializer.instance = salary_rules.save_course_settings(
                serializer.instance, actor=self.request.user, data=serializer.validated_data,
            )
        except AccountingError as exc:
            _fail(exc)


@extend_schema(tags=TAG)
class CourseCycleViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """Циклы курсов. Список сначала фиксирует новые завершённые циклы по
    проведённым урокам (идемпотентно), поэтому показывает актуальное
    состояние. `status=IN_PROGRESS` — незавершённые, отдельно от завершённых."""

    pagination_class = AccountingPagination
    permission_classes = [AccountingAccess]
    serializer_class = s.CourseCycleSerializer
    filterset_fields = ("status", "course", "group")

    def get_queryset(self):
        qs = CourseCycle.objects.select_related("group", "course").order_by("status", "-completed_on", "group__name")
        q = self.request.query_params
        if q.get("completed_from"):
            qs = qs.filter(completed_on__gte=q["completed_from"])
        if q.get("completed_to"):
            qs = qs.filter(completed_on__lte=q["completed_to"])
        if q.get("not_accrued"):
            qs = qs.filter(status=CourseCycle.Status.COMPLETED, accruals__isnull=True)
        return qs

    def list(self, request, *args, **kwargs):
        cycles.sync_all()
        return super().list(request, *args, **kwargs)

    @action(detail=False, methods=["post"])
    def sync(self, request):
        return Response({"completed": cycles.sync_all()})


@extend_schema(tags=TAG, parameters=[OpenApiParameter("course", int)])
class CoursePriceVersionViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """История тарифов курса: чтение — бухгалтер, директор, администратор;
    новая версия — только бухгалтер. Версии не редактируются и не удаляются."""

    pagination_class = AccountingPagination
    permission_classes = [AccountingAccess]
    serializer_class = s.CoursePriceVersionSerializer
    filterset_fields = ("course", "is_migrated")

    def get_queryset(self):
        return CoursePriceVersion.objects.select_related("course", "created_by")

    @extend_schema(request=s.CoursePriceCreateSerializer, responses=s.CoursePriceVersionSerializer)
    def create(self, request):
        data = _valid(s.CoursePriceCreateSerializer, request)
        try:
            version = pricing.set_price(actor=request.user, **data)
        except AccountingError as exc:
            _fail(exc)
        return Response(s.CoursePriceVersionSerializer(version).data, status=status.HTTP_201_CREATED)


@extend_schema(tags=TAG)
class CycleAccrualViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """Начисления за завершённые циклы (блоки). `status=REVIEW_REQUIRED` —
    спорные: смена тренера внутри блока или второй блок группы за месяц."""

    pagination_class = AccountingPagination
    permission_classes = [AccountingAccess]
    serializer_class = s.CycleAccrualSerializer
    filterset_fields = ("status", "employee", "cycle__group", "cycle__course", "payroll")

    def get_queryset(self):
        return CycleAccrual.objects.select_related(
            "employee", "cycle__group", "cycle__course", "reviewed_by", "payroll__period",
        ).order_by("-completed_on", "id")

    @extend_schema(request=s.CycleAccrualReviewSerializer, responses=s.CycleAccrualSerializer)
    @action(detail=True, methods=["post"])
    def review(self, request, pk=None):
        data = _valid(s.CycleAccrualReviewSerializer, request)
        try:
            accrual = cycles.review_accrual(self.get_object(), actor=request.user, **data)
        except AccountingError as exc:
            _fail(exc)
        return Response(s.CycleAccrualSerializer(self.get_queryset().get(pk=accrual.pk)).data)


def _jsonable(value):
    import datetime as dt

    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (dt.date, dt.datetime)):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_jsonable(v) for v in value]
    return value


def _paginate_list(request, rows: list, view) -> Response:
    paginator = AccountingPagination()
    page = paginator.paginate_queryset(rows, request, view=view)
    return paginator.get_paginated_response(_jsonable(page))


@extend_schema(tags=TAG, parameters=[
    OpenApiParameter("group", int), OpenApiParameter("course", int), OpenApiParameter("employee", int),
])
class EstimateListView(APIView):
    """Предварительные оценки по всем незавершённым блокам (не начисления)."""

    permission_classes = [CanViewAccounting]

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request):
        q = request.query_params
        cycles.sync_all()
        rows = estimates.all_open(group=_int(q.get("group"), "group"), course=_int(q.get("course"), "course"),
                                  employee=_int(q.get("employee"), "employee"))
        return _paginate_list(request, rows, self)


# ---------------------------------------------------------------------------
# Аналитика директора и отчёт по сотрудникам (только чтение)
# ---------------------------------------------------------------------------

_ANALYTICS_PARAMS = [
    OpenApiParameter("year", int), OpenApiParameter("month", int), OpenApiParameter("department", str),
    OpenApiParameter("employee", int), OpenApiParameter("group", int), OpenApiParameter("salary_type", str),
    OpenApiParameter("status", str), OpenApiParameter("period_type", str),
]


def _analytics_query(request) -> tuple[int, int, dict]:
    q = request.query_params
    today = timezone.localdate()
    year, month = _int(q.get("year"), "year") or today.year, _int(q.get("month"), "month") or today.month
    if not 1 <= month <= 12:
        raise ValidationError({"month": "Месяц должен быть от 1 до 12."})
    department = q.get("department") or None
    if department and department not in Department.values:
        raise ValidationError({"department": "Неизвестное направление."})
    status_value = q.get("status") or None
    if status_value and status_value not in Payroll.Status.values:
        raise ValidationError({"status": "Неизвестный статус."})
    period_type = q.get("period_type") or None
    if period_type and period_type not in PayrollPeriod.PeriodType.values:
        raise ValidationError({"period_type": "Неизвестный расчётный период."})
    return year, month, {
        "department": department, "employee": _int(q.get("employee"), "employee"),
        "group": _int(q.get("group"), "group"), "salary_type": q.get("salary_type") or None,
        "status": status_value, "period_type": period_type,
    }


@extend_schema(tags=TAG, parameters=_ANALYTICS_PARAMS)
class AnalyticsSummaryView(APIView):
    permission_classes = [CanViewAccounting]

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request):
        year, month, filters = _analytics_query(request)
        return Response(_jsonable(analytics.summary(year, month, filters)))


@extend_schema(tags=TAG, parameters=_ANALYTICS_PARAMS)
class AnalyticsByDepartmentView(APIView):
    permission_classes = [CanViewAccounting]

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request):
        year, month, filters = _analytics_query(request)
        filters.pop("department", None)
        rows = analytics._month_payrolls(year, month, filters)
        return Response({"year": year, "month": month, "results": _jsonable(analytics.by_department(rows))})


@extend_schema(tags=TAG, parameters=_ANALYTICS_PARAMS)
class TeacherReportView(APIView):
    """Отчёт по сотрудникам: расчёты месяца со строками (группа, студенты,
    цена, процент, уроки) и итогами. Пагинация — по расчётам; итоги — по
    всему отбору."""

    permission_classes = [CanViewAccounting]

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request):
        year, month, filters = _analytics_query(request)
        report = analytics.teacher_report(year, month, filters)
        paginator = AccountingPagination()
        page = paginator.paginate_queryset(report["payrolls"], request, view=self)
        body = {k: v for k, v in report.items() if k != "payrolls"}
        body.update({"count": paginator.page.paginator.count, "next": paginator.get_next_link(),
                     "previous": paginator.get_previous_link(), "results": page})
        return Response(_jsonable(body))


@extend_schema(tags=TAG, parameters=_ANALYTICS_PARAMS)
class TeacherReportXlsxView(APIView):
    permission_classes = [CanViewAccounting]

    @extend_schema(responses=OpenApiTypes.BINARY)
    def get(self, request):
        year, month, filters = _analytics_query(request)
        content = render_teacher_report_xlsx(analytics.teacher_report(year, month, filters))
        return _file(content, f"teachers-{year}-{month:02d}.xlsx", XLSX)


@extend_schema(tags=TAG, parameters=_ANALYTICS_PARAMS)
class TeacherReportPdfView(APIView):
    permission_classes = [CanViewAccounting]

    @extend_schema(responses=OpenApiTypes.BINARY)
    def get(self, request):
        year, month, filters = _analytics_query(request)
        content = render_teacher_report_pdf(analytics.teacher_report(year, month, filters))
        return _file(content, f"teachers-{year}-{month:02d}.pdf", PDF)


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
        qs = PayrollAuditLog.objects.select_related("actor")
        q = self.request.query_params
        if q.get("date_from"):
            qs = qs.filter(created_at__date__gte=q["date_from"])
        if q.get("date_to"):
            qs = qs.filter(created_at__date__lte=q["date_to"])
        return qs


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


def _my_salary_filters(request) -> dict:
    """Фильтры истории. Сотрудник — всегда request.user; параметр
    `employee` (или любой другой id) из запроса игнорируется."""
    q = request.query_params
    period_type = q.get("period_type") or None
    if period_type and period_type not in PayrollPeriod.PeriodType.values:
        raise ValidationError({"period_type": "Неизвестный расчётный период."})
    month = _int(q.get("month"), "month")
    if month is not None and not 1 <= month <= 12:
        raise ValidationError({"month": "Месяц должен быть от 1 до 12."})
    return {"year": _int(q.get("year"), "year"), "month": month, "period_type": period_type}


@extend_schema(tags=TAG, parameters=[
    OpenApiParameter("year", int), OpenApiParameter("month", int), OpenApiParameter("period_type", str),
])
class MySalaryView(APIView):
    """«Моя зарплата»: только собственные данные текущего пользователя, только чтение."""

    permission_classes = [IsAuthenticated]
    http_method_names = ["get", "head", "options"]

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request):
        return Response(my_salary.build(request.user, **_my_salary_filters(request)))


@extend_schema(tags=TAG, parameters=[
    OpenApiParameter("year", int), OpenApiParameter("month", int), OpenApiParameter("period_type", str),
])
class MySalaryPdfView(APIView):
    permission_classes = [IsAuthenticated]
    http_method_names = ["get", "head", "options"]

    @extend_schema(responses=OpenApiTypes.BINARY)
    def get(self, request):
        data = my_salary.build(request.user, **_my_salary_filters(request))
        content = render_my_salary_pdf(data, timezone.localtime())
        return _file(content, f"my-salary-{timezone.localdate():%Y-%m-%d}.pdf", PDF)


@extend_schema(tags=TAG)
class MyEstimatesView(APIView):
    """Предварительная зарплата по своим незавершённым блокам — только своя."""

    permission_classes = [IsAuthenticated]
    http_method_names = ["get", "head", "options"]

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request):
        rows = [my_salary._estimate(e) for e in estimates.for_employee(request.user)]
        return Response({"results": rows, "note": estimates.NOTE})


@extend_schema(tags=TAG)
class MyPaymentsView(mixins.ListModelMixin, viewsets.GenericViewSet):
    """Свои подтверждённые выплаты — только чтение."""

    pagination_class = AccountingPagination
    permission_classes = [IsAuthenticated]
    serializer_class = s.PayrollPaymentSerializer

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return PayrollPayment.objects.none()
        return (
            PayrollPayment.objects.filter(payroll__employee=self.request.user, status=PayrollPayment.Status.CONFIRMED)
            .select_related("created_by", "payroll").order_by("-payment_date", "-id")
        )
