"""Educational month and lesson — «3 месяц · 5 урок» / «3-ай · 5-сабак» /
«Month 3 · Lesson 5». The ONE numbering service of the LMS: every page and
role gets a lesson's number from here.

Where the numbers come from (audit of the data model):

* ``Lesson.lesson_number`` is NOT the lesson's place in its subject. Lessons
  generated from a group's shared course plan carry the plan row's
  course-wide number (CourseLessonPlan is unique per course, not per
  subject): in a course whose plan interleaves IT, Soft Skills and English,
  IT lesson 29 is row 85. It must never be split into months directly.
* The **position** of a lesson in its subject's own sequence is its rank
  among the plan rows of the same subject:
    - shared course plan (Lesson.plan): rank among the course's
      CourseLessonPlan rows of that subject, by lesson_number;
    - a program's own plan (Lesson.individual_plan): rank among that
      program's GroupTeacherLessonPlan rows;
    - a lesson without a plan link (plan row deleted, made by hand): the plan
      row of the same subject and lesson_number, if there is one.
  Otherwise there is not enough information and no number is shown —
  nothing is guessed. Each subject (IT, English, Soft Skills, …) has its own
  independent sequence; cancelled lessons and their make-ups keep their plan
  row, so nothing shifts.
* The **educational month** comes from the curriculum, never from dates:
    - a subject the program's study months name (ProgramCurriculum main
      subject / CurriculumMonth subject) follows those months — their
      numbers and their lesson counts (e.g. React in months 4–6 starts at
      «4 месяц · 1 урок»);
    - any other subject (English, Soft Skills…) is split into months of the
      group's lessons per month: its own setting (GroupLessonNumbering), else
      the program's, else 12.
  Lessons beyond the planned months continue with the same size.
* Changing the lessons per month never renumbers what already took place:
  freeze_history() keeps the old months of every subject up to its last
  held lesson (NumberingFreeze).
"""
from __future__ import annotations

import datetime as dt
from collections import defaultdict
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass

from django.db.models import Q
from django.utils import timezone

from apps.academy.models import CourseLessonPlan, Group, GroupTeacher, GroupTeacherLessonPlan, Lesson

from .models import DEFAULT_LESSONS_PER_MONTH, GroupLessonNumbering, NumberingFreeze, ProgramCurriculum

LABELS = {
    "ru": "{month} месяц · {lesson} урок",
    "ky": "{month}-ай · {lesson}-сабак",
    "en": "Month {month} · Lesson {lesson}",
}


def label(month: int, lesson: int, lang: str = "ru") -> str:
    return LABELS.get(lang, LABELS["ru"]).format(month=month, lesson=lesson)


def split(position: int, per_month: int, *, first_lesson: int = 1, first_month: int = 1) -> tuple[int, int]:
    """(month, lesson) of a position in a run of `per_month`-lesson months."""
    offset = position - first_lesson
    return first_month + offset // per_month, offset % per_month + 1


@dataclass(frozen=True)
class Segment:
    first: int            # first position
    month: int            # its educational month
    size: int             # lessons per month in this run
    last: int | None      # last position (None = open end)


@dataclass
class Layout:
    """One subject's sequence split into educational months."""

    segments: list[Segment]

    def place(self, position: int) -> tuple[int, int, int]:
        for segment in self.segments:
            if position >= segment.first and (segment.last is None or position <= segment.last):
                month, lesson = split(position, segment.size, first_lesson=segment.first, first_month=segment.month)
                return month, lesson, segment.size
        first = self.segments[0]
        month, lesson = split(position, first.size)
        return month, lesson, first.size

    def months_up_to(self, position: int) -> list[Segment]:
        """The closed segments covering whole months up to `position` (for freezing)."""
        out = []
        for segment in self.segments:
            if position < segment.first:
                break
            end = segment.last
            if end is None or end > position:
                months = (position - segment.first) // segment.size + 1
                end = segment.first + months * segment.size - 1
                out.append(Segment(segment.first, segment.month, segment.size, end))
                break
            out.append(segment)
        return out


def build_layout(size: int, blocks: list[tuple[int, int]], freezes: list) -> Layout:
    """`blocks`: (month number, planned lessons) of the curriculum months of this
    subject, in order; `freezes`: NumberingFreeze rows of this subject."""
    segments: list[Segment] = []
    position, month = 1, 1
    for freeze in sorted(freezes, key=lambda f: f.first_lesson):
        if freeze.first_lesson > position:  # never happens when written by freeze_history
            segments.append(Segment(position, month, size, freeze.first_lesson - 1))
        segments.append(Segment(freeze.first_lesson, freeze.first_month, freeze.lessons_per_month, freeze.last_lesson))
        months = (freeze.last_lesson - freeze.first_lesson + 1 + freeze.lessons_per_month - 1) // freeze.lessons_per_month
        position, month = freeze.last_lesson + 1, freeze.first_month + months
    for number, planned in blocks:
        if number < month or planned <= 0:
            continue
        segments.append(Segment(position, number, planned, position + planned - 1))
        position, month = position + planned, number + 1
    segments.append(Segment(position, month, size, None))
    return Layout(segments)


@dataclass
class _Course:
    plan_rank: dict[int, tuple[int | None, int]]          # plan row id -> (subject, position)
    by_number: dict[tuple[int | None, int], int]           # (subject, lesson_number) -> position
    blocks: dict[int, list[tuple[int, int]]]               # subject -> [(month, planned)]
    curriculum: ProgramCurriculum | None


@dataclass
class _Program:
    subject_id: int | None
    plan_rank: dict[int, int]                              # individual plan row id -> position
    by_number: dict[int, int]                              # lesson_number -> position


def _ranks(rows) -> tuple[dict, dict]:
    """rows: (id, subject, lesson_number) → ({id: (subject, pos)}, {(subject, n): pos})."""
    by_subject: dict = defaultdict(list)
    for row_id, subject_id, number in rows:
        by_subject[subject_id].append((number, row_id))
    rank, by_number = {}, {}
    for subject_id, items in by_subject.items():
        for position, (number, row_id) in enumerate(sorted(items), start=1):
            rank[row_id] = (subject_id, position)
            by_number[(subject_id, number)] = position
    return rank, by_number


def _curriculum_blocks(curriculum: ProgramCurriculum | None, per_month: int | None) -> dict[int, list[tuple[int, int]]]:
    if curriculum is None:
        return {}
    from .progress import blocks

    out: dict[int, list[tuple[int, int]]] = defaultdict(list)
    for block in blocks(curriculum, per_month):
        if block.subject is not None:
            out[block.subject.pk].append((block.number, block.planned))
    return dict(out)


def effective_sizes(group_ids) -> dict[int, int]:
    """Group id -> lessons per educational month (group > program > 12)."""
    group_ids = set(group_ids)
    if not group_ids:
        return {}
    courses = dict(Group.objects.filter(pk__in=group_ids).values_list("pk", "course_id"))
    by_course = dict(ProgramCurriculum.objects.filter(course_id__in=set(courses.values()))
                     .values_list("course_id", "lessons_per_month"))
    own = dict(GroupLessonNumbering.objects.filter(group_id__in=group_ids).values_list("group_id", "lessons_per_month"))
    return {gid: own.get(gid) or by_course.get(courses.get(gid)) or DEFAULT_LESSONS_PER_MONTH for gid in group_ids}


class Numbering:
    """Batch resolver: a handful of queries for any number of lessons."""

    def __init__(self):
        self._groups: dict[int, tuple[int, int | None]] = {}       # group -> (course, own size)
        self._courses: dict[int, _Course] = {}
        self._programs: dict[int, _Program] = {}
        self._freezes: dict[int, dict[int | None, list]] = {}      # group -> subject -> rows
        self._layouts: dict[tuple[int, int | None], Layout] = {}

    def clear(self) -> None:
        self.__init__()

    # -- loading
    def prime(self, lessons) -> Numbering:
        lessons = [lesson for lesson in lessons if lesson is not None and lesson.group_id]
        self._load_groups({lesson.group_id for lesson in lessons})
        self._load_programs({lesson.group_teacher_id for lesson in lessons if lesson.group_teacher_id})
        return self

    def _load_groups(self, group_ids) -> None:
        new = set(group_ids) - set(self._groups)
        if not new:
            return
        own = dict(GroupLessonNumbering.objects.filter(group_id__in=new).values_list("group_id", "lessons_per_month"))
        for gid, course_id in Group.objects.filter(pk__in=new).values_list("pk", "course_id"):
            self._groups[gid] = (course_id, own.get(gid))
            self._freezes[gid] = defaultdict(list)
        for freeze in NumberingFreeze.objects.filter(group_id__in=new):
            self._freezes[freeze.group_id][freeze.subject_id].append(freeze)
        courses = {course for course, _ in (self._groups[g] for g in new if g in self._groups)} - set(self._courses)
        if courses:
            from .progress import load_curricula

            curricula = load_curricula(courses)
            rows = defaultdict(list)
            for row in CourseLessonPlan.objects.filter(course_id__in=courses).values_list("course_id", "pk", "subject_id",
                                                                                          "lesson_number"):
                rows[row[0]].append(row[1:])
            for course_id in courses:
                rank, by_number = _ranks(rows.get(course_id, []))
                self._courses[course_id] = _Course(rank, by_number, {}, curricula.get(course_id))

    def _load_programs(self, program_ids) -> None:
        new = set(program_ids) - set(self._programs)
        if not new:
            return
        rows = defaultdict(list)
        for gt_id, pk, number in GroupTeacherLessonPlan.objects.filter(group_teacher_id__in=new).values_list(
                "group_teacher_id", "pk", "lesson_number"):
            rows[gt_id].append((number, pk))
        for gt_id, subject_id in GroupTeacher.objects.filter(pk__in=new).values_list("pk", "subject_id"):
            ordered = sorted(rows.get(gt_id, []))
            self._programs[gt_id] = _Program(
                subject_id,
                {pk: position for position, (_, pk) in enumerate(ordered, start=1)},
                {number: position for position, (number, _) in enumerate(ordered, start=1)},
            )

    # -- resolving
    def position(self, lesson: Lesson) -> tuple[int | None, int] | None:
        """(subject id, position in that subject's sequence) — None when the
        curriculum does not say."""
        if lesson is None or not lesson.group_id:
            return None
        self._load_groups([lesson.group_id])
        if lesson.group_teacher_id:
            self._load_programs([lesson.group_teacher_id])
        course_id, _ = self._groups.get(lesson.group_id, (None, None))
        course = self._courses.get(course_id)
        program = self._programs.get(lesson.group_teacher_id) if lesson.group_teacher_id else None
        subject = lesson.subject_id or (program.subject_id if program else None)
        if lesson.individual_plan_id and program and lesson.individual_plan_id in program.plan_rank:
            return subject or program.subject_id, program.plan_rank[lesson.individual_plan_id]
        if lesson.plan_id and course and lesson.plan_id in course.plan_rank:
            return course.plan_rank[lesson.plan_id]
        if not lesson.lesson_number:
            return None
        if program and program.by_number:  # the program runs its own plan
            position = program.by_number.get(lesson.lesson_number)
            return (subject, position) if position else None
        if course and subject is not None and (subject, lesson.lesson_number) in course.by_number:
            return subject, course.by_number[(subject, lesson.lesson_number)]
        return None

    def layout(self, group_id: int, subject_id: int | None) -> Layout:
        key = (group_id, subject_id)
        if key not in self._layouts:
            self._load_groups([group_id])
            course_id, own = self._groups.get(group_id, (None, None))
            course = self._courses.get(course_id)
            curriculum = course.curriculum if course else None
            size = own or (curriculum.lessons_per_month if curriculum else None) or DEFAULT_LESSONS_PER_MONTH
            blocks = _curriculum_blocks(curriculum, own).get(subject_id, []) if subject_id else []
            freezes = self._freezes.get(group_id, {}).get(subject_id, [])
            self._layouts[key] = build_layout(size, blocks, freezes)
        return self._layouts[key]

    def of(self, lesson: Lesson | None) -> dict | None:
        """{"number", "month", "lesson", "per_month", "subject_id", "label", "labels"}
        — None when the curriculum gives no position (nothing is invented)."""
        place = self.position(lesson) if lesson is not None else None
        if place is None:
            return None
        subject_id, position = place
        month, number, per_month = self.layout(lesson.group_id, subject_id).place(position)
        return {
            "number": position,
            "month": month,
            "lesson": number,
            "per_month": per_month,
            "subject_id": subject_id,
            "label": label(month, number),
            "labels": {lang: label(month, number, lang) for lang in LABELS},
        }


# One resolver per request (NumberingMiddleware): payload builders call
# `of(lesson)` row by row and the curriculum is read once per group.
_current: ContextVar[Numbering | None] = ContextVar("lesson_numbering", default=None)


def resolver() -> Numbering:
    current = _current.get()
    return current if current is not None else Numbering()


def of(lesson: Lesson | None) -> dict | None:
    return resolver().of(lesson)


def lesson_numbering(lesson: Lesson | None) -> dict | None:
    return Numbering().of(lesson)


def prime(lessons) -> None:
    current = _current.get()
    if current is not None:
        current.prime(lessons)


def numbering_map(lessons) -> dict[int, dict | None]:
    lessons = [lesson for lesson in lessons if lesson is not None]
    current = resolver().prime(lessons)
    return {lesson.pk: current.of(lesson) for lesson in lessons}


def invalidate() -> None:
    current = _current.get()
    if current is not None:
        current.clear()


class NumberingMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        token = _current.set(Numbering())
        try:
            return self.get_response(request)
        finally:
            _current.reset(token)


# ---------------------------------------------------------------- changes


def locked_positions(group_ids, *, today: dt.date | None = None) -> dict[tuple[int, int | None], int]:
    """(group, subject) -> the last position that already took place (or is
    today): its «месяц · урок» may have been seen and must not move."""
    today = today or timezone.localdate()
    lessons = list(Lesson.objects.filter(group_id__in=set(group_ids)).exclude(status=Lesson.Status.CANCELLED)
                   .filter(Q(status=Lesson.Status.COMPLETED) | Q(date__lte=today)))
    resolver_ = Numbering().prime(lessons)
    out: dict[tuple[int, int | None], int] = {}
    for lesson in lessons:
        place = resolver_.position(lesson)
        if place is not None:
            key = (lesson.group_id, place[0])
            out[key] = max(out.get(key, 0), place[1])
    return out


def snapshot(group_ids, *, today: dt.date | None = None) -> dict[tuple[int, int | None], list[Segment]]:
    """Before a change: the months already started, per (group, subject), under
    the CURRENT settings."""
    resolver_ = Numbering()
    out = {}
    for (group_id, subject_id), position in locked_positions(group_ids, today=today).items():
        out[(group_id, subject_id)] = resolver_.layout(group_id, subject_id).months_up_to(position)
    return out


def freeze_history(before: dict[tuple[int, int | None], list[Segment]], *, user=None, reason: str = "") -> int:
    """After a change: keep the months in `before` (from snapshot()) as they
    were. Idempotent — ranges already frozen are skipped."""
    written = 0
    for (group_id, subject_id), segments in before.items():
        existing = {f.first_lesson for f in NumberingFreeze.objects.filter(group_id=group_id, subject_id=subject_id)}
        for segment in segments:
            if segment.first in existing or segment.last is None:
                continue
            NumberingFreeze.objects.create(
                group_id=group_id, subject_id=subject_id, first_lesson=segment.first, last_lesson=segment.last,
                first_month=segment.month, lessons_per_month=segment.size, created_by=user, reason=reason[:255],
            )
            written += 1
    return written


_preserving: ContextVar[bool] = ContextVar("numbering_preserving", default=False)


def begin(group_ids) -> dict:
    """Before a settings change: the months already started, under the current settings."""
    group_ids = list(group_ids)
    locked = locked_positions(group_ids)
    old = Numbering()
    return {"locked": locked, "layouts": {key: old.layout(*key) for key in locked}}


def finish(state: dict, *, user=None, reason: str = "") -> int:
    """After it: freeze what would otherwise move."""
    invalidate()
    new = Numbering()
    moved = {}
    for key, last in state["locked"].items():
        before, after = state["layouts"][key], new.layout(*key)
        if any(before.place(p)[:2] != after.place(p)[:2] for p in range(1, last + 1)):
            moved[key] = before.months_up_to(last)
    return freeze_history(moved, user=user, reason=reason) if moved else 0


@contextmanager
def preserving(group_ids, *, user=None, reason: str = "Изменены учебные месяцы"):
    """Wrap any change of numbering settings (lessons per month, study months):
    months already started keep their «месяц · урок». Nested uses do nothing."""
    if _preserving.get():
        yield
        return
    state = begin(group_ids)
    token = _preserving.set(True)
    try:
        yield
    finally:
        _preserving.reset(token)
    finish(state, user=user, reason=reason)


def groups_of_course(course_id: int) -> list[int]:
    return list(Group.objects.filter(course_id=course_id).values_list("pk", flat=True))
