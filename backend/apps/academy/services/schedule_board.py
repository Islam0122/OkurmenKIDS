"""The schedule board — one business layer behind the Team Lead's and the
Assistant's «Расписание» pages (apps.academy.schedule_views).

* `board()` — the lessons of a period (server-side filters: trainer, rooms,
  group, status), each with its trainer's color, duration and the clashes it
  is part of; the trainer legend and the counters of the page header.
* `find_conflicts()` — who/what a lesson placed at date/start–end would
  double-book: its trainer, its group or its room. The single check behind
  the board's warnings, the move of a lesson (services.lesson_move) and the
  live check of the move form.
* `room_availability()` — every active room for a date and a time window:
  free or busy, when a busy room frees up, the free window around a free
  one, and the next free interval long enough for the requested duration.

Everything is read from real Lesson rows (cancelled lessons never occupy
anything), never from what a page happens to show. Two intervals overlap by
`start_a < end_b and start_b < end_a` — 14:00–15:00 and 15:00–16:00 touch,
they don't clash (services.group_schedule_conflicts).
"""
from __future__ import annotations

import datetime as dt
from collections import defaultdict
from dataclasses import dataclass, field

from django.db.models import Count, Q
from django.utils import timezone

from apps.users.models import Teacher, User

from ..models import Group, Lesson, Room, Student
from .group_schedule_conflicts import overlapping_groups, time_ranges_overlap

# The board's visible working day: 08:00 – 24:00.
DAY_START_MINUTES = 8 * 60
DAY_END_MINUTES = 24 * 60
MAX_RANGE_DAYS = 31

OPEN_GROUP_STATUSES = (Group.Status.ACTIVE, Group.Status.PAUSED)

LESSON_RELATED = ("group__course", "teacher__user", "group_teacher__teacher__user", "room", "subject")

CONFLICT_LABELS = {"teacher": "Тренер", "room": "Кабинет", "group": "Группа"}


# ---------------------------------------------------------------------------
# Time helpers
# ---------------------------------------------------------------------------

def minutes(value: dt.time) -> int:
    return value.hour * 60 + value.minute


def hm(total: int) -> str:
    """Minutes since midnight → «HH:MM»; 1440 is «24:00» (the board's end)."""
    return f"{total // 60:02d}:{total % 60:02d}"


def parse_hm(value: str | None) -> int | None:
    """«HH:MM» → minutes since midnight, «24:00» allowed; None if invalid."""
    if not value:
        return None
    try:
        hours, mins = (int(part) for part in str(value).split(":")[:2])
    except ValueError:
        return None
    total = hours * 60 + mins
    if not (0 <= mins < 60 and 0 <= total <= DAY_END_MINUTES):
        return None
    return total


def as_time(total: int) -> dt.time:
    """Minutes → a TimeField value; «24:00» is the last instant of the day."""
    if total >= DAY_END_MINUTES:
        return dt.time.max
    return dt.time(total // 60, total % 60)


def overlaps(start_a: int, end_a: int, start_b: int, end_b: int) -> bool:
    return start_a < end_b and start_b < end_a


# ---------------------------------------------------------------------------
# Filters
# ---------------------------------------------------------------------------

def _ids(value) -> list[int]:
    if value is None:
        return []
    parts = value if isinstance(value, (list, tuple)) else str(value).split(",")
    return sorted({int(part) for part in parts if str(part).strip().isdigit()})


@dataclass
class ScheduleFilters:
    teacher: int | None = None
    rooms: list[int] = field(default_factory=list)
    group: int | None = None
    status: str | None = None

    @classmethod
    def from_params(cls, params) -> "ScheduleFilters":
        rooms = params.getlist("room") if hasattr(params, "getlist") else params.get("room")
        if isinstance(rooms, list) and len(rooms) == 1:
            rooms = rooms[0]
        teacher = _ids(params.get("teacher"))
        group = _ids(params.get("group"))
        status = params.get("status")
        return cls(
            teacher=teacher[0] if teacher else None,
            rooms=_ids(rooms),
            group=group[0] if group else None,
            status=status if status in Lesson.Status.values else None,
        )


def teacher_q(teacher_id: int, prefix: str = "") -> Q:
    """Lessons `teacher_id` gives — its own teacher, or its program's
    (the same rule as Lesson.effective_teacher / LessonQuerySet.for_teacher)."""
    return Q(**{f"{prefix}teacher_id": teacher_id}) | Q(
        **{f"{prefix}teacher__isnull": True, f"{prefix}group_teacher__teacher_id": teacher_id}
    )


def lessons_queryset(start: dt.date, end: dt.date, filters: ScheduleFilters):
    qs = Lesson.objects.filter(date__gte=start, date__lte=end).select_related(*LESSON_RELATED)
    if filters.teacher:
        qs = qs.filter(teacher_q(filters.teacher))
    if filters.rooms:
        qs = qs.filter(room_id__in=filters.rooms)
    if filters.group:
        qs = qs.filter(group_id=filters.group)
    if filters.status:
        qs = qs.filter(status=filters.status)
    return qs.order_by("date", "start_time", "group__name")


# ---------------------------------------------------------------------------
# Conflicts
# ---------------------------------------------------------------------------

@dataclass
class _Slot:
    """A live lesson reduced to what a clash check needs (one cheap query)."""

    id: int
    date: dt.date
    start_time: dt.time
    end_time: dt.time
    teacher_id: int | None
    room_id: int | None
    group_id: int
    group_name: str
    room_name: str | None
    teacher_name: str


def _teacher_name(first, last, username) -> str:
    return f"{first or ''} {last or ''}".strip() or (username or "")


def _live_slots(**lookup) -> list[_Slot]:
    """Not-cancelled lessons matching `lookup`, with their effective trainer."""
    rows = (
        Lesson.objects.filter(**lookup)
        .exclude(status=Lesson.Status.CANCELLED)
        .values_list(
            "id", "date", "start_time", "end_time", "teacher_id", "group_teacher__teacher_id",
            "room_id", "group_id", "group__name", "room__name",
            "teacher__user__first_name", "teacher__user__last_name", "teacher__user__username",
            "group_teacher__teacher__user__first_name", "group_teacher__teacher__user__last_name",
            "group_teacher__teacher__user__username",
        )
    )
    slots = []
    for (pk, date, start, end, teacher_id, gt_teacher_id, room_id, group_id, group_name, room_name,
         t_first, t_last, t_user, g_first, g_last, g_user) in rows:
        own = teacher_id is not None
        slots.append(_Slot(
            id=pk, date=date, start_time=start, end_time=end,
            teacher_id=teacher_id if own else gt_teacher_id,
            room_id=room_id, group_id=group_id, group_name=group_name, room_name=room_name,
            teacher_name=_teacher_name(t_first, t_last, t_user) if own else _teacher_name(g_first, g_last, g_user),
        ))
    return slots


def _slot_ref(slot: _Slot) -> dict:
    return {
        "id": slot.id,
        "date": slot.date,
        "start": slot.start_time.strftime("%H:%M"),
        "end": slot.end_time.strftime("%H:%M"),
        "group": {"id": slot.group_id, "name": slot.group_name},
        "teacher": {"id": slot.teacher_id, "name": slot.teacher_name} if slot.teacher_id else None,
        "room": {"id": slot.room_id, "name": slot.room_name} if slot.room_id else None,
    }


def conflict_message(kind: str, *, teacher_name: str = "", group_name: str = "", room_name: str = "",
                     other: _Slot) -> str:
    when = f"{other.start_time:%H:%M}–{other.end_time:%H:%M}"
    if kind == "teacher":
        return f"Тренер «{teacher_name}» уже ведёт занятие в группе «{other.group_name}» ({when})."
    if kind == "group":
        return f"У группы «{group_name}» уже есть занятие в это время ({when})."
    return f"Аудитория «{room_name}» уже занята группой «{other.group_name}» ({when})."


def find_conflicts(*, date: dt.date, start_time: dt.time, end_time: dt.time, teacher_id: int | None = None,
                   room_id: int | None = None, group_id: int | None = None, exclude_lesson_id: int | None = None,
                   teacher_name: str = "", group_name: str = "", room_name: str = "") -> list[dict]:
    """Every live lesson that a lesson at date/start–end with this trainer,
    room and group would clash with — one entry per (kind, other lesson):
    {"kind", "kind_label", "message", "lesson"}. Touching ends never clash."""
    candidates = Q()
    if teacher_id:
        candidates |= teacher_q(teacher_id)
    if room_id:
        candidates |= Q(room_id=room_id)
    if group_id:
        candidates |= Q(group_id=group_id)
    if not candidates:
        return []
    qs = Lesson.objects.filter(candidates, date=date, start_time__lt=end_time, end_time__gt=start_time)
    if exclude_lesson_id:
        qs = qs.exclude(pk=exclude_lesson_id)
    ids = list(qs.values_list("id", flat=True))
    if not ids:
        return []
    found = []
    for other in sorted(_live_slots(id__in=ids), key=lambda s: (s.start_time, s.group_name)):
        for kind, mine, theirs in (
            ("teacher", teacher_id, other.teacher_id),
            ("group", group_id, other.group_id),
            ("room", room_id, other.room_id),
        ):
            if mine and theirs == mine:
                found.append({
                    "kind": kind,
                    "kind_label": CONFLICT_LABELS[kind],
                    "message": conflict_message(kind, teacher_name=teacher_name, group_name=group_name,
                                                room_name=room_name, other=other),
                    "lesson": _slot_ref(other),
                })
    return found


def lesson_conflicts(lesson: Lesson, *, date: dt.date, start_time: dt.time, end_time: dt.time) -> list[dict]:
    """`find_conflicts` for an existing lesson placed at a new date/time."""
    teacher = lesson.effective_teacher
    return find_conflicts(
        date=date, start_time=start_time, end_time=end_time,
        teacher_id=teacher.pk if teacher else None, room_id=lesson.room_id, group_id=lesson.group_id,
        exclude_lesson_id=lesson.pk,
        teacher_name=str(teacher) if teacher else "", group_name=lesson.group.name,
        room_name=lesson.room.name if lesson.room_id else "",
    )


def period_conflicts(start: dt.date, end: dt.date) -> tuple[list[dict], dict[int, list[dict]]]:
    """Every clash among the live lessons of [start, end] — across the whole
    academy, never just the filtered lessons on screen (a room filter must
    not hide that the trainer is elsewhere at the same time).

    Returns (the clash list, {lesson id: the clashes it is part of})."""
    buckets: dict[tuple, list[_Slot]] = defaultdict(list)
    for slot in _live_slots(date__gte=start, date__lte=end):
        if slot.teacher_id:
            buckets[("teacher", slot.teacher_id, slot.date)].append(slot)
        if slot.room_id:
            buckets[("room", slot.room_id, slot.date)].append(slot)
        buckets[("group", slot.group_id, slot.date)].append(slot)

    conflicts: list[dict] = []
    by_lesson: dict[int, list[dict]] = defaultdict(list)
    for (kind, _key, date), items in buckets.items():
        for component in overlapping_groups(items):
            first = component[0]
            name = {"teacher": first.teacher_name, "room": first.room_name, "group": first.group_name}[kind]
            entry = {
                "kind": kind,
                "kind_label": CONFLICT_LABELS[kind],
                "name": name,
                "date": date,
                "message": (
                    f"{CONFLICT_LABELS[kind]} «{name}»: {len(component)} занятия пересекаются по времени "
                    f"({', '.join(f'{s.group_name} {s.start_time:%H:%M}–{s.end_time:%H:%M}' for s in component)})."
                ),
                "lessons": [_slot_ref(s) for s in component],
            }
            conflicts.append(entry)
            for slot in component:
                by_lesson[slot.id].append({
                    "kind": kind,
                    "kind_label": CONFLICT_LABELS[kind],
                    "message": entry["message"],
                    # Only the lessons that overlap this one directly (a
                    # chain A–B–C is one clash, but A doesn't touch C).
                    "with": [o.id for o in component if o.id != slot.id and time_ranges_overlap(slot, o)],
                })
    conflicts.sort(key=lambda c: (c["date"], c["lessons"][0]["start"], c["kind"], c["name"]))
    return conflicts, by_lesson


# ---------------------------------------------------------------------------
# Rooms
# ---------------------------------------------------------------------------

def _merge(intervals: list[tuple[int, int]]) -> list[tuple[int, int]]:
    merged: list[list[int]] = []
    for start, end in sorted(intervals):
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return [(start, end) for start, end in merged]


def _free_gaps(busy: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Free windows of the board's day (08:00–24:00) between merged busy blocks."""
    gaps, cursor = [], DAY_START_MINUTES
    for start, end in busy:
        if start > cursor:
            gaps.append((cursor, min(start, DAY_END_MINUTES)))
        cursor = max(cursor, end)
    if cursor < DAY_END_MINUTES:
        gaps.append((cursor, DAY_END_MINUTES))
    return [(start, end) for start, end in gaps if end > start]


def room_availability(date: dt.date, start: int, end: int, rooms: list[int] | None = None) -> dict:
    """Every active room on `date` for the window start–end (minutes):
    free/busy, the busy room's clashing lessons and when it frees up, the
    free window around a free room, the next free interval at least as long
    as the window (busy rooms). Read from real Lesson rows in one query."""
    duration = end - start
    room_qs = Room.objects.filter(is_active=True).order_by("name")
    if rooms:
        room_qs = room_qs.filter(pk__in=rooms)
    room_list = list(room_qs)
    by_room: dict[int, list[_Slot]] = defaultdict(list)
    for slot in _live_slots(date=date, room_id__in=[room.pk for room in room_list]):
        by_room[slot.room_id].append(slot)

    rows = []
    for room in room_list:
        lessons = sorted(by_room.get(room.pk, []), key=lambda s: s.start_time)
        busy = _merge([(minutes(s.start_time), minutes(s.end_time) or DAY_END_MINUTES) for s in lessons])
        clashing = [s for s in lessons if overlaps(start, end, minutes(s.start_time), minutes(s.end_time))]
        row = {
            "room": {"id": room.pk, "name": room.name, "capacity": room.capacity},
            "is_free": not clashing,
            "lessons_count": len(lessons),
            "busy": [{"start": hm(s), "end": hm(e)} for s, e in busy],
            "conflicting_lessons": [_slot_ref(s) for s in clashing],
            "free_at": None,
            "free_window": None,
            "next_free": None,
        }
        gaps = _free_gaps(busy)
        if clashing:
            # When the room frees up: the end of the busy block the window
            # hits first; and the first free interval at least as long as
            # the requested window from the window's start on.
            block = next(b for b in busy if overlaps(start, end, *b))
            row["free_at"] = hm(block[1])
            for gap_start, gap_end in gaps:
                begin = max(gap_start, start)
                if gap_end - begin >= duration:
                    row["next_free"] = {"start": hm(begin), "end": hm(gap_end)}
                    break
        else:
            # How long the room stays free around the window.
            window = next(((s, e) for s, e in gaps if s <= start and end <= e), (start, end))
            row["free_window"] = {"start": hm(window[0]), "end": hm(window[1])}
        rows.append(row)

    free = [row for row in rows if row["is_free"]]
    return {
        "date": date,
        "start": hm(start),
        "end": hm(end),
        "free_count": len(free),
        "busy_count": len(rows) - len(free),
        "rooms": sorted(rows, key=lambda r: (not r["is_free"], r["room"]["name"])),
    }


# ---------------------------------------------------------------------------
# The board
# ---------------------------------------------------------------------------

def _hm_time(value: dt.time | None) -> str:
    return value.strftime("%H:%M") if value else ""


def _ref(obj) -> dict | None:
    return {"id": obj.pk, "name": str(obj)} if obj is not None else None


def lesson_row(lesson: Lesson, students_count: int | None, conflicts: list[dict]) -> dict:
    teacher = lesson.effective_teacher
    start, end = minutes(lesson.start_time), minutes(lesson.end_time) or DAY_END_MINUTES
    return {
        "id": lesson.pk,
        "date": lesson.date,
        "start": _hm_time(lesson.start_time),
        "end": _hm_time(lesson.end_time),
        "duration_minutes": max(end - start, 0),
        "group": _ref(lesson.group),
        "course": _ref(lesson.group.course),
        "subject": _ref(lesson.subject),
        "teacher": {**_ref(teacher), "color": teacher.color} if teacher else None,
        "room": _ref(lesson.room),
        "topic": lesson.topic,
        "lesson_number": lesson.lesson_number,
        "status": lesson.status,
        "status_display": lesson.get_status_display(),
        "students_count": students_count,
        "schedule_overridden": lesson.schedule_overridden,
        "conflicts": conflicts,
    }


def teacher_ref(teacher: Teacher) -> dict:
    return {"id": teacher.pk, "name": str(teacher), "color": teacher.color}


def options() -> dict:
    """What the board's filters pick from (three cheap queries)."""
    teachers = (
        Teacher.objects.filter(is_active=True, user__is_active=True, user__role=User.Role.TEACHER)
        .select_related("user")
        .order_by("user__first_name", "user__last_name")
    )
    return {
        "teachers": [teacher_ref(t) for t in teachers],
        "rooms": [{"id": r.pk, "name": r.name, "capacity": r.capacity}
                  for r in Room.objects.filter(is_active=True).order_by("name")],
        "groups": [{"id": g.pk, "name": g.name, "course": g.course.name}
                   for g in Group.objects.filter(status__in=OPEN_GROUP_STATUSES).select_related("course").order_by("name")],
        "statuses": [{"value": value, "label": label} for value, label in Lesson.Status.choices],
        "hours": {"start": hm(DAY_START_MINUTES), "end": hm(DAY_END_MINUTES)},
    }


def _free_rooms_stat(start: dt.date, end: dt.date, filters: ScheduleFilters, now: dt.datetime) -> dict | None:
    """«Свободно сейчас» when the period includes today (during working
    hours), else — for a single day — the rooms without a lesson that day."""
    today = now.date()
    if start <= today <= end:
        current = now.hour * 60 + now.minute
        if DAY_START_MINUTES <= current < DAY_END_MINUTES:
            report = room_availability(today, current, current + 1, filters.rooms or None)
            return {"mode": "now", "free": report["free_count"], "total": len(report["rooms"]),
                    "date": today, "at": hm(current)}
    if start == end:
        report = room_availability(start, DAY_START_MINUTES, DAY_END_MINUTES, filters.rooms or None)
        idle = sum(1 for row in report["rooms"] if row["lessons_count"] == 0)
        return {"mode": "day", "free": idle, "total": len(report["rooms"]), "date": start, "at": None}
    return None


def board(start: dt.date, end: dt.date, filters: ScheduleFilters, *, can_edit: bool) -> dict:
    """The whole payload of the «Расписание» page for one period — a fixed
    number of queries, whatever the number of lessons."""
    now = timezone.localtime()
    lessons = list(lessons_queryset(start, end, filters))
    counts = dict(
        Student.objects.filter(group_id__in={l.group_id for l in lessons}, status=Student.Status.ACTIVE)
        .values_list("group_id").annotate(n=Count("id")).values_list("group_id", "n")
    )
    conflicts, by_lesson = period_conflicts(start, end)
    shown = {lesson.pk for lesson in lessons}
    conflicts = [c for c in conflicts if any(item["id"] in shown for item in c["lessons"])]
    rows = [lesson_row(l, counts.get(l.group_id, 0), by_lesson.get(l.pk, [])) for l in lessons]

    legend: dict[int, dict] = {}
    for lesson in lessons:
        teacher = lesson.effective_teacher
        if teacher is not None and teacher.pk not in legend:
            legend[teacher.pk] = {**teacher_ref(teacher), "lessons_count": 0}
        if teacher is not None and lesson.status != Lesson.Status.CANCELLED:
            legend[teacher.pk]["lessons_count"] += 1

    live = [row for row in rows if row["status"] != Lesson.Status.CANCELLED]
    by_status = defaultdict(int)
    for row in rows:
        by_status[row["status"]] += 1
    return {
        "start": start,
        "end": end,
        "now": {"date": now.date(), "time": now.strftime("%H:%M"), "timezone": timezone.get_current_timezone_name()},
        "hours": {"start": hm(DAY_START_MINUTES), "end": hm(DAY_END_MINUTES)},
        "filters": {"teacher": filters.teacher, "rooms": filters.rooms, "group": filters.group, "status": filters.status},
        "capabilities": {"can_edit": can_edit},
        "lessons": rows,
        "legend": sorted(legend.values(), key=lambda t: t["name"]),
        "conflicts": conflicts,
        "stats": {
            "lessons": len(live),
            "by_status": dict(by_status),
            "conflicts": len(conflicts),
            "minutes": sum(row["duration_minutes"] for row in live),
            "free_rooms": _free_rooms_stat(start, end, filters, now),
        },
    }
