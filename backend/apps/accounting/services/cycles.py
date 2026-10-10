"""Автоматический учёт уроков и начисление процента тренеру — по предметам.

Циклы ведутся отдельно для каждой пары «группа + предмет»: у IT, English и
Soft Skills одной группы свои уроки, нумерация циклов и прогресс. Урок
одного предмета никогда не увеличивает счётчик другого, а завершение цикла
по IT не завершает циклы остальных предметов.

Учёт: уроки группы со статусом «Проведён» (отменённые и запланированные не
считаются), по порядку (дата, время, id), с необязательной даты
`count_lessons_from` и только учитываемых предметов курса (если заданы).
Бухгалтер число уроков не вводит — его даёт LMS.

Интервал — `required_lessons` из настроек курса: при 12 пороги предмета 12,
24, 36…; при 20 — 20, 40, 60… Достигнут порог — цикл предмета завершён
(дата завершения = дата урока порога), фиксируется со снимком (уроки,
фактические тренеры и их уроки, студенты, тариф), и начисления создаются
сразу.

Кому и сколько: тренерам, ФАКТИЧЕСКИ проводившим уроки цикла (`Lesson.teacher`,
иначе тренер программы группы), при действующем правиле «Процент»:

    студенты × тариф × процент тренера / 100 × (его уроки / уроков в цикле)

— правило курса `trainer_split_rule = BY_LESSONS` (по умолчанию). Один
тренер провёл весь цикл — получает полную сумму; замена на 3 урока из 12 —
3/12 замене и 9/12 основному тренеру. Смена тренера сама по себе на проверку
не отправляет. Правило `REVIEW` — при нескольких тренерах доли предлагаются,
а решение принимает бухгалтер. Сотрудник с правилом, привязанным к группе,
который никогда не был в ней тренером, получает полную сумму (основание —
сама привязка, как и раньше).

Уникальность: один живой цикл с номером на группу и предмет и одно
начисление на (цикл, сотрудник) — повторное сохранение урока, повторный
запуск или пересчёт дублей не создают.

Переход с общего цикла группы: исторические циклы (`per_subject=False`)
остаются историей со своими начислениями; их уроки (по привязке, иначе —
все уроки группы до последнего урока последнего такого цикла) в предметные
циклы повторно не попадают, поэтому оплаченный урок не оплачивается дважды.

Исправление уроков задним числом не удаляет историю: цикл помечается
«Отменён», неутверждённое начисление отменяется, утверждённое сторнируется
корректировкой, которую утверждает директор; всё пишется в журнал аудита.
"""
from __future__ import annotations

import datetime as dt
import logging
from collections import Counter
from decimal import Decimal

from django.conf import settings as django_settings
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone

from apps.academy.models import Group, GroupTeacher, Lesson, TrainerAssignment
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
Split = CoursePayrollSettings.TrainerSplitRule
SHARE_Q = Decimal("0.0001")


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
    """Тренеры, отвечавшие за группу в день `day` (для исторических циклов)."""
    rows = (
        TrainerAssignment.objects.filter(group_id=group_id, start_date__lte=day)
        .filter(Q(end_date__isnull=True) | Q(end_date__gt=day)).select_related("teacher__user")
    )
    return sorted({r.teacher.user.get_full_name() or r.teacher.user.username for r in rows})


def teacher_names(ids) -> dict[int, str]:
    return {t.pk: str(t) for t in Teacher.objects.filter(pk__in=list(ids)).select_related("user")}


def current_subject_teacher_ids(group_id: int, subject_id: int | None) -> set[int]:
    """Тренеры, которые сейчас ведут предмет в группе (активная программа)."""
    qs = GroupTeacher.objects.filter(group_id=group_id, is_active=True)
    qs = qs.filter(subject_id=subject_id) if subject_id else qs.filter(subject__isnull=True)
    return set(qs.values_list("teacher_id", flat=True))


def _rule_applies(rule: SalaryRule, group_id: int, course_id: int, day) -> bool:
    if not rule.is_active or not rule.overlaps(day, day):
        return False
    if rule.group_id and rule.group_id != group_id:
        return False
    return not (rule.program_id and rule.program_id != course_id)


def percent_rules_on(group_id: int, course_id: int, day) -> dict[int, SalaryRule]:
    """{employee_id: правило} — действующие в день `day` правила «Процент»,
    подходящие группе и курсу (по одному на сотрудника: при пересечении —
    первое, расчёт покажет ошибку). Кому из них положено начисление,
    решают фактические уроки (см. shares)."""
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
        if employee_id not in result and _rule_applies(rule, group_id, course_id, day):
            result[employee_id] = rule
    return result


def _teacher_id(rule: SalaryRule) -> int | None:
    teacher = getattr(rule.employee_profile.employee, "teacher_profile", None)
    return teacher.pk if teacher is not None else None


def shares(cycle: CourseCycle, teacher_lessons: dict | None = None, day=None) -> list[dict]:
    """Кому положено начисление за цикл и какая доля.

    `teacher_lessons` — {id тренера: уроков}; по умолчанию — фактические уроки
    цикла (для оценки передаются ожидаемые). Возвращает
    [{employee_id, rule, lessons_taught, numerator}] — доля = numerator /
    уроков в цикле."""
    day = day or cycle.completed_on
    lessons = {int(k): v for k, v in (cycle.teacher_lessons if teacher_lessons is None else teacher_lessons).items()}
    result = []
    for employee_id, rule in percent_rules_on(cycle.group_id, cycle.course_id, day).items():
        teacher_id = _teacher_id(rule)
        if not cycle.per_subject:
            # Исторический общий цикл: как раньше — отвечавшему за группу.
            if teacher_id is not None and responsible(teacher_id, cycle.group_id, day):
                result.append({"employee_id": employee_id, "rule": rule, "lessons_taught": None,
                               "numerator": cycle.required_lessons})
            elif rule.group_id and cycle.group_id not in trainer_group_ids_ever(teacher_id):
                result.append({"employee_id": employee_id, "rule": rule, "lessons_taught": None,
                               "numerator": cycle.required_lessons})
            continue
        taught = lessons.get(teacher_id, 0) if teacher_id is not None else 0
        if taught:
            result.append({"employee_id": employee_id, "rule": rule, "lessons_taught": taught, "numerator": taught})
        elif rule.group_id and cycle.group_id not in trainer_group_ids_ever(teacher_id):
            result.append({"employee_id": employee_id, "rule": rule, "lessons_taught": None,
                           "numerator": cycle.required_lessons})
    return result


def share_amount(price, students, percentage, numerator, required) -> Decimal:
    """студенты × тариф × процент / 100 × уроки тренера / уроков в цикле —
    одним округлением, без накопления ошибки от округлённой доли."""
    return money(Decimal(price) * students * Decimal(percentage) * numerator / (Decimal(100) * required))


def accrual_values(cycle: CourseCycle, item: dict) -> dict:
    rule, numerator = item["rule"], item["numerator"]
    return dict(
        salary_rule=rule, lessons=cycle.required_lessons, lessons_total=cycle.lessons_total,
        lessons_taught=item["lessons_taught"],
        share=(Decimal(numerator) / cycle.required_lessons).quantize(SHARE_Q),
        completed_on=cycle.completed_on, student_count=cycle.student_count, course_price=cycle.course_price,
        percentage=rule.percentage,
        amount=share_amount(cycle.course_price, cycle.student_count, rule.percentage, numerator,
                            cycle.required_lessons),
    )


def review_reasons(cycle: CourseCycle) -> list[str]:
    """Почему начисления за цикл нельзя создать автоматически.

    * Курс с правилом `REVIEW`, и уроки цикла проводили несколько тренеров:
      доли рассчитаны, но решение — за бухгалтером. При правиле по умолчанию
      (`BY_LESSONS`) смена тренера на проверку не отправляет.
    * У предмета группы уже есть завершённый цикл в этом же календарном
      месяце: стоимость курса — месячная, и начислять процент от полной
      месячной базы за каждый цикл без решения бухгалтера нельзя.
    """
    reasons = []
    settings = CoursePayrollSettings.objects.filter(course_id=cycle.course_id).first()
    teachers = {int(k) for k, v in cycle.teacher_lessons.items() if v}
    if settings is not None and settings.trainer_split_rule == Split.REVIEW and len(teachers) > 1:
        names = teacher_names(teachers)
        listed = ", ".join(f"{names.get(t, t)} — {cycle.teacher_lessons[str(t)]} ур."
                           for t in sorted(teachers, key=lambda t: names.get(t, "")))
        reasons.append(f"Уроки цикла проводили несколько тренеров ({listed}); по правилу курса доли подтверждает "
                       "бухгалтер.")
    if getattr(django_settings, "ACCOUNTING_REVIEW_REPEATED_MONTHLY_CYCLES", True) and cycle.completed_on:
        earlier = CourseCycle.objects.filter(
            group_id=cycle.group_id, course_id=cycle.course_id, subject_id=cycle.subject_id,
            per_subject=cycle.per_subject, status=Status.COMPLETED, number__lt=cycle.number,
            completed_on__year=cycle.completed_on.year, completed_on__month=cycle.completed_on.month,
        ).exclude(pk=cycle.pk).order_by("number").first()
        if earlier is not None:
            what = f"по предмету «{cycle.subject}»" if cycle.subject_id else "у группы"
            reasons.append(
                f"В {cycle.completed_on:%m.%Y} {what} уже завершён цикл {earlier.number} "
                f"({earlier.completed_on:%d.%m.%Y}): месячная стоимость курса не начисляется дважды за месяц "
                "автоматически — подтвердите или отмените начисление."
            )
    return reasons


def ensure_accruals(cycle: CourseCycle, actor=None) -> list[CycleAccrual]:
    """Создать недостающие начисления за завершённый цикл (идемпотентно) и
    обновить ещё не утверждённые, если с тех пор поправили правило.
    Спорный цикл (см. review_reasons) получает начисления в статусе
    «Требует проверки» — в расчёт они не входят до решения бухгалтера."""
    if cycle.status != Status.COMPLETED:
        return []
    created = []
    reasons = review_reasons(cycle)
    for item in shares(cycle):
        values = accrual_values(cycle, item)
        defaults = {**values, "status": AccrualStatus.REVIEW_REQUIRED if reasons else AccrualStatus.ACCRUED,
                    "review_reasons": reasons}
        try:
            with transaction.atomic():
                accrual, was_created = CycleAccrual.objects.get_or_create(
                    cycle=cycle, employee_id=item["employee_id"], defaults=defaults,
                )
        except IntegrityError:  # параллельный запуск уже создал
            continue
        if was_created:
            created.append(accrual)
            audit.log(actor, accrual, "auto_accrue", new={
                "group": cycle.group_id, "subject": cycle.subject_id, "cycle": cycle.number,
                "lessons_total": cycle.lessons_total, "completed_on": cycle.completed_on,
                "students": cycle.student_count, "course_price": cycle.course_price,
                "percentage": item["rule"].percentage, "lessons_taught": item["lessons_taught"],
                "share": values["share"], "amount": accrual.amount, "status": accrual.status,
                "planned_payment_date": accrual.planned_payment_date,
            })
            if reasons:
                audit.log(actor, accrual, "review_required", new={"status": accrual.status, "reasons": reasons},
                          reason=" ".join(reasons))
        elif accrual.status in (AccrualStatus.ACCRUED, AccrualStatus.REVIEW_REQUIRED) and (
            accrual.amount != values["amount"] or accrual.salary_rule_id != item["rule"].pk
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
        f"Уроки исправлены: проведено {lessons_now}"
        f"{f' по предмету «{cycle.subject}»' if cycle.subject_id else ''}, порог цикла {cycle.number} "
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
    """Уроки группы, которые учитываются в циклах курса: с даты начала учёта
    и только учитываемых предметов, если они заданы (например, только IT)."""
    lessons = Lesson.objects.filter(group=group)
    if settings.count_lessons_from:
        lessons = lessons.filter(date__gte=settings.count_lessons_from)
    subject_ids = list(settings.counted_subjects.values_list("pk", flat=True)) if settings.pk else []
    if subject_ids:
        lessons = lessons.filter(subject_id__in=subject_ids)
    return lessons


def _completed_lessons(group: Group, settings: CoursePayrollSettings) -> list[dict]:
    """Проведённые учитываемые уроки группы (все предметы), по порядку."""
    lessons = counted_lessons(group, settings).filter(status=Lesson.Status.COMPLETED)
    rows = lessons.order_by("date", "start_time", "id").values(
        "id", "date", "subject_id", "teacher_id", "group_teacher__teacher_id",
    )
    return [
        {"id": r["id"], "date": r["date"], "subject_id": r["subject_id"],
         "teacher_id": r["teacher_id"] or r["group_teacher__teacher_id"]}
        for r in rows
    ]


def _teacher_counts(rows: list[dict]) -> dict[str, int]:
    return {str(k): v for k, v in sorted(Counter(r["teacher_id"] for r in rows if r["teacher_id"]).items())}


def _link_lessons(cycle: CourseCycle, chunk: list[dict]) -> None:
    """Зафиксировать уроки завершённого цикла (уникальность — индексом БД)."""
    CycleLesson.objects.bulk_create([
        CycleLesson(cycle=cycle, lesson_id=row["id"], lesson_ref=row["id"], lesson_date=row["date"],
                    position=i, teacher_id=row["teacher_id"])
        for i, row in enumerate(chunk, start=1)
    ])


def _legacy(group: Group, settings: CoursePayrollSettings, rows: list[dict], actor) -> set[int]:
    """Исторические общие циклы группы: снять те, чей порог больше не
    достигнут, закрыть открытый общий цикл и вернуть id уже учтённых ими
    уроков — в предметные циклы они повторно не попадают."""
    legacy = CourseCycle.objects.select_for_update().filter(group=group, course=settings.course, per_subject=False)
    for open_cycle in legacy.filter(status=Status.IN_PROGRESS):
        open_cycle.status = Status.INVALIDATED
        open_cycle.invalidated_reason = "Учёт переведён на циклы по предметам."
        open_cycle.save()
        audit.log(actor, open_cycle, "close_legacy", new={"status": open_cycle.status},
                  reason=open_cycle.invalidated_reason)
    completed = list(legacy.filter(status=Status.COMPLETED).order_by("number"))
    while completed and completed[-1].lessons_total > len(rows):
        _invalidate(completed.pop(), len(rows), actor)
    if not completed:
        return set()
    last = completed[-1]
    consumed = set(CycleLesson.objects.filter(cycle__in=completed, is_live=True).values_list("lesson_ref", flat=True))
    position = next((i for i, r in enumerate(rows) if r["id"] == last.last_lesson_id), None)
    if position is not None:
        consumed |= {r["id"] for r in rows[:position + 1]}
    else:
        consumed |= {r["id"] for r in rows if r["date"] <= last.completed_on}
    return consumed


def subjects_for(group: Group, settings: CoursePayrollSettings, rows: list[dict]) -> list:
    """Предметы, по которым ведутся циклы группы: учитываемые предметы курса,
    если заданы; иначе предметы курса, программ группы и проведённых уроков.
    None — уроки без предмета (только если такие есть)."""
    counted = set(settings.counted_subjects.values_list("pk", flat=True))
    if counted:
        subjects = set(counted)
    else:
        subjects = set(settings.course.subjects.values_list("pk", flat=True))
        subjects |= set(GroupTeacher.objects.filter(group=group, is_active=True, subject__isnull=False)
                        .values_list("subject_id", flat=True))
        subjects |= {r["subject_id"] for r in rows if r["subject_id"]}
    ordered: list = sorted(subjects)
    if not counted and any(r["subject_id"] is None for r in rows):
        ordered.append(None)
    return ordered


def _sync_subject(group, settings, subject_id, lessons: list[dict], actor) -> list[CourseCycle]:
    total = len(lessons)
    created: list[CourseCycle] = []
    live = CourseCycle.objects.select_for_update().filter(
        group=group, course=settings.course, subject_id=subject_id, per_subject=True,
    ).exclude(status=Status.INVALIDATED)
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
            student_ids=students, student_count_rule=settings.student_count_rule, course_price=price,
            teacher_lessons=_teacher_counts(chunk),
        )
        if open_cycle is not None:
            open_cycle.number = number
            for name, value in fields.items():
                setattr(open_cycle, name, value)
            open_cycle.save()
            cycle, open_cycle = open_cycle, None
        else:
            cycle = CourseCycle.objects.create(group=group, course=settings.course, subject_id=subject_id,
                                               number=number, **fields)
        _link_lessons(cycle, chunk)
        audit.log(actor, cycle, "complete", new={
            "group": group.pk, "subject": subject_id, "number": number, "lessons_total": consumed,
            "completed_on": end, "students": len(students), "course_price": price,
            "teachers": fields["teacher_lessons"], "lessons": [row["id"] for row in chunk],
        })
        created.append(cycle)
        number += 1
    progress = dict(
        number=number, required_lessons=required, lessons_done=len(remaining),
        lessons_total=consumed + len(remaining), start_date=remaining[0]["date"] if remaining else None,
        teacher_lessons=_teacher_counts(remaining),
    )
    if open_cycle is None:
        try:
            with transaction.atomic():
                CourseCycle.objects.create(group=group, course=settings.course, subject_id=subject_id,
                                           status=Status.IN_PROGRESS, **progress)
        except IntegrityError:  # параллельная синхронизация уже создала
            pass
    elif any(getattr(open_cycle, k) != v for k, v in progress.items()):
        for name, value in progress.items():
            setattr(open_cycle, name, value)
        open_cycle.save()
    return created


def sync_group(group: Group, settings: CoursePayrollSettings, *, actor=None) -> list[CourseCycle]:
    """Привести циклы всех предметов группы в соответствие с проведёнными
    уроками; вернуть новые завершённые циклы (начисления по ним уже созданы)."""
    rows = _completed_lessons(group, settings)
    created: list[CourseCycle] = []
    with transaction.atomic():
        consumed = _legacy(group, settings, rows, actor)
        fresh = [r for r in rows if r["id"] not in consumed]
        for subject_id in subjects_for(group, settings, rows):
            lessons = [r for r in fresh if r["subject_id"] == subject_id]
            created += _sync_subject(group, settings, subject_id, lessons, actor)
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
        group = Group.objects.select_related("course").filter(pk=group_id).first()
        if group is None:  # группу удалили вместе с уроками — пересчитывать нечего
            return
        settings = CoursePayrollSettings.objects.filter(course_id=group.course_id, is_active=True).first()
        if settings is not None and group.status != Group.Status.CANCELLED:
            sync_group(group, settings, actor=actor)
    except Exception:  # noqa: BLE001
        logger.exception("Не удалось обновить циклы курса группы %s", group_id)


def open_cycles_for(employee) -> list[CourseCycle]:
    """Незавершённые циклы предметов, которые сотрудник сейчас ведёт, в
    которых он уже провёл уроки, или групп, к которым привязано его правило."""
    teacher = getattr(employee, "teacher_profile", None)
    rule_groups = set(
        SalaryRule.objects.filter(employee_profile__employee=employee, rule_type=SalaryRule.RuleType.PERCENT,
                                  is_active=True, group__isnull=False).values_list("group_id", flat=True)
    )
    cond = Q(group_id__in=rule_groups)
    if teacher is not None:
        programs = GroupTeacher.objects.filter(teacher=teacher, is_active=True).values_list("group_id", "subject_id")
        for group_id, subject_id in programs:
            cond |= Q(group_id=group_id, subject_id=subject_id)
        cond |= Q(teacher_lessons__has_key=str(teacher.pk))
    return list(
        CourseCycle.objects.filter(cond, status=Status.IN_PROGRESS, per_subject=True)
        .select_related("group", "course", "subject").order_by("group__name", "subject__name")
    )


def today() -> dt.date:
    return timezone.localdate()
