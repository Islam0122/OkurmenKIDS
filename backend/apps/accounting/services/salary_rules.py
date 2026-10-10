"""Зарплатные профили и версии правил начисления.

Правило не редактируется: изменение ставки — новая версия, старая
закрывается днём раньше. Так условия уже рассчитанных периодов не
переписываются, а строки утверждённых расчётов хранят снимок ставки.
"""
from __future__ import annotations

import datetime as dt

from django.core.exceptions import ValidationError
from django.db import transaction

from ..models import CoursePayrollSettings, EmployeeSalaryProfile, Payroll, PayrollLine, SalaryRule
from . import AccountingError, audit

PROFILE_FIELDS = ("position", "salary_type", "is_active", "effective_from", "effective_to")
RULE_FIELDS = (
    "rule_type", "amount", "percentage", "program", "group", "calculation_method", "first_half_share",
    "revenue_basis", "refund_policy", "description", "effective_from", "effective_to", "is_active",
)


def _validated(instance):
    try:
        instance.full_clean()
    except ValidationError as exc:
        messages = exc.message_dict if hasattr(exc, "error_dict") else {"detail": exc.messages}
        raise AccountingError("; ".join(f"{', '.join(v)}" for v in messages.values()))
    return instance


def save_profile(profile: EmployeeSalaryProfile, *, actor, data: dict) -> EmployeeSalaryProfile:
    created = profile.pk is None
    old = {} if created else audit.snapshot(EmployeeSalaryProfile.objects.get(pk=profile.pk), PROFILE_FIELDS)
    for name, value in data.items():
        setattr(profile, name, value)
    with transaction.atomic():
        _validated(profile).save()
        audit.log(actor, profile, "create" if created else "update", old=old,
                  new=audit.snapshot(profile, PROFILE_FIELDS))
    return profile


def create_rule(*, actor, data: dict, previous: SalaryRule | None = None) -> SalaryRule:
    rule = SalaryRule(created_by=actor, previous_version=previous, **data)
    if not rule.calculation_method:
        rule.calculation_method = SalaryRule.METHODS_BY_TYPE.get(rule.rule_type, (SalaryRule.Method.STANDARD,))[0]
    with transaction.atomic():
        if previous is not None:
            previous = SalaryRule.objects.select_for_update().get(pk=previous.pk)
            if hasattr(previous, "next_version"):
                raise AccountingError("У этого правила уже есть новая версия.")
            if rule.effective_from <= previous.effective_from:
                raise AccountingError("Новая версия должна начинаться позже предыдущей.")
            closing = rule.effective_from - dt.timedelta(days=1)
            if previous.effective_to is None or previous.effective_to > closing:
                old = {"effective_to": previous.effective_to}
                previous.effective_to = closing
                previous.save(update_fields=["effective_to"])
                audit.log(actor, previous, "close_version", old=old, new={"effective_to": closing})
        _validated(rule)
        assert_no_overlap(rule)
        rule.save()
        audit.log(actor, rule, "create", new={**audit.snapshot(rule, RULE_FIELDS),
                                              "previous_version": previous.pk if previous else None})
    return rule


def new_version(rule: SalaryRule, *, actor, changes: dict) -> SalaryRule:
    data = {name: getattr(rule, name) for name in RULE_FIELDS}
    data["employee_profile"] = rule.employee_profile
    data["effective_to"] = None
    # Новая версия получает действующий метод типа (оклад — всегда полный месячный).
    data["calculation_method"] = SalaryRule.METHODS_BY_TYPE.get(rule.rule_type, (rule.calculation_method,))[0]
    data.update(changes)
    if "effective_from" not in changes:
        raise AccountingError("Укажите дату, с которой действует новая ставка.")
    return create_rule(actor=actor, data=data, previous=rule)


def deactivate_rule(rule: SalaryRule, *, actor, effective_to: dt.date, reason: str = "") -> SalaryRule:
    """Прекратить действие правила с даты (включительно — последний день)."""
    if effective_to < rule.effective_from:
        raise AccountingError("Дата окончания раньше начала действия правила.")
    locked_until = (
        Payroll.objects.filter(lines__salary_rule=rule, status__in=Payroll.LOCKED_STATUSES)
        .order_by("-period__end_date").values_list("period__end_date", flat=True).first()
    )
    if locked_until and effective_to < locked_until:
        raise AccountingError(
            f"Правило уже использовано в утверждённых расчётах до {locked_until:%d.%m.%Y} — "
            "закрыть его раньше этой даты нельзя."
        )
    with transaction.atomic():
        old = {"effective_to": rule.effective_to}
        rule.effective_to = effective_to
        rule.save(update_fields=["effective_to"])
        audit.log(actor, rule, "deactivate", old=old, new={"effective_to": effective_to}, reason=reason)
    return rule


COURSE_FIELDS = ("price_per_student", "required_lessons", "count_lessons_from", "student_count_rule", "is_active")


def save_course_settings(settings: CoursePayrollSettings, *, actor, data: dict) -> CoursePayrollSettings:
    """Настройки курса. Уже завершённые циклы хранят свой снимок — новое
    число уроков и учитываемые предметы действуют только на следующие циклы.

    Стоимость задаётся при создании (первая версия тарифа), а меняется только
    новой версией тарифа (services.pricing.set_price) — с датой и причиной."""
    from django.utils import timezone

    from .pricing import set_price

    data = dict(data)
    subjects = data.pop("counted_subjects", None)
    price_from = data.pop("price_effective_from", None) or timezone.localdate()
    price_reason = data.pop("price_reason", "") or "Первоначальная стоимость курса"
    created = settings.pk is None
    if not created and "price_per_student" in data and data["price_per_student"] != settings.price_per_student:
        raise AccountingError(
            "Стоимость курса меняется только новой версией тарифа (раздел «Стоимость курсов»): "
            "с датой начала действия и причиной — так сохраняется история цен.",
            code="use_pricing",
        )
    old = {} if created else {
        **audit.snapshot(CoursePayrollSettings.objects.get(pk=settings.pk), COURSE_FIELDS),
        "counted_subjects": sorted(settings.counted_subjects.values_list("pk", flat=True)),
    }
    for name, value in data.items():
        setattr(settings, name, value)
    with transaction.atomic():
        _validated(settings).save()
        if subjects is not None:
            settings.counted_subjects.set(subjects)
        audit.log(actor, settings, "create" if created else "update", old=old, new={
            **audit.snapshot(settings, COURSE_FIELDS),
            "counted_subjects": sorted(settings.counted_subjects.values_list("pk", flat=True)),
        })
        if created:
            set_price(course=settings.course, price_per_student=settings.price_per_student,
                      effective_from=price_from, reason=price_reason, actor=actor)
    return settings


# ---------------------------------------------------------------------------
# Исправление ошибочно созданного правила и замена использованного
# ---------------------------------------------------------------------------
#
# * Правило ещё не попало в утверждённые начисления (нет строк в утверждённых
#   / выплаченных расчётах и нет утверждённых начислений за циклы) — его можно
#   ИСПРАВИТЬ на месте: тип оплаты, ставку, основание (курс / группу), метод,
#   даты, комментарий. Неутверждённые последствия приводятся в порядок:
#   начисления за циклы по этому правилу пересчитываются (или отменяются, если
#   больше не положены), черновые расчёты пересчитываются (или аннулируются,
#   если их период больше не подходит типу оплаты). Ничего не удаляется.
# * Правило уже использовано в утверждённых начислениях — история не
#   меняется: правило ЗАМЕНЯЕТСЯ с даты (старое закрывается днём раньше,
#   создаётся новое), дата — позже последнего утверждённого использования.
# * Правила одного сотрудника, одного типа и одного основания не могут
#   действовать одновременно — проверяется при создании, исправлении и замене.

CORRECTABLE_FIELDS = (
    "rule_type", "amount", "percentage", "program", "group", "calculation_method", "description",
    "effective_from", "effective_to",
)


def _locked_accrual_statuses():
    from ..models import CycleAccrual

    return (CycleAccrual.Status.APPROVED, CycleAccrual.Status.CORRECTED, CycleAccrual.Status.CORRECTION_REQUIRED)


def rule_usage(rule: SalaryRule) -> dict:
    """Где использовано правило: утверждённые расчёты (менять нельзя) и
    черновые (пересчитаются), начисления за циклы."""
    from ..models import CycleAccrual

    lines = PayrollLine.objects.filter(salary_rule=rule).exclude(payroll__status=Payroll.Status.VOID)
    locked_ids = set(lines.filter(payroll__status__in=Payroll.LOCKED_STATUSES).values_list("payroll_id", flat=True))
    draft_ids = set(lines.filter(payroll__status__in=Payroll.EDITABLE_STATUSES).values_list("payroll_id", flat=True))
    accruals = CycleAccrual.objects.filter(salary_rule=rule)
    locked_accruals = accruals.filter(status__in=_locked_accrual_statuses())
    open_accruals = accruals.filter(status__in=(CycleAccrual.Status.ACCRUED, CycleAccrual.Status.REVIEW_REQUIRED))
    dates = [d for d in (
        Payroll.objects.filter(pk__in=locked_ids).order_by("-period__end_date").values_list("period__end_date", flat=True).first(),
        locked_accruals.order_by("-completed_on").values_list("completed_on", flat=True).first(),
    ) if d]
    locked = bool(locked_ids) or locked_accruals.exists()
    return {
        "can_correct": not locked,
        "locked_payrolls": len(locked_ids),
        "draft_payrolls": len(draft_ids),
        "locked_accruals": locked_accruals.count(),
        "open_accruals": open_accruals.count(),
        "used_until": max(dates) if dates else None,
    }


def assert_no_overlap(rule: SalaryRule) -> None:
    """Не допускать одновременного действия правил одного типа и одного
    основания (курс/группа) у сотрудника — иначе расчёт не знает, какое
    применить."""
    end = rule.effective_to or dt.date.max
    clash = (
        SalaryRule.objects.filter(employee_profile_id=rule.employee_profile_id, rule_type=rule.rule_type,
                                  group_id=rule.group_id, program_id=rule.program_id, is_active=True,
                                  effective_from__lte=end)
        .exclude(pk=rule.pk)
        .exclude(effective_to__lt=rule.effective_from)
        .order_by("effective_from").first()
    )
    if clash is not None:
        until = f" по {clash.effective_to:%d.%m.%Y}" if clash.effective_to else " без срока"
        raise AccountingError(
            f"Пересекается с правилом #{clash.pk} ({clash.get_rule_type_display()}, с "
            f"{clash.effective_from:%d.%m.%Y}{until}) того же основания. Сначала прекратите его или выберите другие даты.",
            code="overlap",
        )


def _normalize(rule: SalaryRule) -> None:
    """Поля, которые не относятся к типу правила, очищаются: у оклада нет
    процента и основания, у процента нет суммы."""
    if rule.rule_type == SalaryRule.RuleType.FIXED:
        rule.percentage, rule.program, rule.group = None, None, None
    elif rule.rule_type == SalaryRule.RuleType.PERCENT:
        rule.amount = None
    methods = SalaryRule.METHODS_BY_TYPE.get(rule.rule_type, ())
    if rule.calculation_method not in methods and methods:
        rule.calculation_method = methods[0]


def _set_profile_type(profile: EmployeeSalaryProfile, salary_type: str, actor, reason: str) -> None:
    if profile.salary_type == salary_type:
        return
    old = {"salary_type": profile.salary_type}
    profile.salary_type = salary_type
    profile.save(update_fields=["salary_type", "updated_at"])
    audit.log(actor, profile, "change_salary_type", old=old, new={"salary_type": salary_type}, reason=reason)


def _refresh_open_accruals(employee_id: int, rules, actor, reason: str) -> dict:
    """Неутверждённые начисления за циклы по этим правилам: пересчитать по
    действующему правилу или отменить, если начисление больше не положено."""
    from ..models import CycleAccrual
    from .cycles import accrual_values, shares

    updated = cancelled = 0
    accruals = CycleAccrual.objects.filter(
        employee_id=employee_id, salary_rule__in=rules,
        status__in=(CycleAccrual.Status.ACCRUED, CycleAccrual.Status.REVIEW_REQUIRED),
    ).select_related("cycle")
    for accrual in accruals:
        item = next((i for i in shares(accrual.cycle) if i["employee_id"] == employee_id), None)
        old = {"salary_rule": accrual.salary_rule_id, "amount": accrual.amount, "status": accrual.status}
        if item is None:
            accrual.status = CycleAccrual.Status.CANCELLED
            accrual.payroll, accrual.line = None, None
            accrual.note = f"Правило исправлено — начисление больше не положено. {reason}"
            accrual.save()
            audit.log(actor, accrual, "cancel", old=old, new={"status": accrual.status}, reason=accrual.note)
            cancelled += 1
            continue
        values = accrual_values(accrual.cycle, item)
        if values["amount"] != accrual.amount or values["salary_rule"].pk != accrual.salary_rule_id:
            for name, value in values.items():
                setattr(accrual, name, value)
            accrual.save()
            audit.log(actor, accrual, "update", old=old,
                      new={"salary_rule": accrual.salary_rule_id, "amount": accrual.amount}, reason=reason)
            updated += 1
    return {"accruals_updated": updated, "accruals_cancelled": cancelled}


def _refresh_draft_payrolls(employee, payroll_ids, actor, reason: str) -> dict:
    """Черновые расчёты, где было правило: пересчитать; если период больше
    не подходит типу оплаты (оклад — месяц, процент — половины) — аннулировать
    (запись остаётся в истории со статусом «Аннулирован»)."""
    from .approval_service import void_payroll
    from .payroll_calculator import calculate_payroll

    profile = EmployeeSalaryProfile.objects.get(employee=employee)
    recalculated, voided, failed = [], [], []
    for payroll in Payroll.objects.filter(pk__in=payroll_ids, status__in=Payroll.EDITABLE_STATUSES).select_related("period"):
        fits = (profile.salary_type == SalaryRule.RuleType.FIXED) == payroll.period.is_month
        try:
            if fits:
                calculate_payroll(payroll.period, employee, actor)
                recalculated.append(payroll.pk)
            else:
                void_payroll(payroll, actor, f"Тип оплаты изменён — расчёт за этот период больше не нужен. {reason}")
                voided.append(payroll.pk)
        except AccountingError as exc:
            failed.append({"payroll_id": payroll.pk, "error": exc.message})
    return {"payrolls_recalculated": recalculated, "payrolls_voided": voided, "payrolls_failed": failed}


def correct_rule(rule: SalaryRule, *, actor, changes: dict, reason: str) -> tuple[SalaryRule, dict]:
    """Исправить ошибочное правило на месте — только пока оно не попало в
    утверждённые начисления. Возвращает (правило, что пересчитано)."""
    reason = (reason or "").strip()
    if not reason:
        raise AccountingError("Укажите, что и почему исправляется.", code="reason_required")
    unknown = set(changes) - set(CORRECTABLE_FIELDS)
    if unknown:
        raise AccountingError(f"Эти поля нельзя исправить: {', '.join(sorted(unknown))}.")
    with transaction.atomic():
        rule = SalaryRule.objects.select_for_update().select_related("employee_profile__employee").get(pk=rule.pk)
        usage = rule_usage(rule)
        if not usage["can_correct"]:
            raise AccountingError(
                f"Правило уже использовано в утверждённых начислениях (до {usage['used_until']:%d.%m.%Y}) — "
                "историю менять нельзя. Замените его с даты: старое правило закроется днём раньше, а новое "
                "начнёт действовать с выбранной даты.",
                code="rule_used",
            )
        profile = rule.employee_profile
        versioned = rule.previous_version_id or hasattr(rule, "next_version")
        structural = {"rule_type", "effective_from", "effective_to", "program", "group"} & {
            k for k, v in changes.items() if getattr(rule, f"{k}_id" if k in ("program", "group") else k) != (
                v.pk if hasattr(v, "pk") else v)
        }
        if versioned and structural:
            raise AccountingError(
                "У правила есть другие версии — тип, основание и даты меняются через «Заменить с даты» или "
                "«Прекратить», а не исправлением.", code="versioned",
            )
        new_type = changes.get("rule_type", rule.rule_type)
        if new_type not in SalaryRule.ACTIVE_TYPES:
            raise AccountingError("Допустимы только «Оклад» и «Процент от стоимости курса».")
        if new_type != rule.rule_type and profile.rules.exclude(pk=rule.pk).exists():
            raise AccountingError(
                "Сменить тип можно, только если это единственное правило сотрудника: у него есть другие правила "
                f"типа «{profile.get_salary_type_display()}». Прекратите их или используйте «Заменить с даты».",
                code="type_conflict",
            )
        old = audit.snapshot(rule, RULE_FIELDS)
        for name, value in changes.items():
            setattr(rule, name, value)
        _normalize(rule)
        _set_profile_type(profile, rule.rule_type, actor, reason)
        rule.employee_profile = profile
        _validated(rule)
        assert_no_overlap(rule)
        rule.save()
        audit.log(actor, rule, "correct", old=old, new=audit.snapshot(rule, RULE_FIELDS), reason=reason)
        effects = _refresh_open_accruals(profile.employee_id, [rule], actor, reason)
    # Черновики пересчитываются после фиксации правила (каждый в своей транзакции).
    draft_ids = set(PayrollLine.objects.filter(salary_rule=rule, payroll__status__in=Payroll.EDITABLE_STATUSES)
                    .values_list("payroll_id", flat=True))
    effects.update(_refresh_draft_payrolls(profile.employee, draft_ids, actor, reason))
    return rule, effects


def replace_rule(rule: SalaryRule, *, actor, effective_from: dt.date, data: dict, reason: str) -> tuple[SalaryRule, dict]:
    """Заменить правило с даты: старое закрывается днём раньше (утверждённые
    начисления по нему не меняются), создаётся новое — можно с другим типом
    оплаты, ставкой и основанием."""
    from ..models import CycleAccrual

    reason = (reason or "").strip()
    if not reason:
        raise AccountingError("Укажите причину замены правила.", code="reason_required")
    with transaction.atomic():
        rule = SalaryRule.objects.select_for_update().select_related("employee_profile__employee").get(pk=rule.pk)
        if hasattr(rule, "next_version"):
            raise AccountingError("У правила уже есть следующая версия — заменяйте последнюю.", code="versioned")
        if effective_from <= rule.effective_from:
            raise AccountingError("Новое правило должно начинаться позже старого.", code="bad_date")
        usage = rule_usage(rule)
        if usage["used_until"] and effective_from <= usage["used_until"]:
            raise AccountingError(
                f"Правило использовано в утверждённых начислениях до {usage['used_until']:%d.%m.%Y} — новое может "
                "начинаться не раньше следующего дня.", code="bad_date",
            )
        profile = rule.employee_profile
        new_type = data.get("rule_type", rule.rule_type)
        if new_type not in SalaryRule.ACTIVE_TYPES:
            raise AccountingError("Допустимы только «Оклад» и «Процент от стоимости курса».")
        if new_type != profile.salary_type:
            if effective_from.day != 1:
                raise AccountingError(
                    "Тип оплаты меняется с первого числа месяца: оклад начисляется за календарный месяц.",
                    code="bad_date",
                )
            others = profile.rules.exclude(pk=rule.pk).filter(is_active=True).exclude(effective_to__lt=effective_from)
            if others.exists():
                raise AccountingError(
                    f"У сотрудника есть другие правила, действующие после {effective_from:%d.%m.%Y} "
                    f"(#{', #'.join(str(r.pk) for r in others)}) — сначала прекратите их.", code="type_conflict",
                )
            if profile.salary_type == SalaryRule.RuleType.PERCENT and CycleAccrual.objects.filter(
                employee=profile.employee, completed_on__lt=effective_from,
                status__in=(CycleAccrual.Status.ACCRUED, CycleAccrual.Status.REVIEW_REQUIRED),
            ).exists():
                raise AccountingError(
                    "Есть неутверждённые начисления процента за циклы до даты смены — сначала рассчитайте и утвердите "
                    "их (иначе после смены типа их будет не рассчитать).", code="pending_accruals",
                )
            if profile.salary_type == SalaryRule.RuleType.FIXED and Payroll.objects.filter(
                employee=profile.employee, period__period_type="MONTH", period__end_date__lt=effective_from,
                status__in=Payroll.EDITABLE_STATUSES,
            ).exists():
                raise AccountingError(
                    "Есть неутверждённые расчёты оклада за месяцы до даты смены — сначала утвердите или аннулируйте их.",
                    code="pending_payrolls",
                )
        deactivate_rule(rule, actor=actor, effective_to=effective_from - dt.timedelta(days=1), reason=reason)
        _set_profile_type(profile, new_type, actor, reason)
        new_data = {
            "employee_profile": profile, "rule_type": new_type, "effective_from": effective_from,
            "effective_to": data.get("effective_to"), "amount": data.get("amount"),
            "percentage": data.get("percentage"), "program": data.get("program"), "group": data.get("group"),
            "description": data.get("description", "") or f"Замена правила #{rule.pk}: {reason}",
            "calculation_method": SalaryRule.METHODS_BY_TYPE[new_type][0],
        }
        new_rule = create_rule(actor=actor, data=new_data, previous=rule)
        effects = _refresh_open_accruals(profile.employee_id, [rule, new_rule], actor, reason)
    draft_ids = set(PayrollLine.objects.filter(salary_rule=rule, payroll__status__in=Payroll.EDITABLE_STATUSES,
                                               payroll__period__end_date__gte=effective_from)
                    .values_list("payroll_id", flat=True))
    effects.update(_refresh_draft_payrolls(profile.employee, draft_ids, actor, reason))
    return new_rule, effects
