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
from .progress import financial_package, group_progress

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
    """Кандидаты очереди. «К оплате» / «Просроченные» — договоры с
    непогашенным остатком начислений; в какую очередь попадает договор,
    решает `contract_row` по актуальной стадии (`contracts.payment_stage`:
    сегодняшняя дата, срок, остаток), а не сохранённый статус начисления."""
    qs = apply_filters(base_queryset(), f)
    if queue in ("to_pay", "overdue"):
        return qs.filter(invoices__status__in=Invoice.UNPAID_STATUSES).distinct()
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


def contract_row(profile: StudentBillingProfile, *, last_contact=None, with_next: bool = False,
                 group_cache: dict | None = None) -> dict:
    today = timezone.localdate()
    invoices = list(profile.invoices.all())
    packages = [p for p in profile.packages.all() if p.status != LessonPackage.Status.CANCELLED]
    current = next((p for p in packages if p.status == LessonPackage.Status.ACTIVE), None)
    if current is None and packages:
        current = packages[-1]
    # Стадии — по актуальным данным (`payment_stage`: дата по часовому поясу
    # проекта, урок-срок, остаток), а не по сохранённому статусу начисления.
    stages = {i.pk: payment_stage(i, on=today) for i in invoices}
    unpaid = [i for i in invoices if stages[i.pk] in ("awaiting", "deadline", "overdue")]
    overdue = [i for i in unpaid if stages[i.pk] == "overdue"]
    due = [i for i in unpaid if stages[i.pk] == "deadline"] + [i for i in unpaid if stages[i.pk] == "awaiting"]
    # Этап оплаты: самое срочное неоплаченное начисление.
    focus = overdue[0] if overdue else (due[0] if due else None)
    stage = stages[focus.pk] if focus else (
        "draft" if any(i.status == Invoice.Status.DRAFT for i in invoices) else "paid")
    overdue_lessons = max((i.package.lessons_used - i.due_lesson for i in overdue if i.due_lesson), default=0)
    overdue_days = max(((today - (i.overdue_since or i.due_date)).days for i in overdue), default=0)
    credit = profile.credit_sum if getattr(profile, "credit_sum", None) else ZERO
    usable = applicable_credit(profile, unpaid, credit)
    # «К оплате сейчас» по срокам (только отображение, суммы те же): аванс
    # закрывает сначала просроченное, затем начисления с последним сроком
    # сегодня, затем те, срок которых ещё не наступил.
    left = usable
    split = {}
    for key, part in (("overdue", overdue), ("deadline", [i for i in unpaid if stages[i.pk] == "deadline"]),
                      ("not_due", [i for i in unpaid if stages[i.pk] == "awaiting"])):
        balance = sum((i.balance for i in part), ZERO)
        split[key] = max(balance - left, ZERO)
        left = max(left - balance, ZERO)
    student = profile.student
    # Учебный месяц — месяц ГРУППЫ (`progress.group_progress`: проведённые
    # IT-занятия текущей группы, одинаково у всех учеников). Финансовый пакет
    # договора — отдельные поля `package_*`. Тариф без учебных месяцев — пакет.
    package = financial_package(profile, packages)
    group = group_progress(student.group if student.group_id else None, profile.subject_id,
                           cache=group_cache) if profile.is_course else None
    if group is not None:
        month_number, lessons_used, lessons_total = group["month"], group["in_month"], group["per_month"]
    else:
        month_number = (current.month_number or current.number) if current else None
        lessons_used = current.lessons_used if current else 0
        lessons_total = current.lessons_total if current else (profile.lessons_per_month or 0)
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
        # Учебный месяц группы: месяц, занятие группы в месяце, уроков в месяце.
        "month_number": month_number, "lessons_used": lessons_used, "lessons_total": lessons_total,
        "group_progress": group,  # held / total / warning («Нужна настройка…» — цифр нет)
        # Финансовый пакет договора ученика — по нему начисления и сроки.
        "package_number": package["number"] if package else None,
        "package_lessons_used": package["lessons_used"] if package else None,
        "package_lessons_total": package["lessons_total"] if package else None,
        # Засчитано ученику по договору за курс (не занятия группы) и объём договора.
        "course_lessons_counted": package["counted"] if package else 0,
        "course_lessons_total": (profile.duration_months * profile.lessons_per_month
                                 if profile.duration_months and profile.lessons_per_month else None),
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
        # Из «К оплате сейчас»: последний срок сегодня / срок ещё не наступил
        # (просрочено + сегодня + не наступил = к оплате сейчас).
        "due_today_amount": _s(split["deadline"]), "not_due_amount": _s(split["not_due"]),
        # Категории очередей — единое правило (списки и счётчики): «Просроченные» —
        # срок прошёл и после применимого аванса остаётся долг; «К оплате» —
        # выставленное начисление, срок не прошёл, к оплате > 0. Полностью
        # оплаченное (остаток 0) — ни там, ни там.
        "in_overdue": split["overdue"] > 0, "in_to_pay": split["deadline"] + split["not_due"] > 0,
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
    # «Скоро оплата» — по финансовому пакету (сколько уроков пакета пройдено).
    "lessons": lambda r: (-((r["package_lessons_used"] or 0) / (r["package_lessons_total"] or 1)), r["student_name"]),
    "group": lambda r: (r["group_name"] or "", r["student_name"]),
}


def in_queue(queue: str, row: dict) -> bool:
    """Попадает ли строка в очередь — одно правило для списка и счётчика.

    «Скоро оплата» — следующий месяц приближается, его начисление ещё НЕ
    выставлено и аванс его не покрывает; как только начисление выставлено
    (срок оплаты наступил) — студент в «К оплате», а не здесь."""
    if queue == "to_pay":
        return row["in_to_pay"]
    if queue == "overdue":
        return row["in_overdue"]
    if queue == "soon":
        nxt = row.get("next_month")
        return nxt is not None and not nxt.get("issued") and Decimal(nxt["to_pay"]) > 0
    return True


def queue_rows(queue: str, f: dict) -> list[dict]:
    """Строки очереди (все, до пагинации — сортировка по вычисляемым полям)."""
    profiles = list(queue_queryset(queue, f))
    contacts = _last_contacts([p.pk for p in profiles])
    rows, groups = [], {}  # месяц группы считается один раз на группу
    for profile in profiles:
        row = contract_row(profile, last_contact=contacts.get(profile.pk), with_next=queue == "soon", group_cache=groups)
        if not in_queue(queue, row):
            continue
        rows.append(row)
    default = {"overdue": "overdue", "to_pay": "debt", "soon": "lessons"}.get(queue, "name")
    rows.sort(key=SORTS.get(f.get("ordering") or default, SORTS["name"]))
    return rows


def counts(f: dict | None = None) -> dict:
    f = f or {}
    # Те же строки, что в списках (`in_queue`), — счётчики не расходятся со списками.
    return {queue: len(queue_rows(queue, f)) for queue in ("to_pay", "soon", "overdue")}
