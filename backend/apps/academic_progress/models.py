"""Settings of a program's study months. Nothing here stores progress:
a group's current month is always computed from its completed Lessons
(services.progress), so changing the settings never loses history."""
from __future__ import annotations

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from apps.academy.models import Course, Group
from apps.users.models import Subject, User

LESSONS = [MinValueValidator(1), MaxValueValidator(200)]


class ProgramCurriculum(models.Model):
    """How a program (Course) is split into study months."""

    class CountMode(models.TextChoices):
        MAIN = "main", "Только основные предметы"
        ALL = "all", "Все предметы"

    course = models.OneToOneField(Course, on_delete=models.CASCADE, related_name="curriculum", verbose_name="Программа")
    lessons_per_month = models.PositiveSmallIntegerField(
        default=12, validators=LESSONS, verbose_name="Занятий в учебном месяце",
        help_text="По умолчанию для каждого месяца; отдельный месяц может задать своё число.",
    )
    duration_months = models.PositiveSmallIntegerField(
        default=6, validators=[MinValueValidator(1), MaxValueValidator(60)], verbose_name="Продолжительность, месяцев",
    )
    main_subject = models.ForeignKey(
        Subject, on_delete=models.SET_NULL, null=True, blank=True, related_name="+", verbose_name="Основной предмет",
    )
    extra_subjects = models.ManyToManyField(Subject, blank=True, related_name="+", verbose_name="Дополнительные предметы")
    count_mode = models.CharField(
        max_length=10, choices=CountMode.choices, default=CountMode.MAIN, verbose_name="Какие занятия заполняют месяц",
        help_text="«Только основные» — занятия дополнительных предметов (English, Soft…) не двигают учебный месяц.",
    )
    updated_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="+", verbose_name="Кто изменил")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Создано")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Изменено")

    class Meta:
        verbose_name = "Учебный план программы"
        verbose_name_plural = "Учебные планы программ"
        ordering = ["course__name"]

    def __str__(self):
        return f"{self.course} — {self.duration_months} мес. × {self.lessons_per_month}"


class CurriculumMonth(models.Model):
    """One study month of a program when it differs from the defaults: its
    own main subject and/or number of lessons. Months are in study order."""

    curriculum = models.ForeignKey(ProgramCurriculum, on_delete=models.CASCADE, related_name="months", verbose_name="Учебный план")
    number = models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(60)], verbose_name="Учебный месяц")
    subject = models.ForeignKey(Subject, on_delete=models.SET_NULL, null=True, blank=True, related_name="+", verbose_name="Основной предмет")
    planned_lessons = models.PositiveSmallIntegerField(null=True, blank=True, validators=LESSONS, verbose_name="План занятий")

    class Meta:
        verbose_name = "Учебный месяц"
        verbose_name_plural = "Учебные месяцы"
        ordering = ["curriculum", "number"]
        constraints = [models.UniqueConstraint(fields=["curriculum", "number"], name="unique_curriculum_month")]

    def __str__(self):
        return f"{self.curriculum.course} — {self.number}-й месяц"


class GroupProgressAdjustment(models.Model):
    """A group's history confirmed by a person: how many counted lessons it
    had before its lessons were recorded in the LMS. Without it, a group
    whose recorded lessons do not start from №1 is «Требуется настройка»."""

    group = models.OneToOneField(Group, on_delete=models.CASCADE, related_name="progress_adjustment", verbose_name="Группа")
    lessons_before_lms = models.PositiveSmallIntegerField(
        default=0, validators=[MaxValueValidator(2000)], verbose_name="Проведено занятий до LMS",
    )
    comment = models.CharField(max_length=255, blank=True, verbose_name="Комментарий")
    updated_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="+", verbose_name="Кто изменил")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Изменено")

    class Meta:
        verbose_name = "История прогресса группы"
        verbose_name_plural = "История прогресса групп"

    def __str__(self):
        return f"{self.group} — до LMS: {self.lessons_before_lms}"
