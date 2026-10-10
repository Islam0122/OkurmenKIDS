"""Расчёт начислений за период. Разрешены два типа оплаты.

* FIXED — индивидуальный месячный оклад, начисляется ПОЛНОЙ суммой за
  календарный месяц одним расчётом в месячном периоде (`PeriodType.MONTH`) и
  на половины месяца не делится. Не зависит от студентов, курсов, платежей и
  посещаемости. Неполный месяц бывает только по установленным условиям —
  правило или профиль начинают/прекращают действовать внутри месяца (приём,
  увольнение, новая ставка): тогда оклад × дни действия / дни месяца.
  Аванс — это частичная выплата месячного начисления (`is_advance`), а не
  отдельная половина оклада.
* PERCENT — процент от фиксированной стоимости курса, начисляется за
  каждый ЗАВЕРШЁННЫЙ цикл курса (services.cycles) в группе, за которую
  сотрудник отвечал на дату завершения:
    студенты цикла × стоимость курса × процент / 100
  Цикл относится к периоду по дате завершения (1–15 → первая половина,
  16–конец → вторая). Один цикл начисляется сотруднику один раз
  (`CycleAccrual`, уникально по циклу и сотруднику). Фактические платежи,
  посещаемость и число уроков сверх цикла на сумму не влияют.

`compute()` — чистая функция (строки, предупреждения, ошибки);
`calculate_payroll()` сохраняет результат в транзакции; `calculate_period()`
— массовый расчёт.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.db.models import Q, Sum
from django.utils import timezone

from ..models import (
    ALLOWED_SALARY_TYPES,
    CourseCycle,
    CycleAccrual,
    EmployeeSalaryProfile,
    Payroll,
    PayrollAdjustment,
    PayrollLine,
    PayrollPayment,
    PayrollPeriod,
    SalaryRule,
    SalaryType,
)
from . import AccountingError, audit
from .cycles import ensure_accruals, sync_all
from .money import ZERO, money, plain

LineType = PayrollLine.LineType
RuleType = SalaryRule.RuleType
Method = SalaryRule.Method

BIG_CHANGE_RATIO = Decimal("0.5")


@dataclass
class LineDraft:
    line_type: str
    description: str
    amount: Decimal
    rule: SalaryRule | None = None
    source_type: str = ""
    source_id: int | None = None
    quantity: Decimal | None = None
    rate: Decimal | None = None
    percentage: Decimal | None = None
    base_amount: Decimal | None = None
    metadata: dict = field(default_factory=dict)
    accrual: CycleAccrual | None = None


@dataclass
class Computation:
    lines: list[LineDraft] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    active_students: int | None = None

    @property
    def total(self) -> Decimal:
        return sum((line.amount for line in self.lines), ZERO)


def _q(value) -> Decimal:
    return Decimal(value).quantize(Decimal("0.0001"))


def _fmt(day: dt.date) -> str:
    return f"{day:%d.%m.%Y}"


def rules_for(profile: EmployeeSalaryProfile, period: PayrollPeriod) -> list[SalaryRule]:
    return [
        rule for rule in profile.rules.filter(is_active=True).select_related("group", "program").order_by("id")
        if rule.overlaps(period.start_date, period.end_date)
    ]


def _window(rule: SalaryRule, profile: EmployeeSalaryProfile, period: PayrollPeriod):
    """Дни периода, когда действуют и правило, и профиль."""
    lo = max(period.start_date, rule.effective_from, profile.effective_from)
    hi = min(d for d in (period.end_date, rule.effective_to, profile.effective_to) if d is not None)
    return (lo, hi) if lo <= hi else None


def _rule_label(rule: SalaryRule) -> str:
    scope = rule.group.name if rule.group_id else (rule.program.name if rule.program_id else "")
    return f"{rule.get_rule_type_display()}{f' · {scope}' if scope else ''} (правило #{rule.pk})"


def period_of(day: dt.date) -> tuple[int, int, str]:
    half = PayrollPeriod.PeriodType.FIRST_HALF if day.day <= 15 else PayrollPeriod.PeriodType.SECOND_HALF
    return day.year, day.month, half


# ---------------------------------------------------------------------------
# FIXED
# ---------------------------------------------------------------------------

def _fixed(rule, profile, period, out: Computation):
    """Оклад за календарный месяц: полная сумма, если правило и профиль
    действуют весь месяц; иначе — по дням их действия."""
    window = _window(rule, profile, period)
    if window is None:
        return
    lo, hi = window
    days = (hi - lo).days + 1
    month_name = f"{period.month:02d}.{period.year}"
    if days == period.month_days:
        amount, how = money(rule.amount), "полный месяц"
    else:
        amount = money(rule.amount * days / period.month_days)
        how = f"{days} из {period.month_days} дн.: правило действует {_fmt(lo)}–{_fmt(hi)}"
    out.lines.append(LineDraft(
        LineType.FIXED, f"Оклад за {month_name} ({how})", amount, rule,
        source_type="salary_rule", source_id=rule.pk, quantity=_q(Decimal(days) / period.month_days), rate=rule.amount,
        metadata={"method": SalaryRule.Method.MONTHLY, "days": days, "month_days": period.month_days,
                  "from": lo.isoformat(), "to": hi.isoformat()},
    ))


def _prior_half_month_fixed(profile, period, out: Computation):
    """Переход с прежней схемы: оклад за этот месяц мог уже начисляться
    полумесячными расчётами. Утверждённые не меняются — их сумма засчитывается
    отрицательной строкой; неутверждённые блокируют утверждение, пока
    бухгалтер их не аннулирует (сам расчёт ничего не меняет)."""
    halves = Payroll.objects.filter(
        employee=profile.employee, period__year=period.year, period__month=period.month,
        period__period_type__in=PayrollPeriod.HALVES,
    ).exclude(status=Payroll.Status.VOID).select_related("period")
    for half in halves:
        fixed = half.lines.filter(line_type=LineType.FIXED).aggregate(s=Sum("amount"))["s"] or ZERO
        if not fixed:
            continue
        label = f"{_fmt(half.period.start_date)}–{_fmt(half.period.end_date)}"
        if half.is_locked:
            out.lines.append(LineDraft(
                LineType.PRIOR_FIXED, f"Зачёт: оклад за {label} уже начислен утверждённым расчётом прежней схемы",
                -fixed, None, source_type="payroll", source_id=half.pk,
                metadata={"payroll_id": half.pk, "period": label, "amount": str(fixed)},
            ))
        else:
            out.errors.append(
                f"Есть неутверждённый полумесячный расчёт оклада за {label} (прежняя схема) — "
                "аннулируйте его, чтобы оклад не начислился дважды."
            )


# ---------------------------------------------------------------------------
# PERCENT — завершённые циклы курса
# ---------------------------------------------------------------------------

def _percent(profile, period, payroll_id, out: Computation, window_rules: list[SalaryRule]):
    """Строки процента — из начислений за циклы (`CycleAccrual`), которые
    создаются автоматически при достижении порога уроков (services.cycles).
    Здесь только: досоздать недостающие (правило появилось позже порога),
    обновить неутверждённые и включить их в период по дате завершения."""
    windows = [w for w in (_window(r, profile, period) for r in window_rules) if w]
    if not windows:
        return
    lo, hi = min(w[0] for w in windows), max(w[1] for w in windows)
    candidates = CourseCycle.objects.filter(
        status=CourseCycle.Status.COMPLETED, completed_on__gte=lo, completed_on__lte=hi,
    ).exclude(accruals__employee=profile.employee)
    for cycle in candidates.select_related("group", "course"):
        ensure_accruals(cycle)
    accruals = CycleAccrual.objects.filter(
        employee=profile.employee, status=CycleAccrual.Status.ACCRUED,
    ).filter(Q(payroll__isnull=True) | Q(payroll_id=payroll_id)).select_related("cycle__group", "cycle__course")
    for accrual in accruals.order_by("completed_on", "id"):
        late = False
        if not (lo <= accrual.completed_on <= hi):
            if accrual.completed_on > hi:
                continue
            # Порог достигнут задним числом в уже утверждённом периоде — не
            # теряется, а включается в текущий период с пометкой.
            year, month, half = period_of(accrual.completed_on)
            if not Payroll.objects.filter(
                employee=profile.employee, period__year=year, period__month=month, period__period_type=half,
                status__in=Payroll.LOCKED_STATUSES,
            ).exists():
                continue
            late = True
        ensure_accruals(accrual.cycle)  # обновить сумму, если правило поправили до утверждения
        accrual.refresh_from_db()
        if accrual.status != CycleAccrual.Status.ACCRUED:
            continue
        cycle = accrual.cycle
        note = " — порог достигнут в уже утверждённом периоде" if late else ""
        out.lines.append(LineDraft(
            LineType.PERCENT,
            f"Цикл {cycle.number} ({accrual.lessons_total} ур.) курса «{cycle.course.name}», группа «{cycle.group.name}»: "
            f"{accrual.student_count} студ. × {plain(accrual.course_price)} сом × {plain(accrual.percentage)}% "
            f"(порог {_fmt(accrual.completed_on)}){note}",
            accrual.amount, accrual.salary_rule, source_type="course_cycle", source_id=cycle.pk,
            quantity=Decimal(accrual.student_count), rate=accrual.course_price, percentage=accrual.percentage,
            base_amount=money(accrual.course_price * accrual.student_count), accrual=accrual,
            metadata={
                "cycle_id": cycle.pk, "cycle_number": cycle.number, "accrual_id": accrual.pk,
                "group_id": cycle.group_id, "group": cycle.group.name, "course_id": cycle.course_id,
                "course": cycle.course.name, "lessons": accrual.lessons, "lessons_total": accrual.lessons_total,
                "completed_on": accrual.completed_on.isoformat(), "students_count": accrual.student_count,
                "course_price": str(accrual.course_price), "late": late,
                "planned_payment_date": accrual.planned_payment_date.isoformat(),
            },
        ))
    # Спорные начисления (смена тренера, второй цикл за месяц) в расчёт не
    # входят и блокируют утверждение, пока бухгалтер не примет решение.
    for accrual in CycleAccrual.objects.filter(
        employee=profile.employee, status=CycleAccrual.Status.REVIEW_REQUIRED, completed_on__gte=lo,
        completed_on__lte=hi,
    ).select_related("cycle__group").order_by("completed_on", "id"):
        out.errors.append(
            f"Начисление за цикл {accrual.cycle.number} группы «{accrual.cycle.group.name}» "
            f"({_fmt(accrual.completed_on)}, {accrual.amount} сом) требует проверки: "
            + " ".join(accrual.review_reasons)
        )


def _overlaps(rules: list[SalaryRule]) -> list[str]:
    errors = []
    for i, a in enumerate(rules):
        for b in rules[i + 1:]:
            if a.rule_type != b.rule_type or (a.group_id, a.program_id) != (b.group_id, b.program_id):
                continue
            a_end, b_end = a.effective_to or dt.date.max, b.effective_to or dt.date.max
            if a.effective_from <= b_end and b.effective_from <= a_end:
                errors.append(
                    f"Пересекающиеся правила: #{a.pk} и #{b.pk} ({a.get_rule_type_display()}) "
                    f"действуют одновременно для одного основания."
                )
    return errors


def compute(period: PayrollPeriod, profile: EmployeeSalaryProfile, *, payroll_id=None) -> Computation:
    out = Computation()
    if not profile.is_active:
        out.errors.append("Зарплатный профиль отключён.")
        return out
    if profile.salary_type not in ALLOWED_SALARY_TYPES:
        out.errors.append(
            f"Схема оплаты «{profile.get_salary_type_display()}» больше не поддерживается — "
            "выберите «Фиксированный оклад» или «Процент от стоимости курса»."
        )
        return out
    rules = rules_for(profile, period)
    usable = []
    for rule in rules:
        if rule.rule_type != profile.salary_type:
            out.errors.append(f"{_rule_label(rule)}: тип правила не соответствует типу оплаты сотрудника — не применяется.")
        elif (rule.percentage if rule.rule_type == RuleType.PERCENT else rule.amount) is None:
            out.errors.append(f"{_rule_label(rule)}: не указана ставка.")
        else:
            usable.append(rule)
    if not rules:
        out.errors.append("Не настроена ставка: нет действующих правил начисления в этом периоде.")
        return out
    # Оклад — только в месячном периоде, процент — только в половинах месяца.
    if profile.salary_type == RuleType.FIXED and not period.is_month:
        out.errors.append("Оклад начисляется за полный месяц — рассчитайте период «Весь месяц (оклад)».")
        return out
    if profile.salary_type == RuleType.PERCENT and period.is_month:
        out.errors.append("Процент от курса начисляется по периодам 1–15 и 16–конец месяца, а не за месяц.")
        return out
    out.errors.extend(_overlaps(usable))
    for rule in usable:
        if rule.rule_type == RuleType.FIXED:
            _fixed(rule, profile, period, out)
    if profile.salary_type == RuleType.FIXED:
        _prior_half_month_fixed(profile, period, out)
    if profile.salary_type == RuleType.PERCENT:
        _percent(profile, period, payroll_id, out, usable)
    if profile.salary_type == RuleType.PERCENT:
        out.active_students = sum(int(l.quantity) for l in out.lines if l.line_type == LineType.PERCENT)
        if not out.lines:
            out.warnings.append("В периоде нет завершённых циклов курса — процент не начисляется.")
    return out


# ---------------------------------------------------------------------------
# Сохранение
# ---------------------------------------------------------------------------

def refresh_totals(payroll: Payroll) -> Payroll:
    """Итоги расчёта — всегда из записей (строки, корректировки, выплаты)."""
    payroll.total_accrued = payroll.lines.aggregate(s=Sum("amount"))["s"] or ZERO
    payroll.total_adjustments = (
        payroll.adjustments.filter(status=PayrollAdjustment.Status.APPLIED).aggregate(s=Sum("amount"))["s"] or ZERO
    )
    payroll.total_paid = (
        payroll.payments.filter(status=PayrollPayment.Status.CONFIRMED).aggregate(s=Sum("amount"))["s"] or ZERO
    )
    payroll.amount_due = payroll.total_accrued + payroll.total_adjustments - payroll.total_paid
    return payroll


def _previous_total(payroll: Payroll) -> Decimal | None:
    prev = (
        Payroll.objects.filter(employee_id=payroll.employee_id, period__end_date__lt=payroll.period.start_date,
                               period__period_type__in=(
                                   [PayrollPeriod.PeriodType.MONTH] if payroll.period.is_month else PayrollPeriod.HALVES
                               ))
        .exclude(status=Payroll.Status.VOID).order_by("-period__end_date").first()
    )
    return prev.total_accrued if prev else None


def _lock_payroll(period: PayrollPeriod, employee) -> tuple[Payroll, bool]:
    try:
        with transaction.atomic():
            payroll, created = Payroll.objects.get_or_create(period=period, employee=employee)
    except IntegrityError:  # параллельный запрос успел создать тот же расчёт
        payroll, created = Payroll.objects.get(period=period, employee=employee), False
    return Payroll.objects.select_for_update().get(pk=payroll.pk), created


def calculate_payroll(period: PayrollPeriod, employee, actor, *, sync: bool = True) -> Payroll:
    """Рассчитать (или пересчитать черновой) расчёт сотрудника за период.
    Утверждённый расчёт не пересчитывается — только корректировкой или
    контролируемым переоткрытием."""
    if period.status == PayrollPeriod.Status.CLOSED:
        raise AccountingError("Период закрыт — расчёты в нём больше не меняются.", code="period_closed")
    profile = EmployeeSalaryProfile.objects.select_related("employee").filter(employee=employee).first()
    if profile is None:
        raise AccountingError("У сотрудника нет зарплатного профиля.", code="no_profile")
    mismatch = (profile.salary_type == RuleType.FIXED) != period.is_month
    if mismatch and profile.salary_type in ALLOWED_SALARY_TYPES and not Payroll.objects.filter(
        period=period, employee=employee,
    ).exists():
        raise AccountingError(
            "Оклад рассчитывается в периоде «Весь месяц (оклад)»." if profile.salary_type == RuleType.FIXED
            else "Процент от курса рассчитывается в периодах 1–15 и 16–конец месяца.",
            code="wrong_period",
        )
    if sync and profile.salary_type == RuleType.PERCENT:
        sync_all()
    with transaction.atomic():
        payroll, created = _lock_payroll(period, employee)
        if not payroll.is_editable:
            raise AccountingError(
                f"Расчёт в статусе «{payroll.get_status_display()}» нельзя пересчитать — "
                "добавьте корректировку или переоткройте его через директора.",
                code="locked",
            )
        old = audit.snapshot(payroll, ("status", "total_accrued", "total_adjustments", "amount_due"))
        result = compute(period, profile, payroll_id=payroll.pk)
        CycleAccrual.objects.filter(payroll=payroll, status=CycleAccrual.Status.ACCRUED).update(
            payroll=None, line=None,
        )
        payroll.lines.all().delete()
        for d in result.lines:
            line = PayrollLine.objects.create(
                payroll=payroll, line_type=d.line_type, description=d.description[:255],
                source_type=d.source_type, source_id=d.source_id, salary_rule=d.rule, quantity=d.quantity,
                rate=d.rate, percentage=d.percentage, base_amount=d.base_amount, amount=d.amount,
                metadata=d.metadata,
            )
            if d.accrual is not None:
                CycleAccrual.objects.filter(pk=d.accrual.pk).update(payroll=payroll, line=line)
        refresh_totals(payroll)
        warnings = list(result.warnings)
        previous = _previous_total(payroll)
        if previous and abs(payroll.total_accrued - previous) > previous * BIG_CHANGE_RATIO:
            warnings.append(
                f"Начисление {payroll.total_accrued} сом существенно отличается от предыдущего периода ({previous} сом)."
            )
        payroll.warnings = warnings
        payroll.errors = result.errors
        payroll.salary_type = profile.salary_type
        payroll.position = profile.display_position
        payroll.department = profile.effective_department
        payroll.active_students = result.active_students
        payroll.status = Payroll.Status.CALCULATED
        payroll.return_reason = ""
        payroll.calculated_at = timezone.now()
        payroll.save()
        audit.log(
            actor, payroll, "calculate" if created or old["status"] == Payroll.Status.DRAFT else "recalculate",
            old=old, new=audit.snapshot(payroll, ("status", "total_accrued", "total_adjustments", "amount_due")),
            payroll=payroll,
        )
        if period.status == PayrollPeriod.Status.DRAFT or period.status == PayrollPeriod.Status.APPROVED:
            period.status = PayrollPeriod.Status.CALCULATED
            period.save(update_fields=["status"])
    return payroll


def employees_for(period: PayrollPeriod):
    """Кого считать в периоде: месяц — сотрудники на окладе; половины месяца —
    все остальные (процент и устаревшие схемы, по которым расчёт покажет ошибку)."""
    profiles = (
        EmployeeSalaryProfile.objects.filter(is_active=True, effective_from__lte=period.end_date)
        .filter(Q(effective_to__isnull=True) | Q(effective_to__gte=period.start_date))
        .select_related("employee")
    )
    if period.is_month:
        return profiles.filter(salary_type=SalaryType.FIXED)
    return profiles.exclude(salary_type=SalaryType.FIXED)


def calculate_period(period: PayrollPeriod, actor) -> dict:
    """Массовый расчёт: каждый сотрудник с действующим профилем. Ошибка
    одного сотрудника не прерывает расчёт остальных и не теряется — она
    попадает в отдельный список результата."""
    sync_all()
    calculated, skipped, failed = [], [], []
    for profile in employees_for(period):
        existing = Payroll.objects.filter(period=period, employee=profile.employee).first()
        if existing and not existing.is_editable:
            skipped.append({"employee_id": profile.employee_id, "employee": str(profile.employee),
                            "payroll_id": existing.pk, "status": existing.status,
                            "reason": f"Расчёт уже в статусе «{existing.get_status_display()}»."})
            continue
        try:
            payroll = calculate_payroll(period, profile.employee, actor, sync=False)
        except Exception as exc:  # noqa: BLE001 — каждая ошибка показывается, а не теряется
            message = exc.message if isinstance(exc, AccountingError) else "Внутренняя ошибка расчёта."
            failed.append({"employee_id": profile.employee_id, "employee": str(profile.employee), "error": message})
            continue
        calculated.append(payroll)
    audit.log(actor, period, "calculate_period", new={
        "calculated": len(calculated), "skipped": len(skipped), "failed": len(failed),
    })
    return {"calculated": calculated, "skipped": skipped, "failed": failed}
