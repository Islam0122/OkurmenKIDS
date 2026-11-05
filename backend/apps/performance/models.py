"""Ежедневный снимок общих показателей академии («Общая статистика»).

Снимок — не копия студентов, групп или посещаемости: только итоговые цифры
одного дня, посчитанные из существующих моделей apps.academy
(services.metrics) — по расписанию именно этого дня и составу групп на этот
день (журнал StudentStatusEvent). Хранится, чтобы прошлые месяцы читались из
базы, а не пересчитывались по текущему состоянию.

Жизненный цикл (services.snapshots):

* ``provisional`` — сегодняшний день и дни в пределах
  ``PERFORMANCE_FINALIZE_DELAY_DAYS``: пересчитываются при каждом запуске
  (тренеры отмечают посещаемость и проверяют ДЗ с опозданием);
* ``final`` — зафиксирован, больше никогда не пересчитывается.

Ручная корректировка (только сотрудники с правом, см. permissions) задаёт
значения отдельных полей; эти поля перечислены в ``manual_fields`` и
автоматический пересчёт их не трогает.

Отсутствие данных — ``NULL``, а не 0: день без занятий — «Нет занятий», а не «0 %».
"""
from __future__ import annotations

from django.conf import settings
from django.db import models


class DailyPerformanceSnapshot(models.Model):
    class Status(models.TextChoices):
        PROVISIONAL = "provisional", "Предварительный"
        FINAL = "final", "Зафиксирован"

    # Поля, которые можно скорректировать вручную.
    EDITABLE_FIELDS = (
        "scheduled_groups", "held_groups", "scheduled_students", "attended_students",
        "attendance_percent", "homework_percent",
    )

    date = models.DateField(unique=True, verbose_name="Дата")

    scheduled_groups = models.PositiveIntegerField(
        null=True, blank=True, verbose_name="Групп по расписанию",
        help_text="Группы с неотменёнными занятиями в этот день.",
    )
    held_groups = models.PositiveIntegerField(
        null=True, blank=True, verbose_name="Групп с проведёнными занятиями",
    )
    scheduled_students = models.PositiveIntegerField(
        null=True, blank=True, verbose_name="Студентов по расписанию",
        help_text="Уникальные активные студенты групп с занятиями в этот день (состав на эту дату).",
    )
    attended_students = models.PositiveIntegerField(
        null=True, blank=True, verbose_name="Посетили занятия",
        help_text="Уникальные студенты с отметкой «Присутствовал» или «Опоздал».",
    )
    expected_students = models.PositiveIntegerField(
        default=0, verbose_name="Ожидались на занятиях",
        help_text="Студенты занятий, которые должны были состояться (знаменатель посещаемости).",
    )
    attendance_percent = models.DecimalField(
        max_digits=5, decimal_places=1, null=True, blank=True, verbose_name="Посещаемость, %",
        help_text="Посетили / ожидались. Пусто — в этот день не было занятий.",
    )

    homework_percent = models.DecimalField(
        max_digits=5, decimal_places=1, null=True, blank=True, verbose_name="Домашние задания, %",
        help_text="Сдано (в срок, с опозданием, проверено) от всех результатов ДЗ, заданного в этот день.",
    )
    homework_results = models.PositiveIntegerField(default=0, verbose_name="Результатов ДЗ")
    homework_done = models.PositiveIntegerField(default=0, verbose_name="Из них сдано")

    lessons_count = models.PositiveIntegerField(default=0, verbose_name="Занятий по расписанию")
    held_lessons_count = models.PositiveIntegerField(default=0, verbose_name="Проведено занятий")

    # Значения первой версии панели (до учёта расписания дня, миграция 0003):
    # сохранены как были, ничем не используются и не пересчитываются.
    legacy_active_groups = models.PositiveIntegerField(
        null=True, blank=True, editable=False, verbose_name="Активных групп (первая версия)",
    )
    legacy_active_students = models.PositiveIntegerField(
        null=True, blank=True, editable=False, verbose_name="Активных студентов (первая версия)",
    )
    legacy_attendance_marked = models.PositiveIntegerField(
        default=0, editable=False, verbose_name="Отметок посещаемости (первая версия)",
    )
    legacy_attendance_attended = models.PositiveIntegerField(
        default=0, editable=False, verbose_name="Присутствовали (первая версия)",
    )
    legacy_attendance_percent = models.DecimalField(
        max_digits=5, decimal_places=1, null=True, blank=True, editable=False,
        verbose_name="Посещаемость, % (первая версия)",
    )
    legacy_homework_percent = models.DecimalField(
        max_digits=5, decimal_places=1, null=True, blank=True, editable=False,
        verbose_name="Домашние задания, % (первая версия)",
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


class DashboardAccessKey(models.Model):
    """Ключ доступа «только чтение» к отдельному сайту «Общая статистика»
    (например, для телевизора в офисе, где никто не входит в LMS).

    Ключ открывает только GET /api/v1/monthly-performance/* — и больше ничего:
    это не пользователь, ни один другой эндпоинт LMS его не принимает.
    В базе хранится только SHA-256 ключа; сам ключ показывается один раз при
    создании (Django admin или `manage.py create_dashboard_key`).
    """

    name = models.CharField(max_length=120, verbose_name="Название", help_text="Например: «Телевизор в офисе».")
    key_hash = models.CharField(max_length=64, unique=True, editable=False, verbose_name="Хеш ключа")
    prefix = models.CharField(max_length=8, editable=False, verbose_name="Начало ключа")
    is_active = models.BooleanField(default=True, verbose_name="Активен")
    expires_at = models.DateTimeField(null=True, blank=True, verbose_name="Действует до",
                                      help_text="Пусто — бессрочно (пока ключ активен).")
    last_used_at = models.DateTimeField(null=True, blank=True, editable=False, verbose_name="Последнее использование")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
        editable=False, verbose_name="Создал",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Создан")

    class Meta:
        verbose_name = "Ключ доступа к общей статистике"
        verbose_name_plural = "Общая статистика: ключи доступа"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.name} ({self.prefix}…)"
