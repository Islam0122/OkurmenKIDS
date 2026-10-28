"""Ручная корректировка одного учебного месяца договора по программе.

У месяца три разные суммы, и ни одна не перезаписывает другую незаметно:

* «Стандарт» (`ContractMonthPrice.standard_price`) — базовая цена месяца до
  скидок. Меняет только стандартную стоимость курса и размер скидки
  (стандартная − итоговая); план и начисления не трогает.
* «По плану» (`ContractMonthPrice.amount`) — утверждённая сумма месяца в
  плане договора. Редактируется только у ещё не выставленного месяца: из
  плана месяц будет начислен (`contracts.month_charge`). У выставленного
  месяца плановая сумма по правилам плана равна его начислению.
* «Начисление» (`Invoice.amount`) — сумма выставленного счёта. Меняется
  только перевыставлением: исходное начисление аннулируется (запись и её
  распределения остаются в истории), на тот же учебный месяц выставляется
  новое со ссылкой на исходное (`snapshot.reissue_of`), деньги тех же
  платежей распределяются на него в прежнем порядке. Платежи, чеки и
  поступления не меняются. Уменьшить начисление ниже уже оплаченного нельзя
  — переплату оформляют сторно распределения или возвратом.

Разница плановой суммы или начисления учитывается так, как явно выбрал
сотрудник (`difference`):

* ``course`` — меняется итоговая стоимость курса (на ту же разницу);
* ``future`` — итоговая стоимость не меняется, разница распределяется на
  ещё не выставленные месяцы пропорционально их плановым суммам.

Если план уже расходился с итоговой стоимостью до изменения, расхождение не
исправляется молча: оно остаётся и показывается в предпросмотре.

Предпросмотр (`dry_run`) выполняет ту же операцию в транзакции и откатывает
её — показанные «до / после» ровно те, что получатся при сохранении. Защита
от перезаписи чужих изменений — версия графика (`schedule_version`): форма
отправляет версию, с которой открыта; если с тех пор договор, план или
начисления изменились, сохранение отклоняется (`stale`).

Каждое сохранение — запись `billing_month_edit` в журнале аудита (старые и
новые значения, причина, сотрудник, время, месяц, связанные начисления);
изменение итоговой стоимости — ещё и запись истории условий
(`BillingTermsChange`), как у плана месяцев.
"""
from __future__ import annotations

import hashlib
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from apps.accounting.models import PayrollAuditLog
from apps.accounting.services import audit
from apps.accounting.services.money import money

from ..models import (
    BillingTask,
    BillingTermsChange,
    ContractMonthPrice,
    Invoice,
    InvoiceAdjustment,
    PaymentAllocation,
    PaymentMode,
    StudentBillingProfile,
)
from . import BillingError

ZERO = Decimal("0.00")
CENT = Decimal("0.01")
DIFFERENCE = ("course", "future")
EDIT_ACTION = "billing_month_edit"

UI_STATUS = {
    "future": "Будет выставлен", "draft": "Черновик", "awaiting": "Ожидает оплаты", "partial": "Частично оплачен",
    "paid": "Оплачен", "overdue": "Просрочен",
}


class _DryRun(Exception):
    """Откат предпросмотра: результат — в `args[0]`."""


def _amount(value, field: str) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        amount = Decimal(str(value))
    except Exception:  # noqa: BLE001
        raise BillingError(f"Некорректная сумма: {field}.", code="invalid_amount")
    if amount != amount.quantize(CENT):
        raise BillingError(f"{field.capitalize()} — не точнее тыйына (0.01).", code="invalid_amount")
    if amount < 0:
        raise BillingError(f"{field.capitalize()} не может быть отрицательной.", code="invalid_amount")
    return amount


# ---------------------------------------------------------------------------
# Версия графика и состояние месяцев
# ---------------------------------------------------------------------------

def schedule_version(profile) -> str:
    """Отпечаток всего, от чего зависят суммы месяцев: договор, план,
    начисления (суммы, оплаты, корректировки, статусы)."""
    pk = getattr(profile, "pk", profile)
    head = StudentBillingProfile.objects.filter(pk=pk).values_list(
        "updated_at", "final_course_price", "standard_course_price", "month_plan_mode", "status").first()
    rows = list(ContractMonthPrice.objects.filter(profile_id=pk).order_by("month_number")
                .values_list("month_number", "standard_price", "amount"))
    invoices = list(Invoice.objects.filter(profile_id=pk).order_by("pk")
                    .values_list("pk", "amount", "amount_paid", "amount_adjusted", "status"))
    return hashlib.sha1(repr((head, rows, invoices)).encode()).hexdigest()[:20]


def edit_blocked(profile) -> str | None:
    """Почему суммы месяцев договора сейчас нельзя редактировать (None — можно)."""
    from .contracts import course_invoice

    if not profile.is_course or profile.final_course_price is None:
        return "Суммы месяцев есть только у договора по программе."
    if profile.status in StudentBillingProfile.CLOSED_STATUSES:
        return "Договор закрыт — суммы месяцев не меняются."
    if profile.payment_mode == PaymentMode.FULL_PREPAY or course_invoice(profile) is not None:
        return "Предоплата за весь курс: месяцы — доли начисления «Весь курс». Исправляйте стоимость курса."
    if BillingTermsChange.objects.filter(profile=profile, status=BillingTermsChange.Status.PENDING).exists():
        return "Изменение условий ждёт согласования — сначала решите его."
    return None


def ui_status(invoice: Invoice | None) -> str:
    """Статус месяца для графика по актуальным данным (просрочка — по сроку и
    остатку начисления, `contracts.payment_stage`)."""
    from .contracts import payment_stage

    if invoice is None:
        return "future"
    stage = payment_stage(invoice)
    if stage == "draft":
        return "draft"
    if stage == "paid":
        return "paid"
    if stage == "overdue":
        return "overdue"
    return "partial" if invoice.amount_paid + invoice.amount_adjusted > 0 else "awaiting"


def edited_months(profile) -> set[int]:
    """Месяцы, суммы которых сотрудник менял вручную (журнал аудита)."""
    values = PayrollAuditLog.objects.filter(
        entity_type="studentbillingprofile", entity_id=profile.pk, action=EDIT_ACTION,
    ).values_list("new_values", flat=True)
    return {v.get("month_number") for v in values if isinstance(v, dict) and v.get("month_number")}


def baseline(profile, schedule: dict) -> dict[int, dict]:
    """Действующие значения месяцев: стандарт (план договора или стандартная
    цена месяца), плановая сумма (выставленный месяц — его начисление,
    будущий — план, без плана — прогноз графика) и начисление."""
    stored = {r.month_number: r for r in profile.month_prices.all()} if profile.month_plan_mode else {}
    default_standard = money(profile.month_price) if profile.month_price else None
    invoice_rows: dict[int, list] = {}
    projected: dict[int, Decimal] = {}
    states: dict[int, str] = {}
    for row in schedule["months"]:
        m = row["month_number"]
        if row["state"] == "invoiced":
            invoice_rows.setdefault(m, []).append(row["invoice"])
        elif row["state"] in ("future", "planned"):
            projected[m] = projected.get(m, ZERO) + money(row["amount"])
            states.setdefault(m, row["state"])
    invoices = Invoice.objects.in_bulk([pk for pks in invoice_rows.values() for pk in pks])
    result = {}
    for m in range(1, profile.duration_months + 1):
        row = stored.get(m)
        standard = money(row.standard_price) if row is not None else default_standard
        pks = invoice_rows.get(m, [])
        invoice = invoices.get(pks[0]) if len(pks) == 1 else None
        if pks:
            amount = sum((invoices[pk].amount for pk in pks), ZERO)
            state = "invoiced"
        else:
            state = states.get(m, "future")
            amount = money(row.amount) if row is not None else projected.get(m, ZERO)
        result[m] = {
            "standard": standard, "amount": money(amount), "state": state, "invoice": invoice,
            "invoices": len(pks), "stored_amount": money(row.amount) if row is not None else None,
        }
    return result


def decorate(profile, schedule: dict | None, *, edited: set[int] | None = None) -> dict | None:
    """Добавить в график значения для таблицы и формы «Изменить»: стандарт,
    план и начисление месяца отдельно, оплачено (распределения) и
    корректировки, статус по актуальным данным, признак ручного изменения и
    что из сумм месяца можно менять. Ничего не меняет."""
    if schedule is None:
        return None
    base = baseline(profile, schedule)
    blocked = edit_blocked(profile)
    edited = edited_months(profile) if edited is None else edited
    invoices = Invoice.objects.select_related("package").in_bulk(
        [r["invoice"] for r in schedule["months"] if r.get("invoice")])
    for row in schedule["months"]:
        m = row["month_number"]
        b = base[m]
        inv = invoices.get(row.get("invoice")) if row["state"] == "invoiced" else None
        row["standard"] = b["standard"]
        if inv is not None:
            row["invoice_amount"] = inv.amount
            row["adjusted"] = inv.amount_adjusted
            row["allocated"] = inv.amount_paid
            row["charge"] = money(inv.amount - inv.amount_adjusted)
            row["plan"] = inv.amount if b["invoices"] == 1 else None
            row["plan_mismatch"] = b["stored_amount"] is not None and b["stored_amount"] != inv.amount
            row["ui_status"] = ui_status(inv)
            row["due_reached_on"] = inv.due_reached_on.isoformat() if inv.due_reached_on else None
            row["overdue_since"] = inv.overdue_since.isoformat() if inv.overdue_since else None
        else:
            row["invoice_amount"] = None
            row["adjusted"] = ZERO
            row["allocated"] = money(row.get("paid") or ZERO)
            row["charge"] = None
            row["plan"] = b["amount"] if row["state"] in ("future", "planned") else row.get("amount")
            row["plan_mismatch"] = False
            row["ui_status"] = {"prepaid": "paid", "course_due": "awaiting"}.get(row["state"], "future")
        row["ui_status_display"] = UI_STATUS[row["ui_status"]]
        row["manual"] = m in edited
        reason = blocked or ("В месяце несколько начислений — исправьте через администратора." if b["invoices"] > 1
                             else None)
        row["editable"] = {
            "standard": reason is None, "plan": reason is None and b["state"] == "future",
            "charge": reason is None and b["state"] == "invoiced", "blocked": reason,
        }
    plan_total = sum((b["amount"] for b in base.values()), ZERO)
    standard_total = sum((b["standard"] or ZERO for b in base.values()), ZERO)
    schedule.update({
        "plan_total": money(plan_total), "plan_difference": money(plan_total - schedule["final_course_price"]),
        "standard_total": money(standard_total), "edit_blocked": blocked, "version": schedule_version(profile),
    })
    return schedule


# ---------------------------------------------------------------------------
# Изменение
# ---------------------------------------------------------------------------

def _state(profile) -> dict:
    from .contracts import money_summary, payment_schedule

    fresh = StudentBillingProfile.objects.select_related("plan", "student").get(pk=profile.pk)
    summary = money_summary(fresh)
    schedule = payment_schedule(fresh)
    base = baseline(fresh, schedule)
    course = {
        "final_course_price": summary["final_course_price"], "standard_course_price": summary["standard_course_price"],
        "discount_amount": summary["discount_amount"], "plan_total": money(sum((b["amount"] for b in base.values()), ZERO)),
        "invoiced": summary["invoiced"], "future": summary["future"], "due_now": summary["due_now"],
        "overdue": summary["overdue"], "net_to_pay": summary["net_to_pay"], "credit": summary["credit"],
        "allocated": summary["allocated"], "received": summary["net_received"],
    }
    months = {}
    for m, b in base.items():
        inv = Invoice.objects.get(pk=b["invoice"].pk) if b["invoice"] is not None else None
        months[m] = {
            "standard": b["standard"], "plan": b["amount"], "state": b["state"],
            "charge": money(inv.amount - inv.amount_adjusted) if inv else None,
            "paid": inv.amount_paid if inv else ZERO,
            "balance": inv.balance if inv and inv.status in Invoice.UNPAID_STATUSES else ZERO,
            "invoice": inv.number if inv else None, "status": ui_status(inv),
        }
    return {"course": course, "months": months}


def _reissue(profile, invoice: Invoice, amount: Decimal, *, actor, reason: str) -> Invoice:
    """Перевыставить начисление месяца на новую сумму (под блокировкой
    договора). Исходное аннулируется, распределения сторнируются в аванс и
    теми же платежами в том же порядке направляются на новое; корректировки
    исходного отменяются — новая сумма их заменяет."""
    from .invoices import _create_invoice, close_tasks, refresh_invoice
    from .payments import _allocate_locked, apply_available_credit, reverse_allocation_locked

    invoice = Invoice.objects.select_for_update().select_related("package").get(pk=invoice.pk)
    note = f"Пересчёт начисления {invoice.number}: {reason}"
    adjustments = list(invoice.adjustments.filter(status=InvoiceAdjustment.Status.APPLIED))
    for adj in adjustments:
        adj.status = InvoiceAdjustment.Status.VOID
        adj.voided_by = actor if getattr(actor, "is_authenticated", False) else None
        adj.voided_at, adj.void_reason = timezone.now(), note
        adj.save()
        audit.log(actor, adj, "billing_adjustment_void", reason=note)
    allocations = list(invoice.allocations.filter(status=PaymentAllocation.Status.ACTIVE)
                       .select_related("payment").order_by("pk"))
    for allocation in allocations:
        reverse_allocation_locked(allocation, actor=actor, reason=note)
    invoice = Invoice.objects.select_for_update().select_related("package").get(pk=invoice.pk)
    old = {"status": invoice.status, "amount": invoice.amount, "amount_paid": invoice.amount_paid,
           "amount_adjusted": invoice.amount_adjusted}
    invoice.status = Invoice.Status.VOID
    invoice.void_reason = f"Заменено пересчётом суммы: {reason}"
    invoice.voided_at = timezone.now()
    invoice.voided_by = actor if getattr(actor, "is_authenticated", False) else None
    invoice.amount_paid = invoice.amount_adjusted = ZERO
    invoice.save()
    close_tasks(invoice, "Начисление пересчитано", status=BillingTask.Status.CANCELLED)
    package = invoice.package
    package.final_price = amount
    package.pricing_snapshot = {**package.pricing_snapshot, "charge": str(amount), "manual_charge": True}
    package.save(update_fields=["final_price", "pricing_snapshot", "updated_at"])
    new = _create_invoice(profile, package, amount=amount, kind=invoice.kind, on_date=invoice.issue_date, actor=actor,
                          period_date=invoice.period_date, snapshot={
                              **invoice.snapshot, "charge": str(amount), "reissue_of": invoice.number,
                              "reissue_of_id": invoice.pk, "manual_edit_reason": reason,
                          })
    # Срок и его история — как у исходного начисления: пересчёт суммы не
    # переносит срок оплаты и не обнуляет просрочку.
    new.due_date, new.due_lesson = invoice.due_date, invoice.due_lesson
    new.due_reached_on, new.overdue_since = invoice.due_reached_on, invoice.overdue_since
    new.save(update_fields=["due_date", "due_lesson", "due_reached_on", "overdue_since", "updated_at"])
    audit.log(actor, invoice, "billing_invoice_void", old=old, new={"status": invoice.status, "replaced_by": new.number},
              reason=note)
    left = amount
    for allocation in allocations:
        part = min(allocation.amount, left)
        if part <= 0:
            break
        _allocate_locked(allocation.payment, new, part, actor=actor, source=allocation.source)
        left -= part
    apply_available_credit(profile, actor=actor, locked=True, system=True)
    return refresh_invoice(new)


def _apply(profile, *, actor, month_number: int, standard_price, plan_amount, charge, difference: str,
           reason: str, warnings: list[str]) -> dict:
    from .contracts import payment_schedule
    from .month_plan import distribute

    blocked = edit_blocked(profile)
    if blocked:
        raise BillingError(blocked, code="edit_blocked")
    n = profile.duration_months
    if not 1 <= month_number <= n:
        raise BillingError(f"В договоре {n} учебных месяцев.", code="invalid")
    if difference not in DIFFERENCE:
        raise BillingError("Выберите, как учесть разницу.", code="invalid")
    base = baseline(profile, payment_schedule(profile))
    month = base[month_number]
    if month["invoices"] > 1:
        raise BillingError("В месяце несколько начислений — исправьте через администратора.", code="edit_blocked")
    standard = {m: b["standard"] for m, b in base.items()}
    amounts = {m: b["amount"] for m, b in base.items()}
    if any(v is None for v in standard.values()) and standard_price is None:
        raise BillingError("Не задана стандартная цена месяцев договора — укажите «Стандарт».", code="invalid")
    changes = {}
    new_standard = _amount(standard_price, "стандартная стоимость")
    if new_standard is not None:
        if new_standard <= 0:
            raise BillingError("Стандартная стоимость месяца должна быть больше нуля.", code="invalid_amount")
        if new_standard != standard[month_number]:
            changes["standard"] = [standard[month_number], new_standard]
            standard[month_number] = new_standard
    for m, value in standard.items():
        if value is None:  # нет плана и нет стандартной цены месяца в договоре
            standard[m] = new_standard
    new_plan = _amount(plan_amount, "плановая сумма")
    if new_plan is not None and new_plan != amounts[month_number]:
        if month["state"] != "future":
            raise BillingError(f"Месяц №{month_number} уже выставлен: его плановая сумма равна начислению. "
                               f"Измените «Начисление».", code="month_issued")
        changes["plan"] = [amounts[month_number], new_plan]
        amounts[month_number] = new_plan
    invoice, reissue_to = month["invoice"], None
    new_charge = _amount(charge, "начисление")
    if new_charge is not None:
        if invoice is None:
            if month["state"] == "future":
                raise BillingError(f"Месяц №{month_number} ещё не выставлен — начисление возьмётся из плана. "
                                   f"Измените «По плану».", code="not_issued")
            raise BillingError(f"У месяца №{month_number} нет начисления.", code="not_issued")
        invoice = Invoice.objects.get(pk=invoice.pk)
        effective = invoice.amount - invoice.amount_adjusted
        if new_charge != effective:
            if new_charge < invoice.amount_paid:
                raise BillingError(
                    f"Нельзя уменьшить начисление ниже уже оплаченной суммы ({invoice.amount_paid} сом). Сначала "
                    f"оформите сторно распределения или возврат переплаты.", code="below_paid")
            if invoice.status == Invoice.Status.PAID:
                warnings.append(f"Начисление {invoice.number} полностью оплачено. После изменения остаток станет "
                                f"{money(new_charge - invoice.amount_paid)} сом.")
            if invoice.amount_adjusted:
                warnings.append(f"Корректировки начисления на {invoice.amount_adjusted} сом будут отменены — "
                                f"новая сумма начисления их заменяет.")
            warnings.append(f"Начисление {invoice.number} будет аннулировано и выставлено заново на ту же дату и "
                            f"срок; оплата тех же платежей перейдёт на новое начисление.")
            changes["charge"] = [effective, new_charge]
            amounts[month_number] = new_charge
            reissue_to = new_charge
    if not changes:
        return {"changed": False}
    base_total = sum((b["amount"] for b in base.values()), ZERO)
    old_final = money(profile.final_course_price)
    if base_total != old_final:
        warnings.append(f"До изменения сумма плана ({money(base_total)}) расходилась с итоговой стоимостью "
                        f"({old_final}) на {money(base_total - old_final)} сом — расхождение сохраняется.")
    delta = amounts[month_number] - month["amount"]
    if delta and difference == "future":
        others = [m for m, b in base.items() if b["state"] == "future" and m != month_number]
        if not others:
            raise BillingError("Нет будущих невыставленных месяцев, на которые можно перенести разницу — "
                               "учтите её в стоимости курса.", code="no_future_months")
        pool = sum((amounts[m] for m in others), ZERO) - delta
        if pool < 0:
            raise BillingError(f"Разница {money(delta)} сом больше суммы будущих месяцев — учтите её в стоимости "
                               f"курса.", code="no_future_months")
        weights = [amounts[m] for m in others]
        if sum(weights, ZERO) <= 0:
            weights = [Decimal(1)] * len(others)
        for m, part in zip(others, distribute(weights, pool)):
            amounts[m] = part
    final = money(old_final + sum(amounts.values(), ZERO) - base_total)
    standard_total = money(sum(standard.values(), ZERO))
    if final < 0:
        raise BillingError("Итоговая стоимость курса не может быть отрицательной.", code="invalid_amount")
    if final > standard_total:
        raise BillingError(f"Итоговая стоимость курса ({final}) станет больше стандартной ({standard_total}). "
                           f"Увеличьте «Стандарт» месяца или учтите разницу иначе.", code="above_standard")
    old = {
        "month_number": month_number, "standard": month["standard"], "plan": month["amount"],
        "charge": changes.get("charge", [None])[0], "final_course_price": old_final,
        "standard_course_price": profile.standard_course_price, "mode": profile.month_plan_mode,
        "months": {str(m): [str(b["standard"]), str(b["amount"])] for m, b in base.items()},
    }
    reissued = None
    if reissue_to is not None:
        new_invoice = _reissue(profile, invoice, reissue_to, actor=actor, reason=reason)
        reissued = {"from": invoice.number, "from_id": invoice.pk, "to": new_invoice.number, "to_id": new_invoice.pk}
    for m in range(1, n + 1):
        ContractMonthPrice.objects.update_or_create(
            profile=profile, month_number=m,
            defaults={"standard_price": standard[m], "amount": amounts[m],
                      "updated_by": actor if getattr(actor, "is_authenticated", False) else None},
        )
    plan_changed = any(amounts[m] != (base[m]["stored_amount"] if profile.month_plan_mode else None)
                       for m in amounts)
    previous_terms = {"final_course_price": str(profile.final_course_price),
                      "discount_amount": str(profile.discount_amount)}
    if plan_changed or not profile.month_plan_mode:
        profile.month_plan_mode = "MANUAL"
    profile.standard_course_price = standard_total
    profile.final_course_price = final
    profile.discount_amount = money(standard_total - final)
    profile.discount_enabled = profile.discount_amount > 0
    if profile.discount_enabled and not profile.discount_reason:
        profile.discount_reason = reason
    profile.save()
    if final != old_final:
        BillingTermsChange.objects.create(
            profile=profile, discount_enabled=profile.discount_enabled, final_course_price=final,
            discount_amount=profile.discount_amount, reason=f"Изменение месяца №{month_number}: {reason}",
            previous_terms=previous_terms, status=BillingTermsChange.Status.APPROVED, requested_by=actor,
            decided_by=actor, decided_at=timezone.now(),
        )
    redistributed = {str(m): [str(base[m]["amount"]), str(amounts[m])] for m in amounts
                     if m != month_number and amounts[m] != base[m]["amount"]}
    audit.log(actor, profile, EDIT_ACTION, old=old, new={
        "month_number": month_number, "fields": sorted(changes), "difference": difference,
        "standard": standard[month_number], "plan": amounts[month_number],
        "charge": changes.get("charge", [None, None])[1], "final_course_price": final,
        "standard_course_price": standard_total, "mode": profile.month_plan_mode,
        "months": {str(m): [str(standard[m]), str(amounts[m])] for m in amounts},
        "redistributed": redistributed, "reissued": reissued,
    }, reason=reason)
    return {"changed": True, "fields": sorted(changes), "reissued": reissued}


def edit_month(profile: StudentBillingProfile, *, actor, month_number: int, standard_price=None, plan_amount=None,
               charge=None, difference: str = "course", reason: str = "", version: str | None = None,
               dry_run: bool = False) -> dict:
    """Изменить «Стандарт», «По плану» и/или «Начисление» месяца (см. модуль).
    `dry_run` — посчитать последствия без сохранения. Возвращает состояние
    месяца и договора до и после, затронутые месяцы и предупреждения."""
    from ..permissions import authorize
    from .invoices import lock_profile

    authorize(actor, "approve_terms")
    if charge not in (None, ""):
        authorize(actor, "adjust_invoice")
    reason = (reason or "").strip()
    if not dry_run and not reason:
        raise BillingError("Укажите причину корректировки.", code="reason_required")
    if not dry_run and not version:
        raise BillingError("Обновите карточку: не передана версия графика.", code="stale")
    try:
        with transaction.atomic():
            locked = lock_profile(profile)
            current = schedule_version(locked)
            if version and version != current:
                raise BillingError("Данные договора изменились, пока форма была открыта (другой сотрудник, платёж "
                                   "или урок). Обновите карточку и проверьте суммы ещё раз.", code="stale")
            before = _state(locked)
            warnings: list[str] = []
            result = _apply(locked, actor=actor, month_number=month_number, standard_price=standard_price,
                            plan_amount=plan_amount, charge=charge, difference=difference,
                            reason=reason or "предпросмотр", warnings=warnings)
            after = _state(locked) if result["changed"] else before
            out = {
                **result, "dry_run": dry_run, "month_number": month_number, "difference": difference,
                "warnings": warnings, "version": current if dry_run or not result["changed"] else None,
                "month": {"before": before["months"][month_number], "after": after["months"][month_number]},
                "course": {"before": before["course"], "after": after["course"]},
                "other_months": [
                    {"month_number": m, "plan_before": before["months"][m]["plan"],
                     "plan_after": after["months"][m]["plan"]}
                    for m in sorted(before["months"]) if m != month_number
                    and before["months"][m]["plan"] != after["months"][m]["plan"]
                ],
            }
            if dry_run:
                raise _DryRun(out)
    except _DryRun as preview:
        return preview.args[0]
    out["version"] = schedule_version(profile)
    return out


def month_history(profile, month_number: int | None = None) -> list[dict]:
    """История сумм месяцев договора: ручные изменения, изменения плана,
    перевыставления и корректировки начислений месяца (только чтение)."""
    invoices = Invoice.objects.filter(profile=profile).select_related("package")
    if month_number:
        invoices = invoices.filter(package__month_number=month_number)
    invoice_ids = list(invoices.values_list("pk", flat=True))
    adjustment_ids = list(InvoiceAdjustment.objects.filter(invoice_id__in=invoice_ids).values_list("pk", flat=True))
    rows = PayrollAuditLog.objects.filter(
        entity_type="studentbillingprofile", entity_id=profile.pk,
        action__in=(EDIT_ACTION, "billing_month_plan", "billing_month_plan_redistribute"),
    ) | PayrollAuditLog.objects.filter(entity_type="invoice", entity_id__in=invoice_ids,
                                       action__in=("billing_invoice_create", "billing_invoice_void")) \
        | PayrollAuditLog.objects.filter(entity_type="invoiceadjustment", entity_id__in=adjustment_ids)
    numbers = dict(invoices.values_list("pk", "number"))
    out = []
    for r in rows.select_related("actor").order_by("-created_at", "-pk"):
        new, old = r.new_values or {}, r.old_values or {}
        if r.entity_type == "studentbillingprofile" and month_number:
            if r.action == EDIT_ACTION:
                if new.get("month_number") != month_number and str(month_number) not in (new.get("redistributed") or {}):
                    continue
            elif (old.get("months") or {}).get(str(month_number)) == (new.get("months") or {}).get(str(month_number)):
                continue
        out.append({
            "id": r.pk, "created_at": r.created_at.isoformat(), "actor": str(r.actor) if r.actor_id else "система",
            "action": r.action, "entity_type": r.entity_type, "entity_id": r.entity_id,
            "invoice_number": numbers.get(r.entity_id) if r.entity_type == "invoice" else None,
            "old_values": old, "new_values": new, "reason": r.reason,
        })
    return out
