"""A group's study month and progress — computed, never stored.

* **Counted lessons** — the group's COMPLETED lessons (a lesson really held:
  a scheduled one is not, a cancelled one never is). Each (program, lesson
  number) and each (subject, date, time) counts once, so a rescheduled lesson (the cancelled original plus
  its make-up, which carries the same number — services.lesson_reschedule)
  or a duplicated record never adds twice. With «Только основные предметы»
  the lessons of the program's extra subjects (English, Soft…) don't count.
  Students' absences change nothing: this is the group's progress.
* **Study months** — the program's ProgramCurriculum: `duration_months`
  months of `lessons_per_month` lessons each, any month overriding its
  subject and/or lesson count (CurriculumMonth).
* **Current month** — walk the months with the counted lessons (plus the
  ones confirmed as held before the LMS): the month whose plan is not yet
  full. Exactly full → the next month starts (0 / N). All full → completed.
* **«Требуется настройка»** — no curriculum for the program, or the group's
  recorded lessons don't start from №1 (earlier lessons are not in the LMS)
  and nobody confirmed how many were held before. Nothing is guessed.
"""
from __future__ import annotations

import datetime as dt
from collections import defaultdict
from dataclasses import dataclass

from django.db.models import Min, Q
from django.utils import timezone

from apps.academy.models import Attendance, Group, Lesson, Student

from .models import GroupProgressAdjustment, ProgramCurriculum

ATTENDED = (Attendance.Status.PRESENT, Attendance.Status.LATE)

NEEDS_SETUP = "needs_setup"
NOT_STARTED = "not_started"
IN_PROGRESS = "in_progress"
COMPLETED = "completed"
STATUS_LABELS = {
    NEEDS_SETUP: "Требуется настройка",
    NOT_STARTED: "Ещё не начались",
    IN_PROGRESS: "Идёт обучение",
    COMPLETED: "Курс пройден",
}


def pct(part: int, whole: int) -> float | None:
    return min(round(part / whole * 100, 1), 100.0) if whole else None


def _subject_ref(subject) -> dict | None:
    return {"id": subject.pk, "name": subject.name} if subject is not None else None


@dataclass
class Block:
    number: int
    planned: int
    subject: object | None


def blocks(curriculum: ProgramCurriculum) -> list[Block]:
    """The program's study months, in order, with defaults filled in."""
    overrides = {m.number: m for m in curriculum.months.all()}
    out = []
    for number in range(1, curriculum.duration_months + 1):
        m = overrides.get(number)
        out.append(Block(
            number=number,
            planned=(m.planned_lessons if m and m.planned_lessons else curriculum.lessons_per_month),
            subject=(m.subject if m and m.subject_id else curriculum.main_subject),
        ))
    return out


def load_curricula(course_ids) -> dict[int, ProgramCurriculum]:
    qs = (ProgramCurriculum.objects.filter(course_id__in=set(course_ids))
          .select_related("main_subject").prefetch_related("extra_subjects", "months__subject"))
    return {c.course_id: c for c in qs}


def _counted_lessons(groups: list[Group], curricula: dict[int, ProgramCurriculum]) -> dict[int, list[Lesson]]:
    """Group id -> its counted lessons, chronological, one per (program, number)."""
    if not groups:
        return {}
    lessons = (Lesson.objects.filter(group__in=groups, status=Lesson.Status.COMPLETED)
               .only("pk", "group_id", "group_teacher_id", "lesson_number", "subject_id", "date", "start_time")
               .order_by("date", "start_time", "pk"))
    out: dict[int, list[Lesson]] = defaultdict(list)
    seen: set = set()
    group_course = {g.pk: g.course_id for g in groups}
    for lesson in lessons:
        curriculum = curricula.get(group_course[lesson.group_id])
        if curriculum is not None and curriculum.count_mode == ProgramCurriculum.CountMode.MAIN:
            extra = {s.pk for s in curriculum.extra_subjects.all()}
            if lesson.subject_id in extra:
                continue
        # A lesson already counted — the same program's number, or the same
        # subject at the same date and time recorded twice — never adds again.
        keys = [(lesson.group_id, "slot", lesson.subject_id, lesson.date, lesson.start_time)]
        if lesson.group_teacher_id:
            keys.append((lesson.group_id, "number", lesson.group_teacher_id, lesson.lesson_number))
        if any(k in seen for k in keys):
            continue
        seen.update(keys)
        out[lesson.group_id].append(lesson)
    return out


def _history_gaps(groups: list[Group], curricula: dict[int, ProgramCurriculum]) -> set[int]:
    """Groups whose recorded lessons don't start from №1 — the first
    lessons of some program are missing from the LMS."""
    rows = (Lesson.objects.filter(group__in=groups, group_teacher__isnull=False)
            .exclude(status=Lesson.Status.CANCELLED)
            .values("group_id", "group_teacher_id", "subject_id").annotate(first=Min("lesson_number")))
    group_course = {g.pk: g.course_id for g in groups}
    gaps = set()
    for row in rows:
        curriculum = curricula.get(group_course[row["group_id"]])
        if curriculum is not None and curriculum.count_mode == ProgramCurriculum.CountMode.MAIN:
            if row["subject_id"] in {s.pk for s in curriculum.extra_subjects.all()}:
                continue
        if row["first"] and row["first"] > 1:
            gaps.add(row["group_id"])
    return gaps


def progress_for(groups: list[Group], *, today: dt.date | None = None) -> dict[int, dict]:
    """Progress of several groups with a handful of queries."""
    today = today or timezone.localdate()
    groups = list(groups)
    curricula = load_curricula(g.course_id for g in groups)
    counted = _counted_lessons(groups, curricula)
    gaps = _history_gaps(groups, curricula)
    adjustments = {a.group_id: a for a in GroupProgressAdjustment.objects.filter(group__in=groups)}
    return {
        g.pk: _progress(g, curricula.get(g.course_id), counted.get(g.pk, []), g.pk in gaps, adjustments.get(g.pk), today)
        for g in groups
    }


def group_progress(group: Group, *, today: dt.date | None = None) -> dict:
    return progress_for([group], today=today)[group.pk]


def _progress(group, curriculum, lessons, gap, adjustment, today) -> dict:
    before = adjustment.lessons_before_lms if adjustment else 0
    held_in_lms = len(lessons)
    base = {
        "configured": curriculum is not None,
        "lessons_in_lms": held_in_lms,
        "lessons_before_lms": before,
        "history_confirmed": adjustment is not None,
        "last_lesson_date": lessons[-1].date if lessons else None,
    }
    if curriculum is None:
        return {**base, "status": NEEDS_SETUP, "status_display": STATUS_LABELS[NEEDS_SETUP],
                "reason": "Для программы группы не настроены учебные месяцы.", "month": None, "months": [], "course": None}
    if gap and adjustment is None:
        return {**base, "status": NEEDS_SETUP, "status_display": STATUS_LABELS[NEEDS_SETUP],
                "reason": "Первые занятия группы не внесены в LMS — укажите, сколько занятий проведено до LMS.",
                "month": None, "months": [], "course": None}

    plan = blocks(curriculum)
    done_total = held_in_lms + before
    planned_total = sum(b.planned for b in plan)

    # Lesson dates per block (LMS lessons only; the pre-LMS ones fill the first places).
    months, cursor, current = [], 0, None
    for b in plan:
        start, end = cursor, cursor + b.planned
        done = max(0, min(done_total, end) - start)
        lms_slice = lessons[max(0, start - before):max(0, end - before)]
        state = "done" if done_total >= end else ("current" if done_total >= start and current is None else "upcoming")
        if state == "current":
            current = b
        months.append({
            "number": b.number,
            "subject": _subject_ref(b.subject),
            "planned": b.planned,
            "done": done,
            "remaining": b.planned - done,
            "progress": pct(done, b.planned),
            "state": state,
            "first_date": lms_slice[0].date if lms_slice else None,
            "last_date": lms_slice[-1].date if lms_slice else None,
        })
        cursor = end

    course = {"done": min(done_total, planned_total), "planned": planned_total,
              "remaining": max(planned_total - done_total, 0), "progress": pct(done_total, planned_total),
              "extra": max(done_total - planned_total, 0)}
    if current is None:
        status = COMPLETED
        month = months[-1]
    else:
        month = months[current.number - 1]
        status = NOT_STARTED if done_total == 0 else IN_PROGRESS
    return {
        **base,
        "status": status,
        "status_display": STATUS_LABELS[status],
        "reason": "",
        "month": {**month, "next_lesson": None if status == COMPLETED else month["done"] + 1,
                  "label": f"{month['number']}-й месяц"},
        "months": months,
        "course": course,
        "count_mode": curriculum.count_mode,
    }


def student_progress(group: Group, progress: dict) -> list[dict]:
    """Each student's own progress in the group's current month — kept apart
    from the group's: the group held N lessons whatever a student missed."""
    month = progress.get("month")
    if not month or progress["status"] == NEEDS_SETUP:
        return []
    curricula = load_curricula([group.course_id])
    lessons = _counted_lessons([group], curricula).get(group.pk, [])
    before = progress["lessons_before_lms"]
    start = sum(m["planned"] for m in progress["months"][:month["number"] - 1])
    block = lessons[max(0, start - before):max(0, start + month["planned"] - before)]
    all_ids = [lesson.pk for lesson in lessons]
    block_ids = {lesson.pk for lesson in block}
    marks = Attendance.objects.filter(lesson_id__in=all_ids).values_list("student_id", "lesson_id", "status")
    attended_all: dict[int, int] = defaultdict(int)
    attended_block: dict[int, int] = defaultdict(int)
    for student_id, lesson_id, status in marks:
        if str(status).strip().lower() in ATTENDED:
            attended_all[student_id] += 1
            if lesson_id in block_ids:
                attended_block[student_id] += 1
    students = Student.objects.filter(Q(group=group, status__in=(Student.Status.ACTIVE, Student.Status.PAUSED))).order_by(
        "last_name", "first_name")
    return [
        {
            "id": s.pk, "name": str(s),
            "month_attended": attended_block[s.pk], "month_held": len(block),
            "month_rate": pct(attended_block[s.pk], len(block)),
            "course_attended": attended_all[s.pk], "course_held": len(lessons),
        }
        for s in students
    ]
