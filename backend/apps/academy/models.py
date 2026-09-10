from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator, URLValidator
from django.db import models

from ..users.models import Teacher, Subject


# =========================================================
# COURSE
# =========================================================

class Course(models.Model):
    name = models.CharField(
        max_length=100,
        unique=True,
        verbose_name="Название курса",
    )
    count_lesson = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1)],
        verbose_name="Количество занятий",
    )
    subjects = models.ManyToManyField(
        Subject,
        blank=True,
        related_name="courses",
        verbose_name="Предметы",
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
        verbose_name = "Курс"
        verbose_name_plural = "Курсы"
        ordering = ["name"]

    def __str__(self):
        return self.name


# =========================================================
# COURSE LESSON PLAN
# =========================================================

class CourseLessonPlan(models.Model):
    """
    Шаблон урока курса.

    Например:

    Course: Standard
    Lesson 1
    Subject: HTML
    Topic: Основы HTML
    Description: ...
    YouTube: ...
    Presentation: ...
    Homework: ...
    """

    course = models.ForeignKey(
        Course,
        on_delete=models.CASCADE,
        related_name="lesson_plans",
        verbose_name="Курс",
    )
    lesson_number = models.PositiveSmallIntegerField(
        verbose_name="Номер занятия",
    )
    subject = models.ForeignKey(
        Subject,
        on_delete=models.PROTECT,
        related_name="course_lesson_plans",
        verbose_name="Предмет",
    )
    topic = models.CharField(
        max_length=255,
        verbose_name="Тема",
    )
    description = models.TextField(
        blank=True,
        verbose_name="Описание урока",
    )
    youtube_url = models.URLField(
        blank=True,
        verbose_name="YouTube",
    )
    presentation_urls = models.JSONField(
        default=list,
        blank=True,
        verbose_name="Презентации",
        help_text="Список ссылок на презентации.",
    )
    homework_title = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="Название ДЗ",
    )
    homework_description = models.TextField(
        blank=True,
        verbose_name="Описание ДЗ",
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
        verbose_name = "План занятия курса"
        verbose_name_plural = "План занятий курса"
        ordering = ["course", "lesson_number"]
        constraints = [
            models.UniqueConstraint(
                fields=["course", "lesson_number"],
                name="unique_course_lesson_number",
            )
        ]

    def clean(self):
        errors = {}

        if self.course_id and self.lesson_number:
            if self.course.count_lesson and self.lesson_number > self.course.count_lesson:
                errors["lesson_number"] = (
                    "Номер занятия не может превышать количество занятий курса."
                )

        if self.subject_id and self.course_id:
            if not self.course.subjects.filter(id=self.subject_id).exists():
                errors["subject"] = (
                    "Этот предмет не добавлен в выбранный курс."
                )

        if not isinstance(self.presentation_urls, list):
            errors["presentation_urls"] = "Должен быть список URL."
        else:
            validator = URLValidator()

            for url in self.presentation_urls:
                try:
                    validator(url)
                except ValidationError:
                    errors["presentation_urls"] = (
                        "Все ссылки на презентации должны быть корректными URL."
                    )
                    break

        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return (
            f"{self.course.name} — "
            f"занятие {self.lesson_number}: {self.topic}"
        )


# =========================================================
# ROOM
# =========================================================

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


# =========================================================
# STUDENT
# =========================================================

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
    phone = models.CharField(
        max_length=30,
        blank=True,
        verbose_name="Телефон",
    )
    parent_phone = models.CharField(
        max_length=30,
        blank=True,
        verbose_name="Телефон родителя",
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
        indexes = [
            models.Index(fields=["last_name", "first_name"]),
            models.Index(fields=["group", "is_active"]),
        ]

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}".strip()

    def __str__(self):
        return self.full_name


# =========================================================
# GROUP
# =========================================================

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
    course = models.ForeignKey(
        Course,
        on_delete=models.PROTECT,
        related_name="groups",
        verbose_name="Курс",
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
        indexes = [
            models.Index(fields=["teacher", "status"]),
            models.Index(fields=["course", "status"]),
        ]

    def clean(self):
        errors = {}

        if self.end_date and self.end_date < self.start_date:
            errors["end_date"] = (
                "Дата окончания не может быть раньше даты начала."
            )

        if self.end_time <= self.start_time:
            errors["end_time"] = (
                "Время окончания должно быть позже времени начала."
            )

        if not self.days_of_week:
            errors["days_of_week"] = (
                "Укажите хотя бы один день недели."
            )

        if self.room_id and self.max_students:
            if self.room.capacity and self.max_students > self.room.capacity:
                errors["max_students"] = (
                    "Количество студентов не может превышать "
                    "вместимость аудитории."
                )

        if errors:
            raise ValidationError(errors)

    @property
    def students_count(self):
        return self.students.filter(is_active=True).count()

    @property
    def is_full(self):
        return (
            self.max_students is not None
            and self.students_count >= self.max_students
        )

    def __str__(self):
        return self.name


# =========================================================
# LESSON
# =========================================================

class Lesson(models.Model):
    """
    Конкретный урок группы.

    В отличие от CourseLessonPlan здесь уже реальные:
    дата, время, аудитория и материалы.
    """

    class Status(models.TextChoices):
        PLANNED = "planned", "Запланировано"
        COMPLETED = "completed", "Проведено"
        CANCELLED = "cancelled", "Отменено"

    group = models.ForeignKey(
        Group,
        on_delete=models.CASCADE,
        related_name="lessons",
        verbose_name="Группа",
    )

    plan = models.ForeignKey(
        CourseLessonPlan,
        on_delete=models.PROTECT,
        related_name="lessons",
        verbose_name="План занятия",
    )

    lesson_number = models.PositiveSmallIntegerField(
        verbose_name="Номер занятия",
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
        related_name="lessons",
        verbose_name="Аудитория",
    )

    subject = models.ForeignKey(
        Subject,
        on_delete=models.PROTECT,
        related_name="lessons",
        verbose_name="Предмет",
    )

    topic = models.CharField(
        max_length=255,
        verbose_name="Тема",
    )

    description = models.TextField(
        blank=True,
        verbose_name="Описание урока",
    )

    youtube_url = models.URLField(
        blank=True,
        verbose_name="YouTube",
    )

    presentation_urls = models.JSONField(
        default=list,
        blank=True,
        verbose_name="Презентации",
        help_text="Список ссылок на презентации.",
    )

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PLANNED,
        db_index=True,
        verbose_name="Статус",
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
        verbose_name_plural = "Занятия"
        ordering = ["date", "start_time"]
        constraints = [
            models.UniqueConstraint(
                fields=["group", "lesson_number"],
                name="unique_group_lesson_number",
            )
        ]
        indexes = [
            models.Index(fields=["group", "date"]),
            models.Index(fields=["teacher", "date"])
            if False
            else models.Index(fields=["subject", "date"]),
        ]

    def clean(self):
        errors = {}

        if self.end_time <= self.start_time:
            errors["end_time"] = (
                "Время окончания должно быть позже времени начала."
            )

        if self.plan_id and self.group_id:
            if self.plan.course_id != self.group.course_id:
                errors["plan"] = (
                    "План занятия должен принадлежать курсу этой группы."
                )

        if self.subject_id and self.plan_id:
            if self.subject_id != self.plan.subject_id:
                errors["subject"] = (
                    "Предмет урока должен соответствовать плану занятия."
                )

        if not isinstance(self.presentation_urls, list):
            errors["presentation_urls"] = "Должен быть список URL."
        else:
            validator = URLValidator()

            for url in self.presentation_urls:
                try:
                    validator(url)
                except ValidationError:
                    errors["presentation_urls"] = (
                        "Все ссылки на презентации должны быть корректными URL."
                    )
                    break

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        if self.plan_id:
            self.lesson_number = self.plan.lesson_number
            self.subject = self.plan.subject
            self.topic = self.plan.topic
            self.description = self.plan.description

            if not self.youtube_url:
                self.youtube_url = self.plan.youtube_url

            if not self.presentation_urls:
                self.presentation_urls = self.plan.presentation_urls

        if self.group_id and self.room_id is None:
            self.room = self.group.room

        super().save(*args, **kwargs)

    @property
    def teacher(self):
        return self.group.teacher

    def __str__(self):
        return f"{self.group.name} — {self.lesson_number}. {self.topic}"


# =========================================================
# ATTENDANCE
# =========================================================

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

    lesson = models.ForeignKey(
        Lesson,
        on_delete=models.CASCADE,
        related_name="attendance_records",
        verbose_name="Занятие",
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
        ordering = ["-lesson__date"]
        constraints = [
            models.UniqueConstraint(
                fields=["student", "lesson"],
                name="unique_student_attendance_per_lesson",
            )
        ]
        indexes = [
            models.Index(fields=["student", "status"]),
            models.Index(fields=["lesson", "status"]),
        ]

    def clean(self):
        if (
            self.student_id
            and self.lesson_id
            and self.student.group_id != self.lesson.group_id
        ):
            raise ValidationError(
                {
                    "student": (
                        "Студент не относится к группе этого занятия."
                    )
                }
            )

    def __str__(self):
        return (
            f"{self.student} — "
            f"{self.lesson.date} — "
            f"{self.get_status_display()}"
        )


# =========================================================
# HOMEWORK
# =========================================================

class Homework(models.Model):
    """
    Конкретное домашнее задание урока.
    """

    lesson = models.ForeignKey(
        Lesson,
        on_delete=models.CASCADE,
        related_name="homeworks",
        verbose_name="Занятие",
    )

    title = models.CharField(
        max_length=255,
        verbose_name="Название задания",
    )

    description = models.TextField(
        verbose_name="Задание",
    )

    deadline = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Дедлайн",
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
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.lesson} — {self.title}"


# =========================================================
# HOMEWORK RESULT
# =========================================================

class HomeworkResult(models.Model):
    class Status(models.TextChoices):
        NOT_SUBMITTED = "not_submitted", "Не сдано"
        SUBMITTED = "submitted", "Сдано"
        CHECKED = "checked", "Проверено"
        LATE = "late", "Сдано с опозданием"

    homework = models.ForeignKey(
        Homework,
        on_delete=models.CASCADE,
        related_name="results",
        verbose_name="Домашнее задание",
    )

    student = models.ForeignKey(
        Student,
        on_delete=models.CASCADE,
        related_name="homework_results",
        verbose_name="Студент",
    )

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.NOT_SUBMITTED,
        db_index=True,
        verbose_name="Статус",
    )

    score = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
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
    )

    submitted_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Дата сдачи",
    )

    checked_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Дата проверки",
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
        verbose_name = "Результат домашнего задания"
        verbose_name_plural = "Результаты домашних заданий"
        ordering = ["-updated_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["homework", "student"],
                name="unique_homework_result_per_student",
            )
        ]
        indexes = [
            models.Index(fields=["student", "status"]),
            models.Index(fields=["homework", "status"]),
        ]

    def clean(self):
        if (
            self.student_id
            and self.homework_id
            and self.student.group_id != self.homework.lesson.group_id
        ):
            raise ValidationError(
                {
                    "student": (
                        "Студент не относится к группе этого задания."
                    )
                }
            )

    def __str__(self):
        score = (
            f"{self.score}/10"
            if self.score is not None
            else "без оценки"
        )
        return f"{self.student} — {self.homework.title} — {score}"


# =========================================================
# KPI GROUP
# =========================================================

class KPIGroup(models.Model):
    """
    KPI всей группы за определённый период.
    """

    group = models.ForeignKey(
        Group,
        on_delete=models.CASCADE,
        related_name="kpi_group_records",
        verbose_name="Группа",
    )

    date_from = models.DateField(
        verbose_name="Период с",
    )

    date_to = models.DateField(
        verbose_name="Период по",
    )

    total_students = models.PositiveIntegerField(
        default=0,
        verbose_name="Всего студентов",
    )

    total_lessons = models.PositiveIntegerField(
        default=0,
        verbose_name="Всего занятий",
    )

    completed_lessons = models.PositiveIntegerField(
        default=0,
        verbose_name="Проведено занятий",
    )

    cancelled_lessons = models.PositiveIntegerField(
        default=0,
        verbose_name="Отменено занятий",
    )

    attendance_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0,
        verbose_name="Посещаемость %",
    )

    homework_completion_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0,
        verbose_name="Выполнение ДЗ %",
    )

    average_score = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0,
        verbose_name="Средний балл",
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
        verbose_name = "KPI группы"
        verbose_name_plural = "KPI групп"
        ordering = ["-date_to"]
        constraints = [
            models.UniqueConstraint(
                fields=["group", "date_from", "date_to"],
                name="unique_group_kpi_period",
            )
        ]

    def clean(self):
        if self.date_to < self.date_from:
            raise ValidationError(
                {
                    "date_to": (
                        "Дата окончания периода не может быть "
                        "раньше даты начала."
                    )
                }
            )

    def __str__(self):
        return f"{self.group.name} — {self.date_from} — {self.date_to}"


# =========================================================
# KPI TEACHER
# =========================================================

class KPITeacher(models.Model):
    """
    KPI тренера.
    """

    teacher = models.ForeignKey(
        Teacher,
        on_delete=models.CASCADE,
        related_name="kpi_records",
        verbose_name="Тренер",
    )

    date_from = models.DateField(
        verbose_name="Период с",
    )

    date_to = models.DateField(
        verbose_name="Период по",
    )

    total_groups = models.PositiveIntegerField(
        default=0,
        verbose_name="Количество групп",
    )

    total_lessons = models.PositiveIntegerField(
        default=0,
        verbose_name="Количество занятий",
    )

    completed_lessons = models.PositiveIntegerField(
        default=0,
        verbose_name="Проведено занятий",
    )

    cancelled_lessons = models.PositiveIntegerField(
        default=0,
        verbose_name="Отменено занятий",
    )

    attendance_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0,
        verbose_name="Посещаемость %",
    )

    homework_completion_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0,
        verbose_name="Выполнение ДЗ %",
    )

    average_student_score = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0,
        verbose_name="Средний балл студентов",
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
        verbose_name = "KPI тренера"
        verbose_name_plural = "KPI тренеров"
        ordering = ["-date_to"]
        constraints = [
            models.UniqueConstraint(
                fields=["teacher", "date_from", "date_to"],
                name="unique_teacher_kpi_period",
            )
        ]

    def clean(self):
        if self.date_to < self.date_from:
            raise ValidationError(
                {
                    "date_to": (
                        "Дата окончания периода не может быть "
                        "раньше даты начала."
                    )
                }
            )

    def __str__(self):
        return f"{self.teacher} — {self.date_from} — {self.date_to}"


# =========================================================
# KPI STUDENT
# =========================================================

class KPIStudent(models.Model):
    """
    KPI отдельного студента.
    """

    student = models.ForeignKey(
        Student,
        on_delete=models.CASCADE,
        related_name="kpi_records",
        verbose_name="Студент",
    )

    group = models.ForeignKey(
        Group,
        on_delete=models.CASCADE,
        related_name="student_kpi_records",
        verbose_name="Группа",
    )

    date_from = models.DateField(
        verbose_name="Период с",
    )

    date_to = models.DateField(
        verbose_name="Период по",
    )

    total_lessons = models.PositiveIntegerField(
        default=0,
        verbose_name="Всего занятий",
    )

    present_count = models.PositiveIntegerField(
        default=0,
        verbose_name="Присутствовал",
    )

    absent_count = models.PositiveIntegerField(
        default=0,
        verbose_name="Пропуски",
    )

    late_count = models.PositiveIntegerField(
        default=0,
        verbose_name="Опоздания",
    )

    attendance_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0,
        verbose_name="Посещаемость %",
    )

    total_homeworks = models.PositiveIntegerField(
        default=0,
        verbose_name="Всего ДЗ",
    )

    completed_homeworks = models.PositiveIntegerField(
        default=0,
        verbose_name="Выполнено ДЗ",
    )

    missed_homeworks = models.PositiveIntegerField(
        default=0,
        verbose_name="Не выполнено ДЗ",
    )

    homework_completion_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0,
        verbose_name="Выполнение ДЗ %",
    )

    average_score = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0,
        verbose_name="Средний балл",
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
        verbose_name = "KPI студента"
        verbose_name_plural = "KPI студентов"
        ordering = ["-date_to"]
        constraints = [
            models.UniqueConstraint(
                fields=[
                    "student",
                    "group",
                    "date_from",
                    "date_to",
                ],
                name="unique_student_kpi_period",
            )
        ]

    def clean(self):
        errors = {}

        if self.date_to < self.date_from:
            errors["date_to"] = (
                "Дата окончания периода не может быть "
                "раньше даты начала."
            )

        if (
            self.student_id
            and self.group_id
            and self.student.group_id != self.group_id
        ):
            errors["student"] = (
                "Студент не относится к указанной группе."
            )

        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return f"{self.student} — {self.date_from} — {self.date_to}"


# =========================================================
# KPI LESSON
# =========================================================

class KPILesson(models.Model):
    """
    KPI конкретного урока.
    """

    lesson = models.OneToOneField(
        Lesson,
        on_delete=models.CASCADE,
        related_name="kpi",
        verbose_name="Занятие",
    )

    total_students = models.PositiveIntegerField(
        default=0,
        verbose_name="Всего студентов",
    )

    present_count = models.PositiveIntegerField(
        default=0,
        verbose_name="Присутствовали",
    )

    absent_count = models.PositiveIntegerField(
        default=0,
        verbose_name="Отсутствовали",
    )

    late_count = models.PositiveIntegerField(
        default=0,
        verbose_name="Опоздали",
    )

    attendance_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0,
        verbose_name="Посещаемость %",
    )

    total_homeworks = models.PositiveIntegerField(
        default=0,
        verbose_name="Всего ДЗ",
    )

    homework_completed_count = models.PositiveIntegerField(
        default=0,
        verbose_name="Выполнено ДЗ",
    )

    homework_completion_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0,
        verbose_name="Выполнение ДЗ %",
    )

    average_homework_score = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0,
        verbose_name="Средний балл ДЗ",
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
        verbose_name = "KPI урока"
        verbose_name_plural = "KPI уроков"
        ordering = ["-lesson__date"]

    def __str__(self):
        return f"KPI — {self.lesson}"


# =========================================================
# KPI ATTENDANCE
# =========================================================

class KPIAttendance(models.Model):
    """
    Аналитика посещаемости.
    """

    group = models.ForeignKey(
        Group,
        on_delete=models.CASCADE,
        related_name="attendance_kpi_records",
        verbose_name="Группа",
    )

    date_from = models.DateField(
        verbose_name="Период с",
    )

    date_to = models.DateField(
        verbose_name="Период по",
    )

    total_records = models.PositiveIntegerField(
        default=0,
        verbose_name="Всего отметок",
    )

    present_count = models.PositiveIntegerField(
        default=0,
        verbose_name="Присутствовали",
    )

    absent_count = models.PositiveIntegerField(
        default=0,
        verbose_name="Отсутствовали",
    )

    late_count = models.PositiveIntegerField(
        default=0,
        verbose_name="Опоздали",
    )

    excused_count = models.PositiveIntegerField(
        default=0,
        verbose_name="Уважительная причина",
    )

    attendance_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0,
        verbose_name="Посещаемость %",
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
        verbose_name = "KPI посещаемости"
        verbose_name_plural = "KPI посещаемости"
        ordering = ["-date_to"]
        constraints = [
            models.UniqueConstraint(
                fields=["group", "date_from", "date_to"],
                name="unique_attendance_kpi_period",
            )
        ]

    def clean(self):
        if self.date_to < self.date_from:
            raise ValidationError(
                {
                    "date_to": (
                        "Дата окончания периода не может быть "
                        "раньше даты начала."
                    )
                }
            )

    def __str__(self):
        return (
            f"Посещаемость — {self.group.name} — "
            f"{self.date_from} — {self.date_to}"
        )


# =========================================================
# KPI HOMEWORK
# =========================================================

class KPIHomework(models.Model):
    """
    Аналитика домашних заданий.
    """

    group = models.ForeignKey(
        Group,
        on_delete=models.CASCADE,
        related_name="homework_kpi_records",
        verbose_name="Группа",
    )

    date_from = models.DateField(
        verbose_name="Период с",
    )

    date_to = models.DateField(
        verbose_name="Период по",
    )

    total_homeworks = models.PositiveIntegerField(
        default=0,
        verbose_name="Всего ДЗ",
    )

    total_results = models.PositiveIntegerField(
        default=0,
        verbose_name="Всего результатов",
    )

    submitted_count = models.PositiveIntegerField(
        default=0,
        verbose_name="Сдано",
    )

    checked_count = models.PositiveIntegerField(
        default=0,
        verbose_name="Проверено",
    )

    not_submitted_count = models.PositiveIntegerField(
        default=0,
        verbose_name="Не сдано",
    )

    late_count = models.PositiveIntegerField(
        default=0,
        verbose_name="Сдано с опозданием",
    )

    completion_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0,
        verbose_name="Выполнение %",
    )

    average_score = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0,
        verbose_name="Средний балл",
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
        verbose_name = "KPI домашних заданий"
        verbose_name_plural = "KPI домашних заданий"
        ordering = ["-date_to"]
        constraints = [
            models.UniqueConstraint(
                fields=["group", "date_from", "date_to"],
                name="unique_homework_kpi_period",
            )
        ]

    def clean(self):
        if self.date_to < self.date_from:
            raise ValidationError(
                {
                    "date_to": (
                        "Дата окончания периода не может быть "
                        "раньше даты начала."
                    )
                }
            )

    def __str__(self):
        return (
            f"ДЗ — {self.group.name} — "
            f"{self.date_from} — {self.date_to}"
        )