"""План стоимости учебных месяцев договора по программе.

Каждый договор может иметь свои цены месяцев (например, №1 — 13 000,
№2–4 — по 15 000; стандартная стоимость = 58 000) и итоговую стоимость со
скидкой (например, 50 000). Скидка распределяется по правилу, которое явно
выбирает бухгалтер:

* PROPORTIONAL — пропорционально стандартной цене месяцев (округление вниз
  до тыйына, остаток тыйынов — месяцам с наибольшей дробной частью, затем по
  порядку): Σ = итоговая стоимость ровно;
* MANUAL — итоговая сумма каждого месяца задана вручную; Σ должна совпасть
  с итоговой стоимостью, иначе ошибка с разницей.

Выставленные начисления не меняются: для уже выставленного месяца итоговая
сумма плана равна сумме его начисления, и распределяется только остаток
итоговой стоимости по ещё не выставленным месяцам. Исправить выставленные —
отдельной операцией: `reissue_unstarted` (аннулировать и перевыставить
месяцы, по которым не было уроков и корректировок; оплата по ним
возвращается в аванс и применяется снова) или корректировкой начисления.

Предоплата за весь курс: начисление «Весь курс» = итоговая стоимость, план
показывает, какая часть предоплаты относится к каждому месяцу.

Без плана (пустой `month_plan_mode`) действует прежнее правило — итоговая
делится поровну на оставшиеся месяцы; существующие договоры не меняются.
"""
from __future__ import annotations

from decimal import ROUND_DOWN, Decimal

from django.db import transaction

from apps.accounting.services import audit
from apps.accounting.services.money import money

from ..models import (
    BillingTermsChange,
    ContractMonthPrice,
    Invoice,
    InvoiceAdjustment,
    LessonPackage,
    PaymentMode,
    StudentBillingProfile,
)
from . import BillingError

ZERO = Decimal("0.00")
CENT = Decimal("0.01")
MODES = ("PROPORTIONAL", "MANUAL")


def _money(value, field: str) -> Decimal:
    try:
        amount = Decimal(str(value))
    except Exception:  # noqa: BLE001
        raise BillingError(f"Некорректная сумма: {field}.", code="invalid_amount")
    if amount != amount.quantize(CENT):
        raise BillingError(f"{field}: не точнее тыйына.", code="invalid_amount")
    return amount


def distribute(weights: list[Decimal], total: Decimal) -> list[Decimal]:
    """Разделить `total` пропорционально `weights` с точностью до тыйына:
    Σ результата = total ровно (метод наибольших остатков, при равенстве —
    раньше идущий месяц)."""
    if not weights:
        return []
    base = sum(weights, ZERO)
    if base <= 0:
        raise BillingError("Стандартные цены месяцев должны быть больше нуля.", code="invalid_amount")
    exact = [total * w / base for w in weights]
    parts = [e.quantize(CENT, rounding=ROUND_DOWN) for e in exact]
    left = int(((total - sum(parts, ZERO)) / CENT).to_integral_value())
    order = sorted(range(len(weights)), key=lambda i: (-(exact[i] - parts[i]), i))
    for i in order[:left]:
        parts[i] += CENT
    return parts


def _issued(profile) -> dict:
    """Выставленные (действующие) начисления по номеру месяца и «Весь курс»."""
    by_month, course = {}, None
    for inv in (Invoice.objects.filter(profile=profile).exclude(status=Invoice.Status.VOID)
                .select_related("package")):
        if inv.kind == Invoice.Kind.COURSE:
            course = inv
        elif inv.package.month_number:
            by_month[inv.package.month_number] = by_month.get(inv.package.month_number, ZERO) + inv.amount
    return {"months": by_month, "course": course}


def compute_plan(profile: StudentBillingProfile, *, standard_prices, final_course_price, mode: str,
                 manual_amounts=None) -> dict:
    """Рассчитать план (ничего не сохраняет) — для предпросмотра и сохранения."""
    if not profile.is_course:
        raise BillingError("План месяцев — только для договора по программе.", code="not_course")
    if mode not in MODES:
        raise BillingError("Выберите правило распределения скидки.", code="invalid")
    n = profile.duration_months
    standard = [_money(v, f"цена месяца №{i + 1}") for i, v in enumerate(standard_prices or [])]
    if len(standard) != n:
        raise BillingError(f"Укажите цену каждого из {n} месяцев.", code="invalid")
    if any(v <= 0 for v in standard):
        raise BillingError("Стандартная цена месяца должна быть больше нуля.", code="invalid_amount")
    final = _money(final_course_price, "итоговая стоимость")
    standard_total = sum(standard, ZERO)
    if final < 0 or final > standard_total:
        raise BillingError(f"Итоговая стоимость должна быть от 0 до стандартной ({standard_total}).",
                           code="invalid_discount")
    issued = _issued(profile)
    course = issued["course"]
    months_issued = issued["months"]
    if course is not None and course.amount != final:
        raise BillingError(f"Начисление «Весь курс» уже выставлено на {course.amount} — сначала исправьте его "
                           f"(перевыставление или корректировка).", code="issued_mismatch")
    if profile.payment_mode == PaymentMode.FULL_PREPAY or course is not None:
        # Предоплата: план — разбивка единого начисления по месяцам (для отчёта и карточки).
        open_months = list(range(1, n + 1))
        remaining = final
    else:
        open_months = [m for m in range(1, n + 1) if m not in months_issued]
        remaining = final - sum(months_issued.values(), ZERO)
        if remaining < 0:
            raise BillingError(f"Уже начислено {sum(months_issued.values(), ZERO)} — больше итоговой стоимости "
                               f"{final}: исправьте выставленные начисления корректировкой.", code="below_invoiced")
    if mode == "PROPORTIONAL":
        if not open_months and remaining:
            raise BillingError("Все месяцы выставлены — разницу нельзя распределить, нужна корректировка.",
                               code="below_invoiced")
        open_amounts = distribute([standard[m - 1] for m in open_months], remaining)
    else:
        manual = list(manual_amounts or [])
        if len(manual) != n:
            raise BillingError(f"Укажите итоговую сумму каждого из {n} месяцев.", code="invalid")
        manual = [None if v in (None, "") else _money(v, f"сумма месяца №{i + 1}") for i, v in enumerate(manual)]
        for m in range(1, n + 1):
            if m not in open_months and manual[m - 1] is not None and manual[m - 1] != months_issued[m]:
                raise BillingError(f"Месяц №{m} уже выставлен на {months_issued[m]} — его сумма меняется только "
                                   f"корректировкой.", code="issued_mismatch")
        if any(manual[m - 1] is None or manual[m - 1] < 0 for m in open_months):
            raise BillingError("Суммы месяцев не могут быть пустыми или отрицательными.", code="invalid_amount")
        open_amounts = [manual[m - 1] for m in open_months]
        if sum(open_amounts, ZERO) != remaining:
            raise BillingError(f"Сумма месяцев {money(sum(open_amounts, ZERO))} не равна "
                               f"{'итоговой стоимости' if len(open_months) == n else 'остатку итоговой стоимости'} "
                               f"{money(remaining)} (разница {money(remaining - sum(open_amounts, ZERO))}).",
                               code="plan_total_mismatch")
    amounts = dict(zip(open_months, open_amounts))
    rows = []
    for m in range(1, n + 1):
        issued_amount = months_issued.get(m)
        rows.append({
            "month_number": m, "standard_price": standard[m - 1],
            "amount": amounts.get(m, issued_amount if issued_amount is not None else ZERO),
            "issued": m in months_issued or course is not None,
        })
    total = sum((r["amount"] for r in rows), ZERO)
    return {"mode": mode, "standard_total": money(standard_total), "final_course_price": money(final),
            "discount": money(standard_total - final), "total": money(total), "rows": rows,
            "payment_mode": profile.payment_mode}


def _reissuable(invoice: Invoice) -> bool:
    return (invoice.package.lessons_used == 0 and invoice.package.status != LessonPackage.Status.COMPLETED
            and not invoice.adjustments.filter(status=InvoiceAdjustment.Status.APPLIED).exists())


def set_month_plan(profile: StudentBillingProfile, *, actor, standard_prices, final_course_price, mode: str,
                   manual_amounts=None, reason: str = "", reissue_unstarted: bool = False,
                   initial: bool = False) -> dict:
    """Сохранить план месяцев договора (администратор оплаты, причина, аудит).
    Повторное сохранение того же плана ничего не меняет и начислений не создаёт."""
    from ..permissions import authorize
    from .invoices import _after_invoice_created, _create_invoice, lock_profile, void_invoice

    if not initial:
        authorize(actor, "approve_terms")
    reason = (reason or "").strip()
    if not reason and not initial:
        raise BillingError("Укажите причину изменения плана.", code="reason_required")
    with transaction.atomic():
        profile = lock_profile(profile)
        if profile.status in StudentBillingProfile.CLOSED_STATUSES:
            raise BillingError("Договор закрыт.", code="profile_inactive")
        if not initial and BillingTermsChange.objects.filter(profile=profile,
                                                             status=BillingTermsChange.Status.PENDING).exists():
            raise BillingError("Изменение условий ждёт согласования — сначала решите его.", code="pending_terms")
        reissued = []
        if reissue_unstarted:
            # Отдельная контролируемая корректировка: не начатые месяцы
            # перевыставляются по новому плану (оплата — в аванс и обратно).
            for inv in (Invoice.objects.filter(profile=profile, status__in=(*Invoice.UNPAID_STATUSES, Invoice.Status.PAID))
                        .select_related("package")):
                if _reissuable(inv):
                    void_invoice(inv, actor=actor, reason=f"Перевыставление по плану месяцев: {reason}", system=True,
                                 cancel_package=False)
                    reissued.append((inv.package, inv.period_date, inv.kind, inv.number))
        plan = compute_plan(profile, standard_prices=standard_prices, final_course_price=final_course_price,
                            mode=mode, manual_amounts=manual_amounts)
        current = {r.month_number: (r.standard_price, r.amount) for r in profile.month_prices.all()}
        wanted = {r["month_number"]: (r["standard_price"], r["amount"]) for r in plan["rows"]}
        final = plan["final_course_price"]
        unchanged = (current == wanted and profile.month_plan_mode == mode and profile.final_course_price == final
                     and not reissued)
        if unchanged:
            return {**plan, "changed": False, "reissued": []}
        old = {"mode": profile.month_plan_mode, "final_course_price": profile.final_course_price,
               "standard_course_price": profile.standard_course_price,
               "months": {str(k): [str(a), str(b)] for k, (a, b) in current.items()}}
        for month, (standard, amount) in wanted.items():
            ContractMonthPrice.objects.update_or_create(
                profile=profile, month_number=month,
                defaults={"standard_price": standard, "amount": amount,
                          "updated_by": actor if getattr(actor, "is_authenticated", False) else None},
            )
        previous_terms = {"final_course_price": str(profile.final_course_price),
                          "discount_amount": str(profile.discount_amount)}
        price_changed = profile.final_course_price != final
        profile.month_plan_mode = mode
        profile.standard_course_price = plan["standard_total"]
        profile.final_course_price = final
        profile.discount_amount = plan["discount"]
        profile.discount_enabled = plan["discount"] > 0
        if reason and profile.discount_enabled:
            profile.discount_reason = reason
        profile.save()
        if price_changed and not initial:
            # История итоговой стоимости — как у обычного изменения условий.
            BillingTermsChange.objects.create(
                profile=profile, discount_enabled=profile.discount_enabled, final_course_price=final,
                discount_amount=plan["discount"], reason=f"План месяцев: {reason}", previous_terms=previous_terms,
                status=BillingTermsChange.Status.APPROVED, requested_by=actor, decided_by=actor,
            )
        created = []
        for package, period, kind, number in reissued:
            from .contracts import month_charge

            amount, kind = month_charge(profile, package.month_number)
            package.final_price = amount
            package.pricing_snapshot = {**package.pricing_snapshot, "charge": str(amount), "month_plan": mode}
            package.save(update_fields=["final_price", "pricing_snapshot", "updated_at"])
            if amount > 0:
                invoice = _create_invoice(profile, package, amount=amount, kind=kind, on_date=period, actor=actor,
                                          period_date=period, snapshot={**package.pricing_snapshot,
                                                                        "package_number": package.number,
                                                                        "reissue_of": number})
                created.append(_after_invoice_created(profile, invoice, actor=actor).number)
        audit.log(actor, profile, "billing_month_plan", old=old, new={
            "mode": mode, "final_course_price": final, "standard_course_price": plan["standard_total"],
            "months": {str(k): [str(a), str(b)] for k, (a, b) in wanted.items()},
            "reissued": [r[3] for r in reissued], "created": created,
        }, reason=reason or "Договор оформлен с планом месяцев")
    return {**plan, "changed": True, "reissued": [r[3] for r in reissued], "created": created}


def plan_rows(profile: StudentBillingProfile) -> dict[int, ContractMonthPrice]:
    return {r.month_number: r for r in profile.month_prices.all()} if profile.month_plan_mode else {}


def redistribute_after_price_change(profile: StudentBillingProfile, *, actor) -> None:
    """Итоговая стоимость изменена обычным изменением условий: при правиле
    PROPORTIONAL оставшиеся месяцы пересчитываются по тем же стандартным ценам.
    Вызывается под блокировкой договора."""
    rows = plan_rows(profile)
    if profile.month_plan_mode != "PROPORTIONAL" or not rows:
        return
    plan = compute_plan(profile, standard_prices=[rows[m].standard_price for m in sorted(rows)],
                        final_course_price=profile.final_course_price, mode="PROPORTIONAL")
    for row in plan["rows"]:
        ContractMonthPrice.objects.filter(profile=profile, month_number=row["month_number"]).update(amount=row["amount"])
    profile.standard_course_price = plan["standard_total"]
    StudentBillingProfile.objects.filter(pk=profile.pk).update(standard_course_price=plan["standard_total"])
    audit.log(actor, profile, "billing_month_plan_redistribute", new={
        "final_course_price": profile.final_course_price,
        "months": {str(r["month_number"]): str(r["amount"]) for r in plan["rows"]},
    })
