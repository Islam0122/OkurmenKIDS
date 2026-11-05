"""Показатели академии по дням — по расписанию именно этого дня.

Источники (существующие модели apps.academy, без дублей):

* **Расписание дня** — занятия (`Lesson`) с этой датой. Генератор создаёт их
  из недельного расписания группы (`GroupSchedule`), с учётом переносов и
  отмен, поэтому у каждой группы свои дни (Пн/Ср/Пт, Вт/Чт/Сб…), а смена
  расписания не переписывает прошлые дни — прошедшие занятия остаются как были.
* **Состав групп на дату** — `services.student_roster.RosterHistory`: группа и
  статус студента *на тот день* по журналу `StudentStatusEvent` (зачисление,
  перевод, деактивация, пауза). Поэтому история не меняется при деактивации
  студента или переводе в другую группу сегодня.

Для дня D:

* **Групп по расписанию** — группы с неотменёнными занятиями в D.
* **Групп с проведёнными занятиями** — из них группы, где занятие состоялось
  (статус «Идёт занятие»/«Проведён» или отмечена посещаемость).
* **Студентов по расписанию** — уникальные студенты, активные на D и
  состоящие на D в этих группах.
* **Посетили занятия** — уникальные студенты из них с отметкой
  «Присутствовал» или «Опоздал» хотя бы на одном занятии дня.
* **Посещаемость, %** — посетили / ожидались на занятиях, которые должны
  были состояться (отменённые не учитываются; сегодня — только уже
  начавшиеся). Нет таких занятий — «Нет занятий» (``None``).
* **Домашние задания, %** — по логике аналитики LMS: результаты ДЗ, заданного
  на занятиях дня D, у студентов, активных на D: сдано (в срок, с опозданием,
  проверено) / все результаты. Нет результатов — «Нет данных» (``None``).

Сегодняшние и будущие занятия учитываются только у групп, активных сейчас
(пауза/закрытие группы); прошлые — как они были проведены.
Календарный день — по часовому поясу проекта (`TIME_ZONE`); даты занятий —
DateField, поэтому преобразований DateTime → дата для них не требуется.
"""
from __future__ import annotations

import datetime as dt
from collections import defaultdict
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal

from django.utils import timezone

from apps.academy.models import Attendance, Group, HomeworkResult, Lesson, Student
from apps.academy.services.student_roster import RosterHistory

ATTENDED_STATUSES = (Attendance.Status.PRESENT, Attendance.Status.LATE)
DONE_HOMEWORK_STATUSES = (
    HomeworkResult.Status.SUBMITTED, HomeworkResult.Status.CHECKED, HomeworkResult.Status.LATE,
)
HELD_STATUSES = (Lesson.Status.IN_PROGRESS, Lesson.Status.COMPLETED)


def percent(part: int, total: int) -> Decimal | None:
    if not total:
        return None
    return (Decimal(part) * 100 / Decimal(total)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)


@dataclass
class DayStats:
    lessons_count: int = 0
    held_lessons_count: int = 0
    scheduled_groups: int = 0
    held_groups: int = 0
    scheduled_students: int = 0
    attended_students: int = 0
    # Ожидались на занятиях, которые уже должны были состояться (знаменатель посещаемости).
    expected_students: int = 0
    homework_results: int = 0
    homework_done: int = 0
    group_ids: list[int] = field(default_factory=list)

    @property
    def attendance_percent(self) -> Decimal | None:
        return percent(self.attended_students, self.expected_students)

    @property
    def homework_percent(self) -> Decimal | None:
        return percent(self.homework_done, self.homework_results)

    def as_values(self) -> dict:
        return {
            "lessons_count": self.lessons_count,
            "held_lessons_count": self.held_lessons_count,
            "scheduled_groups": self.scheduled_groups,
            "held_groups": self.held_groups,
            "scheduled_students": self.scheduled_students,
            "attended_students": self.attended_students,
            "expected_students": self.expected_students,
            "attendance_percent": self.attendance_percent,
            "homework_results": self.homework_results,
            "homework_done": self.homework_done,
            "homework_percent": self.homework_percent,
        }


def _started(lesson: dict, today: dt.date, now_time: dt.time) -> bool:
    """Занятие уже должно было состояться (прошлый день или сегодня после начала)."""
    if lesson["date"] < today:
        return True
    return lesson["status"] in HELD_STATUSES or (lesson["date"] == today and lesson["start_time"] <= now_time)


def compute_days(start: dt.date, end: dt.date, *, now: dt.datetime | None = None) -> dict[dt.date, DayStats]:
    """Показатели каждого дня [start, end] (не позже сегодня) — пакетно, за несколько запросов."""
    now = now or timezone.now()
    local_now = timezone.localtime(now)
    today, now_time = local_now.date(), local_now.time()
    end = min(end, today)
    result: dict[dt.date, DayStats] = {}
    if start > end:
        return result
    day = start
    while day <= end:
        result[day] = DayStats()
        day += dt.timedelta(days=1)

    lessons = list(
        Lesson.objects.filter(date__range=(start, end)).exclude(status=Lesson.Status.CANCELLED)
        .values("id", "group_id", "date", "start_time", "status", "group__status")
    )
    # Сегодня — только группы, активные сейчас (на паузе/закрытые не занимаются).
    lessons = [l for l in lessons if l["date"] < today or l["group__status"] == Group.Status.ACTIVE]
    if not lessons:
        return result
    lesson_ids = [l["id"] for l in lessons]

    marks_by_lesson: dict[int, list[tuple[int, str]]] = defaultdict(list)
    for row in Attendance.objects.filter(lesson_id__in=lesson_ids).values_list("lesson_id", "student_id", "status"):
        marks_by_lesson[row[0]].append((row[1], row[2]))
    results_by_lesson: dict[int, list[tuple[int, str]]] = defaultdict(list)
    for row in HomeworkResult.objects.filter(homework__lesson_id__in=lesson_ids).values_list(
        "homework__lesson_id", "student_id", "status",
    ):
        results_by_lesson[row[0]].append((row[1], row[2]))

    history = RosterHistory(group_ids={l["group_id"] for l in lessons})
    by_day: dict[dt.date, list[dict]] = defaultdict(list)
    for lesson in lessons:
        by_day[lesson["date"]].append(lesson)

    for day, day_lessons in by_day.items():
        stats = result[day]
        roster = history.on(day)
        active_by_group: dict[int, set[int]] = defaultdict(set)
        active_ids: set[int] = set()
        for entry in roster.values():
            if entry.status == Student.Status.ACTIVE and entry.group_id is not None:
                active_by_group[entry.group_id].add(entry.student_id)
                active_ids.add(entry.student_id)

        scheduled_groups = {l["group_id"] for l in day_lessons}
        started = [l for l in day_lessons if _started(l, today, now_time)]
        held = [l for l in day_lessons if l["status"] in HELD_STATUSES or marks_by_lesson.get(l["id"])]
        scheduled_students = set().union(*(active_by_group[g] for g in scheduled_groups))
        expected = set().union(*(active_by_group[l["group_id"]] for l in started)) if started else set()
        attendees = {sid for l in started for sid, status in marks_by_lesson.get(l["id"], []) if status in ATTENDED_STATUSES}

        homework = [(sid, status) for l in started for sid, status in results_by_lesson.get(l["id"], []) if sid in active_ids]

        stats.lessons_count = len(day_lessons)
        stats.held_lessons_count = len(held)
        stats.scheduled_groups = len(scheduled_groups)
        stats.held_groups = len({l["group_id"] for l in held})
        stats.scheduled_students = len(scheduled_students)
        stats.expected_students = len(expected)
        stats.attended_students = len(attendees & expected)
        stats.homework_results = len(homework)
        stats.homework_done = sum(1 for _, status in homework if status in DONE_HOMEWORK_STATUSES)
        stats.group_ids = sorted(scheduled_groups)
    return result


def compute_day(day: dt.date, *, now: dt.datetime | None = None) -> DayStats:
    return compute_days(day, day, now=now).get(day, DayStats())
