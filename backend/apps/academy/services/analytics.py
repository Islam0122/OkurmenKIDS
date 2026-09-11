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
from django.db.models.functions import Coalesce

from apps.users.models import Teacher

from ..models import Attendance, Group, GroupTeacher, Homework, HomeworkResult, Lesson, Student

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
            # Any real stake in the group — its own legacy `teacher`, or an
            # active Teaching Program (see models.GroupTeacher). A Group can
            # have several teachers; the roster/group-level sections below
            # (students, group rows) are shared by every Teaching Program of
            # a group this teacher has a stake in, same as Group/Student API
            # access (see models.GroupQuerySet.for_teacher) — only the
            # Lesson-level figures (see `_effective_teacher_q`) are further
            # narrowed to this teacher's own Lessons.
            qs = qs.filter(
                Q(teacher_id=self.teacher_id)
                | Q(teachers__teacher_id=self.teacher_id, teachers__is_active=True)
            ).distinct()
        if self.group_id is not None:
            qs = qs.filter(id=self.group_id)
        return qs

    def _teachers_qs(self) -> QuerySet[Teacher]:
        qs = Teacher.objects.all()
        if self.teacher_id is not None:
            qs = qs.filter(id=self.teacher_id)
        if self.group_id is not None:
            qs = qs.filter(
                Q(groups__id=self.group_id)
                | Q(group_assignments__group_id=self.group_id, group_assignments__is_active=True)
            ).distinct()
        return qs

    def _students_qs(self) -> QuerySet[Student]:
        return Student.objects.filter(group__in=self._groups_qs(), is_active=True)

    def _effective_teacher_q(self, prefix: str = "") -> Q | None:
        """Q object restricting to rows whose Lesson's *effective* teacher
        (its own `teacher`, or — for older/legacy lessons with none — its
        group's own `teacher`; see Lesson.effective_teacher) is
        `self.teacher_id`, for a Lesson reached via `prefix` field lookups
        (e.g. "lesson__" from Attendance, "homework__lesson__" from
        HomeworkResult). None when no teacher filter is active.

        This is what keeps one teacher's figures from being mixed with
        another teacher's, even within a Group they both teach in (see
        models.GroupTeacher) — unlike `_groups_qs`/`_students_qs` above,
        which a Group's several independent Teaching Programs legitimately
        share.
        """
        if self.teacher_id is None:
            return None
        return Q(**{f"{prefix}teacher_id": self.teacher_id}) | Q(
            **{f"{prefix}teacher__isnull": True, f"{prefix}group__teacher_id": self.teacher_id}
        )

    def _lessons_qs(self) -> QuerySet[Lesson]:
        qs = Lesson.objects.filter(
            group__in=self._groups_qs(), date__gte=self.start_date, date__lte=self.end_date
        )
        teacher_q = self._effective_teacher_q()
        if teacher_q is not None:
            qs = qs.filter(teacher_q)
        return qs

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

        # A Teacher's own row for a shared Group must reflect only *their*
        # Teaching Program (see models.GroupTeacher) — not the whole
        # group's combined figures, which would mix in a colleague's
        # Lessons/Attendance/Homework in the same Group (spec §39).
        lesson_teacher_q = self._effective_teacher_q()
        lesson_q = Q(group_id__in=group_ids, date__gte=self.start_date, date__lte=self.end_date)
        if lesson_teacher_q is not None:
            lesson_q &= lesson_teacher_q

        lesson_via_lesson_q = self._effective_teacher_q("lesson__")

        attendance_q = Q(
            lesson__group_id__in=group_ids, lesson__date__gte=self.start_date, lesson__date__lte=self.end_date
        )
        if lesson_via_lesson_q is not None:
            attendance_q &= lesson_via_lesson_q

        homeworks_q = Q(
            lesson__group_id__in=group_ids, lesson__date__gte=self.start_date, lesson__date__lte=self.end_date
        )
        if lesson_via_lesson_q is not None:
            homeworks_q &= lesson_via_lesson_q

        results_q = Q(
            homework__lesson__group_id__in=group_ids,
            homework__lesson__date__gte=self.start_date,
            homework__lesson__date__lte=self.end_date,
        )
        results_teacher_q = self._effective_teacher_q("homework__lesson__")
        if results_teacher_q is not None:
            results_q &= results_teacher_q

        lessons_by_group = {
            row["group_id"]: row
            for row in Lesson.objects.filter(lesson_q)
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
            for row in Attendance.objects.filter(attendance_q)
            .values("lesson__group_id")
            .annotate(total=Count("id"), attended=Count("id", filter=Q(status__in=_ATTENDED_STATUSES)))
        }
        homeworks_by_group = {
            row["lesson__group_id"]: row["count"]
            for row in Homework.objects.filter(homeworks_q)
            .values("lesson__group_id")
            .annotate(count=Count("id"))
        }
        results_by_group = {
            row["homework__lesson__group_id"]: row
            for row in HomeworkResult.objects.filter(results_q)
            .values("homework__lesson__group_id")
            .annotate(completed=Count("id", filter=Q(status__in=_COMPLETED_HOMEWORK_STATUSES)), avg_score=Avg("score"))
        }
        # Roster stays whole-group — a student's own membership doesn't
        # belong to any one Teaching Program (spec §39's Students section).
        students_by_group = {
            row["group_id"]: row["count"]
            for row in Student.objects.filter(group_id__in=group_ids, is_active=True)
            .values("group_id")
            .annotate(count=Count("id"))
        }

        teacher_label = None
        if self.teacher_id is not None:
            requested_teacher = Teacher.objects.filter(id=self.teacher_id).select_related("user").first()
            teacher_label = str(requested_teacher) if requested_teacher else None

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
                    "teacher": teacher_label if teacher_label is not None else str(group.teacher) if group.teacher_id else "—",
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
        """One row per Teacher, built from that teacher's own *effective*
        Lessons only (`Lesson.teacher`, or — for older/legacy lessons with
        none — the lesson's group's own `teacher`; see
        Lesson.effective_teacher). Grouping by `group__teacher_id` (a
        Group's single legacy field) would silently attribute another
        teacher's Lessons in a shared Group to whoever that field happens to
        point at — exactly the cross-Teaching-Program mixing spec §39 rules
        out.
        """
        teachers = list(self._teachers_qs().select_related("user").order_by("user__first_name"))
        if not teachers:
            return []
        teacher_ids = [teacher.id for teacher in teachers]
        group_ids = list(self._groups_qs().values_list("id", flat=True))

        # Which of `group_ids` each teacher has a real stake in — a Group
        # maps to *several* teachers here, one per independent Teaching
        # Program (see models.GroupTeacher), never assumed to be just one.
        legacy_pairs = Group.objects.filter(id__in=group_ids, teacher_id__in=teacher_ids).values_list(
            "teacher_id", "id"
        )
        program_pairs = GroupTeacher.objects.filter(
            group_id__in=group_ids, teacher_id__in=teacher_ids, is_active=True
        ).values_list("teacher_id", "group_id")
        groups_by_teacher_id: dict[int, set[int]] = {}
        for teacher_id, group_id in list(legacy_pairs) + list(program_pairs):
            groups_by_teacher_id.setdefault(teacher_id, set()).add(group_id)

        # Roster stays whole-group per Teaching Program's group, same as
        # `_group_analytics` — a student isn't split by subject.
        students_by_group = {
            row["group_id"]: row["count"]
            for row in Student.objects.filter(group_id__in=group_ids, is_active=True)
            .values("group_id")
            .annotate(count=Count("id"))
        }

        lessons_by_teacher = {
            row["eff_teacher"]: row
            for row in Lesson.objects.filter(group_id__in=group_ids, date__gte=self.start_date, date__lte=self.end_date)
            .annotate(eff_teacher=Coalesce("teacher_id", "group__teacher_id"))
            .values("eff_teacher")
            .annotate(total=Count("id"))
        }
        attendance_by_teacher = {
            row["eff_teacher"]: row
            for row in Attendance.objects.filter(
                lesson__group_id__in=group_ids, lesson__date__gte=self.start_date, lesson__date__lte=self.end_date
            )
            .annotate(eff_teacher=Coalesce("lesson__teacher_id", "lesson__group__teacher_id"))
            .values("eff_teacher")
            .annotate(total=Count("id"), attended=Count("id", filter=Q(status__in=_ATTENDED_STATUSES)))
        }
        homeworks_by_teacher = {
            row["eff_teacher"]: row["count"]
            for row in Homework.objects.filter(
                lesson__group_id__in=group_ids, lesson__date__gte=self.start_date, lesson__date__lte=self.end_date
            )
            .annotate(eff_teacher=Coalesce("lesson__teacher_id", "lesson__group__teacher_id"))
            .values("eff_teacher")
            .annotate(count=Count("id"))
        }
        results_by_teacher = {
            row["eff_teacher"]: row
            for row in HomeworkResult.objects.filter(
                homework__lesson__group_id__in=group_ids,
                homework__lesson__date__gte=self.start_date,
                homework__lesson__date__lte=self.end_date,
            )
            .annotate(eff_teacher=Coalesce("homework__lesson__teacher_id", "homework__lesson__group__teacher_id"))
            .values("eff_teacher")
            .annotate(completed=Count("id", filter=Q(status__in=_COMPLETED_HOMEWORK_STATUSES)), avg_score=Avg("score"))
        }

        rows = []
        for teacher in teachers:
            lessons = lessons_by_teacher.get(teacher.id, {})
            attendance = attendance_by_teacher.get(teacher.id, {})
            results = results_by_teacher.get(teacher.id, {})
            own_group_ids = groups_by_teacher_id.get(teacher.id, set())
            total_students = sum(students_by_group.get(gid, 0) for gid in own_group_ids)
            total_homeworks = homeworks_by_teacher.get(teacher.id, 0)
            completed_results = results.get("completed", 0)
            possible_results = total_homeworks * total_students

            rows.append(
                {
                    "id": teacher.id,
                    "name": str(teacher),
                    "groups": len(own_group_ids),
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

        # A student's row on one teacher's own dashboard must reflect only
        # that teacher's own Teaching Program (spec §39: the same student
        # can be PRESENT on one teacher's Lessons and ABSENT on another's,
        # in the very same Group) — never the whole group's combined figures.
        lesson_teacher_q = self._effective_teacher_q()
        lesson_via_lesson_q = self._effective_teacher_q("lesson__")
        result_teacher_q = self._effective_teacher_q("homework__lesson__")

        # "How many lessons/homeworks were possible" is a property of the
        # student's group + period (+ teacher, when scoped), shared by every
        # student in it — reuse one small per-group query rather than
        # repeating it per student.
        lesson_q = Q(group_id__in=group_ids, date__gte=self.start_date, date__lte=self.end_date)
        if lesson_teacher_q is not None:
            lesson_q &= lesson_teacher_q
        lessons_by_group = {
            row["group_id"]: row["total"]
            for row in Lesson.objects.filter(lesson_q).values("group_id").annotate(total=Count("id"))
        }

        homeworks_q = Q(
            lesson__group_id__in=group_ids, lesson__date__gte=self.start_date, lesson__date__lte=self.end_date
        )
        if lesson_via_lesson_q is not None:
            homeworks_q &= lesson_via_lesson_q
        homeworks_by_group = {
            row["lesson__group_id"]: row["count"]
            for row in Homework.objects.filter(homeworks_q).values("lesson__group_id").annotate(count=Count("id"))
        }

        attendance_q = Q(
            student_id__in=student_ids,
            lesson__group_id__in=group_ids,
            lesson__date__gte=self.start_date,
            lesson__date__lte=self.end_date,
        )
        if lesson_via_lesson_q is not None:
            attendance_q &= lesson_via_lesson_q
        attendance_by_student = {
            row["student_id"]: row
            for row in Attendance.objects.filter(attendance_q)
            .values("student_id")
            .annotate(total=Count("id"), attended=Count("id", filter=Q(status__in=_ATTENDED_STATUSES)))
        }

        results_q = Q(
            student_id__in=student_ids,
            homework__lesson__group_id__in=group_ids,
            homework__lesson__date__gte=self.start_date,
            homework__lesson__date__lte=self.end_date,
        )
        if result_teacher_q is not None:
            results_q &= result_teacher_q
        results_by_student = {
            row["student_id"]: row
            for row in HomeworkResult.objects.filter(results_q)
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
