"""Рабочие списки бухгалтера (только чтение).

* «К оплате» — наступил платёжный этап: есть выставленное неоплаченное
  начисление, срок которого ещё не прошёл (ожидается оплата или сегодня
  последний срок);
* «Скоро оплата» — в текущем учебном месяце осталось ≤ N уроков
  приоритетного предмета (`BillingSettings.due_soon_lessons`), следующий
  месяц есть в договоре и ещё не покрыт (предоплата / аванс → не попадает);
* «Просроченные» — есть начисление после срока с непогашенным остатком
  (бронь сама по себе долгом не является: долг — только наступившие
  начисления).

Строка показывает и то, что студент обязан заплатить сейчас, и будущее
(стоимость следующего месяца), и свободный аванс — отдельно.
"""
from __future__ import annotations

from decimal import Decimal

from django.db.models import OuterRef, Prefetch, Q, Subquery, Sum
from django.utils import timezone

from apps.accounting.services.money import money

from ..models import BillingContactLog, BillingSettings, CreditLedgerEntry, Invoice, LessonPackage, StudentBillingProfile
from .contracts import applicable_credit, next_month_cost, payment_stage

ZERO = Decimal("0.00")
QUEUES = ("to_pay", "soon", "overdue", "all")


def _s(value) -> str | None:
    return None if value is None else str(money(value))


def base_queryset():
    return (
        StudentBillingProfile.objects.select_related("student__group", "plan__course", "subject",
                                                     "responsible_accountant")
        .annotate(credit_sum=Subquery(  # подзапрос: join-фильтры очередей не умножают сумму
            CreditLedgerEntry.objects.filter(profile=OuterRef("pk")).order_by().values("profile")
            .annotate(s=Sum("amount")).values("s")[:1],
        ))
        .prefetch_related(
            Prefetch("invoices", queryset=Invoice.objects.select_related("package").order_by("package__number", "pk")),
            Prefetch("packages", queryset=LessonPackage.objects.order_by("number")),
        )
    )


def apply_filters(qs, f: dict):
    q = Q()
    for part in (f.get("search") or "").split():
        q &= (Q(student__first_name__icontains=part) | Q(student__last_name__icontains=part)
              | Q(parent_phone__icontains=part) | Q(student__parent_phone__icontains=part)
              | Q(parent_name__icontains=part) | Q(student__group__name__icontains=part))
    qs = qs.filter(q)
    if f.get("group"):
        qs = qs.filter(student__group_id=f["group"])
    if f.get("plan"):
        qs = qs.filter(plan_id=f["plan"])
    if f.get("program"):
        qs = qs.filter(plan__course_id=f["program"])
    if f.get("accountant"):
        qs = qs.filter(responsible_accountant_id=f["accountant"])
    if f.get("contract_status"):
        qs = qs.filter(status=f["contract_status"])
    return qs


def queue_queryset(queue: str, f: dict):
    qs = apply_filters(base_queryset(), f)
    if queue == "to_pay":
        return qs.filter(invoices__status__in=(Invoice.Status.OPEN, Invoice.Status.PARTIALLY_PAID)).distinct()
    if queue == "overdue":
        return qs.filter(invoices__status=Invoice.Status.OVERDUE).distinct()
    if queue == "soon":
        return _soon_candidates(qs)
    return qs


def _soon_candidates(qs):
    from django.db.models import F

    n = BillingSettings.load().due_soon_lessons
    return qs.filter(
        status=StudentBillingProfile.Status.ACTIVE,
        packages__status=LessonPackage.Status.ACTIVE,
        packages__lessons_used__gte=F("packages__lessons_total") - n,
        packages__lessons_used__lt=F("packages__lessons_total"),
    ).distinct()


def _last_contacts(profile_ids) -> dict:
    result = {}
    for c in BillingContactLog.objects.filter(profile_id__in=profile_ids).order_by("profile_id", "-contacted_at"):
        result.setdefault(c.profile_id, c)
    return result


def contract_row(profile: StudentBillingProfile, *, last_contact=None, with_next: bool = False) -> dict:
    today = timezone.localdate()
    invoices = list(profile.invoices.all())
    packages = [p for p in profile.packages.all() if p.status != LessonPackage.Status.CANCELLED]
    current = next((p for p in packages if p.status == LessonPackage.Status.ACTIVE), None)
    if current is None and packages:
        current = packages[-1]
    unpaid = [i for i in invoices if i.status in Invoice.UNPAID_STATUSES]
    overdue = [i for i in unpaid if i.status == Invoice.Status.OVERDUE]
    # Этап оплаты: самое срочное неоплаченное начисление.
    focus = overdue[0] if overdue else (unpaid[0] if unpaid else None)
    stage = payment_stage(focus) if focus else (
        "draft" if any(i.status == Invoice.Status.DRAFT for i in invoices) else "paid")
    overdue_lessons = max((i.package.lessons_used - i.due_lesson for i in overdue if i.due_lesson), default=0)
    overdue_days = max(((today - (i.overdue_since or i.due_date)).days for i in overdue), default=0)
    credit = profile.credit_sum if getattr(profile, "credit_sum", None) else ZERO
    usable = applicable_credit(profile, unpaid, credit)
    student = profile.student
    row = {
        "profile": profile.pk, "student": student.pk, "student_name": str(student),
        "group": student.group_id, "group_name": student.group.name if student.group_id else None,
        "program": profile.plan.course.name if profile.plan.course_id else None,
        "plan": profile.plan_id, "plan_name": profile.plan.name,
        "subject_name": profile.subject.name if profile.subject_id else None,
        "parent_name": profile.parent_name, "parent_phone": profile.parent_phone or student.parent_phone,
        "contract_status": profile.status, "contract_status_display": profile.get_status_display(),
        "is_course": profile.is_course, "payment_mode": profile.payment_mode,
        "payment_mode_display": profile.get_payment_mode_display(),
        "duration_months": profile.duration_months,
        "month_number": (current.month_number or current.number) if current else None,
        "lessons_used": current.lessons_used if current else 0,
        "lessons_total": current.lessons_total if current else (profile.lessons_per_month or 0),
        "final_course_price": _s(profile.final_course_price),
        "discount_amount": _s(profile.discount_amount),
        "stage": stage,
        "focus_invoice": None if focus is None else {
            "id": focus.pk, "number": focus.number, "kind": focus.kind,
            "month_number": focus.package.month_number or focus.package.number,
            "amount": _s(focus.amount), "paid": _s(focus.amount_paid + focus.amount_adjusted),
            "balance": _s(focus.balance), "due_lesson": focus.due_lesson,
            "due_date": None if focus.due_lesson else focus.due_date.isoformat(),
            "status": focus.status, "status_display": focus.get_status_display(),
        },
        # Как в карточке (`contracts.money_summary`): за вычетом аванса,
        # который правила договора разрешают направить на эти начисления.
        "due_now": _s(max(sum((i.balance for i in unpaid), ZERO) - usable, ZERO)),
        "overdue_amount": _s(max(sum((i.balance for i in overdue), ZERO) - usable, ZERO)),
        "overdue_lessons": overdue_lessons, "overdue_days": overdue_days,
        "credit": _s(profile.credit_sum if hasattr(profile, "credit_sum") and profile.credit_sum else ZERO),
        "last_contact_at": last_contact.contacted_at.isoformat() if last_contact else None,
        "last_contact_result": last_contact.get_result_display() if last_contact else None,
    }
    if with_next:
        nxt = next_month_cost(profile)
        row["next_month"] = None if nxt is None else {k: (str(v) if isinstance(v, Decimal) else v)
                                                      for k, v in nxt.items()}
    return row


SORTS = {
    "name": lambda r: (r["student_name"],),
    "debt": lambda r: (-Decimal(r["due_now"]), r["student_name"]),
    "overdue": lambda r: (-r["overdue_lessons"], -r["overdue_days"], -Decimal(r["overdue_amount"]), r["student_name"]),
    "lessons": lambda r: (-(r["lessons_used"] / (r["lessons_total"] or 1)), r["student_name"]),
    "group": lambda r: (r["group_name"] or "", r["student_name"]),
}


def queue_rows(queue: str, f: dict) -> list[dict]:
    """Строки очереди (все, до пагинации — сортировка по вычисляемым полям)."""
    profiles = list(queue_queryset(queue, f))
    contacts = _last_contacts([p.pk for p in profiles])
    rows = []
    for profile in profiles:
        row = contract_row(profile, last_contact=contacts.get(profile.pk), with_next=queue == "soon")
        if queue == "to_pay" and row["stage"] not in ("awaiting", "deadline"):
            # Есть просрочка — студент в «Просроченных», здесь только этап «к оплате».
            if not any(i.status in (Invoice.Status.OPEN, Invoice.Status.PARTIALLY_PAID) for i in profile.invoices.all()):
                continue
        if queue == "soon" and (row.get("next_month") is None or Decimal(row["next_month"]["to_pay"]) <= 0):
            continue
        rows.append(row)
    default = {"overdue": "overdue", "to_pay": "debt", "soon": "lessons"}.get(queue, "name")
    rows.sort(key=SORTS.get(f.get("ordering") or default, SORTS["name"]))
    return rows


def counts(f: dict | None = None) -> dict:
    f = f or {}
    return {
        "to_pay": queue_queryset("to_pay", f).count(),
        "soon": len(queue_rows("soon", f)),
        "overdue": queue_queryset("overdue", f).count(),
    }
