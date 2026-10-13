"""План выплат: подготовка выплат сотрудникам на дату.

Источник истины — существующие начисления (`Payroll` в статусах «Утверждён»,
«Частично выплачен», «Выплачен») и выплаты (`PayrollPayment`). План ничего не
начисляет и не выплачивает сам:

* строка плана — сколько планируется выплатить по одному начислению;
* подготовленные средства — сумма, внесённая бухгалтером вручную (в системе нет
  данных о кассе), это НЕ выплаты;
* выплата по плану регистрируется существующим `register_payment` (те же
  проверки остатка, блокировки и идемпотентность) со ссылкой на строку плана.

Формулы
* Остаток начисления = подтверждённая сумма (строки + применённые
  корректировки; удержание — отрицательная корректировка) − действительные
  выплаты = `Payroll.amount_due`.
* Остаток строки = min(запланировано − выплачено по строке, остаток начисления):
  если начисление погасили вне плана, план это видит.
* Резерв начисления = сумма остатков строк в активных (не отменённых) планах;
  он не может превышать остаток начисления — одно начисление нельзя
  запланировать дважды на одну и ту же сумму, переплата невозможна.
* Потребность плана = выплачено по плану + остаток строк (если начисление
  частично погасили вне плана, потребность уменьшается).
* Дефицит = max(0, потребность − подготовлено); готовность = подготовлено /
  потребность × 100 % (0, если в плане нет строк). Выплаты по плану берутся из
  подготовленных средств, поэтому сами по себе дефицит не меняют.

Статус (отображаемый) вычисляется: «Черновик» и «Отменено» — по состоянию;
у утверждённого плана: все строки погашены → «Выплачено»; есть выплаты →
«Частично выплачено»; подготовлено ≥ потребности → «Готово к выплате»;
подготовлено > 0 → «Частично профинансировано»; иначе «Запланировано».
"""
from __future__ import annotations

import datetime as dt
from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from ..models import (
    Department,
    PayoutPlan,
    PayoutPlanLine,
    Payroll,
    PayrollPayment,
)
from . import AccountingError, audit
from .money import ZERO
from .payout import planned_date_for_period
from .report_service import period_label

DRAFT, SCHEDULED, PARTIALLY_FUNDED, READY, PARTIALLY_PAID, PAID, CANCELLED = (
    "DRAFT", "SCHEDULED", "PARTIALLY_FUNDED", "READY", "PARTIALLY_PAID", "PAID", "CANCELLED",
)
STATUS_LABELS = {
    DRAFT: "Черновик", SCHEDULED: "Запланировано", PARTIALLY_FUNDED: "Частично профинансировано",
    READY: "Готово к выплате", PARTIALLY_PAID: "Частично выплачено", PAID: "Выплачено", CANCELLED: "Отменено",
}
PLAN_FIELDS = ("title", "year", "month", "payout_date", "prepared_amount", "comment", "state")


# ---------------------------------------------------------------------------
# Расчёты
# ---------------------------------------------------------------------------

def line_paid(line: PayoutPlanLine) -> Decimal:
    return line.payments.filter(status=PayrollPayment.Status.CONFIRMED).aggregate(s=Sum("amount"))["s"] or ZERO


def line_remaining(line: PayoutPlanLine, *, paid: Decimal | None = None) -> Decimal:
    paid = line_paid(line) if paid is None else paid
    return max(ZERO, min(line.planned_amount - paid, line.payroll.amount_due))


def reserved_elsewhere(payroll: Payroll, *, exclude_line_id=None) -> Decimal:
    """Сколько остатка начисления уже зарезервировано активными планами."""
    lines = PayoutPlanLine.objects.filter(payroll=payroll, is_removed=False).exclude(
        plan__state=PayoutPlan.State.CANCELLED,
    ).select_related("payroll")
    if exclude_line_id:
        lines = lines.exclude(pk=exclude_line_id)
    return sum((line_remaining(line) for line in lines), ZERO)


def available(payroll: Payroll, *, exclude_line_id=None) -> Decimal:
    return max(ZERO, payroll.amount_due - reserved_elsewhere(payroll, exclude_line_id=exclude_line_id))


def _readiness(prepared: Decimal, need: Decimal, has_lines: bool) -> Decimal:
    if need > 0:
        return (min(prepared, need) * 100 / need).quantize(Decimal("0.1"))
    return Decimal("100.0") if has_lines else Decimal("0.0")


@dataclass
class PlanTotals:
    planned: Decimal
    paid: Decimal
    remaining: Decimal
    prepared: Decimal
    deficit: Decimal
    readiness: Decimal
    employees: int
    status: str

    def as_dict(self) -> dict:
        return {"planned": self.planned, "paid": self.paid, "remaining": self.remaining, "prepared": self.prepared,
                "deficit": self.deficit, "readiness_percent": self.readiness, "employees": self.employees,
                "status": self.status, "status_display": STATUS_LABELS[self.status]}


def totals(plan: PayoutPlan) -> PlanTotals:
    lines = list(plan.lines.filter(is_removed=False).select_related("payroll"))
    paid = remaining = planned = ZERO
    for line in lines:
        p = line_paid(line)
        planned += line.planned_amount
        paid += p
        remaining += line_remaining(line, paid=p)
    need = paid + remaining
    deficit = max(ZERO, need - plan.prepared_amount)
    readiness = _readiness(plan.prepared_amount, need, bool(lines))
    if plan.state == PayoutPlan.State.CANCELLED:
        status = CANCELLED
    elif plan.state == PayoutPlan.State.DRAFT:
        status = DRAFT
    elif lines and remaining == 0:
        status = PAID
    elif paid > 0:
        status = PARTIALLY_PAID
    elif plan.prepared_amount >= need > 0:
        status = READY
    elif plan.prepared_amount > 0:
        status = PARTIALLY_FUNDED
    else:
        status = SCHEDULED
    return PlanTotals(planned, paid, remaining, plan.prepared_amount, deficit, readiness,
                      len({line.payroll.employee_id for line in lines}), status)


def explain_line(line: PayoutPlanLine) -> dict:
    """Почему сотруднику запланирована именно эта сумма."""
    payroll = line.payroll
    paid_here = line_paid(line)
    accrued = payroll.total_accrued + payroll.total_adjustments
    paid_before = payroll.total_paid - paid_here
    remaining = line_remaining(line, paid=paid_here)
    subjects = sorted({l.metadata.get("subject") for l in payroll.lines.all() if l.metadata.get("subject")})
    profile = getattr(payroll.employee, "salary_profile", None)
    department = payroll.department or (profile.effective_department if profile else Department.OTHER)
    if remaining == 0 and paid_here >= line.planned_amount:
        status, status_display = "PAID", "Выплачено"
    elif remaining == 0:
        status, status_display = "SETTLED_OUTSIDE", "Погашено вне плана"
    elif paid_here > 0:
        status, status_display = "PARTIALLY_PAID", "Частично выплачено"
    else:
        status, status_display = "PLANNED", "Запланировано"
    return {
        "id": line.pk, "payroll": payroll.pk, "employee": payroll.employee_id,
        "employee_name": payroll.employee.get_full_name() or payroll.employee.username,
        "position": payroll.position, "department": department, "department_display": Department(department).label,
        "subjects": subjects, "salary_type": payroll.salary_type, "salary_type_display": payroll.get_salary_type_display(),
        "period_label": period_label(payroll.period), "year": payroll.period.year, "month": payroll.period.month,
        "accrued": accrued, "paid_before": paid_before, "planned_amount": line.planned_amount,
        "paid_by_plan": paid_here, "remaining_in_plan": remaining,
        "due_after_plan": max(ZERO, payroll.amount_due - remaining),
        "payroll_status": payroll.status, "payroll_status_display": payroll.get_status_display(),
        "planned_payment_date": planned_date_for_period(payroll.period),
        "basis": [{"description": l.description, "amount": l.amount} for l in payroll.lines.all()],
        "comment": line.comment, "status": status, "status_display": status_display,
    }


# ---------------------------------------------------------------------------
# Изменения (все — в транзакции, с блокировкой плана и проверкой версии)
# ---------------------------------------------------------------------------

def _locked_plan(plan: PayoutPlan, version: int | None) -> PayoutPlan:
    plan = PayoutPlan.objects.select_for_update().get(pk=plan.pk)
    if version is not None and int(version) != plan.version:
        raise AccountingError(
            "План уже изменён другим пользователем — обновите страницу и повторите действие.", code="conflict",
        )
    return plan


def _bump(plan: PayoutPlan, fields: list[str]) -> None:
    plan.version += 1
    plan.save(update_fields=[*fields, "version", "updated_at"])


def _require_reason(reason: str) -> str:
    reason = (reason or "").strip()
    if not reason:
        raise AccountingError("Укажите причину.", code="reason_required")
    return reason


def _check_payroll(payroll: Payroll) -> None:
    if payroll.status not in Payroll.LOCKED_STATUSES:
        raise AccountingError(f"Начисление #{payroll.pk} не утверждено — в план включаются только утверждённые "
                              "начисления.", code="not_approved")
    if payroll.period.status == payroll.period.Status.CLOSED:
        raise AccountingError(f"Период начисления #{payroll.pk} закрыт.", code="period_closed")


def create_plan(*, actor, title: str, year: int, month: int, payout_date: dt.date, prepared_amount=ZERO,
                comment: str = "", lines: list[dict] | None = None) -> PayoutPlan:
    with transaction.atomic():
        plan = PayoutPlan.objects.create(title=title.strip(), year=year, month=month, payout_date=payout_date,
                                         prepared_amount=Decimal(prepared_amount or 0), comment=comment,
                                         created_by=actor)
        audit.log(actor, plan, "create", new=audit.snapshot(plan, PLAN_FIELDS))
        for item in lines or []:
            _add_line(plan, actor=actor, **item)
    return plan


def _add_line(plan: PayoutPlan, *, actor, payroll, amount=None, comment: str = "") -> PayoutPlanLine:
    payroll = Payroll.objects.select_for_update(of=("self",)).select_related("period", "employee").get(
        pk=getattr(payroll, "pk", payroll))
    _check_payroll(payroll)
    if plan.lines.filter(payroll=payroll, is_removed=False).exists():
        raise AccountingError(f"Начисление #{payroll.pk} уже есть в этом плане.", code="duplicate")
    free = available(payroll)
    amount = free if amount in (None, "") else Decimal(amount)
    if amount <= 0:
        raise AccountingError(f"По начислению #{payroll.pk} нечего планировать: остаток уже выплачен или "
                              "запланирован в других планах.", code="nothing_due")
    if amount > free:
        raise AccountingError(
            f"По начислению #{payroll.pk} можно запланировать не больше {free} сом (остаток {payroll.amount_due}, "
            f"из них {payroll.amount_due - free} уже в других планах).", code="exceeds_due",
        )
    line = PayoutPlanLine.objects.create(plan=plan, payroll=payroll, planned_amount=amount, comment=comment)
    audit.log(actor, line, "add_line", new={"plan": plan.pk, "payroll": payroll.pk, "amount": amount,
                                            "employee": payroll.employee_id,
                                            "employee_name": payroll.employee.get_full_name()}, payroll=payroll)
    return line


def add_lines(plan: PayoutPlan, *, actor, items: list[dict], version: int | None = None) -> PayoutPlan:
    with transaction.atomic():
        plan = _locked_plan(plan, version)
        if plan.state != PayoutPlan.State.DRAFT:
            raise AccountingError("Состав можно менять только в черновике.", code="bad_state")
        for item in items:
            _add_line(plan, actor=actor, **item)
        _bump(plan, [])
    return plan


def update_line(line: PayoutPlanLine, *, actor, amount=None, comment=None, remove: bool = False,
                reason: str = "", version: int | None = None) -> PayoutPlanLine:
    with transaction.atomic():
        plan = _locked_plan(line.plan, version)
        line = PayoutPlanLine.objects.select_for_update().select_related("payroll").get(pk=line.pk)
        if plan.state != PayoutPlan.State.DRAFT:
            raise AccountingError("Состав можно менять только в черновике.", code="bad_state")
        if line.is_removed:
            raise AccountingError("Строка уже исключена.", code="bad_state")
        old = {"amount": line.planned_amount, "comment": line.comment, "is_removed": line.is_removed}
        if remove:
            line.is_removed = True
        if amount is not None:
            payroll = Payroll.objects.select_for_update().get(pk=line.payroll_id)
            amount = Decimal(amount)
            free = available(payroll, exclude_line_id=line.pk)
            if amount <= 0 or amount > free:
                raise AccountingError(f"Сумма должна быть от 0,01 до {free} сом (остаток начисления с учётом других "
                                      "планов).", code="exceeds_due")
            line.planned_amount = amount
        if comment is not None:
            line.comment = comment
        line.save()
        audit.log(actor, line, "remove_line" if remove else "update_line", old=old,
                  new={"amount": line.planned_amount, "comment": line.comment, "is_removed": line.is_removed},
                  reason=reason, payroll=line.payroll)
        _bump(plan, [])
    return line


def update_plan(plan: PayoutPlan, *, actor, changes: dict, reason: str = "", version: int | None = None) -> PayoutPlan:
    """Черновик: название, месяц, дата, подготовлено, комментарий. Утверждённый
    план: подготовленные средства, комментарий и дата (с причиной)."""
    with transaction.atomic():
        plan = _locked_plan(plan, version)
        if plan.state == PayoutPlan.State.CANCELLED:
            raise AccountingError("План отменён — изменить его нельзя.", code="bad_state")
        allowed = {"title", "year", "month", "payout_date", "prepared_amount", "comment"}
        if plan.state == PayoutPlan.State.APPROVED:
            allowed = {"prepared_amount", "comment", "payout_date"}
        unknown = set(changes) - allowed
        if unknown:
            raise AccountingError(f"В утверждённом плане нельзя менять: {', '.join(sorted(unknown))}.", code="bad_state")
        if plan.state == PayoutPlan.State.APPROVED and "payout_date" in changes and changes["payout_date"] != plan.payout_date:
            _require_reason(reason)
        old = audit.snapshot(plan, PLAN_FIELDS)
        for name, value in changes.items():
            setattr(plan, name, value)
        if plan.prepared_amount < 0:
            raise AccountingError("Подготовленные средства не могут быть отрицательными.")
        _bump(plan, list(changes))
        new = audit.snapshot(plan, PLAN_FIELDS)
        diff_old = {k: v for k, v in old.items() if new[k] != v}
        if diff_old:
            action = "change_prepared" if set(diff_old) == {"prepared_amount"} else (
                "change_date" if set(diff_old) == {"payout_date"} else "update")
            audit.log(actor, plan, action, old=diff_old, new={k: new[k] for k in diff_old}, reason=reason)
    return plan


def approve_plan(plan: PayoutPlan, *, actor, version: int | None = None) -> PayoutPlan:
    """Утвердить: состав фиксируется; резервы перепроверяются под блокировкой
    начислений (параллельные планы не могут разобрать один остаток дважды)."""
    with transaction.atomic():
        plan = _locked_plan(plan, version)
        if plan.state != PayoutPlan.State.DRAFT:
            raise AccountingError("Утвердить можно только черновик.", code="bad_state")
        lines = list(plan.lines.filter(is_removed=False).order_by("payroll_id"))
        if not lines:
            raise AccountingError("В плане нет начислений.", code="empty")
        for line in lines:
            payroll = Payroll.objects.select_for_update().select_related("period").get(pk=line.payroll_id)
            _check_payroll(payroll)
            free = available(payroll, exclude_line_id=line.pk)
            if line.planned_amount > free:
                raise AccountingError(
                    f"{payroll.employee}: запланировано {line.planned_amount} сом, а свободный остаток начисления "
                    f"{free} сом — исправьте строку.", code="exceeds_due",
                )
        plan.state = PayoutPlan.State.APPROVED
        plan.approved_by, plan.approved_at = actor, timezone.now()
        _bump(plan, ["state", "approved_by", "approved_at"])
        audit.log(actor, plan, "approve", old={"state": PayoutPlan.State.DRAFT}, new={
            "state": plan.state, **{k: str(v) for k, v in totals(plan).as_dict().items() if k in ("planned", "prepared")},
        })
    return plan


def cancel_plan(plan: PayoutPlan, *, actor, reason: str, version: int | None = None) -> PayoutPlan:
    """Отменить: начисления и уже сделанные выплаты не меняются; резерв
    остатков освобождается."""
    reason = _require_reason(reason)
    with transaction.atomic():
        plan = _locked_plan(plan, version)
        if plan.state == PayoutPlan.State.CANCELLED:
            raise AccountingError("План уже отменён.", code="bad_state")
        if totals(plan).status == PAID:
            raise AccountingError("План полностью выплачен — отменять нечего.", code="bad_state")
        old = {"state": plan.state}
        plan.state = PayoutPlan.State.CANCELLED
        plan.cancel_reason = reason
        plan.cancelled_by, plan.cancelled_at = actor, timezone.now()
        _bump(plan, ["state", "cancel_reason", "cancelled_by", "cancelled_at"])
        audit.log(actor, plan, "cancel", old=old, new={"state": plan.state}, reason=reason)
    return plan


def pay_line(line: PayoutPlanLine, *, actor, amount, payment_date: dt.date, payment_method: str,
             reference: str = "", comment: str = "", idempotency_key: str | None = None):
    """Зарегистрировать фактическую выплату по строке утверждённого плана —
    существующим механизмом выплат (проверка остатка начисления, блокировки,
    идемпотентность) и не больше остатка строки."""
    from .payment_service import register_payment

    amount = Decimal(amount)
    with transaction.atomic():
        plan = PayoutPlan.objects.select_for_update().get(pk=line.plan_id)
        line = PayoutPlanLine.objects.select_for_update().select_related("payroll").get(pk=line.pk)
        if idempotency_key and PayrollPayment.objects.filter(idempotency_key=idempotency_key).exists():
            existing = PayrollPayment.objects.get(idempotency_key=idempotency_key)
            if existing.payout_plan_line_id != line.pk:
                raise AccountingError("Ключ запроса уже использован для другой выплаты.", code="idempotency_conflict")
            return existing, False
        if plan.state != PayoutPlan.State.APPROVED:
            raise AccountingError("Выплаты по плану — только после его утверждения.", code="bad_state")
        if line.is_removed:
            raise AccountingError("Строка исключена из плана.", code="bad_state")
        remaining = line_remaining(line)
        if amount > remaining:
            raise AccountingError(f"По строке плана осталось выплатить {remaining} сом.", code="exceeds_plan")
        payment, created = register_payment(
            line.payroll, amount=amount, payment_date=payment_date, actor=actor, payment_method=payment_method,
            reference=reference, comment=comment or f"По плану выплат «{plan.title}»", idempotency_key=idempotency_key,
        )
        if created:
            PayrollPayment.objects.filter(pk=payment.pk).update(payout_plan_line=line)
            payment.payout_plan_line = line
            audit.log(actor, plan, "pay_line", new={"line": line.pk, "payment": payment.pk, "amount": amount,
                                                    "payment_date": payment_date}, payroll=line.payroll)
            plan.version += 1
            plan.save(update_fields=["version", "updated_at"])
    return payment, created


# ---------------------------------------------------------------------------
# Кандидаты, сводка, календарь
# ---------------------------------------------------------------------------

def candidates(*, year=None, month=None, employee=None, department=None) -> list[dict]:
    """Утверждённые начисления с остатком, который ещё не запланирован."""
    qs = Payroll.objects.filter(status__in=(Payroll.Status.APPROVED, Payroll.Status.PARTIALLY_PAID),
                                amount_due__gt=0).select_related("employee__salary_profile", "period")
    if year:
        qs = qs.filter(period__year=year)
    if month:
        qs = qs.filter(period__month=month)
    if employee:
        qs = qs.filter(employee_id=employee)
    rows = []
    for p in qs.order_by("period__start_date", "employee__last_name"):
        profile = getattr(p.employee, "salary_profile", None)
        dep = p.department or (profile.effective_department if profile else Department.OTHER)
        if department and dep != department:
            continue
        free = available(p)
        rows.append({
            "payroll": p.pk, "employee": p.employee_id, "employee_name": p.employee.get_full_name() or p.employee.username,
            "department": dep, "department_display": Department(dep).label, "period_label": period_label(p.period),
            "salary_type_display": p.get_salary_type_display(), "accrued": p.total_accrued + p.total_adjustments,
            "paid": p.total_paid, "due": p.amount_due, "reserved": p.amount_due - free, "available": free,
            "planned_payment_date": planned_date_for_period(p.period), "status_display": p.get_status_display(),
        })
    return rows


def filtered_plans(params: dict):
    qs = PayoutPlan.objects.select_related("created_by", "approved_by").prefetch_related("lines__payroll")
    if params.get("year"):
        qs = qs.filter(year=params["year"])
    if params.get("month"):
        qs = qs.filter(month=params["month"])
    if params.get("payout_date"):
        qs = qs.filter(payout_date=params["payout_date"])
    if params.get("date_from"):
        qs = qs.filter(payout_date__gte=params["date_from"])
    if params.get("date_to"):
        qs = qs.filter(payout_date__lte=params["date_to"])
    if params.get("employee"):
        qs = qs.filter(lines__payroll__employee_id=params["employee"], lines__is_removed=False).distinct()
    if params.get("department"):
        qs = qs.filter(lines__payroll__department=params["department"], lines__is_removed=False).distinct()
    plans = list(qs.order_by("payout_date", "id"))
    if params.get("status"):
        plans = [p for p in plans if totals(p).status == params["status"]]
    return plans


def summary(plans) -> dict:
    active = [p for p in plans if p.state != PayoutPlan.State.CANCELLED]
    agg = defaultdict(lambda: ZERO)
    employees = set()
    payroll_ids = set()
    for plan in active:
        t = totals(plan)
        agg["to_pay"] += t.remaining
        agg["planned"] += t.planned
        agg["prepared"] += plan.prepared_amount
        agg["deficit"] += t.deficit
        agg["paid"] += t.paid
        for line in plan.lines.filter(is_removed=False):
            employees.add(line.payroll.employee_id)
            payroll_ids.add(line.payroll_id)
    obligations = Payroll.objects.filter(pk__in=payroll_ids).aggregate(s=Sum("amount_due"))["s"] or ZERO
    return {
        "planned": agg["planned"], "to_pay": agg["to_pay"], "prepared": agg["prepared"], "deficit": agg["deficit"],
        "employees": len(employees), "paid": agg["paid"], "remaining_obligations": obligations,
        "plans": len(active),
        "readiness_percent": _readiness(agg["prepared"], agg["paid"] + agg["to_pay"], bool(payroll_ids)),
    }


def calendar(plans, *, year=None, month=None) -> dict:
    """Хронология выплат по датам + рекомендованные даты по правилам оплаты
    (15-е / 1-е следующего месяца для процента; календарь оклада) для
    утверждённых начислений, которые ещё не запланированы."""
    by_date: dict = defaultdict(lambda: {"to_pay": ZERO, "prepared": ZERO, "paid": ZERO, "deficit": ZERO,
                                         "employees": set(), "plans": []})
    for plan in plans:
        if plan.state == PayoutPlan.State.CANCELLED:
            continue
        t = totals(plan)
        day = by_date[plan.payout_date]
        day["to_pay"] += t.remaining
        day["prepared"] += plan.prepared_amount
        day["paid"] += t.paid
        day["deficit"] += t.deficit
        day["employees"] |= {line.payroll.employee_id for line in plan.lines.filter(is_removed=False)}
        day["plans"].append({"id": plan.pk, "title": plan.title, "status": t.status,
                             "status_display": STATUS_LABELS[t.status]})
    days = []
    for date in sorted(by_date):
        v = by_date[date]
        days.append({
            "date": date, "to_pay": v["to_pay"], "prepared": v["prepared"], "paid": v["paid"],
            "deficit": v["deficit"], "employees": len(v["employees"]),
            "readiness_percent": _readiness(v["prepared"], v["paid"] + v["to_pay"], bool(v["employees"])),
            "plans": v["plans"],
        })
    suggestions: dict = defaultdict(lambda: {"amount": ZERO, "employees": set(), "payrolls": 0})
    for row in candidates(year=year, month=month):
        if row["available"] <= 0:
            continue
        key = row["planned_payment_date"]
        s = suggestions[key]
        s["amount"] += row["available"]
        s["employees"].add(row["employee"])
        s["payrolls"] += 1
    return {
        "days": days,
        "suggestions": [
            {"date": k, "amount": v["amount"], "employees": len(v["employees"]), "payrolls": v["payrolls"],
             "rule": "по правилу выплаты (15-е / 1-е число)" if k else "календарь оклада не настроен — дату выбирает бухгалтер"}
            for k, v in sorted(suggestions.items(), key=lambda kv: (kv[0] is None, kv[0] or dt.date.max))
        ],
    }


def plan_lines(plan: PayoutPlan) -> list[dict]:
    lines = plan.lines.filter(is_removed=False).select_related(
        "payroll__employee__salary_profile", "payroll__period").prefetch_related("payroll__lines")
    return [explain_line(line) for line in lines.order_by("payroll__employee__last_name", "id")]


def plan_report(plan: PayoutPlan) -> dict:
    """Данные для выгрузки плана (Excel / PDF)."""
    return {"plan": plan, "totals": totals(plan).as_dict(), "lines": plan_lines(plan),
            "generated_at": timezone.localtime()}


def my_planned(user) -> list[dict]:
    """Сотруднику — только свои строки утверждённых планов, без чужих сумм и
    без подготовленного бюджета плана."""
    lines = PayoutPlanLine.objects.filter(
        payroll__employee=user, is_removed=False, plan__state=PayoutPlan.State.APPROVED,
    ).select_related("plan", "payroll__period").order_by("plan__payout_date", "id")
    rows = []
    for line in lines:
        paid = line_paid(line)
        rows.append({
            "payout_date": line.plan.payout_date, "period_label": period_label(line.payroll.period),
            "payroll": line.payroll_id, "planned_amount": line.planned_amount, "paid": paid,
            "remaining": line_remaining(line, paid=paid),
        })
    return rows
