"""«Оплата» in the Student & Parent Portal — a read-only view of the
accounting records of ONE student (already authorised by services.scope and
by PortalAccount.can_view_payments).

Nothing is computed or stored a second time here:

* contract money (price, paid, debt, due now) — billing's own summary,
  `billing.services.archive.student_finance` / `profile_totals`
  (→ `contracts.money_summary`);
* how urgent an invoice is — `billing.services.contracts.payment_stage`, the
  same function the accountant's «Скоро оплата / К оплате / Просроченные»
  queues use;
* transactions — `accounting.StudentPayment` (payments and refunds, voided
  ones marked as cancelled), whoever registered them;
* receipts — the `billing.Receipt` the accounting system issued for a
  payment in the same transaction (internal Okurmen Kids receipts, number
  `OK-ГГГГ-NNNNNN`, NOT fiscal documents). Their PDF is the accounting
  system's own `render_receipt_pdf`. A payment without a receipt is shown as
  a payment record, never with an invented number;
* invoices («начисления») are records only — the accounting system does not
  produce an invoice document, so none is pretended here.

The family reads; it never changes anything. Even opening a receipt PDF does
not touch the receipt's print counter or audit trail — those stay the
accountant's (`receipts.mark_printed`).
"""
from __future__ import annotations

import datetime as dt
from decimal import Decimal

from django.http import Http404

from apps.academy.models import Student

ZERO = Decimal("0")
OPEN_STAGES = ("overdue", "deadline", "awaiting")
_STAGE_ORDER = {"overdue": 0, "deadline": 1, "awaiting": 2}

# Transaction filter → which StudentPayment rows.
TRANSACTION_FILTERS = ("all", "completed", "refunded", "cancelled")


def _s(value) -> str | None:
    return None if value is None else str(value)


def _person(user) -> str:
    if user is None:
        return ""
    return user.get_full_name() or user.username


def _profiles(student: Student):
    from apps.billing.models import StudentBillingProfile

    return list(
        StudentBillingProfile.objects.filter(student=student)
        .select_related("subject", "plan__course")
        .order_by("start_date", "pk")
    )


def _course_name(profile) -> str:
    plan = profile.plan
    return plan.course.name if getattr(plan, "course_id", None) else plan.name


# ---------------------------------------------------------------------------
# Invoices (начисления)
# ---------------------------------------------------------------------------

def _invoice_row(invoice, today: dt.date) -> dict:
    from apps.billing.services.contracts import payment_stage

    stage = payment_stage(invoice, on=today)
    package = invoice.package
    return {
        "id": invoice.pk,
        "number": invoice.number,
        "kind": invoice.kind,
        "month_number": getattr(package, "month_number", None),
        "package_number": getattr(package, "number", None),
        "course": _course_name(invoice.profile),
        "subject": invoice.profile.subject.name if invoice.profile.subject_id else None,
        "issue_date": invoice.issue_date,
        "period_date": invoice.period_date,
        "due_date": invoice.due_date,
        # A due date counted in lessons (the invoice is due at its Nth lesson).
        "due_lesson": invoice.due_lesson,
        "lessons_used": getattr(package, "lessons_used", None) if invoice.due_lesson else None,
        "amount": _s(invoice.amount),
        "paid": _s(invoice.amount_paid),
        "adjusted": _s(invoice.amount_adjusted),
        "balance": _s(invoice.balance),
        "status": invoice.status,
        "stage": stage,  # awaiting | deadline | overdue | paid
        "overdue_since": invoice.overdue_since,
        "paid_at": invoice.paid_at,
    }


def _invoices(profiles, today: dt.date) -> list[dict]:
    from apps.billing.models import Invoice

    qs = (
        Invoice.objects.filter(profile__in=profiles)
        .exclude(status__in=(Invoice.Status.DRAFT, Invoice.Status.VOID))
        .select_related("package", "profile__plan__course", "profile__subject")
        .order_by("due_date", "pk")
    )
    return [_invoice_row(i, today) for i in qs]


# ---------------------------------------------------------------------------
# Overview
# ---------------------------------------------------------------------------

def overview(student: Student, *, today: dt.date) -> dict:
    from apps.billing.services.archive import profile_totals, student_finance

    profiles = _profiles(student)
    invoices = _invoices(profiles, today)
    open_invoices = sorted(
        (i for i in invoices if i["stage"] in OPEN_STAGES),
        key=lambda i: (_STAGE_ORDER[i["stage"]], i["due_date"], i["id"]),
    )
    summary = student_finance(student, profiles) if profiles else None

    percent = None
    if summary is not None:
        paid = Decimal(summary["paid"])
        base = Decimal(summary["contract_price"]) if summary["contract_price"] is not None else Decimal(summary["invoiced"])
        percent = min(100, round(paid / base * 100)) if base > 0 else None

    if summary is None:
        status = "no_contract"
    elif any(i["stage"] == "overdue" for i in open_invoices):
        status = "overdue"
    elif any(i["stage"] == "deadline" for i in open_invoices):
        status = "due"
    elif open_invoices:
        status = "upcoming"
    else:
        status = "paid"

    return {
        "status": status,
        "summary": summary,
        "percent_paid": percent,
        "next_payment": open_invoices[0] if open_invoices else None,
        "open_invoices": open_invoices,
        "contracts": [
            {
                "id": p.pk,
                "course": _course_name(p),
                "subject": p.subject.name if p.subject_id else None,
                "plan": p.plan.name,
                "status": p.status,
                "start_date": p.start_date,
                **{key: _s(value) for key, value in profile_totals(p).items()},
            }
            for p in profiles
        ],
        "currency": "KGS",
    }


# ---------------------------------------------------------------------------
# Transactions
# ---------------------------------------------------------------------------

def _receipt_ref(receipt) -> dict | None:
    if receipt is None:
        return None
    return {"id": receipt.pk, "number": receipt.number, "status": receipt.status}


def transactions(student: Student, *, status: str = "all") -> list[dict]:
    from apps.accounting.models import StudentPayment

    qs = (
        StudentPayment.objects.filter(student=student)
        .select_related("course", "group__course", "billing_profile__plan__course", "created_by", "receipt")
        .order_by("-received_date", "-pk")
    )
    if status == "completed":
        qs = qs.filter(status=StudentPayment.Status.CONFIRMED, kind=StudentPayment.Kind.PAYMENT)
    elif status == "refunded":
        qs = qs.filter(status=StudentPayment.Status.CONFIRMED, kind=StudentPayment.Kind.REFUND)
    elif status == "cancelled":
        qs = qs.filter(status=StudentPayment.Status.VOID)
    rows = []
    for p in qs:
        receipt = getattr(p, "receipt", None)
        if p.course_id:
            course = p.course.name
        elif p.billing_profile_id:
            course = _course_name(p.billing_profile)
        elif p.group_id and p.group.course_id:
            course = p.group.course.name
        else:
            course = None
        rows.append({
            "id": p.pk,
            "date": p.received_date,
            "kind": p.kind,  # payment | refund
            "status": "cancelled" if p.status == StudentPayment.Status.VOID else
                      ("refunded" if p.kind == StudentPayment.Kind.REFUND else "completed"),
            "amount": _s(p.amount),
            "currency": p.currency,
            "course": course,
            "method": p.method,
            "reference": p.reference,
            "purpose": p.purpose,
            "service_start": p.service_start,
            "service_end": p.service_end,
            "cashier": (receipt.snapshot or {}).get("staff") if receipt else _person(p.created_by),
            "receipt": _receipt_ref(receipt),
        })
    return rows


# ---------------------------------------------------------------------------
# Receipts & documents
# ---------------------------------------------------------------------------

def _receipts_qs(student: Student):
    from apps.billing.models import Receipt

    # A receipt belongs to the student of its payment (and of its contract).
    return (
        Receipt.objects.filter(payment__student=student, profile__student=student)
        .select_related("payment", "issued_by")
        .order_by("-issued_at", "-pk")
    )


def receipt_row(receipt, *, full: bool = False) -> dict:
    snap = receipt.snapshot or {}
    row = {
        "id": receipt.pk,
        "number": receipt.number,
        "kind": receipt.kind,  # PAYMENT | REFUND
        "status": receipt.status,  # ISSUED | CANCELLED
        "issued_at": receipt.issued_at,
        "received_date": snap.get("received_date") or receipt.payment.received_date,
        "amount": snap.get("amount") or _s(receipt.payment.amount),
        "currency": snap.get("currency") or "KGS",
        "student": snap.get("student") or "",
        "course": snap.get("program") or "",
        "group": snap.get("group") or "",
        "method": snap.get("method") or receipt.payment.method,
        "reference": snap.get("reference") or receipt.payment.reference,
        "cashier": snap.get("staff") or _person(receipt.issued_by),
        "cancelled_at": receipt.cancelled_at,
    }
    if full:
        row.update({
            "payer": receipt.payer_name or snap.get("payer") or "",
            "purpose": snap.get("purpose") or "",
            "purpose_lines": snap.get("purpose_lines") or [],
            "previously_paid": snap.get("previously_paid"),
            "outstanding": snap.get("outstanding"),
            "credit": snap.get("credit"),
            # A receipt issued afterwards for an older payment has no balances of its own.
            "has_balances": not snap.get("backfilled"),
        })
    return row


def documents(student: Student, *, today: dt.date) -> dict:
    """«Документы и чеки»: the receipts the accounting system issued (with
    their PDF) and the invoices (records — no invoice document exists)."""
    return {
        "receipts": [receipt_row(r) for r in _receipts_qs(student)],
        "invoices": list(reversed(_invoices(_profiles(student), today))),
    }


def get_receipt(student: Student, receipt_id):
    try:
        receipt_id = int(receipt_id)
    except (TypeError, ValueError):
        raise Http404
    receipt = _receipts_qs(student).filter(pk=receipt_id).first()
    if receipt is None:
        raise Http404
    return receipt


def receipt_pdf(receipt, *, compact: bool = False) -> bytes:
    """The accounting system's own receipt document — rendered, not copied."""
    from apps.billing.services.receipt_pdf import render_receipt_pdf

    return render_receipt_pdf(receipt, compact=compact)
