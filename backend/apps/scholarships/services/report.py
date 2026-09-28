"""«Отчёты по стипендиям» — one scholarship period at a time: which groups
took part, how each group did, who got how much.

Read-only, built from what the period's calculation stored — nothing is
recalculated, so the admin page, the PDF and the period dashboard can
never disagree.

Period → groups
---------------
`ScholarshipPeriod.groups` (M2M to academy.Group) is the list of groups a
period is for; services.scoring.candidate_students evaluates only students
of those groups. An empty list means the whole academy — automatic cycles
and every period created before the field existed.

What a period's calculation actually covered is stored per student in
`ScholarshipEvaluation` (group FK + `group_name` / `course_name` snapshot),
so the report follows exactly the chain the calculation wrote:

    ScholarshipPeriod.groups → ScholarshipEvaluation (group, program)
                             → student → ScholarshipAward (amount, status)

Every number (groups, students, recipients, amount) is computed from *that
period's* rows only — nothing is global. A group selected for the period
with no evaluated students is still listed, with zeros.

Payment status of a row (the money, not the approval):

* «Выдано»        — the award is paid (services.payments);
* «Не выдано»     — the award exists but nobody handed the money over yet
                    (`awaiting_approval` when the period is still a draft —
                    it cannot be paid before approval);
* «Без стипендии» — evaluated in the period, but no award. These rows are
                    shown only when asked for: the report is about money.
"""
from __future__ import annotations

import datetime as dt
from collections import defaultdict
from dataclasses import dataclass, field
from decimal import Decimal

from django.db.models import F

from ..models import EligibilityStatus, PaymentMethod, ScholarshipAward, ScholarshipEvaluation, ScholarshipPeriod
from .analytics import annotate_periods


class PaymentStatus:
    PAID = "paid"
    UNPAID = "unpaid"
    NOT_AWARDED = "not_awarded"

    LABELS = {
        PAID: "Выдано",
        UNPAID: "Не выдано",
        NOT_AWARDED: "Без стипендии",
    }
    # Table order: paid first, then waiting, then the rest.
    ORDER = {PAID: 0, UNPAID: 1, NOT_AWARDED: 2}
    AWARDED = (PAID, UNPAID)


STATUS_CHOICES = [("", "Все статусы"), *PaymentStatus.LABELS.items()]
METHOD_CHOICES = [("", "Все способы"), *PaymentMethod.choices]

NO_GROUP = "Без группы"


def format_date(value: dt.date | None) -> str:
    return value.strftime("%d.%m.%Y") if value else ""


def format_range(start: dt.date | None, end: dt.date | None) -> str:
    return f"{format_date(start)} — {format_date(end)}"


def short_range(start: dt.date, end: dt.date) -> str:
    """«01.08–31.08» — the year only when the period crosses into another."""
    if start.year != end.year:
        return f"{start:%d.%m.%y}–{end:%d.%m.%y}"
    return f"{start:%d.%m}–{end:%d.%m}"


# ---------------------------------------------------------------------------
# Period choice
# ---------------------------------------------------------------------------

@dataclass
class PeriodOption:
    """One period in the picker, with the groups that took part in it."""

    period: ScholarshipPeriod
    groups: list[str]
    students: int
    recipients: int
    scope_all: bool  # no groups selected → the whole academy

    @property
    def pk(self) -> int:
        return self.period.pk

    @property
    def range_label(self) -> str:
        return format_range(self.period.period_start, self.period.period_end)


def period_options() -> list[PeriodOption]:
    """Every period, newest first, each with its participating groups — two
    queries whatever the number of periods."""
    periods = list(annotate_periods(ScholarshipPeriod.objects.prefetch_related("groups")))
    groups = participating_groups(periods)
    return [
        PeriodOption(
            period=period,
            groups=groups[period.pk],
            students=period.evaluations_count or 0,
            recipients=period.recipients_count or 0,
            scope_all=not period.group_ids,
        )
        for period in periods
    ]


def participating_groups(periods) -> dict[int, list[str]]:
    """{period pk: its participating group names} for a batch of periods
    (the period cards, the report picker) — one query for the evaluated
    groups; prefetch `groups` on the periods to avoid one more per period."""
    periods = list(periods)
    evaluated: dict[int, set[str]] = defaultdict(set)
    for period_id, name in (
        ScholarshipEvaluation.objects.filter(period__in=[p.pk for p in periods])
        .order_by().values_list("period_id", "group_name").distinct()
    ):
        evaluated[period_id].add(name or NO_GROUP)
    return {period.pk: period_group_names(period, evaluated.get(period.pk, set())) for period in periods}


def period_group_names(period: ScholarshipPeriod, evaluated: set[str]) -> list[str]:
    """The period's participating groups: the selected ones plus any group
    its stored evaluations were taken in (a student's group snapshot); for
    a whole-academy period — just the evaluated groups."""
    selected = {group.name for group in period.groups.all()}
    return sorted(selected | set(evaluated), key=lambda name: (name == NO_GROUP, name))


def default_option(options: list[PeriodOption]) -> PeriodOption | None:
    """The newest period that already has numbers; a running one is empty."""
    return next((o for o in options if o.period.is_calculated), options[0] if options else None)


# ---------------------------------------------------------------------------
# Filters (student table only — the period and group blocks are never
# filtered, they describe the whole period)
# ---------------------------------------------------------------------------

@dataclass
class ReportFilters:
    student: str = ""
    group: str = ""
    program: str = ""
    status: str = ""
    method: str = ""

    @property
    def is_active(self) -> bool:
        return bool(self.student or self.group or self.program or self.status or self.method)

    @property
    def status_label(self) -> str:
        return PaymentStatus.LABELS.get(self.status, "")

    @property
    def method_label(self) -> str:
        return PaymentMethod(self.method).label if self.method else ""

    def querystring(self, period: ScholarshipPeriod | None) -> dict:
        params = {
            "period": period.pk if period else "",
            "student": self.student,
            "group": self.group,
            "program": self.program,
            "status": self.status,
            "method": self.method,
        }
        return {key: value for key, value in params.items() if value}


def parse_filters(params) -> ReportFilters:
    status = params.get("status") or ""
    method = params.get("method") or ""
    return ReportFilters(
        student=(params.get("student") or "").strip()[:100],
        group=(params.get("group") or "").strip()[:150],
        program=(params.get("program") or "").strip()[:150],
        status=status if status in PaymentStatus.LABELS else "",
        method=method if method in PaymentMethod.values else "",
    )


def pick_period(options: list[PeriodOption], period_id) -> PeriodOption | None:
    if period_id and str(period_id).isdigit():
        chosen = next((o for o in options if o.pk == int(period_id)), None)
        if chosen is not None:
            return chosen
    return default_option(options)


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

@dataclass
class ReportRow:
    number: int
    evaluation_id: int
    student_id: int
    student_name: str
    group_name: str
    program: str
    amount: Decimal | None
    status: str
    hint: str = ""
    award_id: int | None = None
    awaiting_approval: bool = False
    paid_at: dt.datetime | None = None
    paid_amount: Decimal | None = None
    payment_method: str = ""
    paid_by: str = ""
    comment: str = ""

    @property
    def status_label(self) -> str:
        return PaymentStatus.LABELS[self.status]

    @property
    def method_label(self) -> str:
        return PaymentMethod(self.payment_method).label if self.payment_method else ""

    @property
    def is_awarded(self) -> bool:
        return self.status in PaymentStatus.AWARDED


def _sum(values) -> Decimal | None:
    """0 when there is nothing to add up, None («—») when every value is
    missing (the award has no money amount — award_amount left empty)."""
    values = list(values)
    present = [v for v in values if v is not None]
    if not values:
        return Decimal("0")
    return sum(present, Decimal("0")) if present else None


@dataclass
class Totals:
    """Counts and money for a set of rows (a group, the whole period, the
    filtered table). `amount` is what was accrued (начислено), `paid_amount`
    what was handed over, `remaining` what is still to hand over."""

    students: int = 0
    awards: int = 0
    paid: int = 0
    unpaid: int = 0
    awaiting_approval: int = 0
    not_awarded: int = 0
    amount: Decimal | None = Decimal("0")
    paid_amount: Decimal | None = Decimal("0")
    remaining: Decimal | None = Decimal("0")
    average: Decimal | None = None


@dataclass
class GroupSummary:
    name: str
    programs: list[str]
    totals: Totals

    @property
    def program_label(self) -> str:
        return ", ".join(self.programs) or "—"


@dataclass
class ScholarshipReport:
    period: ScholarshipPeriod
    filters: ReportFilters
    groups: list[GroupSummary]
    programs: list[str]
    totals: Totals  # every award of the period, no filters
    rows: list[ReportRow]  # filtered table
    rows_totals: Totals  # what the filters select — the KPIs, exports, PDF
    all_rows_count: int = 0
    group_names: list[str] = field(default_factory=list)
    scope_all: bool = True

    @property
    def range_label(self) -> str:
        return format_range(self.period.period_start, self.period.period_end)

    @property
    def short_range(self) -> str:
        return short_range(self.period.period_start, self.period.period_end)

    @property
    def has_pending(self) -> bool:
        return self.totals.awaiting_approval > 0


def _status_of(evaluation: ScholarshipEvaluation) -> tuple[str, str]:
    award = getattr(evaluation, "award", None)
    if award is not None:
        if award.is_paid:
            return PaymentStatus.PAID, ""
        if award.status != ScholarshipAward.Status.APPROVED:
            return PaymentStatus.UNPAID, "Период ещё не утверждён — выдать нельзя"
        return PaymentStatus.UNPAID, ""
    if evaluation.eligibility_status == EligibilityStatus.ELIGIBLE:
        return PaymentStatus.NOT_AWARDED, "Допущен, но не вошёл в список стипендиатов"
    return PaymentStatus.NOT_AWARDED, evaluation.ineligibility_reason or evaluation.get_eligibility_status_display()


def totals_of(rows: list[ReportRow]) -> Totals:
    awarded = [row for row in rows if row.is_awarded]
    paid = [row for row in awarded if row.status == PaymentStatus.PAID]
    unpaid = [row for row in awarded if row.status == PaymentStatus.UNPAID]
    amount = _sum(row.amount for row in awarded)
    amounts = [row.amount for row in awarded if row.amount is not None]
    return Totals(
        students=len({row.student_id for row in awarded}),
        awards=len(awarded),
        paid=len(paid),
        unpaid=len(unpaid),
        awaiting_approval=sum(1 for row in unpaid if row.awaiting_approval),
        not_awarded=sum(1 for row in rows if not row.is_awarded),
        amount=amount,
        paid_amount=_sum(row.paid_amount for row in paid),
        remaining=_sum(row.amount for row in unpaid),
        average=(sum(amounts, Decimal("0")) / len(amounts)) if amounts else None,
    )


def _matches(row: ReportRow, filters: ReportFilters) -> bool:
    if filters.student and filters.student.casefold() not in row.student_name.casefold():
        return False
    if filters.group and (row.group_name or NO_GROUP) != filters.group:
        return False
    if filters.program and row.program != filters.program:
        return False
    if filters.status:
        if row.status != filters.status:
            return False
    elif not row.is_awarded:
        # «Все начисления» — the report is about money; students without a
        # scholarship are one status choice away.
        return False
    if filters.method and row.payment_method != filters.method:
        return False
    return True


def build_report(period: ScholarshipPeriod, filters: ReportFilters) -> ScholarshipReport:
    evaluations = (
        ScholarshipEvaluation.objects.filter(period=period)
        .select_related("award", "award__paid_by")
        .order_by(F("rank").asc(nulls_last=True), "student_name", "id")
    )
    all_rows: list[ReportRow] = []
    for evaluation in evaluations:
        status, hint = _status_of(evaluation)
        award = getattr(evaluation, "award", None)
        all_rows.append(ReportRow(
            number=0,
            evaluation_id=evaluation.pk,
            student_id=evaluation.student_id,
            student_name=evaluation.student_name,
            group_name=evaluation.group_name,
            program=evaluation.course_name,
            amount=award.amount if award is not None else None,
            status=status,
            hint=hint,
            award_id=award.pk if award is not None else None,
            awaiting_approval=award is not None and award.status != ScholarshipAward.Status.APPROVED,
            paid_at=award.paid_at if award is not None else None,
            paid_amount=award.paid_amount if award is not None else None,
            payment_method=award.payment_method if award is not None else "",
            paid_by=str(award.paid_by) if award is not None and award.paid_by_id else "",
            comment=award.payment_comment if award is not None else "",
        ))

    rows = [row for row in all_rows if _matches(row, filters)]
    # Stable sort keeps the ranking order inside each status.
    rows.sort(key=lambda row: PaymentStatus.ORDER[row.status])
    for number, row in enumerate(rows, start=1):
        row.number = number

    # Group subtotals follow the table: all of the period's groups without
    # filters, only the groups that still have rows with them.
    by_group: dict[str, list[ReportRow]] = defaultdict(list)
    for row in rows:
        by_group[row.group_name or NO_GROUP].append(row)
    evaluated_groups = {row.group_name or NO_GROUP for row in all_rows}
    selected = {group.name: group for group in period.groups.select_related("course")}
    groups = [
        GroupSummary(
            name=name,
            programs=sorted({row.program for row in by_group.get(name, []) if row.program})
            or ([selected[name].course.name] if name in selected and selected[name].course_id else []),
            totals=totals_of(by_group.get(name, [])),
        )
        for name in period_group_names(period, evaluated_groups)
        if not filters.is_active or name in by_group
    ]
    all_groups = period_group_names(period, evaluated_groups)
    programs = sorted({row.program for row in all_rows if row.program} | {
        g.course.name for g in selected.values() if g.course_id
    })

    return ScholarshipReport(
        period=period,
        filters=filters,
        groups=groups,
        programs=programs,
        totals=totals_of(all_rows),
        rows=rows,
        rows_totals=totals_of(rows),
        all_rows_count=sum(1 for row in all_rows if row.is_awarded),
        group_names=all_groups,
        scope_all=not selected,
    )
