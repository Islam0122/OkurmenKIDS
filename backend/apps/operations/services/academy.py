"""Академия в кабинете операционного директора: тренеры, тимлиды,
ассистенты, проблемные студенты и группы.

Ничего не считается заново:

* заполнение журнала, посещаемости, ДЗ и оценок — сервис «Контроль»
  (academy.services.control), включая правило «ещё не должно быть сделано —
  не нарушение» (занятие не наступило, срок ДЗ не прошёл);
* KPI тренера — Reports / KPI Engine (academy.services.reports);
* проблемные студенты — «Контроль активности» ассистента
  (assistant.activity) с его порогами.
"""
from __future__ import annotations

from collections import defaultdict

from django.db.models import Count, Q

from apps.academy.models import Group, MonthlyTeacherReport, Student
from apps.academy.services.control import ControlQuery, ControlService
from apps.academy.services.control import rules as control_rules
from apps.academy.services.reports import ReportFilters, build_group_rows, build_teacher_detail, build_teacher_rows
from apps.assistant import activity
from apps.users.models import Teacher, User

from ..kpi_registry import achievement
from ..models import OPEN_STATUSES, KPITarget, Task, TaskStatus
from .period import OpsFilters
from .reports import obligations, submission_summary

WARNING_LABELS = {
    "journal_not_filled": "Журнал не заполнен",
    "attendance_not_updated": "Посещаемость не отмечена",
    "homework_not_checked": "ДЗ не проверено",
    "report_not_submitted": "Отчёт не сдан",
    "kpi_below_target": "KPI ниже цели",
}


def report_filters(f: OpsFilters, **extra) -> ReportFilters:
    return ReportFilters.from_query(f.report_query(**{k: v for k, v in extra.items() if v is not None}),
                                    today=f.today)


def control_service(f: OpsFilters, **extra) -> ControlService:
    return ControlService(ControlQuery(filters=report_filters(f, **extra)))


def _photo(teacher: Teacher) -> str | None:
    return teacher.image.url if teacher.image else None


def task_counts(user_ids, now=None) -> dict[int, dict]:
    from django.utils import timezone

    now = now or timezone.now()
    rows = Task.objects.filter(assignee_id__in=user_ids).exclude(status=TaskStatus.CANCELLED).values(
        "assignee_id").annotate(
        open=Count("id", filter=Q(status__in=OPEN_STATUSES)),
        overdue=Count("id", filter=Q(status__in=OPEN_STATUSES, deadline__lt=now)),
        review=Count("id", filter=Q(status=TaskStatus.REVIEW)),
        completed=Count("id", filter=Q(status=TaskStatus.COMPLETED)),
    )
    return {r["assignee_id"]: {k: r[k] for k in ("open", "overdue", "review", "completed")} for r in rows}


EMPTY_TASKS = {"open": 0, "overdue": 0, "review": 0, "completed": 0}


def kpi_target_for(user, metric: str, period: str, on) -> float | None:
    """Действующая цель: личная, иначе цель отдела. Нет — None."""
    from ..departments import department_of

    qs = KPITarget.objects.filter(metric=metric, period=period, valid_from__lte=on).filter(
        Q(valid_to__isnull=True) | Q(valid_to__gte=on)).order_by("-valid_from")
    personal = qs.filter(employee=user).first() if user is not None else None
    target = personal or qs.filter(employee__isnull=True, department=department_of(user) if user else None).first()
    return float(target.target_value) if target else None


def _target_period(f: OpsFilters) -> str:
    return "daily" if f.days == 1 else ("weekly" if f.days <= 7 else "monthly")


def trainer_rows(f: OpsFilters, *, subject_id=None, group_id=None) -> list[dict]:
    rf = report_filters(f, subject=subject_id, group=group_id)
    kpi_rows = {row["id"]: row for row in build_teacher_rows(rf)}
    service = ControlService(ControlQuery(filters=rf))
    by_teacher: dict[int, list] = defaultdict(list)
    for check in service.evaluate():
        teacher = check.lesson.effective_teacher
        if teacher is not None:
            by_teacher[teacher.id].append(check)
    teacher_ids = set(kpi_rows) | set(by_teacher)
    teachers = Teacher.objects.filter(id__in=teacher_ids).select_related("user").prefetch_related("subjects")
    users = [t.user for t in teachers]
    tasks = task_counts([u.pk for u in users])
    duties = defaultdict(list)
    for item in obligations(f.start, f.end, users=users):
        duties[item.user.pk].append(item)
    period = _target_period(f)
    rows = []
    for teacher in teachers:
        kpi = kpi_rows.get(teacher.id, {})
        control = service.aggregate(by_teacher.get(teacher.id, [])) if teacher.id in by_teacher else None
        reports = submission_summary(duties.get(teacher.user_id, []))
        target = kpi_target_for(teacher.user, "trainer_kpi", period, f.elapsed_end)
        warnings = []
        if control:
            if control["lessons"]["not_closed"]:
                warnings.append("journal_not_filled")
            if control["attendance"]["total"] - control["attendance"]["completed"]:
                warnings.append("attendance_not_updated")
            if control["homework"]["awaiting_review"]:
                warnings.append("homework_not_checked")
        if reports["missing"]:
            warnings.append("report_not_submitted")
        if target is not None and kpi.get("kpi") is not None and kpi["kpi"] < target:
            warnings.append("kpi_below_target")
        rows.append({
            "id": teacher.id,
            "user_id": teacher.user_id,
            "name": str(teacher),
            "photo": _photo(teacher),
            "position": teacher.position,
            "subjects": kpi.get("subjects") or sorted(s.name for s in teacher.subjects.all()),
            "groups": kpi.get("groups", []),
            "students": kpi.get("students", {}).get("active", 0),
            "is_active": teacher.is_active and teacher.user.is_active,
            "kpi": kpi.get("kpi"),
            "kpi_level": kpi.get("kpi_level", "no_data"),
            "kpi_target": target,
            "kpi_achievement": achievement(kpi.get("kpi"), target, True),
            "attendance_rate": kpi.get("attendance_rate"),
            "homework_rate": kpi.get("homework_rate"),
            "journal": _journal(control),
            "reports": reports,
            "tasks": tasks.get(teacher.user_id, EMPTY_TASKS),
            "warnings": [{"key": w, "label": WARNING_LABELS[w]} for w in warnings],
        })
    rows.sort(key=lambda r: (-len(r["warnings"]), r["kpi"] if r["kpi"] is not None else 101, r["name"]))
    return rows


def _journal(control: dict | None) -> dict:
    if control is None:
        return {"status": control_rules.STATUS_NO_DATA, "status_label": control_rules.STATUS_LABELS["no_data"],
                "lessons_due": 0, "lessons_closed": 0, "not_closed": 0, "attendance_missing": 0,
                "homework_awaiting_review": 0, "homework_missing": 0, "homework_checked": 0,
                "grades_missing": 0, "upcoming": 0, "last_activity_at": None, "completion": None, "issues": []}
    lessons = control["lessons"]
    return {
        "status": control["status"],
        "status_label": control["status_label"],
        "lessons_due": lessons["total"],
        "lessons_closed": lessons["completed"],
        "not_closed": lessons["not_closed"],
        "upcoming": lessons["upcoming"],
        "attendance_missing": control["attendance"]["total"] - control["attendance"]["completed"],
        "homework_awaiting_review": control["homework"]["awaiting_review"],
        "homework_missing": control["homework"]["missing"],
        "homework_checked": control["homework"]["checked"],
        "grades_missing": control["grades"]["students_missing"],
        "last_activity_at": control["last_activity_at"],
        "completion": lessons["percent"],
        "issues": control["issues"],
    }


def filter_trainer_rows(rows: list[dict], params) -> list[dict]:
    if params.get("kpi_level"):
        rows = [r for r in rows if r["kpi_level"] == params["kpi_level"]]
    if params.get("journal_status"):
        rows = [r for r in rows if r["journal"]["status"] == params["journal_status"]]
    if params.get("warning"):
        rows = [r for r in rows if any(w["key"] == params["warning"] for w in r["warnings"])]
    if params.get("q"):
        q = params["q"].lower()
        rows = [r for r in rows if q in r["name"].lower()]
    return rows


def trainer_summary(rows: list[dict]) -> dict:
    rated = [r["kpi"] for r in rows if r["kpi"] is not None]
    return {
        "trainers": len(rows),
        "with_warnings": sum(1 for r in rows if r["warnings"]),
        "average_kpi": round(sum(rated) / len(rated), 1) if rated else None,
        "warnings": {key: sum(1 for r in rows if any(w["key"] == key for w in r["warnings"]))
                     for key in WARNING_LABELS},
    }


def trainer_detail(teacher: Teacher, f: OpsFilters) -> dict:
    rf = report_filters(f, teacher=teacher.id)
    service = ControlService(ControlQuery(filters=rf))
    checks = service.evaluate()
    control_rows = service.rows(checks)
    groups = [row["group"]["id"] for row in control_rows]
    problem_students = problem_students_for(f, group_ids=groups) if groups else []
    duties = obligations(f.start, f.end, users=[teacher.user])
    monthly = list(MonthlyTeacherReport.objects.filter(teacher=teacher).order_by("-year", "-month").values(
        "id", "year", "month", "comment", "updated_at")[:6])
    row = next((r for r in trainer_rows(f) if r["id"] == teacher.id), None)
    return {
        "trainer": row or {"id": teacher.id, "user_id": teacher.user_id, "name": str(teacher), "photo": _photo(teacher),
                           "position": teacher.position, "subjects": sorted(s.name for s in teacher.subjects.all()),
                           "groups": [], "students": 0, "is_active": teacher.is_active, "kpi": None,
                           "kpi_level": "no_data", "journal": _journal(None), "warnings": [],
                           "tasks": task_counts([teacher.user_id]).get(teacher.user_id, EMPTY_TASKS),
                           "reports": submission_summary(duties)},
        "control": {"summary": service.summary(control_rows), "rows": control_rows},
        "kpi": build_teacher_detail(teacher, rf),
        "problem_students": problem_students,
        "reports": [{"kind": o.kind, "period_start": o.period_start, "period_end": o.period_end, "due": o.due,
                     "status": o.status, "report_id": o.report_id} for o in duties],
        "monthly_reports": monthly,
    }


def problem_students_for(f: OpsFilters, *, group_ids=None, limit: int | None = None) -> list[dict]:
    students = activity.control_students()
    if group_ids is not None:
        students = [s for s in students if s.group_id in set(group_ids)]
    rows, _ = activity.analyse_students(students, start=f.start, today=f.today)
    problems = [r for r in rows if r.status in (activity.STATUS_RISK, activity.STATUS_LOW, activity.STATUS_ATTENTION)
                or "frequent_absence" in r.categories]
    problems.sort(key=activity.SORTS["risk"])
    result = []
    for row in problems[:limit] if limit else problems:
        data = row.as_dict()
        data["category_labels"] = [activity.CATEGORIES[c] for c in row.categories]
        result.append(data)
    return result


def problem_groups(f: OpsFilters, min_attendance: int) -> list[dict]:
    """Группы с посещаемостью ниже порога (OperationsSettings.problem_group_attendance;
    0 — правило выключено) или с KPI «Низкий»."""
    rows = build_group_rows(report_filters(f))
    result = []
    for row in rows:
        low_attendance = bool(min_attendance and row.get("attendance_rate") is not None
                              and row["attendance_rate"] < min_attendance)
        if low_attendance or row.get("kpi_level") == "low":
            result.append({"id": row["id"], "name": row["name"], "kpi": row.get("kpi"),
                           "kpi_level": row.get("kpi_level"), "attendance_rate": row.get("attendance_rate"),
                           "reason": "Низкая посещаемость" if low_attendance else "Низкий KPI"})
    return result


def team_lead_rows(f: OpsFilters) -> list[dict]:
    """Тимлиды. В LMS тимлид руководит всеми тренерами академии (связи
    «тимлид → свои тренеры» нет), поэтому его команда — все активные тренеры,
    а «качество» — сводка Контроля и KPI академии плюс его собственная работа:
    рабочий журнал, отчёты, проверки и задачи."""
    from apps.worklog.models import TeamLeadReport, WorkLogEntry

    leads = list(User.objects.filter(role=User.Role.TEAM_LEAD, is_active=True).order_by("first_name"))
    if not leads:
        return []
    ids = [u.pk for u in leads]
    tasks = task_counts(ids)
    entries = dict(WorkLogEntry.objects.filter(author_id__in=ids, date__range=(f.start, f.end)).values(
        "author_id").annotate(n=Count("id")).values_list("author_id", "n"))
    reports = defaultdict(lambda: defaultdict(int))
    for row in TeamLeadReport.objects.filter(author_id__in=ids, date__range=(f.start, f.end)).exclude(
            status="draft").values("author_id", "kind").annotate(n=Count("id")):
        reports[row["author_id"]][row["kind"]] = row["n"]
    duties = defaultdict(list)
    for item in obligations(f.start, f.end, users=leads):
        duties[item.user.pk].append(item)
    team = Teacher.objects.filter(is_active=True, user__is_active=True).count()
    service = control_service(f)
    summary = service.summary(service.rows(service.evaluate()))
    reviewed = defaultdict(int)
    from ..models import EmployeeReport

    for row in EmployeeReport.objects.filter(reviewed_by_id__in=ids, reviewed_at__date__range=(f.start, f.end)).values(
            "reviewed_by_id").annotate(n=Count("id")):
        reviewed[row["reviewed_by_id"]] = row["n"]
    return [{
        "id": lead.pk,
        "name": lead.get_full_name() or lead.username,
        "team_size": team,
        "worklog_entries": entries.get(lead.pk, 0),
        "reports": dict(reports[lead.pk]),
        "report_obligations": submission_summary(duties[lead.pk]),
        "reports_reviewed": reviewed[lead.pk],
        "tasks": tasks.get(lead.pk, EMPTY_TASKS),
        "academy_control": {"attention": summary["attention_count"], "problem_lessons": summary["problem_lessons"],
                            "attendance_completion": summary["attendance_completion"],
                            "homework_completion": summary["homework_completion"]},
    } for lead in leads]


def assistant_rows(f: OpsFilters) -> list[dict]:
    """Ассистенты: посещаемость студентов и пропуски (Контроль активности),
    их ежедневные отчёты (связь с родителями, отработка пропусков — показатели
    отчёта), задачи. Связи «ассистент → свои группы» в LMS нет: ассистент
    ведёт всю академию, поэтому студенческие показатели общие."""
    from ..models import EmployeeReport
    from .reports import SUBMITTED_STATUSES

    assistants = list(User.objects.filter(role=User.Role.ASSISTANT, is_active=True).order_by("first_name"))
    if not assistants:
        return []
    ids = [u.pk for u in assistants]
    tasks = task_counts(ids)
    duties = defaultdict(list)
    for item in obligations(f.start, f.end, users=assistants):
        duties[item.user.pk].append(item)
    totals = defaultdict(lambda: defaultdict(int))
    for author_id, metrics in EmployeeReport.objects.filter(author_id__in=ids, status__in=SUBMITTED_STATUSES,
                                                            period_start__range=(f.start, f.end)).values_list(
            "author_id", "metrics"):
        for key, value in (metrics or {}).items():
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                totals[author_id][key] += value
    return [{
        "id": a.pk,
        "name": a.get_full_name() or a.username,
        "parents_contacted": totals[a.pk].get("parents_contacted"),
        "absences_followed_up": totals[a.pk].get("absences_followed_up"),
        "tables_updated": totals[a.pk].get("tables_updated"),
        "report_obligations": submission_summary(duties[a.pk]),
        "tasks": tasks.get(a.pk, EMPTY_TASKS),
    } for a in assistants]


def students_overview(f: OpsFilters) -> dict:
    active = Student.objects.filter(status=Student.Status.ACTIVE).count()
    groups = Group.objects.filter(status=Group.Status.ACTIVE).count()
    problems = problem_students_for(f)
    return {
        "active_students": active,
        "active_groups": groups,
        "problem_students": len(problems),
        "risk": sum(1 for p in problems if p["status"] == activity.STATUS_RISK),
        "frequent_absence": sum(1 for p in problems if "frequent_absence" in p["categories"]),
    }
