"""«Отчёты по стипендиям» — who got how much, for which period.

Read-only, built from the stored evaluations and awards (the numbers a
ranking was actually decided on) — nothing is recalculated here, so the
on-screen report and the PDF can never disagree with a period's dashboard.

A scholarship period belongs to the report when it *ended* inside the
chosen date range: every period is counted in exactly one month, even in
the twice-monthly mode where periods straddle month boundaries.

Payment status of one student in one period:

* «Получил»    — the award is approved (the period is approved);
* «Ожидает»    — the award exists but the period is not approved yet;
* «Не получил» — evaluated in the period, but no award.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from decimal import Decimal

from django.db.models import F, Q

from ..models import EligibilityStatus, ScholarshipAward, ScholarshipEvaluation, ScholarshipPeriod


class PaymentStatus:
    RECEIVED = "received"
    PENDING = "pending"
    NOT_RECEIVED = "not_received"

    LABELS = {
        RECEIVED: "Получил",
        PENDING: "Ожидает",
        NOT_RECEIVED: "Не получил",
    }
    # Table order inside one period: paid first, then waiting, then the rest.
    ORDER = {RECEIVED: 0, PENDING: 1, NOT_RECEIVED: 2}


STATUS_CHOICES = [("", "Все статусы"), *PaymentStatus.LABELS.items()]

PRESET_THIS_MONTH = "this_month"
PRESET_LAST_MONTH = "last_month"
PRESET_CUSTOM = "custom"
PRESETS = {
    PRESET_THIS_MONTH: "Этот месяц",
    PRESET_LAST_MONTH: "Прошлый месяц",
    PRESET_CUSTOM: "Выбрать период",
}


def format_date(value: dt.date | None) -> str:
    return value.strftime("%d.%m.%Y") if value else ""


def format_range(start: dt.date | None, end: dt.date | None) -> str:
    return f"{format_date(start)} — {format_date(end)}"


def month_bounds(day: dt.date) -> tuple[dt.date, dt.date]:
    first = day.replace(day=1)
    next_first = (first + dt.timedelta(days=32)).replace(day=1)
    return first, next_first - dt.timedelta(days=1)


def _parse_date(value) -> dt.date | None:
    if not value:
        return None
    try:
        return dt.date.fromisoformat(str(value))
    except ValueError:
        return None


@dataclass
class ReportFilters:
    date_from: dt.date
    date_to: dt.date
    preset: str = PRESET_LAST_MONTH
    student: str = ""
    group: str = ""
    program: str = ""
    status: str = ""

    @property
    def range_label(self) -> str:
        return format_range(self.date_from, self.date_to)

    @property
    def is_default(self) -> bool:
        return not (self.student or self.group or self.program or self.status)

    def querystring(self) -> dict:
        """The GET parameters that reproduce this report (for the PDF link)."""
        params = {
            "preset": self.preset,
            "date_from": self.date_from.isoformat(),
            "date_to": self.date_to.isoformat(),
            "student": self.student,
            "group": self.group,
            "program": self.program,
            "status": self.status,
        }
        return {key: value for key, value in params.items() if value}


def parse_filters(params, today: dt.date) -> ReportFilters:
    """Build the filters from request.GET. Unknown / broken values fall back
    to the defaults instead of failing — this is a read-only page.

    `?period=<id>` (the «Отчёт» link in a period's menu) opens the report on
    exactly that period's dates."""
    preset = params.get("preset") or ""
    date_from = _parse_date(params.get("date_from"))
    date_to = _parse_date(params.get("date_to"))

    period_id = params.get("period")
    if period_id and str(period_id).isdigit() and not (date_from or date_to):
        period = ScholarshipPeriod.objects.filter(pk=int(period_id)).first()
        if period is not None:
            preset, date_from, date_to = PRESET_CUSTOM, period.period_start, period.period_end

    if preset == PRESET_THIS_MONTH:
        date_from, date_to = month_bounds(today)
    elif preset == PRESET_CUSTOM and (date_from or date_to):
        date_from = date_from or date_to
        date_to = date_to or date_from
        if date_to < date_from:
            date_from, date_to = date_to, date_from
    else:
        preset = PRESET_LAST_MONTH
        date_from, date_to = month_bounds(month_bounds(today)[0] - dt.timedelta(days=1))

    status = params.get("status") or ""
    return ReportFilters(
        date_from=date_from,
        date_to=date_to,
        preset=preset,
        student=(params.get("student") or "").strip()[:100],
        group=(params.get("group") or "").strip()[:150],
        program=(params.get("program") or "").strip()[:150],
        status=status if status in PaymentStatus.LABELS else "",
    )


@dataclass
class ReportRow:
    number: int
    evaluation_id: int
    student_id: int
    student_name: str
    group_name: str
    program: str
    amount: Decimal | None
    period: ScholarshipPeriod
    status: str
    hint: str = ""

    @property
    def status_label(self) -> str:
        return PaymentStatus.LABELS[self.status]

    @property
    def period_label(self) -> str:
        return format_range(self.period.period_start, self.period.period_end)


@dataclass
class ReportStats:
    total_students: int = 0
    received_students: int = 0
    pending_students: int = 0
    not_received_students: int = 0
    total_amount: Decimal | None = None
    received_amount: Decimal | None = None
    pending_amount: Decimal | None = None
    average_amount: Decimal | None = None
    awards_count: int = 0


@dataclass
class ScholarshipReport:
    filters: ReportFilters
    rows: list[ReportRow]
    stats: ReportStats
    periods: list[ScholarshipPeriod]
    group_options: list[str] = field(default_factory=list)
    program_options: list[str] = field(default_factory=list)


def _status_of(evaluation: ScholarshipEvaluation) -> tuple[str, str]:
    award = getattr(evaluation, "award", None)
    if award is not None:
        if award.status == ScholarshipAward.Status.APPROVED:
            return PaymentStatus.RECEIVED, ""
        return PaymentStatus.PENDING, "Период ещё не утверждён"
    if evaluation.eligibility_status == EligibilityStatus.ELIGIBLE:
        return PaymentStatus.NOT_RECEIVED, "Допущен, но не вошёл в список стипендиатов"
    return PaymentStatus.NOT_RECEIVED, evaluation.ineligibility_reason or evaluation.get_eligibility_status_display()


def _sum(values) -> Decimal | None:
    values = [value for value in values if value is not None]
    return sum(values, Decimal("0")) if values else None


def build_report(filters: ReportFilters) -> ScholarshipReport:
    periods = list(
        ScholarshipPeriod.objects.filter(period_end__gte=filters.date_from, period_end__lte=filters.date_to)
        .order_by("-period_start", "-award_day", "-pk")
    )
    base = ScholarshipEvaluation.objects.filter(period__in=periods)
    group_options = sorted({name for name in base.values_list("group_name", flat=True) if name})
    program_options = sorted({name for name in base.values_list("course_name", flat=True) if name})

    evaluations = base.select_related("period", "award")
    if filters.student:
        evaluations = evaluations.filter(student_name__icontains=filters.student)
    if filters.group:
        evaluations = evaluations.filter(group_name=filters.group)
    if filters.program:
        evaluations = evaluations.filter(course_name=filters.program)
    if filters.status == PaymentStatus.RECEIVED:
        evaluations = evaluations.filter(award__status=ScholarshipAward.Status.APPROVED)
    elif filters.status == PaymentStatus.PENDING:
        evaluations = evaluations.filter(award__status=ScholarshipAward.Status.PENDING)
    elif filters.status == PaymentStatus.NOT_RECEIVED:
        evaluations = evaluations.filter(Q(award__isnull=True))

    evaluations = evaluations.order_by(
        F("period__period_start").desc(), F("period__award_day").desc(nulls_last=True), "period_id",
        F("rank").asc(nulls_last=True), "student_name", "id",
    )

    rows: list[ReportRow] = []
    for evaluation in evaluations:
        status, hint = _status_of(evaluation)
        award = getattr(evaluation, "award", None)
        rows.append(ReportRow(
            number=0,
            evaluation_id=evaluation.pk,
            student_id=evaluation.student_id,
            student_name=evaluation.student_name,
            group_name=evaluation.group_name,
            program=evaluation.course_name,
            amount=award.amount if award is not None else None,
            period=evaluation.period,
            status=status,
            hint=hint,
        ))
    # Stable: keeps the period / rank order, groups statuses inside a period.
    period_order = {period.pk: index for index, period in enumerate(periods)}
    rows.sort(key=lambda row: (period_order.get(row.period.pk, 0), PaymentStatus.ORDER[row.status]))
    for number, row in enumerate(rows, start=1):
        row.number = number

    return ScholarshipReport(
        filters=filters,
        rows=rows,
        stats=_stats(rows),
        periods=periods,
        group_options=group_options,
        program_options=program_options,
    )


def _stats(rows: list[ReportRow]) -> ReportStats:
    """Students are counted once even if they appear in two periods of the
    range (twice-monthly mode); amounts add up every award. A sum is 0 when
    there are no awards, and «—» (None) only when the awards carry no money
    amount at all (ScholarshipConfiguration.award_amount left empty)."""
    received = {row.student_id for row in rows if row.status == PaymentStatus.RECEIVED}
    pending = {row.student_id for row in rows if row.status == PaymentStatus.PENDING}
    students = {row.student_id for row in rows}
    awarded_rows = [row for row in rows if row.status != PaymentStatus.NOT_RECEIVED]
    amounts = [row.amount for row in awarded_rows if row.amount is not None]
    total = _amount(awarded_rows)
    return ReportStats(
        total_students=len(students),
        received_students=len(received),
        pending_students=len(pending),
        not_received_students=len(students - received - pending),
        total_amount=total,
        received_amount=_amount([row for row in awarded_rows if row.status == PaymentStatus.RECEIVED]),
        pending_amount=_amount([row for row in awarded_rows if row.status == PaymentStatus.PENDING]),
        average_amount=(total / len(amounts)) if amounts else None,
        awards_count=len(awarded_rows),
    )


def _amount(rows: list[ReportRow]) -> Decimal | None:
    return _sum(row.amount for row in rows) if rows else Decimal("0")
