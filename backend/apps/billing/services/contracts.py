"""Договор по программе: стоимость курса, учебные месяцы, сводка денег.

Программа (`BillingPlan` с `duration_months`) задаёт стандартные условия:
цена учебного месяца и уроков приоритетного предмета в нём (версия тарифа),
число месяцев, срок оплаты (урок № месяца). Договор студента
(`StudentBillingProfile`) при оформлении получает их снимок — изменение
тарифа уже оформленный договор не меняет.

Скидка — не процент: академия задаёт итоговую стоимость курса,
скидка = стандартная − итоговая (не отрицательна, итоговая ≥ 0).

Начисление за учебный месяц k (из N):

    осталось начислить = итоговая стоимость − Σ действующих начислений договора
    помесячно:  осталось начислить / (N − k + 1), округление вниз до тыйына,
                последний месяц — точный остаток (Σ месяцев = итоговой цене);
    предоплата: месяц 1 — вся итоговая стоимость (начисление «Весь курс»),
                месяцы 2…N — без начисления (уже оплачены по договору).

Формула от остатка, а не от цены месяца, поэтому изменение итоговой
стоимости в середине курса меняет только будущие месяцы, а уже выставленные
начисления остаются как есть (снимок).

Сводка денег договора считается из записей (начисления, распределения,
корректировки, журнал аванса), а не хранится отдельно. Каждое понятие — своё
поле, одна сумма не попадает в два места:

    получено (received)            = Σ подтверждённых платежей (по дате денег)
    возвращено (refunded)          = Σ подтверждённых возвратов
    распределено (allocated)       = Σ действующих распределений на начисления
                                     = «оплачено по начислениям»
    свободный аванс (credit)       = Σ журнала аванса
                                     = получено − возвраты − распределено − удержания брони
    деньги по договору (paid_total)= распределено + свободный аванс
    начислено (invoiced)           = Σ действующих начислений
    остаток начислений (invoices_balance)
                                   = Σ (сумма − оплачено − корректировки) неоплаченных
    применимый аванс (credit_applicable)
                                   = аванс, который правила договора разрешают
                                     направить на эти начисления (бронь «в общую
                                     стоимость» — только на «Весь курс» / последний месяц)
    к оплате сейчас (due_now)      = max(остаток начислений − применимый аванс, 0)
    просрочено (overdue)           = max(остаток просроченных − применимый аванс, 0)
    остаток по договору (outstanding)
                                   = max(итоговая − распределено − аванс − корректировки, 0)
    будущие периоды (future)       = max(итоговая − начислено, 0) — ещё не выставлено,
                                     не долг и не просрочка

Свободный аванс рядом с неоплаченным начислением — несогласованное состояние
(`credit_unapplied` > 0): платёж записан без распределения. Сервис платежей
больше так не делает; старые записи исправляет `billing_money_audit --apply`.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from decimal import ROUND_DOWN, Decimal

from django.db.models import Q, Sum

from apps.accounting.models import StudentPayment
from apps.accounting.services.money import money

from ..models import (
    CreditLedgerEntry,
    Invoice,
    InvoiceAdjustment,
    LessonPackage,
    PaymentAllocation,
    PaymentMode,
    ReservationAllocation,
    StudentBillingProfile,
)
from . import BillingError

ZERO = Decimal("0.00")
CENT = Decimal("0.01")


def to_money(value, field: str = "сумма") -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        amount = Decimal(str(value))
    except Exception:  # noqa: BLE001
        raise BillingError(f"Некорректное число: {field}.", code="invalid_amount")
    if amount != amount.quantize(CENT):
        raise BillingError(f"{field.capitalize()} — не точнее тыйына (0.01).", code="invalid_amount")
    return amount


# ---------------------------------------------------------------------------
# Стандартные условия программы и итоговая стоимость
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CourseQuote:
    month_price: Decimal
    lessons_per_month: int
    duration_months: int
    deadline_lessons: int
    plan_version_id: int

    @property
    def standard_course_price(self) -> Decimal:
        return money(self.month_price * self.duration_months)


def course_quote(plan, on_date: dt.date) -> CourseQuote:
    from .pricing import plan_version_on

    if not plan.duration_months:
        raise BillingError("У программы не задана продолжительность.", code="not_course")
    version = plan_version_on(plan, on_date)
    return CourseQuote(
        month_price=version.package_price, lessons_per_month=version.lessons_per_package,
        duration_months=plan.duration_months, deadline_lessons=min(plan.payment_deadline_lessons,
                                                                  version.lessons_per_package),
        plan_version_id=version.pk,
    )


def course_terms(*, standard_price: Decimal, discount_enabled: bool, final_price, reason: str = "") -> tuple:
    """Проверить итоговую стоимость; вернуть (итоговая, скидка в сомах).

    Без скидки итоговая = стандартная. Со скидкой — итоговая обязательна,
    0 ≤ итоговая < стандартной, основание обязательно."""
    standard = money(standard_price)
    final = to_money(final_price, "итоговая стоимость курса")
    if not discount_enabled:
        if final is not None and final != standard:
            raise BillingError(
                "Итоговая стоимость отличается от стандартной — отметьте «Скидка предоставлена» и укажите причину.",
                code="invalid_discount",
            )
        return standard, ZERO
    if final is None:
        raise BillingError("Укажите итоговую стоимость курса.", code="invalid_discount")
    if final < 0:
        raise BillingError("Итоговая стоимость курса не может быть отрицательной.", code="invalid_discount")
    if final >= standard:
        raise BillingError("Итоговая стоимость со скидкой должна быть меньше стандартной.", code="invalid_discount")
    if not (reason or "").strip():
        raise BillingError("Укажите причину скидки.", code="reason_required")
    return final, money(standard - final)


# ---------------------------------------------------------------------------
# Учебные месяцы и начисления по ним
# ---------------------------------------------------------------------------

def live_packages(profile):
    return profile.packages.exclude(status=LessonPackage.Status.CANCELLED)


def months_created(profile) -> int:
    return live_packages(profile).count()


def invoiced_total(profile, *, exclude_invoice_id: int | None = None) -> Decimal:
    qs = Invoice.objects.filter(profile=profile).exclude(status=Invoice.Status.VOID)
    if exclude_invoice_id:
        qs = qs.exclude(pk=exclude_invoice_id)
    return qs.aggregate(s=Sum("amount"))["s"] or ZERO


def month_charge(profile: StudentBillingProfile, month_number: int, *,
                 exclude_invoice_id: int | None = None) -> tuple[Decimal, str]:
    """Сумма и вид начисления за учебный месяц `month_number` (см. модуль)."""
    duration = profile.duration_months
    if month_number > duration:
        return ZERO, Invoice.Kind.MONTH
    remaining = max(money(profile.final_course_price) - invoiced_total(profile, exclude_invoice_id=exclude_invoice_id),
                    ZERO)
    if profile.payment_mode == PaymentMode.FULL_PREPAY:
        return remaining, (Invoice.Kind.COURSE if month_number == 1 else Invoice.Kind.MONTH)
    months_left = duration - month_number + 1
    if months_left <= 1:
        return remaining, Invoice.Kind.MONTH
    share = (remaining / months_left).quantize(CENT, rounding=ROUND_DOWN)
    return share, Invoice.Kind.MONTH


def is_final_month(profile, package: LessonPackage) -> bool:
    return bool(profile.duration_months and package.month_number and package.month_number >= profile.duration_months)


def may_fund(profile, payment: StudentPayment, invoice: Invoice) -> bool:
    """Может ли автоматическое распределение направить деньги платежа на
    начисление. Бронь в режиме «в общую стоимость курса» — депозит договора:
    закрывает только начисление последнего месяца (или «Весь курс»), а не
    текущие месяцы. Ручное распределение бухгалтером не ограничено."""
    if (profile.reservation_allocation != ReservationAllocation.COURSE_TOTAL or not profile.is_course
            or payment.purpose != StudentPayment.Purpose.RESERVATION):
        return True
    return invoice.kind == Invoice.Kind.COURSE or is_final_month(profile, invoice.package)


# ---------------------------------------------------------------------------
# Стадия оплаты начисления
# ---------------------------------------------------------------------------

def payment_stage(invoice: Invoice, lessons_used: int | None = None) -> str:
    """awaiting — ожидается оплата; deadline — сегодняшний урок последний
    срок; overdue — просрочка; paid; draft; void."""
    if invoice.status == Invoice.Status.VOID:
        return "void"
    if invoice.status == Invoice.Status.DRAFT:
        return "draft"
    if invoice.status == Invoice.Status.PAID:
        return "paid"
    if invoice.status == Invoice.Status.OVERDUE:
        return "overdue"
    if invoice.due_lesson:
        used = invoice.package.lessons_used if lessons_used is None else lessons_used
        if used == invoice.due_lesson:
            return "deadline"
    return "awaiting"


# ---------------------------------------------------------------------------
# Сводка денег договора
# ---------------------------------------------------------------------------

def applicable_credit(profile: StudentBillingProfile, unpaid: list[Invoice], credit: Decimal) -> Decimal:
    """Сколько свободного аванса можно направить на `unpaid` по правилам
    договора (как `may_fund`): бронь в режиме «в общую стоимость курса» —
    только на «Весь курс» или последний месяц."""
    if credit <= 0:
        return ZERO
    if not (profile.is_course and profile.reservation_allocation == ReservationAllocation.COURSE_TOTAL):
        return credit
    held = max(CreditLedgerEntry.objects.filter(
        profile=profile, payment__purpose=StudentPayment.Purpose.RESERVATION,
    ).aggregate(s=Sum("amount"))["s"] or ZERO, ZERO)
    held = min(held, credit)
    eligible = sum((i.balance for i in unpaid
                    if i.kind == Invoice.Kind.COURSE or is_final_month(profile, i.package)), ZERO)
    return credit - held + min(held, eligible)


def money_summary(profile: StudentBillingProfile) -> dict:
    """Деньги договора из записей (см. модуль). Суммы — Decimal."""
    allocated = PaymentAllocation.objects.filter(
        profile=profile, status=PaymentAllocation.Status.ACTIVE,
    ).aggregate(s=Sum("amount"))["s"] or ZERO
    adjusted = InvoiceAdjustment.objects.filter(
        invoice__profile=profile, status=InvoiceAdjustment.Status.APPLIED,
    ).aggregate(s=Sum("amount"))["s"] or ZERO
    credit = CreditLedgerEntry.objects.filter(profile=profile).aggregate(s=Sum("amount"))["s"] or ZERO
    payments = StudentPayment.objects.filter(billing_profile=profile, status=StudentPayment.Status.CONFIRMED)
    received = payments.filter(kind=StudentPayment.Kind.PAYMENT).aggregate(s=Sum("amount"))["s"] or ZERO
    refunded = payments.filter(kind=StudentPayment.Kind.REFUND).aggregate(s=Sum("amount"))["s"] or ZERO
    reservation_received = payments.filter(
        kind=StudentPayment.Kind.PAYMENT, purpose=StudentPayment.Purpose.RESERVATION,
    ).aggregate(s=Sum("amount"))["s"] or ZERO
    # Нераспределённый остаток платежей брони — депозит договора (режим
    # «в общую стоимость») или аванс.
    reservation_free = CreditLedgerEntry.objects.filter(
        profile=profile, payment__purpose=StudentPayment.Purpose.RESERVATION,
    ).aggregate(s=Sum("amount"))["s"] or ZERO
    unpaid = list(Invoice.objects.filter(profile=profile, status__in=Invoice.UNPAID_STATUSES).select_related("package"))
    balance = sum((i.balance for i in unpaid), ZERO)
    overdue_balance = sum((i.balance for i in unpaid if i.status == Invoice.Status.OVERDUE), ZERO)
    usable = applicable_credit(profile, unpaid, credit)
    unapplied = min(usable, balance)
    due_now = max(balance - usable, ZERO)
    result = {
        "received": money(received), "refunded": money(refunded), "net_received": money(received - refunded),
        "reservation_received": money(reservation_received), "reservation_unused": money(max(reservation_free, ZERO)),
        "allocated": money(allocated), "adjusted": money(adjusted), "credit": money(credit),
        "invoiced": money(invoiced_total(profile)), "invoices_balance": money(balance),
        "credit_applicable": money(usable), "credit_unapplied": money(unapplied),
        "due_now": money(due_now), "overdue": money(max(overdue_balance - usable, ZERO)),
        "paid_total": money(allocated + credit),
    }
    if profile.final_course_price is not None and profile.status == StudentBillingProfile.Status.INACTIVE:
        # Начисления остановлены (ушёл): будущие месяцы — не долг, только наступившие.
        result.update({
            "standard_course_price": money(profile.standard_course_price),
            "final_course_price": money(profile.final_course_price),
            "discount_amount": money(profile.discount_amount), "outstanding": money(due_now), "future": ZERO,
        })
    elif profile.final_course_price is not None:
        final = money(profile.final_course_price)
        result.update({
            "standard_course_price": money(profile.standard_course_price),
            "final_course_price": final,
            "discount_amount": money(profile.discount_amount),
            "outstanding": money(max(final - allocated - credit - adjusted, ZERO)),
            "future": money(max(final - invoiced_total(profile), ZERO)),
        })
    else:
        result.update({"standard_course_price": None, "final_course_price": None, "discount_amount": ZERO,
                       "outstanding": money(due_now), "future": None})
    return result


def current_month(profile) -> LessonPackage | None:
    packages = live_packages(profile)
    return (packages.filter(status=LessonPackage.Status.ACTIVE).first()
            or packages.filter(status=LessonPackage.Status.COMPLETED).order_by("-number").first())


def next_month_cost(profile) -> dict | None:
    """Стоимость следующего учебного месяца и сколько из неё ещё не покрыто
    (для «Скоро оплата»). None — следующего месяца нет (курс кончается)."""
    from .ledger import credit_balance

    current = profile.packages.filter(status=LessonPackage.Status.ACTIVE).first()
    if current is None:
        return None
    planned = profile.packages.filter(status=LessonPackage.Status.PLANNED).order_by("number").first()
    if planned is not None:  # следующий месяц уже выставлен (оплачен вперёд / заранее)
        invoice = planned.invoices.exclude(status=Invoice.Status.VOID).first()
        balance = invoice.balance if invoice and invoice.status in Invoice.UNPAID_STATUSES else ZERO
        cost = invoice.amount if invoice else ZERO
        return {"month_number": planned.month_number or planned.number, "cost": money(cost),
                "covered": money(cost - balance), "to_pay": money(balance)}
    if profile.is_course:
        number = (current.month_number or 0) + 1
        if number > profile.duration_months:
            return None
        cost, _kind = month_charge(profile, number)
        final_next = number >= profile.duration_months
    else:
        from .pricing import quote_for_profile
        cost, number, final_next = quote_for_profile(profile, dt.date.today()).final_price, current.number + 1, True
    credit = credit_balance(profile.pk)
    if profile.is_course and not final_next and profile.reservation_allocation == ReservationAllocation.COURSE_TOTAL:
        credit -= CreditLedgerEntry.objects.filter(
            profile=profile, payment__purpose=StudentPayment.Purpose.RESERVATION,
        ).aggregate(s=Sum("amount"))["s"] or ZERO
    # Долг по текущим начислениям аванс закроет раньше следующего месяца.
    credit -= sum((i.balance for i in profile.invoices.filter(status__in=Invoice.UNPAID_STATUSES)), ZERO)
    covered = min(max(credit, ZERO), cost)
    return {"month_number": number, "cost": money(cost), "covered": money(covered), "to_pay": money(cost - covered)}


def contract_q_active() -> Q:
    return Q(status__in=(StudentBillingProfile.Status.ACTIVE, StudentBillingProfile.Status.PAUSED))
