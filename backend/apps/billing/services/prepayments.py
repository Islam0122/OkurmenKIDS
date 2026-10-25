"""Остаток предоплаты за обучение — один расчёт для карточки дашборда и
детализации по ученикам (только чтение).

Определения (одна сумма не попадает в два показателя):

* **Не распределено по счетам** (`unallocated`) — свободный аванс договора
  (журнал аванса: полученные платежи − возвраты − распределения − удержания;
  сторнированные платежи уже исключены), КРОМЕ депозита брони, который по
  условиям договора ещё не зачтён (бронь «в общую стоимость курса» — до
  начисления последнего месяца / «Весь курс»).
* **Уже распределено на будущие месяцы** (`allocated_future`) — оплаты,
  распределённые на начисления за ещё не начатые учебные месяцы: заранее
  выставленные месяцы / пакеты (PLANNED) и доля оплаченного начисления «Весь
  курс», относящаяся к ещё не начатым месяцам (по плану месяцев договора;
  без плана — равными долями, это отмечено как оценка).
* **Остаток предоплаты** (`prepayment`) = не распределено + распределено на
  будущие месяцы — деньги, полученные заранее и ещё не зачтённые в оплату
  пройденных / текущих учебных месяцев.

Статус ученика:

* «Полная предоплата» — остатка предоплаты хватает на всю оставшуюся
  стоимость обучения по договору (будущие месяцы + неоплаченный остаток);
* «Частичная предоплата» — есть, но не хватает;
* «Остаток аванса» — обязательств по договору не осталось (переплата) или у
  тарифа нет итоговой стоимости (пакеты без срока) — деньги просто не
  распределены;
* «Требует проверки» — договор закрыт, аванс лежит рядом с неоплаченным
  начислением, график не сходится с ценой договора или аванс отрицателен.
"""
from __future__ import annotations

from decimal import ROUND_DOWN, Decimal

from django.db.models import Q, Sum

from apps.accounting.models import StudentPayment
from apps.accounting.services.money import money

from ..models import (
    CreditLedgerEntry,
    Invoice,
    LessonPackage,
    PaymentAllocation,
    ReservationAllocation,
    StudentBillingProfile,
)
from .contracts import money_summary, payment_schedule

ZERO = Decimal("0.00")
CENT = Decimal("0.01")
FULL, PARTIAL, ADVANCE, REVIEW = "full", "partial", "advance", "review"
STATUS_LABEL = {FULL: "Полная предоплата", PARTIAL: "Частичная предоплата", ADVANCE: "Остаток аванса",
                REVIEW: "Требует проверки"}


def _held_reservation(profile, credit: Decimal) -> Decimal:
    """Депозит брони, который условия договора ещё не разрешают зачесть."""
    if not (profile.is_course and profile.reservation_allocation == ReservationAllocation.COURSE_TOTAL):
        return ZERO
    free = CreditLedgerEntry.objects.filter(
        profile=profile, payment__purpose=StudentPayment.Purpose.RESERVATION,
    ).aggregate(s=Sum("amount"))["s"] or ZERO
    has_target = Invoice.objects.filter(profile=profile, status__in=Invoice.UNPAID_STATUSES).filter(
        Q(kind=Invoice.Kind.COURSE) | Q(package__month_number=profile.duration_months)).exists()
    return ZERO if has_target else min(max(free, ZERO), max(credit, ZERO))


def _started_months(profile) -> int:
    return profile.packages.exclude(status=LessonPackage.Status.CANCELLED).filter(
        Q(lessons_used__gt=0) | Q(status=LessonPackage.Status.COMPLETED)).count()


def _allocated_future(profile) -> tuple[Decimal, bool]:
    """(сумма, точно?) — оплаты, распределённые на ещё не начатые месяцы."""
    planned = PaymentAllocation.objects.filter(
        profile=profile, status=PaymentAllocation.Status.ACTIVE,
        invoice__package__status=LessonPackage.Status.PLANNED, invoice__package__lessons_used=0,
    ).exclude(invoice__status=Invoice.Status.VOID).aggregate(s=Sum("amount"))["s"] or ZERO
    exact = True
    course = (Invoice.objects.filter(profile=profile, kind=Invoice.Kind.COURSE)
              .exclude(status=Invoice.Status.VOID).first())
    if course is not None and profile.duration_months:
        paid = course.amount_paid
        started = _started_months(profile)
        remaining_months = max(profile.duration_months - started, 0)
        rows = {r.month_number: r.amount for r in profile.month_prices.all()} if profile.month_plan_mode else {}
        if rows and sum(rows.values(), ZERO) == course.amount:
            future_cost = sum((a for m, a in rows.items() if m > started), ZERO)
        else:
            future_cost = (course.amount * remaining_months / profile.duration_months).quantize(CENT, ROUND_DOWN)
            exact = remaining_months in (0, profile.duration_months)
        # Оплаченная часть «Весь курс» сначала покрывает начатые месяцы.
        planned += max(min(paid - (course.amount - future_cost), future_cost), ZERO)
    return money(planned), exact


def _paid_months(profile) -> int:
    paid = Invoice.objects.filter(profile=profile, status=Invoice.Status.PAID).exclude(kind=Invoice.Kind.COURSE)
    months = paid.values("package_id").distinct().count()
    if Invoice.objects.filter(profile=profile, kind=Invoice.Kind.COURSE, status=Invoice.Status.PAID).exists():
        return profile.duration_months or months
    return months


def prepayment_row(profile: StudentBillingProfile) -> dict | None:
    s = money_summary(profile)
    credit = s["credit"]
    held = _held_reservation(profile, credit)
    unallocated = max(credit - held, ZERO)
    allocated_future, exact = _allocated_future(profile)
    prepayment = unallocated + allocated_future
    if prepayment <= 0 and credit >= 0:
        return None
    schedule = payment_schedule(profile)
    remaining = (s["invoices_balance"] + (s["future"] or ZERO) + allocated_future
                 if s["final_course_price"] is not None else None)
    reasons = []
    if profile.status in StudentBillingProfile.CLOSED_STATUSES:
        reasons.append(f"Договор «{profile.get_status_display()}» — решите возврат или перенос аванса.")
    if s["credit_unapplied"] > 0:
        reasons.append("Аванс не распределён на неоплаченные начисления этого договора.")
    if credit < 0:
        reasons.append("Отрицательный аванс — проверьте журнал.")
    if schedule is not None and not schedule["consistent"]:
        reasons.append("График начислений не сходится с ценой договора.")
    if reasons:
        status = REVIEW
    elif remaining is None or remaining <= 0:
        status = ADVANCE
    elif prepayment >= remaining:
        status = FULL
    else:
        status = PARTIAL
    next_month = None
    if schedule is not None:
        covered = next((m for m in schedule["months"] if m["state"] == "future" and m["covered_by_credit"] > 0), None)
        next_month = covered["month_number"] if covered else None
    student = profile.student
    return {
        "profile": profile.pk, "student": student.pk, "student_name": str(student),
        "program": profile.plan.course.name if profile.plan.course_id else profile.plan.name,
        "program_id": profile.plan.course_id, "plan": profile.plan.name,
        "group": student.group.name if student.group_id else None, "group_id": student.group_id,
        "contract_status": profile.status, "payment_mode": profile.payment_mode,
        "contract_total": s["final_course_price"], "received": s["net_received"],
        "applied_to_studied": max(s["allocated"] - allocated_future, ZERO),
        "allocated_future": allocated_future, "allocated_future_exact": exact,
        "unallocated": unallocated, "reservation_held": held, "prepayment": max(prepayment, ZERO),
        "remaining_obligations": remaining, "paid_months": _paid_months(profile),
        "duration_months": profile.duration_months, "next_covered_month": next_month,
        "status": status, "status_display": STATUS_LABEL[status], "review_reasons": reasons,
    }


def prepayments(filters: dict | None = None) -> dict:
    """Строки по ученикам и итоги. Итог «Остаток предоплаты» = Σ строк —
    тот же расчёт, что у карточки дашборда."""
    from .reports import filter_profiles

    f = filters or {}
    with_credit = CreditLedgerEntry.objects.values("profile").annotate(s=Sum("amount")).exclude(s=0).values("profile")
    future_alloc = PaymentAllocation.objects.filter(status=PaymentAllocation.Status.ACTIVE).filter(
        Q(invoice__package__status=LessonPackage.Status.PLANNED) | Q(invoice__kind=Invoice.Kind.COURSE),
    ).values("profile")
    qs = StudentBillingProfile.objects.filter(Q(pk__in=with_credit) | Q(pk__in=future_alloc)).select_related(
        "student__group", "plan__course").prefetch_related("month_prices")
    qs = filter_profiles(qs, f)
    if f.get("program"):
        qs = qs.filter(plan__course_id=f["program"])
    rows = [row for row in (prepayment_row(p) for p in qs.order_by("student__last_name", "student__first_name"))
            if row is not None]
    if f.get("status"):
        rows = [r for r in rows if r["status"] == f["status"]]
    for part in (f.get("search") or "").lower().split():
        rows = [r for r in rows if part in r["student_name"].lower()]
    total = sum((r["prepayment"] for r in rows), ZERO)
    summary = {
        "prepayment": money(total),
        "students": len(rows),
        "full": sum(1 for r in rows if r["status"] == FULL),
        "partial": sum(1 for r in rows if r["status"] == PARTIAL),
        "advance": sum(1 for r in rows if r["status"] == ADVANCE),
        "review": sum(1 for r in rows if r["status"] == REVIEW),
        "allocated_future": money(sum((r["allocated_future"] for r in rows), ZERO)),
        "unallocated": money(sum((r["unallocated"] for r in rows), ZERO)),
        "reservation_held": money(sum((r["reservation_held"] for r in rows), ZERO)),
        "definitions": {
            "prepayment": "Деньги, полученные от родителей заранее и ещё не зачтённые в оплату пройденных и "
                          "текущих учебных месяцев: = «распределено на будущие месяцы» + «не распределено по счетам».",
            "allocated_future": "Оплаты, уже распределённые на начисления за ещё не начатые месяцы (заранее "
                                "выставленные месяцы и доля начисления «Весь курс»).",
            "unallocated": "Свободный аванс: деньги получены, но ещё не распределены ни на одно начисление "
                           "(без сторнированных платежей, возвратов и не зачтённого депозита брони).",
            "reservation_held": "Депозит брони «в общую стоимость курса», который по договору ещё не зачтён — "
                                "в остаток предоплаты не входит.",
            "full": "Остатка хватает на всю оставшуюся стоимость обучения по договору.",
            "partial": "Предоплата есть, но меньше оставшейся стоимости обучения.",
        },
    }
    return {"summary": summary, "results": [_json(r) for r in rows]}


def _json(row: dict) -> dict:
    return {k: (str(v) if isinstance(v, Decimal) else v) for k, v in row.items()}


__all__ = ["FULL", "PARTIAL", "ADVANCE", "REVIEW", "prepayment_row", "prepayments"]
