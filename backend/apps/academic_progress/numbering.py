"""Monthly lesson numbering — «Месяц 2 · Урок 1».

Lessons keep their global sequence number (`Lesson.lesson_number`, one
sequence per GroupTeacher: a cancelled lesson keeps its number and its
make-up re-uses it, so the sequence never shifts). The educational month and
the lesson within it are DERIVED from that number, never stored:

    month  = (n - 1) // lessons_per_month + 1
    lesson = (n - 1) %  lessons_per_month + 1

`lessons_per_month` (12 or 20) is the group's own setting
(GroupLessonNumbering), else its program's (ProgramCurriculum), else 12.
Educational months are lesson counts, not calendar months.

Changing the setting never renumbers lessons that already took place:
freeze_history() first fixes, for every sequence of the affected groups, the
whole educational months up to the last lesson held (or dated today or
earlier) with the OLD size (NumberingFreeze). The new size applies from the
next educational month on. Future-only sequences simply follow the setting.
"""
from __future__ import annotations

import datetime as dt
from contextvars import ContextVar
from dataclasses import dataclass, field

from django.db.models import Max, Q
from django.utils import timezone

from apps.academy.models import Group, GroupTeacher, Lesson

from .models import DEFAULT_LESSONS_PER_MONTH, GroupLessonNumbering, NumberingFreeze, ProgramCurriculum

LABELS = {
    "ru": "Месяц {month} · Урок {lesson}",
    "ky": "{month}-ай · {lesson}-сабак",
}


def split(number: int, per_month: int, *, first_lesson: int = 1, first_month: int = 1) -> tuple[int, int]:
    """(month, lesson in month) of `number` in a run of `per_month`-lesson months
    starting at `first_lesson` / `first_month`."""
    offset = number - first_lesson
    return first_month + offset // per_month, offset % per_month + 1


def label(month: int, lesson: int, lang: str = "ru") -> str:
    return LABELS.get(lang, LABELS["ru"]).format(month=month, lesson=lesson)


@dataclass
class Layout:
    """How one lesson sequence is split into educational months."""

    per_month: int
    freezes: list[NumberingFreeze] = field(default_factory=list)

    @property
    def tail(self) -> tuple[int, int]:
        """(first lesson, first month) of the part that follows the current setting."""
        if not self.freezes:
            return 1, 1
        last = self.freezes[-1]
        months = (last.last_lesson - last.first_lesson + 1 + last.lessons_per_month - 1) // last.lessons_per_month
        return last.last_lesson + 1, last.first_month + months

    def place(self, number: int) -> tuple[int, int, int]:
        """(month, lesson, lessons per month) of a lesson number."""
        for freeze in self.freezes:
            if freeze.first_lesson <= number <= freeze.last_lesson:
                month, lesson = split(number, freeze.lessons_per_month,
                                      first_lesson=freeze.first_lesson, first_month=freeze.first_month)
                return month, lesson, freeze.lessons_per_month
        first_lesson, first_month = self.tail
        if number < first_lesson:  # a gap before the frozen ranges: plain formula
            month, lesson = split(number, self.per_month)
        else:
            month, lesson = split(number, self.per_month, first_lesson=first_lesson, first_month=first_month)
        return month, lesson, self.per_month


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
    """Batch resolver: a few queries for any number of lessons. Use one per
    request / payload (`numbering.of(lesson)`), priming it with the lessons
    first when there are many."""

    def __init__(self):
        self._sizes: dict[int, int] = {}
        self._freezes: dict[int, list[NumberingFreeze]] = {}

    def prime(self, lessons) -> Numbering:
        lessons = [lesson for lesson in lessons if lesson is not None]
        groups = {lesson.group_id for lesson in lessons if lesson.group_id} - set(self._sizes)
        self._sizes.update(effective_sizes(groups))
        sequences = {lesson.group_teacher_id for lesson in lessons if lesson.group_teacher_id} - set(self._freezes)
        if sequences:
            loaded: dict[int, list[NumberingFreeze]] = {gt: [] for gt in sequences}
            for freeze in NumberingFreeze.objects.filter(group_teacher_id__in=sequences).order_by("first_lesson"):
                loaded[freeze.group_teacher_id].append(freeze)
            self._freezes.update(loaded)
        return self

    def size(self, group_id: int) -> int:
        if group_id not in self._sizes:
            self._sizes.update(effective_sizes([group_id]))
        return self._sizes.get(group_id, DEFAULT_LESSONS_PER_MONTH)

    def layout(self, group_id: int, group_teacher_id: int | None) -> Layout:
        if group_teacher_id and group_teacher_id not in self._freezes:
            self._freezes[group_teacher_id] = list(
                NumberingFreeze.objects.filter(group_teacher_id=group_teacher_id).order_by("first_lesson"))
        return Layout(self.size(group_id), self._freezes.get(group_teacher_id, []) if group_teacher_id else [])

    def of(self, lesson: Lesson | None) -> dict | None:
        """{"number", "month", "lesson", "per_month", "label"} — None without a number."""
        if lesson is None or not lesson.lesson_number or not lesson.group_id:
            return None
        month, number_in_month, per_month = self.layout(lesson.group_id, lesson.group_teacher_id).place(lesson.lesson_number)
        return {
            "number": lesson.lesson_number,
            "month": month,
            "lesson": number_in_month,
            "per_month": per_month,
            "label": label(month, number_in_month),
        }


# One resolver per request (NumberingMiddleware): every payload builder can
# call `of(lesson)` row by row and the settings are read once per group.
_current: ContextVar[Numbering | None] = ContextVar("lesson_numbering", default=None)


def resolver() -> Numbering:
    current = _current.get()
    return current if current is not None else Numbering()


def of(lesson: Lesson | None) -> dict | None:
    """«Месяц · Урок» of one lesson (cached per request)."""
    return resolver().of(lesson)


def prime(lessons) -> None:
    """Load the settings of many lessons at once (no-op outside a request)."""
    current = _current.get()
    if current is not None:
        current.prime(lessons)


def numbering_map(lessons) -> dict[int, dict | None]:
    lessons = [lesson for lesson in lessons if lesson is not None]
    current = resolver().prime(lessons)
    return {lesson.pk: current.of(lesson) for lesson in lessons}


def invalidate() -> None:
    """Settings changed during this request: forget what was read."""
    current = _current.get()
    if current is not None:
        current._sizes.clear()
        current._freezes.clear()


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


def _locked_number(group_teacher_id: int, today: dt.date) -> int | None:
    """The last lesson of a sequence that already took place (or is today):
    its «Месяц · Урок» may have been seen and must not move."""
    return (Lesson.objects.filter(group_teacher_id=group_teacher_id)
            .exclude(status=Lesson.Status.CANCELLED)
            .filter(Q(status=Lesson.Status.COMPLETED) | Q(date__lte=today))
            .aggregate(n=Max("lesson_number"))["n"])


def freeze_history(old_sizes: dict[int, int], *, user=None, today: dt.date | None = None, reason: str = "") -> int:
    """Before a group's lessons per month changes from `old_sizes[group]`:
    fix the educational months already started with the old size. Returns
    the number of freezes written. Idempotent."""
    today = today or timezone.localdate()
    written = 0
    for group_id, old in old_sizes.items():
        for gt_id in GroupTeacher.objects.filter(group_id=group_id).values_list("pk", flat=True):
            locked = _locked_number(gt_id, today)
            if not locked:
                continue
            layout = Layout(old, list(NumberingFreeze.objects.filter(group_teacher_id=gt_id).order_by("first_lesson")))
            first_lesson, first_month = layout.tail
            if locked < first_lesson:
                continue  # already fixed by an earlier change
            months = (locked - first_lesson) // old + 1  # the started month is kept whole
            NumberingFreeze.objects.create(
                group_teacher_id=gt_id, first_lesson=first_lesson, last_lesson=first_lesson + months * old - 1,
                first_month=first_month, lessons_per_month=old, created_by=user, reason=reason[:255],
            )
            written += 1
    return written


def groups_of_course(course_id: int) -> list[int]:
    return list(Group.objects.filter(course_id=course_id).values_list("pk", flat=True))
