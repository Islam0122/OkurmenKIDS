"""Team Lead's work log, tasks and reports (section 6 of the Team Lead role).

Two models, nothing else:

* WorkLogEntry — one record of the «Рабочий журнал»: what was done, when,
  with which group / trainer / student, the result, the problem found, the
  decision and the next action with its owner, deadline, priority and status.
  A task (e.g. a meeting decision) is the same record with entry_kind=TASK —
  one list of everything that has an owner and a deadline.
* TeamLeadReport — every structured report (daily, weekly, team meeting,
  lesson visit, trainer review, problem student, internship, probation,
  monthly). Its form fields are described in apps.worklog.schemas and kept
  in `data`; every figure the LMS already knows (groups, students,
  attendance, homework, KPI, tests, exams) is computed by the existing
  Reports/KPI services and testing data into `metrics`, never typed in.
"""
from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone


class WorkType(models.TextChoices):
    LESSON_CONTROL = "lesson_control", "Контроль занятия"
    TRAINER = "trainer", "Работа с тренером"
    STUDENT = "student", "Работа со студентом"
    EXAM = "exam", "Экзамен"
    HACKATHON = "hackathon", "Хакатон"
    MEETING = "meeting", "Собрание"
    INTERNSHIP = "internship", "Стажировка"
    PROBATION = "probation", "Испытательный срок"
    ANALYTICS = "analytics", "Аналитика"
    PROBLEM = "problem", "Проблема"
    OTHER = "other", "Другое"


class TaskStatus(models.TextChoices):
    NEW = "new", "Новая"
    IN_PROGRESS = "in_progress", "В работе"
    DONE = "done", "Выполнено"
    OVERDUE = "overdue", "Просрочено"
    POSTPONED = "postponed", "Отложено"
    ESCALATED = "escalated", "Эскалировано"


# Statuses that still wait for someone: past their deadline they are «Просрочено».
OPEN_STATUSES = (TaskStatus.NEW, TaskStatus.IN_PROGRESS, TaskStatus.OVERDUE)


class Priority(models.TextChoices):
    LOW = "low", "Низкий"
    MEDIUM = "medium", "Средний"
    HIGH = "high", "Высокий"
    CRITICAL = "critical", "Критический"


class WorkLogEntry(models.Model):
    class Kind(models.TextChoices):
        LOG = "log", "Запись журнала"
        TASK = "task", "Задача"

    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="worklog_entries", verbose_name="Автор",
    )
    entry_kind = models.CharField(max_length=8, choices=Kind.choices, default=Kind.LOG, verbose_name="Вид", db_index=True)
    date = models.DateField(default=timezone.localdate, verbose_name="Дата", db_index=True)
    time_from = models.TimeField(null=True, blank=True, verbose_name="Время с")
    time_to = models.TimeField(null=True, blank=True, verbose_name="Время до")
    work_type = models.CharField(max_length=20, choices=WorkType.choices, default=WorkType.OTHER, verbose_name="Тип работы")

    group = models.ForeignKey("academy.Group", on_delete=models.SET_NULL, null=True, blank=True,
                              related_name="worklog_entries", verbose_name="Группа")
    teacher = models.ForeignKey("users.Teacher", on_delete=models.SET_NULL, null=True, blank=True,
                                related_name="worklog_entries", verbose_name="Тренер")
    student = models.ForeignKey("academy.Student", on_delete=models.SET_NULL, null=True, blank=True,
                                related_name="worklog_entries", verbose_name="Студент")
    with_whom = models.CharField(max_length=255, blank=True, verbose_name="С кем (если не группа/тренер/студент)")

    title = models.CharField(max_length=255, blank=True, verbose_name="Задача")
    goal = models.TextField(blank=True, verbose_name="Цель")
    description = models.TextField(blank=True, verbose_name="Что сделано")
    result = models.TextField(blank=True, verbose_name="Результат")
    problem = models.TextField(blank=True, verbose_name="Выявленная проблема")
    decision = models.TextField(blank=True, verbose_name="Принятое решение")
    next_action = models.TextField(blank=True, verbose_name="Следующее действие")
    responsible = models.CharField(max_length=255, blank=True, verbose_name="Ответственный")
    deadline = models.DateField(null=True, blank=True, verbose_name="Срок", db_index=True)
    priority = models.CharField(max_length=10, choices=Priority.choices, default=Priority.MEDIUM, verbose_name="Приоритет")
    status = models.CharField(max_length=12, choices=TaskStatus.choices, default=TaskStatus.NEW, verbose_name="Статус", db_index=True)
    comment = models.TextField(blank=True, verbose_name="Комментарий")

    # A meeting decision (or any task) born from a report.
    report = models.ForeignKey("worklog.TeamLeadReport", on_delete=models.CASCADE, null=True, blank=True,
                               related_name="tasks", verbose_name="Отчёт")

    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Создано")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Обновлено")

    class Meta:
        verbose_name = "Запись рабочего журнала"
        verbose_name_plural = "Рабочий журнал"
        ordering = ["-date", "-time_from", "-id"]

    def __str__(self):
        return f"{self.date:%d.%m.%Y} — {self.title or self.get_work_type_display()}"

    def effective_status(self, today=None) -> str:
        """«Просрочено» is never typed in: an open record past its deadline is overdue."""
        today = today or timezone.localdate()
        if self.status in OPEN_STATUSES and self.deadline and self.deadline < today:
            return TaskStatus.OVERDUE
        if self.status == TaskStatus.OVERDUE and not (self.deadline and self.deadline < today):
            return TaskStatus.IN_PROGRESS
        return self.status


class ReportKind(models.TextChoices):
    DAILY = "daily", "Ежедневный отчёт"
    WEEKLY = "weekly", "Еженедельный отчёт"
    MEETING = "meeting", "Встреча с командой"
    LESSON_VISIT = "lesson_visit", "Посещение занятия"
    TRAINER_REVIEW = "trainer_review", "Отчёт по тренеру"
    PROBLEM_STUDENT = "problem_student", "Проблемный студент"
    INTERNSHIP = "internship", "Стажировка нового тренера"
    PROBATION = "probation", "Испытательный срок"
    MONTHLY = "monthly", "Ежемесячный отчёт"


class TeamLeadReport(models.Model):
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="teamlead_reports", verbose_name="Автор",
    )
    kind = models.CharField(max_length=20, choices=ReportKind.choices, verbose_name="Вид отчёта", db_index=True)
    date = models.DateField(default=timezone.localdate, verbose_name="Дата", db_index=True)
    period_start = models.DateField(null=True, blank=True, verbose_name="Период с")
    period_end = models.DateField(null=True, blank=True, verbose_name="Период по")

    group = models.ForeignKey("academy.Group", on_delete=models.SET_NULL, null=True, blank=True,
                              related_name="teamlead_reports", verbose_name="Группа")
    teacher = models.ForeignKey("users.Teacher", on_delete=models.SET_NULL, null=True, blank=True,
                                related_name="teamlead_reports", verbose_name="Тренер")
    student = models.ForeignKey("academy.Student", on_delete=models.SET_NULL, null=True, blank=True,
                                related_name="teamlead_reports", verbose_name="Студент")
    lesson = models.ForeignKey("academy.Lesson", on_delete=models.SET_NULL, null=True, blank=True,
                               related_name="teamlead_reports", verbose_name="Занятие")

    # Form fields of the kind (apps.worklog.schemas), validated on save.
    data = models.JSONField(default=dict, blank=True, verbose_name="Данные отчёта")
    # Figures computed by the existing services when the report is created
    # (or recalculated) — a snapshot, so the report keeps what it said.
    metrics = models.JSONField(default=dict, blank=True, verbose_name="Показатели LMS")
    metrics_calculated_at = models.DateTimeField(null=True, blank=True, verbose_name="Показатели посчитаны")
    status = models.CharField(max_length=20, default="draft", verbose_name="Статус", db_index=True)

    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Создан")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Обновлён")

    class Meta:
        verbose_name = "Отчёт Team Lead"
        verbose_name_plural = "Отчёты Team Lead"
        ordering = ["-date", "-id"]

    def __str__(self):
        return f"{self.get_kind_display()} — {self.date:%d.%m.%Y}"
