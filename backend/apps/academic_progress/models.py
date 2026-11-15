"""Settings of a program's study months. Nothing here stores progress:
a group's current month is always computed from its completed Lessons
(services.progress), so changing the settings never loses history."""
from __future__ import annotations

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from apps.academy.models import Course, Group, GroupTeacher
from apps.users.models import Subject, User

LESSONS = [MinValueValidator(1), MaxValueValidator(200)]

#: Lessons in one educational month — what the monthly lesson numbering
#: («Месяц 2 · Урок 1») and the study months use. Without any setting: 12.
LESSONS_PER_MONTH_CHOICES = [(12, "12 занятий"), (20, "20 занятий")]
ALLOWED_LESSONS_PER_MONTH = tuple(value for value, _ in LESSONS_PER_MONTH_CHOICES)
DEFAULT_LESSONS_PER_MONTH = 12


def validate_lessons_per_month(value):
    from django.core.exceptions import ValidationError

    if value not in ALLOWED_LESSONS_PER_MONTH:
        raise ValidationError("Занятий в учебном месяце: 12 или 20.")


class ProgramCurriculum(models.Model):
    """How a program (Course) is split into study months."""

    class CountMode(models.TextChoices):
        MAIN = "main", "Только основные предметы"
        ALL = "all", "Все предметы"

    course = models.OneToOneField(Course, on_delete=models.CASCADE, related_name="curriculum", verbose_name="Программа")
    lessons_per_month = models.PositiveSmallIntegerField(
        default=DEFAULT_LESSONS_PER_MONTH, validators=[validate_lessons_per_month], verbose_name="Занятий в учебном месяце",
        help_text="12 или 20. Задаёт нумерацию «Месяц · Урок» всех групп программы (группа может задать своё).",
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


class GroupLessonNumbering(models.Model):
    """A group's own number of lessons per educational month, when it differs
    from its program's (ProgramCurriculum.lessons_per_month)."""

    group = models.OneToOneField(Group, on_delete=models.CASCADE, related_name="lesson_numbering", verbose_name="Группа")
    lessons_per_month = models.PositiveSmallIntegerField(
        choices=LESSONS_PER_MONTH_CHOICES, validators=[validate_lessons_per_month], verbose_name="Занятий в учебном месяце",
    )
    updated_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="+", verbose_name="Кто изменил")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Изменено")

    class Meta:
        verbose_name = "Нумерация занятий группы"
        verbose_name_plural = "Нумерация занятий групп"

    def __str__(self):
        return f"{self.group} — {self.lessons_per_month} занятий в месяце"


class NumberingFreeze(models.Model):
    """Educational months fixed before a change of the lessons per month, so
    a change never renumbers lessons that already took place.

    Covers whole months of ONE subject's lesson sequence in a group (IT,
    English and Soft Skills are separate sequences): positions
    `first_lesson`…`last_lesson` of that subject's plan are months
    `first_month`… of `lessons_per_month` lessons each. Written by
    numbering.freeze_history(); later positions follow the current settings.
    """

    group = models.ForeignKey(Group, on_delete=models.CASCADE, null=True, related_name="numbering_freezes",
                              verbose_name="Группа")
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, null=True, blank=True, related_name="+",
                                verbose_name="Предмет")
    # Kept for history only (the first version keyed freezes by program).
    group_teacher = models.ForeignKey(GroupTeacher, on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
                                      verbose_name="Программа группы")
    first_lesson = models.PositiveIntegerField(verbose_name="С урока предмета №")
    last_lesson = models.PositiveIntegerField(verbose_name="По урок предмета №")
    first_month = models.PositiveSmallIntegerField(verbose_name="С учебного месяца")
    lessons_per_month = models.PositiveSmallIntegerField(verbose_name="Занятий в месяце")
    reason = models.CharField(max_length=255, blank=True, verbose_name="Причина")
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="+", verbose_name="Кто")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Создано")

    class Meta:
        verbose_name = "Зафиксированная нумерация"
        verbose_name_plural = "Зафиксированная нумерация"
        ordering = ["group", "subject", "first_lesson"]
        constraints = [
            models.UniqueConstraint(fields=["group", "subject", "first_lesson"], name="unique_numbering_freeze_subject_start"),
            models.CheckConstraint(condition=models.Q(last_lesson__gte=models.F("first_lesson")), name="numbering_freeze_range"),
        ]

    def __str__(self):
        subject = self.subject.name if self.subject_id else "—"
        return f"{self.group} · {subject}: уроки {self.first_lesson}–{self.last_lesson} по {self.lessons_per_month}"
