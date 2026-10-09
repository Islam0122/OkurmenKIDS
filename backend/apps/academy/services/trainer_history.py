"""Trainer assignment history and the one rule «who is responsible for a
lesson» used by every KPI / report / analytics figure.

Why it exists: a Teaching Program (GroupTeacher) is edited in place when its
trainer changes (services.program_editing) — its slots, plan and lesson
numbering stay with the program. Reading «the program's trainer» therefore
always gives today's trainer, and any figure computed from it rewrote the
past: trainer A's September vanished from A's profile (A had no *current*
assignment in the group any more) and lessons without an explicit trainer
moved to trainer B.

The rule now, in priority order:

1. `Lesson.teacher` — the trainer stored on the lesson itself. Set by the
   lesson generator from the slot, kept on past lessons when the program
   changes hands (only open future lessons move to the new trainer), and
   filled from the program on every new lesson (Lesson.save()). This is the
   historical source of truth.
2. For a lesson without one (legacy data only) — the TrainerAssignment of
   its program that covers the lesson's date.
3. Otherwise nobody: the lesson counts for its group, subject and the
   academy, but never for a trainer (no guessing — see the 0022 migration
   and `manage.py audit_trainer_history`).

Groups of a trainer for a period are the groups the trainer was assigned
to at any time inside it, or actually taught in it — never «the groups the
trainer runs today».
"""
from __future__ import annotations

import contextlib
import contextvars
import datetime as dt

from django.db import models
from django.db.models import Exists, OuterRef, Q, Subquery
from django.db.models.functions import Coalesce
from django.utils import timezone

_actor: contextvars.ContextVar = contextvars.ContextVar("trainer_assignment_actor", default=None)
_request: contextvars.ContextVar = contextvars.ContextVar("trainer_assignment_request", default=None)


@contextlib.contextmanager
def acting_user(user):
    """Who is changing assignments inside this block (recorded as
    TrainerAssignment.changed_by)."""
    token = _actor.set(user if getattr(user, "pk", None) else None)
    try:
        yield
    finally:
        _actor.reset(token)


class ActorMiddleware:
    """Remembers the current request, so an assignment change made anywhere
    while serving it (admin, API, workspace) records who made it. The user
    is read when the change happens — after DRF has authenticated the JWT."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        token = _request.set(request)
        try:
            return self.get_response(request)
        finally:
            _request.reset(token)


def _current_user():
    user = _actor.get()
    if user is not None:
        return user
    request = _request.get()
    user = getattr(request, "user", None) if request is not None else None
    return user if getattr(user, "is_authenticated", False) else None


def first_start_date(program, today: dt.date) -> dt.date:
    """A program's first assignment covers it from the group's start — every
    lesson of the program is this trainer's until someone else takes over."""
    group_start = getattr(program.group, "start_date", None)
    if isinstance(group_start, str):  # an instance created with a string date, not reloaded
        try:
            group_start = dt.date.fromisoformat(group_start[:10])
        except ValueError:
            group_start = None
    if isinstance(group_start, dt.datetime):
        group_start = group_start.date()
    return min(today, group_start) if group_start else today


def sync_assignment(program, *, today: dt.date | None = None, user=None):
    """Bring the program's history in line with the program as saved: close
    the open assignment if the trainer changed or the program was switched
    off; open one for the current trainer if the program is active. Never
    deletes or rewrites a closed assignment."""
    from ..models import TrainerAssignment

    today = today or timezone.localdate()
    user = user or _current_user()
    open_row = TrainerAssignment.objects.filter(program=program, end_date__isnull=True).first()
    if open_row is not None and program.is_active and open_row.teacher_id == program.teacher_id:
        if open_row.subject_id != program.subject_id:
            TrainerAssignment.objects.filter(pk=open_row.pk).update(subject_id=program.subject_id)
        return open_row
    if open_row is not None:
        TrainerAssignment.objects.filter(pk=open_row.pk).update(
            end_date=max(today, open_row.start_date), closed_at=timezone.now(),
        )
    if not program.is_active:
        return None
    has_history = open_row is not None or TrainerAssignment.objects.filter(program=program).exists()
    start = today if has_history else first_start_date(program, today)
    return TrainerAssignment.objects.create(
        program=program, group_id=program.group_id, teacher_id=program.teacher_id, subject_id=program.subject_id,
        start_date=start, changed_by=user,
    )


# ---------------------------------------------------------------------------
# Query building blocks
# ---------------------------------------------------------------------------

def _covering(prefix: str = ""):
    """Assignments of the lesson's program that cover the lesson's date."""
    from ..models import TrainerAssignment

    date = OuterRef(f"{prefix}date")
    return TrainerAssignment.objects.filter(
        program_id=OuterRef(f"{prefix}group_teacher_id"), start_date__lte=date,
    ).filter(Q(end_date__isnull=True) | Q(end_date__gt=date))


def effective_teacher(prefix: str = ""):
    """The responsible trainer of a lesson reached via `prefix` («»,
    «lesson__», «homework__lesson__»), as a DB expression: its own
    `teacher`, else the program's assignment on the lesson's date."""
    historical = Subquery(_covering(prefix).order_by("-start_date", "-id").values("teacher_id")[:1])
    return Coalesce(f"{prefix}teacher_id", historical, output_field=models.IntegerField())


def taught_by_q(teacher_id, prefix: str = "") -> Q:
    """Lessons (via `prefix`) `teacher_id` is responsible for."""
    return Q(**{f"{prefix}teacher_id": teacher_id}) | (
        Q(**{f"{prefix}teacher__isnull": True}) & Exists(_covering(prefix).filter(teacher_id=teacher_id))
    )


def taught_by_any_q(teacher_ids, prefix: str = "") -> Q:
    return Q(**{f"{prefix}teacher_id__in": teacher_ids}) | (
        Q(**{f"{prefix}teacher__isnull": True}) & Exists(_covering(prefix).filter(teacher_id__in=teacher_ids))
    )


def assignments_overlapping(start: dt.date, end: dt.date):
    """Assignments in force on at least one day of [start, end] (inclusive)."""
    from ..models import TrainerAssignment

    return TrainerAssignment.objects.filter(start_date__lte=end).filter(
        Q(end_date__isnull=True) | Q(end_date__gt=start)
    ).exclude(end_date=models.F("start_date"))


def teacher_group_ids_q(teacher_id, start: dt.date, end: dt.date) -> Q:
    """Groups `teacher_id` was responsible for in [start, end]: assigned at
    some point in it, or gave a lesson in it."""
    from ..models import Lesson

    assigned = assignments_overlapping(start, end).filter(teacher_id=teacher_id).values("group_id")
    taught = Lesson.objects.filter(date__gte=start, date__lte=end).filter(taught_by_q(teacher_id)).values("group_id")
    return Q(id__in=assigned) | Q(id__in=taught)


def group_teacher_ids_q(start: dt.date, end: dt.date, *, group_id=None, course_id=None) -> Q:
    """Trainers responsible for the group / course's groups in [start, end]."""
    from ..models import Lesson

    assigned = assignments_overlapping(start, end)
    lessons = Lesson.objects.filter(date__gte=start, date__lte=end)
    if group_id is not None:
        assigned, lessons = assigned.filter(group_id=group_id), lessons.filter(group_id=group_id)
    if course_id is not None:
        assigned, lessons = assigned.filter(group__course_id=course_id), lessons.filter(group__course_id=course_id)
    taught = lessons.annotate(_t=effective_teacher()).filter(_t__isnull=False).values("_t")
    return Q(id__in=assigned.values("teacher_id")) | Q(id__in=taught)


def teacher_at(program_id: int, on: dt.date):
    """The trainer of the program on `on` per the history (or None)."""
    from ..models import TrainerAssignment

    row = (
        TrainerAssignment.objects.filter(program_id=program_id, start_date__lte=on)
        .filter(Q(end_date__isnull=True) | Q(end_date__gt=on))
        .select_related("teacher__user").order_by("-start_date", "-id").first()
    )
    return row.teacher if row else None
