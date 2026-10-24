"""Финансовая аналитика оплаты обучения за период (только чтение).

Два независимых показателя — не смешиваются:

* **Фактически получено** — реальные деньги по дате поступления
  (`StudentPayment.received_date`): валовые поступления = подтверждённые
  платежи (отменённые / сторнированные не входят); возвраты — отдельно по
  дате возврата; чистый денежный поток = валовые − возвраты.
* **Ожидалось получить** — начисления, срок оплаты которых наступил в
  периоде, оплачены они или нет: срок в уроках — дата зачтённого урока-
  дедлайна (`Invoice.due_reached_on`), срок по дате — `due_date`.

Скидка — не поступление (показывается отдельно как сумма предоставленных
скидок по договорам, оформленным в периоде). Неоплаченное начисление — не
полученные деньги. Задолженность на конец периода — по начислениям со
сроком до конца периода минус оплаты деньгами, полученными до этой даты
(по дате поступления, а не по дате записи), и корректировки с датой до неё —
то есть «как было», а не «как сейчас». Период начисления
(`Invoice.period_date`) и разбивка поступлений по периодам — `periods.py`.
"""
from __future__ import annotations

import datetime as dt
from decimal import Decimal

from django.db.models import Count, F, Q, Sum
from django.db.models.functions import Coalesce

from apps.accounting.models import StudentPayment
from apps.accounting.services.money import money

from ..models import Invoice, InvoiceAdjustment, LessonPackage, PaymentAllocation, PaymentMode, StudentBillingProfile

ZERO = Decimal("0.00")
LIVE = (Invoice.Status.OPEN, Invoice.Status.PARTIALLY_PAID, Invoice.Status.OVERDUE, Invoice.Status.PAID)


def _s(value) -> str:
    return str(money(value if value is not None else ZERO))


def _payments(f: dict):
    qs = StudentPayment.objects.filter(billing_profile__isnull=False)
    if f.get("program"):
        qs = qs.filter(billing_profile__plan__course_id=f["program"])
    if f.get("plan"):
        qs = qs.filter(billing_profile__plan_id=f["plan"])
    if f.get("group"):
        qs = qs.filter(group_id=f["group"])  # группа платежа — история не ломается при переводе
    if f.get("method"):
        qs = qs.filter(method=f["method"])
    return qs


def _invoices(f: dict):
    qs = Invoice.objects.filter(status__in=LIVE)
    if f.get("program"):
        qs = qs.filter(profile__plan__course_id=f["program"])
    if f.get("plan"):
        qs = qs.filter(profile__plan_id=f["plan"])
    if f.get("group"):
        qs = qs.filter(profile__student__group_id=f["group"])
    if f.get("status"):
        qs = qs.filter(status=f["status"])
    return qs


def due_in(date_from: dt.date, date_to: dt.date) -> Q:
    return (Q(due_lesson__isnull=False, due_reached_on__gte=date_from, due_reached_on__lte=date_to)
            | Q(due_lesson__isnull=True, due_date__gte=date_from, due_date__lte=date_to))


def due_by(date_to: dt.date) -> Q:
    return Q(due_lesson__isnull=False, due_reached_on__lte=date_to) | Q(due_lesson__isnull=True, due_date__lte=date_to)


def paid_as_of(invoices, on: dt.date) -> Decimal:
    """Сколько по начислениям оплачено деньгами, ФАКТИЧЕСКИ полученными не
    позже `on` (`StudentPayment.received_date`), а не по времени записи в
    системе: платёж за сентябрь, внесённый в октябре задним числом, гасит
    сентябрьский долг; октябрьские деньги за сентябрь — нет."""
    return PaymentAllocation.objects.filter(
        invoice_id__in=invoices.values("pk"), status=PaymentAllocation.Status.ACTIVE,
        payment__received_date__lte=on,
    ).aggregate(s=Sum("amount"))["s"] or ZERO


def adjusted_as_of(invoices, on: dt.date) -> Decimal:
    return InvoiceAdjustment.objects.filter(
        invoice_id__in=invoices.values("pk"), status=InvoiceAdjustment.Status.APPLIED, effective_date__lte=on,
    ).aggregate(s=Sum("amount"))["s"] or ZERO


def debt_as_of(invoices, on: dt.date) -> Decimal:
    """Долг на дату: сумма начислений − оплаты деньгами, полученными до этой
    даты, − корректировки с датой до неё. Сторнированные распределения и
    отменённые корректировки — исправленные ошибки — не учитываются ни в
    какую дату (иначе перенесённая оплата считалась бы дважды)."""
    total = invoices.aggregate(s=Sum("amount"))["s"] or ZERO
    return max(total - paid_as_of(invoices, on) - adjusted_as_of(invoices, on), ZERO)


def finance_analytics(f: dict, *, date_from: dt.date, date_to: dt.date) -> dict:
    payments = _payments(f)
    in_period = payments.filter(received_date__gte=date_from, received_date__lte=date_to)
    confirmed = in_period.filter(status=StudentPayment.Status.CONFIRMED)
    received = confirmed.filter(kind=StudentPayment.Kind.PAYMENT)
    refunds = confirmed.filter(kind=StudentPayment.Kind.REFUND)
    gross = received.aggregate(s=Sum("amount"), n=Count("pk"))
    refunded = refunds.aggregate(s=Sum("amount"), n=Count("pk"))
    reversed_ = payments.filter(
        status=StudentPayment.Status.VOID, kind=StudentPayment.Kind.PAYMENT,
        voided_at__date__gte=date_from, voided_at__date__lte=date_to,
    ).aggregate(s=Sum("amount"), n=Count("pk"))
    reservations = received.filter(purpose=StudentPayment.Purpose.RESERVATION).aggregate(s=Sum("amount"))["s"]
    prepayment = received.filter(
        Q(purpose=StudentPayment.Purpose.PREPAYMENT)
        | Q(purpose=StudentPayment.Purpose.TUITION, billing_profile__payment_mode=PaymentMode.FULL_PREPAY),
    ).aggregate(s=Sum("amount"))["s"]
    by_method = [
        {"method": r["method"], "method_display": dict(StudentPayment.Method.choices).get(r["method"], r["method"]),
         "amount": _s(r["s"]), "count": r["n"]}
        for r in received.values("method").annotate(s=Sum("amount"), n=Count("pk")).order_by("method")
    ]

    invoices = _invoices(f)
    expected_qs = invoices.filter(due_in(date_from, date_to))
    paid_expr = F("amount_paid") + F("amount_adjusted")
    exp = expected_qs.aggregate(
        s=Sum("amount"), paid=Sum(paid_expr), n=Count("pk"),
        n_paid=Count("pk", filter=Q(status=Invoice.Status.PAID)),
        n_partial=Count("pk", filter=Q(status__in=(Invoice.Status.PARTIALLY_PAID, Invoice.Status.OVERDUE),
                                       amount_paid__gt=0)),
        n_overdue=Count("pk", filter=Q(status=Invoice.Status.OVERDUE)),
        students=Count("profile__student", distinct=True),
    )
    gross_sum, refunds_sum = gross["s"] or ZERO, refunded["s"] or ZERO
    expected_sum, expected_paid = exp["s"] or ZERO, exp["paid"] or ZERO
    debt_end = debt_as_of(invoices.filter(due_by(date_to)), date_to)

    contracts = StudentBillingProfile.objects.filter(created_at__date__gte=date_from, created_at__date__lte=date_to)
    if f.get("program"):
        contracts = contracts.filter(plan__course_id=f["program"])
    if f.get("plan"):
        contracts = contracts.filter(plan_id=f["plan"])
    if f.get("group"):
        contracts = contracts.filter(student__group_id=f["group"])
    course_discounts = contracts.filter(discount_enabled=True).aggregate(s=Sum("discount_amount"), n=Count("pk"))
    package_discounts = LessonPackage.objects.filter(
        created_at__date__gte=date_from, created_at__date__lte=date_to, profile__duration_months__isnull=True,
        discount_amount__gt=0,
    ).exclude(status=LessonPackage.Status.CANCELLED)
    if f.get("program"):
        package_discounts = package_discounts.filter(profile__plan__course_id=f["program"])
    package_discount_sum = package_discounts.aggregate(s=Sum("discount_amount"))["s"] or ZERO

    by_program = {}

    def bucket(key, name):
        return by_program.setdefault(key, {"program": key, "program_name": name or "Без программы",
                                           "received": ZERO, "refunded": ZERO, "expected": ZERO,
                                           "expected_paid": ZERO, "students": 0})

    for r in received.values("billing_profile__plan__course_id", "billing_profile__plan__course__name").annotate(
            s=Sum("amount")):
        bucket(r["billing_profile__plan__course_id"], r["billing_profile__plan__course__name"])["received"] += r["s"]
    for r in refunds.values("billing_profile__plan__course_id", "billing_profile__plan__course__name").annotate(
            s=Sum("amount")):
        bucket(r["billing_profile__plan__course_id"], r["billing_profile__plan__course__name"])["refunded"] += r["s"]
    for r in expected_qs.values("profile__plan__course_id", "profile__plan__course__name").annotate(
            s=Sum("amount"), paid=Sum(paid_expr), st=Count("profile__student", distinct=True)):
        b = bucket(r["profile__plan__course_id"], r["profile__plan__course__name"])
        b["expected"] += r["s"]
        b["expected_paid"] += r["paid"] or ZERO
        b["students"] = r["st"]
    programs = []
    for b in sorted(by_program.values(), key=lambda x: x["program_name"]):
        programs.append({**b, "received": _s(b["received"]), "refunded": _s(b["refunded"]),
                         "net": _s(b["received"] - b["refunded"]), "expected": _s(b["expected"]),
                         "expected_paid": _s(b["expected_paid"]),
                         "expected_unpaid": _s(b["expected"] - b["expected_paid"])})

    return {
        "date_from": date_from.isoformat(), "date_to": date_to.isoformat(),
        "received": {
            "basis": "Валовые поступления: подтверждённые платежи по дате поступления денег "
                     "(отменённые не входят). Чистый поток = валовые − возвраты.",
            "gross": _s(gross_sum), "count": gross["n"], "refunds": _s(refunds_sum), "refunds_count": refunded["n"],
            "net": _s(gross_sum - refunds_sum),
            "reversed": _s(reversed_["s"]), "reversed_count": reversed_["n"],
            "by_method": by_method,
        },
        "expected": {
            "basis": "Начисления, срок оплаты которых наступил в периоде (оплаченные и нет).",
            "amount": _s(expected_sum), "count": exp["n"], "students": exp["students"],
            "paid": _s(expected_paid), "unpaid": _s(expected_sum - expected_paid),
            "paid_count": exp["n_paid"], "partial_count": exp["n_partial"], "overdue_count": exp["n_overdue"],
        },
        "difference": _s(expected_sum - gross_sum),
        "debt_end": _s(debt_end),
        "discounts": {"amount": _s((course_discounts["s"] or ZERO) + package_discount_sum),
                      "contracts": course_discounts["n"]},
        "reservations": _s(reservations), "prepayment": _s(prepayment),
        "by_program": programs,
    }


def invoices_due_in_period(f: dict, *, date_from: dt.date, date_to: dt.date):
    return _invoices(f).filter(due_in(date_from, date_to)).annotate(
        due_on=Coalesce("due_reached_on", "due_date"),
    )
