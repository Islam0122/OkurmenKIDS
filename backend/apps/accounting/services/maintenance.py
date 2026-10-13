"""Очистка данных бухгалтерии (Django Admin → Бухгалтерия → Обслуживание
базы данных → Очистка данных). Только суперпользователь.

Два режима:

* `PAYROLL` — расчёты зарплаты: начисления за циклы, выплаты, корректировки,
  строки расчётов, журнал аудита, расчёты, периоды. Правила и профили,
  циклы курсов, настройки курсов, тарифы и платежи студентов сохраняются.
* `FULL` — вся бухгалтерия: всё из `PAYROLL` + уроки циклов (зависимая
  таблица: PROTECT на цикл), циклы, правила, профили, настройки курсов (с их
  связью «учитываемые предметы»), платежи студентов с возвратами; по
  отдельному флажку — история тарифов.

Никогда не трогаются пользователи, тренеры, группы, курсы, предметы, уроки и
посещаемость: удаляются только модели приложения `accounting`.

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

from django.db import transaction

from ..models import (
    CourseCycle,
    CoursePayrollSettings,
    CoursePriceVersion,
    CycleAccrual,
    CycleLesson,
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
    Table("payrolladjustment", PayrollAdjustment, "Корректировки"),
    Table("payrollline", PayrollLine, "Строки расчётов"),
    Table("payroll", Payroll, "Расчёты зарплаты"),
    Table("payrollperiod", PayrollPeriod, "Расчётные периоды"),
)
FULL_EXTRA_TABLES = (
    Table("cyclelesson", CycleLesson, "Уроки циклов", "зависимая таблица: ссылается на циклы (PROTECT)"),
    Table("coursecycle", CourseCycle, "Циклы курсов"),
    Table("salaryrule", SalaryRule, "Правила зарплат"),
    Table("employeesalaryprofile", EmployeeSalaryProfile, "Зарплатные профили сотрудников"),
    Table("coursepayrollsettings_subjects", _SUBJECTS_THROUGH, "Учитываемые предметы курсов",
          "связь M2M, удаляется вместе с настройками"),
    Table("coursepayrollsettings", CoursePayrollSettings, "Настройки курсов"),
    Table("studentpayment", StudentPayment, "Платежи студентов (включая возвраты)"),
)
TARIFF_TABLE = Table("coursepriceversion", CoursePriceVersion, "История тарифов курсов",
                     "не входит в список по умолчанию — только по отдельному флажку")
KEPT_IN_PAYROLL = (FULL_EXTRA_TABLES[1], FULL_EXTRA_TABLES[2], FULL_EXTRA_TABLES[3], FULL_EXTRA_TABLES[5],
                   FULL_EXTRA_TABLES[6], FULL_EXTRA_TABLES[0], TARIFF_TABLE)


def tables_to_delete(mode: str, *, include_tariffs: bool = False) -> tuple[Table, ...]:
    if mode == PAYROLL:
        return PAYROLL_TABLES
    if mode == FULL:
        return PAYROLL_TABLES + FULL_EXTRA_TABLES + ((TARIFF_TABLE,) if include_tariffs else ())
    raise AccountingError("Неизвестный режим очистки.", code="bad_mode")


def tables_kept(mode: str, *, include_tariffs: bool = False) -> tuple[Table, ...]:
    if mode == PAYROLL:
        return KEPT_IN_PAYROLL
    return () if include_tariffs else (TARIFF_TABLE,)


def counts(tables) -> dict[str, int]:
    return {t.key: t.model._base_manager.count() for t in tables}


def preview() -> dict:
    """Количество записей по каждой таблице — для страницы подтверждения."""
    every = PAYROLL_TABLES + FULL_EXTRA_TABLES + (TARIFF_TABLE,)
    return counts(every)


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
        with maintenance_delete():
            for table in to_delete:
                _delete(table)
        left = {k: v for k, v in counts(to_delete).items() if v}
        if left:
            raise AccountingError(f"Очистка не завершена, остались записи: {left}. Изменения отменены.")
        if counts(kept) != kept_before:
            raise AccountingError("Очистка затронула таблицы, которые должны сохраниться. Изменения отменены.")
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
