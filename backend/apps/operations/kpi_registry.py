"""Реестр KPI-показателей операционного модуля.

Факт каждого показателя считается из существующих данных LMS. Ни один
норматив не зашит: цель задаёт руководство (models.KPITarget); без цели
показатель отображается без «достижения» и не порождает нарушений.

* Академия — KPI тренеров из `academy.services.kpi_engine` (единственный
  источник KPI в LMS) и заполнение журналов из сервиса «Контроль».
* Все отделы — выполнение задач в срок, сдача отчётов, посещаемость.
* Продажи — ежедневные отчёты менеджеров (CRM в LMS нет).
* Маркетинг — контент-план и кампании (apps.marketing).
* HR — найм (apps.recruitment).

`compute(start, end, department, employee)` возвращает число или None
(«нет данных» — никогда не выдуманный 0).
"""
from __future__ import annotations

import datetime as dt
from collections.abc import Callable
from dataclasses import dataclass, field

from django.db.models import Count, Q, Sum
from django.utils import timezone

from .departments import Department, roles_of

PERCENT, COUNT, MONEY, MINUTES = "percent", "count", "money", "minutes"


@dataclass(frozen=True)
class Metric:
    key: str
    label: str
    unit: str
    compute: Callable
    departments: tuple[str, ...] = ()  # пусто — любой отдел
    higher_is_better: bool = True
    department_level: bool = True
    employee_level: bool = True
    financial: bool = False
    source: str = ""
    roles: tuple[str, ...] = field(default=())  # кому из сотрудников показатель применим


def _users(department: str | None, employee):
    from apps.users.models import User

    if employee is not None:
        return [employee]
    qs = User.objects.filter(is_active=True)
    if department:
        qs = qs.filter(role__in=roles_of(department))
    return list(qs)


def _pct(part, whole):
    return round(part / whole * 100, 1) if whole else None


# --- Задачи и отчёты (все отделы) -------------------------------------------

def _tasks_qs(department, employee):
    from .models import Task

    qs = Task.objects.exclude(status="cancelled")
    if employee is not None:
        return qs.filter(assignee=employee)
    return qs.filter(department=department) if department else qs


def task_completion_rate(start, end, department=None, employee=None):
    """Выполнено в срок / задач с дедлайном в периоде, срок которых уже прошёл."""
    from django.db.models import F

    now = timezone.now()
    qs = _tasks_qs(department, employee).filter(deadline__date__range=(start, end), deadline__lt=now)
    agg = qs.aggregate(total=Count("id"),
                       on_time=Count("id", filter=Q(status="completed", completed_at__lte=F("deadline"))))
    return _pct(agg["on_time"], agg["total"])


def tasks_completed(start, end, department=None, employee=None):
    return _tasks_qs(department, employee).filter(status="completed", completed_at__date__range=(start, end)).count()


def tasks_overdue(start, end, department=None, employee=None):
    from .models import OPEN_STATUSES

    return _tasks_qs(department, employee).filter(status__in=OPEN_STATUSES, deadline__lt=timezone.now(),
                                                  deadline__date__lte=end).count()


def report_submission_rate(start, end, department=None, employee=None):
    from .services.reports import obligations, submission_summary

    return submission_summary(obligations(start, end, users=_users(department, employee)))["rate"]


def staff_attendance_rate(start, end, department=None, employee=None):
    from .services import staff

    users = [u for u in _users(department, employee) if u in staff.tracked_users()] if employee is None else [employee]
    return staff.summarize(staff.rows(users, start, min(end, timezone.localdate())))["attendance_rate"]


def late_minutes(start, end, department=None, employee=None):
    from .services import staff

    users = _users(department, employee)
    if not users:
        return None
    return staff.summarize(staff.rows(users, start, min(end, timezone.localdate())))["late_minutes"]


# --- Академия ---------------------------------------------------------------

def _teacher_id(employee):
    teacher = getattr(employee, "teacher_profile", None) if employee is not None else None
    return teacher.pk if teacher is not None else None


def trainer_kpi(start, end, department=None, employee=None):
    from apps.academy.services.kpi_engine import KPIEngine

    teacher_id = _teacher_id(employee)
    if employee is not None and teacher_id is None:
        return None
    return KPIEngine.calculate(start=start, end=end, teacher_id=teacher_id).total


def _control_summary(start, end, employee):
    from apps.academy.services.control import ControlQuery, ControlService
    from apps.academy.services.reports import ReportFilters

    teacher_id = _teacher_id(employee)
    if employee is not None and teacher_id is None:
        return None
    filters = ReportFilters.from_query({"period": "custom", "start_date": start.isoformat(),
                                        "end_date": end.isoformat(), "teacher": teacher_id or ""})
    service = ControlService(ControlQuery(filters=filters))
    return service.summary(service.rows(service.evaluate()))


def journal_completion(start, end, department=None, employee=None):
    summary = _control_summary(start, end, employee)
    if summary is None:
        return None
    return _pct(summary["completed_lessons"], summary["total_lessons"])


def attendance_marking(start, end, department=None, employee=None):
    summary = _control_summary(start, end, employee)
    return summary and summary["attendance_completion"]


def homework_check(start, end, department=None, employee=None):
    summary = _control_summary(start, end, employee)
    return summary and summary["homework_completion"]


# --- Продажи (ежедневные отчёты менеджеров) ---------------------------------

def _sales_sum(key):
    def compute(start, end, department=None, employee=None):
        return sales_totals(start, end, employee).get(key)
    return compute


def sales_totals(start, end, employee=None) -> dict:
    """Сумма показателей ежедневных отчётов менеджеров по продажам за период
    (только сданные отчёты). Нет отчётов — пустой словарь (нет данных)."""
    from apps.users.models import User

    from .models import EmployeeReport
    from .services.reports import SUBMITTED_STATUSES

    qs = EmployeeReport.objects.filter(kind="daily", period_start__range=(start, end), status__in=SUBMITTED_STATUSES)
    qs = qs.filter(author=employee) if employee is not None else qs.filter(author__role=User.Role.SALES_MANAGER)
    totals: dict[str, float] = {}
    reports = 0
    for metrics in qs.values_list("metrics", flat=True):
        reports += 1
        for key, value in (metrics or {}).items():
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                totals[key] = totals.get(key, 0) + value
    if not reports:
        return {}
    totals["reports"] = reports
    processed = totals.get("leads_processed", 0)
    totals["conversion"] = _pct(totals.get("sales", 0), processed)
    totals["trial_attendance"] = _pct(totals.get("trials_attended", 0), totals.get("trials_scheduled", 0))
    return totals


# --- Маркетинг и HR ---------------------------------------------------------

def content_published(start, end, department=None, employee=None):
    from apps.marketing.models import ContentItem

    qs = ContentItem.objects.filter(status="published", published_at__date__range=(start, end))
    return (qs.filter(responsible=employee) if employee is not None else qs).count()


def _campaigns(start, end, employee):
    from apps.marketing.models import Campaign

    qs = Campaign.objects.filter(start_date__lte=end).filter(Q(end_date__isnull=True) | Q(end_date__gte=start))
    return qs.filter(responsible=employee) if employee is not None else qs


def campaign_leads(start, end, department=None, employee=None):
    return _campaigns(start, end, employee).aggregate(total=Sum("leads"))["total"]


def cost_per_lead(start, end, department=None, employee=None):
    agg = _campaigns(start, end, employee).aggregate(spent=Sum("spent"), leads=Sum("leads"))
    return round(float(agg["spent"]) / agg["leads"], 2) if agg["leads"] else None


def hires(start, end, department=None, employee=None):
    from apps.recruitment.models import Application

    qs = Application.objects.filter(status="hired", status_changed_at__date__range=(start, end))
    return (qs.filter(responsible=employee) if employee is not None else qs).count()


SALES, MARKETING, HR, ACADEMY = Department.SALES, Department.MARKETING, Department.HR, Department.ACADEMY
TEACHER = ("teacher",)

METRICS: dict[str, Metric] = {m.key: m for m in [
    Metric("task_completion_rate", "Задачи выполнены в срок", PERCENT, task_completion_rate, source="Задачи"),
    Metric("tasks_completed", "Выполнено задач", COUNT, tasks_completed, source="Задачи"),
    Metric("tasks_overdue", "Просроченные задачи", COUNT, tasks_overdue, higher_is_better=False, source="Задачи"),
    Metric("report_submission_rate", "Сдача отчётов", PERCENT, report_submission_rate, source="Отчёты"),
    Metric("staff_attendance_rate", "Посещаемость сотрудников", PERCENT, staff_attendance_rate,
           source="Учёт прихода и ухода"),
    Metric("late_minutes", "Опоздания, мин", MINUTES, late_minutes, higher_is_better=False,
           source="Учёт прихода и ухода"),
    Metric("trainer_kpi", "KPI тренеров", PERCENT, trainer_kpi, departments=(ACADEMY,), roles=TEACHER,
           source="KPI Engine академии"),
    Metric("journal_completion", "Журнал заполнен", PERCENT, journal_completion, departments=(ACADEMY,),
           roles=TEACHER, source="Контроль занятий"),
    Metric("attendance_marking", "Посещаемость отмечена", PERCENT, attendance_marking, departments=(ACADEMY,),
           roles=TEACHER, source="Контроль занятий"),
    Metric("homework_check", "ДЗ проверены", PERCENT, homework_check, departments=(ACADEMY,), roles=TEACHER,
           source="Контроль занятий"),
    Metric("leads_processed", "Обработано заявок", COUNT, _sales_sum("leads_processed"), departments=(SALES,),
           roles=("sales_manager",), source="Ежедневные отчёты продаж"),
    Metric("calls", "Звонки", COUNT, _sales_sum("calls"), departments=(SALES,), roles=("sales_manager",),
           source="Ежедневные отчёты продаж"),
    Metric("trials_attended", "Пробные уроки (пришли)", COUNT, _sales_sum("trials_attended"), departments=(SALES,),
           roles=("sales_manager",), source="Ежедневные отчёты продаж"),
    Metric("sales", "Продажи", COUNT, _sales_sum("sales"), departments=(SALES,), roles=("sales_manager",),
           source="Ежедневные отчёты продаж"),
    Metric("conversion", "Конверсия заявок в продажи", PERCENT, _sales_sum("conversion"), departments=(SALES,),
           roles=("sales_manager",), source="Ежедневные отчёты продаж"),
    Metric("revenue", "Выручка", MONEY, _sales_sum("revenue"), departments=(SALES,), roles=("sales_manager",),
           financial=True, source="Ежедневные отчёты продаж"),
    Metric("content_published", "Опубликовано материалов", COUNT, content_published, departments=(MARKETING,),
           roles=("marketing",), source="Контент-план"),
    Metric("campaign_leads", "Лиды кампаний", COUNT, campaign_leads, departments=(MARKETING,), roles=("marketing",),
           source="Рекламные кампании"),
    Metric("cost_per_lead", "Стоимость лида (CPL)", MONEY, cost_per_lead, departments=(MARKETING,),
           roles=("marketing",), higher_is_better=False, financial=True, source="Рекламные кампании"),
    Metric("hires", "Принято на работу", COUNT, hires, departments=(HR,), roles=("hr_manager",), source="Найм"),
]}


def metrics_for(department: str | None = None, role: str | None = None) -> list[Metric]:
    result = []
    for metric in METRICS.values():
        if department and metric.departments and department not in metric.departments:
            continue
        if role and metric.roles and role not in metric.roles:
            continue
        result.append(metric)
    return result


def describe(metric: Metric) -> dict:
    return {"key": metric.key, "label": metric.label, "unit": metric.unit, "departments": list(metric.departments),
            "higher_is_better": metric.higher_is_better, "department_level": metric.department_level,
            "employee_level": metric.employee_level, "financial": metric.financial, "source": metric.source,
            "roles": list(metric.roles)}


def achievement(actual, target, higher_is_better: bool) -> float | None:
    if actual is None or target is None:
        return None
    target, actual = float(target), float(actual)
    if higher_is_better:
        return round(actual / target * 100, 1) if target else None
    if actual == 0:
        return 100.0 if target >= 0 else None
    return round(target / actual * 100, 1)


__all__ = ["METRICS", "Metric", "achievement", "describe", "metrics_for", "sales_totals", "dt"]
