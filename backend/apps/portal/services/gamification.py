"""«Жетишкендиктер» — levels, collectible achievements, goals, weekly
activity and a timeline for ONE student (already authorised by
services.scope). Everything is derived from records the LMS already keeps;
nothing is stored, and nothing is unlocked that the records do not prove:

* XP is the public leaderboard's own rules — `leaderboard.student_xp` for
  totals and `leaderboard.student_xp_daily` (same filters and constants) for
  days. There is no XP for projects in the LMS, so none is shown.
* Levels are `data.level_for` (100 XP more per level: 0, 100, 300, 600…).
* An achievement is a threshold on real records. Its unlock date is the date
  of the record that crossed it (the Nth completed homework's lesson, the
  day cumulative XP reached the level, the award date…).
* Achievements carry no XP reward of their own in the LMS; `xp_reward` is
  therefore always None — the page shows a reward only if one existed.

Families and tiers (rarity = how hard the tier is):

    homework_done   5 / 20 / 50 / 100 completed homeworks  (existing badge thresholds)
    top_homework    1 / 10 / 25 homeworks graded 10/10      (existing badge thresholds)
    attendance      10 / 25 / 50 / 100 attended lessons
    level           levels 2 / 5 / 7 / 10
    perfect_month   a calendar month with ≥ 4 marked lessons and no miss (existing badge rule)
    scholarship     an approved scholarship award            (existing badge rule)
"""
from __future__ import annotations

import datetime as dt
from collections import defaultdict

from apps.academy.models import Attendance, HomeworkResult, Lesson, Student

from . import data

RARITIES = ("common", "rare", "epic", "legendary")
_DONE = data.DONE
_ATTENDED = data.ATTENDED

TIERS = {
    "homework_done": {"category": "homework", "thresholds": data.HOMEWORK_DONE_THRESHOLDS,
                      "rarity": ("common", "rare", "epic", "legendary")},
    "top_homework": {"category": "quality", "thresholds": data.HOMEWORK_TOP_THRESHOLDS,
                     "rarity": ("common", "rare", "epic")},
    "attendance": {"category": "attendance", "thresholds": (10, 25, 50, 100),
                   "rarity": ("common", "rare", "epic", "legendary")},
    "level": {"category": "level", "thresholds": (2, 5, 7, 10),
              "rarity": ("common", "rare", "epic", "legendary")},
}
CATEGORIES = ("homework", "quality", "attendance", "level", "scholarship")
EPOCH = dt.date(2000, 1, 1)
PERFECT_MONTH_MIN_MARKED = 4


# ---------------------------------------------------------------------------
# Raw records, ordered by the date they count on
# ---------------------------------------------------------------------------

def _homework_dates(student: Student) -> list[dt.date]:
    """Lesson date of every completed homework (the date its XP counts on)."""
    return list(
        HomeworkResult.objects.filter(student=student, status__in=_DONE)
        .exclude(homework__lesson__status=Lesson.Status.CANCELLED)
        .order_by("homework__lesson__date", "pk")
        .values_list("homework__lesson__date", flat=True)
    )


def _top_dates(student: Student) -> list[dt.date]:
    return list(
        HomeworkResult.objects.filter(student=student, score=10)
        .exclude(homework__lesson__status=Lesson.Status.CANCELLED)
        .order_by("homework__lesson__date", "pk")
        .values_list("homework__lesson__date", flat=True)
    )


def _attendance_dates(student: Student) -> list[dt.date]:
    return list(
        Attendance.objects.filter(student=student, status__in=_ATTENDED)
        .exclude(lesson__status=Lesson.Status.CANCELLED)
        .order_by("lesson__date", "pk")
        .values_list("lesson__date", flat=True)
    )


def daily_xp(student: Student, today: dt.date) -> dict[dt.date, dict]:
    from apps.leaderboard.services import Period, student_xp_daily

    return student_xp_daily(Period("custom", EPOCH, today), student.pk)


def level_reached_on(daily: dict[dt.date, dict]) -> dict[int, dt.date]:
    """{level: first day cumulative XP reached it} — from the daily XP."""
    reached: dict[int, dt.date] = {}
    cumulative = 0
    for day in sorted(daily):
        cumulative += sum(daily[day].values())
        level = data.level_for(cumulative)["level"]
        for lvl in range(2, level + 1):
            reached.setdefault(lvl, day)
    return reached


def _perfect_months(student: Student, today: dt.date) -> list[dt.date]:
    """Month-end dates of complete past months with ≥ 4 marked lessons and no miss."""
    by_month: dict[tuple[int, int], list[str]] = defaultdict(list)
    for day, status in (
        Attendance.objects.filter(student=student, lesson__date__lt=today.replace(day=1))
        .exclude(lesson__status=Lesson.Status.CANCELLED)
        .values_list("lesson__date", "status")
    ):
        by_month[(day.year, day.month)].append(status)
    months = []
    for (year, month), statuses in sorted(by_month.items()):
        if len(statuses) >= PERFECT_MONTH_MIN_MARKED and all(s in _ATTENDED for s in statuses):
            months.append(data.month_bounds(year, month)[1])
    return months


# ---------------------------------------------------------------------------
# Achievements
# ---------------------------------------------------------------------------

def _tier_items(code: str, dates_or_reached, current: int) -> list[dict]:
    spec = TIERS[code]
    items = []
    for index, threshold in enumerate(spec["thresholds"]):
        if code == "level":
            unlocked_on = dates_or_reached.get(threshold)
        else:
            unlocked_on = dates_or_reached[threshold - 1] if len(dates_or_reached) >= threshold else None
        items.append({
            "id": f"{code}-{threshold}",
            "code": code,
            "category": spec["category"],
            "rarity": spec["rarity"][index],
            "threshold": threshold,
            "current": min(current, threshold),
            "unlocked": unlocked_on is not None,
            "unlocked_on": unlocked_on,
            "xp_reward": None,
        })
    return items


def achievements(student: Student, *, today: dt.date, daily: dict | None = None) -> list[dict]:
    """The whole collection: every tier, locked or unlocked, with its real
    progress and (when unlocked) the date of the record that unlocked it."""
    from apps.scholarships.models import ScholarshipAward

    daily = daily if daily is not None else daily_xp(student, today)
    total = sum(sum(parts.values()) for parts in daily.values())
    level = data.level_for(total)["level"]
    homework, top, attended = _homework_dates(student), _top_dates(student), _attendance_dates(student)

    items = (
        _tier_items("homework_done", homework, len(homework))
        + _tier_items("top_homework", top, len(top))
        + _tier_items("attendance", attended, len(attended))
        + _tier_items("level", level_reached_on(daily), level)
    )

    months = _perfect_months(student, today)
    for end in months:
        items.append({"id": f"perfect_month-{end:%Y-%m}", "code": "perfect_month", "category": "attendance",
                      "rarity": "epic", "threshold": 1, "current": 1, "unlocked": True, "unlocked_on": end,
                      "xp_reward": None, "params": {"year": end.year, "month": end.month}})
    if not months:
        items.append({"id": "perfect_month", "code": "perfect_month", "category": "attendance", "rarity": "epic",
                      "threshold": 1, "current": 0, "unlocked": False, "unlocked_on": None, "xp_reward": None})

    awards = list(ScholarshipAward.objects.filter(student=student, status=ScholarshipAward.Status.APPROVED)
                  .order_by("award_date", "pk"))
    for award in awards:
        items.append({"id": f"scholarship-{award.pk}", "code": "scholarship", "category": "scholarship",
                      "rarity": "legendary", "threshold": 1, "current": 1, "unlocked": True,
                      "unlocked_on": award.award_date, "xp_reward": None, "params": {"rank": award.rank}})
    if not awards:
        items.append({"id": "scholarship", "code": "scholarship", "category": "scholarship", "rarity": "legendary",
                      "threshold": 1, "current": 0, "unlocked": False, "unlocked_on": None, "xp_reward": None})
    return items


def goals(items: list[dict], *, level: dict, total_xp: int) -> list[dict]:
    """The next locked tier of every family — current, target, what remains."""
    out = []
    for code in ("homework_done", "top_homework", "attendance"):
        nxt = next((i for i in items if i["code"] == code and not i["unlocked"]), None)
        if nxt:
            out.append({"code": code, "category": nxt["category"], "rarity": nxt["rarity"], "current": nxt["current"],
                        "target": nxt["threshold"], "remaining": nxt["threshold"] - nxt["current"], "xp_reward": None})
    # The next level is always a goal: XP, against the real threshold.
    out.append({"code": "level", "category": "level", "rarity": None, "current": total_xp, "target": level["next"],
                "remaining": level["next"] - total_xp, "xp_reward": None, "params": {"level": level["level"] + 1}})
    return out


# ---------------------------------------------------------------------------
# Weekly activity and timeline
# ---------------------------------------------------------------------------

def _counts_by_day(student: Student, start: dt.date, end: dt.date) -> dict[dt.date, dict]:
    from apps.testing.models import AttemptStatus, StudentAttempt
    from django.utils import timezone

    counts: dict[dt.date, dict] = defaultdict(lambda: {"lessons": 0, "homework": 0, "tests": 0})
    for day in (Attendance.objects.filter(student=student, status__in=_ATTENDED, lesson__date__range=(start, end))
                .exclude(lesson__status=Lesson.Status.CANCELLED).values_list("lesson__date", flat=True)):
        counts[day]["lessons"] += 1
    for day in (HomeworkResult.objects.filter(student=student, status__in=_DONE,
                                              homework__lesson__date__range=(start, end))
                .exclude(homework__lesson__status=Lesson.Status.CANCELLED)
                .values_list("homework__lesson__date", flat=True)):
        counts[day]["homework"] += 1
    for finished in (StudentAttempt.objects.filter(student=student, status=AttemptStatus.FINISHED,
                                                   finished_at__isnull=False,
                                                   finished_at__date__gte=start - dt.timedelta(days=1),
                                                   finished_at__date__lte=end + dt.timedelta(days=1))
                     .values_list("finished_at", flat=True)):
        day = timezone.localdate(finished)
        if start <= day <= end:
            counts[day]["tests"] += 1
    return counts


def weekly(student: Student, *, today: dt.date, daily: dict) -> dict:
    start = today - dt.timedelta(days=6)
    counts = _counts_by_day(student, start, today)
    days = []
    for offset in range(7):
        day = start + dt.timedelta(days=offset)
        parts = daily.get(day, {"attendance": 0, "homework": 0, "tests": 0})
        days.append({"date": day, **{f"xp_{k}": v for k, v in parts.items()}, "xp": sum(parts.values()),
                     **counts.get(day, {"lessons": 0, "homework": 0, "tests": 0})})
    previous_start = start - dt.timedelta(days=7)
    previous = sum(sum(parts.values()) for day, parts in daily.items() if previous_start <= day < start)
    has_previous = any(day < start for day in daily)
    return {"start": start, "end": today, "days": days, "total": sum(d["xp"] for d in days),
            "previous_total": previous if has_previous else None}


def timeline(items: list[dict], daily: dict, *, today: dt.date, limit: int = 40) -> list[dict]:
    """Real events, newest first: achievements unlocked, levels reached and
    the XP received on each day of the last 30 days."""
    events = []
    for item in items:
        if item["unlocked"] and item["code"] != "level":
            events.append({"kind": "achievement", "date": item["unlocked_on"], "achievement": item})
    for level, day in level_reached_on(daily).items():
        events.append({"kind": "level", "date": day, "level": level})
    since = today - dt.timedelta(days=30)
    for day, parts in daily.items():
        if day >= since and sum(parts.values()) > 0:
            events.append({"kind": "xp", "date": day, "xp": sum(parts.values()), "parts": parts})
    order = {"level": 0, "achievement": 1, "xp": 2}
    events.sort(key=lambda e: (e["date"], -order[e["kind"]]), reverse=True)
    return events[:limit]


# ---------------------------------------------------------------------------
# The page
# ---------------------------------------------------------------------------

def overview(student: Student, *, today: dt.date) -> dict:
    daily = daily_xp(student, today)
    parts = {"attendance": 0, "homework": 0, "tests": 0}
    for day_parts in daily.values():
        for key, value in day_parts.items():
            parts[key] += value
    total = sum(parts.values())
    level = data.level_for(total)
    items = achievements(student, today=today, daily=daily)
    month_start = today.replace(day=1)
    month = {key: sum(p[key] for d, p in daily.items() if d >= month_start) for key in parts}
    return {
        "level": {**level, "total_xp": total, "to_next": level["next"] - total,
                  "reached_on": level_reached_on(daily).get(level["level"])},
        "xp": {"total": {**parts, "total": total}, "month": {**month, "total": sum(month.values())},
               # Projects earn no XP in the LMS — the page hides the line.
               "projects_supported": False},
        "achievements": items,
        "categories": list(CATEGORIES),
        "goals": goals(items, level=level, total_xp=total),
        "weekly": weekly(student, today=today, daily=daily),
        "timeline": timeline(items, daily, today=today),
    }
