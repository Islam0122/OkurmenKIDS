"""Group Analytics — one Group, every one of its Teaching Programs.

Each program (GroupTeacher) is an independent stream with its own lessons,
attendance and homework; this module lays them side by side (one row per
program) and sums them into a group-wide summary, under one set of
filters: program, teacher, subject, period (this week / this month /
whole course) and lesson status.

Definitions are the ones the rest of the app already uses, so a number
here never disagrees with the same number elsewhere:

* lesson counts — by real `Lesson.status` (services.lesson_status);
  "upcoming" is still-scheduled and dated today or later;
* attendance rate — (present + late) / every attendance record
  (services.analytics.attendance);
* homework rate — (submitted + checked + late) / every homework result
  (services.analytics.homework);
* plan progress — conducted lessons / the program's own share of the plan
  (services.lesson_generator.planned_lessons_by_program). Progress is a
  property of the whole course, so it ignores the period filter.

Every figure is computed from the database in a fixed number of grouped
queries (not one query per program).
"""
from __future__ import annotations

import calendar
import datetime as dt
from dataclasses import dataclass, field

from django.db.models import Count, Min, Q
from django.utils import timezone

from ..models import Attendance, Group, HomeworkResult, Lesson
from .lesson_generator import planned_lessons_by_program

PERIOD_WEEK = "week"
PERIOD_MONTH = "month"
PERIOD_COURSE = "course"
PERIOD_CHOICES = [
    (PERIOD_COURSE, "Весь курс"),
    (PERIOD_MONTH, "Этот месяц"),
    (PERIOD_WEEK, "Эта неделя"),
]

_ATTENDED = (Attendance.Status.PRESENT, Attendance.Status.LATE)
_SUBMITTED = (HomeworkResult.Status.SUBMITTED, HomeworkResult.Status.CHECKED, HomeworkResult.Status.LATE)

# Row key for lessons whose program was deleted (Lesson.group_teacher is SET_NULL).
NO_PROGRAM = None


@dataclass(frozen=True)
class GroupAnalyticsFilters:
    program_id: int | None = None
    teacher_id: int | None = None
    subject_id: int | None = None
    period: str = PERIOD_COURSE
    status: str | None = None

    @classmethod
    def from_query(cls, params) -> "GroupAnalyticsFilters":
        def as_int(name):
            value = (params.get(name) or "").strip()
            return int(value) if value.isdigit() else None

        period = params.get("period") or PERIOD_COURSE
        if period not in dict(PERIOD_CHOICES):
            period = PERIOD_COURSE
        status = params.get("status") or None
        if status not in dict(Lesson.Status.choices):
            status = None
        return cls(
            program_id=as_int("program"), teacher_id=as_int("teacher"), subject_id=as_int("subject"),
            period=period, status=status,
        )

    def as_query(self) -> dict:
        return {
            key: value
            for key, value in {
                "program": self.program_id, "teacher": self.teacher_id, "subject": self.subject_id,
                "period": self.period if self.period != PERIOD_COURSE else None, "status": self.status,
            }.items()
            if value
        }


def period_range(period: str, today: dt.date) -> tuple[dt.date, dt.date] | None:
    """Inclusive date range of a period key; None for the whole course."""
    if period == PERIOD_WEEK:
        start = today - dt.timedelta(days=today.weekday())
        return start, start + dt.timedelta(days=6)
    if period == PERIOD_MONTH:
        last_day = calendar.monthrange(today.year, today.month)[1]
        return today.replace(day=1), today.replace(day=last_day)
    return None


def _rate(part: int, total: int) -> float | None:
    return round(part / total * 100, 1) if total else None


@dataclass
class ProgramAnalyticsRow:
    group_teacher_id: int | None
    subject: str
    teacher: str
    is_active: bool
    plan_total: int = 0
    lessons: int = 0  # non-cancelled lessons in the filtered set
    completed: int = 0
    upcoming: int = 0
    cancelled: int = 0
    attention: int = 0
    attendance_total: int = 0
    attendance_attended: int = 0
    homework_results: int = 0
    homework_submitted: int = 0
    completed_all_time: int = 0
    next_lesson_date: dt.date | None = None

    @property
    def attendance_rate(self) -> float | None:
        return _rate(self.attendance_attended, self.attendance_total)

    @property
    def homework_rate(self) -> float | None:
        return _rate(self.homework_submitted, self.homework_results)

    @property
    def progress(self) -> float | None:
        if not self.plan_total:
            return None
        return min(round(self.completed_all_time / self.plan_total * 100, 1), 100.0)

    @property
    def completion_of_lessons(self) -> float | None:
        """Conducted share of the (non-cancelled) lessons in the filtered set."""
        return _rate(self.completed, self.lessons)

    def as_dict(self) -> dict:
        return {
            "program": self.group_teacher_id,
            "subject": self.subject,
            "teacher": self.teacher,
            "is_active": self.is_active,
            "plan_total": self.plan_total,
            "lessons": self.lessons,
            "completed": self.completed,
            "upcoming": self.upcoming,
            "cancelled": self.cancelled,
            "attention": self.attention,
            "attendance_rate": self.attendance_rate,
            "homework_rate": self.homework_rate,
            "completed_all_time": self.completed_all_time,
            "progress": self.progress,
            "next_lesson_date": self.next_lesson_date,
        }


@dataclass
class GroupAnalytics:
    filters: GroupAnalyticsFilters
    date_range: tuple[dt.date, dt.date] | None
    students: int
    rows: list[ProgramAnalyticsRow] = field(default_factory=list)

    def _sum(self, name: str) -> int:
        return sum(getattr(row, name) for row in self.rows)

    @property
    def summary(self) -> dict:
        plan_total = self._sum("plan_total")
        return {
            "students": self.students,
            "programs": sum(1 for row in self.rows if row.group_teacher_id is not NO_PROGRAM),
            "lessons": self._sum("lessons"),
            "completed": self._sum("completed"),
            "upcoming": self._sum("upcoming"),
            "cancelled": self._sum("cancelled"),
            "attention": self._sum("attention"),
            "plan_total": plan_total,
            "completed_all_time": self._sum("completed_all_time"),
            # Weighted by records, never an average of per-program rates.
            "attendance_rate": _rate(self._sum("attendance_attended"), self._sum("attendance_total")),
            "homework_rate": _rate(self._sum("homework_submitted"), self._sum("homework_results")),
            "progress": (
                min(round(self._sum("completed_all_time") / plan_total * 100, 1), 100.0) if plan_total else None
            ),
        }

    def as_dict(self) -> dict:
        return {
            "filters": {
                "program": self.filters.program_id, "teacher": self.filters.teacher_id,
                "subject": self.filters.subject_id, "period": self.filters.period, "status": self.filters.status,
            },
            "date_from": self.date_range[0] if self.date_range else None,
            "date_to": self.date_range[1] if self.date_range else None,
            "summary": self.summary,
            "programs": [row.as_dict() for row in self.rows],
        }


def _program_q(filters: GroupAnalyticsFilters, prefix: str = "") -> Q:
    """Program/teacher/subject filters for a Lesson (at `prefix`). Teacher
    uses the lesson's *effective* teacher, same rule as
    LessonQuerySet.for_teacher."""
    q = Q()
    if filters.program_id:
        q &= Q(**{f"{prefix}group_teacher_id": filters.program_id})
    if filters.teacher_id:
        q &= Q(**{f"{prefix}teacher_id": filters.teacher_id}) | Q(
            **{f"{prefix}teacher__isnull": True, f"{prefix}group_teacher__teacher_id": filters.teacher_id}
        )
    if filters.subject_id:
        q &= Q(**{f"{prefix}subject_id": filters.subject_id})
    return q


def get_group_analytics(group: Group, filters: GroupAnalyticsFilters | None = None, *,
                        today: dt.date | None = None) -> GroupAnalytics:
    filters = filters or GroupAnalyticsFilters()
    today = today or timezone.localdate()
    now_time = timezone.localtime().time()
    date_range = period_range(filters.period, today)

    lessons = Lesson.objects.filter(group=group).filter(_program_q(filters))
    if date_range:
        lessons = lessons.filter(date__gte=date_range[0], date__lte=date_range[1])
    if filters.status:
        lessons = lessons.filter(status=filters.status)

    programs = list(group.teachers.select_related("teacher__user", "subject").order_by("subject__name", "id"))
    if filters.program_id:
        programs = [gt for gt in programs if gt.pk == filters.program_id]
    if filters.teacher_id:
        programs = [gt for gt in programs if gt.teacher_id == filters.teacher_id]
    if filters.subject_id:
        programs = [gt for gt in programs if gt.subject_id == filters.subject_id]

    planned = planned_lessons_by_program(group)
    rows: dict[int | None, ProgramAnalyticsRow] = {
        gt.pk: ProgramAnalyticsRow(
            group_teacher_id=gt.pk,
            subject=gt.subject.name if gt.subject_id else "Без предмета",
            teacher=str(gt.teacher),
            is_active=gt.is_active,
            plan_total=planned.get(gt.pk, 0),
        )
        for gt in programs
    }

    def row_for(group_teacher_id) -> ProgramAnalyticsRow | None:
        if group_teacher_id in rows:
            return rows[group_teacher_id]
        if group_teacher_id is NO_PROGRAM and not filters.program_id:
            rows[NO_PROGRAM] = ProgramAnalyticsRow(
                group_teacher_id=NO_PROGRAM, subject="Без программы", teacher="—", is_active=False,
            )
            return rows[NO_PROGRAM]
        return None  # a program filtered out above

    open_statuses = [Lesson.Status.SCHEDULED, Lesson.Status.IN_PROGRESS]
    lesson_counts = lessons.values("group_teacher_id").annotate(
        lessons=Count("id", filter=~Q(status=Lesson.Status.CANCELLED)),
        completed=Count("id", filter=Q(status=Lesson.Status.COMPLETED)),
        cancelled=Count("id", filter=Q(status=Lesson.Status.CANCELLED)),
        upcoming=Count("id", filter=Q(status=Lesson.Status.SCHEDULED, date__gte=today)),
        attention=Count(
            "id", filter=Q(status__in=open_statuses) & (Q(date__lt=today) | Q(date=today, end_time__lte=now_time)),
        ),
        next_date=Min("date", filter=Q(status=Lesson.Status.SCHEDULED, date__gte=today)),
    )
    for item in lesson_counts:
        row = row_for(item["group_teacher_id"])
        if row is None:
            continue
        row.lessons, row.completed, row.cancelled = item["lessons"], item["completed"], item["cancelled"]
        row.upcoming, row.attention, row.next_lesson_date = item["upcoming"], item["attention"], item["next_date"]

    attendance = (
        Attendance.objects.filter(lesson__in=lessons)
        .values("lesson__group_teacher_id")
        .annotate(total=Count("id"), attended=Count("id", filter=Q(status__in=_ATTENDED)))
    )
    for item in attendance:
        row = row_for(item["lesson__group_teacher_id"])
        if row is not None:
            row.attendance_total, row.attendance_attended = item["total"], item["attended"]

    homework = (
        HomeworkResult.objects.filter(homework__lesson__in=lessons)
        .values("homework__lesson__group_teacher_id")
        .annotate(total=Count("id"), submitted=Count("id", filter=Q(status__in=_SUBMITTED)))
    )
    for item in homework:
        row = row_for(item["homework__lesson__group_teacher_id"])
        if row is not None:
            row.homework_results, row.homework_submitted = item["total"], item["submitted"]

    # Plan progress is course-wide: every conducted lesson of the program,
    # whatever the period/status filter.
    conducted = (
        Lesson.objects.filter(group=group, status=Lesson.Status.COMPLETED)
        .filter(_program_q(filters))
        .values("group_teacher_id")
        .annotate(n=Count("id"))
    )
    for item in conducted:
        row = row_for(item["group_teacher_id"])
        if row is not None:
            row.completed_all_time = item["n"]

    ordered = sorted(
        rows.values(),
        key=lambda row: (row.group_teacher_id is NO_PROGRAM, not row.is_active, row.subject, row.teacher),
    )
    return GroupAnalytics(filters=filters, date_range=date_range, students=group.students_count, rows=ordered)
