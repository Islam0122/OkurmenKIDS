"""«Скоро оплата» — предстоящие платежи по дате срока (только чтение).

Подразделы считаются при каждом запросе на сервере по актуальным данным
(как «К оплате» / «Просроченные», `contracts.payment_stage`), а не по
сохранённому статусу, который обновляет Railway Cron. Записи не меняются.

Единица расчёта — **финансовое обязательство**, а не студент:

* выставленное неоплаченное начисление, срок которого ещё не наступил
  (стадия `awaiting`; срок сегодня — `deadline` — это «К оплате», срок
  прошёл — «Просроченные», в будущие подразделы они не попадают);
* следующий учебный месяц договора (пакет тарифа), который ещё не выставлен,
  — прогноз по тем же правилам, по которым его выставит
  `invoices.create_next_package_invoice` (сумма — `contracts.next_month_cost`).

Дата срока обязательства — по действующим правилам:

* срок датой (`Invoice.due_date`, тарифы пакетов) — сама дата начисления;
* срок в уроках (договор по программе: `deadline_lessons`-й зачтённый урок
  месяца) — дата того урока по расписанию группы ученика: ближайшие
  запланированные занятия приоритетного предмета договора (`Lesson`,
  `scheduled` / `in_progress`, с сегодняшнего дня). Нужно уроков: остаток
  текущего месяца (для следующего месяца) + урок-срок − уже засчитано;
* невыставленный пакет тарифа без программы — урок, на котором он будет
  выставлен (конец пакета или ранний счёт), + `payment_due_days`.

Даты нет (нет группы, ученик / договор не обучается, в расписании не хватает
занятий, урок не засчитывается договору) — обязательство в подразделы не
попадает (`undated`): дата не подтверждена, не выдумывается.

Подраздел — по числу календарных дней до срока (Asia/Bishkek,
`timezone.localdate`): 1–3, 4–5, 6–10; «Следующий месяц» — срок в следующем
календарном месяце и больше 10 дней. Сегодня, прошедшие сроки и сроки позже
следующего месяца — ни в один подраздел.

Сумма обязательства — к оплате после аванса, который правила договора
разрешают направить (`contracts.applicable_credit`, тот же порядок, что в
«К оплате сейчас»: сначала просроченное, затем срок сегодня, затем по дате
срока). Покрытое авансом (к оплате 0) — не предстоящий платёж. Разные
начисления не объединяются: у студента может быть несколько обязательств в
разных подразделах, каждое показано отдельно.

«Полностью оплатили курс» — `contracts.course_paid_in_full` (то же правило,
что в карточке).
"""
from __future__ import annotations

import datetime as dt
from decimal import Decimal

from apps.academy.models import Lesson, Student
from apps.accounting.services.money import money

from ..models import Invoice, LessonPackage, StudentBillingProfile

ZERO = Decimal("0.00")
TIME_SECTIONS = ("days_1_3", "days_4_5", "days_6_10", "next_month")
PAID_COURSE = "paid_course"
SECTIONS = TIME_SECTIONS + (PAID_COURSE,)
LOOKAHEAD_LESSONS = 120  # уроков расписания вперёд (≥ остаток месяца + урок-срок)
UPCOMING = (Lesson.Status.SCHEDULED, Lesson.Status.IN_PROGRESS)


def next_month_start(today: dt.date) -> dt.date:
    return (today.replace(day=1) + dt.timedelta(days=32)).replace(day=1)


def section_for(due: dt.date | None, today: dt.date) -> str | None:
    """Подраздел срока: календарные дни от сегодняшней даты проекта."""
    if due is None:
        return None
    days = (due - today).days
    if days < 1:
        return None
    if days <= 3:
        return "days_1_3"
    if days <= 5:
        return "days_4_5"
    if days <= 10:
        return "days_6_10"
    start = next_month_start(today)
    if (due.year, due.month) == (start.year, start.month):
        return "next_month"
    return None


class LessonCalendar:
    """Ближайшие запланированные уроки, которые будут засчитаны договору
    (те же условия, что `lessons.chargeable_profiles`, кроме посещаемости —
    она ещё неизвестна). Расписание группы читается один раз на запрос."""

    def __init__(self, today: dt.date):
        self.today = today
        self._cache: dict = {}

    def upcoming(self, profile: StudentBillingProfile) -> list[dt.date] | None:
        student = profile.student
        if (not student.group_id or profile.stopped_on or profile.status != StudentBillingProfile.Status.ACTIVE
                or student.status != Student.Status.ACTIVE):
            return None  # не обучается — уроки не засчитываются, даты нет
        group = student.group
        if profile.plan.course_id and profile.plan.course_id != group.course_id:
            return None
        key = (group.pk, profile.subject_id)
        if key not in self._cache:
            qs = Lesson.objects.filter(group_id=group.pk, date__gte=self.today, status__in=UPCOMING)
            if profile.subject_id:
                qs = qs.filter(subject_id=profile.subject_id)
            self._cache[key] = list(qs.order_by("date", "start_time", "pk")
                                    .values_list("date", flat=True)[:LOOKAHEAD_LESSONS])
        return [d for d in self._cache[key] if d >= profile.start_date]

    def nth(self, profile, k: int) -> dt.date | None:
        """Дата k-го (с 1) ближайшего засчитываемого урока; None — не известна."""
        dates = self.upcoming(profile)
        if dates is None or k < 1 or k > len(dates):
            return None
        return dates[k - 1]


def _lessons_before(package: LessonPackage, packages: list[LessonPackage]) -> int | None:
    """Сколько уроков уйдёт в более ранние пакеты, прежде чем начнётся `package`
    (уроки идут в текущий пакет, затем в следующие по номеру)."""
    if package.status == LessonPackage.Status.ACTIVE:
        return 0
    if package.status != LessonPackage.Status.PLANNED:
        return None
    return sum(p.lessons_remaining for p in packages
               if p.status == LessonPackage.Status.ACTIVE
               or (p.status == LessonPackage.Status.PLANNED and p.number < package.number))


def invoice_due(invoice: Invoice, packages: list[LessonPackage], profile, calendar: LessonCalendar):
    """(дата срока, основание) выставленного начисления; дата None — не известна."""
    if not invoice.due_lesson:
        return invoice.due_date, "invoice_date"
    before = _lessons_before(invoice.package, packages)
    if before is None:
        return None, "schedule"
    return calendar.nth(profile, before + invoice.due_lesson - invoice.package.lessons_used), "schedule"


def forecast_due(profile, packages: list[LessonPackage], calendar: LessonCalendar):
    """Следующий, ещё не выставленный месяц / пакет: (номер, дата срока).
    None — следующего нет (курс кончается, уже создан, договор не продолжается)."""
    if profile.status != StudentBillingProfile.Status.ACTIVE:
        return None
    current = next((p for p in packages if p.status == LessonPackage.Status.ACTIVE), None)
    if current is None or any(p.status == LessonPackage.Status.PLANNED for p in packages):
        return None  # следующий уже создан — его начисление считается как выставленное
    remaining = current.lessons_remaining
    if profile.is_course:
        number = (current.month_number or 0) + 1
        if number > (profile.duration_months or 0):
            return None
        # Начисление выставит последний урок месяца; срок — урок `deadline_lessons`
        # нового месяца (без урока-срока — день выставления).
        return number, calendar.nth(profile, remaining + (profile.deadline_lessons or 0))
    plan = profile.plan
    issue_k = remaining
    if plan.early_invoice_enabled and plan.early_invoice_after_lessons:
        early = plan.early_invoice_after_lessons - current.lessons_used
        if 0 < early < remaining:
            issue_k = early
    issued = calendar.nth(profile, issue_k)
    due = None if issued is None else issued + dt.timedelta(days=plan.payment_due_days)
    return current.number + 1, due


def _s(value) -> str:
    return str(money(value))


def upcoming_obligations(profile, *, invoices: list[Invoice], stages: dict, packages: list[LessonPackage],
                         usable: Decimal, today: dt.date, calendar: LessonCalendar) -> dict:
    """Предстоящие обязательства договора с подразделами (см. модуль).

    {"items": [...], "undated": bool} — `items` только с подразделом и
    суммой к оплате > 0."""
    from .contracts import next_month_cost

    awaiting = [i for i in invoices if stages[i.pk] == "awaiting"]
    dues = {i.pk: invoice_due(i, packages, profile, calendar) for i in awaiting}
    # Аванс — как в «К оплате сейчас»: просроченное, срок сегодня, затем по сроку.
    left = usable
    for stage in ("overdue", "deadline"):
        left -= sum((i.balance for i in invoices if stages[i.pk] == stage), ZERO)
    left = max(left, ZERO)
    far = dt.date.max
    items, undated = [], False
    for inv in sorted(awaiting, key=lambda i: (dues[i.pk][0] or far, i.pk)):
        due, basis = dues[inv.pk]
        applied = min(left, inv.balance)
        left -= applied
        to_pay = inv.balance - applied
        if to_pay <= 0:
            continue  # покрыто авансом — предстоящего платежа нет
        if due is None:
            undated = True
            continue
        section = section_for(due, today)
        if section is None:
            continue
        items.append({
            "key": f"invoice:{inv.pk}", "source": "invoice", "invoice": inv.pk, "number": inv.number,
            "kind": inv.kind, "month_number": inv.package.month_number or inv.package.number,
            "due_date": due.isoformat(), "days": (due - today).days, "date_basis": basis,
            "due_lesson": inv.due_lesson, "amount": _s(inv.amount), "paid": _s(inv.amount_paid + inv.amount_adjusted),
            "balance": _s(inv.balance), "credit_applied": _s(applied), "to_pay": _s(to_pay), "section": section,
        })
    forecast = forecast_due(profile, packages, calendar)
    if forecast is not None:
        number, due = forecast
        section = section_for(due, today)
        if due is None:
            undated = True
        elif section is not None:
            nxt = next_month_cost(profile)  # сумма — только для попавших в подраздел
            if nxt is not None and nxt["to_pay"] > 0:
                items.append({
                    "key": f"next:{nxt['month_number']}", "source": "forecast", "invoice": None, "number": None,
                    "kind": Invoice.Kind.MONTH if profile.is_course else Invoice.Kind.PACKAGE,
                    "month_number": nxt["month_number"], "due_date": due.isoformat(), "days": (due - today).days,
                    "date_basis": "schedule",
                    "due_lesson": (profile.deadline_lessons or None) if profile.is_course else None,
                    "amount": _s(nxt["cost"]), "paid": _s(nxt.get("prepaid", ZERO)),
                    "balance": _s(nxt["cost"] - nxt.get("prepaid", ZERO)),
                    "credit_applied": _s(nxt["covered"] - nxt.get("prepaid", ZERO)), "to_pay": _s(nxt["to_pay"]),
                    "section": section,
                })
    items.sort(key=lambda o: (o["days"], o["key"]))
    return {"items": items, "undated": undated}


__all__ = ["LessonCalendar", "PAID_COURSE", "SECTIONS", "TIME_SECTIONS", "section_for", "upcoming_obligations"]
