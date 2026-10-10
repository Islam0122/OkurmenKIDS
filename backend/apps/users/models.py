from django.contrib.auth.models import AbstractUser, UserManager
from django.core.validators import MaxValueValidator, MinValueValidator, RegexValidator
from django.db import models


class CustomUserManager(UserManager):
    """Ensures `python manage.py createsuperuser` produces a correct ADMIN.

    Without this, `role` would fall back to its model default (TEACHER) for
    any superuser created via the standard command, and the account would
    also be blocked at login by the Trainer verification checks. Superusers
    are trusted admin accounts from the moment they're created.
    """

    def create_superuser(self, username, email=None, password=None, **extra_fields):
        extra_fields.setdefault("role", User.Role.ADMIN)
        extra_fields.setdefault("is_verified", True)
        return super().create_superuser(username, email, password, **extra_fields)


class User(AbstractUser):
    class Role(models.TextChoices):
        ADMIN = "admin", "Администратор"
        TEACHER = "teacher", "Тренер"
        # Руководитель тренеров: видит всю академию (тренеры, группы,
        # студенты, занятия, KPI, аналитика, отчёты), но только читает —
        # см. apps.users.permissions.can_view_academy / IsTeamLeadReadOnly.
        TEAM_LEAD = "team_lead", "Team Lead"
        # Операционная роль академии: группы, студенты (добавление, перевод,
        # деактивация/активация), расписание, посещаемость, стипендии,
        # опросы — только через Assistant Workspace (/assistant/ во фронтенде,
        # /api/v1/assistant/ в API). Никаких KPI, HR, ролей и Django admin —
        # см. apps.users.permissions.is_assistant / IsAdminOrAssistant.
        ASSISTANT = "assistant", "Ассистент"
        # Бухгалтерия: расчёт зарплат, выплаты, платежи студентов, отчёты —
        # только через раздел бухгалтерии (/accounting/ во фронтенде,
        # /api/v1/accounting/ в API). Не утверждает начисления, не меняет
        # роли и системные настройки — см. apps.accounting.permissions.
        ACCOUNTANT = "accountant", "Бухгалтер"
        # Директор: сводная финансовая панель, утверждение/возврат начислений,
        # отчёты и журнал изменений бухгалтерии.
        DIRECTOR = "director", "Директор"

    username = models.CharField(
        max_length=150,
        unique=True,
        verbose_name="Логин",
        help_text="Уникальный логин пользователя для входа в систему.",
    )

    email = models.EmailField(
        unique=True,
        verbose_name="Электронная почта",
        help_text="Уникальный адрес электронной почты пользователя.",
    )

    first_name = models.CharField(
        max_length=100,
        verbose_name="Имя",
        help_text="Имя пользователя.",
    )

    last_name = models.CharField(
        max_length=100,
        blank=True,
        verbose_name="Фамилия",
        help_text="Фамилия пользователя.",
    )

    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.TEACHER,
        db_index=True,
        verbose_name="Роль",
        help_text="Определяет права доступа пользователя в системе.",
    )

    is_verified = models.BooleanField(
        default=False,
        verbose_name="Аккаунт подтверждён",
        help_text="Подтверждён ли аккаунт администратором.",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Дата создания",
        help_text="Дата и время создания аккаунта.",
    )

    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="Дата обновления",
        help_text="Дата и время последнего изменения аккаунта.",
    )

    objects = CustomUserManager()

    # Roles that work only through the LMS, never through Django admin.
    LMS_ONLY_ROLES = (Role.TEAM_LEAD, Role.ASSISTANT, Role.ACCOUNTANT, Role.DIRECTOR)

    class Meta:
        verbose_name = "Пользователь"
        verbose_name_plural = "Пользователи"
        ordering = ["-created_at"]

    def __str__(self):
        return self.get_full_name() or self.username

    def save(self, *args, **kwargs):
        # Team Lead works only through the LMS (frontend/API), read-only: it
        # is never a Django superuser nor a Django admin (staff) account,
        # whatever form or script saved it. Access itself comes from the role
        # (apps.users.permissions), never from Django permissions. The same
        # holds for an Assistant: it works only through the Assistant
        # Workspace, never through Django admin.
        if self.role in self.LMS_ONLY_ROLES:
            self.is_superuser = False
            self.is_staff = False
            update_fields = kwargs.get("update_fields")
            if update_fields is not None:
                kwargs["update_fields"] = {*update_fields, "is_superuser", "is_staff"}
        super().save(*args, **kwargs)

    @property
    def is_teacher(self):
        return self.role == self.Role.TEACHER

    @property
    def is_admin(self):
        return self.role == self.Role.ADMIN

    @property
    def is_team_lead(self):
        return self.role == self.Role.TEAM_LEAD

    @property
    def is_assistant(self):
        return self.role == self.Role.ASSISTANT

    @property
    def is_accountant(self):
        return self.role == self.Role.ACCOUNTANT

    @property
    def is_director(self):
        return self.role == self.Role.DIRECTOR


class Subject(models.Model):
    name = models.CharField(
        max_length=100,
        unique=True,
        verbose_name="Название предмета",
        help_text=(
            "Название направления или предмета. "
            "Например: Python, Frontend, Backend, JavaScript."
        ),
    )

    description = models.TextField(
        blank=True,
        verbose_name="Описание",
        help_text="Краткое описание предмета.",
    )

    is_active = models.BooleanField(
        default=True,
        db_index=True,
        verbose_name="Активный",
        help_text="Можно ли назначать этот предмет новым группам.",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Дата создания",
        help_text="Дата и время создания предмета.",
    )

    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="Дата обновления",
        help_text="Дата и время последнего изменения предмета.",
    )

    class Meta:
        verbose_name = "Предмет"
        verbose_name_plural = "Предметы"
        ordering = ["name"]

    def __str__(self):
        return self.name


class Teacher(models.Model):
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="teacher_profile",
        verbose_name="Аккаунт",
        help_text="Аккаунт пользователя, связанный с профилем тренера.",
    )

    subjects = models.ManyToManyField(
        Subject,
        blank=True,
        related_name="teachers",
        verbose_name="Предметы",
        help_text="Предметы, которые преподаёт тренер.",
    )

    phone = models.CharField(
        max_length=30,
        blank=True,
        verbose_name="Номер телефона",
        help_text="Контактный номер телефона тренера.",
    )

    image = models.ImageField(
        upload_to="teachers/",
        blank=True,
        null=True,
        verbose_name="Фотография",
        help_text="Фотография профиля тренера.",
    )

    position = models.CharField(
        max_length=100,
        default="Тренер",
        verbose_name="Должность",
        help_text="Должность тренера в OkurmenKIDS.",
    )

    experience_years = models.PositiveSmallIntegerField(
        default=0,
        validators=[
            MinValueValidator(0),
            MaxValueValidator(60),
        ],
        verbose_name="Опыт работы",
        help_text="Количество лет преподавательского опыта.",
    )

    bio = models.TextField(
        blank=True,
        verbose_name="О тренере",
        help_text="Краткая информация о тренере.",
    )

    hire_date = models.DateField(
        null=True,
        blank=True,
        verbose_name="Дата начала работы",
        help_text="Дата начала работы тренера в OkurmenKIDS.",
    )

    is_active = models.BooleanField(
        default=True,
        db_index=True,
        verbose_name="Активный",
        help_text="Может ли тренер работать с группами.",
    )

    color = models.CharField(
        max_length=7,
        blank=True,
        validators=[RegexValidator(r"^#[0-9a-fA-F]{6}$", "Цвет в формате #RRGGBB.")],
        verbose_name="Цвет в расписании",
        help_text=(
            "Постоянный цвет тренера в расписании (#RRGGBB). Пусто — назначается "
            "автоматически из палитры при сохранении."
        ),
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Дата создания",
        help_text="Дата и время создания профиля.",
    )

    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="Дата обновления",
        help_text="Дата и время последнего изменения профиля.",
    )

    class Meta:
        verbose_name = "Тренер"
        verbose_name_plural = "Тренеры"
        ordering = ["-created_at"]

    def __str__(self):
        return self.user.get_full_name() or self.user.username

    def save(self, *args, **kwargs):
        # A trainer keeps one color for good: it is picked once (the palette
        # color fewest trainers use) and never re-rolled, so the schedule
        # looks the same on every page load.
        if not self.color:
            self.color = next_trainer_color(exclude_pk=self.pk)
            update_fields = kwargs.get("update_fields")
            if update_fields is not None:
                kwargs["update_fields"] = {*update_fields, "color"}
        super().save(*args, **kwargs)


# Distinct, calm colors that stay readable as a card's accent stripe and as a
# light tint behind dark text (see the schedule board on the frontend).
TRAINER_PALETTE = (
    "#2563EB",  # blue
    "#D97706",  # amber
    "#7C3AED",  # violet
    "#DB2777",  # pink
    "#0891B2",  # cyan
    "#16A34A",  # green
    "#DC2626",  # red
    "#4F46E5",  # indigo
    "#C2410C",  # orange
    "#0D9488",  # teal
    "#9333EA",  # purple
    "#65A30D",  # lime
    "#BE123C",  # rose
    "#0369A1",  # sky
    "#A16207",  # ochre
    "#475569",  # slate
)


def next_trainer_color(exclude_pk=None) -> str:
    """The palette color the fewest trainers already have (palette order
    breaks ties) — so the first 16 trainers all get different colors and
    later ones spread evenly."""
    used = Teacher.objects.exclude(color="")
    if exclude_pk is not None:
        used = used.exclude(pk=exclude_pk)
    counts = {color.upper(): 0 for color in TRAINER_PALETTE}
    for color in used.values_list("color", flat=True):
        if color.upper() in counts:
            counts[color.upper()] += 1
    return min(TRAINER_PALETTE, key=lambda color: counts[color])