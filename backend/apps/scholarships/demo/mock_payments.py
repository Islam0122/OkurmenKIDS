"""MOCK data for the payments UI: «Стипендии», periods list, accounting
report (`python manage.py seed_scholarships`).

Unlike `seed_scholarship_demo` (a full LMS dataset that is then really
calculated), this writes the *outcome* directly: periods, evaluations and
awards in every payment state (fully paid, partly paid, nothing paid, no
recipients, not approved yet). Nothing is recalculated and the scholarship
business logic is not touched.

What counts as mock data — and so is all `--clear` ever deletes:

* periods: `title` starts with ``MOCK-SCH-2026`` (manual periods only);
* students: `phone` starts with ``+000-MOCKSCH-`` (+000 is not a real
  country code, so no real phone can match);
* groups / programs: `name` starts with ``MOCK-SCH-``.

Groups: the demo groups of the four programs (``SCH-DEMO-CS-01`` …, from
`seed_scholarship_demo`) are reused when they exist; any missing one is
created as ``MOCK-SCH-CS-01`` …. Real groups are never used: mock students
would show up in their rosters.

Mock students are created as «Деактивирован». A period only evaluates
active students (or students with attendance in the period), so the
students never enter a real period's calculation. Mock periods are
limited to the mock groups, so recalculating one never touches real
students either.
"""
from __future__ import annotations

import datetime as dt
import random
from dataclasses import dataclass, field
from decimal import Decimal

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.academy.models import Course, Group, Student
from apps.users.models import User

from ..models import (
    EligibilityStatus,
    PaymentMethod,
    PaymentStatus,
    ScholarshipAward,
    ScholarshipConfiguration,
    ScholarshipEvaluation,
    ScholarshipPeriod,
)
from . import namespace as demo_ns

TITLE_PREFIX = "MOCK-SCH-2026"
PHONE_PREFIX = "+000-MOCKSCH-"
GROUP_PREFIX = "MOCK-SCH-"
SEED = 2026

PROGRAMS = {
    "CS": "Cyber Security",
    "KIDS": "IT Kids",
    "PY": "Python Development",
    "WEB": "Web Development",
}
GROUPS = [("CS", 1), ("CS", 2), ("CS", 3), ("KIDS", 1), ("KIDS", 2), ("PY", 1), ("PY", 2), ("WEB", 1), ("WEB", 2)]

# (first name, last name) — 80 unique students.
NAMES = [
    ("Бермет", "Сылыкова"), ("Гулзат", "Касымова"), ("Нурлан", "Турдубаев"), ("Эмир", "Мамытов"),
    ("Тимур", "Сыдыков"), ("Айдана", "Абдрахманова"), ("Алина", "Исмаилова"), ("Мухаммад", "Алиев"),
    ("Азамат", "Жумабеков"), ("Айпери", "Токтогулова"), ("Бекзат", "Осмонов"), ("Нуриза", "Эсенова"),
    ("Санжар", "Бакиров"), ("Элина", "Кадырова"), ("Улан", "Шаршеев"), ("Жибек", "Орозбекова"),
    ("Данияр", "Молдокматов"), ("Асель", "Джумалиева"), ("Руслан", "Абдыкадыров"), ("Мээрим", "Султанова"),
    ("Адилет", "Кочкоров"), ("Камила", "Иманалиева"), ("Эрлан", "Табалдиев"), ("Сезим", "Асанова"),
    ("Айбек", "Мукашев"), ("Нургуль", "Жолдошева"), ("Бакыт", "Раимбеков"), ("Айзада", "Сатыбалдиева"),
    ("Кубаныч", "Эсенгулов"), ("Дильназ", "Урматова"), ("Максат", "Акматов"), ("Айгерим", "Бообекова"),
    ("Ислам", "Нурматов"), ("Толгонай", "Мамбетова"), ("Чынгыз", "Абылкасымов"), ("Акмарал", "Садыкова"),
    ("Бектур", "Ибраимов"), ("Нурай", "Молдоева"), ("Арсен", "Токтосунов"), ("Салтанат", "Керимова"),
    ("Ильяс", "Жээнбеков"), ("Айсулуу", "Бейшеналиева"), ("Талант", "Алымкулов"), ("Жамиля", "Орозова"),
    ("Нурсултан", "Касымалиев"), ("Аида", "Маматова"), ("Эрмек", "Сагынбаев"), ("Гулира", "Токтобаева"),
    ("Самат", "Дуйшеев"), ("Азиза", "Рахманова"), ("Мирлан", "Жолдошбеков"), ("Мадина", "Усенова"),
    ("Темирлан", "Шайлообеков"), ("Айжан", "Абдыкеримова"), ("Нурбек", "Карабеков"), ("Элнура", "Мырзакматова"),
    ("Акылбек", "Сооронбаев"), ("Самира", "Джапарова"), ("Алмаз", "Кулубаев"), ("Динара", "Байсалова"),
    ("Бекжан", "Асылбеков"), ("Карина", "Омурбекова"), ("Жоомарт", "Эркинбеков"), ("Фатима", "Алымбекова"),
    ("Эльдар", "Турсунов"), ("Майрам", "Бакытбекова"), ("Нуржигит", "Сейталиев"), ("Бегимай", "Кененсарова"),
    ("Амир", "Токторалиев"), ("Сабина", "Абдылдаева"), ("Аскар", "Мамасалиев"), ("Эльмира", "Жусупова"),
    ("Тилек", "Кожомбердиев"), ("Назира", "Исаева"), ("Канат", "Бекболотов"), ("Айнура", "Чолпонбаева"),
    ("Уланбек", "Нармаматов"), ("Зарина", "Эргешова"), ("Эрбол", "Абдиев"), ("Малика", "Садырбаева"),
]


MAIN_AMOUNT = Decimal("1500")


@dataclass(frozen=True)
class PeriodPlan:
    """One financial scenario. `amounts` lists (how many awards, amount each)
    in ranking order; `paid` of them are paid, spread evenly over the list
    (so a mixed-amount period has paid rows at every amount)."""

    start: dt.date
    end: dt.date
    label: str
    scenario: str
    limit: int
    amounts: tuple[tuple[int, Decimal], ...]
    paid: int
    approved: bool = True

    @property
    def awards(self) -> int:
        return sum(count for count, _ in self.amounts)

    def amount_at(self, index: int) -> Decimal:
        for count, amount in self.amounts:
            if index < count:
                return amount
            index -= count
        raise IndexError(index)

    def is_paid(self, index: int) -> bool:
        """Exactly `paid` of the `awards` rows, spread evenly."""
        if self.paid >= self.awards:
            return True
        return (index * self.paid) // self.awards != ((index + 1) * self.paid) // self.awards

    @property
    def expected(self) -> dict:
        """What the backend must compute for this period — used to verify it."""
        amounts = [self.amount_at(i) for i in range(self.awards)]
        paid = [a for i, a in enumerate(amounts) if self.approved and self.is_paid(i)]
        total = sum(amounts, Decimal("0"))
        return {
            "awards": self.awards, "total": total, "paid": len(paid), "paid_amount": sum(paid, Decimal("0")),
            "pending": self.awards - len(paid), "pending_amount": total - sum(paid, Decimal("0")),
        }


def _flat(count: int, amount: str = "1500") -> tuple[tuple[int, Decimal], ...]:
    return ((count, Decimal(amount)),)


PLANS = [
    PeriodPlan(dt.date(2026, 5, 1), dt.date(2026, 5, 31), "Май", "FULLY PAID", 20, _flat(20), 20),
    PeriodPlan(
        dt.date(2026, 6, 1), dt.date(2026, 6, 30), "Июнь", "DIFFERENT AMOUNTS", 20,
        ((5, Decimal("2500")), (5, Decimal("2000")), (5, Decimal("1500")), (5, Decimal("1000"))), 8,
    ),
    PeriodPlan(dt.date(2026, 7, 1), dt.date(2026, 7, 31), "Июль", "NOTHING PAID", 20, _flat(20), 0),
    PeriodPlan(dt.date(2026, 8, 1), dt.date(2026, 8, 31), "Август", "PARTIALLY PAID", 20, _flat(20), 7),
    PeriodPlan(dt.date(2026, 8, 15), dt.date(2026, 9, 15), "15.08–15.09", "NO SCHOLARSHIPS", 10, (), 0),
    PeriodPlan(dt.date(2026, 9, 1), dt.date(2026, 9, 30), "Сентябрь", "LARGE AMOUNT", 50, _flat(50, "3000"), 30),
    PeriodPlan(dt.date(2026, 10, 1), dt.date(2026, 10, 31), "Октябрь", "PARTIALLY PAID", 15, _flat(15), 9),
    # Not approved yet: «В процессе» / «Ждёт утверждения». An award can
    # only be paid once its period is approved (DB constraint), so every
    # award here is pending, with its amount.
    PeriodPlan(dt.date(2026, 11, 1), dt.date(2026, 11, 30), "Ноябрь", "NOT APPROVED", 20, _flat(20), 0, approved=False),
]

PAYMENT_DATES = [
    dt.date(2026, 9, d) for d in (1, 2, 3, 5, 10, 15, 26, 28)
]
EVALUATED_PER_PERIOD = 44

_INELIGIBLE = [
    (EligibilityStatus.BELOW_THRESHOLD, "Итоговый балл ниже порога."),
    (EligibilityStatus.INCOMPLETE_DATA, "Нет оценки тренера по одному из предметов."),
    (EligibilityStatus.NO_DATA, "Нет отмеченных занятий за период."),
]


def mock_student_q(prefix: str = "") -> Q:
    return Q(**{f"{prefix}phone__startswith": PHONE_PREFIX})


def mock_period_q() -> Q:
    return Q(title__startswith=TITLE_PREFIX, award_day__isnull=True)


@dataclass
class SeedResult:
    periods: list[ScholarshipPeriod] = field(default_factory=list)
    checks: list[PeriodCheck] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    groups: list[Group] = field(default_factory=list)
    students: int = 0
    payer: User | None = None


# ---------------------------------------------------------------------------
# Clearing
# ---------------------------------------------------------------------------

def clear_mock_data() -> dict[str, int]:
    """Delete only rows that carry the mock marker (see module docstring)."""
    students = Student.objects.filter(mock_student_q())
    foreign = ScholarshipAward.objects.filter(student__in=students).exclude(
        period__title__startswith=TITLE_PREFIX
    )
    if foreign.exists():
        raise ValueError(
            "Mock-студенты получили стипендию в не-mock периоде — удаление остановлено, чтобы не "
            "потерять данные этого периода. Уберите их из периода вручную."
        )
    periods = ScholarshipPeriod.objects.filter(mock_period_q())
    counts = {
        "Стипендиальные периоды": periods.count(),
        "Стипендии": ScholarshipAward.objects.filter(period__in=periods).count(),
        "Студенты": students.count(),
    }
    groups = Group.objects.filter(name__startswith=GROUP_PREFIX)
    courses = Course.objects.filter(name__startswith=GROUP_PREFIX)
    with transaction.atomic():
        periods.delete()
        students.delete()
        counts["Группы"] = groups.count()
        groups.delete()
        counts["Программы"] = courses.filter(groups__isnull=True).count()
        courses.filter(groups__isnull=True).delete()
    return counts


# ---------------------------------------------------------------------------
# Seeding
# ---------------------------------------------------------------------------

def find_payer() -> User | None:
    """The existing admin, never a new one: a real superuser first, then an
    ADMIN-role user. Never the demo seed's admin: a payer can't be deleted
    (ScholarshipAward.paid_by is PROTECT), which would block
    `seed_scholarship_demo --clear`."""
    real = User.objects.exclude(demo_ns.demo_user_q())
    return (
        real.filter(is_superuser=True, is_active=True).order_by("pk").first()
        or real.filter(role=User.Role.ADMIN, is_active=True).order_by("pk").first()
    )


def _groups() -> list[Group]:
    groups = []
    for code, number in GROUPS:
        demo = Group.objects.filter(name=f"{demo_ns.PREFIX}{code}-{number:02d}").first()
        if demo is not None:
            groups.append(demo)
            continue
        course, _ = Course.objects.get_or_create(
            name=f"{GROUP_PREFIX}{PROGRAMS[code]}",
            defaults={"count_lesson": 48, "description": "Mock-программа для проверки выплат стипендий."},
        )
        group, _ = Group.objects.get_or_create(
            name=f"{GROUP_PREFIX}{code}-{number:02d}",
            defaults={"course": course, "start_date": dt.date(2026, 1, 12)},
        )
        groups.append(group)
    return groups


def _students(groups: list[Group]) -> list[Student]:
    students = []
    for index, (first, last) in enumerate(NAMES, start=1):
        student, _ = Student.objects.update_or_create(
            phone=f"{PHONE_PREFIX}{index:03d}",
            defaults={
                "first_name": first,
                "last_name": last,
                "group": groups[(index - 1) % len(groups)],
                "enrollment_date": dt.date(2026, 1, 12),
                # Not a candidate of any real period (see module docstring).
                "status": Student.Status.WITHDRAWN,
                "is_active": False,
            },
        )
        students.append(student)
    return students


def _snapshot(config: ScholarshipConfiguration | None) -> dict:
    if config is None:
        return dict(
            configuration=None, attendance_weight=Decimal("0.40"), homework_weight=Decimal("0.30"),
            feedback_weight=Decimal("0.30"), subject_aggregation="equal", late_homework_credit=Decimal("0.50"),
            min_overall_score=Decimal("0"), min_marked_lessons=1, require_complete_feedback=True,
        )
    return dict(
        configuration=config, attendance_weight=config.attendance_weight, homework_weight=config.homework_weight,
        feedback_weight=config.feedback_weight, subject_aggregation=config.subject_aggregation,
        late_homework_credit=config.late_homework_credit, min_overall_score=config.min_overall_score,
        min_marked_lessons=config.min_marked_lessons, require_complete_feedback=config.require_complete_feedback,
    )


def _paid_at(plan: PeriodPlan, index: int) -> dt.datetime:
    """Different dates, after the period when the list allows it."""
    after = [d for d in PAYMENT_DATES if d > plan.end] or PAYMENT_DATES[-2:]
    day = after[index % len(after)]
    return timezone.make_aware(dt.datetime.combine(day, dt.time(10, 0)) + dt.timedelta(minutes=17 * index))


def _method(index: int) -> str:
    # ~70 % cash, ~30 % bank transfer.
    return PaymentMethod.BANK if index % 10 in (2, 5, 8) else PaymentMethod.CASH


def _comment(method: str, index: int) -> str:
    if method == PaymentMethod.BANK:
        return "Перевод на карту родителя"
    return "Выдано в кассе, подпись родителя" if index % 4 == 0 else ""


def _score(rng: random.Random, low: float, high: float) -> Decimal:
    return Decimal(str(round(rng.uniform(low, high), 2)))


def _period(plan: PeriodPlan, number: int, groups, students, config, payer, rng, now) -> ScholarshipPeriod:
    period, _ = ScholarshipPeriod.objects.update_or_create(
        award_day=None, period_start=plan.start, period_end=plan.end,
        defaults={
            **_snapshot(config),
            "title": f"{TITLE_PREFIX} · {plan.label}",
            "evaluation_date": plan.end + dt.timedelta(days=1),
            "max_recipients": plan.limit,
            "award_amount": MAIN_AMOUNT,
            "status": ScholarshipPeriod.Status.APPROVED if plan.approved else ScholarshipPeriod.Status.DRAFT,
            "last_calculated_at": now,
            "generated_by": payer,
            "approved_by": payer if plan.approved else None,
            "approved_at": now if plan.approved else None,
        },
    )
    period.groups.set(groups)
    # Idempotent: the period keeps its pk, its rows are rebuilt.
    period.awards.all().delete()
    period.evaluations.all().delete()

    evaluated = rng.sample(students, min(len(students), max(EVALUATED_PER_PERIOD, plan.awards + 14)))
    eligible_count = 0 if plan.awards == 0 else plan.awards + rng.randint(6, 12)
    scores = sorted((_score(rng, 72, 98) for _ in range(eligible_count)), reverse=True)

    evaluations = []
    for index, student in enumerate(evaluated):
        group = student.group
        common = dict(
            period=period, student=student, student_name=str(student), group=group,
            group_name=group.name if group else "", course_name=group.course.name if group else "",
            enrollment_date=student.enrollment_date, subjects_count=2,
        )
        if index < eligible_count:
            overall = scores[index]
            evaluations.append(ScholarshipEvaluation(
                **common, rank=index + 1, eligibility_status=EligibilityStatus.ELIGIBLE, overall_score=overall,
                attendance_score=min(Decimal("100"), overall + _score(rng, 0, 6)),
                homework_score=max(Decimal("0"), overall - _score(rng, 0, 8)),
                feedback_score=overall, lessons_count=rng.randint(12, 16),
            ))
        else:
            status, reason = _INELIGIBLE[index % len(_INELIGIBLE)]
            has_scores = status != EligibilityStatus.NO_DATA
            evaluations.append(ScholarshipEvaluation(
                **common, rank=None, eligibility_status=status, ineligibility_reason=reason,
                overall_score=_score(rng, 35, 68) if has_scores else None,
                lessons_count=rng.randint(4, 12) if has_scores else 0,
            ))
    evaluations = ScholarshipEvaluation.objects.bulk_create(evaluations)

    award_status = ScholarshipAward.Status.APPROVED if plan.approved else ScholarshipAward.Status.PENDING
    awards = []
    for evaluation in evaluations:
        if evaluation.rank is None or evaluation.rank > plan.awards:
            continue
        index = evaluation.rank - 1
        amount = plan.amount_at(index)
        award = ScholarshipAward(
            period=period, student_id=evaluation.student_id, evaluation=evaluation, rank=evaluation.rank,
            award_date=period.evaluation_date, amount=amount, status=award_status,
            approved_by=payer if plan.approved else None, approved_at=now if plan.approved else None,
        )
        # Payments are spread over the ranking, not just the top ones.
        if plan.approved and plan.is_paid(index):
            method = _method(index + number)
            award.payment_status = PaymentStatus.PAID
            award.paid_at = _paid_at(plan, index)
            award.paid_by = payer
            award.paid_by_name = str(payer)[:150]
            award.paid_amount = amount
            award.payment_method = method
            award.payment_comment = _comment(method, index)
        awards.append(award)
    ScholarshipAward.objects.bulk_create(awards)
    return period


def seed_mock_data(*, stdout=None) -> SeedResult:
    rng = random.Random(SEED)
    now = timezone.now()
    result = SeedResult(payer=find_payer())
    if result.payer is None:
        raise NoPayer(
            "Нет администратора: у каждой выплаты должно быть «кто выдал». "
            "Создайте superuser (python manage.py createsuperuser) и запустите команду снова."
        )
    config = ScholarshipConfiguration.objects.active()
    with transaction.atomic():
        result.groups = _groups()
        students = _students(result.groups)
        result.students = len(students)
        for number, plan in enumerate(PLANS):
            clash = ScholarshipPeriod.objects.filter(
                award_day__isnull=True, period_start=plan.start, period_end=plan.end,
            ).exclude(title__startswith=TITLE_PREFIX)
            if clash.exists():
                result.skipped.append(
                    f"{plan.start:%d.%m.%Y} — {plan.end:%d.%m.%Y}: уже есть реальный период с этими датами — не трогаем."
                )
                continue
            period = _period(plan, number, result.groups, students, config, result.payer, rng, now)
            result.periods.append(period)
            result.checks.append(PeriodCheck(period=period, plan=plan, figures={}))
    return result


class NoPayer(Exception):
    """No admin in the database to record as the payer."""


class FinanceMismatch(Exception):
    """The backend computed a different number than the seeded data holds."""


@dataclass
class PeriodCheck:
    period: ScholarshipPeriod
    plan: PeriodPlan
    figures: dict  # awards, total, paid, paid_amount, pending, pending_amount, balance


def _figures_from_rows(awards) -> dict:
    """Independent recount, row by row — no ORM aggregates, no services."""
    total = paid_amount = pending_amount = Decimal("0")
    paid = pending = 0
    for award in awards:
        if award.amount is None:
            raise FinanceMismatch(f"Стипендия #{award.pk} без суммы.")
        total += award.amount
        if award.payment_status == PaymentStatus.PAID:
            if award.paid_at is None or award.paid_amount != award.amount or not award.payment_method:
                raise FinanceMismatch(f"Выплата #{award.pk}: нет даты, суммы или способа.")
            paid += 1
            paid_amount += award.paid_amount
        else:
            if award.paid_at or award.paid_by_id or award.paid_amount is not None or award.payment_method:
                raise FinanceMismatch(f"Невыплаченная стипендия #{award.pk} содержит данные выплаты.")
            pending += 1
            pending_amount += award.amount
    return {
        "awards": paid + pending, "total": total, "paid": paid, "paid_amount": paid_amount,
        "pending": pending, "pending_amount": pending_amount, "balance": total - paid_amount,
    }


def _compare(where: str, name: str, expected, actual) -> None:
    if (actual or 0) != (expected or 0):
        raise FinanceMismatch(f"{where}: {name} = {actual}, ожидалось {expected}.")


def verify_finances(checks: list[PeriodCheck]) -> dict:
    """Check that every place the backend computes money agrees with the
    seeded rows and with the plan:

    * the «Стипендии» KPIs (analytics.payment_summary) — per period and overall;
    * the accounting report / Excel / PDF (report.build_report rows_totals);
    * the plan's own arithmetic (e.g. 7 × 1 500 = 10 500).

    Raises FinanceMismatch on the first difference; returns the overall figures."""
    from ..services.analytics import payment_summary
    from ..services.report import ReportFilters, build_report

    for check in checks:
        where = f"{check.period.period_start:%d.%m}–{check.period.period_end:%d.%m}"
        rows = _figures_from_rows(check.period.awards.all())
        for key, value in check.plan.expected.items():
            _compare(where, key, value, rows[key])
        _compare(where, "balance", rows["total"] - rows["paid_amount"], rows["pending_amount"])

        summary = payment_summary(check.period.awards.all())
        for key, backend in (("awards", "total"), ("paid", "paid"), ("pending", "unpaid"), ("total", "accrued"),
                             ("paid_amount", "paid_sum"), ("pending_amount", "remaining")):
            _compare(f"{where} [Стипендии]", backend, rows[key], summary[backend])

        report = build_report(check.period, ReportFilters()).rows_totals
        for key, backend in (("awards", "awards"), ("paid", "paid"), ("pending", "unpaid"), ("total", "amount"),
                             ("paid_amount", "paid_amount"), ("pending_amount", "remaining")):
            _compare(f"{where} [Отчёт]", backend, rows[key], getattr(report, backend))
        check.figures = rows

    awards = ScholarshipAward.objects.filter(period__in=[c.period for c in checks])
    overall = _figures_from_rows(awards)
    summary = payment_summary(awards)
    for key, backend in (("awards", "total"), ("paid", "paid"), ("pending", "unpaid"), ("total", "accrued"),
                         ("paid_amount", "paid_sum"), ("pending_amount", "remaining")):
        _compare("Итого [Стипендии]", backend, overall[key], summary[backend])
    overall["cash"] = awards.filter(payment_method=PaymentMethod.CASH).count()
    overall["bank"] = awards.filter(payment_method=PaymentMethod.BANK).count()
    return overall
