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
        null=True,
        blank=True,
        related_name="groups",
        verbose_name="Тренер (устар.)",
        help_text=(
            "Устаревшее поле, оставлено только для совместимости со старыми данными. "
            "Тренеров группы назначайте через «Тренеры / программы» (GroupTeacher) — "
            "это поле больше не влияет на расписание и генерацию занятий."
        ),
    )

    room = models.ForeignKey(
        Room,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="groups",
        verbose_name="Аудитория (устар.)",
        help_text="Устаревшее поле — см. help_text поля «Тренер (устар.)».",
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
        null=True,
        blank=True,
        verbose_name="Время начала (устар.)",
        help_text="Устаревшее поле — см. help_text поля «Тренер (устар.)».",
    )

    end_time = models.TimeField(
        null=True,
        blank=True,
        verbose_name="Время окончания (устар.)",
        help_text="Устаревшее поле — см. help_text поля «Тренер (устар.)».",
    )

    days_of_week = models.JSONField(
        default=list,
        blank=True,
        verbose_name="Дни недели (устар.)",
        help_text="Устаревшее поле, например: ['mon', 'wed', 'fri'] — см. help_text поля «Тренер (устар.)».",
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
        """Note: none of the checks below are required for a Group to be
        usable — teacher/room/start_time/end_time/days_of_week are legacy
        fields (see their help_text) that no longer drive schedule or lesson
        generation; a Group with every one of them blank is perfectly valid
        once it has at least one GroupTeacher. These checks only run when an
        admin still fills them in (for historical/migrated data), as a
        sanity net on values that would otherwise silently make no sense.
        """
        errors = {}

        if self.end_date and self.start_date and self.end_date < self.start_date:
            errors["end_date"] = "Дата окончания не может быть раньше даты начала."

        if self.start_time and self.end_time and self.end_time <= self.start_time:
            errors["end_time"] = "Время окончания должно быть позже времени начала."

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
# GroupTeacher — "Teacher Program": one Teacher teaching one Subject on its
# own Schedule with its own Lesson Plan within one Group. This is the *only*
# unit a Group's teachers, schedules and lesson plans belong to — every
# GroupTeacher of a Group is equally a first-class teaching stream; none is
# more "primary" than another, and there is no separate code path or UI
# section for "the group's main teacher/schedule/room" as a distinct kind of
# thing. A Group with several teachers has one GroupTeacher per distinct
# (group, teacher, subject) combination; every GroupSchedule row of that
# teacher/subject in the group points at the same GroupTeacher (see
# GroupSchedule.save()), so it's the single place to hang a teacher's own
# GroupTeacherLessonPlan and see their own Lessons, independent of every
# other teacher in the same group.
#
# Never created directly by an admin/API call — always get-or-created
# automatically from a GroupSchedule save, so adding a Teacher Program is
# just: add a GroupSchedule row for that (teacher, subject) pair (typically
# via the Group admin page's schedule inline) — no separate "create the
# program first" step.
# ---------------------------------------------------------------------------

class GroupTeacher(models.Model):
    group = models.ForeignKey(
        Group,
        on_delete=models.CASCADE,
        related_name="teachers",
        verbose_name="Группа",
    )

    teacher = models.ForeignKey(
        Teacher,
        on_delete=models.PROTECT,
        related_name="group_assignments",
        verbose_name="Тренер",
    )

    subject = models.ForeignKey(
        Subject,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="group_assignments",
        verbose_name="Предмет",
        help_text=(
            "Предмет, который этот тренер ведёт в этой группе. Пусто — обычно "
            "означает программу, перенесённую из устаревших полей Group "
            "(teacher/room/schedule), без единого фиксированного предмета; "
            "это не влияет на то, как эта программа обрабатывается."
        ),
    )

    is_active = models.BooleanField(
        default=True,
        db_index=True,
        verbose_name="Активен",
        help_text="Неактивные назначения игнорируются при генерации занятий и проверке конфликтов.",
    )

    is_legacy_primary = models.BooleanField(
        default=False,
        verbose_name="Перенесено из устаревших полей группы",
        help_text=(
            "Чисто историческая метка: эта программа была создана переносом старых "
            "Group.teacher/room/start_time/end_time/days_of_week, а не добавлена вручную. "
            "Не даёт этой программе никаких особых прав или поведения — она полностью "
            "равноправна любой другой Teacher Program этой группы."
        ),
    )

    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Дата обновления")

    class Meta:
        verbose_name = "Тренер группы"
        verbose_name_plural = "Тренеры группы"
        ordering = ["group", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["group", "teacher", "subject"],
                name="unique_group_teacher_subject",
            ),
        ]
        indexes = [
            models.Index(fields=["group", "is_active"], name="ix_gteacher_group_active"),
            models.Index(fields=["teacher"], name="ix_gteacher_teacher"),
        ]

    def __str__(self):
        subject = self.subject.name if self.subject_id else "—"
        return f"{self.group.name} — {self.teacher} ({subject})"

    def clean(self):
        errors = {}
        if self.teacher_id and not self.teacher.is_active:
            errors["teacher"] = "Тренер должен быть активным."
        if self.subject_id and not self.subject.is_active:
            errors["subject"] = "Предмет должен быть активным."
        if errors:
            raise ValidationError(errors)


class GroupTeacherLessonPlan(models.Model):
    """One row of a GroupTeacher's own lesson-by-lesson plan.

    The individual counterpart of CourseLessonPlan: where CourseLessonPlan
    is a reusable, course-wide template shared by every group of that
    course, a GroupTeacherLessonPlan belongs to one specific teacher's
    assignment within one specific group, with its own lesson_number
    sequence starting at 1. A GroupTeacher with no rows here simply keeps
    using the group's shared CourseLessonPlan, exactly as every group did
    before this model existed (see services.lesson_generator) — this table
    only ever holds plans an admin has explicitly opted a teacher into.
    """

    group_teacher = models.ForeignKey(
        GroupTeacher,
        on_delete=models.CASCADE,
        related_name="lesson_plans",
        verbose_name="Тренер группы",
    )

    lesson_number = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1)],
        verbose_name="Номер занятия",
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
        verbose_name = "План занятия тренера"
        verbose_name_plural = "Планы занятий тренеров"
        ordering = ["group_teacher", "lesson_number"]
        constraints = [
            models.UniqueConstraint(
                fields=["group_teacher", "lesson_number"],
                name="unique_group_teacher_lesson_number_plan",
            ),
        ]

    def __str__(self):
        return f"{self.group_teacher} — занятие {self.lesson_number}: {self.topic}"


# ---------------------------------------------------------------------------
# GroupSchedule — a Group's recurring weekly timetable, one row per
# (weekday, time range) taught by one Teacher/Subject/Room — this is the
# *only* source of a Group's schedule and the *only* thing lesson generation
# and conflict-checking read (see services.lesson_generator). There is no
# separate "the group's main slot" concept: every row here is an equal
# Teacher Program slot, whether it was added by hand or (for data that
# predates GroupTeacher) migrated once from Group's now-inert legacy
# teacher/room/start_time/end_time/days_of_week fields — see
# services.group_schedule_sync, used only by that one-off migration, never
# called automatically on Group save.
#
# Every row belongs to exactly one GroupTeacher (see above) — a row's
# `group_teacher` is derived and kept in sync automatically from its own
# `teacher`/`subject` on every save(), never set directly by an admin/API
# call, so the pre-existing teacher/subject-based workflow (inline forms,
# filters, conflict checks) needs no changes at all.
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

    group_teacher = models.ForeignKey(
        GroupTeacher,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="schedules",
        verbose_name="Тренер группы",
        help_text="Заполняется автоматически из group/teacher/subject при сохранении.",
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

    def save(self, *args, **kwargs):
        # Keep group_teacher in lockstep with (group, teacher, subject) on
        # every save — including an edit that changes teacher/subject on an
        # existing row — so it's never a second, independently-editable
        # field an admin/API call could set out of sync with the two it's
        # derived from.
        group_teacher, _ = GroupTeacher.objects.get_or_create(
            group_id=self.group_id,
            teacher_id=self.teacher_id,
            subject_id=self.subject_id,
            defaults={"is_legacy_primary": self.subject_id is None},
        )
        self.group_teacher = group_teacher

        update_fields = kwargs.get("update_fields")
        if update_fields is not None:
            update_fields = set(update_fields)
            update_fields.add("group_teacher")
            kwargs["update_fields"] = update_fields

        super().save(*args, **kwargs)

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

    group_teacher = models.ForeignKey(
        GroupTeacher,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="lessons",
        verbose_name="Тренер группы",
        help_text=(
            "Тренер группы (GroupTeacher), которому принадлежит это занятие и его "
            "нумерация. Заполняется автоматически при сохранении, если не указано явно."
        ),
    )

    individual_plan = models.ForeignKey(
        GroupTeacherLessonPlan,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="lessons",
        verbose_name="Индивидуальный план занятия",
        help_text="Заполняется вместо `plan`, когда тренер использует свой собственный план (GroupTeacherLessonPlan).",
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
                fields=["group_teacher", "lesson_number"],
                name="unique_group_teacher_lesson_number",
            ),
        ]
        indexes = [
            models.Index(fields=["group", "date"], name="ix_lesson_group_date"),
            models.Index(fields=["subject", "date"], name="ix_lesson_subject_date"),
            models.Index(fields=["status", "date"], name="ix_lesson_status_date"),
            models.Index(fields=["group_teacher", "lesson_number"], name="ix_lesson_gteacher_number"),
        ]

    def __str__(self):
        return f"{self.group.name} — занятие {self.lesson_number} ({self.date})"

    def save(self, *args, **kwargs):
        # Every Lesson belongs to exactly one GroupTeacher, whose own
        # lesson_number sequence the uniqueness constraint above is scoped
        # to. The generator always sets it explicitly (see
        # services.lesson_generator); this fallback only matters for a
        # Lesson created some other way (e.g. by hand in Admin) — it derives
        # the same GroupTeacher `schedule.group_teacher` would resolve to,
        # falling back to the group's own primary teacher, so such a Lesson
        # still gets correct duplicate protection without the caller having
        # to know GroupTeacher exists.
        if self.group_teacher_id is None and self.group_id:
            if self.schedule_id and self.schedule.group_teacher_id:
                self.group_teacher_id = self.schedule.group_teacher_id
            else:
                teacher_id = self.teacher_id or self.group.teacher_id
                group_teacher, _ = GroupTeacher.objects.get_or_create(
                    group_id=self.group_id,
                    teacher_id=teacher_id,
                    subject_id=None,
                    defaults={"is_legacy_primary": True},
                )
                self.group_teacher_id = group_teacher.id

            update_fields = kwargs.get("update_fields")
            if update_fields is not None:
                update_fields = set(update_fields)
                update_fields.add("group_teacher")
                kwargs["update_fields"] = update_fields

        super().save(*args, **kwargs)

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

