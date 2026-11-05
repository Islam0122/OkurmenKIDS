"""Ежедневный снимок общих показателей академии («Общая статистика»).

Снимок — не копия студентов, групп или посещаемости: только итоговые цифры
одного дня, посчитанные из существующих моделей apps.academy
(services.metrics). Зачем он хранится, а не считается на лету: количество
активных групп и студентов — это состояние «на тот день»; при деактивации
студента или закрытии группы прошлые дни не должны меняться задним числом.

Жизненный цикл (services.snapshots):

* ``provisional`` — сегодняшний день и дни в пределах
  ``PERFORMANCE_FINALIZE_DELAY_DAYS``: проценты пересчитываются при каждом
  запуске (тренеры отмечают посещаемость и ДЗ с опозданием), а количество
  групп и студентов обновляется только в сам этот день;
* ``final`` — зафиксирован, больше никогда не пересчитывается.

Ручная корректировка (только сотрудники с правом, см. permissions) задаёт
значения отдельных полей; эти поля перечислены в ``manual_fields`` и
автоматический пересчёт их не трогает.

Отсутствие данных — ``NULL``, а не 0: день без занятий не равен «0 %».
"""
from __future__ import annotations

from django.conf import settings
from django.db import models


class DailyPerformanceSnapshot(models.Model):
    class Status(models.TextChoices):
        PROVISIONAL = "provisional", "Предварительный"
        FINAL = "final", "Зафиксирован"

    # Поля, которые можно скорректировать вручную.
    EDITABLE_FIELDS = ("attendance_percent", "homework_percent", "active_groups", "active_students")

    date = models.DateField(unique=True, verbose_name="Дата")

    attendance_percent = models.DecimalField(
        max_digits=5, decimal_places=1, null=True, blank=True, verbose_name="Посещаемость, %",
        help_text="Присутствовал + опоздал от всех отметок за день. Пусто — в этот день не было отметок.",
    )
    attendance_marked = models.PositiveIntegerField(default=0, verbose_name="Отметок посещаемости")
    attendance_attended = models.PositiveIntegerField(default=0, verbose_name="Из них присутствовали")

    homework_percent = models.DecimalField(
        max_digits=5, decimal_places=1, null=True, blank=True, verbose_name="Домашние задания, %",
        help_text="Сдано (в срок, с опозданием, проверено) от всех результатов ДЗ, внесённых за день.",
    )
    homework_results = models.PositiveIntegerField(default=0, verbose_name="Результатов ДЗ")
    homework_done = models.PositiveIntegerField(default=0, verbose_name="Из них сдано")

    lessons_count = models.PositiveIntegerField(default=0, verbose_name="Занятий (без отменённых)")

    active_groups = models.PositiveIntegerField(
        null=True, blank=True, verbose_name="Активных групп",
        help_text="Состояние на этот день. Пусто — в тот день снимок не делался.",
    )
    active_students = models.PositiveIntegerField(
        null=True, blank=True, verbose_name="Активных студентов",
        help_text="Состояние на этот день. Пусто — в тот день снимок не делался.",
    )

    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PROVISIONAL, db_index=True, verbose_name="Состояние",
    )
    manual_fields = models.JSONField(
        default=list, blank=True, verbose_name="Скорректировано вручную",
        help_text="Поля с ручным значением — автоматический пересчёт их не меняет.",
    )
    manual_comment = models.CharField(max_length=255, blank=True, verbose_name="Комментарий к корректировке")
    corrected_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
        verbose_name="Скорректировал",
    )
    corrected_at = models.DateTimeField(null=True, blank=True, verbose_name="Дата корректировки")

    computed_at = models.DateTimeField(null=True, blank=True, verbose_name="Последний расчёт")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Дата обновления")

    class Meta:
        verbose_name = "Снимок общей статистики"
        verbose_name_plural = "Общая статистика: ежедневные снимки"
        ordering = ["-date"]

    def __str__(self):
        return f"Статистика за {self.date:%d.%m.%Y}"

    @property
    def is_final(self) -> bool:
        return self.status == self.Status.FINAL
