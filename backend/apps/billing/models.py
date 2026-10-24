"""Оплата обучения студентов (billing) OkurmenKIDS.

Оплата привязана к пакетам ФАКТИЧЕСКИ проведённых уроков, а не к
календарному месяцу: пакет — N уроков по тарифу (12 у IT, 20 у English —
из тарифа, не из кода). Урок списывается, когда занятие в LMS «Проведён»
(`academy.Lesson.status`), и только для студентов, которые в этот день
действительно числились в группе (история `academy.StudentStatusEvent`).

Переиспользуется существующее, без дублей:

* студент, группа, направление, урок, посещаемость — модели LMS
  (`academy.Student`, `academy.Group`, `users.Subject`, `academy.Lesson`,
  `academy.Attendance`);
* фактический платёж и возврат — `accounting.StudentPayment` (поле
  `billing_profile` связывает его с платёжным профилем); отдельной модели
  Payment нет;
* журнал аудита — `accounting.PayrollAuditLog` (через
  `apps.accounting.services.audit.log`); отдельного BillingAuditLog нет;
* запрет удаления финансовых записей — `accounting.ImmutableQuerySet`.

Новые сущности: тариф и его версии, платёжный профиль студента и история
его условий, пакет уроков и списания, начисление (счёт) и его
корректировки, распределение платежей, журнал аванса, бронь, задачи и
журнал контактов бухгалтера, уведомления (transactional outbox) и журнал
обработки событий.

Все суммы — Decimal в сомах (KGS). Финансовые записи не удаляются и не
переписываются: ошибки исправляются корректирующими операциями
(сторно списания, сторно распределения, отмена платежа, возврат).
"""
from __future__ import annotations

import uuid
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import F, Q

from apps.accounting.models import CURRENCY, ImmutableQuerySet

MONEY = {"max_digits": 14, "decimal_places": 2}
ZERO = Decimal("0.00")


class _NoDelete:
    """Финансовая запись: удалить нельзя ни по одной, ни массово."""

    delete_message = "Финансовую запись нельзя удалить — используйте корректирующую операцию."

    def delete(self, *args, **kwargs):
        raise ValidationError(self.delete_message)


# ---------------------------------------------------------------------------
# Тарифы
# ---------------------------------------------------------------------------

class AbsencePolicy(models.TextChoices):
    """Какие проведённые уроки группы списываются со студента."""

    ALL_HELD = "ALL_HELD", "Все проведённые уроки группы (пропуск списывается)"
    EXCEPT_EXCUSED = "EXCEPT_EXCUSED", "Кроме пропуска по уважительной причине"
    ATTENDED_ONLY = "ATTENDED_ONLY", "Только посещённые (присутствовал / опоздал)"


class BillingPlan(models.Model):
    """Тариф: направление, правила пакета и оплаты. Цена и число уроков в
    пакете — в версиях (`BillingPlanVersion`), чтобы хранилась история."""

    name = models.CharField(max_length=150, unique=True, verbose_name="Название")
    subject = models.ForeignKey(
        "users.Subject", on_delete=models.PROTECT, null=True, blank=True, related_name="billing_plans",
        verbose_name="Направление", help_text="IT, English, Soft Skills… Пусто — все уроки группы.",
    )
    course = models.ForeignKey(
        "academy.Course", on_delete=models.PROTECT, null=True, blank=True, related_name="billing_plans",
        verbose_name="Программа", help_text="Необязательно: ограничить тариф программой.",
    )
    payment_due_days = models.PositiveSmallIntegerField(
        default=5, validators=[MaxValueValidator(90)], verbose_name="Срок оплаты, дней",
        help_text="Через сколько дней после выставления начисление должно быть оплачено.",
    )
    warn_before_end_lessons = models.PositiveSmallIntegerField(
        default=3, verbose_name="Предупредить за N уроков до конца пакета",
        help_text="12 уроков и 3 — предупреждение бухгалтеру после 9-го урока. 0 — не предупреждать.",
    )
    early_invoice_enabled = models.BooleanField(
        default=False, verbose_name="Выставлять следующее начисление заранее",
    )
    early_invoice_after_lessons = models.PositiveSmallIntegerField(
        null=True, blank=True, validators=[MinValueValidator(1)], verbose_name="Заранее — после урока №",
        help_text="Например 9 из 12. Действует только при включённой настройке выше.",
    )
    absence_policy = models.CharField(
        max_length=20, choices=AbsencePolicy.choices, default=AbsencePolicy.ALL_HELD,
        verbose_name="Списание при отсутствии",
    )
    # Программа с фиксированной продолжительностью (Kid's Club Standard,
    # Next…): курс = `duration_months` учебных месяцев, месяц = «уроков в
    # пакете» приоритетного предмета (`subject`, обычно IT), стандартная
    # стоимость курса = цена месяца × месяцев. Пусто — тариф без срока
    # (пакеты идут, пока студент учится).
    duration_months = models.PositiveSmallIntegerField(
        null=True, blank=True, validators=[MinValueValidator(1), MaxValueValidator(60)],
        verbose_name="Продолжительность, учебных месяцев",
    )
    payment_deadline_lessons = models.PositiveSmallIntegerField(
        default=3, validators=[MinValueValidator(1)], verbose_name="Срок оплаты — урок № месяца",
        help_text="Оплата месяца — не позднее этого зачтённого урока приоритетного предмета; со следующего — просрочка.",
    )
    allow_monthly = models.BooleanField(default=True, verbose_name="Помесячная оплата")
    allow_full_prepay = models.BooleanField(default=True, verbose_name="Предоплата за весь курс")
    currency = models.CharField(max_length=3, default=CURRENCY, editable=False)
    is_active = models.BooleanField(default=True, db_index=True, verbose_name="Действует")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Тариф обучения"
        verbose_name_plural = "Тарифы обучения"
        ordering = ["name"]
        constraints = [
            models.CheckConstraint(
                condition=Q(early_invoice_enabled=False) | Q(early_invoice_after_lessons__isnull=False),
                name="billing_plan_early_invoice_lesson",
            ),
            models.CheckConstraint(
                condition=Q(allow_monthly=True) | Q(allow_full_prepay=True), name="billing_plan_some_payment_mode",
            ),
        ]

    def __str__(self):
        return self.name

    @property
    def is_course(self) -> bool:
        return bool(self.duration_months)

    def delete(self, *args, **kwargs):
        raise ValidationError("Тариф нельзя удалить — отключите его.")


class BillingPlanVersion(_NoDelete, models.Model):
    """Версия тарифа: цена пакета и уроков в пакете с даты. Не
    редактируется: новая цена — новая версия, прежняя закрывается днём
    раньше. Созданные пакеты и счета хранят снимок и от версий не зависят."""

    plan = models.ForeignKey(BillingPlan, on_delete=models.PROTECT, related_name="versions", verbose_name="Тариф")
    lessons_per_package = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1)], verbose_name="Уроков в пакете",
    )
    package_price = models.DecimalField(
        **MONEY, validators=[MinValueValidator(Decimal("0.01"))], verbose_name="Стоимость пакета, сом",
    )
    currency = models.CharField(max_length=3, default=CURRENCY, editable=False)
    effective_from = models.DateField(verbose_name="Действует с")
    effective_to = models.DateField(null=True, blank=True, verbose_name="Действует по (включительно)")
    reason = models.TextField(verbose_name="Основание изменения")
    previous_version = models.OneToOneField(
        "self", on_delete=models.PROTECT, null=True, blank=True, related_name="next_version",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    objects = ImmutableQuerySet.as_manager()

    class Meta:
        verbose_name = "Версия тарифа"
        verbose_name_plural = "История тарифов обучения"
        ordering = ["plan", "-effective_from", "-id"]
        constraints = [
            models.UniqueConstraint(fields=["plan", "effective_from"], name="unique_billing_plan_version_start"),
            models.UniqueConstraint(
                fields=["plan"], condition=Q(effective_to__isnull=True), name="unique_open_billing_plan_version",
            ),
            models.CheckConstraint(condition=Q(package_price__gt=0), name="billing_plan_price_positive"),
            models.CheckConstraint(condition=Q(lessons_per_package__gt=0), name="billing_plan_lessons_positive"),
            models.CheckConstraint(
                condition=Q(effective_to__isnull=True) | Q(effective_to__gte=F("effective_from")),
                name="billing_plan_version_range",
            ),
        ]

    def __str__(self):
        return f"{self.plan}: {self.lessons_per_package} ур. / {self.package_price} сом с {self.effective_from:%d.%m.%Y}"


# ---------------------------------------------------------------------------
# Платёжный профиль студента
# ---------------------------------------------------------------------------

class DiscountType(models.TextChoices):
    NONE = "NONE", "Без скидки"
    PERCENT = "PERCENT", "Процент"
    FIXED = "FIXED", "Фиксированная сумма"


def _discount_constraints(prefix: str) -> list:
    return [
        models.CheckConstraint(condition=Q(discount_value__gte=0), name=f"{prefix}_discount_non_negative"),
        models.CheckConstraint(
            condition=~Q(discount_type="PERCENT") | Q(discount_value__lte=100), name=f"{prefix}_discount_percent_max",
        ),
        models.CheckConstraint(
            condition=~Q(discount_type="NONE") | Q(discount_value=0), name=f"{prefix}_discount_none_zero",
        ),
        models.CheckConstraint(
            condition=Q(custom_price__isnull=True) | Q(custom_price__gt=0), name=f"{prefix}_custom_price_positive",
        ),
    ]


class PaymentMode(models.TextChoices):
    MONTHLY = "MONTHLY", "Помесячная оплата"
    FULL_PREPAY = "FULL_PREPAY", "Предоплата за весь курс"


class ReservationAllocation(models.TextChoices):
    FIRST_MONTH = "FIRST_MONTH", "Бронь засчитывается в первый месяц"
    COURSE_TOTAL = "COURSE_TOTAL", "Бронь засчитывается в общую стоимость курса"


def _course_price_constraints(prefix: str) -> list:
    return [
        models.CheckConstraint(
            condition=Q(final_course_price__isnull=True) | Q(final_course_price__gte=0),
            name=f"{prefix}_final_non_negative",
        ),
        models.CheckConstraint(condition=Q(discount_amount__gte=0), name=f"{prefix}_course_discount_non_negative"),
        models.CheckConstraint(
            condition=Q(discount_enabled=True) | Q(discount_amount=0), name=f"{prefix}_no_discount_zero",
        ),
    ]


class StudentBillingProfile(models.Model):
    """Договор студента (платёжный профиль): условия оплаты по программе.

    У программы с продолжительностью (`plan.duration_months`) договор хранит
    снимок условий на момент оформления: стандартную и итоговую стоимость
    курса, цену и длину учебного месяца, срок оплаты. Изменение тарифа
    программы договор не меняет. Скидка — не процент: академия задаёт
    итоговую стоимость курса, скидка = стандартная − итоговая.

    Действующие условия — здесь, их история — `BillingTermsChange`. Аванс
    и долг — по `CreditLedgerEntry` и `Invoice` (не хранятся отдельно)."""

    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Обучается"
        PAUSED = "PAUSED", "Приостановлен"
        INACTIVE = "INACTIVE", "Начисления остановлены"
        COMPLETED = "COMPLETED", "Курс завершён"

    CLOSED_STATUSES = (Status.INACTIVE, Status.COMPLETED)

    class StopSource(models.TextChoices):
        MANUAL = "MANUAL", "Вручную"
        STUDENT_STATUS = "STUDENT_STATUS", "Статус студента в LMS"

    student = models.ForeignKey(
        "academy.Student", on_delete=models.PROTECT, related_name="billing_profiles", verbose_name="Студент",
    )
    subject = models.ForeignKey(
        "users.Subject", on_delete=models.PROTECT, null=True, blank=True, related_name="billing_profiles",
        verbose_name="Направление",
    )
    plan = models.ForeignKey(BillingPlan, on_delete=models.PROTECT, related_name="profiles", verbose_name="Тариф")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ACTIVE, db_index=True)
    start_date = models.DateField(verbose_name="Начало обучения")
    parent_name = models.CharField(max_length=150, blank=True, verbose_name="Родитель")
    parent_phone = models.CharField(max_length=30, blank=True, verbose_name="Телефон родителя")
    custom_price = models.DecimalField(
        **MONEY, null=True, blank=True, verbose_name="Индивидуальная цена пакета, сом",
        help_text="Пусто — стандартная цена тарифа.",
    )
    discount_type = models.CharField(max_length=10, choices=DiscountType.choices, default=DiscountType.NONE)
    discount_value = models.DecimalField(**MONEY, default=ZERO, verbose_name="Скидка (процент или сумма)")
    discount_reason = models.TextField(blank=True, verbose_name="Основание скидки / цены")
    discount_assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="+",
        verbose_name="Назначил",
    )
    discount_approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="+",
        verbose_name="Согласовал",
    )
    special_terms = models.TextField(blank=True, verbose_name="Особые условия оплаты")
    # Условия договора по программе с продолжительностью (снимок).
    payment_mode = models.CharField(
        max_length=12, choices=PaymentMode.choices, default=PaymentMode.MONTHLY, verbose_name="Способ оплаты курса",
    )
    reservation_allocation = models.CharField(
        max_length=12, choices=ReservationAllocation.choices, default=ReservationAllocation.FIRST_MONTH,
        verbose_name="Учёт брони",
    )
    duration_months = models.PositiveSmallIntegerField(null=True, blank=True, verbose_name="Учебных месяцев")
    lessons_per_month = models.PositiveSmallIntegerField(null=True, blank=True, verbose_name="Уроков в месяце")
    deadline_lessons = models.PositiveSmallIntegerField(null=True, blank=True, verbose_name="Срок оплаты — урок №")
    month_price = models.DecimalField(**MONEY, null=True, blank=True, verbose_name="Стандартная цена месяца")
    standard_course_price = models.DecimalField(
        **MONEY, null=True, blank=True, verbose_name="Стандартная стоимость курса",
    )
    final_course_price = models.DecimalField(**MONEY, null=True, blank=True, verbose_name="Итоговая стоимость курса")
    discount_enabled = models.BooleanField(default=False, verbose_name="Скидка предоставлена")
    discount_amount = models.DecimalField(**MONEY, default=ZERO, verbose_name="Размер скидки, сом")
    responsible_accountant = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="billing_profiles",
        verbose_name="Ответственный бухгалтер",
    )
    stopped_on = models.DateField(null=True, blank=True, verbose_name="Начисления остановлены с")
    stop_reason = models.TextField(blank=True)
    stop_source = models.CharField(max_length=20, choices=StopSource.choices, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Платёжный профиль студента"
        verbose_name_plural = "Платёжные профили студентов"
        ordering = ["student__last_name", "student__first_name", "id"]
        constraints = [
            *_discount_constraints("billing_profile"),
            # Один действующий профиль на студента и направление.
            models.UniqueConstraint(
                fields=["student", "subject"], condition=~Q(status__in=("INACTIVE", "COMPLETED")),
                name="unique_live_billing_contract_subject",
            ),
            models.UniqueConstraint(
                fields=["student"], condition=Q(subject__isnull=True) & ~Q(status__in=("INACTIVE", "COMPLETED")),
                name="unique_live_billing_contract_no_subject",
            ),
            *_course_price_constraints("billing_contract"),
        ]
        indexes = [models.Index(fields=["status", "responsible_accountant"], name="ix_bprofile_status_acc")]

    def __str__(self):
        return f"{self.student} · {self.subject or self.plan}"

    @property
    def is_course(self) -> bool:
        """Договор по программе с продолжительностью (учебные месяцы)."""
        return bool(self.duration_months)

    def delete(self, *args, **kwargs):
        raise ValidationError("Платёжный профиль нельзя удалить — остановите начисления.")


class BillingTermsChange(_NoDelete, models.Model):
    """История индивидуальной цены и скидки профиля: кто назначил, кто
    согласовал, основание. Скидка сверх полномочий менеджера ждёт решения
    администратора (`PENDING`) и до решения не действует."""

    class Status(models.TextChoices):
        PENDING = "PENDING", "Ожидает согласования"
        APPROVED = "APPROVED", "Применено"
        REJECTED = "REJECTED", "Отклонено"

    profile = models.ForeignKey(
        StudentBillingProfile, on_delete=models.PROTECT, related_name="terms_changes", verbose_name="Профиль",
    )
    custom_price = models.DecimalField(**MONEY, null=True, blank=True)
    discount_type = models.CharField(max_length=10, choices=DiscountType.choices, default=DiscountType.NONE)
    discount_value = models.DecimalField(**MONEY, default=ZERO)
    # Условия курса (договор по программе с продолжительностью).
    final_course_price = models.DecimalField(**MONEY, null=True, blank=True)
    discount_enabled = models.BooleanField(default=False)
    discount_amount = models.DecimalField(**MONEY, default=ZERO)
    reason = models.TextField(verbose_name="Основание")
    previous_terms = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, db_index=True)
    requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, related_name="+")
    requested_at = models.DateTimeField(auto_now_add=True)
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="+",
    )
    decided_at = models.DateTimeField(null=True, blank=True)
    decision_comment = models.TextField(blank=True)

    objects = ImmutableQuerySet.as_manager()

    class Meta:
        verbose_name = "Изменение условий оплаты"
        verbose_name_plural = "История условий оплаты"
        ordering = ["-requested_at", "-id"]
        constraints = [
            *_discount_constraints("billing_terms"),
            *_course_price_constraints("billing_terms"),
            models.UniqueConstraint(
                fields=["profile"], condition=Q(status="PENDING"), name="unique_pending_terms_change",
            ),
        ]


# ---------------------------------------------------------------------------
# Пакеты уроков и списания
# ---------------------------------------------------------------------------

class LessonPackage(_NoDelete, models.Model):
    """Пакет уроков студента со снимком цены и условий на момент создания.
    В договоре по программе — учебный месяц №`number`: `lessons_total`
    уроков приоритетного предмета (IT), `lessons_used` — зачтено; история
    переходов — `started_on` / `completed_on` и журнал аудита.

    PLANNED — создан заранее (выставлено начисление или оплачено вперёд),
    ACTIVE — текущий, уроки списываются в него, COMPLETED — все уроки
    использованы, CANCELLED — не начат и отменён (остановка начислений)."""

    class Status(models.TextChoices):
        PLANNED = "PLANNED", "Следующий"
        ACTIVE = "ACTIVE", "Текущий"
        COMPLETED = "COMPLETED", "Использован"
        CANCELLED = "CANCELLED", "Отменён"

    profile = models.ForeignKey(
        StudentBillingProfile, on_delete=models.PROTECT, related_name="packages", verbose_name="Профиль",
    )
    number = models.PositiveIntegerField(verbose_name="№ пакета")
    month_number = models.PositiveSmallIntegerField(
        null=True, blank=True, verbose_name="Учебный месяц №",
        help_text="Номер учебного месяца договора по программе (пусто — тариф без срока).",
    )
    status = models.CharField(max_length=10, choices=Status.choices, db_index=True)
    lessons_total = models.PositiveSmallIntegerField(verbose_name="Уроков в пакете")
    lessons_used = models.PositiveSmallIntegerField(default=0, verbose_name="Использовано уроков")
    plan_version = models.ForeignKey(BillingPlanVersion, on_delete=models.PROTECT, related_name="packages")
    base_price = models.DecimalField(**MONEY, verbose_name="Цена тарифа")
    custom_price = models.DecimalField(**MONEY, null=True, blank=True, verbose_name="Индивидуальная цена")
    discount_type = models.CharField(max_length=10, choices=DiscountType.choices, default=DiscountType.NONE)
    discount_value = models.DecimalField(**MONEY, default=ZERO)
    discount_amount = models.DecimalField(**MONEY, default=ZERO, verbose_name="Скидка, сом")
    final_price = models.DecimalField(**MONEY, verbose_name="К оплате, сом")
    pricing_snapshot = models.JSONField(default=dict, blank=True)
    started_on = models.DateField(null=True, blank=True)
    completed_on = models.DateField(null=True, blank=True)
    ending_notified_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = ImmutableQuerySet.as_manager()

    class Meta:
        verbose_name = "Пакет уроков"
        verbose_name_plural = "Пакеты уроков"
        ordering = ["profile", "number"]
        constraints = [
            models.UniqueConstraint(fields=["profile", "number"], name="unique_billing_package_number"),
            # Один действующий учебный месяц с номером на договор.
            models.UniqueConstraint(
                fields=["profile", "month_number"], condition=Q(month_number__isnull=False) & ~Q(status="CANCELLED"),
                name="unique_billing_study_month",
            ),
            models.UniqueConstraint(
                fields=["profile"], condition=Q(status="ACTIVE"), name="unique_active_billing_package",
            ),
            models.CheckConstraint(condition=Q(lessons_total__gt=0), name="billing_package_lessons_positive"),
            models.CheckConstraint(
                condition=Q(lessons_used__lte=F("lessons_total")), name="billing_package_used_le_total",
            ),
            models.CheckConstraint(condition=Q(final_price__gte=0), name="billing_package_price_non_negative"),
            models.CheckConstraint(condition=Q(discount_amount__gte=0), name="billing_package_discount_non_negative"),
        ]

    def __str__(self):
        return f"{self.profile} · пакет №{self.number} ({self.lessons_used}/{self.lessons_total})"

    @property
    def lessons_remaining(self) -> int:
        return self.lessons_total - self.lessons_used


class LessonConsumption(_NoDelete, models.Model):
    """Списание одного проведённого урока со студента в пакет.

    Повторное списание того же урока невозможно (частичный уникальный
    индекс). Ошибочное списание исправляется сторно: исходная запись
    помечается REVERSED, создаётся запись REVERSAL со ссылкой на неё."""

    class Kind(models.TextChoices):
        CONSUME = "CONSUME", "Списание"
        REVERSAL = "REVERSAL", "Сторно"

    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Действует"
        REVERSED = "REVERSED", "Сторнировано"

    package = models.ForeignKey(LessonPackage, on_delete=models.PROTECT, related_name="consumptions")
    profile = models.ForeignKey(StudentBillingProfile, on_delete=models.PROTECT, related_name="consumptions")
    student = models.ForeignKey("academy.Student", on_delete=models.PROTECT, related_name="lesson_consumptions")
    lesson = models.ForeignKey(
        "academy.Lesson", on_delete=models.SET_NULL, null=True, blank=True, related_name="billing_consumptions",
    )
    lesson_ref = models.PositiveBigIntegerField(help_text="id урока (сохраняется, даже если урок удалён).")
    lesson_date = models.DateField()
    group = models.ForeignKey("academy.Group", on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    kind = models.CharField(max_length=10, choices=Kind.choices, default=Kind.CONSUME)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ACTIVE, db_index=True)
    reversal_of = models.OneToOneField(
        "self", on_delete=models.PROTECT, null=True, blank=True, related_name="reversal",
    )
    reason = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    objects = ImmutableQuerySet.as_manager()

    class Meta:
        verbose_name = "Списание урока"
        verbose_name_plural = "Списания уроков"
        ordering = ["-lesson_date", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["profile", "lesson_ref"], condition=Q(kind="CONSUME", status="ACTIVE"),
                name="unique_active_lesson_consumption",
            ),
            models.CheckConstraint(
                condition=(Q(kind="CONSUME", reversal_of__isnull=True) | Q(kind="REVERSAL", reversal_of__isnull=False)),
                name="billing_consumption_reversal_link",
            ),
        ]
        indexes = [models.Index(fields=["lesson_ref", "kind", "status"], name="ix_bconsume_lesson")]


# ---------------------------------------------------------------------------
# Начисления (счета)
# ---------------------------------------------------------------------------

class Invoice(models.Model):
    """Начисление за пакет уроков. Сумма — снимок цены пакета.

    Остаток = сумма − действующие распределения платежей − применённые
    корректировки. `amount_paid`/`amount_adjusted` — кеш этих сумм,
    обновляется только сервисом под блокировкой профиля (сверка —
    `services.invoices.calculate_invoice_balance`)."""

    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Черновик"
        OPEN = "OPEN", "Ожидает оплаты"
        PARTIALLY_PAID = "PARTIALLY_PAID", "Частично оплачено"
        PAID = "PAID", "Оплачено"
        OVERDUE = "OVERDUE", "Просрочено"
        VOID = "VOID", "Аннулировано"

    UNPAID_STATUSES = (Status.OPEN, Status.PARTIALLY_PAID, Status.OVERDUE)

    class Kind(models.TextChoices):
        PACKAGE = "PACKAGE", "Пакет уроков"
        MONTH = "MONTH", "Учебный месяц"
        COURSE = "COURSE", "Весь курс (предоплата)"

    profile = models.ForeignKey(StudentBillingProfile, on_delete=models.PROTECT, related_name="invoices")
    kind = models.CharField(max_length=10, choices=Kind.choices, default=Kind.PACKAGE, verbose_name="Назначение")
    # Срок оплаты в уроках: начисление должно быть оплачено не позднее
    # `due_lesson`-го зачтённого урока своего месяца; со следующего —
    # просрочка. Пусто — срок по дате (`due_date`, тарифы без программы).
    due_lesson = models.PositiveSmallIntegerField(null=True, blank=True, verbose_name="Срок — урок №")
    due_reached_on = models.DateField(null=True, blank=True, db_index=True, verbose_name="Срок наступил")
    overdue_since = models.DateField(null=True, blank=True, verbose_name="Просрочено с")
    package = models.ForeignKey(LessonPackage, on_delete=models.PROTECT, related_name="invoices")
    number = models.CharField(max_length=30, unique=True, null=True, blank=True, verbose_name="Номер")
    business_key = models.CharField(
        max_length=80, unique=True, help_text="Уникальный бизнес-ключ: повторный запуск не создаёт дубль.",
    )
    amount = models.DecimalField(**MONEY, verbose_name="Сумма начисления")
    amount_paid = models.DecimalField(**MONEY, default=ZERO, verbose_name="Оплачено")
    amount_adjusted = models.DecimalField(**MONEY, default=ZERO, verbose_name="Корректировки")
    currency = models.CharField(max_length=3, default=CURRENCY, editable=False)
    status = models.CharField(max_length=20, choices=Status.choices, db_index=True)
    issue_date = models.DateField(verbose_name="Дата начисления")
    # Учебный / финансовый период, к которому относится начисление: начало
    # договора для первого месяца, дата урока, которым закончился предыдущий
    # учебный месяц, — для следующих. Не дата создания записи (`created_at`)
    # и не дата выставления: договор, оформленный в октябре задним числом с
    # 1 сентября, начисляет сентябрь. Фиксируется при создании; исправляется
    # только `invoices.correct_invoice_period` с основанием и аудитом.
    period_date = models.DateField(db_index=True, verbose_name="Период начисления")
    due_date = models.DateField(db_index=True, verbose_name="Срок оплаты")
    snapshot = models.JSONField(default=dict, blank=True, verbose_name="Условия на момент начисления")
    paid_at = models.DateTimeField(null=True, blank=True)
    void_reason = models.TextField(blank=True)
    voided_at = models.DateTimeField(null=True, blank=True)
    voided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="+",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = ImmutableQuerySet.as_manager()

    class Meta:
        verbose_name = "Начисление"
        verbose_name_plural = "Начисления"
        ordering = ["-issue_date", "-id"]
        constraints = [
            # Одно действующее начисление на пакет.
            models.UniqueConstraint(fields=["package"], condition=~Q(status="VOID"), name="unique_live_invoice_package"),
            models.CheckConstraint(condition=Q(amount__gte=0), name="billing_invoice_amount_non_negative"),
            models.CheckConstraint(condition=Q(amount_paid__gte=0), name="billing_invoice_paid_non_negative"),
            models.CheckConstraint(condition=Q(amount_adjusted__gte=0), name="billing_invoice_adjusted_non_negative"),
            models.CheckConstraint(
                condition=Q(amount__gte=F("amount_paid") + F("amount_adjusted")), name="billing_invoice_no_overpay",
            ),
            models.CheckConstraint(condition=Q(due_date__gte=F("issue_date")), name="billing_invoice_due_after_issue"),
            models.CheckConstraint(
                condition=Q(due_lesson__isnull=True) | Q(due_lesson__gt=0), name="billing_invoice_due_lesson_positive",
            ),
        ]
        indexes = [
            models.Index(fields=["status", "due_date"], name="ix_binvoice_status_due"),
            models.Index(fields=["profile", "status"], name="ix_binvoice_profile_status"),
        ]

    def __str__(self):
        return f"{self.number or self.business_key} · {self.amount} сом · {self.get_status_display()}"

    @property
    def balance(self) -> Decimal:
        return self.amount - self.amount_paid - self.amount_adjusted

    def delete(self, *args, **kwargs):
        raise ValidationError("Начисление нельзя удалить — аннулируйте его.")


class InvoiceAdjustment(_NoDelete, models.Model):
    """Корректировка начисления (списание долга, перерасчёт) — уменьшает
    остаток, не меняя исходную сумму. Отменяется, а не удаляется."""

    class Status(models.TextChoices):
        APPLIED = "APPLIED", "Применена"
        VOID = "VOID", "Отменена"

    invoice = models.ForeignKey(Invoice, on_delete=models.PROTECT, related_name="adjustments")
    amount = models.DecimalField(**MONEY, validators=[MinValueValidator(Decimal("0.01"))])
    reason = models.TextField()
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.APPLIED)
    # Дата, на которую корректировка уменьшает долг (историческая задолженность
    # считается по ней), — отдельно от времени записи в системе (`created_at`).
    effective_date = models.DateField(db_index=True, verbose_name="Дата корректировки")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    voided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="+",
    )
    voided_at = models.DateTimeField(null=True, blank=True)
    void_reason = models.TextField(blank=True)

    objects = ImmutableQuerySet.as_manager()

    class Meta:
        verbose_name = "Корректировка начисления"
        verbose_name_plural = "Корректировки начислений"
        ordering = ["-created_at", "-id"]
        constraints = [models.CheckConstraint(condition=Q(amount__gt=0), name="billing_adjustment_positive")]


# ---------------------------------------------------------------------------
# Деньги: распределение платежей и аванс
# ---------------------------------------------------------------------------

class PaymentAllocation(_NoDelete, models.Model):
    """Часть платежа (`accounting.StudentPayment`), направленная на
    начисление. Сумма самого платежа не меняется. Ошибочное распределение
    сторнируется (REVERSED) — деньги возвращаются в аванс."""

    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Действует"
        REVERSED = "REVERSED", "Сторнировано"

    class Source(models.TextChoices):
        PAYMENT = "PAYMENT", "При поступлении платежа"
        CREDIT = "CREDIT", "Из аванса"
        MANUAL = "MANUAL", "Вручную бухгалтером"

    payment = models.ForeignKey(
        "accounting.StudentPayment", on_delete=models.PROTECT, related_name="billing_allocations",
    )
    invoice = models.ForeignKey(Invoice, on_delete=models.PROTECT, related_name="allocations")
    profile = models.ForeignKey(StudentBillingProfile, on_delete=models.PROTECT, related_name="allocations")
    amount = models.DecimalField(**MONEY, validators=[MinValueValidator(Decimal("0.01"))])
    source = models.CharField(max_length=10, choices=Source.choices)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ACTIVE, db_index=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    reversed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="+",
    )
    reversed_at = models.DateTimeField(null=True, blank=True)
    reverse_reason = models.TextField(blank=True)

    objects = ImmutableQuerySet.as_manager()

    class Meta:
        verbose_name = "Распределение платежа"
        verbose_name_plural = "Распределения платежей"
        ordering = ["-created_at", "-id"]
        constraints = [models.CheckConstraint(condition=Q(amount__gt=0), name="billing_allocation_positive")]
        indexes = [models.Index(fields=["payment", "status"], name="ix_balloc_payment_status")]


class CreditLedgerEntry(_NoDelete, models.Model):
    """Журнал аванса профиля (только добавление). Доступный аванс = сумма
    записей. Платёж приходит целиком (+), распределение на начисление
    списывает (−), сторно распределения возвращает (+), возврат денег и
    удержание брони списывают (−). Поэтому одни и те же деньги никогда не
    числятся одновременно и оплатой начисления, и свободным авансом."""

    class Kind(models.TextChoices):
        PAYMENT_IN = "PAYMENT_IN", "Поступление"
        ALLOCATION = "ALLOCATION", "Оплата начисления"
        ALLOCATION_REVERSAL = "ALLOCATION_REVERSAL", "Сторно оплаты начисления"
        REFUND = "REFUND", "Возврат денег"
        RETENTION = "RETENTION", "Удержание брони"
        PAYMENT_VOID = "PAYMENT_VOID", "Отмена платежа"
        REFUND_REVERSAL = "REFUND_REVERSAL", "Отмена возврата"

    SIGN = {
        Kind.PAYMENT_IN: 1, Kind.ALLOCATION: -1, Kind.ALLOCATION_REVERSAL: 1, Kind.REFUND: -1,
        Kind.RETENTION: -1, Kind.PAYMENT_VOID: -1, Kind.REFUND_REVERSAL: 1,
    }

    profile = models.ForeignKey(StudentBillingProfile, on_delete=models.PROTECT, related_name="credit_entries")
    kind = models.CharField(max_length=20, choices=Kind.choices, db_index=True)
    amount = models.DecimalField(**MONEY, help_text="Со знаком: + пополняет аванс, − уменьшает.")
    payment = models.ForeignKey(
        "accounting.StudentPayment", on_delete=models.PROTECT, null=True, blank=True, related_name="credit_entries",
    )
    allocation = models.ForeignKey(
        PaymentAllocation, on_delete=models.PROTECT, null=True, blank=True, related_name="credit_entries",
    )
    refund = models.ForeignKey(
        "accounting.StudentPayment", on_delete=models.PROTECT, null=True, blank=True, related_name="+",
        help_text="Возврат (StudentPayment kind=refund), к которому относится запись.",
    )
    reservation = models.ForeignKey(
        "Reservation", on_delete=models.PROTECT, null=True, blank=True, related_name="credit_entries",
    )
    comment = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    objects = ImmutableQuerySet.as_manager()

    class Meta:
        verbose_name = "Запись аванса"
        verbose_name_plural = "Журнал авансов"
        ordering = ["-created_at", "-id"]
        constraints = [
            models.CheckConstraint(condition=~Q(amount=0), name="billing_credit_non_zero"),
            models.CheckConstraint(
                condition=(Q(kind__in=("PAYMENT_IN", "ALLOCATION_REVERSAL", "REFUND_REVERSAL"), amount__gt=0)
                           | Q(kind__in=("ALLOCATION", "REFUND", "RETENTION", "PAYMENT_VOID"), amount__lt=0)),
                name="billing_credit_sign",
            ),
            models.UniqueConstraint(
                fields=["allocation", "kind"], condition=Q(allocation__isnull=False), name="unique_credit_allocation_kind",
            ),
            models.UniqueConstraint(
                fields=["payment"], condition=Q(kind="PAYMENT_IN"), name="unique_credit_payment_in",
            ),
            models.UniqueConstraint(
                fields=["payment"], condition=Q(kind="PAYMENT_VOID"), name="unique_credit_payment_void",
            ),
            models.UniqueConstraint(
                fields=["refund", "kind"], condition=Q(refund__isnull=False), name="unique_credit_refund_kind",
            ),
        ]
        indexes = [models.Index(fields=["profile", "created_at"], name="ix_bcredit_profile")]

    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise ValidationError("Запись журнала аванса нельзя изменить.")
        super().save(*args, **kwargs)


class Reservation(models.Model):
    """Бронь места — отдельная от оплаты обучения операция. Оплаченная бронь
    становится авансом профиля; при отмене неиспользованная часть
    возвращается и/или удерживается по решению бухгалтера с основанием."""

    class Status(models.TextChoices):
        PENDING = "PENDING", "Ожидает оплаты"
        PAID = "PAID", "Оплачена (аванс)"
        CANCELLED = "CANCELLED", "Отменена"

    profile = models.ForeignKey(StudentBillingProfile, on_delete=models.PROTECT, related_name="reservations")
    group = models.ForeignKey(
        "academy.Group", on_delete=models.PROTECT, null=True, blank=True, related_name="billing_reservations",
    )
    expected_amount = models.DecimalField(**MONEY, validators=[MinValueValidator(Decimal("0.01"))])
    reserved_until = models.DateField(null=True, blank=True, verbose_name="Бронь до")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING, db_index=True)
    payment = models.OneToOneField(
        "accounting.StudentPayment", on_delete=models.PROTECT, null=True, blank=True, related_name="reservation",
    )
    comment = models.TextField(blank=True)
    refunded_amount = models.DecimalField(**MONEY, default=ZERO)
    retained_amount = models.DecimalField(**MONEY, default=ZERO)
    cancel_reason = models.TextField(blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancelled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="+",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Бронь"
        verbose_name_plural = "Брони"
        ordering = ["-created_at", "-id"]
        constraints = [
            models.CheckConstraint(condition=Q(expected_amount__gt=0), name="billing_reservation_amount_positive"),
            models.CheckConstraint(
                condition=Q(refunded_amount__gte=0) & Q(retained_amount__gte=0), name="billing_reservation_non_negative",
            ),
            models.UniqueConstraint(
                fields=["profile"], condition=Q(status__in=("PENDING", "PAID")), name="unique_live_reservation",
            ),
        ]

    def delete(self, *args, **kwargs):
        raise ValidationError("Бронь нельзя удалить — отмените её.")


# ---------------------------------------------------------------------------
# Работа бухгалтера: задачи, журнал контактов, уведомления
# ---------------------------------------------------------------------------

class BillingTask(models.Model):
    """Задача бухгалтеру по неоплаченному начислению. Закрывается
    автоматически, когда начисление оплачено или аннулировано."""

    class Kind(models.TextChoices):
        COLLECT_PAYMENT = "COLLECT_PAYMENT", "Получить оплату"

    class Status(models.TextChoices):
        OPEN = "OPEN", "Открыта"
        PROMISED = "PROMISED", "Обещана оплата"
        DISPUTE = "DISPUTE", "Спор по начислению"
        DONE = "DONE", "Выполнена"
        CANCELLED = "CANCELLED", "Отменена"

    LIVE_STATUSES = (Status.OPEN, Status.PROMISED, Status.DISPUTE)

    kind = models.CharField(max_length=20, choices=Kind.choices, default=Kind.COLLECT_PAYMENT)
    invoice = models.ForeignKey(Invoice, on_delete=models.PROTECT, related_name="tasks")
    profile = models.ForeignKey(StudentBillingProfile, on_delete=models.PROTECT, related_name="tasks")
    assignee = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="billing_tasks",
    )
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.OPEN, db_index=True)
    promised_date = models.DateField(null=True, blank=True)
    next_contact_date = models.DateField(null=True, blank=True, db_index=True)
    last_contact_at = models.DateTimeField(null=True, blank=True)
    close_reason = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    closed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Задача бухгалтера"
        verbose_name_plural = "Задачи бухгалтера"
        ordering = ["next_contact_date", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["invoice", "kind"], condition=Q(status__in=("OPEN", "PROMISED", "DISPUTE")),
                name="unique_live_billing_task",
            ),
        ]

    def delete(self, *args, **kwargs):
        raise ValidationError("Задачу нельзя удалить.")


class BillingContactLog(_NoDelete, models.Model):
    """Журнал контактов бухгалтера с родителями. Только добавление: каждый
    контакт — новая запись, история не перезаписывается."""

    class Channel(models.TextChoices):
        CALL = "CALL", "Звонок"
        TELEGRAM = "TELEGRAM", "Telegram"
        WHATSAPP = "WHATSAPP", "WhatsApp"
        OTHER = "OTHER", "Другое"

    class Result(models.TextChoices):
        ANSWERED = "ANSWERED", "Ответил"
        NO_ANSWER = "NO_ANSWER", "Не ответил"
        PROMISED = "PROMISED", "Обещал оплатить"
        PAID = "PAID", "Оплата получена"
        DISPUTE = "DISPUTE", "Спор по начислению"
        FOLLOW_UP = "FOLLOW_UP", "Требуется повторный контакт"

    profile = models.ForeignKey(StudentBillingProfile, on_delete=models.PROTECT, related_name="contacts")
    student = models.ForeignKey("academy.Student", on_delete=models.PROTECT, related_name="billing_contacts")
    invoice = models.ForeignKey(Invoice, on_delete=models.PROTECT, null=True, blank=True, related_name="contacts")
    task = models.ForeignKey(BillingTask, on_delete=models.PROTECT, null=True, blank=True, related_name="contacts")
    staff = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="billing_contacts")
    contacted_at = models.DateTimeField(db_index=True)
    channel = models.CharField(max_length=10, choices=Channel.choices)
    result = models.CharField(max_length=10, choices=Result.choices)
    comment = models.TextField(blank=True)
    promised_payment_date = models.DateField(null=True, blank=True)
    next_contact_date = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = ImmutableQuerySet.as_manager()

    class Meta:
        verbose_name = "Контакт с родителем"
        verbose_name_plural = "Журнал контактов с родителями"
        ordering = ["-contacted_at", "-id"]
        constraints = [
            models.CheckConstraint(
                condition=~Q(result="PROMISED") | Q(promised_payment_date__isnull=False),
                name="billing_contact_promise_date",
            ),
        ]

    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise ValidationError("Запись журнала контактов нельзя изменить — добавьте новую.")
        super().save(*args, **kwargs)


class BillingNotification(models.Model):
    """Уведомление бухгалтеру — transactional outbox: создаётся в той же
    транзакции, что и событие (откат — уведомления нет), доставляется после
    коммита. `dedup_key` не даёт повторному запуску задач продублировать
    уведомление."""

    class Kind(models.TextChoices):
        PACKAGE_ENDING = "PACKAGE_ENDING", "Пакет скоро закончится"
        PACKAGE_COMPLETED = "PACKAGE_COMPLETED", "Пакет использован"
        INVOICE_CREATED = "INVOICE_CREATED", "Новое начисление"
        INVOICE_PAID = "INVOICE_PAID", "Начисление оплачено"
        OVERDUE = "OVERDUE", "Просрочка"
        PAYMENT_DEADLINE = "PAYMENT_DEADLINE", "Последний срок оплаты"
        FOLLOW_UP = "FOLLOW_UP", "Повторный контакт"
        DISCOUNT_APPROVAL = "DISCOUNT_APPROVAL", "Скидка ждёт согласования"
        REPORT = "REPORT", "Финансовый отчёт"

    class Status(models.TextChoices):
        PENDING = "PENDING", "Ожидает отправки"
        SENT = "SENT", "Отправлено"
        FAILED = "FAILED", "Ошибка"

    kind = models.CharField(max_length=20, choices=Kind.choices, db_index=True)
    dedup_key = models.CharField(max_length=120, unique=True)
    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="billing_notifications",
        help_text="Пусто — всем бухгалтерам.",
    )
    profile = models.ForeignKey(
        StudentBillingProfile, on_delete=models.PROTECT, null=True, blank=True, related_name="notifications",
    )
    invoice = models.ForeignKey(Invoice, on_delete=models.PROTECT, null=True, blank=True, related_name="notifications")
    title = models.CharField(max_length=200)
    message = models.TextField(blank=True)
    payload = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING, db_index=True)
    attempts = models.PositiveSmallIntegerField(default=0)
    last_error = models.TextField(blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    read_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = "Уведомление бухгалтерии"
        verbose_name_plural = "Уведомления бухгалтерии"
        ordering = ["-created_at", "-id"]


class BillingEvent(models.Model):
    """Журнал обработки событий и запусков фоновых задач: что обработано,
    сколько попыток, результат или ошибка. Ключ уникален — повторный запуск
    той же обработки обновляет запись, а не создаёт новую."""

    class Status(models.TextChoices):
        PROCESSING = "PROCESSING", "Обрабатывается"
        DONE = "DONE", "Обработано"
        FAILED = "FAILED", "Ошибка"

    key = models.CharField(max_length=150, unique=True)
    kind = models.CharField(max_length=40, db_index=True)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PROCESSING, db_index=True)
    attempts = models.PositiveIntegerField(default=0)
    result = models.JSONField(default=dict, blank=True)
    error = models.TextField(blank=True)
    run_id = models.UUIDField(default=uuid.uuid4)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    processed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Событие обработки"
        verbose_name_plural = "Журнал обработки событий"
        ordering = ["-updated_at", "-id"]


# ---------------------------------------------------------------------------
# Чеки
# ---------------------------------------------------------------------------

class Receipt(_NoDelete, models.Model):
    """Внутренний чек Okurmen Kids на зарегистрированную операцию (платёж или
    возврат) — не фискальный документ. Создаётся в той же транзакции, что и
    платёж; суммы на момент операции хранятся в `snapshot`, поэтому повторная
    печать показывает ровно ту операцию и не создаёт ни платежа, ни чека.
    Отмена платежа помечает чек «Аннулирован», запись остаётся."""

    class Kind(models.TextChoices):
        PAYMENT = "PAYMENT", "Приём оплаты"
        REFUND = "REFUND", "Возврат"

    class Status(models.TextChoices):
        ISSUED = "ISSUED", "Выдан"
        CANCELLED = "CANCELLED", "Аннулирован"

    payment = models.OneToOneField(
        "accounting.StudentPayment", on_delete=models.PROTECT, related_name="receipt", verbose_name="Операция",
    )
    profile = models.ForeignKey(StudentBillingProfile, on_delete=models.PROTECT, related_name="receipts")
    number = models.CharField(max_length=30, unique=True, null=True, blank=True, verbose_name="Номер чека")
    kind = models.CharField(max_length=10, choices=Kind.choices, default=Kind.PAYMENT)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ISSUED, db_index=True)
    payer_name = models.CharField(max_length=150, blank=True, verbose_name="Плательщик")
    snapshot = models.JSONField(default=dict, blank=True, verbose_name="Данные чека на момент операции")
    issued_at = models.DateTimeField(auto_now_add=True, db_index=True)
    issued_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="+",
    )
    print_count = models.PositiveIntegerField(default=0)
    last_printed_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancel_reason = models.TextField(blank=True)

    objects = ImmutableQuerySet.as_manager()

    class Meta:
        verbose_name = "Чек"
        verbose_name_plural = "Чеки"
        ordering = ["-issued_at", "-id"]

    def __str__(self):
        return self.number or f"Чек #{self.pk}"


# ---------------------------------------------------------------------------
# Настройки финансового модуля
# ---------------------------------------------------------------------------

class BillingSettings(models.Model):
    """Глобальные настройки оплаты (одна запись, id=1). Меняет бухгалтер;
    каждое изменение — в журнале аудита. Пусто — значения из settings.py."""

    manager_max_discount_percent = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal("10.00"),
        validators=[MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("100"))],
        verbose_name="Скидка менеджера без согласования, %",
    )
    due_soon_lessons = models.PositiveSmallIntegerField(
        default=3, verbose_name="«Скоро оплата» — за N уроков до конца месяца",
    )
    default_deadline_lessons = models.PositiveSmallIntegerField(
        default=3, validators=[MinValueValidator(1)], verbose_name="Срок оплаты для новых программ — урок №",
    )
    accountant_refund_limit = models.DecimalField(
        **MONEY, null=True, blank=True, verbose_name="Возврат без согласования — до, сом",
    )
    academy_name = models.CharField(max_length=150, default="Okurmen Kids", verbose_name="Название в чеке")
    academy_details = models.TextField(blank=True, verbose_name="Реквизиты / адрес / телефон для чека")
    receipt_footer = models.TextField(
        blank=True, default="Спасибо за оплату! Сохраните чек до конца обучения.", verbose_name="Подпись в чеке",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="+",
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Настройки оплаты"
        verbose_name_plural = "Настройки оплаты"
        constraints = [models.CheckConstraint(condition=Q(id=1), name="billing_settings_singleton")]

    def __str__(self):
        return "Настройки оплаты"

    def delete(self, *args, **kwargs):
        raise ValidationError("Настройки нельзя удалить.")

    @classmethod
    def load(cls) -> "BillingSettings":
        obj = cls.objects.filter(pk=1).first()
        if obj is None:
            obj, _ = cls.objects.get_or_create(pk=1, defaults={
                "manager_max_discount_percent": Decimal(str(getattr(settings, "BILLING_MANAGER_MAX_DISCOUNT_PERCENT", 10))),
                "accountant_refund_limit": (
                    Decimal(str(settings.BILLING_ACCOUNTANT_REFUND_LIMIT))
                    if getattr(settings, "BILLING_ACCOUNTANT_REFUND_LIMIT", None) not in (None, "") else None
                ),
            })
        return obj
