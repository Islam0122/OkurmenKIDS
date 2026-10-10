"""«Моя зарплата» — собственные начисления и выплаты сотрудника.

Только чтение и только по `request.user`: сотрудник передаётся сюда из
представления, никакие id из запроса не используются. Отдельной таблицы
зарплат нет — всё из EmployeeSalaryProfile / SalaryRule / Payroll /
PayrollLine / PayrollAdjustment / PayrollPayment.

Что видит сотрудник: рассчитанные (ещё не утверждённые — с пометкой),
утверждённые, частично и полностью выплаченные начисления. Черновик и
возвращённый на исправление расчёт — «Ожидает расчёта» без сумм (цифры в нём
ещё не проверены бухгалтером); аннулированные не показываются. Итоги
«Начислено / Выплачено / Остаток» — только по утверждённым начислениям.
"""
from __future__ import annotations

import datetime as dt
from decimal import Decimal

from django.utils import timezone

from ..models import EmployeeSalaryProfile, Payroll, PayrollAdjustment, PayrollPayment, PayrollPeriod
from . import estimates as estimates_service
from .money import ZERO
from .payout import planned_date_for_period
from .report_service import period_label

AWAITING = "AWAITING"
STATUS_LABELS = {
    AWAITING: "Ожидает расчёта",
    Payroll.Status.CALCULATED: "Рассчитано, ожидает утверждения",
    Payroll.Status.APPROVED: "Утверждено",
    Payroll.Status.PARTIALLY_PAID: "Частично выплачено",
    Payroll.Status.PAID: "Выплачено",
}
VISIBLE = (Payroll.Status.CALCULATED, *Payroll.LOCKED_STATUSES)
MONTHS = ("Январь", "Февраль", "Март", "Апрель", "Май", "Июнь", "Июль", "Август", "Сентябрь", "Октябрь",
          "Ноябрь", "Декабрь")
HALVES = (PayrollPeriod.PeriodType.FIRST_HALF, PayrollPeriod.PeriodType.SECOND_HALF)


def status_of(payroll: Payroll | None) -> str:
    if payroll is None or payroll.status not in VISIBLE:
        return AWAITING
    return payroll.status


def _money(value) -> str:
    return str(Decimal(value or 0).quantize(Decimal("0.01")))


def _rates(profile: EmployeeSalaryProfile | None, today: dt.date) -> list[dict]:
    if profile is None:
        return []
    rules = profile.rules.filter(is_active=True, effective_from__lte=today).select_related("group", "program")
    result = []
    for rule in rules:
        if rule.effective_to and rule.effective_to < today:
            continue
        result.append({
            "rule_type": rule.rule_type, "label": rule.get_rule_type_display(),
            "amount": _money(rule.amount) if rule.amount is not None else None,
            "percentage": str(rule.percentage) if rule.percentage is not None else None,
            "scope": rule.group.name if rule.group_id else (rule.program.name if rule.program_id else ""),
            "effective_from": rule.effective_from.isoformat(),
        })
    return result


def _row(payroll: Payroll) -> dict:
    status = status_of(payroll)
    shown = status != AWAITING
    adjustments = payroll.adjustments.filter(status=PayrollAdjustment.Status.APPLIED) if shown else []
    accrued = payroll.total_accrued + payroll.total_adjustments
    planned = planned_date_for_period(payroll.period)
    return {
        "payroll_id": payroll.pk,
        "planned_payment_date": planned.isoformat() if planned else None,
        "year": payroll.period.year,
        "month": payroll.period.month,
        "period_type": payroll.period.period_type,
        "period_label": period_label(payroll.period),
        "status": status,
        "status_display": STATUS_LABELS[status],
        "is_final": payroll.is_locked,
        "accrued": _money(accrued) if shown else None,
        "paid": _money(payroll.total_paid) if shown else None,
        "due": _money(payroll.amount_due) if shown else None,
        "lines": [{"description": l.description, "amount": _money(l.amount)} for l in payroll.lines.all()] if shown else [],
        "adjustments": [{"kind": a.get_kind_display(), "reason": a.reason, "amount": _money(a.amount)} for a in adjustments],
    }


def _payments(employee, payrolls_qs) -> list[dict]:
    payments = (
        PayrollPayment.objects.filter(payroll__employee=employee, payroll__in=payrolls_qs,
                                      status=PayrollPayment.Status.CONFIRMED)
        .select_related("payroll__period").order_by("-payment_date", "-id")
    )
    return [
        {"id": p.pk, "payment_date": p.payment_date.isoformat(), "amount": _money(p.amount),
         "method": p.get_payment_method_display(), "is_advance": p.is_advance, "reference": p.reference,
         "period_label": period_label(p.payroll.period), "payroll_id": p.payroll_id}
        for p in payments
    ]


def _estimate(e: dict) -> dict:
    """Предварительная оценка блока для сотрудника — без чужих данных и без
    списка студентов (только их число)."""
    def iso(value):
        return value.isoformat() if value else None

    return {
        "cycle_id": e["cycle_id"], "cycle_number": e["cycle_number"], "group_name": e["group_name"],
        "course_name": e["course_name"], "subjects": e["subjects"], "student_count": e["student_count"],
        "price_per_student": _money(e["price_per_student"]), "percentage": str(e["percentage"]),
        "expected_amount": _money(e["expected_amount"]), "lessons_done": e["lessons_done"],
        "required_lessons": e["required_lessons"], "lessons_remaining": e["lessons_remaining"],
        "projected_completion_date": iso(e["projected_completion_date"]),
        "expected_payment_date": iso(e["expected_payment_date"]),
        "status": e["status"], "status_display": e["status_display"], "warnings": e["warnings"], "note": e["note"],
    }


def build(employee, *, year: int | None = None, month: int | None = None, period_type: str | None = None) -> dict:
    today = timezone.localdate()
    profile = EmployeeSalaryProfile.objects.filter(employee=employee).first()
    own = Payroll.objects.filter(employee=employee).exclude(status=Payroll.Status.VOID).select_related("period")
    locked = own.filter(status__in=Payroll.LOCKED_STATUSES)

    accrued = sum((p.total_accrued + p.total_adjustments for p in locked), ZERO)
    paid = sum((p.total_paid for p in locked), ZERO)
    pending = sum((p.total_accrued + p.total_adjustments for p in own.filter(status=Payroll.Status.CALCULATED)), ZERO)
    last = (
        PayrollPayment.objects.filter(payroll__employee=employee, status=PayrollPayment.Status.CONFIRMED)
        .order_by("-payment_date", "-id").first()
    )

    current = []
    by_half = {p.period.period_type: p for p in own.filter(period__year=today.year, period__month=today.month)}
    # Оклад — один месячный расчёт, процент — две половины месяца (плюс любые
    # уже существующие расчёты этого месяца, например прежней схемы).
    expected = (PayrollPeriod.PeriodType.MONTH,) if profile and profile.salary_type == "FIXED" else HALVES
    kinds = [k for k in (*HALVES, PayrollPeriod.PeriodType.MONTH) if k in expected or k in by_half]
    for half in kinds:
        start, end = PayrollPeriod.bounds(today.year, today.month, half)
        payroll = by_half.get(half)
        row = _row(payroll) if payroll else {
            "payroll_id": None, "year": today.year, "month": today.month, "period_type": half,
            "period_label": f"{start:%d.%m.%Y}–{end:%d.%m.%Y}", "status": AWAITING,
            "status_display": STATUS_LABELS[AWAITING], "is_final": False, "accrued": None, "paid": None,
            "due": None, "lines": [], "adjustments": [],
            "planned_payment_date": (lambda d: d.isoformat() if d else None)(
                planned_date_for_period(PayrollPeriod(year=today.year, month=today.month, period_type=half,
                                                      start_date=start, end_date=end))),
        }
        current.append(row)
    month_accrued = sum((Decimal(r["accrued"]) for r in current if r["accrued"] is not None), ZERO)

    history = own.order_by("-period__end_date", "-period__start_date")
    if year:
        history = history.filter(period__year=year)
    if month:
        history = history.filter(period__month=month)
    if period_type:
        history = history.filter(period__period_type=period_type)
    history = history.prefetch_related("lines", "adjustments")

    # Предварительная зарплата — отдельно от начислений: не входит ни в
    # «Начислено», ни в «Остаток» (это не задолженность).
    estimates = estimates_service.for_employee(employee, today=today)
    estimated = sum((e["expected_amount"] for e in estimates), ZERO)
    upcoming = sorted(
        (planned_date_for_period(p.period), p) for p in locked.filter(amount_due__gt=0)
        if planned_date_for_period(p.period) is not None
    )
    next_planned = next((d for d, _ in upcoming if d >= today), upcoming[0][0] if upcoming else None)

    return {
        "employee_name": employee.get_full_name() or employee.username,
        "has_profile": profile is not None,
        "profile": None if profile is None else {
            "salary_type": profile.salary_type,
            "salary_type_display": profile.get_salary_type_display(),
            "position": profile.display_position,
            "rates": _rates(profile, today),
        },
        "totals": {
            "accrued": _money(accrued), "paid": _money(paid), "due": _money(accrued - paid),
            "pending_approval": _money(pending), "estimated": _money(estimated),
        },
        "next_planned_payment_date": next_planned.isoformat() if next_planned else None,
        "estimates": [_estimate(e) for e in estimates],
        "last_payment": None if last is None else {
            "payment_date": last.payment_date.isoformat(), "amount": _money(last.amount),
        },
        "current_month": {
            "year": today.year, "month": today.month, "label": f"{MONTHS[today.month - 1]} {today.year}",
            "accrued": _money(month_accrued), "periods": current,
        },
        "history": [_row(p) for p in history],
        "payments": _payments(employee, history),
        "filters": {"year": year, "month": month, "period_type": period_type},
    }
