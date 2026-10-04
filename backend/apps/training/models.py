"""Public training portal — content managed in the Django admin.

Tests, questions, attempts and answers are NOT here: the portal uses the
testing module (Test / Question / TestSession / StudentAttempt). A
training session marked «Публичная тренировка» (TestSession.is_public) is
what the portal lists. This app only adds what the testing module has no
place for: the portal's own texts and exam link, useful videos and links.
"""
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator, URLValidator
from django.db import models

validate_http_url = URLValidator(schemes=["http", "https"], message="Укажите ссылку, начинающуюся с http:// или https://.")


class PortalSettings(models.Model):
    """One row: the portal's hero texts and the real exam link («Экзаменге өтүү»)."""

    hero_title = models.CharField("Заголовок главной", max_length=120, default="Экзаменге даярдан")
    hero_subtitle = models.CharField(
        "Подзаголовок главной", max_length=300,
        default="Билимиңди текшер, машыгып көр жана экзаменге ишенимдүү даярдан.",
    )
    start_button_label = models.CharField("Текст кнопки тренировки", max_length=60, default="Тренировка баштоо")
    exam_button_label = models.CharField("Текст кнопки экзамена", max_length=60, default="Экзаменге өтүү")
    exam_url = models.URLField(
        "Ссылка на настоящий экзамен", max_length=500, blank=True, validators=[validate_http_url],
        help_text="Куда ведёт кнопка «Экзаменге өтүү» (например, кабинет студента LMS). Пусто — кнопка скрыта.",
    )
    exam_open_in_new_tab = models.BooleanField("Открывать экзамен в новой вкладке", default=False)
    updated_at = models.DateTimeField("Обновлено", auto_now=True)

    class Meta:
        verbose_name = "Настройки портала"
        verbose_name_plural = "Настройки портала"

    def __str__(self):
        return "Настройки тренировочного портала"

    def save(self, *args, **kwargs):
        self.pk = 1  # singleton
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Настройки портала нельзя удалить.")

    @classmethod
    def load(cls) -> "PortalSettings":
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class PublishedQuerySet(models.QuerySet):
    def published(self):
        return self.filter(published=True).order_by("order", "id")


class TrainingVideo(models.Model):
    title = models.CharField("Название", max_length=200)
    description = models.TextField("Описание", blank=True)
    video_url = models.URLField(
        "Ссылка на видео", max_length=500, validators=[validate_http_url],
        help_text="YouTube, Vimeo или прямая ссылка на видеофайл (.mp4/.webm). Файл на сервер не загружается.",
    )
    thumbnail_url = models.URLField(
        "Обложка (URL)", max_length=500, blank=True, validators=[validate_http_url],
        help_text="Необязательно: для YouTube обложка подставляется автоматически.",
    )
    category = models.CharField("Категория", max_length=60, blank=True)
    duration = models.CharField("Длительность", max_length=16, blank=True, help_text="Например: 12:30.")
    order = models.PositiveIntegerField("Порядок", default=0)
    published = models.BooleanField("Опубликовано", default=False, db_index=True)
    created_at = models.DateTimeField("Создано", auto_now_add=True)
    updated_at = models.DateTimeField("Обновлено", auto_now=True)

    objects = PublishedQuerySet.as_manager()

    class Meta:
        ordering = ["order", "id"]
        verbose_name = "Видео"
        verbose_name_plural = "Видео"

    def __str__(self):
        return self.title


validate_icon = RegexValidator(r"^[a-z0-9-]{1,40}$", "Имя иконки Bootstrap Icons без «bi-», например: filetype-py.")


class TrainingLink(models.Model):
    title = models.CharField("Название", max_length=200)
    description = models.TextField("Описание", blank=True)
    url = models.URLField("Ссылка", max_length=500, validators=[validate_http_url])
    category = models.CharField("Категория", max_length=60, blank=True)
    icon = models.CharField(
        "Иконка", max_length=40, blank=True, validators=[validate_icon],
        help_text="Имя из Bootstrap Icons (icons.getbootstrap.com) без «bi-»: filetype-py, book, link-45deg…",
    )
    order = models.PositiveIntegerField("Порядок", default=0)
    published = models.BooleanField("Опубликовано", default=False, db_index=True)
    created_at = models.DateTimeField("Создано", auto_now_add=True)
    updated_at = models.DateTimeField("Обновлено", auto_now=True)

    objects = PublishedQuerySet.as_manager()

    class Meta:
        ordering = ["order", "id"]
        verbose_name = "Полезная ссылка"
        verbose_name_plural = "Полезные ссылки"

    def __str__(self):
        return self.title
