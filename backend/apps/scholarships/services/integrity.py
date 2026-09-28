"""Rows that break the award money rules — checked by migration 0006
before the schema is tightened, and by `manage.py scholarship_integrity`.

Nothing here changes data. The functions take the award *model* so the
migration can pass its historical model; only columns that existed before
0006 are read (values()), so this also works on a database that has not
been migrated yet.
"""
from __future__ import annotations

from collections import defaultdict

PAID, UNPAID = "paid", "unpaid"

# problem code → human description
PROBLEMS = {
    "amount_null": "сумма не задана (NULL)",
    "amount_negative": "отрицательная сумма",
    "paid_not_approved": "выдана, но период не утверждён",
    "paid_no_money": "выдана, но сумма стипендии 0 или не задана",
    "paid_incomplete": "выдана без даты, «кто выдал», выплаченной суммы или способа",
    "paid_over_amount": "выплачено больше начисленного",
    "unpaid_has_payment_data": "не выдана, но содержит данные выплаты",
    "bad_payment_status": "неизвестный статус выплаты",
}
# Problems `scholarship_integrity --fix-unpaid-null-amounts` may resolve:
# an unpaid award without an amount meant «стипендия без денежной суммы»,
# which is now amount = 0. Everything else needs a person to decide.
FIXABLE = {"amount_null"}


def _problems(row: dict) -> list[str]:
    found = []
    amount, status = row["amount"], row["payment_status"]
    if amount is None:
        found.append("amount_null")
    elif amount < 0:
        found.append("amount_negative")
    if status == PAID:
        if row["status"] != "approved":
            found.append("paid_not_approved")
        if amount is None or amount <= 0:
            found.append("paid_no_money")
        if row["paid_at"] is None or row["paid_by_id"] is None or row["paid_amount"] is None or not row["payment_method"]:
            found.append("paid_incomplete")
        if row["paid_amount"] is not None and (row["paid_amount"] < 0 or (amount is not None and row["paid_amount"] > amount)):
            found.append("paid_over_amount")
    elif status == UNPAID:
        if row["paid_at"] or row["paid_by_id"] or row["paid_amount"] is not None or row["payment_method"]:
            found.append("unpaid_has_payment_data")
    else:
        found.append("bad_payment_status")
    return found


def find_conflicts(award_model) -> list[dict]:
    """Every award that breaks a rule: id, period, student, the problems."""
    rows = award_model.objects.order_by("pk").values(
        "pk", "period_id", "evaluation__student_name", "amount", "status", "payment_status",
        "paid_at", "paid_by_id", "paid_amount", "payment_method",
    )
    conflicts = []
    for row in rows:
        problems = _problems(row)
        if problems:
            conflicts.append({**row, "problems": problems})
    return conflicts


def describe(conflicts: list[dict], limit: int = 20) -> str:
    by_problem = defaultdict(list)
    for row in conflicts:
        for problem in row["problems"]:
            by_problem[problem].append(row)
    lines = []
    for problem, rows in by_problem.items():
        lines.append(f"  • {PROBLEMS[problem]}: {len(rows)}")
        for row in rows[:limit]:
            lines.append(
                f"      #{row['pk']} период {row['period_id']}, {row['evaluation__student_name']}, "
                f"сумма {row['amount']}, выплата {row['payment_status']}"
            )
        if len(rows) > limit:
            lines.append(f"      … и ещё {len(rows) - limit}")
    return "\n".join(lines)
