"""Договор по программе: стоимость курса, учебные месяцы, сводка денег.

Программа (`BillingPlan` с `duration_months`) задаёт стандартные условия:
цена учебного месяца и уроков приоритетного предмета в нём (версия тарифа),
число месяцев, срок оплаты (урок № месяца). Договор студента
(`StudentBillingProfile`) при оформлении получает их снимок — изменение
тарифа уже оформленный договор не меняет.

Скидка — не процент: академия задаёт итоговую стоимость курса,
скидка = стандартная − итоговая (не отрицательна, итоговая ≥ 0).

Начисление за учебный месяц k (из N) — если у договора есть план месяцев
(`ContractMonthPrice`, `services.month_plan`), сумма месяца берётся из плана;
иначе — прежнее правило:

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
    аванс на будущие начисления (credit_reserved_future)
                                   = min(аванс, оставшийся после текущих начислений, будущие)
                                     — ПРОГНОЗ: деньги остаются свободным авансом и
                                     распределяются, когда месяц будет выставлен
    свободный аванс сверх будущих (credit_unreserved) = аванс − текущий долг, покрытый
                                     авансом, − аванс на будущие (переплата сверх договора)
    осталось оплатить (net_to_pay) = остаток по договору (= текущий долг + будущие −
                                     весь аванс; ноль, если аванс всё покрывает)
    сторнировано (voided)          = Σ сторнированных платежей — справочно, в «получено»
                                     не входит (сторно ≠ возврат денег)

Свободный аванс рядом с неоплаченным начислением — несогласованное состояние
(`credit_unapplied` > 0): платёж записан без распределения. Сервис платежей
больше так не делает; старые записи исправляет `billing_money_audit --apply`.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from decimal import ROUND_DOWN, Decimal

from django.db.models import Count, Q, Sum
from django.utils import timezone

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
    if profile.month_plan_mode:
        # План договора (`ContractMonthPrice`): сумма месяца задана планом;
        # больше остатка итоговой стоимости не начисляется никогда.
        row = profile.month_prices.filter(month_number=month_number).first()
        if row is not None:
            return min(money(row.amount), remaining), Invoice.Kind.MONTH
    months_left = duration - month_number + 1
    if months_left <= 1:
        return remaining, Invoice.Kind.MONTH
    share = (remaining / months_left).quantize(CENT, rounding=ROUND_DOWN)
    return share, Invoice.Kind.MONTH


def course_invoice(profile) -> Invoice | None:
    """Действующее начисление «Весь курс» (предоплата за весь курс)."""
    if not profile.is_course:
        return None
    return (Invoice.objects.filter(profile=profile, kind=Invoice.Kind.COURSE).exclude(status=Invoice.Status.VOID)
            .select_related("package").order_by("pk").first())


def course_month_shares(profile, total: Decimal) -> dict[int, Decimal]:
    """Доля суммы «Весь курс» на каждый учебный месяц: по плану стоимости
    месяцев договора (если он сходится с суммой), иначе поровну (остаток
    тыйынов — по методу наибольших остатков). Это разбивка одного уже
    выставленного начисления — для графика и карточки, не новое начисление."""
    from .month_plan import distribute

    n = profile.duration_months
    plan = {r.month_number: money(r.amount) for r in profile.month_prices.all()} if profile.month_plan_mode else {}
    if set(plan) == set(range(1, n + 1)) and sum(plan.values(), ZERO) == money(total):
        return dict(sorted(plan.items()))
    return dict(zip(range(1, n + 1), distribute([Decimal(1)] * n, money(total))))


def course_coverage(profile) -> dict | None:
    """Предоплата за весь курс: начисление «Весь курс» и какие учебные месяцы
    закрыты его оплатой (деньги начисления идут на месяцы по порядку).
    None — у договора нет начисления «Весь курс»."""
    invoice = course_invoice(profile)
    if invoice is None:
        return None
    left = invoice.amount_paid + invoice.amount_adjusted if invoice.status != Invoice.Status.DRAFT else ZERO
    months = {}
    for month, share in course_month_shares(profile, invoice.amount).items():
        paid = min(share, max(left, ZERO))
        left -= paid
        months[month] = {"share": share, "paid": money(paid)}
    return {"invoice": invoice, "months": months, "paid_in_full": invoice.status == Invoice.Status.PAID}


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

def payment_stage(invoice: Invoice, lessons_used: int | None = None, on: dt.date | None = None) -> str:
    """Стадия оплаты начисления — по актуальным данным, а не по сохранённому
    статусу (его обновляют уроки и фоновая задача, он может отставать):

    * paid — остаток 0 (оплачено распределениями / корректировками);
    * срок в уроках (`due_lesson`): до него — awaiting, на уроке-сроке —
      deadline, после — overdue;
    * срок датой (`due_date`): раньше даты — awaiting, в день срока —
      deadline, после — overdue. «Сегодня» — по часовому поясу проекта
      (`timezone.localdate`, Asia/Bishkek).

    Единый источник для очередей «Скоро оплата» / «К оплате» / «Просроченные»,
    их счётчиков, строки студента и карточки."""
    if invoice.status == Invoice.Status.VOID:
        return "void"
    if invoice.status == Invoice.Status.DRAFT:
        return "draft"
    if invoice.status == Invoice.Status.PAID or invoice.balance <= 0:
        return "paid"
    if invoice.due_lesson:
        used = invoice.package.lessons_used if lessons_used is None else lessons_used
        if used > invoice.due_lesson:
            return "overdue"
        return "deadline" if used == invoice.due_lesson else "awaiting"
    on = on or timezone.localdate()
    if invoice.due_date < on:
        return "overdue"
    return "deadline" if invoice.due_date == on else "awaiting"


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
    overdue_balance = sum((i.balance for i in unpaid if payment_stage(i) == "overdue"), ZERO)
    usable = applicable_credit(profile, unpaid, credit)
    unapplied = min(usable, balance)
    due_now = max(balance - usable, ZERO)
    voided = StudentPayment.objects.filter(billing_profile=profile, status=StudentPayment.Status.VOID,
                                           kind=StudentPayment.Kind.PAYMENT).aggregate(s=Sum("amount"), n=Count("pk"))
    future_amount = (max(money(profile.final_course_price) - invoiced_total(profile), ZERO)
                     if profile.final_course_price is not None
                     and profile.status != StudentBillingProfile.Status.INACTIVE else ZERO)
    reserved = min(max(usable - balance, ZERO), future_amount)
    result = {
        "voided": money(voided["s"] or ZERO), "voided_count": voided["n"],
        "credit_reserved_future": money(reserved),
        "credit_unreserved": money(max(credit - unapplied - reserved, ZERO)),
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
    result["net_to_pay"] = result["outstanding"]
    # «Курс полностью оплачен»: итоговая стоимость покрыта, наступившего и
    # будущего долга нет — дополнительные платежи не требуются.
    result["course_paid_in_full"] = bool(
        profile.final_course_price is not None and profile.final_course_price > 0
        and result["outstanding"] == 0 and result["due_now"] == 0)
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
        # issued — начисление следующего месяца уже выставлено (срок оплаты наступил):
        # студент в «К оплате», не в «Скоро оплата».
        return {"month_number": planned.month_number or planned.number, "cost": money(cost),
                "covered": money(cost - balance), "to_pay": money(balance), "issued": invoice is not None}
    coverage = None
    if profile.is_course:
        number = (current.month_number or 0) + 1
        if number > profile.duration_months:
            return None
        cost, _kind = month_charge(profile, number)
        final_next = number >= profile.duration_months
        coverage = course_coverage(profile)
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
    if coverage is not None:
        # Предоплата за весь курс: месяц стоит свою долю «Весь курс». Оплаченная
        # часть доли уже закрыта этим начислением, неоплаченная — долг по нему
        # (он уже в «К оплате», второй раз не считается). К оплате за месяц —
        # только доплата сверх «Весь курс» (`cost`, после повышения цены).
        month = coverage["months"].get(number, {"share": ZERO, "paid": ZERO})
        extra_covered = min(max(credit, ZERO), cost)
        return {"month_number": number, "cost": money(month["share"] + cost),
                "covered": money(month["paid"] + extra_covered), "prepaid": month["paid"],
                "to_pay": money(cost - extra_covered)}
    covered = min(max(credit, ZERO), cost)
    return {"month_number": number, "cost": money(cost), "covered": money(covered), "to_pay": money(cost - covered)}


def contract_q_active() -> Q:
    return Q(status__in=(StudentBillingProfile.Status.ACTIVE, StudentBillingProfile.Status.PAUSED))


def payment_schedule(profile: StudentBillingProfile) -> dict | None:
    """График оплаты договора по программе: выставленные учебные месяцы
    (сумма, оплачено, остаток) и прогноз оставшихся по той же формуле, что
    выставит `month_charge`, — с учётом свободного аванса, который их закроет.

    Проверка согласованности: Σ начислений + Σ прогноза = итоговая стоимость.
    Если месяцы выставлены по прежней итоговой стоимости (изменена после
    выставления), это видно из `price_changes` — суммы выставленных начислений
    не пересчитываются (снимок), разница уходит в оставшиеся месяцы."""
    if not profile.is_course or profile.final_course_price is None:
        return None
    from ..models import BillingTermsChange

    final = money(profile.final_course_price)
    duration = profile.duration_months
    live = list(Invoice.objects.filter(profile=profile).exclude(status=Invoice.Status.VOID)
                .select_related("package").order_by("package__number", "pk"))
    # Предоплата за весь курс: «Весь курс» — начисление договора, а не месяца
    # №1 (к пакету №1 оно привязано технически). Каждый месяц показывает свою
    # долю курса и сколько из неё закрыто оплатой «Весь курс».
    coverage = course_coverage(profile)
    course = coverage["invoice"] if coverage else None
    lessons_by_month = {p.month_number: p.lessons_used for p in live_packages(profile) if p.month_number}
    rows, by_month = [], {}
    for inv in live:
        if course is not None and inv.pk == course.pk:
            continue
        by_month.setdefault(inv.package.month_number or 0, []).append(inv)
    invoiced = sum((i.amount for i in live), ZERO)
    unpaid = [i for i in live if i.status in Invoice.UNPAID_STATUSES]
    credit = CreditLedgerEntry.objects.filter(profile=profile).aggregate(s=Sum("amount"))["s"] or ZERO
    spare = max(applicable_credit(profile, unpaid, credit) - sum((i.balance for i in unpaid), ZERO), ZERO)
    covered_months = {p.month_number for p in live_packages(profile) if p.month_number}
    remaining = max(final - invoiced, ZERO)
    projected_total = ZERO
    plan = {r.month_number: r for r in profile.month_prices.all()} if profile.month_plan_mode else {}
    surcharge_month = next((m for m in range(1, duration + 1) if m not in covered_months), None)
    for month in range(1, duration + 1):
        invoices = by_month.get(month, [])
        if course is not None:
            share = coverage["months"][month]
            rows.append({
                "month_number": month, "state": "prepaid" if share["paid"] == share["share"] else "course_due",
                "invoice": course.pk, "number": course.number, "kind": Invoice.Kind.COURSE,
                "amount": share["share"], "paid": share["paid"], "balance": ZERO,
                "status": course.status, "status_display": course.get_status_display(),
                "due_lesson": None, "due_date": None, "lessons_used": lessons_by_month.get(month),
                "covered_by_credit": ZERO, "to_pay": ZERO,
            })
            if not invoices and month == surcharge_month and remaining > 0:
                # Доплата сверх «Весь курс» (цена курса повышена): её выставит
                # следующий учебный месяц (`month_charge`).
                covered = min(spare, remaining)
                spare -= covered
                projected_total += remaining
                rows.append({"month_number": month, "state": "future", "kind": Invoice.Kind.MONTH,
                             "amount": remaining, "paid": ZERO, "balance": ZERO, "covered_by_credit": covered,
                             "to_pay": remaining - covered})
                remaining = ZERO
            if not invoices:
                continue
        if invoices:
            for inv in invoices:
                rows.append({
                    "month_number": month, "state": "invoiced", "invoice": inv.pk, "number": inv.number,
                    "kind": inv.kind, "amount": inv.amount, "paid": inv.amount_paid + inv.amount_adjusted,
                    "balance": inv.balance if inv.status in Invoice.UNPAID_STATUSES else ZERO, "status": inv.status,
                    "status_display": inv.get_status_display(), "due_lesson": inv.due_lesson,
                    "due_date": None if inv.due_lesson else inv.due_date.isoformat(),
                    "lessons_used": inv.package.lessons_used,
                    "covered_by_credit": ZERO, "to_pay": ZERO,
                })
            continue
        if profile.payment_mode == PaymentMode.FULL_PREPAY or month in covered_months:
            # Предоплата: месяц оплачен начислением «Весь курс» (своего начисления нет).
            amount = ZERO
        elif month in plan:
            amount = min(money(plan[month].amount), remaining)
            remaining -= amount
        else:
            months_left = sum(1 for m in range(month, duration + 1) if m not in by_month)
            amount = remaining if months_left <= 1 else (remaining / months_left).quantize(CENT, rounding=ROUND_DOWN)
            remaining -= amount
        covered = min(spare, amount)
        spare -= covered
        projected_total += amount
        rows.append({"month_number": month, "state": "planned" if month in covered_months else "future",
                     "amount": amount, "paid": ZERO, "balance": ZERO, "covered_by_credit": covered,
                     "to_pay": amount - covered})
    changes = [{
        "date": c.decided_at.date().isoformat() if c.decided_at else c.requested_at.date().isoformat(),
        "from": str(money(c.previous_terms.get("final_course_price") or 0)) if c.previous_terms.get("final_course_price") else None,
        "to": str(money(c.final_course_price)), "reason": c.reason,
    } for c in BillingTermsChange.objects.filter(profile=profile, status=BillingTermsChange.Status.APPROVED,
                                                 final_course_price__isnull=False).order_by("requested_at", "pk")]
    # Записи «38 000 → 38 000» (повторные сохранения до исправления) не
    # удаляются из истории условий, но в истории стоимости не показываются.
    changes = [c for c in changes if c["from"] != c["to"]]
    total = invoiced + projected_total
    issues = []
    if invoiced > final:
        issues.append(f"Начислено {money(invoiced)} — больше итоговой стоимости {final}: нужна корректировка начислений.")
    elif total != final:
        issues.append(f"Начислено и запланировано {money(total)}, а итоговая стоимость {final}.")
    for row in rows:
        price = plan.get(row["month_number"])
        row["standard_price"] = money(price.standard_price) if price else None
        row["plan_amount"] = money(price.amount) if price else None
    return {
        "month_plan_mode": profile.month_plan_mode,
        "standard_course_price": money(profile.standard_course_price) if profile.standard_course_price else None,
        "discount_amount": money(profile.discount_amount),
        "final_course_price": final, "invoiced": money(invoiced), "projected": money(projected_total),
        "total": money(total), "consistent": not issues, "issues": issues, "price_changes": changes,
        "course": None if course is None else {
            "invoice": course.pk, "number": course.number, "amount": money(course.amount),
            "paid": money(course.amount_paid + course.amount_adjusted),
            "balance": money(course.balance) if course.status in Invoice.UNPAID_STATUSES else ZERO,
            "status": course.status, "status_display": course.get_status_display(),
            "due_date": course.due_date.isoformat() if course.due_date else None,
            "paid_in_full": coverage["paid_in_full"],
        },
        "months": [{k: (money(v) if isinstance(v, Decimal) else v) for k, v in r.items()} for r in rows],
    }
