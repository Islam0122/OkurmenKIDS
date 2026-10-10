"""Данные отчётов и дашборда — только из записей БД (строки расчёта,
применённые корректировки, подтверждённые выплаты), а не из вручную
изменяемых итогов. PDF и Excel рендерят одни и те же объекты, поэтому их
итоги не могут разойтись."""
from __future__ import annotations

import calendar
from collections import defaultdict
from dataclasses import dataclass, field
from decimal import Decimal

from django.db.models import DecimalField, OuterRef, Q, Subquery, Sum, Value
from django.db.models.functions import Coalesce
from django.utils import timezone

from apps.academy.models import Group

from ..models import Payroll, PayrollAdjustment, PayrollLine, PayrollPayment, PayrollPeriod, SalaryType
from .money import ZERO

_DEC = DecimalField(max_digits=14, decimal_places=2)


def _sum_of(model, filters: Q):
    sub = (
        model.objects.filter(filters, payroll=OuterRef("pk")).order_by().values("payroll")
        .annotate(s=Sum("amount")).values("s")
    )
    return Coalesce(Subquery(sub, output_field=_DEC), Value(ZERO, output_field=_DEC))


def with_totals(queryset):
    """Итоги каждого расчёта, посчитанные из записей."""
    return queryset.annotate(
        r_accrued=_sum_of(PayrollLine, Q()),
        r_adjustments=_sum_of(PayrollAdjustment, Q(status=PayrollAdjustment.Status.APPLIED)),
        r_paid=_sum_of(PayrollPayment, Q(status=PayrollPayment.Status.CONFIRMED)),
    )


def dashboard(periods) -> dict:
    payrolls = with_totals(Payroll.objects.filter(period__in=periods).exclude(status=Payroll.Status.VOID))
    accrued = adjustments = paid = ZERO
    employees = set()
    for p in payrolls:
        accrued += p.r_accrued
        adjustments += p.r_adjustments
        paid += p.r_paid
        if p.r_accrued + p.r_adjustments:
            employees.add(p.employee_id)
    return {
        "total_accrued": accrued + adjustments,
        "total_lines": accrued,
        "total_adjustments": adjustments,
        "total_paid": paid,
        "total_due": accrued + adjustments - paid,
        "employees_with_accruals": len(employees),
        "pending_approval": payrolls.filter(status=Payroll.Status.CALCULATED).count(),
        "pending_adjustments": PayrollAdjustment.objects.filter(
            payroll__period__in=periods, status=PayrollAdjustment.Status.PENDING,
        ).count(),
        "with_errors": sum(1 for p in payrolls if p.errors),
    }


def outstanding_debt() -> Decimal:
    """Общая задолженность перед сотрудниками по всем утверждённым начислениям."""
    rows = with_totals(Payroll.objects.filter(status__in=Payroll.LOCKED_STATUSES))
    return sum((p.r_accrued + p.r_adjustments - p.r_paid for p in rows), ZERO)


@dataclass
class Row:
    payroll: Payroll
    employee: str
    position: str
    salary_type: str
    period: str
    accrued: Decimal
    adjustments: Decimal
    paid: Decimal
    due: Decimal
    status: str

    @property
    def total(self) -> Decimal:
        return self.accrued + self.adjustments


@dataclass
class Totals:
    accrued: Decimal = ZERO
    adjustments: Decimal = ZERO
    paid: Decimal = ZERO
    due: Decimal = ZERO

    @property
    def total(self) -> Decimal:
        return self.accrued + self.adjustments


@dataclass
class PayrollReport:
    title: str
    range_label: str
    rows: list[Row] = field(default_factory=list)
    totals: Totals = field(default_factory=Totals)
    by_group: list[tuple[str, str, Decimal]] = field(default_factory=list)
    by_program: list[tuple[str, Decimal]] = field(default_factory=list)
    generated_at: object = None


def period_label(period: PayrollPeriod) -> str:
    return f"{period.start_date:%d.%m.%Y}–{period.end_date:%d.%m.%Y}"


def resolve_periods(*, period_id=None, year=None, month=None, period_type=None):
    if period_id:
        periods = list(PayrollPeriod.objects.filter(pk=period_id))
        label = period_label(periods[0]) if periods else ""
    else:
        qs = PayrollPeriod.objects.filter(year=year, month=month)
        if period_type:
            qs = qs.filter(period_type=period_type)
        periods = list(qs)
        if period_type and periods:
            label = period_label(periods[0])
        else:
            last = calendar.monthrange(int(year), int(month))[1]
            label = f"01.{int(month):02d}.{year}–{last}.{int(month):02d}.{year} (полный месяц)"
    return periods, label


def build_report(periods, *, label: str, payrolls=None) -> PayrollReport:
    qs = payrolls if payrolls is not None else Payroll.objects.filter(period__in=periods)
    qs = with_totals(qs.exclude(status=Payroll.Status.VOID).select_related("employee", "period")).order_by(
        "employee__last_name", "employee__first_name", "period__start_date",
    )
    report = PayrollReport("Сводная ведомость начислений", label, generated_at=timezone.localtime())
    types = dict(SalaryType.choices)
    for p in qs:
        due = p.r_accrued + p.r_adjustments - p.r_paid
        report.rows.append(Row(
            p, p.employee.get_full_name() or p.employee.username, p.position, types.get(p.salary_type, ""),
            period_label(p.period), p.r_accrued, p.r_adjustments, p.r_paid, due, p.get_status_display(),
        ))
        t = report.totals
        t.accrued += p.r_accrued
        t.adjustments += p.r_adjustments
        t.paid += p.r_paid
        t.due += due

    group_sums: dict[int, Decimal] = defaultdict(lambda: ZERO)
    for line in PayrollLine.objects.filter(payroll__in=[r.payroll.pk for r in report.rows]):
        # Процент за цикл курса (и строки прежних версий) несут группу в metadata.
        gid = line.metadata.get("group_id") or (line.source_id if line.source_type == "group" else None)
        if gid:
            group_sums[gid] += line.amount
    groups = {g.pk: g for g in Group.objects.filter(pk__in=group_sums).select_related("course")}
    program_sums: dict[str, Decimal] = defaultdict(lambda: ZERO)
    for gid, amount in sorted(group_sums.items(), key=lambda kv: groups[kv[0]].name):
        report.by_group.append((groups[gid].name, groups[gid].course.name, amount))
        program_sums[groups[gid].course.name] += amount
    report.by_program = sorted(program_sums.items())
    return report


@dataclass
class IndividualReport:
    payroll: Payroll
    employee: str
    position: str
    salary_type: str
    period: str
    lines: list
    adjustments: list
    payments: list
    accrued: Decimal
    adjustments_total: Decimal
    paid: Decimal
    due: Decimal
    generated_at: object


def build_individual(payroll: Payroll) -> IndividualReport:
    p = with_totals(Payroll.objects.filter(pk=payroll.pk)).select_related("employee", "period").get()
    return IndividualReport(
        payroll=p,
        employee=p.employee.get_full_name() or p.employee.username,
        position=p.position,
        salary_type=dict(SalaryType.choices).get(p.salary_type, ""),
        period=period_label(p.period),
        lines=list(p.lines.all()),
        adjustments=list(p.adjustments.filter(status=PayrollAdjustment.Status.APPLIED)),
        payments=list(p.payments.filter(status=PayrollPayment.Status.CONFIRMED)),
        accrued=p.r_accrued,
        adjustments_total=p.r_adjustments,
        paid=p.r_paid,
        due=p.r_accrued + p.r_adjustments - p.r_paid,
        generated_at=timezone.localtime(),
    )
