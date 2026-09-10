from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from ..users.models import Teacher


class Room(models.Model):
    name = models.CharField(
        max_length=100,
        unique=True,
        verbose_name="Название",
    )

    capacity = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(1)],
        verbose_name="Вместимость",
    )

    description = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="Описание",
    )

    is_active = models.BooleanField(
        default=True,
        db_index=True,
        verbose_name="Активна",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Дата создания",
    )

    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="Дата обновления",
    )

    class Meta:
        verbose_name = "Аудитория"
        verbose_name_plural = "Аудитории"
        ordering = ["name"]

    def __str__(self):
        return self.name


class Student(models.Model):
    first_name = models.CharField(
        max_length=100,
        verbose_name="Имя",
    )

    last_name = models.CharField(
        max_length=100,
        blank=True,
        verbose_name="Фамилия",
    )

    group = models.ForeignKey(
        "Group",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="students",
        verbose_name="Группа",
    )

    is_active = models.BooleanField(
        default=True,
        db_index=True,
        verbose_name="Активен",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Дата создания",
    )

    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="Дата обновления",
    )

    class Meta:
        verbose_name = "Студент"
        verbose_name_plural = "Студенты"
        ordering = ["last_name", "first_name"]

    def __str__(self):
        return f"{self.first_name} {self.last_name}".strip()


class Group(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active", "Активна"
        PAUSED = "paused", "Приостановлена"
        COMPLETED = "completed", "Завершена"
        CANCELLED = "cancelled", "Отменена"

    name = models.CharField(
        max_length=150,
        unique=True,
        verbose_name="Название группы",
    )

    teacher = models.ForeignKey(
        Teacher,
        on_delete=models.PROTECT,
        related_name="groups",
        verbose_name="Тренер",
    )

    room = models.ForeignKey(
        Room,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="groups",
        verbose_name="Аудитория",
    )

    start_date = models.DateField(
        verbose_name="Дата начала",
    )

    end_date = models.DateField(
        null=True,
        blank=True,
        verbose_name="Дата окончания",
    )

    start_time = models.TimeField(
        verbose_name="Время начала",
    )

    end_time = models.TimeField(
        verbose_name="Время окончания",
    )

    days_of_week = models.JSONField(
        default=list,
        verbose_name="Дни недели",
        help_text="Например: ['mon', 'wed', 'fri'].",
    )

    max_students = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(1)],
        verbose_name="Максимум студентов",
    )

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.ACTIVE,
        db_index=True,
        verbose_name="Статус",
    )

    description = models.TextField(
        blank=True,
        verbose_name="Описание",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Дата создания",
    )

    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="Дата обновления",
    )

    class Meta:
        verbose_name = "Группа"
        verbose_name_plural = "Группы"
        ordering = ["-start_date", "name"]

    def __str__(self):
        return self.name

    @property
    def students_count(self):
        return self.students.filter(is_active=True).count()

    @property
    def is_full(self):
        if self.max_students is None:
            return False

        return self.students_count >= self.max_students


class Schedule(models.Model):
    group = models.ForeignKey(
        Group,
        on_delete=models.CASCADE,
        related_name="schedules",
        verbose_name="Группа",
    )

    date = models.DateField(
        verbose_name="Дата занятия",
    )

    start_time = models.TimeField(
        verbose_name="Время начала",
    )

    end_time = models.TimeField(
        verbose_name="Время окончания",
    )

    room = models.ForeignKey(
        Room,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="schedules",
        verbose_name="Аудитория",
    )

    is_cancelled = models.BooleanField(
        default=False,
        verbose_name="Отменено",
    )

    cancellation_reason = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="Причина отмены",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Дата создания",
    )

    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="Дата обновления",
    )

    class Meta:
        verbose_name = "Занятие"
        verbose_name_plural = "Расписание"
        ordering = ["date", "start_time"]

    def __str__(self):
        return f"{self.group.name} — {self.date} {self.start_time}"


class Attendance(models.Model):
    class Status(models.TextChoices):
        PRESENT = "present", "Присутствовал"
        ABSENT = "absent", "Отсутствовал"
        LATE = "late", "Опоздал"
        EXCUSED = "excused", "Уважительная причина"

    student = models.ForeignKey(
        Student,
        on_delete=models.CASCADE,
        related_name="attendance_records",
        verbose_name="Студент",
    )

    group = models.ForeignKey(
        Group,
        on_delete=models.CASCADE,
        related_name="attendance_records",
        verbose_name="Группа",
    )

    date = models.DateField(
        verbose_name="Дата",
    )

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        verbose_name="Статус",
    )

    comment = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="Комментарий",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Дата создания",
    )

    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="Дата обновления",
    )

    class Meta:
        verbose_name = "Посещаемость"
        verbose_name_plural = "Посещаемость"
        ordering = ["-date"]

        constraints = [
            models.UniqueConstraint(
                fields=["student", "group", "date"],
                name="unique_student_group_attendance_per_day",
            ),
        ]

    def __str__(self):
        return (
            f"{self.student} — "
            f"{self.date} — "
            f"{self.get_status_display()}"
        )


class Homework(models.Model):
    student = models.ForeignKey(
        Student,
        on_delete=models.CASCADE,
        related_name="homework_results",
        verbose_name="Студент",
    )

    group = models.ForeignKey(
        Group,
        on_delete=models.CASCADE,
        related_name="homework_results",
        verbose_name="Группа",
    )

    date = models.DateField(
        verbose_name="Дата",
    )

    score = models.PositiveSmallIntegerField(
        validators=[
            MinValueValidator(0),
            MaxValueValidator(10),
        ],
        verbose_name="Баллы",
        help_text="От 0 до 10.",
    )

    comment = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="Комментарий",
        help_text="Например: Не сделал, не смог, выполнено частично.",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Дата создания",
    )

    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="Дата обновления",
    )

    class Meta:
        verbose_name = "Домашнее задание"
        verbose_name_plural = "Домашние задания"
        ordering = ["-date"]

        constraints = [
            models.UniqueConstraint(
                fields=["student", "group", "date"],
                name="unique_student_group_homework_per_day",
            ),
        ]

    def __str__(self):
        return f"{self.student} — {self.date} — {self.score}/10"


class KPI(models.Model):
    student = models.ForeignKey(
        Student,
        on_delete=models.CASCADE,
        related_name="kpi_records",
        verbose_name="Студент",
    )

    group = models.ForeignKey(
        Group,
        on_delete=models.CASCADE,
        related_name="kpi_records",
        verbose_name="Группа",
    )

    date_from = models.DateField(
        verbose_name="Период с",
    )

    date_to = models.DateField(
        verbose_name="Период по",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Дата создания",
    )

    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="Дата обновления",
    )

    class Meta:
        verbose_name = "KPI"
        verbose_name_plural = "KPI"
        ordering = ["-date_to"]

        constraints = [
            models.UniqueConstraint(
                fields=[
                    "student",
                    "group",
                    "date_from",
                    "date_to",
                ],
                name="unique_student_group_kpi_period",
            ),
        ]

    def __str__(self):
        return (
            f"{self.student} — "
            f"{self.date_from} — {self.date_to}"
        )