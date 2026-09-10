from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from ..users.models import Subject, Teacher
from .constants import WEEKDAY_CODES, WEEKDAY_LABELS_FULL


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

class GroupQuerySet(models.QuerySet):
    def for_teacher(self, teacher):
        """Every Group `teacher` has a real stake in: as the group's own
        primary teacher, or via any active GroupSchedule slot — a group can
        now have several teachers across different slots, and any of them
        gets the same full access to the group a single teacher always had.
        """
        return self.filter(
            models.Q(teacher=teacher) | models.Q(schedules__teacher=teacher, schedules__is_active=True)
        ).distinct()


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

    objects = GroupQuerySet.as_manager()

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

        if self.teacher_id and self.days_of_week and self.start_time and self.end_time and self.start_date:
            from .services.group_schedule_conflicts import find_group_teacher_conflict

            conflict = find_group_teacher_conflict(
                teacher=self.teacher,
                days_of_week=self.days_of_week,
                start_time=self.start_time,
                end_time=self.end_time,
                start_date=self.start_date,
                end_date=self.end_date,
                exclude_group_id=self.pk,
            )
            if conflict is not None:
                errors["teacher"] = f"Тренер «{self.teacher}» уже занят в это время группой «{conflict.name}»."

        if errors:
            raise ValidationError(errors)


# ---------------------------------------------------------------------------
# GroupSchedule — a Group's recurring weekly timetable, one row per
# (weekday, time range) taught by one Teacher/Subject/Room. Additive to
# Group's own teacher/room/start_time/end_time/days_of_week: those legacy
# fields describe the group's own "primary" slot and keep working exactly
# as before (a Group with no explicit GroupSchedule rows still generates
# lessons from them, see services.lesson_generator); GroupSchedule rows are
# how a Group gains *additional* slots — different teachers, subjects, days
# or time ranges layered on top of that primary one. Every Group's primary
# slot is also mirrored here (see services.group_schedule_sync, called from
# signals.py) so this table is always the single, complete source of truth
# for conflict-checking and lesson generation, never a second one.
# ---------------------------------------------------------------------------

class GroupSchedule(models.Model):
    DAY_CHOICES = [(code, WEEKDAY_LABELS_FULL[code]) for code in WEEKDAY_CODES]

    group = models.ForeignKey(
        Group,
        on_delete=models.CASCADE,
        related_name="schedules",
        verbose_name="Группа",
    )

    teacher = models.ForeignKey(
        Teacher,
        on_delete=models.PROTECT,
        related_name="group_schedules",
        verbose_name="Тренер",
    )

    subject = models.ForeignKey(
        Subject,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="group_schedules",
        verbose_name="Предмет",
        help_text=(
            "Предмет этого слота. Пусто — унаследованный слот без явного "
            "предмета (для него занятия создаются по общему порядку плана курса)."
        ),
    )

    day_of_week = models.CharField(
        max_length=3,
        choices=DAY_CHOICES,
        db_index=True,
        verbose_name="День недели",
    )

    start_time = models.TimeField(verbose_name="Время начала")
    end_time = models.TimeField(verbose_name="Время окончания")

    room = models.ForeignKey(
        Room,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="group_schedules",
        verbose_name="Аудитория",
    )

    is_active = models.BooleanField(
        default=True,
        db_index=True,
        verbose_name="Активно",
        help_text="Неактивные слоты игнорируются при генерации занятий и проверке конфликтов.",
    )

    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Дата обновления")

    class Meta:
        verbose_name = "Слот расписания группы"
        verbose_name_plural = "Расписание группы"
        ordering = ["group", "day_of_week", "start_time"]
        indexes = [
            models.Index(fields=["group", "day_of_week"], name="ix_gsched_group_day"),
            models.Index(fields=["teacher", "day_of_week"], name="ix_gsched_teacher_day"),
            models.Index(fields=["room", "day_of_week"], name="ix_gsched_room_day"),
        ]

    def __str__(self):
        return f"{self.group.name} — {self.get_day_of_week_display()} {self.start_time}–{self.end_time}"

    def clean(self):
        errors = {}

        if self.start_time and self.end_time and self.end_time <= self.start_time:
            errors["end_time"] = "Время окончания должно быть позже времени начала."

        if self.teacher_id and not self.teacher.is_active:
            errors["teacher"] = "Тренер должен быть активным."

        if self.subject_id and not self.subject.is_active:
            errors["subject"] = "Предмет должен быть активным."

        if self.room_id and not self.room.is_active:
            errors["room"] = "Аудитория должна быть активной."

        if self.teacher_id and self.day_of_week and self.start_time and self.end_time:
            from .services.group_schedule_conflicts import find_schedule_teacher_conflict

            conflict = find_schedule_teacher_conflict(
                teacher=self.teacher,
                day_of_week=self.day_of_week,
                start_time=self.start_time,
                end_time=self.end_time,
                exclude_schedule_id=self.pk,
            )
            if conflict is not None:
                errors["teacher"] = (
                    f"Тренер «{self.teacher}» уже занят в это время в группе «{conflict.group.name}»."
                )

        if self.room_id and self.day_of_week and self.start_time and self.end_time:
            from .services.group_schedule_conflicts import find_schedule_room_conflict

            conflict = find_schedule_room_conflict(
                room=self.room,
                day_of_week=self.day_of_week,
                start_time=self.start_time,
                end_time=self.end_time,
                exclude_schedule_id=self.pk,
            )
            if conflict is not None:
                errors["room"] = (
                    f"Аудитория «{self.room.name}» уже занята в это время в группе «{conflict.group.name}»."
                )

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

    schedule = models.ForeignKey(
        GroupSchedule,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="lessons",
        verbose_name="Слот расписания",
        help_text="Слот GroupSchedule, из которого сгенерировано это занятие (если есть).",
    )

    teacher = models.ForeignKey(
        Teacher,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="lessons",
        verbose_name="Тренер",
        help_text=(
            "Тренер, который ведёт именно это занятие. Заполняется генератором из "
            "расписания группы; для занятий, созданных до появления нескольких "
            "тренеров на группу, может быть пустым — тогда тренером считается "
            "group.teacher (см. apps.academy.permissions)."
        ),
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

    @property
    def effective_teacher(self) -> Teacher | None:
        """The Teacher who actually gives this lesson.

        `teacher` is set by the generator whenever the lesson came from a
        GroupSchedule slot; lessons generated before multi-teacher support
        (or otherwise created without one) fall back to the group's own
        `teacher` — the same single-teacher assumption the whole app made
        before this field existed.
        """
        return self.teacher or self.group.teacher


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

