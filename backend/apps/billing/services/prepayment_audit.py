"""Разбор строки «Остатка предоплаты» до исходных записей (только чтение).

Для бухгалтерской проверки конкретных договоров (случаи вида «получено
91 000 при договоре 53 000»): откуда каждая сумма строки, какие платежи,
возвраты, сторно, распределения и записи журнала аванса за ней стоят, и какие
признаки ошибки видны. Ничего не меняет; расчёт строки — тот же
`prepayments.prepayment_row`.
"""
from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

from django.db.models import Sum

from apps.accounting.models import StudentPayment
from apps.accounting.services.money import money

from ..models import CreditLedgerEntry, Invoice, PaymentAllocation, StudentBillingProfile
from .contracts import course_coverage, money_summary
from .prepayments import prepayment_row

ZERO = Decimal("0.00")


def _s(value):
    return str(money(value)) if isinstance(value, Decimal) else value


def explain(profile: StudentBillingProfile) -> dict:
    s = money_summary(profile)
    row = prepayment_row(profile)
    payments = [{
        "id": p.pk, "received_date": p.received_date.isoformat(), "kind": p.kind, "purpose": p.purpose or "",
        "status": p.status, "amount": _s(p.amount), "refund_of": p.refund_of_id,
        "unallocated": _s(CreditLedgerEntry.objects.filter(payment=p).aggregate(x=Sum("amount"))["x"] or ZERO),
    } for p in StudentPayment.objects.filter(billing_profile=profile).order_by("received_date", "pk")]
    invoices = []
    for inv in Invoice.objects.filter(profile=profile).select_related("package").order_by("package__number", "pk"):
        alloc = PaymentAllocation.objects.filter(invoice=inv)
        invoices.append({
            "number": inv.number, "kind": inv.kind, "status": inv.status,
            "month": inv.package.month_number if inv.package_id else None,
            "package_status": inv.package.status if inv.package_id else None,
            "lessons_used": inv.package.lessons_used if inv.package_id else None,
            "amount": _s(inv.amount), "paid_active": _s(alloc.filter(status=PaymentAllocation.Status.ACTIVE)
                                                       .aggregate(x=Sum("amount"))["x"] or ZERO),
            "paid_reversed": _s(alloc.exclude(status=PaymentAllocation.Status.ACTIVE).aggregate(x=Sum("amount"))["x"]
                                or ZERO),
            "adjusted": _s(inv.amount_adjusted),
        })
    ledger = defaultdict(lambda: ZERO)
    for e in CreditLedgerEntry.objects.filter(profile=profile):
        ledger[e.kind] += e.amount
    retention = -ledger.get(CreditLedgerEntry.Kind.RETENTION, ZERO)
    coverage = course_coverage(profile)
    findings = []
    if s["credit"] != s["net_received"] - s["allocated"] - retention:
        findings.append("Журнал аванса не сходится с платежами и распределениями.")
    if s["credit_unreserved"] > 0 and s["final_course_price"] is not None:
        findings.append(f"Деньги сверх оставшейся стоимости договора: {_s(s['credit_unreserved'])} "
                        "(переплата или депозит, который нечем зачесть).")
    if row and row["reservation_held"] > 0 and s["future"] == 0 and s["invoices_balance"] == 0:
        findings.append("Депозит брони числится «не зачтённым», но неоплаченных начислений и будущих месяцев "
                        "нет — зачесть его не во что: нужен возврат / перенос.")
    if coverage is not None and row is not None:
        covered = sum(1 for m in coverage["months"].values() if m["paid"] == m["share"])
        if covered != row["paid_months"]:
            findings.append(f"«Оплачено месяцев» {row['paid_months']}, а по графику «Весь курс» закрыто {covered}.")
    others = [{
        "profile": o.pk, "plan": o.plan.name, "status": o.status,
        "received": _s(money_summary(o)["net_received"]),
    } for o in StudentBillingProfile.objects.filter(student=profile.student).exclude(pk=profile.pk).select_related("plan")]
    return {
        "profile": profile.pk, "student": str(profile.student), "plan": profile.plan.name,
        "contract": {"status": profile.status, "payment_mode": profile.payment_mode,
                     "duration_months": profile.duration_months,
                     "standard_course_price": _s(s.get("standard_course_price")),
                     "final_course_price": _s(s.get("final_course_price")), "month_plan_mode": profile.month_plan_mode,
                     "reservation_allocation": profile.reservation_allocation},
        "row": None if row is None else {k: _s(v) for k, v in row.items()},
        "summary": {k: _s(s[k]) for k in ("received", "refunded", "net_received", "voided", "allocated", "adjusted",
                                          "credit", "invoiced", "invoices_balance", "due_now", "future",
                                          "credit_unapplied", "credit_reserved_future", "credit_unreserved",
                                          "reservation_unused", "course_paid_in_full")},
        "ledger": {k: _s(v) for k, v in sorted(ledger.items())},
        "payments": payments, "invoices": invoices, "other_contracts": others, "findings": findings,
    }
