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

Payment status of a student in the period:

* «Получил»    — the award is approved (the period is approved);
* «Ожидает»    — the award exists but the period is not approved yet;
* «Не получил» — evaluated in the period, but no award.
"""
from __future__ import annotations

import datetime as dt
from collections import defaultdict
from dataclasses import dataclass, field
from decimal import Decimal

from django.db.models import F

from ..models import EligibilityStatus, ScholarshipAward, ScholarshipEvaluation, ScholarshipPeriod
from .analytics import annotate_periods


class PaymentStatus:
    RECEIVED = "received"
    PENDING = "pending"
    NOT_RECEIVED = "not_received"

    LABELS = {
        RECEIVED: "Получил",
        PENDING: "Ожидает",
        NOT_RECEIVED: "Не получил",
    }
    # Table order: paid first, then waiting, then the rest.
    ORDER = {RECEIVED: 0, PENDING: 1, NOT_RECEIVED: 2}


STATUS_CHOICES = [("", "Все статусы"), *PaymentStatus.LABELS.items()]

NO_GROUP = "Без группы"


def format_date(value: dt.date | None) -> str:
    return value.strftime("%d.%m.%Y") if value else ""


def format_range(start: dt.date | None, end: dt.date | None) -> str:
    return f"{format_date(start)} — {format_date(end)}"


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

    @property
    def is_active(self) -> bool:
        return bool(self.student or self.group or self.program or self.status)

    @property
    def status_label(self) -> str:
        return PaymentStatus.LABELS.get(self.status, "")

    def querystring(self, period: ScholarshipPeriod | None) -> dict:
        params = {
            "period": period.pk if period else "",
            "student": self.student,
            "group": self.group,
            "program": self.program,
            "status": self.status,
        }
        return {key: value for key, value in params.items() if value}


def parse_filters(params) -> ReportFilters:
    status = params.get("status") or ""
    return ReportFilters(
        student=(params.get("student") or "").strip()[:100],
        group=(params.get("group") or "").strip()[:150],
        program=(params.get("program") or "").strip()[:150],
        status=status if status in PaymentStatus.LABELS else "",
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

    @property
    def status_label(self) -> str:
        return PaymentStatus.LABELS[self.status]


@dataclass
class Totals:
    """Counts and money for a set of rows (a group, the whole period, the
    filtered student table)."""

    students: int = 0
    received: int = 0
    pending: int = 0
    not_received: int = 0
    amount: Decimal | None = Decimal("0")
    average: Decimal | None = None
    awards: int = 0

    @property
    def awarded(self) -> int:
        return self.received + self.pending


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
    totals: Totals  # whole period
    rows: list[ReportRow]  # filtered student table
    rows_totals: Totals
    all_rows_count: int = 0
    group_names: list[str] = field(default_factory=list)
    scope_all: bool = True

    @property
    def range_label(self) -> str:
        return format_range(self.period.period_start, self.period.period_end)

    @property
    def has_pending(self) -> bool:
        return self.totals.pending > 0


def _status_of(evaluation: ScholarshipEvaluation) -> tuple[str, str]:
    award = getattr(evaluation, "award", None)
    if award is not None:
        if award.status == ScholarshipAward.Status.APPROVED:
            return PaymentStatus.RECEIVED, ""
        return PaymentStatus.PENDING, "Период ещё не утверждён"
    if evaluation.eligibility_status == EligibilityStatus.ELIGIBLE:
        return PaymentStatus.NOT_RECEIVED, "Допущен, но не вошёл в список стипендиатов"
    return PaymentStatus.NOT_RECEIVED, evaluation.ineligibility_reason or evaluation.get_eligibility_status_display()


def totals_of(rows: list[ReportRow]) -> Totals:
    """A sum is 0 when there are no awards, and None («—») only when the
    awards carry no money amount (ScholarshipConfiguration.award_amount
    left empty)."""
    awarded = [row for row in rows if row.status != PaymentStatus.NOT_RECEIVED]
    amounts = [row.amount for row in awarded if row.amount is not None]
    if not awarded:
        amount = Decimal("0")
    elif amounts:
        amount = sum(amounts, Decimal("0"))
    else:
        amount = None
    return Totals(
        students=len({row.student_id for row in rows}),
        received=sum(1 for row in rows if row.status == PaymentStatus.RECEIVED),
        pending=sum(1 for row in rows if row.status == PaymentStatus.PENDING),
        not_received=sum(1 for row in rows if row.status == PaymentStatus.NOT_RECEIVED),
        amount=amount,
        average=(amount / len(amounts)) if amounts else None,
        awards=len(awarded),
    )


def _matches(row: ReportRow, filters: ReportFilters) -> bool:
    if filters.student and filters.student.casefold() not in row.student_name.casefold():
        return False
    if filters.group and (row.group_name or NO_GROUP) != filters.group:
        return False
    if filters.program and row.program != filters.program:
        return False
    if filters.status and row.status != filters.status:
        return False
    return True


def build_report(period: ScholarshipPeriod, filters: ReportFilters) -> ScholarshipReport:
    evaluations = (
        ScholarshipEvaluation.objects.filter(period=period)
        .select_related("award")
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
        ))

    by_group: dict[str, list[ReportRow]] = defaultdict(list)
    for row in all_rows:
        by_group[row.group_name or NO_GROUP].append(row)
    selected = {group.name: group for group in period.groups.select_related("course")}
    groups = [
        GroupSummary(
            name=name,
            programs=sorted({row.program for row in by_group.get(name, []) if row.program})
            or ([selected[name].course.name] if name in selected and selected[name].course_id else []),
            totals=totals_of(by_group.get(name, [])),
        )
        for name in period_group_names(period, set(by_group))
    ]

    rows = [row for row in all_rows if _matches(row, filters)]
    # Stable sort keeps the ranking order inside each status.
    rows.sort(key=lambda row: PaymentStatus.ORDER[row.status])
    for number, row in enumerate(rows, start=1):
        row.number = number

    return ScholarshipReport(
        period=period,
        filters=filters,
        groups=groups,
        programs=sorted({program for group in groups for program in group.programs}),
        totals=totals_of(all_rows),
        rows=rows,
        rows_totals=totals_of(rows),
        all_rows_count=len(all_rows),
        group_names=[group.name for group in groups],
        scope_all=not selected,
    )
