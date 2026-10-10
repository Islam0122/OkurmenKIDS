"""Расчётные циклы курсов — по фактически проведённым урокам группы.

Правило: уроки группы со статусом «Проведён» начиная с даты
`count_lessons_from` из настроек курса, по порядку (дата, время, id).
Каждые `required_lessons` таких уроков — один завершённый цикл. Дата
завершения — дата последнего необходимого урока (а не ручного изменения
статуса группы). Остаток уроков — текущий незавершённый цикл.

Завершённый цикл фиксируется один раз со снимком (уроки, дата, студенты,
стоимость курса) и потом не меняется: ни изменение `required_lessons` или
цены в настройках, ни правка уроков задним числом его не переписывают.
Новые настройки действуют только на следующие циклы.

Из LMS читаются только нужные поля: у урока — id, дата, время; студенты —
через шлюз `activity` (id, группа, статус, даты).
"""
from __future__ import annotations

from django.db import IntegrityError, transaction

from apps.academy.models import Group, Lesson

from ..models import CourseCycle, CoursePayrollSettings
from .activity import active_student_days

Status = CourseCycle.Status
Rule = CoursePayrollSettings.StudentCountRule


def _completed_lessons(group: Group, settings: CoursePayrollSettings) -> list[dict]:
    return list(
        Lesson.objects.filter(group=group, status=Lesson.Status.COMPLETED, date__gte=settings.count_lessons_from)
        .order_by("date", "start_time", "id").values("id", "date")
    )


def counted_students(group_id: int, start, end, rule: str) -> list[int]:
    """Студенты, учитываемые в цикле [start, end] группы, по правилу курса."""
    lo = end if rule == Rule.ON_COMPLETION else (start or end)
    activity = active_student_days(lo, end, group_ids=[group_id])
    if rule == Rule.ON_COMPLETION:
        return sorted(sid for sid, days in activity.items() if days.get(end) == group_id)
    return sorted(sid for sid, days in activity.items() if group_id in days.values())


def sync_group(group: Group, settings: CoursePayrollSettings) -> list[CourseCycle]:
    """Зафиксировать новые завершённые циклы группы и обновить текущий."""
    lessons = _completed_lessons(group, settings)
    with transaction.atomic():
        cycles = CourseCycle.objects.select_for_update().filter(group=group, course=settings.course)
        completed = list(cycles.filter(status=Status.COMPLETED).order_by("number"))
        consumed = sum(c.required_lessons for c in completed)
        remaining = lessons[consumed:]
        number = len(completed) + 1
        required = settings.required_lessons
        open_cycle = cycles.filter(status=Status.IN_PROGRESS).first()
        created = []
        while len(remaining) >= required:
            chunk, remaining = remaining[:required], remaining[required:]
            start, end = chunk[0]["date"], chunk[-1]["date"]
            students = counted_students(group.pk, start, end, settings.student_count_rule)
            fields = dict(
                status=Status.COMPLETED, required_lessons=required, lessons_done=required, start_date=start,
                completed_on=end, last_lesson_id=chunk[-1]["id"], student_count=len(students), student_ids=students,
                student_count_rule=settings.student_count_rule, course_price=settings.price_per_student,
            )
            if open_cycle is not None and open_cycle.number == number:
                for name, value in fields.items():
                    setattr(open_cycle, name, value)
                open_cycle.save()
                created.append(open_cycle)
                open_cycle = None
            else:
                created.append(CourseCycle.objects.create(group=group, course=settings.course, number=number, **fields))
            number += 1
        progress = dict(
            required_lessons=required, lessons_done=len(remaining),
            start_date=remaining[0]["date"] if remaining else None,
        )
        if open_cycle is None:
            try:
                with transaction.atomic():
                    CourseCycle.objects.create(group=group, course=settings.course, number=number,
                                               status=Status.IN_PROGRESS, **progress)
            except IntegrityError:  # параллельная синхронизация уже создала
                pass
        else:
            changed = open_cycle.number != number or any(getattr(open_cycle, k) != v for k, v in progress.items())
            if changed:
                open_cycle.number = number
                for name, value in progress.items():
                    setattr(open_cycle, name, value)
                open_cycle.save()
    return created


def sync_all() -> int:
    """Синхронизировать циклы всех групп курсов с активными настройками.
    Возвращает число новых завершённых циклов."""
    total = 0
    for settings in CoursePayrollSettings.objects.filter(is_active=True).select_related("course"):
        groups = Group.objects.filter(course=settings.course).exclude(status=Group.Status.CANCELLED).only(
            "id", "course_id", "status",
        )
        for group in groups:
            total += len(sync_group(group, settings))
    return total


def responsible_teacher_names(group_id: int, day) -> list[str]:
    """Тренеры, отвечавшие за группу в день `day` (по истории назначений)."""
    from django.db.models import Q

    from apps.academy.models import TrainerAssignment

    rows = (
        TrainerAssignment.objects.filter(group_id=group_id, start_date__lte=day)
        .filter(Q(end_date__isnull=True) | Q(end_date__gt=day)).select_related("teacher__user")
    )
    return sorted({r.teacher.user.get_full_name() or r.teacher.user.username for r in rows})


def open_cycles_for(employee) -> list[CourseCycle]:
    """Незавершённые циклы групп, за которые сотрудник сейчас отвечает или к
    которым привязано его правило «Процент»."""
    from django.db.models import Q

    from apps.academy.models import TrainerAssignment

    from ..models import SalaryRule

    teacher = getattr(employee, "teacher_profile", None)
    group_ids = set(
        SalaryRule.objects.filter(employee_profile__employee=employee, rule_type=SalaryRule.RuleType.PERCENT,
                                  is_active=True, group__isnull=False).values_list("group_id", flat=True)
    )
    if teacher is not None:
        group_ids |= set(TrainerAssignment.objects.filter(teacher=teacher, end_date__isnull=True)
                         .values_list("group_id", flat=True))
    return list(
        CourseCycle.objects.filter(status=Status.IN_PROGRESS, group_id__in=group_ids)
        .select_related("group", "course").order_by("group__name")
    )
