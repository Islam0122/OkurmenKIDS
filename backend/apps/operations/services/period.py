"""Фильтры кабинета: период (today / yesterday / this_week / this_month /
last_month / custom), отдел, должность (роль) и сотрудник — одинаково для
каждой страницы и экспорта."""
from __future__ import annotations

import calendar
import datetime as dt
from dataclasses import dataclass

from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.users.models import User

from ..departments import Department, roles_of

PERIODS = [
    ("today", "Сегодня"),
    ("yesterday", "Вчера"),
    ("this_week", "Эта неделя"),
    ("this_month", "Этот месяц"),
    ("last_month", "Прошлый месяц"),
    ("custom", "Свой период"),
]
MAX_DAYS = 93


@dataclass(frozen=True)
class OpsFilters:
    period: str
    start: dt.date
    end: dt.date
    today: dt.date
    department: str | None = None
    role: str | None = None
    employee_id: int | None = None

    @property
    def label(self) -> str:
        if self.period == "custom":
            return f"{self.start:%d.%m.%Y} — {self.end:%d.%m.%Y}"
        return dict(PERIODS)[self.period]

    @property
    def days(self) -> int:
        return (self.end - self.start).days + 1

    @property
    def elapsed_end(self) -> dt.date:
        """Конец периода, но не позже сегодня: будущие дни ещё не наступили."""
        return min(self.end, self.today)

    def previous(self) -> "OpsFilters":
        if self.period in ("this_month", "last_month"):
            prev_end = self.start - dt.timedelta(days=1)
            prev_start = prev_end.replace(day=1)
            # «Этот месяц» сравнивается с тем же числом дней прошлого месяца.
            if self.period == "this_month":
                last = calendar.monthrange(prev_start.year, prev_start.month)[1]
                prev_end = prev_start.replace(day=min(self.elapsed_end.day, last))
        else:
            length = (self.elapsed_end - self.start).days + 1
            prev_end = self.start - dt.timedelta(days=1)
            prev_start = prev_end - dt.timedelta(days=length - 1)
        return OpsFilters("custom", prev_start, prev_end, self.today, self.department, self.role, self.employee_id)

    def users_qs(self):
        qs = User.objects.filter(is_active=True)
        if self.department:
            qs = qs.filter(role__in=roles_of(self.department))
        if self.role:
            qs = qs.filter(role=self.role)
        if self.employee_id:
            qs = qs.filter(pk=self.employee_id)
        return qs

    def as_dict(self) -> dict:
        return {"period": self.period, "label": self.label, "start": self.start, "end": self.end,
                "department": self.department, "role": self.role, "employee": self.employee_id}

    def report_query(self, **extra) -> dict:
        """Параметры для academy ReportFilters (тот же период)."""
        return {"period": "custom", "start_date": self.start.isoformat(), "end_date": self.end.isoformat(), **extra}


def _date(params, name):
    value = params.get(name)
    if not value:
        return None
    try:
        return dt.date.fromisoformat(value)
    except ValueError:
        raise ValidationError({name: "Дата в формате ГГГГ-ММ-ДД."})


def resolve(period: str, today: dt.date, start=None, end=None) -> tuple[dt.date, dt.date]:
    if period == "today":
        return today, today
    if period == "yesterday":
        day = today - dt.timedelta(days=1)
        return day, day
    if period == "this_week":
        start = today - dt.timedelta(days=today.weekday())
        return start, start + dt.timedelta(days=6)
    if period == "this_month":
        return today.replace(day=1), today.replace(day=calendar.monthrange(today.year, today.month)[1])
    if period == "last_month":
        end = today.replace(day=1) - dt.timedelta(days=1)
        return end.replace(day=1), end
    if not (start and end):
        raise ValidationError({"detail": "Для своего периода укажите start_date и end_date."})
    if end < start:
        raise ValidationError({"end_date": "Конец периода раньше начала."})
    if (end - start).days + 1 > MAX_DAYS:
        raise ValidationError({"detail": f"Период — не длиннее {MAX_DAYS} дней."})
    return start, end


def from_query(params, *, default: str = "this_month", today: dt.date | None = None) -> OpsFilters:
    today = today or timezone.localdate()
    start, end = _date(params, "start_date"), _date(params, "end_date")
    period = params.get("period") or ("custom" if start and end else default)
    if period not in dict(PERIODS):
        raise ValidationError({"period": "Неизвестный период."})
    start, end = resolve(period, today, start, end)
    department = params.get("department") or None
    if department and department not in Department.values:
        raise ValidationError({"department": "Неизвестный отдел."})
    role = params.get("role") or None
    if role and role not in User.Role.values:
        raise ValidationError({"role": "Неизвестная должность."})
    employee = params.get("employee") or None
    if employee and not str(employee).isdigit():
        raise ValidationError({"employee": "Неверный сотрудник."})
    return OpsFilters(period, start, end, today, department, role, int(employee) if employee else None)
