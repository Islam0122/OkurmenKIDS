"""Предварительная зарплата тренера по незавершённым циклам курса.

Оценка считается «на лету» из текущего незавершённого цикла ПРЕДМЕТА группы
(`CourseCycle` со статусом IN_PROGRESS) и действующих сегодня условий:

    ожидаемая сумма = студенты × текущий тариф × процент / 100 × ожидаемые
                      уроки тренера / уроков в цикле

Ожидаемые уроки тренера: уже проведённые им уроки цикла плюс оставшиеся, если
он сейчас ведёт этот предмет (один тренер провёл весь блок — полная сумма).

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

from django.db.models import Q
from django.utils import timezone

from apps.academy.models import Group, Lesson

from ..models import CourseCycle, CoursePayrollSettings, CycleAccrual, SalaryRule
from .cycles import (
    counted_lessons,
    counted_students,
    current_subject_teacher_ids,
    open_cycles_for,
    share_amount,
    shares,
    sync_group_safely,
    teacher_names,
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
        "после завершения блока предмета по фактически проведённым урокам и условиям на дату завершения.")


def _projected_completion(group: Group, settings: CoursePayrollSettings, subject_id, remaining: int, today: dt.date):
    """Дата урока, на котором предмет достигнет порога, — по уже
    запланированным урокам ЭТОГО предмета (если их хватает), иначе None."""
    if remaining <= 0:
        return today
    lessons = counted_lessons(group, settings).filter(
        status__in=(Lesson.Status.SCHEDULED, Lesson.Status.IN_PROGRESS), date__gte=today,
    )
    lessons = lessons.filter(subject_id=subject_id) if subject_id else lessons.filter(subject__isnull=True)
    upcoming = lessons.order_by("date", "start_time", "id").values_list("date", flat=True)[remaining - 1:remaining]
    return next(iter(upcoming), None)


def expected_teacher_lessons(cycle: CourseCycle) -> dict[str, int]:
    """Ожидаемое распределение уроков цикла: уже проведённые — как есть,
    оставшиеся — текущему тренеру предмета (если он один)."""
    lessons = dict(cycle.teacher_lessons)
    remaining = max(cycle.required_lessons - cycle.lessons_done, 0)
    current = current_subject_teacher_ids(cycle.group_id, cycle.subject_id)
    if remaining and len(current) == 1:
        teacher = str(next(iter(current)))
        lessons[teacher] = lessons.get(teacher, 0) + remaining
    return lessons


def _warnings(cycle: CourseCycle, projected: dt.date | None) -> list[str]:
    warnings = []
    if projected is not None and CourseCycle.objects.filter(
        group_id=cycle.group_id, course_id=cycle.course_id, subject_id=cycle.subject_id, per_subject=True,
        status=CourseCycle.Status.COMPLETED, completed_on__year=projected.year, completed_on__month=projected.month,
    ).exists():
        warnings.append("В месяце ожидаемого завершения по этому предмету уже есть завершённый блок — начисление "
                        "потребует проверки бухгалтером.")
    return warnings


def _estimate_rows(cycle: CourseCycle, today: dt.date, *, only_employee=None) -> list[dict]:
    settings = CoursePayrollSettings.objects.filter(course_id=cycle.course_id).first()
    if settings is None:
        return []
    group = cycle.group
    remaining = max(cycle.required_lessons - cycle.lessons_done, 0)
    start = cycle.start_date or today
    students = counted_students(group.pk, start, today, settings.student_count_rule)
    price = price_on(settings, today)
    projected = _projected_completion(group, settings, cycle.subject_id, remaining, today)
    status = (READY_FOR_ACCRUAL if remaining == 0 else BLOCK_IN_PROGRESS if cycle.lessons_done else ESTIMATED)
    expected = expected_teacher_lessons(cycle)
    items = shares(cycle, teacher_lessons=expected, day=today)
    if only_employee is not None:
        items = [i for i in items if i["employee_id"] == only_employee.pk]
    names = teacher_names(int(k) for k in cycle.teacher_lessons)
    common = {
        "cycle_id": cycle.pk, "cycle_number": cycle.number, "group": group.pk, "group_name": group.name,
        "course": cycle.course_id, "course_name": cycle.course.name,
        "subject": cycle.subject_id, "subject_name": cycle.subject.name if cycle.subject_id else "Без предмета",
        "subjects": [cycle.subject.name] if cycle.subject_id else [],
        "lessons_done": cycle.lessons_done, "required_lessons": cycle.required_lessons,
        "lessons_remaining": remaining, "cycle_start_date": cycle.start_date,
        "trainers": [{"name": names.get(int(k), "—"), "lessons": v} for k, v in cycle.teacher_lessons.items()],
        "student_count": len(students), "student_count_rule": settings.student_count_rule,
        "student_count_rule_display": settings.get_student_count_rule_display(),
        "price_per_student": price, "base_amount": money(price * len(students)),
        "projected_completion_date": projected,
        "expected_payment_date": planned_date_for_completion(projected) if projected else None,
        "status": status, "status_display": STATUS_LABELS[status], "is_estimate": True,
        "warnings": _warnings(cycle, projected), "note": NOTE, "calculated_at": timezone.now(),
    }
    result = []
    for item in items:
        user = item["rule"].employee_profile.employee
        taught = item["lessons_taught"]
        result.append({
            **common, "employee": item["employee_id"], "employee_name": user.get_full_name() or user.username,
            "salary_rule": item["rule"].pk, "percentage": item["rule"].percentage,
            "expected_lessons": item["numerator"],
            "share_label": f"{item['numerator']} из {cycle.required_lessons} уроков" if taught is not None else "весь блок",
            "expected_amount": share_amount(price, len(students), item["rule"].percentage, item["numerator"],
                                            cycle.required_lessons),
        })
    if not items and only_employee is None:
        result.append({
            **common, "employee": None, "employee_name": "", "salary_rule": None, "percentage": None,
            "expected_lessons": None, "share_label": "", "expected_amount": None,
            "warnings": [*common["warnings"], "Нет тренера предмета с действующим правилом «Процент» — "
                                              "начисления не будет."],
        })
    return result


def for_employee(employee, *, today: dt.date | None = None) -> list[dict]:
    """Оценки сотрудника по его незавершённым блокам предметов (только свои)."""
    today = today or timezone.localdate()
    if not SalaryRule.objects.filter(employee_profile__employee=employee, rule_type=SalaryRule.RuleType.PERCENT,
                                     is_active=True).exists():
        return []
    for group_id in {c.group_id for c in open_cycles_for(employee)}:
        sync_group_safely(group_id)
    result = []
    for cycle in open_cycles_for(employee):
        result.extend(_estimate_rows(cycle, today, only_employee=employee))
    return result


def all_open(*, today: dt.date | None = None, group=None, course=None, employee=None, subject=None) -> list[dict]:
    """Оценки по всем незавершённым блокам предметов — для бухгалтерии и директора."""
    today = today or timezone.localdate()
    cycles = CourseCycle.objects.filter(status=CourseCycle.Status.IN_PROGRESS, per_subject=True).select_related(
        "group", "course", "subject",
    )
    if group:
        cycles = cycles.filter(group_id=group)
    if course:
        cycles = cycles.filter(course_id=course)
    if subject:
        cycles = cycles.filter(subject_id=subject)
    rows = []
    for cycle in cycles.order_by("group__name", "subject__name"):
        rows.extend(_estimate_rows(cycle, today))
    if employee:
        rows = [r for r in rows if r["employee"] == employee]
    return rows


def pending_review(employee=None):
    qs = CycleAccrual.objects.filter(status=CycleAccrual.Status.REVIEW_REQUIRED)
    if employee is not None:
        qs = qs.filter(Q(employee=employee))
    return qs
