"""Предварительная зарплата тренера по незавершённым циклам курса.

Оценка считается «на лету» из текущего незавершённого цикла группы
(`CourseCycle` со статусом IN_PROGRESS) и действующих сегодня условий:

    ожидаемая сумма = учитываемые студенты × текущий тариф курса × процент / 100

Это не начисление и не задолженность: оценка нигде не хранится как деньги,
не входит в расчёты, итоги «Начислено / Выплачено / Остаток», аналитику и
отчёты. Окончательное начисление создаётся только при завершении цикла
(services.cycles) — по параметрам на дату его завершения, а не по оценке.
Поэтому изменение состава группы, тарифа или процента сразу меняет оценку,
не трогая утверждённых начислений; в ответе видны все использованные
параметры, чтобы оценку можно было проверить.

Статусы оценки: ESTIMATED — в цикле ещё нет проведённых уроков;
BLOCK_IN_PROGRESS — цикл идёт; READY_FOR_ACCRUAL — порог достигнут, а
начисление ещё не создано (например, нет правила «Процент» на дату порога).
"""
from __future__ import annotations

import datetime as dt
from decimal import Decimal

from django.db.models import Q
from django.utils import timezone

from apps.academy.models import Group, Lesson
from apps.users.models import Teacher

from ..models import CourseCycle, CoursePayrollSettings, CycleAccrual, SalaryRule
from .cycles import (
    _completed_lessons,
    counted_lessons,
    counted_students,
    open_cycles_for,
    percent_rules_on,
    sync_group_safely,
)
from .money import money
from .payout import planned_date_for_completion
from .pricing import price_on

ESTIMATED = "ESTIMATED"
BLOCK_IN_PROGRESS = "BLOCK_IN_PROGRESS"
READY_FOR_ACCRUAL = "READY_FOR_ACCRUAL"
STATUS_LABELS = {
    ESTIMATED: "Предварительный расчёт",
    BLOCK_IN_PROGRESS: "Блок в процессе",
    READY_FOR_ACCRUAL: "Готов к начислению",
}
NOTE = ("Предварительный расчёт — не начисление и не задолженность. Окончательное начисление будет создано "
        "после завершения блока по условиям на дату завершения.")


def _projected_completion(group: Group, settings: CoursePayrollSettings, remaining: int, today: dt.date):
    """Дата урока, на котором будет достигнут порог, — по уже
    запланированным урокам группы (если их хватает), иначе None."""
    if remaining <= 0:
        return today
    upcoming = (
        counted_lessons(group, settings)
        .filter(status__in=(Lesson.Status.SCHEDULED, Lesson.Status.IN_PROGRESS), date__gte=today)
        .order_by("date", "start_time", "id").values_list("date", flat=True)[remaining - 1:remaining]
    )
    return next(iter(upcoming), None)


def _warnings(cycle: CourseCycle, done_rows: list[dict], projected: dt.date | None) -> list[str]:
    warnings = []
    teachers = {r["teacher_id"] for r in done_rows if r["teacher_id"]}
    if len(teachers) > 1:
        names = ", ".join(sorted(str(t) for t in Teacher.objects.filter(pk__in=teachers).select_related("user")))
        warnings.append(f"Уроки блока проводили разные тренеры ({names}) — начисление потребует проверки.")
    if projected is not None and CourseCycle.objects.filter(
        group_id=cycle.group_id, course_id=cycle.course_id, status=CourseCycle.Status.COMPLETED,
        completed_on__year=projected.year, completed_on__month=projected.month,
    ).exists():
        warnings.append("В месяце ожидаемого завершения у группы уже есть завершённый блок — начисление "
                        "потребует проверки бухгалтером.")
    return warnings


def _estimate_rows(cycle: CourseCycle, today: dt.date, *, only_employee=None) -> list[dict]:
    settings = CoursePayrollSettings.objects.filter(course_id=cycle.course_id).first()
    if settings is None:
        return []
    group = cycle.group
    rows = _completed_lessons(group, settings)
    consumed = cycle.lessons_total - cycle.lessons_done
    done_rows = rows[consumed:consumed + cycle.lessons_done]
    remaining = max(cycle.required_lessons - cycle.lessons_done, 0)
    start = cycle.start_date or today
    students = counted_students(group.pk, start, today, settings.student_count_rule)
    price = price_on(settings, today)
    projected = _projected_completion(group, settings, remaining, today)
    status = (READY_FOR_ACCRUAL if remaining == 0 else BLOCK_IN_PROGRESS if cycle.lessons_done else ESTIMATED)
    rules = percent_rules_on(group.pk, cycle.course_id, today)
    if only_employee is not None:
        rules = {k: v for k, v in rules.items() if k == only_employee.pk}
    warnings = _warnings(cycle, done_rows, projected)
    base = money(price * len(students))
    common = {
        "cycle_id": cycle.pk, "cycle_number": cycle.number, "group": group.pk, "group_name": group.name,
        "course": cycle.course_id, "course_name": cycle.course.name,
        "subjects": sorted(cycle.course.subjects.values_list("name", flat=True)),
        "lessons_done": cycle.lessons_done, "required_lessons": cycle.required_lessons,
        "lessons_remaining": remaining, "cycle_start_date": cycle.start_date,
        "student_count": len(students), "student_count_rule": settings.student_count_rule,
        "student_count_rule_display": settings.get_student_count_rule_display(),
        "price_per_student": price, "base_amount": base,
        "projected_completion_date": projected,
        "expected_payment_date": planned_date_for_completion(projected) if projected else None,
        "status": status, "status_display": STATUS_LABELS[status], "is_estimate": True,
        "warnings": warnings, "note": NOTE, "calculated_at": timezone.now(),
    }
    result = []
    for employee_id, rule in rules.items():
        user = rule.employee_profile.employee
        result.append({
            **common, "employee": employee_id, "employee_name": user.get_full_name() or user.username,
            "salary_rule": rule.pk, "percentage": rule.percentage,
            "expected_amount": money(price * len(students) * rule.percentage / Decimal(100)),
        })
    if not rules and only_employee is None:
        result.append({
            **common, "employee": None, "employee_name": "", "salary_rule": None, "percentage": None,
            "expected_amount": None,
            "warnings": [*warnings, "Нет действующего правила «Процент» для тренера группы — начисления не будет."],
        })
    return result


def for_employee(employee, *, today: dt.date | None = None) -> list[dict]:
    """Оценки сотрудника по его незавершённым блокам (только свои)."""
    today = today or timezone.localdate()
    if not SalaryRule.objects.filter(employee_profile__employee=employee, rule_type=SalaryRule.RuleType.PERCENT,
                                     is_active=True).exists():
        return []
    for cycle in open_cycles_for(employee):
        sync_group_safely(cycle.group_id)
    result = []
    for cycle in open_cycles_for(employee):
        result.extend(_estimate_rows(cycle, today, only_employee=employee))
    return result


def all_open(*, today: dt.date | None = None, group=None, course=None, employee=None) -> list[dict]:
    """Оценки по всем незавершённым блокам — для бухгалтерии и директора."""
    today = today or timezone.localdate()
    cycles = CourseCycle.objects.filter(status=CourseCycle.Status.IN_PROGRESS).select_related("group", "course")
    if group:
        cycles = cycles.filter(group_id=group)
    if course:
        cycles = cycles.filter(course_id=course)
    rows = []
    for cycle in cycles.order_by("group__name"):
        rows.extend(_estimate_rows(cycle, today))
    if employee:
        rows = [r for r in rows if r["employee"] == employee]
    return rows


def pending_review(employee=None):
    qs = CycleAccrual.objects.filter(status=CycleAccrual.Status.REVIEW_REQUIRED)
    if employee is not None:
        qs = qs.filter(Q(employee=employee))
    return qs
