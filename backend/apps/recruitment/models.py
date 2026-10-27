"""Подбор персонала: карьерный сайт и рабочая зона HR-менеджера.

Модели:

* Vacancy — вакансия с полной карточкой для карьерного сайта (обязанности,
  требования, условия, зарплата, формат и тип занятости) и жизненным циклом
  публикации: черновик → опубликована ⇄ приостановлена → закрыта → архив.
  Публичный сайт видит только опубликованные вакансии со сроком приёма, который
  ещё не истёк (`Vacancy.objects.public()`); опубликовать может только HR явным
  действием.
* Candidate — человек: ФИО, контакты и профиль. Один кандидат — сколько угодно
  откликов. Людей не объединяют по имени: при совпадении контактов отклик
  помечается на проверку, а HR связывает записи явным действием (`merged_into`).
* Application — отклик кандидата на вакансию (или на должность без вакансии):
  этап найма, ответственный, источник, анкета, сопроводительное письмо, резюме
  в закрытом хранилище, согласие на обработку данных. Переходы этапов проверяет
  `services.pipeline`. «Принят на работу» — ровно вместе с учётной записью LMS
  (`hired_user`, OneToOne: повторно создать того же сотрудника нельзя).
* InternalNote — внутренние заметки HR о кандидате (видны только HR).
* Interview — собеседование отклика: время, формат, место или ссылка,
  интервьюер, статус (назначено, проведено, перенесено, отменено, неявка),
  оценка и результат. Перенос закрывает встречу статусом «Перенесено» и создаёт
  новую (`rescheduled_to`), так что история времени сохраняется.
* AccountRequest — запрос на учётную запись для роли, которой HR не управляет:
  её создаёт администратор (Django admin), а не HR в обход ограничений.
* HRActivity — неизменяемый журнал кадровых событий: из него строятся история
  кандидата, лента главной HR и показатели отчётов.

Сотрудник — существующий `users.User`; отдельной таблицы сотрудников нет.
"""
from __future__ import annotations

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q
from django.utils import timezone

from .storage import private_storage

RATING = [MinValueValidator(1), MaxValueValidator(5)]


class VacancyQuerySet(models.QuerySet):
    def public(self):
        """Что видит посетитель карьерного сайта: опубликовано, приём не закрыт."""
        today = timezone.localdate()
        return self.filter(status=Vacancy.Status.PUBLISHED).filter(
            Q(closes_on__isnull=True) | Q(closes_on__gte=today))


class Vacancy(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Черновик"
        PUBLISHED = "published", "Опубликована"
        PAUSED = "paused", "Приостановлена"
        CLOSED = "closed", "Закрыта"
        ARCHIVED = "archived", "В архиве"

    class WorkFormat(models.TextChoices):
        OFFICE = "office", "В офисе"
        REMOTE = "remote", "Удалённо"
        HYBRID = "hybrid", "Гибридный формат"

    class EmploymentType(models.TextChoices):
        FULL_TIME = "full_time", "Полная занятость"
        PART_TIME = "part_time", "Частичная занятость"
        PROJECT = "project", "Проектная работа"
        INTERNSHIP = "internship", "Стажировка"

    class Currency(models.TextChoices):
        KGS = "KGS", "сом"
        USD = "USD", "$"

    title = models.CharField(max_length=200, verbose_name="Название")
    slug = models.SlugField(max_length=220, unique=True, allow_unicode=False, verbose_name="Адрес на сайте")
    department = models.CharField(max_length=150, blank=True, verbose_name="Направление или отдел")
    summary = models.CharField(max_length=300, blank=True, verbose_name="Краткое описание")
    description = models.TextField(blank=True, verbose_name="Описание")
    responsibilities = models.TextField(blank=True, verbose_name="Обязанности")
    requirements = models.TextField(blank=True, verbose_name="Обязательные требования")
    nice_to_have = models.TextField(blank=True, verbose_name="Желательные навыки")
    conditions = models.TextField(blank=True, verbose_name="Условия работы")
    selection_stages = models.TextField(blank=True, verbose_name="Этапы отбора",
                                        help_text="По одному этапу в строке.")
    location = models.CharField(max_length=150, blank=True, verbose_name="Город или место работы")
    work_format = models.CharField(max_length=10, choices=WorkFormat.choices, default=WorkFormat.OFFICE,
                                   verbose_name="Формат работы")
    employment_type = models.CharField(max_length=12, choices=EmploymentType.choices,
                                       default=EmploymentType.FULL_TIME, verbose_name="Тип занятости")
    salary_min = models.PositiveIntegerField(null=True, blank=True, verbose_name="Зарплата от")
    salary_max = models.PositiveIntegerField(null=True, blank=True, verbose_name="Зарплата до")
    salary_currency = models.CharField(max_length=3, choices=Currency.choices, default=Currency.KGS,
                                       verbose_name="Валюта")
    show_salary = models.BooleanField(default=False, verbose_name="Публиковать зарплату")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT, db_index=True,
                              verbose_name="Статус")
    published_at = models.DateTimeField(null=True, blank=True, verbose_name="Опубликована")
    closes_on = models.DateField(null=True, blank=True, verbose_name="Приём откликов до")
    closed_at = models.DateTimeField(null=True, blank=True, verbose_name="Закрыта")
    archived_at = models.DateTimeField(null=True, blank=True, verbose_name="В архиве с")
    responsible = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="hr_vacancies",
        verbose_name="Ответственный",
    )
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                   related_name="+", verbose_name="Кем создана")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Создана")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Изменена")

    objects = VacancyQuerySet.as_manager()

    class Meta:
        verbose_name = "Вакансия"
        verbose_name_plural = "Вакансии"
        ordering = ["-created_at", "-id"]
        indexes = [models.Index(fields=["status", "published_at"], name="recruit_vacancy_public_idx")]
        constraints = [
            models.CheckConstraint(
                condition=Q(salary_min__isnull=True) | Q(salary_max__isnull=True) | Q(salary_min__lte=models.F("salary_max")),
                name="recruitment_salary_range",
            ),
            # Опубликованная (или когда-либо бывшая на сайте) вакансия знает дату публикации.
            models.CheckConstraint(
                condition=~Q(status="published") | Q(published_at__isnull=False),
                name="recruitment_published_has_date",
            ),
        ]

    def __str__(self):
        return self.title

    @property
    def is_accepting(self) -> bool:
        """Принимает ли сейчас отклики с сайта."""
        return self.status == self.Status.PUBLISHED and (
            self.closes_on is None or self.closes_on >= timezone.localdate())


class Candidate(models.Model):
    """Человек. Контакты нормализуются (`email` — в нижнем регистре,
    `phone_digits` — только цифры с кодом страны) для поиска совпадений."""

    last_name = models.CharField(max_length=100, blank=True, verbose_name="Фамилия")
    first_name = models.CharField(max_length=100, verbose_name="Имя")
    middle_name = models.CharField(max_length=100, blank=True, verbose_name="Отчество")
    phone = models.CharField(max_length=32, blank=True, verbose_name="Телефон")
    phone_digits = models.CharField(max_length=20, blank=True, db_index=True, verbose_name="Телефон (цифры)")
    email = models.EmailField(blank=True, db_index=True, verbose_name="Email")
    city = models.CharField(max_length=100, blank=True, verbose_name="Город проживания")
    experience = models.TextField(blank=True, verbose_name="Опыт работы")
    education = models.TextField(blank=True, verbose_name="Образование")
    skills = models.TextField(blank=True, verbose_name="Профессиональные навыки")
    portfolio_url = models.URLField(blank=True, verbose_name="Портфолио или профиль")
    # Запись, объединённая с другой (дубль): отклики перенесены, сама запись
    # остаётся для истории.
    merged_into = models.ForeignKey("self", on_delete=models.PROTECT, null=True, blank=True,
                                    related_name="merged_from", verbose_name="Объединён с")
    # Персональные данные удалены по сроку хранения или по запросу.
    erased_at = models.DateTimeField(null=True, blank=True, verbose_name="Данные удалены")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                   related_name="+", verbose_name="Кем добавлен")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Создан")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Изменён")

    class Meta:
        verbose_name = "Кандидат"
        verbose_name_plural = "Кандидаты"
        ordering = ["last_name", "first_name", "id"]

    def __str__(self):
        return self.full_name

    @property
    def full_name(self) -> str:
        return " ".join(part for part in (self.last_name, self.first_name, self.middle_name) if part)

    @property
    def employee(self):
        """Учётная запись сотрудника, если кандидат принят по одному из откликов."""
        hired = next((a for a in self.applications.all() if a.hired_user_id), None)
        return hired.hired_user if hired else None


def resume_path(instance, filename: str) -> str:
    """Случайное имя: по имени файла не угадать ни кандидата, ни сам файл."""
    import uuid

    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "bin"
    return f"recruitment/resumes/{timezone.localdate():%Y/%m}/{uuid.uuid4().hex}.{ext}"


class Application(models.Model):
    class Status(models.TextChoices):
        NEW = "new", "Новый отклик"
        SCREENING = "screening", "Первичный просмотр"
        SHORTLISTED = "shortlisted", "Подходит для собеседования"
        INTERVIEW_SCHEDULED = "interview_scheduled", "Собеседование назначено"
        INTERVIEW_DONE = "interview_done", "Собеседование проведено"
        AWAITING_DECISION = "awaiting_decision", "Ожидается решение"
        NEXT_STAGE = "next_stage", "Следующий этап"
        OFFER = "offer", "Предложение о работе"
        HIRED = "hired", "Принят на работу"
        REJECTED = "rejected", "Отказ компании"
        WITHDRAWN = "withdrawn", "Кандидат отказался"

    class Source(models.TextChoices):
        COMPANY_SITE = "company_site", "Сайт вакансий компании"
        JOB_SITE = "job_site", "Сайт поиска работы"
        SOCIAL = "social", "Социальные сети"
        REFERRAL = "referral", "Рекомендация"
        DIRECT = "direct", "Обратился сам"
        AGENCY = "agency", "Кадровое агентство"
        OTHER = "other", "Другое"

    class Channel(models.TextChoices):
        PUBLIC = "public", "Отклик с сайта"
        HR = "hr", "Добавлен HR"

    number = models.CharField(max_length=16, unique=True, verbose_name="Номер заявки")
    candidate = models.ForeignKey(Candidate, on_delete=models.PROTECT, related_name="applications",
                                  verbose_name="Кандидат")
    vacancy = models.ForeignKey(Vacancy, on_delete=models.PROTECT, null=True, blank=True,
                                related_name="applications", verbose_name="Вакансия")
    position = models.CharField(max_length=150, blank=True, verbose_name="Должность",
                                help_text="Если кандидат рассматривается не на конкретную вакансию.")
    channel = models.CharField(max_length=8, choices=Channel.choices, default=Channel.HR, verbose_name="Канал")
    source = models.CharField(max_length=20, choices=Source.choices, default=Source.OTHER, db_index=True,
                              verbose_name="Источник")
    source_details = models.CharField(max_length=255, blank=True, verbose_name="Источник — подробнее")
    applied_on = models.DateField(default=timezone.localdate, db_index=True, verbose_name="Дата отклика")
    responsible = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="hr_applications", verbose_name="Ответственный",
    )
    status = models.CharField(max_length=24, choices=Status.choices, default=Status.NEW, db_index=True,
                              verbose_name="Этап")
    status_changed_at = models.DateTimeField(default=timezone.now, verbose_name="Этап изменён")
    cover_letter = models.TextField(blank=True, verbose_name="Сопроводительное письмо")
    # Анкета так, как её отправил кандидат (ФИО, контакты, опыт…): профиль
    # кандидата может меняться, а заявка остаётся неизменной.
    submitted_data = models.JSONField(default=dict, blank=True, verbose_name="Анкета отклика")
    resume = models.FileField(upload_to=resume_path, storage=private_storage, blank=True, verbose_name="Резюме")
    resume_name = models.CharField(max_length=255, blank=True, verbose_name="Имя файла резюме")
    resume_size = models.PositiveIntegerField(null=True, blank=True, verbose_name="Размер резюме, байт")
    consent_at = models.DateTimeField(null=True, blank=True, verbose_name="Согласие на обработку данных")
    consent_version = models.CharField(max_length=20, blank=True, verbose_name="Версия текста согласия")
    # Ключ формы: повторная отправка той же формы не создаёт второй отклик.
    submission_token = models.UUIDField(null=True, blank=True, unique=True, verbose_name="Ключ отправки")
    # Контакты совпали с другим кандидатом не полностью — нужна проверка HR.
    needs_duplicate_review = models.BooleanField(default=False, db_index=True,
                                                 verbose_name="Проверить на дубль")
    hired_user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
        related_name="hired_from_application", verbose_name="Учётная запись сотрудника",
    )
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                   related_name="+", verbose_name="Кем добавлен")
    created_at = models.DateTimeField(default=timezone.now, db_index=True, verbose_name="Создан")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Изменён")

    class Meta:
        verbose_name = "Отклик"
        verbose_name_plural = "Отклики"
        ordering = ["-created_at", "-id"]
        indexes = [models.Index(fields=["vacancy", "status"], name="recruit_app_vacancy_idx")]
        constraints = [
            # «Принят на работу» — ровно тогда, когда создана учётная запись.
            models.CheckConstraint(
                condition=(Q(status="hired") & Q(hired_user__isnull=False))
                | (~Q(status="hired") & Q(hired_user__isnull=True)),
                name="recruitment_app_hired_has_account",
            ),
            # Один действующий отклик кандидата на одну вакансию.
            models.UniqueConstraint(
                fields=["candidate", "vacancy"],
                condition=Q(vacancy__isnull=False) & ~Q(status__in=["hired", "rejected", "withdrawn"]),
                name="recruitment_one_active_application",
            ),
        ]

    def __str__(self):
        return f"{self.number} — {self.candidate}"

    @property
    def position_label(self) -> str:
        return self.vacancy.title if self.vacancy_id else self.position


class InternalNote(models.Model):
    candidate = models.ForeignKey(Candidate, on_delete=models.PROTECT, related_name="internal_notes",
                                  verbose_name="Кандидат")
    application = models.ForeignKey(Application, on_delete=models.PROTECT, null=True, blank=True,
                                    related_name="internal_notes", verbose_name="Отклик")
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+",
                               verbose_name="Автор")
    text = models.TextField(verbose_name="Текст")
    created_at = models.DateTimeField(default=timezone.now, verbose_name="Создана")

    class Meta:
        verbose_name = "Заметка HR"
        verbose_name_plural = "Заметки HR"
        ordering = ["-created_at", "-id"]

    def __str__(self):
        return f"{self.candidate} — {self.created_at:%Y-%m-%d %H:%M}"


class Interview(models.Model):
    class Status(models.TextChoices):
        SCHEDULED = "scheduled", "Запланировано"
        COMPLETED = "completed", "Проведено"
        RESCHEDULED = "rescheduled", "Перенесено"
        CANCELLED = "cancelled", "Отменено"
        NO_SHOW = "no_show", "Кандидат не пришёл"

    class Format(models.TextChoices):
        IN_PERSON = "in_person", "Очно"
        ONLINE = "online", "Онлайн"
        PHONE = "phone", "По телефону"

    class Result(models.TextChoices):
        PASSED = "passed", "Подходит"
        FAILED = "failed", "Не подходит"
        UNDECIDED = "undecided", "Нужно решение"

    class NextStep(models.TextChoices):
        NEXT_INTERVIEW = "next_interview", "Следующий этап"
        AWAITING_DECISION = "awaiting_decision", "Ожидать решения"
        OFFER = "offer", "Сделать предложение"
        REJECT = "reject", "Отказать"

    application = models.ForeignKey(Application, on_delete=models.PROTECT, related_name="interviews",
                                    verbose_name="Отклик")
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
    notes = models.TextField(blank=True, verbose_name="Внутренние заметки")
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.SCHEDULED, db_index=True,
                              verbose_name="Статус")
    reschedule_count = models.PositiveSmallIntegerField(default=0, verbose_name="Переносов")
    rescheduled_to = models.OneToOneField("self", on_delete=models.PROTECT, null=True, blank=True,
                                          related_name="rescheduled_from", verbose_name="Перенесено на")
    cancel_reason = models.CharField(max_length=255, blank=True, verbose_name="Причина отмены")
    cancelled_at = models.DateTimeField(null=True, blank=True, verbose_name="Отменено")
    result = models.CharField(max_length=10, choices=Result.choices, blank=True, verbose_name="Решение")
    overall_rating = models.PositiveSmallIntegerField(null=True, blank=True, validators=RATING,
                                                      verbose_name="Общая оценка")
    skills_rating = models.PositiveSmallIntegerField(null=True, blank=True, validators=RATING,
                                                     verbose_name="Профессиональные навыки")
    strengths = models.TextField(blank=True, verbose_name="Сильные стороны")
    concerns = models.TextField(blank=True, verbose_name="Замечания")
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
            # Решение и оценки есть только у проведённого собеседования.
            models.CheckConstraint(
                condition=(Q(status="completed") & ~Q(result="") & Q(completed_at__isnull=False))
                | (~Q(status="completed") & Q(result="") & Q(overall_rating__isnull=True)
                   & Q(skills_rating__isnull=True)),
                name="recruitment_result_only_when_completed",
            ),
            models.CheckConstraint(
                condition=~Q(status="rescheduled") | Q(rescheduled_to__isnull=False),
                name="recruitment_rescheduled_has_target",
            ),
        ]

    def __str__(self):
        return f"{self.application.candidate} — {self.scheduled_at:%Y-%m-%d %H:%M}"

    @property
    def candidate(self) -> Candidate:
        return self.application.candidate


class AccountRequest(models.Model):
    """Учётная запись для роли вне полномочий HR: HR оформляет запрос,
    администратор создаёт учётную запись (Django admin → действие «Одобрить»)."""

    class Status(models.TextChoices):
        PENDING = "pending", "Ожидает администратора"
        APPROVED = "approved", "Учётная запись создана"
        REJECTED = "rejected", "Отклонён"

    application = models.ForeignKey(Application, on_delete=models.PROTECT, related_name="account_requests",
                                    verbose_name="Отклик")
    role = models.CharField(max_length=20, verbose_name="Роль")
    username = models.CharField(max_length=150, verbose_name="Логин")
    email = models.EmailField(verbose_name="Email")
    first_name = models.CharField(max_length=100, verbose_name="Имя")
    last_name = models.CharField(max_length=100, blank=True, verbose_name="Фамилия")
    comment = models.TextField(blank=True, verbose_name="Комментарий HR")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING, db_index=True,
                              verbose_name="Статус")
    requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
                                     related_name="+", verbose_name="Запросил")
    decided_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                   related_name="+", verbose_name="Решил")
    decided_at = models.DateTimeField(null=True, blank=True, verbose_name="Решение принято")
    decision_comment = models.CharField(max_length=255, blank=True, verbose_name="Комментарий администратора")
    created_at = models.DateTimeField(default=timezone.now, verbose_name="Создан")

    class Meta:
        verbose_name = "Запрос на учётную запись"
        verbose_name_plural = "Запросы на учётные записи"
        ordering = ["-created_at", "-id"]
        constraints = [
            models.UniqueConstraint(fields=["application"], condition=Q(status="pending"),
                                    name="recruitment_one_pending_account_request"),
        ]

    def __str__(self):
        return f"{self.username} ({self.role}) — {self.get_status_display()}"


class HRActivity(models.Model):
    class Kind(models.TextChoices):
        EMPLOYEE_CREATED = "employee_created", "Создан сотрудник"
        EMPLOYEE_UPDATED = "employee_updated", "Изменены данные сотрудника"
        EMPLOYEE_PASSWORD = "employee_password", "Изменён пароль сотрудника"
        EMPLOYEE_DEACTIVATED = "employee_deactivated", "Сотрудник деактивирован"
        EMPLOYEE_ACTIVATED = "employee_activated", "Сотрудник активирован"
        VACANCY_CREATED = "vacancy_created", "Создана вакансия"
        VACANCY_UPDATED = "vacancy_updated", "Изменена вакансия"
        VACANCY_STATUS = "vacancy_status", "Изменён статус вакансии"
        APPLICATION_RECEIVED = "application_received", "Получен отклик с сайта"
        CANDIDATE_CREATED = "candidate_created", "Добавлен кандидат"
        CANDIDATE_UPDATED = "candidate_updated", "Изменены данные кандидата"
        CANDIDATE_STATUS = "candidate_status", "Изменён этап кандидата"
        CANDIDATE_NOTE = "candidate_note", "Добавлена заметка"
        CANDIDATE_MERGED = "candidate_merged", "Записи кандидата объединены"
        CANDIDATE_ERASED = "candidate_erased", "Персональные данные удалены"
        RESUME_ACCESSED = "resume_accessed", "Открыто резюме"
        CANDIDATE_HIRED = "candidate_hired", "Кандидат принят на работу"
        ACCOUNT_REQUESTED = "account_requested", "Запрошена учётная запись"
        ACCOUNT_REQUEST_DONE = "account_request_done", "Решение по запросу учётной записи"
        INTERVIEW_SCHEDULED = "interview_scheduled", "Назначено собеседование"
        INTERVIEW_RESCHEDULED = "interview_rescheduled", "Собеседование перенесено"
        INTERVIEW_CANCELLED = "interview_cancelled", "Собеседование отменено"
        INTERVIEW_NO_SHOW = "interview_no_show", "Кандидат не пришёл на собеседование"
        INTERVIEW_COMPLETED = "interview_completed", "Зафиксирован результат собеседования"

    kind = models.CharField(max_length=24, choices=Kind.choices, db_index=True, verbose_name="Событие")
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+",
                              verbose_name="Кто")
    employee = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
                                 related_name="hr_activities", verbose_name="Сотрудник")
    candidate = models.ForeignKey(Candidate, on_delete=models.PROTECT, null=True, blank=True,
                                  related_name="activities", verbose_name="Кандидат")
    application = models.ForeignKey(Application, on_delete=models.PROTECT, null=True, blank=True,
                                    related_name="activities", verbose_name="Отклик")
    interview = models.ForeignKey(Interview, on_delete=models.PROTECT, null=True, blank=True,
                                  related_name="activities", verbose_name="Собеседование")
    vacancy = models.ForeignKey(Vacancy, on_delete=models.PROTECT, null=True, blank=True,
                                related_name="activities", verbose_name="Вакансия")
    # Переход этапа отклика (для истории и времени этапов в отчётах).
    from_status = models.CharField(max_length=24, blank=True, verbose_name="Из этапа")
    to_status = models.CharField(max_length=24, blank=True, verbose_name="В этап")
    message = models.TextField(blank=True, verbose_name="Описание")
    created_at = models.DateTimeField(default=timezone.now, db_index=True, verbose_name="Когда")

    class Meta:
        verbose_name = "Кадровое событие"
        verbose_name_plural = "Кадровые события"
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["candidate", "created_at"], name="recruit_activity_cand_idx"),
            models.Index(fields=["kind", "created_at"], name="recruit_activity_kind_idx"),
        ]

    def __str__(self):
        return f"{self.get_kind_display()} — {self.created_at:%Y-%m-%d %H:%M}"
