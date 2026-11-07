import os
import uuid

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone

from apps.academy.models import Group, Student


class Technology(models.Model):
    """A tech-stack tag («React», «Python»…). Shared by every project, so the
    filter and the form suggest the names trainers already use."""

    name = models.CharField(max_length=50, unique=True, verbose_name="Название")

    class Meta:
        verbose_name = "Технология"
        verbose_name_plural = "Технологии"
        ordering = ["name"]

    def __str__(self):
        return self.name


class StudentProject(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Черновик"
        PUBLISHED = "published", "Опубликован"

    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="projects", verbose_name="Студент")
    # The student's group when the project was registered — kept even if the
    # student later moves to another group.
    group = models.ForeignKey(Group, on_delete=models.SET_NULL, null=True, blank=True, related_name="student_projects",
                              verbose_name="Группа")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="student_projects",
                                   verbose_name="Тренер")

    title = models.CharField(max_length=150, verbose_name="Название проекта")
    short_description = models.CharField(max_length=300, blank=True, verbose_name="Краткое описание")
    description = models.TextField(blank=True, verbose_name="Полное описание")
    technologies = models.ManyToManyField(Technology, blank=True, related_name="projects", verbose_name="Технологии")
    project_date = models.DateField(default=timezone.localdate, db_index=True, verbose_name="Дата проекта")

    github_url = models.URLField(max_length=500, blank=True, verbose_name="GitHub")
    demo_url = models.URLField(max_length=500, blank=True, verbose_name="Демо")
    figma_url = models.URLField(max_length=500, blank=True, verbose_name="Figma")

    trainer_comment = models.TextField(blank=True, verbose_name="Комментарий тренера")
    rating = models.PositiveSmallIntegerField(null=True, blank=True,
                                              validators=[MinValueValidator(1), MaxValueValidator(5)],
                                              verbose_name="Оценка (1–5)")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT, db_index=True,
                              verbose_name="Статус")

    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Создан")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Изменён")

    class Meta:
        verbose_name = "Проект студента"
        verbose_name_plural = "Проекты студентов"
        ordering = ["-project_date", "-id"]

    def __str__(self):
        return self.title


def project_image_path(instance, filename: str) -> str:
    ext = os.path.splitext(filename)[1].lower()[:10]
    return f"projects/{timezone.now():%Y/%m}/{uuid.uuid4().hex}{ext}"


class ProjectImage(models.Model):
    project = models.ForeignKey(StudentProject, on_delete=models.CASCADE, related_name="images", verbose_name="Проект")
    image = models.ImageField(upload_to=project_image_path, max_length=255, verbose_name="Изображение")
    is_cover = models.BooleanField(default=False, verbose_name="Обложка")
    order = models.PositiveIntegerField(default=0, verbose_name="Порядок")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Изображение проекта"
        verbose_name_plural = "Изображения проектов"
        ordering = ["order", "id"]

    def __str__(self):
        return f"{self.project} #{self.pk}"


def _drop_image_file(sender, instance, **kwargs):
    """A deleted image (or a deleted project's images) leaves no file behind."""
    if instance.image:
        instance.image.delete(save=False)


models.signals.post_delete.connect(_drop_image_file, sender=ProjectImage, dispatch_uid="projects_drop_image_file")
