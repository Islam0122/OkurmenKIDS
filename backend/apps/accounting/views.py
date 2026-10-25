"""API бухгалтерии (/api/v1/accounting/). Представления только проверяют
права, валидируют ввод и вызывают сервисы — расчётов здесь нет."""
from __future__ import annotations

from decimal import Decimal

from django.db.models import Exists, OuterRef, Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import APIException, ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.academy.models import Course, Group, GroupTeacher, Student
from apps.users.models import Subject, Teacher, User

from . import serializers as s
from .filters import filter_payrolls
from .models import (
    ALLOWED_SALARY_TYPES,
    CourseCycle,
    CoursePayrollSettings,
    CoursePriceVersion,
    AppliedDeduction,
    CycleAccrual,
    DeductionRule,
    Department,
    EmployeeSalaryProfile,
    Expense,
    ExpenseCategory,
    PaymentMethod,
    PayoutPlan,
    PayoutPlanLine,
    Payroll,
    PayrollAdjustment,
    PayrollAuditLog,
    PayrollPayment,
    PayrollPeriod,
    RecurringExpense,
    SalaryRule,
    StudentPayment,
)
from .permissions import AccountingAccess, CanApprove, CanViewAccounting, capabilities
from .services import AccountingError
from .services import approval_service, cycles, payment_service, payroll_calculator, report_service, salary_rules
from .services import student_payments as student_payment_service
from .services.periods import close_period, get_or_create_period
from .services import analytics, deductions, earnings, estimates, my_salary, payout_plans, pricing
from .services import expenses as expense_service
from .services.money import money
from .services import finance_overview
from .services.report_pdf import (
    render_individual_pdf,
    render_my_salary_pdf,
    render_payout_plan_pdf,
    render_period_pdf,
    render_teacher_report_pdf,
)
from .services.report_xlsx import (
    render_individual_xlsx,
    render_payout_plan_xlsx,
    render_period_xlsx,
    render_teacher_report_xlsx,
)

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
            "trainer_split_rules": [
                {"value": v, "label": l} for v, l in CoursePayrollSettings.TrainerSplitRule.choices
            ],
            "trainers": [
                {"id": t.pk, "name": str(t)} for t in Teacher.objects.select_related("user").order_by("user__last_name")
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

    @extend_schema(request=s.SalaryRuleCorrectSerializer, responses=OpenApiTypes.OBJECT)
    @action(detail=True, methods=["post"])
    def correct(self, request, pk=None):
        """Исправить ошибочное правило: тип оплаты, ставку, основание, метод,
        даты. Только пока правило не попало в утверждённые начисления."""
        data = _valid(s.SalaryRuleCorrectSerializer, request)
        reason = data.pop("reason")
        try:
            rule, effects = salary_rules.correct_rule(self.get_object(), actor=request.user, changes=data, reason=reason)
        except AccountingError as exc:
            _fail(exc)
        return Response({"rule": s.SalaryRuleSerializer(rule).data, "effects": effects})

    @extend_schema(request=s.SalaryRuleReplaceSerializer, responses=OpenApiTypes.OBJECT)
    @action(detail=True, methods=["post"])
    def replace(self, request, pk=None):
        """Заменить правило с даты: старое закрывается днём раньше, история
        утверждённых начислений не меняется."""
        data = _valid(s.SalaryRuleReplaceSerializer, request)
        reason, effective_from = data.pop("reason"), data.pop("effective_from")
        try:
            rule, effects = salary_rules.replace_rule(self.get_object(), actor=request.user,
                                                      effective_from=effective_from, data=data, reason=reason)
        except AccountingError as exc:
            _fail(exc)
        return Response({"rule": s.SalaryRuleSerializer(rule).data, "effects": effects},
                        status=status.HTTP_201_CREATED)

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
    filterset_fields = ("status", "course", "group", "subject", "per_subject")

    def get_queryset(self):
        qs = CourseCycle.objects.select_related("group", "course", "subject").prefetch_related("accruals").order_by(
            "group__name", "group_id", "per_subject", "subject__name", "-number",
        )
        q = self.request.query_params
        if q.get("search"):
            qs = qs.filter(group__name__icontains=q["search"].strip())
        if q.get("trainer"):
            trainer = _int(q["trainer"], "trainer")
            teaches_now = GroupTeacher.objects.filter(
                group_id=OuterRef("group_id"), subject_id=OuterRef("subject_id"), teacher_id=trainer, is_active=True,
            )
            qs = qs.filter(Q(teacher_lessons__has_key=str(trainer))
                           | Q(Exists(teaches_now), status=CourseCycle.Status.IN_PROGRESS))
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
                                  employee=_int(q.get("employee"), "employee"),
                                  subject=_int(q.get("subject"), "subject"))
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
# Заработок сотрудников (единый расчёт с «Моей зарплатой»)
# ---------------------------------------------------------------------------

@extend_schema(tags=TAG, parameters=[OpenApiParameter("department", str), OpenApiParameter("search", str)])
class EarningsListView(APIView):
    """Заработано / удержания / на руки / официально начислено / выплачено /
    остаток — по каждому сотруднику. Только чтение; ничего не начисляет."""

    permission_classes = [CanViewAccounting]

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request):
        q = request.query_params
        rows = earnings.employees_summary(department=q.get("department") or None, search=q.get("search") or "")
        return _paginate_list(request, earnings.as_json(rows), self)


@extend_schema(tags=TAG, parameters=[
    OpenApiParameter("date_from", OpenApiTypes.DATE), OpenApiParameter("date_to", OpenApiTypes.DATE),
    OpenApiParameter("department", str), OpenApiParameter("search", str),
])
class PayoutScheduleView(APIView):
    """График выплат по датам (15-е / 1-е): кому и сколько, удержания,
    выплачено, остаток; отдельно — заработок по незавершённым блокам, ещё не
    включённый в выплату. Только чтение."""

    permission_classes = [CanViewAccounting]

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request):
        q = request.query_params
        bounds = {}
        for name in ("date_from", "date_to"):
            if q.get(name):
                try:
                    bounds[name] = timezone.datetime.fromisoformat(q[name]).date()
                except ValueError:
                    raise ValidationError({name: "Ожидается дата ГГГГ-ММ-ДД."})
        data = earnings.payout_calendar(department=q.get("department") or None, search=q.get("search") or "",
                                        **bounds)
        return Response(earnings.as_json(data))


@extend_schema(tags=TAG)
class EarningsDetailView(APIView):
    """Детали заработка сотрудника: предметы, группы, блоки, расчёты,
    удержания и причины расхождения с официальным начислением."""

    permission_classes = [CanViewAccounting]

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request, employee_id: int):
        employee = get_object_or_404(User, pk=employee_id)
        data = earnings.summary(employee)
        data["employee"] = employee.pk
        data["employee_name"] = employee.get_full_name() or employee.username
        return Response(earnings.as_json(data))


# ---------------------------------------------------------------------------
# Налоги и удержания
# ---------------------------------------------------------------------------

def _effects(data: dict) -> dict:
    return {"payrolls_recalculated": data["payrolls_recalculated"], "payrolls_failed": data["payrolls_failed"]}


@extend_schema(tags=TAG, parameters=[
    OpenApiParameter("employee", int), OpenApiParameter("kind", str), OpenApiParameter("is_active", bool),
    OpenApiParameter("current", bool, description="Только последние версии правил"),
])
class DeductionRuleViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """Правила удержаний (налоги, взносы, другие). Создание и изменение —
    бухгалтер; директор и администратор — только просмотр. Удалять нельзя:
    правило отключается или закрывается датой, история версий сохраняется."""

    pagination_class = AccountingPagination
    permission_classes = [AccountingAccess]
    serializer_class = s.DeductionRuleSerializer

    def get_queryset(self):
        qs = DeductionRule.objects.select_related("employee", "created_by", "next_version")
        q = self.request.query_params
        if q.get("employee"):
            qs = qs.filter(Q(scope=DeductionRule.Scope.EMPLOYEE, employee_id=_int(q["employee"], "employee"))
                           | ~Q(scope=DeductionRule.Scope.EMPLOYEE))
        if q.get("kind"):
            qs = qs.filter(kind=q["kind"])
        if q.get("is_active") in ("true", "1"):
            qs = qs.filter(is_active=True)
        if q.get("current") in ("true", "1"):
            qs = qs.filter(next_version__isnull=True)
        return qs

    @extend_schema(request=s.DeductionRuleInputSerializer, responses=OpenApiTypes.OBJECT)
    def create(self, request, *args, **kwargs):
        data = _valid(s.DeductionRuleInputSerializer, request)
        try:
            rule, effects = deductions.create_rule(actor=request.user, **data)
        except AccountingError as exc:
            _fail(exc)
        return Response({"rule": s.DeductionRuleSerializer(rule).data, "effects": _effects(effects)},
                        status=status.HTTP_201_CREATED)

    @extend_schema(request=s.DeductionRuleChangeSerializer, responses=OpenApiTypes.OBJECT)
    @action(detail=True, methods=["post"])
    def change(self, request, pk=None):
        data = dict(_valid(s.DeductionRuleChangeSerializer, request))
        reason = data.pop("reason")
        try:
            rule, effects = deductions.change_rule(self.get_object(), actor=request.user, changes=data, reason=reason)
        except AccountingError as exc:
            _fail(exc)
        return Response({"rule": s.DeductionRuleSerializer(rule).data, "effects": _effects(effects)})

    @extend_schema(responses=OpenApiTypes.OBJECT)
    @action(detail=True, methods=["get"])
    def history(self, request, pk=None):
        rule = self.get_object()
        chain = deductions.versions(rule)
        log = PayrollAuditLog.objects.filter(entity_type="deductionrule", entity_id__in=[r.pk for r in chain]) \
            .select_related("actor").order_by("-created_at", "-id")
        return Response({"versions": s.DeductionRuleSerializer(chain, many=True).data,
                         "audit": s.PayrollAuditLogSerializer(log, many=True).data})


@extend_schema(tags=TAG, parameters=[
    OpenApiParameter("employee", int), OpenApiParameter("year", int), OpenApiParameter("month", int),
])
class AppliedDeductionListView(APIView):
    """Журнал применённых удержаний: одна запись на правило, сотрудника и
    месяц; сколько удержано по расчётам и сколько осталось не удержанным."""

    permission_classes = [CanViewAccounting]

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request):
        q = request.query_params
        qs = AppliedDeduction.objects.select_related("employee", "rule").prefetch_related("allocations__payroll__period")
        for name in ("year", "month"):
            if q.get(name):
                qs = qs.filter(**{name: _int(q[name], name)})
        if q.get("employee"):
            qs = qs.filter(employee_id=_int(q["employee"], "employee"))
        rows = []
        for h in qs:
            allocations = [a for a in h.allocations.all() if a.payroll.status != Payroll.Status.VOID]
            withheld = sum((a.amount for a in allocations), Decimal("0"))
            rows.append({
                "id": h.pk, "rule": h.rule_id, "name": h.name, "kind": h.kind,
                "kind_display": DeductionRule.Kind(h.kind).label, "employee": h.employee_id,
                "employee_name": h.employee.get_full_name() or h.employee.username, "year": h.year, "month": h.month,
                "amount": h.amount, "withheld": withheld, "remaining": max(Decimal("0"), h.amount - withheld),
                "payrolls": [{"payroll": a.payroll_id, "period_label": report_service.period_label(a.payroll.period),
                              "status": a.payroll.status, "amount": a.amount} for a in allocations],
            })
        return _paginate_list(request, rows, self)


# ---------------------------------------------------------------------------
# План выплат
# ---------------------------------------------------------------------------

class Conflict(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "Конфликт изменений."


def _plan_fail(exc: AccountingError):
    if exc.code == "conflict":
        raise Conflict({"detail": exc.message, "code": exc.code})
    _fail(exc)


PLAN_FILTERS = [
    OpenApiParameter("year", int), OpenApiParameter("month", int), OpenApiParameter("payout_date", OpenApiTypes.DATE),
    OpenApiParameter("date_from", OpenApiTypes.DATE), OpenApiParameter("date_to", OpenApiTypes.DATE),
    OpenApiParameter("status", str), OpenApiParameter("department", str), OpenApiParameter("employee", int),
]


def _plan_params(request) -> dict:
    q = request.query_params
    params = {"year": _int(q.get("year"), "year"), "month": _int(q.get("month"), "month"),
              "employee": _int(q.get("employee"), "employee")}
    for name in ("payout_date", "date_from", "date_to"):
        value = q.get(name)
        if value:
            try:
                params[name] = timezone.datetime.fromisoformat(value).date()
            except ValueError:
                raise ValidationError({name: "Ожидается дата ГГГГ-ММ-ДД."})
    if q.get("status"):
        if q["status"] not in payout_plans.STATUS_LABELS:
            raise ValidationError({"status": "Неизвестный статус."})
        params["status"] = q["status"]
    if q.get("department"):
        params["department"] = q["department"]
    return params


@extend_schema(tags=TAG)
class PayoutPlanViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """План выплат на дату. Чтение — бухгалтер, директор, администратор;
    изменения — только бухгалтер. Подготовленные средства — не выплаты:
    фактические выплаты регистрируются действием `pay` строки (существующий
    механизм выплат)."""

    pagination_class = AccountingPagination
    permission_classes = [AccountingAccess]
    serializer_class = s.PayoutPlanSerializer
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_queryset(self):
        return PayoutPlan.objects.select_related("created_by", "approved_by", "cancelled_by")

    def _detail(self, plan, *, code=status.HTTP_200_OK):
        plan = self.get_queryset().get(pk=plan.pk)
        line_ids = list(plan.lines.values_list("pk", flat=True))
        history = PayrollAuditLog.objects.filter(
            Q(entity_type="payoutplan", entity_id=plan.pk) | Q(entity_type="payoutplanline", entity_id__in=line_ids),
        ).select_related("actor").order_by("-created_at", "-id")
        data = s.PayoutPlanSerializer(plan).data
        data["lines"] = _jsonable(payout_plans.plan_lines(plan))
        data["history"] = s.PayrollAuditLogSerializer(history, many=True).data
        return Response(data, status=code)

    @extend_schema(parameters=PLAN_FILTERS)
    def list(self, request, *args, **kwargs):
        plans = payout_plans.filtered_plans(_plan_params(request))
        page = self.paginate_queryset(plans)
        return self.get_paginated_response(s.PayoutPlanSerializer(page, many=True).data)

    def retrieve(self, request, *args, **kwargs):
        return self._detail(self.get_object())

    @extend_schema(request=s.PayoutPlanCreateSerializer, responses=s.PayoutPlanSerializer)
    def create(self, request, *args, **kwargs):
        data = _valid(s.PayoutPlanCreateSerializer, request)
        try:
            plan = payout_plans.create_plan(actor=request.user, **data)
        except AccountingError as exc:
            _plan_fail(exc)
        return self._detail(plan, code=status.HTTP_201_CREATED)

    @extend_schema(request=s.PayoutPlanUpdateSerializer, responses=s.PayoutPlanSerializer)
    def partial_update(self, request, *args, **kwargs):
        data = dict(_valid(s.PayoutPlanUpdateSerializer, request))
        version, reason = data.pop("version", None), data.pop("reason", "")
        try:
            plan = payout_plans.update_plan(self.get_object(), actor=request.user, changes=data, reason=reason,
                                            version=version)
        except AccountingError as exc:
            _plan_fail(exc)
        return self._detail(plan)

    @extend_schema(request=s.PayoutPlanVersionSerializer, responses=s.PayoutPlanSerializer)
    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        data = _valid(s.PayoutPlanVersionSerializer, request)
        try:
            plan = payout_plans.approve_plan(self.get_object(), actor=request.user, version=data.get("version"))
        except AccountingError as exc:
            _plan_fail(exc)
        return self._detail(plan)

    @extend_schema(request=s.PayoutPlanCancelSerializer, responses=s.PayoutPlanSerializer)
    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        data = _valid(s.PayoutPlanCancelSerializer, request)
        try:
            plan = payout_plans.cancel_plan(self.get_object(), actor=request.user, reason=data["reason"],
                                            version=data.get("version"))
        except AccountingError as exc:
            _plan_fail(exc)
        return self._detail(plan)

    @extend_schema(request=s.PayoutPlanAddLinesSerializer, responses=s.PayoutPlanSerializer)
    @action(detail=True, methods=["post"])
    def lines(self, request, pk=None):
        data = _valid(s.PayoutPlanAddLinesSerializer, request)
        try:
            plan = payout_plans.add_lines(self.get_object(), actor=request.user, items=data["lines"],
                                          version=data.get("version"))
        except AccountingError as exc:
            _plan_fail(exc)
        return self._detail(plan)

    def _line(self, plan, line_id):
        return get_object_or_404(PayoutPlanLine, pk=line_id, plan=plan)

    @extend_schema(request=s.PayoutPlanLineUpdateSerializer, responses=s.PayoutPlanSerializer)
    @action(detail=True, methods=["patch"], url_path=r"lines/(?P<line_id>\d+)")
    def line(self, request, pk=None, line_id=None):
        plan = self.get_object()
        data = _valid(s.PayoutPlanLineUpdateSerializer, request)
        try:
            payout_plans.update_line(self._line(plan, line_id), actor=request.user, amount=data.get("amount"),
                                     comment=data.get("comment"), remove=data["remove"], reason=data["reason"],
                                     version=data.get("version"))
        except AccountingError as exc:
            _plan_fail(exc)
        return self._detail(plan)

    @extend_schema(request=s.PayoutPlanPaySerializer, responses=s.PayrollPaymentSerializer)
    @action(detail=True, methods=["post"], url_path=r"lines/(?P<line_id>\d+)/pay")
    def pay(self, request, pk=None, line_id=None):
        plan = self.get_object()
        data = _valid(s.PayoutPlanPaySerializer, request)
        key = _idempotency_key(request, data)
        data.pop("idempotency_key", None)
        try:
            payment, created = payout_plans.pay_line(self._line(plan, line_id), actor=request.user,
                                                     idempotency_key=key, **data)
        except AccountingError as exc:
            _plan_fail(exc)
        return Response(s.PayrollPaymentSerializer(payment).data,
                        status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)

    @extend_schema(parameters=PLAN_FILTERS, responses=OpenApiTypes.OBJECT)
    @action(detail=False, methods=["get"])
    def summary(self, request):
        return Response(_jsonable(payout_plans.summary(payout_plans.filtered_plans(_plan_params(request)))))

    @extend_schema(parameters=PLAN_FILTERS, responses=OpenApiTypes.OBJECT)
    @action(detail=False, methods=["get"])
    def calendar(self, request):
        params = _plan_params(request)
        data = payout_plans.calendar(payout_plans.filtered_plans(params), year=params["year"], month=params["month"])
        return Response(_jsonable(data))

    @extend_schema(parameters=[OpenApiParameter("year", int), OpenApiParameter("month", int),
                               OpenApiParameter("employee", int), OpenApiParameter("department", str)],
                   responses=OpenApiTypes.OBJECT)
    @action(detail=False, methods=["get"])
    def candidates(self, request):
        q = request.query_params
        rows = payout_plans.candidates(year=_int(q.get("year"), "year"), month=_int(q.get("month"), "month"),
                                       employee=_int(q.get("employee"), "employee"),
                                       department=q.get("department") or None)
        return Response({"results": _jsonable(rows)})

    @extend_schema(responses=OpenApiTypes.BINARY)
    @action(detail=True, methods=["get"], url_path="report.xlsx")
    def report_xlsx(self, request, pk=None):
        plan = self.get_object()
        return _file(render_payout_plan_xlsx(payout_plans.plan_report(plan)),
                     f"payout-plan-{plan.pk}-{plan.payout_date:%Y-%m-%d}.xlsx", XLSX)

    @extend_schema(responses=OpenApiTypes.BINARY)
    @action(detail=True, methods=["get"], url_path="report.pdf")
    def report_pdf(self, request, pk=None):
        plan = self.get_object()
        return _file(render_payout_plan_pdf(payout_plans.plan_report(plan)),
                     f"payout-plan-{plan.pk}-{plan.payout_date:%Y-%m-%d}.pdf", PDF)


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


@extend_schema(tags=TAG)
class MyPayoutPlanView(APIView):
    """Свои запланированные выплаты (утверждённые планы) — только своё, только чтение."""

    permission_classes = [IsAuthenticated]
    http_method_names = ["get", "head", "options"]

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request):
        return Response({"results": _jsonable(payout_plans.my_planned(request.user))})


# ---------------------------------------------------------------------------
# Расходы компании
# ---------------------------------------------------------------------------

def _date_param(request, name):
    value = request.query_params.get(name)
    if not value:
        return None
    try:
        return timezone.datetime.fromisoformat(value).date()
    except ValueError:
        raise ValidationError({name: "Ожидается дата ГГГГ-ММ-ДД."})


def _range_from_query(request):
    """Период отчёта: `month=ГГГГ-ММ`, или `date_from` + `date_to`; по
    умолчанию — текущий месяц."""
    from .services.finance_overview import month_range

    month = request.query_params.get("month")
    if month:
        try:
            year, mm = (int(x) for x in month.split("-"))
            return month_range(year, mm)
        except (TypeError, ValueError):
            raise ValidationError({"month": "Ожидается ГГГГ-ММ."})
    date_from, date_to = _date_param(request, "date_from"), _date_param(request, "date_to")
    if date_from and date_to:
        if date_to < date_from:
            raise ValidationError({"date_to": "Конец периода раньше начала."})
        if (date_to - date_from).days > 3 * 366:
            raise ValidationError({"date_to": "Период не длиннее трёх лет."})
        return date_from, date_to
    today = timezone.localdate()
    return month_range(today.year, today.month)


def _expense_filters(request) -> dict:
    q = request.query_params
    f = {k: q.get(k) for k in ("search", "status", "payment_method", "vendor", "recurring", "overdue", "include_void")
         if q.get(k)}
    for name in ("category", "responsible"):
        if q.get(name):
            f[name] = _int(q[name], name)
    for name in ("date_from", "date_to", "paid_from", "paid_to"):
        value = _date_param(request, name)
        if value:
            f[name] = value
    if f.get("status") and f["status"] not in Expense.Status.values:
        raise ValidationError({"status": "Неизвестный статус."})
    return f


def _expense_fail(exc: AccountingError):
    if exc.code == "conflict":
        raise Conflict({"detail": exc.message, "code": exc.code})
    _fail(exc)


EXPENSE_FILTERS = [
    OpenApiParameter("search", str), OpenApiParameter("category", int), OpenApiParameter("status", str),
    OpenApiParameter("payment_method", str), OpenApiParameter("responsible", int), OpenApiParameter("vendor", str),
    OpenApiParameter("date_from", OpenApiTypes.DATE), OpenApiParameter("date_to", OpenApiTypes.DATE),
    OpenApiParameter("paid_from", OpenApiTypes.DATE), OpenApiParameter("paid_to", OpenApiTypes.DATE),
    OpenApiParameter("recurring", bool), OpenApiParameter("overdue", bool), OpenApiParameter("include_void", bool),
]


@extend_schema(tags=TAG)
class ExpenseCategoryViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """Справочник категорий расходов: чтение — бухгалтер, директор,
    администратор; создание и изменение — бухгалтер. Не удаляется — отключается."""

    permission_classes = [AccountingAccess]
    serializer_class = s.ExpenseCategorySerializer
    http_method_names = ["get", "post", "patch", "head", "options"]
    pagination_class = None

    def get_queryset(self):
        from django.db.models import Count

        qs = ExpenseCategory.objects.annotate(expenses_count=Count("expenses", filter=~Q(expenses__status="VOID")))
        if self.request.query_params.get("active") in ("1", "true"):
            qs = qs.filter(is_active=True)
        return qs

    def create(self, request, *args, **kwargs):
        data = _valid(s.ExpenseCategorySerializer, request)
        try:
            category = expense_service.save_category(actor=request.user, **data)
        except AccountingError as exc:
            _fail(exc)
        return Response(s.ExpenseCategorySerializer(category).data, status=status.HTTP_201_CREATED)

    def partial_update(self, request, *args, **kwargs):
        serializer = s.ExpenseCategorySerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        data = {k: v for k, v in serializer.validated_data.items() if k != "code"}
        try:
            category = expense_service.save_category(actor=request.user, category=self.get_object(), **data)
        except AccountingError as exc:
            _fail(exc)
        return Response(s.ExpenseCategorySerializer(category).data)


@extend_schema(tags=TAG, parameters=EXPENSE_FILTERS)
class ExpenseViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """Расходы компании. Чтение — бухгалтер, директор, администратор; запись —
    бухгалтер. Неоплаченный расход — обязательство (в движение денег не
    входит); оплата — `pay/`, отмена — `void/` с причиной; удаления нет."""

    pagination_class = AccountingPagination
    permission_classes = [AccountingAccess]
    serializer_class = s.ExpenseSerializer
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_parsers(self):
        from rest_framework.parsers import FormParser, JSONParser, MultiPartParser

        return [JSONParser(), MultiPartParser(), FormParser()]

    def get_queryset(self):
        qs = Expense.objects.select_related("category", "responsible", "created_by", "voided_by", "recurring")
        if self.action == "list":
            qs = expense_service.filter_expenses(qs, _expense_filters(self.request))
            ordering = self.request.query_params.get("ordering")
            if ordering in ("expense_date", "-expense_date", "amount", "-amount", "due_date", "-due_date",
                            "paid_date", "-paid_date"):
                qs = qs.order_by(ordering, "-id")
        return qs

    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)
        from django.db.models import Sum

        qs = self.filter_queryset(self.get_queryset())
        totals = qs.aggregate(total=Sum("amount"), paid=Sum("amount", filter=Q(status=Expense.Status.PAID)),
                              unpaid=Sum("amount", filter=Q(status=Expense.Status.UNPAID)))
        response.data["totals"] = {k: str(money(v or 0)) for k, v in totals.items()}
        return response

    def _out(self, expense, *, code=status.HTTP_200_OK):
        return Response(s.ExpenseSerializer(self.get_queryset().get(pk=expense.pk)).data, status=code)

    @extend_schema(request=s.ExpenseCreateSerializer, responses=s.ExpenseSerializer)
    def create(self, request, *args, **kwargs):
        data = dict(_valid(s.ExpenseCreateSerializer, request))
        data["idempotency_key"] = _idempotency_key(request, data) or None
        try:
            expense, created = expense_service.create_expense(actor=request.user, **data)
        except AccountingError as exc:
            _fail(exc)
        return self._out(expense, code=status.HTTP_201_CREATED if created else status.HTTP_200_OK)

    @extend_schema(request=s.ExpenseUpdateSerializer, responses=s.ExpenseSerializer)
    def partial_update(self, request, *args, **kwargs):
        data = dict(_valid(s.ExpenseUpdateSerializer, request))
        version, reason = data.pop("version", None), data.pop("reason", "")
        try:
            expense = expense_service.update_expense(self.get_object(), actor=request.user, changes=data,
                                                     reason=reason, version=version)
        except AccountingError as exc:
            _expense_fail(exc)
        return self._out(expense)

    @extend_schema(request=s.ExpensePaySerializer, responses=s.ExpenseSerializer)
    @action(detail=True, methods=["post"])
    def pay(self, request, pk=None):
        data = _valid(s.ExpensePaySerializer, request)
        try:
            expense = expense_service.mark_paid(self.get_object(), actor=request.user, **data)
        except AccountingError as exc:
            _expense_fail(exc)
        return self._out(expense)

    @extend_schema(request=s.ExpenseReasonSerializer, responses=s.ExpenseSerializer)
    @action(detail=True, methods=["post"])
    def unpay(self, request, pk=None):
        data = _valid(s.ExpenseReasonSerializer, request)
        try:
            expense = expense_service.unmark_paid(self.get_object(), actor=request.user, **data)
        except AccountingError as exc:
            _expense_fail(exc)
        return self._out(expense)

    @extend_schema(request=s.ExpenseReasonSerializer, responses=s.ExpenseSerializer)
    @action(detail=True, methods=["post"])
    def void(self, request, pk=None):
        data = _valid(s.ExpenseReasonSerializer, request)
        try:
            expense = expense_service.void_expense(self.get_object(), actor=request.user, **data)
        except AccountingError as exc:
            _expense_fail(exc)
        return self._out(expense)

    @extend_schema(responses=OpenApiTypes.OBJECT)
    @action(detail=True, methods=["get"])
    def history(self, request, pk=None):
        expense = self.get_object()
        log = PayrollAuditLog.objects.filter(entity_type="expense", entity_id=expense.pk).select_related("actor") \
            .order_by("-created_at", "-id")
        return Response({"results": s.PayrollAuditLogSerializer(log, many=True).data})

    @extend_schema(responses=OpenApiTypes.BINARY)
    @action(detail=True, methods=["get", "post"])
    def document(self, request, pk=None):
        """GET — скачать подтверждающий документ (только через API: файл не
        отдаётся публичной ссылкой); POST (multipart `document`) — прикрепить
        или заменить."""
        expense = self.get_object()
        if request.method == "POST":
            try:
                expense = expense_service.attach_document(
                    expense, actor=request.user, document=request.FILES.get("document"),
                    version=_int(request.data.get("version"), "version"),
                )
            except AccountingError as exc:
                _expense_fail(exc)
            return self._out(expense)
        if not expense.document:
            raise ValidationError({"detail": "К расходу не прикреплён документ.", "code": "no_document"})
        from django.http import FileResponse

        try:
            handle = expense.document.open("rb")
        except FileNotFoundError:
            raise ValidationError({"detail": "Файл документа не найден в хранилище.", "code": "missing_file"})
        response = FileResponse(handle, as_attachment=True, filename=expense.document_name or expense.document.name)
        response["Cache-Control"] = "no-store"
        return response

    @extend_schema(responses=OpenApiTypes.OBJECT, parameters=[OpenApiParameter("month", str)])
    @action(detail=False, methods=["get"])
    def report(self, request):
        date_from, date_to = _range_from_query(request)
        return Response(_jsonable(expense_service.report(date_from, date_to, _expense_filters(request))))

    @extend_schema(responses=OpenApiTypes.BINARY, parameters=[OpenApiParameter("month", str)])
    @action(detail=False, methods=["get"], url_path="export.xlsx")
    def export_xlsx(self, request):
        from .services.report_xlsx import render_expenses_xlsx

        date_from, date_to = _range_from_query(request)
        f = _expense_filters(request)
        rows = list(expense_service.filter_expenses(
            Expense.objects.select_related("category", "responsible"),
            {**f, "date_from": date_from, "date_to": date_to},
        ).order_by("expense_date", "id"))
        content = render_expenses_xlsx(rows, expense_service.report(date_from, date_to, f))
        return _file(content, f"expenses-{date_from:%Y-%m-%d}-{date_to:%Y-%m-%d}.xlsx", XLSX)

    @extend_schema(responses=OpenApiTypes.OBJECT)
    @action(detail=False, methods=["get"])
    def options(self, request):
        """Справочники формы расхода: категории, способы, статусы и сотрудники
        (только id и ФИО — для поля «Ответственный»)."""
        staff = User.objects.filter(is_active=True).order_by("last_name", "first_name") \
            .values("id", "first_name", "last_name", "username")
        return Response({
            "categories": s.ExpenseCategorySerializer(ExpenseCategory.objects.all(), many=True).data,
            "payment_methods": [{"value": v, "label": label} for v, label in PaymentMethod.choices],
            "statuses": [{"value": v, "label": label} for v, label in Expense.Status.choices],
            "staff": [{"id": u["id"], "name": f"{u['last_name']} {u['first_name']}".strip() or u["username"]}
                      for u in staff],
            "unpaid": _jsonable(expense_service.unpaid_summary()),
        })


@extend_schema(tags=TAG)
class RecurringExpenseViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """Регулярные (ежемесячные) расходы. Шаблон не является деньгами: по нему
    раз в месяц создаётся один неоплаченный расход (`generate/`, ежедневный
    `run_scheduled_tasks`); повторный запуск ничего не дублирует."""

    permission_classes = [AccountingAccess]
    serializer_class = s.RecurringExpenseSerializer
    http_method_names = ["get", "post", "patch", "head", "options"]
    pagination_class = None

    def get_queryset(self):
        from django.db.models import Count, Max

        return RecurringExpense.objects.select_related("category", "responsible").annotate(
            expenses_count=Count("expenses", filter=~Q(expenses__status="VOID")),
            last_month=Max("expenses__recurrence_month"),
        )

    def _out(self, recurring, *, code=status.HTTP_200_OK):
        return Response(s.RecurringExpenseSerializer(self.get_queryset().get(pk=recurring.pk)).data, status=code)

    def create(self, request, *args, **kwargs):
        data = _valid(s.RecurringExpenseSerializer, request)
        try:
            recurring = expense_service.save_recurring(actor=request.user, **data)
        except AccountingError as exc:
            _fail(exc)
        return self._out(recurring, code=status.HTTP_201_CREATED)

    def partial_update(self, request, *args, **kwargs):
        serializer = s.RecurringExpenseSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        try:
            recurring = expense_service.save_recurring(actor=request.user, recurring=self.get_object(),
                                                       **serializer.validated_data)
        except AccountingError as exc:
            _fail(exc)
        return self._out(recurring)

    @extend_schema(responses=OpenApiTypes.OBJECT)
    @action(detail=False, methods=["post"])
    def generate(self, request):
        today = timezone.localdate()
        year = _int(request.data.get("year"), "year") or today.year
        month = _int(request.data.get("month"), "month") or today.month
        if not 1 <= month <= 12:
            raise ValidationError({"month": "Месяц 1–12."})
        return Response(expense_service.generate_recurring(year, month, actor=request.user))


# ---------------------------------------------------------------------------
# Финансовая панель и касса
# ---------------------------------------------------------------------------

RANGE_PARAMS = [OpenApiParameter("month", str), OpenApiParameter("date_from", OpenApiTypes.DATE),
                OpenApiParameter("date_to", OpenApiTypes.DATE)]


@extend_schema(tags=TAG, parameters=RANGE_PARAMS)
class FinanceOverviewView(APIView):
    """Единая финансовая панель за период: оплата студентов, зарплата,
    расходы, денежный поток, сравнение с предыдущим периодом (только чтение)."""

    permission_classes = [CanViewAccounting]

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request):
        date_from, date_to = _range_from_query(request)
        return Response(_jsonable(finance_overview.overview(date_from, date_to)))


@extend_schema(tags=TAG, parameters=RANGE_PARAMS + [
    OpenApiParameter("kind", str), OpenApiParameter("method", str), OpenApiParameter("direction", str),
    OpenApiParameter("search", str),
])
class CashFlowView(APIView):
    """Касса: все фактические движения денег за период одной лентой."""

    permission_classes = [CanViewAccounting]

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request):
        date_from, date_to = _range_from_query(request)
        q = request.query_params
        if q.get("kind") and q["kind"] not in finance_overview.KINDS:
            raise ValidationError({"kind": "Неизвестный тип операции."})
        data = finance_overview.cash_movements(date_from, date_to, kind=q.get("kind"), method=q.get("method"),
                                               direction=q.get("direction"), search=q.get("search"))
        paginator = AccountingPagination()
        page = paginator.paginate_queryset(data["results"], request, view=self)
        response = paginator.get_paginated_response(_jsonable(page))
        response.data.update(_jsonable({k: v for k, v in data.items() if k != "results"}))
        return response


@extend_schema(tags=TAG, parameters=RANGE_PARAMS)
class FinanceReportXlsxView(APIView):
    permission_classes = [CanViewAccounting]

    @extend_schema(responses=OpenApiTypes.BINARY)
    def get(self, request):
        from .services.report_xlsx import render_finance_xlsx

        date_from, date_to = _range_from_query(request)
        content = render_finance_xlsx(
            finance_overview.overview(date_from, date_to),
            finance_overview.cash_movements(date_from, date_to),
            expense_service.report(date_from, date_to),
        )
        return _file(content, f"finance-{date_from:%Y-%m-%d}-{date_to:%Y-%m-%d}.xlsx", XLSX)
