"""Public website data (/api/v1/public/site/) — read-only, no login.

Only records that are **published and whose publication time has come**
(drafts, «на согласовании», archived and scheduled-for-later never leave the
LMS) through a closed whitelist of fields. Personal data is never returned:
no registrations, no leads, no contacts of trainers, no LMS ids of students.

Each content type is built once per language and cached (the version is
bumped by any change, see signals.py); the publication time is checked on
every request, so scheduled records appear on time.
"""
from __future__ import annotations

import datetime as dt

from django.conf import settings
from django.core import signing
from django.core.cache import cache
from django.db.models import Count, Prefetch, Q
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.academy_news import public as news_public
from apps.projects import public as projects_public

from .markup import lines, video_embed
from .models import (
    Achievement, AchievementPhoto, Branch, CoursePage, Event, EventPhoto, EventRegistration, HomeSection,
    PromoBanner, SiteSettings, Statistic, TeamMember, Testimonial, Workflow,
)

LANGS = ("ru", "ky", "en")
_VERSION_KEY = "public_site:version"
PREVIEW_SALT = "website.preview"
PREVIEW_MAX_AGE = 7 * 24 * 3600
DEFAULT_PAGE_SIZE = 9
MAX_PAGE_SIZE = 36
RELATED = 3

DEFAULT_SECTIONS = [key for key, _ in HomeSection.Key.choices]


def cache_seconds() -> int:
    return getattr(settings, "PUBLIC_SITE_CACHE_SECONDS", 120)


def cache_version() -> int:
    return cache.get(_VERSION_KEY) or 1


def bump_cache_version(**_kwargs) -> None:
    try:
        cache.incr(_VERSION_KEY)
    except ValueError:
        cache.set(_VERSION_KEY, 2, None)


def _cached(name: str, build):
    seconds = cache_seconds()
    if not seconds:
        return build()
    key = f"public_site:{cache_version()}:{name}"
    value = cache.get(key)
    if value is None:
        value = build()
        cache.set(key, value, seconds)
    return value


def lang_of(value) -> str:
    value = (value or "").strip().lower()[:2]
    return value if value in LANGS else "ru"


def tr(obj, field: str, lang: str) -> str:
    """The translation of a field, falling back to Russian."""
    if lang != "ru":
        translated = getattr(obj, f"{field}_{lang}", "") or ""
        if translated.strip():
            return translated
    return getattr(obj, field, "") or ""


def _url(field_file) -> str | None:
    try:
        return field_file.url if field_file else None
    except ValueError:
        return None


def _image(original, large=None, thumb=None, width=None, height=None, caption="") -> dict | None:
    full = _url(large) or _url(original)
    if not full:
        return None
    return {"url": full, "thumb": _url(thumb) or full, "width": width, "height": height, "caption": caption or ""}


def _cover(obj) -> dict | None:
    return _image(obj.cover, obj.cover_large, obj.cover_thumb, obj.cover_width, obj.cover_height)


def _photos(obj) -> list[dict]:
    return [img for p in obj.photos.all() if (img := _image(p.image, p.large, p.thumb, p.width, p.height, p.caption))]


def _int(value, name: str, low: int, high: int, default: int) -> int:
    if value in (None, ""):
        return default
    try:
        number = int(value)
    except (TypeError, ValueError):
        raise ValidationError({name: "Ожидается число."})
    if not low <= number <= high:
        raise ValidationError({name: f"Допустимо от {low} до {high}."})
    return number


def _visible(records: list[dict], now: dt.datetime | None = None) -> list[dict]:
    ts = (now or timezone.now()).timestamp()
    return [r for r in records if r["_ts"] <= ts]


def _strip(record: dict) -> dict:
    return {k: v for k, v in record.items() if not k.startswith("_")}


def _page(records: list[dict], page, page_size, fields) -> dict:
    size = _int(page_size, "page_size", 1, MAX_PAGE_SIZE, DEFAULT_PAGE_SIZE)
    number = _int(page, "page", 1, 10_000, 1)
    offset = (number - 1) * size
    return {
        "count": len(records),
        "page": number,
        "page_size": size,
        "num_pages": max(1, -(-len(records) // size)),
        "results": [{f: r[f] for f in fields if f in r} for r in records[offset:offset + size]],
    }


# ---------------------------------------------------------------------------
# Settings, contacts, homepage
# ---------------------------------------------------------------------------

def _social(value: str, base: str) -> str | None:
    value = (value or "").strip()
    if not value:
        return None
    if value.startswith(("http://", "https://")):
        return value
    return base + value.lstrip("@")


def _whatsapp(value: str) -> str | None:
    digits = "".join(ch for ch in value or "" if ch.isdigit())
    return f"https://wa.me/{digits}" if digits else None


def _site_data(lang: str) -> dict:
    def build():
        s = SiteSettings.load()
        branches = [
            {
                "id": b.pk,
                "name": tr(b, "name", lang),
                "address": tr(b, "address", lang),
                "phone": b.phone,
                "working_hours": b.working_hours,
                "map_url": b.map_url or None,
                "latitude": float(b.latitude) if b.latitude is not None else None,
                "longitude": float(b.longitude) if b.longitude is not None else None,
            }
            for b in Branch.objects.filter(is_active=True)
        ]
        configured = {section.key: section for section in HomeSection.objects.all()}
        ordered = sorted(DEFAULT_SECTIONS, key=lambda k: (configured[k].order if k in configured else 1000 + DEFAULT_SECTIONS.index(k)))
        sections = [
            {"key": key, "title": tr(configured[key], "title", lang) if key in configured else ""}
            for key in ordered if key not in configured or configured[key].is_visible
        ]
        return {
            "hero": {
                "title": tr(s, "hero_title", lang),
                "subtitle": tr(s, "hero_subtitle", lang),
                "image": _image(s.hero_image),
                "primary_cta": {"label": s.primary_cta_label, "url": s.primary_cta_url},
                "secondary_cta": {"label": s.secondary_cta_label, "url": s.secondary_cta_url},
            },
            "intro_video": video_embed(s.intro_video_url),
            "seo": {
                "title": tr(s, "seo_title", lang) or None,
                "description": tr(s, "seo_description", lang) or None,
                "image": _image(s.og_image),
            },
            "about": {
                "story": tr(s, "about_story", lang),
                "mission": tr(s, "mission", lang),
                "vision": tr(s, "vision", lang),
            },
            "contacts": {
                "phone": s.phone or None,
                "whatsapp": _whatsapp(s.whatsapp),
                "telegram": _social(s.telegram, "https://t.me/"),
                "instagram": _social(s.instagram, "https://instagram.com/"),
                "facebook": _social(s.facebook, "https://facebook.com/"),
                "youtube": _social(s.youtube, "https://youtube.com/@"),
                "tiktok": _social(s.tiktok, "https://tiktok.com/@"),
                "email": s.email or None,
                "working_hours": s.working_hours or None,
            },
            "branches": branches,
            "stats": [{"value": st.value, "label": tr(st, "label", lang)} for st in Statistic.objects.filter(is_active=True)],
            "sections": sections,
            "_banners": [
                {
                    "title": tr(b, "title", lang),
                    "text": tr(b, "text", lang),
                    "image": _image(b.image),
                    "cta_label": b.cta_label,
                    "cta_url": b.cta_url,
                    "_from": b.starts_at.timestamp() if b.starts_at else None,
                    "_to": b.ends_at.timestamp() if b.ends_at else None,
                }
                for b in PromoBanner.objects.filter(is_active=True)
            ],
            "_featured_projects": list(s.featured_projects.values_list("pk", flat=True)),
            "_featured_news": list(s.featured_news.values_list("slug", flat=True)),
        }

    return _cached(f"site:{lang}", build)


def site(lang: str) -> dict:
    data = _site_data(lang)
    now = timezone.now().timestamp()
    banners = [
        {k: v for k, v in b.items() if not k.startswith("_")}
        for b in data["_banners"]
        if (b["_from"] is None or b["_from"] <= now) and (b["_to"] is None or now <= b["_to"])
    ]
    return {**_strip(data), "banners": banners}


# ---------------------------------------------------------------------------
# Courses
# ---------------------------------------------------------------------------

COURSE_CARD = ("slug", "title", "tagline", "icon", "cover", "age_min", "age_max", "duration", "schedule",
               "lessons", "price", "is_featured")


def _course_record(page: CoursePage, lang: str) -> dict:
    curriculum = []
    for line in lines(tr(page, "curriculum", lang)):
        title, _, text = line.partition(":")
        curriculum.append({"title": title.strip(), "text": text.strip()})
    course = page.course
    return {
        "slug": page.slug,
        "title": tr(page, "title", lang),
        "tagline": tr(page, "tagline", lang),
        "icon": page.icon,
        "cover": _cover(page),
        "age_min": page.age_min,
        "age_max": page.age_max,
        "duration": tr(page, "duration", lang) or None,
        "schedule": tr(page, "schedule", lang) or None,
        "lessons": course.count_lesson if course else None,
        "price": page.price or None,
        "is_featured": page.is_featured,
        "body": tr(page, "body", lang),
        "outcomes": lines(tr(page, "outcomes", lang)),
        "curriculum": curriculum,
        "subjects": [s.name for s in course.subjects.all()] if course else [],
        "project_category": page.project_category or None,
        # SEO overrides are written in Russian; /ky and /en use the translated texts.
        "seo_title": (page.seo_title or None) if lang == "ru" else None,
        "seo_description": (page.seo_description or None) if lang == "ru" else None,
        "updated_at": page.updated_at.isoformat(),
        "_ts": page.published_at.timestamp(),
    }


def _courses(lang: str) -> list[dict]:
    def build():
        qs = (CoursePage.objects.filter(status=Workflow.PUBLISHED)
              .select_related("course").prefetch_related("course__subjects"))
        return [_course_record(p, lang) for p in qs]
    return _cached(f"courses:{lang}", build)


def courses(lang: str) -> dict:
    return {"results": [{f: r[f] for f in COURSE_CARD} for r in _visible(_courses(lang))]}


def course(slug: str, lang: str) -> dict | None:
    record = next((r for r in _visible(_courses(lang)) if r["slug"] == slug), None)
    if record is None:
        return None
    projects = []
    if record["project_category"]:
        projects = [p for p in projects_public.published() if record["project_category"] in p["categories"]][:3]
    return {**_strip(record), "projects": [project_card(p) for p in projects]}


# ---------------------------------------------------------------------------
# Student projects / news (existing public APIs, reused)
# ---------------------------------------------------------------------------

def project_card(record: dict) -> dict:
    return {f: record[f] for f in projects_public.LIST_FIELDS}


def featured_projects(ids: list[int], limit: int = 6) -> list[dict]:
    records = projects_public.published()
    if ids:
        keys = {projects_public.public_key(pk) for pk in ids}
        chosen = [r for r in records if r["key"] in keys]
        if chosen:
            return [project_card(r) for r in chosen[:limit]]
    return [project_card(r) for r in records[:limit]]


def featured_news(slugs: list[str], limit: int = 3, lang: str = "ru") -> list[dict]:
    records = news_public.visible(lang=lang)
    if slugs:
        chosen = [r for r in records if r["slug"] in set(slugs)]
        if chosen:
            return [news_public.card(r) for r in chosen[:limit]]
    return [news_public.card(r) for r in records[:limit]]


# ---------------------------------------------------------------------------
# Events
# ---------------------------------------------------------------------------

EVENT_CARD = ("slug", "title", "excerpt", "category", "starts_at", "ends_at", "location", "branch", "cover",
              "phase", "registration_open", "is_featured")
EVENT_PHASES = ("upcoming", "ongoing", "completed")


def _event_record(event: Event, lang: str) -> dict:
    return {
        "slug": event.slug,
        "title": tr(event, "title", lang),
        "excerpt": tr(event, "excerpt", lang),
        "body": tr(event, "body", lang),
        "category": event.category,
        "starts_at": event.starts_at.isoformat(),
        "ends_at": event.ends_at.isoformat() if event.ends_at else None,
        "location": event.location or None,
        "branch": tr(event.branch, "name", lang) if event.branch_id else None,
        "branch_address": tr(event.branch, "address", lang) if event.branch_id else None,
        "cover": _cover(event),
        "photos": _photos(event),
        "is_featured": event.is_featured,
        # SEO overrides are written in Russian; /ky and /en use the translated texts.
        "seo_title": (event.seo_title or None) if lang == "ru" else None,
        "seo_description": (event.seo_description or None) if lang == "ru" else None,
        "updated_at": event.updated_at.isoformat(),
        "_ts": event.published_at.timestamp(),
        "_start": event.starts_at.timestamp(),
        "_end": (event.ends_at or event.starts_at).timestamp(),
        "_reg": event.registration_enabled,
        "_limit": event.registration_limit,
        "_deadline": (event.registration_deadline or event.starts_at).timestamp(),
        "_taken": getattr(event, "taken", 0) or 0,
    }


def _events(lang: str) -> list[dict]:
    def build():
        qs = (Event.objects.filter(status=Workflow.PUBLISHED).select_related("branch")
              .prefetch_related(Prefetch("photos", queryset=EventPhoto.objects.order_by("order", "id")))
              .annotate(taken=Count("registrations", filter=~Q(registrations__status=EventRegistration.Status.CANCELLED))))
        return [_event_record(e, lang) for e in qs]
    return _cached(f"events:{lang}", build)


def _event_live(record: dict, now: float) -> dict:
    """Phase and registration are time-dependent — computed per request."""
    if now < record["_start"]:
        phase = "upcoming"
    elif now <= max(record["_end"], record["_start"] + (0 if record["ends_at"] else 6 * 3600)):
        phase = "ongoing"
    else:
        phase = "completed"
    spots_left = None
    if record["_limit"] is not None:
        spots_left = max(0, record["_limit"] - record["_taken"])
    is_open = bool(record["_reg"] and now <= record["_deadline"] and (spots_left is None or spots_left > 0))
    return {
        **record,
        "phase": phase,
        "registration_open": is_open,
        "registration": {
            "enabled": record["_reg"],
            "open": is_open,
            "deadline": dt.datetime.fromtimestamp(record["_deadline"], tz=dt.timezone.utc).isoformat() if record["_reg"] else None,
            "spots_left": spots_left,
        },
    }


def _live_events(lang: str) -> list[dict]:
    now = timezone.now().timestamp()
    return [_event_live(r, now) for r in _visible(_events(lang))]


def events(lang: str, *, phase="", category="", page=None, page_size=None) -> dict:
    records = _live_events(lang)
    phase = (phase or "").strip().lower()
    if phase and phase != "all" and phase not in EVENT_PHASES:
        raise ValidationError({"phase": "Одно из: all, upcoming, ongoing, completed."})
    counts = {"all": len(records), **{p: 0 for p in EVENT_PHASES}}
    for r in records:
        counts[r["phase"]] += 1
    category = (category or "").strip().lower()
    if category and category != "all":
        if category not in Event.Category.values:
            raise ValidationError({"category": f"Одно из: all, {', '.join(Event.Category.values)}."})
        records = [r for r in records if r["category"] == category]
    if phase and phase != "all":
        records = [r for r in records if r["phase"] == phase]
    # Upcoming and ongoing — the nearest first; completed — the latest first.
    active = sorted((r for r in records if r["phase"] != "completed"), key=lambda r: r["_start"])
    done = sorted((r for r in records if r["phase"] == "completed"), key=lambda r: -r["_start"])
    return {**_page(active + done, page, page_size, EVENT_CARD), "counts": counts}


def event(slug: str, lang: str) -> dict | None:
    records = _live_events(lang)
    record = next((r for r in records if r["slug"] == slug), None)
    if record is None:
        return None
    others = sorted((r for r in records if r["slug"] != slug and r["phase"] != "completed"), key=lambda r: r["_start"])
    related = [{f: r[f] for f in EVENT_CARD} for r in others[:RELATED]]
    return {**_strip(record), "related": related}


def upcoming_events(lang: str, limit: int = 3) -> list[dict]:
    records = sorted((r for r in _live_events(lang) if r["phase"] != "completed"), key=lambda r: r["_start"])
    return [{f: r[f] for f in EVENT_CARD} for r in records[:limit]]


# ---------------------------------------------------------------------------
# Achievements
# ---------------------------------------------------------------------------

ACHIEVEMENT_CARD = ("slug", "title", "excerpt", "category", "date", "cover", "photo_count", "is_featured", "recipient")


def _achievement_record(item: Achievement, lang: str) -> dict:
    photos = _photos(item)
    cover = _cover(item)
    return {
        "slug": item.slug,
        "title": tr(item, "title", lang),
        "excerpt": tr(item, "excerpt", lang),
        "body": tr(item, "body", lang),
        "category": item.category,
        "recipient": item.recipient or None,
        "date": item.date.isoformat(),
        "cover": cover,
        "photos": photos,
        "photo_count": len(photos) + bool(cover),
        "is_featured": item.is_featured,
        # SEO overrides are written in Russian; /ky and /en use the translated texts.
        "seo_title": (item.seo_title or None) if lang == "ru" else None,
        "seo_description": (item.seo_description or None) if lang == "ru" else None,
        "updated_at": item.updated_at.isoformat(),
        "_ts": item.published_at.timestamp(),
    }


def _achievements(lang: str) -> list[dict]:
    def build():
        qs = (Achievement.objects.filter(status=Workflow.PUBLISHED)
              .prefetch_related(Prefetch("photos", queryset=AchievementPhoto.objects.order_by("order", "id"))))
        return [_achievement_record(a, lang) for a in qs]
    return _cached(f"achievements:{lang}", build)


def achievements(lang: str, *, category="", page=None, page_size=None) -> dict:
    records = _visible(_achievements(lang))
    counts = {"all": len(records), **{c: 0 for c in Achievement.Category.values}}
    for r in records:
        counts[r["category"]] += 1
    # One category or several, comma-separated (the site groups e.g. award,certificate,recognition).
    wanted = {c.strip() for c in (category or "").lower().split(",") if c.strip() and c.strip() != "all"}
    if wanted:
        unknown = wanted - set(Achievement.Category.values)
        if unknown:
            raise ValidationError({"category": f"Одно или несколько через запятую из: all, {', '.join(Achievement.Category.values)}."})
        records = [r for r in records if r["category"] in wanted]
    return {**_page(records, page, page_size, ACHIEVEMENT_CARD), "counts": counts}


def achievement(slug: str, lang: str) -> dict | None:
    records = _visible(_achievements(lang))
    record = next((r for r in records if r["slug"] == slug), None)
    if record is None:
        return None
    others = [r for r in records if r["slug"] != slug]
    same = [r for r in others if r["category"] == record["category"]]
    related = (same + [r for r in others if r["category"] != record["category"]])[:RELATED]
    return {**_strip(record), "related": [{f: r[f] for f in ACHIEVEMENT_CARD} for r in related]}


def featured_achievements(lang: str, limit: int = 3) -> list[dict]:
    records = _visible(_achievements(lang))
    records = sorted(records, key=lambda r: not r["is_featured"])
    return [{f: r[f] for f in ACHIEVEMENT_CARD} for r in records[:limit]]


# ---------------------------------------------------------------------------
# Team, testimonials
# ---------------------------------------------------------------------------

def _member_record(m: TeamMember, lang: str) -> dict:
    teacher = m.teacher if m.teacher_id else None
    photo = None
    if m.photo_approved:
        photo = _image(m.photo) or (_image(teacher.image) if teacher and teacher.image else None)
    # Only what was entered on the site profile — never a default from the LMS.
    experience = m.experience_years
    specialization = m.specialization
    if not specialization and teacher:
        specialization = ", ".join(s.name for s in teacher.subjects.all())
    return {
        "id": m.pk,
        "slug": m.slug,
        "name": m.display_name,
        "position": tr(m, "position", lang),
        # The job title as written in each language (null = not translated).
        "positions": {"ru": m.position, "ky": m.position_ky or None, "en": m.position_en or None},
        "group": m.group or None,
        "specialization": specialization or None,
        "bio": tr(m, "bio", lang),
        "experience_years": experience or None,
        "photo": photo,
        "career": lines(tr(m, "career", lang)),
        "achievements": lines(tr(m, "achievements", lang)),
        # SEO overrides are written in Russian; /ky and /en use the translated texts.
        "seo_title": (m.seo_title or None) if lang == "ru" else None,
        "seo_description": (m.seo_description or None) if lang == "ru" else None,
        "_ts": m.published_at.timestamp(),
    }


PROFILE_ONLY = ("career", "achievements", "seo_title", "seo_description")


def _team_records(lang: str) -> list[dict]:
    def build():
        qs = (TeamMember.objects.filter(status=Workflow.PUBLISHED)
              .select_related("teacher__user").prefetch_related("teacher__subjects"))
        # A trainer who left the academy (inactive in the LMS) leaves the site too.
        qs = qs.filter(Q(teacher__isnull=True) | Q(teacher__is_active=True, teacher__user__is_active=True))
        return [_member_record(m, lang) for m in qs]
    return _visible(_cached(f"team:{lang}", build))


def team(lang: str) -> dict:
    return {"results": [{k: v for k, v in _strip(r).items() if k not in PROFILE_ONLY} for r in _team_records(lang)]}


def team_member(slug: str, lang: str) -> dict | None:
    """One public profile (/team/<slug>) with colleagues from the same department."""
    records = _team_records(lang)
    record = next((r for r in records if r["slug"] == slug), None)
    if record is None:
        return None
    colleagues = [r for r in records if r["slug"] != slug and record["group"] and r["group"] == record["group"]]
    card = lambda r: {k: v for k, v in _strip(r).items() if k not in PROFILE_ONLY}  # noqa: E731
    return {**_strip(record), "colleagues": [card(r) for r in colleagues[:3]]}


def _testimonial_record(t: Testimonial) -> dict:
    video = video_embed(t.video_url)
    photo = _image(t.photo)
    return {
        "id": t.pk,
        "author_name": t.author_name,
        "author_role": t.author_role,
        "course": t.course_label or None,
        "text": t.text,
        "language": t.language,
        "rating": t.rating,
        "photo": photo,
        "video_embed": video,
        "kind": "video" if video else ("photo" if photo else "text"),
        "is_featured": t.is_featured,
        "_ts": t.published_at.timestamp(),
    }


def _testimonials() -> list[dict]:
    def build():
        return [_testimonial_record(t) for t in Testimonial.objects.filter(status=Workflow.PUBLISHED, consent=True)]
    return _cached("testimonials", build)


def testimonials(*, kind="", page=None, page_size=None) -> dict:
    records = _visible(_testimonials())
    counts = {"all": len(records), "text": 0, "photo": 0, "video": 0}
    for r in records:
        counts[r["kind"]] += 1
    kind = (kind or "").strip().lower()
    if kind and kind != "all":
        if kind not in ("text", "photo", "video"):
            raise ValidationError({"kind": "Одно из: all, text, photo, video."})
        records = [r for r in records if r["kind"] == kind]
    ratings = [r["rating"] for r in _visible(_testimonials()) if r["rating"]]
    fields = [k for k in records[0] if not k.startswith("_")] if records else []
    return {
        **_page(records, page, page_size or 12, fields),
        "counts": counts,
        "average_rating": round(sum(ratings) / len(ratings), 1) if ratings else None,
    }


# ---------------------------------------------------------------------------
# Homepage (one request)
# ---------------------------------------------------------------------------

def home(lang: str) -> dict:
    data = site(lang)
    keys = {s["key"] for s in data["sections"]}
    raw = _site_data(lang)
    course_cards = [r for r in courses(lang)["results"]]
    featured_courses = [c for c in course_cards if c["is_featured"]] or course_cards
    members = team(lang)["results"]
    reviews = sorted(_visible(_testimonials()), key=lambda r: not r["is_featured"])
    return {
        **data,
        "courses": featured_courses[:6] if "courses" in keys else [],
        "projects": featured_projects(raw["_featured_projects"]) if "projects" in keys else [],
        "news": featured_news(raw["_featured_news"], lang=lang) if "news" in keys else [],
        "events": upcoming_events(lang) if "events" in keys else [],
        "achievements": featured_achievements(lang) if "achievements" in keys else [],
        "team": members[:4] if "team" in keys else [],
        "testimonials": [_strip(r) for r in reviews[:6]] if "testimonials" in keys else [],
    }


# ---------------------------------------------------------------------------
# Sitemap, preview
# ---------------------------------------------------------------------------

def sitemap() -> dict:
    return {
        "courses": [{"slug": r["slug"], "updated_at": r["updated_at"]} for r in _visible(_courses("ru"))],
        "events": [{"slug": r["slug"], "updated_at": r["updated_at"]} for r in _visible(_events("ru"))],
        "achievements": [{"slug": r["slug"], "updated_at": r["updated_at"]} for r in _visible(_achievements("ru"))],
        "team": [{"slug": r["slug"], "updated_at": None} for r in _team_records("ru")],
        "news": [{"slug": r["slug"], "updated_at": r["published_at"]} for r in news_public.visible()],
        "projects": [{"slug": r["key"], "updated_at": r["date"]} for r in projects_public.published()],
    }


PREVIEW_KINDS = {"course": CoursePage, "event": Event, "achievement": Achievement}


def preview_token(kind: str, pk: int) -> str:
    return signing.dumps({"k": kind, "id": pk}, salt=PREVIEW_SALT, compress=True)


def preview(token: str, lang: str) -> dict | None:
    """Any status — a signed link from the LMS editor, valid 7 days."""
    try:
        data = signing.loads(token, salt=PREVIEW_SALT, max_age=PREVIEW_MAX_AGE)
    except signing.BadSignature:
        return None
    kind, pk = data.get("k"), data.get("id")
    if kind == "news":
        from apps.academy_news.models import Article

        article = Article.objects.filter(pk=pk).prefetch_related("photos").first()
        if article is None:
            return None
        record = news_public._record(article, lang_of(lang))
        return {"kind": "news", "item": {**_strip(record), "related": []}}
    model = PREVIEW_KINDS.get(kind)
    obj = model.objects.filter(pk=pk).first() if model else None
    if obj is None:
        return None
    if kind == "course":
        item = {**_strip(_course_record(obj, lang)), "projects": []}
    elif kind == "event":
        obj.taken = obj.registrations.exclude(status=EventRegistration.Status.CANCELLED).count()
        item = {**_strip(_event_live(_event_record(obj, lang), timezone.now().timestamp())), "related": []}
    else:
        item = {**_strip(_achievement_record(obj, lang)), "related": []}
    return {"kind": kind, "item": item}
