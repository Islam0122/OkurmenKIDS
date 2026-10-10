"""Автоматический учёт уроков и начисление процента тренеру по циклам курса.

Учёт: уроки группы со статусом «Проведён» (отменённые и запланированные не
считаются), по порядку (дата, время, id), с первого проведённого урока
(или с необязательной даты `count_lessons_from`). Бухгалтер число уроков не
вводит — его даёт LMS.

Интервал — `required_lessons` из настроек курса (Course): при 12 пороги
12, 24, 36, 48…; при 20 — 20, 40, 60… Достигнут очередной порог — цикл
завершён: дата завершения = дата урока, на котором достигнут порог; цикл
фиксируется со снимком (уроки, порог, дата, студенты, стоимость курса), и
тренеру СРАЗУ создаётся начисление `CycleAccrual` по его проценту —
`студенты × стоимость курса × процент / 100`. Уникальность: один цикл с
номером на группу и одно начисление на (цикл, тренер), поэтому повторное
сохранение урока, повторный запуск или пересчёт дублей не создают.

Изменение интервала действует на новые циклы: завершённые хранят свой
порог. Исправление уроков задним числом (урок отменили — порог больше не
достигнут) не удаляет историю: цикл помечается «Отменён», неутверждённое
начисление отменяется, а утверждённое сторнируется корректировкой,
которую утверждает директор; всё пишется в журнал аудита.

Синхронизация запускается автоматически при сохранении/удалении урока
(signals), при расчёте зарплаты, при открытии списка циклов и командой
`manage.py sync_course_cycles`.
"""
from __future__ import annotations

import datetime as dt
import logging

from django.conf import settings as django_settings
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone

from apps.academy.models import Group, Lesson, TrainerAssignment
from apps.users.models import Teacher

from ..models import (
    CourseCycle,
    CoursePayrollSettings,
    CycleAccrual,
    CycleLesson,
    EmployeeSalaryProfile,
    Payroll,
    PayrollAdjustment,
    SalaryRule,
    SalaryType,
)
from . import audit
from .activity import active_student_days, trainer_group_ids_ever
from .money import money
from .pricing import price_on

logger = logging.getLogger(__name__)

Status = CourseCycle.Status
AccrualStatus = CycleAccrual.Status
Rule = CoursePayrollSettings.StudentCountRule


# ---------------------------------------------------------------------------
# Студенты и тренеры цикла
# ---------------------------------------------------------------------------

def counted_students(group_id: int, start, end, rule: str) -> list[int]:
    """Студенты, учитываемые в цикле [start, end] группы, по правилу курса."""
    lo = end if rule == Rule.ON_COMPLETION else (start or end)
    activity = active_student_days(lo, end, group_ids=[group_id])
    if rule == Rule.ON_COMPLETION:
        return sorted(sid for sid, days in activity.items() if days.get(end) == group_id)
    return sorted(sid for sid, days in activity.items() if group_id in days.values())


def responsible(teacher_id, group_id, day) -> bool:
    return TrainerAssignment.objects.filter(
        teacher_id=teacher_id, group_id=group_id, start_date__lte=day,
    ).filter(Q(end_date__isnull=True) | Q(end_date__gt=day)).exists()


def responsible_teacher_names(group_id: int, day) -> list[str]:
    """Тренеры, отвечавшие за группу в день `day` (по истории назначений)."""
    rows = (
        TrainerAssignment.objects.filter(group_id=group_id, start_date__lte=day)
        .filter(Q(end_date__isnull=True) | Q(end_date__gt=day)).select_related("teacher__user")
    )
    return sorted({r.teacher.user.get_full_name() or r.teacher.user.username for r in rows})


def rule_covers_on(rule: SalaryRule, group_id: int, course_id: int, day) -> bool:
    """Правило «Процент» сотрудника распространяется на группу курса в день
    `day`: действует, подходит по курсу/группе, и сотрудник отвечал за группу
    (правило с конкретной группой у сотрудника, который никогда не был в ней
    тренером, — основание сама привязка)."""
    if not rule.is_active or not rule.overlaps(day, day):
        return False
    if rule.group_id and rule.group_id != group_id:
        return False
    if rule.program_id and rule.program_id != course_id:
        return False
    teacher = getattr(rule.employee_profile.employee, "teacher_profile", None)
    teacher_id = teacher.pk if teacher is not None else None
    if rule.group_id and group_id not in trainer_group_ids_ever(teacher_id):
        return True
    return teacher_id is not None and responsible(teacher_id, group_id, day)


def rule_covers(rule: SalaryRule, cycle: CourseCycle) -> bool:
    """Правило покрывает завершённый цикл — на дату его завершения."""
    return rule_covers_on(rule, cycle.group_id, cycle.course_id, cycle.completed_on)


def percent_rules_on(group_id: int, course_id: int, day) -> dict[int, SalaryRule]:
    """{employee_id: правило} — кому положен процент за группу курса в день
    `day` (по одному правилу на сотрудника: при пересечении — первое, расчёт
    покажет ошибку)."""
    profiles = EmployeeSalaryProfile.objects.filter(
        salary_type=SalaryType.PERCENT, is_active=True, effective_from__lte=day,
    ).filter(Q(effective_to__isnull=True) | Q(effective_to__gte=day))
    rules = (
        SalaryRule.objects.filter(employee_profile__in=profiles, rule_type=SalaryRule.RuleType.PERCENT, is_active=True)
        .select_related("employee_profile__employee__teacher_profile").order_by("id")
    )
    result: dict[int, SalaryRule] = {}
    for rule in rules:
        employee_id = rule.employee_profile.employee_id
        if employee_id not in result and rule_covers_on(rule, group_id, course_id, day):
            result[employee_id] = rule
    return result


def percent_rules_for(cycle: CourseCycle) -> dict[int, SalaryRule]:
    return percent_rules_on(cycle.group_id, cycle.course_id, cycle.completed_on)


def accrual_values(cycle: CourseCycle, rule: SalaryRule) -> dict:
    return dict(
        salary_rule=rule, lessons=cycle.required_lessons, lessons_total=cycle.lessons_total,
        completed_on=cycle.completed_on, student_count=cycle.student_count, course_price=cycle.course_price,
        percentage=rule.percentage, amount=money(cycle.course_price * cycle.student_count * rule.percentage / 100),
    )


def review_reasons(cycle: CourseCycle, employee_id: int, rule: SalaryRule | None = None) -> list[str]:
    """Почему начисление за цикл нельзя создать автоматически.

    * Уроки цикла проводили разные тренеры (или не тот, кому положено
      начисление): весь цикл не переносится одному тренеру — правило
      распределения между тренерами не утверждено, решает бухгалтер.
    * У группы уже есть завершённый цикл в этом же календарном месяце:
      стоимость курса — месячная, и начислять процент от полной месячной
      базы за каждый цикл без решения бухгалтера нельзя.
    """
    reasons = []
    links = list(cycle.cycle_lessons.filter(is_live=True).values_list("teacher_id", flat=True))
    teachers = {t for t in links if t is not None}
    if teachers:
        names = {t.pk: str(t) for t in Teacher.objects.filter(pk__in=teachers).select_related("user")}
        counts = {t: links.count(t) for t in teachers}
        recipient = Teacher.objects.filter(user_id=employee_id).values_list("pk", flat=True).first()
        if len(teachers) > 1:
            listed = ", ".join(f"{names[t]} — {counts[t]} ур." for t in sorted(teachers, key=lambda t: names[t]))
            reasons.append(f"Смена тренера внутри цикла: уроки проводили {listed}.")
        elif recipient is not None and recipient not in teachers and not (rule and rule.group_id):
            only = next(iter(teachers))
            reasons.append(
                f"Уроки цикла проводил {names[only]}, а начисление положено по назначению на дату завершения "
                "другому сотруднику."
            )
    if getattr(django_settings, "ACCOUNTING_REVIEW_REPEATED_MONTHLY_CYCLES", True) and cycle.completed_on:
        earlier = CourseCycle.objects.filter(
            group_id=cycle.group_id, course_id=cycle.course_id, status=Status.COMPLETED, number__lt=cycle.number,
            completed_on__year=cycle.completed_on.year, completed_on__month=cycle.completed_on.month,
        ).exclude(pk=cycle.pk).order_by("number").first()
        if earlier is not None:
            reasons.append(
                f"В {cycle.completed_on:%m.%Y} у группы уже завершён цикл {earlier.number} "
                f"({earlier.completed_on:%d.%m.%Y}): месячная стоимость курса не начисляется дважды за месяц "
                "автоматически — подтвердите или отмените начисление."
            )
    return reasons


def ensure_accruals(cycle: CourseCycle, actor=None) -> list[CycleAccrual]:
    """Создать недостающие начисления за завершённый цикл (идемпотентно) и
    обновить ещё не утверждённые, если с тех пор поправили правило.
    Спорный цикл (см. review_reasons) получает начисление в статусе
    «Требует проверки» — в расчёт оно не входит до решения бухгалтера."""
    if cycle.status != Status.COMPLETED:
        return []
    created = []
    for employee_id, rule in percent_rules_for(cycle).items():
        values = accrual_values(cycle, rule)
        reasons = review_reasons(cycle, employee_id, rule)
        defaults = {**values, "status": AccrualStatus.REVIEW_REQUIRED if reasons else AccrualStatus.ACCRUED,
                    "review_reasons": reasons}
        try:
            with transaction.atomic():
                accrual, was_created = CycleAccrual.objects.get_or_create(
                    cycle=cycle, employee_id=employee_id, defaults=defaults,
                )
        except IntegrityError:  # параллельный запуск уже создал
            continue
        if was_created:
            created.append(accrual)
            audit.log(actor, accrual, "auto_accrue", new={
                "group": cycle.group_id, "cycle": cycle.number, "lessons_total": cycle.lessons_total,
                "completed_on": cycle.completed_on, "students": cycle.student_count,
                "course_price": cycle.course_price, "percentage": rule.percentage, "amount": accrual.amount,
                "status": accrual.status, "planned_payment_date": accrual.planned_payment_date,
            })
            if reasons:
                audit.log(actor, accrual, "review_required", new={"status": accrual.status, "reasons": reasons},
                          reason=" ".join(reasons))
        elif accrual.status in (AccrualStatus.ACCRUED, AccrualStatus.REVIEW_REQUIRED) and (
            accrual.amount != values["amount"] or accrual.salary_rule_id != rule.pk
        ):
            old = {"percentage": accrual.percentage, "amount": accrual.amount}
            for name, value in values.items():
                setattr(accrual, name, value)
            accrual.save()
            audit.log(actor, accrual, "update", old=old,
                      new={"percentage": accrual.percentage, "amount": accrual.amount},
                      reason="Правило «Процент» изменено до утверждения начисления.")
    return created


def review_accrual(accrual: CycleAccrual, *, confirm: bool, reason: str, actor) -> CycleAccrual:
    """Решение бухгалтера по спорному начислению: подтвердить (войдёт в
    ближайший расчёт) или отменить (история сохраняется; распределение между
    тренерами — корректировками в их расчётах)."""
    from . import AccountingError

    reason = (reason or "").strip()
    if not reason:
        raise AccountingError("Укажите основание решения.", code="reason_required")
    with transaction.atomic():
        accrual = CycleAccrual.objects.select_for_update().get(pk=accrual.pk)
        if accrual.employee_id == getattr(actor, "pk", None):
            raise AccountingError("Нельзя проверять собственное начисление.", code="own_payroll")
        if accrual.status != AccrualStatus.REVIEW_REQUIRED:
            raise AccountingError("Начисление не ожидает проверки.", code="bad_status")
        old = {"status": accrual.status}
        accrual.status = AccrualStatus.ACCRUED if confirm else AccrualStatus.CANCELLED
        accrual.note = reason
        accrual.reviewed_by, accrual.reviewed_at = actor, timezone.now()
        accrual.save()
        audit.log(actor, accrual, "review_confirm" if confirm else "review_cancel", old=old,
                  new={"status": accrual.status, "amount": accrual.amount}, reason=reason)
    return accrual


# ---------------------------------------------------------------------------
# Исправление уроков после завершения цикла
# ---------------------------------------------------------------------------

def _invalidate(cycle: CourseCycle, lessons_now: int, actor) -> None:
    reason = (
        f"Уроки группы исправлены: проведено {lessons_now}, порог цикла {cycle.number} "
        f"({cycle.lessons_total} уроков) больше не достигнут."
    )
    cycle.status = Status.INVALIDATED
    cycle.invalidated_reason = reason
    cycle.save()
    CycleLesson.objects.filter(cycle=cycle, is_live=True).update(is_live=False)
    audit.log(actor, cycle, "invalidate", old={"status": Status.COMPLETED}, new={"status": cycle.status},
              reason=reason)
    for accrual in cycle.accruals.select_related("payroll", "payroll__period"):
        _reverse(accrual, reason, actor)


def _reverse(accrual: CycleAccrual, reason: str, actor) -> None:
    """Отменить начисление за отменённый цикл, не удаляя историю."""
    from .payroll_calculator import refresh_totals

    old = {"status": accrual.status}
    payroll = accrual.payroll
    if accrual.status in (AccrualStatus.ACCRUED, AccrualStatus.REVIEW_REQUIRED):
        # Ещё не утверждено: убрать строку из черновика и отменить начисление.
        if payroll is not None and payroll.is_editable:
            if accrual.line_id:
                accrual.line.delete()
            payroll = Payroll.objects.select_for_update().get(pk=payroll.pk)
            refresh_totals(payroll)
            payroll.warnings = [*payroll.warnings, f"{reason} Начисление за цикл отменено — проверьте расчёт."]
            payroll.save()
        accrual.status = AccrualStatus.CANCELLED
        accrual.payroll, accrual.line = None, None
        accrual.note = reason
        accrual.save()
        audit.log(actor, accrual, "cancel", old=old, new={"status": accrual.status}, reason=reason, payroll=payroll)
        return
    if accrual.status != AccrualStatus.APPROVED:
        return
    # Утверждено: история не трогается — сторно корректировкой, которую
    # утверждает директор (утверждённое начисление нельзя менять незаметно).
    if payroll.period.status == payroll.period.Status.CLOSED:
        accrual.status = AccrualStatus.CORRECTION_REQUIRED
        accrual.note = f"{reason} Период закрыт — корректировку оформляет директор вручную."
        accrual.save()
        audit.log(actor, accrual, "correction_required", old=old, new={"status": accrual.status},
                  reason=accrual.note, payroll=payroll)
        return
    adjustment = PayrollAdjustment.objects.create(
        payroll=payroll, kind=PayrollAdjustment.Kind.CORRECTION, amount=-accrual.amount,
        reason=f"Сторно начисления за цикл: {reason}", status=PayrollAdjustment.Status.PENDING,
        created_by=actor if getattr(actor, "is_authenticated", False) else None,
    )
    accrual.status = AccrualStatus.CORRECTED
    accrual.adjustment = adjustment
    accrual.note = reason
    accrual.save()
    audit.log(actor, adjustment, "create", new={"kind": adjustment.kind, "amount": adjustment.amount,
                                                "status": adjustment.status, "auto": True},
              reason=adjustment.reason, payroll=payroll)
    audit.log(actor, accrual, "reverse", old=old, new={"status": accrual.status, "adjustment": adjustment.pk},
              reason=reason, payroll=payroll)


# ---------------------------------------------------------------------------
# Синхронизация
# ---------------------------------------------------------------------------

def counted_lessons(group: Group, settings: CoursePayrollSettings):
    """Уроки группы, которые учитываются в циклах курса: только проведённые
    (отменённые и запланированные — нет), с даты начала учёта, и только
    учитываемых предметов, если они заданы (например, только IT-уроки)."""
    lessons = Lesson.objects.filter(group=group)
    if settings.count_lessons_from:
        lessons = lessons.filter(date__gte=settings.count_lessons_from)
    subject_ids = list(settings.counted_subjects.values_list("pk", flat=True)) if settings.pk else []
    if subject_ids:
        lessons = lessons.filter(subject_id__in=subject_ids)
    return lessons


def _completed_lessons(group: Group, settings: CoursePayrollSettings) -> list[dict]:
    lessons = counted_lessons(group, settings).filter(status=Lesson.Status.COMPLETED)
    rows = lessons.order_by("date", "start_time", "id").values("id", "date", "teacher_id", "group_teacher__teacher_id")
    return [
        {"id": r["id"], "date": r["date"], "teacher_id": r["teacher_id"] or r["group_teacher__teacher_id"]}
        for r in rows
    ]


def _link_lessons(cycle: CourseCycle, chunk: list[dict]) -> None:
    """Зафиксировать уроки завершённого цикла (уникальность — индексом БД)."""
    CycleLesson.objects.bulk_create([
        CycleLesson(cycle=cycle, lesson_id=row["id"], lesson_ref=row["id"], lesson_date=row["date"],
                    position=i, teacher_id=row["teacher_id"])
        for i, row in enumerate(chunk, start=1)
    ])


def sync_group(group: Group, settings: CoursePayrollSettings, *, actor=None) -> list[CourseCycle]:
    """Привести циклы группы в соответствие с проведёнными уроками;
    вернуть новые завершённые циклы (начисления по ним уже созданы)."""
    lessons = _completed_lessons(group, settings)
    total = len(lessons)
    created: list[CourseCycle] = []
    with transaction.atomic():
        live = CourseCycle.objects.select_for_update().filter(group=group, course=settings.course).exclude(
            status=Status.INVALIDATED,
        )
        completed = list(live.filter(status=Status.COMPLETED).order_by("number"))
        open_cycle = live.filter(status=Status.IN_PROGRESS).first()
        # Урок исправили задним числом — снять циклы, чей порог больше не достигнут.
        while completed and completed[-1].lessons_total > total:
            _invalidate(completed.pop(), total, actor)
        consumed = completed[-1].lessons_total if completed else 0
        number = len(completed) + 1
        required = settings.required_lessons
        remaining = lessons[consumed:]
        while len(remaining) >= required:
            chunk, remaining = remaining[:required], remaining[required:]
            consumed += required
            start, end = chunk[0]["date"], chunk[-1]["date"]
            students = counted_students(group.pk, start, end, settings.student_count_rule)
            price = price_on(settings, end)
            fields = dict(
                status=Status.COMPLETED, required_lessons=required, lessons_done=required, lessons_total=consumed,
                start_date=start, completed_on=end, last_lesson_id=chunk[-1]["id"], student_count=len(students),
                student_ids=students, student_count_rule=settings.student_count_rule,
                course_price=price,
            )
            if open_cycle is not None:
                open_cycle.number = number
                for name, value in fields.items():
                    setattr(open_cycle, name, value)
                open_cycle.save()
                cycle, open_cycle = open_cycle, None
            else:
                cycle = CourseCycle.objects.create(group=group, course=settings.course, number=number, **fields)
            _link_lessons(cycle, chunk)
            audit.log(actor, cycle, "complete", new={
                "group": group.pk, "number": number, "lessons_total": consumed, "completed_on": end,
                "students": len(students), "course_price": price, "lessons": [row["id"] for row in chunk],
            })
            created.append(cycle)
            number += 1
        progress = dict(
            number=number, required_lessons=required, lessons_done=len(remaining),
            lessons_total=consumed + len(remaining), start_date=remaining[0]["date"] if remaining else None,
        )
        if open_cycle is None:
            try:
                with transaction.atomic():
                    CourseCycle.objects.create(group=group, course=settings.course, status=Status.IN_PROGRESS,
                                               **progress)
            except IntegrityError:  # параллельная синхронизация уже создала
                pass
        elif any(getattr(open_cycle, k) != v for k, v in progress.items()):
            for name, value in progress.items():
                setattr(open_cycle, name, value)
            open_cycle.save()
        for cycle in created:
            ensure_accruals(cycle, actor)
    return created


def sync_course_groups(settings: CoursePayrollSettings, *, actor=None) -> int:
    total = 0
    groups = Group.objects.filter(course=settings.course).exclude(status=Group.Status.CANCELLED).only(
        "id", "course_id", "status",
    )
    for group in groups:
        total += len(sync_group(group, settings, actor=actor))
    return total


def sync_all(*, actor=None) -> int:
    """Синхронизировать все группы курсов с активными настройками.
    Возвращает число новых завершённых циклов."""
    return sum(
        sync_course_groups(settings, actor=actor)
        for settings in CoursePayrollSettings.objects.filter(is_active=True).select_related("course")
    )


def sync_group_safely(group_id: int, actor=None) -> None:
    """Для сигнала урока: ошибка учёта не должна ломать сохранение урока в LMS."""
    try:
        group = Group.objects.select_related("course").get(pk=group_id)
        settings = CoursePayrollSettings.objects.filter(course_id=group.course_id, is_active=True).first()
        if settings is not None and group.status != Group.Status.CANCELLED:
            sync_group(group, settings, actor=actor)
    except Exception:  # noqa: BLE001
        logger.exception("Не удалось обновить циклы курса группы %s", group_id)


def open_cycles_for(employee) -> list[CourseCycle]:
    """Незавершённые циклы групп, за которые сотрудник сейчас отвечает или к
    которым привязано его правило «Процент»."""
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


def today() -> dt.date:
    return timezone.localdate()
