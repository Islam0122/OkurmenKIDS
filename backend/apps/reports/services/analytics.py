"""Report analytics — every number of a parent report, from the LMS records.

Built on the group KPI's own per-student engine
(apps.academy.services.analytics.student_progress), so a report never
disagrees with «Мои группы → группа → KPI»:

* lessons — ``AnalyticsScope.lessons_qs`` of the group (a trainer: only the
  lessons they give); *conducted* = completed and not in the future, so
  cancelled, still-open and future lessons are never conducted;
* a student is measured only on the conducted lessons of the time they
  actually belonged to the group (membership history);
* attendance % is over the lessons marked for the student — an unmarked
  lesson is not an absence;
* homework counts only where a Homework exists for the lesson; a missing
  score is never a zero;
* tests — finished attempts of LMS students of this group in the period;
  attempts whose answers still wait for review are not results yet (same
  rule as the KPI engine's analytics.assessments).

Report-specific rules:

* the students of a report are the group's **active** students on the
  period's last day (services.student_roster): deactivated, paused,
  graduated and transferred-out students are left out of the table and of
  every group figure;
* group rates are pooled over those students' records (attended / marked,
  done / due, mean of every score) — the KPI engine's definition;
* the previous period is computed for the *same* students, so the change is
  a real change, not a change of who is in the group;
* no data → None («Нет данных»), never 0 and never a division by zero.

The result is a plain JSON-ready dict — it is stored as the report's
calculation snapshot and is the only input of the text and image generators.
"""
from __future__ import annotations

import dataclasses
import datetime as dt

from django.db.models import Prefetch
from django.utils import timezone

from apps.academy.models import Group, GroupTeacher, Lesson, Student, StudentStatusEvent
from apps.academy.services import student_roster
from apps.academy.services.analytics import student_progress as sp
from apps.academy.services.analytics.scope import AnalyticsScope

from . import comparison
from .periods import ReportPeriod

SNAPSHOT_VERSION = 1

# Individual status: composite of the available metrics, each on 0–100.
STATUS_EXCELLENT = "excellent"
STATUS_GOOD = "good"
STATUS_ATTENTION = "attention"
STATUS_SUPPORT = "support"
STATUS_NO_DATA = "no_data"
STATUSES = (STATUS_EXCELLENT, STATUS_GOOD, STATUS_ATTENTION, STATUS_SUPPORT, STATUS_NO_DATA)

EXCELLENT_FROM = 85.0
GOOD_FROM = 70.0
ATTENTION_FROM = 55.0
# Below this attendance a student needs support whatever their grades.
CRITICAL_ATTENDANCE = 50.0

def _pct(part: int, total: int) -> float | None:
    return round(part / total * 100, 1) if total else None


def _avg(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 1) if values else None


def student_status(figures: dict) -> str:
    """Отлично / Хорошо / Нужно внимание / Требуется поддержка / Нет данных."""
    attendance = figures.get("attendance_rate")
    parts = [
        value for value in (
            attendance,
            figures.get("homework_rate"),
            figures["average_score"] * 10 if figures.get("average_score") is not None else None,
            figures.get("test_average"),
        )
        if value is not None
    ]
    if not parts:
        return STATUS_NO_DATA
    if attendance is not None and attendance < CRITICAL_ATTENDANCE:
        return STATUS_SUPPORT
    composite = sum(parts) / len(parts)
    if composite >= EXCELLENT_FROM:
        return STATUS_EXCELLENT
    if composite >= GOOD_FROM:
        return STATUS_GOOD
    if composite >= ATTENTION_FROM:
        return STATUS_ATTENTION
    return STATUS_SUPPORT


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------

def _drop_unreviewed_tests(rows) -> None:
    """Attempts with answers still waiting for review have a provisional score."""
    from apps.testing.models import REVIEW_GRADING_STATUSES, StudentAttempt

    ids = [attempt.pk for attempts in rows.tests.values() for attempt in attempts]
    if not ids:
        return
    pending = set(
        StudentAttempt.objects.filter(pk__in=ids, answers__grading_status__in=REVIEW_GRADING_STATUSES)
        .values_list("pk", flat=True)
    )
    if pending:
        rows.tests = {
            student_id: kept for student_id, attempts in rows.tests.items()
            if (kept := [attempt for attempt in attempts if attempt.pk not in pending])
        }


def _load_rows(scope: AnalyticsScope, group: Group, date_range, today: dt.date, student_ids: list[int]):
    rows = sp._load(scope.with_range(date_range), group, date_range, today=today, student_ids=student_ids)
    _drop_unreviewed_tests(rows)
    return rows


def active_students(group: Group, period: ReportPeriod, today: dt.date, student_ids=None) -> list[Student]:
    """The group's active students on the period's last day (never in the future)."""
    roster = student_roster.roster_on(student_roster.roster_date(period.current.end, today), group_ids=[group.pk])
    ids = [sid for sid, entry in roster.items() if entry.is_active and entry.group_id == group.pk]
    if student_ids is not None:
        wanted = set(student_ids)
        ids = [sid for sid in ids if sid in wanted]
    return list(
        Student.objects.filter(pk__in=ids)
        .prefetch_related(Prefetch("status_events", queryset=StudentStatusEvent.objects.order_by()))
        .order_by("last_name", "first_name", "pk")
    )


# ---------------------------------------------------------------------------
# Per student
# ---------------------------------------------------------------------------

@dataclasses.dataclass
class _Measure:
    figures: dict
    scores: list[float]
    test_scores: list[float]
    tests: list[dict]


def _scores(student: Student, lessons: list[Lesson], rows) -> list[float]:
    scores = []
    for lesson in lessons:
        for homework in rows.homework_by_lesson.get(lesson.pk, ()):
            result = rows.results.get((student.pk, homework.pk))
            if result is not None and result.score is not None:
                scores.append(float(result.score))
    return scores


def _measure(student: Student, timeline, group: Group, rows) -> _Measure | None:
    lessons = sp._student_lessons(student, timeline, group, rows)
    attempts = rows.tests.get(student.pk, [])
    if not lessons and not attempts:
        return None
    figures = sp._figures(student, lessons, rows)
    return _Measure(
        figures=figures,
        scores=_scores(student, lessons, rows),
        test_scores=[float(attempt.score) for attempt in attempts],
        tests=[_test(attempt) for attempt in attempts],
    )


def _test(attempt) -> dict:
    detail = sp._test_detail(attempt)
    return {
        "title": detail["title"],
        "date": detail["date"].isoformat() if detail["date"] else None,
        "score": detail["score"],
        "passed": detail["passed"],
    }


_EMPTY_FIGURES = {
    "lessons_held": 0, "attendance_marked": 0, "attended": 0, "late": 0, "absences": 0, "excused": 0,
    "attendance_rate": None, "homework_due": 0, "homework_done": 0, "homework_rate": None,
    "average_score": None, "scored_count": 0, "tests_count": 0, "test_average": None,
}


def _student_entry(student: Student, current: _Measure | None, previous: _Measure | None) -> dict:
    figures = dict(current.figures) if current else dict(_EMPTY_FIGURES)
    prev = {key: previous.figures[key] for key in comparison.COMPARED_METRICS} if previous else None
    return {
        "id": student.pk,
        "name": str(student),
        "first_name": student.first_name,
        "last_name": student.last_name,
        **figures,
        "tests": current.tests if current else [],
        "status": student_status(figures),
        "previous": prev,
        "comparison": comparison.compare(figures, prev),
    }


# ---------------------------------------------------------------------------
# Group
# ---------------------------------------------------------------------------

def _pooled(measures: list[_Measure]) -> dict:
    marked = sum(m.figures["attendance_marked"] for m in measures)
    attended = sum(m.figures["attended"] for m in measures)
    due = sum(m.figures["homework_due"] for m in measures)
    done = sum(m.figures["homework_done"] for m in measures)
    scores = [score for m in measures for score in m.scores]
    tests = [score for m in measures for score in m.test_scores]
    return {
        "attendance_marked": marked,
        "attended": attended,
        "absences": sum(m.figures["absences"] for m in measures),
        "attendance_rate": _pct(attended, marked),
        "homework_due": due,
        "homework_done": done,
        "homework_rate": _pct(done, due),
        "average_score": _avg(scores),
        "scored_count": len(scores),
        "tests_count": len(tests),
        "test_average": _avg(tests),
    }


def _trainers(group: Group, teacher_id: int | None) -> list[str]:
    programs = GroupTeacher.objects.filter(group=group, is_active=True).select_related("teacher__user")
    if teacher_id is not None:
        programs = programs.filter(teacher_id=teacher_id)
    names = []
    for program in programs.order_by("pk"):
        name = str(program.teacher)
        if name not in names:
            names.append(name)
    return names


def build_report_data(
    group: Group,
    period: ReportPeriod,
    *,
    teacher_id: int | None = None,
    today: dt.date | None = None,
    student_ids: list[int] | None = None,
) -> dict:
    """The full calculation snapshot of one report (group + every student)."""
    today = today or timezone.localdate()
    scope = AnalyticsScope(date_range=period.current, teacher_id=teacher_id, group_id=group.pk)

    students = active_students(group, period, today, student_ids)
    ids = [student.pk for student in students]
    rows = _load_rows(scope, group, period.current, today, ids)
    prev_rows = _load_rows(scope, group, period.previous, today, ids)

    entries, current_measures, previous_measures = [], [], []
    for student in students:
        timeline = sp.membership(student)
        current = _measure(student, timeline, group, rows)
        previous = _measure(student, timeline, group, prev_rows)
        entries.append(_student_entry(student, current, previous))
        if current:
            current_measures.append(current)
        if previous:
            previous_measures.append(previous)

    lessons = scope.lessons_qs()
    planned = lessons.exclude(status=Lesson.Status.CANCELLED).count()
    cancelled = lessons.filter(status=Lesson.Status.CANCELLED).count()

    stats = _pooled(current_measures)
    status_counts = {status: sum(1 for entry in entries if entry["status"] == status) for status in STATUSES}
    stats.update({
        "active_students": len(entries),
        "planned_lessons": planned,
        "conducted_lessons": len(rows.lessons),
        "cancelled_lessons": cancelled,
        "excellent_count": status_counts[STATUS_EXCELLENT],
        "attention_count": status_counts[STATUS_ATTENTION] + status_counts[STATUS_SUPPORT],
        "status_counts": status_counts,
    })
    previous_stats = _pooled(previous_measures) if previous_measures else None
    prev_compared = {key: previous_stats[key] for key in comparison.COMPARED_METRICS} if previous_stats else None

    return {
        "version": SNAPSHOT_VERSION,
        "generated_at": timezone.now().isoformat(),
        "today": today.isoformat(),
        "group": {
            "id": group.pk,
            "name": group.name,
            "course": group.course.name if group.course_id else "",
            "trainers": _trainers(group, teacher_id),
        },
        "teacher_scope_id": teacher_id,
        "period": {
            "key": period.key,
            "start": period.current.start.isoformat(),
            "end": period.current.end.isoformat(),
            "monthly": period.is_monthly,
        },
        "comparison_period": {"start": period.previous.start.isoformat(), "end": period.previous.end.isoformat()},
        "group_stats": stats,
        "previous_group_stats": prev_compared,
        "group_comparison": comparison.compare(stats, prev_compared),
        "students": entries,
    }

