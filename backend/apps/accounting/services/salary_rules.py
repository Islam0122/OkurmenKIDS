"""Зарплатные профили и версии правил начисления.

Правило не редактируется: изменение ставки — новая версия, старая
закрывается днём раньше. Так условия уже рассчитанных периодов не
переписываются, а строки утверждённых расчётов хранят снимок ставки.
"""
from __future__ import annotations

import datetime as dt

from django.core.exceptions import ValidationError
from django.db import transaction

from ..models import CoursePayrollSettings, EmployeeSalaryProfile, Payroll, SalaryRule
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
        _validated(rule).save()
        audit.log(actor, rule, "create", new={**audit.snapshot(rule, RULE_FIELDS),
                                              "previous_version": previous.pk if previous else None})
    return rule


def new_version(rule: SalaryRule, *, actor, changes: dict) -> SalaryRule:
    data = {name: getattr(rule, name) for name in RULE_FIELDS}
    data["employee_profile"] = rule.employee_profile
    data["effective_to"] = None
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
    """Настройки курса. Уже завершённые циклы хранят свой снимок — новая
    стоимость и число уроков действуют только на следующие циклы."""
    created = settings.pk is None
    old = {} if created else audit.snapshot(CoursePayrollSettings.objects.get(pk=settings.pk), COURSE_FIELDS)
    for name, value in data.items():
        setattr(settings, name, value)
    with transaction.atomic():
        _validated(settings).save()
        audit.log(actor, settings, "create" if created else "update", old=old,
                  new=audit.snapshot(settings, COURSE_FIELDS))
    return settings
