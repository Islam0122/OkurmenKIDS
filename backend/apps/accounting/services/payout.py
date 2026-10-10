"""Плановые даты выплат. Плановая дата — не факт перевода: статус «Выплачено»
ставит только зарегистрированная бухгалтером выплата, а не наступление даты.

* Процент (IT-тренеры): цикл завершён 1–15 числа включительно → выплата
  15-го того же месяца; 16-го — последнего дня → 1-го следующего месяца
  (31 декабря → 1 января следующего года). Дата завершения — дата урока, на
  котором достигнут порог (а не дата запуска синхронизации), в часовом поясе
  проекта (TIME_ZONE = Asia/Bishkek). Это совпадает с расчётным периодом
  цикла: 1–15 → выплата 15-го, 16–конец → 1-го.
* Оклад (FIXED): по отдельно настроенному месячному календарю —
  ACCOUNTING_FIXED_PAYDAY_DAY (число месяца) и
  ACCOUNTING_FIXED_PAYDAY_NEXT_MONTH (в следующем месяце после расчётного или
  в том же). День больше длины месяца → последний день месяца. Не настроено —
  плановая дата не определяется (None), а не придумывается.
"""
from __future__ import annotations

import calendar
import datetime as dt

from django.conf import settings

from ..models import PayrollPeriod


def _next_month_first(day: dt.date) -> dt.date:
    return dt.date(day.year + 1, 1, 1) if day.month == 12 else dt.date(day.year, day.month + 1, 1)


def planned_date_for_completion(completed_on: dt.date) -> dt.date:
    """Плановая выплата за цикл, завершённый в день `completed_on`."""
    if completed_on.day <= 15:
        return completed_on.replace(day=15)
    return _next_month_first(completed_on)


def fixed_payday(year: int, month: int) -> dt.date | None:
    """Плановая выплата оклада за расчётный месяц (или None, если календарь
    не настроен)."""
    day = getattr(settings, "ACCOUNTING_FIXED_PAYDAY_DAY", None)
    if not day:
        return None
    if getattr(settings, "ACCOUNTING_FIXED_PAYDAY_NEXT_MONTH", True):
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return dt.date(year, month, min(int(day), calendar.monthrange(year, month)[1]))


def planned_date_for_period(period: PayrollPeriod) -> dt.date | None:
    if period.period_type == PayrollPeriod.PeriodType.MONTH:
        return fixed_payday(period.year, period.month)
    if period.period_type == PayrollPeriod.PeriodType.FIRST_HALF:
        return dt.date(period.year, period.month, 15)
    return _next_month_first(period.end_date)
