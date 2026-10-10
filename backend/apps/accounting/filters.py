"""Фильтры списка начислений и отчётов (одни и те же для API и экспорта)."""
from __future__ import annotations

from django.db.models import Q
from rest_framework.exceptions import ValidationError


def _int(params, name):
    value = params.get(name)
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        raise ValidationError({name: "Ожидается число."})


def filter_payrolls(qs, params):
    """period, year, month, period_type, employee, status, salary_type,
    program, group, search (ФИО)."""
    if (period := _int(params, "period")) is not None:
        qs = qs.filter(period_id=period)
    if (year := _int(params, "year")) is not None:
        qs = qs.filter(period__year=year)
    if (month := _int(params, "month")) is not None:
        qs = qs.filter(period__month=month)
    if params.get("period_type"):
        qs = qs.filter(period__period_type=params["period_type"])
    if (employee := _int(params, "employee")) is not None:
        qs = qs.filter(employee_id=employee)
    if params.get("status"):
        qs = qs.filter(status__in=params["status"].split(","))
    if params.get("salary_type"):
        qs = qs.filter(salary_type=params["salary_type"])
    if (program := _int(params, "program")) is not None:
        qs = qs.filter(
            Q(employee__salary_profile__rules__program_id=program)
            | Q(employee__salary_profile__rules__group__course_id=program)
            | Q(lines__source_type="group", lines__source_id__in=_group_ids_of_program(program))
        ).distinct()
    if (group := _int(params, "group")) is not None:
        qs = qs.filter(
            Q(employee__salary_profile__rules__group_id=group) | Q(lines__source_type="group", lines__source_id=group)
        ).distinct()
    search = (params.get("search") or "").strip()
    for part in search.split():
        qs = qs.filter(Q(employee__first_name__icontains=part) | Q(employee__last_name__icontains=part))
    return qs


def _group_ids_of_program(program_id):
    from apps.academy.models import Group

    return Group.objects.filter(course_id=program_id).values("id")
