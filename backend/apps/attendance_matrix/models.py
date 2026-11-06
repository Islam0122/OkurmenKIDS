"""Access scopes, settings and the audit log of the attendance matrix.

The marks themselves are never duplicated here: attendance lives in
``academy.Attendance`` and homework in ``academy.HomeworkResult``.
"""
from __future__ import annotations

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from apps.academy.models import Attendance, Group, Lesson, Student
from apps.users.models import Subject, User


class GroupAssistant(models.Model):
    """An Assistant assigned to a Group. In the matrix an Assistant sees only
    the groups they are assigned to; `can_edit` lets them mark attendance and
    homework there (otherwise — view and comment only)."""

    group = models.ForeignKey(Group, on_delete=models.CASCADE, related_name="assistant_assignments", verbose_name="Группа")
    assistant = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="assistant_groups",
        limit_choices_to={"role": User.Role.ASSISTANT},
        verbose_name="Ассистент",
    )
    can_edit = models.BooleanField(
        default=True,
        verbose_name="Может отмечать",
        help_text="Отмечать посещаемость и ДЗ. Без этого — только просмотр и комментарии.",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата назначения")

    class Meta:
        verbose_name = "Ассистент группы"
        verbose_name_plural = "Ассистенты групп"
        ordering = ["group__name"]
        constraints = [models.UniqueConstraint(fields=["group", "assistant"], name="unique_group_assistant")]

    def __str__(self):
        return f"{self.assistant} — {self.group}"


class TeamLeadDirection(models.Model):
    """A direction (Subject) a Team Lead is responsible for. A Team Lead with
    no direction assigned keeps the academy-wide view they had before."""

    team_lead = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="lead_directions",
        limit_choices_to={"role": User.Role.TEAM_LEAD},
        verbose_name="Team Lead",
    )
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name="team_leads", verbose_name="Направление")

    class Meta:
        verbose_name = "Направление Team Lead"
        verbose_name_plural = "Направления Team Lead"
        constraints = [models.UniqueConstraint(fields=["team_lead", "subject"], name="unique_team_lead_direction")]

    def __str__(self):
        return f"{self.team_lead} — {self.subject}"


class MatrixSettings(models.Model):
    """Singleton (pk=1): warning thresholds and who besides trainers may edit."""

    consecutive_absences_warning = models.PositiveSmallIntegerField(
        default=2, validators=[MinValueValidator(1), MaxValueValidator(50)],
        verbose_name="Пропусков подряд — предупреждение",
    )
    monthly_absences_attention = models.PositiveSmallIntegerField(
        default=3, validators=[MinValueValidator(1), MaxValueValidator(50)],
        verbose_name="Пропусков за месяц — обратить внимание",
    )
    monthly_absences_critical = models.PositiveSmallIntegerField(
        default=4, validators=[MinValueValidator(1), MaxValueValidator(50)],
        verbose_name="Пропусков за месяц — критично",
    )
    missed_homework_warning = models.PositiveSmallIntegerField(
        default=3, validators=[MinValueValidator(1), MaxValueValidator(50)],
        verbose_name="Несданных ДЗ — предупреждение",
    )
    team_lead_can_edit = models.BooleanField(default=False, verbose_name="Team Lead может изменять отметки")
    operations_director_can_edit = models.BooleanField(
        default=False, verbose_name="Операционный директор может изменять отметки",
    )
    updated_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="+", verbose_name="Кто изменил")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Дата обновления")

    class Meta:
        verbose_name = "Настройки посещаемости"
        verbose_name_plural = "Настройки посещаемости"

    def __str__(self):
        return "Настройки посещаемости"

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls) -> "MatrixSettings":
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class AttendanceChangeLog(models.Model):
    """Append-only: every change of a cell (attendance, reason, comment,
    homework) made through the matrix — who, when, what was before/after."""

    lesson = models.ForeignKey(Lesson, on_delete=models.CASCADE, related_name="attendance_changes", verbose_name="Занятие")
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="attendance_changes", verbose_name="Студент")
    attendance = models.ForeignKey(
        Attendance, on_delete=models.SET_NULL, null=True, blank=True, related_name="changes", verbose_name="Отметка",
    )
    actor = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="+", verbose_name="Кто изменил")
    actor_role = models.CharField(max_length=30, blank=True, verbose_name="Роль")
    changes = models.JSONField(default=dict, verbose_name="Изменения", help_text="{поле: [было, стало]}")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True, verbose_name="Когда")

    class Meta:
        verbose_name = "Изменение посещаемости"
        verbose_name_plural = "Журнал изменений посещаемости"
        ordering = ["-created_at", "-id"]
        indexes = [models.Index(fields=["lesson", "student"], name="ix_attchange_lesson_student")]

    def __str__(self):
        return f"{self.student} — {self.lesson.date} — {self.actor}"
