"""Attention Required — автоматический поиск проблем.

Каждый детектор возвращает найденные проблемы с ключом (`fingerprint`) и
область, которую он проверил. Затем:

* новой проблемы нет в базе — создаётся (+ событие «Обнаружена» и
  уведомление ответственному);
* открытая проблема найдена снова — обновляется `last_seen_at` (дубля нет,
  уведомления повторно не шлются);
* решённая проблема найдена снова — открывается заново, `reopen_count`
  растёт: это повторное нарушение;
* отклонённую вручную проблему детектор не открывает;
* открытая автоматическая проблема в проверенной области больше не найдена —
  закрывается («Устранена (проверка)»).

Ничего не считается нарушением раньше срока: Контроль занятий учитывает
только прошедшие занятия и истёкшие сроки ДЗ, отчёт — только после срока
сдачи, отсутствие прихода — только после конца рабочего дня, KPI-счётчики —
только за завершённый период.
"""
from __future__ import annotations

import datetime as dt
import logging
from collections import defaultdict
from dataclasses import dataclass, field

from django.db import transaction
from django.utils import timezone

from apps.academy.services.control import rules as control_rules
from apps.users.models import Teacher

from .. import kpi_registry
from ..departments import Department, department_of
from ..models import (
    ACTIVE_ISSUE_STATUSES,
    OPEN_STATUSES,
    IssueEvent,
    IssueKind,
    IssueStatus,
    KPITarget,
    NotificationKind,
    OperationalIssue,
    OperationsSettings,
    Priority,
    Task,
)
from . import staff
from .academy import control_service, problem_groups, problem_students_for
from .period import OpsFilters
from .reports import obligations
from .notifications import notify

logger = logging.getLogger(__name__)
CONTROL_LOOKBACK_DAYS = 7
REPORT_LOOKBACK_DAYS = 7


@dataclass
class Found:
    fingerprint: str
    kind: str
    title: str
    department: str
    description: str = ""
    priority: str = Priority.MEDIUM
    responsible: object = None
    object_type: str = ""
    object_id: int | None = None
    link: str = ""
    payload: dict = field(default_factory=dict)


@dataclass
class Detection:
    kind: str
    found: list[Found]
    covers: object = None  # callable(issue) -> bool; None — все проблемы этого вида


def _plural(n: int, one: str, few: str, many: str) -> str:
    if n % 10 == 1 and n % 100 != 11:
        return one
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return few
    return many


def detect_overdue_tasks(now) -> Detection:
    found = []
    for task in Task.objects.filter(status__in=OPEN_STATUSES, deadline__lt=now).select_related("assignee",
                                                                                               "created_by"):
        days = (now - task.deadline).days
        priority = task.priority if task.priority in (Priority.HIGH, Priority.CRITICAL) else (
            Priority.HIGH if days >= 3 else Priority.MEDIUM)
        found.append(Found(
            f"task_overdue:{task.pk}", IssueKind.TASK_OVERDUE, f"Просрочена задача «{task.title}»", task.department,
            f"Дедлайн: {timezone.localtime(task.deadline):%d.%m.%Y %H:%M}. Исполнитель: "
            f"{task.assignee or 'не назначен'}.", priority, task.assignee or task.created_by, "task", task.pk,
            f"/tasks/{task.pk}", {"deadline": task.deadline.isoformat()}))
    return Detection(IssueKind.TASK_OVERDUE, found)


def detect_missing_reports(now, today, config) -> Detection:
    start = today - dt.timedelta(days=REPORT_LOOKBACK_DAYS)
    found = []
    for item in obligations(start, today, now=now, config=config):
        if item.status != "missing":
            continue
        found.append(Found(
            f"report_missing:{item.user.pk}:{item.kind}:{item.period_start}", IssueKind.REPORT_MISSING,
            f"Не сдан отчёт: {item.user.get_full_name() or item.user.username}", department_of(item.user),
            f"{dict(_REPORT_LABELS)[item.kind]} за {item.period_start:%d.%m.%Y}"
            + (f" — {item.period_end:%d.%m.%Y}" if item.period_end != item.period_start else "")
            + f", срок — {timezone.localtime(item.due):%d.%m.%Y %H:%M}.",
            Priority.MEDIUM, item.user, "user", item.user.pk, "/work-reports",
            {"kind": item.kind, "period_start": item.period_start.isoformat()}))
    return Detection(IssueKind.REPORT_MISSING, found,
                     covers=lambda issue: issue.payload.get("period_start", "") >= start.isoformat())


_REPORT_LABELS = (("daily", "Ежедневный отчёт"), ("weekly", "Еженедельный отчёт"), ("monthly", "Ежемесячный отчёт"))


def detect_lesson_control(today) -> list[Detection]:
    """Журнал, посещаемость и ДЗ за последние дни — по тренеру. Одна
    проблема на тренера и вид: пока есть незаполненное, проблема открыта;
    всё заполнено — закрывается; снова пропустил — повторное нарушение."""
    f = OpsFilters("custom", today - dt.timedelta(days=CONTROL_LOOKBACK_DAYS), today, today)
    checks = control_service(f).evaluate()
    journal, attendance, homework = defaultdict(list), defaultdict(list), defaultdict(list)
    teachers = {}
    for check in checks:
        if not check.is_due:
            continue
        teacher = check.lesson.effective_teacher
        if teacher is None:
            continue
        teachers[teacher.id] = teacher
        if not check.closed:
            journal[teacher.id].append(check)
        if check.attendance_counts and not check.attendance_ok:
            attendance[teacher.id].append(check)
        if check.homework_state == control_rules.COMPONENT_UNCHECKED:
            homework[teacher.id].append(check)
    users = {t.id: t.user for t in Teacher.objects.filter(id__in=teachers).select_related("user")}

    def build(kind, groups, title, what):
        found = []
        for teacher_id, items in groups.items():
            n = len(items)
            dates = ", ".join(sorted({f"{c.lesson.date:%d.%m}" for c in items}))
            found.append(Found(
                f"{kind}:teacher:{teacher_id}", kind, f"{title}: {teachers[teacher_id]}", Department.ACADEMY,
                f"{what} — {n} {_plural(n, 'занятие', 'занятия', 'занятий')} ({dates}).",
                Priority.HIGH if n >= 3 else Priority.MEDIUM, users.get(teacher_id), "teacher", teacher_id,
                f"/operations/trainers/{teacher_id}", {"lessons": [c.lesson.id for c in items]}))
        return Detection(kind, found)

    return [
        build(IssueKind.JOURNAL_NOT_FILLED, journal, "Журнал не заполнен", "Не закрыто"),
        build(IssueKind.ATTENDANCE_NOT_MARKED, attendance, "Посещаемость не отмечена", "Без отметок"),
        build(IssueKind.HOMEWORK_NOT_CHECKED, homework, "ДЗ не проверено", "Ждут проверки"),
    ]


def _period_bounds(period: str, day: dt.date) -> tuple[dt.date, dt.date]:
    from .reports import normalize_period

    return normalize_period(period, day)


def detect_kpi(today) -> Detection:
    """KPI ниже цели. Доли (%) — за текущий период; счётчики и суммы — только
    за завершённый прошлый период (середина месяца — ещё не провал плана)."""
    found = []
    for target in KPITarget.objects.filter(valid_from__lte=today).exclude(valid_to__lt=today).select_related("employee"):
        metric = kpi_registry.METRICS.get(target.metric)
        if metric is None or (target.employee is not None and not target.employee.is_active):
            continue
        if metric.unit == kpi_registry.PERCENT:
            start, end = _period_bounds(target.period, today)
        else:
            start, end = _period_bounds(target.period, _period_bounds(target.period, today)[0] - dt.timedelta(days=1))
            if start < target.valid_from:
                continue
        actual = metric.compute(start, end, target.department, target.employee)
        level = kpi_registry.achievement(actual, target.target_value, metric.higher_is_better)
        if level is None or level >= 100:
            continue
        who = target.employee.get_full_name() if target.employee else Department(target.department).label
        found.append(Found(
            f"kpi:{target.pk}:{start}", IssueKind.KPI_BELOW_TARGET, f"KPI ниже цели: {metric.label} — {who}",
            target.department, f"Факт {actual} при цели {target.target_value} ({level}%) за {start:%d.%m} — "
            f"{end:%d.%m.%Y}.", Priority.HIGH if level < 70 else Priority.MEDIUM, target.employee, "kpi_target",
            target.pk, "/operations/kpi", {"actual": actual, "achievement": level, "period_start": start.isoformat()}))
    return Detection(IssueKind.KPI_BELOW_TARGET, found)


def detect_problem_groups(today, config) -> Detection:
    f = OpsFilters("this_month", today.replace(day=1), today, today)
    found = [Found(f"problem_group:{g['id']}:{today:%Y-%m}", IssueKind.PROBLEM_GROUP,
                   f"Проблемная группа: {g['name']}", Department.ACADEMY,
                   f"{g['reason']}. Посещаемость: {g['attendance_rate']}%, KPI: {g['kpi']}.", Priority.MEDIUM, None,
                   "group", g["id"], "/operations/trainers", {"month": f"{today:%Y-%m}"})
             for g in problem_groups(f, config.problem_group_attendance)]
    return Detection(IssueKind.PROBLEM_GROUP, found,
                     covers=lambda issue: issue.payload.get("month") == f"{today:%Y-%m}")


def detect_student_absences(today) -> Detection:
    f = OpsFilters("custom", today - dt.timedelta(days=29), today, today)
    found = []
    for row in problem_students_for(f):
        if "frequent_absence" not in row["categories"]:
            continue
        group = (row.get("group") or {}).get("name", "—")
        found.append(Found(
            f"student_absences:{row['student_id']}", IssueKind.STUDENT_ABSENCES,
            f"Частые пропуски: {row['name']}", Department.ACADEMY,
            f"Группа {group}: {row['absent']} пропусков за 30 дней, подряд — {row['consecutive_absences']}.",
            Priority.HIGH if row["status"] == "risk" else Priority.MEDIUM, None, "student", row["student_id"],
            f"/operations/students?student={row['student_id']}", {}))
    return Detection(IssueKind.STUDENT_ABSENCES, found)


def detect_staff_absence(today, config) -> Detection:
    """Нет прихода в рабочий день — только за прошедшие дни (вчера и раньше
    в пределах недели): сегодня рабочее время ещё может идти."""
    start, end = today - dt.timedelta(days=7), today - dt.timedelta(days=1)
    if not config.detect_staff_absence:
        return Detection(IssueKind.STAFF_ABSENCE, [],
                         covers=lambda issue: issue.payload.get("date", "") >= start.isoformat())
    found = []
    for row in staff.rows(staff.tracked_users(), start, end):
        if staff.ops_status(row) != staff.ABSENT:
            continue
        found.append(Found(
            f"staff_absence:{row.user.pk}:{row.day}", IssueKind.STAFF_ABSENCE,
            f"Нет отметки прихода: {row.user.get_full_name() or row.user.username}", department_of(row.user),
            f"{row.day:%d.%m.%Y} — рабочий день по расписанию, отметки прихода нет.", Priority.LOW, row.user, "user",
            row.user.pk, "/operations/attendance", {"date": row.day.isoformat()}))
    return Detection(IssueKind.STAFF_ABSENCE, found, covers=lambda issue: issue.payload.get("date", "") >= start.isoformat())


# --- Применение ----------------------------------------------------------------

def _event(issue, action, *, actor=None, from_status="", to_status="", comment=""):
    IssueEvent.objects.create(issue=issue, actor=actor, action=action, from_status=from_status, to_status=to_status,
                              comment=comment)


def _notify(issue: OperationalIssue):
    if issue.responsible is None:
        return
    kind = NotificationKind.KPI_BELOW_TARGET if issue.kind == IssueKind.KPI_BELOW_TARGET else (
        NotificationKind.REPORT_MISSING if issue.kind == IssueKind.REPORT_MISSING else NotificationKind.ISSUE_DETECTED)
    link = issue.link if issue.kind in (IssueKind.TASK_OVERDUE, IssueKind.REPORT_MISSING) else ""
    notify(issue.responsible, kind, f"issue:{issue.fingerprint}:{issue.reopen_count}", issue.title,
           issue.description, link)


def apply(detection: Detection, now) -> dict:
    stats = {"created": 0, "reopened": 0, "seen": 0, "resolved": 0}
    seen = set()
    for item in detection.found:
        seen.add(item.fingerprint)
        with transaction.atomic():
            issue = OperationalIssue.objects.select_for_update().filter(fingerprint=item.fingerprint).first()
            if issue is None:
                issue = OperationalIssue.objects.create(
                    kind=item.kind, fingerprint=item.fingerprint, title=item.title[:255], description=item.description,
                    priority=item.priority, department=item.department, responsible=item.responsible,
                    object_type=item.object_type, object_id=item.object_id, link=item.link, payload=item.payload,
                    detected_at=now, last_seen_at=now)
                _event(issue, IssueEvent.Action.DETECTED, to_status=issue.status)
                _notify(issue)
                stats["created"] += 1
                continue
            new_day = timezone.localtime(issue.last_seen_at).date() < timezone.localtime(now).date()
            issue.title, issue.description, issue.payload = item.title[:255], item.description, item.payload
            issue.last_seen_at = now
            if new_day:
                issue.times_detected += 1
            if issue.status == IssueStatus.RESOLVED:
                issue.status, issue.reopen_count, issue.resolved_at, issue.resolved_by = IssueStatus.OPEN, \
                    issue.reopen_count + 1, None, None
                issue.priority = Priority.HIGH if issue.priority in (Priority.LOW, Priority.MEDIUM) else issue.priority
                issue.save()
                _event(issue, IssueEvent.Action.REDETECTED, from_status=IssueStatus.RESOLVED, to_status=IssueStatus.OPEN,
                       comment="Повторное нарушение.")
                _notify(issue)
                stats["reopened"] += 1
                continue
            issue.save()
            stats["seen"] += 1
    stale = OperationalIssue.objects.filter(kind=detection.kind, auto_detected=True,
                                            status__in=ACTIVE_ISSUE_STATUSES).exclude(fingerprint__in=seen)
    for issue in stale:
        if detection.covers is not None and not detection.covers(issue):
            continue
        with transaction.atomic():
            from_status = issue.status
            issue.status, issue.resolved_at = IssueStatus.RESOLVED, now
            issue.save(update_fields=["status", "resolved_at"])
            _event(issue, IssueEvent.Action.AUTO_RESOLVED, from_status=from_status, to_status=IssueStatus.RESOLVED)
            stats["resolved"] += 1
    return stats


def scan(now=None) -> dict:
    """Одна полная проверка. Сбой одного детектора не останавливает остальные."""
    now = now or timezone.now()
    today = timezone.localtime(now).date()
    config = OperationsSettings.load()
    detectors = [
        ("task_overdue", lambda: [detect_overdue_tasks(now)]),
        ("report_missing", lambda: [detect_missing_reports(now, today, config)]),
        ("lesson_control", lambda: detect_lesson_control(today)),
        ("kpi_below_target", lambda: [detect_kpi(today)]),
        ("problem_group", lambda: [detect_problem_groups(today, config)]),
        ("student_absences", lambda: [detect_student_absences(today)]),
        ("staff_absence", lambda: [detect_staff_absence(today, config)]),
    ]
    result = {}
    for name, run in detectors:
        try:
            for detection in run():
                result[detection.kind] = apply(detection, now)
        except Exception as exc:  # noqa: BLE001 — один детектор не должен ронять проверку
            logger.exception("operations: detector %s failed", name)
            result[name] = {"error": str(exc)}
    return result


# --- Ручные действия -----------------------------------------------------------

STATUS_TRANSITIONS = {
    IssueStatus.OPEN: (IssueStatus.IN_PROGRESS, IssueStatus.RESOLVED, IssueStatus.DISMISSED),
    IssueStatus.IN_PROGRESS: (IssueStatus.OPEN, IssueStatus.RESOLVED, IssueStatus.DISMISSED),
    IssueStatus.RESOLVED: (IssueStatus.OPEN,),
    IssueStatus.DISMISSED: (IssueStatus.OPEN,),
}


@transaction.atomic
def change_status(actor, issue: OperationalIssue, status: str, comment: str = "") -> OperationalIssue:
    from rest_framework.exceptions import ValidationError

    issue = OperationalIssue.objects.select_for_update().get(pk=issue.pk)
    if status not in STATUS_TRANSITIONS.get(issue.status, ()):
        raise ValidationError({"status": "Недопустимая смена статуса."})
    if status == IssueStatus.DISMISSED and not (comment or "").strip():
        raise ValidationError({"comment": "Укажите, почему проблема отклонена."})
    from_status = issue.status
    issue.status = status
    if status == IssueStatus.RESOLVED:
        issue.resolved_at, issue.resolved_by = timezone.now(), actor
    elif status == IssueStatus.OPEN:
        issue.resolved_at = issue.resolved_by = None
    issue.save()
    _event(issue, IssueEvent.Action.STATUS, actor=actor, from_status=from_status, to_status=status, comment=comment)
    return issue


@transaction.atomic
def assign(actor, issue: OperationalIssue, responsible) -> OperationalIssue:
    issue.responsible = responsible
    issue.save(update_fields=["responsible"])
    _event(issue, IssueEvent.Action.ASSIGNED, actor=actor, comment=str(responsible) if responsible else "—")
    _notify(issue)
    return issue


def comment(actor, issue: OperationalIssue, text: str) -> IssueEvent:
    from rest_framework.exceptions import ValidationError

    text = (text or "").strip()
    if not text:
        raise ValidationError({"text": "Комментарий не может быть пустым."})
    return IssueEvent.objects.create(issue=issue, actor=actor, action=IssueEvent.Action.COMMENT, comment=text)


def create_manual(actor, data: dict) -> OperationalIssue:
    import uuid

    with transaction.atomic():
        issue = OperationalIssue.objects.create(
            kind=IssueKind.MANUAL, fingerprint=f"manual:{uuid.uuid4().hex}", title=data["title"],
            description=data.get("description", ""), department=data["department"], priority=data.get("priority",
                                                                                                      "medium"),
            responsible=data.get("responsible"), auto_detected=False)
        _event(issue, IssueEvent.Action.DETECTED, actor=actor, to_status=issue.status, comment="Добавлена вручную.")
        _notify(issue)
    return issue
