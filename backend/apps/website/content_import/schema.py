"""Columns of each importable content type.

Canonical column keys are what the templates contain (``title_ru``,
``starts_at`` …). Uploaded headers are normalised and also matched through
aliases, so «Название (RU)», «title ru», «Title_KG» or «Обложка» are read too.
Languages: ``ky`` is the site's code for Kyrgyz; ``kg`` is accepted as an alias.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from apps.academy_news.models import Article

from ..models import Achievement, Event

LANGS = ("ru", "ky", "en")
TYPES = ("events", "achievements", "news")
TYPE_LABEL = {"events": "Мероприятия", "achievements": "Достижения", "news": "Новости"}

# Sheet names accepted for each type (case-insensitive); README is ignored.
SHEET_ALIASES = {
    "events": {"events", "event", "мероприятия", "события", "иш-чаралар"},
    "achievements": {"achievements", "achievement", "достижения", "жетишкендиктер"},
    "news": {"news", "новости", "жаңылыктар", "articles"},
}


@dataclass(frozen=True)
class Column:
    key: str
    label: str
    required: bool = False
    help: str = ""
    example_values: str = ""


def _translated(base: str, label: str, required_ru: bool = False, help_: str = "") -> list[Column]:
    names = {"ru": "RU", "ky": "KG", "en": "EN"}
    return [Column(f"{base}_{lang}", f"{label} ({names[lang]})", required=required_ru and lang == "ru", help=help_) for lang in LANGS]


COMMON_TAIL = [
    Column("status", "Статус", help="draft (по умолчанию), review или archived. «published» будет импортирован как черновик.",
           example_values="draft, review, archived"),
    Column("cover", "Обложка (ссылка или имя файла)", help="Не загружается автоматически: сохраняется в заметке, "
           "изображение добавляется вручную в редакторе."),
    Column("verification_note", "Заметка для проверки", help="Что нужно проверить перед публикацией. Хранится в истории импорта."),
    Column("slug", "Адрес (slug)", help="Необязательно. Пусто — из названия. Используется для поиска дублей."),
]

COLUMNS: dict[str, list[Column]] = {
    "events": [
        *_translated("title", "Название", required_ru=True),
        *_translated("excerpt", "Короткое описание"),
        *_translated("body", "Описание"),
        Column("category", "Тип", required=True, help="Код или название типа мероприятия.",
               example_values=", ".join(Event.Category.values)),
        Column("starts_at", "Начало", required=True, help="ГГГГ-ММ-ДД ЧЧ:ММ или ДД.ММ.ГГГГ ЧЧ:ММ"),
        Column("ends_at", "Окончание", help="Необязательно, не раньше начала."),
        Column("location", "Место"),
        Column("branch", "Филиал", help="Название существующего филиала (необязательно)."),
        Column("registration_enabled", "Регистрация открыта", help="да / нет (по умолчанию нет)"),
        Column("registration_limit", "Мест", help="Целое число, пусто — без ограничения."),
        *COMMON_TAIL,
    ],
    "achievements": [
        *_translated("title", "Название", required_ru=True),
        *_translated("excerpt", "Короткое описание"),
        *_translated("body", "Описание"),
        Column("category", "Категория", required=True, help="Код или название категории.",
               example_values=", ".join(Achievement.Category.values)),
        Column("date", "Дата", required=True, help="ГГГГ-ММ-ДД или ДД.ММ.ГГГГ"),
        Column("recipient", "Студент или организация", help="Только подтверждённые данные; имя ребёнка — с согласия семьи."),
        *COMMON_TAIL,
    ],
    "news": [
        *_translated("title", "Заголовок", required_ru=True,
                     help_="Новости академии хранятся на одном языке (RU): KG/EN сохраняются только в истории импорта."),
        *_translated("excerpt", "Краткое описание"),
        *_translated("body", "Текст"),
        Column("category", "Категория", required=True, help="Код или название категории новости.",
               example_values=", ".join(Article.Category.values)),
        Column("published_at", "Дата публикации", help="Дата, которая будет у новости после утверждения. Пусто — дата утверждения."),
        *[c for c in COMMON_TAIL if c.key != "status"],
        Column("status", "Статус", help="Новость всегда импортируется черновиком (draft).", example_values="draft"),
    ],
}

# Russian / English / Kyrgyz header words → canonical base names.
_WORDS = {
    "название": "title", "заголовок": "title", "аталышы": "title", "name": "title", "headline": "title",
    "краткое_описание": "excerpt", "короткое_описание": "excerpt", "анонс": "excerpt", "summary": "excerpt", "short_description": "excerpt",
    "описание": "body", "текст": "body", "description": "body", "content": "body", "text": "body",
    "категория": "category", "тип": "category", "type": "category",
    "статус": "status",
    "дата": "date", "начало": "starts_at", "start": "starts_at", "start_date": "starts_at", "date_start": "starts_at", "datetime": "starts_at",
    "окончание": "ends_at", "end": "ends_at", "end_date": "ends_at",
    "место": "location", "venue": "location", "address": "location", "адрес": "location",
    "филиал": "branch",
    "регистрация": "registration_enabled", "registration": "registration_enabled",
    "мест": "registration_limit", "лимит": "registration_limit", "capacity": "registration_limit", "seats": "registration_limit",
    "обложка": "cover", "изображение": "cover", "фото": "cover", "image": "cover", "image_url": "cover", "cover_url": "cover", "photo": "cover",
    "заметка": "verification_note", "примечание": "verification_note", "проверка": "verification_note", "notes": "verification_note",
    "note": "verification_note", "verification": "verification_note", "verification_notes": "verification_note",
    "получатель": "recipient", "участник": "recipient", "студент_или_организация": "recipient", "winner": "recipient",
    "дата_публикации": "published_at", "publish_date": "published_at", "publication_date": "published_at", "published": "published_at",
}
_LANG_ALIASES = {"ru": "ru", "rus": "ru", "kg": "ky", "ky": "ky", "kgz": "ky", "kyr": "ky", "en": "en", "eng": "en"}


def normalize_header(raw: str) -> str:
    """«Название (RU)*» → title_ru, «Title KG» → title_ky, «Обложка» → cover."""
    text = (raw or "").strip().casefold().replace("ё", "е").rstrip("*").strip()
    text = re.sub(r"[\s\-()\[\]/:.]+", "_", text).strip("_")
    lang = None
    match = re.match(r"^(.*?)_(ru|rus|kg|ky|kgz|kyr|en|eng)$", text)
    if match:
        text, lang = match.group(1), _LANG_ALIASES[match.group(2)]
    base = _WORDS.get(text, text)
    return f"{base}_{lang}" if lang else base


def column_keys(kind: str) -> set[str]:
    return {c.key for c in COLUMNS[kind]}


def choices_for(kind: str) -> list[tuple[str, str]]:
    model = {"events": Event, "achievements": Achievement, "news": Article}[kind]
    return list(model.Category.choices)
