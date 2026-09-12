from django.conf import settings
from django.db import models


class ExportTemplate(models.Model):
    """A saved, reusable column layout for one adapter's export.

    ``columns`` is an ordered list of ``{"field": <FieldSpec.key>, "label":
    <display label>}`` — only the fields the template author chose to
    include, already in the order they should appear. ``model_key`` matches
    a ``ModelAdapter.key`` from the registry (e.g. ``"academy.course"``);
    nothing here is Course/CourseLessonPlan/Subject-specific, so the same
    model serves every adapter that gets registered later.
    """

    class Format(models.TextChoices):
        CSV = "csv", "CSV"
        XLSX = "xlsx", "XLSX"

    model_key = models.CharField(max_length=100, db_index=True, verbose_name="Раздел")
    name = models.CharField(max_length=150, verbose_name="Название шаблона")
    columns = models.JSONField(default=list, verbose_name="Колонки")
    fmt = models.CharField(
        max_length=10,
        choices=Format.choices,
        default=Format.CSV,
        verbose_name="Формат по умолчанию",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="export_templates",
        verbose_name="Автор",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Дата обновления")

    class Meta:
        verbose_name = "Шаблон экспорта"
        verbose_name_plural = "Шаблоны экспорта"
        ordering = ["model_key", "name"]
        constraints = [
            models.UniqueConstraint(fields=["model_key", "name"], name="unique_export_template_name_per_model"),
        ]

    def __str__(self):
        return f"{self.name}"
