"""CSV-выгрузка посещаемости. Ячейки, которые табличный редактор принял бы
за формулу, экранируются апострофом (CSV/formula injection)."""
from __future__ import annotations

import csv
import io

from django.utils import timezone

from apps.users.models import User

from .reports import STATUS_LABELS, DayRow

_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")

HEADER = ["Сотрудник", "Логин", "Роль", "Дата", "Приход", "Уход", "Продолжительность (ч:мм)",
          "Опоздание (мин)", "Статус", "Исправлена вручную"]


def safe_cell(value) -> str:
    text = "" if value is None else str(value)
    return "'" + text if text.startswith(_FORMULA_PREFIXES) else text


def _duration(seconds: int) -> str:
    return f"{seconds // 3600}:{seconds % 3600 // 60:02d}"


def rows_to_csv(rows: list[DayRow], tz) -> str:
    roles = dict(User.Role.choices)
    buffer = io.StringIO()
    buffer.write("﻿")  # Excel открывает UTF-8 с BOM без «кракозябр»
    writer = csv.writer(buffer, delimiter=";")
    writer.writerow(HEADER)
    for row in rows:
        user = row.user
        writer.writerow([safe_cell(c) for c in (
            user.get_full_name() or user.username,
            user.username,
            roles.get(user.role, user.role),
            row.day.strftime("%d.%m.%Y"),
            timezone.localtime(row.first_in, tz).strftime("%H:%M") if row.first_in else "",
            timezone.localtime(row.last_out, tz).strftime("%H:%M") if row.last_out else "",
            _duration(row.duration_seconds) if row.sessions else "",
            row.late_minutes or "",
            STATUS_LABELS.get(row.status, row.status),
            "да" if row.is_adjusted else "",
        )])
    return buffer.getvalue()
