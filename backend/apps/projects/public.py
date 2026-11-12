"""Public student projects gallery — what OkurmenKids Digital may publish.

Read-only, no login (/api/v1/public/projects/). The LMS stays the only place
where projects are created, edited and published (see access.py); this
module only reads the projects a trainer (or an Admin) has **published**.
Drafts never leave the LMS.

A closed whitelist of fields — nothing else is ever serialised:

* project: opaque public key (never the database id), title, short and full
  description, technologies, a category, the project date, the demo link
  (http/https only) and the images;
* student: first name + last-name initial («Алия С.»), and nothing at all
  when the student's privacy switch ``show_in_leaderboard`` is off (the same
  switch parents use for the public leaderboard);
* group: its name;
* trainer: the name, only when ``PUBLIC_PROJECTS_SHOW_TRAINER`` is on
  (off by default).

Never published: the trainer's comment and rating, GitHub / Figma links,
student contacts, status, ids, author account.

The whole published set is small (hundreds), so it is built once, cached
(version bumped on every project / image / technology / student change) and
filtered in Python, like the public leaderboard.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
from urllib.parse import urlparse

from django.conf import settings
from django.core.cache import cache
from django.db.models import Prefetch
from rest_framework.exceptions import ValidationError

from apps.leaderboard.services import public_name

from .images import image_asset
from .models import ProjectImage, StudentProject

_VERSION_KEY = "public_projects:version"

DEFAULT_PAGE_SIZE = 12
MAX_PAGE_SIZE = 48

# Gallery filter → technology names (case-insensitive). A project belongs to
# every category one of its technologies maps to; «other» = none of them.
CATEGORIES: dict[str, set[str]] = {
    "html-css": {"html", "css", "html/css", "html5", "css3", "scss", "sass", "less", "tailwind", "tailwind css",
                 "tailwindcss", "bootstrap", "верстка", "вёрстка"},
    "javascript": {"javascript", "js", "typescript", "ts", "node", "node.js", "nodejs", "jquery", "es6"},
    "react": {"react", "react.js", "reactjs", "react native", "next", "next.js", "nextjs", "redux"},
    "python": {"python", "django", "flask", "fastapi", "pygame", "aiogram", "telegram bot", "python 3"},
}
CATEGORY_IDS = (*CATEGORIES, "other")


def config() -> dict:
    return {
        "show_trainer": getattr(settings, "PUBLIC_PROJECTS_SHOW_TRAINER", False),
        "cache_seconds": getattr(settings, "PUBLIC_PROJECTS_CACHE_SECONDS", 120),
    }


# ---------------------------------------------------------------------------
# Opaque keys
# ---------------------------------------------------------------------------

def public_key(pk: int) -> str:
    """Stable, non-guessable — the page address never reveals the database id
    or how many projects (drafts included) exist."""
    digest = hmac.new(settings.SECRET_KEY.encode(), f"public-projects:project:{pk}".encode(), hashlib.sha256).digest()
    return base64.b32encode(digest[:8]).decode().rstrip("=").lower()


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------

def cache_version() -> int:
    return cache.get(_VERSION_KEY) or 1


def bump_cache_version(**_kwargs) -> None:
    try:
        cache.incr(_VERSION_KEY)
    except ValueError:
        cache.set(_VERSION_KEY, 2, None)


def _cached(name: str, build):
    seconds = config()["cache_seconds"]
    if not seconds:
        return build()
    key = f"public_projects:{cache_version()}:{name}"
    value = cache.get(key)
    if value is None:
        value = build()
        cache.set(key, value, seconds)
    return value


# ---------------------------------------------------------------------------
# Building the public records
# ---------------------------------------------------------------------------

def categories_of(technologies: list[str]) -> list[str]:
    names = {name.strip().casefold() for name in technologies}
    found = [cat for cat, aliases in CATEGORIES.items() if names & aliases]
    return found or ["other"]


def _safe_url(value: str) -> str | None:
    value = (value or "").strip()
    if not value:
        return None
    parsed = urlparse(value)
    return value if parsed.scheme in ("http", "https") and parsed.netloc else None


def _image_url(field) -> str | None:
    try:
        return field.url if field else None
    except ValueError:
        return None


def _student_name(student) -> str | None:
    if not student.show_in_leaderboard:
        return None
    return public_name(student.first_name, student.last_name) or None


def _record(project: StudentProject, show_trainer: bool) -> dict:
    images = [img for img in project.images.all() if img.image]  # prefetched, ordered
    cover = next((img for img in images if img.is_cover), images[0] if images else None)
    technologies = [tech.name for tech in project.technologies.all()]
    trainer = None
    if show_trainer and project.created_by_id:
        trainer = project.created_by.get_full_name() or None
    return {
        "key": public_key(project.pk),
        "title": project.title,
        "short_description": project.short_description,
        "description": project.description,
        "technologies": technologies,
        "categories": categories_of(technologies),
        "date": project.project_date.isoformat(),
        "student": _student_name(project.student),
        "group": project.group.name if project.group_id else None,
        "trainer": trainer,
        "demo_url": _safe_url(project.demo_url),
        "cover_url": _image_url(cover.image) if cover else None,
        # The same cover as WebP copies with its size ({url, thumb, width, height}) — cards use `thumb`.
        "cover": image_asset(cover.image) if cover else None,
        "images": [{"url": url, "is_cover": img.is_cover} for img in images if (url := _image_url(img.image))],
    }


def published_queryset():
    return (
        StudentProject.objects.filter(status=StudentProject.Status.PUBLISHED)
        .select_related("student", "group", "created_by")
        .prefetch_related("technologies", Prefetch("images", queryset=ProjectImage.objects.order_by("order", "id")))
        .order_by("-project_date", "-id")
    )


def published() -> list[dict]:
    """Every published project as a public record, newest first (cached)."""
    show_trainer = config()["show_trainer"]
    return _cached(f"all:{int(show_trainer)}", lambda: [_record(p, show_trainer) for p in published_queryset()])


# ---------------------------------------------------------------------------
# Responses
# ---------------------------------------------------------------------------

LIST_FIELDS = ("key", "title", "short_description", "technologies", "categories", "date", "student", "group",
               "cover_url", "cover")


def _int(value, name: str, low: int, high: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        raise ValidationError({name: "Ожидается число."})
    if not low <= number <= high:
        raise ValidationError({name: f"Допустимо от {low} до {high}."})
    return number


def _matches(record: dict, query: str) -> bool:
    haystack = [record["title"], record["short_description"], record["group"] or "", record["student"] or "",
                *record["technologies"]]
    # The student's name is searchable only when it is shown at all (it is
    # None for a hidden student), so a search can never reveal a hidden one.
    return any(query in text.casefold() for text in haystack)


TECHNOLOGY_FACETS = 24


def _technology_facets(records: list[dict]) -> list[dict]:
    """The technologies of the current result set, most used first (for filter chips)."""
    totals: dict[str, int] = {}
    spellings: dict[str, dict[str, int]] = {}
    for record in records:
        seen = {t.strip().casefold(): t.strip() for t in record["technologies"] if t.strip()}
        for key, name in seen.items():
            totals[key] = totals.get(key, 0) + 1
            spellings.setdefault(key, {})[name] = spellings.setdefault(key, {}).get(name, 0) + 1

    def label(key: str) -> str:
        # The most used spelling; on a tie the capitalised one («Python», not «python»).
        return max(spellings[key].items(), key=lambda item: (item[1], item[0] != item[0].lower(), item[0]))[0]

    ranked = sorted(totals, key=lambda key: (-totals[key], key))
    return [{"name": label(key), "count": totals[key]} for key in ranked[:TECHNOLOGY_FACETS]]


def gallery(*, q: str = "", category: str = "", technology: str = "", page=None, page_size=None) -> dict:
    records = published()
    query = (q or "").strip().casefold()[:100]
    if query:
        records = [r for r in records if _matches(r, query)]
    # Facets of the search result; the technology filter itself (exact name,
    # case-insensitive) narrows the list and the category counts.
    technologies = _technology_facets(records)
    technology = (technology or "").strip().casefold()[:60]
    if technology:
        records = [r for r in records if technology in {t.casefold() for t in r["technologies"]}]

    counts = {"all": len(records), **{cat: 0 for cat in CATEGORY_IDS}}
    for record in records:
        for cat in record["categories"]:
            counts[cat] += 1

    category = (category or "").strip().lower()
    if category and category != "all":
        if category not in CATEGORY_IDS:
            raise ValidationError({"category": f"Одно из: all, {', '.join(CATEGORY_IDS)}."})
        records = [r for r in records if category in r["categories"]]

    size = DEFAULT_PAGE_SIZE if page_size in (None, "") else _int(page_size, "page_size", 1, MAX_PAGE_SIZE)
    num_pages = max(1, -(-len(records) // size))
    number = 1 if page in (None, "") else _int(page, "page", 1, 10_000)
    offset = (number - 1) * size
    return {
        "count": len(records),
        "page": number,
        "page_size": size,
        "num_pages": num_pages,
        "counts": counts,
        "technologies": technologies,
        "results": [{field: r[field] for field in LIST_FIELDS} for r in records[offset:offset + size]],
    }


def detail(key: str) -> dict | None:
    key = (key or "").strip().lower()
    if not key.isalnum() or len(key) > 32:
        return None
    return next((r for r in published() if hmac.compare_digest(r["key"], key)), None)
