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
from django.db.models import Count, Q, Sum
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


@dataclass(frozen=True)
class PeriodPlan:
    start: dt.date
    end: dt.date
    label: str
    limit: int
    awards: int
    paid: int
    approved: bool = True
    flat_amount: bool = False  # every award exactly 1 500 сом


PLANS = [
    PeriodPlan(dt.date(2026, 5, 1), dt.date(2026, 5, 31), "Май", 20, 20, 20),
    PeriodPlan(dt.date(2026, 6, 1), dt.date(2026, 6, 30), "Июнь", 20, 20, 20),
    PeriodPlan(dt.date(2026, 7, 1), dt.date(2026, 7, 31), "Июль", 20, 20, 0),
    PeriodPlan(dt.date(2026, 8, 1), dt.date(2026, 8, 31), "Август", 20, 20, 7, flat_amount=True),
    PeriodPlan(dt.date(2026, 8, 15), dt.date(2026, 9, 15), "15.08–15.09", 10, 0, 0),
    PeriodPlan(dt.date(2026, 9, 1), dt.date(2026, 9, 30), "Сентябрь", 20, 20, 12),
    PeriodPlan(dt.date(2026, 10, 1), dt.date(2026, 10, 31), "Октябрь", 15, 15, 9),
    # Not approved yet: shows «В процессе» / «Ждёт утверждения». An award
    # can only be paid once its period is approved (DB constraint), so this
    # one has no payments.
    PeriodPlan(dt.date(2026, 11, 1), dt.date(2026, 11, 30), "Ноябрь", 20, 20, 0, approved=False),
]

PAYMENT_DATES = [
    dt.date(2026, 9, d) for d in (1, 2, 3, 5, 10, 15, 26, 28)
]
MAIN_AMOUNT = Decimal("1500")
TOP_AMOUNTS = [Decimal("3000"), Decimal("2500"), Decimal("2000")]
LOW_AMOUNT = Decimal("1000")
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
    ADMIN-role user, then the demo seed's admin."""
    real = User.objects.exclude(demo_ns.demo_user_q())
    return (
        real.filter(is_superuser=True, is_active=True).order_by("pk").first()
        or real.filter(role=User.Role.ADMIN, is_active=True).order_by("pk").first()
        or User.objects.filter(is_superuser=True).order_by("pk").first()
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


def _amount(plan: PeriodPlan, rank: int) -> Decimal:
    if plan.flat_amount:
        return MAIN_AMOUNT
    if rank <= len(TOP_AMOUNTS):
        return TOP_AMOUNTS[rank - 1]
    if rank > plan.awards - 2:
        return LOW_AMOUNT
    return MAIN_AMOUNT


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

    evaluated = rng.sample(students, EVALUATED_PER_PERIOD)
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
        amount = _amount(plan, evaluation.rank)
        award = ScholarshipAward(
            period=period, student_id=evaluation.student_id, evaluation=evaluation, rank=evaluation.rank,
            award_date=period.evaluation_date, amount=amount, status=award_status,
            approved_by=payer if plan.approved else None, approved_at=now if plan.approved else None,
        )
        # Payments are spread over the ranking, not just the top ones.
        if plan.approved and _is_paid(index, plan):
            method = _method(index + number)
            award.payment_status = PaymentStatus.PAID
            award.paid_at = _paid_at(plan, index)
            award.paid_by = payer
            award.paid_amount = amount
            award.payment_method = method
            award.payment_comment = _comment(method, index)
        awards.append(award)
    ScholarshipAward.objects.bulk_create(awards)
    return period


def _is_paid(index: int, plan: PeriodPlan) -> bool:
    """Exactly `plan.paid` of the `plan.awards` rows, spread evenly."""
    if plan.paid >= plan.awards:
        return True
    return (index * plan.paid) // plan.awards != ((index + 1) * plan.paid) // plan.awards


def seed_mock_data(*, stdout=None) -> SeedResult:
    rng = random.Random(SEED)
    now = timezone.now()
    result = SeedResult(payer=find_payer())
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
            result.periods.append(_period(plan, number, result.groups, students, config, result.payer, rng, now))
    return result


def statistics(periods) -> dict:
    awards = ScholarshipAward.objects.filter(period__in=periods)
    paid = Q(payment_status=PaymentStatus.PAID)
    totals = awards.aggregate(
        total=Count("id"), paid=Count("id", filter=paid), pending=Count("id", filter=~paid),
        accrued=Sum("amount"), paid_sum=Sum("paid_amount", filter=paid), remaining=Sum("amount", filter=~paid),
        cash=Count("id", filter=paid & Q(payment_method=PaymentMethod.CASH)),
        bank=Count("id", filter=paid & Q(payment_method=PaymentMethod.BANK)),
    )
    rows = []
    for period in ScholarshipPeriod.objects.filter(pk__in=[p.pk for p in periods]).order_by("period_start", "period_end"):
        agg = period.awards.aggregate(
            total=Count("id"), paid=Count("id", filter=paid), accrued=Sum("amount"),
            paid_sum=Sum("paid_amount", filter=paid),
        )
        rows.append((period, agg))
    return {"totals": totals, "rows": rows}
