"""Расходы компании: создание, изменение, оплата, отмена, регулярные расходы
и отчёты.

Правила:

* **Неоплаченный расход — обязательство, а не деньги.** В расходы по
  кассовому методу и в движение денежных средств попадают только оплаченные
  расходы — по дате оплаты (`paid_date`). Неоплаченные показываются
  отдельно («к оплате поставщикам»).
* **Без повторного проведения.** `Idempotency-Key` возвращает тот же расход
  при повторе запроса; номер документа поставщика не принимается дважды
  (уникальный индекс `unique_live_expense_document`); регулярный расход
  создаётся не больше одного раза на месяц (`unique_recurring_expense_month`).
* **Без удаления.** Ошибочный расход отменяется (VOID) с причиной; изменение
  оплаченного расхода требует причины. Всё — в журнале аудита
  (`PayrollAuditLog`, `entity_type=expense`).
* Каждая операция — `transaction.atomic()` + `select_for_update` расхода и
  проверка `version` (409 при одновременном изменении).
"""
from __future__ import annotations

import calendar
import datetime as dt
from collections import defaultdict
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.db.models import Count, Q, Sum
from django.utils import timezone

from ..models import Expense, ExpenseCategory, PaymentMethod, RecurringExpense
from . import AccountingError
from . import audit
from .money import ZERO, money, money_all

TRACKED = ("category_id", "description", "amount", "expense_date", "due_date", "vendor", "payment_method",
           "responsible_id", "reference", "comment", "status", "paid_date", "document_name")
EDITABLE = ("category", "description", "amount", "expense_date", "due_date", "vendor", "payment_method",
            "responsible", "reference", "comment")
# Изменение этих полей у оплаченного расхода меняет отчёты о потраченных
# деньгах — только с причиной.
MONEY_FIELDS = ("amount", "category", "payment_method", "expense_date")

MAX_DOCUMENT_BYTES = 10 * 1024 * 1024
DOCUMENT_EXTENSIONS = ("pdf", "jpg", "jpeg", "png", "webp", "heic", "xlsx", "xls", "docx", "doc")
RECURRING_TRACKED = ("category_id", "description", "amount", "vendor", "payment_method", "responsible_id",
                     "day_of_month", "start_month", "end_month", "is_active", "comment")


def _snap(expense: Expense) -> dict:
    return audit.snapshot(expense, TRACKED)


def _today() -> dt.date:
    return timezone.localdate()


def _check_dates(*, expense_date: dt.date | None, paid_date: dt.date | None = None):
    today = _today()
    if paid_date and paid_date > today:
        raise AccountingError("Дата оплаты не может быть в будущем.", code="future_date")
    if expense_date and paid_date and paid_date < expense_date - dt.timedelta(days=366):
        raise AccountingError("Дата оплаты больше чем на год раньше даты расхода — проверьте даты.", code="bad_dates")


def _check_category(category: ExpenseCategory | None, *, current: ExpenseCategory | None = None):
    if category is None:
        raise AccountingError("Укажите категорию расхода.", code="category_required")
    if not category.is_active and category != current:
        raise AccountingError("Категория отключена — выберите действующую.", code="category_inactive")


def _check_document(file) -> None:
    if file is None:
        return
    name = getattr(file, "name", "") or ""
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    if ext not in DOCUMENT_EXTENSIONS:
        raise AccountingError(
            f"Недопустимый тип файла. Разрешены: {', '.join(DOCUMENT_EXTENSIONS)}.", code="bad_document",
        )
    if getattr(file, "size", 0) > MAX_DOCUMENT_BYTES:
        raise AccountingError("Файл больше 10 МБ.", code="document_too_large")


def _duplicate_document(vendor: str, reference: str, *, exclude: int | None = None) -> Expense | None:
    if not reference:
        return None
    qs = Expense.objects.filter(vendor=vendor, reference=reference).exclude(status=Expense.Status.VOID)
    if exclude:
        qs = qs.exclude(pk=exclude)
    return qs.first()


def _duplicate_error(found: Expense) -> AccountingError:
    return AccountingError(
        f"Документ №{found.reference} этого получателя уже проведён (расход #{found.pk} от "
        f"{found.expense_date:%d.%m.%Y}). Повторное проведение запрещено.", code="duplicate_document",
    )


def _lock(expense: Expense, version: int | None) -> Expense:
    locked = Expense.objects.select_for_update().get(pk=expense.pk)
    if version is not None and locked.version != version:
        raise AccountingError("Расход уже изменён другим пользователем — обновите страницу.", code="conflict")
    return locked


def create_expense(*, actor, category, description: str, amount: Decimal, expense_date: dt.date,
                   due_date: dt.date | None = None, vendor: str = "", payment_method: str = PaymentMethod.CASH,
                   responsible=None, reference: str = "", comment: str = "", paid: bool = False,
                   paid_date: dt.date | None = None, document=None, idempotency_key: str | None = None,
                   recurring: RecurringExpense | None = None, recurrence_month: dt.date | None = None) -> tuple[Expense, bool]:
    """Создать расход. Возвращает (расход, создан ли новый): повтор с тем же
    `idempotency_key` возвращает уже созданный расход."""
    if idempotency_key:
        existing = Expense.objects.filter(idempotency_key=idempotency_key).first()
        if existing is not None:
            return existing, False
    _check_category(category)
    amount = money(amount)
    if amount <= 0:
        raise AccountingError("Сумма расхода должна быть больше нуля.", code="bad_amount")
    if not (description or "").strip():
        raise AccountingError("Укажите описание расхода.", code="description_required")
    if paid and paid_date is None:
        paid_date = _today()
    _check_dates(expense_date=expense_date, paid_date=paid_date if paid else None)
    _check_document(document)
    vendor, reference = (vendor or "").strip(), (reference or "").strip()
    with transaction.atomic():
        found = _duplicate_document(vendor, reference)
        if found is not None:
            raise _duplicate_error(found)
        expense = Expense(
            category=category, description=description.strip(), amount=amount, expense_date=expense_date,
            due_date=due_date, vendor=vendor, payment_method=payment_method, responsible=responsible,
            reference=reference, comment=comment or "",
            status=Expense.Status.PAID if paid else Expense.Status.UNPAID, paid_date=paid_date if paid else None,
            idempotency_key=idempotency_key or None, created_by=actor if getattr(actor, "is_authenticated", False) else None,
            recurring=recurring, recurrence_month=recurrence_month,
        )
        if document is not None:
            expense.document = document
            expense.document_name = getattr(document, "name", "")[:255]
        try:
            with transaction.atomic():
                expense.save()
        except IntegrityError:
            if idempotency_key:
                existing = Expense.objects.filter(idempotency_key=idempotency_key).first()
                if existing is not None:
                    return existing, False
            raise AccountingError("Такой расход уже проведён.", code="duplicate")
        audit.log(actor, expense, "expense_create", new=_snap(expense))
    return expense, True


def update_expense(expense: Expense, *, actor, changes: dict, reason: str = "", version: int | None = None) -> Expense:
    """Изменить поля расхода. Отменённый не меняется; у оплаченного сумма,
    категория, способ и дата меняются только с причиной."""
    unknown = set(changes) - set(EDITABLE)
    if unknown:
        raise AccountingError(f"Эти поля нельзя изменить: {', '.join(sorted(unknown))}.", code="bad_field")
    with transaction.atomic():
        expense = _lock(expense, version)
        if expense.status == Expense.Status.VOID:
            raise AccountingError("Отменённый расход не изменяется.", code="void")
        old = _snap(expense)
        if "category" in changes:
            _check_category(changes["category"], current=expense.category)
        if "amount" in changes:
            changes["amount"] = money(changes["amount"])
            if changes["amount"] <= 0:
                raise AccountingError("Сумма расхода должна быть больше нуля.", code="bad_amount")
        if "description" in changes and not (changes["description"] or "").strip():
            raise AccountingError("Укажите описание расхода.", code="description_required")
        for name in ("vendor", "reference", "description"):
            if name in changes:
                changes[name] = (changes[name] or "").strip()
        changed = {name: value for name, value in changes.items() if getattr(expense, name) != value}
        if not changed:
            return expense
        if expense.status == Expense.Status.PAID and set(changed) & set(MONEY_FIELDS) and not reason.strip():
            raise AccountingError("Расход уже оплачен — укажите причину изменения.", code="reason_required")
        for name, value in changed.items():
            setattr(expense, name, value)
        _check_dates(expense_date=expense.expense_date, paid_date=expense.paid_date)
        found = _duplicate_document(expense.vendor, expense.reference, exclude=expense.pk)
        if found is not None:
            raise _duplicate_error(found)
        expense.version += 1
        expense.save()
        audit.log(actor, expense, "expense_update", old=old, new=_snap(expense), reason=reason)
    return expense


def mark_paid(expense: Expense, *, actor, paid_date: dt.date | None = None, payment_method: str | None = None,
              reference: str | None = None, version: int | None = None) -> Expense:
    """Отметить оплату. Повторная отметка — ошибка (деньги не проводятся
    дважды); исправить дату оплаты — «Отменить оплату» и отметить снова."""
    paid_date = paid_date or _today()
    with transaction.atomic():
        expense = _lock(expense, version)
        if expense.status == Expense.Status.VOID:
            raise AccountingError("Расход отменён.", code="void")
        if expense.status == Expense.Status.PAID:
            raise AccountingError(f"Расход уже оплачен {expense.paid_date:%d.%m.%Y}.", code="already_paid")
        _check_dates(expense_date=expense.expense_date, paid_date=paid_date)
        old = _snap(expense)
        expense.status, expense.paid_date = Expense.Status.PAID, paid_date
        if payment_method:
            expense.payment_method = payment_method
        if reference is not None and reference.strip():
            expense.reference = reference.strip()
            found = _duplicate_document(expense.vendor, expense.reference, exclude=expense.pk)
            if found is not None:
                raise _duplicate_error(found)
        expense.version += 1
        expense.save()
        audit.log(actor, expense, "expense_pay", old=old, new=_snap(expense))
    return expense


def unmark_paid(expense: Expense, *, actor, reason: str, version: int | None = None) -> Expense:
    """Отменить отметку об оплате (ошибочная дата или оплата не состоялась)."""
    if not (reason or "").strip():
        raise AccountingError("Укажите причину.", code="reason_required")
    with transaction.atomic():
        expense = _lock(expense, version)
        if expense.status != Expense.Status.PAID:
            raise AccountingError("Расход не оплачен.", code="not_paid")
        old = _snap(expense)
        expense.status, expense.paid_date = Expense.Status.UNPAID, None
        expense.version += 1
        expense.save()
        audit.log(actor, expense, "expense_unpay", old=old, new=_snap(expense), reason=reason)
    return expense


def void_expense(expense: Expense, *, actor, reason: str, version: int | None = None) -> Expense:
    """Отменить ошибочный расход (оплаченный тоже): он перестаёт учитываться
    в отчётах, запись и история остаются."""
    if not (reason or "").strip():
        raise AccountingError("Укажите причину отмены.", code="reason_required")
    with transaction.atomic():
        expense = _lock(expense, version)
        if expense.status == Expense.Status.VOID:
            raise AccountingError("Расход уже отменён.", code="void")
        old = _snap(expense)
        expense.status, expense.void_reason = Expense.Status.VOID, reason.strip()
        expense.voided_by = actor if getattr(actor, "is_authenticated", False) else None
        expense.voided_at = timezone.now()
        expense.version += 1
        expense.save()
        audit.log(actor, expense, "expense_void", old=old, new=_snap(expense), reason=reason)
    return expense


def attach_document(expense: Expense, *, actor, document, version: int | None = None) -> Expense:
    _check_document(document)
    if document is None:
        raise AccountingError("Выберите файл.", code="document_required")
    with transaction.atomic():
        expense = _lock(expense, version)
        if expense.status == Expense.Status.VOID:
            raise AccountingError("Отменённый расход не изменяется.", code="void")
        old = _snap(expense)
        # Прежний файл не удаляется с диска: он остаётся в истории (аудит хранит его имя).
        expense.document = document
        expense.document_name = getattr(document, "name", "")[:255]
        expense.version += 1
        expense.save()
        audit.log(actor, expense, "expense_document", old=old, new=_snap(expense))
    return expense


# ---------------------------------------------------------------------------
# Категории
# ---------------------------------------------------------------------------

def save_category(*, actor, category: ExpenseCategory | None = None, **fields) -> ExpenseCategory:
    name = (fields.get("name") or (category.name if category else "")).strip()
    if not name:
        raise AccountingError("Укажите название категории.", code="name_required")
    # Сравнение без учёта регистра — в Python: SQLite не сворачивает регистр кириллицы.
    others = ExpenseCategory.objects.exclude(pk=getattr(category, "pk", None)).values_list("name", flat=True)
    if name.casefold() in {n.casefold() for n in others}:
        raise AccountingError("Категория с таким названием уже есть.", code="duplicate")
    with transaction.atomic():
        if category is None:
            code = fields.get("code") or _free_code(name)
            if ExpenseCategory.objects.filter(code=code).exists():
                raise AccountingError("Категория с таким кодом уже есть.", code="duplicate")
            category = ExpenseCategory.objects.create(
                code=code, name=name, description=fields.get("description", ""),
                sort_order=fields.get("sort_order", 100), is_active=fields.get("is_active", True),
            )
            audit.log(actor, category, "expense_category_create",
                      new=audit.snapshot(category, ("code", "name", "description", "sort_order", "is_active")))
            return category
        tracked = ("name", "description", "sort_order", "is_active")
        old = audit.snapshot(category, tracked)
        for key in tracked:
            if key in fields:
                setattr(category, key, name if key == "name" else fields[key])
        category.save()
        audit.log(actor, category, "expense_category_update", old=old, new=audit.snapshot(category, tracked))
    return category


def _free_code(name: str) -> str:
    from django.utils.text import slugify

    base = (slugify(name, allow_unicode=False) or "category")[:30]
    code, n = base, 1
    while ExpenseCategory.objects.filter(code=code).exists():
        n += 1
        code = f"{base}-{n}"
    return code


# ---------------------------------------------------------------------------
# Регулярные расходы
# ---------------------------------------------------------------------------

def _first(day: dt.date) -> dt.date:
    return day.replace(day=1)


def save_recurring(*, actor, recurring: RecurringExpense | None = None, **fields) -> RecurringExpense:
    if "start_month" in fields and fields["start_month"]:
        fields["start_month"] = _first(fields["start_month"])
    if fields.get("end_month"):
        fields["end_month"] = _first(fields["end_month"])
    if "amount" in fields:
        fields["amount"] = money(fields["amount"])
        if fields["amount"] <= 0:
            raise AccountingError("Сумма должна быть больше нуля.", code="bad_amount")
    with transaction.atomic():
        if recurring is None:
            _check_category(fields.get("category"))
            if not fields.get("start_month"):
                raise AccountingError("Укажите месяц начала.", code="start_required")
            recurring = RecurringExpense(created_by=actor, **fields)
            old = {}
            action = "recurring_expense_create"
        else:
            recurring = RecurringExpense.objects.select_for_update().get(pk=recurring.pk)
            if "category" in fields:
                _check_category(fields["category"], current=recurring.category)
            old = audit.snapshot(recurring, RECURRING_TRACKED)
            for key, value in fields.items():
                setattr(recurring, key, value)
            action = "recurring_expense_update"
        if recurring.end_month and recurring.end_month < recurring.start_month:
            raise AccountingError("Месяц окончания раньше месяца начала.", code="bad_range")
        recurring.save()
        audit.log(actor, recurring, action, old=old, new=audit.snapshot(recurring, RECURRING_TRACKED))
    return recurring


def generate_recurring(year: int, month: int, *, actor=None) -> dict:
    """Создать неоплаченные расходы месяца по действующим шаблонам. Уже
    созданные (в том числе отменённые) не создаются повторно."""
    month_start = dt.date(year, month, 1)
    last_day = calendar.monthrange(year, month)[1]
    created, skipped = [], []
    templates = RecurringExpense.objects.filter(is_active=True, start_month__lte=month_start).filter(
        Q(end_month__isnull=True) | Q(end_month__gte=month_start),
    ).select_related("category", "responsible")
    for template in templates:
        if Expense.objects.filter(recurring=template, recurrence_month=month_start).exists():
            skipped.append(template.pk)
            continue
        on = dt.date(year, month, min(template.day_of_month, last_day))
        try:
            expense, is_new = create_expense(
                actor=actor, category=template.category, description=template.description, amount=template.amount,
                expense_date=on, due_date=on, vendor=template.vendor, payment_method=template.payment_method,
                responsible=template.responsible, comment=template.comment,
                idempotency_key=f"recurring:{template.pk}:{month_start:%Y-%m}",
                recurring=template, recurrence_month=month_start,
            )
        except AccountingError:
            skipped.append(template.pk)
            continue
        (created if is_new else skipped).append(expense.pk if is_new else template.pk)
    return {"year": year, "month": month, "created": created, "skipped": skipped}


# ---------------------------------------------------------------------------
# Выборки и отчёты
# ---------------------------------------------------------------------------

def filter_expenses(qs, f: dict):
    """Фильтры списка: поиск, категория, статус, способ, ответственный,
    период по дате расхода (`date_from`/`date_to`) или по дате оплаты
    (`paid_from`/`paid_to`), регулярные, просроченные."""
    if f.get("search"):
        for part in f["search"].split():
            qs = qs.filter(Q(description__icontains=part) | Q(vendor__icontains=part) | Q(reference__icontains=part)
                           | Q(comment__icontains=part))
    if f.get("category"):
        qs = qs.filter(category_id=f["category"])
    if f.get("status"):
        qs = qs.filter(status=f["status"])
    else:
        qs = qs.exclude(status=Expense.Status.VOID) if not f.get("include_void") else qs
    if f.get("payment_method"):
        qs = qs.filter(payment_method=f["payment_method"])
    if f.get("responsible"):
        qs = qs.filter(responsible_id=f["responsible"])
    if f.get("vendor"):
        qs = qs.filter(vendor__icontains=f["vendor"])
    if f.get("date_from"):
        qs = qs.filter(expense_date__gte=f["date_from"])
    if f.get("date_to"):
        qs = qs.filter(expense_date__lte=f["date_to"])
    if f.get("paid_from"):
        qs = qs.filter(paid_date__gte=f["paid_from"])
    if f.get("paid_to"):
        qs = qs.filter(paid_date__lte=f["paid_to"])
    if f.get("recurring") in (True, "1", "true"):
        qs = qs.filter(recurring__isnull=False)
    if f.get("overdue") in (True, "1", "true"):
        qs = qs.filter(status=Expense.Status.UNPAID, due_date__lt=_today())
    return qs


def paid_total(date_from: dt.date, date_to: dt.date) -> Decimal:
    """Потрачено деньгами: оплаченные расходы по дате оплаты."""
    return Expense.objects.filter(status=Expense.Status.PAID, paid_date__gte=date_from,
                                  paid_date__lte=date_to).aggregate(s=Sum("amount"))["s"] or ZERO


def unpaid_summary(*, on: dt.date | None = None) -> dict:
    on = on or _today()
    unpaid = Expense.objects.filter(status=Expense.Status.UNPAID)
    agg = unpaid.aggregate(s=Sum("amount"), n=Count("pk"),
                           overdue=Sum("amount", filter=Q(due_date__lt=on)), n_overdue=Count("pk", filter=Q(due_date__lt=on)))
    return {"amount": money(agg["s"] or ZERO), "count": agg["n"], "overdue_amount": money(agg["overdue"] or ZERO),
            "overdue_count": agg["n_overdue"]}


def _months(date_from: dt.date, date_to: dt.date) -> list[tuple[int, int]]:
    out, y, m = [], date_from.year, date_from.month
    while (y, m) <= (date_to.year, date_to.month):
        out.append((y, m))
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def report(date_from: dt.date, date_to: dt.date, filters: dict | None = None) -> dict:
    """Отчёт по категориям и месяцам за период.

    * **Оплачено** — оплаченные расходы по дате оплаты (кассовый метод) —
      это и есть потраченные деньги;
    * **Начислено** — все неотменённые расходы по дате расхода (оплаченные и
      нет) — обязательства периода;
    * **Не оплачено** — расходы периода (по дате расхода), ещё не оплаченные.
    """
    f = {k: v for k, v in (filters or {}).items() if k not in ("date_from", "date_to", "paid_from", "paid_to", "status")}
    base = filter_expenses(Expense.objects.all(), f).exclude(status=Expense.Status.VOID)
    paid = base.filter(status=Expense.Status.PAID, paid_date__gte=date_from, paid_date__lte=date_to)
    incurred = base.filter(expense_date__gte=date_from, expense_date__lte=date_to)
    categories = {c.pk: c for c in ExpenseCategory.objects.all()}
    rows: dict[int, dict] = {}

    def row(category_id):
        c = categories[category_id]
        return rows.setdefault(category_id, {"category": c.pk, "category_name": c.name, "sort_order": c.sort_order,
                                             "paid": ZERO, "paid_count": 0, "incurred": ZERO, "unpaid": ZERO})

    for r in paid.values("category_id").annotate(s=Sum("amount"), n=Count("pk")):
        row(r["category_id"]).update(paid=r["s"], paid_count=r["n"])
    for r in incurred.values("category_id").annotate(
            s=Sum("amount"), u=Sum("amount", filter=Q(status=Expense.Status.UNPAID))):
        row(r["category_id"]).update(incurred=r["s"], unpaid=r["u"] or ZERO)
    by_month = defaultdict(lambda: {"paid": ZERO, "incurred": ZERO})
    for e in paid.only("paid_date", "amount"):
        by_month[(e.paid_date.year, e.paid_date.month)]["paid"] += e.amount
    for e in incurred.only("expense_date", "amount"):
        by_month[(e.expense_date.year, e.expense_date.month)]["incurred"] += e.amount
    by_category = sorted(rows.values(), key=lambda r: (r.pop("sort_order"), r["category_name"]))
    total_paid = sum((r["paid"] for r in by_category), ZERO)
    for r in by_category:
        r["share_percent"] = (r["paid"] * 100 / total_paid).quantize(Decimal("0.1")) if total_paid else None
    return money_all({
        "date_from": date_from, "date_to": date_to,
        "paid": total_paid, "paid_count": sum(r["paid_count"] for r in by_category),
        "incurred": sum((r["incurred"] for r in by_category), ZERO),
        "unpaid": sum((r["unpaid"] for r in by_category), ZERO),
        "by_category": by_category,
        "by_month": [{"year": y, "month": m, **by_month[(y, m)]} for y, m in _months(date_from, date_to)],
        "unpaid_now": unpaid_summary(),
        "definitions": {
            "paid": "Оплаченные расходы по дате оплаты — фактически потраченные деньги.",
            "incurred": "Все действующие расходы по дате расхода (оплаченные и нет) — обязательства периода.",
            "unpaid": "Расходы периода, которые ещё не оплачены — это не потраченные деньги.",
        },
    })
