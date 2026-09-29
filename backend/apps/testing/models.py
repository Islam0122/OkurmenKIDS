"""Testing module — tests, questions, sessions, attempts and answers.

Ported from the standalone OkurmenKidsTEST project. The table layout
(``testing_*`` tables, UUID primary keys, column names, indexes and
constraints) is kept identical to that project's production schema so its
data can be copied over as-is (see migrations/0001_initial.py).

Everything LMS-specific is additive and nullable (migrations/0002+):

* ``TestSession.group``   → academy.Group    (who the session is for)
* ``TestSession.lesson``  → academy.Lesson   (optional: the lesson it follows)
* ``TestSession.teacher`` → users.Teacher    (who ran it)
* ``StudentAttempt.student`` → academy.Student

``StudentAttempt.student_name`` stays: it is the historical snapshot of the
name the attempt was taken under — the only identity legacy attempts have,
and still filled in for new attempts so results read the same even after a
Student is renamed or deleted.

The standalone project's own ``Teacher`` / ``TeacherAccess`` models are
deliberately not ported: they never had a migration (so hold no production
data) and are replaced by ``users.Teacher`` and LMS authentication.
"""
import secrets
import uuid
from datetime import timedelta

from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


class QuestionType(models.TextChoices):
    SINGLE_CHOICE = "single_choice", "Один вариант"
    MULTIPLE_CHOICE = "multiple_choice", "Несколько вариантов"
    TEXT = "text", "Текстовый ответ"
    CODE = "code", "Код"


class DifficultyLevel(models.TextChoices):
    EASY = "easy", "Лёгкий"
    MEDIUM = "medium", "Средний"
    HARD = "hard", "Сложный"


class ProgrammingLanguage(models.TextChoices):
    PYTHON = "python", "Python"
    JAVASCRIPT = "javascript", "JavaScript"
    HTML = "html", "HTML"
    CSS = "css", "CSS"
    NONE = "", "—"


class SessionType(models.TextChoices):
    EXAM = "exam", "Экзамен"
    TRAINING = "training", "Тренажёр"


class SessionStatus(models.TextChoices):
    CREATED = "created", "Создана"
    RUNNING = "running", "Идёт"
    FINISHED = "finished", "Завершена"


class AttemptStatus(models.TextChoices):
    ACTIVE = "active", "Активна"
    FINISHED = "finished", "Завершена"
    EXPIRED = "expired", "Просрочена"


class GradingStatus(models.TextChoices):
    PENDING = "pending", "На проверке"
    PROCESSING = "processing", "Обрабатывается"
    AUTO = "auto", "Авто"
    AI = "ai", "AI"  # legacy value, kept so old rows stay valid
    DONE = "done", "Готово"
    FAILED = "failed", "Ошибка AI"
    MANUAL = "manual", "Вручную"


# ---------------------------------------------------------------------------
# Test / Question / QuestionOption
# ---------------------------------------------------------------------------

class Test(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=255, unique=True, verbose_name="Название")
    description = models.TextField(blank=True, verbose_name="Описание")
    level = models.CharField(
        max_length=10,
        choices=DifficultyLevel.choices,
        default=DifficultyLevel.MEDIUM,
        verbose_name="Уровень",
    )
    is_active = models.BooleanField(default=True, verbose_name="Активен")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Создан")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Обновлён")

    class Meta:
        ordering = ["title"]
        verbose_name = "Тест"
        verbose_name_plural = "Тесты"

    def __str__(self):
        return self.title

    @property
    def question_count(self):
        return self.questions.count()


class Question(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    test = models.ForeignKey(
        Test,
        on_delete=models.CASCADE,
        related_name="questions",
        verbose_name="Тест",
    )
    text = models.TextField(verbose_name="Текст вопроса")
    question_type = models.CharField(
        max_length=20,
        choices=QuestionType.choices,
        default=QuestionType.SINGLE_CHOICE,
        verbose_name="Тип",
    )
    language = models.CharField(
        max_length=20,
        choices=ProgrammingLanguage.choices,
        default=ProgrammingLanguage.NONE,
        blank=True,
        verbose_name="Язык",
    )
    difficulty = models.CharField(
        max_length=10,
        choices=DifficultyLevel.choices,
        default=DifficultyLevel.MEDIUM,
        verbose_name="Сложность",
    )
    order = models.PositiveIntegerField(default=0, verbose_name="Порядок")
    metadata = models.JSONField(default=dict, blank=True, verbose_name="Метаданные")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Создан")

    class Meta:
        ordering = ["test", "order", "created_at"]
        verbose_name = "Вопрос"
        verbose_name_plural = "Вопросы"
        indexes = [
            models.Index(fields=["test", "order"], name="question_test_order_idx"),
            models.Index(fields=["question_type"], name="question_type_idx"),
        ]
        constraints = [
            models.UniqueConstraint(fields=["test", "text"], name="unique_question_text_per_test"),
        ]

    def __str__(self):
        return f"[{self.test.title}] {self.text[:60]}"

    def clean(self):
        if self.question_type == QuestionType.CODE and not self.language:
            raise ValidationError({"language": "Для code-вопроса обязателен язык."})

    @property
    def is_auto_gradable(self) -> bool:
        """True если вопрос можно проверить автоматически (без AI)."""
        return self.question_type in (QuestionType.SINGLE_CHOICE, QuestionType.MULTIPLE_CHOICE)


class QuestionOption(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    question = models.ForeignKey(
        Question,
        on_delete=models.CASCADE,
        related_name="options",
        verbose_name="Вопрос",
    )
    text = models.CharField(max_length=1024, verbose_name="Текст варианта")
    is_correct = models.BooleanField(default=False, verbose_name="Правильный")
    order = models.PositiveSmallIntegerField(default=0, verbose_name="Порядок")

    class Meta:
        ordering = ["order"]
        verbose_name = "Вариант ответа"
        verbose_name_plural = "Варианты ответов"
        indexes = [
            models.Index(fields=["question", "is_correct"], name="option_question_correct_idx"),
        ]

    def __str__(self):
        return f'{"✓" if self.is_correct else "✗"} {self.text[:60]}'


# ---------------------------------------------------------------------------
# TestSession
# ---------------------------------------------------------------------------

SESSION_TTL_HOURS = 2


def _default_expires():
    return timezone.now() + timedelta(hours=SESSION_TTL_HOURS)


def _generate_key():
    return secrets.token_urlsafe(16)


class TestSession(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    test = models.ForeignKey(
        Test,
        on_delete=models.CASCADE,
        related_name="sessions",
        verbose_name="Тест",
    )

    # -- LMS links (all nullable: legacy sessions predate them) --------------
    # SET_NULL everywhere: deleting a Group/Lesson/Teacher must neither be
    # blocked by nor wipe test history — ScholarshipEvaluation.group follows
    # the same rule. Lessons in particular are regenerated/repaired by
    # academy services, so a PROTECT here would break those flows.
    group = models.ForeignKey(
        "academy.Group",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="test_sessions",
        verbose_name="Группа",
        help_text="Группа, для которой проводится тестирование.",
    )
    lesson = models.ForeignKey(
        "academy.Lesson",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="test_sessions",
        verbose_name="Урок",
        help_text="Необязательно: урок группы, после которого проводится тест.",
    )
    teacher = models.ForeignKey(
        "users.Teacher",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="test_sessions",
        verbose_name="Тренер",
        help_text="Тренер, создавший сессию.",
    )

    session_type = models.CharField(
        max_length=10,
        choices=SessionType.choices,
        default=SessionType.EXAM,
        verbose_name="Тип сессии",
        db_index=True,
    )
    title = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="Название сессии",
        help_text='Необязательное название (напр. "Группа A, 01.04.2026")',
    )
    key = models.CharField(
        max_length=64,
        unique=True,
        default=_generate_key,
        verbose_name="Ключ сессии",
        db_index=True,
    )
    status = models.CharField(
        max_length=10,
        choices=SessionStatus.choices,
        default=SessionStatus.CREATED,
        verbose_name="Статус",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Создана")
    expires_at = models.DateTimeField(default=_default_expires, verbose_name="Истекает")
    is_active = models.BooleanField(default=True, verbose_name="Активна")

    # None = без ограничений (training); exam defaults to 1 at creation time.
    max_attempts_per_student = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        verbose_name="Макс. попыток на студента",
        help_text="Только для режима exam. Пусто = без ограничений.",
    )

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Сессия тестирования"
        verbose_name_plural = "Сессии тестирования"
        indexes = [
            models.Index(fields=["status", "is_active"], name="session_status_active_idx"),
        ]

    def __str__(self):
        label = self.title or self.key
        return f"{self.test.title} [{self.get_session_type_display()}] / {label}"

    @property
    def is_exam(self) -> bool:
        return self.session_type == SessionType.EXAM

    @property
    def is_training(self) -> bool:
        return self.session_type == SessionType.TRAINING

    @property
    def is_time_expired(self) -> bool:
        """Только для exam: время вышло."""
        return self.is_exam and timezone.now() >= self.expires_at

    @property
    def is_valid(self) -> bool:
        """Exam: активна и не истёк expires_at. Training: просто активна."""
        if not self.is_active:
            return False
        if self.is_exam:
            return timezone.now() < self.expires_at
        return True

    @property
    def effective_status(self) -> str:
        if self.is_exam and timezone.now() >= self.expires_at:
            return SessionStatus.FINISHED
        return self.status

    @property
    def active_attempt_count(self) -> int:
        return self.attempts.filter(status=AttemptStatus.ACTIVE).count()

    def clean(self):
        super().clean()
        if self.lesson_id is None:
            return
        if self.group_id is None:
            raise ValidationError({"group": "Укажите группу: урок выбирается внутри группы."})
        if self.lesson.group_id != self.group_id:
            raise ValidationError({"lesson": "Урок не принадлежит выбранной группе."})

    def can_student_attempt(self, student_name: str = "", student=None) -> bool:
        """Лимит попыток: None = без ограничений; истёкшие попытки не считаются.

        Attempts are counted per LMS Student when one is given, otherwise
        per typed name — the only identity legacy attempts have.
        """
        if self.max_attempts_per_student is None:
            return True
        attempts = self.attempts.exclude(status=AttemptStatus.EXPIRED)
        if student is not None:
            attempts = attempts.filter(student=student)
        else:
            attempts = attempts.filter(student_name=student_name)
        return attempts.count() < self.max_attempts_per_student

    def deactivate(self) -> None:
        """Exam деактивируется полностью; training только получает status=finished."""
        self.status = SessionStatus.FINISHED
        if self.is_exam:
            self.is_active = False
        self.save(update_fields=["status", "is_active"])


# ---------------------------------------------------------------------------
# StudentAttempt / Answer
# ---------------------------------------------------------------------------

class StudentAttempt(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session = models.ForeignKey(
        TestSession,
        on_delete=models.CASCADE,
        related_name="attempts",
        verbose_name="Сессия",
    )
    student = models.ForeignKey(
        "academy.Student",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="test_attempts",
        verbose_name="Студент",
        help_text="Студент LMS. Пусто у попыток из старой системы, ещё не сопоставленных со студентом.",
    )
    # Historical snapshot — see the module docstring.
    student_name = models.CharField(max_length=255, verbose_name="Имя студента")
    started_at = models.DateTimeField(auto_now_add=True, verbose_name="Начата")
    finished_at = models.DateTimeField(null=True, blank=True, verbose_name="Завершена")
    score = models.FloatField(default=0.0, verbose_name="Балл (0–100)")
    status = models.CharField(
        max_length=10,
        choices=AttemptStatus.choices,
        default=AttemptStatus.ACTIVE,
        verbose_name="Статус",
        db_index=True,
    )

    class Meta:
        ordering = ["-started_at"]
        verbose_name = "Попытка прохождения"
        verbose_name_plural = "Попытки прохождения"
        indexes = [
            models.Index(fields=["session", "student_name"], name="attempt_session_student_idx"),
            models.Index(fields=["status", "started_at"], name="attempt_status_started_idx"),
            # Student profile → «Результаты тестов», newest first.
            models.Index(fields=["student", "-started_at"], name="attempt_student_started_idx"),
        ]

    def __str__(self):
        return f"{self.student_name} → {self.session}"

    def save(self, *args, **kwargs):
        # Keep the snapshot filled in for LMS-linked attempts too.
        if not self.student_name and self.student_id is not None:
            self.student_name = str(self.student)
            update_fields = kwargs.get("update_fields")
            if update_fields is not None:
                kwargs["update_fields"] = {*update_fields, "student_name"}
        super().save(*args, **kwargs)

    @property
    def is_finished(self) -> bool:
        return self.status == AttemptStatus.FINISHED

    @property
    def duration_seconds(self) -> float | None:
        if self.finished_at:
            return (self.finished_at - self.started_at).total_seconds()
        return None

    def _recalculate_score(self) -> None:
        """score = correct / TOTAL_QUESTIONS · 100 (unchanged from the legacy app)."""
        from .services.question_selector import TOTAL_QUESTIONS

        answers = list(self.answers.all())
        gradable = [a for a in answers if a.is_correct is not None]
        if not gradable:
            self.score = 0.0
            return
        correct = sum(1 for a in gradable if a.is_correct)
        self.score = round((correct / TOTAL_QUESTIONS) * 100, 2)

    def finish(self) -> None:
        if self.is_finished:
            raise ValidationError("Attempt already finished.")
        self.finished_at = timezone.now()
        self.status = AttemptStatus.FINISHED
        self._recalculate_score()
        self.save(update_fields=["finished_at", "status", "score"])

    def expire(self) -> None:
        """Принудительно истекает попытка (например, по таймауту сессии)."""
        if self.is_finished:
            return
        self.status = AttemptStatus.EXPIRED
        self.save(update_fields=["status"])


class Answer(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    attempt = models.ForeignKey(
        StudentAttempt,
        on_delete=models.CASCADE,
        related_name="answers",
        verbose_name="Попытка",
    )
    question = models.ForeignKey(
        Question,
        on_delete=models.CASCADE,
        related_name="answers",
        verbose_name="Вопрос",
    )
    answer_text = models.TextField(blank=True, verbose_name="Текстовый ответ")
    selected_options = models.JSONField(default=list, verbose_name="Выбранные варианты (UUID)")
    is_correct = models.BooleanField(null=True, blank=True, verbose_name="Верно?")

    grading_status = models.CharField(
        max_length=15,
        choices=GradingStatus.choices,
        default=GradingStatus.PENDING,
        verbose_name="Статус проверки",
        db_index=True,
    )

    # Legacy AI fields — kept for rows graded by the old checker.
    ai_grade = models.FloatField(null=True, blank=True, verbose_name="Оценка AI (0–10)")
    ai_feedback = models.TextField(blank=True, verbose_name="Комментарий AI")

    ai_score = models.FloatField(null=True, blank=True, verbose_name="Балл AI (0–10)")
    ai_confidence = models.FloatField(null=True, blank=True, verbose_name="Уверенность AI (0–1)")
    ai_suggestion = models.TextField(blank=True, verbose_name="Подсказка AI")

    answered_at = models.DateTimeField(auto_now_add=True, verbose_name="Отвечено")

    class Meta:
        ordering = ["answered_at"]
        verbose_name = "Ответ пользователя"
        verbose_name_plural = "Ответы пользователей"
        indexes = [
            models.Index(fields=["attempt", "question"], name="answer_attempt_question_idx"),
            models.Index(fields=["grading_status"], name="answer_grading_status_idx"),
            models.Index(fields=["grading_status", "answered_at"], name="answer_grading_status_time_idx"),
        ]
        constraints = [
            models.UniqueConstraint(fields=["attempt", "question"], name="unique_answer_per_attempt_question"),
        ]

    def __str__(self):
        return f"{self.attempt.student_name} → Q:{self.question_id}"

    def mark_auto_graded(self, is_correct: bool) -> None:
        self.is_correct = is_correct
        self.grading_status = GradingStatus.AUTO
        self.save(update_fields=["is_correct", "grading_status"])

    def mark_ai_graded(self, grade: float, feedback: str) -> None:
        self.ai_grade = grade
        self.ai_feedback = feedback
        self.is_correct = grade >= 5.0
        self.grading_status = GradingStatus.DONE
        self.save(update_fields=["ai_grade", "ai_feedback", "is_correct", "grading_status"])

    def mark_manual_graded(self, is_correct: bool) -> None:
        self.is_correct = is_correct
        self.grading_status = GradingStatus.MANUAL
        self.save(update_fields=["is_correct", "grading_status"])
