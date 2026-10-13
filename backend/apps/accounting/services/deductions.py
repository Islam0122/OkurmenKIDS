"""Налоги и удержания из зарплаты (раздел «Зарплатные правила» → «Налоги и
удержания»).

Удержание — не отдельный расчёт зарплаты: оно применяется внутри
существующего `calculate_payroll` и учитывается в итогах расчёта
(`Payroll.total_deductions`, `amount_due` = начислено + корректировки −
удержания − выплачено). Поэтому «План выплат», выплаты и отчёты, которые
работают от `amount_due`, уже видят сумму после удержаний и не вычитают её
повторно.

Правила применения
* Ежемесячное правило (и правило «в указанный период») удерживается один раз
  за календарный месяц, у сотрудника может быть несколько расчётов в месяце
  (половины месяца, оклад и процент, несколько циклов и предметов). Запись
  `AppliedDeduction` уникальна по (правило-серия, сотрудник, год, месяц) —
  ограничение БД, а не только проверка кода.
* Однократное правило — один раз в месяце даты начала.
* Сумма месяца распределяется по расчётам месяца (`DeductionAllocation`):
  каждый расчёт отдаёт не больше, чем в нём доступно (начислено +
  корректировки − уже взятые удержания − выплачено), поэтому к выплате не
  становится отрицательным. Недостающая часть показывается как остаток
  удержания; на следующие месяцы она автоматически не переносится.
* Пересчёт черновика заменяет только распределение этого расчёта; запись
  месяца не создаётся заново. Утверждённые расчёты не пересчитываются — их
  удержания заморожены.
"""
from __future__ import annotations

import calendar
import copy
import datetime as dt
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.db.models import Q, Sum

from ..models import (
    AppliedDeduction,
    DeductionAllocation,
    DeductionRule,
    Department,
    EmployeeSalaryProfile,
    Payroll,
    PayrollAdjustment,
    PayrollPayment,
    PayrollPeriod,
)
from . import AccountingError, audit
from .money import ZERO

R = DeductionRule
RULE_FIELDS = ("name", "kind", "calc_type", "amount", "frequency", "scope", "employee", "department",
               "effective_from", "effective_to", "is_active", "description")
# Меняют, сколько и у кого удерживается — для использованной версии только новой версией с даты.
MATERIAL = {"kind", "amount", "frequency", "scope", "employee", "department", "effective_from"}


def month_bounds(year: int, month: int) -> tuple[dt.date, dt.date]:
    return dt.date(year, month, 1), dt.date(year, month, calendar.monthrange(year, month)[1])


def _department(employee) -> str:
    profile = EmployeeSalaryProfile.objects.filter(employee=employee).first()
    return profile.effective_department if profile else Department.OTHER


def applies_in_month(rule: DeductionRule, year: int, month: int) -> bool:
    start, end = month_bounds(year, month)
    if not rule.is_active:
        return False
    if rule.frequency == R.Frequency.ONCE:
        return (rule.effective_from.year, rule.effective_from.month) == (year, month)
    return rule.effective_from <= end and (rule.effective_to is None or rule.effective_to >= start)


def covers(rule: DeductionRule, employee, department: str | None = None) -> bool:
    if rule.scope == R.Scope.ALL:
        return True
    if rule.scope == R.Scope.EMPLOYEE:
        return rule.employee_id == employee.pk
    return rule.department == (department if department is not None else _department(employee))


def applicable_rules(employee, year: int, month: int) -> list[DeductionRule]:
    """Действующие в месяце правила сотрудника — по одной версии на правило."""
    start, end = month_bounds(year, month)
    department = _department(employee)
    qs = R.objects.filter(is_active=True, effective_from__lte=end).filter(
        Q(scope=R.Scope.ALL) | Q(scope=R.Scope.EMPLOYEE, employee=employee)
        | Q(scope=R.Scope.DEPARTMENT, department=department),
    ).order_by("series", "-effective_from", "-id")
    chosen: dict = {}
    for rule in qs:
        if rule.series not in chosen and applies_in_month(rule, year, month):
            chosen[rule.series] = rule
    return sorted(chosen.values(), key=lambda r: (list(R.Kind.values).index(r.kind), r.name, r.pk))


def _gross(payroll: Payroll) -> Decimal:
    lines = payroll.lines.aggregate(s=Sum("amount"))["s"] or ZERO
    adjustments = payroll.adjustments.filter(status=PayrollAdjustment.Status.APPLIED).aggregate(
        s=Sum("amount"))["s"] or ZERO
    return lines + adjustments


def _taken_elsewhere(header: AppliedDeduction, payroll: Payroll) -> Decimal:
    return header.allocations.exclude(payroll=payroll).exclude(payroll__status=Payroll.Status.VOID).aggregate(
        s=Sum("amount"))["s"] or ZERO


def _frozen(header: AppliedDeduction) -> bool:
    """Удержание уже вошло в утверждённый расчёт — запись месяца не меняется."""
    return header.allocations.filter(payroll__status__in=Payroll.LOCKED_STATUSES).exists()


def _lock_header(rule: DeductionRule, employee, year: int, month: int) -> tuple[AppliedDeduction, bool]:
    defaults = {"rule": rule, "name": rule.name, "kind": rule.kind, "amount": rule.amount}
    try:
        with transaction.atomic():
            header, created = AppliedDeduction.objects.get_or_create(
                series=rule.series, employee=employee, year=year, month=month, defaults=defaults)
    except IntegrityError:  # параллельный расчёт успел создать ту же запись
        header, created = AppliedDeduction.objects.get(
            series=rule.series, employee=employee, year=year, month=month), False
    return AppliedDeduction.objects.select_for_update().get(pk=header.pk), created


def apply_to_payroll(payroll: Payroll, actor) -> list[DeductionAllocation]:
    """Распределить удержания месяца на (черновой) расчёт. Вызывается из
    `calculate_payroll` внутри его транзакции, после записи строк."""
    if not payroll.is_editable:
        raise AccountingError("Удержания утверждённого расчёта не меняются.", code="locked")
    period = payroll.period
    year, month = period.year, period.month
    employee = payroll.employee
    DeductionAllocation.objects.filter(payroll=payroll).delete()  # только этого чернового расчёта
    rules = applicable_rules(employee, year, month)
    series = {r.series for r in rules}
    # Правило больше не применяется (отключено, сменился круг сотрудников) и
    # из месяца ещё ничего не удержано — запись месяца больше не нужна.
    for stale in AppliedDeduction.objects.filter(employee=employee, year=year, month=month).exclude(series__in=series):
        if not stale.allocations.exists():
            stale.delete()
    paid = payroll.payments.filter(status=PayrollPayment.Status.CONFIRMED).aggregate(s=Sum("amount"))["s"] or ZERO
    available = max(ZERO, _gross(payroll) - paid)
    created_allocations = []
    for rule in rules:
        header, created = _lock_header(rule, employee, year, month)
        if not created and not _frozen(header) and (
            header.rule_id != rule.pk or header.amount != rule.amount or header.name != rule.name
        ):
            old = {"rule": header.rule_id, "amount": header.amount, "name": header.name}
            header.rule, header.amount, header.name, header.kind = rule, rule.amount, rule.name, rule.kind
            header.save(update_fields=["rule", "amount", "name", "kind", "updated_at"])
            audit.log(actor, header, "deduction_refresh", old=old,
                      new={"rule": rule.pk, "amount": rule.amount, "name": rule.name}, payroll=payroll)
        elif created:
            audit.log(actor, header, "deduction_apply", new={
                "rule": rule.pk, "name": rule.name, "amount": rule.amount, "year": year, "month": month,
            }, payroll=payroll)
        take = min(max(ZERO, header.amount - _taken_elsewhere(header, payroll)), available)
        if take > 0:
            created_allocations.append(DeductionAllocation.objects.create(applied=header, payroll=payroll, amount=take))
            available -= take
    return created_allocations


def payroll_deductions(payroll: Payroll) -> list[dict]:
    """Удержания расчёта для детализации: сколько полагается за месяц, сколько
    взято из этого расчёта, из других расчётов месяца и сколько не удержано."""
    rows = []
    allocations = {a.applied_id: a for a in payroll.deduction_allocations.select_related("applied")}
    headers = AppliedDeduction.objects.filter(
        Q(pk__in=allocations) | Q(employee_id=payroll.employee_id, year=payroll.period.year,
                                   month=payroll.period.month),
    ).select_related("rule").order_by("kind", "name", "id")
    for header in headers:
        here = allocations[header.pk].amount if header.pk in allocations else ZERO
        elsewhere = _taken_elsewhere(header, payroll)
        rows.append({
            "id": header.pk, "rule": header.rule_id, "name": header.name, "kind": header.kind,
            "kind_display": R.Kind(header.kind).label, "frequency_display": header.rule.get_frequency_display(),
            "year": header.year, "month": header.month, "month_amount": header.amount,
            "amount": here, "other_payrolls": elsewhere,
            "remaining": max(ZERO, header.amount - here - elsewhere),
        })
    return rows


# ---------------------------------------------------------------------------
# Правила: создание, исправление, новая версия
# ---------------------------------------------------------------------------

def usage(rule: DeductionRule) -> dict:
    locked = DeductionAllocation.objects.filter(applied__rule=rule, payroll__status__in=Payroll.LOCKED_STATUSES)
    last = locked.order_by("-applied__year", "-applied__month").values_list("applied__year", "applied__month").first()
    return {
        "locked_payrolls": locked.values("payroll").distinct().count(),
        "draft_payrolls": DeductionAllocation.objects.filter(
            applied__rule=rule, payroll__status__in=Payroll.EDITABLE_STATUSES).values("payroll").distinct().count(),
        "used_until": month_bounds(*last)[1] if last else None,
        "can_correct": not locked.exists(),
    }


def _validate(data: dict) -> None:
    errors = {}
    amount = data.get("amount")
    if amount is None or Decimal(amount) <= 0:
        errors["amount"] = "Сумма удержания должна быть больше нуля."
    else:
        data["amount"] = Decimal(amount).quantize(Decimal("0.01"))
    if data.get("calc_type", R.CalcType.FIXED) != R.CalcType.FIXED:
        errors["calc_type"] = "Поддерживается фиксированная сумма."
    scope = data.get("scope")
    if scope == R.Scope.EMPLOYEE and not data.get("employee"):
        errors["employee"] = "Выберите сотрудника."
    if scope == R.Scope.DEPARTMENT and not data.get("department"):
        errors["department"] = "Выберите направление."
    if scope != R.Scope.EMPLOYEE:
        data["employee"] = None
    if scope != R.Scope.DEPARTMENT:
        data["department"] = ""
    start, end = data.get("effective_from"), data.get("effective_to")
    if not start:
        errors["effective_from"] = "Укажите дату начала."
    elif end and end < start:
        errors["effective_to"] = "Дата окончания раньше даты начала."
    if data.get("frequency") == R.Frequency.PERIOD and not end:
        errors["effective_to"] = "Для периода укажите дату окончания."
    if not (data.get("name") or "").strip():
        errors["name"] = "Укажите название."
    if errors:
        raise AccountingError("; ".join(errors.values()), code="invalid")


def _affected_payrolls(rules: list[DeductionRule]):
    """Черновые расчёты, которых касаются правила (для пересчёта)."""
    starts = [r.effective_from for r in rules]
    ends = [r.effective_to for r in rules]
    lo = month_bounds(min(starts).year, min(starts).month)[0]
    qs = Payroll.objects.filter(status__in=Payroll.EDITABLE_STATUSES, period__end_date__gte=lo).exclude(
        period__status=PayrollPeriod.Status.CLOSED).select_related("period", "employee")
    if all(e is not None for e in ends):
        qs = qs.filter(period__start_date__lte=max(ends))
    return [p for p in qs if any(covers(r, p.employee) for r in rules)]


def recalculate_drafts(rules: list[DeductionRule], actor) -> dict:
    """Пересчитать черновые расчёты, чтобы удержания в них совпали с правилами.
    Утверждённые расчёты не трогаются."""
    from .payroll_calculator import calculate_payroll

    done, failed = [], []
    for payroll in _affected_payrolls(rules):
        try:
            calculate_payroll(payroll.period, payroll.employee, actor, sync=False)
            done.append(payroll.pk)
        except AccountingError as exc:
            failed.append({"payroll_id": payroll.pk, "error": exc.message})
    return {"payrolls_recalculated": done, "payrolls_failed": failed}


def create_rule(*, actor, **data) -> tuple[DeductionRule, dict]:
    _validate(data)
    with transaction.atomic():
        rule = R.objects.create(created_by=actor, **{k: v for k, v in data.items() if k in RULE_FIELDS})
        audit.log(actor, rule, "deduction_rule_create", new=audit.snapshot(rule, RULE_FIELDS))
    return rule, recalculate_drafts([rule], actor)


def change_rule(rule: DeductionRule, *, actor, changes: dict, reason: str) -> tuple[DeductionRule, dict]:
    """Изменить правило. Не использованное в утверждённых расчётах — исправляется
    на месте. Использованное: название, комментарий, включение и дата окончания
    (не раньше последнего утверждённого месяца) меняются на месте; сумма, вид,
    периодичность, круг сотрудников и дата начала — только новой версией с
    даты (с 1-го числа месяца после последнего утверждённого удержания)."""
    reason = (reason or "").strip()
    if not reason:
        raise AccountingError("Укажите причину изменения.", code="reason_required")
    with transaction.atomic():
        rule = R.objects.select_for_update().get(pk=rule.pk)
        if hasattr(rule, "next_version"):
            raise AccountingError("Это не последняя версия правила — меняйте действующую.", code="not_latest")
        info = usage(rule)
        current = {k: getattr(rule, k if k != "employee" else "employee_id") for k in RULE_FIELDS}
        changed = {k: v for k, v in changes.items()
                   if k in RULE_FIELDS and (v.pk if k == "employee" and v is not None else v) != current[k]}
        if not changed:
            return rule, {"payrolls_recalculated": [], "payrolls_failed": []}
        merged = {**{k: getattr(rule, k) for k in RULE_FIELDS}, **changed}
        _validate(merged)
        old = audit.snapshot(rule, RULE_FIELDS)
        used_until = info["used_until"]
        if info["can_correct"] or not (set(changed) & MATERIAL):
            if used_until and merged["effective_to"] and merged["effective_to"] < used_until:
                raise AccountingError(f"Удержание уже вошло в утверждённые расчёты до {used_until:%d.%m.%Y} — "
                                      "закончить правило раньше нельзя.", code="used")
            before = copy.copy(rule)
            for key, value in merged.items():
                setattr(rule, key, value)
            rule.save()
            audit.log(actor, rule, "deduction_rule_correct", old={k: old[k] for k in changed},
                      new={k: audit.snapshot(rule, RULE_FIELDS)[k] for k in changed}, reason=reason)
            return rule, recalculate_drafts([before, rule], actor)
        start = merged["effective_from"] if "effective_from" in changed else None
        if start is None:
            raise AccountingError("Правило уже применено в утверждённых расчётах — укажите дату, с которой "
                                  "действует новая версия.", code="date_required")
        if start.day != 1:
            raise AccountingError("Новая версия ежемесячного удержания начинается с 1-го числа месяца.",
                                  code="month_start")
        if used_until and start <= used_until:
            raise AccountingError(f"Удержание по этой версии уже утверждено до {used_until:%d.%m.%Y} — новая "
                                  f"версия может начаться не раньше {used_until + dt.timedelta(days=1):%d.%m.%Y}.",
                                  code="used")
        if start <= rule.effective_from:
            raise AccountingError("Новая версия должна начинаться позже текущей.", code="bad_date")
        rule.effective_to = start - dt.timedelta(days=1)
        rule.save(update_fields=["effective_to", "updated_at"])
        new = R.objects.create(series=rule.series, previous_version=rule, created_by=actor,
                               **{k: v for k, v in merged.items() if k in RULE_FIELDS})
        audit.log(actor, new, "deduction_rule_new_version", old={**old, "id": rule.pk},
                  new={**audit.snapshot(new, RULE_FIELDS), "id": new.pk}, reason=reason)
    return new, recalculate_drafts([rule, new], actor)


def versions(rule: DeductionRule) -> list[DeductionRule]:
    return list(R.objects.filter(series=rule.series).order_by("effective_from", "id"))
