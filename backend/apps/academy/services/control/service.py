"""ControlService — loads a period's lessons once and turns them into the
Control page: a summary, one row per (responsible trainer, group), and the
per-lesson checks behind every row.

Queries are fixed in number (lessons, active students, attendance, homework,
results), never one per lesson; every rule lives in `rules.py`.
"""
from __future__ import annotations

import dataclasses
import datetime as dt
from collections import defaultdict

from django.db.models import Q, QuerySet
from django.utils import timezone

from apps.users.models import Subject, Teacher

from apps.academy.models import Attendance, Group, Homework, HomeworkResult, Lesson, Student
from apps.academy.services.reports.filters import ReportFilters, period_options

from . import rules
from .rules import (
    HomeworkRef,
    LessonCheck,
    ResultRef,
    StudentRef,
    component_level,
    evaluate_lesson,
    percent,
)

UNASSIGNED = "none"


def _student_name(first: str, last: str) -> str:
    return f"{last} {first}".strip()


def _teacher_ref(teacher: Teacher | None) -> dict | None:
    if teacher is None:
        return None
    return {"id": teacher.id, "name": str(teacher), "is_active": teacher.is_active}


def _person(user) -> dict | None:
    if user is None:
        return None
    return {"id": user.id, "name": user.get_full_name() or user.username}


def _component(completed: int, total: int) -> dict:
    return {
        "completed": completed,
        "total": total,
        "percent": percent(completed, total),
        "level": component_level(completed, total),
    }


def _plural(count: int, one: str, few: str, many: str) -> str:
    if count % 10 == 1 and count % 100 != 11:
        return one
    if count % 10 in (2, 3, 4) and count % 100 not in (12, 13, 14):
        return few
    return many


def _lessons_word(count: int) -> str:
    return f"{count} {_plural(count, 'занятие', 'занятия', 'занятий')}"


@dataclasses.dataclass(frozen=True)
class ControlQuery:
    """ReportFilters (period/program/group/teacher/subject) plus the Control
    page's own `status` filter. `teacher_id` is already forced to the
    viewer's own profile for a Trainer (see views)."""

    filters: ReportFilters
    status: str | None = None
    now_time: dt.time | None = None

    @property
    def today(self) -> dt.date:
        return self.filters.today


class ControlService:
    def __init__(self, query: ControlQuery, *, restrict_teacher: Teacher | None = None):
        self.query = query
        self.filters = query.filters
        self.today = query.today
        self.now_time = query.now_time or timezone.localtime().time()
        # A Trainer's Control is always only their own lessons.
        self.restrict_teacher = restrict_teacher

    # ------------------------------------------------------------------
    # Lesson scope
    # ------------------------------------------------------------------
    @staticmethod
    def responsible_q(teacher_id: int, prefix: str = "") -> Q:
        """Lessons whose *responsible* trainer is `teacher_id` — the
        `Lesson.effective_teacher` rule (see LessonQuerySet.for_teacher)."""
        from apps.academy.services.trainer_history import taught_by_q

        return taught_by_q(teacher_id, prefix)

    def lessons_qs(self) -> QuerySet[Lesson]:
        return self.lessons_qs_for_range(self.filters.start, self.filters.end)

    def lessons_qs_for_range(self, start: dt.date, end: dt.date) -> QuerySet[Lesson]:
        f = self.filters
        qs = Lesson.objects.filter(date__gte=start, date__lte=end)
        if self.restrict_teacher is not None:
            qs = qs.filter(self.responsible_q(self.restrict_teacher.id))
        if f.teacher_id is not None:
            qs = qs.filter(self.responsible_q(f.teacher_id))
        if f.group_id is not None:
            qs = qs.filter(group_id=f.group_id)
        if f.course_id is not None:
            qs = qs.filter(group__course_id=f.course_id)
        if f.subject_id is not None:
            qs = qs.filter(subject_id=f.subject_id)
        return qs

    # ------------------------------------------------------------------
    # Loading + evaluation
    # ------------------------------------------------------------------
    def evaluate(self, lessons_qs: QuerySet[Lesson] | None = None) -> list[LessonCheck]:
        lessons_qs = self.lessons_qs() if lessons_qs is None else lessons_qs
        lessons = list(
            lessons_qs.select_related(
                "group", "subject", "teacher__user", "group_teacher__teacher__user", "completed_by",
            ).order_by("date", "start_time", "id")
        )
        if not lessons:
            return []
        lesson_ids = [lesson.id for lesson in lessons]
        group_ids = {lesson.group_id for lesson in lessons}

        students_by_group: dict[int, list[StudentRef]] = defaultdict(list)
        for row in (
            Student.objects.filter(group_id__in=group_ids, is_active=True)
            .order_by("last_name", "first_name", "id")
            .values("id", "first_name", "last_name", "group_id")
        ):
            students_by_group[row["group_id"]].append(
                StudentRef(row["id"], _student_name(row["first_name"], row["last_name"]))
            )

        attendance: dict[int, dict[int, dt.datetime]] = defaultdict(dict)
        for row in Attendance.objects.filter(lesson_id__in=lesson_ids).values(
            "lesson_id", "student_id", "updated_at"
        ):
            attendance[row["lesson_id"]][row["student_id"]] = row["updated_at"]

        homeworks: dict[int, list[HomeworkRef]] = defaultdict(list)
        homework_lesson: dict[int, int] = {}
        for row in Homework.objects.filter(lesson_id__in=lesson_ids).order_by("id").values(
            "id", "lesson_id", "deadline", "updated_at"
        ):
            homeworks[row["lesson_id"]].append(HomeworkRef(row["id"], row["deadline"], row["updated_at"]))
            homework_lesson[row["id"]] = row["lesson_id"]

        results: dict[int, list[ResultRef]] = defaultdict(list)
        if homework_lesson:
            for row in HomeworkResult.objects.filter(homework_id__in=list(homework_lesson)).values(
                "homework_id", "student_id", "status", "score", "updated_at"
            ):
                results[homework_lesson[row["homework_id"]]].append(
                    ResultRef(row["homework_id"], row["student_id"], row["status"], row["score"], row["updated_at"])
                )

        return [
            evaluate_lesson(
                lesson,
                today=self.today,
                now_time=self.now_time,
                students=students_by_group.get(lesson.group_id, []),
                attendance=attendance.get(lesson.id, {}),
                homeworks=homeworks.get(lesson.id, []),
                results=results.get(lesson.id, []),
            )
            for lesson in lessons
        ]

    # ------------------------------------------------------------------
    # Rows
    # ------------------------------------------------------------------
    @staticmethod
    def _row_key(check: LessonCheck) -> tuple:
        teacher = check.lesson.effective_teacher
        return (teacher.id if teacher else None, check.lesson.group_id)

    @staticmethod
    def aggregate(checks: list[LessonCheck]) -> dict:
        """Counts, levels, status and "what is left" for any set of lessons —
        one teacher×group row, or all of one teacher's lessons."""
        due = [c for c in checks if c.is_due]
        closed = sum(1 for c in due if c.closed)
        attendance = _component(sum(1 for c in due if c.attendance_counts and c.attendance_ok),
                                sum(1 for c in due if c.attendance_counts))
        homework = _component(sum(1 for c in due if c.homework_counts and c.homework_ok),
                              sum(1 for c in due if c.homework_counts))
        grades = _component(sum(1 for c in due if c.grades_counts and c.grades_ok),
                            sum(1 for c in due if c.grades_counts))
        grades["students_missing"] = sum(len(c.grades_missing) for c in due if c.grades_counts)
        upcoming = sum(1 for c in checks if c.state == rules.STATE_UPCOMING)
        cancelled = sum(1 for c in checks if c.state == rules.STATE_CANCELLED)

        status = rules.row_status(
            due=len(due), closed=closed, levels=[attendance["level"], homework["level"], grades["level"]]
        )
        if status == rules.STATUS_NO_DATA and upcoming:
            status = rules.STATUS_UPCOMING

        issues = []
        not_closed = len(due) - closed
        if not_closed:
            issues.append(f"Не закрыто: {_lessons_word(not_closed)}")
        if attendance["total"] - attendance["completed"]:
            issues.append(f"Посещаемость не отмечена: {_lessons_word(attendance['total'] - attendance['completed'])}")
        missing_hw = sum(1 for c in due if c.homework_state == rules.COMPONENT_MISSING)
        unchecked_hw = sum(1 for c in due if c.homework_state == rules.COMPONENT_UNCHECKED)
        if missing_hw:
            issues.append(f"ДЗ не выдано: {_lessons_word(missing_hw)}")
        if unchecked_hw:
            issues.append(f"ДЗ не проверено: {_lessons_word(unchecked_hw)}")
        if grades["students_missing"]:
            n = grades["students_missing"]
            issues.append(
                f"Без балла: {n} {_plural(n, 'оценка', 'оценки', 'оценок')} "
                f"на {_lessons_word(grades['total'] - grades['completed'])}"
            )

        stamps = [c.last_activity_at for c in checks if c.last_activity_at]
        attention_lessons = [c for c in due if c.status != rules.STATUS_OK]
        next_lesson = min(attention_lessons, key=lambda c: (c.lesson.date, c.lesson.start_time), default=None)
        return {
            "lessons": {
                **_component(closed, len(due)),
                "not_closed": not_closed,
                "upcoming": upcoming,
                "cancelled": cancelled,
            },
            "attendance": attendance,
            "homework": homework,
            "grades": grades,
            "status": status,
            "status_label": rules.STATUS_LABELS[status],
            "problem_lessons": len(attention_lessons),
            "issues": issues,
            "first_problem_lesson_id": next_lesson.lesson.id if next_lesson else None,
            "last_activity_at": max(stamps) if stamps else None,
        }

    def build_row(self, checks: list[LessonCheck]) -> dict:
        first = checks[0].lesson
        teacher = first.effective_teacher
        subjects = {}
        for c in checks:
            if c.lesson.subject_id and c.lesson.subject_id not in subjects:
                subjects[c.lesson.subject_id] = {"id": c.lesson.subject_id, "name": c.lesson.subject.name}
        return {
            "key": f"{teacher.id if teacher else UNASSIGNED}-{first.group_id}",
            "teacher": _teacher_ref(teacher),
            "group": {"id": first.group_id, "name": first.group.name},
            "subjects": list(subjects.values()),
            **self.aggregate(checks),
        }

    def rows(self, checks: list[LessonCheck]) -> list[dict]:
        grouped: dict[tuple, list[LessonCheck]] = defaultdict(list)
        for check in checks:
            grouped[self._row_key(check)].append(check)
        rows = [self.build_row(items) for items in grouped.values()]
        rows.sort(key=lambda r: (
            rules.STATUS_PRIORITY[r["status"]],
            -r["problem_lessons"],
            (r["teacher"] or {}).get("name", "~").lower(),
            r["group"]["name"].lower(),
        ))
        return rows

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    @staticmethod
    def summary(rows: list[dict]) -> dict:
        def total(component: str, field: str) -> int:
            return sum(r[component][field] for r in rows)

        status_counts = {key: 0 for key in rules.STATUS_PRIORITY if key != rules.STATUS_CANCELLED}
        for row in rows:
            status_counts[row["status"]] += 1
        return {
            "total_lessons": total("lessons", "total"),
            "completed_lessons": total("lessons", "completed"),
            "not_closed_lessons": total("lessons", "not_closed"),
            "upcoming_lessons": total("lessons", "upcoming"),
            "cancelled_lessons": total("lessons", "cancelled"),
            "attendance_completion": percent(total("attendance", "completed"), total("attendance", "total")),
            "homework_completion": percent(total("homework", "completed"), total("homework", "total")),
            "grade_completion": percent(total("grades", "completed"), total("grades", "total")),
            "students_without_grade": total("grades", "students_missing"),
            "attention_count": status_counts[rules.STATUS_ATTENTION] + status_counts[rules.STATUS_PROBLEM],
            "problem_lessons": sum(r["problem_lessons"] for r in rows),
            "rows_total": len(rows),
            "status_counts": status_counts,
        }

    def build(self) -> dict:
        rows = self.rows(self.evaluate())
        summary = self.summary(rows)
        if self.query.status:
            rows = [r for r in rows if r["status"] == self.query.status]
        return {"filters": self.filters_dict(), "summary": summary, "items": rows}

    def build_detail(self, *, group_id: int, teacher_id: int | None) -> dict | None:
        """One teacher×group row plus every lesson behind it, newest first.
        `teacher_id=None` is the row of lessons without a responsible trainer."""
        qs = self.lessons_qs().filter(group_id=group_id)
        if teacher_id is None:
            qs = qs.filter(teacher__isnull=True, group_teacher__isnull=True)
        else:
            qs = qs.filter(self.responsible_q(teacher_id))
        checks = self.evaluate(qs)
        if not checks:
            return None
        row = self.build_row(checks)
        lessons = sorted(checks, key=lambda c: (c.lesson.date, c.lesson.start_time), reverse=True)
        return {
            "filters": self.filters_dict(),
            "row": row,
            "lessons": [lesson_payload(c) for c in lessons],
        }

    # ------------------------------------------------------------------
    # Trainers — the Admin Panel's «Контроль тренеров»
    # ------------------------------------------------------------------
    def _has_scope_filters(self) -> bool:
        f = self.filters
        return any(v is not None for v in (f.group_id, f.course_id, f.subject_id))

    def _idle_teachers(self) -> list[Teacher]:
        """Trainers listed even without a lesson in the period (status «Нет
        данных») — every active trainer, unless the page is narrowed to a
        group/program/subject, where only trainers with lessons there count."""
        if self.restrict_teacher is not None:
            return [self.restrict_teacher]
        if self.filters.teacher_id is not None:
            return list(Teacher.objects.select_related("user").filter(id=self.filters.teacher_id))
        if self._has_scope_filters():
            return []
        return list(Teacher.objects.select_related("user").filter(is_active=True))

    def teacher_row(self, teacher: Teacher, checks: list[LessonCheck]) -> dict:
        by_group: dict[int, list[LessonCheck]] = defaultdict(list)
        for check in checks:
            by_group[check.lesson.group_id].append(check)
        groups = sorted(
            ({"id": items[0].lesson.group_id, "name": items[0].lesson.group.name} for items in by_group.values()),
            key=lambda g: g["name"].lower(),
        )
        aggregate = self.aggregate(checks) if checks else {
            **self.aggregate([]), "status": rules.STATUS_NO_DATA, "status_label": rules.STATUS_LABELS[rules.STATUS_NO_DATA],
        }
        return {
            "key": str(teacher.id),
            "teacher": _teacher_ref(teacher),
            "groups": groups,
            "groups_count": len(groups),
            **aggregate,
            "search": " ".join([str(teacher), *(g["name"] for g in groups)]).lower(),
        }

    SORT_KEYS = ("status", "name", "groups", "unfilled", "attendance", "homework", "grades")

    @classmethod
    def sort_teacher_rows(cls, rows: list[dict], sort: str) -> list[dict]:
        """`status` (default, problems first), `name`, `groups`, `unfilled`
        (lessons with gaps) or a component's completion percent; a leading
        «-» reverses. Rows with no data for a percent always sort last."""
        desc = sort.startswith("-")
        key = sort.lstrip("-")
        if key not in cls.SORT_KEYS:
            key, desc = "status", False

        def name(r):
            return r["teacher"]["name"].lower()

        if key == "status":
            ordered = sorted(rows, key=lambda r: (rules.STATUS_PRIORITY[r["status"]], -r["problem_lessons"], name(r)))
            return list(reversed(ordered)) if desc else ordered
        if key == "name":
            return sorted(rows, key=name, reverse=desc)
        if key in ("groups", "unfilled"):
            field = "groups_count" if key == "groups" else "problem_lessons"
            return sorted(rows, key=lambda r: (-r[field] if desc else r[field], name(r)))
        with_value = [r for r in rows if r[key]["percent"] is not None]
        without = [r for r in rows if r[key]["percent"] is None]
        with_value.sort(key=lambda r: (-r[key]["percent"] if desc else r[key]["percent"], name(r)))
        return with_value + sorted(without, key=name)

    def teacher_rows(self, checks: list[LessonCheck]) -> list[dict]:
        by_teacher: dict[int, list[LessonCheck]] = defaultdict(list)
        teachers: dict[int, Teacher] = {}
        for check in checks:
            teacher = check.lesson.effective_teacher
            if teacher is None:
                continue  # no responsible trainer — shown on the lesson-level Control page
            by_teacher[teacher.id].append(check)
            teachers[teacher.id] = teacher
        for teacher in self._idle_teachers():
            teachers.setdefault(teacher.id, teacher)
        return [self.teacher_row(teacher, by_teacher.get(tid, [])) for tid, teacher in teachers.items()]

    def today_summary(self) -> dict:
        """Today's lessons in the same trainer/group/subject scope, whatever
        the selected period — "Занятий сегодня / Закрыто / Не заполнено"."""
        qs = self.lessons_qs_for_range(self.today, self.today).exclude(status=Lesson.Status.CANCELLED)
        checks = self.evaluate(qs)
        return {
            "total": len(checks),
            "closed": sum(1 for c in checks if c.closed),
            "not_filled": sum(1 for c in checks if c.is_due and c.status in (rules.STATUS_ATTENTION, rules.STATUS_PROBLEM)),
            "upcoming": sum(1 for c in checks if c.state == rules.STATE_UPCOMING),
        }

    def build_teachers(self, *, sort: str = "status") -> dict:
        return self._teachers_from(self.evaluate(), sort)

    def _teachers_from(self, checks: list[LessonCheck], sort: str) -> dict:
        rows = self.teacher_rows(checks)
        counts = {key: 0 for key in rules.FILTERABLE_STATUSES}
        for row in rows:
            counts[row["status"]] += 1
        summary = {
            "teachers": len(rows),
            "ok": counts[rules.STATUS_OK],
            "attention": counts[rules.STATUS_ATTENTION],
            "problem": counts[rules.STATUS_PROBLEM],
            "no_data": counts[rules.STATUS_NO_DATA] + counts[rules.STATUS_UPCOMING],
            "status_counts": counts,
            "lessons": sum(r["lessons"]["total"] for r in rows),
            "problem_lessons": sum(r["problem_lessons"] for r in rows),
            "today": self.today_summary(),
        }
        if self.query.status:
            rows = [r for r in rows if r["status"] == self.query.status]
        return {"filters": self.filters_dict(), "summary": summary, "items": self.sort_teacher_rows(rows, sort)}

    def export_data(self, *, sort: str = "status") -> dict:
        """Everything the Excel/PDF export needs, for the listed trainers."""
        checks = self.evaluate()
        overview = self._teachers_from(checks, sort)
        teacher_ids = {row["teacher"]["id"] for row in overview["items"]}
        scoped = [c for c in checks if c.lesson.effective_teacher and c.lesson.effective_teacher.id in teacher_ids]
        problems = sorted(
            (c for c in scoped if c.is_due and c.status != rules.STATUS_OK),
            key=lambda c: (c.lesson.date, c.lesson.start_time),
            reverse=True,
        )
        return {
            "filters": self.filters,
            "summary": overview["summary"],
            "teachers": overview["items"],
            "groups": self.rows(scoped),
            "problems": [lesson_payload(c) for c in problems],
        }

    def build_teacher_detail(self, teacher: Teacher) -> dict:
        """One trainer: totals, one row per group, and every lesson that
        still needs something — newest first, each with its link target."""
        checks = self.evaluate(self.lessons_qs().filter(self.responsible_q(teacher.id)))
        row = self.teacher_row(teacher, checks)
        group_rows = sorted(
            self.rows(checks),
            key=lambda r: (rules.STATUS_PRIORITY[r["status"]], r["group"]["name"].lower()),
        )
        problems = sorted(
            (c for c in checks if c.is_due and c.status != rules.STATUS_OK),
            key=lambda c: (c.lesson.date, c.lesson.start_time),
            reverse=True,
        )
        upcoming = sorted(
            (c for c in checks if c.state == rules.STATE_UPCOMING),
            key=lambda c: (c.lesson.date, c.lesson.start_time),
        )
        return {
            "filters": self.filters_dict(),
            "row": row,
            "groups": group_rows,
            "problems": [lesson_payload(c) for c in problems],
            "upcoming": [lesson_payload(c) for c in upcoming],
        }

    def filters_dict(self) -> dict:
        return {**self.filters.as_dict(), "status": self.query.status}

    def options(self) -> dict:
        """Select options, scoped to what the viewer may see."""
        if self.restrict_teacher is not None:
            teacher = self.restrict_teacher
            own = Lesson.objects.filter(self.responsible_q(teacher.id))
            teachers = [{"id": teacher.id, "name": str(teacher)}]
            groups = Group.objects.filter(Q(id__in=own.values("group_id")) | Q(id__in=Group.objects.for_teacher(teacher)))
            subjects = Subject.objects.filter(id__in=own.values("subject_id"))
        else:
            teachers = [
                {"id": t.id, "name": str(t)}
                for t in Teacher.objects.select_related("user").order_by("user__first_name", "user__last_name")
            ]
            groups = Group.objects.all()
            subjects = Subject.objects.all()
        return {
            "periods": [{"key": key, "label": label} for key, label in period_options(self.today)],
            "teachers": teachers,
            "groups": list(groups.order_by("name").values("id", "name").distinct()),
            "subjects": list(subjects.order_by("name").values("id", "name").distinct()),
            "statuses": [{"key": key, "label": rules.STATUS_LABELS[key]} for key in rules.FILTERABLE_STATUSES],
        }


def lesson_payload(check: LessonCheck) -> dict:
    """One lesson's full check — what the drawer and the lesson view show."""
    lesson = check.lesson
    teacher = lesson.effective_teacher
    planned = lesson.group_teacher.teacher if lesson.group_teacher_id else None
    return {
        "id": lesson.id,
        "lesson_number": lesson.lesson_number,
        "date": lesson.date,
        "start_time": lesson.start_time,
        "end_time": lesson.end_time,
        "topic": lesson.topic,
        "subject": {"id": lesson.subject_id, "name": lesson.subject.name} if lesson.subject_id else None,
        "group": {"id": lesson.group_id, "name": lesson.group.name},
        "teacher": _teacher_ref(teacher),
        "planned_teacher": _teacher_ref(planned) if planned and teacher and planned.id != teacher.id else None,
        "state": check.state,
        "lesson_status": lesson.status,
        "lesson_status_label": lesson.get_status_display(),
        "closed": check.closed,
        "closed_at": lesson.completed_at,
        "closed_by": _person(lesson.completed_by),
        "status": check.status,
        "status_label": rules.STATUS_LABELS[check.status],
        "students_total": check.students_total,
        "attendance": {
            "state": check.attendance_state,
            "label": check.attendance_label,
            "marked": check.attendance_marked,
            "total": check.students_total,
            "missing_students": [{"id": s.id, "name": s.name} for s in check.attendance_missing],
        },
        "homework": {
            "state": check.homework_state,
            "label": check.homework_label,
            "id": check.homework_id,
            "given": check.homework_id is not None,
            "not_required": lesson.homework_not_required,
            "deadline": check.homework_deadline,
            "pending_check": check.pending_check,
        },
        "grades": {
            "state": check.grades_state,
            "label": check.grades_label,
            "given": check.grades_given,
            "total": check.grades_required,
            "missing": len(check.grades_missing),
            "missing_students": [{"id": s.id, "name": s.name} for s in check.grades_missing],
        },
        "problems": check.problems,
        "notes": check.notes,
        "last_activity_at": check.last_activity_at,
    }


def lesson_check(lesson: Lesson, *, today: dt.date | None = None, now_time: dt.time | None = None) -> dict:
    """A single lesson's check, independent of any period filter."""
    today = today or timezone.localdate()
    service = ControlService(ControlQuery(filters=ReportFilters.default(today=today), now_time=now_time))
    checks = service.evaluate(Lesson.objects.filter(pk=lesson.pk))
    return lesson_payload(checks[0])
