"""Сотрудники и отделы: справочник, профиль сотрудника, сводки отделов
(продажи, РОП, маркетинг, HR). Только чтение существующих данных; о людях —
имя, роль, отдел, статус, дата начала работы (без контактов и зарплат)."""
from __future__ import annotations

import datetime as dt
from collections import defaultdict

from django.db.models import Count, Q, Sum
from django.utils import timezone

from apps.users.models import User

from .. import kpi_registry
from ..departments import Department, department_of, roles_of
from ..models import (
    ACTIVE_ISSUE_STATUSES,
    OPEN_STATUSES,
    EmployeeReport,
    OperationalIssue,
    Task,
    TaskStatus,
)
from . import staff
from .academy import EMPTY_TASKS, kpi_target_for, task_counts
from .period import OpsFilters
from .reports import SUBMITTED_STATUSES, obligations, submission_summary


def employee_card(user) -> dict:
    teacher = getattr(user, "teacher_profile", None)
    return {
        "id": user.pk,
        "full_name": user.get_full_name() or user.username,
        "role": user.role,
        "role_label": user.get_role_display(),
        "department": department_of(user),
        "department_label": Department(department_of(user)).label,
        "position": teacher.position if teacher else user.get_role_display(),
        "photo": teacher.image.url if teacher and teacher.image else None,
        "teacher_id": teacher.pk if teacher else None,
        "is_active": user.is_active,
        "joined": (teacher.hire_date if teacher and teacher.hire_date else timezone.localtime(user.date_joined).date()),
        "last_login": user.last_login,
    }


def employees(f: OpsFilters, *, search: str = "", include_inactive: bool = False) -> list[dict]:
    qs = f.users_qs() if not include_inactive else User.objects.filter(
        role__in=roles_of(f.department) if f.department else User.Role.values)
    if search:
        qs = qs.filter(Q(first_name__icontains=search) | Q(last_name__icontains=search) | Q(username__icontains=search))
    users = list(qs.select_related("teacher_profile").order_by("first_name", "last_name"))
    tasks = task_counts([u.pk for u in users])
    duties = defaultdict(list)
    for item in obligations(f.start, f.end, users=[u for u in users if u.is_active]):
        duties[item.user.pk].append(item)
    attendance = defaultdict(list)
    for row in staff.rows([u for u in users if u in staff.tracked_users()], f.start, f.elapsed_end):
        attendance[row.user.pk].append(row)
    result = []
    for user in users:
        card = employee_card(user)
        card["tasks"] = tasks.get(user.pk, EMPTY_TASKS)
        card["reports"] = submission_summary(duties[user.pk])
        card["attendance"] = staff.summarize(attendance[user.pk]) if user.pk in attendance else None
        result.append(card)
    return result


def employee_profile(user, f: OpsFilters) -> dict:
    from ..serializers import TaskListSerializer

    now = timezone.now()
    tasks_qs = Task.objects.filter(assignee=user).select_related("assignee", "created_by")
    open_tasks = tasks_qs.filter(status__in=(*OPEN_STATUSES, TaskStatus.REVIEW)).order_by("deadline")[:50]
    done = tasks_qs.filter(status=TaskStatus.COMPLETED, completed_at__date__range=(f.start, f.end))
    duties = obligations(f.start, f.end, users=[user])
    rows = staff.rows([user], f.start, f.elapsed_end) if user in staff.tracked_users() else []
    metrics = []
    period = "daily" if f.days == 1 else ("weekly" if f.days <= 7 else "monthly")
    for metric in kpi_registry.metrics_for(department_of(user), user.role):
        if not metric.employee_level:
            continue
        actual = metric.compute(f.start, f.end, None, user)
        target = kpi_target_for(user, metric.key, period, f.elapsed_end)
        metrics.append({**kpi_registry.describe(metric), "actual": actual, "target": target,
                        "achievement": kpi_registry.achievement(actual, target, metric.higher_is_better)})
    history = []
    month_start = f.today.replace(day=1)
    for _ in range(6):
        month_end = (month_start + dt.timedelta(days=32)).replace(day=1) - dt.timedelta(days=1)
        history.append({
            "month": month_start.isoformat()[:7],
            "tasks_completed": kpi_registry.tasks_completed(month_start, month_end, None, user),
            "task_completion_rate": kpi_registry.task_completion_rate(month_start, month_end, None, user),
        })
        month_start = (month_start - dt.timedelta(days=1)).replace(day=1)
    reports = EmployeeReport.objects.filter(author=user).order_by("-period_start")[:20]
    issues = OperationalIssue.objects.filter(responsible=user, status__in=ACTIVE_ISSUE_STATUSES)
    return {
        "employee": employee_card(user),
        "tasks": {
            **task_counts([user.pk]).get(user.pk, EMPTY_TASKS),
            "completed_in_period": done.count(),
            "overdue_items": TaskListSerializer([t for t in open_tasks if t.is_overdue(now)], many=True,
                                                context={"now": now}).data,
            "open_items": TaskListSerializer(open_tasks, many=True, context={"now": now}).data,
        },
        "reports": {
            "summary": submission_summary(duties),
            "obligations": [{"kind": o.kind, "period_start": o.period_start, "status": o.status, "due": o.due,
                             "report_id": o.report_id} for o in duties],
            "recent": [{"id": r.pk, "kind": r.kind, "kind_label": r.get_kind_display(), "period_start": r.period_start,
                        "status": r.status, "status_label": r.get_status_display()} for r in reports],
        },
        "attendance": {"summary": staff.summarize(rows), "days": [staff.serialize_row(r) for r in rows[-31:]]}
        if rows else None,
        "kpi": metrics,
        "history": list(reversed(history)),
        "issues": [{"id": i.pk, "title": i.title, "kind": i.kind, "priority": i.priority, "status": i.status}
                   for i in issues[:20]],
        "subordinates": _subordinates(user),
    }


def _subordinates(user) -> list[dict]:
    from ..departments import led_department

    department = led_department(user)
    if not department:
        return []
    qs = User.objects.filter(is_active=True, role__in=roles_of(department)).exclude(pk=user.pk).exclude(
        role=user.role).order_by("first_name")
    return [employee_card(u) for u in qs]


def department_overview(f: OpsFilters) -> list[dict]:
    now = timezone.now()
    users_by_dep = defaultdict(list)
    for user in User.objects.filter(is_active=True):
        users_by_dep[department_of(user)].append(user)
    task_rows = Task.objects.exclude(status=TaskStatus.CANCELLED).values("department").annotate(
        open=Count("id", filter=Q(status__in=OPEN_STATUSES)),
        overdue=Count("id", filter=Q(status__in=OPEN_STATUSES, deadline__lt=now)),
        review=Count("id", filter=Q(status=TaskStatus.REVIEW)),
        completed=Count("id", filter=Q(status=TaskStatus.COMPLETED, completed_at__date__range=(f.start, f.end))),
    )
    tasks = {r["department"]: r for r in task_rows}
    issues = dict(OperationalIssue.objects.filter(status__in=ACTIVE_ISSUE_STATUSES).values("department").annotate(
        n=Count("id")).values_list("department", "n"))
    duties = defaultdict(list)
    for item in obligations(f.start, f.end):
        duties[department_of(item.user)].append(item)
    tracked = set(staff.tracked_users())
    attendance = defaultdict(list)
    for row in staff.rows(list(tracked), f.start, f.elapsed_end):
        attendance[department_of(row.user)].append(row)
    result = []
    for key, label in Department.choices:
        t = tasks.get(key, {})
        completion = kpi_registry.task_completion_rate(f.start, f.end, key, None)
        att = staff.summarize(attendance[key]) if attendance[key] else None
        reports = submission_summary(duties[key])
        parts = [v for v in (completion, att and att["attendance_rate"], reports["rate"]) if v is not None]
        result.append({
            "key": key,
            "label": label,
            "employees": len(users_by_dep[key]),
            "tasks": {"open": t.get("open", 0), "overdue": t.get("overdue", 0), "review": t.get("review", 0),
                      "completed": t.get("completed", 0), "completion_rate": completion},
            "attendance_rate": att and att["attendance_rate"],
            "reports": reports,
            "open_issues": issues.get(key, 0),
            # Сводный показатель — среднее имеющихся долей (задачи в срок,
            # посещаемость, сдача отчётов); без данных — None.
            "performance": round(sum(parts) / len(parts), 1) if parts else None,
        })
    return result


# --- Продажи ----------------------------------------------------------------

def sales_overview(f: OpsFilters) -> dict:
    managers = list(User.objects.filter(is_active=True, role=User.Role.SALES_MANAGER).order_by("first_name"))
    tasks = task_counts([m.pk for m in managers])
    duties = defaultdict(list)
    for item in obligations(f.start, f.end, users=managers):
        duties[item.user.pk].append(item)
    period = "daily" if f.days == 1 else ("weekly" if f.days <= 7 else "monthly")
    rows = []
    for manager in managers:
        totals = kpi_registry.sales_totals(f.start, f.end, manager)
        plan = kpi_target_for(manager, "sales", period, f.elapsed_end)
        rows.append({
            **employee_card(manager),
            "funnel": totals,
            "sales_plan": plan,
            "sales_fact": totals.get("sales"),
            "plan_achievement": kpi_registry.achievement(totals.get("sales"), plan, True),
            "tasks": tasks.get(manager.pk, EMPTY_TASKS),
            "reports": submission_summary(duties[manager.pk]),
        })
    department = kpi_registry.sales_totals(f.start, f.end)
    plan = _department_target("sales", Department.SALES, period, f.elapsed_end)
    daily = []
    if department:
        by_day = defaultdict(lambda: defaultdict(float))
        for day, metrics in EmployeeReport.objects.filter(
                kind="daily", period_start__range=(f.start, f.end), status__in=SUBMITTED_STATUSES,
                author__role=User.Role.SALES_MANAGER).values_list("period_start", "metrics"):
            for key in ("leads_processed", "sales", "calls"):
                value = (metrics or {}).get(key)
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    by_day[day][key] += value
        daily = [{"date": day, **values} for day, values in sorted(by_day.items())]
    return {
        "source": "Ежедневные отчёты менеджеров (CRM в LMS не подключена)",
        "crm_connected": False,
        "department": {**department, "sales_plan": plan,
                       "plan_achievement": kpi_registry.achievement(department.get("sales"), plan, True)},
        "managers": rows,
        "daily": daily,
    }


def _department_target(metric, department, period, on):
    from ..models import KPITarget

    target = KPITarget.objects.filter(metric=metric, department=department, employee__isnull=True, period=period,
                                      valid_from__lte=on).filter(Q(valid_to__isnull=True) | Q(valid_to__gte=on)).order_by(
        "-valid_from").first()
    return float(target.target_value) if target else None


def head_of_sales(f: OpsFilters) -> dict:
    """РОП: результаты отдела и его работа как руководителя — планёрки, 1:1,
    проверки качества обработки заявок, решённые ситуации (его ежедневные
    отчёты), проверка отчётов менеджеров, задачи, поставленные команде."""
    heads = list(User.objects.filter(is_active=True, role__in=(User.Role.ROP, User.Role.DOP)).order_by("role"))
    sales = sales_overview(f)
    managers = [m["id"] for m in sales["managers"]]
    result = []
    for head in heads:
        own = defaultdict(float)
        planning_days = reports_count = 0
        for metrics in EmployeeReport.objects.filter(author=head, kind="daily", status__in=SUBMITTED_STATUSES,
                                                     period_start__range=(f.start, f.end)).values_list("metrics",
                                                                                                      flat=True):
            reports_count += 1
            for key, value in (metrics or {}).items():
                if key == "planning_meeting":
                    planning_days += 1 if value else 0
                elif isinstance(value, (int, float)) and not isinstance(value, bool):
                    own[key] += value
        team_reports = EmployeeReport.objects.filter(author_id__in=managers, period_start__range=(f.start, f.end))
        team_tasks = Task.objects.filter(created_by=head, assignee_id__in=managers, created_at__date__range=(
            f.start, f.end))
        result.append({
            **employee_card(head),
            "own_reports": reports_count,
            "planning_meetings": planning_days,
            "one_to_ones": own.get("one_to_ones"),
            "issues_resolved": own.get("issues_resolved"),
            "crm_checks": own.get("crm_checks"),
            "team_reports_reviewed": team_reports.filter(reviewed_by=head).count(),
            "team_reports_waiting": team_reports.filter(status=EmployeeReport.Status.SUBMITTED).count(),
            "team_tasks_created": team_tasks.count(),
            "team_tasks_completed": team_tasks.filter(status=TaskStatus.COMPLETED).count(),
            "tasks": task_counts([head.pk]).get(head.pk, EMPTY_TASKS),
            "reports": submission_summary(obligations(f.start, f.end, users=[head])),
        })
    managers_reports = [m["reports"] for m in sales["managers"]]
    expected = sum(r["expected"] for r in managers_reports)
    return {
        "heads": result,
        "department": sales["department"],
        "managers": sales["managers"],
        "team_report_rate": round(sum(r["submitted"] for r in managers_reports) / expected * 100, 1) if expected else None,
        "crm_connected": False,
    }


# --- Маркетинг и HR ---------------------------------------------------------

def marketing_overview(f: OpsFilters, *, with_budget: bool) -> dict:
    from apps.marketing.models import Campaign, ContentItem, MarketingTask

    today = f.today
    content = ContentItem.objects.filter(publish_date__range=(f.start, f.end))
    due = content.filter(publish_date__lte=today)
    published = content.filter(status=ContentItem.Status.PUBLISHED)
    campaigns_qs = Campaign.objects.filter(start_date__lte=f.end).filter(
        Q(end_date__isnull=True) | Q(end_date__gte=f.start)).select_related("responsible")
    agg = campaigns_qs.aggregate(leads=Sum("leads"), sales=Sum("sales"), budget=Sum("budget"), spent=Sum("spent"))
    campaigns = []
    for c in campaigns_qs:
        row = {"id": c.pk, "name": c.name, "channel": c.get_channel_display(), "status": c.status,
               "status_label": c.get_status_display(), "start_date": c.start_date, "end_date": c.end_date,
               "responsible": c.responsible.get_full_name() if c.responsible else None, "leads": c.leads,
               "sales": c.sales, "conversion": c.conversion, "result": c.result}
        if with_budget:
            row.update(budget=c.budget, spent=c.spent, cost_per_lead=c.cost_per_lead)
        campaigns.append(row)
    tasks = MarketingTask.objects.all()
    summary = {
        "content_planned": content.count(),
        "content_published": published.count(),
        "plan_completion": round(due.filter(status=ContentItem.Status.PUBLISHED).count() / due.count() * 100, 1)
        if due.exists() else None,
        "campaigns": campaigns_qs.count(),
        "campaigns_active": campaigns_qs.filter(status=Campaign.Status.ACTIVE).count(),
        "leads": agg["leads"] or 0,
        "campaign_sales": agg["sales"] or 0,
        "conversion": round((agg["sales"] or 0) / agg["leads"] * 100, 1) if agg["leads"] else None,
        "tasks_open": tasks.filter(status__in=MarketingTask.OPEN_STATUSES).count(),
        "tasks_overdue": tasks.filter(status__in=MarketingTask.OPEN_STATUSES, due_date__lt=today).count(),
        "tasks_done": tasks.filter(status=MarketingTask.Status.DONE, completed_at__date__range=(f.start, f.end)).count(),
    }
    if with_budget:
        summary.update(budget=agg["budget"] or 0, spent=agg["spent"] or 0,
                       cost_per_lead=round(float(agg["spent"]) / agg["leads"], 2) if agg["leads"] else None)
    calendar = [{"id": c.pk, "title": c.title, "date": c.publish_date, "channel": c.get_channel_display(),
                 "status": c.status, "status_label": c.get_status_display(),
                 "responsible": c.responsible.get_full_name() if c.responsible else None}
                for c in content.select_related("responsible").order_by("publish_date", "publish_time")[:200]]
    team = list(User.objects.filter(is_active=True, role=User.Role.MARKETING))
    return {"summary": summary, "campaigns": campaigns, "calendar": calendar, "budget_visible": with_budget,
            "team": [{**employee_card(u), "tasks": task_counts([u.pk]).get(u.pk, EMPTY_TASKS),
                      "content_published": published.filter(responsible=u).count()} for u in team]}


def hr_overview(f: OpsFilters) -> dict:
    """HR: численность, новые сотрудники, вакансии и воронка найма, задачи HR.
    Зарплатные данные сюда не входят. Документы сотрудников и адаптация в LMS
    не ведутся — вопрос к руководству (docs/operations.md)."""
    from apps.recruitment.models import Application, Interview, Vacancy

    users = User.objects.filter(is_active=True)
    joined = User.objects.filter(date_joined__date__range=(f.start, f.end))
    applications = Application.objects.filter(applied_on__range=(f.start, f.end))
    funnel = {row["status"]: row["n"] for row in applications.values("status").annotate(n=Count("id"))}
    hr_team = list(User.objects.filter(is_active=True, role=User.Role.HR_MANAGER))
    return {
        "active_employees": users.count(),
        "inactive_employees": User.objects.filter(is_active=False).count(),
        "new_employees": [employee_card(u) for u in joined.order_by("-date_joined")[:50]],
        "new_employees_count": joined.count(),
        "by_department": [{"key": key, "label": label, "count": sum(1 for u in users if department_of(u) == key)}
                          for key, label in Department.choices],
        "vacancies": {
            "open": Vacancy.objects.filter(status=Vacancy.Status.PUBLISHED).count(),
            "draft": Vacancy.objects.filter(status=Vacancy.Status.DRAFT).count(),
            "paused": Vacancy.objects.filter(status=Vacancy.Status.PAUSED).count(),
        },
        "recruitment": {
            "applications": applications.count(),
            "funnel": [{"status": key, "label": label, "count": funnel.get(key, 0)}
                       for key, label in Application.Status.choices],
            "interviews": Interview.objects.filter(scheduled_at__date__range=(f.start, f.end)).count(),
            "hired": kpi_registry.hires(f.start, f.end),
        },
        "team": [{**employee_card(u), "tasks": task_counts([u.pk]).get(u.pk, EMPTY_TASKS)} for u in hr_team],
        "onboarding_tracked": False,
        "documents_tracked": False,
    }
