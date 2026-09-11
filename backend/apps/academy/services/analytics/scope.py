"""AnalyticsScope: a date range plus teacher/group/course/subject filters,
and the base queryset builders every analytics module composes from.

Keeping the filtering logic in exactly one place is what keeps every
domain module (students/teachers/groups/lessons/attendance/homework) and
insights.py in lockstep with each other and with the write-side permission
model (see apps.academy.permissions, models.LessonQuerySet.for_teacher) —
a Teacher's dashboard must see only their own Teaching Assignment's data,
even inside a Group they share with other teachers (spec: "Teaching
Assignment isolation").
"""
from __future__ import annotations

import dataclasses

from django.db.models import Q, QuerySet

from apps.users.models import Teacher

from apps.academy.models import Group, Lesson, Student
from .period import DateRange


@dataclasses.dataclass(frozen=True)
class AnalyticsScope:
    date_range: DateRange
    teacher_id: int | None = None
    group_id: int | None = None
    course_id: int | None = None
    subject_id: int | None = None

    def with_range(self, date_range: DateRange) -> "AnalyticsScope":
        return dataclasses.replace(self, date_range=date_range)

    # ------------------------------------------------------------------
    # Base querysets. `teacher_id`/`course_id` narrow which Groups/Teachers
    # are in scope at all (a Teaching Program stake, or a course match);
    # `subject_id` narrows to Groups/Teachers running that Subject.
    # Lesson-level figures are narrowed further, to only the Lessons this
    # teacher actually gives (see `_effective_teacher_q`) — a Group's other
    # Teaching Programs (models.GroupTeacher) belong to other teachers.
    # ------------------------------------------------------------------

    def groups_qs(self) -> QuerySet[Group]:
        # Deliberately no `subject_id` filter here: a Group's GroupTeacher
        # rows can have `subject=None` (the legacy/shared-course-plan case —
        # see models.GroupTeacher/services.lesson_generator), so filtering
        # Groups by a declared Teaching Program subject would wrongly drop
        # a group whose actual Lessons *do* cover that subject via the
        # shared course plan. Subject scoping happens at the Lesson level
        # instead (see `lessons_qs`/`lesson_teacher_q` callers), which reads
        # each Lesson's own `subject` — the real source of truth.
        qs = Group.objects.all()
        if self.teacher_id is not None:
            qs = qs.filter(teachers__teacher_id=self.teacher_id, teachers__is_active=True)
        if self.group_id is not None:
            qs = qs.filter(id=self.group_id)
        if self.course_id is not None:
            qs = qs.filter(course_id=self.course_id)
        if self.teacher_id is not None:
            qs = qs.distinct()
        return qs

    def teachers_qs(self) -> QuerySet[Teacher]:
        # No `subject_id` filter — same reasoning as `groups_qs`.
        qs = Teacher.objects.all()
        if self.teacher_id is not None:
            qs = qs.filter(id=self.teacher_id)
        if self.group_id is not None:
            qs = qs.filter(group_assignments__group_id=self.group_id, group_assignments__is_active=True)
        if self.course_id is not None:
            qs = qs.filter(group_assignments__group__course_id=self.course_id, group_assignments__is_active=True)
        if self.group_id is not None or self.course_id is not None:
            qs = qs.distinct()
        return qs

    def students_qs(self) -> QuerySet[Student]:
        return Student.objects.filter(group__in=self.groups_qs())

    def _effective_teacher_q(self, prefix: str = "") -> Q | None:
        """Q restricting to rows whose Lesson's *effective* teacher (its own
        `teacher`, or — for lessons with none — its GroupTeacher's own
        `teacher`; see Lesson.effective_teacher) is `self.teacher_id`, for a
        Lesson reached via `prefix` field lookups (e.g. "lesson__" from
        Attendance, "homework__lesson__" from HomeworkResult). Never the
        legacy `Group.teacher` field — every Lesson's `group_teacher` FK
        already covers that case (see the 0006 backfill migration). None
        when no teacher filter is active.
        """
        if self.teacher_id is None:
            return None
        return Q(**{f"{prefix}teacher_id": self.teacher_id}) | Q(
            **{f"{prefix}teacher__isnull": True, f"{prefix}group_teacher__teacher_id": self.teacher_id}
        )

    def lessons_qs(self, *, date_range: DateRange | None = None) -> QuerySet[Lesson]:
        rng = date_range or self.date_range
        qs = Lesson.objects.filter(group__in=self.groups_qs(), date__gte=rng.start, date__lte=rng.end)
        teacher_q = self._effective_teacher_q()
        if teacher_q is not None:
            qs = qs.filter(teacher_q)
        if self.subject_id is not None:
            qs = qs.filter(subject_id=self.subject_id)
        return qs

    def lesson_teacher_q(self, prefix: str) -> Q | None:
        """Same as `_effective_teacher_q`, exposed for other modules that
        reach Lesson through a relation (Attendance -> lesson, HomeworkResult
        -> homework -> lesson) rather than querying Lesson directly."""
        return self._effective_teacher_q(prefix)
