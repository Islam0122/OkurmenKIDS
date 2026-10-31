"""Отделы компании — разрез операционного управления.

Отдельной таблицы отделов нет и не нужно: в LMS отдел сотрудника однозначно
следует из его роли (`User.role`), а роли — единственный источник прав. Здесь
только соответствие «роль → отдел» и обратное. `accounting.Department` — это
другое: направление в зарплатном профиле (IT / Soft Skills / английский …),
его ведёт бухгалтер; операционный модуль его не трогает.
"""
from __future__ import annotations

from django.db import models

from apps.users.models import User


class Department(models.TextChoices):
    MANAGEMENT = "management", "Руководство"
    ACADEMY = "academy", "Академия"
    SALES = "sales", "Отдел продаж"
    MARKETING = "marketing", "Маркетинг"
    HR = "hr", "HR"
    FINANCE = "finance", "Бухгалтерия"


R = User.Role

ROLE_DEPARTMENT: dict[str, str] = {
    R.ADMIN: Department.MANAGEMENT,
    R.DIRECTOR: Department.MANAGEMENT,
    R.OPERATIONS_DIRECTOR: Department.MANAGEMENT,
    R.TEAM_LEAD: Department.ACADEMY,
    R.TEACHER: Department.ACADEMY,
    R.ASSISTANT: Department.ACADEMY,
    R.DOP: Department.SALES,
    R.ROP: Department.SALES,
    R.SALES_MANAGER: Department.SALES,
    R.MARKETING: Department.MARKETING,
    R.HR_MANAGER: Department.HR,
    R.ACCOUNTANT: Department.FINANCE,
}

# Руководители отдела: ставят задачи сотрудникам своего отдела и проверяют их
# отчёты. Team Lead — академия (тренеры и ассистенты), РОП и ДОП — продажи.
DEPARTMENT_LEADS: dict[str, tuple[str, ...]] = {
    Department.ACADEMY: (R.TEAM_LEAD,),
    Department.SALES: (R.ROP, R.DOP),
}


def department_of(user) -> str:
    return ROLE_DEPARTMENT.get(getattr(user, "role", None), Department.MANAGEMENT)


def roles_of(department: str) -> list[str]:
    return [role for role, dep in ROLE_DEPARTMENT.items() if dep == department]


def led_department(user) -> str | None:
    """Отдел, которым руководит `user` (Team Lead → академия, РОП/ДОП → продажи)."""
    role = getattr(user, "role", None)
    for department, roles in DEPARTMENT_LEADS.items():
        if role in roles:
            return department
    return None


def choices() -> list[dict]:
    return [{"value": value, "label": label} for value, label in Department.choices]
