"""Общие помощники подбора: ошибки сервисов, нормализация контактов, адреса
вакансий и номера заявок."""
from __future__ import annotations

import re
import secrets
from dataclasses import dataclass, field

from django.utils import timezone


@dataclass
class RecruitmentError(Exception):
    """Ошибка бизнес-правила: сообщение для человека, код для интерфейса."""

    message: str
    code: str = "invalid"
    status: int = 400
    extra: dict = field(default_factory=dict)


TRANSLIT = str.maketrans({
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e", "ж": "zh", "з": "z", "и": "i",
    "й": "y", "к": "k", "л": "l", "м": "m", "н": "n", "ң": "n", "о": "o", "ө": "o", "п": "p", "р": "r",
    "с": "s", "т": "t", "у": "u", "ү": "u", "ф": "f", "х": "h", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "sch",
    "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
})

# Без похожих символов (0/O, 1/I): номер заявки диктуют по телефону.
NUMBER_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def slugify(text: str) -> str:
    """Латинский адрес из названия: «Менеджер по продажам» → menedzher-po-prodazham."""
    value = re.sub(r"[^a-z0-9]+", "-", text.lower().translate(TRANSLIT)).strip("-")
    return value[:80].strip("-") or "vacancy"


def unique_slug(title: str, exclude_pk: int | None = None) -> str:
    from ..models import Vacancy

    base = slugify(title)
    slug, n = base, 2
    qs = Vacancy.objects.exclude(pk=exclude_pk) if exclude_pk else Vacancy.objects.all()
    while qs.filter(slug=slug).exists():
        slug, n = f"{base}-{n}", n + 1
    return slug


def phone_digits(phone: str) -> str:
    """Только цифры с кодом страны: «0555 12-34-56» и «+996 555 123 456» совпадают."""
    value = re.sub(r"\D", "", phone or "")
    if len(value) == 10 and value.startswith("0"):
        value = "996" + value[1:]
    return value


def normalize_email(email: str) -> str:
    return (email or "").strip().lower()


def new_application_number() -> str:
    """Номер заявки вида 2026-K7QM3D: случайный, по нему не перебрать чужие заявки."""
    from ..models import Application

    year = timezone.localdate().year
    while True:
        value = f"{year}-{''.join(secrets.choice(NUMBER_ALPHABET) for _ in range(6))}"
        if not Application.objects.filter(number=value).exists():
            return value


def split_full_name(full_name: str) -> tuple[str, str, str]:
    """«Фамилия Имя Отчество» → (фамилия, имя, отчество). Одно слово — имя."""
    parts = full_name.split()
    if len(parts) == 1:
        return "", parts[0], ""
    return parts[0], parts[1], " ".join(parts[2:])
