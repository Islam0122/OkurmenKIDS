"""Операционное управление: задачи, отчёты сотрудников, KPI-цели, проблемы,
уведомления и настройки модуля.

Что здесь НЕ хранится (берётся из существующих модулей, не дублируется):

* сотрудники и отделы — `users.User` и его роль (см. departments.py);
* журнал занятий, посещаемость и ДЗ студентов — `academy` (сервис «Контроль»);
* KPI тренеров — `academy.services.kpi_engine` (единственный источник);
* приход/уход сотрудников — `staff_attendance` (QR, геозона, расписание);
* рабочий журнал и отчёты Team Lead — `worklog.TeamLeadReport`;
* найм — `recruitment`, контент и кампании — `marketing`.

Модели:

* Task (+ TaskChecklistItem, TaskComment, TaskAttachment, TaskHistory,
  TaskReview) — универсальная задача с workflow и полной историей.
* TaskRecurrence — шаблон повторяющейся задачи; каждое повторение — обычная
  Task с `occurrence_date` (уникально в паре с шаблоном → история по датам и
  идемпотентная генерация).
* EmployeeReport — ежедневный / еженедельный / месячный отчёт сотрудника.
* KPITarget — целевое значение показателя (отдел или сотрудник, период).
  Нормативы не зашиты в код: нет цели — нет «достижения» и нет нарушения.
* OperationalIssue (+ IssueEvent) — обнаруженная проблема; `fingerprint`
  уникален, поэтому повторная проверка не создаёт дубль.
* Notification — уведомление сотруднику (outbox: дедупликация по ключу,
  доставка во внешний канал — после коммита).
* OperationsSettings — настраиваемые правила модуля (одна запись).
"""
from __future__ import annotations

import os
import uuid
from datetime import time

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q
from django.utils import timezone

from apps.recruitment.storage import PrivateStorage

from .departments import Department

USER = settings.AUTH_USER_MODEL


# ---------------------------------------------------------------------------
# Задачи
# ---------------------------------------------------------------------------

class TaskStatus(models.TextChoices):
    PENDING = "pending", "Ожидает"
    IN_PROGRESS = "in_progress", "В работе"
    REVIEW = "review", "На проверке"
    COMPLETED = "completed", "Выполнена"
    REJECTED = "rejected", "Возвращена"
    CANCELLED = "cancelled", "Отменена"
    # Не хранится: вычисляется для открытой задачи с прошедшим дедлайном.
    OVERDUE = "overdue", "Просрочена"


STORED_STATUSES = [s for s in TaskStatus.values if s != TaskStatus.OVERDUE]
# Задача ещё ждёт исполнителя (после дедлайна — «Просрочена»).
OPEN_STATUSES = (TaskStatus.PENDING, TaskStatus.IN_PROGRESS, TaskStatus.REJECTED)
CLOSED_STATUSES = (TaskStatus.COMPLETED, TaskStatus.CANCELLED)


class Priority(models.TextChoices):
    LOW = "low", "Низкий"
    MEDIUM = "medium", "Средний"
    HIGH = "high", "Высокий"
    CRITICAL = "critical", "Критический"


PRIORITY_RANK = {Priority.CRITICAL: 0, Priority.HIGH: 1, Priority.MEDIUM: 2, Priority.LOW: 3}


class TaskCategory(models.TextChoices):
    GENERAL = "general", "Общая"
    ACADEMIC = "academic", "Учебный процесс"
    STUDENTS = "students", "Студенты и родители"
    REPORTING = "reporting", "Отчётность"
    SALES = "sales", "Продажи"
    MARKETING = "marketing", "Маркетинг"
    HR = "hr", "Персонал"
    FINANCE = "finance", "Финансы"
    ADMINISTRATIVE = "administrative", "Административная"


class Recurrence(models.TextChoices):
    DAILY = "daily", "Ежедневно"
    WEEKLY = "weekly", "Еженедельно"
    MONTHLY = "monthly", "Ежемесячно"


class TaskRecurrence(models.Model):
    """Шаблон повторяющейся задачи. Повторения создаёт планировщик
    (services.recurrence) — по одному на дату, повторный запуск ничего не
    дублирует (уникальная пара recurrence + occurrence_date)."""

    title = models.CharField(max_length=255, verbose_name="Название")
    description = models.TextField(blank=True, verbose_name="Описание")
    department = models.CharField(max_length=20, choices=Department.choices, verbose_name="Отдел")
    assignee = models.ForeignKey(USER, on_delete=models.PROTECT, related_name="task_recurrences",
                                 verbose_name="Исполнитель")
    created_by = models.ForeignKey(USER, on_delete=models.PROTECT, related_name="+", verbose_name="Автор")
    priority = models.CharField(max_length=10, choices=Priority.choices, default=Priority.MEDIUM)
    category = models.CharField(max_length=20, choices=TaskCategory.choices, default=TaskCategory.GENERAL)
    requires_approval = models.BooleanField(default=False, verbose_name="Требует подтверждения")
    checklist = models.JSONField(default=list, blank=True, verbose_name="Пункты чек-листа")
    frequency = models.CharField(max_length=10, choices=Recurrence.choices, verbose_name="Периодичность")
    # Еженедельно — дни недели (0 — понедельник … 6 — воскресенье);
    # ежемесячно — число месяца (короткий месяц — последний день).
    weekdays = models.JSONField(default=list, blank=True, verbose_name="Дни недели")
    month_day = models.PositiveSmallIntegerField(null=True, blank=True,
                                                 validators=[MinValueValidator(1), MaxValueValidator(31)],
                                                 verbose_name="Число месяца")
    due_time = models.TimeField(null=True, blank=True, verbose_name="Срок в течение дня")
    starts_on = models.DateField(default=timezone.localdate, verbose_name="Начало")
    ends_on = models.DateField(null=True, blank=True, verbose_name="Окончание")
    is_active = models.BooleanField(default=True, db_index=True, verbose_name="Активен")
    last_generated_on = models.DateField(null=True, blank=True, verbose_name="Сгенерировано по")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Повторяющаяся задача"
        verbose_name_plural = "Повторяющиеся задачи"
        ordering = ["title", "id"]

    def __str__(self):
        return f"{self.title} ({self.get_frequency_display()})"

    def clean(self):
        if self.frequency == Recurrence.WEEKLY:
            if not self.weekdays or any(d not in range(7) for d in self.weekdays):
                raise ValidationError({"weekdays": "Для еженедельной задачи укажите дни недели (0–6)."})
        if self.frequency == Recurrence.MONTHLY and not self.month_day:
            raise ValidationError({"month_day": "Для ежемесячной задачи укажите число месяца."})
        if self.ends_on and self.ends_on < self.starts_on:
            raise ValidationError({"ends_on": "Окончание раньше начала."})


class Task(models.Model):
    title = models.CharField(max_length=255, verbose_name="Название")
    description = models.TextField(blank=True, verbose_name="Описание")
    department = models.CharField(max_length=20, choices=Department.choices, db_index=True, verbose_name="Отдел")
    assignee = models.ForeignKey(USER, on_delete=models.PROTECT, null=True, blank=True, related_name="ops_tasks",
                                 verbose_name="Исполнитель",
                                 help_text="Пусто — задача отдела, её берёт любой сотрудник отдела.")
    created_by = models.ForeignKey(USER, on_delete=models.PROTECT, related_name="ops_tasks_created",
                                   verbose_name="Автор")
    reviewer = models.ForeignKey(USER, on_delete=models.PROTECT, null=True, blank=True, related_name="ops_tasks_review",
                                 verbose_name="Проверяющий", help_text="Пусто — автор задачи.")
    priority = models.CharField(max_length=10, choices=Priority.choices, default=Priority.MEDIUM, db_index=True)
    category = models.CharField(max_length=20, choices=TaskCategory.choices, default=TaskCategory.GENERAL)
    status = models.CharField(max_length=12, choices=[(s, TaskStatus(s).label) for s in STORED_STATUSES],
                              default=TaskStatus.PENDING, db_index=True)
    start_date = models.DateField(null=True, blank=True, verbose_name="Дата начала")
    deadline = models.DateTimeField(null=True, blank=True, db_index=True, verbose_name="Дедлайн")
    requires_approval = models.BooleanField(default=False, verbose_name="Требует подтверждения")

    recurrence = models.ForeignKey(TaskRecurrence, on_delete=models.SET_NULL, null=True, blank=True,
                                   related_name="occurrences", verbose_name="Шаблон повторения")
    occurrence_date = models.DateField(null=True, blank=True, verbose_name="Дата повторения")

    started_at = models.DateTimeField(null=True, blank=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True, db_index=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Задача"
        verbose_name_plural = "Задачи"
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["assignee", "status"], name="ops_task_assignee_status"),
            models.Index(fields=["department", "status"], name="ops_task_department_status"),
            models.Index(fields=["status", "deadline"], name="ops_task_status_deadline"),
        ]
        constraints = [
            models.UniqueConstraint(fields=["recurrence", "occurrence_date"], condition=Q(recurrence__isnull=False),
                                    name="ops_task_unique_occurrence"),
            models.CheckConstraint(condition=~Q(status="completed") | Q(completed_at__isnull=False),
                                   name="ops_task_completed_has_date"),
        ]

    def __str__(self):
        return self.title

    @property
    def effective_reviewer_id(self) -> int:
        return self.reviewer_id or self.created_by_id

    def is_overdue(self, now=None) -> bool:
        now = now or timezone.now()
        return bool(self.status in OPEN_STATUSES and self.deadline and self.deadline < now)

    def effective_status(self, now=None) -> str:
        """«Просрочена» не хранится: открытая задача после дедлайна."""
        return TaskStatus.OVERDUE if self.is_overdue(now) else self.status


class TaskChecklistItem(models.Model):
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name="checklist")
    text = models.CharField(max_length=255)
    position = models.PositiveSmallIntegerField(default=0)
    is_done = models.BooleanField(default=False)
    done_by = models.ForeignKey(USER, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    done_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Пункт чек-листа"
        verbose_name_plural = "Чек-лист"
        ordering = ["position", "id"]

    def __str__(self):
        return self.text


class TaskComment(models.Model):
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name="comments")
    author = models.ForeignKey(USER, on_delete=models.PROTECT, related_name="+")
    text = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Комментарий к задаче"
        verbose_name_plural = "Комментарии к задачам"
        ordering = ["created_at", "id"]


def attachment_path(instance, filename: str) -> str:
    ext = os.path.splitext(filename)[1].lower()[:10]
    return f"tasks/{timezone.now():%Y/%m}/{uuid.uuid4().hex}{ext}"


def private_storage() -> PrivateStorage:
    # Тот же закрытый каталог, что у резюме кандидатов: config/urls.py его не
    # отдаёт, скачать файл можно только через API задач с проверкой прав.
    return PrivateStorage()


class TaskAttachment(models.Model):
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name="attachments")
    file = models.FileField(upload_to=attachment_path, storage=private_storage, max_length=255)
    original_name = models.CharField(max_length=255)
    content_type = models.CharField(max_length=120, blank=True)
    size = models.PositiveIntegerField(default=0)
    uploaded_by = models.ForeignKey(USER, on_delete=models.PROTECT, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Вложение задачи"
        verbose_name_plural = "Вложения задач"
        ordering = ["created_at", "id"]


class TaskHistory(models.Model):
    """Журнал действий с задачей. Только добавление — ни изменения, ни удаления."""

    class Action(models.TextChoices):
        CREATED = "created", "Создана"
        UPDATED = "updated", "Изменена"
        ASSIGNED = "assigned", "Назначена"
        STARTED = "started", "Взята в работу"
        SUBMITTED = "submitted", "Отправлена на проверку"
        APPROVED = "approved", "Подтверждена"
        REJECTED = "rejected", "Возвращена на доработку"
        COMPLETED = "completed", "Выполнена"
        REOPENED = "reopened", "Открыта снова"
        CANCELLED = "cancelled", "Отменена"
        COMMENTED = "commented", "Комментарий"
        CHECKLIST = "checklist", "Чек-лист"
        ATTACHMENT = "attachment", "Вложение"

    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name="history")
    actor = models.ForeignKey(USER, on_delete=models.SET_NULL, null=True, related_name="+")
    action = models.CharField(max_length=12, choices=Action.choices, db_index=True)
    from_status = models.CharField(max_length=12, blank=True)
    to_status = models.CharField(max_length=12, blank=True)
    changes = models.JSONField(default=dict, blank=True)
    comment = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = "Событие задачи"
        verbose_name_plural = "История задач"
        ordering = ["created_at", "id"]


class TaskReview(models.Model):
    class Decision(models.TextChoices):
        APPROVED = "approved", "Подтверждена"
        REJECTED = "rejected", "Возвращена"

    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name="reviews")
    reviewer = models.ForeignKey(USER, on_delete=models.PROTECT, related_name="+")
    decision = models.CharField(max_length=10, choices=Decision.choices)
    comment = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Проверка задачи"
        verbose_name_plural = "Проверки задач"
        ordering = ["created_at", "id"]
        constraints = [
            models.CheckConstraint(condition=~Q(decision="rejected") | ~Q(comment=""),
                                   name="ops_review_reject_has_comment"),
        ]


# ---------------------------------------------------------------------------
# Отчёты сотрудников
# ---------------------------------------------------------------------------

class ReportKind(models.TextChoices):
    DAILY = "daily", "Ежедневный"
    WEEKLY = "weekly", "Еженедельный"
    MONTHLY = "monthly", "Ежемесячный"


class EmployeeReport(models.Model):
    """Отчёт сотрудника за период. Team Lead пишет отчёты в своём рабочем
    журнале (worklog.TeamLeadReport) — здесь их нет, модуль читает их оттуда.
    Числа, которых в LMS ещё нет (звонки, встречи, продажи — CRM не
    подключена), сотрудник вносит в `metrics` по схеме своей роли."""

    class Status(models.TextChoices):
        DRAFT = "draft", "Черновик"
        SUBMITTED = "submitted", "Сдан"
        ACCEPTED = "accepted", "Принят"
        RETURNED = "returned", "Возвращён"

    author = models.ForeignKey(USER, on_delete=models.PROTECT, related_name="work_reports")
    department = models.CharField(max_length=20, choices=Department.choices, db_index=True)
    kind = models.CharField(max_length=10, choices=ReportKind.choices, db_index=True)
    period_start = models.DateField(db_index=True)
    period_end = models.DateField()
    done = models.TextField(blank=True, verbose_name="Что сделано")
    plans = models.TextField(blank=True, verbose_name="Планы")
    problems = models.TextField(blank=True, verbose_name="Проблемы")
    metrics = models.JSONField(default=dict, blank=True, verbose_name="Показатели")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT, db_index=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(USER, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    reviewed_at = models.DateTimeField(null=True, blank=True)
    review_comment = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Отчёт сотрудника"
        verbose_name_plural = "Отчёты сотрудников"
        ordering = ["-period_start", "-id"]
        constraints = [
            models.UniqueConstraint(fields=["author", "kind", "period_start"], name="ops_report_unique_period"),
        ]
        indexes = [models.Index(fields=["kind", "period_start", "status"], name="ops_report_kind_period")]

    def __str__(self):
        return f"{self.get_kind_display()} — {self.author} — {self.period_start:%d.%m.%Y}"


# ---------------------------------------------------------------------------
# KPI-цели
# ---------------------------------------------------------------------------

class KPIPeriod(models.TextChoices):
    DAILY = "daily", "День"
    WEEKLY = "weekly", "Неделя"
    MONTHLY = "monthly", "Месяц"


class KPITarget(models.Model):
    """Целевое значение показателя (DepartmentKPI / EmployeeKPI в одной
    таблице: `employee` пуст — цель отдела). Факт всегда считается из данных
    LMS (services.kpi); цели вводит руководство в интерфейсе."""

    metric = models.CharField(max_length=40, db_index=True, verbose_name="Показатель")
    department = models.CharField(max_length=20, choices=Department.choices, db_index=True)
    employee = models.ForeignKey(USER, on_delete=models.CASCADE, null=True, blank=True, related_name="kpi_targets")
    period = models.CharField(max_length=10, choices=KPIPeriod.choices, default=KPIPeriod.MONTHLY)
    target_value = models.DecimalField(max_digits=14, decimal_places=2, validators=[MinValueValidator(0)])
    valid_from = models.DateField(default=timezone.localdate)
    valid_to = models.DateField(null=True, blank=True)
    note = models.CharField(max_length=255, blank=True)
    created_by = models.ForeignKey(USER, on_delete=models.SET_NULL, null=True, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "KPI-цель"
        verbose_name_plural = "KPI-цели"
        ordering = ["department", "metric", "-valid_from"]

    def __str__(self):
        return f"{self.metric} · {self.target_value}"

    def clean(self):
        if self.valid_to and self.valid_to < self.valid_from:
            raise ValidationError({"valid_to": "Окончание раньше начала."})


# ---------------------------------------------------------------------------
# Проблемы (Attention Required)
# ---------------------------------------------------------------------------

class IssueKind(models.TextChoices):
    TASK_OVERDUE = "task_overdue", "Просроченная задача"
    REPORT_MISSING = "report_missing", "Отчёт не сдан"
    JOURNAL_NOT_FILLED = "journal_not_filled", "Журнал не заполнен"
    ATTENDANCE_NOT_MARKED = "attendance_not_marked", "Посещаемость не отмечена"
    HOMEWORK_NOT_CHECKED = "homework_not_checked", "ДЗ не проверено"
    KPI_BELOW_TARGET = "kpi_below_target", "KPI ниже цели"
    PROBLEM_GROUP = "problem_group", "Проблемная группа"
    STUDENT_ABSENCES = "student_absences", "Частые пропуски студента"
    STAFF_ABSENCE = "staff_absence", "Сотрудник не отметил приход"
    MANUAL = "manual", "Добавлена вручную"


class IssueStatus(models.TextChoices):
    OPEN = "open", "Открыта"
    IN_PROGRESS = "in_progress", "В работе"
    RESOLVED = "resolved", "Решена"
    DISMISSED = "dismissed", "Отклонена"


ACTIVE_ISSUE_STATUSES = (IssueStatus.OPEN, IssueStatus.IN_PROGRESS)


class OperationalIssue(models.Model):
    kind = models.CharField(max_length=24, choices=IssueKind.choices, db_index=True)
    # Ключ проблемы (вид + объект + период). Уникален: повторная проверка
    # обновляет `last_seen_at`, а не создаёт вторую запись.
    fingerprint = models.CharField(max_length=160, unique=True)
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    priority = models.CharField(max_length=10, choices=Priority.choices, default=Priority.MEDIUM, db_index=True)
    status = models.CharField(max_length=12, choices=IssueStatus.choices, default=IssueStatus.OPEN, db_index=True)
    department = models.CharField(max_length=20, choices=Department.choices, db_index=True)
    responsible = models.ForeignKey(USER, on_delete=models.SET_NULL, null=True, blank=True, related_name="ops_issues")
    object_type = models.CharField(max_length=40, blank=True)
    object_id = models.PositiveBigIntegerField(null=True, blank=True)
    link = models.CharField(max_length=255, blank=True)
    payload = models.JSONField(default=dict, blank=True)
    detected_at = models.DateTimeField(default=timezone.now, db_index=True)
    last_seen_at = models.DateTimeField(default=timezone.now)
    times_detected = models.PositiveIntegerField(default=1)
    # Проблема вернулась после «Решена» — повторное нарушение.
    reopen_count = models.PositiveIntegerField(default=0)
    auto_detected = models.BooleanField(default=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolved_by = models.ForeignKey(USER, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")

    class Meta:
        verbose_name = "Проблема"
        verbose_name_plural = "Проблемы"
        ordering = ["-detected_at", "-id"]
        indexes = [models.Index(fields=["status", "department"], name="ops_issue_status_department")]

    def __str__(self):
        return self.title


class IssueEvent(models.Model):
    class Action(models.TextChoices):
        DETECTED = "detected", "Обнаружена"
        REDETECTED = "redetected", "Обнаружена повторно"
        STATUS = "status", "Смена статуса"
        ASSIGNED = "assigned", "Назначен ответственный"
        COMMENT = "comment", "Комментарий"
        AUTO_RESOLVED = "auto_resolved", "Устранена (проверка)"

    issue = models.ForeignKey(OperationalIssue, on_delete=models.CASCADE, related_name="events")
    actor = models.ForeignKey(USER, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    action = models.CharField(max_length=16, choices=Action.choices)
    from_status = models.CharField(max_length=12, blank=True)
    to_status = models.CharField(max_length=12, blank=True)
    comment = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Событие проблемы"
        verbose_name_plural = "История проблем"
        ordering = ["created_at", "id"]


# ---------------------------------------------------------------------------
# Уведомления
# ---------------------------------------------------------------------------

class NotificationKind(models.TextChoices):
    TASK_ASSIGNED = "task_assigned", "Новая задача"
    TASK_DEADLINE = "task_deadline", "Приближается дедлайн"
    TASK_OVERDUE = "task_overdue", "Задача просрочена"
    TASK_REJECTED = "task_rejected", "Задача возвращена"
    TASK_APPROVED = "task_approved", "Задача подтверждена"
    TASK_REVIEW = "task_review", "Задача ждёт проверки"
    TASK_COMMENT = "task_comment", "Комментарий к задаче"
    REPORT_MISSING = "report_missing", "Отчёт не сдан"
    REPORT_RETURNED = "report_returned", "Отчёт возвращён"
    KPI_BELOW_TARGET = "kpi_below_target", "KPI ниже цели"
    ISSUE_DETECTED = "issue_detected", "Обнаружена проблема"


class Notification(models.Model):
    recipient = models.ForeignKey(USER, on_delete=models.CASCADE, related_name="ops_notifications")
    kind = models.CharField(max_length=20, choices=NotificationKind.choices, db_index=True)
    title = models.CharField(max_length=200)
    message = models.TextField(blank=True)
    link = models.CharField(max_length=255, blank=True)
    dedup_key = models.CharField(max_length=160, unique=True)
    is_read = models.BooleanField(default=False, db_index=True)
    read_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    delivery_attempts = models.PositiveSmallIntegerField(default=0)
    delivery_error = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = "Уведомление"
        verbose_name_plural = "Уведомления"
        ordering = ["-created_at", "-id"]
        indexes = [models.Index(fields=["recipient", "is_read"], name="ops_notification_unread")]

    def __str__(self):
        return self.title


# ---------------------------------------------------------------------------
# Настройки
# ---------------------------------------------------------------------------

def default_required_reports() -> dict:
    # Пусто: какие отчёты обязательны для какой роли, решает руководство в
    # «Настройках». Пока правило не задано — несданный отчёт не нарушение.
    return {}


class OperationsSettings(models.Model):
    """Настраиваемые правила модуля. Всегда одна запись — см. `load()`."""

    required_reports = models.JSONField(
        default=default_required_reports, blank=True, verbose_name="Обязательные отчёты",
        help_text='Роль → виды отчётов, например {"teacher": ["daily"], "sales_manager": ["daily", "monthly"]}.',
    )
    daily_report_due = models.TimeField(default=time(20, 0), verbose_name="Ежедневный отчёт сдаётся до")
    deadline_reminder_hours = models.PositiveSmallIntegerField(
        default=24, validators=[MaxValueValidator(168)], verbose_name="Напоминать о дедлайне за, ч",
    )
    # «Частые пропуски» студента — пороги «Контроля активности» ассистента
    # (settings.ASSISTANT_CONTROL_THRESHOLDS), второй настройки здесь нет.
    problem_group_attendance = models.PositiveSmallIntegerField(
        default=0, validators=[MaxValueValidator(100)], verbose_name="Посещаемость группы ниже, % — проблемная",
        help_text="0 — правило выключено.",
    )
    detect_staff_absence = models.BooleanField(default=True, verbose_name="Проблема при отсутствии отметки прихода")
    notify_telegram = models.BooleanField(default=False, verbose_name="Дублировать уведомления в Telegram")
    # Финансовые данные маркетинга (бюджет, CPL) — директору и администратору
    # всегда; операционному директору — если разрешено здесь.
    operations_director_sees_marketing_budget = models.BooleanField(
        default=True, verbose_name="Операционный директор видит бюджеты маркетинга",
    )
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(USER, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")

    class Meta:
        verbose_name = "Настройки операционного модуля"
        verbose_name_plural = "Настройки операционного модуля"

    def __str__(self):
        return "Настройки операционного модуля"

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls) -> "OperationsSettings":
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def required_kinds(self, role: str) -> list[str]:
        return [k for k in (self.required_reports or {}).get(role, []) if k in ReportKind.values]

    def clean(self):
        from apps.users.models import User

        if not isinstance(self.required_reports, dict):
            raise ValidationError({"required_reports": "Ожидается объект «роль → список отчётов»."})
        roles = set(User.Role.values)
        for role, kinds in self.required_reports.items():
            if role not in roles or not isinstance(kinds, list) or not set(kinds) <= set(ReportKind.values):
                raise ValidationError({"required_reports": f"Неверное правило для роли «{role}»."})


class ReportExport(models.Model):
    """Журнал сформированных отчётов (кто, какой, за какой период, в каком
    формате) — «история отчётов» и аудит выгрузки данных."""

    kind = models.CharField(max_length=20, db_index=True)
    format = models.CharField(max_length=8)
    filters = models.JSONField(default=dict, blank=True)
    rows = models.PositiveIntegerField(default=0)
    created_by = models.ForeignKey(USER, on_delete=models.SET_NULL, null=True, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = "Выгрузка отчёта"
        verbose_name_plural = "Выгрузки отчётов"
        ordering = ["-created_at", "-id"]
