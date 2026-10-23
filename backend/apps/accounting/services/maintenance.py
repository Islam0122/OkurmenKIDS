"""Очистка данных бухгалтерии (Django Admin → Бухгалтерия → Обслуживание
базы данных → Очистка данных). Только суперпользователь.

Два режима:

* `PAYROLL` — расчёты зарплаты: начисления за циклы, выплаты, корректировки,
  строки расчётов, журнал аудита, расчёты, периоды. Правила и профили,
  циклы курсов, настройки курсов, тарифы и платежи студентов сохраняются.
* `FULL` — вся бухгалтерия: всё из `PAYROLL` + уроки циклов (зависимая
  таблица: PROTECT на цикл), циклы, правила, профили, настройки курсов (с их
  связью «учитываемые предметы»), платежи студентов с возвратами и вся
  оплата обучения (`apps.billing`: договоры, учебные месяцы, списания уроков,
  начисления, распределения, авансы, брони, чеки, задачи, контакты,
  уведомления, журнал событий); по отдельному флажку — тарифы (история цен
  курсов и тарифы оплаты обучения с версиями).

Никогда не трогаются пользователи, тренеры, студенты, группы, курсы,
предметы, уроки и посещаемость: удаляются только модели приложений
`accounting` и `billing`. Ни одна модель других приложений не ссылается на
них (проверено по `_meta`), поэтому каскадом LMS не задевается. Сохраняются
настройки оплаты (`BillingSettings`) и права (группы `Accountant`,
`BillingDirector`). Записи реестра тестовых данных (`DemoSeedRecord`),
указывающие на удалённые бухгалтерские объекты, удаляются вместе с ними.

Безопасность:
* порядок удаления следует зависимостям (PROTECT / CASCADE / SET_NULL
  проверены по `_meta`); удаление — обычный `QuerySet.delete()` (коллектор
  Django, проверки внешних ключей, on_delete и сигналы работают), поэтому
  ошибка порядка даёт `ProtectedError`, а не «висящие» ссылки;
* самоссылки с PROTECT (версии правил и тарифов, возвраты) удаляются от
  листьев к корню, без отключения проверок;
* всё в одной `transaction.atomic()`: после удаления проверяется, что
  удаляемые таблицы пусты, а сохраняемые не изменились, — иначе откат;
* сырого SQL нет, пользовательский ввод в запросы не попадает;
* по завершении в (уже очищенный) журнал аудита пишется одна запись об
  операции: кто, когда, режим и сколько удалено.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from django.apps import apps as django_apps
from django.contrib.contenttypes.models import ContentType
from django.db import transaction

from apps.billing.models import (
    BillingContactLog,
    BillingEvent,
    BillingNotification,
    BillingPlan,
    BillingPlanVersion,
    BillingTask,
    BillingTermsChange,
    CreditLedgerEntry,
    Invoice,
    InvoiceAdjustment,
    LessonConsumption,
    LessonPackage,
    PaymentAllocation,
    Receipt,
    Reservation,
    StudentBillingProfile,
)

from ..models import (
    AppliedDeduction,
    CourseCycle,
    CoursePayrollSettings,
    CoursePriceVersion,
    CycleAccrual,
    CycleLesson,
    DeductionAllocation,
    DemoSeedRecord,
    DeductionRule,
    EmployeeSalaryProfile,
    PayoutPlan,
    PayoutPlanLine,
    Payroll,
    PayrollAdjustment,
    PayrollAuditLog,
    PayrollLine,
    PayrollPayment,
    PayrollPeriod,
    SalaryRule,
    StudentPayment,
    maintenance_delete,
)
from . import AccountingError

logger = logging.getLogger(__name__)

PAYROLL = "PAYROLL"
FULL = "FULL"
CONFIRM_PHRASE = "DELETE ACCOUNTING"
FULL_CONFIRM_PHRASE = "FULL RESET"

_SUBJECTS_THROUGH = CoursePayrollSettings.counted_subjects.through


@dataclass(frozen=True)
class Table:
    key: str
    model: type
    label: str
    note: str = ""

    @property
    def db_table(self) -> str:
        return self.model._meta.db_table


# Порядок = порядок удаления (сначала те, кто ссылается на других).
PAYROLL_TABLES = (
    Table("cycleaccrual", CycleAccrual, "Начисления за циклы"),
    Table("payrollauditlog", PayrollAuditLog, "Журнал аудита бухгалтерии"),
    Table("payrollpayment", PayrollPayment, "Выплаты сотрудникам"),
    Table("payoutplanline", PayoutPlanLine, "Строки планов выплат"),
    Table("payoutplan", PayoutPlan, "Планы выплат"),
    Table("deductionallocation", DeductionAllocation, "Удержания в расчётах"),
    Table("applieddeduction", AppliedDeduction, "Применённые удержания"),
    Table("payrolladjustment", PayrollAdjustment, "Корректировки"),
    Table("payrollline", PayrollLine, "Строки расчётов"),
    Table("payroll", Payroll, "Расчёты зарплаты"),
    Table("payrollperiod", PayrollPeriod, "Расчётные периоды"),
)
# Оплата обучения: всё, что ссылается на платежи и договоры, — раньше
# платежей; сами договоры — после платежей (платёж ссылается на договор).
BILLING_BEFORE_PAYMENTS = (
    Table("receipt", Receipt, "Чеки"),
    Table("billingcontactlog", BillingContactLog, "Контакты с родителями"),
    Table("billingnotification", BillingNotification, "Уведомления бухгалтерии"),
    Table("billingtask", BillingTask, "Задачи бухгалтера"),
    Table("creditledgerentry", CreditLedgerEntry, "Журнал авансов"),
    Table("paymentallocation", PaymentAllocation, "Распределения платежей"),
    Table("invoiceadjustment", InvoiceAdjustment, "Корректировки начислений"),
    Table("reservation", Reservation, "Брони"),
    Table("invoice", Invoice, "Начисления за учебные месяцы"),
    Table("lessonconsumption", LessonConsumption, "Списания уроков", "уроки LMS не удаляются (ссылка SET_NULL)"),
    Table("lessonpackage", LessonPackage, "Учебные месяцы / пакеты уроков"),
    Table("billingtermschange", BillingTermsChange, "История условий и скидок"),
    Table("billingevent", BillingEvent, "Журнал обработки событий"),
)
FULL_EXTRA_TABLES = (
    Table("cyclelesson", CycleLesson, "Уроки циклов", "зависимая таблица: ссылается на циклы (PROTECT)"),
    Table("coursecycle", CourseCycle, "Циклы курсов"),
    Table("salaryrule", SalaryRule, "Правила зарплат"),
    Table("deductionrule", DeductionRule, "Правила налогов и удержаний"),
    Table("employeesalaryprofile", EmployeeSalaryProfile, "Зарплатные профили сотрудников"),
    Table("coursepayrollsettings_subjects", _SUBJECTS_THROUGH, "Учитываемые предметы курсов",
          "связь M2M, удаляется вместе с настройками"),
    Table("coursepayrollsettings", CoursePayrollSettings, "Настройки курсов"),
    *BILLING_BEFORE_PAYMENTS,
    Table("studentpayment", StudentPayment, "Платежи студентов (включая возвраты)"),
    Table("studentbillingprofile", StudentBillingProfile, "Договоры (платёжные профили) студентов",
          "студенты LMS не удаляются"),
)
TARIFF_TABLE = Table("coursepriceversion", CoursePriceVersion, "История тарифов курсов",
                     "не входит в список по умолчанию — только по отдельному флажку")
TARIFF_TABLES = (
    TARIFF_TABLE,
    Table("billingplanversion", BillingPlanVersion, "Версии тарифов оплаты обучения", "только по флажку тарифов"),
    Table("billingplan", BillingPlan, "Тарифы / программы оплаты обучения", "только по флажку тарифов"),
)
BILLING_TABLES = BILLING_BEFORE_PAYMENTS + (FULL_EXTRA_TABLES[-1],)
KEPT_IN_PAYROLL = (FULL_EXTRA_TABLES[1], FULL_EXTRA_TABLES[2], FULL_EXTRA_TABLES[3], FULL_EXTRA_TABLES[5],
                   FULL_EXTRA_TABLES[6], FULL_EXTRA_TABLES[0], *BILLING_TABLES, *TARIFF_TABLES)
# Приложения, которые очистка не должна менять ни на одну запись.
OWN_APPS = ("accounting", "billing")


def tables_to_delete(mode: str, *, include_tariffs: bool = False) -> tuple[Table, ...]:
    if mode == PAYROLL:
        return PAYROLL_TABLES
    if mode == FULL:
        return PAYROLL_TABLES + FULL_EXTRA_TABLES + (TARIFF_TABLES if include_tariffs else ())
    raise AccountingError("Неизвестный режим очистки.", code="bad_mode")


def tables_kept(mode: str, *, include_tariffs: bool = False) -> tuple[Table, ...]:
    if mode == PAYROLL:
        return KEPT_IN_PAYROLL
    return () if include_tariffs else TARIFF_TABLES


def counts(tables) -> dict[str, int]:
    return {t.key: t.model._base_manager.count() for t in tables}


def preview() -> dict:
    """Количество записей по каждой таблице — для страницы подтверждения."""
    every = PAYROLL_TABLES + FULL_EXTRA_TABLES + TARIFF_TABLES
    return counts(every)


def other_app_counts() -> dict[str, int]:
    """Количество записей каждой модели вне бухгалтерии (LMS и другие
    модули) — до и после очистки должно совпасть. Сессии и журнал Django
    Admin меняются от действий пользователей и не сравниваются."""
    skip = {"sessions.Session", "admin.LogEntry", "token_blacklist.OutstandingToken",
            "token_blacklist.BlacklistedToken"}
    return {
        m._meta.label: m._base_manager.count() for m in django_apps.get_models()
        if m._meta.app_label not in OWN_APPS and m._meta.label not in skip and not m._meta.proxy
    }


def external_references() -> list[str]:
    """Модели других приложений, ссылающиеся на удаляемые таблицы. Пустой
    список — удаление не может каскадом задеть LMS."""
    out = []
    for app in OWN_APPS:
        for model in django_apps.get_app_config(app).get_models():
            for rel in model._meta.related_objects:
                if rel.related_model._meta.app_label not in OWN_APPS:
                    out.append(f"{rel.related_model._meta.label}.{rel.field.name} → {model._meta.label}")
    return out


def _delete_leaf_first(model, reverse_name: str) -> int:
    """Удалить все записи модели с самоссылкой PROTECT: сначала те, на кого
    никто не ссылается (последние версии / возвраты), и так до корня."""
    deleted = 0
    while True:
        remaining = model._base_manager.count()
        if not remaining:
            return deleted
        leaves = model.objects.filter(**{f"{reverse_name}__isnull": True})
        n, _ = leaves.delete()
        if not n:
            raise AccountingError(f"Не удалось удалить {model._meta.verbose_name_plural}: циклическая ссылка.")
        deleted += n


def _delete(table: Table) -> None:
    model = table.model
    if model is SalaryRule:
        _delete_leaf_first(SalaryRule, "next_version")
    elif model is CoursePriceVersion:
        _delete_leaf_first(CoursePriceVersion, "next_version")
    elif model is StudentPayment:
        _delete_leaf_first(StudentPayment, "refunds")  # сначала возвраты, потом исходные платежи
    elif model is LessonConsumption:
        _delete_leaf_first(LessonConsumption, "reversal")  # сначала сторно, потом исходные списания
    elif model is BillingPlanVersion:
        _delete_leaf_first(BillingPlanVersion, "next_version")
    elif model is _SUBJECTS_THROUGH:
        return  # удаляется коллектором вместе с настройками курсов
    else:
        model.objects.all().delete()


def purge(mode: str, *, actor, include_tariffs: bool = False, reason: str = "") -> dict[str, int]:
    """Удалить данные выбранного режима. Возвращает {таблица: удалено}.
    Только суперпользователь; любая ошибка — откат всей операции."""
    if not (getattr(actor, "is_authenticated", False) and actor.is_active and actor.is_superuser):
        raise AccountingError("Очистка данных доступна только суперпользователю.", code="forbidden")
    to_delete = tables_to_delete(mode, include_tariffs=include_tariffs)
    kept = tables_kept(mode, include_tariffs=include_tariffs)
    with transaction.atomic():
        before = counts(to_delete)
        kept_before = counts(kept)
        others_before = other_app_counts()
        deleted_models = [t.model for t in to_delete if not t.model._meta.auto_created]
        demo_types = ContentType.objects.get_for_models(*deleted_models, for_concrete_models=False).values()
        with maintenance_delete():
            for table in to_delete:
                _delete(table)
            # Реестр тестовых данных: строки про удалённые бухгалтерские объекты.
            demo_records = DemoSeedRecord.objects.filter(content_type__in=list(demo_types)).delete()[0]
        left = {k: v for k, v in counts(to_delete).items() if v}
        if left:
            raise AccountingError(f"Очистка не завершена, остались записи: {left}. Изменения отменены.")
        if counts(kept) != kept_before:
            raise AccountingError("Очистка затронула таблицы, которые должны сохраниться. Изменения отменены.")
        changed = {k for k, v in other_app_counts().items() if others_before.get(k) != v}
        if changed:
            raise AccountingError(f"Очистка изменила данные других модулей ({sorted(changed)}). Изменения отменены.")
        if demo_records:
            before["demoseedrecord"] = demo_records
        PayrollAuditLog.objects.create(
            actor=actor, entity_type="maintenance", entity_id=0,
            action="purge_full" if mode == FULL else "purge_payroll",
            old_values={"deleted": before},
            new_values={"mode": mode, "include_tariffs": include_tariffs,
                        "tables": [t.db_table for t in to_delete]},
            reason=reason or "Очистка данных бухгалтерии через Django Admin",
        )
    logger.warning("Accounting data purged: mode=%s actor=%s deleted=%s", mode, actor.pk, before)
    return before
