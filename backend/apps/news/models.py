from django.db import models
from django.utils import timezone


class NewsQuerySet(models.QuerySet):
    def active(self):
        """Published and not yet expired — the state a Teacher is ever allowed to see."""
        now = timezone.now()
        return self.filter(is_published=True).filter(
            models.Q(expires_at__isnull=True) | models.Q(expires_at__gt=now)
        )

    def visible_to(self, teacher):
        """Active News addressed to `teacher`: either sent to everyone, or
        sent to a selected list that includes them."""
        return self.active().filter(
            models.Q(audience=News.Audience.ALL)
            | models.Q(audience=News.Audience.SELECTED, teachers=teacher)
        ).distinct()


class News(models.Model):
    class NewsType(models.TextChoices):
        INFO = "info", "Информация"
        IMPORTANT = "important", "Важно"
        WARNING = "warning", "Предупреждение"
        EVENT = "event", "Мероприятие"

    class Audience(models.TextChoices):
        ALL = "all", "Всем"
        SELECTED = "selected", "Выбранным"

    title = models.CharField(
        max_length=255,
        verbose_name="Заголовок",
        help_text="Короткий заголовок новости.",
    )

    text = models.TextField(
        verbose_name="Текст",
        help_text="Текст новости или объявления.",
    )

    type = models.CharField(
        max_length=20,
        choices=NewsType.choices,
        default=NewsType.INFO,
        verbose_name="Тип",
        help_text="Определяет иконку и цвет новости для тренеров.",
    )

    audience = models.CharField(
        max_length=20,
        choices=Audience.choices,
        default=Audience.ALL,
        verbose_name="Аудитория",
        help_text="Кому показывать новость: всем тренерам или только выбранным.",
    )

    teachers = models.ManyToManyField(
        "users.Teacher",
        blank=True,
        related_name="news",
        verbose_name="Тренеры",
        help_text="Тренеры, которым адресована новость (только при аудитории «Выбранным»).",
    )

    is_published = models.BooleanField(
        default=True,
        verbose_name="Опубликовано",
        help_text="Неопубликованная новость не видна тренерам.",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Дата создания",
    )

    expires_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Дата окончания",
        help_text="После этой даты новость перестаёт показываться тренерам. Можно оставить пустым.",
    )

    objects = NewsQuerySet.as_manager()

    class Meta:
        verbose_name = "Новость"
        verbose_name_plural = "Новости"
        ordering = ["-created_at"]

    def __str__(self):
        return self.title


class NewsRead(models.Model):
    news = models.ForeignKey(
        News,
        on_delete=models.CASCADE,
        related_name="reads",
        verbose_name="Новость",
    )

    teacher = models.ForeignKey(
        "users.Teacher",
        on_delete=models.CASCADE,
        related_name="news_reads",
        verbose_name="Тренер",
    )

    read_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Дата прочтения",
    )

    class Meta:
        verbose_name = "Прочтение новости"
        verbose_name_plural = "Прочтения новостей"
        ordering = ["-read_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["news", "teacher"],
                name="unique_news_teacher_read",
            )
        ]

    def __str__(self):
        return f"{self.teacher} — {self.news}"
