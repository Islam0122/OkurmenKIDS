"""Public academy news — what OkurmenKids Digital shows on /news.

An article is written in the Django admin (cover, text, category, any number
of photos with captions), saved as a draft, published at once or scheduled
for a date, and can be unpublished again. Visitors see an article only when
it is **published and its publication time has come** (`Article.objects.public()`).
"""
from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone

from .images import make_variants, upload_path, validate_image
from .slugs import unique_slug


class ArticleQuerySet(models.QuerySet):
    def public(self, now=None):
        now = now or timezone.now()
        return self.filter(status=Article.Status.PUBLISHED, published_at__lte=now)


class Article(models.Model):
    class Category(models.TextChoices):
        EVENTS = "events", "Мероприятия академии"
        ACHIEVEMENTS = "achievements", "Достижения студентов"
        COMPETITIONS = "competitions", "Соревнования"
        EDUCATION = "education", "Обучение"
        ANNOUNCEMENTS = "announcements", "Объявления"
        ACTIVITIES = "activities", "Активности"

    class Status(models.TextChoices):
        DRAFT = "draft", "Черновик"
        PUBLISHED = "published", "Опубликована"

    title = models.CharField(max_length=200, verbose_name="Заголовок")
    slug = models.SlugField(
        max_length=220, unique=True, blank=True, allow_unicode=False, verbose_name="Адрес (slug)",
        help_text="Часть адреса /news/<slug>. Пусто — создаётся из заголовка.",
    )
    category = models.CharField(max_length=20, choices=Category.choices, default=Category.EVENTS, db_index=True,
                                verbose_name="Категория")
    excerpt = models.CharField(max_length=300, blank=True, verbose_name="Краткое описание",
                               help_text="1–2 предложения для карточки и превью ссылки.")
    body = models.TextField(
        blank=True, verbose_name="Текст статьи",
        help_text="Абзацы разделяйте пустой строкой. «## » в начале строки — подзаголовок, «- » — пункт списка.",
    )

    # Translations for the public site (/ky, /en). Empty — the Russian text is shown.
    title_ky = models.CharField(max_length=200, blank=True, verbose_name="Заголовок (кыргызча)")
    title_en = models.CharField(max_length=200, blank=True, verbose_name="Заголовок (English)")
    excerpt_ky = models.CharField(max_length=300, blank=True, verbose_name="Краткое описание (кыргызча)")
    excerpt_en = models.CharField(max_length=300, blank=True, verbose_name="Краткое описание (English)")
    body_ky = models.TextField(blank=True, verbose_name="Текст (кыргызча)")
    body_en = models.TextField(blank=True, verbose_name="Текст (English)")
    seo_title = models.CharField(max_length=70, blank=True, verbose_name="SEO title",
                                 help_text="Заголовок для поисковиков и соцсетей. Пусто — заголовок новости.")
    seo_description = models.CharField(max_length=200, blank=True, verbose_name="SEO description",
                                       help_text="Описание для поисковиков. Пусто — краткое описание.")
    cover = models.ImageField(upload_to=upload_path, max_length=255, blank=True, validators=[validate_image],
                              verbose_name="Обложка", help_text="JPEG, PNG или WebP до 15 МБ. Лучше горизонтальная, от 1600 px.")
    cover_caption = models.CharField(max_length=200, blank=True, verbose_name="Подпись к обложке")
    cover_large = models.ImageField(upload_to=upload_path, max_length=255, blank=True, editable=False)
    cover_thumb = models.ImageField(upload_to=upload_path, max_length=255, blank=True, editable=False)
    cover_width = models.PositiveIntegerField(null=True, blank=True, editable=False)
    cover_height = models.PositiveIntegerField(null=True, blank=True, editable=False)

    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT, db_index=True,
                              verbose_name="Статус")
    published_at = models.DateTimeField(
        default=timezone.now, db_index=True, verbose_name="Дата публикации",
        help_text="Дата в будущем — статья появится на сайте в это время (отложенная публикация).",
    )
    is_featured = models.BooleanField(default=False, verbose_name="Главная новость",
                                      help_text="Показывать крупно в начале страницы новостей.")

    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                               related_name="academy_articles", verbose_name="Автор")
    show_author = models.BooleanField(default=False, verbose_name="Показывать автора на сайте",
                                      help_text="Имя автора видно посетителям только с этой галочкой.")

    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Создана")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Изменена")

    objects = ArticleQuerySet.as_manager()

    class Meta:
        verbose_name = "Новость академии"
        verbose_name_plural = "Новости академии"
        ordering = ["-published_at", "-id"]

    def __str__(self):
        return self.title

    @property
    def is_public(self) -> bool:
        return self.status == self.Status.PUBLISHED and self.published_at <= timezone.now()

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = unique_slug(Article, self.title, exclude_pk=self.pk)
        previous = Article.objects.filter(pk=self.pk).values_list("cover", flat=True).first() if self.pk else None
        cover_changed = bool(self.cover) and self.cover.name != previous
        if not self.cover:
            _drop(self.cover_large, self.cover_thumb)
            self.cover_large = self.cover_thumb = None
            self.cover_width = self.cover_height = None
        super().save(*args, **kwargs)
        if cover_changed:
            _drop(self.cover_large, self.cover_thumb)
            self.cover_width, self.cover_height, files = make_variants(self.cover)
            self.cover_large.save(files["large"].name, files["large"], save=False)
            self.cover_thumb.save(files["thumb"].name, files["thumb"], save=False)
            super().save(update_fields=["cover_large", "cover_thumb", "cover_width", "cover_height"])


class ArticlePhoto(models.Model):
    article = models.ForeignKey(Article, on_delete=models.CASCADE, related_name="photos", verbose_name="Новость")
    image = models.ImageField(upload_to=upload_path, max_length=255, validators=[validate_image],
                              verbose_name="Фотография")
    caption = models.CharField(max_length=200, blank=True, verbose_name="Подпись")
    order = models.PositiveIntegerField(default=0, verbose_name="Порядок")
    large = models.ImageField(upload_to=upload_path, max_length=255, blank=True, editable=False)
    thumb = models.ImageField(upload_to=upload_path, max_length=255, blank=True, editable=False)
    width = models.PositiveIntegerField(null=True, blank=True, editable=False)
    height = models.PositiveIntegerField(null=True, blank=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Фотография"
        verbose_name_plural = "Фотографии"
        ordering = ["order", "id"]

    def __str__(self):
        return self.caption or f"Фото #{self.pk}"

    def save(self, *args, **kwargs):
        previous = ArticlePhoto.objects.filter(pk=self.pk).values_list("image", flat=True).first() if self.pk else None
        changed = bool(self.image) and self.image.name != previous
        super().save(*args, **kwargs)
        if changed:
            _drop(self.large, self.thumb)
            self.width, self.height, files = make_variants(self.image)
            self.large.save(files["large"].name, files["large"], save=False)
            self.thumb.save(files["thumb"].name, files["thumb"], save=False)
            super().save(update_fields=["large", "thumb", "width", "height"])


def _drop(*files) -> None:
    for field_file in files:
        if field_file:
            field_file.delete(save=False)


def _delete_files(sender, instance, **kwargs):
    """A deleted article or photo leaves no files behind."""
    if isinstance(instance, Article):
        _drop(instance.cover, instance.cover_large, instance.cover_thumb)
    else:
        _drop(instance.image, instance.large, instance.thumb)


models.signals.post_delete.connect(_delete_files, sender=Article, dispatch_uid="academy_news_drop_article_files")
models.signals.post_delete.connect(_delete_files, sender=ArticlePhoto, dispatch_uid="academy_news_drop_photo_files")
