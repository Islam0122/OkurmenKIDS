"""Computes every academy analytics figure on demand from Lesson/Attendance/
Homework/HomeworkResult/Student/Group/Teacher — the real business models.

Nothing here is ever persisted. There is no KPI table to keep in sync: call
``AnalyticsService(...).get_dashboard()`` and the numbers it returns are
already correct for whatever the database looks like right now. Change an
Attendance record and the very next call reflects it — no recalculation
step, no cache to invalidate, no Celery task.

Every section below is built from a small, fixed number of GROUP BY
aggregate queries (``Count``/``Avg`` with a ``filter=Q(...)`` clause) run
once against the whole scoped queryset, never one query per row — so the
dashboard costs the same handful of queries whether there are 5 groups or
500 students.

Percentage conventions (carried over unchanged from the old
``services/kpi_calculator.py`` this replaces — see history):
- Attendance percentage counts LATE as attended, ABSENT as not attended,
  measured against attendance records that actually exist (an unmarked
  lesson doesn't count against anyone).
- Homework completion at the group/teacher/overview level is measured
  against the number of results that *could* exist (homeworks assigned in
  the period x active students) — how much of the class actually turned
  work in.
- Homework completion at the student level is measured against homeworks
  *assigned* to their group in the period (a homework with no
  HomeworkResult row at all still counts as missed).
- The dedicated "Homework Analytics" section (`homework` key) mirrors the
  old KPIHomework meaning instead: completion measured against results
  that already exist (`total_results`), i.e. how much of what came in was
  submitted/checked/on time — a different question from the group/teacher
  numbers above, kept distinct on purpose.
"""
from __future__ import annotations

import datetime as dt

from django.db.models import Avg, Count, Q, QuerySet

from apps.users.models import Teacher

from ..models import Attendance, Group, Homework, HomeworkResult, Lesson, Student

_COMPLETED_HOMEWORK_STATUSES = (
    HomeworkResult.Status.SUBMITTED,
    HomeworkResult.Status.CHECKED,
    HomeworkResult.Status.LATE,
)
_ATTENDED_STATUSES = (Attendance.Status.PRESENT, Attendance.Status.LATE)


def _pct(numerator: int, denominator: int) -> float:
    return round(numerator / denominator * 100, 1) if denominator else 0.0


def _round1(value: float | None) -> float:
    return round(value, 1) if value is not None else 0.0


class AnalyticsService:
    """Builds the Analytics Dashboard payload for one date range, optionally
    narrowed to a single Teacher and/or a single Group. No Teacher/Group
    filter means "all of them" — never a separate stored record per slice."""

    def __init__(
        self,
        start_date: dt.date,
        end_date: dt.date,
        teacher_id: int | None = None,
        group_id: int | None = None,
    ) -> None:
        self.start_date = start_date
        self.end_date = end_date
        self.teacher_id = teacher_id
        self.group_id = group_id

    # ------------------------------------------------------------------
    # Scoped base querysets — every section below starts from one of these.
    # ------------------------------------------------------------------

    def _groups_qs(self) -> QuerySet[Group]:
        # `is not None`, not a truthy check — a caller may deliberately pass
        # an id that matches nothing (e.g. 0) to force an empty dashboard,
        # and that must still filter, not be treated as "no filter".
        qs = Group.objects.all()
        if self.teacher_id is not None:
            qs = qs.filter(teacher_id=self.teacher_id)
        if self.group_id is not None:
            qs = qs.filter(id=self.group_id)
        return qs

    def _teachers_qs(self) -> QuerySet[Teacher]:
        qs = Teacher.objects.all()
        if self.teacher_id is not None:
            qs = qs.filter(id=self.teacher_id)
        if self.group_id is not None:
            qs = qs.filter(groups__id=self.group_id).distinct()
        return qs

    def _students_qs(self) -> QuerySet[Student]:
        return Student.objects.filter(group__in=self._groups_qs(), is_active=True)

    def _lessons_qs(self) -> QuerySet[Lesson]:
        return Lesson.objects.filter(
            group__in=self._groups_qs(), date__gte=self.start_date, date__lte=self.end_date
        )

    def _attendance_qs(self) -> QuerySet[Attendance]:
        return Attendance.objects.filter(lesson__in=self._lessons_qs())

    def _homeworks_qs(self) -> QuerySet[Homework]:
        return Homework.objects.filter(lesson__in=self._lessons_qs())

    def _homework_results_qs(self) -> QuerySet[HomeworkResult]:
        return HomeworkResult.objects.filter(homework__in=self._homeworks_qs())

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def get_dashboard(self) -> dict:
        lesson_stats = self._lesson_stats()
        attendance_stats = self._attendance_stats()
        homework_stats = self._homework_stats()

        groups_count = self._groups_qs().count()
        teachers_count = self._teachers_qs().count()
        students_count = self._students_qs().count()

        total_homeworks_assigned = self._homeworks_qs().count()
        possible_results = total_homeworks_assigned * students_count
        overview_homework_percent = _pct(homework_stats["completed"], possible_results)

        group_rows = self._group_analytics()
        teacher_rows = self._teacher_analytics()
        student_rows = self._student_analytics()

        overview = {
            "groups": groups_count,
            "teachers": teachers_count,
            "students": students_count,
            "lessons": lesson_stats["total"],
            "attendance_percent": attendance_stats["percent"],
            "homework_completion_percent": overview_homework_percent,
            "average_score": homework_stats["average_score"],
        }

        return {
            "period": {"start_date": self.start_date, "end_date": self.end_date},
            "filters": {"teacher_id": self.teacher_id, "group_id": self.group_id},
            "overview": overview,
            "lessons": lesson_stats,
            "attendance": attendance_stats,
            "homework": homework_stats,
            "groups": group_rows,
            "teachers": teacher_rows,
            "top_students": student_rows[:15],
            "charts": {
                "attendance_over_time": attendance_stats["by_date"],
                "lessons_by_status": [
                    {"status": "completed", "label": "Проведено", "count": lesson_stats["completed"]},
                    {"status": "planned", "label": "Запланировано", "count": lesson_stats["planned"]},
                    {"status": "cancelled", "label": "Отменено", "count": lesson_stats["cancelled"]},
                ],
                "students_by_group": [{"group": row["name"], "students": row["students"]} for row in group_rows],
                "homework_completion_over_time": homework_stats["by_date"],
                "teacher_performance": [
                    {"teacher": row["name"], "attendance_percent": row["attendance_percent"]} for row in teacher_rows
                ],
                "group_performance": [
                    {"group": row["name"], "attendance_percent": row["attendance_percent"]} for row in group_rows
                ],
            },
        }

    # ------------------------------------------------------------------
    # Lesson / attendance / homework — flat, single-table aggregates.
    # ------------------------------------------------------------------

    def _lesson_stats(self) -> dict:
        agg = self._lessons_qs().aggregate(
            total=Count("id"),
            completed=Count("id", filter=Q(status=Lesson.Status.COMPLETED)),
            cancelled=Count("id", filter=Q(status=Lesson.Status.CANCELLED)),
            planned=Count("id", filter=Q(status=Lesson.Status.PLANNED)),
        )
        total = agg["total"] or 0
        completed = agg["completed"] or 0
        return {
            "total": total,
            "completed": completed,
            "cancelled": agg["cancelled"] or 0,
            "planned": agg["planned"] or 0,
            "completion_rate": _pct(completed, total),
        }

    def _attendance_stats(self) -> dict:
        agg = self._attendance_qs().aggregate(
            total=Count("id"),
            present=Count("id", filter=Q(status=Attendance.Status.PRESENT)),
            absent=Count("id", filter=Q(status=Attendance.Status.ABSENT)),
            late=Count("id", filter=Q(status=Attendance.Status.LATE)),
            excused=Count("id", filter=Q(status=Attendance.Status.EXCUSED)),
        )
        total = agg["total"] or 0
        attended = (agg["present"] or 0) + (agg["late"] or 0)

        by_date_rows = (
            self._attendance_qs()
            .values("lesson__date")
            .annotate(total=Count("id"), attended=Count("id", filter=Q(status__in=_ATTENDED_STATUSES)))
            .order_by("lesson__date")
        )

        return {
            "total": total,
            "present": agg["present"] or 0,
            "absent": agg["absent"] or 0,
            "late": agg["late"] or 0,
            "excused": agg["excused"] or 0,
            "percent": _pct(attended, total),
            "by_date": [
                {"date": row["lesson__date"], "percent": _pct(row["attended"], row["total"])} for row in by_date_rows
            ],
        }

    def _homework_stats(self) -> dict:
        """Mirrors the old KPIHomework meaning: completion measured against
        results that already exist, not against every possible result."""
        agg = self._homework_results_qs().aggregate(
            total=Count("id"),
            submitted=Count("id", filter=Q(status=HomeworkResult.Status.SUBMITTED)),
            checked=Count("id", filter=Q(status=HomeworkResult.Status.CHECKED)),
            late=Count("id", filter=Q(status=HomeworkResult.Status.LATE)),
            not_submitted=Count("id", filter=Q(status=HomeworkResult.Status.NOT_SUBMITTED)),
            avg_score=Avg("score"),
        )
        total_results = agg["total"] or 0
        completed = (agg["submitted"] or 0) + (agg["checked"] or 0) + (agg["late"] or 0)

        by_date_rows = (
            self._homework_results_qs()
            .values("homework__lesson__date")
            .annotate(
                total=Count("id"),
                completed=Count("id", filter=Q(status__in=_COMPLETED_HOMEWORK_STATUSES)),
            )
            .order_by("homework__lesson__date")
        )

        return {
            "total_homeworks": self._homeworks_qs().count(),
            "total_results": total_results,
            "submitted": agg["submitted"] or 0,
            "checked": agg["checked"] or 0,
            "late": agg["late"] or 0,
            "not_submitted": agg["not_submitted"] or 0,
            "completed": completed,
            "completion_percent": _pct(completed, total_results),
            "average_score": _round1(agg["avg_score"]),
            "by_date": [
                {"date": row["homework__lesson__date"], "percent": _pct(row["completed"], row["total"])}
                for row in by_date_rows
            ],
        }

    # ------------------------------------------------------------------
    # Per-group / per-teacher / per-student tables — each built from a
    # fixed handful of GROUP BY queries, merged in Python by id. Never one
    # query per row.
    # ------------------------------------------------------------------

    def _group_analytics(self) -> list[dict]:
        groups = list(self._groups_qs().select_related("teacher__user").order_by("name"))
        if not groups:
            return []
        group_ids = [group.id for group in groups]

        lessons_by_group = {
            row["group_id"]: row
            for row in Lesson.objects.filter(group_id__in=group_ids, date__gte=self.start_date, date__lte=self.end_date)
            .values("group_id")
            .annotate(
                total=Count("id"),
                completed=Count("id", filter=Q(status=Lesson.Status.COMPLETED)),
                cancelled=Count("id", filter=Q(status=Lesson.Status.CANCELLED)),
                planned=Count("id", filter=Q(status=Lesson.Status.PLANNED)),
            )
        }
        attendance_by_group = {
            row["lesson__group_id"]: row
            for row in Attendance.objects.filter(
                lesson__group_id__in=group_ids, lesson__date__gte=self.start_date, lesson__date__lte=self.end_date
            )
            .values("lesson__group_id")
            .annotate(total=Count("id"), attended=Count("id", filter=Q(status__in=_ATTENDED_STATUSES)))
        }
        homeworks_by_group = {
            row["lesson__group_id"]: row["count"]
            for row in Homework.objects.filter(
                lesson__group_id__in=group_ids, lesson__date__gte=self.start_date, lesson__date__lte=self.end_date
            )
            .values("lesson__group_id")
            .annotate(count=Count("id"))
        }
        results_by_group = {
            row["homework__lesson__group_id"]: row
            for row in HomeworkResult.objects.filter(
                homework__lesson__group_id__in=group_ids,
                homework__lesson__date__gte=self.start_date,
                homework__lesson__date__lte=self.end_date,
            )
            .values("homework__lesson__group_id")
            .annotate(completed=Count("id", filter=Q(status__in=_COMPLETED_HOMEWORK_STATUSES)), avg_score=Avg("score"))
        }
        students_by_group = {
            row["group_id"]: row["count"]
            for row in Student.objects.filter(group_id__in=group_ids, is_active=True)
            .values("group_id")
            .annotate(count=Count("id"))
        }

        rows = []
        for group in groups:
            lessons = lessons_by_group.get(group.id, {})
            attendance = attendance_by_group.get(group.id, {})
            results = results_by_group.get(group.id, {})
            total_students = students_by_group.get(group.id, 0)
            total_homeworks = homeworks_by_group.get(group.id, 0)
            completed_results = results.get("completed", 0)
            possible_results = total_homeworks * total_students

            rows.append(
                {
                    "id": group.id,
                    "name": group.name,
                    "teacher": str(group.teacher),
                    "students": total_students,
                    "lessons": lessons.get("total", 0),
                    "completed_lessons": lessons.get("completed", 0),
                    "cancelled_lessons": lessons.get("cancelled", 0),
                    "planned_lessons": lessons.get("planned", 0),
                    "attendance_percent": _pct(attendance.get("attended", 0), attendance.get("total", 0)),
                    "homework_completion_percent": _pct(completed_results, possible_results),
                    "average_score": _round1(results.get("avg_score")),
                    "status": group.status,
                    "status_display": group.get_status_display(),
                }
            )
        return rows

    def _teacher_analytics(self) -> list[dict]:
        teachers = list(self._teachers_qs().select_related("user").order_by("user__first_name"))
        if not teachers:
            return []
        teacher_ids = [teacher.id for teacher in teachers]
        group_ids = list(self._groups_qs().values_list("id", flat=True))

        groups_by_teacher = {
            row["teacher_id"]: row["count"]
            for row in Group.objects.filter(id__in=group_ids, teacher_id__in=teacher_ids)
            .values("teacher_id")
            .annotate(count=Count("id"))
        }
        students_by_teacher = {
            row["group__teacher_id"]: row["count"]
            for row in Student.objects.filter(group_id__in=group_ids, is_active=True)
            .values("group__teacher_id")
            .annotate(count=Count("id"))
        }
        lessons_by_teacher = {
            row["group__teacher_id"]: row
            for row in Lesson.objects.filter(group_id__in=group_ids, date__gte=self.start_date, date__lte=self.end_date)
            .values("group__teacher_id")
            .annotate(total=Count("id"))
        }
        attendance_by_teacher = {
            row["lesson__group__teacher_id"]: row
            for row in Attendance.objects.filter(
                lesson__group_id__in=group_ids, lesson__date__gte=self.start_date, lesson__date__lte=self.end_date
            )
            .values("lesson__group__teacher_id")
            .annotate(total=Count("id"), attended=Count("id", filter=Q(status__in=_ATTENDED_STATUSES)))
        }
        homeworks_by_teacher = {
            row["lesson__group__teacher_id"]: row["count"]
            for row in Homework.objects.filter(
                lesson__group_id__in=group_ids, lesson__date__gte=self.start_date, lesson__date__lte=self.end_date
            )
            .values("lesson__group__teacher_id")
            .annotate(count=Count("id"))
        }
        results_by_teacher = {
            row["homework__lesson__group__teacher_id"]: row
            for row in HomeworkResult.objects.filter(
                homework__lesson__group_id__in=group_ids,
                homework__lesson__date__gte=self.start_date,
                homework__lesson__date__lte=self.end_date,
            )
            .values("homework__lesson__group__teacher_id")
            .annotate(completed=Count("id", filter=Q(status__in=_COMPLETED_HOMEWORK_STATUSES)), avg_score=Avg("score"))
        }

        rows = []
        for teacher in teachers:
            lessons = lessons_by_teacher.get(teacher.id, {})
            attendance = attendance_by_teacher.get(teacher.id, {})
            results = results_by_teacher.get(teacher.id, {})
            total_students = students_by_teacher.get(teacher.id, 0)
            total_homeworks = homeworks_by_teacher.get(teacher.id, 0)
            completed_results = results.get("completed", 0)
            possible_results = total_homeworks * total_students

            rows.append(
                {
                    "id": teacher.id,
                    "name": str(teacher),
                    "groups": groups_by_teacher.get(teacher.id, 0),
                    "students": total_students,
                    "lessons": lessons.get("total", 0),
                    "attendance_percent": _pct(attendance.get("attended", 0), attendance.get("total", 0)),
                    "homework_completion_percent": _pct(completed_results, possible_results),
                    "average_score": _round1(results.get("avg_score")),
                }
            )
        return rows

    def _student_analytics(self) -> list[dict]:
        students = list(self._students_qs().select_related("group"))
        if not students:
            return []
        student_ids = [student.id for student in students]
        group_ids = list(self._groups_qs().values_list("id", flat=True))

        # "How many lessons/homeworks were possible" is a property of the
        # student's group + period, shared by every student in it — reuse
        # one small per-group query rather than repeating it per student.
        lessons_by_group = {
            row["group_id"]: row["total"]
            for row in Lesson.objects.filter(group_id__in=group_ids, date__gte=self.start_date, date__lte=self.end_date)
            .values("group_id")
            .annotate(total=Count("id"))
        }
        homeworks_by_group = {
            row["lesson__group_id"]: row["count"]
            for row in Homework.objects.filter(
                lesson__group_id__in=group_ids, lesson__date__gte=self.start_date, lesson__date__lte=self.end_date
            )
            .values("lesson__group_id")
            .annotate(count=Count("id"))
        }

        attendance_by_student = {
            row["student_id"]: row
            for row in Attendance.objects.filter(
                student_id__in=student_ids, lesson__date__gte=self.start_date, lesson__date__lte=self.end_date
            )
            .values("student_id")
            .annotate(total=Count("id"), attended=Count("id", filter=Q(status__in=_ATTENDED_STATUSES)))
        }
        results_by_student = {
            row["student_id"]: row
            for row in HomeworkResult.objects.filter(
                student_id__in=student_ids,
                homework__lesson__date__gte=self.start_date,
                homework__lesson__date__lte=self.end_date,
            )
            .values("student_id")
            .annotate(completed=Count("id", filter=Q(status__in=_COMPLETED_HOMEWORK_STATUSES)), avg_score=Avg("score"))
        }

        rows = []
        for student in students:
            attendance = attendance_by_student.get(student.id, {})
            results = results_by_student.get(student.id, {})
            total_homeworks = homeworks_by_group.get(student.group_id, 0)
            completed = results.get("completed", 0)

            rows.append(
                {
                    "id": student.id,
                    "name": str(student),
                    "group": student.group.name if student.group_id else None,
                    "lessons": lessons_by_group.get(student.group_id, 0),
                    "attendance_percent": _pct(attendance.get("attended", 0), attendance.get("total", 0)),
                    "homework_completion_percent": _pct(completed, total_homeworks),
                    "average_score": _round1(results.get("avg_score")),
                }
            )

        rows.sort(key=lambda row: (row["attendance_percent"], row["average_score"]), reverse=True)
        return rows
