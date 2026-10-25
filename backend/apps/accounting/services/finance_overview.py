"""Единая финансовая панель и движение денежных средств (только чтение).

Ничего не пересчитывает заново: каждый показатель берётся из сервиса своего
раздела, поэтому числа совпадают с разделами «Оплата студентов»,
«Зарплата» и «Расходы».

Разные по природе величины не смешиваются:

| Показатель | Источник | Что это |
|---|---|---|
| Поступило от студентов | `StudentPayment` (PAYMENT, подтверждён) по `received_date` | деньги пришли |
| Возвраты студентам | `StudentPayment` (REFUND, подтверждён) по `received_date` | деньги ушли |
| Выставлено студентам | `billing.Invoice` по периоду начисления (`period_date`) | требование оплаты, **не доход и не деньги** |
| Задолженность студентов | `billing.services.reports.dashboard` / `analytics.debt_as_of` | неоплаченные начисления |
| Остаток авансов | `billing.services.prepayments` | полученные, ещё не зачтённые деньги — **обязательство** |
| Начислено зарплаты | утверждённые расчёты периодов, целиком лежащих в диапазоне | обязательство перед сотрудниками |
| Выплачено зарплаты | `PayrollPayment` (подтверждена) по `payment_date` | деньги ушли |
| Долг перед сотрудниками | `report_service.outstanding_debt` | утверждено и не выплачено, на сейчас |
| Расходы оплаченные | `Expense` PAID по `paid_date` | деньги ушли |
| Расходы начисленные / к оплате | `Expense` по `expense_date` / UNPAID | обязательство |

**Денежный поток** = поступило − (возвраты + выплаты зарплаты + оплаченные
расходы). Это и есть **финансовый результат по кассовому методу**.

**Результат по методу начисления не рассчитывается**: в проекте нет модели
признания выручки — начисление студенту выставляется на учебный месяц
целиком в его начале (а при предоплате — на весь курс сразу), а не по мере
проведённых уроков. Сложить «выставлено» с «начислено зарплаты» значило бы
выдать требования к оплате за заработанный доход.

Филиалов в проекте нет (ни у групп, ни у сотрудников), поэтому фильтра по
филиалу нет (`branches_supported: false`).
"""
from __future__ import annotations

import calendar
import datetime as dt
from collections import defaultdict
from decimal import Decimal

from django.db.models import Count, Q, Sum
from django.db.models.functions import TruncMonth
from django.utils import timezone

from ..models import Expense, Payroll, PayrollPayment, PayrollPeriod, StudentPayment
from . import expenses as expense_service
from .analytics import _aggregate
from .money import ZERO, money, money_all
from .report_service import outstanding_debt, period_label, with_totals

METHOD_LABELS = {"cash": "Наличные", "bank": "Банковский перевод", "card": "Карта / QR", "other": "Другое"}

ACCRUAL_RESULT_NOTE = (
    "Результат по методу начисления не рассчитывается: в системе нет модели признания выручки — "
    "начисление студенту выставляется на учебный месяц целиком (при предоплате — на весь курс сразу), "
    "а не по мере проведённых уроков. Показан денежный результат (кассовый метод)."
)


def month_range(year: int, month: int) -> tuple[dt.date, dt.date]:
    return dt.date(year, month, 1), dt.date(year, month, calendar.monthrange(year, month)[1])


def previous_range(date_from: dt.date, date_to: dt.date) -> tuple[dt.date, dt.date]:
    """Предыдущий период той же длины; полный календарный месяц → прошлый месяц."""
    if date_from.day == 1 and date_to == month_range(date_to.year, date_to.month)[1] \
            and (date_from.year, date_from.month) == (date_to.year, date_to.month):
        prev_end = date_from - dt.timedelta(days=1)
        return prev_end.replace(day=1), prev_end
    length = (date_to - date_from).days + 1
    return date_from - dt.timedelta(days=length), date_from - dt.timedelta(days=1)


# ---------------------------------------------------------------------------
# Базовые суммы периода
# ---------------------------------------------------------------------------

def _student_money(date_from, date_to) -> dict:
    qs = StudentPayment.objects.filter(status=StudentPayment.Status.CONFIRMED, received_date__gte=date_from,
                                       received_date__lte=date_to)
    agg = qs.aggregate(
        gross=Sum("amount", filter=Q(kind=StudentPayment.Kind.PAYMENT)),
        n=Count("pk", filter=Q(kind=StudentPayment.Kind.PAYMENT)),
        refunds=Sum("amount", filter=Q(kind=StudentPayment.Kind.REFUND)),
        n_refunds=Count("pk", filter=Q(kind=StudentPayment.Kind.REFUND)),
    )
    gross, refunds = agg["gross"] or ZERO, agg["refunds"] or ZERO
    return {"gross": gross, "count": agg["n"], "refunds": refunds, "refunds_count": agg["n_refunds"],
            "net": gross - refunds}


def _payroll_periods(date_from, date_to):
    """Расчётные периоды, целиком лежащие в диапазоне (для месяца — обе
    половины и месячный период окладов)."""
    return PayrollPeriod.objects.filter(start_date__gte=date_from, end_date__lte=date_to)


def _payroll_money(date_from, date_to) -> dict:
    rows = list(with_totals(Payroll.objects.filter(period__in=_payroll_periods(date_from, date_to))
                            .exclude(status=Payroll.Status.VOID)))
    agg = _aggregate(rows)
    paid_cash = PayrollPayment.objects.filter(
        status=PayrollPayment.Status.CONFIRMED, payment_date__gte=date_from, payment_date__lte=date_to,
    ).aggregate(s=Sum("amount"), n=Count("pk"))
    return {
        "accrued": agg["accrued"], "deductions": agg["deductions"], "paid_on_accrued": agg["paid"],
        "outstanding_on_accrued": agg["outstanding"], "awaiting_approval": agg["awaiting_approval_amount"],
        "employees": agg["employees"], "paid_cash": paid_cash["s"] or ZERO, "paid_cash_count": paid_cash["n"],
    }


def _core(date_from, date_to) -> dict:
    students = _student_money(date_from, date_to)
    payroll = _payroll_money(date_from, date_to)
    expenses_paid = expense_service.paid_total(date_from, date_to)
    expenses_incurred = Expense.objects.filter(expense_date__gte=date_from, expense_date__lte=date_to) \
        .exclude(status=Expense.Status.VOID).aggregate(s=Sum("amount"))["s"] or ZERO
    inflow = students["gross"]
    outflow = students["refunds"] + payroll["paid_cash"] + expenses_paid
    return {
        "students": students, "payroll": payroll,
        "expenses": {"paid": expenses_paid, "incurred": expenses_incurred},
        "cash_flow": {"inflow": inflow, "outflow": outflow, "net": inflow - outflow,
                      "outflow_refunds": students["refunds"], "outflow_payroll": payroll["paid_cash"],
                      "outflow_expenses": expenses_paid},
    }


def _change(current: Decimal, previous: Decimal) -> dict:
    delta = current - previous
    return {"current": current, "previous": previous, "delta": delta,
            "percent": (delta * 100 / abs(previous)).quantize(Decimal("0.1")) if previous else None}


def _history(date_to: dt.date, months: int = 12) -> list[dict]:
    """Денежный поток по месяцам (агрегатами, по 1 запросу на источник)."""
    y, m = date_to.year, date_to.month
    keys = []
    for _ in range(months):
        keys.append((y, m))
        y, m = (y - 1, 12) if m == 1 else (y, m - 1)
    keys.reverse()
    lo, hi = dt.date(*keys[0], 1), month_range(*keys[-1])[1]
    data = defaultdict(lambda: {"inflow": ZERO, "refunds": ZERO, "payroll": ZERO, "expenses": ZERO})

    def put(qs, date_field, target, **filters):
        rows = qs.filter(**{f"{date_field}__gte": lo, f"{date_field}__lte": hi}, **filters) \
            .annotate(mm=TruncMonth(date_field)).values("mm").annotate(s=Sum("amount"))
        for r in rows:
            mm = r["mm"]
            data[(mm.year, mm.month)][target] += r["s"] or ZERO

    confirmed = StudentPayment.objects.filter(status=StudentPayment.Status.CONFIRMED)
    put(confirmed, "received_date", "inflow", kind=StudentPayment.Kind.PAYMENT)
    put(confirmed, "received_date", "refunds", kind=StudentPayment.Kind.REFUND)
    put(PayrollPayment.objects.filter(status=PayrollPayment.Status.CONFIRMED), "payment_date", "payroll")
    put(Expense.objects.filter(status=Expense.Status.PAID), "paid_date", "expenses")
    out = []
    for key in keys:
        row = data[key]
        outflow = row["refunds"] + row["payroll"] + row["expenses"]
        out.append({"year": key[0], "month": key[1], **row, "outflow": outflow, "net": row["inflow"] - outflow})
    return out


# ---------------------------------------------------------------------------
# Финансовая панель
# ---------------------------------------------------------------------------

def overview(date_from: dt.date, date_to: dt.date, *, today: dt.date | None = None) -> dict:
    from apps.billing.services.analytics import finance_analytics
    from apps.billing.services.reports import dashboard as billing_dashboard
    from apps.billing.services.prepayments import prepayments
    from apps.billing.models import Invoice

    today = today or timezone.localdate()
    current = _core(date_from, date_to)
    prev_from, prev_to = previous_range(date_from, date_to)
    previous = _core(prev_from, prev_to)

    billing = finance_analytics({}, date_from=date_from, date_to=date_to)
    now = billing_dashboard({}, on=today)
    prepay = prepayments({})["summary"]
    invoiced = Invoice.objects.filter(
        period_date__gte=date_from, period_date__lte=date_to,
        status__in=(Invoice.Status.OPEN, Invoice.Status.PARTIALLY_PAID, Invoice.Status.OVERDUE, Invoice.Status.PAID),
    ).aggregate(s=Sum("amount"), n=Count("pk"))

    by_method = defaultdict(lambda: {"inflow": ZERO, "outflow": ZERO})
    payments = StudentPayment.objects.filter(status=StudentPayment.Status.CONFIRMED, received_date__gte=date_from,
                                             received_date__lte=date_to)
    for r in payments.values("method", "kind").annotate(s=Sum("amount")):
        by_method[r["method"]]["inflow" if r["kind"] == StudentPayment.Kind.PAYMENT else "outflow"] += r["s"]
    for r in PayrollPayment.objects.filter(status=PayrollPayment.Status.CONFIRMED, payment_date__gte=date_from,
                                           payment_date__lte=date_to).values("payment_method").annotate(s=Sum("amount")):
        by_method[r["payment_method"]]["outflow"] += r["s"]
    for r in Expense.objects.filter(status=Expense.Status.PAID, paid_date__gte=date_from, paid_date__lte=date_to) \
            .values("payment_method").annotate(s=Sum("amount")):
        by_method[r["payment_method"]]["outflow"] += r["s"]

    c, p = current, previous
    return money_all({
        "date_from": date_from, "date_to": date_to,
        "previous_period": {"date_from": prev_from, "date_to": prev_to},
        "branches_supported": False,
        "students": {
            **c["students"],
            "invoiced": invoiced["s"] or ZERO, "invoiced_count": invoiced["n"],
            "expected": Decimal(billing["expected"]["amount"]), "expected_paid": Decimal(billing["expected"]["paid"]),
            "debt_end": Decimal(billing["debt_end"]),
            "debt_now": Decimal(now["total_debt"]), "overdue_now": Decimal(now["overdue_amount"]),
            "overdue_students": now["overdue_students"], "students_awaiting": now["students_awaiting"],
            "prepayment": prepay["prepayment"], "prepayment_students": prepay["students"],
            "unallocated_credit": prepay["unallocated"], "prepayment_review": prepay["review"],
        },
        "payroll": {**c["payroll"], "outstanding_now": outstanding_debt()},
        "expenses": {**c["expenses"], **{f"unpaid_now_{k}": v for k, v in expense_service.unpaid_summary(on=today).items()}},
        "cash_flow": {
            **c["cash_flow"],
            "by_method": [{"method": k, "method_display": METHOD_LABELS.get(k, k), "inflow": v["inflow"],
                           "outflow": v["outflow"], "net": v["inflow"] - v["outflow"]}
                          for k, v in sorted(by_method.items())],
        },
        "result": {
            "cash": c["cash_flow"]["net"],
            "cash_basis": "Денежный результат = поступления − возвраты − выплаченная зарплата − оплаченные расходы.",
            "accrual": None,
            "accrual_note": ACCRUAL_RESULT_NOTE,
        },
        "comparison": {
            "student_receipts": _change(c["students"]["net"], p["students"]["net"]),
            "payroll_accrued": _change(c["payroll"]["accrued"], p["payroll"]["accrued"]),
            "payroll_paid": _change(c["payroll"]["paid_cash"], p["payroll"]["paid_cash"]),
            "expenses_paid": _change(c["expenses"]["paid"], p["expenses"]["paid"]),
            "cash_flow_net": _change(c["cash_flow"]["net"], p["cash_flow"]["net"]),
        },
        "history": _history(date_to),
        "definitions": {
            "students.gross": "Подтверждённые платежи студентов по дате поступления денег.",
            "students.invoiced": "Начисления студентам по периоду начисления — требование оплаты, не доход и не деньги.",
            "students.debt_now": "Остаток неоплаченных начислений на сегодня (как в «Оплата студентов → Dashboard»).",
            "students.prepayment": "Полученные заранее деньги, ещё не зачтённые в обучение, — обязательство перед родителями.",
            "payroll.accrued": "Утверждённые начисления зарплаты за расчётные периоды внутри выбранного диапазона.",
            "payroll.paid_cash": "Выплаты сотрудникам с датой перевода в периоде (за любые месяцы).",
            "payroll.outstanding_now": "Утверждено и ещё не выплачено (после удержаний), на сегодня.",
            "expenses.paid": "Оплаченные расходы по дате оплаты.",
            "expenses.incurred": "Действующие расходы по дате расхода, оплаченные и нет.",
        },
    })


# ---------------------------------------------------------------------------
# Касса: движение денежных средств
# ---------------------------------------------------------------------------

KINDS = {
    "student_payment": "Платёж студента",
    "student_refund": "Возврат студенту",
    "payroll_payment": "Выплата зарплаты",
    "expense": "Оплата расхода",
}


def cash_movements(date_from: dt.date, date_to: dt.date, *, kind: str | None = None, method: str | None = None,
                   direction: str | None = None, search: str | None = None) -> dict:
    """Все фактические движения денег за период одной лентой: приход — платежи
    студентов, расход — возвраты, выплаты зарплаты и оплаченные расходы.
    Отменённые записи и неоплаченные расходы сюда не попадают."""
    rows: list[dict] = []
    if kind in (None, "", "student_payment", "student_refund"):
        qs = StudentPayment.objects.filter(status=StudentPayment.Status.CONFIRMED, received_date__gte=date_from,
                                           received_date__lte=date_to).select_related("student", "group")
        if kind == "student_payment":
            qs = qs.filter(kind=StudentPayment.Kind.PAYMENT)
        elif kind == "student_refund":
            qs = qs.filter(kind=StudentPayment.Kind.REFUND)
        for p in qs:
            refund = p.kind == StudentPayment.Kind.REFUND
            rows.append({
                "key": f"sp-{p.pk}", "date": p.received_date, "kind": "student_refund" if refund else "student_payment",
                "direction": "out" if refund else "in", "amount": p.amount, "method": p.method,
                "counterparty": str(p.student), "description": p.group.name if p.group_id else "",
                "reference": p.reference, "source_id": p.pk,
                "link": f"/finance/payments/{p.pk}" if p.billing_profile_id else "/accounting/student-payments",
            })
    if kind in (None, "", "payroll_payment"):
        qs = PayrollPayment.objects.filter(status=PayrollPayment.Status.CONFIRMED, payment_date__gte=date_from,
                                           payment_date__lte=date_to).select_related("payroll__employee", "payroll__period")
        for p in qs:
            employee = p.payroll.employee
            rows.append({
                "key": f"pp-{p.pk}", "date": p.payment_date, "kind": "payroll_payment", "direction": "out",
                "amount": p.amount, "method": p.payment_method,
                "counterparty": employee.get_full_name() or employee.username,
                "description": ("Аванс · " if p.is_advance else "") + f"зарплата за {period_label(p.payroll.period)}",
                "reference": p.reference, "source_id": p.pk, "link": f"/accounting/payrolls/{p.payroll_id}",
            })
    if kind in (None, "", "expense"):
        qs = Expense.objects.filter(status=Expense.Status.PAID, paid_date__gte=date_from,
                                    paid_date__lte=date_to).select_related("category")
        for e in qs:
            rows.append({
                "key": f"ex-{e.pk}", "date": e.paid_date, "kind": "expense", "direction": "out", "amount": e.amount,
                "method": e.payment_method, "counterparty": e.vendor or "—",
                "description": f"{e.category.name}: {e.description}", "reference": e.reference, "source_id": e.pk,
                "link": f"/accounting/expenses?expense={e.pk}",
            })
    if method:
        rows = [r for r in rows if r["method"] == method]
    if direction in ("in", "out"):
        rows = [r for r in rows if r["direction"] == direction]
    for part in (search or "").lower().split():
        rows = [r for r in rows if part in f"{r['counterparty']} {r['description']} {r['reference']}".lower()]
    rows.sort(key=lambda r: (r["date"], r["key"]), reverse=True)
    inflow = sum((r["amount"] for r in rows if r["direction"] == "in"), ZERO)
    outflow = sum((r["amount"] for r in rows if r["direction"] == "out"), ZERO)
    methods = defaultdict(lambda: {"inflow": ZERO, "outflow": ZERO})
    for r in rows:
        r["kind_display"] = KINDS[r["kind"]]
        r["method_display"] = METHOD_LABELS.get(r["method"], r["method"])
        methods[r["method"]]["inflow" if r["direction"] == "in" else "outflow"] += r["amount"]
    return money_all({
        "date_from": date_from, "date_to": date_to,
        "summary": {"inflow": money(inflow), "outflow": money(outflow), "net": money(inflow - outflow),
                    "count": len(rows),
                    "by_method": [{"method": k, "method_display": METHOD_LABELS.get(k, k), "inflow": v["inflow"],
                                   "outflow": v["outflow"], "net": v["inflow"] - v["outflow"]}
                                  for k, v in sorted(methods.items())]},
        "note": "Остаток кассы на начало периода в системе не ведётся: показано сальдо движений за период.",
        "results": rows,
    })
