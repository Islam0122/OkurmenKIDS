"""Public website content — what okurmen-public-website shows.

Everything here is edited by the marketing team in the LMS cabinet
(`/api/v1/marketing/site/`, see `cms_views.py`) or by an administrator in the
Django admin. Visitors read it through `/api/v1/public/site/` (`public.py`):
only records that are **published and whose publication time has come**,
through a closed whitelist of fields.

Reused, not duplicated:

* courses — `academy.Course` stays the academic source of truth; `CoursePage`
  only adds the marketing description of a course for the site;
* trainers — `users.Teacher`; `TeamMember` is the *approved public profile*
  (a teacher appears on the site only through one, with an explicit photo
  consent);
* news — `academy_news.Article` (unchanged), student projects —
  `projects.StudentProject` (unchanged, managed by trainers).

Translations: the Russian field is the main one; `*_ky` and `*_en` are
optional — an empty translation falls back to Russian (`public.tr`).

Rich text (`body` fields) is plain text in a small, safe markup (no HTML is
ever stored or rendered) — see `docs/website.md`.
"""
from __future__ import annotations

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone

from apps.academy_news.images import make_variants, validate_image
from apps.academy_news.slugs import unique_slug

import os
import uuid


def upload_path(instance, filename: str) -> str:
    ext = os.path.splitext(filename)[1].lower()[:10]
    return f"site/{instance._meta.model_name}/{timezone.now():%Y/%m}/{uuid.uuid4().hex}{ext}"


def media_upload_path(instance, filename: str) -> str:
    ext = os.path.splitext(filename)[1].lower()[:10]
    return f"site/library/{timezone.now():%Y/%m}/{uuid.uuid4().hex}{ext}"


def _drop(*files) -> None:
    for field_file in files:
        if field_file:
            try:
                field_file.delete(save=False)
            except Exception:  # noqa: BLE001 — a missing file must not block saving
                pass


def refresh_variants(instance, source: str, large: str, thumb: str, width: str, height: str, previous: str | None):
    """WebP copies (large ≤ 1600 px, thumb ≤ 640 px) of an image field —
    the same pipeline as the public news (`academy_news.images`)."""
    original = getattr(instance, source)
    if not original:
        _drop(getattr(instance, large), getattr(instance, thumb))
        if getattr(instance, large) or getattr(instance, thumb) or getattr(instance, width):
            setattr(instance, large, None)
            setattr(instance, thumb, None)
            setattr(instance, width, None)
            setattr(instance, height, None)
            return True
        return False
    if original.name == previous and getattr(instance, large):
        return False
    _drop(getattr(instance, large), getattr(instance, thumb))
    w, h, files = make_variants(original)
    getattr(instance, large).save(files["large"].name, files["large"], save=False)
    getattr(instance, thumb).save(files["thumb"].name, files["thumb"], save=False)
    setattr(instance, width, w)
    setattr(instance, height, h)
    return True


def validate_video_url(value: str) -> None:
    from .markup import video_embed

    if value and not video_embed(value):
        raise ValidationError("Нужна ссылка на YouTube или Vimeo.")


# ---------------------------------------------------------------------------
# Publication workflow
# ---------------------------------------------------------------------------

class Workflow(models.TextChoices):
    DRAFT = "draft", "Черновик"
    REVIEW = "review", "На согласовании"
    PUBLISHED = "published", "Опубликовано"
    ARCHIVED = "archived", "В архиве"


class PublicQuerySet(models.QuerySet):
    def public(self, now=None):
        """Published and the publication time has come («Запланировано» =
        published with a future date)."""
        now = now or timezone.now()
        return self.filter(status=Workflow.PUBLISHED, published_at__lte=now)


class Publishable(models.Model):
    status = models.CharField(max_length=10, choices=Workflow.choices, default=Workflow.DRAFT, db_index=True,
                              verbose_name="Статус")
    published_at = models.DateTimeField(default=timezone.now, db_index=True, verbose_name="Дата публикации",
                                        help_text="Дата в будущем — материал появится на сайте в это время.")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                   related_name="+", editable=False, verbose_name="Автор")
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                    related_name="+", editable=False, verbose_name="Утвердил")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Создано")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Изменено")

    objects = PublicQuerySet.as_manager()

    class Meta:
        abstract = True

    @property
    def is_public(self) -> bool:
        return self.status == Workflow.PUBLISHED and self.published_at <= timezone.now()

    @property
    def workflow_state(self) -> str:
        """draft / review / scheduled / published / archived — «scheduled» is
        a published record whose time has not come yet."""
        if self.status == Workflow.PUBLISHED and self.published_at > timezone.now():
            return "scheduled"
        return self.status


class CoverImage(models.Model):
    cover = models.ImageField(upload_to=upload_path, max_length=255, blank=True, validators=[validate_image],
                              verbose_name="Обложка")
    cover_large = models.ImageField(upload_to=upload_path, max_length=255, blank=True, editable=False)
    cover_thumb = models.ImageField(upload_to=upload_path, max_length=255, blank=True, editable=False)
    cover_width = models.PositiveIntegerField(null=True, blank=True, editable=False)
    cover_height = models.PositiveIntegerField(null=True, blank=True, editable=False)

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        previous = type(self).objects.filter(pk=self.pk).values_list("cover", flat=True).first() if self.pk else None
        super().save(*args, **kwargs)
        if refresh_variants(self, "cover", "cover_large", "cover_thumb", "cover_width", "cover_height", previous):
            super().save(update_fields=["cover_large", "cover_thumb", "cover_width", "cover_height"])

    def delete(self, *args, **kwargs):
        files = (self.cover, self.cover_large, self.cover_thumb)
        result = super().delete(*args, **kwargs)
        _drop(*files)
        return result


class Photo(models.Model):
    """A gallery photo (event, achievement) with WebP copies."""

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
        abstract = True
        ordering = ["order", "id"]

    def __str__(self):
        return self.caption or f"Фото #{self.pk}"

    def save(self, *args, **kwargs):
        previous = type(self).objects.filter(pk=self.pk).values_list("image", flat=True).first() if self.pk else None
        super().save(*args, **kwargs)
        if refresh_variants(self, "image", "large", "thumb", "width", "height", previous):
            super().save(update_fields=["large", "thumb", "width", "height"])

    def delete(self, *args, **kwargs):
        files = (self.image, self.large, self.thumb)
        result = super().delete(*args, **kwargs)
        _drop(*files)
        return result


def _slug_save(instance, *args, **kwargs):
    if not instance.slug:
        instance.slug = unique_slug(type(instance), instance.title, exclude_pk=instance.pk)


# ---------------------------------------------------------------------------
# Site settings, homepage
# ---------------------------------------------------------------------------

class SiteSettings(models.Model):
    """The single settings record (pk=1): hero, contacts, about texts."""

    hero_title = models.CharField(max_length=160, default="Будущее начинается с первой строки кода",
                                  verbose_name="Заголовок главного экрана")
    hero_title_ky = models.CharField(max_length=160, blank=True, verbose_name="Заголовок (кыргызча)")
    hero_title_en = models.CharField(max_length=160, blank=True, verbose_name="Заголовок (English)")
    hero_subtitle = models.TextField(blank=True, verbose_name="Текст главного экрана")
    hero_subtitle_ky = models.TextField(blank=True, verbose_name="Текст (кыргызча)")
    hero_subtitle_en = models.TextField(blank=True, verbose_name="Текст (English)")
    hero_image = models.ImageField(upload_to=upload_path, max_length=255, blank=True, validators=[validate_image],
                                   verbose_name="Фото главного экрана")
    intro_video_url = models.URLField(max_length=300, blank=True, validators=[validate_video_url],
                                      verbose_name="Видео об академии (YouTube / Vimeo)")
    primary_cta_label = models.CharField(max_length=60, blank=True, verbose_name="Кнопка 1 — текст",
                                         help_text="Пусто — «Записать ребёнка».")
    primary_cta_url = models.CharField(max_length=300, blank=True, verbose_name="Кнопка 1 — ссылка",
                                       help_text="Пусто — форма записи.")
    secondary_cta_label = models.CharField(max_length=60, blank=True, verbose_name="Кнопка 2 — текст",
                                           help_text="Пусто — «Посмотреть курсы».")
    secondary_cta_url = models.CharField(max_length=300, blank=True, verbose_name="Кнопка 2 — ссылка",
                                         help_text="Пусто — /courses.")

    about_story = models.TextField(blank=True, verbose_name="История академии")
    about_story_ky = models.TextField(blank=True, verbose_name="История (кыргызча)")
    about_story_en = models.TextField(blank=True, verbose_name="История (English)")
    mission = models.TextField(blank=True, verbose_name="Миссия")
    mission_ky = models.TextField(blank=True, verbose_name="Миссия (кыргызча)")
    mission_en = models.TextField(blank=True, verbose_name="Миссия (English)")
    vision = models.TextField(blank=True, verbose_name="Видение")
    vision_ky = models.TextField(blank=True, verbose_name="Видение (кыргызча)")
    vision_en = models.TextField(blank=True, verbose_name="Видение (English)")

    phone = models.CharField(max_length=40, blank=True, verbose_name="Телефон")
    whatsapp = models.CharField(max_length=40, blank=True, verbose_name="WhatsApp (номер)")
    telegram = models.CharField(max_length=100, blank=True, verbose_name="Telegram (@имя или ссылка)")
    instagram = models.CharField(max_length=100, blank=True, verbose_name="Instagram (@имя или ссылка)")
    email = models.EmailField(blank=True, verbose_name="E-mail")
    working_hours = models.CharField(max_length=120, blank=True, verbose_name="Часы работы")

    featured_projects = models.ManyToManyField("projects.StudentProject", blank=True, related_name="+",
                                               verbose_name="Проекты на главной",
                                               help_text="Показываются только опубликованные. Пусто — последние.")
    featured_news = models.ManyToManyField("academy_news.Article", blank=True, related_name="+",
                                           verbose_name="Новости на главной",
                                           help_text="Показываются только опубликованные. Пусто — последние.")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Настройки сайта"
        verbose_name_plural = "Настройки сайта"

    def __str__(self):
        return "Настройки сайта"

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls) -> "SiteSettings":
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class HomeSection(models.Model):
    """Visibility and order of the homepage blocks."""

    class Key(models.TextChoices):
        VIDEO = "video", "Видео об академии"
        STATS = "stats", "Статистика"
        COURSES = "courses", "Популярные курсы"
        PROJECTS = "projects", "Проекты студентов"
        ACHIEVEMENTS = "achievements", "Достижения"
        NEWS = "news", "Новости"
        EVENTS = "events", "Мероприятия"
        TEAM = "team", "Преподаватели"
        TESTIMONIALS = "testimonials", "Отзывы"
        CTA = "cta", "Призыв записаться"

    key = models.CharField(max_length=20, choices=Key.choices, unique=True, verbose_name="Блок")
    is_visible = models.BooleanField(default=True, verbose_name="Показывать")
    order = models.PositiveIntegerField(default=0, verbose_name="Порядок")
    title = models.CharField(max_length=120, blank=True, verbose_name="Свой заголовок",
                             help_text="Пусто — стандартный заголовок блока.")
    title_ky = models.CharField(max_length=120, blank=True, verbose_name="Заголовок (кыргызча)")
    title_en = models.CharField(max_length=120, blank=True, verbose_name="Заголовок (English)")

    class Meta:
        verbose_name = "Блок главной страницы"
        verbose_name_plural = "Блоки главной страницы"
        ordering = ["order", "id"]

    def __str__(self):
        return self.get_key_display()


class Statistic(models.Model):
    value = models.CharField(max_length=20, verbose_name="Значение", help_text="Например: 1200+, 8 лет, 95%")
    label = models.CharField(max_length=80, verbose_name="Подпись")
    label_ky = models.CharField(max_length=80, blank=True, verbose_name="Подпись (кыргызча)")
    label_en = models.CharField(max_length=80, blank=True, verbose_name="Подпись (English)")
    order = models.PositiveIntegerField(default=0, verbose_name="Порядок")
    is_active = models.BooleanField(default=True, verbose_name="Показывать")

    class Meta:
        verbose_name = "Показатель академии"
        verbose_name_plural = "Показатели академии"
        ordering = ["order", "id"]

    def __str__(self):
        return f"{self.value} — {self.label}"


class Branch(models.Model):
    name = models.CharField(max_length=120, verbose_name="Название")
    name_ky = models.CharField(max_length=120, blank=True, verbose_name="Название (кыргызча)")
    name_en = models.CharField(max_length=120, blank=True, verbose_name="Название (English)")
    address = models.CharField(max_length=255, verbose_name="Адрес")
    address_ky = models.CharField(max_length=255, blank=True, verbose_name="Адрес (кыргызча)")
    address_en = models.CharField(max_length=255, blank=True, verbose_name="Адрес (English)")
    phone = models.CharField(max_length=40, blank=True, verbose_name="Телефон")
    working_hours = models.CharField(max_length=120, blank=True, verbose_name="Часы работы")
    map_url = models.URLField(max_length=500, blank=True, verbose_name="Ссылка на карту (Google Maps / 2GIS)")
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True, verbose_name="Широта")
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True, verbose_name="Долгота")
    order = models.PositiveIntegerField(default=0, verbose_name="Порядок")
    is_active = models.BooleanField(default=True, verbose_name="Показывать на сайте")

    class Meta:
        verbose_name = "Филиал"
        verbose_name_plural = "Филиалы"
        ordering = ["order", "id"]

    def __str__(self):
        return self.name


class PromoBanner(models.Model):
    title = models.CharField(max_length=120, verbose_name="Заголовок")
    title_ky = models.CharField(max_length=120, blank=True, verbose_name="Заголовок (кыргызча)")
    title_en = models.CharField(max_length=120, blank=True, verbose_name="Заголовок (English)")
    text = models.CharField(max_length=300, blank=True, verbose_name="Текст")
    text_ky = models.CharField(max_length=300, blank=True, verbose_name="Текст (кыргызча)")
    text_en = models.CharField(max_length=300, blank=True, verbose_name="Текст (English)")
    image = models.ImageField(upload_to=upload_path, max_length=255, blank=True, validators=[validate_image],
                              verbose_name="Изображение")
    cta_label = models.CharField(max_length=60, blank=True, verbose_name="Текст кнопки")
    cta_url = models.CharField(max_length=300, blank=True, verbose_name="Ссылка кнопки")
    starts_at = models.DateTimeField(null=True, blank=True, verbose_name="Показывать с")
    ends_at = models.DateTimeField(null=True, blank=True, verbose_name="Показывать до")
    is_active = models.BooleanField(default=True, verbose_name="Включён")
    order = models.PositiveIntegerField(default=0, verbose_name="Порядок")

    class Meta:
        verbose_name = "Промо-баннер"
        verbose_name_plural = "Промо-баннеры"
        ordering = ["order", "id"]

    def __str__(self):
        return self.title


# ---------------------------------------------------------------------------
# Courses
# ---------------------------------------------------------------------------

PROJECT_CATEGORIES = (
    ("", "—"), ("html-css", "HTML / CSS"), ("javascript", "JavaScript"), ("react", "React"),
    ("python", "Python"), ("other", "Другое"),
)


class CoursePage(Publishable, CoverImage):
    """The public page of a course. Linked to `academy.Course` when the course
    exists in the LMS (the number of lessons comes from there); the marketing
    texts live here. Nothing (price, duration, guarantees) is invented —
    empty fields are simply not shown."""

    class Icon(models.TextChoices):
        CODE = "code", "Код"
        PYTHON = "python", "Python"
        WEB = "web", "Веб"
        GAME = "game", "Игры"
        ROBOT = "robot", "Робототехника"
        DIGITAL = "digital", "Цифровые навыки"
        DESIGN = "design", "Дизайн"

    course = models.OneToOneField("academy.Course", on_delete=models.SET_NULL, null=True, blank=True,
                                  related_name="site_page", verbose_name="Курс в LMS")
    slug = models.SlugField(max_length=220, unique=True, blank=True, allow_unicode=False, verbose_name="Адрес (slug)")
    title = models.CharField(max_length=150, verbose_name="Название")
    title_ky = models.CharField(max_length=150, blank=True, verbose_name="Название (кыргызча)")
    title_en = models.CharField(max_length=150, blank=True, verbose_name="Название (English)")
    tagline = models.CharField(max_length=200, blank=True, verbose_name="Короткое описание")
    tagline_ky = models.CharField(max_length=200, blank=True, verbose_name="Короткое описание (кыргызча)")
    tagline_en = models.CharField(max_length=200, blank=True, verbose_name="Короткое описание (English)")
    body = models.TextField(blank=True, verbose_name="Описание")
    body_ky = models.TextField(blank=True, verbose_name="Описание (кыргызча)")
    body_en = models.TextField(blank=True, verbose_name="Описание (English)")
    outcomes = models.TextField(blank=True, verbose_name="Чему научится ребёнок", help_text="Один пункт — одна строка.")
    outcomes_ky = models.TextField(blank=True, verbose_name="Чему научится (кыргызча)")
    outcomes_en = models.TextField(blank=True, verbose_name="Чему научится (English)")
    curriculum = models.TextField(blank=True, verbose_name="Программа",
                                  help_text="Один модуль — одна строка: «Название: описание».")
    curriculum_ky = models.TextField(blank=True, verbose_name="Программа (кыргызча)")
    curriculum_en = models.TextField(blank=True, verbose_name="Программа (English)")
    age_min = models.PositiveSmallIntegerField(null=True, blank=True, validators=[MinValueValidator(3), MaxValueValidator(25)],
                                               verbose_name="Возраст от")
    age_max = models.PositiveSmallIntegerField(null=True, blank=True, validators=[MinValueValidator(3), MaxValueValidator(25)],
                                               verbose_name="Возраст до")
    duration = models.CharField(max_length=80, blank=True, verbose_name="Длительность", help_text="Например: 9 месяцев")
    duration_ky = models.CharField(max_length=80, blank=True, verbose_name="Длительность (кыргызча)")
    duration_en = models.CharField(max_length=80, blank=True, verbose_name="Длительность (English)")
    schedule = models.CharField(max_length=120, blank=True, verbose_name="Формат занятий",
                                help_text="Например: 2 раза в неделю по 90 минут")
    price = models.CharField(max_length=80, blank=True, verbose_name="Стоимость",
                             help_text="Пусто — не показывается на сайте.")
    icon = models.CharField(max_length=10, choices=Icon.choices, default=Icon.CODE, verbose_name="Иконка")
    project_category = models.CharField(max_length=12, choices=PROJECT_CATEGORIES, blank=True,
                                        verbose_name="Примеры проектов",
                                        help_text="Категория опубликованных проектов студентов для этого курса.")
    is_featured = models.BooleanField(default=False, verbose_name="Популярный (на главной)")
    order = models.PositiveIntegerField(default=0, verbose_name="Порядок")

    class Meta:
        verbose_name = "Курс на сайте"
        verbose_name_plural = "Курсы на сайте"
        ordering = ["order", "id"]

    def __str__(self):
        return self.title

    def clean(self):
        if self.age_min and self.age_max and self.age_min > self.age_max:
            raise ValidationError({"age_max": "«Возраст до» меньше «Возраст от»."})

    def save(self, *args, **kwargs):
        _slug_save(self)
        super().save(*args, **kwargs)


# ---------------------------------------------------------------------------
# Team
# ---------------------------------------------------------------------------

class TeamMember(Publishable):
    """An approved public profile. A trainer (`users.Teacher`) appears on the
    site only through one of these; the photo is shown only with
    `photo_approved`."""

    teacher = models.OneToOneField("users.Teacher", on_delete=models.SET_NULL, null=True, blank=True,
                                   related_name="site_profile", verbose_name="Тренер в LMS")
    name = models.CharField(max_length=120, blank=True, verbose_name="Имя на сайте",
                            help_text="Пусто — имя и фамилия тренера из LMS.")
    position = models.CharField(max_length=120, verbose_name="Должность")
    position_ky = models.CharField(max_length=120, blank=True, verbose_name="Должность (кыргызча)")
    position_en = models.CharField(max_length=120, blank=True, verbose_name="Должность (English)")
    specialization = models.CharField(max_length=160, blank=True, verbose_name="Специализация",
                                      help_text="Например: Python, веб-разработка")
    bio = models.TextField(blank=True, verbose_name="О себе")
    bio_ky = models.TextField(blank=True, verbose_name="О себе (кыргызча)")
    bio_en = models.TextField(blank=True, verbose_name="О себе (English)")
    experience_years = models.PositiveSmallIntegerField(null=True, blank=True, validators=[MaxValueValidator(60)],
                                                        verbose_name="Опыт (лет)",
                                                        help_text="Пусто — опыт из LMS (если указан) или не показывается.")
    photo = models.ImageField(upload_to=upload_path, max_length=255, blank=True, validators=[validate_image],
                              verbose_name="Фото для сайта", help_text="Пусто — фото из профиля тренера.")
    photo_approved = models.BooleanField(default=False, verbose_name="Фото согласовано для сайта")
    order = models.PositiveIntegerField(default=0, verbose_name="Порядок")

    class Meta:
        verbose_name = "Сотрудник на сайте"
        verbose_name_plural = "Команда на сайте"
        ordering = ["order", "id"]

    def __str__(self):
        return self.display_name or f"Профиль #{self.pk}"

    @property
    def display_name(self) -> str:
        if self.name:
            return self.name
        if self.teacher_id:
            return self.teacher.user.get_full_name()
        return ""

    def clean(self):
        if not self.name and not self.teacher_id:
            raise ValidationError({"name": "Укажите имя или выберите тренера."})


# ---------------------------------------------------------------------------
# Events
# ---------------------------------------------------------------------------

class Event(Publishable, CoverImage):
    class Category(models.TextChoices):
        OPEN_DAY = "open_day", "День открытых дверей"
        HACKATHON = "hackathon", "Хакатон"
        COMPETITION = "competition", "IT-соревнование"
        WORKSHOP = "workshop", "Мастер-класс"
        PRESENTATION = "presentation", "Презентация проектов"
        PARENT_MEETING = "parent_meeting", "Встреча с родителями"
        OTHER = "other", "Другое"

    slug = models.SlugField(max_length=220, unique=True, blank=True, verbose_name="Адрес (slug)")
    title = models.CharField(max_length=200, verbose_name="Название")
    title_ky = models.CharField(max_length=200, blank=True, verbose_name="Название (кыргызча)")
    title_en = models.CharField(max_length=200, blank=True, verbose_name="Название (English)")
    excerpt = models.CharField(max_length=300, blank=True, verbose_name="Короткое описание")
    excerpt_ky = models.CharField(max_length=300, blank=True, verbose_name="Короткое описание (кыргызча)")
    excerpt_en = models.CharField(max_length=300, blank=True, verbose_name="Короткое описание (English)")
    body = models.TextField(blank=True, verbose_name="Описание")
    body_ky = models.TextField(blank=True, verbose_name="Описание (кыргызча)")
    body_en = models.TextField(blank=True, verbose_name="Описание (English)")
    category = models.CharField(max_length=20, choices=Category.choices, default=Category.OTHER, db_index=True,
                                verbose_name="Тип")
    starts_at = models.DateTimeField(db_index=True, verbose_name="Начало")
    ends_at = models.DateTimeField(null=True, blank=True, verbose_name="Окончание")
    location = models.CharField(max_length=255, blank=True, verbose_name="Место")
    branch = models.ForeignKey(Branch, on_delete=models.SET_NULL, null=True, blank=True, related_name="events",
                               verbose_name="Филиал")
    registration_enabled = models.BooleanField(default=False, verbose_name="Регистрация открыта")
    registration_limit = models.PositiveIntegerField(null=True, blank=True, verbose_name="Мест",
                                                     help_text="Пусто — без ограничения.")
    registration_deadline = models.DateTimeField(null=True, blank=True, verbose_name="Регистрация до",
                                                 help_text="Пусто — до начала мероприятия.")
    is_featured = models.BooleanField(default=False, verbose_name="На главной")

    class Meta:
        verbose_name = "Мероприятие"
        verbose_name_plural = "Мероприятия"
        ordering = ["-starts_at", "-id"]

    def __str__(self):
        return self.title

    def clean(self):
        if self.ends_at and self.starts_at and self.ends_at < self.starts_at:
            raise ValidationError({"ends_at": "Окончание раньше начала."})

    def save(self, *args, **kwargs):
        _slug_save(self)
        super().save(*args, **kwargs)

    def phase(self, now=None) -> str:
        """upcoming / ongoing / completed."""
        now = now or timezone.now()
        end = self.ends_at or self.starts_at
        if now < self.starts_at:
            return "upcoming"
        if now <= end or (self.ends_at is None and now.date() == timezone.localtime(self.starts_at).date()):
            return "ongoing"
        return "completed"

    def registration_open(self, now=None, taken: int | None = None) -> bool:
        now = now or timezone.now()
        if not self.registration_enabled:
            return False
        deadline = self.registration_deadline or self.starts_at
        if now > deadline:
            return False
        if self.registration_limit is not None:
            count = taken if taken is not None else self.registrations.exclude(
                status=EventRegistration.Status.CANCELLED).count()
            if count >= self.registration_limit:
                return False
        return True


class EventPhoto(Photo):
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="photos", verbose_name="Мероприятие")

    class Meta(Photo.Meta):
        verbose_name = "Фото мероприятия"
        verbose_name_plural = "Фото мероприятия"


class EventRegistration(models.Model):
    """Registration from the public site. Personal data — visible only in
    the LMS (marketing, admin, director), never through the public API."""

    class Status(models.TextChoices):
        NEW = "new", "Новая"
        CONFIRMED = "confirmed", "Подтверждена"
        ATTENDED = "attended", "Пришёл"
        CANCELLED = "cancelled", "Отменена"

    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="registrations",
                              verbose_name="Мероприятие")
    parent_name = models.CharField(max_length=120, verbose_name="Имя")
    phone = models.CharField(max_length=40, verbose_name="Телефон")
    phone_digits = models.CharField(max_length=20, db_index=True, editable=False)
    child_name = models.CharField(max_length=120, blank=True, verbose_name="Имя ребёнка")
    child_age = models.PositiveSmallIntegerField(null=True, blank=True, verbose_name="Возраст ребёнка")
    comment = models.TextField(blank=True, verbose_name="Комментарий")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.NEW, db_index=True,
                              verbose_name="Статус")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Получена")

    class Meta:
        verbose_name = "Регистрация на мероприятие"
        verbose_name_plural = "Регистрации на мероприятия"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.parent_name} — {self.event}"


# ---------------------------------------------------------------------------
# Achievements
# ---------------------------------------------------------------------------

class Achievement(Publishable, CoverImage):
    class Category(models.TextChoices):
        COMPETITION = "competition", "Победа в соревновании"
        AWARD = "award", "Награда"
        CERTIFICATE = "certificate", "Сертификат"
        STUDENT = "student", "Успех студента"
        MILESTONE = "milestone", "Этап развития академии"
        PARTNERSHIP = "partnership", "Партнёрство"
        RECOGNITION = "recognition", "Признание"

    slug = models.SlugField(max_length=220, unique=True, blank=True, verbose_name="Адрес (slug)")
    title = models.CharField(max_length=200, verbose_name="Название")
    title_ky = models.CharField(max_length=200, blank=True, verbose_name="Название (кыргызча)")
    title_en = models.CharField(max_length=200, blank=True, verbose_name="Название (English)")
    excerpt = models.CharField(max_length=300, blank=True, verbose_name="Короткое описание")
    excerpt_ky = models.CharField(max_length=300, blank=True, verbose_name="Короткое описание (кыргызча)")
    excerpt_en = models.CharField(max_length=300, blank=True, verbose_name="Короткое описание (English)")
    body = models.TextField(blank=True, verbose_name="Описание")
    body_ky = models.TextField(blank=True, verbose_name="Описание (кыргызча)")
    body_en = models.TextField(blank=True, verbose_name="Описание (English)")
    category = models.CharField(max_length=20, choices=Category.choices, default=Category.AWARD, db_index=True,
                                verbose_name="Категория")
    date = models.DateField(default=timezone.localdate, db_index=True, verbose_name="Дата")
    is_featured = models.BooleanField(default=False, verbose_name="На главной")

    class Meta:
        verbose_name = "Достижение"
        verbose_name_plural = "Достижения"
        ordering = ["-date", "-id"]

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        _slug_save(self)
        super().save(*args, **kwargs)


class AchievementPhoto(Photo):
    achievement = models.ForeignKey(Achievement, on_delete=models.CASCADE, related_name="photos",
                                    verbose_name="Достижение")

    class Meta(Photo.Meta):
        verbose_name = "Фото достижения"
        verbose_name_plural = "Фото и сертификаты"


# ---------------------------------------------------------------------------
# Testimonials
# ---------------------------------------------------------------------------

class Testimonial(Publishable):
    class Role(models.TextChoices):
        PARENT = "parent", "Родитель"
        STUDENT = "student", "Студент"
        GRADUATE = "graduate", "Выпускник"

    class Language(models.TextChoices):
        RU = "ru", "Русский"
        KY = "ky", "Кыргызча"
        EN = "en", "English"

    author_name = models.CharField(max_length=120, verbose_name="Имя автора на сайте",
                                   help_text="Как автор разрешил себя подписать, например «Айгуль, мама Эмира».")
    author_role = models.CharField(max_length=10, choices=Role.choices, default=Role.PARENT, verbose_name="Кто")
    course_label = models.CharField(max_length=120, blank=True, verbose_name="Курс")
    text = models.TextField(blank=True, verbose_name="Отзыв")
    language = models.CharField(max_length=2, choices=Language.choices, default=Language.RU, verbose_name="Язык отзыва")
    rating = models.PositiveSmallIntegerField(null=True, blank=True, validators=[MinValueValidator(1), MaxValueValidator(5)],
                                              verbose_name="Оценка (1–5)")
    photo = models.ImageField(upload_to=upload_path, max_length=255, blank=True, validators=[validate_image],
                              verbose_name="Фото")
    video_url = models.URLField(max_length=300, blank=True, validators=[validate_video_url],
                                verbose_name="Видео-отзыв (YouTube / Vimeo)")
    consent = models.BooleanField(default=False, verbose_name="Есть согласие автора на публикацию",
                                  help_text="Без согласия отзыв не публикуется.")
    is_featured = models.BooleanField(default=False, verbose_name="На главной")
    order = models.PositiveIntegerField(default=0, verbose_name="Порядок")

    class Meta:
        verbose_name = "Отзыв"
        verbose_name_plural = "Отзывы"
        ordering = ["order", "-published_at", "-id"]

    def __str__(self):
        return self.author_name

    def clean(self):
        if not (self.text or self.video_url):
            raise ValidationError({"text": "Нужен текст отзыва или видео."})
        if self.status == Workflow.PUBLISHED and not self.consent:
            raise ValidationError({"consent": "Отзыв публикуется только с согласия автора."})


# ---------------------------------------------------------------------------
# Media library
# ---------------------------------------------------------------------------

class MediaCategory(models.Model):
    name = models.CharField(max_length=80, unique=True, verbose_name="Название")

    class Meta:
        verbose_name = "Папка медиатеки"
        verbose_name_plural = "Папки медиатеки"
        ordering = ["name"]

    def __str__(self):
        return self.name


MEDIA_MAX_BYTES = 80 * 1024 * 1024
MEDIA_EXTENSIONS = {
    "image": {".jpg", ".jpeg", ".png", ".webp", ".gif", ".svg"},
    "video": {".mp4", ".webm", ".mov"},
    "document": {".pdf"},
}


def validate_media_file(field_file) -> None:
    ext = os.path.splitext(field_file.name or "")[1].lower()
    if not any(ext in exts for exts in MEDIA_EXTENSIONS.values()):
        raise ValidationError("Допустимы изображения (JPEG, PNG, WebP, GIF, SVG), видео (MP4, WebM, MOV) и PDF.")
    if (getattr(field_file, "size", 0) or 0) > MEDIA_MAX_BYTES:
        raise ValidationError(f"Файл больше {MEDIA_MAX_BYTES // (1024 * 1024)} МБ.")


class MediaAsset(models.Model):
    class Kind(models.TextChoices):
        IMAGE = "image", "Изображение"
        VIDEO = "video", "Видео"
        DOCUMENT = "document", "Документ"

    title = models.CharField(max_length=200, verbose_name="Название")
    file = models.FileField(upload_to=media_upload_path, max_length=255, validators=[validate_media_file],
                            verbose_name="Файл")
    kind = models.CharField(max_length=10, choices=Kind.choices, editable=False, db_index=True, verbose_name="Тип")
    category = models.ForeignKey(MediaCategory, on_delete=models.SET_NULL, null=True, blank=True,
                                 related_name="assets", verbose_name="Папка")
    alt = models.CharField(max_length=200, blank=True, verbose_name="Описание для незрячих (alt)")
    size = models.PositiveBigIntegerField(default=0, editable=False, verbose_name="Размер, байт")
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                    related_name="+", editable=False, verbose_name="Загрузил")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Загружен")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Изменён")

    class Meta:
        verbose_name = "Файл медиатеки"
        verbose_name_plural = "Медиатека"
        ordering = ["-created_at", "-id"]

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        previous = MediaAsset.objects.filter(pk=self.pk).values_list("file", flat=True).first() if self.pk else None
        ext = os.path.splitext(self.file.name or "")[1].lower()
        self.kind = next((kind for kind, exts in MEDIA_EXTENSIONS.items() if ext in exts), self.Kind.DOCUMENT)
        try:
            self.size = self.file.size
        except (OSError, ValueError):
            pass
        super().save(*args, **kwargs)
        if previous and previous != self.file.name:
            self.file.storage.delete(previous)

    def delete(self, *args, **kwargs):
        file = self.file
        result = super().delete(*args, **kwargs)
        _drop(file)
        return result


# ---------------------------------------------------------------------------
# Enrollment leads
# ---------------------------------------------------------------------------

class Lead(models.Model):
    """«Записать ребёнка» from the public site. The LMS has no CRM
    (docs/marketing.md: campaign leads are entered by hand), so this is the
    minimal inbox the sales and marketing team work from. Personal data —
    never returned by any public endpoint."""

    class Status(models.TextChoices):
        NEW = "new", "Новая"
        CONTACTED = "contacted", "Связались"
        TRIAL = "trial", "Пробный урок"
        ENROLLED = "enrolled", "Записан"
        REJECTED = "rejected", "Отказ"

    class ContactMethod(models.TextChoices):
        PHONE = "phone", "Звонок"
        WHATSAPP = "whatsapp", "WhatsApp"
        TELEGRAM = "telegram", "Telegram"

    parent_name = models.CharField(max_length=120, verbose_name="Имя родителя")
    phone = models.CharField(max_length=40, verbose_name="Телефон")
    phone_digits = models.CharField(max_length=20, db_index=True, editable=False)
    child_age = models.PositiveSmallIntegerField(validators=[MinValueValidator(3), MaxValueValidator(25)],
                                                 verbose_name="Возраст ребёнка")
    course = models.ForeignKey(CoursePage, on_delete=models.SET_NULL, null=True, blank=True, related_name="leads",
                               verbose_name="Курс")
    branch = models.ForeignKey(Branch, on_delete=models.SET_NULL, null=True, blank=True, related_name="leads",
                               verbose_name="Филиал")
    contact_method = models.CharField(max_length=10, choices=ContactMethod.choices, default=ContactMethod.PHONE,
                                      verbose_name="Как связаться")
    message = models.TextField(blank=True, verbose_name="Сообщение")
    language = models.CharField(max_length=2, blank=True, verbose_name="Язык сайта")
    source = models.CharField(max_length=200, blank=True, verbose_name="Страница")
    utm_source = models.CharField(max_length=100, blank=True, verbose_name="utm_source")
    utm_medium = models.CharField(max_length=100, blank=True, verbose_name="utm_medium")
    utm_campaign = models.CharField(max_length=100, blank=True, verbose_name="utm_campaign")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.NEW, db_index=True,
                              verbose_name="Статус")
    note = models.TextField(blank=True, verbose_name="Заметка менеджера")
    repeat_count = models.PositiveIntegerField(default=0, editable=False, verbose_name="Повторных отправок")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True, verbose_name="Получена")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Изменена")

    class Meta:
        verbose_name = "Заявка на обучение"
        verbose_name_plural = "Заявки на обучение"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.parent_name} ({self.phone})"
