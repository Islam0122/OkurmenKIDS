"""The public leaderboard — top students and top groups for a year, a month
or a week, open to anyone at leaderboard.okurmenkids.com.

XP is *computed*, never stored: every point comes from a real, dated record
the LMS already keeps, so a corrected or deleted result changes the
leaderboard on the next request (the cache version is bumped by signals),
nothing can be credited twice, and no history is ever invented. The rules
(docs/leaderboard.md) are the same for every student:

* Attendance — per marked lesson (non-cancelled, dated in the period):
  PRESENT = 10 XP, LATE = 5 XP. ABSENT / EXCUSED earn nothing.
  `Attendance` is unique per (student, lesson) → one credit per lesson.
* Homework — per result of a homework given on a non-cancelled lesson dated
  in the period: SUBMITTED / CHECKED = 10 XP, LATE = 5 XP, plus the
  trainer's grade (0–10) when there is one. NOT_SUBMITTED earns nothing.
  `HomeworkResult` is unique per (homework, student) → one credit each.
* Tests — per test session: the best finished attempt of the student,
  score 0–100 → round(score / 5) = 0–20 XP, dated by when that best attempt
  was finished. Re-taking a session never adds a second credit.

Dates are the project's calendar (settings.TIME_ZONE, Asia/Bishkek): a
lesson counts on its own date, a test on the local date it was finished.
Weeks run Monday → Sunday.

Who is listed: active students (Student.is_active) of an open group
(active / paused). A student whose `show_in_leaderboard` is off stays in
the ranking (so nobody else's place is faked) but as an anonymous row
without a name or group. Students with 0 XP in the period are not ranked.

Groups are ranked by **average XP per listed student** (total XP of the
group's current students ÷ their number), not by the raw total — a large
group must not win only for being large. Total XP is shown alongside.

What leaves the server is a closed whitelist: a public name (first name +
initial of the last name), opaque keys, group / course names and XP. Never
phones, ids, statuses, comments, grades of single homeworks or answers.
"""
from __future__ import annotations

import datetime as dt
import hashlib
from collections import defaultdict
from dataclasses import dataclass

from django.conf import settings
from django.core.cache import cache
from django.db.models import Count, Max, Min, Q, Sum, Value
from django.db.models.functions import Coalesce, Least
from django.utils import timezone

from apps.academy.models import Attendance, Group, HomeworkResult, Lesson, Student
from apps.academy.services.public_schedule import public_key
from apps.testing.models import AttemptStatus, StudentAttempt

# -- XP rules ----------------------------------------------------------------
XP_ATTENDANCE_PRESENT = 10
XP_ATTENDANCE_LATE = 5
XP_HOMEWORK_DONE = 10
XP_HOMEWORK_LATE = 5
XP_TEST_DIVISOR = 5  # score 0–100 → 0–20 XP

OPEN_GROUP_STATUSES = (Group.Status.ACTIVE, Group.Status.PAUSED)
PERIODS = ("year", "month", "week")
MIN_YEAR = 2000
DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100
TOP_MEMBERS = 5
HIDDEN_NAME = "Скрытый участник"
_VERSION_KEY = "public_leaderboard:version"


class LeaderboardError(ValueError):
    """Invalid request parameters (→ 400)."""


def config() -> dict:
    return {"cache_seconds": getattr(settings, "PUBLIC_LEADERBOARD_CACHE_SECONDS", 120)}


def rules() -> dict:
    return {
        "attendance_present": XP_ATTENDANCE_PRESENT,
        "attendance_late": XP_ATTENDANCE_LATE,
        "homework_done": XP_HOMEWORK_DONE,
        "homework_late": XP_HOMEWORK_LATE,
        "homework_grade_max": 10,
        "test_max": 100 // XP_TEST_DIVISOR,
        "group_method": "average",
        "week_starts": "monday",
        "timezone": settings.TIME_ZONE,
    }


# ---------------------------------------------------------------------------
# Periods
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Period:
    kind: str
    start: dt.date
    end: dt.date

    def previous(self) -> Period:
        if self.kind == "year":
            return year_period(self.start.year - 1)
        if self.kind == "month":
            first = self.start - dt.timedelta(days=1)
            return month_period(first.year, first.month)
        return week_period(self.start - dt.timedelta(days=7))

    def as_dict(self, today: dt.date) -> dict:
        data = {"type": self.kind, "start": self.start, "end": self.end, "is_current": self.start <= today <= self.end}
        if self.kind == "year":
            data["year"] = self.start.year
        elif self.kind == "month":
            data.update(year=self.start.year, month=self.start.month)
        else:
            data["week_start"] = self.start
        return data


def year_period(year: int) -> Period:
    return Period("year", dt.date(year, 1, 1), dt.date(year, 12, 31))


def month_period(year: int, month: int) -> Period:
    start = dt.date(year, month, 1)
    following = dt.date(year + (month == 12), month % 12 + 1, 1)
    return Period("month", start, following - dt.timedelta(days=1))


def week_period(day: dt.date) -> Period:
    monday = day - dt.timedelta(days=day.weekday())
    return Period("week", monday, monday + dt.timedelta(days=6))


def _int(value, name: str, low: int, high: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        raise LeaderboardError(f"{name}: ожидается целое число.")
    if not low <= number <= high:
        raise LeaderboardError(f"{name}: допустимо от {low} до {high}.")
    return number


def resolve_period(kind=None, year=None, month=None, week_start=None, today: dt.date | None = None) -> Period:
    """The requested period; missing parts default to the one containing
    `today`. A period that has not started yet is refused."""
    today = today or timezone.localdate()
    kind = kind or "month"
    if kind not in PERIODS:
        raise LeaderboardError("period: допустимо year, month или week.")
    if kind == "week":
        if week_start in (None, ""):
            period = week_period(today)
        else:
            try:
                day = dt.date.fromisoformat(str(week_start))
            except ValueError:
                raise LeaderboardError("week_start: неверный формат даты (ожидается ГГГГ-ММ-ДД).")
            if day.weekday() != 0:
                raise LeaderboardError("week_start: неделя начинается с понедельника.")
            period = week_period(day)
    else:
        year = today.year if year in (None, "") else _int(year, "year", MIN_YEAR, today.year)
        if kind == "year":
            period = year_period(year)
        else:
            month = today.month if month in (None, "") else _int(month, "month", 1, 12)
            period = month_period(year, month)
    if period.start > today or period.start.year < MIN_YEAR:
        raise LeaderboardError("Этот период ещё не начался.")
    return period


def _day_start(day: dt.date) -> dt.datetime:
    return timezone.make_aware(dt.datetime.combine(day, dt.time.min))


# ---------------------------------------------------------------------------
# XP
# ---------------------------------------------------------------------------

def _empty() -> dict:
    return {"attendance": 0, "homework": 0, "tests": 0}


def student_xp(period: Period) -> dict[int, dict]:
    """{student_id: {attendance, homework, tests}} — XP earned in `period`,
    from three aggregate queries (no per-student queries)."""
    xp: dict[int, dict] = defaultdict(_empty)
    in_period = Q(lesson__date__range=(period.start, period.end)) & ~Q(lesson__status=Lesson.Status.CANCELLED)

    attendance = (
        Attendance.objects.filter(in_period, status__in=(Attendance.Status.PRESENT, Attendance.Status.LATE))
        .values("student_id")
        .annotate(
            present=Count("id", filter=Q(status=Attendance.Status.PRESENT)),
            late=Count("id", filter=Q(status=Attendance.Status.LATE)),
        )
    )
    for row in attendance:
        xp[row["student_id"]]["attendance"] = row["present"] * XP_ATTENDANCE_PRESENT + row["late"] * XP_ATTENDANCE_LATE

    homework = (
        HomeworkResult.objects.filter(
            homework__lesson__date__range=(period.start, period.end),
            status__in=(HomeworkResult.Status.SUBMITTED, HomeworkResult.Status.CHECKED, HomeworkResult.Status.LATE),
        )
        .exclude(homework__lesson__status=Lesson.Status.CANCELLED)
        .values("student_id")
        .annotate(
            done=Count("id", filter=~Q(status=HomeworkResult.Status.LATE)),
            late=Count("id", filter=Q(status=HomeworkResult.Status.LATE)),
            grades=Coalesce(Sum(Least("score", Value(10))), 0),
        )
    )
    for row in homework:
        xp[row["student_id"]]["homework"] = (
            row["done"] * XP_HOMEWORK_DONE + row["late"] * XP_HOMEWORK_LATE + row["grades"]
        )

    for student_id, points in _test_xp(period).items():
        xp[student_id]["tests"] = points
    return xp


def _test_xp(period: Period) -> dict[int, int]:
    """Best finished attempt per (student, session), credited on the local
    date it was finished — so a re-take in a later period adds nothing."""
    finished = StudentAttempt.objects.filter(status=AttemptStatus.FINISHED, student__isnull=False, finished_at__isnull=False)
    pairs = set(
        finished.filter(finished_at__gte=_day_start(period.start), finished_at__lt=_day_start(period.end + dt.timedelta(days=1)))
        .values_list("student_id", "session_id")
    )
    if not pairs:
        return {}
    best: dict[tuple, tuple] = {}
    rows = finished.filter(
        student_id__in={s for s, _ in pairs}, session_id__in={x for _, x in pairs}
    ).values_list("student_id", "session_id", "score", "finished_at")
    for student_id, session_id, score, finished_at in rows:
        pair = (student_id, session_id)
        if pair not in pairs:
            continue
        current = best.get(pair)
        # Highest score wins; on a tie the earliest attempt that reached it.
        if current is None or score > current[0] or (score == current[0] and finished_at < current[1]):
            best[pair] = (score, finished_at)
    xp: dict[int, int] = defaultdict(int)
    for (student_id, _), (score, finished_at) in best.items():
        if period.start <= timezone.localdate(finished_at) <= period.end:
            xp[student_id] += int(max(score, 0) / XP_TEST_DIVISOR + 0.5)
    return xp


# ---------------------------------------------------------------------------
# Who is listed
# ---------------------------------------------------------------------------

def listed_students():
    return (
        Student.objects.filter(is_active=True, group__isnull=False, group__status__in=OPEN_GROUP_STATUSES)
        .select_related("group__course")
        .only("id", "first_name", "last_name", "show_in_leaderboard", "group__id", "group__name",
              "group__course__id", "group__course__name")
    )


def public_name(first_name: str, last_name: str) -> str:
    first, last = (first_name or "").strip(), (last_name or "").strip()
    return f"{first} {last[0]}." if last else first


def initials(first_name: str, last_name: str) -> str:
    return "".join(part.strip()[:1] for part in (first_name or "", last_name or "") if part.strip()).upper()


def _ref(kind: str, obj) -> dict | None:
    return {"key": public_key(kind, obj.pk), "name": obj.name} if obj else None


# ---------------------------------------------------------------------------
# Rankings
# ---------------------------------------------------------------------------

def _assign_ranks(rows: list[dict], score) -> None:
    """Competition ranking: equal scores share a place (1, 2, 2, 4)."""
    previous, rank = None, 0
    for index, row in enumerate(rows, start=1):
        value = score(row)
        if value != previous:
            rank, previous = index, value
        row["rank"] = rank


def _change(rank: int, previous_rank: int | None, previous_has_data: bool) -> dict | None:
    if not previous_has_data:
        return None  # nothing to compare with — neutral, never invented
    if previous_rank is None:
        return {"status": "new", "value": 0}
    delta = previous_rank - rank
    return {"status": "up" if delta > 0 else "down" if delta < 0 else "same", "value": delta}


def _student_rows(period: Period, students: list[Student]) -> list[dict]:
    xp = student_xp(period)
    rows = []
    for student in students:
        points = xp.get(student.pk)
        total = sum(points.values()) if points else 0
        if total <= 0:
            continue
        rows.append({"student": student, "xp": total, "breakdown": dict(points)})
    rows.sort(key=lambda r: (-r["xp"], r["student"].first_name.lower(), r["student"].last_name.lower(), r["student"].pk))
    _assign_ranks(rows, lambda r: r["xp"])
    return rows


def _group_rows(student_rows: list[dict], students: list[Student]) -> list[dict]:
    members: dict[int, list[Student]] = defaultdict(list)
    for student in students:
        members[student.group_id].append(student)
    earned: dict[int, list[dict]] = defaultdict(list)
    for row in student_rows:
        earned[row["student"].group_id].append(row)
    rows = []
    for group_id, group_rows in earned.items():
        total = sum(r["xp"] for r in group_rows)
        size = len(members[group_id])
        rows.append({
            "group": group_rows[0]["student"].group,
            "total_xp": total,
            "members": size,
            "active_students": len(group_rows),
            "average_xp": round(total / size, 1),
            "top": [r for r in group_rows if r["student"].show_in_leaderboard][:TOP_MEMBERS],
        })
    rows.sort(key=lambda r: (-r["average_xp"], -r["total_xp"], r["group"].name.lower()))
    _assign_ranks(rows, lambda r: r["average_xp"])
    return rows


def _student_public(row: dict, change: dict | None) -> dict:
    student = row["student"]
    group = student.group
    visible = student.show_in_leaderboard
    return {
        "key": public_key("student", student.pk),
        "rank": row["rank"],
        "name": public_name(student.first_name, student.last_name) if visible else HIDDEN_NAME,
        "initials": initials(student.first_name, student.last_name) if visible else "",
        "hidden": not visible,
        "group": _ref("group", group) if visible else None,
        "course": _ref("course", group.course) if visible else None,
        "xp": row["xp"],
        "breakdown": row["breakdown"],
        "change": change,
    }


def _group_public(row: dict, change: dict | None) -> dict:
    group = row["group"]
    return {
        "key": public_key("group", group.pk),
        "rank": row["rank"],
        "name": group.name,
        "course": _ref("course", group.course),
        "members": row["members"],
        "active_students": row["active_students"],
        "total_xp": row["total_xp"],
        "average_xp": row["average_xp"],
        "top_members": [
            {"name": public_name(r["student"].first_name, r["student"].last_name),
             "initials": initials(r["student"].first_name, r["student"].last_name), "xp": r["xp"]}
            for r in row["top"]
        ],
        "change": change,
    }


def compute(period: Period, today: dt.date | None = None) -> dict:
    """Both full rankings of `period`, each row with its change against the
    previous comparable period (same students, same rules)."""
    today = today or timezone.localdate()
    students = list(listed_students())
    current = _student_rows(period, students)
    previous = _student_rows(period.previous(), students)
    previous_student_rank = {r["student"].pk: r["rank"] for r in previous}
    current_groups = _group_rows(current, students)
    previous_groups = {r["group"].pk: r["rank"] for r in _group_rows(previous, students)}
    return {
        "period": period.as_dict(today),
        "previous_period": period.previous().as_dict(today),
        "generated_at": timezone.now(),
        "students": [
            _student_public(r, _change(r["rank"], previous_student_rank.get(r["student"].pk), bool(previous)))
            for r in current
        ],
        "groups": [
            _group_public(r, _change(r["rank"], previous_groups.get(r["group"].pk), bool(previous_groups)))
            for r in current_groups
        ],
    }


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


def cached(name: str, params: dict, build):
    seconds = config()["cache_seconds"]
    if not seconds:
        return build()
    raw = "&".join(f"{k}={params[k]}" for k in sorted(params) if params[k] not in (None, ""))
    key = f"public_leaderboard:{cache_version()}:{name}:{hashlib.sha1(raw.encode()).hexdigest()}"
    value = cache.get(key)
    if value is None:
        value = build()
        cache.set(key, value, seconds)
    return value


def rankings(period: Period) -> dict:
    today = timezone.localdate()
    return cached("rankings", {"kind": period.kind, "start": period.start, "today": today}, lambda: compute(period, today))


# ---------------------------------------------------------------------------
# Public responses
# ---------------------------------------------------------------------------

def _paginate(rows: list[dict], page, page_size) -> dict:
    page_size = DEFAULT_PAGE_SIZE if page_size in (None, "") else _int(page_size, "page_size", 1, MAX_PAGE_SIZE)
    num_pages = max(1, -(-len(rows) // page_size))
    page = 1 if page in (None, "") else _int(page, "page", 1, 10_000)
    offset = (page - 1) * page_size
    return {"count": len(rows), "page": page, "page_size": page_size, "num_pages": num_pages,
            "results": rows[offset:offset + page_size]}


def _matches(text: str, query: str) -> bool:
    return query.casefold() in text.casefold()


def student_board(period: Period, *, q="", group=None, course=None, order="desc", page=None, page_size=None) -> dict:
    data = rankings(period)
    rows = data["students"]
    q = (q or "").strip()[:100]
    if q:
        rows = [r for r in rows if not r["hidden"] and _matches(r["name"], q)]
    if group:
        rows = [r for r in rows if r["group"] and r["group"]["key"] == group]
    if course:
        rows = [r for r in rows if r["course"] and r["course"]["key"] == course]
    if order == "asc":
        rows = list(reversed(rows))
    elif order not in (None, "", "desc"):
        raise LeaderboardError("order: допустимо asc или desc.")
    return {
        "period": data["period"],
        "previous_period": data["previous_period"],
        "generated_at": data["generated_at"],
        "participants": len(data["students"]),
        "podium": data["students"][:3],
        **_paginate(rows, page, page_size),
    }


def group_board(period: Period, *, q="", course=None, order="desc", page=None, page_size=None) -> dict:
    data = rankings(period)
    rows = data["groups"]
    q = (q or "").strip()[:100]
    if q:
        rows = [r for r in rows if _matches(r["name"], q)]
    if course:
        rows = [r for r in rows if r["course"] and r["course"]["key"] == course]
    if order == "asc":
        rows = list(reversed(rows))
    elif order not in (None, "", "desc"):
        raise LeaderboardError("order: допустимо asc или desc.")
    return {
        "period": data["period"],
        "previous_period": data["previous_period"],
        "generated_at": data["generated_at"],
        "participants": len(data["groups"]),
        "students_ranked": len(data["students"]),
        "podium": data["groups"][:3],
        **_paginate(rows, page, page_size),
    }


def meta(today: dt.date | None = None) -> dict:
    """Everything the filters and period pickers need: current periods, the
    years that have data, groups and courses (public keys), the XP rules."""
    today = today or timezone.localdate()
    first_lesson = (
        Attendance.objects.exclude(lesson__status=Lesson.Status.CANCELLED).aggregate(first=Min("lesson__date"))["first"]
    )
    first_attempt = StudentAttempt.objects.filter(
        status=AttemptStatus.FINISHED, student__isnull=False
    ).aggregate(first=Min("finished_at"))["first"]
    starts = [d for d in (first_lesson, first_attempt and timezone.localdate(first_attempt)) if d]
    first_year = max(MIN_YEAR, min(starts).year) if starts else today.year
    first_year = min(first_year, today.year)
    groups = (
        Group.objects.filter(status__in=OPEN_GROUP_STATUSES)
        .annotate(listed=Count("students", filter=Q(students__is_active=True)))
        .filter(listed__gt=0)
        .select_related("course")
        .order_by("name")
    )
    courses: dict[int, dict] = {}
    group_list = []
    for group in groups:
        course = _ref("course", group.course)
        if course:
            courses.setdefault(group.course.pk, course)
        group_list.append({"key": public_key("group", group.pk), "name": group.name, "course": course["key"] if course else None})
    week = week_period(today)
    return {
        "today": today,
        "timezone": settings.TIME_ZONE,
        "current": {"year": today.year, "month": today.month, "week_start": week.start},
        "first_date": min(starts) if starts else None,
        "years": list(range(today.year, first_year - 1, -1)),
        "groups": group_list,
        "courses": sorted(courses.values(), key=lambda c: c["name"].lower()),
        "rules": rules(),
        "last_activity": last_activity(),
    }


def last_activity():
    """When the newest XP-bearing record was last written — «данные
    обновлены» on the site."""
    stamps = [
        Attendance.objects.aggregate(v=Max("updated_at"))["v"],
        HomeworkResult.objects.aggregate(v=Max("updated_at"))["v"],
        StudentAttempt.objects.filter(status=AttemptStatus.FINISHED, student__isnull=False).aggregate(v=Max("finished_at"))["v"],
    ]
    stamps = [s for s in stamps if s]
    return max(stamps) if stamps else None
