"""The public schedule — what anyone (parents, students, trainers, visitors)
may see without an account, at schedule.okurmenkids.com.

Built from the same Lesson rows as the LMS, so a lesson moved or cancelled
in the LMS shows here as soon as the short cache expires (or at once: every
lesson save bumps the cache version). Nothing is stored or copied.

What leaves the server is a closed whitelist (see `lesson_row`): date and
time, group / course / subject names, the trainer's name and color (unless
PUBLIC_SCHEDULE_SHOW_TRAINERS is off), the room name (unless
PUBLIC_SCHEDULE_SHOW_ROOMS is off) and the lesson status. Never students,
contacts, attendance, homework, scores, KPI, topics or comments — and no
database ids: groups, trainers and rooms are referred to by opaque keys
(an HMAC of the id with the project's SECRET_KEY) that only this API can
map back, and only for filtering.

The trainer of a lesson is its historical one (services.trainer_history):
a group handed to another trainer never repaints its past lessons.
"""
from __future__ import annotations

import base64
import datetime as dt
import hashlib
import hmac

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

from apps.users.models import Teacher, User

from ..models import Group, Lesson, Room
from . import trainer_history

OPEN_GROUP_STATUSES = (Group.Status.ACTIVE, Group.Status.PAUSED)
STATUS_LABELS = dict(Lesson.Status.choices)
_VERSION_KEY = "public_schedule:version"


def config() -> dict:
    return {
        "show_trainers": getattr(settings, "PUBLIC_SCHEDULE_SHOW_TRAINERS", True),
        "show_rooms": getattr(settings, "PUBLIC_SCHEDULE_SHOW_ROOMS", True),
        # How far back / ahead a visitor may look, and how many days at once.
        "past_days": getattr(settings, "PUBLIC_SCHEDULE_PAST_DAYS", 31),
        "future_days": getattr(settings, "PUBLIC_SCHEDULE_FUTURE_DAYS", 120),
        "max_range_days": 7,
        "cache_seconds": getattr(settings, "PUBLIC_SCHEDULE_CACHE_SECONDS", 60),
    }


# ---------------------------------------------------------------------------
# Opaque public keys
# ---------------------------------------------------------------------------

def public_key(kind: str, pk: int) -> str:
    """A stable, non-guessable key for a group / trainer / room / lesson —
    never the database id."""
    digest = hmac.new(settings.SECRET_KEY.encode(), f"public-schedule:{kind}:{pk}".encode(), hashlib.sha256).digest()
    return base64.b32encode(digest[:8]).decode().rstrip("=").lower()


def _resolve(kind: str, key: str | None, candidates) -> int | None | bool:
    """The id behind `key` among `candidates` (ids); False for an unknown key
    (so a bad filter returns nothing rather than everything)."""
    if not key:
        return None
    for pk in candidates:
        if hmac.compare_digest(public_key(kind, pk), key):
            return pk
    return False


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------

def cache_version() -> int:
    return cache.get(_VERSION_KEY) or 1


def bump_cache_version(**_kwargs) -> None:
    """Called on every Lesson save / delete: the next request rebuilds."""
    try:
        cache.incr(_VERSION_KEY)
    except ValueError:
        cache.set(_VERSION_KEY, 2, None)


def cached(name: str, params: dict, build):
    seconds = config()["cache_seconds"]
    if not seconds:
        return build()
    raw = "&".join(f"{k}={params[k]}" for k in sorted(params) if params[k] not in (None, ""))
    key = f"public_schedule:{cache_version()}:{name}:{hashlib.sha1(raw.encode()).hexdigest()}"
    value = cache.get(key)
    if value is None:
        value = build()
        cache.set(key, value, seconds)
    return value


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------

def window(today: dt.date | None = None) -> tuple[dt.date, dt.date]:
    today = today or timezone.localdate()
    cfg = config()
    return today - dt.timedelta(days=cfg["past_days"]), today + dt.timedelta(days=cfg["future_days"])


def _full_name(first, last, username) -> str:
    return f"{first or ''} {last or ''}".strip() or username


def _published_teachers():
    return (
        Teacher.objects.filter(is_active=True, user__is_active=True, user__role=User.Role.TEACHER)
        .filter(trainer_assignments__end_date__isnull=True, trainer_assignments__group__status__in=OPEN_GROUP_STATUSES)
        .distinct()
    )


def options() -> dict:
    cfg = config()
    first, last = window()
    groups = (
        Group.objects.filter(status__in=OPEN_GROUP_STATUSES).order_by("name").values_list("id", "name", "course__name")
    )
    payload = {
        "today": timezone.localdate(),
        "window": {"first": first, "last": last, "max_days": cfg["max_range_days"]},
        "hours": {"start": "08:00", "end": "24:00"},
        "show": {"trainers": cfg["show_trainers"], "rooms": cfg["show_rooms"]},
        "groups": [{"key": public_key("group", pk), "name": name, "course": course} for pk, name, course in groups],
        "trainers": [],
        "rooms": [],
    }
    if cfg["show_trainers"]:
        rows = _published_teachers().values_list("id", "user__first_name", "user__last_name", "user__username", "color")
        payload["trainers"] = sorted(
            ({"key": public_key("trainer", pk), "name": _full_name(f, l, u), "color": color or None} for pk, f, l, u, color in rows),
            key=lambda t: t["name"],
        )
    if cfg["show_rooms"]:
        payload["rooms"] = [
            {"key": public_key("room", pk), "name": name}
            for pk, name in Room.objects.filter(is_active=True).order_by("name").values_list("id", "name")
        ]
    return payload


class PublicScheduleError(ValueError):
    pass


def lessons(start: dt.date, end: dt.date, *, group: str | None = None, trainer: str | None = None,
            room: str | None = None) -> dict:
    cfg = config()
    first, last = window()
    if end < start or (end - start).days >= cfg["max_range_days"]:
        raise PublicScheduleError(f"Период — от 1 до {cfg['max_range_days']} дней.")
    if start < first or end > last:
        raise PublicScheduleError(f"Расписание опубликовано с {first:%d.%m.%Y} по {last:%d.%m.%Y}.")

    qs = Lesson.objects.filter(date__gte=start, date__lte=end)
    group_id = _resolve("group", group, Group.objects.values_list("id", flat=True)) if group else None
    trainer_id = (
        _resolve("trainer", trainer, Teacher.objects.values_list("id", flat=True)) if trainer and cfg["show_trainers"] else None
    )
    room_id = _resolve("room", room, Room.objects.values_list("id", flat=True)) if room and cfg["show_rooms"] else None
    if False in (group_id, trainer_id, room_id):
        qs = qs.none()
    if group_id:
        qs = qs.filter(group_id=group_id)
    if trainer_id:
        qs = qs.filter(trainer_history.taught_by_q(trainer_id))
    if room_id:
        qs = qs.filter(room_id=room_id)

    rows = list(
        qs.annotate(_teacher=trainer_history.effective_teacher())
        .order_by("date", "start_time", "group__name")
        .values_list(
            "id", "date", "start_time", "end_time", "status", "schedule_overridden",
            "group_id", "group__name", "group__course__name", "subject__name", "room_id", "room__name", "_teacher",
        )
    )
    teachers = {}
    if cfg["show_trainers"]:
        teachers = {
            pk: {"key": public_key("trainer", pk), "name": _full_name(f, l, u), "color": color or None}
            for pk, f, l, u, color in Teacher.objects.filter(id__in={r[12] for r in rows if r[12]})
            .values_list("id", "user__first_name", "user__last_name", "user__username", "color")
        }
    now = timezone.localtime()
    return {
        "start": start,
        "end": end,
        "now": {"date": now.date(), "time": now.strftime("%H:%M"), "timezone": timezone.get_current_timezone_name()},
        "hours": {"start": "08:00", "end": "24:00"},
        "show": {"trainers": cfg["show_trainers"], "rooms": cfg["show_rooms"]},
        "lessons": [lesson_row(row, teachers, cfg) for row in rows],
    }


def lesson_row(row, teachers: dict, cfg: dict) -> dict:
    """The whole public view of one lesson — add nothing here that a parent
    or a passer-by shouldn't see."""
    (pk, date, start, end, status, moved, group_id, group_name, course, subject, room_id, room_name, teacher_id) = row
    minutes = (end.hour * 60 + end.minute or 24 * 60) - (start.hour * 60 + start.minute)
    item = {
        "key": public_key("lesson", pk),
        "date": date,
        "start": start.strftime("%H:%M"),
        "end": end.strftime("%H:%M"),
        "duration_minutes": max(minutes, 0),
        "group": {"key": public_key("group", group_id), "name": group_name},
        "course": course,
        "subject": subject,
        "status": status,
        "status_label": STATUS_LABELS.get(status, status),
        "rescheduled": bool(moved),
    }
    if cfg["show_trainers"]:
        item["trainer"] = teachers.get(teacher_id)
    if cfg["show_rooms"]:
        item["room"] = {"key": public_key("room", room_id), "name": room_name} if room_id else None
    return item


__all__ = ["PublicScheduleError", "bump_cache_version", "cached", "lessons", "options", "public_key", "window"]
