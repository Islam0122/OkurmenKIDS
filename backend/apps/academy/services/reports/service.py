"""Reports (Отчёты) — Overview, Groups, Subjects, Teachers, and their detail
pages.

Nothing here is stored: every figure is computed on demand from Student/
StudentStatusEvent/Group/GroupTeacher/Lesson/Attendance/Homework/
HomeworkResult, with the same definitions the rest of the app already
uses (see services.monthly_report, services.academy_monthly_report,
services.analytics). Filtering goes through `analytics.scope.
AnalyticsScope` — the one place group/teacher/course/subject scoping and
the effective-teacher rule (Lesson.teacher, else its GroupTeacher's
teacher) already live.

Performance: every breakdown (per group, per teacher, per student) is a
single grouped aggregate query per table — the number of queries does not
grow with the number of groups, teachers or students (see
`_period_stats`). Nothing loads individual Attendance/HomeworkResult rows
into Python.

Definitions:
* students total/active — the *current* roster (Student.group /
  Student.status); there is no historical roster to rewind to;
* left — distinct students with a deactivation StudentStatusEvent dated in
  the period, attributed to the group they left from (event.group);
* returned — distinct students with a reactivation/continuation event in
  the period; new — students whose record was created in the period (the
  Analytics Dashboard's own definition);
* groups in a report — active/paused groups, plus any other group that had
  lessons in the period (a group finished two years ago with no lessons in
  the period is not part of this period's picture); an explicitly selected
  group is always included;
* subjects in a report — every active Subject, plus any subject that had
  lessons in the period; with a program/group/teacher/subject filter, only
  the subjects actually taught (lessons) or assigned (GroupTeacher) inside
  that scope. A subject's figures are its own lessons (Lesson.subject) —
  summed across every group that runs it; a teacher who runs two subjects
  counts towards each of them separately;
* KPI — services.kpi_engine, the single source of truth for every KPI.
"""
from __future__ import annotations

import dataclasses
from collections import defaultdict

from django.db.models import Avg, Count, Q
from django.db.models.functions import Coalesce

from apps.users.models import Subject, Teacher

from apps.academy.models import Attendance, Course, Group, GroupTeacher, Homework, HomeworkResult, Lesson, Student, StudentStatusEvent
from .filters import ReportFilters
from apps.academy.services.kpi_engine import KPICounts, KPIEngine, KPIResult, from_counts

from .kpi import kpi_weights, rate, weights_description

_ATTENDED = (Attendance.Status.PRESENT, Attendance.Status.LATE)
_SUBMITTED = (HomeworkResult.Status.SUBMITTED, HomeworkResult.Status.CHECKED, HomeworkResult.Status.LATE)
_RETURN_EVENTS = (StudentStatusEvent.EventType.REACTIVATED, StudentStatusEvent.EventType.CONTINUED)
_RELEVANT_GROUP_STATUSES = (Group.Status.ACTIVE, Group.Status.PAUSED)

NO_TEACHER_LABEL = "Не назначен"


# ---------------------------------------------------------------------------
# Period statistics (lessons / attendance / homework) — one accumulator per
# key (a group, a teacher, a student, or the whole scope).
# ---------------------------------------------------------------------------

@dataclasses.dataclass
class PeriodStats:
    lessons_total: int = 0
    lessons_held: int = 0
    lessons_cancelled: int = 0
    lessons_due: int = 0
    attendance_total: int = 0
    attendance_present: int = 0
    attendance_late: int = 0
    attendance_absent: int = 0
    attendance_excused: int = 0
    homework_assigned: int = 0
    homework_results: int = 0
    homework_submitted: int = 0
    homework_checked: int = 0
    homework_not_submitted: int = 0
    homework_late: int = 0
    avg_score: float | None = None

    @property
    def attendance_rate(self) -> float | None:
        return rate(self.attendance_present + self.attendance_late, self.attendance_total)

    @property
    def absence_rate(self) -> float | None:
        return rate(self.attendance_absent + self.attendance_excused, self.attendance_total)

    @property
    def homework_rate(self) -> float | None:
        return rate(self.homework_submitted, self.homework_results)

    @property
    def activity_rate(self) -> float | None:
        # Held lessons out of the lessons already due — a lesson later in
        # the period that simply hasn't happened yet is not "not held".
        return rate(self.lessons_held, self.lessons_due)

    @property
    def progress_rate(self) -> float | None:
        return round(self.avg_score / 10 * 100, 1) if self.avg_score is not None else None

    @property
    def has_data(self) -> bool:
        return bool(self.lessons_total or self.attendance_total or self.homework_results)

    def kpi_result(self, weights: dict | None = None) -> KPIResult:
        """This row's KPI through the one engine formula (exact values in,
        rounded once at the end)."""
        return from_counts(
            KPICounts(
                attendance_total=self.attendance_total,
                attendance_attended=self.attendance_present + self.attendance_late,
                homework_results=self.homework_results,
                homework_submitted=self.homework_submitted,
                lessons_due=self.lessons_due,
                lessons_held=self.lessons_held,
                avg_score=self.avg_score,
            ),
            weights,
        )

    def kpi(self, weights: dict | None = None) -> dict:
        result = self.kpi_result(weights)
        return {"total": result.total, "status": result.status}

    def as_dict(self, weights: dict | None = None) -> dict:
        return {
            "lessons": {
                "total": self.lessons_total,
                "held": self.lessons_held,
                "cancelled": self.lessons_cancelled,
                "due": self.lessons_due,
            },
            "attendance": {
                "total": self.attendance_total,
                "present": self.attendance_present,
                "late": self.attendance_late,
                "absent": self.attendance_absent,
                "excused": self.attendance_excused,
                "rate": self.attendance_rate,
                "absence_rate": self.absence_rate,
            },
            "homework": {
                "assigned": self.homework_assigned,
                "results": self.homework_results,
                "submitted": self.homework_submitted,
                "not_submitted": self.homework_not_submitted,
                "checked": self.homework_checked,
                "late": self.homework_late,
                "completion_rate": self.homework_rate,
                "average_score": round(self.avg_score, 1) if self.avg_score is not None else None,
            },
            **_contract(self.kpi_result(weights)),
            "has_data": self.has_data,
        }


def _contract(result: KPIResult) -> dict:
    contract = result.as_contract()
    return {"metrics": contract["metrics"], "kpi": contract["kpi"]}


def _eff_teacher(prefix: str = ""):
    """Lesson.effective_teacher as a DB expression (see models.Lesson)."""
    return Coalesce(f"{prefix}teacher_id", f"{prefix}group_teacher__teacher_id")


_KEYS = {
    # key -> (lesson prefix path used by each table)
    "group": {"lesson": "group_id", "attendance": "lesson__group_id", "homework": "lesson__group_id",
              "result": "homework__lesson__group_id"},
    "teacher": {"lesson": _eff_teacher(), "attendance": _eff_teacher("lesson__"), "homework": _eff_teacher("lesson__"),
                "result": _eff_teacher("homework__lesson__")},
    "student": {"attendance": "student_id", "result": "student_id"},
    "subject": {"lesson": "subject_id", "attendance": "lesson__subject_id", "homework": "lesson__subject_id",
                "result": "homework__lesson__subject_id"},
}


def _grouped(qs, key_expr, **aggregates) -> dict:
    """{key: {aggregate: value}} in one query. `.order_by()` clears model
    default ordering, which would otherwise leak into GROUP BY."""
    if key_expr is None:
        return {None: qs.aggregate(**aggregates)}
    if isinstance(key_expr, str):
        rows = qs.order_by().values(key_expr).annotate(**aggregates)
        return {row[key_expr]: row for row in rows}
    rows = qs.order_by().annotate(_key=key_expr).values("_key").annotate(**aggregates)
    return {row["_key"]: row for row in rows}


def _period_stats(filters: ReportFilters, key: str | None, *, lessons=None, only_keys=None) -> dict:
    """PeriodStats per `key` ("group"/"teacher"/"student"/"subject", or None for one
    scope-wide total) over the lessons in scope — 4 queries (3 for
    students), whatever the number of keys."""
    lessons = lessons if lessons is not None else filters.scope().lessons_qs()
    paths = _KEYS.get(key, {}) if key else {}
    stats: dict = defaultdict(PeriodStats)

    def keep(k) -> bool:
        return only_keys is None or k in only_keys

    if key != "student":
        for k, row in _grouped(
            lessons, paths.get("lesson"),
            total=Count("id"),
            held=Count("id", filter=Q(status=Lesson.Status.COMPLETED)),
            cancelled=Count("id", filter=Q(status=Lesson.Status.CANCELLED)),
            due=Count("id", filter=Q(date__lte=filters.today)),
        ).items():
            if keep(k):
                s = stats[k]
                s.lessons_total, s.lessons_held = row["total"] or 0, row["held"] or 0
                s.lessons_cancelled, s.lessons_due = row["cancelled"] or 0, row["due"] or 0

        for k, row in _grouped(Homework.objects.filter(lesson__in=lessons), paths.get("homework"), n=Count("id")).items():
            if keep(k):
                stats[k].homework_assigned = row["n"] or 0

    attendance_qs = Attendance.objects.filter(lesson__in=lessons)
    results_qs = HomeworkResult.objects.filter(homework__lesson__in=lessons)
    if key == "student" and only_keys is not None:
        attendance_qs = attendance_qs.filter(student_id__in=only_keys)
        results_qs = results_qs.filter(student_id__in=only_keys)

    for k, row in _grouped(
        attendance_qs, paths.get("attendance"),
        total=Count("id"),
        present=Count("id", filter=Q(status=Attendance.Status.PRESENT)),
        late=Count("id", filter=Q(status=Attendance.Status.LATE)),
        absent=Count("id", filter=Q(status=Attendance.Status.ABSENT)),
        excused=Count("id", filter=Q(status=Attendance.Status.EXCUSED)),
    ).items():
        if keep(k):
            s = stats[k]
            s.attendance_total, s.attendance_present = row["total"] or 0, row["present"] or 0
            s.attendance_late, s.attendance_absent = row["late"] or 0, row["absent"] or 0
            s.attendance_excused = row["excused"] or 0

    for k, row in _grouped(
        results_qs, paths.get("result"),
        total=Count("id"),
        submitted=Count("id", filter=Q(status__in=_SUBMITTED)),
        checked=Count("id", filter=Q(status=HomeworkResult.Status.CHECKED)),
        not_submitted=Count("id", filter=Q(status=HomeworkResult.Status.NOT_SUBMITTED)),
        late=Count("id", filter=Q(status=HomeworkResult.Status.LATE)),
        avg_score=Avg("score"),
    ).items():
        if keep(k):
            s = stats[k]
            s.homework_results, s.homework_submitted = row["total"] or 0, row["submitted"] or 0
            s.homework_checked, s.homework_not_submitted = row["checked"] or 0, row["not_submitted"] or 0
            s.homework_late, s.avg_score = row["late"] or 0, row["avg_score"]

    return stats


# ---------------------------------------------------------------------------
# Which groups / teachers a report covers
# ---------------------------------------------------------------------------

def report_group_ids(filters: ReportFilters) -> list[int]:
    scope = filters.scope()
    period_group_ids = scope.lessons_qs().values("group_id")
    qs = scope.groups_qs()
    if filters.group_id is None:
        qs = qs.filter(Q(status__in=_RELEVANT_GROUP_STATUSES) | Q(id__in=period_group_ids))
    if filters.subject_id is not None:
        qs = qs.filter(
            Q(teachers__subject_id=filters.subject_id, teachers__is_active=True) | Q(id__in=period_group_ids)
        )
    return list(qs.order_by().values_list("id", flat=True).distinct())


def _has_scope_filters(filters: ReportFilters) -> bool:
    return any(v is not None for v in (filters.course_id, filters.group_id, filters.teacher_id, filters.subject_id))


def report_teacher_ids(filters: ReportFilters, group_ids: list[int]) -> list[int]:
    scope = filters.scope()
    lesson_teacher_ids = {
        tid for tid in scope.lessons_qs().order_by().annotate(_t=_eff_teacher()).values_list("_t", flat=True).distinct()
        if tid is not None
    }
    assigned_ids = set(
        GroupTeacher.objects.filter(group_id__in=group_ids, is_active=True)
        .filter(**({"subject_id": filters.subject_id} if filters.subject_id else {}))
        .values_list("teacher_id", flat=True)
    )
    qs = scope.teachers_qs()
    if _has_scope_filters(filters):
        qs = qs.filter(id__in=lesson_teacher_ids | assigned_ids)
    else:
        # Unfiltered: every active trainer (including one with no groups
        # yet), plus anyone who actually taught in the period.
        qs = qs.filter(Q(is_active=True) | Q(id__in=lesson_teacher_ids))
    return list(qs.order_by().values_list("id", flat=True).distinct())


# ---------------------------------------------------------------------------
# Student movement per group
# ---------------------------------------------------------------------------

def _enrolled_in_period_q(filters: ReportFilters) -> Q:
    """"New student" = the record was created in the period — the same
    definition the Analytics Dashboard and the Academy Monthly Report use
    (services.analytics.students), so the three never disagree."""
    return Q(created_at__date__gte=filters.start, created_at__date__lte=filters.end)


def _student_counts_by_group(filters: ReportFilters, group_ids) -> dict[int, dict]:
    rows = (
        Student.objects.filter(group_id__in=group_ids).order_by().values("group_id")
        .annotate(
            total=Count("id"),
            active=Count("id", filter=Q(status=Student.Status.ACTIVE)),
            new=Count("id", filter=_enrolled_in_period_q(filters)),
        )
    )
    return {row["group_id"]: row for row in rows}


def _event_pairs(filters: ReportFilters, event_types, group_ids=None) -> set[tuple[int | None, int]]:
    """Distinct (group_id, student_id) pairs of events in the period — a
    small set (only students whose status actually changed)."""
    qs = StudentStatusEvent.objects.filter(
        event_type__in=event_types, event_date__gte=filters.start, event_date__lte=filters.end
    )
    if group_ids is not None:
        qs = qs.filter(group_id__in=group_ids)
    return set(qs.order_by().values_list("group_id", "student_id").distinct())


def _students_per_group(pairs) -> dict[int | None, set]:
    by_group: dict = defaultdict(set)
    for group_id, student_id in pairs:
        by_group[group_id].add(student_id)
    return by_group


# ---------------------------------------------------------------------------
# Groups
# ---------------------------------------------------------------------------

def _subject_assignment_q(subject_id: int) -> Q:
    """Teaching Programs (GroupTeacher) that cover `subject_id`: its own, plus
    legacy subject-less ones — those run the group's whole shared course plan
    (see models.GroupTeacher), so they cover every subject in it."""
    return Q(subject_id=subject_id) | Q(subject__isnull=True)


def _group_programs(group_ids, subject_id: int | None = None) -> dict[int, list[GroupTeacher]]:
    """Active Teaching Programs per group — only the ones covering
    `subject_id` when the report is filtered by a subject (a group's English
    trainer is not part of its Python figures)."""
    programs = defaultdict(list)
    qs = GroupTeacher.objects.filter(group_id__in=group_ids, is_active=True)
    if subject_id is not None:
        qs = qs.filter(_subject_assignment_q(subject_id))
    for gt in (
        qs
        .select_related("teacher__user", "subject")
        .order_by("group_id", "subject__name", "id")
    ):
        programs[gt.group_id].append(gt)
    return programs


def _unique(items) -> list:
    seen = []
    for item in items:
        if item not in seen:
            seen.append(item)
    return seen


def _group_row(group: Group, programs, counts: dict, left: set, returned: set, stats: PeriodStats, weights) -> dict:
    teachers = _unique([(gt.teacher_id, str(gt.teacher)) for gt in programs])
    subjects = _unique([gt.subject.name for gt in programs if gt.subject_id])
    detail = stats.as_dict(weights)
    kpi = detail["kpi"]
    return {
        "id": group.id,
        "name": group.name,
        "program": group.course.name,
        "program_id": group.course_id,
        "status": group.status,
        "status_display": group.get_status_display(),
        "start_date": group.start_date,
        "teachers": [{"id": tid, "name": name} for tid, name in teachers],
        "teacher_names": ", ".join(name for _tid, name in teachers) or NO_TEACHER_LABEL,
        "has_teacher": bool(teachers),
        "subjects": subjects,
        "students": {
            "total": counts.get("total", 0),
            "active": counts.get("active", 0),
            "left": len(left),
            "new": counts.get("new", 0),
            "returned": len(returned),
        },
        "lessons": detail["lessons"],
        "attendance": detail["attendance"],
        "homework": detail["homework"],
        "attendance_rate": stats.attendance_rate,
        "homework_rate": stats.homework_rate,
        "activity_rate": stats.activity_rate,
        "progress_rate": stats.progress_rate,
        "kpi": kpi["total"],
        "kpi_level": kpi["status"],
        "has_data": stats.has_data,
    }


def build_group_rows(filters: ReportFilters, group_ids: list[int] | None = None) -> list[dict]:
    group_ids = report_group_ids(filters) if group_ids is None else group_ids
    if not group_ids:
        return []
    weights = kpi_weights()
    groups = Group.objects.filter(id__in=group_ids).select_related("course").order_by("name")
    programs = _group_programs(group_ids, filters.subject_id)
    counts = _student_counts_by_group(filters, group_ids)
    left = _students_per_group(_event_pairs(filters, [StudentStatusEvent.EventType.DEACTIVATED], group_ids))
    returned = _students_per_group(_event_pairs(filters, _RETURN_EVENTS, group_ids))
    stats = _period_stats(filters, "group", only_keys=set(group_ids))
    return [
        _group_row(g, programs.get(g.id, []), counts.get(g.id, {}), left.get(g.id, set()),
                   returned.get(g.id, set()), stats.get(g.id, PeriodStats()), weights)
        for g in groups
    ]


# ---------------------------------------------------------------------------
# Teachers
# ---------------------------------------------------------------------------

def build_teacher_rows(filters: ReportFilters, group_ids: list[int] | None = None, *, group_rows=None) -> list[dict]:
    group_ids = report_group_ids(filters) if group_ids is None else group_ids
    teacher_ids = report_teacher_ids(filters, group_ids)
    if not teacher_ids:
        return []
    weights = kpi_weights()
    teachers = (
        Teacher.objects.filter(id__in=teacher_ids).select_related("user").prefetch_related("subjects")
        .order_by("user__first_name", "user__last_name")
    )

    # teacher -> groups: active assignments within the report's groups,
    # plus any group they actually taught in during the period.
    teacher_groups: dict[int, set] = defaultdict(set)
    teacher_subjects: dict[int, set] = defaultdict(set)
    assignments = GroupTeacher.objects.filter(teacher_id__in=teacher_ids, group_id__in=group_ids, is_active=True)
    if filters.subject_id is not None:
        # Filtered by a subject: only the groups where the teacher runs it.
        assignments = assignments.filter(_subject_assignment_q(filters.subject_id))
    for gt in assignments.values("teacher_id", "group_id", "subject__name"):
        teacher_groups[gt["teacher_id"]].add(gt["group_id"])
        if gt["subject__name"]:
            teacher_subjects[gt["teacher_id"]].add(gt["subject__name"])
    lessons = filters.scope().lessons_qs()
    for row in (
        lessons.order_by().annotate(_t=_eff_teacher()).filter(_t__in=teacher_ids)
        .values("_t", "group_id", "subject__name").distinct()
    ):
        teacher_groups[row["_t"]].add(row["group_id"])
        if row["subject__name"]:
            teacher_subjects[row["_t"]].add(row["subject__name"])

    all_group_ids = set().union(*teacher_groups.values()) if teacher_groups else set()
    counts = _student_counts_by_group(filters, all_group_ids)
    left_pairs = _event_pairs(filters, [StudentStatusEvent.EventType.DEACTIVATED], all_group_ids)
    left_by_group = _students_per_group(left_pairs)
    names = dict(Group.objects.filter(id__in=all_group_ids).values_list("id", "name"))
    stats = _period_stats(filters, "teacher", lessons=lessons, only_keys=set(teacher_ids))
    group_kpi = {row["id"]: row for row in (group_rows or [])}

    rows = []
    for teacher in teachers:
        gids = sorted(teacher_groups.get(teacher.id, ()), key=lambda gid: names.get(gid, ""))
        subjects = sorted(teacher_subjects.get(teacher.id, ())) or sorted(s.name for s in teacher.subjects.all())
        s = stats.get(teacher.id, PeriodStats())
        kpi = s.kpi(weights)
        left_students = set().union(*(left_by_group.get(gid, set()) for gid in gids)) if gids else set()
        rows.append(
            {
                "id": teacher.id,
                "name": str(teacher),
                "position": teacher.position,
                "is_active": teacher.is_active,
                "groups": [
                    {"id": gid, "name": names.get(gid, "—"), "kpi": group_kpi.get(gid, {}).get("kpi")}
                    for gid in gids
                ],
                "groups_count": len(gids),
                "subjects": subjects,
                "students": {
                    # A student belongs to exactly one group, so summing the
                    # teacher's groups' rosters counts each student once.
                    "total": sum(counts.get(gid, {}).get("total", 0) for gid in gids),
                    "active": sum(counts.get(gid, {}).get("active", 0) for gid in gids),
                    "left": len(left_students),
                },
                "lessons": {"total": s.lessons_total, "held": s.lessons_held},
                "attendance_rate": s.attendance_rate,
                "homework_rate": s.homework_rate,
                "activity_rate": s.activity_rate,
                "progress_rate": s.progress_rate,
                "kpi": kpi["total"],
                "kpi_level": kpi["status"],
                "has_data": s.has_data,
            }
        )
    return rows


# ---------------------------------------------------------------------------
# Subjects
# ---------------------------------------------------------------------------

def report_subject_ids(filters: ReportFilters, group_ids: list[int]) -> list[int]:
    """Which subjects a report covers (see the module docstring). Never a
    hard-coded list — always the real Subject rows."""
    if filters.subject_id is not None:
        # An explicitly selected subject is always shown, data or not.
        return list(Subject.objects.filter(id=filters.subject_id).values_list("id", flat=True))
    lesson_subject_ids = set(
        filters.scope().lessons_qs().order_by().exclude(subject_id=None)
        .values_list("subject_id", flat=True).distinct()
    )
    qs = Subject.objects.all()
    if _has_scope_filters(filters):
        assignments = GroupTeacher.objects.filter(group_id__in=group_ids, is_active=True, subject__isnull=False)
        if filters.teacher_id is not None:
            assignments = assignments.filter(teacher_id=filters.teacher_id)
        assigned_ids = set(assignments.values_list("subject_id", flat=True))
        qs = qs.filter(id__in=lesson_subject_ids | assigned_ids)
    else:
        # Unfiltered: every active subject (including one nobody runs yet),
        # plus any subject actually taught in the period.
        qs = qs.filter(Q(is_active=True) | Q(id__in=lesson_subject_ids))
    return list(qs.order_by().values_list("id", flat=True).distinct())


def build_subject_rows(filters: ReportFilters, group_ids: list[int] | None = None) -> list[dict]:
    """One row per subject. Figures are the subject's own lessons in scope
    (Lesson.subject), summed across every group that runs it, through the
    same `_period_stats` aggregation and KPI engine as groups and teachers.

    groups/teachers of a subject: its active Teaching Programs (GroupTeacher
    with that subject) within the report's groups, plus any group/teacher
    that actually gave a lesson of it in the period. Students — the current
    roster of those groups (a student belongs to exactly one group, so the
    sum counts each student once)."""
    group_ids = report_group_ids(filters) if group_ids is None else group_ids
    subject_ids = report_subject_ids(filters, group_ids)
    if not subject_ids:
        return []
    weights = kpi_weights()
    lessons = filters.scope().lessons_qs()

    subject_groups: dict[int, set] = defaultdict(set)
    subject_teachers: dict[int, set] = defaultdict(set)
    assignments = GroupTeacher.objects.filter(group_id__in=group_ids, subject_id__in=subject_ids, is_active=True)
    if filters.teacher_id is not None:
        assignments = assignments.filter(teacher_id=filters.teacher_id)
    for gt in assignments.values("subject_id", "group_id", "teacher_id"):
        subject_groups[gt["subject_id"]].add(gt["group_id"])
        subject_teachers[gt["subject_id"]].add(gt["teacher_id"])
    for row in (
        lessons.order_by().filter(subject_id__in=subject_ids).annotate(_t=_eff_teacher())
        .values("subject_id", "group_id", "_t").distinct()
    ):
        subject_groups[row["subject_id"]].add(row["group_id"])
        if row["_t"] is not None:
            subject_teachers[row["subject_id"]].add(row["_t"])

    all_group_ids = set().union(*subject_groups.values()) if subject_groups else set()
    all_teacher_ids = set().union(*subject_teachers.values()) if subject_teachers else set()
    group_names = dict(Group.objects.filter(id__in=all_group_ids).values_list("id", "name"))
    teacher_names = {
        t.id: str(t) for t in Teacher.objects.filter(id__in=all_teacher_ids).select_related("user")
    }
    counts = _student_counts_by_group(filters, all_group_ids)
    stats = _period_stats(filters, "subject", lessons=lessons, only_keys=set(subject_ids))

    rows = []
    for subject in Subject.objects.filter(id__in=subject_ids).order_by("name"):
        gids = sorted(subject_groups.get(subject.id, ()), key=lambda gid: group_names.get(gid, ""))
        tids = sorted(subject_teachers.get(subject.id, ()), key=lambda tid: teacher_names.get(tid, ""))
        s = stats.get(subject.id, PeriodStats())
        rows.append(
            {
                "id": subject.id,
                "name": subject.name,
                "is_active": subject.is_active,
                "groups": [{"id": gid, "name": group_names.get(gid, "—")} for gid in gids],
                "groups_count": len(gids),
                "teachers": [{"id": tid, "name": teacher_names.get(tid, NO_TEACHER_LABEL)} for tid in tids],
                "teachers_count": len(tids),
                "teacher_names": ", ".join(teacher_names.get(tid, "") for tid in tids) or NO_TEACHER_LABEL,
                "students": {
                    "total": sum(counts.get(gid, {}).get("total", 0) for gid in gids),
                    "active": sum(counts.get(gid, {}).get("active", 0) for gid in gids),
                },
                "average_score": round(s.avg_score, 1) if s.avg_score is not None else None,
                **_rates(s, weights),
                # Overrides `_rates`' short {total, held}: the subject table
                # also shows "held of due" and cancellations.
                "lessons": {
                    "total": s.lessons_total,
                    "held": s.lessons_held,
                    "due": s.lessons_due,
                    "cancelled": s.lessons_cancelled,
                },
            }
        )
    return rows


def unassigned_subject_lessons(filters: ReportFilters) -> int:
    """Lessons in scope with no subject set — they count towards groups,
    teachers and the overall KPI, but belong to no row of the subjects table
    (shown as a footnote, so the tables still reconcile)."""
    if filters.subject_id is not None:
        return 0
    return filters.scope().lessons_qs().filter(subject__isnull=True).count()


def subject_summary(subject_rows: list[dict]) -> dict:
    rated = [row["kpi"] for row in subject_rows if row["kpi"] is not None]
    return {
        "total": len(subject_rows),
        "with_data": len(rated),
        "average_kpi": round(sum(rated) / len(rated), 1) if rated else None,
        "levels": _level_counts(subject_rows),
    }


# ---------------------------------------------------------------------------
# Students
# ---------------------------------------------------------------------------

def build_student_rows(filters: ReportFilters, students, *, lessons=None) -> list[dict]:
    """Per-student period figures for an already-selected list of students
    (a page of a group's roster, or every student of the report for the
    Excel export) — two grouped queries for the whole list."""
    students = list(students)
    ids = {s.id for s in students}
    stats = _period_stats(filters, "student", lessons=lessons, only_keys=ids) if ids else {}
    rows = []
    for student in students:
        s = stats.get(student.id, PeriodStats())
        rows.append(
            {
                "id": student.id,
                "name": str(student),
                "group": student.group.name if student.group_id else "—",
                "group_id": student.group_id,
                "status": student.status,
                "status_display": student.get_status_display(),
                "is_active": student.status == Student.Status.ACTIVE,
                "enrollment_date": student.enrollment_date,
                "attendance_total": s.attendance_total,
                "attended": s.attendance_present + s.attendance_late,
                "attendance_rate": s.attendance_rate,
                "homework_results": s.homework_results,
                "homework_submitted": s.homework_submitted,
                "homework_rate": s.homework_rate,
                "average_score": round(s.avg_score, 1) if s.avg_score is not None else None,
                "progress_rate": s.progress_rate,
                "level": s.kpi_result().status,
            }
        )
    return rows


# ---------------------------------------------------------------------------
# Overview
# ---------------------------------------------------------------------------

def build_overview(filters: ReportFilters, *, group_rows=None, teacher_rows=None, subject_rows=None) -> dict:
    group_ids = report_group_ids(filters)
    if group_rows is None:
        group_rows = build_group_rows(filters, group_ids)
    if teacher_rows is None:
        teacher_rows = build_teacher_rows(filters, group_ids, group_rows=group_rows)
    if subject_rows is None:
        subject_rows = build_subject_rows(filters, group_ids)
    weights = kpi_weights()

    if _has_scope_filters(filters):
        students_qs = Student.objects.filter(group_id__in=group_ids)
        event_groups = group_ids
    else:
        students_qs = Student.objects.all()
        event_groups = None
    counts = students_qs.aggregate(
        total=Count("id"),
        active=Count("id", filter=Q(status=Student.Status.ACTIVE)),
        paused=Count("id", filter=Q(status=Student.Status.PAUSED)),
        new=Count("id", filter=_enrolled_in_period_q(filters)),
    )
    left = {sid for _g, sid in _event_pairs(filters, [StudentStatusEvent.EventType.DEACTIVATED], event_groups)}
    returned = {sid for _g, sid in _event_pairs(filters, _RETURN_EVENTS, event_groups)}
    completed = {sid for _g, sid in _event_pairs(filters, [StudentStatusEvent.EventType.COMPLETED], event_groups)}

    total_stats = _period_stats(filters, None).get(None, PeriodStats())
    # The KPI, retention and teacher workload come from the one engine, for
    # exactly the same scope every other KPI page uses.
    engine = KPIEngine.calculate(scope=filters.scope(), today=filters.today)
    total = counts["total"] or 0
    active = counts["active"] or 0
    rated = [row for row in group_rows if row["kpi"] is not None]
    ranked = sorted(rated, key=lambda row: row["kpi"], reverse=True)

    return {
        "filters": filters.as_dict(),
        "students": {
            "total": total,
            "active": active,
            "left": len(left),
            "paused": counts["paused"] or 0,
            "new": counts["new"] or 0,
            "returned": len(returned),
            "completed": len(completed),
            "retention_rate": engine.metrics["retention"],
        },
        "teachers": {
            "total": len(teacher_rows),
            "with_groups": sum(1 for row in teacher_rows if row["groups_count"]),
            "without_groups": sum(1 for row in teacher_rows if not row["groups_count"]),
        },
        "groups": {
            "total": len(group_rows),
            "active": sum(1 for row in group_rows if row["status"] == Group.Status.ACTIVE),
            "without_teacher": sum(1 for row in group_rows if not row["has_teacher"]),
            "with_data": len(rated),
        },
        **{key: value for key, value in total_stats.as_dict(weights).items() if key not in ("has_data", "metrics", "kpi")},
        **_contract(engine),
        "has_data": total_stats.has_data,
        "kpi_weights": weights_description(weights),
        "levels": {
            "groups": _level_counts(group_rows),
            "teachers": _level_counts(teacher_rows),
            "subjects": _level_counts(subject_rows),
        },
        "subjects": {
            **subject_summary(subject_rows),
            "unassigned_lessons": unassigned_subject_lessons(filters),
            "rows": subject_rows,
        },
        "top_groups": [row for row in ranked if row["kpi_level"] == "good"][:5],
        "attention_groups": [row for row in reversed(ranked) if row["kpi_level"] in ("low", "attention")][:5],
        "teacher_summary": [
            {
                "id": row["id"],
                "name": row["name"],
                "groups": [g["name"] for g in row["groups"]],
                "subjects": row["subjects"],
                "kpi": row["kpi"],
                "kpi_level": row["kpi_level"],
            }
            for row in teacher_rows
        ],
    }


def _level_counts(rows) -> dict:
    counts = {"good": 0, "attention": 0, "low": 0, "no_data": 0}
    for row in rows:
        counts[row["kpi_level"]] += 1
    return counts


# ---------------------------------------------------------------------------
# Detail pages
# ---------------------------------------------------------------------------

def build_group_detail(group: Group, filters: ReportFilters) -> dict:
    from apps.academy.services.group_analytics import get_group_analytics

    group_filters = dataclasses.replace(filters, group_id=group.id)
    row = build_group_rows(group_filters, [group.id])[0]
    lessons = group_filters.scope().lessons_qs()
    stats = _period_stats(group_filters, None, lessons=lessons).get(None, PeriodStats())
    weights = kpi_weights()

    # Per-teacher breakdown within this group (each Teaching Program is its
    # own stream — see models.GroupTeacher).
    by_teacher = _period_stats(group_filters, "teacher", lessons=lessons)
    teacher_names = dict(
        (t.id, str(t)) for t in Teacher.objects.filter(id__in=[k for k in by_teacher if k]).select_related("user")
    )
    teacher_breakdown = [
        {"id": tid, "name": teacher_names.get(tid, NO_TEACHER_LABEL), **_rates(s, weights)}
        for tid, s in sorted(by_teacher.items(), key=lambda item: teacher_names.get(item[0], "я"))
    ]

    # Plan progress is course-wide, not period-bound (see group_analytics).
    plan_progress = get_group_analytics(group).summary["progress"]

    return {
        "group": {
            "id": group.id,
            "name": group.name,
            "program": group.course.name,
            "status": group.status,
            "status_display": group.get_status_display(),
            "start_date": group.start_date,
            "end_date": group.end_date,
            "teachers": row["teachers"],
            "teacher_names": row["teacher_names"],
            "subjects": row["subjects"],
            "max_students": group.max_students,
        },
        "filters": filters.as_dict(),
        "students": row["students"],
        **{key: value for key, value in stats.as_dict(weights).items() if key not in ("has_data", "metrics", "kpi")},
        **_contract(KPIEngine.calculate(scope=group_filters.scope(), today=filters.today)),
        "has_data": stats.has_data,
        "plan_progress": plan_progress,
        "teacher_breakdown": teacher_breakdown,
    }


def _rates(s: PeriodStats, weights) -> dict:
    kpi = s.kpi(weights)
    return {
        "lessons": {"total": s.lessons_total, "held": s.lessons_held},
        "attendance_rate": s.attendance_rate,
        "homework_rate": s.homework_rate,
        "activity_rate": s.activity_rate,
        "progress_rate": s.progress_rate,
        "kpi": kpi["total"],
        "kpi_level": kpi["status"],
        "has_data": s.has_data,
    }


def build_subject_detail(subject: Subject, filters: ReportFilters) -> dict:
    """One subject: its summary row, KPI (the engine, scoped to this subject),
    and its groups and teachers — each figure counted over this subject's
    lessons only (a group's or teacher's other subjects are left out)."""
    subject_filters = dataclasses.replace(filters, subject_id=subject.id)
    group_ids = report_group_ids(subject_filters)
    row = build_subject_rows(subject_filters, group_ids)[0]
    subject_group_ids = [g["id"] for g in row["groups"]]
    group_rows = build_group_rows(subject_filters, subject_group_ids)
    teacher_rows = build_teacher_rows(subject_filters, subject_group_ids, group_rows=group_rows)
    weights = kpi_weights()
    stats = _period_stats(subject_filters, None).get(None, PeriodStats())
    return {
        "subject": {
            "id": subject.id,
            "name": subject.name,
            "description": subject.description,
            "is_active": subject.is_active,
        },
        "filters": filters.as_dict(),
        "groups_count": row["groups_count"],
        "teachers_count": row["teachers_count"],
        "students": row["students"],
        **{key: value for key, value in stats.as_dict(weights).items() if key not in ("has_data", "metrics", "kpi")},
        **_contract(KPIEngine.calculate(scope=subject_filters.scope(), today=filters.today)),
        "has_data": stats.has_data,
        "group_rows": group_rows,
        "teacher_rows": teacher_rows,
    }


def group_student_rows(group: Group, filters: ReportFilters) -> list[dict]:
    """Every student on the group's roster with their period figures for
    this group's lessons (two grouped queries for the whole roster)."""
    group_filters = dataclasses.replace(filters, group_id=group.id)
    students = Student.objects.filter(group=group).select_related("group").order_by("last_name", "first_name")
    return build_student_rows(group_filters, students, lessons=group_filters.scope().lessons_qs())


def build_teacher_detail(teacher: Teacher, filters: ReportFilters) -> dict:
    teacher_filters = dataclasses.replace(filters, teacher_id=teacher.id)
    group_ids = report_group_ids(teacher_filters)
    group_rows = build_group_rows(teacher_filters, group_ids)
    rows = build_teacher_rows(teacher_filters, group_ids, group_rows=group_rows)
    weights = kpi_weights()
    row = next((r for r in rows if r["id"] == teacher.id), None)
    stats = _period_stats(teacher_filters, None).get(None, PeriodStats())

    if row is None:
        # A teacher with no groups and no lessons in the period.
        row = {
            "groups": [], "groups_count": 0,
            "subjects": sorted(s.name for s in teacher.subjects.all()),
            "students": {"total": 0, "active": 0, "left": 0},
        }

    return {
        "teacher": {
            "id": teacher.id,
            "name": str(teacher),
            "position": teacher.position,
            "email": teacher.user.email,
            "phone": teacher.phone,
            "is_active": teacher.is_active,
            "hire_date": teacher.hire_date,
        },
        "filters": filters.as_dict(),
        "groups": row["groups"],
        "subjects": row["subjects"],
        "students": row["students"],
        **{key: value for key, value in stats.as_dict(weights).items() if key not in ("has_data", "metrics", "kpi")},
        **_contract(KPIEngine.calculate(scope=teacher_filters.scope(), today=filters.today)),
        "has_data": stats.has_data,
        # This teacher's own figures in each of their groups — scoped to
        # the lessons they give (never a co-teacher's lessons in a shared group).
        "group_performance": group_rows,
    }


# ---------------------------------------------------------------------------
# Filter choices (select options on every Reports screen)
# ---------------------------------------------------------------------------

def filter_options() -> dict:
    return {
        "programs": list(Course.objects.order_by("name").values("id", "name")),
        "groups": list(Group.objects.order_by("name").values("id", "name")),
        "teachers": [
            {"id": t.id, "name": str(t)}
            for t in Teacher.objects.select_related("user").order_by("user__first_name", "user__last_name")
        ],
        "subjects": list(Subject.objects.order_by("name").values("id", "name")),
    }


def describe_filters(filters: ReportFilters) -> str:
    """Human-readable list of the applied program/group/teacher/subject
    filters (PDF cover, Excel overview)."""
    labels = []
    for model, value, title in (
        (Course, filters.course_id, "Программа"),
        (Group, filters.group_id, "Группа"),
        (Teacher, filters.teacher_id, "Тренер"),
        (Subject, filters.subject_id, "Предмет"),
    ):
        if value:
            obj = model.objects.filter(pk=value).first()
            labels.append(f"{title}: {obj if obj is not None else '#' + str(value)}")
    return " · ".join(labels) if labels else "Все программы, группы, тренеры и предметы"


def build_full_report(filters: ReportFilters) -> dict:
    """Everything the PDF/Excel exports need, in one pass."""
    group_ids = report_group_ids(filters)
    group_rows = build_group_rows(filters, group_ids)
    teacher_rows = build_teacher_rows(filters, group_ids, group_rows=group_rows)
    subject_rows = build_subject_rows(filters, group_ids)
    overview = build_overview(filters, group_rows=group_rows, teacher_rows=teacher_rows, subject_rows=subject_rows)
    return {"filters": filters, "overview": overview, "groups": group_rows, "teachers": teacher_rows,
            "subjects": subject_rows, "group_ids": group_ids}


def build_all_student_rows(filters: ReportFilters, group_ids) -> list[dict]:
    students = Student.objects.filter(group_id__in=group_ids).select_related("group").order_by(
        "group__name", "last_name", "first_name"
    )
    return build_student_rows(filters, students)


__all__ = [
    "PeriodStats",
    "build_all_student_rows",
    "build_full_report",
    "build_group_detail",
    "build_group_rows",
    "build_overview",
    "build_student_rows",
    "build_subject_detail",
    "build_subject_rows",
    "build_teacher_detail",
    "build_teacher_rows",
    "describe_filters",
    "filter_options",
    "group_student_rows",
    "report_group_ids",
    "report_subject_ids",
    "report_teacher_ids",
    "subject_summary",
]
