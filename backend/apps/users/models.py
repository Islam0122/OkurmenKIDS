from django.contrib.auth.models import AbstractUser
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class User(AbstractUser):
    class Role(models.TextChoices):
        ADMIN = "admin", "Администратор"
        TEACHER = "teacher", "Тренер"

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

    is_email_verified = models.BooleanField(
        default=False,
        verbose_name="Email подтверждён",
        help_text="Подтверждён ли адрес электронной почты пользователя.",
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

    class Meta:
        verbose_name = "Пользователь"
        verbose_name_plural = "Пользователи"
        ordering = ["-created_at"]

    def __str__(self):
        return self.get_full_name() or self.username

    @property
    def is_teacher(self):
        return self.role == self.Role.TEACHER

    @property
    def is_admin(self):
        return self.role == self.Role.ADMIN


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