"""Заработок сотрудника на текущий момент — единый расчёт для «Моей зарплаты»,
кабинета бухгалтера и сверки с «Планом выплат».

Три разных показателя, которые здесь не смешиваются:

1. **Заработано** — сумма за фактически выполненную работу по действующим
   правилам:
   * расчёты зарплаты (оклад, процент за завершённые блоки, корректировки) —
     кроме аннулированных;
   * завершённые блоки, начисление за которые создано, но ещё не вошло в
     расчёт;
   * незавершённые блоки предметов — по урокам, которые сотрудник уже
     провёл, той же формулой, что и официальное начисление за блок
     (`cycles.shares` / `share_amount`): студенты × тариф × процент / 100 ×
     проведённые тренером уроки / уроков в блоке. Оставшиеся уроки не
     учитываются, полная стоимость блока до его завершения не считается.
2. **Официально начислено** — утверждённые расчёты (бухгалтерия их
   зафиксировала).
3. **Компания должна выплатить** — Σ `amount_due` утверждённых расчётов:
   начислено − удержания − выплачено.

Заработок нигде не сохраняется как деньги и не создаёт ни начислений, ни
долга, ни платежей. «План выплат» работает только с утверждёнными расчётами
(п. 2–3), поэтому заработок по незавершённым блокам в план не попадает и не
учитывается дважды: при завершении блока он становится начислением, и
строка «незавершённый блок» исчезает.

Налоги и удержания для заработка — по тем же правилам бухгалтерии:
ежемесячное удержание — один раз за месяц на сотрудника (не за урок, предмет
или блок) и не больше заработанного в этом месяце. Если за месяц уже есть
запись удержания (`AppliedDeduction`), берётся её сумма — история не
переписывается. Официальные удержания — фактически взятые в утверждённых
расчётах.
"""
from __future__ import annotations

import datetime as dt
from collections import defaultdict
from decimal import Decimal

from django.db.models import Q, Sum
from django.utils import timezone

from ..models import (
    AppliedDeduction,
    CoursePayrollSettings,
    CycleAccrual,
    DeductionAllocation,
    DeductionRule,
    EmployeeSalaryProfile,
    Payroll,
    PayrollPayment,
)
from .cycles import counted_students, open_cycles_for, share_amount, shares
from .deductions import applicable_rules
from .money import ZERO
from .payout import planned_date_for_completion, planned_date_for_period
from .pricing import price_on
from .report_service import period_label

MONTHS = ("Январь", "Февраль", "Март", "Апрель", "Май", "Июнь", "Июль", "Август", "Сентябрь", "Октябрь",
          "Ноябрь", "Декабрь")
TAX = DeductionRule.Kind.TAX

OPEN_BLOCK = "OPEN_BLOCK"
ACCRUAL_PENDING = "ACCRUAL_PENDING"
PAYROLL_DRAFT = "PAYROLL_DRAFT"
PAYROLL_OFFICIAL = "PAYROLL_OFFICIAL"
REVIEW = "REVIEW"
SOURCE_LABELS = {
    OPEN_BLOCK: "Блок идёт — официальное начисление после завершения блока",
    ACCRUAL_PENDING: "Блок завершён — начисление ещё не включено в расчёт зарплаты",
    PAYROLL_DRAFT: "Расчёт зарплаты ещё не утверждён",
    PAYROLL_OFFICIAL: "Официально начислено",
    REVIEW: "Требует проверки бухгалтером — не входит в заработок до решения",
}


def _month_label(year: int, month: int) -> str:
    return f"{MONTHS[month - 1]} {year}"


def _open_block_rows(employee, today: dt.date) -> list[dict]:
    """Работа в незавершённых блоках — только по уже проведённым урокам."""
    rows = []
    for cycle in open_cycles_for(employee):
        settings = CoursePayrollSettings.objects.filter(course_id=cycle.course_id).first()
        if settings is None or not cycle.lessons_done:
            continue
        mine = [i for i in shares(cycle, day=today)
                if i["employee_id"] == employee.pk and i["lessons_taught"]]  # только фактически проведённые
        if not mine:
            continue
        students = counted_students(cycle.group_id, cycle.start_date or today, today, settings.student_count_rule)
        price = price_on(settings, today)
        for item in mine:
            rule = item["rule"]
            amount = share_amount(price, len(students), rule.percentage, item["lessons_taught"], cycle.required_lessons)
            rows.append({
                "source": OPEN_BLOCK, "source_display": SOURCE_LABELS[OPEN_BLOCK], "official": False,
                "year": today.year, "month": today.month, "period_label": _month_label(today.year, today.month),
                "cycle_id": cycle.pk, "cycle_number": cycle.number, "group_name": cycle.group.name,
                "course_name": cycle.course.name,
                "subject_name": cycle.subject.name if cycle.subject_id else "Без предмета",
                "lessons_taught": item["lessons_taught"], "lessons_done": cycle.lessons_done,
                "required_lessons": cycle.required_lessons, "student_count": len(students),
                "price_per_student": price, "percentage": rule.percentage, "gross": amount,
                "formula": (f"{len(students)} студ. × {price} сом × {rule.percentage}% × "
                            f"{item['lessons_taught']}/{cycle.required_lessons} ур."),
                "planned_payment_date": None, "payroll_id": None,
            })
    return rows


def _accrual_rows(employee) -> tuple[list[dict], list[dict]]:
    """Завершённые блоки вне расчётов: созданные начисления и спорные."""
    qs = CycleAccrual.objects.filter(employee=employee).filter(
        Q(payroll__isnull=True) | Q(payroll__status=Payroll.Status.VOID),
    ).select_related("cycle__group", "cycle__course", "cycle__subject")
    pending, review = [], []
    for a in qs.filter(status__in=(CycleAccrual.Status.ACCRUED, CycleAccrual.Status.REVIEW_REQUIRED)):
        source = ACCRUAL_PENDING if a.status == CycleAccrual.Status.ACCRUED else REVIEW
        row = {
            "source": source, "source_display": SOURCE_LABELS[source], "official": False,
            "year": a.completed_on.year, "month": a.completed_on.month,
            "period_label": _month_label(a.completed_on.year, a.completed_on.month),
            "cycle_id": a.cycle_id, "cycle_number": a.cycle.number, "group_name": a.cycle.group.name,
            "course_name": a.cycle.course.name,
            "subject_name": a.cycle.subject.name if a.cycle.subject_id else "Без предмета",
            "lessons_taught": a.lessons_taught, "lessons_done": a.lessons, "required_lessons": a.lessons,
            "student_count": a.student_count, "price_per_student": a.course_price, "percentage": a.percentage,
            "gross": a.amount,
            "formula": (f"{a.student_count} студ. × {a.course_price} сом × {a.percentage}% × "
                        f"{a.lessons_taught or a.lessons}/{a.lessons} ур."),
            "planned_payment_date": planned_date_for_completion(a.completed_on), "payroll_id": None,
        }
        (pending if source == ACCRUAL_PENDING else review).append(row)
    return pending, review


def _payroll_rows(employee) -> list[dict]:
    rows = []
    for p in Payroll.objects.filter(employee=employee).exclude(status=Payroll.Status.VOID).select_related("period"):
        official = p.is_locked
        source = PAYROLL_OFFICIAL if official else PAYROLL_DRAFT
        rows.append({
            "source": source, "source_display": SOURCE_LABELS[source], "official": official,
            "year": p.period.year, "month": p.period.month, "period_label": period_label(p.period),
            "payroll_id": p.pk, "payroll_status": p.status, "payroll_status_display": p.get_status_display(),
            "gross": p.total_accrued + p.total_adjustments, "deductions": p.total_deductions,
            "paid": p.total_paid, "due": p.amount_due if official else None,
            "planned_payment_date": planned_date_for_period(p.period),
            "lines": [{"description": line.description, "amount": line.amount} for line in p.lines.all()],
        })
    return rows


def _month_deductions(employee, year: int, month: int, gross: Decimal) -> list[dict]:
    """Удержания месяца для заработанной суммы: по одному на правило за месяц,
    не больше заработанного (к выплате не бывает отрицательным)."""
    headers = {h.series: h for h in AppliedDeduction.objects.filter(employee=employee, year=year, month=month)}
    items = []
    seen = set()
    for rule in applicable_rules(employee, year, month):
        header = headers.get(rule.series)
        items.append((rule.series, header.name if header else rule.name, header.kind if header else rule.kind,
                      header.amount if header else rule.amount))
        seen.add(rule.series)
    for series, header in headers.items():  # уже применённые в утверждённых расчётах — история
        if series not in seen and header.allocations.filter(payroll__status__in=Payroll.LOCKED_STATUSES).exists():
            items.append((series, header.name, header.kind, header.amount))
    left = max(ZERO, gross)
    result = []
    for _series, name, kind, amount in items:
        take = min(amount, left)
        left -= take
        result.append({"name": name, "kind": kind, "kind_display": DeductionRule.Kind(kind).label,
                       "year": year, "month": month, "period_label": _month_label(year, month),
                       "month_amount": amount, "amount": take, "remaining": amount - take})
    return result


def summary(employee, *, today: dt.date | None = None) -> dict:
    """Заработано / удержания / на руки / официально начислено / выплачено /
    остаток — для одного сотрудника."""
    today = today or timezone.localdate()
    payrolls = _payroll_rows(employee)
    pending, review = _accrual_rows(employee)
    open_blocks = _open_block_rows(employee, today)
    earned_rows = payrolls + pending + open_blocks

    by_month: dict[tuple[int, int], Decimal] = defaultdict(lambda: ZERO)
    for row in earned_rows:
        by_month[(row["year"], row["month"])] += row["gross"]
    deductions = []
    for (year, month), gross in sorted(by_month.items()):
        deductions.extend(_month_deductions(employee, year, month, gross))
    deductions = [d for d in deductions if d["month_amount"] > 0]

    earned_gross = sum((r["gross"] for r in earned_rows), ZERO)
    earned_tax = sum((d["amount"] for d in deductions if d["kind"] == TAX), ZERO)
    earned_other = sum((d["amount"] for d in deductions if d["kind"] != TAX), ZERO)
    earned_net = earned_gross - earned_tax - earned_other

    official = [r for r in payrolls if r["official"]]
    official_gross = sum((r["gross"] for r in official), ZERO)
    allocations = DeductionAllocation.objects.filter(
        payroll__employee=employee, payroll__status__in=Payroll.LOCKED_STATUSES)
    official_tax = allocations.filter(applied__kind=TAX).aggregate(s=Sum("amount"))["s"] or ZERO
    official_other = allocations.exclude(applied__kind=TAX).aggregate(s=Sum("amount"))["s"] or ZERO
    paid = PayrollPayment.objects.filter(
        payroll__employee=employee, status=PayrollPayment.Status.CONFIRMED,
    ).exclude(payroll__status=Payroll.Status.VOID).aggregate(s=Sum("amount"))["s"] or ZERO
    company_owes = sum((r["due"] for r in official), ZERO)

    dates = sorted({r["planned_payment_date"] for r in official if r["due"] > 0 and r["planned_payment_date"]}
                   | {r["planned_payment_date"] for r in payrolls + pending
                      if not r["official"] and r["planned_payment_date"]})
    next_date = next((d for d in dates if d >= today), dates[0] if dates else None)

    def total(source):
        return sum((r["gross"] for r in earned_rows + review if r["source"] == source), ZERO)

    reasons = [
        {"source": s, "label": SOURCE_LABELS[s], "amount": total(s)}
        for s in (OPEN_BLOCK, ACCRUAL_PENDING, PAYROLL_DRAFT, REVIEW) if total(s)
    ]
    return {
        "as_of": today,
        "earned": {"gross": earned_gross, "tax": earned_tax, "other_deductions": earned_other, "net": earned_net},
        "official": {"gross": official_gross, "tax": official_tax, "other_deductions": official_other,
                     "net": official_gross - official_tax - official_other},
        "paid": paid,
        "company_owes": company_owes,
        "earned_unpaid": max(ZERO, earned_net - paid),
        "next_payment_date": next_date,
        "difference": earned_gross - official_gross,
        "difference_reasons": reasons,
        "items": sorted(earned_rows + review, key=lambda r: (r["year"], r["month"], r["source"]), reverse=True),
        "deductions": deductions,
    }


def employees_summary(*, today: dt.date | None = None, department: str | None = None, search: str = "") -> list[dict]:
    """Сводка по всем сотрудникам с зарплатным профилем — для бухгалтерии."""
    today = today or timezone.localdate()
    profiles = EmployeeSalaryProfile.objects.select_related("employee").order_by(
        "employee__last_name", "employee__first_name")
    if search:
        profiles = profiles.filter(Q(employee__first_name__icontains=search) | Q(employee__last_name__icontains=search))
    rows = []
    for profile in profiles:
        if department and profile.effective_department != department:
            continue
        data = summary(profile.employee, today=today)
        rows.append({
            "employee": profile.employee_id,
            "employee_name": profile.employee.get_full_name() or profile.employee.username,
            "position": profile.display_position, "salary_type": profile.salary_type,
            "salary_type_display": profile.get_salary_type_display(), "department": profile.effective_department,
            **{k: data[k] for k in ("earned", "official", "paid", "company_owes", "earned_unpaid",
                                    "next_payment_date", "difference", "difference_reasons")},
        })
    return rows


def as_json(value):
    """Суммы — строками с копейками (без float), даты — ISO."""
    if isinstance(value, Decimal):
        return str(value.quantize(Decimal("0.01")))
    if isinstance(value, (dt.date, dt.datetime)):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: as_json(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [as_json(v) for v in value]
    return value
