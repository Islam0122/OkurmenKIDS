"""Feedback surveys — admin-built questionnaires shared with parents and
students through a public link.

Privacy model (see also docs/feedback.md):

* OkurmenKIDS has no parent or student accounts (only ADMIN/TEACHER users),
  so every respondent is an unauthenticated visitor of a public link.
  Nothing a respondent types about themselves or their child is verified —
  it is stored and shown as *self-reported*.
* An ANONYMOUS response stores no respondent name, and the system never
  stores an IP address, user agent, phone or e-mail for any response. The
  only identifying data an anonymous response can ever carry is a child's
  name, and only when the Admin explicitly enabled
  ``Survey.ask_child_name_when_anonymous`` — the public form then warns the
  respondent that the answer is not fully anonymous.
* Duplicate-submission protection is a signed browser cookie only (no
  server-side fingerprint), so it can be bypassed by clearing cookies; it is
  a convenience guard, not an identity check.
"""
from __future__ import annotations

import secrets

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone

# Hard caps that apply regardless of per-question settings — they bound what
# a public, unauthenticated client can ever make the database store.
TEXT_ANSWER_MAX_LENGTH = 5000
NAME_MAX_LENGTH = 150
QUESTION_TEXT_MAX_LENGTH = 500
OPTION_TEXT_MAX_LENGTH = 200
MAX_OPTIONS_PER_QUESTION = 30
MAX_QUESTIONS_PER_SURVEY = 100


def generate_public_token() -> str:
    """~192 bits of randomness, URL-safe — never derived from the pk."""
    return secrets.token_urlsafe(24)


class SurveyQuerySet(models.QuerySet):
    def published(self):
        return self.filter(status=Survey.Status.PUBLISHED)


class Survey(models.Model):
    class Audience(models.TextChoices):
        PARENT = "parent", "Родители"
        STUDENT = "student", "Студенты"

    class VisibilityMode(models.TextChoices):
        OPEN = "open", "Открытый отзыв"
        ANONYMOUS = "anonymous", "Анонимный отзыв"
        BOTH = "both", "На выбор респондента"

    class Status(models.TextChoices):
        DRAFT = "draft", "Черновик"
        PUBLISHED = "published", "Опубликован"
        CLOSED = "closed", "Закрыт"

    class ChildNameMode(models.TextChoices):
        REQUIRED = "required", "Обязательно"
        OPTIONAL = "optional", "Необязательно"
        NOT_COLLECTED = "not_collected", "Не спрашивать"

    class Availability(models.TextChoices):
        AVAILABLE = "available", "Принимает ответы"
        DRAFT = "draft", "Черновик"
        CLOSED = "closed", "Закрыт"
        NOT_STARTED = "not_started", "Ещё не начался"
        ENDED = "ended", "Срок истёк"
        FULL = "full", "Лимит ответов исчерпан"

    title = models.CharField(max_length=200, verbose_name="Название")
    description = models.TextField(
        blank=True,
        max_length=2000,
        verbose_name="Описание",
        help_text="Показывается респонденту над вопросами.",
    )
    audience = models.CharField(
        max_length=20,
        choices=Audience.choices,
        default=Audience.PARENT,
        db_index=True,
        verbose_name="Аудитория",
    )
    visibility_mode = models.CharField(
        max_length=20,
        choices=VisibilityMode.choices,
        default=VisibilityMode.ANONYMOUS,
        verbose_name="Тип отзыва",
        help_text=(
            "Открытый — респондент указывает имя, администратор его видит. "
            "Анонимный — имя не спрашивается и не сохраняется. "
            "На выбор — респондент сам решает при заполнении."
        ),
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.DRAFT,
        db_index=True,
        verbose_name="Статус",
    )

    starts_at = models.DateTimeField(null=True, blank=True, verbose_name="Начало приёма ответов")
    ends_at = models.DateTimeField(null=True, blank=True, verbose_name="Окончание приёма ответов")
    max_responses = models.PositiveIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(100000)],
        verbose_name="Максимум ответов",
        help_text="Пусто — без ограничения.",
    )
    allow_multiple_submissions = models.BooleanField(
        default=False,
        verbose_name="Разрешить повторные ответы",
        help_text=(
            "Выключено — после отправки браузер запоминает, что ответ уже дан. "
            "Это защита от случайных повторов, а не проверка личности."
        ),
    )

    # Parent-specific child identification rules. Ignored for student surveys.
    child_name_mode = models.CharField(
        max_length=20,
        choices=ChildNameMode.choices,
        default=ChildNameMode.OPTIONAL,
        verbose_name="Имя ребёнка",
        help_text="Только для опросов родителей. Имя ребёнка не проверяется — это данные со слов родителя.",
    )
    ask_child_name_when_anonymous = models.BooleanField(
        default=False,
        verbose_name="Спрашивать имя ребёнка в анонимном отзыве",
        help_text=(
            "Имя ребёнка косвенно указывает на родителя — такой ответ уже не полностью анонимный, "
            "и форма предупредит об этом респондента."
        ),
    )

    # Optional targeting — context shown on the public page and used as the
    # analytics filter dimensions. Validated against real LMS relationships.
    group = models.ForeignKey(
        "academy.Group",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="feedback_surveys",
        verbose_name="Группа",
    )
    teacher = models.ForeignKey(
        "users.Teacher",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="feedback_surveys",
        verbose_name="Тренер",
    )
    subject = models.ForeignKey(
        "users.Subject",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="feedback_surveys",
        verbose_name="Предмет",
    )

    confirmation_message = models.TextField(
        blank=True,
        max_length=1000,
        default="Спасибо! Ваш ответ отправлен.",
        verbose_name="Сообщение после отправки",
    )

    public_token = models.CharField(
        max_length=64,
        unique=True,
        default=generate_public_token,
        editable=False,
        verbose_name="Токен ссылки",
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="feedback_surveys",
        verbose_name="Автор",
    )
    published_at = models.DateTimeField(null=True, blank=True, editable=False, verbose_name="Опубликован")
    closed_at = models.DateTimeField(null=True, blank=True, editable=False, verbose_name="Закрыт")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Дата обновления")

    objects = SurveyQuerySet.as_manager()

    class Meta:
        verbose_name = "Опрос"
        verbose_name_plural = "Опросы"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["audience", "status"], name="ix_survey_audience_status"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(starts_at__isnull=True)
                    | models.Q(ends_at__isnull=True)
                    | models.Q(ends_at__gt=models.F("starts_at"))
                ),
                name="survey_ends_after_starts",
            ),
        ]

    def __str__(self):
        return self.title

    # -- Derived state ------------------------------------------------------

    @property
    def is_parent_survey(self) -> bool:
        return self.audience == self.Audience.PARENT

    def allowed_visibilities(self) -> list[str]:
        """The response-level visibility values a respondent may pick."""
        if self.visibility_mode == self.VisibilityMode.BOTH:
            return [SurveyResponse.Visibility.OPEN, SurveyResponse.Visibility.ANONYMOUS]
        if self.visibility_mode == self.VisibilityMode.OPEN:
            return [SurveyResponse.Visibility.OPEN]
        return [SurveyResponse.Visibility.ANONYMOUS]

    def child_name_mode_for(self, visibility: str) -> str:
        """Effective child-name rule for one response visibility."""
        if not self.is_parent_survey:
            return self.ChildNameMode.NOT_COLLECTED
        if visibility == SurveyResponse.Visibility.ANONYMOUS and not self.ask_child_name_when_anonymous:
            return self.ChildNameMode.NOT_COLLECTED
        return self.child_name_mode

    def availability(self, *, now=None, response_count: int | None = None) -> str:
        now = now or timezone.now()
        if self.status == self.Status.DRAFT:
            return self.Availability.DRAFT
        if self.status == self.Status.CLOSED:
            return self.Availability.CLOSED
        if self.starts_at and now < self.starts_at:
            return self.Availability.NOT_STARTED
        if self.ends_at and now >= self.ends_at:
            return self.Availability.ENDED
        if self.max_responses is not None:
            if response_count is None:
                response_count = self.responses.count()
            if response_count >= self.max_responses:
                return self.Availability.FULL
        return self.Availability.AVAILABLE

    def has_responses(self) -> bool:
        return self.responses.exists()

    def clean(self):
        errors = {}
        if self.starts_at and self.ends_at and self.ends_at <= self.starts_at:
            errors["ends_at"] = "Окончание должно быть позже начала."
        if self.group_id and self.teacher_id:
            from apps.academy.models import GroupTeacher

            if not GroupTeacher.objects.filter(group_id=self.group_id, teacher_id=self.teacher_id).exists():
                errors["teacher"] = "Этот тренер не ведёт занятия в выбранной группе."
        if self.group_id and self.subject_id:
            if not self.group.course.subjects.filter(pk=self.subject_id).exists():
                errors["subject"] = "Предмет не входит в курс выбранной группы."
        if errors:
            raise ValidationError(errors)


class SurveyQuestion(models.Model):
    class QuestionType(models.TextChoices):
        TEXT = "text", "Текстовый ответ"
        SINGLE_CHOICE = "single_choice", "Один вариант"
        MULTIPLE_CHOICE = "multiple_choice", "Несколько вариантов"

    survey = models.ForeignKey(Survey, on_delete=models.CASCADE, related_name="questions", verbose_name="Опрос")
    text = models.CharField(max_length=QUESTION_TEXT_MAX_LENGTH, verbose_name="Вопрос")
    help_text = models.CharField(max_length=300, blank=True, verbose_name="Подсказка")
    question_type = models.CharField(
        max_length=20,
        choices=QuestionType.choices,
        default=QuestionType.SINGLE_CHOICE,
        verbose_name="Тип вопроса",
    )
    is_required = models.BooleanField(default=True, verbose_name="Обязательный")
    order = models.PositiveIntegerField(default=0, db_index=True, verbose_name="Порядок")

    # TEXT settings
    is_multiline = models.BooleanField(default=True, verbose_name="Многострочный ответ")
    min_length = models.PositiveIntegerField(
        null=True, blank=True, validators=[MaxValueValidator(TEXT_ANSWER_MAX_LENGTH)], verbose_name="Мин. длина"
    )
    max_length = models.PositiveIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(TEXT_ANSWER_MAX_LENGTH)],
        verbose_name="Макс. длина",
    )

    # MULTIPLE_CHOICE settings
    min_selections = models.PositiveIntegerField(
        null=True, blank=True, validators=[MaxValueValidator(MAX_OPTIONS_PER_QUESTION)], verbose_name="Мин. выбранных"
    )
    max_selections = models.PositiveIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(MAX_OPTIONS_PER_QUESTION)],
        verbose_name="Макс. выбранных",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Вопрос опроса"
        verbose_name_plural = "Вопросы опроса"
        ordering = ["survey", "order", "id"]
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(min_length__isnull=True)
                    | models.Q(max_length__isnull=True)
                    | models.Q(max_length__gte=models.F("min_length"))
                ),
                name="question_length_range_valid",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(min_selections__isnull=True)
                    | models.Q(max_selections__isnull=True)
                    | models.Q(max_selections__gte=models.F("min_selections"))
                ),
                name="question_selection_range_valid",
            ),
        ]

    def __str__(self):
        return self.text

    @property
    def is_choice(self) -> bool:
        return self.question_type in (self.QuestionType.SINGLE_CHOICE, self.QuestionType.MULTIPLE_CHOICE)

    @property
    def effective_max_length(self) -> int:
        return self.max_length or TEXT_ANSWER_MAX_LENGTH


class QuestionOption(models.Model):
    question = models.ForeignKey(
        SurveyQuestion, on_delete=models.CASCADE, related_name="options", verbose_name="Вопрос"
    )
    text = models.CharField(max_length=OPTION_TEXT_MAX_LENGTH, verbose_name="Вариант")
    order = models.PositiveIntegerField(default=0, verbose_name="Порядок")

    class Meta:
        verbose_name = "Вариант ответа"
        verbose_name_plural = "Варианты ответа"
        ordering = ["question", "order", "id"]

    def __str__(self):
        return self.text


class SurveyResponse(models.Model):
    class Visibility(models.TextChoices):
        OPEN = "open", "Открытый"
        ANONYMOUS = "anonymous", "Анонимный"

    # PROTECT: a survey that already collected answers can't be deleted by
    # accident — close it instead (or delete its responses deliberately).
    survey = models.ForeignKey(Survey, on_delete=models.PROTECT, related_name="responses", verbose_name="Опрос")
    visibility = models.CharField(max_length=20, choices=Visibility.choices, db_index=True, verbose_name="Тип отзыва")
    # Both names are self-reported and never verified against LMS records.
    # Always blank for an anonymous response (child_name may be set only
    # when the survey explicitly asks for it — see Survey docstring).
    respondent_name = models.CharField(max_length=NAME_MAX_LENGTH, blank=True, verbose_name="Имя респондента")
    child_name = models.CharField(max_length=NAME_MAX_LENGTH, blank=True, verbose_name="Имя ребёнка (со слов)")
    submitted_at = models.DateTimeField(default=timezone.now, db_index=True, verbose_name="Отправлено")

    class Meta:
        verbose_name = "Ответ на опрос"
        verbose_name_plural = "Ответы на опросы"
        ordering = ["-submitted_at"]
        indexes = [
            models.Index(fields=["survey", "submitted_at"], name="ix_response_survey_date"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=~models.Q(visibility="anonymous") | models.Q(respondent_name=""),
                name="anonymous_response_has_no_name",
            ),
        ]

    def __str__(self):
        return f"{self.survey} — {self.submitted_at:%d.%m.%Y %H:%M}"

    @property
    def display_name(self) -> str:
        if self.visibility == self.Visibility.ANONYMOUS:
            return "Аноним"
        return self.respondent_name or "—"


class SurveyAnswer(models.Model):
    response = models.ForeignKey(SurveyResponse, on_delete=models.CASCADE, related_name="answers")
    # PROTECT: answered questions/options can't be deleted, so historical
    # responses are never silently corrupted by later survey edits.
    question = models.ForeignKey(SurveyQuestion, on_delete=models.PROTECT, related_name="answers")
    text_value = models.TextField(blank=True, max_length=TEXT_ANSWER_MAX_LENGTH)
    selected_options = models.ManyToManyField(
        QuestionOption, through="SurveyAnswerOption", related_name="answers", blank=True
    )

    class Meta:
        verbose_name = "Ответ на вопрос"
        verbose_name_plural = "Ответы на вопросы"
        constraints = [
            models.UniqueConstraint(fields=["response", "question"], name="unique_answer_per_question"),
        ]


class SurveyAnswerOption(models.Model):
    answer = models.ForeignKey(SurveyAnswer, on_delete=models.CASCADE, related_name="option_links")
    option = models.ForeignKey(QuestionOption, on_delete=models.PROTECT, related_name="answer_links")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["answer", "option"], name="unique_answer_option"),
        ]
