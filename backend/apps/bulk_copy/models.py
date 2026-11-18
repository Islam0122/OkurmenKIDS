"""Audit log of bulk copies (services/engine.py). The copied data itself
lives only in the existing academy models — Attendance and HomeworkResult;
nothing here duplicates them. Every changed row is kept in BulkCopyItem with
its values before and after, which is what makes a safe undo possible."""
from __future__ import annotations

from django.conf import settings
from django.db import models

USER = settings.AUTH_USER_MODEL


class Category(models.TextChoices):
    ATTENDANCE = "attendance", "Посещаемость"
    HOMEWORK = "homework", "Домашние задания"
    SCORES = "scores", "Оценки за ДЗ"


class BulkCopyOperation(models.Model):
    class Status(models.TextChoices):
        QUEUED = "queued", "В очереди"
        RUNNING = "running", "Выполняется"
        APPLIED = "applied", "Применено"
        FAILED = "failed", "Ошибка — ничего не изменено"
        REVERTED = "reverted", "Отменено"
        PARTIALLY_REVERTED = "partially_reverted", "Отменено частично"

    # Client-generated idempotency key — a retried request runs once.
    operation_id = models.UUIDField(unique=True, editable=False, verbose_name="Идентификатор операции")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.QUEUED, db_index=True,
                              verbose_name="Статус")

    source_group = models.ForeignKey("academy.Group", on_delete=models.SET_NULL, null=True, related_name="+",
                                     verbose_name="Группа-источник")
    source_group_name = models.CharField(max_length=150, verbose_name="Группа-источник (название)")
    source_subject = models.ForeignKey("users.Subject", on_delete=models.SET_NULL, null=True, related_name="+",
                                       verbose_name="Предмет-источник")
    source_subject_name = models.CharField(max_length=100, verbose_name="Предмет-источник (название)")
    source_start = models.DateField(verbose_name="Период-источник: с")
    source_end = models.DateField(verbose_name="Период-источник: по")

    target_group = models.ForeignKey("academy.Group", on_delete=models.SET_NULL, null=True, related_name="+",
                                     verbose_name="Целевая группа")
    target_group_name = models.CharField(max_length=150, verbose_name="Целевая группа (название)")
    target_subject = models.ForeignKey("users.Subject", on_delete=models.SET_NULL, null=True, related_name="+",
                                       verbose_name="Целевой предмет")
    target_subject_name = models.CharField(max_length=100, verbose_name="Целевой предмет (название)")
    target_start = models.DateField(verbose_name="Целевой период: с")
    target_end = models.DateField(verbose_name="Целевой период: по")

    categories = models.JSONField(default=list, verbose_name="Категории данных")
    # The full request (lesson map, students, conflict policy, flags) — a queued
    # operation is executed from exactly this.
    request = models.JSONField(default=dict, verbose_name="Параметры")
    fingerprint = models.CharField(max_length=64, verbose_name="Отпечаток предпросмотра")

    copied_count = models.PositiveIntegerField(default=0, verbose_name="Создано записей")
    overwritten_count = models.PositiveIntegerField(default=0, verbose_name="Перезаписано записей")
    skipped_count = models.PositiveIntegerField(default=0, verbose_name="Пропущено")
    skipped_details = models.JSONField(default=dict, blank=True, verbose_name="Причины пропуска")
    error = models.TextField(blank=True, verbose_name="Ошибка")

    created_by = models.ForeignKey(USER, on_delete=models.PROTECT, related_name="+", verbose_name="Администратор")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True, verbose_name="Создано")
    finished_at = models.DateTimeField(null=True, blank=True, verbose_name="Выполнено")
    reverted_by = models.ForeignKey(USER, on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
                                    verbose_name="Отменил")
    reverted_at = models.DateTimeField(null=True, blank=True, verbose_name="Время отмены")
    revert_details = models.JSONField(default=dict, blank=True, verbose_name="Итог отмены")

    class Meta:
        verbose_name = "Массовое копирование"
        verbose_name_plural = "Массовое копирование данных"
        ordering = ["-created_at", "-id"]
        permissions = [("run_bulk_copy", "Может выполнять массовое копирование данных")]

    def __str__(self):
        return (f"{self.source_group_name} / {self.source_subject_name} → "
                f"{self.target_group_name} / {self.target_subject_name} ({self.created_at:%d.%m.%Y %H:%M})")


class BulkCopyItem(models.Model):
    """One Attendance or HomeworkResult row an operation created or overwrote."""

    class Kind(models.TextChoices):
        ATTENDANCE = "attendance", "Посещаемость"
        HOMEWORK_RESULT = "homework_result", "Результат ДЗ"

    class Action(models.TextChoices):
        CREATED = "created", "Создана"
        OVERWRITTEN = "overwritten", "Перезаписана"

    class UndoResult(models.TextChoices):
        PENDING = "", "—"
        RESTORED = "restored", "Восстановлена"
        DELETED = "deleted", "Удалена (была создана копированием)"
        SKIPPED_CHANGED = "skipped_changed", "Не тронута: изменена после копирования"
        SKIPPED_MISSING = "skipped_missing", "Не тронута: запись уже удалена"

    operation = models.ForeignKey(BulkCopyOperation, on_delete=models.CASCADE, related_name="items",
                                  verbose_name="Операция")
    kind = models.CharField(max_length=20, choices=Kind.choices, verbose_name="Тип записи")
    attendance = models.ForeignKey("academy.Attendance", on_delete=models.SET_NULL, null=True, blank=True,
                                   related_name="+", verbose_name="Отметка посещаемости")
    homework_result = models.ForeignKey("academy.HomeworkResult", on_delete=models.SET_NULL, null=True, blank=True,
                                        related_name="+", verbose_name="Результат ДЗ")
    student = models.ForeignKey("academy.Student", on_delete=models.CASCADE, related_name="+", verbose_name="Студент")
    source_lesson = models.ForeignKey("academy.Lesson", on_delete=models.SET_NULL, null=True, related_name="+",
                                      verbose_name="Занятие-источник")
    target_lesson = models.ForeignKey("academy.Lesson", on_delete=models.SET_NULL, null=True, related_name="+",
                                      verbose_name="Целевое занятие")
    action = models.CharField(max_length=12, choices=Action.choices, verbose_name="Действие")
    before = models.JSONField(null=True, blank=True, verbose_name="Было")
    after = models.JSONField(verbose_name="Стало")
    undo_result = models.CharField(max_length=20, choices=UndoResult.choices, blank=True, default="",
                                   verbose_name="Результат отмены")

    class Meta:
        verbose_name = "Запись копирования"
        verbose_name_plural = "Записи копирования"
        ordering = ["operation", "id"]
        indexes = [models.Index(fields=["operation", "kind"], name="ix_bulkcopy_item_op_kind")]

    def __str__(self):
        return f"{self.operation_id}: {self.get_kind_display()} {self.student_id} ({self.get_action_display()})"
