"""Пакеты и начисления.

Алгоритм следующего платёжного цикла (`create_next_package_invoice`):

1. профиль заблокирован (`select_for_update`) — параллельные вызовы идут
   по очереди;
2. уже есть следующий пакет (PLANNED: оплачен вперёд или выставлен
   заранее) — новый не создаётся, возвращается он;
3. стоимость — по действующим условиям профиля на дату события (снимок);
4. пакет и начисление создаются с уникальными бизнес-ключами
   (`profile+number`, `package`), поэтому повтор невозможен даже в обход
   блокировки;
5. доступный аванс сразу применяется к начислению: покрыл полностью —
   статус «Оплачено», частично — остаток долга на том же начислении;
6. срок оплаты — договор по программе: не позднее `deadline_lessons`-го
   зачтённого урока приоритетного предмета этого месяца (со следующего —
   просрочка); тариф без срока — `plan.payment_due_days` от даты;
7. неоплаченное начисление — задача ответственному бухгалтеру;
8. уведомление — через outbox, доставка после коммита.
"""
from __future__ import annotations

import datetime as dt
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.db.models import F, Max, Q, Sum
from django.utils import timezone

from apps.accounting.services import audit
from apps.accounting.services.money import money

from ..models import (
    BillingNotification,
    BillingTask,
    BillingTermsChange,
    Invoice,
    InvoiceAdjustment,
    LessonPackage,
    PaymentAllocation,
    StudentBillingProfile,
)
from . import BillingError
from .notifications import notify
from .pricing import quote_for_profile

ZERO = Decimal("0.00")
Status = Invoice.Status
PackageStatus = LessonPackage.Status


def today() -> dt.date:
    return timezone.localdate()


def lock_profile(profile_or_id) -> StudentBillingProfile:
    pk = getattr(profile_or_id, "pk", profile_or_id)
    return StudentBillingProfile.objects.select_for_update().select_related("plan", "student").get(pk=pk)


# ---------------------------------------------------------------------------
# Остаток и статус начисления
# ---------------------------------------------------------------------------

def calculate_invoice_balance(invoice: Invoice) -> dict:
    """Остаток по записям (источник истины, не по кешу):
    сумма − действующие распределения − применённые корректировки."""
    paid = invoice.allocations.filter(status=PaymentAllocation.Status.ACTIVE).aggregate(s=Sum("amount"))["s"] or ZERO
    adjusted = invoice.adjustments.filter(status=InvoiceAdjustment.Status.APPLIED).aggregate(s=Sum("amount"))["s"] or ZERO
    return {"amount": invoice.amount, "paid": paid, "adjusted": adjusted, "balance": invoice.amount - paid - adjusted}


def status_for(invoice: Invoice, balance: Decimal, paid: Decimal, adjusted: Decimal, on: dt.date) -> str:
    if invoice.status in (Status.VOID, Status.DRAFT):
        return invoice.status
    if balance <= 0:
        return Status.PAID
    if invoice.due_lesson:
        # Срок в уроках: урок № due_lesson — последний срок, дальше просрочка.
        if invoice.package.lessons_used > invoice.due_lesson:
            return Status.OVERDUE
    elif invoice.due_date < on:
        return Status.OVERDUE
    if paid > 0 or adjusted > 0:
        return Status.PARTIALLY_PAID
    return Status.OPEN


def refresh_invoice(invoice: Invoice, *, on: dt.date | None = None) -> Invoice:
    """Пересчитать кеш сумм и статус по записям. Вызывается под блокировкой
    профиля. Оплачено — задачи закрываются, бухгалтер получает уведомление."""
    invoice = Invoice.objects.select_for_update().select_related("package").get(pk=invoice.pk)
    on = on or today()
    sums = calculate_invoice_balance(invoice)
    previous = invoice.status
    invoice.amount_paid, invoice.amount_adjusted = sums["paid"], sums["adjusted"]
    invoice.status = status_for(invoice, sums["balance"], sums["paid"], sums["adjusted"], on)
    if invoice.status == Status.PAID and invoice.paid_at is None:
        invoice.paid_at = timezone.now()
    elif invoice.status != Status.PAID:
        invoice.paid_at = None
    if invoice.due_lesson and invoice.status != Status.DRAFT:
        # Даты наступления срока и просрочки — история: фиксируются один раз.
        if invoice.due_reached_on is None and invoice.package.lessons_used >= invoice.due_lesson:
            invoice.due_reached_on = on
        if invoice.overdue_since is None and invoice.status == Status.OVERDUE:
            invoice.overdue_since = on
    elif invoice.due_reached_on is None and invoice.status != Status.DRAFT and invoice.due_date <= on:
        invoice.due_reached_on = invoice.due_date
    if invoice.status == Status.OVERDUE and invoice.overdue_since is None:
        invoice.overdue_since = on
    invoice.save(update_fields=["amount_paid", "amount_adjusted", "status", "paid_at", "due_reached_on",
                                "overdue_since", "updated_at"])
    if invoice.status == Status.OVERDUE and previous != Status.OVERDUE:
        notify(
            BillingNotification.Kind.OVERDUE, f"overdue:{invoice.pk}",
            f"Просрочено: {invoice.profile.student} — {invoice.number}",
            f"Остаток {invoice.balance} сом.", recipient=invoice.profile.responsible_accountant,
            profile=invoice.profile, invoice=invoice,
        )
    if invoice.status == Status.PAID and previous != Status.PAID:
        close_tasks(invoice, "Начисление оплачено")
        notify(
            BillingNotification.Kind.INVOICE_PAID, f"paid:{invoice.pk}:{invoice.paid_at:%Y%m%d%H%M%S%f}",
            f"Оплачено: {invoice.profile.student} — {invoice.number}", f"{invoice.amount} сом",
            recipient=invoice.profile.responsible_accountant, profile=invoice.profile, invoice=invoice,
        )
    elif invoice.status in Invoice.UNPAID_STATUSES:
        ensure_task(invoice)
    return invoice


# ---------------------------------------------------------------------------
# Задачи бухгалтера
# ---------------------------------------------------------------------------

def ensure_task(invoice: Invoice) -> BillingTask:
    task = BillingTask.objects.filter(invoice=invoice, status__in=BillingTask.LIVE_STATUSES).first()
    if task is None:
        task = BillingTask.objects.create(
            invoice=invoice, profile=invoice.profile, assignee=invoice.profile.responsible_accountant,
            next_contact_date=today() if invoice.due_lesson else invoice.due_date,
        )
    return task


def close_tasks(invoice: Invoice, reason: str, *, status=BillingTask.Status.DONE) -> int:
    return BillingTask.objects.filter(invoice=invoice, status__in=BillingTask.LIVE_STATUSES).update(
        status=status, close_reason=reason[:200], closed_at=timezone.now(), updated_at=timezone.now(),
    )


# ---------------------------------------------------------------------------
# Пакеты и начисления
# ---------------------------------------------------------------------------

def _due_date(profile: StudentBillingProfile, issue_date: dt.date, *, first: bool) -> dt.date:
    start = max(issue_date, profile.start_date) if first else issue_date
    return start + dt.timedelta(days=profile.plan.payment_due_days)


def _has_pending_terms(profile) -> bool:
    return BillingTermsChange.objects.filter(profile=profile, status=BillingTermsChange.Status.PENDING).exists()


def _create_package(profile: StudentBillingProfile, *, status: str, on_date: dt.date, actor) -> tuple:
    """Новый пакет (учебный месяц) и его начисление. Начисления может не
    быть (None): месяц договора уже оплачен предоплатой за весь курс."""
    if profile.is_course:
        return _create_study_month(profile, status=status, on_date=on_date, actor=actor)
    number = (profile.packages.aggregate(m=Max("number"))["m"] or 0) + 1
    quote = quote_for_profile(profile, on_date)
    package = LessonPackage.objects.create(
        profile=profile, number=number, status=status, lessons_total=quote.lessons, plan_version=quote.version,
        base_price=quote.base_price, custom_price=quote.custom_price, discount_type=quote.discount_type,
        discount_value=quote.discount_value, discount_amount=quote.discount_amount, final_price=quote.final_price,
        pricing_snapshot=quote.snapshot(), created_by=actor if getattr(actor, "is_authenticated", False) else None,
    )
    invoice = _create_invoice(profile, package, amount=quote.final_price, kind=Invoice.Kind.PACKAGE, on_date=on_date,
                              actor=actor, snapshot={**quote.snapshot(), "package_number": number})
    return package, invoice


def _create_invoice(profile, package, *, amount, kind, on_date, actor, snapshot: dict) -> Invoice:
    draft = _has_pending_terms(profile)
    course = profile.is_course
    # Ключ — пакет; перевыставление после аннулирования получает свой номер.
    reissue = Invoice.objects.filter(package=package, status=Status.VOID).count()
    key = f"package:{package.pk}" + (f":r{reissue}" if reissue else "")
    invoice = Invoice.objects.create(
        profile=profile, package=package, kind=kind, business_key=key, amount=amount,
        status=Status.DRAFT if draft else Status.OPEN, issue_date=on_date,
        due_date=on_date if course else _due_date(profile, on_date, first=package.number == 1),
        due_lesson=profile.deadline_lessons if course else None,
        snapshot={
            **snapshot, "student": str(profile.student),
            "subject": str(profile.subject) if profile.subject_id else None,
            "discount_reason": profile.discount_reason,
        },
        created_by=actor if getattr(actor, "is_authenticated", False) else None,
    )
    invoice.number = f"INV-{on_date:%Y}-{invoice.pk:06d}"
    invoice.save(update_fields=["number"])
    audit.log(actor, invoice, "billing_invoice_create", new={
        "profile": profile.pk, "package": package.pk, "number": package.number, "kind": kind, "amount": invoice.amount,
        "status": invoice.status, "due_date": invoice.due_date, "due_lesson": invoice.due_lesson,
    })
    return invoice


def _create_study_month(profile: StudentBillingProfile, *, status: str, on_date: dt.date, actor) -> tuple:
    from .contracts import month_charge, months_created
    from .pricing import plan_version_on

    month_number = months_created(profile) + 1
    if month_number > profile.duration_months:
        raise BillingError("Все учебные месяцы договора уже созданы — курс завершается.", code="course_finished")
    number = (profile.packages.aggregate(m=Max("number"))["m"] or 0) + 1
    amount, kind = month_charge(profile, month_number)
    month_price = money(profile.month_price)
    snapshot = {
        "contract": profile.pk, "plan": profile.plan.name, "plan_id": profile.plan_id, "month_number": month_number,
        "duration_months": profile.duration_months, "lessons": profile.lessons_per_month,
        "month_price": str(month_price), "standard_course_price": str(profile.standard_course_price),
        "final_course_price": str(profile.final_course_price), "discount_amount": str(profile.discount_amount),
        "payment_mode": profile.payment_mode, "charge": str(amount), "kind": kind,
    }
    if kind == Invoice.Kind.COURSE:
        discount = money(profile.discount_amount)
    else:
        discount = max(month_price - amount, ZERO) if amount else ZERO
    package = LessonPackage.objects.create(
        profile=profile, number=number, month_number=month_number, status=status,
        lessons_total=profile.lessons_per_month, plan_version=plan_version_on(profile.plan, on_date),
        base_price=month_price, discount_amount=discount, final_price=amount, pricing_snapshot=snapshot,
        created_by=actor if getattr(actor, "is_authenticated", False) else None,
    )
    audit.log(actor, package, "billing_month_create", new={
        "profile": profile.pk, "month_number": month_number, "lessons": package.lessons_total, "status": status,
    })
    if amount <= 0:
        return package, None
    invoice = _create_invoice(profile, package, amount=amount, kind=kind, on_date=on_date, actor=actor,
                              snapshot={**snapshot, "package_number": number})
    return package, invoice


def _after_invoice_created(profile, invoice: Invoice, *, actor) -> Invoice:
    from .payments import apply_available_credit

    if invoice is None or invoice.status == Status.DRAFT:
        return invoice
    apply_available_credit(profile, actor=actor, locked=True, system=True)
    invoice = refresh_invoice(invoice)
    due = (f"срок — {invoice.due_lesson}-й урок месяца" if invoice.due_lesson
           else f"срок {invoice.due_date:%d.%m.%Y}")
    what = (f"Учебный месяц №{invoice.package.month_number}" if invoice.package.month_number
            else f"Пакет №{invoice.package.number}")
    notify(
        BillingNotification.Kind.INVOICE_CREATED, f"invoice:{invoice.pk}",
        f"Начисление {invoice.number}: {profile.student}",
        f"{what}, {invoice.amount} сом, {due}. Статус: {invoice.get_status_display()}.",
        recipient=profile.responsible_accountant, profile=profile, invoice=invoice,
    )
    return invoice


def is_continuing(profile: StudentBillingProfile) -> bool:
    """Студент активен и продолжает обучение — будущие пакеты выставляются."""
    from apps.academy.models import Student

    return profile.status == StudentBillingProfile.Status.ACTIVE and profile.student.status == Student.Status.ACTIVE


def create_first_package(profile: StudentBillingProfile, *, actor, on_date: dt.date | None = None):
    """Первый пакет при регистрации: сразу текущий, с начислением."""
    package, invoice = _create_package(profile, status=PackageStatus.ACTIVE, on_date=on_date or today(), actor=actor)
    invoice = _after_invoice_created(profile, invoice, actor=actor)
    return package, invoice


def next_planned_package(profile) -> LessonPackage | None:
    return profile.packages.filter(status=PackageStatus.PLANNED).order_by("number").first()


def create_next_package_invoice(profile: StudentBillingProfile, *, actor=None, on_date: dt.date | None = None,
                                activate: bool = False, for_held_lesson: bool = False):
    """Следующий пакет и начисление. Возвращает (пакет, начисление, создан).

    Идемпотентно: если следующий пакет уже есть (оплачен вперёд или
    выставлен заранее) — возвращается он (при `activate` и отсутствии
    текущего — становится текущим), повторного начисления нет.

    `for_held_lesson` — пакет нужен под уже проведённый урок, когда
    студент ещё учился (поздняя обработка): проверка «продолжает обучение»
    не применяется, урок всё равно подлежит оплате."""
    from ..permissions import authorize

    authorize(actor, "create_invoice")
    on_date = on_date or today()
    with transaction.atomic():
        profile = lock_profile(profile)
        active = profile.packages.filter(status=PackageStatus.ACTIVE).first()
        has_active = active is not None
        if activate and active is not None:
            # Текущий пакет уже идёт — следующий цикл начат, повтора нет.
            return active, active.invoices.exclude(status=Status.VOID).first(), False
        planned = next_planned_package(profile)
        if planned is not None:
            if activate and not has_active:
                activate_package(planned)
            return planned, planned.invoices.exclude(status=Status.VOID).first(), False
        if not for_held_lesson and not is_continuing(profile):
            raise BillingError("Студент не продолжает обучение — следующий пакет не выставляется.", code="not_continuing")
        if profile.is_course and course_finished(profile):
            raise BillingError("Все учебные месяцы договора пройдены.", code="course_finished")
        status = PackageStatus.ACTIVE if activate and not has_active else PackageStatus.PLANNED
        package, invoice = _create_package(profile, status=status, on_date=on_date, actor=actor)
        invoice = _after_invoice_created(profile, invoice, actor=actor)
    return package, invoice, True


def course_finished(profile) -> bool:
    from .contracts import months_created

    return bool(profile.is_course and months_created(profile) >= profile.duration_months)


def activate_package(package: LessonPackage) -> LessonPackage:
    package.status = PackageStatus.ACTIVE
    package.save(update_fields=["status", "updated_at"])
    return package


def ensure_future_packages(profile: StudentBillingProfile, count: int, *, actor, on_date: dt.date | None = None) -> list:
    """Предоплата нескольких пакетов: обеспечить `count` следующих пакетов
    (PLANNED) с начислениями. Уже существующие не дублируются. Вызывается
    под блокировкой профиля; деньги распределяет вызывающий."""
    created = []
    if count <= 0:
        return created
    if not is_continuing(profile):
        raise BillingError("Студент не продолжает обучение — оплата вперёд невозможна.", code="not_continuing")
    max_ahead = int(getattr(settings, "BILLING_MAX_PREPAID_PACKAGES", 12))
    if count > max_ahead:
        raise BillingError(f"Оплатить вперёд можно не больше {max_ahead} пакетов.", code="too_many_packages")
    while profile.packages.filter(status=PackageStatus.PLANNED).count() < count:
        if course_finished(profile):
            raise BillingError("Больше месяцев, чем осталось в договоре.", code="too_many_packages")
        package, invoice = _create_package(profile, status=PackageStatus.PLANNED, on_date=on_date or today(), actor=actor)
        if invoice is not None:
            created.append(invoice)
    return created


# ---------------------------------------------------------------------------
# Просрочки, корректировки, аннулирование
# ---------------------------------------------------------------------------

def mark_overdue_invoices(on: dt.date | None = None) -> list[int]:
    """OPEN / PARTIALLY_PAID со сроком раньше `on` и остатком — OVERDUE.
    Повторный запуск в тот же день ничего не меняет и не дублирует
    уведомления (ключ — начисление)."""
    on = on or today()
    ids = list(
        Invoice.objects.filter(status__in=(Status.OPEN, Status.PARTIALLY_PAID))
        .filter(Q(due_lesson__isnull=True, due_date__lt=on)
                | Q(due_lesson__isnull=False, package__lessons_used__gt=F("due_lesson")))
        .values_list("pk", "profile_id")
    )
    marked = []
    for invoice_id, profile_id in ids:
        with transaction.atomic():
            profile = lock_profile(profile_id)
            invoice = refresh_invoice(Invoice.objects.get(pk=invoice_id), on=on)
            if invoice.status == Status.OVERDUE:
                marked.append(invoice.pk)  # уведомление — в refresh_invoice (одно на начисление)
    return marked


def adjust_invoice(invoice: Invoice, *, actor, amount, reason: str) -> InvoiceAdjustment:
    """Корректировка (списание долга / перерасчёт) — уменьшает остаток, не
    меняя сумму начисления."""
    from ..permissions import authorize

    authorize(actor, "adjust_invoice")
    reason = (reason or "").strip()
    if not reason:
        raise BillingError("Укажите основание корректировки.", code="reason_required")
    amount = Decimal(str(amount))
    if amount <= 0:
        raise BillingError("Сумма корректировки должна быть больше нуля.", code="invalid_amount")
    with transaction.atomic():
        lock_profile(invoice.profile_id)
        invoice = Invoice.objects.select_for_update().get(pk=invoice.pk)
        if invoice.status in (Status.VOID, Status.DRAFT):
            raise BillingError("Корректировать можно только выставленное начисление.", code="bad_status")
        if amount > calculate_invoice_balance(invoice)["balance"]:
            raise BillingError("Корректировка больше остатка начисления.", code="exceeds_balance")
        adjustment = InvoiceAdjustment.objects.create(invoice=invoice, amount=amount, reason=reason, created_by=actor)
        audit.log(actor, adjustment, "billing_adjustment", new={"invoice": invoice.pk, "amount": amount}, reason=reason)
        refresh_invoice(invoice)
    return adjustment


def void_adjustment(adjustment: InvoiceAdjustment, *, actor, reason: str) -> InvoiceAdjustment:
    from ..permissions import authorize

    authorize(actor, "adjust_invoice")
    if not (reason or "").strip():
        raise BillingError("Укажите причину отмены.", code="reason_required")
    with transaction.atomic():
        lock_profile(adjustment.invoice.profile_id)
        adjustment = InvoiceAdjustment.objects.select_for_update().get(pk=adjustment.pk)
        if adjustment.status != InvoiceAdjustment.Status.APPLIED:
            raise BillingError("Корректировка уже отменена.", code="bad_status")
        adjustment.status = InvoiceAdjustment.Status.VOID
        adjustment.voided_by, adjustment.voided_at, adjustment.void_reason = actor, timezone.now(), reason.strip()
        adjustment.save()
        audit.log(actor, adjustment, "billing_adjustment_void", reason=reason)
        refresh_invoice(adjustment.invoice)
    return adjustment


def void_invoice(invoice: Invoice, *, actor, reason: str, system: bool = False, cancel_package: bool = True) -> Invoice:
    """Аннулировать начисление. Оплата по нему сначала возвращается в аванс
    (сторно распределений). Не начатый пакет отменяется вместе с ним; у
    начатого пакета уроки уже списаны — аннулирование не разрешено,
    используйте корректировку."""
    from ..permissions import authorize
    from .payments import reverse_allocation_locked

    if not system:
        authorize(actor, "void_invoice")
    reason = (reason or "").strip()
    if not reason:
        raise BillingError("Укажите причину аннулирования.", code="reason_required")
    with transaction.atomic():
        lock_profile(invoice.profile_id)
        invoice = Invoice.objects.select_for_update().select_related("package").get(pk=invoice.pk)
        if invoice.status == Status.VOID:
            raise BillingError("Начисление уже аннулировано.", code="bad_status")
        package = invoice.package
        if package.lessons_used > 0 or package.status == PackageStatus.COMPLETED:
            raise BillingError(
                "По пакету уже списаны уроки — аннулировать нельзя, оформите корректировку.", code="package_started",
            )
        if invoice.adjustments.filter(status=InvoiceAdjustment.Status.APPLIED).exists():
            raise BillingError("Сначала отмените корректировки начисления.", code="has_adjustments")
        for allocation in invoice.allocations.filter(status=PaymentAllocation.Status.ACTIVE):
            reverse_allocation_locked(allocation, actor=actor, reason=f"Аннулирование начисления: {reason}")
        old = {"status": invoice.status, "amount_paid": invoice.amount_paid}
        invoice = Invoice.objects.select_for_update().get(pk=invoice.pk)
        invoice.status = Status.VOID
        invoice.void_reason, invoice.voided_at = reason, timezone.now()
        invoice.voided_by = actor if getattr(actor, "is_authenticated", False) else None
        invoice.amount_paid = ZERO
        invoice.save()
        close_tasks(invoice, "Начисление аннулировано", status=BillingTask.Status.CANCELLED)
        if cancel_package:
            package.status = PackageStatus.CANCELLED
            package.save(update_fields=["status", "updated_at"])
        audit.log(actor, invoice, "billing_invoice_void", old=old, new={"status": invoice.status}, reason=reason)
    return invoice


def issue_drafts(profile: StudentBillingProfile, *, actor) -> list[Invoice]:
    """После решения по условиям: черновики профиля пересчитываются по
    действующим условиям (деньги по ним ещё не принимались) и выставляются."""
    issued = []
    for invoice in profile.invoices.filter(status=Status.DRAFT).select_related("package").order_by("package__number"):
        package = invoice.package
        if profile.is_course:
            from .contracts import month_charge

            old = {"amount": invoice.amount, "status": invoice.status}
            amount, kind = month_charge(profile, package.month_number, exclude_invoice_id=invoice.pk)
            package.final_price = amount
            package.pricing_snapshot = {**package.pricing_snapshot, "charge": str(amount),
                                        "final_course_price": str(profile.final_course_price),
                                        "discount_amount": str(profile.discount_amount)}
            package.save()
            invoice.amount, invoice.kind, invoice.status = amount, kind, Status.OPEN
            invoice.snapshot = {**invoice.snapshot, **package.pricing_snapshot, "discount_reason": profile.discount_reason}
            invoice.save()
            audit.log(actor, invoice, "billing_invoice_issue", old=old,
                      new={"amount": invoice.amount, "status": invoice.status})
            issued.append(_after_invoice_created(profile, invoice, actor=actor))
            continue
        quote = quote_for_profile(profile, invoice.issue_date)
        old = {"amount": invoice.amount, "status": invoice.status}
        for field in ("base_price", "custom_price", "discount_type", "discount_value", "discount_amount", "final_price"):
            setattr(package, field, getattr(quote, field))
        if package.lessons_used <= quote.lessons:
            package.lessons_total = quote.lessons
        package.plan_version, package.pricing_snapshot = quote.version, quote.snapshot()
        package.save()
        invoice.amount = quote.final_price
        invoice.snapshot = {**invoice.snapshot, **quote.snapshot(), "discount_reason": profile.discount_reason}
        invoice.status = Status.OPEN
        invoice.save()
        audit.log(actor, invoice, "billing_invoice_issue", old=old, new={"amount": invoice.amount, "status": invoice.status})
        issued.append(_after_invoice_created(profile, invoice, actor=actor))
    return issued


def due_soon_q(on: dt.date, days: int) -> Q:
    return Q(status__in=(Status.OPEN, Status.PARTIALLY_PAID), due_date__gte=on, due_date__lte=on + dt.timedelta(days=days))
