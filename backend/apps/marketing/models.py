"""Кабинет маркетинга: контент-план и задачи отдела.

Модели:

* ContentItem — публикация контент-плана: тема, канал, формат, дата (и время)
  выхода, ответственный и статус: идея → подготовка → согласование →
  запланировано → опубликовано. Запланированная и опубликованная публикация
  всегда знает дату выхода; момент публикации (`published_at`) ставит сервер,
  когда статус становится «Опубликовано», — по нему строятся отчёты.
* MarketingTask — задача отдела: срок, приоритет, статус, ответственный.
  «Просрочено» не хранится, а вычисляется: открытая задача со сроком в прошлом.
  Момент выполнения (`completed_at`) ставит сервер.

Ответственный — существующий `users.User` с ролью «Маркетинг». Отдельной
таблицы сотрудников нет; приход и уход — apps.staff_attendance.
"""
from __future__ import annotations

from django.conf import settings
from django.db import models
from django.db.models import Q


class Channel(models.TextChoices):
    INSTAGRAM = "instagram", "Instagram"
    TIKTOK = "tiktok", "TikTok"
    FACEBOOK = "facebook", "Facebook"
    TELEGRAM = "telegram", "Telegram"
    YOUTUBE = "youtube", "YouTube"
    WHATSAPP = "whatsapp", "WhatsApp"
    WEBSITE = "website", "Сайт"
    OTHER = "other", "Другое"


class ContentFormat(models.TextChoices):
    POST = "post", "Пост"
    CAROUSEL = "carousel", "Карусель"
    REELS = "reels", "Reels / короткое видео"
    STORIES = "stories", "Сторис"
    VIDEO = "video", "Видео"
    ARTICLE = "article", "Статья"
    OTHER = "other", "Другое"


class ContentItem(models.Model):
    class Status(models.TextChoices):
        IDEA = "idea", "Идея"
        PREPARING = "preparing", "Подготовка"
        REVIEW = "review", "Согласование"
        SCHEDULED = "scheduled", "Запланировано"
        PUBLISHED = "published", "Опубликовано"

    # Статусы, которым нужна дата выхода.
    DATED_STATUSES = (Status.SCHEDULED, Status.PUBLISHED)
    # Материал готов (прошёл подготовку) — для отчёта «подготовлено».
    READY_STATUSES = (Status.REVIEW, Status.SCHEDULED, Status.PUBLISHED)

    title = models.CharField(max_length=200, verbose_name="Тема")
    channel = models.CharField(max_length=12, choices=Channel.choices, default=Channel.INSTAGRAM,
                               verbose_name="Канал")
    format = models.CharField(max_length=10, choices=ContentFormat.choices, default=ContentFormat.POST,
                              verbose_name="Формат")
    publish_date = models.DateField(null=True, blank=True, db_index=True, verbose_name="Дата публикации")
    publish_time = models.TimeField(null=True, blank=True, verbose_name="Время публикации")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.IDEA, db_index=True,
                              verbose_name="Статус")
    responsible = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="marketing_content",
        verbose_name="Ответственный",
    )
    description = models.TextField(blank=True, verbose_name="Описание и заметки")
    post_url = models.URLField(max_length=500, blank=True, verbose_name="Ссылка на публикацию")
    published_at = models.DateTimeField(null=True, blank=True, verbose_name="Опубликовано")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                   related_name="+", verbose_name="Кем создана")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Создана")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Изменена")

    class Meta:
        verbose_name = "Публикация контент-плана"
        verbose_name_plural = "Контент-план"
        ordering = ["publish_date", "publish_time", "id"]
        constraints = [
            models.CheckConstraint(
                condition=~Q(status__in=["scheduled", "published"]) | Q(publish_date__isnull=False),
                name="marketing_content_dated_status",
            ),
            models.CheckConstraint(
                condition=~Q(status="published") | Q(published_at__isnull=False),
                name="marketing_content_published_at",
            ),
        ]

    def __str__(self):
        return self.title


class MarketingTask(models.Model):
    class Status(models.TextChoices):
        TODO = "todo", "К выполнению"
        IN_PROGRESS = "in_progress", "В работе"
        DONE = "done", "Выполнено"

    class Priority(models.TextChoices):
        LOW = "low", "Низкий"
        MEDIUM = "medium", "Средний"
        HIGH = "high", "Высокий"

    OPEN_STATUSES = (Status.TODO, Status.IN_PROGRESS)

    title = models.CharField(max_length=200, verbose_name="Название")
    description = models.TextField(blank=True, verbose_name="Описание")
    due_date = models.DateField(null=True, blank=True, db_index=True, verbose_name="Срок")
    priority = models.CharField(max_length=6, choices=Priority.choices, default=Priority.MEDIUM,
                                verbose_name="Приоритет")
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.TODO, db_index=True,
                              verbose_name="Статус")
    responsible = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="marketing_tasks",
        verbose_name="Ответственный",
    )
    completed_at = models.DateTimeField(null=True, blank=True, verbose_name="Выполнена")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                   related_name="+", verbose_name="Кем создана")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Создана")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Изменена")

    class Meta:
        verbose_name = "Задача маркетинга"
        verbose_name_plural = "Задачи маркетинга"
        ordering = ["-created_at", "-id"]
        constraints = [
            models.CheckConstraint(
                condition=~Q(status="done") | Q(completed_at__isnull=False),
                name="marketing_task_done_has_date",
            ),
        ]

    def __str__(self):
        return self.title

    def is_overdue(self, today) -> bool:
        return self.status in self.OPEN_STATUSES and self.due_date is not None and self.due_date < today
