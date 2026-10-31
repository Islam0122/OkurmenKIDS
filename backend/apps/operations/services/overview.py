"""Главная кабинета, ежедневный контроль, KPI-аналитика и последние события.

Все цифры — из БД на момент запроса (никаких снимков и статических чисел),
через сервисы задач, отчётов, Контроля, KPI Engine и учёта прихода."""
from __future__ import annotations

import datetime as dt
from collections import defaultdict

from django.db.models import Count, Q
from django.utils import timezone

from apps.users.models import User

from .. import kpi_registry
from ..departments import Department, department_of, roles_of
from ..models import (
    ACTIVE_ISSUE_STATUSES,
    OPEN_STATUSES,
    EmployeeReport,
    KPITarget,
    OperationalIssue,
    Priority,
    Task,
    TaskHistory,
    TaskStatus,
)
from . import staff
from .academy import control_service, students_overview, problem_students_for
from .org import department_overview
from .period import OpsFilters
from .reports import obligations, submission_summary


def _person(user):
    return None if user is None else {"id": user.pk, "full_name": user.get_full_name() or user.username,
                                      "role_label": user.get_role_display()}


def _task_row(task, now):
    return {"id": task.pk, "title": task.title, "department": task.department,
            "department_label": task.get_department_display(), "assignee": _person(task.assignee),
            "priority": task.priority, "priority_label": task.get_priority_display(),
            "status": task.effective_status(now), "deadline": task.deadline}


def task_metrics(f: OpsFilters, users_qs=None) -> dict:
    now = timezone.now()
    qs = Task.objects.exclude(status=TaskStatus.CANCELLED)
    if f.department:
        qs = qs.filter(department=f.department)
    if f.role or f.employee_id:
        qs = qs.filter(assignee__in=users_qs if users_qs is not None else f.users_qs())
    return qs.aggregate(
        completed=Count("id", filter=Q(status=TaskStatus.COMPLETED, completed_at__date__range=(f.start, f.end))),
        in_progress=Count("id", filter=Q(status=TaskStatus.IN_PROGRESS)),
        pending=Count("id", filter=Q(status__in=(TaskStatus.PENDING, TaskStatus.REJECTED))),
        overdue=Count("id", filter=Q(status__in=OPEN_STATUSES, deadline__lt=now)),
        review=Count("id", filter=Q(status=TaskStatus.REVIEW)),
        created=Count("id", filter=Q(created_at__date__range=(f.start, f.end))),
    )


def _kpi_achievement(f: OpsFilters) -> dict:
    """Средний процент достижения по действующим целям периода. Целей нет —
    None: норматив не придумывается."""
    period = "daily" if f.days == 1 else ("weekly" if f.days <= 7 else "monthly")
    targets = KPITarget.objects.filter(period=period, valid_from__lte=f.elapsed_end).filter(
        Q(valid_to__isnull=True) | Q(valid_to__gte=f.start)).select_related("employee")
    if f.department:
        targets = targets.filter(department=f.department)
    if f.employee_id:
        targets = targets.filter(employee_id=f.employee_id)
    levels, below = [], 0
    for target in targets:
        metric = kpi_registry.METRICS.get(target.metric)
        if metric is None:
            continue
        level = kpi_registry.achievement(metric.compute(f.start, f.end, target.department, target.employee),
                                         target.target_value, metric.higher_is_better)
        if level is not None:
            levels.append(min(level, 200))
            below += level < 100
    return {"targets": targets.count(), "measured": len(levels), "below_target": below,
            "achievement": round(sum(levels) / len(levels), 1) if levels else None}


def dashboard(f: OpsFilters) -> dict:
    now = timezone.now()
    users = f.users_qs()
    tracked = [u for u in staff.tracked_users(users)]
    att_rows = staff.rows(tracked, f.start, f.elapsed_end)
    duties = obligations(f.start, f.end, users=list(users))
    tasks = task_metrics(f, users)
    reports = submission_summary(duties)
    pending_reports = EmployeeReport.objects.filter(status=EmployeeReport.Status.SUBMITTED)
    if f.department:
        pending_reports = pending_reports.filter(department=f.department)
    departments = department_overview(f)
    if f.department:
        departments = [d for d in departments if d["key"] == f.department]
    previous = f.previous()
    prev_tasks = task_metrics(previous, users)
    prev_att = staff.summarize(staff.rows(tracked, previous.start, previous.elapsed_end))
    attendance = staff.summarize(att_rows)

    today_tasks = Task.objects.filter(deadline__date=f.today).exclude(status=TaskStatus.CANCELLED).select_related(
        "assignee")
    overdue = Task.objects.filter(status__in=OPEN_STATUSES, deadline__lt=now).select_related("assignee").order_by(
        "deadline")
    if f.department:
        today_tasks, overdue = today_tasks.filter(department=f.department), overdue.filter(department=f.department)
    issues = OperationalIssue.objects.filter(status__in=ACTIVE_ISSUE_STATUSES)
    if f.department:
        issues = issues.filter(department=f.department)
    issues_by_kind = dict(issues.values("kind").annotate(n=Count("id")).values_list("kind", "n"))
    performance = [d["performance"] for d in departments if d["performance"] is not None]
    return {
        "filters": f.as_dict(),
        "metrics": {
            "total_employees": User.objects.filter(role__in=roles_of(f.department) if f.department
                                                   else User.Role.values).count(),
            "active_employees": users.count(),
            "tasks_completed": tasks["completed"],
            "tasks_in_progress": tasks["in_progress"],
            "tasks_overdue": tasks["overdue"],
            "pending_reviews": tasks["review"] + pending_reports.count(),
            "attendance_rate": attendance["attendance_rate"],
            "reports_submitted": reports["submitted"],
            "reports_expected": reports["expected"],
            "kpi": _kpi_achievement(f),
            "overall_performance": round(sum(performance) / len(performance), 1) if performance else None,
        },
        "previous": {"tasks_completed": prev_tasks["completed"], "attendance_rate": prev_att["attendance_rate"],
                     "label": f"{previous.start:%d.%m} — {previous.end:%d.%m}"},
        "departments": departments,
        "today_tasks": [_task_row(t, now) for t in today_tasks.order_by("deadline")[:15]],
        "overdue_tasks": [_task_row(t, now) for t in overdue[:15]],
        "overdue_total": overdue.count(),
        "attendance": {**attendance, "today": staff.summarize(staff.rows(tracked, f.today, f.today))
                       if f.start <= f.today <= f.end else None},
        "reports": reports,
        "attention": {"total": issues.count(),
                      "critical": issues.filter(priority__in=(Priority.CRITICAL, Priority.HIGH)).count(),
                      "by_kind": issues_by_kind,
                      "top": [{"id": i.pk, "title": i.title, "priority": i.priority, "kind": i.kind,
                               "kind_label": i.get_kind_display(), "department_label": i.get_department_display(),
                               "responsible": _person(i.responsible), "detected_at": i.detected_at}
                              for i in issues.select_related("responsible").order_by("priority", "-detected_at")[:8]]},
        "students": students_overview(f) if f.department in (None, Department.ACADEMY) else None,
        "activity": recent_activity(limit=12, department=f.department),
    }


def recent_activity(*, limit: int = 30, department: str | None = None) -> list[dict]:
    """Лента: действия с задачами, сданные и проверенные отчёты, проблемы."""
    events = []
    history = TaskHistory.objects.select_related("actor", "task").order_by("-created_at")
    if department:
        history = history.filter(task__department=department)
    for h in history[:limit]:
        events.append({"at": h.created_at, "type": "task", "action": h.get_action_display(), "title": h.task.title,
                       "actor": _person(h.actor), "link": f"/tasks/{h.task_id}"})
    reports = EmployeeReport.objects.exclude(status=EmployeeReport.Status.DRAFT).select_related("author").order_by(
        "-updated_at")
    if department:
        reports = reports.filter(department=department)
    for r in reports[:limit]:
        events.append({"at": r.reviewed_at or r.submitted_at or r.updated_at, "type": "report",
                       "action": r.get_status_display(), "title": f"{r.get_kind_display()} отчёт за "
                                                                  f"{r.period_start:%d.%m.%Y}",
                       "actor": _person(r.author), "link": "/operations/reports"})
    issues = OperationalIssue.objects.select_related("responsible").order_by("-detected_at")
    if department:
        issues = issues.filter(department=department)
    for i in issues[:limit]:
        events.append({"at": i.detected_at, "type": "issue", "action": "Обнаружена проблема", "title": i.title,
                       "actor": None, "link": f"/operations/issues/{i.pk}"})
    events.sort(key=lambda e: e["at"] or timezone.now(), reverse=True)
    return events[:limit]


def daily_control(day: dt.date) -> dict:
    """Что произошло за день по каждому отделу и кто отвечает за невыполненное."""
    now = timezone.now()
    f = OpsFilters("custom", day, day, timezone.localdate())
    done = Task.objects.filter(status=TaskStatus.COMPLETED, completed_at__date=day).select_related("assignee")
    missed = Task.objects.filter(status__in=OPEN_STATUSES, deadline__date__lte=day,
                                 deadline__lt=now).select_related("assignee")
    duties = obligations(day, day)
    service = control_service(f)
    control_rows = service.rows(service.evaluate())
    tracked = staff.tracked_users()
    att_rows = staff.rows(tracked, day, day)
    by_dep = defaultdict(lambda: {"completed": 0, "overdue": 0, "reports_missing": 0, "absent": 0, "late": 0})
    for t in done:
        by_dep[t.department]["completed"] += 1
    for t in missed:
        by_dep[t.department]["overdue"] += 1
    for o in duties:
        if o.status == "missing":
            by_dep[department_of(o.user)]["reports_missing"] += 1
    for r in att_rows:
        status = staff.ops_status(r)
        if status == staff.ABSENT:
            by_dep[department_of(r.user)]["absent"] += 1
        if status == staff.LATE:
            by_dep[department_of(r.user)]["late"] += 1
    issues = OperationalIssue.objects.filter(status__in=ACTIVE_ISSUE_STATUSES).select_related("responsible")
    return {
        "date": day,
        "tasks": {"completed": [_task_row(t, now) for t in done[:100]],
                  "overdue": [_task_row(t, now) for t in missed.order_by("deadline")[:100]],
                  "completed_count": done.count(), "overdue_count": missed.count()},
        "reports": {**submission_summary(duties),
                    "missing": [{"user": _person(o.user), "kind": o.kind, "due": o.due} for o in duties
                                if o.status == "missing"]},
        "journals": {"summary": service.summary(control_rows),
                     "problems": [r for r in control_rows if r["status"] in ("problem", "attention")][:50]},
        "attendance": {**staff.summarize(att_rows),
                       "absent": [staff.serialize_row(r) for r in att_rows if staff.ops_status(r) == staff.ABSENT],
                       "late": [staff.serialize_row(r) for r in att_rows if staff.ops_status(r) == staff.LATE]},
        "kpi": _kpi_achievement(f),
        "students": problem_students_for(f, limit=20),
        "issues": {"open": issues.count(),
                   "new_today": issues.filter(detected_at__date=day).count(),
                   "items": [{"id": i.pk, "title": i.title, "kind_label": i.get_kind_display(),
                              "priority": i.priority, "responsible": _person(i.responsible),
                              "department_label": i.get_department_display()}
                             for i in issues.order_by("priority", "-detected_at")[:30]]},
        "departments": [{"key": key, "label": label, **by_dep[key]} for key, label in Department.choices],
    }


# --- KPI ----------------------------------------------------------------------

def _period_type(f: OpsFilters) -> str:
    return "daily" if f.days == 1 else ("weekly" if f.days <= 7 else "monthly")


def _target_value(metric_key, department, employee, period, on):
    qs = KPITarget.objects.filter(metric=metric_key, period=period, valid_from__lte=on).filter(
        Q(valid_to__isnull=True) | Q(valid_to__gte=on)).order_by("-valid_from")
    if employee is not None:
        target = qs.filter(employee=employee).first() or qs.filter(employee__isnull=True,
                                                                   department=department_of(employee)).first()
    else:
        target = qs.filter(employee__isnull=True, department=department).first()
    return float(target.target_value) if target else None


def _trend(actual, previous):
    if actual is None or previous is None:
        return None
    if previous == 0:
        return {"direction": "up" if actual > 0 else "stable", "change": None}
    change = round((actual - previous) / abs(previous) * 100, 1)
    return {"direction": "up" if change > 0 else ("down" if change < 0 else "stable"), "change": change}


def kpi_overview(f: OpsFilters, *, can_see_finance: bool) -> dict:
    previous = f.previous()
    period = _period_type(f)
    employee = User.objects.filter(pk=f.employee_id).first() if f.employee_id else None
    departments = [f.department] if f.department else [d for d, _ in Department.choices if d != "finance"]
    result = []
    for department in departments:
        rows = []
        for metric in kpi_registry.metrics_for(department, employee.role if employee else None):
            if metric.financial and not can_see_finance:
                continue
            if employee is None and not metric.department_level:
                continue
            dep = department if employee is None else None
            actual = metric.compute(f.start, f.end, dep, employee)
            prev = metric.compute(previous.start, previous.end, dep, employee)
            target = _target_value(metric.key, department, employee, period, f.elapsed_end)
            rows.append({**kpi_registry.describe(metric), "actual": actual, "previous": prev, "target": target,
                         "achievement": kpi_registry.achievement(actual, target, metric.higher_is_better),
                         "trend": _trend(actual, prev)})
        result.append({"department": department, "label": Department(department).label, "metrics": rows})
    return {"filters": f.as_dict(), "period_type": period, "previous": previous.as_dict(), "departments": result,
            "employee": _person(employee)}


def kpi_history(metric_key: str, *, department: str | None, employee, period: str, points: int = 6,
                today: dt.date | None = None) -> list[dict]:
    from .reports import normalize_period

    metric = kpi_registry.METRICS[metric_key]
    today = today or timezone.localdate()
    start, _ = normalize_period(period, today)
    history = []
    for _ in range(points):
        p_start, p_end = normalize_period(period, start)
        actual = metric.compute(p_start, p_end, department, employee)
        target = _target_value(metric_key, department, employee, period, p_end)
        history.append({"start": p_start, "end": p_end, "actual": actual, "target": target,
                        "achievement": kpi_registry.achievement(actual, target, metric.higher_is_better)})
        start = p_start - dt.timedelta(days=1)
    return list(reversed(history))
