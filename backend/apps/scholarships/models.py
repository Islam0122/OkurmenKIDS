"""Monthly scholarship system.

Business rules live in docs/scholarships.md; the short version:

* A scholarship period is a one-month window that has already ended. The
  cycle awarded on day D of a month evaluates [D of previous month,
  D-1 of this month] — for the default D=1 that is exactly the previous
  calendar month.
* Every student is scored across *all* subjects they had lessons in during
  the period (attendance / homework / trainer feedback per subject), the
  subject scores are aggregated into one overall score, eligible students
  are ranked deterministically and the top `max_recipients` get a pending
  award that an Admin approves.

Nothing here duplicates academy data: attendance, homework and lessons are
always read from apps.academy. The only new *input* data is
`TrainerFeedback` — this project had no trainer → student assessment
before (apps.feedback is parent/student surveys, a different thing).
"""
from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

WEIGHT_TOTAL = Decimal("1.00")


class AwardMode(models.TextChoices):
    MONTHLY = "monthly", "Раз в месяц (1-го числа)"
    TWICE_MONTHLY = "twice_monthly", "Два независимых цикла (1-го и 15-го)"


class SubjectAggregation(models.TextChoices):
    EQUAL = "equal", "Все предметы равны"
    LESSON_WEIGHTED = "lesson_weighted", "Пропорционально числу занятий"


# The only award days the system supports. Both are <= 28, so "the same day
# of the previous month" always exists (no February/31st edge cases).
AWARD_DAY_CHOICES = [(1, "1-е число"), (15, "15-е число")]
AWARD_DAYS_BY_MODE = {
    AwardMode.MONTHLY: (1,),
    AwardMode.TWICE_MONTHLY: (1, 15),
}


class ScholarshipConfigurationQuerySet(models.QuerySet):
    def active(self):
        return self.filter(is_active=True).first()


class ScholarshipConfiguration(models.Model):
    name = models.CharField(max_length=150, verbose_name="Название")

    is_active = models.BooleanField(
        default=True,
        verbose_name="Активна",
        help_text="Одновременно может быть активна только одна конфигурация.",
    )

    award_mode = models.CharField(
        max_length=20,
        choices=AwardMode.choices,
        default=AwardMode.MONTHLY,
        verbose_name="Режим начисления",
        help_text=(
            "«Раз в месяц»: 1-го числа оценивается прошлый календарный месяц, 15-е число ничего не начисляет. "
            "«Два цикла»: 1-го и 15-го — два независимых распределения, каждое за свой завершённый "
            "месячный период и со своим лимитом получателей."
        ),
    )

    max_recipients = models.PositiveSmallIntegerField(
        default=20,
        validators=[MinValueValidator(1), MaxValueValidator(1000)],
        verbose_name="Максимум получателей",
        help_text="Максимальное число уникальных получателей за один цикл.",
    )

    attendance_weight = models.DecimalField(
        max_digits=3, decimal_places=2, default=Decimal("0.40"),
        validators=[MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("1"))],
        verbose_name="Вес посещаемости",
    )
    homework_weight = models.DecimalField(
        max_digits=3, decimal_places=2, default=Decimal("0.30"),
        validators=[MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("1"))],
        verbose_name="Вес домашних заданий",
    )
    feedback_weight = models.DecimalField(
        max_digits=3, decimal_places=2, default=Decimal("0.30"),
        validators=[MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("1"))],
        verbose_name="Вес оценки тренера",
    )

    subject_aggregation = models.CharField(
        max_length=20,
        choices=SubjectAggregation.choices,
        default=SubjectAggregation.EQUAL,
        verbose_name="Агрегация предметов",
        help_text="Как баллы по предметам сводятся в один итоговый балл студента.",
    )

    late_homework_credit = models.DecimalField(
        max_digits=3, decimal_places=2, default=Decimal("0.50"),
        validators=[MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("1"))],
        verbose_name="Зачёт ДЗ, сданного с опозданием",
        help_text="Доля (0–1), которую получает ДЗ со статусом «Сдано с опозданием».",
    )

    min_overall_score = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal("0"),
        validators=[MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("100"))],
        verbose_name="Минимальный итоговый балл",
        help_text="Студенты с баллом ниже порога не получают стипендию. 0 — без порога.",
    )

    min_marked_lessons = models.PositiveSmallIntegerField(
        default=1,
        validators=[MinValueValidator(1)],
        verbose_name="Минимум отмеченных занятий",
        help_text="Сколько занятий с отметкой посещаемости (без уважительных) нужно за период.",
    )

    require_complete_feedback = models.BooleanField(
        default=True,
        verbose_name="Требовать оценку тренера по всем предметам",
        help_text=(
            "Если включено, студент без оценки тренера хотя бы по одному предмету получает статус "
            "«Неполные данные» и не участвует в распределении. Если выключено — отсутствующая "
            "оценка считается как 0 (никогда не как максимальный балл)."
        ),
    )

    auto_approve = models.BooleanField(
        default=False,
        verbose_name="Утверждать автоматически",
        help_text="Если выключено, сформированный рейтинг ждёт утверждения администратором.",
    )

    award_amount = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        validators=[MinValueValidator(Decimal("0"))],
        verbose_name="Сумма стипендии",
        help_text="Необязательно. Пусто — стипендия без денежной суммы.",
    )

    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Дата обновления")

    objects = ScholarshipConfigurationQuerySet.as_manager()

    class Meta:
        verbose_name = "Настройки стипендии"
        verbose_name_plural = "Настройки стипендии"
        ordering = ["-is_active", "-updated_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["is_active"],
                condition=models.Q(is_active=True),
                name="unique_active_scholarship_configuration",
            ),
        ]

    def __str__(self):
        return self.name

    @property
    def award_days(self) -> tuple[int, ...]:
        return AWARD_DAYS_BY_MODE[AwardMode(self.award_mode)]

    @property
    def weights_total(self) -> Decimal:
        return (self.attendance_weight or 0) + (self.homework_weight or 0) + (self.feedback_weight or 0)

    def clean(self):
        if None in (self.attendance_weight, self.homework_weight, self.feedback_weight):
            return
        if self.weights_total != WEIGHT_TOTAL:
            raise ValidationError(
                f"Сумма весов должна быть равна 1.00 (100%), сейчас {self.weights_total}."
            )


class ScholarshipPeriod(models.Model):
    """One scholarship period and its outcome — the container everything else
    (evaluations, awards, trainer feedback, run log) hangs off.

    Two kinds, same model:

    * **cycle** periods (`award_day` = 1 or 15) are generated by the schedule
      for the month that ended the day before the award date;
    * **manual** periods (`award_day` is null) are created by an Admin with
      arbitrary start/end dates; `evaluation_date` is the day after the end.

    The weights/limits used are *snapshotted* from the configuration at
    creation time, so editing the configuration later never silently
    rewrites a past ranking; recalculation of a DRAFT period reuses the
    snapshot. `max_recipients` is null for "без ограничения".
    """

    class Status(models.TextChoices):
        DRAFT = "draft", "Черновик (ожидает утверждения)"
        APPROVED = "approved", "Утверждён"

    configuration = models.ForeignKey(
        ScholarshipConfiguration,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="periods",
        verbose_name="Конфигурация",
    )

    title = models.CharField(max_length=150, default="Стипендия", verbose_name="Название")

    award_day = models.PositiveSmallIntegerField(
        choices=AWARD_DAY_CHOICES,
        null=True,
        blank=True,
        verbose_name="Цикл (день начисления)",
        help_text="Пусто — период создан вручную с произвольными датами.",
    )

    period_start = models.DateField(verbose_name="Начало периода")
    period_end = models.DateField(verbose_name="Конец периода")
    evaluation_date = models.DateField(verbose_name="Дата начисления")

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.DRAFT,
        db_index=True,
        verbose_name="Статус",
    )

    max_recipients = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(1)],
        verbose_name="Лимит стипендиатов",
        help_text="Пусто — без ограничения.",
    )
    attendance_weight = models.DecimalField(max_digits=3, decimal_places=2, verbose_name="Вес посещаемости")
    homework_weight = models.DecimalField(max_digits=3, decimal_places=2, verbose_name="Вес ДЗ")
    feedback_weight = models.DecimalField(max_digits=3, decimal_places=2, verbose_name="Вес оценки тренера")
    subject_aggregation = models.CharField(
        max_length=20, choices=SubjectAggregation.choices, verbose_name="Агрегация предметов",
    )
    late_homework_credit = models.DecimalField(max_digits=3, decimal_places=2, verbose_name="Зачёт ДЗ с опозданием")
    min_overall_score = models.DecimalField(max_digits=5, decimal_places=2, verbose_name="Минимальный балл")
    min_marked_lessons = models.PositiveSmallIntegerField(verbose_name="Минимум отмеченных занятий")
    require_complete_feedback = models.BooleanField(verbose_name="Требовать оценку тренера")
    award_amount = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True, verbose_name="Сумма стипендии",
    )

    last_calculated_at = models.DateTimeField(null=True, blank=True, verbose_name="Последний расчёт")
    generated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="+", verbose_name="Сформировал",
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="+", verbose_name="Утвердил",
    )
    approved_at = models.DateTimeField(null=True, blank=True, verbose_name="Дата утверждения")

    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Дата обновления")

    class Meta:
        verbose_name = "Стипендиальный период"
        verbose_name_plural = "Стипендиальные периоды"
        ordering = ["-period_start", "-award_day"]
        constraints = [
            models.UniqueConstraint(
                fields=["award_day", "period_start"],
                name="unique_scholarship_cycle_period",
            ),
            models.UniqueConstraint(
                fields=["period_start", "period_end"],
                condition=models.Q(award_day__isnull=True),
                name="unique_manual_scholarship_period",
            ),
            models.CheckConstraint(
                condition=models.Q(period_end__gte=models.F("period_start")),
                name="scholarship_period_end_after_start",
            ),
            models.CheckConstraint(
                condition=models.Q(evaluation_date__gt=models.F("period_end")),
                name="scholarship_evaluated_after_period_end",
            ),
        ]
        permissions = [
            ("generate_scholarshipperiod", "Может формировать стипендиальный рейтинг"),
            ("approve_scholarshipperiod", "Может утверждать стипендии"),
        ]

    def __str__(self):
        return f"{self.title} {self.date_range}"

    @property
    def date_range(self) -> str:
        return f"{self.period_start:%d.%m.%Y} — {self.period_end:%d.%m.%Y}"

    @property
    def is_draft(self) -> bool:
        return self.status == self.Status.DRAFT

    @property
    def is_manual(self) -> bool:
        return self.award_day is None

    @property
    def is_unlimited(self) -> bool:
        return self.max_recipients is None

    @property
    def is_calculated(self) -> bool:
        return self.last_calculated_at is not None

    def has_room_for(self, awarded: int) -> bool:
        """Whether one more recipient fits under the limit when `awarded`
        already have a scholarship."""
        return self.is_unlimited or awarded < self.max_recipients


class EligibilityStatus(models.TextChoices):
    ELIGIBLE = "eligible", "Допущен"
    NOT_FULL_PERIOD = "not_full_period", "Не весь период обучения"
    INACTIVE = "inactive", "Неактивен / на паузе"
    NO_DATA = "no_data", "Нет данных за период"
    INCOMPLETE_DATA = "incomplete_data", "Неполные данные"
    BELOW_THRESHOLD = "below_threshold", "Ниже порога"


class ScholarshipEvaluation(models.Model):
    """One student's computed result for one period — stored (unlike the
    on-demand academy reports) because a ranking that decided who got money
    must stay reproducible after the underlying data changes."""

    period = models.ForeignKey(
        ScholarshipPeriod, on_delete=models.CASCADE, related_name="evaluations", verbose_name="Период",
    )
    student = models.ForeignKey(
        "academy.Student", on_delete=models.CASCADE, related_name="scholarship_evaluations", verbose_name="Студент",
    )

    # Snapshots — what the student looked like when evaluated.
    student_name = models.CharField(max_length=210, verbose_name="ФИО")
    group = models.ForeignKey(
        "academy.Group", on_delete=models.SET_NULL, null=True, blank=True, related_name="+", verbose_name="Группа",
    )
    group_name = models.CharField(max_length=150, blank=True, verbose_name="Группа (на момент оценки)")
    course_name = models.CharField(max_length=150, blank=True, verbose_name="Курс (программа)")
    enrollment_date = models.DateField(null=True, blank=True, verbose_name="Дата начала обучения")

    overall_score = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True, verbose_name="Итоговый балл")
    attendance_score = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True, verbose_name="Посещаемость")
    homework_score = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True, verbose_name="Домашние задания")
    feedback_score = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True, verbose_name="Оценка тренера")

    lessons_count = models.PositiveIntegerField(default=0, verbose_name="Занятий учтено")
    subjects_count = models.PositiveSmallIntegerField(default=0, verbose_name="Предметов учтено")

    rank = models.PositiveIntegerField(null=True, blank=True, verbose_name="Место")
    eligibility_status = models.CharField(
        max_length=20, choices=EligibilityStatus.choices, db_index=True, verbose_name="Допуск",
    )
    ineligibility_reason = models.TextField(blank=True, verbose_name="Причина недопуска")
    data_warnings = models.JSONField(default=list, blank=True, verbose_name="Предупреждения о данных")

    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Дата обновления")

    class Meta:
        verbose_name = "Оценка студента"
        verbose_name_plural = "Оценки студентов"
        ordering = ["period", "rank", "-overall_score", "student_name"]
        constraints = [
            models.UniqueConstraint(fields=["period", "student"], name="unique_student_scholarship_evaluation"),
            models.UniqueConstraint(fields=["period", "rank"], name="unique_scholarship_evaluation_rank"),
        ]
        indexes = [
            models.Index(fields=["period", "eligibility_status"], name="ix_scheval_period_status"),
            models.Index(fields=["student", "period"], name="ix_scheval_student_period"),
        ]

    def __str__(self):
        return f"{self.student_name} — {self.period}"

    @property
    def is_eligible(self) -> bool:
        return self.eligibility_status == EligibilityStatus.ELIGIBLE


class ScholarshipSubjectScore(models.Model):
    """Per-subject breakdown of one evaluation. `subject` is null only for
    lessons that have no subject set (legacy data) — they are shown as
    their own «Без предмета» row, never silently dropped."""

    evaluation = models.ForeignKey(
        ScholarshipEvaluation, on_delete=models.CASCADE, related_name="subject_scores", verbose_name="Оценка",
    )
    subject = models.ForeignKey(
        "users.Subject", on_delete=models.SET_NULL, null=True, blank=True, related_name="+", verbose_name="Предмет",
    )
    subject_name = models.CharField(max_length=100, verbose_name="Предмет (название)")

    lessons_attended = models.PositiveIntegerField(default=0, verbose_name="Посещено")
    lessons_missed = models.PositiveIntegerField(default=0, verbose_name="Пропущено")
    lessons_excused = models.PositiveIntegerField(default=0, verbose_name="Уважительные")
    lessons_unmarked = models.PositiveIntegerField(default=0, verbose_name="Без отметки")

    homework_required = models.PositiveIntegerField(default=0, verbose_name="ДЗ задано")
    homework_completed = models.DecimalField(max_digits=7, decimal_places=2, default=Decimal("0"), verbose_name="ДЗ зачтено")

    feedback_expected = models.PositiveSmallIntegerField(default=0, verbose_name="Тренеров по предмету")
    feedback_received = models.PositiveSmallIntegerField(default=0, verbose_name="Оценок тренеров")

    attendance_score = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True, verbose_name="Посещаемость")
    homework_score = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True, verbose_name="ДЗ")
    feedback_score = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True, verbose_name="Оценка тренера")
    subject_score = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True, verbose_name="Балл по предмету")
    aggregation_weight = models.DecimalField(
        max_digits=8, decimal_places=2, default=Decimal("0"), verbose_name="Вес в итоговом балле",
        help_text="0 — предмет не учитывался (нет данных).",
    )

    class Meta:
        verbose_name = "Балл по предмету"
        verbose_name_plural = "Баллы по предметам"
        ordering = ["evaluation", "subject_name"]

    def __str__(self):
        return f"{self.evaluation.student_name} — {self.subject_name}"


class ScholarshipAward(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Ожидает утверждения"
        APPROVED = "approved", "Утверждена"

    period = models.ForeignKey(
        ScholarshipPeriod, on_delete=models.CASCADE, related_name="awards", verbose_name="Период",
    )
    student = models.ForeignKey(
        "academy.Student", on_delete=models.CASCADE, related_name="scholarship_awards", verbose_name="Студент",
    )
    evaluation = models.OneToOneField(
        ScholarshipEvaluation, on_delete=models.CASCADE, related_name="award", verbose_name="Оценка",
    )
    rank = models.PositiveIntegerField(verbose_name="Место")
    award_date = models.DateField(verbose_name="Дата начисления")
    amount = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, verbose_name="Сумма")
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING, db_index=True, verbose_name="Статус",
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="+", verbose_name="Утвердил",
    )
    approved_at = models.DateTimeField(null=True, blank=True, verbose_name="Дата утверждения")

    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Дата обновления")

    class Meta:
        verbose_name = "Стипендия"
        verbose_name_plural = "Стипендии"
        ordering = ["-award_date", "rank"]
        constraints = [
            # The duplicate-award guarantee: one award per student per
            # period (= per award cycle, since a period *is* one cycle).
            models.UniqueConstraint(fields=["student", "period"], name="unique_student_scholarship_period"),
            models.UniqueConstraint(fields=["period", "rank"], name="unique_scholarship_award_rank"),
        ]
        indexes = [
            models.Index(fields=["student", "status"], name="ix_schaward_student_status"),
        ]

    def __str__(self):
        return f"{self.student} — {self.period} (#{self.rank})"


_CRITERION_VALIDATORS = [MinValueValidator(1), MaxValueValidator(5)]


class TrainerFeedback(models.Model):
    """A trainer's standardized assessment of one student in one subject for
    one scholarship period. Every criterion is 1–5; the feedback score is
    their mean mapped to 0–100 (mean / 5 × 100)."""

    CRITERIA = ("progress", "participation", "discipline", "understanding")

    period = models.ForeignKey(
        ScholarshipPeriod, on_delete=models.CASCADE, related_name="feedback", verbose_name="Период",
    )
    student = models.ForeignKey(
        "academy.Student", on_delete=models.CASCADE, related_name="trainer_feedback", verbose_name="Студент",
    )
    subject = models.ForeignKey(
        "users.Subject", on_delete=models.PROTECT, related_name="trainer_feedback", verbose_name="Предмет",
    )
    teacher = models.ForeignKey(
        "users.Teacher", on_delete=models.CASCADE, related_name="scholarship_feedback", verbose_name="Тренер",
    )

    progress = models.PositiveSmallIntegerField(verbose_name="Прогресс", validators=_CRITERION_VALIDATORS)
    participation = models.PositiveSmallIntegerField(verbose_name="Активность на занятиях", validators=_CRITERION_VALIDATORS)
    discipline = models.PositiveSmallIntegerField(verbose_name="Дисциплина", validators=_CRITERION_VALIDATORS)
    understanding = models.PositiveSmallIntegerField(verbose_name="Понимание материала", validators=_CRITERION_VALIDATORS)

    comment = models.TextField(blank=True, max_length=2000, verbose_name="Комментарий")

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="+", verbose_name="Создал",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="+", verbose_name="Изменил",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Дата обновления")

    class Meta:
        verbose_name = "Оценка тренера"
        verbose_name_plural = "Оценки тренеров"
        ordering = ["-period__period_start", "student__last_name", "subject__name"]
        constraints = [
            models.UniqueConstraint(
                fields=["period", "student", "subject", "teacher"],
                name="unique_trainer_feedback_per_period",
            ),
        ]
        indexes = [
            models.Index(fields=["period", "student"], name="ix_trfeedback_period_student"),
        ]

    def __str__(self):
        return f"{self.student} — {self.subject} ({self.teacher})"

    @property
    def score(self) -> Decimal:
        values = [getattr(self, name) for name in self.CRITERIA]
        return Decimal(sum(values)) / Decimal(len(values)) / Decimal(5) * Decimal(100)


class ScholarshipRunLog(models.Model):
    class Action(models.TextChoices):
        GENERATE = "generate", "Формирование"
        RECALCULATE = "recalculate", "Пересчёт"
        APPROVE = "approve", "Утверждение"
        EDIT = "edit", "Изменение периода"
        AWARD = "award", "Изменение списка стипендиатов"

    class Trigger(models.TextChoices):
        SCHEDULE = "schedule", "По расписанию"
        ADMIN = "admin", "Админ-панель"
        API = "api", "API"

    class Result(models.TextChoices):
        SUCCESS = "success", "Успешно"
        SKIPPED = "skipped", "Пропущено"
        FAILED = "failed", "Ошибка"

    action = models.CharField(max_length=20, choices=Action.choices, verbose_name="Действие")
    trigger = models.CharField(max_length=20, choices=Trigger.choices, verbose_name="Источник")
    result = models.CharField(max_length=20, choices=Result.choices, db_index=True, verbose_name="Результат")
    period = models.ForeignKey(
        ScholarshipPeriod, on_delete=models.SET_NULL, null=True, blank=True, related_name="run_logs",
        verbose_name="Период",
    )
    award_day = models.PositiveSmallIntegerField(null=True, blank=True, verbose_name="Цикл")
    award_date = models.DateField(null=True, blank=True, verbose_name="Дата начисления")
    message = models.TextField(blank=True, verbose_name="Сообщение")
    triggered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="+", verbose_name="Пользователь",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Время")

    class Meta:
        verbose_name = "Журнал запусков"
        verbose_name_plural = "Журнал запусков"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.get_action_display()} — {self.get_result_display()} ({self.created_at:%d.%m.%Y %H:%M})"
