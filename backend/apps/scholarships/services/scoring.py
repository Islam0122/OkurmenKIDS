"""Scholarship score calculation across *all* of a student's subjects.

Everything is loaded in a handful of bulk queries per period and computed
in Python with `Decimal`, so a period's result never depends on query
order, float rounding or N+1 access patterns. The rules implemented here
are documented in docs/scholarships.md; the key ones:

* Lesson set: every non-cancelled lesson dated inside the period that has
  an Attendance record for the student. Attendance is unique per
  (student, lesson), so no lesson can be counted twice, and lessons from a
  group the student left mid-period still count for the lessons they were
  actually marked in. Subject = `Lesson.subject`.
* Attendance: PRESENT and LATE count as attended, ABSENT as missed, EXCUSED
  is excluded from the denominator. A completed lesson of the student's
  current group with *no* attendance record is reported as "unmarked" —
  surfaced as a data warning, never silently turned into an absence.
* Homework: every Homework on a lesson in the lesson set, except lessons
  flagged «ДЗ не требуется» and lessons the student missed with an excused
  absence. SUBMITTED/CHECKED = 1, LATE = configured partial credit,
  NOT_SUBMITTED or no result row = 0. A subject with no homework has no
  homework component (weights are renormalised for that subject).
* Trainer feedback: mean of every TrainerFeedback for (period, student,
  subject), each mapped to 0–100. Missing feedback is 0 — never a perfect
  score — and, if the configuration requires it, makes the student
  ineligible with status «Неполные данные».
* Subject score: weighted mix of the available components. Overall score:
  aggregate of subject scores (equal per subject, or by number of counted
  lessons — configurable).
"""
from __future__ import annotations

import datetime as dt
from collections import defaultdict
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal

from django.db.models import Q

from apps.academy.models import Attendance, Homework, HomeworkResult, Lesson, Student, StudentStatusEvent

from ..models import EligibilityStatus, ScholarshipPeriod, SubjectAggregation, TrainerFeedback

HUNDRED = Decimal(100)
ZERO = Decimal(0)
ONE = Decimal(1)
NO_SUBJECT_NAME = "Без предмета"

_ATTENDED = {Attendance.Status.PRESENT, Attendance.Status.LATE}
_COMPLETED_HOMEWORK = {HomeworkResult.Status.SUBMITTED, HomeworkResult.Status.CHECKED}
_LEAVING_EVENTS = {
    StudentStatusEvent.EventType.DEACTIVATED,
    StudentStatusEvent.EventType.PAUSED,
    StudentStatusEvent.EventType.COMPLETED,
}
_RETURNING_EVENTS = {StudentStatusEvent.EventType.REACTIVATED, StudentStatusEvent.EventType.CONTINUED}


def quantize(value: Decimal | None) -> Decimal | None:
    if value is None:
        return None
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _ratio_percent(numerator: Decimal, denominator: Decimal) -> Decimal | None:
    if not denominator:
        return None
    return Decimal(numerator) / Decimal(denominator) * HUNDRED


def _weighted_mean(pairs: list[tuple[Decimal, Decimal]]) -> Decimal | None:
    """Σ value·weight / Σ weight over the pairs whose value is known."""
    known = [(value, weight) for value, weight in pairs if value is not None]
    total_weight = sum((weight for _, weight in known), ZERO)
    if not total_weight:
        return None
    return sum((value * weight for value, weight in known), ZERO) / total_weight


@dataclass
class ScoringSettings:
    attendance_weight: Decimal
    homework_weight: Decimal
    feedback_weight: Decimal
    subject_aggregation: str
    late_homework_credit: Decimal
    min_overall_score: Decimal
    min_marked_lessons: int
    require_complete_feedback: bool

    @classmethod
    def from_period(cls, period: ScholarshipPeriod) -> "ScoringSettings":
        return cls(
            attendance_weight=period.attendance_weight,
            homework_weight=period.homework_weight,
            feedback_weight=period.feedback_weight,
            subject_aggregation=period.subject_aggregation,
            late_homework_credit=period.late_homework_credit,
            min_overall_score=period.min_overall_score,
            min_marked_lessons=period.min_marked_lessons,
            require_complete_feedback=period.require_complete_feedback,
        )


@dataclass
class SubjectResult:
    subject_id: int | None
    subject_name: str
    lessons_attended: int = 0
    lessons_missed: int = 0
    lessons_excused: int = 0
    lessons_unmarked: int = 0
    homework_required: int = 0
    homework_completed: Decimal = ZERO
    homework_without_result: int = 0
    teacher_ids: set = field(default_factory=set)
    feedback_scores: list = field(default_factory=list)
    attendance_score: Decimal | None = None
    homework_score: Decimal | None = None
    feedback_score: Decimal | None = None
    subject_score: Decimal | None = None
    aggregation_weight: Decimal = ZERO

    @property
    def countable_lessons(self) -> int:
        return self.lessons_attended + self.lessons_missed

    @property
    def feedback_applicable(self) -> bool:
        # Feedback is given per real Subject — a legacy subject-less lesson
        # has nothing a trainer could be asked to assess it under.
        return self.subject_id is not None

    @property
    def feedback_missing(self) -> bool:
        return self.feedback_applicable and self.countable_lessons > 0 and not self.feedback_scores

    @property
    def is_counted(self) -> bool:
        return self.aggregation_weight > 0


@dataclass
class StudentResult:
    student: Student
    subjects: list[SubjectResult]
    overall_score: Decimal | None
    attendance_score: Decimal | None
    homework_score: Decimal | None
    feedback_score: Decimal | None
    lessons_count: int
    eligibility_status: str
    ineligibility_reason: str
    warnings: list[str]

    @property
    def counted_subjects(self) -> list[SubjectResult]:
        return [s for s in self.subjects if s.is_counted]


# ---------------------------------------------------------------------------
# Bulk data loading
# ---------------------------------------------------------------------------

@dataclass
class _PeriodData:
    attendance_by_student: dict  # student_id -> list[dict]
    unmarked_by_student: dict  # student_id -> list[dict] (lesson rows)
    homework_by_lesson: dict  # lesson_id -> list[homework_id]
    results: dict  # (homework_id, student_id) -> status
    feedback: dict  # student_id -> {subject_id: list[Decimal]}
    events_by_student: dict  # student_id -> list[StudentStatusEvent]


def candidate_students(period: ScholarshipPeriod):
    """Every currently active student, plus anyone (active or not) with an
    attendance record in the period — so inactive/withdrawn students show up
    in the report as ineligible with a reason instead of vanishing."""
    in_period = Attendance.objects.filter(
        lesson__date__gte=period.period_start, lesson__date__lte=period.period_end
    ).values("student_id")
    return (
        Student.objects.filter(Q(status=Student.Status.ACTIVE) | Q(id__in=in_period))
        .select_related("group__course")
        .order_by("id")
    )


def _load_period_data(period: ScholarshipPeriod, students: list[Student]) -> _PeriodData:
    student_ids = [s.id for s in students]
    lessons_in_period = Lesson.objects.filter(
        date__gte=period.period_start, date__lte=period.period_end
    ).exclude(status=Lesson.Status.CANCELLED)

    attendance_by_student: dict[int, list[dict]] = defaultdict(list)
    marked_lessons: dict[int, set] = defaultdict(set)
    for row in (
        Attendance.objects.filter(lesson__in=lessons_in_period, student_id__in=student_ids)
        .values(
            "student_id",
            "lesson_id",
            "status",
            "lesson__subject_id",
            "lesson__subject__name",
            "lesson__homework_not_required",
            "lesson__teacher_id",
            "lesson__group_teacher__teacher_id",
        )
        .order_by("lesson__date", "lesson_id")
    ):
        attendance_by_student[row["student_id"]].append(row)
        marked_lessons[row["student_id"]].add(row["lesson_id"])

    # Completed lessons of each student's *current* group that have no
    # attendance record for them — reported, never scored as absences.
    group_ids = {s.group_id for s in students if s.group_id}
    lessons_by_group: dict[int, list[dict]] = defaultdict(list)
    for row in lessons_in_period.filter(group_id__in=group_ids, status=Lesson.Status.COMPLETED).values(
        "id", "group_id", "date", "subject_id", "subject__name"
    ):
        lessons_by_group[row["group_id"]].append(row)
    unmarked_by_student: dict[int, list[dict]] = {}
    for student in students:
        if not student.group_id:
            continue
        unmarked_by_student[student.id] = [
            row
            for row in lessons_by_group.get(student.group_id, [])
            if row["id"] not in marked_lessons[student.id]
            and (student.enrollment_date is None or row["date"] >= student.enrollment_date)
        ]

    lesson_ids = {row["lesson_id"] for rows in attendance_by_student.values() for row in rows}
    homework_by_lesson: dict[int, list[int]] = defaultdict(list)
    for homework_id, lesson_id in Homework.objects.filter(lesson_id__in=lesson_ids).values_list("id", "lesson_id"):
        homework_by_lesson[lesson_id].append(homework_id)
    homework_ids = [hw for hws in homework_by_lesson.values() for hw in hws]
    results = {
        (homework_id, student_id): status
        for homework_id, student_id, status in HomeworkResult.objects.filter(
            homework_id__in=homework_ids, student_id__in=student_ids
        ).values_list("homework_id", "student_id", "status")
    }

    feedback: dict[int, dict] = defaultdict(lambda: defaultdict(list))
    for item in TrainerFeedback.objects.filter(period=period, student_id__in=student_ids).order_by("id"):
        feedback[item.student_id][item.subject_id].append(item.score)

    events_by_student: dict[int, list] = defaultdict(list)
    for event in StudentStatusEvent.objects.filter(
        student_id__in=student_ids,
        event_date__gte=period.period_start,
        event_date__lt=period.evaluation_date,
    ).order_by("event_date", "id"):
        events_by_student[event.student_id].append(event)

    return _PeriodData(
        attendance_by_student=attendance_by_student,
        unmarked_by_student=unmarked_by_student,
        homework_by_lesson=homework_by_lesson,
        results=results,
        feedback=feedback,
        events_by_student=events_by_student,
    )


# ---------------------------------------------------------------------------
# Per-student computation
# ---------------------------------------------------------------------------

def _collect_subjects(student: Student, data: _PeriodData, settings: ScoringSettings) -> dict:
    subjects: dict[int | None, SubjectResult] = {}

    def bucket(subject_id, subject_name) -> SubjectResult:
        if subject_id not in subjects:
            subjects[subject_id] = SubjectResult(subject_id, subject_name or NO_SUBJECT_NAME)
        return subjects[subject_id]

    for row in data.attendance_by_student.get(student.id, []):
        result = bucket(row["lesson__subject_id"], row["lesson__subject__name"])
        status = row["status"]
        if status in _ATTENDED:
            result.lessons_attended += 1
        elif status == Attendance.Status.EXCUSED:
            result.lessons_excused += 1
        else:
            result.lessons_missed += 1

        teacher_id = row["lesson__teacher_id"] or row["lesson__group_teacher__teacher_id"]
        if teacher_id:
            result.teacher_ids.add(teacher_id)

        if row["lesson__homework_not_required"] or status == Attendance.Status.EXCUSED:
            continue
        for homework_id in data.homework_by_lesson.get(row["lesson_id"], []):
            result.homework_required += 1
            hw_status = data.results.get((homework_id, student.id))
            if hw_status in _COMPLETED_HOMEWORK:
                result.homework_completed += ONE
            elif hw_status == HomeworkResult.Status.LATE:
                result.homework_completed += settings.late_homework_credit
            elif hw_status is None:
                result.homework_without_result += 1

    for row in data.unmarked_by_student.get(student.id, []):
        bucket(row["subject_id"], row["subject__name"]).lessons_unmarked += 1

    for subject_id, scores in data.feedback.get(student.id, {}).items():
        if subject_id in subjects:
            subjects[subject_id].feedback_scores.extend(scores)

    return subjects


def _score_subject(result: SubjectResult, settings: ScoringSettings) -> None:
    result.attendance_score = _ratio_percent(result.lessons_attended, result.countable_lessons)
    result.homework_score = _ratio_percent(result.homework_completed, result.homework_required)
    if result.feedback_applicable and result.countable_lessons:
        result.feedback_score = (
            sum(result.feedback_scores, ZERO) / len(result.feedback_scores) if result.feedback_scores else ZERO
        )

    if result.attendance_score is None:
        # No countable lesson (none, or only excused) — nothing to judge
        # this subject on; it is shown in the breakdown but not counted.
        result.subject_score = None
        result.aggregation_weight = ZERO
        return

    result.subject_score = _weighted_mean(
        [
            (result.attendance_score, settings.attendance_weight),
            (result.homework_score, settings.homework_weight),
            (result.feedback_score, settings.feedback_weight),
        ]
    )
    if result.subject_score is None:
        result.aggregation_weight = ZERO
    elif settings.subject_aggregation == SubjectAggregation.LESSON_WEIGHTED:
        result.aggregation_weight = Decimal(result.countable_lessons)
    else:
        result.aggregation_weight = ONE


def _status_problem(student: Student, period: ScholarshipPeriod, events: list) -> tuple[str, str] | None:
    if student.enrollment_date is None:
        return EligibilityStatus.INCOMPLETE_DATA, "Не указана дата начала обучения."
    if student.enrollment_date > period.period_start:
        return (
            EligibilityStatus.NOT_FULL_PERIOD,
            f"Начало обучения {student.enrollment_date:%d.%m.%Y} — позже начала периода "
            f"{period.period_start:%d.%m.%Y}; первый полный период ещё не завершён.",
        )
    if student.status != Student.Status.ACTIVE:
        return EligibilityStatus.INACTIVE, f"Текущий статус обучения: «{student.get_status_display()}»."
    for event in events:
        if event.event_type in _LEAVING_EVENTS:
            return (
                EligibilityStatus.INACTIVE,
                f"{event.get_event_type_display()} {event.event_date:%d.%m.%Y} — обучение прерывалось в периоде.",
            )
        if event.event_type in _RETURNING_EVENTS and event.event_date > period.period_start:
            return (
                EligibilityStatus.NOT_FULL_PERIOD,
                f"{event.get_event_type_display()} {event.event_date:%d.%m.%Y} — обучался не весь период.",
            )
    return None


def evaluate_student(
    student: Student, period: ScholarshipPeriod, data: _PeriodData, settings: ScoringSettings
) -> StudentResult:
    subjects = _collect_subjects(student, data, settings)
    for result in subjects.values():
        _score_subject(result, settings)
    ordered = sorted(subjects.values(), key=lambda s: (s.subject_id is None, s.subject_name))
    counted = [s for s in ordered if s.is_counted]

    overall = _weighted_mean([(s.subject_score, s.aggregation_weight) for s in counted])
    attendance = _weighted_mean([(s.attendance_score, s.aggregation_weight) for s in counted])
    homework = _weighted_mean([(s.homework_score, s.aggregation_weight) for s in counted])
    feedback = _weighted_mean([(s.feedback_score, s.aggregation_weight) for s in counted])
    lessons_count = sum(s.countable_lessons for s in ordered)

    warnings: list[str] = []
    for s in ordered:
        if s.lessons_unmarked:
            warnings.append(f"{s.subject_name}: {s.lessons_unmarked} проведённых занятий без отметки посещаемости.")
        if s.homework_without_result:
            warnings.append(f"{s.subject_name}: {s.homework_without_result} ДЗ без результата (засчитано как не сдано).")
        if s.feedback_missing:
            warnings.append(f"{s.subject_name}: нет оценки тренера.")
        if s.subject_id is None and s.countable_lessons:
            warnings.append(f"{NO_SUBJECT_NAME}: у {s.countable_lessons} занятий не указан предмет.")
        if not s.is_counted:
            warnings.append(f"{s.subject_name}: нет занятий для оценки — предмет не учитывается в итоговом балле.")

    problem = _status_problem(student, period, data.events_by_student.get(student.id, []))
    if problem is None and (not counted or lessons_count < settings.min_marked_lessons):
        problem = (
            EligibilityStatus.NO_DATA,
            f"Отмечено занятий за период: {lessons_count} (нужно не меньше {settings.min_marked_lessons}).",
        )
    if problem is None and settings.require_complete_feedback:
        missing = [s.subject_name for s in counted if s.feedback_missing]
        if missing:
            problem = EligibilityStatus.INCOMPLETE_DATA, "Нет оценки тренера: " + ", ".join(missing) + "."
    if problem is None and quantize(overall) < settings.min_overall_score:
        problem = (
            EligibilityStatus.BELOW_THRESHOLD,
            f"Итоговый балл {quantize(overall)} ниже порога {settings.min_overall_score}.",
        )
    status, reason = problem if problem else (EligibilityStatus.ELIGIBLE, "")

    return StudentResult(
        student=student,
        subjects=ordered,
        overall_score=quantize(overall),
        attendance_score=quantize(attendance),
        homework_score=quantize(homework),
        feedback_score=quantize(feedback),
        lessons_count=lessons_count,
        eligibility_status=status,
        ineligibility_reason=reason,
        warnings=warnings,
    )


def evaluate_period(period: ScholarshipPeriod) -> list[StudentResult]:
    settings = ScoringSettings.from_period(period)
    students = list(candidate_students(period))
    data = _load_period_data(period, students)
    return [evaluate_student(student, period, data, settings) for student in students]


def ranking_key(result: StudentResult) -> tuple:
    """Deterministic ordering, best first — documented tie-breakers:
    overall ↓, attendance ↓, homework ↓ (none ranks last), feedback ↓,
    earlier enrollment date, then lower student id as the final, stable
    (never random) tie-breaker."""
    minus_one = Decimal(-1)
    return (
        -(result.overall_score if result.overall_score is not None else minus_one),
        -(result.attendance_score if result.attendance_score is not None else minus_one),
        -(result.homework_score if result.homework_score is not None else minus_one),
        -(result.feedback_score if result.feedback_score is not None else minus_one),
        result.student.enrollment_date or dt.date.max,
        result.student.id,
    )
