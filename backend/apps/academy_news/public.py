"""Public news API data (/api/v1/public/news/) — read-only, no login.

Only articles that are published **and** whose publication time has come;
drafts, unpublished and scheduled-for-later articles never leave the admin.
A closed whitelist of fields: slug, title, excerpt, body, category, date,
cover and photos (WebP copies, size, caption), and the author's name only
when the article says `show_author`.

The published set is small; it is built once, cached (version bumped on
every article / photo change) and filtered in Python — the publication time
is checked on every request, so a scheduled article appears on time.
"""
from __future__ import annotations

import datetime as dt

from django.conf import settings
from django.core.cache import cache
from django.db.models import Prefetch
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from .models import Article, ArticlePhoto

_VERSION_KEY = "public_news:version"
DEFAULT_PAGE_SIZE = 9
MAX_PAGE_SIZE = 36
RELATED = 3
CATEGORY_IDS = tuple(Article.Category.values)
LANGS = ("ru", "ky", "en")


def lang_of(value) -> str:
    value = (value or "").strip().lower()[:2]
    return value if value in LANGS else "ru"


def _tr(article: Article, field: str, lang: str) -> str:
    """The translation of a field (public site /ky, /en), falling back to Russian."""
    if lang != "ru":
        translated = (getattr(article, f"{field}_{lang}", "") or "").strip()
        if translated:
            return getattr(article, f"{field}_{lang}")
    return getattr(article, field, "") or ""


def cache_seconds() -> int:
    return getattr(settings, "PUBLIC_NEWS_CACHE_SECONDS", 120)


def cache_version() -> int:
    return cache.get(_VERSION_KEY) or 1


def bump_cache_version(**_kwargs) -> None:
    try:
        cache.incr(_VERSION_KEY)
    except ValueError:
        cache.set(_VERSION_KEY, 2, None)


def _url(field_file) -> str | None:
    try:
        return field_file.url if field_file else None
    except ValueError:
        return None


def _image(original, large, thumb, width, height, caption) -> dict | None:
    full = _url(large) or _url(original)
    if not full:
        return None
    return {"url": full, "thumb": _url(thumb) or full, "width": width, "height": height, "caption": caption or ""}


def _record(article: Article, lang: str = "ru") -> dict:
    cover = _image(article.cover, article.cover_large, article.cover_thumb, article.cover_width, article.cover_height,
                   article.cover_caption)
    photos = [
        image for photo in article.photos.all()
        if (image := _image(photo.image, photo.large, photo.thumb, photo.width, photo.height, photo.caption))
    ]
    author = None
    if article.show_author and article.author_id:
        author = article.author.get_full_name() or None
    return {
        "slug": article.slug,
        "title": _tr(article, "title", lang),
        "excerpt": _tr(article, "excerpt", lang),
        "body": _tr(article, "body", lang),
        # SEO overrides are written in Russian; /ky and /en use the translated texts.
        "seo_title": (article.seo_title or None) if lang == "ru" else None,
        "seo_description": (article.seo_description or None) if lang == "ru" else None,
        "category": article.category,
        "published_at": article.published_at.isoformat(),
        "is_featured": article.is_featured,
        "author": author,
        "cover": cover,
        "photos": photos,
        "_ts": article.published_at.timestamp(),
    }


def _all_published(lang: str = "ru") -> list[dict]:
    def build():
        qs = (
            Article.objects.filter(status=Article.Status.PUBLISHED)
            .select_related("author")
            .prefetch_related(Prefetch("photos", queryset=ArticlePhoto.objects.order_by("order", "id")))
            .order_by("-published_at", "-id")
        )
        return [_record(article, lang) for article in qs]

    seconds = cache_seconds()
    if not seconds:
        return build()
    key = f"public_news:{cache_version()}:all:{lang}"
    value = cache.get(key)
    if value is None:
        value = build()
        cache.set(key, value, seconds)
    return value


def visible(now: dt.datetime | None = None, lang: str = "ru") -> list[dict]:
    """Published articles whose time has come, newest first."""
    ts = (now or timezone.now()).timestamp()
    return [record for record in _all_published(lang_of(lang)) if record["_ts"] <= ts]


CARD_FIELDS = ("slug", "title", "excerpt", "category", "published_at", "cover")


def card(record: dict) -> dict:
    return {**{field: record[field] for field in CARD_FIELDS}, "photo_count": len(record["photos"]) + bool(record["cover"])}


def _int(value, name: str, low: int, high: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        raise ValidationError({name: "Ожидается число."})
    if not low <= number <= high:
        raise ValidationError({name: f"Допустимо от {low} до {high}."})
    return number


def listing(*, q: str = "", category: str = "", page=None, page_size=None, lang: str = "ru") -> dict:
    records = visible(lang=lang)
    query = (q or "").strip().casefold()[:100]
    category = (category or "").strip().lower()
    if category and category != "all" and category not in CATEGORY_IDS:
        raise ValidationError({"category": f"Одно из: all, {', '.join(CATEGORY_IDS)}."})

    # The featured article: the newest one marked «Главная новость», else the
    # newest overall — shown on the first page when nothing is filtered.
    featured = next((r for r in records if r["is_featured"]), records[0] if records else None)

    if query:
        records = [r for r in records if query in r["title"].casefold() or query in r["excerpt"].casefold()
                   or query in r["body"].casefold()]
    counts = {"all": len(records), **{cat: 0 for cat in CATEGORY_IDS}}
    for record in records:
        counts[record["category"]] += 1
    if category and category != "all":
        records = [r for r in records if r["category"] == category]

    size = DEFAULT_PAGE_SIZE if page_size in (None, "") else _int(page_size, "page_size", 1, MAX_PAGE_SIZE)
    number = 1 if page in (None, "") else _int(page, "page", 1, 10_000)
    show_featured = featured is not None and not query and (not category or category == "all")
    if show_featured:
        records = [r for r in records if r["slug"] != featured["slug"]]
    offset = (number - 1) * size
    return {
        "count": len(records),
        "page": number,
        "page_size": size,
        "num_pages": max(1, -(-len(records) // size)),
        "counts": counts,
        "featured": card(featured) if show_featured and number == 1 else None,
        "results": [card(r) for r in records[offset:offset + size]],
    }


def article(slug: str, lang: str = "ru") -> dict | None:
    slug = (slug or "").strip().lower()
    if not slug or len(slug) > 220:
        return None
    records = visible(lang=lang)
    record = next((r for r in records if r["slug"] == slug), None)
    if record is None:
        return None
    others = [r for r in records if r["slug"] != slug]
    same = [r for r in others if r["category"] == record["category"]]
    related = (same + [r for r in others if r["category"] != record["category"]])[:RELATED]
    detail = {key: value for key, value in record.items() if not key.startswith("_") and key != "is_featured"}
    return {**detail, "related": [card(r) for r in related]}
