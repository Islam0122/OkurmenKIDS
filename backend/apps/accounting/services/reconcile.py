"""Сверка финансовых данных — только чтение, ничего не исправляет.

Используется перед и после миграции на staging/production
(`manage.py payroll_reconcile`): показывает расхождения сохранённых итогов с
записями, противоречивые статусы, данные, требующие проверки (перенесённые
тарифы, циклы без привязки уроков, начисления «Требует проверки»), и
несопоставленные значения (профили без направления).
"""
from __future__ import annotations

from collections import Counter
from decimal import Decimal

from django.db.models import Count, Sum

from ..models import (
    CourseCycle,
    CoursePayrollSettings,
    CoursePriceVersion,
    CycleAccrual,
    CycleLesson,
    EmployeeSalaryProfile,
    Payroll,
    PayrollAdjustment,
    PayrollPayment,
)
from .money import ZERO, money


def _payroll_ref(p: Payroll) -> dict:
    return {"payroll_id": p.pk, "employee": str(p.employee), "period": str(p.period), "status": p.status}


def run() -> dict:
    totals_mismatch, status_mismatch, overpaid = [], [], []
    grand = {"accrued": ZERO, "adjustments": ZERO, "paid": ZERO, "due": ZERO}
    for p in Payroll.objects.exclude(status=Payroll.Status.VOID).select_related("employee", "period"):
        lines = p.lines.aggregate(s=Sum("amount"))["s"] or ZERO
        adj = p.adjustments.filter(status=PayrollAdjustment.Status.APPLIED).aggregate(s=Sum("amount"))["s"] or ZERO
        paid = p.payments.filter(status=PayrollPayment.Status.CONFIRMED).aggregate(s=Sum("amount"))["s"] or ZERO
        due = lines + adj - paid
        grand["accrued"] += lines
        grand["adjustments"] += adj
        grand["paid"] += paid
        grand["due"] += due
        if (p.total_accrued, p.total_adjustments, p.total_paid, p.amount_due) != (lines, adj, paid, due):
            totals_mismatch.append({**_payroll_ref(p), "stored": {
                "accrued": str(p.total_accrued), "adjustments": str(p.total_adjustments), "paid": str(p.total_paid),
                "due": str(p.amount_due)}, "records": {
                "accrued": str(lines), "adjustments": str(adj), "paid": str(paid), "due": str(due)}})
        if due < 0:
            overpaid.append({**_payroll_ref(p), "due": str(due)})
        expected = None
        if p.is_locked:
            expected = (Payroll.Status.APPROVED if paid <= 0 else Payroll.Status.PAID if due <= 0
                        else Payroll.Status.PARTIALLY_PAID)
        elif paid > 0:
            expected = "без выплат (расчёт не утверждён)"
        if expected and expected != p.status:
            status_mismatch.append({**_payroll_ref(p), "expected": expected})

    accrual_mismatch = []
    for a in CycleAccrual.objects.select_related("payroll", "cycle"):
        amount = money(a.course_price * a.student_count * a.percentage / Decimal(100))
        if amount != a.amount:
            accrual_mismatch.append({"accrual_id": a.pk, "stored": str(a.amount), "formula": str(amount)})
        if a.status == CycleAccrual.Status.APPROVED and (a.payroll is None or not a.payroll.is_locked):
            accrual_mismatch.append({"accrual_id": a.pk, "problem": "утверждено, но расчёт не утверждён"})
        if a.status == CycleAccrual.Status.ACCRUED and a.payroll is not None and a.payroll.is_locked:
            accrual_mismatch.append({"accrual_id": a.pk, "problem": "в утверждённом расчёте, но статус «Начислено»"})

    duplicate_lessons = [
        {"lesson_ref": row["lesson_ref"], "cycles": row["n"]}
        for row in CycleLesson.objects.filter(is_live=True).values("lesson_ref").annotate(n=Count("id")).filter(n__gt=1)
    ]
    linked = set(CycleLesson.objects.values_list("cycle_id", flat=True))
    cycles_without_links = [
        {"cycle_id": c.pk, "group": c.group.name, "number": c.number, "completed_on": c.completed_on}
        for c in CourseCycle.objects.filter(status=CourseCycle.Status.COMPLETED).select_related("group")
        if c.pk not in linked
    ]
    backfilled = CycleLesson.objects.filter(backfilled=True).values("cycle_id").distinct().count()
    lesson_counts = Counter(CycleLesson.objects.filter(is_live=True).values_list("cycle_id", flat=True))
    short_cycles = [
        {"cycle_id": c.pk, "group": c.group.name, "number": c.number, "linked": lesson_counts.get(c.pk, 0),
         "required": c.required_lessons}
        for c in CourseCycle.objects.filter(status=CourseCycle.Status.COMPLETED, pk__in=lesson_counts).select_related("group")
        if lesson_counts.get(c.pk, 0) != c.required_lessons
    ]
    priced = set(CoursePriceVersion.objects.values_list("course_id", flat=True))
    return {
        "totals": {k: str(v) for k, v in grand.items()},
        "payroll_totals_mismatch": totals_mismatch,
        "payroll_status_mismatch": status_mismatch,
        "overpaid_payrolls": overpaid,
        "cycle_accrual_mismatch": accrual_mismatch,
        "lessons_in_several_live_cycles": duplicate_lessons,
        "completed_cycles_without_lesson_links": cycles_without_links,
        "cycles_with_backfilled_links": backfilled,
        "cycles_with_wrong_link_count": short_cycles,
        "accruals_review_required": list(
            CycleAccrual.objects.filter(status=CycleAccrual.Status.REVIEW_REQUIRED).values_list("pk", flat=True)
        ),
        "accruals_correction_required": list(
            CycleAccrual.objects.filter(status=CycleAccrual.Status.CORRECTION_REQUIRED).values_list("pk", flat=True)
        ),
        "courses_without_price_history": [
            s.course.name for s in CoursePayrollSettings.objects.select_related("course") if s.course_id not in priced
        ],
        "migrated_prices_to_verify": [
            {"course": v.course.name, "price": str(v.price_per_student), "version_id": v.pk}
            for v in CoursePriceVersion.objects.filter(is_migrated=True).select_related("course")
        ],
        "profiles_without_department": [
            {"profile_id": p.pk, "employee": str(p.employee), "derived": p.effective_department}
            for p in EmployeeSalaryProfile.objects.filter(department="").select_related("employee")
        ],
        "legacy_salary_types": list(
            EmployeeSalaryProfile.objects.exclude(salary_type__in=("FIXED", "PERCENT")).values_list("pk", flat=True)
        ),
    }


def problems_count(report: dict) -> int:
    keys = ("payroll_totals_mismatch", "payroll_status_mismatch", "overpaid_payrolls", "cycle_accrual_mismatch",
            "lessons_in_several_live_cycles", "cycles_with_wrong_link_count")
    return sum(len(report[k]) for k in keys)
