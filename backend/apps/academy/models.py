from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from ..users.models import Subject, Teacher


# ---------------------------------------------------------------------------
# Course catalogue
# ---------------------------------------------------------------------------

class Course(models.Model):
    name = models.CharField(
        max_length=150,
        unique=True,
        verbose_name="Название",
    )

    count_lesson = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1)],
        verbose_name="Количество занятий",
        help_text="Общее число занятий в полном учебном плане курса.",
    )

    subjects = models.ManyToManyField(
        Subject,
        related_name="courses",
        verbose_name="Предметы",
        help_text="Предметы, которые входят в курс (любое распределение).",
    )

    description = models.TextField(
        blank=True,
        verbose_name="Описание",
    )

    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Дата обновления")

    class Meta:
        verbose_name = "Курс"
        verbose_name_plural = "Курсы"
        ordering = ["name"]

    def __str__(self):
        return self.name


class CourseLessonPlan(models.Model):
    """A single row of a course's full lesson-by-lesson template.

    Lesson generation copies this row's content onto a real Lesson; after
    that the two are independent — editing the plan later does not touch
    already-generated lessons (see Lesson).
    """

    course = models.ForeignKey(
        Course,
        on_delete=models.CASCADE,
        related_name="lesson_plans",
        verbose_name="Курс",
    )

    lesson_number = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1)],
        verbose_name="Номер занятия",
    )

    subject = models.ForeignKey(
        Subject,
        on_delete=models.PROTECT,
        related_name="lesson_plans",
        verbose_name="Предмет",
    )

    topic = models.CharField(
        max_length=255,
        verbose_name="Тема",
    )

    description = models.TextField(
        blank=True,
        verbose_name="Описание",
    )

    youtube_url = models.URLField(
        blank=True,
        verbose_name="Ссылка на YouTube",
    )

    presentation_urls = models.JSONField(
        default=list,
        blank=True,
        verbose_name="Ссылки на презентации",
        help_text="Список URL.",
    )

    homework_title = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="Название домашнего задания",
    )

    homework_description = models.TextField(
        blank=True,
        verbose_name="Описание домашнего задания",
    )

    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Дата обновления")

    class Meta:
        verbose_name = "План занятия"
        verbose_name_plural = "Планы занятий"
        ordering = ["course", "lesson_number"]
        constraints = [
            models.UniqueConstraint(
                fields=["course", "lesson_number"],
                name="unique_course_lesson_number",
            ),
        ]

    def __str__(self):
        return f"{self.course.name} — занятие {self.lesson_number}: {self.topic}"

    def clean(self):
        errors = {}

        if self.course_id and self.lesson_number and self.lesson_number > self.course.count_lesson:
            errors["lesson_number"] = (
                f"Номер занятия не может превышать количество занятий курса ({self.course.count_lesson})."
            )

        if (
            self.course_id
            and self.subject_id
            and not self.course.subjects.filter(pk=self.subject_id).exists()
        ):
            errors["subject"] = "Предмет должен входить в состав выбранного курса."

        if errors:
            raise ValidationError(errors)


# ---------------------------------------------------------------------------
# Rooms & students
# ---------------------------------------------------------------------------

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

    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Дата обновления")

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

    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Дата обновления")

    class Meta:
        verbose_name = "Студент"
        verbose_name_plural = "Студенты"
        ordering = ["last_name", "first_name"]

    def __str__(self):
        return f"{self.first_name} {self.last_name}".strip()


# ---------------------------------------------------------------------------
# Groups
# ---------------------------------------------------------------------------

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

    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Дата обновления")

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

    def clean(self):
        errors = {}

        if self.end_date and self.start_date and self.end_date < self.start_date:
            errors["end_date"] = "Дата окончания не может быть раньше даты начала."

        if self.start_time and self.end_time and self.end_time <= self.start_time:
            errors["end_time"] = "Время окончания должно быть позже времени начала."

        if not self.days_of_week:
            errors["days_of_week"] = "Укажите хотя бы один день недели."

        if self.room_id and self.room.capacity and self.max_students and self.max_students > self.room.capacity:
            errors["max_students"] = (
                f"Максимум студентов ({self.max_students}) превышает вместимость "
                f"аудитории «{self.room.name}» ({self.room.capacity})."
            )

        if self.room_id and self.days_of_week and self.start_time and self.end_time and self.start_date:
            from .services.room_conflicts import find_room_schedule_conflict

            conflict = find_room_schedule_conflict(
                room=self.room,
                days_of_week=self.days_of_week,
                start_time=self.start_time,
                end_time=self.end_time,
                start_date=self.start_date,
                end_date=self.end_date,
                exclude_group_id=self.pk,
            )
            if conflict is not None:
                errors["room"] = f"Аудитория «{self.room.name}» уже занята в это время группой «{conflict.name}»."

        if errors:
            raise ValidationError(errors)


# ---------------------------------------------------------------------------
# Lessons
# ---------------------------------------------------------------------------

class Lesson(models.Model):
    """A concrete, scheduled lesson event for a Group.

    When generated from a CourseLessonPlan, its content fields are copied
    from the plan — but the copy is the source of truth from then on, so a
    teacher can freely adjust a specific lesson's topic/materials without
    touching the template.
    """

    class Status(models.TextChoices):
        PLANNED = "planned", "Запланирован"
        COMPLETED = "completed", "Проведён"
        CANCELLED = "cancelled", "Отменён"

    group = models.ForeignKey(
        Group,
        on_delete=models.CASCADE,
        related_name="lessons",
        verbose_name="Группа",
    )

    plan = models.ForeignKey(
        CourseLessonPlan,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="lessons",
        verbose_name="План занятия",
    )

    lesson_number = models.PositiveSmallIntegerField(
        verbose_name="Номер занятия",
    )

    date = models.DateField(
        verbose_name="Дата",
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
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="lessons",
        verbose_name="Предмет",
    )

    topic = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="Тема",
    )

    description = models.TextField(
        blank=True,
        verbose_name="Описание",
    )

    youtube_url = models.URLField(
        blank=True,
        verbose_name="Ссылка на YouTube",
    )

    presentation_urls = models.JSONField(
        default=list,
        blank=True,
        verbose_name="Ссылки на презентации",
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

    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Дата обновления")

    class Meta:
        verbose_name = "Занятие"
        verbose_name_plural = "Занятия"
        ordering = ["date", "start_time"]
        constraints = [
            models.UniqueConstraint(
                fields=["group", "lesson_number"],
                name="unique_group_lesson_number",
            ),
        ]
        indexes = [
            models.Index(fields=["group", "date"], name="ix_lesson_group_date"),
            models.Index(fields=["subject", "date"], name="ix_lesson_subject_date"),
            models.Index(fields=["status", "date"], name="ix_lesson_status_date"),
        ]

    def __str__(self):
        return f"{self.group.name} — занятие {self.lesson_number} ({self.date})"

    def clean(self):
        if self.start_time and self.end_time and self.end_time <= self.start_time:
            raise ValidationError({"end_time": "Время окончания должно быть позже времени начала."})


# ---------------------------------------------------------------------------
# Homework (the assignment) & results (per-student outcome)
# ---------------------------------------------------------------------------

class Homework(models.Model):
    lesson = models.ForeignKey(
        Lesson,
        on_delete=models.CASCADE,
        related_name="homeworks",
        verbose_name="Занятие",
    )

    title = models.CharField(
        max_length=255,
        verbose_name="Название",
    )

    description = models.TextField(
        blank=True,
        verbose_name="Описание",
    )

    deadline = models.DateField(
        null=True,
        blank=True,
        verbose_name="Срок сдачи",
    )

    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Дата обновления")

    class Meta:
        verbose_name = "Домашнее задание"
        verbose_name_plural = "Домашние задания"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.lesson} — {self.title}"


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
        validators=[MinValueValidator(0), MaxValueValidator(10)],
        verbose_name="Баллы",
        help_text="От 0 до 10.",
    )

    comment = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="Комментарий",
    )

    submitted_at = models.DateTimeField(null=True, blank=True, verbose_name="Дата сдачи")
    checked_at = models.DateTimeField(null=True, blank=True, verbose_name="Дата проверки")

    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Дата обновления")

    class Meta:
        verbose_name = "Результат домашнего задания"
        verbose_name_plural = "Результаты домашних заданий"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["homework", "student"],
                name="unique_homework_student_result",
            ),
        ]
        indexes = [
            models.Index(fields=["homework", "student"], name="ix_hwresult_hw_student"),
            models.Index(fields=["student", "status"], name="ix_hwresult_student_status"),
        ]

    def __str__(self):
        return f"{self.student} — {self.homework.title}"

    def clean(self):
        if self.student_id and self.homework_id and self.student.group_id != self.homework.lesson.group_id:
            raise ValidationError({"student": "Студент не принадлежит группе этого занятия."})


# ---------------------------------------------------------------------------
# Attendance
# ---------------------------------------------------------------------------

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

    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Дата обновления")

    class Meta:
        verbose_name = "Посещаемость"
        verbose_name_plural = "Посещаемость"
        ordering = ["-lesson__date"]
        constraints = [
            models.UniqueConstraint(
                fields=["student", "lesson"],
                name="unique_student_lesson_attendance",
            ),
        ]
        indexes = [
            models.Index(fields=["student", "lesson"], name="ix_attendance_student_lesson"),
            models.Index(fields=["lesson", "status"], name="ix_attendance_lesson_status"),
        ]

    def __str__(self):
        return f"{self.student} — {self.lesson} — {self.get_status_display()}"

    def clean(self):
        if self.student_id and self.lesson_id and self.student.group_id != self.lesson.group_id:
            raise ValidationError({"student": "Студент не принадлежит группе этого занятия."})


# ---------------------------------------------------------------------------
# KPI — one focused model per analytical subject, never a single junk table
# ---------------------------------------------------------------------------

class KPIGroup(models.Model):
    group = models.ForeignKey(
        Group,
        on_delete=models.CASCADE,
        related_name="kpi_records",
        verbose_name="Группа",
    )

    date_from = models.DateField(verbose_name="Период с")
    date_to = models.DateField(verbose_name="Период по")

    total_students = models.PositiveIntegerField(default=0, verbose_name="Всего студентов")
    total_lessons = models.PositiveIntegerField(default=0, verbose_name="Всего занятий")
    completed_lessons = models.PositiveIntegerField(default=0, verbose_name="Проведено занятий")
    cancelled_lessons = models.PositiveIntegerField(default=0, verbose_name="Отменено занятий")

    attendance_percent = models.FloatField(default=0, verbose_name="Посещаемость, %")
    homework_completion_percent = models.FloatField(default=0, verbose_name="Выполнение ДЗ, %")
    average_score = models.FloatField(default=0, verbose_name="Средний балл")

    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Дата обновления")

    class Meta:
        verbose_name = "KPI группы"
        verbose_name_plural = "KPI групп"
        ordering = ["-date_to"]
        constraints = [
            models.UniqueConstraint(
                fields=["group", "date_from", "date_to"], name="unique_kpi_group_period"
            ),
        ]

    def __str__(self):
        return f"{self.group} — {self.date_from} — {self.date_to}"


class KPITeacher(models.Model):
    teacher = models.ForeignKey(
        Teacher,
        on_delete=models.CASCADE,
        related_name="kpi_records",
        verbose_name="Тренер",
    )

    date_from = models.DateField(verbose_name="Период с")
    date_to = models.DateField(verbose_name="Период по")

    total_groups = models.PositiveIntegerField(default=0, verbose_name="Всего групп")
    total_lessons = models.PositiveIntegerField(default=0, verbose_name="Всего занятий")
    completed_lessons = models.PositiveIntegerField(default=0, verbose_name="Проведено занятий")
    cancelled_lessons = models.PositiveIntegerField(default=0, verbose_name="Отменено занятий")

    attendance_percent = models.FloatField(default=0, verbose_name="Посещаемость, %")
    homework_completion_percent = models.FloatField(default=0, verbose_name="Выполнение ДЗ, %")
    average_student_score = models.FloatField(default=0, verbose_name="Средний балл студентов")

    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Дата обновления")

    class Meta:
        verbose_name = "KPI тренера"
        verbose_name_plural = "KPI тренеров"
        ordering = ["-date_to"]
        constraints = [
            models.UniqueConstraint(
                fields=["teacher", "date_from", "date_to"], name="unique_kpi_teacher_period"
            ),
        ]

    def __str__(self):
        return f"{self.teacher} — {self.date_from} — {self.date_to}"


class KPIStudent(models.Model):
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

    date_from = models.DateField(verbose_name="Период с")
    date_to = models.DateField(verbose_name="Период по")

    total_lessons = models.PositiveIntegerField(default=0, verbose_name="Всего занятий")
    present_count = models.PositiveIntegerField(default=0, verbose_name="Присутствовал")
    absent_count = models.PositiveIntegerField(default=0, verbose_name="Отсутствовал")
    late_count = models.PositiveIntegerField(default=0, verbose_name="Опозданий")
    attendance_percent = models.FloatField(default=0, verbose_name="Посещаемость, %")

    total_homeworks = models.PositiveIntegerField(default=0, verbose_name="Всего ДЗ")
    completed_homeworks = models.PositiveIntegerField(default=0, verbose_name="Выполнено ДЗ")
    missed_homeworks = models.PositiveIntegerField(default=0, verbose_name="Пропущено ДЗ")
    homework_completion_percent = models.FloatField(default=0, verbose_name="Выполнение ДЗ, %")
    average_score = models.FloatField(default=0, verbose_name="Средний балл")

    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Дата обновления")

    class Meta:
        verbose_name = "KPI студента"
        verbose_name_plural = "KPI студентов"
        ordering = ["-date_to"]
        constraints = [
            models.UniqueConstraint(
                fields=["student", "group", "date_from", "date_to"], name="unique_kpi_student_period"
            ),
        ]

    def __str__(self):
        return f"{self.student} — {self.date_from} — {self.date_to}"

    def clean(self):
        if self.student_id and self.group_id and self.student.group_id != self.group_id:
            raise ValidationError({"group": "Студент не принадлежит указанной группе."})


class KPILesson(models.Model):
    lesson = models.OneToOneField(
        Lesson,
        on_delete=models.CASCADE,
        related_name="kpi",
        verbose_name="Занятие",
    )

    total_students = models.PositiveIntegerField(default=0, verbose_name="Всего студентов")
    present_count = models.PositiveIntegerField(default=0, verbose_name="Присутствовало")
    absent_count = models.PositiveIntegerField(default=0, verbose_name="Отсутствовало")
    late_count = models.PositiveIntegerField(default=0, verbose_name="Опозданий")
    attendance_percent = models.FloatField(default=0, verbose_name="Посещаемость, %")

    total_homeworks = models.PositiveIntegerField(default=0, verbose_name="Всего ДЗ")
    homework_completed_count = models.PositiveIntegerField(default=0, verbose_name="Выполнено ДЗ")
    homework_completion_percent = models.FloatField(default=0, verbose_name="Выполнение ДЗ, %")
    average_homework_score = models.FloatField(default=0, verbose_name="Средний балл за ДЗ")

    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Дата обновления")

    class Meta:
        verbose_name = "KPI занятия"
        verbose_name_plural = "KPI занятий"
        ordering = ["-lesson__date"]

    def __str__(self):
        return f"KPI — {self.lesson}"


class KPIAttendance(models.Model):
    group = models.ForeignKey(
        Group,
        on_delete=models.CASCADE,
        related_name="attendance_kpi_records",
        verbose_name="Группа",
    )

    date_from = models.DateField(verbose_name="Период с")
    date_to = models.DateField(verbose_name="Период по")

    total_records = models.PositiveIntegerField(default=0, verbose_name="Всего записей")
    present_count = models.PositiveIntegerField(default=0, verbose_name="Присутствовал")
    absent_count = models.PositiveIntegerField(default=0, verbose_name="Отсутствовал")
    late_count = models.PositiveIntegerField(default=0, verbose_name="Опозданий")
    excused_count = models.PositiveIntegerField(default=0, verbose_name="Уважительная причина")
    attendance_percent = models.FloatField(default=0, verbose_name="Посещаемость, %")

    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Дата обновления")

    class Meta:
        verbose_name = "KPI посещаемости"
        verbose_name_plural = "KPI посещаемости"
        ordering = ["-date_to"]
        constraints = [
            models.UniqueConstraint(
                fields=["group", "date_from", "date_to"], name="unique_kpi_attendance_period"
            ),
        ]

    def __str__(self):
        return f"{self.group} — {self.date_from} — {self.date_to}"


class KPIHomework(models.Model):
    group = models.ForeignKey(
        Group,
        on_delete=models.CASCADE,
        related_name="homework_kpi_records",
        verbose_name="Группа",
    )

    date_from = models.DateField(verbose_name="Период с")
    date_to = models.DateField(verbose_name="Период по")

    total_homeworks = models.PositiveIntegerField(default=0, verbose_name="Всего ДЗ")
    total_results = models.PositiveIntegerField(default=0, verbose_name="Всего результатов")
    submitted_count = models.PositiveIntegerField(default=0, verbose_name="Сдано")
    checked_count = models.PositiveIntegerField(default=0, verbose_name="Проверено")
    not_submitted_count = models.PositiveIntegerField(default=0, verbose_name="Не сдано")
    late_count = models.PositiveIntegerField(default=0, verbose_name="Сдано с опозданием")
    completion_percent = models.FloatField(default=0, verbose_name="Выполнение, %")
    average_score = models.FloatField(default=0, verbose_name="Средний балл")

    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Дата обновления")

    class Meta:
        verbose_name = "KPI домашних заданий"
        verbose_name_plural = "KPI домашних заданий"
        ordering = ["-date_to"]
        constraints = [
            models.UniqueConstraint(
                fields=["group", "date_from", "date_to"], name="unique_kpi_homework_period"
            ),
        ]

    def __str__(self):
        return f"{self.group} — {self.date_from} — {self.date_to}"
