"""Финансовые периоды: выбор месяца, отчёт за период и проверка
исторических начислений (только чтение, кроме `apply_period_review`).

Три даты не смешиваются:

* `Invoice.period_date` — учебный / финансовый период начисления (к какому
  месяцу относится долг);
* `StudentPayment.received_date` — когда деньги фактически получены
  (к какому месяцу относится поступление);
* `created_at` — когда запись внесена в систему (только аудит; в отчётах
  — лишь как признак «внесено задним числом»).

Поэтому октябрьская оплата сентябрьского долга уменьшает сентябрьское
начисление, но в отчёте — октябрьское поступление «за прошлые периоды», а
в сентябре — «долг на конец периода» и «погашено позже: октябрь».
"""
from __future__ import annotations

import calendar
import datetime as dt
from collections import defaultdict
from decimal import Decimal

from django.db.models import Count, Min, Sum
from django.db.models.functions import TruncMonth
from django.utils import timezone

from apps.accounting.models import StudentPayment
from apps.accounting.services.money import money

from ..models import Invoice, InvoiceAdjustment, PaymentAllocation
from . import BillingError
from .analytics import debt_as_of
from .reports import filter_profiles

ZERO = Decimal("0.00")
LIVE = (Invoice.Status.OPEN, Invoice.Status.PARTIALLY_PAID, Invoice.Status.OVERDUE, Invoice.Status.PAID)
MONTHS = ("Январь", "Февраль", "Март", "Апрель", "Май", "Июнь", "Июль", "Август", "Сентябрь", "Октябрь",
          "Ноябрь", "Декабрь")


def _s(value) -> str:
    return str(money(value if value is not None else ZERO))


def month_bounds(value: str) -> tuple[dt.date, dt.date]:
    """`2026-09` → (1 сентября, 30 сентября)."""
    try:
        year, month = (int(part) for part in str(value).split("-")[:2])
        first = dt.date(year, month, 1)
    except (TypeError, ValueError):
        raise BillingError("Месяц — в формате ГГГГ-ММ.", code="bad_date")
    return first, first.replace(day=calendar.monthrange(year, month)[1])


def month_label(day: dt.date) -> str:
    return f"{MONTHS[day.month - 1]} {day.year}"


def _month_key(day) -> str:
    day = day.date() if isinstance(day, dt.datetime) else day
    return f"{day:%Y-%m}"


def available_periods(*, on: dt.date | None = None) -> dict:
    """Месяцы для переключателя: от первого месяца с данными (начисление или
    поступление) до следующего за текущим. Текущий — по умолчанию."""
    on = on or timezone.localdate()
    first = min(
        filter(None, (
            Invoice.objects.aggregate(m=Min("period_date"))["m"],
            StudentPayment.objects.filter(billing_profile__isnull=False).aggregate(m=Min("received_date"))["m"],
        )),
        default=on,
    )
    cursor, last = first.replace(day=1), (on.replace(day=1) + dt.timedelta(days=32)).replace(day=1)
    months = []
    while cursor <= last:
        date_from, date_to = month_bounds(_month_key(cursor))
        months.append({"value": _month_key(cursor), "label": month_label(cursor),
                       "date_from": date_from.isoformat(), "date_to": date_to.isoformat(),
                       "is_current": cursor == on.replace(day=1)})
        cursor = (cursor + dt.timedelta(days=32)).replace(day=1)
    return {"today": on.isoformat(), "current": _month_key(on), "months": months[::-1]}


def _invoices(f: dict):
    return filter_profiles(Invoice.objects.filter(status__in=LIVE), f, "profile__")


def _payments(f: dict):
    return filter_profiles(
        StudentPayment.objects.filter(billing_profile__isnull=False, status=StudentPayment.Status.CONFIRMED),
        f, "billing_profile__",
    )


def _allocations(f: dict):
    return filter_profiles(
        PaymentAllocation.objects.filter(status=PaymentAllocation.Status.ACTIVE, invoice__status__in=LIVE),
        f, "profile__",
    )


def _sum(qs, field="amount") -> Decimal:
    return qs.aggregate(s=Sum(field))["s"] or ZERO


def _by_month(qs, field: str) -> list[dict]:
    rows = (qs.annotate(m=TruncMonth(field)).values("m").annotate(s=Sum("amount"), n=Count("pk")).order_by("m"))
    return [{"month": _month_key(r["m"]), "label": month_label(r["m"]), "amount": _s(r["s"]), "count": r["n"]}
            for r in rows if r["m"] is not None]


def period_report(f: dict, *, date_from: dt.date, date_to: dt.date) -> dict:
    """Всё, что бухгалтер видит, выбрав месяц:

    * поступило в периоде (по дате поступления) и за какие периоды эти деньги;
    * начислено за период (по периоду начисления);
    * долг на начало и на конец периода — по операциям до этой даты;
    * судьба начислений периода: оплачено в периоде, раньше (аванс), позже
      (по месяцам поступления), не оплачено сейчас.
    """
    if date_from > date_to:
        raise BillingError("Начало периода позже конца.", code="bad_date")
    invoices, payments, allocations = _invoices(f), _payments(f), _allocations(f)

    # 1. Деньги, фактически полученные в периоде.
    received = payments.filter(received_date__gte=date_from, received_date__lte=date_to)
    gross = received.filter(kind=StudentPayment.Kind.PAYMENT)
    refunds = received.filter(kind=StudentPayment.Kind.REFUND)
    gross_sum, refunds_sum = _sum(gross), _sum(refunds)
    money_in = allocations.filter(payment__received_date__gte=date_from, payment__received_date__lte=date_to)
    for_current = _sum(money_in.filter(invoice__period_date__gte=date_from, invoice__period_date__lte=date_to))
    previous = money_in.filter(invoice__period_date__lt=date_from)
    for_previous = _sum(previous)
    for_future = _sum(money_in.filter(invoice__period_date__gt=date_to))
    backdated = gross.filter(created_at__date__gt=date_to)

    # 2. Начисления периода и их судьба.
    accrued = invoices.filter(period_date__gte=date_from, period_date__lte=date_to)
    accrued_totals = accrued.aggregate(s=Sum("amount"), n=Count("pk"), st=Count("profile__student", distinct=True))
    accrued_sum = accrued_totals["s"] or ZERO
    accrued_alloc = allocations.filter(invoice__in=accrued.values("pk"))
    paid_before = _sum(accrued_alloc.filter(payment__received_date__lt=date_from))
    paid_in = _sum(accrued_alloc.filter(payment__received_date__gte=date_from, payment__received_date__lte=date_to))
    later = accrued_alloc.filter(payment__received_date__gt=date_to)
    adjustments = InvoiceAdjustment.objects.filter(invoice__in=accrued.values("pk"),
                                                   status=InvoiceAdjustment.Status.APPLIED)
    adjusted_by_end = _sum(adjustments.filter(effective_date__lte=date_to))
    adjusted_later = _sum(adjustments.filter(effective_date__gt=date_to))
    unpaid_at_end = max(accrued_sum - paid_before - paid_in - adjusted_by_end, ZERO)
    still_unpaid = sum((inv.balance for inv in accrued.filter(
        status__in=Invoice.UNPAID_STATUSES).only("amount", "amount_paid", "amount_adjusted")), ZERO)

    # 3. Задолженность «как была» — все периоды до даты.
    opening_day = date_from - dt.timedelta(days=1)
    opening = debt_as_of(invoices.filter(period_date__lte=opening_day), opening_day)
    closing_qs = invoices.filter(period_date__lte=date_to)
    closing = debt_as_of(closing_qs, date_to)

    return {
        "date_from": date_from.isoformat(), "date_to": date_to.isoformat(),
        "label": (month_label(date_from) if (date_from.day == 1 and date_to == month_bounds(_month_key(date_from))[1])
                  else f"{date_from:%d.%m.%Y} — {date_to:%d.%m.%Y}"),
        "basis": {
            "received": "По дате фактического поступления денег (received_date).",
            "accrued": "По периоду начисления (period_date), а не по дате записи или выставления.",
            "debt": "Начисления периодов до даты − деньги, полученные до этой даты, − корректировки с датой до неё.",
        },
        "received": {
            "gross": _s(gross_sum), "count": gross.count(), "refunds": _s(refunds_sum), "refunds_count": refunds.count(),
            "net": _s(gross_sum - refunds_sum),
            "for_current_period": _s(for_current), "for_previous_periods": _s(for_previous),
            "for_future_periods": _s(for_future),
            "to_credit": _s(max(gross_sum - for_current - for_previous - for_future, ZERO)),
            "previous_by_period": _by_month(previous, "invoice__period_date"),
            "backdated": {"amount": _s(_sum(backdated)), "count": backdated.count()},
        },
        "accrued": {
            "amount": _s(accrued_sum), "count": accrued_totals["n"], "students": accrued_totals["st"],
            "paid_in_advance": _s(paid_before), "paid_in_period": _s(paid_in),
            "adjusted_by_end": _s(adjusted_by_end), "unpaid_at_end": _s(unpaid_at_end),
            "paid_later": _s(_sum(later)), "paid_later_by_month": _by_month(later, "payment__received_date"),
            "adjusted_later": _s(adjusted_later), "unpaid_now": _s(still_unpaid),
        },
        "debt": {"opening": _s(opening), "closing": _s(closing)},
        "debtors_at_end": debtors_as_of(closing_qs, date_to),
    }


def debtors_as_of(invoices, on: dt.date, *, limit: int = 500) -> list[dict]:
    """Должники на дату: по договору — долг «как был» на `on` и сколько из
    него не погашено до сих пор."""
    totals: dict[int, dict] = {}
    for inv in invoices.select_related("profile__student__group", "profile__subject").order_by("period_date"):
        row = totals.setdefault(inv.profile_id, {
            "profile": inv.profile_id, "student": inv.profile.student_id, "student_name": str(inv.profile.student),
            "group": inv.profile.student.group.name if inv.profile.student.group_id else None,
            "subject": str(inv.profile.subject) if inv.profile.subject_id else None,
            "parent_phone": inv.profile.parent_phone, "ids": [], "amount": ZERO, "unpaid_now": ZERO,
            "oldest_period": inv.period_date.isoformat(),
        })
        row["ids"].append(inv.pk)
        row["amount"] += inv.amount
        if inv.status in Invoice.UNPAID_STATUSES:
            row["unpaid_now"] += inv.balance
    paid, adjusted = defaultdict(lambda: ZERO), defaultdict(lambda: ZERO)
    ids = [pk for row in totals.values() for pk in row["ids"]]
    for r in PaymentAllocation.objects.filter(
            invoice_id__in=ids, status=PaymentAllocation.Status.ACTIVE, payment__received_date__lte=on,
    ).values("profile_id").annotate(s=Sum("amount")):
        paid[r["profile_id"]] = r["s"]
    for r in InvoiceAdjustment.objects.filter(
            invoice_id__in=ids, status=InvoiceAdjustment.Status.APPLIED, effective_date__lte=on,
    ).values("invoice__profile_id").annotate(s=Sum("amount")):
        adjusted[r["invoice__profile_id"]] = r["s"]
    rows = []
    for profile_id, row in totals.items():
        debt = row.pop("amount") - paid[profile_id] - adjusted[profile_id]
        row.pop("ids")
        if debt > 0:
            rows.append({**row, "debt": _s(debt), "unpaid_now": _s(row["unpaid_now"])})
    rows.sort(key=lambda r: (-Decimal(r["debt"]), r["student_name"]))
    return rows[:limit]


# ---------------------------------------------------------------------------
# Проверка исторических периодов
# ---------------------------------------------------------------------------

def period_review() -> list[dict]:
    """Начисления, период которых, вероятно, записан не тем месяцем (договор
    оформлен задним числом до появления `period_date`: первый месяц
    записан днём оформления, а не началом договора).

    `proposed` — исправление с проверяемым основанием (начало договора, и
    первый засчитанный урок пакета в том же месяце); `ambiguous` — период
    однозначно не определить, нужна ручная проверка (`proposed` пусто).
    Ничего не меняет."""
    rows = []
    invoices = (Invoice.objects.exclude(status=Invoice.Status.VOID)
                .select_related("package", "profile__student").order_by("profile_id", "package__number", "pk"))
    first_numbers = {}
    for inv in invoices:
        first_numbers.setdefault(inv.profile_id, inv.package.number)
    for inv in invoices:
        package, profile = inv.package, inv.profile
        started = package.started_on
        row = {
            "invoice": inv.pk, "number": inv.number, "profile": profile.pk, "student_name": str(profile.student),
            "package_number": package.number, "month_number": package.month_number,
            "issue_date": inv.issue_date.isoformat(), "period_date": inv.period_date.isoformat(),
            "contract_start": profile.start_date.isoformat(), "first_lesson": started.isoformat() if started else None,
            "created_at": inv.created_at.isoformat(), "proposed": None, "ambiguous": False, "reason": "",
        }
        if package.number == first_numbers[inv.profile_id]:
            if _month_key(inv.period_date) == _month_key(profile.start_date) or inv.period_date < profile.start_date:
                continue
            if started is not None and _month_key(started) == _month_key(profile.start_date):
                row.update(proposed=profile.start_date.isoformat(),
                           reason=f"Договор с {profile.start_date:%d.%m.%Y}, первый засчитанный урок "
                                  f"{started:%d.%m.%Y} — начисление относится к этому месяцу, "
                                  f"а записано {inv.period_date:%d.%m.%Y} (день оформления).")
            elif started is None:
                row.update(ambiguous=True, reason="Договор начат раньше, чем записан период, но уроков по пакету "
                                                  "нет — период не подтверждается уроками.")
            else:
                row.update(ambiguous=True, reason=f"Начало договора ({profile.start_date:%d.%m.%Y}) и первый урок "
                                                  f"({started:%d.%m.%Y}) — в разных месяцах.")
            rows.append(row)
        elif started is not None and started < inv.period_date and _month_key(started) != _month_key(inv.period_date):
            row.update(ambiguous=True, reason=f"Учебный месяц начался {started:%d.%m.%Y}, а период начисления — "
                                              f"{inv.period_date:%d.%m.%Y}: начисление выставлено позже.")
            rows.append(row)
    return rows


def apply_period_review(*, actor=None, invoice_ids: list[int] | None = None) -> list[dict]:
    """Исправить период начислений, у которых есть проверяемое основание
    (`proposed`), — каждое изменение в журнале аудита с основанием.
    Неоднозначные не трогаются. Повторный запуск ничего не меняет."""
    from .invoices import correct_invoice_period

    changed = []
    for row in period_review():
        if not row["proposed"] or (invoice_ids is not None and row["invoice"] not in invoice_ids):
            continue
        invoice = Invoice.objects.get(pk=row["invoice"])
        correct_invoice_period(invoice, actor=actor, period_date=dt.date.fromisoformat(row["proposed"]),
                               reason=f"Проверка исторических периодов: {row['reason']}", system=actor is None)
        changed.append(row)
    return changed


__all__ = ["apply_period_review", "available_periods", "debtors_as_of", "month_bounds", "period_report", "period_review"]
