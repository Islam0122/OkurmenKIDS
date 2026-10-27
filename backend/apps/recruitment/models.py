"""Подбор персонала — рабочая зона HR-менеджера.

Модели:

* Vacancy — минимальный справочник вакансий (в проекте его не было): название,
  описание, отдел/должность, статус, ответственный.
* Candidate — кандидат и его этап найма. Переходы между этапами проверяет
  `services.pipeline` (никаких противоречивых состояний: «Принят» только
  вместе с созданной учётной записью, «Собеседование назначено» — только пока
  есть назначенная встреча). Нанятый кандидат связан со своим `users.User`
  через OneToOne — повторно создать того же сотрудника нельзя.
* Interview — собеседование: дата и время, формат, место или ссылка,
  интервьюер, статус, результат и следующий шаг.
* HRActivity — неизменяемый журнал кадровых событий: действия с учётными
  записями сотрудников, история взаимодействия с кандидатом, переходы этапов
  (из какого — в какой, когда), собеседования. Из него строятся лента событий,
  история кандидата, перенесённые/отменённые встречи и время этапов в отчётах.

Сотрудник — существующий `users.User`; отдельной таблицы сотрудников нет.
"""
from __future__ import annotations

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q
from django.utils import timezone


class Vacancy(models.Model):
    class Status(models.TextChoices):
        OPEN = "open", "Открыта"
        PAUSED = "paused", "Приостановлена"
        CLOSED = "closed", "Закрыта"

    title = models.CharField(max_length=200, verbose_name="Название")
    description = models.TextField(blank=True, verbose_name="Описание")
    department = models.CharField(max_length=150, blank=True, verbose_name="Отдел или должность")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.OPEN, db_index=True,
                              verbose_name="Статус")
    responsible = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="hr_vacancies",
        verbose_name="Ответственный",
    )
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                   related_name="+", verbose_name="Кем создана")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Создана")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Изменена")

    class Meta:
        verbose_name = "Вакансия"
        verbose_name_plural = "Вакансии"
        ordering = ["-created_at", "-id"]

    def __str__(self):
        return self.title


class Candidate(models.Model):
    class Status(models.TextChoices):
        NEW = "new", "Новый кандидат"
        CONTACTED = "contacted", "Первичный контакт"
        INTERVIEW_SCHEDULED = "interview_scheduled", "Собеседование назначено"
        INTERVIEW_DONE = "interview_done", "Собеседование пройдено"
        AWAITING_DECISION = "awaiting_decision", "Ожидается решение"
        OFFER = "offer", "Предложение о работе"
        HIRED = "hired", "Принят на работу"
        REJECTED = "rejected", "Отказ"
        WITHDRAWN = "withdrawn", "Кандидат отказался"

    class Source(models.TextChoices):
        JOB_SITE = "job_site", "Сайт вакансий"
        COMPANY_SITE = "company_site", "Сайт компании"
        SOCIAL = "social", "Социальные сети"
        REFERRAL = "referral", "Рекомендация"
        DIRECT = "direct", "Обратился сам"
        AGENCY = "agency", "Кадровое агентство"
        OTHER = "other", "Другое"

    last_name = models.CharField(max_length=100, verbose_name="Фамилия")
    first_name = models.CharField(max_length=100, verbose_name="Имя")
    middle_name = models.CharField(max_length=100, blank=True, verbose_name="Отчество")
    phone = models.CharField(max_length=32, blank=True, verbose_name="Телефон")
    email = models.EmailField(blank=True, verbose_name="Email")
    vacancy = models.ForeignKey(Vacancy, on_delete=models.PROTECT, null=True, blank=True, related_name="candidates",
                                verbose_name="Вакансия")
    position = models.CharField(max_length=150, blank=True, verbose_name="Должность",
                                help_text="Если кандидат рассматривается не на конкретную вакансию.")
    source = models.CharField(max_length=20, choices=Source.choices, default=Source.OTHER, db_index=True,
                              verbose_name="Источник")
    source_details = models.CharField(max_length=255, blank=True, verbose_name="Источник — подробнее")
    added_on = models.DateField(default=timezone.localdate, db_index=True, verbose_name="Дата добавления")
    responsible = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="hr_candidates",
        verbose_name="Ответственный",
    )
    notes = models.TextField(blank=True, verbose_name="Заметки")
    status = models.CharField(max_length=24, choices=Status.choices, default=Status.NEW, db_index=True,
                              verbose_name="Этап")
    status_changed_at = models.DateTimeField(default=timezone.now, verbose_name="Этап изменён")
    # Учётная запись, созданная при найме. OneToOne: один аккаунт — один кандидат.
    hired_user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="hired_from_candidate",
        verbose_name="Учётная запись сотрудника",
    )
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                   related_name="+", verbose_name="Кем добавлен")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Создан")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Изменён")

    class Meta:
        verbose_name = "Кандидат"
        verbose_name_plural = "Кандидаты"
        ordering = ["-added_on", "-id"]
        constraints = [
            # «Принят на работу» — ровно тогда, когда создана учётная запись.
            models.CheckConstraint(
                condition=(Q(status="hired") & Q(hired_user__isnull=False))
                | (~Q(status="hired") & Q(hired_user__isnull=True)),
                name="recruitment_hired_has_account",
            ),
        ]

    def __str__(self):
        return self.full_name

    @property
    def full_name(self) -> str:
        return " ".join(part for part in (self.last_name, self.first_name, self.middle_name) if part)

    @property
    def position_label(self) -> str:
        return self.vacancy.title if self.vacancy_id else self.position


class Interview(models.Model):
    class Status(models.TextChoices):
        SCHEDULED = "scheduled", "Назначено"
        COMPLETED = "completed", "Проведено"
        CANCELLED = "cancelled", "Отменено"

    class Format(models.TextChoices):
        IN_PERSON = "in_person", "Очно"
        ONLINE = "online", "Онлайн"
        PHONE = "phone", "По телефону"

    class Result(models.TextChoices):
        PASSED = "passed", "Успешно"
        FAILED = "failed", "Не прошёл"
        UNDECIDED = "undecided", "Нужно решение"

    class NextStep(models.TextChoices):
        NEXT_INTERVIEW = "next_interview", "Следующее собеседование"
        AWAITING_DECISION = "awaiting_decision", "Ожидать решения"
        OFFER = "offer", "Сделать предложение"
        REJECT = "reject", "Отказать"

    candidate = models.ForeignKey(Candidate, on_delete=models.PROTECT, related_name="interviews",
                                  verbose_name="Кандидат")
    vacancy = models.ForeignKey(Vacancy, on_delete=models.PROTECT, null=True, blank=True, related_name="interviews",
                                verbose_name="Вакансия")
    scheduled_at = models.DateTimeField(db_index=True, verbose_name="Дата и время")
    duration_minutes = models.PositiveSmallIntegerField(
        default=60, validators=[MinValueValidator(15), MaxValueValidator(480)], verbose_name="Длительность, мин",
    )
    format = models.CharField(max_length=10, choices=Format.choices, default=Format.IN_PERSON, verbose_name="Формат")
    location = models.CharField(max_length=255, blank=True, verbose_name="Место проведения")
    meeting_url = models.URLField(blank=True, verbose_name="Ссылка на онлайн-встречу")
    interviewer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="hr_interviews",
                                    verbose_name="Интервьюер")
    notes = models.TextField(blank=True, verbose_name="Заметки")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.SCHEDULED, db_index=True,
                              verbose_name="Статус")
    reschedule_count = models.PositiveSmallIntegerField(default=0, verbose_name="Переносов")
    cancel_reason = models.CharField(max_length=255, blank=True, verbose_name="Причина отмены")
    cancelled_at = models.DateTimeField(null=True, blank=True, verbose_name="Отменено")
    result = models.CharField(max_length=10, choices=Result.choices, blank=True, verbose_name="Результат")
    result_comment = models.TextField(blank=True, verbose_name="Комментарий к результату")
    next_step = models.CharField(max_length=20, choices=NextStep.choices, blank=True, verbose_name="Следующий шаг")
    next_step_date = models.DateField(null=True, blank=True, verbose_name="Дата следующего этапа")
    completed_at = models.DateTimeField(null=True, blank=True, verbose_name="Результат зафиксирован")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                   related_name="+", verbose_name="Кем назначено")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Создано")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Изменено")

    class Meta:
        verbose_name = "Собеседование"
        verbose_name_plural = "Собеседования"
        ordering = ["scheduled_at", "id"]
        indexes = [models.Index(fields=["status", "scheduled_at"], name="recruit_interview_status_idx")]
        constraints = [
            # Результат есть ровно у проведённого собеседования.
            models.CheckConstraint(
                condition=(Q(status="completed") & ~Q(result="") & Q(completed_at__isnull=False))
                | (~Q(status="completed") & Q(result="")),
                name="recruitment_result_only_when_completed",
            ),
        ]

    def __str__(self):
        return f"{self.candidate} — {self.scheduled_at:%Y-%m-%d %H:%M}"


class HRActivity(models.Model):
    class Kind(models.TextChoices):
        EMPLOYEE_CREATED = "employee_created", "Создан сотрудник"
        EMPLOYEE_UPDATED = "employee_updated", "Изменены данные сотрудника"
        EMPLOYEE_PASSWORD = "employee_password", "Изменён пароль сотрудника"
        EMPLOYEE_DEACTIVATED = "employee_deactivated", "Сотрудник деактивирован"
        EMPLOYEE_ACTIVATED = "employee_activated", "Сотрудник активирован"
        VACANCY_CREATED = "vacancy_created", "Создана вакансия"
        VACANCY_UPDATED = "vacancy_updated", "Изменена вакансия"
        CANDIDATE_CREATED = "candidate_created", "Добавлен кандидат"
        CANDIDATE_UPDATED = "candidate_updated", "Изменены данные кандидата"
        CANDIDATE_STATUS = "candidate_status", "Изменён этап кандидата"
        CANDIDATE_NOTE = "candidate_note", "Взаимодействие с кандидатом"
        CANDIDATE_HIRED = "candidate_hired", "Кандидат принят на работу"
        INTERVIEW_SCHEDULED = "interview_scheduled", "Назначено собеседование"
        INTERVIEW_RESCHEDULED = "interview_rescheduled", "Собеседование перенесено"
        INTERVIEW_CANCELLED = "interview_cancelled", "Собеседование отменено"
        INTERVIEW_COMPLETED = "interview_completed", "Зафиксирован результат собеседования"

    kind = models.CharField(max_length=24, choices=Kind.choices, db_index=True, verbose_name="Событие")
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+",
                              verbose_name="Кто")
    employee = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
                                 related_name="hr_activities", verbose_name="Сотрудник")
    candidate = models.ForeignKey(Candidate, on_delete=models.PROTECT, null=True, blank=True,
                                  related_name="activities", verbose_name="Кандидат")
    interview = models.ForeignKey(Interview, on_delete=models.PROTECT, null=True, blank=True,
                                  related_name="activities", verbose_name="Собеседование")
    vacancy = models.ForeignKey(Vacancy, on_delete=models.PROTECT, null=True, blank=True,
                                related_name="activities", verbose_name="Вакансия")
    # Переход этапа кандидата (для истории и времени этапов в отчётах).
    from_status = models.CharField(max_length=24, blank=True, verbose_name="Из этапа")
    to_status = models.CharField(max_length=24, blank=True, verbose_name="В этап")
    message = models.TextField(blank=True, verbose_name="Описание")
    created_at = models.DateTimeField(default=timezone.now, db_index=True, verbose_name="Когда")

    class Meta:
        verbose_name = "Кадровое событие"
        verbose_name_plural = "Кадровые события"
        ordering = ["-created_at", "-id"]
        indexes = [models.Index(fields=["candidate", "created_at"], name="recruit_activity_cand_idx")]

    def __str__(self):
        return f"{self.get_kind_display()} — {self.created_at:%Y-%m-%d %H:%M}"
