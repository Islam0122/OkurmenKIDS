"""Report history: every generated parent report is kept as its own row.

A report never changes after it is generated — «Перегенерировать» creates a
new row (``regenerated_from`` points back), so the history is never
overwritten. The numbers are frozen in ``snapshot`` (the full calculation
result of services.analytics at generation time); the texts and images were
rendered from that snapshot.

No student, attendance, homework or KPI data is duplicated here beyond that
frozen snapshot — the live numbers always come from apps.academy.
"""
from __future__ import annotations

from django.conf import settings
from django.core.serializers.json import DjangoJSONEncoder
from django.db import models

from .storage import report_image_storage


class ParentReport(models.Model):
    class ReportType(models.TextChoices):
        GROUP = "group", "Отчёт по группе"
        STUDENTS = "students", "Индивидуальные отчёты"

    class Language(models.TextChoices):
        RU = "ru", "Русский"
        KY = "ky", "Кыргызча"

    class OutputFormat(models.TextChoices):
        PNG = "png", "PNG-изображение"
        TEXT = "text", "Текст для WhatsApp"
        BOTH = "both", "Изображение и текст"

    class Status(models.TextChoices):
        READY = "ready", "Готов"
        PARTIAL = "partial", "Готов без изображения"
        FAILED = "failed", "Ошибка"

    group = models.ForeignKey(
        "academy.Group", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="parent_reports", verbose_name="Группа",
    )
    # Kept so the history stays readable after a group is renamed or removed.
    group_name = models.CharField(max_length=255, verbose_name="Название группы")
    course_name = models.CharField(max_length=255, blank=True, verbose_name="Курс")

    report_type = models.CharField(max_length=20, choices=ReportType.choices, verbose_name="Тип отчёта")
    language = models.CharField(max_length=5, choices=Language.choices, default=Language.RU, verbose_name="Язык")
    output_format = models.CharField(
        max_length=10, choices=OutputFormat.choices, default=OutputFormat.BOTH, verbose_name="Формат",
    )

    period_key = models.CharField(max_length=20, verbose_name="Период")
    start_date = models.DateField(verbose_name="Начало периода")
    end_date = models.DateField(verbose_name="Конец периода")
    compare_start_date = models.DateField(null=True, blank=True, verbose_name="Начало периода сравнения")
    compare_end_date = models.DateField(null=True, blank=True, verbose_name="Конец периода сравнения")

    options = models.JSONField(default=dict, blank=True, verbose_name="Параметры")
    snapshot = models.JSONField(default=dict, encoder=DjangoJSONEncoder, verbose_name="Снимок расчёта")

    text = models.TextField(blank=True, verbose_name="Сгенерированный текст")
    edited_text = models.TextField(blank=True, verbose_name="Текст после правки")
    student_texts = models.JSONField(default=dict, blank=True, verbose_name="Тексты по студентам")
    edited_student_texts = models.JSONField(default=dict, blank=True, verbose_name="Тексты по студентам после правки")

    status = models.CharField(max_length=10, choices=Status.choices, default=Status.READY, verbose_name="Статус")
    error = models.TextField(blank=True, verbose_name="Ошибка генерации")

    # Whose lessons were counted: a trainer's report covers only the lessons
    # they give (teacher isolation); None = every lesson of the group.
    teacher_scope = models.ForeignKey(
        "users.Teacher", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="parent_reports", verbose_name="Занятия тренера",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="parent_reports", verbose_name="Создал",
    )
    regenerated_from = models.ForeignKey(
        "self", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="regenerations", verbose_name="Перегенерирован из",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")

    class Meta:
        verbose_name = "Отчёт для родителей"
        verbose_name_plural = "Отчёты для родителей"
        ordering = ["-created_at", "-id"]
        indexes = [models.Index(fields=["group", "-created_at"], name="ix_parentreport_group_created")]

    def __str__(self):
        return f"{self.group_name} · {self.start_date:%d.%m.%Y}–{self.end_date:%d.%m.%Y} ({self.get_report_type_display()})"

    @property
    def final_text(self) -> str:
        return self.edited_text or self.text


def _image_path(instance: "ParentReportImage", filename: str) -> str:
    return f"{instance.report.created_at:%Y/%m}/report-{instance.report_id}/{filename}"


class ParentReportImage(models.Model):
    """One PNG page: a page of the group report, or one student's report."""

    report = models.ForeignKey(ParentReport, on_delete=models.CASCADE, related_name="images", verbose_name="Отчёт")
    student = models.ForeignKey(
        "academy.Student", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="parent_report_images", verbose_name="Студент",
    )
    student_name = models.CharField(max_length=255, blank=True, verbose_name="Имя студента")
    page = models.PositiveSmallIntegerField(default=1, verbose_name="Страница")
    image = models.FileField(upload_to=_image_path, storage=report_image_storage, verbose_name="Изображение")
    width = models.PositiveIntegerField(default=0)
    height = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = "Изображение отчёта"
        verbose_name_plural = "Изображения отчётов"
        ordering = ["report", "page", "id"]

    def __str__(self):
        return f"{self.report_id} · стр. {self.page}"
