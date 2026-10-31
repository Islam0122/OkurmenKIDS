"""Отчёты сотрудников: периоды, схемы показателей по ролям, сдача и проверка,
контроль «отчёт не сдан».

Обязательность отчёта не зашита в код: какие роли сдают какие отчёты, задаёт
руководство (OperationsSettings.required_reports). Пока правило не задано,
несданный отчёт не считается нарушением. Отчёт считается просроченным только
после срока сдачи (конец периода + `daily_report_due`): до этого его ещё не
должны были сдать.

Team Lead пишет отчёты в рабочем журнале (worklog.TeamLeadReport) — они и
учитываются; здесь второго журнала для него нет.
"""
from __future__ import annotations

import calendar
import datetime as dt
from dataclasses import dataclass
from zoneinfo import ZoneInfo

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from apps.users.models import User

from ..departments import department_of
from ..models import EmployeeReport, NotificationKind, OperationsSettings, ReportKind
from ..permissions import can_review_report
from .notifications import notify

R = User.Role
SUBMITTED_STATUSES = (EmployeeReport.Status.SUBMITTED, EmployeeReport.Status.ACCEPTED, EmployeeReport.Status.RETURNED)


def _int(key, label):
    return {"key": key, "label": label, "type": "int"}


# Числа, которых в LMS ещё нет: CRM не подключена, поэтому воронку продаж
# менеджер вносит в ежедневный отчёт. Остальные роли пишут текст — их цифры
# (журнал, посещаемость, контент, найм) LMS считает сама.
METRIC_SCHEMAS: dict[str, list[dict]] = {
    R.SALES_MANAGER: [
        _int("leads_new", "Новые заявки"),
        _int("leads_processed", "Обработано заявок"),
        _int("calls", "Звонки"),
        _int("meetings", "Встречи"),
        _int("trials_scheduled", "Записано на пробный урок"),
        _int("trials_attended", "Пришли на пробный урок"),
        _int("sales", "Продажи"),
        {"key": "revenue", "label": "Выручка, сом", "type": "money"},
    ],
    R.ROP: [
        {"key": "planning_meeting", "label": "Планёрка проведена", "type": "bool"},
        _int("one_to_ones", "Встречи с менеджерами 1:1"),
        _int("issues_resolved", "Решено проблемных ситуаций"),
        _int("crm_checks", "Проверок качества обработки заявок"),
    ],
    R.ASSISTANT: [
        _int("parents_contacted", "Связь с родителями"),
        _int("absences_followed_up", "Отработано пропусков"),
        _int("tables_updated", "Обновлено рабочих таблиц"),
    ],
}
METRIC_SCHEMAS[R.DOP] = METRIC_SCHEMAS[R.ROP]


def metric_schema(role: str) -> list[dict]:
    return METRIC_SCHEMAS.get(role, [])


def normalize_period(kind: str, day: dt.date) -> tuple[dt.date, dt.date]:
    if kind == ReportKind.WEEKLY:
        start = day - dt.timedelta(days=day.weekday())
        return start, start + dt.timedelta(days=6)
    if kind == ReportKind.MONTHLY:
        return day.replace(day=1), day.replace(day=calendar.monthrange(day.year, day.month)[1])
    return day, day


def due_at(kind: str, period_start: dt.date, config: OperationsSettings) -> dt.datetime:
    _, end = normalize_period(kind, period_start)
    return dt.datetime.combine(end, config.daily_report_due, tzinfo=ZoneInfo(settings.TIME_ZONE))


# --- Сдача и проверка --------------------------------------------------------

def save_report(author, data: dict, instance: EmployeeReport | None = None) -> EmployeeReport:
    if instance is not None:
        if instance.author_id != author.pk:
            raise PermissionDenied("Изменять отчёт может только его автор.")
        if instance.status in (EmployeeReport.Status.SUBMITTED, EmployeeReport.Status.ACCEPTED):
            raise ValidationError({"detail": "Сданный отчёт не редактируется."})
        for field, value in data.items():
            setattr(instance, field, value)
        instance.save()
        return instance
    if EmployeeReport.objects.filter(author=author, kind=data["kind"], period_start=data["period_start"]).exists():
        raise ValidationError({"period_start": "Отчёт за этот период уже есть — откройте его."})
    return EmployeeReport.objects.create(author=author, department=department_of(author), **data)


@transaction.atomic
def submit_report(author, report: EmployeeReport) -> EmployeeReport:
    report = EmployeeReport.objects.select_for_update().get(pk=report.pk)
    if report.author_id != author.pk:
        raise PermissionDenied("Сдать отчёт может только его автор.")
    if report.status in (EmployeeReport.Status.SUBMITTED, EmployeeReport.Status.ACCEPTED):
        raise ValidationError({"detail": "Отчёт уже сдан."})
    if not (report.done.strip() or report.metrics):
        raise ValidationError({"done": "Опишите, что сделано, или заполните показатели."})
    report.status = EmployeeReport.Status.SUBMITTED
    report.submitted_at = timezone.now()
    report.save(update_fields=["status", "submitted_at", "updated_at"])
    return report


@transaction.atomic
def review_report(reviewer, report: EmployeeReport, accept: bool, comment: str = "") -> EmployeeReport:
    report = EmployeeReport.objects.select_for_update().select_related("author").get(pk=report.pk)
    if not can_review_report(reviewer, report):
        raise PermissionDenied("Проверить отчёт может руководитель отдела или операционный директор.")
    if report.status != EmployeeReport.Status.SUBMITTED:
        raise ValidationError({"detail": "Проверить можно только сданный отчёт."})
    comment = (comment or "").strip()
    if not accept and not comment:
        raise ValidationError({"comment": "Укажите, что исправить."})
    report.status = EmployeeReport.Status.ACCEPTED if accept else EmployeeReport.Status.RETURNED
    report.reviewed_by, report.reviewed_at, report.review_comment = reviewer, timezone.now(), comment
    report.save(update_fields=["status", "reviewed_by", "reviewed_at", "review_comment", "updated_at"])
    if not accept:
        notify(report.author, NotificationKind.REPORT_RETURNED, f"report:{report.pk}:returned:{report.reviewed_at:%s}",
               f"Отчёт возвращён: {report.get_kind_display().lower()} за {report.period_start:%d.%m.%Y}", comment,
               "/work-reports")
    return report


# --- Контроль сдачи ----------------------------------------------------------

@dataclass
class Obligation:
    user: object
    kind: str
    period_start: dt.date
    period_end: dt.date
    due: dt.datetime
    status: str  # submitted | missing | pending (срок ещё не наступил)
    report_id: int | None = None
    source: str = "operations"  # operations | worklog


def _periods(kind: str, start: dt.date, end: dt.date) -> list[dt.date]:
    periods, day = [], normalize_period(kind, start)[0]
    while day <= end:
        periods.append(day)
        day = normalize_period(kind, day)[1] + dt.timedelta(days=1)
    return periods


def _worklog_reports(user_ids, start, end) -> dict[tuple, int]:
    from apps.worklog.models import TeamLeadReport

    found = {}
    for row in TeamLeadReport.objects.filter(author_id__in=user_ids, kind__in=ReportKind.values,
                                             date__range=(start, end)).exclude(status="draft").values(
            "id", "author_id", "kind", "date"):
        found[(row["author_id"], row["kind"], normalize_period(row["kind"], row["date"])[0])] = row["id"]
    return found


def obligations(start: dt.date, end: dt.date, *, users=None, now: dt.datetime | None = None,
                config: OperationsSettings | None = None) -> list[Obligation]:
    """Все обязательные отчёты сотрудников за период [start, end] и их
    состояние. Дни до найма сотрудника не учитываются."""
    config = config or OperationsSettings.load()
    now = now or timezone.now()
    rules = {role: config.required_kinds(role) for role in (config.required_reports or {})}
    if not any(rules.values()):
        return []
    users = list(users if users is not None else User.objects.filter(is_active=True, role__in=list(rules)))
    users = [u for u in users if rules.get(u.role)]
    if not users:
        return []
    ids = [u.pk for u in users]
    lookup_start = normalize_period(ReportKind.MONTHLY, start)[0]
    submitted = {
        (r["author_id"], r["kind"], r["period_start"]): r["id"]
        for r in EmployeeReport.objects.filter(author_id__in=ids, status__in=SUBMITTED_STATUSES,
                                               period_start__range=(lookup_start, end)).values(
            "id", "author_id", "kind", "period_start")
    }
    worklog = _worklog_reports([u.pk for u in users if u.role == R.TEAM_LEAD], lookup_start, end)
    result = []
    for user in users:
        joined = timezone.localtime(user.date_joined).date() if user.date_joined else start
        for kind in rules[user.role]:
            for period_start in _periods(kind, start, end):
                period_end = normalize_period(kind, period_start)[1]
                if period_end < joined:
                    continue
                key = (user.pk, kind, period_start)
                report_id = worklog.get(key) if user.role == R.TEAM_LEAD else submitted.get(key)
                due = due_at(kind, period_start, config)
                status = "submitted" if report_id else ("missing" if now > due else "pending")
                result.append(Obligation(user, kind, period_start, period_end, due, status, report_id,
                                         "worklog" if user.role == R.TEAM_LEAD else "operations"))
    return result


def submission_summary(items: list[Obligation]) -> dict:
    due = [o for o in items if o.status != "pending"]
    submitted = sum(1 for o in due if o.status == "submitted")
    return {
        "expected": len(due),
        "submitted": submitted,
        "missing": len(due) - submitted,
        "pending": len(items) - len(due),
        "rate": round(submitted / len(due) * 100, 1) if due else None,
    }
