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

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator, URLValidator
from django.db import IntegrityError, models, transaction
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
    TYPESCRIPT = "typescript", "TypeScript"
    HTML = "html", "HTML"
    CSS = "css", "CSS"
    NONE = "", "—"


class TestLevel(models.TextChoices):
    """Test.level — same stored values as DifficultyLevel (legacy rows keep
    working), labelled the way the LMS describes a whole test."""

    EASY = "easy", "Начальный"
    MEDIUM = "medium", "Средний"
    HARD = "hard", "Продвинутый"


class TestStatus(models.TextChoices):
    DRAFT = "draft", "Черновик"
    ACTIVE = "active", "Активен"
    ARCHIVED = "archived", "Архив"


class AnswerMatch(models.TextChoices):
    """How a text answer is compared with the accepted answers."""

    EXACT = "exact", "Точное совпадение"
    IGNORE_CASE = "ignore_case", "Без учёта регистра"


class SessionType(models.TextChoices):
    EXAM = "exam", "Экзамен"
    TRAINING = "training", "Тренажёр"


class SessionStatus(models.TextChoices):
    """Stored state-machine status (see TestSession)."""

    CREATED = "created", "Создана"
    RUNNING = "running", "Идёт"
    PAUSED = "paused", "На паузе"
    FINISHED = "finished", "Завершена"
    EXPIRED = "expired", "Время истекло"
    CANCELLED = "cancelled", "Отменена"


class SessionPhase(models.TextChoices):
    """What the LMS shows for a session (TestSession.phase), derived from the
    stored status and the schedule — never stored itself."""

    DRAFT = "draft", "Черновик"
    SCHEDULED = "scheduled", "Запланирована"
    ACTIVE = "active", "Активна"
    FINISHED = "finished", "Завершена"
    CANCELLED = "cancelled", "Отменена"


class ParticipantStatus(models.TextChoices):
    """A student's state in a session (SessionParticipant.live_status).
    Stored: NOT_STARTED / IN_PROGRESS / COMPLETED / EXPIRED; PAUSED and
    DISCONNECTED are derived at read time from the session and the last
    heartbeat, so they never go stale."""

    NOT_STARTED = "not_started", "Не начал"
    IN_PROGRESS = "in_progress", "Проходит экзамен"
    PAUSED = "paused", "Приостановлен"
    DISCONNECTED = "disconnected", "Нет соединения"
    COMPLETED = "completed", "Завершил"
    EXPIRED = "expired", "Время истекло"


class AttemptStatus(models.TextChoices):
    ACTIVE = "active", "Активна"
    FINISHED = "finished", "Завершена"
    EXPIRED = "expired", "Просрочена"


class FinishReason(models.TextChoices):
    """Why an Exam Mode attempt ended (StudentAttempt.finish_reason)."""

    NONE = "", "—"
    SUBMITTED = "submitted", "Отправлено студентом"
    TIME_EXPIRED = "time_expired", "Время истекло"
    VIOLATIONS = "violations", "Превышен лимит нарушений"
    SESSION_CLOSED = "session_closed", "Сессия завершена"


class GradingStatus(models.TextChoices):
    PENDING = "pending", "На проверке"
    PROCESSING = "processing", "Обрабатывается"
    AUTO = "auto", "Авто"
    AI = "ai", "AI"  # legacy value, kept so old rows stay valid
    DONE = "done", "Готово"
    FAILED = "failed", "Ошибка AI"
    MANUAL = "manual", "Вручную"


# Answers still waiting for AI or a teacher — shown as «🟡 Review» (computed,
# never stored as a session/attempt status).
REVIEW_GRADING_STATUSES = (GradingStatus.PENDING, GradingStatus.PROCESSING, GradingStatus.FAILED)


# ---------------------------------------------------------------------------
# Test / Question / QuestionOption
# ---------------------------------------------------------------------------

# Images are links only: the URL is stored, nothing is uploaded or kept in
# MEDIA_ROOT. Only http(s) — never javascript:, data:, file: and the like.
IMAGE_URL_MAX_LENGTH = 1000
validate_image_url = URLValidator(
    schemes=["http", "https"],
    message="Укажите ссылку на изображение, начинающуюся с http:// или https://.",
)


def image_url_field(verbose_name: str = "Изображение (URL)"):
    return models.URLField(
        max_length=IMAGE_URL_MAX_LENGTH,
        blank=True,
        default="",
        validators=[validate_image_url],
        verbose_name=verbose_name,
        help_text="Необязательно. Ссылка на картинку (http:// или https://); файл не загружается на сервер.",
    )


class Test(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=255, unique=True, verbose_name="Название")
    description = models.TextField(blank=True, verbose_name="Описание")
    image_url = image_url_field("Изображение теста")
    subject = models.ForeignKey(
        "users.Subject",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="tests",
        verbose_name="Предмет",
        help_text="Пусто у тестов из старой системы.",
    )
    level = models.CharField(
        max_length=10,
        choices=TestLevel.choices,
        default=TestLevel.MEDIUM,
        verbose_name="Уровень",
    )
    status = models.CharField(
        max_length=10,
        choices=TestStatus.choices,
        default=TestStatus.DRAFT,
        verbose_name="Статус",
        db_index=True,
    )
    # Legacy column, kept in sync with ``status`` (== ACTIVE) by save():
    # the ported services and analytics still filter on it.
    is_active = models.BooleanField(default=False, verbose_name="Активен")

    # -- Settings (all optional: legacy tests have none of them) -------------
    time_limit_minutes = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(720)],
        verbose_name="Время прохождения, мин",
        help_text="Пусто — без ограничения времени.",
    )
    max_attempts = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(1)],
        verbose_name="Количество попыток",
        help_text="Пусто — без ограничений.",
    )
    passing_score = models.PositiveSmallIntegerField(
        default=60,
        validators=[MaxValueValidator(100)],
        verbose_name="Проходной балл, %",
    )
    questions_per_attempt = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(1)],
        verbose_name="Вопросов в попытке",
        help_text="Пусто — все вопросы теста. Иначе — случайная выборка такого размера.",
    )
    shuffle_questions = models.BooleanField(default=False, verbose_name="Перемешивать вопросы")
    shuffle_options = models.BooleanField(default=False, verbose_name="Перемешивать варианты ответа")
    show_result = models.BooleanField(default=True, verbose_name="Показывать результат")
    show_correct_answers = models.BooleanField(default=False, verbose_name="Показывать правильные ответы")
    allow_retry = models.BooleanField(default=True, verbose_name="Разрешить повторную попытку")
    available_from = models.DateTimeField(null=True, blank=True, verbose_name="Дата начала")
    available_until = models.DateTimeField(null=True, blank=True, verbose_name="Дата окончания")

    # -- Exam Mode (the exam portal: /exam/?key=… → the React exam) ----------
    # Only Exam Mode attempts read these; the legacy /exam/ form ignores them.
    require_fullscreen = models.BooleanField(
        default=False,
        verbose_name="Требовать полноэкранный режим",
        help_text="Выход из полноэкранного режима фиксируется как нарушение.",
    )
    max_tab_switches = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        default=3,
        validators=[MaxValueValidator(100)],
        verbose_name="Допустимо уходов со страницы",
        help_text="Сколько раз можно переключиться на другую вкладку; следующий уход завершает экзамен. "
        "Пусто — без лимита (уходы только фиксируются).",
    )
    track_tab_switches = models.BooleanField(
        default=True,
        verbose_name="Отслеживать уход со страницы",
        help_text="Переключение на другую вкладку фиксируется и считается нарушением.",
    )
    block_copy_paste = models.BooleanField(
        default=True,
        verbose_name="Запрет копирования и вставки",
        help_text="Copy / Paste / Cut и контекстное меню блокируются; попытки фиксируются.",
    )
    auto_submit = models.BooleanField(
        default=True,
        verbose_name="Автоотправка по истечении времени",
        help_text="Когда время вышло, сохранённые ответы отправляются на проверку. "
        "Если выключено — попытка закрывается как просроченная, без оценки.",
    )

    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Создан")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Обновлён")

    class Meta:
        ordering = ["title"]
        verbose_name = "Тест"
        verbose_name_plural = "Тесты"

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        self.is_active = self.status == TestStatus.ACTIVE
        update_fields = kwargs.get("update_fields")
        if update_fields is not None and "status" in update_fields:
            kwargs["update_fields"] = {*update_fields, "is_active"}
        super().save(*args, **kwargs)

    def clean(self):
        super().clean()
        if self.available_from and self.available_until and self.available_from >= self.available_until:
            raise ValidationError({"available_until": "Дата окончания должна быть позже даты начала."})

    @property
    def question_count(self):
        return self.questions.count()

    @property
    def effective_max_attempts(self) -> int | None:
        """Attempts one student may make; None = unlimited."""
        if not self.allow_retry:
            return 1
        return self.max_attempts

    def availability_error(self, now=None) -> str | None:
        """Why students can't take the test right now (None = they can)."""
        now = now or timezone.now()
        if self.status != TestStatus.ACTIVE:
            return "Тест не опубликован."
        if self.available_from and now < self.available_from:
            return "Тест ещё не начался."
        if self.available_until and now >= self.available_until:
            return "Срок прохождения теста истёк."
        return None


class Question(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    test = models.ForeignKey(
        Test,
        on_delete=models.CASCADE,
        related_name="questions",
        verbose_name="Тест",
    )
    text = models.TextField(verbose_name="Текст вопроса")
    image_url = image_url_field("Изображение вопроса")
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
    hint = models.TextField(blank=True, verbose_name="Подсказка")
    points = models.PositiveSmallIntegerField(
        default=1, validators=[MinValueValidator(1), MaxValueValidator(100)], verbose_name="Баллы"
    )
    is_required = models.BooleanField(default=True, verbose_name="Обязательный вопрос")
    # Text questions: accepted answers (the first is «Правильный ответ»).
    # Empty (legacy) → the answer goes to review instead of auto-grading.
    correct_answers = models.JSONField(default=list, blank=True, verbose_name="Правильные ответы")
    answer_match = models.CharField(
        max_length=12,
        choices=AnswerMatch.choices,
        default=AnswerMatch.IGNORE_CASE,
        verbose_name="Проверка ответа",
    )
    # Code questions. There is no code execution engine in the project:
    # code answers are reviewed by a teacher; the tests below are the
    # reference for that review (and for a future runner).
    starter_code = models.TextField(blank=True, verbose_name="Стартовый код")
    code_tests = models.JSONField(
        default=list, blank=True, verbose_name="Тесты к коду",
        help_text='Список {"input": ..., "expected_output": ...}.',
    )
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
    # Blank when the option is a picture only (image_url).
    text = models.CharField(max_length=1024, blank=True, verbose_name="Текст варианта")
    image_url = image_url_field("Изображение варианта")
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
        return f'{"✓" if self.is_correct else "✗"} {(self.text or self.image_url)[:60]}'

# ---------------------------------------------------------------------------
# TestSession
# ---------------------------------------------------------------------------

# Legacy default TTL. Only referenced by migrations/0001_initial.py, which
# imports _default_expires/_generate_key — both must keep existing.
SESSION_TTL_HOURS = 2


def _default_expires():
    return timezone.now() + timedelta(hours=SESSION_TTL_HOURS)


def _generate_key():
    return secrets.token_urlsafe(16)


# Short, child-friendly session keys: "PY-82X91". No 0/O/1/I/L so a key read
# off a projector can't be mistyped. 31**5 ≈ 28.6M combinations per prefix —
# a key is a *locator*, not a secret: brute force is stopped by API throttling,
# a key only works while its session is running, and every attempt is then
# bound to its own attempt token.
SESSION_KEY_ALPHABET = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"
SESSION_KEY_LENGTH = 5
SESSION_KEY_DEFAULT_PREFIX = "OK"
_KEY_GENERATION_ATTEMPTS = 10

MAX_SESSION_DURATION = timedelta(hours=12)
MAX_SESSION_EXTENSION = timedelta(hours=12)


def session_key_prefix(*sources: str) -> str:
    """First two Latin letters of the first source that has them ("Python" → "PY")."""
    for source in sources:
        letters = [ch for ch in (source or "").upper() if "A" <= ch <= "Z"]
        if len(letters) >= 2:
            return "".join(letters[:2])
    return SESSION_KEY_DEFAULT_PREFIX


def generate_session_key(prefix: str = SESSION_KEY_DEFAULT_PREFIX) -> str:
    body = "".join(secrets.choice(SESSION_KEY_ALPHABET) for _ in range(SESSION_KEY_LENGTH))
    return f"{prefix}-{body}"


def normalize_session_key(raw: str) -> str:
    """What a student typed → the stored form (keys are case-insensitive)."""
    return (raw or "").strip().upper()


class SessionTransitionError(ValidationError):
    """A session state change that the state machine does not allow."""


def teacher_session_q(teacher, prefix: str = "") -> models.Q:
    """The test sessions (exams, trainers) that belong to `teacher` — the one
    ownership rule for every trainer-facing exam list, page and result.
    `prefix` applies it through a relation (``"session__"`` for attempts).

    A session belongs to the trainer who runs it:
      * ``TestSession.teacher`` — set when the session is created (the
        creating trainer, or the group's program for the test's subject:
        apps.academy.services.trainer_assignment.group_trainer); or
      * with no ``teacher`` recorded (older sessions): the trainer of the
        group's active program (GroupTeacher) for the test's subject.

    Never «any session of a group the trainer teaches in» — a group has
    several programs and trainers (English — Aizhan, Soft Skills — Nurisa),
    and never «any session of a subject the trainer teaches» — two trainers
    can teach the same subject in different groups."""
    from apps.academy.models import GroupTeacher

    program = GroupTeacher.objects.filter(
        group=models.OuterRef(f"{prefix}group"),
        subject=models.OuterRef(f"{prefix}test__subject"),
        teacher=teacher,
        is_active=True,
    )
    return models.Q(**{f"{prefix}teacher": teacher}) | (
        models.Q(**{f"{prefix}teacher__isnull": True}) & models.Exists(program)
    )


class TestSessionQuerySet(models.QuerySet):
    def for_teacher(self, teacher):
        """Sessions that belong to `teacher` (see teacher_session_q)."""
        return self.filter(teacher_session_q(teacher))


class TestSession(models.Model):
    """One run of a Test for a Group.

    State machine (``status``)::

        created ──start──▶ running ──pause──▶ paused
                            │  ▲               │
                            │  └────resume─────┘
                            ├──finish──▶ finished ◀──finish── paused
                            └──(deadline passed)──▶ expired

    Timer. ``expires_at`` is always the deadline *as if the session kept
    running*: it is set on start (``started_at + duration``), and on resume
    it is pushed forward by exactly the time spent paused. So while paused
    the remaining time is frozen at ``expires_at - paused_at``, and nothing
    has to tick in the background. Training sessions have no duration and
    therefore no deadline.

    Expiry is lazy: a running session whose deadline has passed *is*
    expired (see ``effective_status``); the stored status catches up on the
    next transition attempt or via ``expire()`` (the periodic task in the
    Celery step). Every transition locks the row, so e.g. a teacher's pause
    and the expiry sweep can't interleave.

    ``is_active`` is a legacy column kept in sync as "not ended yet"
    (created/running/paused) because existing Testing analytics filter on it.
    It is never used to express pause.
    """

    TRANSITIONS = {
        "start": ({SessionStatus.CREATED}, SessionStatus.RUNNING),
        "pause": ({SessionStatus.RUNNING}, SessionStatus.PAUSED),
        "resume": ({SessionStatus.PAUSED}, SessionStatus.RUNNING),
        "finish": ({SessionStatus.RUNNING, SessionStatus.PAUSED}, SessionStatus.FINISHED),
        "expire": ({SessionStatus.RUNNING}, SessionStatus.EXPIRED),
        "cancel": ({SessionStatus.CREATED, SessionStatus.RUNNING, SessionStatus.PAUSED}, SessionStatus.CANCELLED),
    }
    ENDED_STATUSES = frozenset({SessionStatus.FINISHED, SessionStatus.EXPIRED, SessionStatus.CANCELLED})

    objects = TestSessionQuerySet.as_manager()

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
    # The LMS account that created the session through the LMS (e.g. the Team
    # Lead, who has no Teacher profile). A Team Lead may start only sessions
    # they created — see apps.testing.teacher_api.
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_test_sessions",
        verbose_name="Создал",
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
        blank=True,
        verbose_name="Ключ сессии",
        help_text="Генерируется автоматически, напр. PY-82X91.",
        db_index=True,
    )
    status = models.CharField(
        max_length=10,
        choices=SessionStatus.choices,
        default=SessionStatus.CREATED,
        verbose_name="Статус",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Создана")

    # -- Timer ---------------------------------------------------------------
    duration = models.DurationField(
        null=True,
        blank=True,
        verbose_name="Длительность",
        help_text="Время на прохождение экзамена. Пусто у тренажёра и у старых сессий.",
    )
    started_at = models.DateTimeField(null=True, blank=True, verbose_name="Запущена")
    paused_at = models.DateTimeField(null=True, blank=True, verbose_name="На паузе с")
    ended_at = models.DateTimeField(null=True, blank=True, verbose_name="Завершена")
    expires_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Истекает",
        help_text="Дедлайн с учётом пауз. Выставляется при запуске.",
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name="Активна",
        help_text="Служебное поле: сессия ещё не завершена и не истекла.",
    )

    # -- Schedule (LMS sessions; legacy ones have none) ---------------------
    # A session with a start time is «Запланирована» until then and starts
    # by itself (sync_schedule); the end time closes it. For an exam the
    # window is also its duration.
    scheduled_start = models.DateTimeField(null=True, blank=True, verbose_name="Начало", db_index=True)
    scheduled_end = models.DateTimeField(null=True, blank=True, verbose_name="Окончание")
    time_limit_minutes = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(720)],
        verbose_name="Время на прохождение, мин",
        help_text="Пусто — как в настройках теста.",
    )

    # Public training portal (apps.training): a running training session
    # marked public is listed there and taken by name, without the key.
    is_public = models.BooleanField(
        default=False,
        db_index=True,
        verbose_name="Публичная тренировка",
        help_text="Только для тренажёра: тест доступен в публичном тренировочном портале по имени, без ключа.",
    )

    # Trainer (public training) extras — see apps.training.models.Trainer.
    course = models.ForeignKey(
        "academy.Course",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="test_sessions",
        verbose_name="Программа",
    )
    exam_url = models.URLField(
        max_length=500,
        blank=True,
        verbose_name="Ссылка на экзамен",
        help_text="Куда ведёт «Экзаменге өтүү» с этого тренажёра. Пусто — ссылка из настроек портала.",
    )

    # None = без ограничений (training); exam defaults to 1 at creation time.
    max_attempts_per_student = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        verbose_name="Макс. попыток на студента",
        help_text="Только для режима exam. Пусто = без ограничений.",
    )

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Сессия"
        verbose_name_plural = "Сессии"
        indexes = [
            models.Index(fields=["status", "is_active"], name="session_status_active_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=~models.Q(status="paused") | models.Q(paused_at__isnull=False),
                name="testsession_paused_has_paused_at",
            ),
            models.CheckConstraint(
                condition=models.Q(duration__isnull=True) | models.Q(duration__gt=timedelta(0)),
                name="testsession_duration_positive",
            ),
        ]

    def __str__(self):
        label = self.title or self.key
        return f"{self.test.title} [{self.get_session_type_display()}] / {label}"

    def save(self, *args, **kwargs):
        if self.key:
            # Normalize only on creation: legacy keys are mixed-case
            # token_urlsafe strings and must never change under a saved row.
            if self._state.adding:
                self.key = normalize_session_key(self.key)
            return super().save(*args, **kwargs)
        # Auto-generate a short key; retry on the (rare) collision, including
        # one that races in between our check and the INSERT.
        prefix = self._key_prefix()
        for _ in range(_KEY_GENERATION_ATTEMPTS):
            self.key = generate_session_key(prefix)
            if TestSession.objects.filter(key=self.key).exists():
                continue
            try:
                with transaction.atomic():
                    return super().save(*args, **kwargs)
            except IntegrityError:
                if not TestSession.objects.filter(key=self.key).exists():
                    raise
        raise IntegrityError("Не удалось сгенерировать уникальный ключ сессии.")

    def _key_prefix(self) -> str:
        test = self.test
        subject = test.subject.name if test.subject_id else ""
        return session_key_prefix(subject, test.title)

    def clean(self):
        super().clean()
        errors = {}
        if self.lesson_id is not None:
            if self.group_id is None:
                errors["group"] = "Укажите группу: урок выбирается внутри группы."
            elif self.lesson.group_id != self.group_id:
                errors["lesson"] = "Урок не принадлежит выбранной группе."
        if self.scheduled_start and self.scheduled_end:
            if self.scheduled_end <= self.scheduled_start:
                errors["scheduled_end"] = "Время окончания должно быть позже начала."
            elif self.is_exam and self.status == SessionStatus.CREATED:
                # The scheduled window is the exam's duration.
                self.duration = self.scheduled_end - self.scheduled_start
        elif self.scheduled_end and not self.scheduled_start:
            errors["scheduled_start"] = "Укажите время начала."
        if self.duration is not None:
            if self.is_training:
                errors["duration"] = "У тренажёра нет ограничения по времени."
            elif not timedelta(0) < self.duration <= MAX_SESSION_DURATION:
                errors["duration"] = "Длительность должна быть больше 0 и не больше 12 часов."
        elif self.is_exam and self._state.adding:
            errors["duration"] = "Укажите длительность экзамена."
        if errors:
            raise ValidationError(errors)

    # -- Read-only state -----------------------------------------------------

    @property
    def is_exam(self) -> bool:
        return self.session_type == SessionType.EXAM

    @property
    def is_training(self) -> bool:
        return self.session_type == SessionType.TRAINING

    def _deadline_passed(self, now) -> bool:
        # Training never expires — legacy training rows still carry the old
        # 2-hour expires_at, which the standalone app ignored for them too.
        if self.is_training:
            return False
        return self.expires_at is not None and now >= self.expires_at

    def effective_status_at(self, now) -> str:
        """Stored status, plus lazy expiry of a running session past its deadline.

        Legacy ``created`` sessions also count: the standalone app let
        students in without an explicit start and gave every session a
        2-hour ``expires_at`` at creation (new ``created`` sessions have no
        deadline until started).
        """
        if self.status in (SessionStatus.RUNNING, SessionStatus.CREATED) and self._deadline_passed(now):
            return SessionStatus.EXPIRED
        return self.status

    @property
    def effective_status(self) -> str:
        return self.effective_status_at(timezone.now())

    def phase_at(self, now) -> str:
        """Черновик / Запланирована / Активна / Завершена / Отменена."""
        status = self.effective_status_at(now)
        if status == SessionStatus.CANCELLED:
            return SessionPhase.CANCELLED
        if status in self.ENDED_STATUSES:
            return SessionPhase.FINISHED
        if status in (SessionStatus.RUNNING, SessionStatus.PAUSED):
            return SessionPhase.ACTIVE
        return SessionPhase.SCHEDULED if self.scheduled_start else SessionPhase.DRAFT

    @property
    def phase(self) -> str:
        return self.phase_at(timezone.now())

    @property
    def phase_label(self) -> str:
        return SessionPhase(self.phase).label

    @property
    def effective_time_limit_minutes(self) -> int | None:
        """Per-attempt time limit: the session's override, else the test's."""
        return self.time_limit_minutes or self.test.time_limit_minutes

    def sync_schedule(self, now=None) -> None:
        """Apply the schedule: start a scheduled session once its start time
        has come, finish a running one after its end time. Called lazily
        (lists, the student page, monitoring) — there is no background
        worker; the state machine's own rules and locking still apply."""
        now = now or timezone.now()
        try:
            if self.status == SessionStatus.CREATED and self.scheduled_start and now >= self.scheduled_start:
                if self.scheduled_end and now >= self.scheduled_end:
                    return  # the whole window passed unopened: leave it for the admin
                self.start()
            if (
                self.scheduled_end
                and now >= self.scheduled_end
                and self.status in (SessionStatus.RUNNING, SessionStatus.PAUSED)
                and self.effective_status_at(now) != SessionStatus.EXPIRED
            ):
                self.finish()
        except SessionTransitionError:
            self.refresh_from_db()

    @property
    def is_time_expired(self) -> bool:
        return self.effective_status == SessionStatus.EXPIRED

    @property
    def accepts_answers(self) -> bool:
        """Only a running session inside its deadline takes answers — never a paused one."""
        return self.effective_status == SessionStatus.RUNNING

    @property
    def is_valid(self) -> bool:
        """Legacy name used by the ported services/serializers."""
        return self.accepts_answers

    @property
    def remaining_time(self) -> timedelta | None:
        """Time left on the clock; None when the session has no time limit."""
        if self.is_training:
            return None
        if self.status == SessionStatus.CREATED and self.expires_at is None:
            return self.duration
        if self.expires_at is None:
            return None
        now = timezone.now()
        if self.effective_status_at(now) in self.ENDED_STATUSES:
            return timedelta(0)
        reference = self.paused_at if self.status == SessionStatus.PAUSED else now
        return max(self.expires_at - reference, timedelta(0))

    @property
    def active_attempt_count(self) -> int:
        return self.attempts.filter(status=AttemptStatus.ACTIVE).count()

    @property
    def needs_review(self) -> bool:
        """«🟡 Review»: some answer is still waiting for AI or a teacher."""
        return Answer.objects.filter(attempt__session=self, grading_status__in=REVIEW_GRADING_STATUSES).exists()

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

    # -- Transitions ---------------------------------------------------------

    def start(self) -> None:
        self._transition("start")

    def pause(self) -> None:
        self._transition("pause")

    def resume(self) -> None:
        self._transition("resume")

    def finish(self) -> None:
        self._transition("finish")

    def expire(self) -> None:
        self._transition("expire")

    def cancel(self) -> None:
        self._transition("cancel")

    def extend(self, delta: timedelta) -> None:
        """Add time to a not-yet-ended exam.

        created        → duration grows (the clock hasn't started yet)
        running/paused → deadline and duration grow; a paused session keeps
                         its frozen remaining time + delta
        finished       → rejected
        expired        → rejected, including a running session whose deadline
                         already passed (it is expired first) — time can't be
                         added to a session students were already cut off from
        """
        if not isinstance(delta, timedelta) or not timedelta(0) < delta <= MAX_SESSION_EXTENSION:
            raise SessionTransitionError("Продление должно быть больше 0 и не больше 12 часов.")
        self._transition("extend", delta=delta)

    def _transition(self, action: str, delta: timedelta | None = None) -> None:
        now = timezone.now()
        error = None
        with transaction.atomic():
            locked = TestSession.objects.select_for_update().get(pk=self.pk)
            stored = locked.status
            if locked.effective_status_at(now) == SessionStatus.EXPIRED and stored != SessionStatus.EXPIRED:
                # Persist lazy expiry first; it must survive even if the
                # requested action is then rejected.
                locked._apply(SessionStatus.EXPIRED, now)
                locked.save()
                stored = locked.status
            if action == "expire" and stored == SessionStatus.EXPIRED:
                pass  # already expired (just now or earlier) — idempotent
            elif action == "extend":
                error = locked._apply_extend(delta, stored)
                if error is None:
                    locked.save()
            else:
                allowed_from, target = self.TRANSITIONS[action]
                if stored not in allowed_from:
                    error = self._rejection(action, stored)
                else:
                    locked._apply(target, now)
                    locked.save()
        self.refresh_from_db()
        if error:
            raise SessionTransitionError(error)

    def _apply(self, target: str, now) -> None:
        if target == SessionStatus.RUNNING and self.status == SessionStatus.CREATED:
            self.started_at = now
            if self.duration is not None:
                self.expires_at = now + self.duration
            if self.is_exam and self.scheduled_end and self.scheduled_end > now:
                # A scheduled exam closes at its end time, whenever it opened.
                self.expires_at = self.scheduled_end
        elif target == SessionStatus.RUNNING and self.status == SessionStatus.PAUSED:
            if self.expires_at is not None:
                self.expires_at += now - self.paused_at
            self.paused_at = None
        elif target == SessionStatus.PAUSED:
            self.paused_at = now
        elif target in self.ENDED_STATUSES:
            self.paused_at = None
            self.ended_at = now
            self.is_active = False
        self.status = target

    def _apply_extend(self, delta: timedelta, stored: str) -> str | None:
        if stored in self.ENDED_STATUSES:
            return "Нельзя продлить завершённую или истёкшую сессию."
        if self.is_training:
            return "У тренажёра нет ограничения по времени."
        if stored == SessionStatus.CREATED and self.expires_at is None:
            self.duration = (self.duration or timedelta(0)) + delta
            return None
        if self.expires_at is None:
            return "У этой сессии нет ограничения по времени."
        self.expires_at += delta
        if self.duration is not None:
            self.duration += delta
        return None

    @staticmethod
    def _rejection(action: str, stored: str) -> str:
        labels = dict(SessionStatus.choices)
        return f"Действие «{action}» недоступно для сессии в статусе «{labels.get(stored, stored)}»."


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
    # An LMS account taking the test itself (e.g. the Team Lead checking a
    # test) — not a student. The attempt's owner: only this user may open,
    # answer or see it through the LMS. Kept out of student statistics.
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="test_attempts",
        verbose_name="Аккаунт LMS",
    )
    # Historical snapshot — see the module docstring.
    student_name = models.CharField(max_length=255, verbose_name="Имя студента")
    # Result snapshot, taken when the attempt starts (services.result_snapshot):
    # the group / teacher / subject / test title the result belongs to. A
    # student who later moves group, a teacher who is replaced or a test
    # that is renamed or re-subjected does not rewrite old results.
    group = models.ForeignKey(
        "academy.Group", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="result_attempts", verbose_name="Группа (на момент попытки)",
    )
    teacher = models.ForeignKey(
        "users.Teacher", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="result_attempts", verbose_name="Тренер (на момент попытки)",
    )
    subject = models.ForeignKey(
        "users.Subject", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="result_attempts", verbose_name="Предмет (на момент попытки)",
    )
    test_title = models.CharField(max_length=255, blank=True, verbose_name="Тест (на момент попытки)")
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
    # The questions this attempt shows, in display order (set when the
    # attempt starts). Empty for legacy attempts, which keep the legacy
    # score formula — see _recalculate_score().
    question_ids = models.JSONField(default=list, blank=True, verbose_name="Вопросы попытки")

    # -- Exam Mode (the exam portal) — see services/exam_portal.py ----------
    exam_mode = models.BooleanField(
        default=False, db_index=True, verbose_name="Exam Mode",
        help_text="Попытка идёт в экзаменационном портале (таймер сервера, автосохранение, нарушения).",
    )
    # The attempt's own time-limit deadline (started_at + limit), stored when
    # it starts. The session's deadline still caps it — attempt_deadline().
    expires_at = models.DateTimeField(null=True, blank=True, verbose_name="Истекает")
    # Autosaved answers {question_id: {"text": str, "options": [id, ...]}},
    # graded into Answer rows only when the attempt is finished.
    draft_answers = models.JSONField(default=dict, blank=True, verbose_name="Черновик ответов")
    draft_saved_at = models.DateTimeField(null=True, blank=True, verbose_name="Черновик сохранён")
    # Where the student is in the attempt (the shared test UI restores it
    # after a reload). position_seq is the page's clock at the move: an older
    # request arriving late never overwrites a newer position.
    current_question_id = models.UUIDField(null=True, blank=True, verbose_name="Текущий вопрос")
    position_seq = models.PositiveBigIntegerField(default=0, editable=False)
    tab_switch_count = models.PositiveIntegerField(default=0, verbose_name="Уходов со страницы")
    violation_count = models.PositiveIntegerField(default=0, verbose_name="Нарушений")
    finish_reason = models.CharField(
        max_length=20, choices=FinishReason.choices, default=FinishReason.NONE, blank=True,
        verbose_name="Причина завершения",
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
            models.Index(fields=["group", "status", "finished_at"], name="attempt_group_result_idx"),
            models.Index(fields=["teacher", "status", "finished_at"], name="attempt_teacher_result_idx"),
        ]

    def __str__(self):
        return f"{self.student_name} → {self.session}"

    def save(self, *args, **kwargs):
        if self._state.adding:
            from .services.result_snapshot import fill_snapshot

            fill_snapshot(self)
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
    def can_answer(self) -> bool:
        """Answers are accepted only while the attempt is active and its session is running."""
        return self.status == AttemptStatus.ACTIVE and self.session.accepts_answers

    @property
    def needs_review(self) -> bool:
        return self.answers.filter(grading_status__in=REVIEW_GRADING_STATUSES).exists()

    @property
    def duration_seconds(self) -> float | None:
        if self.finished_at:
            return (self.finished_at - self.started_at).total_seconds()
        return None

    def _recalculate_score(self) -> None:
        """Attempts with their own question list: earned points / possible
        points · 100 (services.grading). Legacy attempts: correct /
        TOTAL_QUESTIONS · 100, unchanged from the legacy app."""
        if self.question_ids:
            from .services.grading import attempt_score

            self.score = attempt_score(self).percent
            return

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


class TestResultManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(status=AttemptStatus.FINISHED, student__isnull=False)


class TestResult(StudentAttempt):
    """«Результаты тестов» in the admin: finished attempts of LMS students.
    A proxy — a result is the attempt itself, no separate table."""

    objects = TestResultManager()

    class Meta:
        proxy = True
        verbose_name = "Результат теста"
        verbose_name_plural = "Результаты тестов"


# A student in progress whose page hasn't reported for this long is shown
# as «Нет соединения» (the student page sends a heartbeat every 15 s).
PARTICIPANT_STALE_AFTER = timedelta(seconds=45)


class SessionParticipant(models.Model):
    """One student invited to a session (the session's roster) and their
    live state in it — what the teacher monitors. Results themselves stay
    in StudentAttempt/Answer; ``attempt`` points at the current/latest one.

    Updated by services.participants when the student starts, reports
    progress, leaves the page and finishes.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session = models.ForeignKey(
        TestSession, on_delete=models.CASCADE, related_name="participants", verbose_name="Сессия",
    )
    student = models.ForeignKey(
        "academy.Student", on_delete=models.CASCADE, related_name="test_participations", verbose_name="Студент",
    )
    attempt = models.ForeignKey(
        StudentAttempt, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="participations", verbose_name="Текущая попытка",
    )
    status = models.CharField(
        max_length=15, choices=ParticipantStatus.choices, default=ParticipantStatus.NOT_STARTED,
        verbose_name="Статус", db_index=True,
    )
    current_question = models.PositiveSmallIntegerField(default=0, verbose_name="Текущий вопрос")
    answered_count = models.PositiveSmallIntegerField(default=0, verbose_name="Отвечено вопросов")
    question_total = models.PositiveSmallIntegerField(default=0, verbose_name="Вопросов в попытке")
    started_at = models.DateTimeField(null=True, blank=True, verbose_name="Начал")
    finished_at = models.DateTimeField(null=True, blank=True, verbose_name="Завершил")
    last_seen_at = models.DateTimeField(null=True, blank=True, verbose_name="Последняя активность")
    left_at = models.DateTimeField(null=True, blank=True, verbose_name="Закрыл страницу")
    score = models.FloatField(null=True, blank=True, verbose_name="Балл (0–100)")

    class Meta:
        ordering = ["student__first_name", "student__last_name"]
        verbose_name = "Участник сессии"
        verbose_name_plural = "Участники сессии"
        constraints = [
            models.UniqueConstraint(fields=["session", "student"], name="unique_participant_per_session"),
        ]

    def __str__(self):
        return f"{self.student} → {self.session}"

    def live_status_at(self, now) -> str:
        if self.status != ParticipantStatus.IN_PROGRESS:
            return self.status
        session_status = self.session.effective_status_at(now)
        if session_status == SessionStatus.PAUSED:
            return ParticipantStatus.PAUSED
        if session_status in TestSession.ENDED_STATUSES:
            return ParticipantStatus.EXPIRED
        limit = self.session.effective_time_limit_minutes
        if limit and self.started_at and now > self.started_at + timedelta(minutes=limit, seconds=90):
            return ParticipantStatus.EXPIRED
        if self.left_at and (self.last_seen_at is None or self.left_at >= self.last_seen_at):
            return ParticipantStatus.DISCONNECTED
        if self.last_seen_at and now - self.last_seen_at > PARTICIPANT_STALE_AFTER:
            return ParticipantStatus.DISCONNECTED
        return ParticipantStatus.IN_PROGRESS

    @property
    def live_status(self) -> str:
        return self.live_status_at(timezone.now())

    @property
    def live_status_label(self) -> str:
        return ParticipantStatus(self.live_status).label

    @property
    def duration_seconds(self) -> int | None:
        if not self.started_at:
            return None
        end = self.finished_at or (timezone.now() if self.status == ParticipantStatus.IN_PROGRESS else None)
        return int((end - self.started_at).total_seconds()) if end else None


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


# ---------------------------------------------------------------------------
# Exam Mode event log
# ---------------------------------------------------------------------------

class ExamEventType(models.TextChoices):
    EXAM_STARTED = "EXAM_STARTED", "Экзамен начат"
    ANSWER_SAVED = "ANSWER_SAVED", "Ответ сохранён"
    TAB_SWITCH = "TAB_SWITCH", "Уход со страницы"
    FULLSCREEN_EXIT = "FULLSCREEN_EXIT", "Выход из полноэкранного режима"
    COPY_ATTEMPT = "COPY_ATTEMPT", "Попытка копирования"
    PASTE_ATTEMPT = "PASTE_ATTEMPT", "Попытка вставки"
    CUT_ATTEMPT = "CUT_ATTEMPT", "Попытка вырезания"
    CONTEXT_MENU_ATTEMPT = "CONTEXT_MENU_ATTEMPT", "Контекстное меню"
    DEVTOOLS_ATTEMPT = "DEVTOOLS_ATTEMPT", "Горячие клавиши DevTools"
    PAGE_LEAVE = "PAGE_LEAVE", "Страница закрыта"
    EXAM_SUBMITTED = "EXAM_SUBMITTED", "Экзамен отправлен"
    TIME_EXPIRED = "TIME_EXPIRED", "Время истекло"
    EXAM_TERMINATED = "EXAM_TERMINATED", "Экзамен завершён из-за нарушений"
    TRAINING_STARTED = "TRAINING_STARTED", "Тренировка начата"
    TRAINING_SUBMITTED = "TRAINING_SUBMITTED", "Тренировка отправлена"
    TAB_RETURN = "TAB_RETURN", "Возврат на страницу"
    FULLSCREEN_ENTER = "FULLSCREEN_ENTER", "Вход в полноэкранный режим"


# Reported by the Exam Mode page and counted as violations
# (StudentAttempt.violation_count) — see services/exam_portal.py.
EXAM_VIOLATION_EVENTS = frozenset({
    ExamEventType.TAB_SWITCH,
    ExamEventType.FULLSCREEN_EXIT,
    ExamEventType.COPY_ATTEMPT,
    ExamEventType.PASTE_ATTEMPT,
    ExamEventType.CUT_ATTEMPT,
    ExamEventType.CONTEXT_MENU_ATTEMPT,
    ExamEventType.DEVTOOLS_ATTEMPT,
})


class ExamAttemptEvent(models.Model):
    """Append-only audit log of an Exam Mode attempt. No answers and no
    personal data beyond what the request itself carries (user agent and,
    unless EXAM_EVENTS_STORE_IP is off, the IP address)."""

    attempt = models.ForeignKey(
        StudentAttempt, on_delete=models.CASCADE, related_name="events", verbose_name="Попытка",
    )
    event_type = models.CharField(max_length=24, choices=ExamEventType.choices, verbose_name="Событие")
    timestamp = models.DateTimeField(default=timezone.now, verbose_name="Время")
    metadata = models.JSONField(default=dict, blank=True, verbose_name="Детали")
    user_agent = models.CharField(max_length=255, blank=True, verbose_name="Браузер")
    ip_address = models.GenericIPAddressField(null=True, blank=True, verbose_name="IP-адрес")

    class Meta:
        ordering = ["timestamp", "id"]
        verbose_name = "Событие экзамена"
        verbose_name_plural = "События экзамена"
        indexes = [
            models.Index(fields=["attempt", "timestamp"], name="exam_event_attempt_time_idx"),
        ]

    def __str__(self):
        return f"{self.get_event_type_display()} · {self.attempt_id}"

    @property
    def severity(self) -> str:
        """danger / warning / info — how the admin event log colours it."""
        if self.event_type in EXAM_VIOLATION_EVENTS or self.event_type == ExamEventType.EXAM_TERMINATED:
            return "danger"
        if self.event_type in (ExamEventType.PAGE_LEAVE, ExamEventType.TIME_EXPIRED):
            return "warning"
        return "info"
