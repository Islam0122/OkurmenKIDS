"""Бухгалтерия и расчёт зарплат OkurmenKIDS.

Источники данных переиспользуются из LMS: сотрудник — это `users.User`
(тренер — через его `academy.Teacher`), программа — `academy.Course`,
группа — `academy.Group`, студент — `academy.Student`, история активности
студента — `academy.StudentStatusEvent`, история тренеров группы —
`academy.TrainerAssignment`.

Единственная новая «первичная» сущность — `StudentPayment`: до этого модуля
в проекте не было ни одной модели оплат студентов (см. комментарий над
`academy.StudentStatusEvent`), а процент тренера считается именно от
фактических платежей.

Финансовые записи никогда не удаляются физически: платежи, выплаты и
корректировки отменяются (status=VOID) с причиной, всё пишется в
`PayrollAuditLog`. Все суммы — `Decimal` в сомах (KGS).
"""
from __future__ import annotations

import calendar
import datetime as dt
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

CURRENCY = "KGS"
MONEY = {"max_digits": 14, "decimal_places": 2}
ZERO = Decimal("0.00")


class ImmutableQuerySet(models.QuerySet):
    """Финансовые записи не удаляются массово (admin, shell, каскады)."""

    def delete(self):  # pragma: no cover - guarded by tests through the model
        raise ValidationError("Финансовые записи нельзя удалять — используйте отмену (VOID).")


# ---------------------------------------------------------------------------
# Платежи студентов
# ---------------------------------------------------------------------------

class StudentPayment(models.Model):
    """Фактический платёж студента за обучение (или возврат по нему).

    Различаются три даты: `received_date` — когда деньги реально поступили
    (или вернулись — для возврата); `service_start`/`service_end` — период
    обучения, за который заплачено. Платёж за несколько месяцев — одна
    запись с длинным периодом обучения: в зарплату он попадает один раз
    (по дате поступления) или распределяется по дням периода обучения —
    смотря по правилу признания выручки в `SalaryRule.revenue_basis`.

    Возврат — отдельная запись kind=REFUND, обязательно ссылающаяся на
    исходный платёж (`refund_of`): так всегда известно, к какому платежу
    (и через него — к какому начислению) он относится.
    """

    class Kind(models.TextChoices):
        PAYMENT = "payment", "Оплата"
        REFUND = "refund", "Возврат"

    class Status(models.TextChoices):
        CONFIRMED = "confirmed", "Подтверждён"
        VOID = "void", "Отменён"

    class Method(models.TextChoices):
        CASH = "cash", "Наличные"
        BANK = "bank", "Банковский перевод"
        CARD = "card", "Карта / QR"
        OTHER = "other", "Другое"

    student = models.ForeignKey(
        "academy.Student", on_delete=models.PROTECT, related_name="payments", verbose_name="Студент",
    )
    group = models.ForeignKey(
        "academy.Group", on_delete=models.PROTECT, related_name="student_payments", verbose_name="Группа",
        help_text="Группа, за обучение в которой оплачено.",
    )
    course = models.ForeignKey(
        "academy.Course", on_delete=models.PROTECT, related_name="student_payments", verbose_name="Программа",
        help_text="Заполняется автоматически из группы.",
    )
    kind = models.CharField(max_length=10, choices=Kind.choices, default=Kind.PAYMENT, verbose_name="Тип")
    amount = models.DecimalField(
        **MONEY, validators=[MinValueValidator(Decimal("0.01"))], verbose_name="Сумма, сом",
        help_text="Всегда положительная; для возврата знак задаёт тип операции.",
    )
    currency = models.CharField(max_length=3, default=CURRENCY, editable=False, verbose_name="Валюта")
    received_date = models.DateField(db_index=True, verbose_name="Дата поступления / возврата")
    service_start = models.DateField(verbose_name="Обучение с")
    service_end = models.DateField(verbose_name="Обучение по")
    refund_of = models.ForeignKey(
        "self", on_delete=models.PROTECT, null=True, blank=True, related_name="refunds",
        verbose_name="Возврат по платежу",
    )
    method = models.CharField(max_length=10, choices=Method.choices, default=Method.CASH, verbose_name="Способ")
    reference = models.CharField(max_length=100, blank=True, verbose_name="Номер документа")
    comment = models.TextField(blank=True, verbose_name="Комментарий")
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.CONFIRMED, db_index=True, verbose_name="Статус",
    )
    void_reason = models.TextField(blank=True, verbose_name="Причина отмены")
    idempotency_key = models.CharField(max_length=64, null=True, blank=True, unique=True, editable=False)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+", verbose_name="Кто внёс",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Создано")
    voided_at = models.DateTimeField(null=True, blank=True, verbose_name="Отменено")
    voided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="+",
        verbose_name="Кто отменил",
    )

    objects = ImmutableQuerySet.as_manager()

    class Meta:
        verbose_name = "Платёж студента"
        verbose_name_plural = "Платежи студентов"
        ordering = ["-received_date", "-id"]
        indexes = [
            models.Index(fields=["group", "received_date"], name="ix_stpay_group_date"),
            models.Index(fields=["course", "received_date"], name="ix_stpay_course_date"),
        ]
        constraints = [
            models.CheckConstraint(condition=models.Q(amount__gt=0), name="student_payment_amount_positive"),
            models.CheckConstraint(
                condition=models.Q(service_end__gte=models.F("service_start")), name="student_payment_service_range",
            ),
            models.CheckConstraint(
                condition=(models.Q(kind="refund", refund_of__isnull=False) | models.Q(kind="payment", refund_of__isnull=True)),
                name="student_payment_refund_link",
            ),
        ]

    def __str__(self):
        sign = "−" if self.kind == self.Kind.REFUND else ""
        return f"{self.student} · {sign}{self.amount} сом · {self.received_date:%d.%m.%Y}"

    @property
    def signed_amount(self) -> Decimal:
        return -self.amount if self.kind == self.Kind.REFUND else self.amount

    def delete(self, *args, **kwargs):
        raise ValidationError("Платёж нельзя удалить — отмените его с указанием причины.")


# ---------------------------------------------------------------------------
# Зарплатные настройки
# ---------------------------------------------------------------------------

class SalaryType(models.TextChoices):
    """Разрешены только два типа оплаты: оклад или процент от стоимости
    курса. Комбинированной схемы нет. Остальные значения — устаревшие (из
    первой версии модуля): остаются в истории, новые записи их не получают,
    а расчёт по ним выдаёт ошибку."""

    FIXED = "FIXED", "Фиксированный оклад"
    PERCENT = "PERCENT", "Процент от стоимости курса"
    REVENUE_PERCENT = "REVENUE_PERCENT", "Процент от оплаты студентов (устар.)"
    PER_STUDENT = "PER_STUDENT", "За активного студента (устар.)"
    PER_GROUP = "PER_GROUP", "За группу (устар.)"
    COMBINED = "COMBINED", "Комбинированная схема (устар.)"


ALLOWED_SALARY_TYPES = (SalaryType.FIXED, SalaryType.PERCENT)


class Department(models.TextChoices):
    """Направление сотрудника — разрез аналитики директора (расходы по
    направлениям). В LMS такого поля нет, поэтому его ведёт бухгалтер в
    зарплатном профиле; в каждом расчёте хранится снимок."""

    IT = "IT", "IT"
    SOFT_SKILLS = "SOFT_SKILLS", "Soft Skills"
    ENGLISH = "ENGLISH", "Английский"
    TEAM_LEAD = "TEAM_LEAD", "Тимлиды"
    ASSISTANT = "ASSISTANT", "Ассистенты"
    OTHER = "OTHER", "Прочий персонал"


def default_department(user) -> str:
    """Направление по роли, если бухгалтер его не указал: Team Lead и
    Ассистент однозначны, остальным — «Прочий персонал» (тренера по роли
    не отнести к IT / Soft Skills / английскому — это решает бухгалтер)."""
    role = getattr(user, "role", None)
    if role == "team_lead":
        return Department.TEAM_LEAD
    if role == "assistant":
        return Department.ASSISTANT
    return Department.OTHER


class EmployeeSalaryProfile(models.Model):
    """Зарплатная карточка сотрудника. Ставки живут в `SalaryRule` —
    у каждой своя версия и срок действия, поэтому изменение ставки никогда
    не переписывает условия уже рассчитанных периодов."""

    employee = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="salary_profile", verbose_name="Сотрудник",
    )
    position = models.CharField(
        max_length=100, blank=True, verbose_name="Должность",
        help_text="Пусто — должность из профиля тренера или роль пользователя.",
    )
    salary_type = models.CharField(max_length=20, choices=SalaryType.choices, verbose_name="Тип оплаты")
    department = models.CharField(
        max_length=20, choices=Department.choices, blank=True, verbose_name="Направление",
        help_text="Пусто — по роли: Team Lead, Ассистент, иначе «Прочий персонал».",
    )
    currency = models.CharField(max_length=3, default=CURRENCY, editable=False, verbose_name="Валюта")
    is_active = models.BooleanField(default=True, db_index=True, verbose_name="Активна")
    effective_from = models.DateField(verbose_name="Действует с")
    effective_to = models.DateField(null=True, blank=True, verbose_name="Действует по")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Зарплатный профиль"
        verbose_name_plural = "Зарплатные профили"
        ordering = ["employee__last_name", "employee__first_name"]

    def __str__(self):
        return f"{self.employee} · {self.get_salary_type_display()}"

    @property
    def display_position(self) -> str:
        if self.position:
            return self.position
        teacher = getattr(self.employee, "teacher_profile", None)
        if teacher is not None:
            return teacher.position
        return self.employee.get_role_display()

    @property
    def effective_department(self) -> str:
        return self.department or default_department(self.employee)

    def clean(self):
        if self.effective_to and self.effective_to < self.effective_from:
            raise ValidationError({"effective_to": "Дата окончания раньше даты начала."})
        if self.salary_type not in ALLOWED_SALARY_TYPES:
            raise ValidationError({"salary_type": "Допустимы только «Фиксированный оклад» и «Процент от стоимости курса»."})


class SalaryRule(models.Model):
    """Одна версия одного правила начисления.

    Правило не редактируется после создания: новая ставка — новая версия
    (`previous_version` → старая версия закрывается датой). Строки расчёта
    хранят снимок ставки, так что утверждённые начисления не зависят от
    последующих изменений.
    """

    class RuleType(models.TextChoices):
        FIXED = "FIXED", "Оклад"
        PERCENT = "PERCENT", "Процент от стоимости курса"
        # Устаревшие типы первой версии — только история, не рассчитываются.
        REVENUE_PERCENT = "REVENUE_PERCENT", "Процент от оплаты студентов (устар.)"
        PER_STUDENT = "PER_STUDENT", "За активного студента (устар.)"
        PER_GROUP = "PER_GROUP", "За группу (устар.)"
        BONUS = "BONUS", "Дополнительное начисление (устар.)"

    class Method(models.TextChoices):
        # FIXED: полная сумма за календарный месяц
        MONTHLY = "MONTHLY", "Полный месячный оклад"
        # Устаревшие методы оклада (делили оклад на половины месяца) — только история
        SPLIT = "SPLIT", "Доля месячной суммы в каждой половине (по умолчанию 50/50)"
        PRORATE_DAYS = "PRORATE_DAYS", "Пропорционально календарным дням"
        # PER_STUDENT
        STUDENT_DAYS = "STUDENT_DAYS", "По дням активности каждого студента"
        SNAPSHOT = "SNAPSHOT", "По числу студентов на контрольную дату (конец периода)"
        # REVENUE_PERCENT / BONUS
        STANDARD = "STANDARD", "Стандартный"

    class RevenueBasis(models.TextChoices):
        RECEIVED = "RECEIVED", "Фактически полученные платежи (по дате поступления)"
        ALLOCATED = "ALLOCATED", "Распределённая выручка (по дням периода обучения)"

    class RefundPolicy(models.TextChoices):
        DEDUCT = "DEDUCT", "Вычитать в периоде возврата (со ссылкой на исходный платёж)"
        IGNORE = "IGNORE", "Не учитывать возвраты в зарплате"

    ACTIVE_TYPES = (RuleType.FIXED, RuleType.PERCENT)

    METHODS_BY_TYPE = {
        RuleType.FIXED: (Method.MONTHLY,),
        RuleType.PERCENT: (Method.STANDARD,),
        RuleType.PER_GROUP: (Method.PRORATE_DAYS, Method.SPLIT),
        RuleType.PER_STUDENT: (Method.STUDENT_DAYS, Method.SNAPSHOT),
        RuleType.REVENUE_PERCENT: (Method.STANDARD,),
        RuleType.BONUS: (Method.STANDARD,),
    }

    employee_profile = models.ForeignKey(
        EmployeeSalaryProfile, on_delete=models.PROTECT, related_name="rules", verbose_name="Профиль",
    )
    rule_type = models.CharField(max_length=20, choices=RuleType.choices, verbose_name="Тип правила")
    amount = models.DecimalField(
        **MONEY, null=True, blank=True, validators=[MinValueValidator(Decimal("0"))],
        verbose_name="Сумма / ставка, сом",
        help_text="Оклад в месяц, ставка за студента в месяц, ставка за группу в месяц или сумма бонуса.",
    )
    percentage = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True,
        validators=[MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("100"))], verbose_name="Процент",
    )
    program = models.ForeignKey(
        "academy.Course", on_delete=models.PROTECT, null=True, blank=True, related_name="salary_rules",
        verbose_name="Программа",
    )
    group = models.ForeignKey(
        "academy.Group", on_delete=models.PROTECT, null=True, blank=True, related_name="salary_rules",
        verbose_name="Группа",
    )
    calculation_method = models.CharField(max_length=20, choices=Method.choices, verbose_name="Метод расчёта")
    first_half_share = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal("50.00"),
        validators=[MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("100"))],
        verbose_name="Доля первой половины, %", help_text="Для метода SPLIT: остаток — во второй половине.",
    )
    revenue_basis = models.CharField(
        max_length=20, choices=RevenueBasis.choices, default=RevenueBasis.RECEIVED, verbose_name="База процента",
    )
    refund_policy = models.CharField(
        max_length=20, choices=RefundPolicy.choices, default=RefundPolicy.DEDUCT, verbose_name="Учёт возвратов",
    )
    description = models.CharField(max_length=255, blank=True, verbose_name="Комментарий")
    effective_from = models.DateField(verbose_name="Действует с")
    effective_to = models.DateField(null=True, blank=True, verbose_name="Действует по (включительно)")
    is_active = models.BooleanField(default=True, db_index=True, verbose_name="Активно")
    previous_version = models.OneToOneField(
        "self", on_delete=models.PROTECT, null=True, blank=True, related_name="next_version",
        verbose_name="Предыдущая версия",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Правило начисления"
        verbose_name_plural = "Правила начисления"
        ordering = ["employee_profile", "rule_type", "-effective_from", "-id"]
        indexes = [models.Index(fields=["employee_profile", "is_active"], name="ix_srule_profile_active")]

    def __str__(self):
        return f"{self.employee_profile.employee} · {self.get_rule_type_display()} с {self.effective_from:%d.%m.%Y}"

    def overlaps(self, start: dt.date, end: dt.date) -> bool:
        return self.effective_from <= end and (self.effective_to is None or self.effective_to >= start)

    def clean(self):
        errors = {}
        if self.effective_to and self.effective_to < self.effective_from:
            errors["effective_to"] = "Дата окончания раньше даты начала."
        if self.rule_type not in self.ACTIVE_TYPES:
            raise ValidationError({"rule_type": "Допустимы только правила «Оклад» и «Процент от стоимости курса»."})
        if self.employee_profile_id and self.employee_profile.salary_type != self.rule_type:
            raise ValidationError({"rule_type": "Тип правила должен совпадать с типом оплаты сотрудника "
                                                f"(«{self.employee_profile.get_salary_type_display()}»)."})
        if self.rule_type in (self.RuleType.PERCENT, self.RuleType.REVENUE_PERCENT):
            if self.percentage is None:
                errors["percentage"] = "Укажите процент."
        elif self.amount is None:
            errors["amount"] = "Укажите сумму."
        if not self.calculation_method:
            self.calculation_method = self.METHODS_BY_TYPE[self.rule_type][0]
        elif self.calculation_method not in self.METHODS_BY_TYPE.get(self.rule_type, ()):
            errors["calculation_method"] = "Метод не подходит для этого типа правила."
        if self.group_id and self.program_id and self.group.course_id != self.program_id:
            errors["group"] = "Группа не относится к выбранной программе."
        if errors:
            raise ValidationError(errors)


# ---------------------------------------------------------------------------
# Периоды и расчёты
# ---------------------------------------------------------------------------

class PayrollPeriod(models.Model):
    class PeriodType(models.TextChoices):
        FIRST_HALF = "FIRST_HALF", "1–15"
        SECOND_HALF = "SECOND_HALF", "16–конец месяца"
        # Оклад (FIXED) начисляется за полный календарный месяц — одним расчётом.
        MONTH = "MONTH", "Весь месяц (оклад)"

    HALVES = (PeriodType.FIRST_HALF, PeriodType.SECOND_HALF)

    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Черновик"
        CALCULATED = "CALCULATED", "Рассчитан"
        APPROVED = "APPROVED", "Утверждён"
        CLOSED = "CLOSED", "Закрыт"

    year = models.PositiveSmallIntegerField(validators=[MinValueValidator(2000), MaxValueValidator(2100)])
    month = models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(12)])
    period_type = models.CharField(max_length=20, choices=PeriodType.choices)
    start_date = models.DateField(editable=False)
    end_date = models.DateField(editable=False)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT, db_index=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="+",
        help_text="Пусто — период создан автоматически (manage.py payroll_autorun).",
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    approved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Расчётный период"
        verbose_name_plural = "Расчётные периоды"
        ordering = ["-year", "-month", "-period_type"]
        constraints = [
            models.UniqueConstraint(fields=["year", "month", "period_type"], name="unique_payroll_period"),
        ]

    def __str__(self):
        return f"{self.start_date:%d.%m.%Y}–{self.end_date:%d.%m.%Y}"

    @staticmethod
    def bounds(year: int, month: int, period_type: str) -> tuple[dt.date, dt.date]:
        last = calendar.monthrange(year, month)[1]
        if period_type == PayrollPeriod.PeriodType.FIRST_HALF:
            return dt.date(year, month, 1), dt.date(year, month, 15)
        if period_type == PayrollPeriod.PeriodType.MONTH:
            return dt.date(year, month, 1), dt.date(year, month, last)
        return dt.date(year, month, 16), dt.date(year, month, last)

    @property
    def month_days(self) -> int:
        return calendar.monthrange(self.year, self.month)[1]

    @property
    def month_start(self) -> dt.date:
        return dt.date(self.year, self.month, 1)

    @property
    def month_end(self) -> dt.date:
        return dt.date(self.year, self.month, self.month_days)

    @property
    def days(self) -> int:
        return (self.end_date - self.start_date).days + 1

    @property
    def is_first_half(self) -> bool:
        return self.period_type == self.PeriodType.FIRST_HALF

    @property
    def is_month(self) -> bool:
        return self.period_type == self.PeriodType.MONTH

    def save(self, *args, **kwargs):
        self.start_date, self.end_date = self.bounds(self.year, self.month, self.period_type)
        super().save(*args, **kwargs)


class Payroll(models.Model):
    """Расчёт зарплаты одного сотрудника за один период.

    `total_accrued` — сумма строк расчёта (замораживается утверждением);
    `total_adjustments` — сумма применённых корректировок; `total_paid` —
    сумма подтверждённых выплат; `amount_due` = начислено + корректировки −
    выплачено. Итоги пересчитываются только сервисами из записей.
    """

    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Черновик"
        CALCULATED = "CALCULATED", "Рассчитан"
        RETURNED = "RETURNED", "Возвращён на исправление"
        APPROVED = "APPROVED", "Утверждён"
        PARTIALLY_PAID = "PARTIALLY_PAID", "Частично выплачен"
        PAID = "PAID", "Выплачен"
        VOID = "VOID", "Аннулирован"

    EDITABLE_STATUSES = (Status.DRAFT, Status.CALCULATED, Status.RETURNED)
    LOCKED_STATUSES = (Status.APPROVED, Status.PARTIALLY_PAID, Status.PAID)

    period = models.ForeignKey(PayrollPeriod, on_delete=models.PROTECT, related_name="payrolls")
    employee = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="payrolls")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT, db_index=True)
    total_accrued = models.DecimalField(**MONEY, default=ZERO)
    total_adjustments = models.DecimalField(**MONEY, default=ZERO)
    total_paid = models.DecimalField(**MONEY, default=ZERO)
    amount_due = models.DecimalField(**MONEY, default=ZERO)
    warnings = models.JSONField(default=list, blank=True, help_text="Предупреждения последнего расчёта.")
    errors = models.JSONField(default=list, blank=True, help_text="Ошибки, блокирующие утверждение.")
    salary_type = models.CharField(max_length=20, choices=SalaryType.choices, blank=True)
    position = models.CharField(max_length=100, blank=True)
    department = models.CharField(
        max_length=20, choices=Department.choices, blank=True, db_index=True,
        help_text="Снимок направления сотрудника на момент расчёта (для аналитики).",
    )
    active_students = models.PositiveIntegerField(
        null=True, blank=True, help_text="Число разных активных студентов в периоде — если применимо.",
    )
    return_reason = models.TextField(blank=True)
    calculated_at = models.DateTimeField(null=True, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = ImmutableQuerySet.as_manager()

    class Meta:
        verbose_name = "Расчёт зарплаты"
        verbose_name_plural = "Расчёты зарплаты"
        ordering = ["-period__year", "-period__month", "-period__period_type", "employee__last_name"]
        constraints = [
            models.UniqueConstraint(fields=["period", "employee"], name="unique_payroll_employee_period"),
        ]

    def __str__(self):
        return f"{self.employee} · {self.period}"

    @property
    def is_editable(self) -> bool:
        return self.status in self.EDITABLE_STATUSES

    @property
    def is_locked(self) -> bool:
        return self.status in self.LOCKED_STATUSES

    @property
    def planned_payment_date(self) -> dt.date | None:
        """Плановая дата выплаты (не факт перевода) — services.payout."""
        from .services.payout import planned_date_for_period

        return planned_date_for_period(self.period)

    def delete(self, *args, **kwargs):
        raise ValidationError("Расчёт нельзя удалить — его можно только аннулировать.")


class PayrollLine(models.Model):
    class LineType(models.TextChoices):
        FIXED = "FIXED", "Оклад"
        PERCENT = "PERCENT", "Процент за завершённый цикл курса"
        REVENUE_PERCENT = "REVENUE_PERCENT", "Процент от оплаты"
        REFUND_CORRECTION = "REFUND_CORRECTION", "Корректировка возврата"
        # Оклад за месяц, часть которого уже начислена утверждёнными
        # полумесячными расчётами прежней схемы, — зачёт без их изменения.
        PRIOR_FIXED = "PRIOR_FIXED", "Зачёт оклада, начисленного по прежней схеме"
        PER_STUDENT = "PER_STUDENT", "За активных студентов"
        PER_GROUP = "PER_GROUP", "За группу"
        BONUS = "BONUS", "Дополнительное начисление"

    payroll = models.ForeignKey(Payroll, on_delete=models.CASCADE, related_name="lines")
    line_type = models.CharField(max_length=20, choices=LineType.choices)
    description = models.CharField(max_length=255)
    source_type = models.CharField(max_length=40, blank=True)
    source_id = models.PositiveBigIntegerField(null=True, blank=True)
    salary_rule = models.ForeignKey(SalaryRule, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    quantity = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)
    rate = models.DecimalField(**MONEY, null=True, blank=True)
    percentage = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    base_amount = models.DecimalField(**MONEY, null=True, blank=True)
    amount = models.DecimalField(**MONEY)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Строка расчёта"
        verbose_name_plural = "Строки расчёта"
        ordering = ["payroll", "id"]

    def __str__(self):
        return f"{self.description}: {self.amount}"


class PayrollAdjustment(models.Model):
    """Корректировка начисления: бонус, удержание или исправление.

    К черновому расчёту применяется сразу (входит в утверждаемую сумму).
    К утверждённому — создаётся как PENDING и меняет остаток только после
    утверждения директором: утверждённое начисление нельзя изменить
    незаметно.
    """

    class Kind(models.TextChoices):
        BONUS = "BONUS", "Премия / доплата"
        DEDUCTION = "DEDUCTION", "Удержание"
        CORRECTION = "CORRECTION", "Исправление"

    class Status(models.TextChoices):
        PENDING = "PENDING", "Ожидает утверждения"
        APPLIED = "APPLIED", "Применена"
        REJECTED = "REJECTED", "Отклонена"
        VOID = "VOID", "Отменена"

    payroll = models.ForeignKey(Payroll, on_delete=models.PROTECT, related_name="adjustments")
    kind = models.CharField(max_length=20, choices=Kind.choices)
    amount = models.DecimalField(
        **MONEY, help_text="Со знаком: удержание всегда отрицательное, премия — положительная.",
    )
    reason = models.TextField()
    status = models.CharField(max_length=20, choices=Status.choices, db_index=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="+",
        help_text="Пусто — создана системой (автокорректировка после исправления уроков).",
    )
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="+",
    )
    decided_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = ImmutableQuerySet.as_manager()

    class Meta:
        verbose_name = "Корректировка"
        verbose_name_plural = "Корректировки"
        ordering = ["payroll", "id"]

    def __str__(self):
        return f"{self.get_kind_display()}: {self.amount}"

    def delete(self, *args, **kwargs):
        raise ValidationError("Корректировку нельзя удалить — её можно отменить.")


class PayrollPayment(models.Model):
    class Method(models.TextChoices):
        BANK = "bank", "Банковский перевод"
        CASH = "cash", "Наличные"
        OTHER = "other", "Другое"

    class Status(models.TextChoices):
        CONFIRMED = "CONFIRMED", "Подтверждена"
        VOID = "VOID", "Отменена"

    payroll = models.ForeignKey(Payroll, on_delete=models.PROTECT, related_name="payments")
    amount = models.DecimalField(**MONEY, validators=[MinValueValidator(Decimal("0.01"))])
    payment_date = models.DateField()
    payment_method = models.CharField(max_length=10, choices=Method.choices, default=Method.BANK)
    reference = models.CharField(max_length=100, blank=True)
    comment = models.TextField(blank=True)
    is_advance = models.BooleanField(default=False, verbose_name="Аванс")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.CONFIRMED, db_index=True)
    void_reason = models.TextField(blank=True)
    idempotency_key = models.CharField(max_length=64, null=True, blank=True, unique=True, editable=False)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    voided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="+",
    )
    voided_at = models.DateTimeField(null=True, blank=True)

    objects = ImmutableQuerySet.as_manager()

    class Meta:
        verbose_name = "Выплата сотруднику"
        verbose_name_plural = "Выплаты сотрудникам"
        ordering = ["payroll", "payment_date", "id"]
        constraints = [
            models.CheckConstraint(condition=models.Q(amount__gt=0), name="payroll_payment_amount_positive"),
        ]

    def __str__(self):
        return f"{self.amount} сом · {self.payment_date:%d.%m.%Y}"

    def delete(self, *args, **kwargs):
        raise ValidationError("Выплату нельзя удалить — отмените её с указанием причины.")


class PayrollAuditLog(models.Model):
    """Журнал финансовых изменений. Только добавление: ни API, ни admin
    не дают изменить или удалить запись."""

    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, related_name="+")
    entity_type = models.CharField(max_length=40, db_index=True)
    entity_id = models.PositiveBigIntegerField(db_index=True)
    action = models.CharField(max_length=40, db_index=True)
    old_values = models.JSONField(default=dict, blank=True)
    new_values = models.JSONField(default=dict, blank=True)
    reason = models.TextField(blank=True)
    payroll = models.ForeignKey(
        Payroll, on_delete=models.PROTECT, null=True, blank=True, related_name="audit_entries",
        help_text="Расчёт, к которому относится запись (для истории на странице расчёта).",
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    objects = ImmutableQuerySet.as_manager()

    class Meta:
        verbose_name = "Запись журнала аудита"
        verbose_name_plural = "Журнал аудита бухгалтерии"
        ordering = ["-created_at", "-id"]

    def __str__(self):
        return f"{self.created_at:%d.%m.%Y %H:%M} · {self.action} · {self.entity_type}#{self.entity_id}"

    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise ValidationError("Запись журнала аудита нельзя изменить.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Запись журнала аудита нельзя удалить.")


# ---------------------------------------------------------------------------
# Процент от стоимости курса: настройки курса, циклы, начисления по циклу
# ---------------------------------------------------------------------------

class CoursePayrollSettings(models.Model):
    """Зарплатные настройки курса (программы): фиксированная стоимость за
    студента и число уроков в расчётном цикле. Хранятся в бухгалтерии, а не
    в коде и не в учебной карточке курса: их ведёт бухгалтер. Изменение
    настроек не трогает уже завершённые циклы — у каждого свой снимок."""

    class StudentCountRule(models.TextChoices):
        ON_COMPLETION = "ON_COMPLETION", "Активные в группе на дату завершения цикла"
        DURING_CYCLE = "DURING_CYCLE", "Активные в группе хотя бы один день цикла"

    course = models.OneToOneField(
        "academy.Course", on_delete=models.PROTECT, related_name="payroll_settings", verbose_name="Курс",
    )
    price_per_student = models.DecimalField(
        **MONEY, validators=[MinValueValidator(Decimal("0.01"))], verbose_name="Стоимость курса за студента, сом",
    )
    required_lessons = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1)], verbose_name="Уроков в цикле",
        help_text="Сколько проведённых уроков завершают расчётный цикл (например 12 или 20).",
    )
    count_lessons_from = models.DateField(
        null=True, blank=True, verbose_name="Учитывать уроки с",
        help_text="Необязательно. Пусто — учёт с первого проведённого урока группы.",
    )
    student_count_rule = models.CharField(
        max_length=20, choices=StudentCountRule.choices, default=StudentCountRule.ON_COMPLETION,
        verbose_name="Правило учёта студентов",
    )
    counted_subjects = models.ManyToManyField(
        "users.Subject", blank=True, related_name="+", verbose_name="Учитываемые предметы",
        help_text="Только уроки этих предметов входят в цикл (например, только IT). Пусто — все уроки группы.",
    )
    is_active = models.BooleanField(default=True, verbose_name="Активны")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Зарплатные настройки курса"
        verbose_name_plural = "Зарплатные настройки курсов"
        ordering = ["course__name"]

    def __str__(self):
        return f"{self.course}: {self.price_per_student} сом, {self.required_lessons} ур."


class CoursePriceVersion(models.Model):
    """Версия тарифа: фиксированная стоимость обучения одного студента за
    календарный месяц, действующая с даты. Не редактируется и не удаляется:
    новая цена — новая версия, предыдущая закрывается днём раньше. Каждый
    завершённый цикл берёт цену, действовавшую на дату его завершения, и
    хранит её снимок, поэтому новый тариф не меняет уже созданные начисления.

    Это согласованная цена курса, а не поступившие деньги — фактические
    платежи студентов ведёт `StudentPayment`.
    """

    course = models.ForeignKey(
        "academy.Course", on_delete=models.PROTECT, related_name="price_versions", verbose_name="Курс",
    )
    price_per_student = models.DecimalField(
        **MONEY, validators=[MinValueValidator(Decimal("0.01"))], verbose_name="Стоимость за студента в месяц, сом",
    )
    currency = models.CharField(max_length=3, default=CURRENCY, editable=False, verbose_name="Валюта")
    effective_from = models.DateField(verbose_name="Действует с")
    effective_to = models.DateField(null=True, blank=True, verbose_name="Действует по (включительно)")
    reason = models.TextField(verbose_name="Причина изменения")
    previous_version = models.OneToOneField(
        "self", on_delete=models.PROTECT, null=True, blank=True, related_name="next_version",
        verbose_name="Предыдущая версия",
    )
    is_migrated = models.BooleanField(
        default=False, verbose_name="Перенесена из прежних настроек",
        help_text="Цена из настроек курса до введения истории тарифов: дата начала неизвестна — проверьте.",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="+",
        verbose_name="Автор изменения",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    objects = ImmutableQuerySet.as_manager()

    class Meta:
        verbose_name = "Тариф курса"
        verbose_name_plural = "История тарифов курсов"
        ordering = ["course", "-effective_from", "-id"]
        constraints = [
            models.UniqueConstraint(fields=["course", "effective_from"], name="unique_course_price_start"),
            models.UniqueConstraint(
                fields=["course"], condition=models.Q(effective_to__isnull=True), name="unique_open_course_price",
            ),
            models.CheckConstraint(condition=models.Q(price_per_student__gt=0), name="course_price_positive"),
            models.CheckConstraint(
                condition=models.Q(effective_to__isnull=True) | models.Q(effective_to__gte=models.F("effective_from")),
                name="course_price_range",
            ),
        ]

    def __str__(self):
        return f"{self.course}: {self.price_per_student} сом с {self.effective_from:%d.%m.%Y}"

    def delete(self, *args, **kwargs):
        raise ValidationError("Тариф нельзя удалить — создайте новую версию.")


class CourseCycle(models.Model):
    """Расчётный цикл курса в группе: каждые `required_lessons` проведённых
    уроков группы — один цикл. Завершённый цикл — зафиксированный факт со
    снимком: число уроков, дата последнего необходимого урока, число
    учитываемых студентов и стоимость курса. Незавершённый — текущий
    прогресс группы (обновляется при каждой синхронизации)."""

    class Status(models.TextChoices):
        IN_PROGRESS = "IN_PROGRESS", "Идёт"
        COMPLETED = "COMPLETED", "Завершён"
        # Порог больше не достигнут: урок исправили после завершения цикла.
        INVALIDATED = "INVALIDATED", "Отменён (уроки исправлены)"

    group = models.ForeignKey("academy.Group", on_delete=models.PROTECT, related_name="payroll_cycles")
    course = models.ForeignKey("academy.Course", on_delete=models.PROTECT, related_name="payroll_cycles")
    number = models.PositiveIntegerField(verbose_name="Номер цикла в группе")
    status = models.CharField(max_length=20, choices=Status.choices, db_index=True)
    required_lessons = models.PositiveSmallIntegerField()
    lessons_done = models.PositiveSmallIntegerField(default=0)
    lessons_total = models.PositiveIntegerField(
        default=0, help_text="Накопленное число проведённых уроков группы на пороге цикла (12, 24, 36…).",
    )
    invalidated_reason = models.TextField(blank=True)
    start_date = models.DateField(null=True, blank=True, help_text="Дата первого урока цикла.")
    completed_on = models.DateField(null=True, blank=True, db_index=True,
                                    help_text="Дата проведения последнего необходимого урока.")
    last_lesson_id = models.PositiveBigIntegerField(null=True, blank=True)
    student_count = models.PositiveIntegerField(null=True, blank=True)
    student_ids = models.JSONField(default=list, blank=True, help_text="Основание (только id студентов).")
    student_count_rule = models.CharField(max_length=20, blank=True)
    course_price = models.DecimalField(**MONEY, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = ImmutableQuerySet.as_manager()

    class Meta:
        verbose_name = "Цикл курса"
        verbose_name_plural = "Циклы курсов"
        ordering = ["group", "number"]
        constraints = [
            models.UniqueConstraint(
                fields=["group", "course", "number"], condition=~models.Q(status="INVALIDATED"),
                name="unique_course_cycle",
            ),
            models.UniqueConstraint(
                fields=["group", "course"], condition=models.Q(status="IN_PROGRESS"), name="unique_open_course_cycle",
            ),
        ]

    def __str__(self):
        return f"{self.group} · цикл {self.number} ({self.lessons_done}/{self.required_lessons})"

    @property
    def base_amount(self) -> Decimal | None:
        if self.student_count is None or self.course_price is None:
            return None
        return self.course_price * self.student_count

    def delete(self, *args, **kwargs):
        raise ValidationError("Цикл курса нельзя удалить.")


class CycleLesson(models.Model):
    """Конкретный проведённый урок, вошедший в завершённый цикл.

    Связь фиксируется при завершении цикла и не переписывается: у
    отменённого цикла она остаётся историей (`is_live=False`). Частичный
    уникальный индекс не даёт одному уроку попасть в два действующих
    оплачиваемых цикла. Урок, удалённый из LMS, остаётся здесь датой и id."""

    cycle = models.ForeignKey(CourseCycle, on_delete=models.PROTECT, related_name="cycle_lessons")
    lesson = models.ForeignKey(
        "academy.Lesson", on_delete=models.SET_NULL, null=True, blank=True, related_name="payroll_cycle_links",
    )
    lesson_ref = models.PositiveBigIntegerField(help_text="id урока (сохраняется, даже если урок удалён).")
    lesson_date = models.DateField()
    position = models.PositiveSmallIntegerField(help_text="Порядковый номер урока в цикле, с 1.")
    teacher = models.ForeignKey(
        "users.Teacher", on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
        help_text="Тренер, фактически проводивший урок.",
    )
    is_live = models.BooleanField(default=True, db_index=True)
    backfilled = models.BooleanField(default=False, help_text="Восстановлено миграцией по текущим урокам.")
    created_at = models.DateTimeField(auto_now_add=True)

    objects = ImmutableQuerySet.as_manager()

    class Meta:
        verbose_name = "Урок цикла"
        verbose_name_plural = "Уроки циклов"
        ordering = ["cycle", "position"]
        constraints = [
            models.UniqueConstraint(
                fields=["lesson_ref"], condition=models.Q(is_live=True), name="unique_live_cycle_lesson",
            ),
            models.UniqueConstraint(fields=["cycle", "position"], name="unique_cycle_lesson_position"),
        ]

    def __str__(self):
        return f"{self.cycle} · урок {self.position} ({self.lesson_date:%d.%m.%Y})"

    def delete(self, *args, **kwargs):
        raise ValidationError("Связь урока с циклом нельзя удалить.")


class CycleAccrual(models.Model):
    """Начисление процента тренеру за завершённый цикл. Создаётся
    автоматически, как только группа достигает порога (12, 24, 36… уроков);
    одно на пару (цикл, сотрудник) — повторное сохранение урока, повторный
    запуск синхронизации или пересчёт дубликата не создают. Хранит снимок
    всех величин; расчёт периода только включает его строкой."""

    class Status(models.TextChoices):
        ACCRUED = "ACCRUED", "Начислено"
        APPROVED = "APPROVED", "Утверждено"
        CANCELLED = "CANCELLED", "Отменено (уроки исправлены до утверждения)"
        CORRECTED = "CORRECTED", "Сторнировано корректировкой"
        CORRECTION_REQUIRED = "CORRECTION_REQUIRED", "Требует ручной корректировки"
        # Не начисляется автоматически: смена тренера внутри цикла или второй
        # цикл группы в том же месяце — решение принимает бухгалтер.
        REVIEW_REQUIRED = "REVIEW_REQUIRED", "Требует проверки"

    cycle = models.ForeignKey(CourseCycle, on_delete=models.PROTECT, related_name="accruals")
    employee = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    salary_rule = models.ForeignKey(SalaryRule, on_delete=models.PROTECT, related_name="+")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACCRUED, db_index=True)
    payroll = models.ForeignKey(Payroll, on_delete=models.PROTECT, null=True, blank=True, related_name="cycle_accruals")
    line = models.OneToOneField(PayrollLine, on_delete=models.SET_NULL, null=True, blank=True,
                                related_name="cycle_accrual")
    adjustment = models.ForeignKey(PayrollAdjustment, on_delete=models.PROTECT, null=True, blank=True,
                                   related_name="+", help_text="Корректировка, сторнирующая это начисление.")
    lessons = models.PositiveSmallIntegerField(help_text="Уроков в цикле.")
    lessons_total = models.PositiveIntegerField(default=0, help_text="Порог: накопленные уроки группы.")
    completed_on = models.DateField()
    student_count = models.PositiveIntegerField()
    course_price = models.DecimalField(**MONEY)
    percentage = models.DecimalField(max_digits=5, decimal_places=2)
    amount = models.DecimalField(**MONEY)
    note = models.TextField(blank=True)
    review_reasons = models.JSONField(default=list, blank=True, help_text="Почему начисление требует проверки.")
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="+",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = ImmutableQuerySet.as_manager()

    @property
    def planned_payment_date(self) -> dt.date:
        """Плановая дата выплаты по дате завершения цикла (1–15 → 15-е,
        16–конец → 1-е следующего месяца); если начисление вошло в расчёт —
        по периоду этого расчёта."""
        from .services.payout import planned_date_for_completion, planned_date_for_period

        if self.payroll_id:
            return planned_date_for_period(self.payroll.period)
        return planned_date_for_completion(self.completed_on)

    class Meta:
        verbose_name = "Начисление за цикл"
        verbose_name_plural = "Начисления за циклы"
        ordering = ["-completed_on", "id"]
        constraints = [models.UniqueConstraint(fields=["cycle", "employee"], name="unique_cycle_accrual")]

    def __str__(self):
        return f"{self.employee} · {self.cycle}: {self.amount}"

    def delete(self, *args, **kwargs):
        raise ValidationError("Начисление за цикл нельзя удалить — только отменить или сторнировать.")
