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
from dataclasses import dataclass
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


WEEKDAY_LABELS = ("Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье")
WEEKDAY_SHORT = ("Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс")
DAY_HOURS_KEYS = ("start", "end", "break_start", "break_end")


@dataclass(frozen=True)
class DayHours:
    """Рабочие часы одного дня личного расписания (время офиса)."""

    start: time
    end: time
    break_start: time | None = None
    break_end: time | None = None

    def as_json(self) -> dict:
        def fmt(value):
            return value.strftime("%H:%M") if value else None

        return {"start": fmt(self.start), "end": fmt(self.end),
                "break_start": fmt(self.break_start), "break_end": fmt(self.break_end)}


def _parse_time(value, field: str, day_label: str) -> time | None:
    if value in (None, ""):
        return None
    if isinstance(value, time):
        return value.replace(second=0, microsecond=0)
    if isinstance(value, str):
        try:
            return time.fromisoformat(value).replace(second=0, microsecond=0)
        except ValueError:
            pass
    raise ValidationError(f"{day_label}: неверное время «{value}» в поле {field}.")


def check_day_hours(hours: DayHours, day_label: str = "") -> dict[str, str]:
    """Ошибки одного дня {поле: сообщение}; пусто — день корректен."""
    prefix = f"{day_label}: " if day_label else ""
    errors: dict[str, str] = {}
    if hours.end <= hours.start:
        errors["end"] = f"{prefix}окончание рабочего дня должно быть позже начала."
    if (hours.break_start is None) != (hours.break_end is None):
        key = "break_end" if hours.break_end is None else "break_start"
        errors[key] = f"{prefix}укажите и начало, и конец перерыва (или оставьте оба пустыми)."
    elif hours.break_start is not None:
        if hours.break_end <= hours.break_start:
            errors["break_end"] = f"{prefix}конец перерыва должен быть позже его начала."
        elif hours.break_start < hours.start or hours.break_end > hours.end:
            errors["break_start"] = f"{prefix}перерыв должен быть внутри рабочего времени."
    return errors


def parse_day_hours(value) -> dict[str, DayHours]:
    """Проверяет и разбирает `AttendanceWorkSchedule.day_hours`:
    {"0".."6": {"start": "HH:MM", "end": "HH:MM", "break_start": "HH:MM"|null, "break_end": ...}}."""
    if value in (None, ""):
        return {}
    if not isinstance(value, dict):
        raise ValidationError("Часы по дням — объект {номер дня: {start, end, break_start, break_end}}.")
    parsed: dict[str, DayHours] = {}
    for key, raw in value.items():
        key = str(key)
        if key not in {str(d) for d in ALL_WEEKDAYS}:
            raise ValidationError(f"Неизвестный день недели «{key}» (допустимо 0…6).")
        label = WEEKDAY_LABELS[int(key)]
        if not isinstance(raw, dict) or set(raw) - set(DAY_HOURS_KEYS):
            raise ValidationError(f"{label}: ожидаются поля start, end, break_start, break_end.")
        start = _parse_time(raw.get("start"), "start", label)
        end = _parse_time(raw.get("end"), "end", label)
        if start is None or end is None:
            raise ValidationError(f"{label}: укажите начало и окончание рабочего дня.")
        hours = DayHours(start, end, _parse_time(raw.get("break_start"), "break_start", label),
                         _parse_time(raw.get("break_end"), "break_end", label))
        errors = check_day_hours(hours, label)
        if errors:
            raise ValidationError(list(errors.values()))
        parsed[key] = hours
    return parsed


def validate_day_hours(value) -> None:
    parse_day_hours(value)


class AttendanceWorkSchedule(models.Model):
    """Личное расписание сотрудника. Нет записи, она выключена или сегодня
    вне периода действия — действует общее расписание из настроек (или
    занятия тренера, если это включено).

    Часы дня: `work_start`/`work_end` (+ перерыв `break_start`/`break_end`) —
    базовые для всех рабочих дней; `day_hours` хранит только дни, у которых
    часы отличаются от базовых. Старые записи (`day_hours` пуст) работают
    как раньше."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="attendance_schedule",
        verbose_name="Сотрудник",
    )
    work_start = models.TimeField(verbose_name="Начало рабочего дня")
    work_end = models.TimeField(verbose_name="Окончание рабочего дня")
    work_days = models.JSONField(default=default_work_days, validators=[validate_weekdays], verbose_name="Рабочие дни")
    break_start = models.TimeField(null=True, blank=True, verbose_name="Начало перерыва")
    break_end = models.TimeField(null=True, blank=True, verbose_name="Конец перерыва")
    day_hours = models.JSONField(
        default=dict, blank=True, validators=[validate_day_hours], verbose_name="Часы по дням",
        help_text="Дни с часами, отличными от базовых: {\"5\": {\"start\": \"10:00\", \"end\": \"15:00\", "
                  "\"break_start\": null, \"break_end\": null}}.",
    )
    late_grace_minutes = models.PositiveSmallIntegerField(
        null=True, blank=True, validators=[MaxValueValidator(240)],
        verbose_name="Льготное время, мин", help_text="Пусто — как в общих настройках.",
    )
    valid_from = models.DateField(null=True, blank=True, verbose_name="Действует с",
                                  help_text="Пусто — без ограничения.")
    valid_until = models.DateField(null=True, blank=True, verbose_name="Действует по",
                                   help_text="Включительно. Пусто — бессрочно.")
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

    @property
    def base_hours(self) -> DayHours:
        return DayHours(self.work_start, self.work_end, self.break_start, self.break_end)

    def hours_for(self, weekday: int) -> DayHours | None:
        """Часы дня недели (0 — пн) или None, если день не рабочий."""
        if weekday not in (self.work_days or []):
            return None
        try:
            override = parse_day_hours(self.day_hours).get(str(weekday))
        except ValidationError:
            override = None  # повреждённая запись не должна ломать расчёт: берём базовые часы
        return override or self.base_hours

    def is_effective_on(self, day) -> bool:
        return (self.is_active and (self.valid_from is None or self.valid_from <= day)
                and (self.valid_until is None or day <= self.valid_until))

    def clean(self):
        errors: dict[str, list[str]] = {}
        if self.work_start and self.work_end:
            for field, message in check_day_hours(self.base_hours).items():
                errors.setdefault({"start": "work_start", "end": "work_end"}.get(field, field), []).append(message)
        if self.valid_from and self.valid_until and self.valid_until < self.valid_from:
            errors.setdefault("valid_until", []).append("Дата окончания не может быть раньше даты начала.")
        try:
            overrides = parse_day_hours(self.day_hours)
        except ValidationError as exc:
            errors.setdefault("day_hours", []).extend(exc.messages)
        else:
            # Храним только отличия от базовых часов в едином формате. Часы
            # нерабочих дней отбрасываются: клиент, который меняет только
            # work_days, не должен получать ошибку из-за старых часов дня.
            working = {str(d) for d in (self.work_days or [])}
            self.day_hours = {k: h.as_json() for k, h in sorted(overrides.items())
                              if k in working and h != self.base_hours}
        if errors:
            raise ValidationError(errors)


class AttendanceScheduleException(models.Model):
    """Исключение из графика сотрудника на дату или период: отпуск,
    больничный, выходной (отгул) или особые часы. Действует поверх личного
    и общего расписания. Записи вносит администратор / HR — запись и есть
    утверждённое решение; заявок и согласования в LMS нет."""

    class Kind(models.TextChoices):
        VACATION = "vacation", "Отпуск"
        SICK_LEAVE = "sick_leave", "Больничный"
        DAY_OFF = "day_off", "Выходной (отгул)"
        CUSTOM_HOURS = "custom_hours", "Особые часы"

    LEAVE_KINDS = (Kind.VACATION, Kind.SICK_LEAVE)

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="attendance_exceptions",
        verbose_name="Сотрудник",
    )
    kind = models.CharField(max_length=20, choices=Kind.choices, verbose_name="Вид")
    date_from = models.DateField(verbose_name="С")
    date_to = models.DateField(verbose_name="По", help_text="Включительно. Один день — та же дата.")
    work_start = models.TimeField(null=True, blank=True, verbose_name="Начало дня",
                                  help_text="Только для «Особые часы».")
    work_end = models.TimeField(null=True, blank=True, verbose_name="Окончание дня",
                                help_text="Только для «Особые часы».")
    note = models.CharField(max_length=255, blank=True, verbose_name="Комментарий")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Создано")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
        verbose_name="Кем создано",
    )

    class Meta:
        verbose_name = "Исключение из графика"
        verbose_name_plural = "Исключения из графика (отпуск, больничный, отгул)"
        ordering = ["-date_from", "-id"]
        indexes = [models.Index(fields=["user", "date_from", "date_to"], name="staff_att_exc_user_dates_idx")]
        constraints = [
            models.CheckConstraint(condition=Q(date_to__gte=F("date_from")), name="staff_att_exc_dates_order"),
        ]

    def __str__(self):
        period = f"{self.date_from:%d.%m.%Y}" if self.date_from == self.date_to else \
            f"{self.date_from:%d.%m.%Y}–{self.date_to:%d.%m.%Y}"
        return f"{self.user}: {self.get_kind_display()} {period}"

    def covers(self, day) -> bool:
        return self.date_from <= day <= self.date_to

    def clean(self):
        errors: dict[str, str] = {}
        if self.date_from and self.date_to and self.date_to < self.date_from:
            errors["date_to"] = "Дата окончания не может быть раньше даты начала."
        if self.kind == self.Kind.CUSTOM_HOURS:
            if self.work_start is None:
                errors["work_start"] = "Укажите начало рабочего дня."
            if self.work_end is None:
                errors["work_end"] = "Укажите окончание рабочего дня."
            if self.work_start and self.work_end and self.work_end <= self.work_start:
                errors["work_end"] = "Окончание рабочего дня должно быть позже начала."
        else:
            # Часы нужны только для «Особые часы»: в остальных случаях день нерабочий.
            self.work_start = self.work_end = None
        if not errors and self.user_id and self.date_from and self.date_to:
            overlap = (AttendanceScheduleException.objects.filter(
                user_id=self.user_id, date_from__lte=self.date_to, date_to__gte=self.date_from)
                .exclude(pk=self.pk).first())
            if overlap:
                errors["date_from"] = f"Пересекается с другим исключением: {overlap}."
        if errors:
            raise ValidationError(errors)


class AttendanceEmployeeSettings(models.Model):
    """Настройки учёта одного сотрудника. Меняет только суперпользователь
    (Django admin). Нет записи — действуют общие настройки (учёт по роли).

    * tracking_enabled = False — сотрудник не отмечает приход и уход и не
      появляется в отчётах, даже если его роль отслеживается.
    * excluded_from_calculations = True — отмечаться может, отметки видны,
      но в посещаемость, опоздания, отсутствия и KPI его дни не входят.
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="attendance_profile",
        verbose_name="Сотрудник",
    )
    tracking_enabled = models.BooleanField(default=True, verbose_name="Учёт прихода и ухода включён")
    excluded_from_calculations = models.BooleanField(
        default=False, verbose_name="Не учитывать в расчётах",
        help_text="Отметки сохраняются, но не влияют на посещаемость, опоздания, отсутствия и KPI.",
    )
    note = models.CharField(max_length=255, blank=True, verbose_name="Комментарий")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Изменено")
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
        verbose_name="Кем изменено",
    )

    class Meta:
        verbose_name = "Учёт сотрудника"
        verbose_name_plural = "Учёт сотрудников (включение, исключение из расчётов)"

    def __str__(self):
        return str(self.user)


class AttendancePermission(models.Model):
    """«Отпросился»: разрешение не быть на работе в указанный интервал.

    Интервал [starts_at, ends_at) — время, за которое сотрудника не
    наказывают: если он покрывает начало рабочего дня — ожидаемый приход
    сдвигается на его конец, если конец дня — ожидаемый уход на его начало,
    весь день — день не считается отсутствием. Отметки по QR не меняются и
    не создаются. Запись создаёт уполномоченный (операционный директор или
    суперпользователь) — она сразу утверждена им; отмена — с причиной, запись
    остаётся в истории."""

    class Kind(models.TextChoices):
        FULL_DAY = "full_day", "Весь день"
        PARTIAL_DAY = "partial_day", "Часть дня"
        LATE_ARRIVAL = "late_arrival", "Опоздание"
        EARLY_DEPARTURE = "early_departure", "Ранний уход"

    class Status(models.TextChoices):
        APPROVED = "approved", "Утверждено"
        CANCELLED = "cancelled", "Отменено"

    MAX_DAYS = 31

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="attendance_permissions",
                             verbose_name="Сотрудник")
    kind = models.CharField(max_length=20, choices=Kind.choices, verbose_name="Вид")
    starts_at = models.DateTimeField(verbose_name="С")
    ends_at = models.DateTimeField(verbose_name="По")
    reason = models.CharField(max_length=255, verbose_name="Причина")
    comment = models.TextField(blank=True, verbose_name="Комментарий")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.APPROVED, db_index=True,
                              verbose_name="Статус")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Создано")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+",
                                   verbose_name="Кто создал")
    approved_at = models.DateTimeField(null=True, blank=True, verbose_name="Когда утверждено")
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
                                    related_name="+", verbose_name="Кто утвердил")
    cancelled_at = models.DateTimeField(null=True, blank=True, verbose_name="Когда отменено")
    cancelled_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
                                     related_name="+", verbose_name="Кто отменил")
    cancel_reason = models.CharField(max_length=255, blank=True, verbose_name="Причина отмены")

    class Meta:
        verbose_name = "Разрешение «Отпросился»"
        verbose_name_plural = "Разрешения «Отпросился»"
        ordering = ["-starts_at", "-id"]
        indexes = [models.Index(fields=["user", "status", "starts_at", "ends_at"], name="staff_att_perm_user_idx")]
        constraints = [
            models.CheckConstraint(condition=Q(ends_at__gt=F("starts_at")), name="staff_att_perm_end_after_start"),
        ]

    def __str__(self):
        return f"{self.user}: {self.get_kind_display()} {self.starts_at:%d.%m.%Y %H:%M}"

    def clean(self):
        from datetime import datetime, timedelta

        errors: dict[str, str] = {}
        if self.starts_at and self.ends_at:
            tz = AttendanceSettings.load().tzinfo
            start, end = dj_timezone.localtime(self.starts_at, tz), dj_timezone.localtime(self.ends_at, tz)
            if self.kind == self.Kind.FULL_DAY:
                # Весь день: с начала первого дня до конца последнего (по часовому поясу офиса).
                first, last = start.date(), end.date()
                if end.time() == time(0, 0) and last > first:
                    last -= timedelta(days=1)  # «по 05.11 00:00» — значит, по 04.11 включительно
                start = datetime.combine(first, time(0, 0), tzinfo=tz)
                end = datetime.combine(last, time(0, 0), tzinfo=tz) + timedelta(days=1)
                self.starts_at, self.ends_at = start, end
                if (end - start).days > self.MAX_DAYS:
                    errors["ends_at"] = f"Не больше {self.MAX_DAYS} дней; для отпуска используйте исключения из графика."
            elif end <= start:
                errors["ends_at"] = "Окончание должно быть позже начала."
            elif end.date() != start.date() and not (end.time() == time(0, 0) and end.date() == start.date() + timedelta(days=1)):
                errors["ends_at"] = "Разрешение на часть дня — в пределах одного дня."
            if not errors and self.user_id and self.status == self.Status.APPROVED:
                overlap = (AttendancePermission.objects.filter(
                    user_id=self.user_id, status=self.Status.APPROVED,
                    starts_at__lt=self.ends_at, ends_at__gt=self.starts_at).exclude(pk=self.pk).first())
                if overlap:
                    errors["starts_at"] = (f"Пересекается с другим разрешением: {overlap.get_kind_display().lower()} "
                                           f"{dj_timezone.localtime(overlap.starts_at, tz):%d.%m %H:%M}–"
                                           f"{dj_timezone.localtime(overlap.ends_at, tz):%H:%M}.")
        if not (self.reason or "").strip():
            errors["reason"] = "Укажите причину."
        if errors:
            raise ValidationError(errors)


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
