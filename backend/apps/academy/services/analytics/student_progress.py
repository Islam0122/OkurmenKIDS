"""«Прогресс студентов» — each student's own figures inside one group's KPI
for a period (Мои группы → группа → KPI), next to the group KPI.

The lessons are exactly the group KPI's own (`AnalyticsScope.lessons_qs` with
the same group / trainer scoping and `resolve_period`), so the group card and
the per-student table always describe the same period and the same lessons.
The group KPI itself (services.analytics / services.kpi_engine) is untouched.

Rules:
* a lesson counts as held only once it is completed and not in the future;
  cancelled and still-open lessons are never held, so never a miss;
* a student is measured only on the held lessons of the time they actually
  belonged to the group (enrollment date + their StudentStatusEvent history:
  transfers, departures, pauses, returns). A lesson the student has an
  attendance or homework record for always counts — the record proves they
  were there;
* attendance % is over the lessons actually marked for the student (the
  group KPI's own definition); an unmarked lesson is not a miss;
* homework counts only where a Homework exists for the lesson — no homework
  planned, nothing to fail; a missing score is never a zero;
* no data → None («Нет данных» in the UI), never a division by zero;
* one row per (student, lesson) / (student, homework) — the DB constraints
  already guarantee it, the dicts below make it hold regardless.

Queries: a fixed handful per call (lessons, attendance, homework, results,
students + their status events, test attempts) — never one per student or
per lesson. The figures are then put together in Python from those rows, as
membership dates per student can't be expressed as one aggregate.
"""
from __future__ import annotations

import dataclasses
import datetime as dt

from django.db.models import Prefetch, Q

from apps.academy.models import Attendance, Group, Homework, HomeworkResult, Lesson, Student, StudentStatusEvent
from .period import DateRange, resolve_comparison, resolve_period
from .scope import AnalyticsScope

_ATTENDED = (Attendance.Status.PRESENT, Attendance.Status.LATE)
_DONE = (HomeworkResult.Status.SUBMITTED, HomeworkResult.Status.CHECKED, HomeworkResult.Status.LATE)

# «The previous comparable period» for each period of the KPI switch.
_COMPARE_FOR_PERIOD = {
    "today": "previous_period",
    "yesterday": "previous_period",
    "last_7_days": "previous_period",
    "this_week": "previous_week",
    "last_week": "previous_week",
    "this_month": "previous_month",
    "last_month": "previous_month",
    "custom": "previous_period",
}

# Events that take the student out of their group / bring them into one.
_LEAVES = (
    StudentStatusEvent.EventType.DEACTIVATED,
    StudentStatusEvent.EventType.PAUSED,
    StudentStatusEvent.EventType.COMPLETED,
)
_JOINS = (StudentStatusEvent.EventType.REACTIVATED, StudentStatusEvent.EventType.CONTINUED)


def _pct(part: int, total: int) -> float | None:
    return round(part / total * 100, 1) if total else None


def _avg(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 1) if values else None


def _change(current: float | None, previous: float | None) -> float | None:
    if current is None or previous is None:
        return None
    return round(current - previous, 1)


# ---------------------------------------------------------------------------
# Membership
# ---------------------------------------------------------------------------

@dataclasses.dataclass(frozen=True)
class Membership:
    """Which group a student was in on each day: a start date (enrollment)
    plus a sorted list of (date, group id or None) changes."""

    start: dt.date | None
    initial_group: int | None
    changes: tuple[tuple[dt.date, int | None], ...]

    def group_on(self, day: dt.date) -> int | None:
        if self.start is not None and day < self.start:
            return None
        group = self.initial_group
        for when, target in self.changes:
            if when > day:
                break
            group = target
        return group

    def in_group(self, group_id: int, start: dt.date, end: dt.date) -> bool:
        """Was the student in `group_id` on at least one day of [start, end]?"""
        turns = [start] + [when for when, _ in self.changes if start < when <= end]
        if self.start is not None and start < self.start <= end:
            turns.append(self.start)
        return any(self.group_on(day) == group_id for day in turns)


def membership(student: Student) -> Membership:
    """From the student's history log (prefetched `status_events`). Before
    the first event the student was in the group that event moved them out
    of (or, with no events at all, in today's group)."""
    events = sorted(student.status_events.all(), key=lambda e: (e.event_date, e.created_at, e.pk))
    changes: list[tuple[dt.date, int | None]] = []
    for event in events:
        if event.event_type == StudentStatusEvent.EventType.TRANSFERRED:
            changes.append((event.event_date, event.group_id))
        elif event.event_type in _LEAVES:
            changes.append((event.event_date, None))
        elif event.event_type in _JOINS:
            changes.append((event.event_date, event.group_id or student.group_id))
    if not events:
        initial = student.group_id
    else:
        first = events[0]
        if first.event_type == StudentStatusEvent.EventType.TRANSFERRED:
            initial = first.from_group_id
        elif first.event_type in _LEAVES:
            initial = first.group_id
        else:
            initial = None
    return Membership(start=student.enrollment_date, initial_group=initial, changes=tuple(changes))


# ---------------------------------------------------------------------------
# Raw rows for one group and one date range — a fixed number of queries.
# ---------------------------------------------------------------------------

@dataclasses.dataclass
class _Rows:
    lessons: list[Lesson]
    attendance: dict[tuple[int, int], str]  # (student, lesson) -> status
    homework_by_lesson: dict[int, list[Homework]]
    results: dict[tuple[int, int], HomeworkResult]  # (student, homework) -> result
    tests: dict[int, list]  # student -> finished attempts


def _load(scope: AnalyticsScope, group: Group, date_range: DateRange, *, today: dt.date, student_ids=None) -> _Rows:
    from apps.testing.models import AttemptStatus, StudentAttempt

    lessons = list(
        scope.lessons_qs(date_range=date_range)
        .filter(status=Lesson.Status.COMPLETED, date__lte=today)
        .select_related("subject")
        .order_by("date", "start_time", "lesson_number", "pk")
    )
    lesson_ids = [lesson.pk for lesson in lessons]

    attendance_qs = Attendance.objects.filter(lesson_id__in=lesson_ids)
    if student_ids is not None:
        attendance_qs = attendance_qs.filter(student_id__in=student_ids)
    attendance = {(row["student_id"], row["lesson_id"]): row["status"]
                  for row in attendance_qs.order_by().values("student_id", "lesson_id", "status")}

    homework_by_lesson: dict[int, list[Homework]] = {}
    for homework in Homework.objects.filter(lesson_id__in=lesson_ids).order_by("pk"):
        homework_by_lesson.setdefault(homework.lesson_id, []).append(homework)

    results_qs = HomeworkResult.objects.filter(homework__lesson_id__in=lesson_ids)
    if student_ids is not None:
        results_qs = results_qs.filter(student_id__in=student_ids)
    results = {(r.student_id, r.homework_id): r for r in results_qs.order_by("pk")}

    attempts = StudentAttempt.objects.filter(
        status=AttemptStatus.FINISHED, student__isnull=False, user__isnull=True, group=group,
        finished_at__date__gte=date_range.start, finished_at__date__lte=date_range.end,
    )
    if scope.teacher_id is not None:
        attempts = attempts.filter(teacher_id=scope.teacher_id)
    if scope.subject_id is not None:
        attempts = attempts.filter(subject_id=scope.subject_id)
    if student_ids is not None:
        attempts = attempts.filter(student_id__in=student_ids)
    tests: dict[int, list] = {}
    for attempt in attempts.select_related("session__test").order_by("finished_at"):
        tests.setdefault(attempt.student_id, []).append(attempt)

    return _Rows(lessons, attendance, homework_by_lesson, results, tests)


def _students(group: Group, rows: _Rows, date_range: DateRange, student_ids=None) -> list[tuple[Student, Membership]]:
    """Students who belonged to the group during the period, or have a record
    on one of its lessons — each with their membership timeline."""
    with_records = {student for student, _ in rows.attendance} | {student for student, _ in rows.results} | set(rows.tests)
    qs = Student.objects.filter(
        Q(group=group) | Q(status_events__group=group) | Q(status_events__from_group=group) | Q(pk__in=with_records)
    )
    if student_ids is not None:
        qs = qs.filter(pk__in=student_ids)
    qs = qs.distinct().prefetch_related(
        Prefetch("status_events", queryset=StudentStatusEvent.objects.order_by())
    ).order_by("last_name", "first_name", "pk")
    picked = []
    for student in qs:
        timeline = membership(student)
        if student.pk in with_records or timeline.in_group(group.pk, date_range.start, date_range.end):
            picked.append((student, timeline))
    return picked


# ---------------------------------------------------------------------------
# Figures
# ---------------------------------------------------------------------------

def _student_lessons(student: Student, timeline: Membership, group: Group, rows: _Rows) -> list[Lesson]:
    """The held lessons that count for this student."""
    own = []
    for lesson in rows.lessons:
        has_record = (student.pk, lesson.pk) in rows.attendance or any(
            (student.pk, hw.pk) in rows.results for hw in rows.homework_by_lesson.get(lesson.pk, ())
        )
        if has_record or timeline.group_on(lesson.date) == group.pk:
            own.append(lesson)
    return own


def _figures(student: Student, lessons: list[Lesson], rows: _Rows) -> dict:
    counts = {status: 0 for status in Attendance.Status.values}
    homework_due = homework_done = 0
    scores: list[float] = []
    for lesson in lessons:
        status = rows.attendance.get((student.pk, lesson.pk))
        if status:
            counts[status] += 1
        for homework in rows.homework_by_lesson.get(lesson.pk, ()):
            homework_due += 1
            result = rows.results.get((student.pk, homework.pk))
            if result is not None:
                if result.status in _DONE:
                    homework_done += 1
                if result.score is not None:
                    scores.append(result.score)
    marked = sum(counts.values())
    attended = counts[Attendance.Status.PRESENT] + counts[Attendance.Status.LATE]
    tests = rows.tests.get(student.pk, [])
    return {
        "lessons_held": len(lessons),
        "attendance_marked": marked,
        "attended": attended,
        "late": counts[Attendance.Status.LATE],
        "absences": counts[Attendance.Status.ABSENT] + counts[Attendance.Status.EXCUSED],
        "excused": counts[Attendance.Status.EXCUSED],
        "attendance_rate": _pct(attended, marked),
        "homework_due": homework_due,
        "homework_done": homework_done,
        "homework_rate": _pct(homework_done, homework_due),
        "average_score": _avg(scores),
        "scored_count": len(scores),
        "tests_count": len(tests),
        "test_average": _avg([attempt.score for attempt in tests]),
    }


_COMPARED = ("attendance_rate", "homework_rate", "average_score", "test_average")


def _dynamics(current: dict, previous: dict | None) -> dict:
    return {key: _change(current[key], previous[key] if previous else None) for key in _COMPARED}


def _lesson_detail(student: Student, lesson: Lesson, rows: _Rows) -> dict:
    homeworks = []
    for homework in rows.homework_by_lesson.get(lesson.pk, ()):
        result = rows.results.get((student.pk, homework.pk))
        homeworks.append({
            "id": homework.pk,
            "title": homework.title,
            "status": result.status if result else None,
            "status_display": result.get_status_display() if result else "Нет результата",
            "score": result.score if result else None,
        })
    status = rows.attendance.get((student.pk, lesson.pk))
    return {
        "id": lesson.pk,
        "date": lesson.date,
        "lesson_number": lesson.lesson_number,
        "topic": lesson.topic,
        "subject": lesson.subject.name if lesson.subject_id else None,
        "attendance": status,
        "attendance_display": Attendance.Status(status).label if status else None,
        "homework": homeworks,
    }


def _test_detail(attempt) -> dict:
    test = attempt.session.test if attempt.session_id else None
    passing = getattr(test, "passing_score", None)
    return {
        "id": str(attempt.pk),
        "title": attempt.test_title or (test.title if test else ""),
        "date": attempt.finished_at.date() if attempt.finished_at else None,
        "score": round(attempt.score, 1),
        "passed": attempt.score >= passing if passing is not None else None,
    }


# ---------------------------------------------------------------------------
# Entry points
# ---------------------------------------------------------------------------

def _ranges(period: str, start_date, end_date, today: dt.date) -> tuple[DateRange, DateRange]:
    current = resolve_period(period, today=today, start_date=start_date, end_date=end_date)
    previous = resolve_comparison(current, _COMPARE_FOR_PERIOD.get(period, "previous_period"))
    return current, previous


def _period_payload(period: str, current: DateRange, previous: DateRange) -> dict:
    return {
        "period": {"key": period, "start_date": current.start, "end_date": current.end},
        "comparison": {"start_date": previous.start, "end_date": previous.end},
    }


def _row(student: Student, group: Group, figures: dict, previous: dict | None) -> dict:
    return {
        "id": student.pk,
        "name": str(student),
        "first_name": student.first_name,
        "last_name": student.last_name,
        "status": student.status,
        "status_display": student.get_status_display(),
        "in_group_now": student.group_id == group.pk,
        **figures,
        "previous": {key: previous[key] for key in _COMPARED} if previous else None,
        "change": _dynamics(figures, previous),
    }


def _previous_figures(student, timeline, group, prev_rows) -> dict | None:
    prev_lessons = _student_lessons(student, timeline, group, prev_rows)
    if not prev_lessons and not prev_rows.tests.get(student.pk):
        return None
    return _figures(student, prev_lessons, prev_rows)


def group_student_progress(
    group: Group,
    *,
    period: str,
    start_date: dt.date | None = None,
    end_date: dt.date | None = None,
    teacher_id: int | None = None,
    today: dt.date,
) -> dict:
    """Every student's figures for the period, plus their change against the
    previous comparable period."""
    current, previous = _ranges(period, start_date, end_date, today)
    scope = AnalyticsScope(date_range=current, teacher_id=teacher_id, group_id=group.pk)
    rows = _load(scope, group, current, today=today)
    prev_rows = _load(scope.with_range(previous), group, previous, today=today)

    students = []
    for student, timeline in _students(group, rows, current):
        figures = _figures(student, _student_lessons(student, timeline, group, rows), rows)
        students.append(_row(student, group, figures, _previous_figures(student, timeline, group, prev_rows)))

    return {
        **_period_payload(period, current, previous),
        "lessons_held": len(rows.lessons),
        "students": students,
    }


def student_progress_detail(
    group: Group,
    student_id: int,
    *,
    period: str,
    start_date: dt.date | None = None,
    end_date: dt.date | None = None,
    teacher_id: int | None = None,
    today: dt.date,
) -> dict | None:
    """One student's lessons of the period — date, attendance, homework and
    its status / score — plus their tests and the change against the previous
    period. None when the student isn't part of this group's period."""
    current, previous = _ranges(period, start_date, end_date, today)
    scope = AnalyticsScope(date_range=current, teacher_id=teacher_id, group_id=group.pk)
    rows = _load(scope, group, current, today=today, student_ids=[student_id])
    picked = _students(group, rows, current, student_ids=[student_id])
    if not picked:
        return None
    student, timeline = picked[0]
    prev_rows = _load(scope.with_range(previous), group, previous, today=today, student_ids=[student_id])
    lessons = _student_lessons(student, timeline, group, rows)
    figures = _figures(student, lessons, rows)
    return {
        **_period_payload(period, current, previous),
        "student": _row(student, group, figures, _previous_figures(student, timeline, group, prev_rows)),
        "lessons": [_lesson_detail(student, lesson, rows) for lesson in lessons],
        "tests": [_test_detail(attempt) for attempt in rows.tests.get(student.pk, [])],
    }
