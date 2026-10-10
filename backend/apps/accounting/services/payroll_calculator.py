"""Расчёт начислений за период.

`compute(period, profile)` — чистая функция: по правилам сотрудника и
данным LMS возвращает строки расчёта, предупреждения и ошибки, ничего не
записывая. `calculate_payroll` сохраняет результат в `Payroll` (один на
сотрудника и период) в транзакции; `calculate_period` — массовый расчёт.

Формулы (все суммы — Decimal, округление по строке — services.money):

* FIXED / SPLIT        — оклад × доля половины × (дни действия / дни периода)
* FIXED / PRORATE_DAYS — оклад × дни действия в периоде / дни месяца
* PER_GROUP            — так же, по дням, когда группа существовала и
                         сотрудник отвечал за неё (история тренеров)
* PER_STUDENT / STUDENT_DAYS — ставка × Σ(дни активности студента / дни месяца);
                         студент считается один раз на день, даже если
                         попадает под несколько групп / правил
* PER_STUDENT / SNAPSHOT — ставка × студенты на конец периода × дни действия / дни месяца
* REVENUE_PERCENT      — учитываемая выручка × процент / 100, отдельно по
                         каждой группе; возвраты — отдельными строками
* BONUS                — разово, в периоде, куда попадает дата начала правила
"""
from __future__ import annotations

import datetime as dt
from collections import defaultdict
from dataclasses import dataclass, field
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.db.models import F, Q, Sum
from django.utils import timezone

from apps.academy.models import Group, Student, TrainerAssignment

from ..models import (
    EmployeeSalaryProfile,
    Payroll,
    PayrollAdjustment,
    PayrollLine,
    PayrollPayment,
    PayrollPeriod,
    SalaryRule,
    StudentPayment,
)
from . import AccountingError, audit
from .activity import active_student_days, days_between, group_active_days, trainer_days, trainer_group_ids_ever
from .money import ZERO, allocate_by_days, money

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


def _runs(days: set[dt.date]):
    """Непрерывные отрезки [lo, hi] из множества дней."""
    ordered = sorted(days)
    if not ordered:
        return
    lo = prev = ordered[0]
    for day in ordered[1:]:
        if day != prev + dt.timedelta(days=1):
            yield lo, prev
            lo = day
        prev = day
    yield lo, prev


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


class _Context:
    """Общие данные одного расчёта сотрудника: учтённые платежи и
    студенто-дни, чтобы одно основание не попало в зарплату дважды."""

    def __init__(self, period, profile):
        self.period = period
        self.profile = profile
        self.employee = profile.employee
        teacher = getattr(self.employee, "teacher_profile", None)
        self.teacher_id = teacher.pk if teacher is not None else None
        self.counted_payments: set[int] = set()
        self.counted_refunds: set[int] = set()
        self.counted_student_days: set[tuple[int, dt.date]] = set()
        self.counted_group_days: set[tuple[int, dt.date]] = set()
        self.students: set[int] = set()
        self._ever = None

    @property
    def ever_groups(self) -> set[int]:
        if self._ever is None:
            self._ever = trainer_group_ids_ever(self.teacher_id)
        return self._ever

    def scope_groups(self, rule: SalaryRule) -> list[Group]:
        if rule.group_id:
            return [rule.group]
        groups = Group.objects.filter(id__in=self.ever_groups)
        if rule.program_id:
            groups = groups.filter(course_id=rule.program_id)
        return list(groups.select_related("course"))

    def coverage(self, rule: SalaryRule, lo: dt.date, hi: dt.date) -> dict[int, set[dt.date]]:
        """{group_id: дни [lo, hi], когда сотрудник отвечает за группу по
        этому правилу}. Если правило привязано к группе, а сотрудник в ней
        никогда не был тренером (куратор, программист без назначения) —
        все дни окна: основанием служит сама привязка правила."""
        tdays = trainer_days(self.teacher_id, lo, hi)
        window = days_between(lo, hi)
        result = {}
        for group in self.scope_groups(rule):
            if rule.group_id and group.pk not in self.ever_groups:
                result[group.pk] = set(window)
            else:
                result[group.pk] = tdays.get(group.pk, set()) & window
        return result


# ---------------------------------------------------------------------------
# Компоненты
# ---------------------------------------------------------------------------

def _fixed(rule, ctx: _Context, out: Computation):
    period = ctx.period
    window = _window(rule, ctx.profile, period)
    if window is None:
        return
    lo, hi = window
    days = (hi - lo).days + 1
    half = "первую" if period.is_first_half else "вторую"
    if rule.calculation_method == Method.PRORATE_DAYS:
        quantity = _q(Decimal(days) / period.month_days)
        amount = money(rule.amount * days / period.month_days)
        how = f"{days} из {period.month_days} дн. месяца"
    else:
        share = rule.first_half_share if period.is_first_half else Decimal("100") - rule.first_half_share
        quantity = _q(share / 100 * Decimal(days) / period.days)
        amount = money(rule.amount * share / 100 * days / period.days)
        how = f"{share.normalize()}% месячного оклада" + (f", {days} из {period.days} дн." if days != period.days else "")
    out.lines.append(LineDraft(
        LineType.FIXED, f"Оклад за {half} половину месяца ({how})", amount, rule,
        source_type="salary_rule", source_id=rule.pk, quantity=quantity, rate=rule.amount,
        metadata={"method": rule.calculation_method, "days": days, "from": lo.isoformat(), "to": hi.isoformat()},
    ))


def _bonus(rule, ctx: _Context, out: Computation):
    period = ctx.period
    if period.start_date <= rule.effective_from <= period.end_date:
        out.lines.append(LineDraft(
            LineType.BONUS, rule.description or "Дополнительное начисление", money(rule.amount), rule,
            source_type="salary_rule", source_id=rule.pk, quantity=Decimal("1"), rate=rule.amount,
        ))


def _per_group(rule, ctx: _Context, out: Computation):
    period = ctx.period
    window = _window(rule, ctx.profile, period)
    if window is None:
        return
    lo, hi = window
    coverage = ctx.coverage(rule, lo, hi)
    if not coverage:
        out.warnings.append(f"{_rule_label(rule)}: нет групп, за которые отвечает сотрудник.")
        return
    groups = {g.pk: g for g in Group.objects.filter(pk__in=coverage)}
    for group_id, days in coverage.items():
        group = groups[group_id]
        days = days & group_active_days(group, lo, hi)
        fresh = {d for d in days if (group_id, d) not in ctx.counted_group_days}
        if len(fresh) < len(days):
            out.warnings.append(
                f"{_rule_label(rule)}: группа «{group.name}» уже оплачена другим правилом за "
                f"{len(days) - len(fresh)} дн. — повторно не начисляется."
            )
        if not fresh:
            continue
        ctx.counted_group_days.update((group_id, d) for d in fresh)
        n = len(fresh)
        if rule.calculation_method == Method.SPLIT:
            share = rule.first_half_share if period.is_first_half else Decimal("100") - rule.first_half_share
            amount = money(rule.amount * share / 100 * n / period.days)
            quantity = _q(share / 100 * Decimal(n) / period.days)
            how = f"{share.normalize()}% ставки, {n} из {period.days} дн."
        else:
            amount = money(rule.amount * n / period.month_days)
            quantity = _q(Decimal(n) / period.month_days)
            how = f"{n} из {period.month_days} дн. месяца"
        out.lines.append(LineDraft(
            LineType.PER_GROUP, f"Оплата за группу «{group.name}» ({how})", amount, rule,
            source_type="group", source_id=group_id, quantity=quantity, rate=rule.amount,
            metadata={"group": group.name, "days": n, "method": rule.calculation_method},
        ))


def _per_student(rule, ctx: _Context, out: Computation):
    period = ctx.period
    window = _window(rule, ctx.profile, period)
    if window is None:
        return
    lo, hi = window
    coverage = ctx.coverage(rule, lo, hi)
    if not coverage:
        out.warnings.append(f"{_rule_label(rule)}: нет групп, за которые отвечает сотрудник.")
        return
    activity = active_student_days(lo, hi, group_ids=coverage.keys())

    if rule.calculation_method == Method.SNAPSHOT:
        control = hi
        students = sorted(
            sid for sid, days in activity.items()
            if control in days and control in coverage.get(days[control], set())
            and (sid, control) not in ctx.counted_student_days
        )
        ctx.counted_student_days.update((sid, control) for sid in students)
        ctx.students.update(students)
        n_days = (hi - lo).days + 1
        amount = money(rule.amount * len(students) * n_days / period.month_days)
        if not students:
            out.warnings.append(f"{_rule_label(rule)}: на {_fmt(control)} нет активных студентов.")
        out.lines.append(LineDraft(
            LineType.PER_STUDENT,
            f"Оплата за {len(students)} активн. студ. на {_fmt(control)} ({n_days} из {period.month_days} дн. месяца)",
            amount, rule, source_type="salary_rule", source_id=rule.pk, quantity=Decimal(len(students)),
            rate=rule.amount, metadata={"method": "SNAPSHOT", "control_date": control.isoformat(),
                                        "students": _student_rows({s: n_days for s in students})},
        ))
        return

    per_student: dict[int, int] = {}
    duplicates = 0
    for sid, days in activity.items():
        n = 0
        for day, group_id in days.items():
            if day not in coverage.get(group_id, set()):
                continue
            if (sid, day) in ctx.counted_student_days:
                duplicates += 1
                continue
            ctx.counted_student_days.add((sid, day))
            n += 1
        if n:
            per_student[sid] = n
    if duplicates:
        out.warnings.append(
            f"{_rule_label(rule)}: {duplicates} студенто-дн. уже учтены другим правилом — повторно не начисляются."
        )
    ctx.students.update(per_student)
    student_days = sum(per_student.values())
    equivalent = _q(Decimal(student_days) / period.month_days)
    amount = money(rule.amount * student_days / period.month_days)
    if not per_student:
        out.warnings.append(f"{_rule_label(rule)}: нет данных об активных студентах в периоде.")
    out.lines.append(LineDraft(
        LineType.PER_STUDENT,
        f"Оплата за {len(per_student)} активн. студ. ({student_days} студенто-дн. / {period.month_days} дн. месяца "
        f"= {equivalent.normalize()} студ.-мес.)",
        amount, rule, source_type="salary_rule", source_id=rule.pk, quantity=equivalent, rate=rule.amount,
        metadata={"method": "STUDENT_DAYS", "student_days": student_days, "month_days": period.month_days,
                  "students": _student_rows(per_student)},
    ))


def _student_rows(days_by_student: dict[int, int]) -> list[dict]:
    names = {s.pk: str(s) for s in Student.objects.filter(pk__in=days_by_student)}
    return [
        {"id": sid, "name": names.get(sid, f"#{sid}"), "days": n}
        for sid, n in sorted(days_by_student.items(), key=lambda kv: names.get(kv[0], ""))
    ]


class _Responsibility:
    """Кто отвечал за группу в конкретный день (по истории назначений)."""

    def __init__(self, group_ids):
        self.rows = defaultdict(list)
        for row in TrainerAssignment.objects.filter(group_id__in=group_ids).exclude(end_date=F("start_date")):
            self.rows[row.group_id].append(row)

    def teachers(self, group_id, day) -> set[int]:
        return {
            r.teacher_id for r in self.rows[group_id]
            if r.start_date <= day and (r.end_date is None or r.end_date > day)
        }

    def attribution_day(self, payment: StudentPayment) -> dt.date:
        """День, по которому платёж закрепляется за тренером: дата
        поступления. Предоплата до первого назначения тренера в группу
        (деньги пришли раньше, чем группа начала работать) закрепляется за
        первым тренером, отвечающим за оплаченный период."""
        if self.teachers(payment.group_id, payment.received_date):
            return payment.received_date
        starts = [r.start_date for r in self.rows[payment.group_id]]
        if starts and payment.received_date < min(starts):
            return max(payment.service_start, min(starts))
        return payment.received_date


def _revenue(rule, ctx: _Context, out: Computation):
    period = ctx.period
    window = _window(rule, ctx.profile, period)
    if window is None:
        return
    lo, hi = window
    groups = ctx.scope_groups(rule)
    if not groups:
        out.warnings.append(f"{_rule_label(rule)}: нет групп, за которые отвечает сотрудник.")
        return
    group_ids = [g.pk for g in groups]
    names = {g.pk: g for g in groups}
    resp = _Responsibility(group_ids)
    bound_without_history = {gid for gid in group_ids if rule.group_id and gid not in ctx.ever_groups}
    pct = rule.percentage
    allocated = rule.revenue_basis == SalaryRule.RevenueBasis.ALLOCATED
    coverage = ctx.coverage(rule, lo, hi) if allocated else None

    def owns(payment: StudentPayment) -> bool:
        if payment.group_id in bound_without_history:
            return True
        return ctx.teacher_id in resp.teachers(payment.group_id, resp.attribution_day(payment))

    confirmed = StudentPayment.objects.filter(status=StudentPayment.Status.CONFIRMED, group_id__in=group_ids)
    base: dict[int, Decimal] = defaultdict(lambda: ZERO)
    rows: dict[int, list] = defaultdict(list)
    skipped = 0

    if allocated:
        payments = confirmed.filter(
            kind=StudentPayment.Kind.PAYMENT, service_start__lte=hi, service_end__gte=lo,
        ).select_related("student")
        for p in payments:
            portion = sum(
                (allocate_by_days(p.amount, p.service_start, p.service_end, a, b)
                 for a, b in _runs(coverage.get(p.group_id, set()))),
                ZERO,
            )
            if not portion:
                continue
            if p.pk in ctx.counted_payments:
                skipped += 1
                continue
            ctx.counted_payments.add(p.pk)
            base[p.group_id] += portion
            rows[p.group_id].append(_payment_row(p, portion))
    else:
        payments = confirmed.filter(
            kind=StudentPayment.Kind.PAYMENT, received_date__gte=lo, received_date__lte=hi,
        ).select_related("student")
        for p in payments:
            if not owns(p):
                continue
            if p.pk in ctx.counted_payments:
                skipped += 1
                continue
            ctx.counted_payments.add(p.pk)
            base[p.group_id] += p.amount
            rows[p.group_id].append(_payment_row(p, p.amount))
    if skipped:
        out.warnings.append(f"{_rule_label(rule)}: {skipped} платеж(а) уже учтены другим правилом — повторно не начисляются.")

    for group_id in sorted(base, key=lambda gid: names[gid].name):
        group_base = base[group_id]
        group = names[group_id]
        out.lines.append(LineDraft(
            LineType.REVENUE_PERCENT,
            f"{pct.normalize()}% с оплаты группы «{group.name}» ({group.course.name})",
            money(group_base * pct / 100), rule, source_type="group", source_id=group_id,
            quantity=Decimal(len(rows[group_id])), percentage=pct, base_amount=money(group_base),
            metadata={"basis": rule.revenue_basis, "group": group.name, "program": group.course.name,
                      "payments": rows[group_id]},
        ))
    if not base:
        out.warnings.append(f"{_rule_label(rule)}: за период нет учитываемых платежей студентов.")

    if rule.refund_policy == SalaryRule.RefundPolicy.IGNORE:
        return
    refunds = confirmed.filter(kind=StudentPayment.Kind.REFUND, refund_of__status=StudentPayment.Status.CONFIRMED)
    if allocated:
        refunds = refunds.filter(received_date__lte=hi).filter(
            Q(refund_of__service_end__gte=lo) | Q(received_date__gte=lo)
        )
    else:
        refunds = refunds.filter(received_date__gte=lo, received_date__lte=hi)
    for r in refunds.select_related("refund_of", "student"):
        original = r.refund_of
        if allocated:
            start = max(r.received_date, original.service_start)
            end = original.service_end if r.received_date <= original.service_end else r.received_date
            portion = sum(
                (allocate_by_days(r.amount, start, end, a, b) for a, b in _runs(coverage.get(r.group_id, set()))),
                ZERO,
            )
        else:
            portion = r.amount if owns(original) else ZERO
        if not portion or r.pk in ctx.counted_refunds:
            continue
        ctx.counted_refunds.add(r.pk)
        origin_payroll = (
            Payroll.objects.filter(
                employee=ctx.employee, period__start_date__lte=original.received_date,
                period__end_date__gte=original.received_date,
            ).values("id", "period_id").first()
        )
        group = names.get(r.group_id)
        out.lines.append(LineDraft(
            LineType.REFUND_CORRECTION,
            f"Корректировка возврата: {r.student} — {r.amount} сом от {_fmt(r.received_date)} "
            f"(платёж от {_fmt(original.received_date)})",
            -money(portion * pct / 100), rule, source_type="student_payment", source_id=r.pk,
            percentage=pct, base_amount=-money(portion),
            metadata={"refund_id": r.pk, "original_payment_id": original.pk,
                      "original_received_date": original.received_date.isoformat(),
                      "original_payroll_id": origin_payroll["id"] if origin_payroll else None,
                      "group": group.name if group else "", "group_id": r.group_id},
        ))


def _payment_row(p: StudentPayment, counted: Decimal) -> dict:
    return {
        "id": p.pk, "student_id": p.student_id, "student": str(p.student), "amount": str(p.amount),
        "counted": str(money(counted)), "received_date": p.received_date.isoformat(),
        "service_start": p.service_start.isoformat(), "service_end": p.service_end.isoformat(),
    }


_HANDLERS = {
    RuleType.FIXED: _fixed,
    RuleType.BONUS: _bonus,
    RuleType.PER_GROUP: _per_group,
    RuleType.PER_STUDENT: _per_student,
    RuleType.REVENUE_PERCENT: _revenue,
}


def _overlaps(rules: list[SalaryRule]) -> list[str]:
    errors = []
    for i, a in enumerate(rules):
        for b in rules[i + 1:]:
            if a.rule_type == RuleType.BONUS or a.rule_type != b.rule_type:
                continue
            if (a.group_id, a.program_id) != (b.group_id, b.program_id):
                continue
            a_end, b_end = a.effective_to or dt.date.max, b.effective_to or dt.date.max
            if a.effective_from <= b_end and b.effective_from <= a_end:
                errors.append(
                    f"Пересекающиеся правила: #{a.pk} и #{b.pk} ({a.get_rule_type_display()}) "
                    f"действуют одновременно для одного основания."
                )
    return errors


def compute(period: PayrollPeriod, profile: EmployeeSalaryProfile) -> Computation:
    out = Computation()
    rules = rules_for(profile, period)
    if not profile.is_active:
        out.errors.append("Зарплатный профиль отключён.")
        return out
    if not rules:
        out.errors.append("Не настроена ставка: нет действующих правил начисления в этом периоде.")
        return out
    out.errors.extend(_overlaps(rules))
    ctx = _Context(period, profile)
    for rule in rules:
        if rule.rule_type == RuleType.REVENUE_PERCENT and rule.percentage is None or (
            rule.rule_type != RuleType.REVENUE_PERCENT and rule.amount is None
        ):
            out.errors.append(f"{_rule_label(rule)}: не указана ставка.")
            continue
        if not rule.group_id and ctx.teacher_id is None and rule.rule_type in (
            RuleType.PER_GROUP, RuleType.PER_STUDENT, RuleType.REVENUE_PERCENT,
        ):
            out.errors.append(
                f"{_rule_label(rule)}: сотрудник не тренер — укажите в правиле конкретную группу."
            )
            continue
        _HANDLERS[rule.rule_type](rule, ctx, out)
    if any(r.rule_type == RuleType.PER_STUDENT for r in rules):
        out.active_students = len(ctx.students)
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
        Payroll.objects.filter(employee_id=payroll.employee_id, period__end_date__lt=payroll.period.start_date)
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


def calculate_payroll(period: PayrollPeriod, employee, actor) -> Payroll:
    """Рассчитать (или пересчитать черновой) расчёт сотрудника за период.
    Утверждённый расчёт не пересчитывается — только корректировкой или
    контролируемым переоткрытием."""
    if period.status == PayrollPeriod.Status.CLOSED:
        raise AccountingError("Период закрыт — расчёты в нём больше не меняются.", code="period_closed")
    profile = EmployeeSalaryProfile.objects.select_related("employee").filter(employee=employee).first()
    if profile is None:
        raise AccountingError("У сотрудника нет зарплатного профиля.", code="no_profile")
    with transaction.atomic():
        payroll, created = _lock_payroll(period, employee)
        if not payroll.is_editable:
            raise AccountingError(
                f"Расчёт в статусе «{payroll.get_status_display()}» нельзя пересчитать — "
                "добавьте корректировку или переоткройте его через директора.",
                code="locked",
            )
        old = audit.snapshot(payroll, ("status", "total_accrued", "total_adjustments", "amount_due"))
        result = compute(period, profile)
        payroll.lines.all().delete()
        PayrollLine.objects.bulk_create([
            PayrollLine(
                payroll=payroll, line_type=d.line_type, description=d.description[:255],
                source_type=d.source_type, source_id=d.source_id, salary_rule=d.rule, quantity=d.quantity,
                rate=d.rate, percentage=d.percentage, base_amount=d.base_amount, amount=d.amount,
                metadata=d.metadata,
            )
            for d in result.lines
        ])
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
    return (
        EmployeeSalaryProfile.objects.filter(is_active=True, effective_from__lte=period.end_date)
        .filter(Q(effective_to__isnull=True) | Q(effective_to__gte=period.start_date))
        .select_related("employee")
    )


def calculate_period(period: PayrollPeriod, actor) -> dict:
    """Массовый расчёт: каждый сотрудник с действующим профилем. Ошибка
    одного сотрудника не прерывает расчёт остальных и не теряется — она
    попадает в отдельный список результата."""
    calculated, skipped, failed = [], [], []
    for profile in employees_for(period):
        existing = Payroll.objects.filter(period=period, employee=profile.employee).first()
        if existing and not existing.is_editable:
            skipped.append({"employee_id": profile.employee_id, "employee": str(profile.employee),
                            "payroll_id": existing.pk, "status": existing.status,
                            "reason": f"Расчёт уже в статусе «{existing.get_status_display()}»."})
            continue
        try:
            payroll = calculate_payroll(period, profile.employee, actor)
        except Exception as exc:  # noqa: BLE001 — каждая ошибка показывается, а не теряется
            message = exc.message if isinstance(exc, AccountingError) else "Внутренняя ошибка расчёта."
            failed.append({"employee_id": profile.employee_id, "employee": str(profile.employee), "error": message})
            continue
        calculated.append(payroll)
    audit.log(actor, period, "calculate_period", new={
        "calculated": len(calculated), "skipped": len(skipped), "failed": len(failed),
    })
    return {"calculated": calculated, "skipped": skipped, "failed": failed}
