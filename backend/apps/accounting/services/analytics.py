"""Финансовая аналитика директора и отчёт по сотрудникам.

Определения показателей (только из записей БД, без предварительных оценок):

* **Начислено за месяц** — строки расчёта + применённые корректировки
  утверждённых (APPROVED / PARTIALLY_PAID / PAID) расчётов, чей расчётный
  период относится к месяцу. Не утверждённые суммы — отдельным показателем
  «ожидает утверждения», в «начислено» не входят.
* **Выплачено по начислениям месяца** — подтверждённые выплаты по этим
  расчётам, когда бы они ни были сделаны.
* **Остаток** — начислено − выплачено по начислениям месяца.
* **Денежные выплаты в месяце** — подтверждённые выплаты с датой перевода в
  месяце, за какой бы месяц ни было начисление (перевод в октябре за
  сентябрь — в октябрьских выплатах, но в сентябрьских начислениях).
* **Сотрудников** — разные сотрудники с утверждённым начислением за месяц.
* **По направлениям** — по снимку направления в расчёте (`Payroll.department`).
  Расчёт принадлежит одному направлению, поэтому выплаты не суммируются дважды.
* **Предварительные оценки** незавершённых циклов сюда не входят никогда.

Отчёт по сотрудникам: строки — строки расчёта (группа, студенты, цена,
процент, уроки, сумма строки). Выплаты относятся к расчёту целиком, а не к
отдельной группе, поэтому «выплачено / остаток» показываются строкой итога
расчёта, а не делятся между группами (правило распределения не утверждено).
"""
from __future__ import annotations

import calendar
import datetime as dt
from collections import defaultdict
from decimal import Decimal

from django.utils import timezone

from ..models import (
    CourseCycle,
    CycleAccrual,
    Department,
    Payroll,
    PayrollLine,
    PayrollPayment,
    PayrollPeriod,
    SalaryType,
)
from .money import ZERO
from .payout import planned_date_for_period
from .report_service import period_label, with_totals

LOCKED = Payroll.LOCKED_STATUSES
PENDING = (Payroll.Status.DRAFT, Payroll.Status.CALCULATED, Payroll.Status.RETURNED)


def _prev(year: int, month: int) -> tuple[int, int]:
    return (year - 1, 12) if month == 1 else (year, month - 1)


def _month_bounds(year: int, month: int) -> tuple[dt.date, dt.date]:
    return dt.date(year, month, 1), dt.date(year, month, calendar.monthrange(year, month)[1])


def department_of(payroll: Payroll) -> str:
    if payroll.department:
        return payroll.department
    profile = getattr(payroll.employee, "salary_profile", None)
    return profile.effective_department if profile is not None else Department.OTHER


def filter_scope(qs, filters: dict, *, prefix: str = ""):
    """Фильтры аналитики по полям расчёта (prefix — путь до Payroll)."""
    f = filters or {}
    if f.get("employee"):
        qs = qs.filter(**{f"{prefix}employee_id": f["employee"]})
    if f.get("salary_type"):
        qs = qs.filter(**{f"{prefix}salary_type": f["salary_type"]})
    if f.get("status"):
        qs = qs.filter(**{f"{prefix}status": f["status"]})
    if f.get("period_type"):
        qs = qs.filter(**{f"{prefix}period__period_type": f["period_type"]})
    if f.get("group"):
        ids = PayrollLine.objects.filter(metadata__group_id=int(f["group"])).values("payroll_id")
        qs = qs.filter(**{f"{prefix}id__in": ids})
    return qs


def _month_payrolls(year: int, month: int, filters: dict):
    qs = Payroll.objects.filter(period__year=year, period__month=month).exclude(status=Payroll.Status.VOID)
    qs = filter_scope(qs, filters).select_related("employee__salary_profile", "period")
    rows = list(with_totals(qs))
    department = (filters or {}).get("department")
    if department:
        rows = [p for p in rows if department_of(p) == department]
    return rows


def _aggregate(rows) -> dict:
    accrued = paid = pending = ZERO
    employees = set()
    for p in rows:
        total = p.r_accrued + p.r_adjustments
        if p.status in LOCKED:
            accrued += total
            paid += p.r_paid
            if total:
                employees.add(p.employee_id)
        elif p.status in PENDING:
            pending += total
    return {"accrued": accrued, "paid": paid, "outstanding": accrued - paid, "awaiting_approval_amount": pending,
            "employees": len(employees)}


def cash_paid(year: int, month: int, filters: dict) -> Decimal:
    lo, hi = _month_bounds(year, month)
    qs = PayrollPayment.objects.filter(status=PayrollPayment.Status.CONFIRMED, payment_date__gte=lo,
                                       payment_date__lte=hi).select_related("payroll__employee__salary_profile")
    qs = filter_scope(qs, filters, prefix="payroll__")
    department = (filters or {}).get("department")
    return sum((p.amount for p in qs if not department or department_of(p.payroll) == department), ZERO)


def by_department(rows) -> list[dict]:
    sums = {d.value: {"accrued": ZERO, "paid": ZERO, "employees": set()} for d in Department}
    for p in rows:
        if p.status not in LOCKED:
            continue
        bucket = sums[department_of(p)]
        bucket["accrued"] += p.r_accrued + p.r_adjustments
        bucket["paid"] += p.r_paid
        bucket["employees"].add(p.employee_id)
    return [
        {"department": d.value, "label": d.label, "accrued": sums[d.value]["accrued"], "paid": sums[d.value]["paid"],
         "outstanding": sums[d.value]["accrued"] - sums[d.value]["paid"], "employees": len(sums[d.value]["employees"])}
        for d in Department
    ]


def upcoming_payments(filters: dict | None = None, *, today: dt.date | None = None, limit: int = 10) -> list[dict]:
    """Ближайшие плановые выплаты: утверждённые расчёты с остатком > 0 —
    по плановой дате (просроченные — первыми, с пометкой)."""
    today = today or timezone.localdate()
    qs = filter_scope(
        Payroll.objects.filter(status__in=(Payroll.Status.APPROVED, Payroll.Status.PARTIALLY_PAID)),
        filters or {},
    ).select_related("employee__salary_profile", "period")
    rows = []
    for p in with_totals(qs):
        due = p.r_accrued + p.r_adjustments - p.r_paid
        if due <= 0:
            continue
        if (filters or {}).get("department") and department_of(p) != filters["department"]:
            continue
        planned = planned_date_for_period(p.period)
        rows.append({
            "payroll_id": p.pk, "employee": p.employee_id,
            "employee_name": p.employee.get_full_name() or p.employee.username,
            "period_label": period_label(p.period), "planned_payment_date": planned, "due": due,
            "status": p.status, "status_display": p.get_status_display(),
            "is_overdue": bool(planned and planned < today),
        })
    rows.sort(key=lambda r: (r["planned_payment_date"] or dt.date.max, r["employee_name"]))
    return rows[:limit]


def summary(year: int, month: int, filters: dict | None = None, *, history_months: int = 12) -> dict:
    filters = filters or {}
    rows = _month_payrolls(year, month, filters)
    current = _aggregate(rows)
    py, pm = _prev(year, month)
    previous = _aggregate(_month_payrolls(py, pm, filters))
    delta = current["accrued"] - previous["accrued"]
    history = []
    y, m = year, month
    for _ in range(history_months):
        agg = _aggregate(_month_payrolls(y, m, filters))
        history.append({"year": y, "month": m, "accrued": agg["accrued"], "paid": agg["paid"],
                        "outstanding": agg["outstanding"], "cash_paid": cash_paid(y, m, filters)})
        y, m = _prev(y, m)
    history.reverse()
    periods = PayrollPeriod.objects.filter(year=year, month=month)
    return {
        "year": year, "month": month,
        **current,
        "cash_paid_in_month": cash_paid(year, month, filters),
        "previous_month": {"year": py, "month": pm, **previous},
        "accrued_change": delta,
        "accrued_change_percent": (
            (delta * 100 / previous["accrued"]).quantize(Decimal("0.1")) if previous["accrued"] else None
        ),
        "by_department": by_department(rows),
        "pending_approval_count": sum(1 for p in rows if p.status == Payroll.Status.CALCULATED),
        "review_required_count": CycleAccrual.objects.filter(status=CycleAccrual.Status.REVIEW_REQUIRED).count(),
        "completed_cycles_without_accrual": CourseCycle.objects.filter(
            status=CourseCycle.Status.COMPLETED, accruals__isnull=True,
        ).count(),
        "open_cycles": CourseCycle.objects.filter(status=CourseCycle.Status.IN_PROGRESS).count(),
        "upcoming_payments": upcoming_payments(filters),
        "history": history,
        "periods": [{"id": p.pk, "period_type": p.period_type, "label": period_label(p), "status": p.status}
                    for p in periods],
    }


# ---------------------------------------------------------------------------
# Отчёт по сотрудникам
# ---------------------------------------------------------------------------

def teacher_report(year: int, month: int, filters: dict | None = None) -> dict:
    filters = filters or {}
    payrolls = _month_payrolls(year, month, filters)
    payrolls.sort(key=lambda p: (p.employee.last_name, p.employee.first_name, p.period.start_date))
    lines_by_payroll = defaultdict(list)
    accruals = {
        a.line_id: a for a in CycleAccrual.objects.filter(payroll__in=[p.pk for p in payrolls], line__isnull=False)
        .select_related("cycle")
    }
    for line in PayrollLine.objects.filter(payroll__in=[p.pk for p in payrolls]).order_by("payroll_id", "id"):
        lines_by_payroll[line.payroll_id].append(line)
    types = dict(SalaryType.choices)
    labels = dict(Department.choices)
    groups, totals = [], {"accrued": ZERO, "adjustments": ZERO, "total": ZERO, "paid": ZERO, "due": ZERO}
    dep_totals = {d.value: {"accrued": ZERO, "paid": ZERO, "due": ZERO} for d in Department}
    group_totals: dict[str, Decimal] = defaultdict(lambda: ZERO)
    for p in payrolls:
        dep = department_of(p)
        planned = planned_date_for_period(p.period)
        total = p.r_accrued + p.r_adjustments
        due = total - p.r_paid
        lines = []
        for line in lines_by_payroll[p.pk]:
            meta = line.metadata or {}
            accrual = accruals.get(line.pk)
            is_cycle = line.line_type == PayrollLine.LineType.PERCENT
            lines.append({
                "line_id": line.pk, "line_type": line.line_type, "line_type_display": line.get_line_type_display(),
                "description": line.description, "group": meta.get("group_id"), "group_name": meta.get("group", ""),
                "course_name": meta.get("course", ""),
                "students": meta.get("students_count") if is_cycle else None,
                "price_per_student": line.rate if is_cycle else None,
                "percentage": line.percentage if is_cycle else None,
                "lessons_done": meta.get("lessons") if is_cycle else None,
                "target_lessons": accrual.cycle.required_lessons if accrual else (meta.get("lessons") if is_cycle else None),
                "completed_on": meta.get("completed_on"),
                "rate": line.rate if not is_cycle else None, "accrued": line.amount,
            })
            if meta.get("group"):
                group_totals[meta["group"]] += line.amount
        groups.append({
            "payroll_id": p.pk, "employee": p.employee_id,
            "employee_name": p.employee.get_full_name() or p.employee.username,
            "department": dep, "department_display": labels.get(dep, dep),
            "period_label": period_label(p.period), "period_type": p.period.period_type,
            "salary_type": p.salary_type, "salary_type_display": types.get(p.salary_type, ""),
            "status": p.status, "status_display": p.get_status_display(),
            "planned_payment_date": planned, "lines": lines,
            "accrued": p.r_accrued, "adjustments": p.r_adjustments, "total": total, "paid": p.r_paid, "due": due,
        })
        totals["accrued"] += p.r_accrued
        totals["adjustments"] += p.r_adjustments
        totals["total"] += total
        totals["paid"] += p.r_paid
        totals["due"] += due
        dep_totals[dep]["accrued"] += total
        dep_totals[dep]["paid"] += p.r_paid
        dep_totals[dep]["due"] += due
    last = calendar.monthrange(year, month)[1]
    return {
        "year": year, "month": month,
        "range_label": f"01.{month:02d}.{year}–{last}.{month:02d}.{year}",
        "payrolls": groups,
        "totals": totals,
        "by_department": [{"department": d, "label": labels[d], **v} for d, v in dep_totals.items() if any(v.values())],
        "by_group": [{"group_name": g, "accrued": v} for g, v in sorted(group_totals.items())],
        "note": "Выплаты учитываются по расчёту целиком и между группами не делятся.",
        "generated_at": timezone.localtime(),
    }

