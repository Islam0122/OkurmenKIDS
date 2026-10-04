"""KPI Engine — the single source of truth for every KPI in the LMS.

Every report that shows a KPI — the Reports section (overview, groups,
teachers), the Analytics dashboard, the Academy Monthly Report and the
Teacher Monthly Report — gets its numbers from here. No other module may
combine metrics into a total KPI.

Official formula (the one the project's monthly reports already used;
weights live in settings.KPI_WEIGHTS):

    total_kpi = Σ(metric × weight) / Σ(weight of metrics that have data)

    attendance         25%   (present + late) / every attendance record
    homework           25%   (submitted + checked + late) / every homework result
    lesson_completion  25%   completed lessons / lessons already due (date ≤ today)
    progress           25%   average homework score (0–10) × 10

Reported alongside, but NOT part of the total:

    retention          active students / (active + students who left in the
                       period and are still inactive) — students of the
                       groups in scope
    teacher_workload   active teachers in scope who gave ≥1 lesson in the
                       period / active teachers in scope
    test_score         average result (0–100) of LMS students' finished
                       tests in the period (analytics.assessments)
    test_pass_rate     share of those results at or above the test's
                       passing score

A metric with no underlying data is None ("no data", never a fabricated
0%) and is left out of the total, the remaining weights renormalised. The
total is computed from the exact (unrounded) metrics and rounded once, at
the very end; the status is derived from that rounded total, so the value
and its status can never disagree.

Scope: always `analytics.scope.AnalyticsScope` — the same period, groups,
lessons (effective-teacher rule), students and teachers for every caller.
"""
from __future__ import annotations

import dataclasses
import datetime as dt

from django.conf import settings
from django.db.models import Avg, Count, Q
from django.db.models.functions import Coalesce
from django.utils import timezone

from typing import TYPE_CHECKING

from apps.academy.models import Attendance, HomeworkResult, Lesson, Student, StudentStatusEvent

if TYPE_CHECKING:  # the analytics package imports this module — import lazily at runtime
    from apps.academy.services.analytics.scope import AnalyticsScope

COMPONENTS = ("attendance", "homework", "lesson_completion", "progress")
METRICS = COMPONENTS + ("retention", "teacher_workload", "test_score", "test_pass_rate")
DEFAULT_WEIGHTS = {"attendance": 0.25, "homework": 0.25, "lesson_completion": 0.25, "progress": 0.25}

METRIC_LABELS = {
    "attendance": "Посещаемость",
    "homework": "Домашние задания",
    "lesson_completion": "Проведённые занятия",
    "progress": "Прогресс (средний балл ДЗ)",
    "retention": "Удержание студентов",
    "teacher_workload": "Нагрузка тренеров",
    "test_score": "Средний результат тестов",
    "test_pass_rate": "Сдали тесты",
}

# Status of a KPI value: >= 90 good, 75–89.9 attention, < 75 low.
STATUS_GOOD = 90
STATUS_ATTENTION = 75
STATUS_LABELS = {
    "good": "Хороший",
    "attention": "Требует внимания",
    "low": "Низкий",
    "no_data": "Нет данных",
}

ATTENDED = (Attendance.Status.PRESENT, Attendance.Status.LATE)
SUBMITTED = (HomeworkResult.Status.SUBMITTED, HomeworkResult.Status.CHECKED, HomeworkResult.Status.LATE)


def kpi_weights() -> dict[str, float]:
    configured = getattr(settings, "KPI_WEIGHTS", None) or DEFAULT_WEIGHTS
    weights = {name: float(configured.get(name, 0) or 0) for name in COMPONENTS}
    return weights if sum(weights.values()) > 0 else dict(DEFAULT_WEIGHTS)


def ratio(part: float, total: float) -> float | None:
    """Exact percentage (no rounding) — None when there is nothing to measure."""
    return part / total * 100 if total else None


def round1(value: float | None) -> float | None:
    return None if value is None else round(value, 1)


def kpi_status(value: float | None) -> str:
    if value is None:
        return "no_data"
    if value >= STATUS_GOOD:
        return "good"
    if value >= STATUS_ATTENTION:
        return "attention"
    return "low"


def total_kpi(metrics: dict[str, float | None], weights: dict[str, float] | None = None) -> float | None:
    """Exact weighted total of the official components that have data."""
    weights = weights or kpi_weights()
    present = {name: metrics.get(name) for name in COMPONENTS if metrics.get(name) is not None and weights[name]}
    weight_sum = sum(weights[name] for name in present)
    if not weight_sum:
        return None
    return sum(value * weights[name] for name, value in present.items()) / weight_sum


def weights_description(weights: dict[str, float] | None = None) -> list[dict]:
    weights = weights or kpi_weights()
    weight_sum = sum(weights.values())
    return [
        {"key": name, "label": METRIC_LABELS[name], "weight": round(weights[name] / weight_sum * 100, 1)}
        for name in COMPONENTS
    ]


@dataclasses.dataclass
class KPICounts:
    """Raw counts every metric is derived from. `None` for a population the
    caller didn't measure (e.g. teacher workload inside one group row)."""

    attendance_total: int = 0
    attendance_attended: int = 0
    homework_results: int = 0
    homework_submitted: int = 0
    lessons_due: int = 0
    lessons_held: int = 0
    avg_score: float | None = None
    students_active: int | None = None
    students_left: int | None = None
    teachers_active: int | None = None
    teachers_with_lessons: int | None = None
    test_attempts: int = 0
    test_passed: int = 0
    test_avg_score: float | None = None


@dataclasses.dataclass
class KPIResult:
    counts: KPICounts
    metrics_exact: dict[str, float | None]
    total_exact: float | None
    weights: dict[str, float]

    @property
    def metrics(self) -> dict[str, float | None]:
        return {name: round1(value) for name, value in self.metrics_exact.items()}

    @property
    def total(self) -> float | None:
        return round1(self.total_exact)

    @property
    def status(self) -> str:
        return kpi_status(self.total)

    def as_contract(self) -> dict:
        """The response contract every KPI endpoint returns."""
        return {
            "metrics": self.metrics,
            "kpi": {
                "total": self.total,
                "status": self.status,
                "status_label": STATUS_LABELS[self.status],
                "weights": weights_description(self.weights),
            },
        }


def from_counts(counts: KPICounts, weights: dict[str, float] | None = None) -> KPIResult:
    """Metrics and total KPI from raw counts — the one formula, used both by
    `KPIEngine.calculate` and by per-group/per-teacher breakdown rows."""
    weights = weights or kpi_weights()
    retention_base = (
        counts.students_active + counts.students_left
        if counts.students_active is not None and counts.students_left is not None
        else 0
    )
    metrics = {
        "attendance": ratio(counts.attendance_attended, counts.attendance_total),
        "homework": ratio(counts.homework_submitted, counts.homework_results),
        "lesson_completion": ratio(counts.lessons_held, counts.lessons_due),
        "progress": counts.avg_score * 10 if counts.avg_score is not None else None,
        "retention": ratio(counts.students_active, retention_base) if counts.students_active is not None else None,
        "teacher_workload": (
            ratio(counts.teachers_with_lessons, counts.teachers_active)
            if counts.teachers_active is not None
            else None
        ),
        "test_score": counts.test_avg_score,
        "test_pass_rate": ratio(counts.test_passed, counts.test_attempts),
    }
    return KPIResult(counts=counts, metrics_exact=metrics, total_exact=total_kpi(metrics, weights), weights=weights)


def _effective_teacher():
    return Coalesce("teacher_id", "group_teacher__teacher_id")


class KPIEngine:
    """`KPIEngine.calculate(start=..., end=..., group_id=..., teacher_id=...,
    program_id=..., subject_id=...)` or `KPIEngine.calculate(scope=...)`."""

    @classmethod
    def calculate(
        cls,
        *,
        scope: AnalyticsScope | None = None,
        start: dt.date | None = None,
        end: dt.date | None = None,
        group_id: int | None = None,
        teacher_id: int | None = None,
        program_id: int | None = None,
        subject_id: int | None = None,
        today: dt.date | None = None,
    ) -> KPIResult:
        if scope is None:
            from apps.academy.services.analytics.period import DateRange
            from apps.academy.services.analytics.scope import AnalyticsScope

            if start is None or end is None:
                raise ValueError("KPIEngine.calculate needs either `scope` or `start` and `end`.")
            scope = AnalyticsScope(
                date_range=DateRange(start, end), teacher_id=teacher_id, group_id=group_id,
                course_id=program_id, subject_id=subject_id,
            )
        return from_counts(cls.counts(scope, today=today or timezone.localdate()))

    @staticmethod
    def counts(scope: AnalyticsScope, *, today: dt.date) -> KPICounts:
        rng = scope.date_range
        lessons = scope.lessons_qs()

        lesson_agg = lessons.aggregate(
            held=Count("id", filter=Q(status=Lesson.Status.COMPLETED)),
            due=Count("id", filter=Q(date__lte=today)),
        )
        attendance_agg = Attendance.objects.filter(lesson__in=lessons).aggregate(
            total=Count("id"), attended=Count("id", filter=Q(status__in=ATTENDED))
        )
        results_agg = HomeworkResult.objects.filter(homework__lesson__in=lessons).aggregate(
            total=Count("id"), submitted=Count("id", filter=Q(status__in=SUBMITTED)), avg_score=Avg("score")
        )

        groups = scope.groups_qs()
        students_active = Student.objects.filter(group__in=groups, status=Student.Status.ACTIVE).count()
        students_left = (
            StudentStatusEvent.objects.filter(
                event_type=StudentStatusEvent.EventType.DEACTIVATED,
                event_date__gte=rng.start,
                event_date__lte=rng.end,
                group__in=groups,
            )
            .exclude(student__status=Student.Status.ACTIVE)
            .values("student_id")
            .distinct()
            .count()
        )

        from apps.academy.services.analytics import assessments

        tests = assessments.counts(scope, rng)

        active_teacher_ids = set(scope.teachers_qs().filter(is_active=True).values_list("id", flat=True))
        taught_ids = set(
            lessons.order_by().annotate(_t=_effective_teacher()).values_list("_t", flat=True).distinct()
        )

        return KPICounts(
            attendance_total=attendance_agg["total"] or 0,
            attendance_attended=attendance_agg["attended"] or 0,
            homework_results=results_agg["total"] or 0,
            homework_submitted=results_agg["submitted"] or 0,
            lessons_due=lesson_agg["due"] or 0,
            lessons_held=lesson_agg["held"] or 0,
            avg_score=results_agg["avg_score"],
            students_active=students_active,
            students_left=students_left,
            teachers_active=len(active_teacher_ids),
            teachers_with_lessons=len(active_teacher_ids & taught_ids),
            test_attempts=tests["attempts"],
            test_passed=tests["passed"],
            test_avg_score=tests["average"],
        )
