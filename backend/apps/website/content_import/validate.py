"""Row validation: blocking errors vs warnings, and duplicate detection.

A row becomes ``{"key", "kind", "row", "values", "errors", "warnings",
"duplicate", ...}``. ``values`` are the cleaned model field values (JSON-safe:
dates as ISO strings) and are what the import writes — never anything sent by
the browser. Rules (see docs/content_import.md):

* errors (row cannot be imported): missing RU title / category / date, unknown
  category / status / branch, invalid date or number, end before start, text
  too long, the same record twice in the file;
* warnings (row can be imported): missing KG / EN translation, missing image,
  «published» in the file (imported as a draft), date without time, a news
  translation that the news model cannot store, an existing record (duplicate).

Nothing is invented: an empty optional cell stays empty.
"""
from __future__ import annotations

import datetime as dt
import re
import unicodedata

from django.utils import timezone
from django.utils.text import slugify

from apps.academy_news.models import Article
from apps.users.import_export.formats import parse_bool

from ..models import Achievement, Branch, Event
from .schema import LANGS, column_keys, normalize_header

MODELS = {"events": Event, "achievements": Achievement, "news": Article}
DATE_FIELD = {"events": "starts_at", "achievements": "date", "news": "published_at"}
MAX_LEN = {"title": 200, "excerpt": 300, "location": 255, "recipient": 200, "slug": 200, "verification_note": 2000,
           "cover": 500}
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

_DATE_FORMATS = ("%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y", "%d.%m.%y")
_DATETIME_FORMATS = ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M", "%Y-%m-%dT%H:%M:%S",
                     "%d.%m.%Y %H:%M", "%d.%m.%Y %H:%M:%S", "%d/%m/%Y %H:%M")

STATUS_ALIASES = {
    "draft": "draft", "черновик": "draft", "долбоор": "draft", "": "draft", "new": "draft",
    "review": "review", "на согласовании": "review", "на проверке": "review", "pending": "review",
    "needs verification": "review", "verify": "review", "проверка": "review", "текшерүүдө": "review",
    "published": "published", "опубликовано": "published", "опубликована": "published", "publish": "published",
    "жарыяланды": "published",
    "archived": "archived", "архив": "archived", "в архиве": "archived", "archive": "archived",
}


def clean_text(value: str) -> str:
    return _CONTROL.sub("", unicodedata.normalize("NFC", value or "")).strip()


def norm_title(value: str) -> str:
    return re.sub(r"\s+", " ", clean_text(value)).casefold().replace("ё", "е")


def parse_date(value: str) -> dt.date | None:
    text = value.strip()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}T00:00:00", text):  # Excel date cell
        text = text[:10]
    for fmt in _DATE_FORMATS:
        try:
            return dt.datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def parse_datetime(value: str) -> tuple[dt.datetime | None, bool]:
    """→ (aware datetime, has_time). Midnight from an Excel date cell counts as «no time»."""
    text = value.strip()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}T00:00:00", text):
        text = text[:10]
    for fmt in _DATETIME_FORMATS:
        try:
            return timezone.make_aware(dt.datetime.strptime(text, fmt)), True
        except ValueError:
            continue
    day = parse_date(text)
    if day:
        return timezone.make_aware(dt.datetime.combine(day, dt.time())), False
    return None, False


def _choice_lookup(kind: str) -> dict[str, str]:
    model = MODELS[kind]
    lookup = {}
    for value, label in model.Category.choices:
        for alias in (value, value.replace("_", " "), value.replace("_", "-"), label):
            lookup[norm_title(alias)] = value
    return lookup


def map_row(kind: str, raw: dict[str, str]) -> tuple[dict[str, str], list[str]]:
    """Header → canonical key. Returns (cells, unknown headers)."""
    known = column_keys(kind)
    cells, unknown = {}, []
    for header, value in raw.items():
        key = normalize_header(header)
        if key == "title" or key == "excerpt" or key == "body":  # no language suffix = Russian
            key = f"{key}_ru"
        if kind == "achievements" and key == "starts_at":
            key = "date"
        if kind == "news" and key in ("date", "starts_at"):
            key = "published_at"
        if key in known:
            if not cells.get(key):
                cells[key] = clean_text(value)
        elif value and header.strip():
            unknown.append(header.strip())
    return cells, unknown


class RowValidator:
    """Validates rows of one upload; remembers keys seen to catch in-file duplicates."""

    def __init__(self):
        self.seen: dict[tuple, int] = {}
        self.branches = {norm_title(n): pk for pk, *names in Branch.objects.values_list("pk", "name", "name_ky", "name_en")
                         for n in names if n}
        self.categories = {kind: _choice_lookup(kind) for kind in MODELS}

    def validate(self, kind: str, row_number: int, raw: dict[str, str]) -> dict:
        cells, unknown = map_row(kind, raw)
        errors: list[dict] = []
        warnings: list[dict] = []
        values: dict = {}

        def err(field, message):
            errors.append({"field": field, "message": message})

        def warn(field, message):
            warnings.append({"field": field, "message": message})

        # Texts and translations
        for base in ("title", "excerpt", "body"):
            for lang in LANGS:
                text = cells.get(f"{base}_{lang}", "")
                if base in MAX_LEN and len(text) > MAX_LEN[base]:
                    err(f"{base}_{lang}", f"Больше {MAX_LEN[base]} символов ({len(text)}).")
                field = base if lang == "ru" else f"{base}_{lang}"
                values[field] = text
        if not values["title"]:
            err("title_ru", "Нет названия на русском (обязательное поле).")
        languages = {lang: bool(cells.get(f"title_{lang}")) for lang in LANGS}
        if kind == "news":
            extra = [lang.upper().replace("KY", "KG") for lang in ("ky", "en")
                     if any(cells.get(f"{b}_{lang}") for b in ("title", "excerpt", "body"))]
            if extra:
                warn("title_ky", f"Новости хранятся только на русском: перевод {', '.join(extra)} сохранён "
                                 "в истории импорта, но не в новости.")
            translations = {f: values.pop(f) for f in list(values) if f.endswith(("_ky", "_en"))}
        else:
            translations = {}
            for lang, name in (("ky", "KG"), ("en", "EN")):
                if values["title"] and not cells.get(f"title_{lang}"):
                    warn(f"title_{lang}", f"Нет перевода {name} — на сайте будет показан русский текст.")
                elif cells.get(f"title_{lang}") and values["body"] and not cells.get(f"body_{lang}"):
                    warn(f"body_{lang}", f"Описание без перевода {name}.")

        # Category
        category_raw = cells.get("category", "")
        if not category_raw:
            err("category", "Не указана категория.")
        else:
            category = self.categories[kind].get(norm_title(category_raw))
            if category:
                values["category"] = category
            else:
                err("category", f"Неизвестная категория «{category_raw}».")

        # Dates
        date_key = DATE_FIELD[kind]
        date_raw = cells.get(date_key, "")
        if kind == "events":
            start, has_time = parse_datetime(date_raw) if date_raw else (None, False)
            if not date_raw:
                err("starts_at", "Не указана дата начала.")
            elif not start:
                err("starts_at", f"Неверная дата «{date_raw}».")
            else:
                values["starts_at"] = start.isoformat()
                if not has_time:
                    warn("starts_at", "Время начала не указано (стоит 00:00) — уточните перед публикацией.")
            end_raw = cells.get("ends_at", "")
            if end_raw:
                end, _ = parse_datetime(end_raw)
                if not end:
                    err("ends_at", f"Неверная дата окончания «{end_raw}».")
                elif start and end < start:
                    err("ends_at", "Окончание раньше начала.")
                else:
                    values["ends_at"] = end.isoformat()
            values["location"] = cells.get("location", "")
            if len(values["location"]) > MAX_LEN["location"]:
                err("location", f"Место длиннее {MAX_LEN['location']} символов.")
            branch_raw = cells.get("branch", "")
            if branch_raw:
                branch = self.branches.get(norm_title(branch_raw))
                if branch:
                    values["branch_id"] = branch
                else:
                    err("branch", f"Филиал «{branch_raw}» не найден — создайте его в разделе «Главная» или очистите ячейку.")
            reg_raw = cells.get("registration_enabled", "")
            try:
                values["registration_enabled"] = parse_bool(reg_raw, default=False)
            except ValueError:
                err("registration_enabled", f"Неверное значение «{reg_raw}» (нужно да / нет).")
            limit_raw = cells.get("registration_limit", "")
            if limit_raw:
                if limit_raw.isdigit() and int(limit_raw) > 0:
                    values["registration_limit"] = int(limit_raw)
                else:
                    err("registration_limit", f"Количество мест должно быть целым числом больше 0 («{limit_raw}»).")
            if values.get("registration_enabled") and start and start < timezone.now():
                warn("registration_enabled", "Регистрация открыта, но мероприятие уже прошло.")
        elif kind == "achievements":
            day = parse_date(date_raw) if date_raw else None
            if not date_raw:
                err("date", "Не указана дата.")
            elif not day:
                err("date", f"Неверная дата «{date_raw}».")
            else:
                values["date"] = day.isoformat()
                if day > timezone.localdate():
                    warn("date", "Дата достижения в будущем — проверьте.")
            values["recipient"] = cells.get("recipient", "")
            if len(values["recipient"]) > MAX_LEN["recipient"]:
                err("recipient", f"Длиннее {MAX_LEN['recipient']} символов.")
        else:  # news
            if date_raw:
                when, _ = parse_datetime(date_raw)
                if when:
                    values["published_at"] = when.isoformat()
                else:
                    err("published_at", f"Неверная дата «{date_raw}».")

        # Status: never published
        status_raw = cells.get("status", "")
        status = STATUS_ALIASES.get(norm_title(status_raw))
        if status is None:
            err("status", f"Неизвестный статус «{status_raw}» (draft, review, archived).")
            status = "draft"
        if status == "published":
            warn("status", "«Опубликовано» в файле: импортируется черновиком, публикация — после проверки.")
            status = "draft"
        if kind == "news" and status != "draft":
            warn("status", "Новость импортируется черновиком (у новостей нет согласования и архива).")
            status = "draft"
        values["status"] = status

        # Slug
        slug_raw = cells.get("slug", "")
        if slug_raw:
            slug = slugify(slug_raw)
            if not slug or len(slug) > MAX_LEN["slug"]:
                err("slug", f"Неверный адрес «{slug_raw}» (латиница, цифры, дефис).")
            else:
                values["slug"] = slug

        # Image and notes (kept as text; nothing is downloaded)
        cover = cells.get("cover", "")[:MAX_LEN["cover"]]
        if not cover:
            warn("cover", "Нет изображения — добавьте обложку в редакторе перед публикацией.")
        note = cells.get("verification_note", "")[:MAX_LEN["verification_note"]]

        if unknown:
            warn("", f"Колонки не распознаны и пропущены: {', '.join(unknown[:6])}.")

        # Duplicates: in the file (error) and in the database (warning → skip / update)
        title_key = norm_title(values["title"])
        date_value = values.get(date_key, "")[:10] if kind != "news" else ""
        in_file_keys = [("slug", values["slug"])] if values.get("slug") else []
        if title_key:
            in_file_keys.append(("title", title_key, date_value))
        for k in in_file_keys:
            first = self.seen.get((kind, *k))
            if first:
                err("title_ru", f"Повтор строки {first} этого листа.")
                break
        else:
            for k in in_file_keys:
                self.seen[(kind, *k)] = row_number
        duplicate = find_duplicate(kind, values) if not errors else None
        if duplicate:
            warn("", f"Уже есть: «{duplicate['title']}» ({duplicate['status_label']}) — будет пропущено, "
                     "если не выбрать обновление.")

        return {
            "key": f"{kind}:{row_number}",
            "kind": kind,
            "row": row_number,
            "title": values["title"] or cells.get("title_ky") or cells.get("title_en") or "",
            "category": values.get("category", ""),
            "category_raw": category_raw,
            "date": values.get(date_key, "") or "",
            "languages": languages,
            "status": status,
            "status_raw": status_raw,
            "cover": cover,
            "verification_note": note,
            "translations": translations,
            "values": values,
            "errors": errors,
            "warnings": warnings,
            "duplicate": duplicate,
            "valid": not errors,
        }


def find_duplicate(kind: str, values: dict) -> dict | None:
    """Same slug, or the same title (case / spaces ignored) on the same date."""
    model = MODELS[kind]
    match = None
    if values.get("slug"):
        match = model.objects.filter(slug=values["slug"]).first()
    if match is None and values.get("title"):
        # Compared in Python: SQL case-insensitive matching is ASCII-only on some databases.
        qs = model.objects.all()
        if kind == "events" and values.get("starts_at"):
            qs = qs.filter(starts_at__date=dt.date.fromisoformat(values["starts_at"][:10]))
        elif kind == "achievements" and values.get("date"):
            qs = qs.filter(date=values["date"])
        target = norm_title(values["title"])
        pk = next((pk for pk, title in qs.values_list("pk", "title").iterator() if norm_title(title) == target), None)
        match = model.objects.filter(pk=pk).first() if pk else None
    if match is None:
        return None
    status = match.status
    published = status == "published"
    return {
        "id": match.pk,
        "title": match.title,
        "slug": match.slug,
        "status": status,
        "status_label": match.get_status_display(),
        "updatable": not published,
    }
