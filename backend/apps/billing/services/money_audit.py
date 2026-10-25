"""Аудит денег договора: все связанные записи, их связи и несогласованности
(только чтение, кроме `apply_safe_fixes`).

Проверяется, чем на самом деле является каждая сумма: подтверждённое
поступление или возврат, какому договору принадлежит платёж, на какие
начисления распределён, что осталось авансом, к какой операции выдан чек.
Автоматически исправляется только одно — свободный аванс рядом с
неоплаченным начислением того же договора: деньги распределяются обычной
корректирующей операцией (`PaymentAllocation`, журнал аванса, аудит) под
блокировкой договора. Платежи, чеки и начисления не удаляются и не
переписываются; всё остальное — список для ручной проверки.
"""
from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

from django.db.models import Count, Q, Sum

from apps.accounting.models import StudentPayment
from apps.accounting.services.money import money

from ..models import CreditLedgerEntry, Invoice, PaymentAllocation, PaymentMode, Receipt, StudentBillingProfile
from .contracts import invoiced_total, money_summary, payment_schedule
from .invoices import calculate_invoice_balance
from .payment_chain import chain, unlinked_replacements

ZERO = Decimal("0.00")
D = Decimal


def _s(value) -> str:
    return str(money(value if value is not None else ZERO))


def find_profiles(*, profile_id: int | None = None, student: str | None = None,
                  receipts: list[str] | None = None, invoices: list[str] | None = None):
    """Договоры по id, части имени студента, номерам чеков или начислений.
    Номер найден — в выборку попадают ВСЕ договоры этого студента (платёж по
    старому договору и начисление по новому — тоже)."""
    qs = StudentBillingProfile.objects.select_related("student", "plan").order_by("pk")
    if profile_id:
        qs = qs.filter(pk=profile_id)
    for part in (student or "").split():
        qs = qs.filter(Q(student__first_name__icontains=part) | Q(student__last_name__icontains=part))
    if receipts or invoices:
        students = set(Receipt.objects.filter(number__in=receipts or []).values_list("profile__student_id", flat=True))
        students |= set(Invoice.objects.filter(number__in=invoices or []).values_list("profile__student_id", flat=True))
        qs = qs.filter(student_id__in=students)
    return qs


def lookup_numbers(*, receipts: list[str] | None = None, invoices: list[str] | None = None) -> dict:
    """Что на самом деле стоит за номерами: чек → платёж → распределения;
    начисление → пакет, оплаты, корректировки, аннулирование."""
    result = {"receipts": [], "invoices": [], "not_found": []}
    for number in receipts or []:
        receipt = Receipt.objects.select_related("payment", "profile__student").filter(number=number).first()
        if receipt is None:
            result["not_found"].append(number)
            continue
        p = receipt.payment
        result["receipts"].append({
            "receipt": receipt.pk, "number": receipt.number, "status": receipt.status, "kind": receipt.kind,
            "issued_at": receipt.issued_at.isoformat(), "print_count": receipt.print_count,
            "snapshot_amount": receipt.snapshot.get("amount"), "snapshot_purpose_lines": receipt.snapshot.get("purpose_lines"),
            "profile": receipt.profile_id, "student": str(receipt.profile.student),
            "payment": {
                "id": p.pk, "kind": p.kind, "purpose": p.purpose, "status": p.status, "amount": _s(p.amount),
                "received_date": p.received_date.isoformat(), "created_at": p.created_at.isoformat(),
                "created_by": str(p.created_by), "method": p.method, "reference": p.reference,
                "has_idempotency_key": bool(p.idempotency_key), "billing_profile": p.billing_profile_id,
                "void_reason": p.void_reason, "refund_of": p.refund_of_id,
            },
            "allocations": _allocations(PaymentAllocation.objects.filter(payment=p)),
        })
    for number in invoices or []:
        inv = Invoice.objects.select_related("package", "profile__student").filter(number=number).first()
        if inv is None:
            result["not_found"].append(number)
            continue
        result["invoices"].append({
            **_invoice_row(inv), "profile": inv.profile_id, "student": str(inv.profile.student),
            "allocations": _allocations(PaymentAllocation.objects.filter(invoice=inv)),
        })
    return result


def _allocations(qs) -> list[dict]:
    return [{
        "allocation": a.pk, "payment": a.payment_id, "invoice": a.invoice.number, "amount": _s(a.amount),
        "source": a.source, "status": a.status, "created_at": a.created_at.isoformat(),
        "reversed_at": a.reversed_at.isoformat() if a.reversed_at else None, "reverse_reason": a.reverse_reason,
    } for a in qs.select_related("invoice").order_by("pk")]


def _invoice_row(inv: Invoice) -> dict:
    sums = calculate_invoice_balance(inv)
    return {
        "invoice": inv.pk, "number": inv.number, "kind": inv.kind, "month_number": inv.package.month_number,
        "package": inv.package_id, "amount": _s(inv.amount), "paid": _s(sums["paid"]),
        "adjusted": _s(sums["adjusted"]), "balance": _s(sums["balance"]), "status": inv.status,
        "period_date": inv.period_date.isoformat(), "issue_date": inv.issue_date.isoformat(),
        "created_at": inv.created_at.isoformat(), "void_reason": inv.void_reason,
        # Откуда «Ожидалось»: срок в уроках — дата зачтённого урока-срока
        # (`due_reached_on`), срок по дате — `due_date` (analytics.due_in).
        "due_lesson": inv.due_lesson, "due_date": inv.due_date.isoformat(),
        "due_reached_on": inv.due_reached_on.isoformat() if inv.due_reached_on else None,
        "overdue_since": inv.overdue_since.isoformat() if inv.overdue_since else None,
    }


def profile_money_audit(profile: StudentBillingProfile) -> dict:
    from .lessons import lesson_breakdown

    summary = money_summary(profile)
    payments = list(StudentPayment.objects.filter(billing_profile=profile).order_by("received_date", "pk"))
    receipts = {r.payment_id: r for r in Receipt.objects.filter(payment__in=payments)}
    allocated = defaultdict(lambda: ZERO)
    for row in PaymentAllocation.objects.filter(payment__in=payments, status=PaymentAllocation.Status.ACTIVE) \
            .values("payment_id").annotate(s=Sum("amount")):
        allocated[row["payment_id"]] = row["s"]
    problems = []

    payment_rows = []
    seen = defaultdict(list)
    for p in payments:
        receipt = receipts.get(p.pk)
        row = {
            "payment": p.pk, "kind": p.kind, "purpose": p.purpose, "status": p.status, "amount": _s(p.amount),
            "received_date": p.received_date.isoformat(), "created_at": p.created_at.isoformat(),
            "before_contract_start": p.received_date < profile.start_date,
            "method": p.method, "reference": p.reference, "created_by": str(p.created_by),
            "has_idempotency_key": bool(p.idempotency_key), "void_reason": p.void_reason,
            "voided_at": p.voided_at.isoformat() if p.voided_at else None,
            "voided_by": str(p.voided_by) if p.voided_by_id else None, **chain(p),
            "allocated": _s(allocated[p.pk]) if p.kind == StudentPayment.Kind.PAYMENT else None,
            "unallocated": _s(p.amount - allocated[p.pk]) if p.kind == StudentPayment.Kind.PAYMENT
            and p.status == StudentPayment.Status.CONFIRMED else None,
            "receipt": None if receipt is None else {
                "number": receipt.number, "status": receipt.status, "snapshot_amount": receipt.snapshot.get("amount"),
            },
        }
        payment_rows.append(row)
        if receipt is None:
            problems.append({"type": "receipt_missing", "payment": p.pk, "fix": "manual"})
        else:
            if receipt.profile_id != profile.pk:
                problems.append({"type": "receipt_other_contract", "payment": p.pk, "receipt": receipt.number,
                                 "fix": "manual"})
            amount = receipt.snapshot.get("amount")
            if amount is not None and Decimal(str(amount)) != p.amount:
                problems.append({"type": "receipt_amount_mismatch", "payment": p.pk, "receipt": receipt.number,
                                 "receipt_amount": amount, "payment_amount": _s(p.amount), "fix": "manual"})
            if (receipt.status == Receipt.Status.CANCELLED) != (p.status == StudentPayment.Status.VOID):
                problems.append({"type": "receipt_status_mismatch", "payment": p.pk, "receipt": receipt.number,
                                 "fix": "manual"})
        if p.status == StudentPayment.Status.CONFIRMED and p.kind == StudentPayment.Kind.PAYMENT:
            seen[(p.amount, p.received_date, p.method)].append(p.pk)
    for (amount, day, _method), ids in seen.items():
        if len(ids) > 1:
            problems.append({"type": "possible_duplicate_payment", "payments": ids, "amount": _s(amount),
                             "received_date": day.isoformat(), "fix": "manual"})
    # Одинаковые суммы в разные дни (в том числе по другому договору этого
    # студента): может быть повторная регистрация одних и тех же денег, а может
    # — два реальных поступления. Автоматически не объединяется: решает
    # бухгалтер по кассе / выписке; дубль сторнируется `reverse_payment`.
    same_amount = StudentPayment.objects.filter(
        student_id=profile.student_id, billing_profile__isnull=False, kind=StudentPayment.Kind.PAYMENT,
        status=StudentPayment.Status.CONFIRMED,
    ).values("amount").annotate(n=Count("pk")).filter(n__gt=1)
    for row in same_amount:
        ids = list(StudentPayment.objects.filter(
            student_id=profile.student_id, billing_profile__isnull=False, kind=StudentPayment.Kind.PAYMENT,
            status=StudentPayment.Status.CONFIRMED, amount=row["amount"],
        ).order_by("received_date", "pk").values_list("pk", flat=True))
        if not any(set(ids) == set(p.get("payments", [])) for p in problems):
            problems.append({
                "type": "same_amount_payments", "payments": ids, "amount": _s(row["amount"]), "fix": "confirm",
                "detail": "Сверьте с кассой / выпиской: если деньги получены один раз — сторно лишнего платежа "
                          "(billing_money_audit --reverse-payment ID --reason … --confirm); если дважды — оба "
                          "остаются, лишняя сумма — аванс или возврат.",
            })

    invoice_rows = []
    live = Invoice.objects.filter(profile=profile).exclude(status=Invoice.Status.VOID).select_related("package")
    for inv in Invoice.objects.filter(profile=profile).select_related("package").order_by("package__number", "pk"):
        row = _invoice_row(inv)  # аннулированные тоже — видно, какое начисление чем заменено
        invoice_rows.append(row)
        if inv.status != Invoice.Status.VOID and (D(row["paid"]) != inv.amount_paid
                                                  or D(row["adjusted"]) != inv.amount_adjusted):
            problems.append({"type": "invoice_cache", "invoice": inv.pk, "fix": "manual"})
    if profile.final_course_price is not None and invoiced_total(profile) > profile.final_course_price:
        problems.append({"type": "course_overinvoiced", "invoiced": _s(invoiced_total(profile)),
                         "final_course_price": _s(profile.final_course_price), "fix": "manual"})
    if profile.payment_mode == PaymentMode.FULL_PREPAY and live.filter(kind=Invoice.Kind.COURSE).exists() \
            and live.filter(kind=Invoice.Kind.MONTH, amount__gt=0).exists():
        problems.append({"type": "prepay_with_month_invoices", "fix": "manual"})
    if summary["credit_unapplied"] > 0:
        problems.append({"type": "credit_unapplied", "amount": _s(summary["credit_unapplied"]),
                         "detail": "Свободный аванс и неоплаченное начисление одного договора — платёж не распределён.",
                         "fix": "apply_credit"})
    for reservation in profile.reservations.filter(payment__isnull=False).select_related("payment"):
        paid = reservation.payment
        if paid.status == StudentPayment.Status.CONFIRMED and paid.amount > reservation.expected_amount:
            problems.append({
                "type": "reservation_paid_over_expected", "reservation": reservation.pk, "payment": paid.pk,
                "expected": _s(reservation.expected_amount), "paid": _s(paid.amount), "fix": "confirm",
                "detail": "Через «Оплату брони» принято больше суммы брони — возможно, это оплата обучения. "
                          "Бронь — тот же платёж, деньги не считаются дважды. Если это оплата обучения, "
                          "измените назначение платежа (payments/{id}/correct/ purpose=tuition|prepayment).",
            })
    for row in unlinked_replacements(profile):
        problems.append({
            "type": "unlinked_replacement", **row, "fix": "confirm",
            "detail": "Сторнированный платёж и внесённые после него платежи на ту же сумму без связи: проверьте, "
                      "что это те же деньги, и свяжите (billing_money_audit --link ИСХОДНЫЙ --replacements A,B "
                      "--reason … --confirm). Суммы уже не дублируются — исходный в «получено» не входит.",
        })
    schedule = payment_schedule(profile)
    if schedule is not None and not schedule["consistent"]:
        problems.append({"type": "schedule_mismatch", "issues": schedule["issues"], "fix": "manual"})
    if summary["credit"] < 0:
        problems.append({"type": "negative_credit", "fix": "manual"})

    lessons = lesson_breakdown(profile)
    before = lessons["priority_before_contract"]
    if before["count"]:
        problems.append({"type": "priority_lessons_before_start", "count": before["count"],
                         "first_date": before["first_date"], "contract_start": profile.start_date.isoformat(),
                         "detail": "Если дата начала указана ошибочно — POST profiles/{id}/start-date/ с основанием.",
                         "fix": "manual"})
    return {
        "profile": profile.pk, "student": str(profile.student), "plan": profile.plan.name, "status": profile.status,
        "payment_mode": profile.payment_mode, "start_date": profile.start_date.isoformat(),
        "created_at": profile.created_at.isoformat(),
        "summary": {k: (str(v) if isinstance(v, Decimal) else v) for k, v in summary.items()},
        "payments": payment_rows, "invoices": invoice_rows,
        "allocations": _allocations(PaymentAllocation.objects.filter(profile=profile)),
        "ledger": [{"id": e.pk, "kind": e.kind, "amount": _s(e.amount), "payment": e.payment_id,
                    "allocation": e.allocation_id, "created_at": e.created_at.isoformat(), "comment": e.comment}
                   for e in CreditLedgerEntry.objects.filter(profile=profile).order_by("pk")],
        "lessons": {"attended": lessons["attended"], "counted": lessons["counted"], "totals": lessons["totals"],
                    "priority_before_contract": before},
        "problems": problems,
    }


def apply_safe_fixes(profile: StudentBillingProfile, *, actor=None) -> list[dict]:
    """Распределить свободный аванс на неоплаченные начисления договора —
    по тем же правилам, что и при поступлении (порядок месяцев, бронь
    «в общую стоимость» — только на последний месяц). Идемпотентно."""
    from .payments import apply_available_credit

    allocations = apply_available_credit(profile, actor=actor, system=actor is None)
    return [{"allocation": a.pk, "payment": a.payment_id, "invoice": a.invoice_id, "amount": _s(a.amount)}
            for a in allocations]
