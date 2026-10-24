"""Панель бухгалтера и финансовые отчёты по оплате обучения (только чтение).

Определения (отчёты различают студентов, счета и суммы — один студент
может иметь несколько начислений):

* ожидают оплаты — начисления OPEN / PARTIALLY_PAID / OVERDUE; студенты
  считаются уникальными (`students_awaiting`), счета — отдельно
  (`invoices_awaiting`);
* долг — Σ остатков этих начислений (сумма − оплачено − корректировки);
* поступления за период — подтверждённые платежи по пакетам с датой
  поступления в периоде, возвраты — отдельно, нетто — разница (отменённые
  платежи не учитываются);
* авансы — Σ журнала аванса (свободные деньги, ещё не распределённые);
* активные студенты (профили «Обучается») — отдельный показатель, не путать
  с должниками.
"""
from __future__ import annotations

import datetime as dt
from decimal import Decimal

from django.conf import settings
from django.db.models import Count, F, Q, Sum
from django.utils import timezone

from apps.accounting.models import StudentPayment
from apps.accounting.services.money import money

from ..models import (
    BillingContactLog,
    BillingTask,
    CreditLedgerEntry,
    Invoice,
    LessonPackage,
    StudentBillingProfile,
)
from .ledger import credit_balance

ZERO = Decimal("0.00")
UNPAID = Invoice.UNPAID_STATUSES


def _s(value) -> str:
    return str(money(value if value is not None else ZERO))


def filter_profiles(qs, filters: dict, prefix: str = ""):
    """Фильтры панели к любому запросу, связанному с профилем через `prefix`."""
    p = prefix
    if filters.get("group"):
        qs = qs.filter(**{f"{p}student__group_id": filters["group"]})
    if filters.get("subject"):
        qs = qs.filter(**{f"{p}subject_id": filters["subject"]})
    if filters.get("student"):
        qs = qs.filter(**{f"{p}student_id": filters["student"]})
    if filters.get("accountant"):
        qs = qs.filter(**{f"{p}responsible_accountant_id": filters["accountant"]})
    if filters.get("plan"):
        qs = qs.filter(**{f"{p}plan_id": filters["plan"]})
    return qs


def invoices_qs(filters: dict):
    qs = filter_profiles(Invoice.objects.all(), filters, "profile__")
    if filters.get("status"):
        qs = qs.filter(status=filters["status"])
    return qs


def _invoice_row(inv: Invoice) -> dict:
    student = inv.profile.student
    return {
        "invoice": inv.pk, "number": inv.number, "profile": inv.profile_id, "student": student.pk, "student_name": str(student),
        "group": student.group.name if student.group_id else None,
        "subject": str(inv.profile.subject) if inv.profile.subject_id else None,
        "package_number": inv.package.number, "amount": _s(inv.amount), "paid": _s(inv.amount_paid),
        "balance": _s(inv.balance), "due_date": inv.due_date.isoformat(), "period_date": inv.period_date.isoformat(),
        "status": inv.status,
        "status_display": inv.get_status_display(), "parent_phone": inv.profile.parent_phone,
        "accountant": inv.profile.responsible_accountant_id,
    }


def dashboard(filters: dict, *, on: dt.date | None = None) -> dict:
    on = on or timezone.localdate()
    date_from = filters.get("date_from") or on.replace(day=1)
    date_to = filters.get("date_to") or on
    soon_days = int(getattr(settings, "BILLING_DUE_SOON_DAYS", 3))
    rel = ("profile__student__group", "profile__subject", "package")

    unpaid = invoices_qs({**filters, "status": None}).filter(status__in=UNPAID)
    if filters.get("status"):
        unpaid = unpaid.filter(status=filters["status"])
    balance = F("amount") - F("amount_paid") - F("amount_adjusted")
    totals = unpaid.aggregate(
        invoices=Count("pk"), students=Count("profile__student", distinct=True), debt=Sum(balance),
    )
    overdue = unpaid.filter(status=Invoice.Status.OVERDUE)
    overdue_totals = overdue.aggregate(
        invoices=Count("pk"), students=Count("profile__student", distinct=True), amount=Sum(balance),
    )
    due_soon = unpaid.filter(
        status__in=(Invoice.Status.OPEN, Invoice.Status.PARTIALLY_PAID),
        due_date__gte=on, due_date__lte=on + dt.timedelta(days=soon_days),
    ).select_related(*rel).order_by("due_date")
    partial = unpaid.filter(amount_paid__gt=0).select_related(*rel).order_by("due_date")

    payments = filter_profiles(
        StudentPayment.objects.filter(billing_profile__isnull=False, status=StudentPayment.Status.CONFIRMED,
                                      received_date__gte=date_from, received_date__lte=date_to),
        filters, "billing_profile__",
    )
    received = payments.filter(kind=StudentPayment.Kind.PAYMENT).aggregate(s=Sum("amount"), n=Count("pk"))
    refunds = payments.filter(kind=StudentPayment.Kind.REFUND).aggregate(s=Sum("amount"), n=Count("pk"))
    credit = filter_profiles(CreditLedgerEntry.objects.all(), filters, "profile__").aggregate(s=Sum("amount"))["s"]
    credit_profiles = (
        filter_profiles(CreditLedgerEntry.objects.all(), filters, "profile__")
        .values("profile").annotate(s=Sum("amount")).filter(s__gt=0).count()
    )
    profiles = filter_profiles(StudentBillingProfile.objects.all(), filters)
    contacts = filter_profiles(BillingContactLog.objects.all(), filters, "profile__").select_related(
        "student", "staff", "invoice",
    )
    if filters.get("date_from") or filters.get("date_to"):
        contacts = contacts.filter(contacted_at__date__gte=date_from, contacted_at__date__lte=date_to)
    tasks = filter_profiles(BillingTask.objects.filter(status__in=BillingTask.LIVE_STATUSES), filters, "profile__")
    received_sum, refunds_sum = received["s"] or ZERO, refunds["s"] or ZERO

    return {
        "date": on.isoformat(), "date_from": date_from.isoformat(), "date_to": date_to.isoformat(),
        "active_students": profiles.filter(status=StudentBillingProfile.Status.ACTIVE)
        .values("student").distinct().count(),
        "students_awaiting": totals["students"] or 0,
        "invoices_awaiting": totals["invoices"] or 0,
        "total_debt": _s(totals["debt"]),
        "overdue_invoices": overdue_totals["invoices"] or 0,
        "overdue_students": overdue_totals["students"] or 0,
        "overdue_amount": _s(overdue_totals["amount"]),
        "due_soon_days": soon_days,
        "due_soon": [_invoice_row(inv) for inv in due_soon[:100]],
        "received": {"amount": _s(received_sum), "count": received["n"], "refunds": _s(refunds_sum),
                     "refunds_count": refunds["n"], "net": _s(received_sum - refunds_sum)},
        "credit_total": _s(credit), "credit_profiles": credit_profiles,
        "partial": [_invoice_row(inv) for inv in partial[:100]],
        "packages_ending": filter_profiles(
            LessonPackage.objects.filter(status=LessonPackage.Status.ACTIVE, ending_notified_at__isnull=False),
            filters, "profile__",
        ).count(),
        "open_tasks": tasks.count(),
        "follow_ups_due": tasks.filter(next_contact_date__lte=on).count(),
        "contacts": [
            {
                "id": c.pk, "student": c.student_id, "student_name": str(c.student),
                "invoice": c.invoice.number if c.invoice_id else None, "staff": str(c.staff),
                "contacted_at": c.contacted_at.isoformat(), "channel": c.channel,
                "channel_display": c.get_channel_display(), "result": c.result, "result_display": c.get_result_display(),
                "comment": c.comment,
                "promised_payment_date": c.promised_payment_date.isoformat() if c.promised_payment_date else None,
                "next_contact_date": c.next_contact_date.isoformat() if c.next_contact_date else None,
            }
            for c in contacts[:50]
        ],
    }


def debtors(filters: dict, *, on: dt.date | None = None) -> list[dict]:
    """Очередь должников бухгалтера: по студенту — число счетов, общий долг,
    просрочка, ближайший срок, состояние задачи и последний контакт."""
    on = on or timezone.localdate()
    unpaid = invoices_qs({**filters, "status": None}).filter(status__in=UNPAID)
    if filters.get("status"):
        unpaid = unpaid.filter(status=filters["status"])
    unpaid = unpaid.select_related("profile__student__group", "profile__subject", "profile__responsible_accountant")
    rows: dict[int, dict] = {}
    for inv in unpaid.order_by("due_date"):
        profile = inv.profile
        row = rows.setdefault(profile.pk, {
            "profile": profile.pk, "student": profile.student_id, "student_name": str(profile.student),
            "group": profile.student.group.name if profile.student.group_id else None,
            "subject": str(profile.subject) if profile.subject_id else None,
            "parent_name": profile.parent_name, "parent_phone": profile.parent_phone,
            "accountant": profile.responsible_accountant_id,
            "accountant_name": str(profile.responsible_accountant) if profile.responsible_accountant_id else None,
            "invoices": 0, "debt": ZERO, "overdue_amount": ZERO, "oldest_due": inv.due_date.isoformat(),
            "max_days_overdue": 0, "has_partial": False,
        })
        row["invoices"] += 1
        row["debt"] += inv.balance
        if inv.status == Invoice.Status.OVERDUE:
            row["overdue_amount"] += inv.balance
            row["max_days_overdue"] = max(row["max_days_overdue"], (on - inv.due_date).days)
        row["has_partial"] = row["has_partial"] or inv.amount_paid > 0
    tasks = {
        t.profile_id: t for t in BillingTask.objects.filter(
            profile_id__in=rows, status__in=BillingTask.LIVE_STATUSES,
        ).order_by("next_contact_date")
    }
    last_contacts = {}
    for c in BillingContactLog.objects.filter(profile_id__in=rows).order_by("profile_id", "-contacted_at"):
        last_contacts.setdefault(c.profile_id, c)
    result = []
    for profile_id, row in rows.items():
        task, contact = tasks.get(profile_id), last_contacts.get(profile_id)
        row.update({
            "debt": _s(row["debt"]), "overdue_amount": _s(row["overdue_amount"]),
            "credit": _s(credit_balance(profile_id)),
            "task": task.pk if task else None, "task_status": task.status if task else None,
            "promised_date": task.promised_date.isoformat() if task and task.promised_date else None,
            "next_contact_date": task.next_contact_date.isoformat() if task and task.next_contact_date else None,
            "last_contact_at": contact.contacted_at.isoformat() if contact else None,
            "last_contact_result": contact.get_result_display() if contact else None,
        })
        result.append(row)
    result.sort(key=lambda r: (-r["max_days_overdue"], r["oldest_due"]))
    return result


def financial_report(filters: dict, *, date_from: dt.date, date_to: dt.date) -> dict:
    """Отчёт за период: начислено, поступило, возвращено, долг на конец,
    аванс; по направлениям. Начислено — выставленные (не черновики и не
    аннулированные) начисления, ПЕРИОД которых (`period_date`) в отчётном
    периоде — не дата выставления и не дата записи. Поступило — по дате
    поступления денег. Долг на конец — как был на `date_to`."""
    from .analytics import debt_as_of

    live = invoices_qs(filters).exclude(status__in=(Invoice.Status.DRAFT, Invoice.Status.VOID))
    issued = live.filter(period_date__gte=date_from, period_date__lte=date_to)
    payments = filter_profiles(
        StudentPayment.objects.filter(billing_profile__isnull=False, status=StudentPayment.Status.CONFIRMED,
                                      received_date__gte=date_from, received_date__lte=date_to),
        filters, "billing_profile__",
    )
    balance = F("amount") - F("amount_paid") - F("amount_adjusted")
    by_subject = []
    for row in issued.values("profile__subject_id", "profile__subject__name").annotate(
        invoices=Count("pk"), students=Count("profile__student", distinct=True), amount=Sum("amount"),
    ).order_by("profile__subject__name"):
        by_subject.append({
            "subject": row["profile__subject_id"], "subject_name": row["profile__subject__name"] or "Все уроки",
            "invoices": row["invoices"], "students": row["students"], "amount": _s(row["amount"]),
        })
    received = payments.filter(kind=StudentPayment.Kind.PAYMENT).aggregate(s=Sum("amount"))["s"] or ZERO
    refunded = payments.filter(kind=StudentPayment.Kind.REFUND).aggregate(s=Sum("amount"))["s"] or ZERO
    debt = invoices_qs(filters).filter(status__in=UNPAID).aggregate(
        s=Sum(balance), n=Count("pk"), st=Count("profile__student", distinct=True),
    )
    issued_totals = issued.aggregate(s=Sum("amount"), n=Count("pk"), st=Count("profile__student", distinct=True))
    return {
        "date_from": date_from.isoformat(), "date_to": date_to.isoformat(),
        "invoiced": {"amount": _s(issued_totals["s"]), "invoices": issued_totals["n"], "students": issued_totals["st"]},
        "received": _s(received), "refunded": _s(refunded), "net_received": _s(received - refunded),
        "debt_now": {"amount": _s(debt["s"]), "invoices": debt["n"], "students": debt["st"]},
        "debt_end": _s(debt_as_of(live.filter(period_date__lte=date_to), date_to)),
        "credit_now": _s(filter_profiles(CreditLedgerEntry.objects.all(), filters, "profile__")
                         .aggregate(s=Sum("amount"))["s"]),
        "by_subject": by_subject,
    }


def reconcile() -> list[dict]:
    """Сверка: кеш начислений против записей, аванс не отрицателен,
    счётчики пакетов против списаний. Пустой список — расхождений нет."""
    from .invoices import calculate_invoice_balance

    problems = []
    for inv in Invoice.objects.exclude(status=Invoice.Status.VOID):
        sums = calculate_invoice_balance(inv)
        if sums["paid"] != inv.amount_paid or sums["adjusted"] != inv.amount_adjusted:
            problems.append({"type": "invoice_cache", "invoice": inv.pk})
        if sums["balance"] < 0:
            problems.append({"type": "invoice_overpaid", "invoice": inv.pk})
    for row in CreditLedgerEntry.objects.values("profile").annotate(s=Sum("amount")).filter(s__lt=0):
        problems.append({"type": "negative_credit", "profile": row["profile"]})
    for row in CreditLedgerEntry.objects.values("payment").annotate(s=Sum("amount")).filter(s__lt=0):
        problems.append({"type": "payment_overallocated", "payment": row["payment"]})
    # Проведённые уроки, которые по правилам договора должны быть в учебном
    # месяце, но не списаны (договор оформлен позже уроков и т.п.).
    from .lessons import lesson_breakdown

    for profile in StudentBillingProfile.objects.filter(status=StudentBillingProfile.Status.ACTIVE).select_related("plan"):
        missing = lesson_breakdown(profile)["totals"].get("not_processed", 0)
        if missing:
            problems.append({"type": "lessons_not_consumed", "profile": profile.pk, "lessons": missing})
    used = LessonPackage.objects.annotate(
        live=Count("consumptions", filter=Q(consumptions__kind="CONSUME", consumptions__status="ACTIVE")),
    ).exclude(live=F("lessons_used"))
    problems += [{"type": "package_counter", "package": p.pk} for p in used]
    return problems
