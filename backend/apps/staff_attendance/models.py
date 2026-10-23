"""Учёт прихода и ухода сотрудников по постоянному QR-коду офиса.

Не путать с `academy.Attendance` — это посещаемость студентов на занятиях.
Здесь — рабочее время сотрудников LMS (тренеры, ассистенты, бухгалтерия,
администрация, руководство). Отдельной таблицы сотрудников нет: сотрудник —
это существующий `users.User`, его категория — `User.role`.

Модели:

* AttendanceSettings — одна запись (pk=1): часовой пояс офиса, допустимая
  погрешность GPS, общее расписание, льготные минуты, отслеживаемые роли,
  режим проверки офисной сети.
* AttendanceLocation — офис: координаты центра геозоны, радиус и постоянный
  публичный код, который зашит в QR-код (не секрет и не персональные данные).
* AttendanceWorkSchedule — личное расписание сотрудника поверх общего.
* AttendanceSession — рабочая сессия «приход → уход». У сотрудника не может
  быть двух открытых сессий одновременно (частичный уникальный индекс).
* AttendanceEvent — неизменяемый журнал отметок (что и когда сервер принял).
* AttendanceAdjustment — ручное исправление сессии: было/стало, причина,
  кто и когда. Исходные события при этом не удаляются.
* AttendanceAdminLog — журнал изменений настроек и локаций.

Координаты сотрудника не хранятся: только расстояние до центра геозоны и
заявленная браузером точность в момент отметки.
"""
from __future__ import annotations

import secrets
from datetime import time
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import F, Q
from django.utils import timezone as dj_timezone


ALL_WEEKDAYS = (0, 1, 2, 3, 4, 5, 6)  # Пн = 0 … Вс = 6, как date.weekday()


def default_work_days() -> list[int]:
    return [0, 1, 2, 3, 4, 5]


def default_tracked_roles() -> list[str]:
    from apps.users.models import User

    return [value for value, _ in User.Role.choices]


def new_location_code() -> str:
    # Публичный идентификатор офиса для QR-ссылки. Не секрет: QR-код висит на
    # стене, поэтому присутствие подтверждают геозона и серверные проверки.
    return secrets.token_urlsafe(12)


def validate_timezone(value: str) -> None:
    try:
        ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ValidationError(f"Неизвестный часовой пояс: {value}") from exc


def validate_weekdays(value) -> None:
    if not isinstance(value, list) or any(day not in ALL_WEEKDAYS for day in value):
        raise ValidationError("Рабочие дни — список чисел 0…6 (0 — понедельник).")


class AttendanceSettings(models.Model):
    """Общие настройки модуля. Всегда одна запись — см. `load()`."""

    timezone = models.CharField(
        max_length=64, default="Asia/Bishkek", validators=[validate_timezone],
        verbose_name="Часовой пояс офиса",
    )
    max_gps_accuracy_m = models.PositiveIntegerField(
        default=100, validators=[MinValueValidator(5), MaxValueValidator(1000)],
        verbose_name="Максимальная погрешность GPS, м",
        help_text="Отметка отклоняется, если браузер сообщает погрешность больше этой.",
    )
    work_start = models.TimeField(default=time(9, 0), verbose_name="Начало рабочего дня")
    work_end = models.TimeField(default=time(18, 0), verbose_name="Окончание рабочего дня")
    work_days = models.JSONField(
        default=default_work_days, validators=[validate_weekdays], verbose_name="Рабочие дни недели",
        help_text="0 — понедельник … 6 — воскресенье.",
    )
    late_grace_minutes = models.PositiveSmallIntegerField(
        default=10, validators=[MaxValueValidator(240)], verbose_name="Льготное время опоздания, мин",
    )
    tracked_roles = models.JSONField(
        default=default_tracked_roles, verbose_name="Роли, которые отмечают приход и уход",
    )
    teacher_schedule_from_lessons = models.BooleanField(
        default=False, verbose_name="Тренеры: начало дня по первому занятию",
        help_text=(
            "Если включено, ожидаемый приход тренера — начало его первого занятия в этот день "
            "(минус «прийти заранее»); в день без занятий опоздание и «нет прихода» не считаются."
        ),
    )
    teacher_arrival_before_lesson_minutes = models.PositiveSmallIntegerField(
        default=0, validators=[MaxValueValidator(240)], verbose_name="Тренеры: прийти до занятия за, мин",
    )
    tracking_started_on = models.DateField(
        default=dj_timezone.localdate, verbose_name="Учёт ведётся с",
        help_text="Дни до этой даты не считаются ни пропусками, ни опозданиями: учёта ещё не было.",
    )
    network_check_enabled = models.BooleanField(
        default=False, verbose_name="Проверять офисную сеть",
        help_text="Отметка принимается только с IP-адресов из списка ниже.",
    )
    office_networks = models.TextField(
        blank=True, verbose_name="Офисные сети (CIDR)",
        help_text="По одной сети в строке, например 203.0.113.0/24.",
    )
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Изменено")
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
        verbose_name="Кем изменено",
    )

    class Meta:
        verbose_name = "Настройки посещаемости сотрудников"
        verbose_name_plural = "Настройки посещаемости сотрудников"

    def __str__(self):
        return "Настройки посещаемости сотрудников"

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls) -> "AttendanceSettings":
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    @property
    def tzinfo(self) -> ZoneInfo:
        return ZoneInfo(self.timezone)

    def clean(self):
        if self.work_end <= self.work_start:
            raise ValidationError({"work_end": "Окончание рабочего дня должно быть позже начала."})
        from apps.users.models import User

        known = {value for value, _ in User.Role.choices}
        if not isinstance(self.tracked_roles, list) or not set(self.tracked_roles) <= known:
            raise ValidationError({"tracked_roles": "Неизвестная роль."})
        from .services.network import parse_networks

        parse_networks(self.office_networks)


class AttendanceLocation(models.Model):
    name = models.CharField(max_length=150, verbose_name="Название")
    address = models.CharField(max_length=255, blank=True, verbose_name="Адрес")
    code = models.CharField(
        max_length=64, unique=True, default=new_location_code, editable=False,
        verbose_name="Код для QR-ссылки",
    )
    latitude = models.FloatField(
        validators=[MinValueValidator(-90), MaxValueValidator(90)], verbose_name="Широта центра",
    )
    longitude = models.FloatField(
        validators=[MinValueValidator(-180), MaxValueValidator(180)], verbose_name="Долгота центра",
    )
    radius_m = models.PositiveIntegerField(
        default=100, validators=[MinValueValidator(10), MaxValueValidator(5000)],
        verbose_name="Радиус геозоны, м",
    )
    is_active = models.BooleanField(default=True, db_index=True, verbose_name="Активна")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Создана")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Изменена")

    class Meta:
        verbose_name = "Офис (локация отметки)"
        verbose_name_plural = "Офисы (локации отметки)"
        ordering = ["name", "id"]

    def __str__(self):
        return self.name


class AttendanceWorkSchedule(models.Model):
    """Личное расписание сотрудника. Нет записи или она выключена — действует
    общее расписание из настроек (или занятия тренера, если это включено)."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="attendance_schedule",
        verbose_name="Сотрудник",
    )
    work_start = models.TimeField(verbose_name="Начало рабочего дня")
    work_end = models.TimeField(verbose_name="Окончание рабочего дня")
    work_days = models.JSONField(default=default_work_days, validators=[validate_weekdays], verbose_name="Рабочие дни")
    late_grace_minutes = models.PositiveSmallIntegerField(
        null=True, blank=True, validators=[MaxValueValidator(240)],
        verbose_name="Льготное время, мин", help_text="Пусто — как в общих настройках.",
    )
    is_active = models.BooleanField(default=True, verbose_name="Действует")
    note = models.CharField(max_length=255, blank=True, verbose_name="Комментарий")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Изменено")
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
        verbose_name="Кем изменено",
    )

    class Meta:
        verbose_name = "Личное расписание сотрудника"
        verbose_name_plural = "Личные расписания сотрудников"

    def __str__(self):
        return f"{self.user}: {self.work_start:%H:%M}–{self.work_end:%H:%M}"

    def clean(self):
        if self.work_end <= self.work_start:
            raise ValidationError({"work_end": "Окончание рабочего дня должно быть позже начала."})


class AttendanceSession(models.Model):
    class Status(models.TextChoices):
        OPEN = "open", "На работе"
        CLOSED = "closed", "Завершена"
        # Сотрудник не отметил уход: сессия закрыта системой без времени ухода.
        MISSING_CHECKOUT = "missing_checkout", "Нет ухода"

    class Source(models.TextChoices):
        QR = "qr", "QR-код"
        MANUAL = "manual", "Вручную (администратор)"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="attendance_sessions",
        verbose_name="Сотрудник",
    )
    location = models.ForeignKey(
        AttendanceLocation, on_delete=models.PROTECT, null=True, blank=True, related_name="sessions",
        verbose_name="Офис",
    )
    work_date = models.DateField(db_index=True, verbose_name="Рабочий день (по часовому поясу офиса)")
    checked_in_at = models.DateTimeField(verbose_name="Приход")
    checked_out_at = models.DateTimeField(null=True, blank=True, verbose_name="Уход")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN, db_index=True,
                              verbose_name="Состояние")
    source = models.CharField(max_length=10, choices=Source.choices, default=Source.QR, verbose_name="Источник")
    expected_start = models.DateTimeField(null=True, blank=True, verbose_name="Ожидаемое начало")
    late_minutes = models.PositiveIntegerField(default=0, verbose_name="Опоздание, мин")
    check_in_distance_m = models.FloatField(null=True, blank=True, verbose_name="Расстояние при приходе, м")
    check_in_accuracy_m = models.FloatField(null=True, blank=True, verbose_name="Точность GPS при приходе, м")
    check_out_distance_m = models.FloatField(null=True, blank=True, verbose_name="Расстояние при уходе, м")
    check_out_accuracy_m = models.FloatField(null=True, blank=True, verbose_name="Точность GPS при уходе, м")
    is_adjusted = models.BooleanField(default=False, db_index=True, verbose_name="Исправлена вручную")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Создана")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Изменена")

    class Meta:
        verbose_name = "Рабочая сессия"
        verbose_name_plural = "Рабочие сессии"
        ordering = ["-checked_in_at", "-id"]
        indexes = [
            models.Index(fields=["user", "work_date"], name="staff_att_user_date_idx"),
            models.Index(fields=["work_date", "status"], name="staff_att_date_status_idx"),
        ]
        constraints = [
            # Главная защита от двойного прихода: даже при гонке двух запросов
            # PostgreSQL не даст создать вторую открытую сессию.
            models.UniqueConstraint(
                fields=["user"], condition=Q(status="open"), name="staff_att_one_open_session_per_user",
            ),
            models.CheckConstraint(
                condition=Q(checked_out_at__isnull=True) | Q(checked_out_at__gte=F("checked_in_at")),
                name="staff_att_checkout_after_checkin",
            ),
            models.CheckConstraint(
                condition=(
                    (Q(status="closed") & Q(checked_out_at__isnull=False))
                    | (Q(status__in=["open", "missing_checkout"]) & Q(checked_out_at__isnull=True))
                ),
                name="staff_att_status_matches_checkout",
            ),
        ]
        permissions = [
            ("view_attendance_reports", "Может просматривать отчёты посещаемости сотрудников"),
            ("adjust_attendance", "Может исправлять записи посещаемости сотрудников"),
            ("manage_attendance", "Может управлять офисами и настройками посещаемости"),
        ]

    def __str__(self):
        return f"{self.user} — {self.work_date}"

    @property
    def duration_seconds(self) -> int | None:
        if self.checked_out_at is None:
            return None
        return int((self.checked_out_at - self.checked_in_at).total_seconds())


class AttendanceEvent(models.Model):
    """Неизменяемый журнал: каждая принятая сервером отметка и каждое
    системное действие. Исправления сюда не пишутся задним числом —
    они фиксируются в AttendanceAdjustment."""

    class Kind(models.TextChoices):
        CHECK_IN = "check_in", "Приход"
        CHECK_OUT = "check_out", "Уход"
        AUTO_CLOSE = "auto_close", "Закрыта без ухода"
        MANUAL_CREATE = "manual_create", "Создана администратором"

    session = models.ForeignKey(AttendanceSession, on_delete=models.PROTECT, related_name="events",
                                verbose_name="Сессия")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="attendance_events",
                             verbose_name="Сотрудник")
    kind = models.CharField(max_length=20, choices=Kind.choices, verbose_name="Событие")
    occurred_at = models.DateTimeField(db_index=True, verbose_name="Время (сервер, UTC)")
    location = models.ForeignKey(AttendanceLocation, on_delete=models.PROTECT, null=True, blank=True,
                                 related_name="events", verbose_name="Офис")
    distance_m = models.FloatField(null=True, blank=True, verbose_name="Расстояние до центра, м")
    accuracy_m = models.FloatField(null=True, blank=True, verbose_name="Точность GPS, м")
    idempotency_key = models.UUIDField(null=True, blank=True, verbose_name="Ключ идемпотентности")
    ip_address = models.GenericIPAddressField(null=True, blank=True, verbose_name="IP-адрес")
    user_agent = models.CharField(max_length=255, blank=True, verbose_name="Браузер")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                   related_name="+", verbose_name="Кем создано (для ручных)")

    class Meta:
        verbose_name = "Событие отметки"
        verbose_name_plural = "События отметок"
        ordering = ["-occurred_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "idempotency_key"], condition=Q(idempotency_key__isnull=False),
                name="staff_att_event_idempotency",
            ),
        ]

    def __str__(self):
        return f"{self.get_kind_display()} — {self.user} — {self.occurred_at:%Y-%m-%d %H:%M}"


class AttendanceAdjustment(models.Model):
    class Action(models.TextChoices):
        CREATE = "create", "Создание записи"
        UPDATE = "update", "Исправление записи"

    session = models.ForeignKey(AttendanceSession, on_delete=models.PROTECT, related_name="adjustments",
                                verbose_name="Сессия")
    action = models.CharField(max_length=10, choices=Action.choices, default=Action.UPDATE, verbose_name="Действие")
    old_values = models.JSONField(default=dict, verbose_name="Было")
    new_values = models.JSONField(default=dict, verbose_name="Стало")
    reason = models.TextField(verbose_name="Причина")
    adjusted_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+",
                                    verbose_name="Кто исправил")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True, verbose_name="Когда")

    class Meta:
        verbose_name = "Исправление посещаемости"
        verbose_name_plural = "Исправления посещаемости"
        ordering = ["-created_at", "-id"]

    def __str__(self):
        return f"{self.session} — {self.get_action_display()}"


class AttendanceAdminLog(models.Model):
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+",
                              verbose_name="Кто")
    action = models.CharField(max_length=40, verbose_name="Действие")
    object_type = models.CharField(max_length=40, verbose_name="Объект")
    object_id = models.CharField(max_length=40, blank=True, verbose_name="ID объекта")
    changes = models.JSONField(default=dict, verbose_name="Изменения")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True, verbose_name="Когда")

    class Meta:
        verbose_name = "Журнал администрирования посещаемости"
        verbose_name_plural = "Журнал администрирования посещаемости"
        ordering = ["-created_at", "-id"]

    def __str__(self):
        return f"{self.action} {self.object_type}#{self.object_id}"
