"""Historical student roster: who was enrolled, in which group and with
which status *as of a given date*.

Why this exists (bug «сентябрь показывает данные октября»): every report
used to count students with a live query — ``Student.objects.filter(
status=ACTIVE)`` / ``group.students.filter(is_active=True)`` — i.e. the
state of the database *today*. The period filter moved lessons, attendance
and homework to the selected month, but the student counts (and the KPI
retention built on them) stayed on the current roster, so September showed
October's 110 students instead of its own 97.

The Student row only holds the current status/group, but every status or
group change goes through services.student_status /
services.student_enrollment, which append a ``StudentStatusEvent`` with the
date, the status *before* the change (``previous_status``) and the group
(``group``, plus ``from_group`` for a transfer). That ledger is enough to
reconstruct the roster on any past date:

* a student exists on ``D`` once they had joined by then — the earliest of
  ``enrollment_date``, the record's ``created_at`` and their first lesson
  with an attendance mark or a homework result (a student typed in later
  but already studying still counts);
* status/group on ``D`` = the state after their last event dated ``<= D``;
  with no such event, the state *before* their first later event
  (``previous_status``; for a transfer the ``from_group``); with no events
  at all, the current status/group.

For a period the roster is taken on its last day, capped at today — «the
students of September» are the ones enrolled on 30 September.
"""
from __future__ import annotations

import dataclasses
import datetime as dt
from collections import defaultdict
from collections.abc import Iterable

from django.db.models import Min, Q
from django.utils import timezone

from apps.academy.models import Attendance, HomeworkResult, Student, StudentStatusEvent

_STATUS_AFTER_EVENT = {
    StudentStatusEvent.EventType.DEACTIVATED: Student.Status.WITHDRAWN,
    StudentStatusEvent.EventType.REACTIVATED: Student.Status.ACTIVE,
    StudentStatusEvent.EventType.COMPLETED: Student.Status.COMPLETED,
    StudentStatusEvent.EventType.PAUSED: Student.Status.PAUSED,
    StudentStatusEvent.EventType.CONTINUED: Student.Status.ACTIVE,
    # A transfer changes the group only, never the status.
}


@dataclasses.dataclass(frozen=True)
class RosterEntry:
    student_id: int
    group_id: int | None
    status: str
    created_on: dt.date

    @property
    def is_active(self) -> bool:
        return self.status == Student.Status.ACTIVE


def roster_date(end: dt.date, today: dt.date | None = None) -> dt.date:
    """The day a period's roster is read on: its last day, never the future."""
    today = today or timezone.localdate()
    return min(end, today)


def _status_after(event: dict) -> str:
    status = _STATUS_AFTER_EVENT.get(event["event_type"])
    if status is not None:
        return status
    return event["previous_status"] or Student.Status.ACTIVE


@dataclasses.dataclass
class _StudentHistory:
    student_id: int
    joined_on: dt.date
    created_on: dt.date
    status: str
    group_id: int | None
    events: list[dict]

    def on(self, day: dt.date) -> tuple[str, int | None] | None:
        """``(status, group_id)`` on ``day``, or None if not enrolled yet."""
        if self.joined_on > day:
            return None
        past = [event for event in self.events if event["event_date"] <= day]
        if past:
            last = past[-1]
            return _status_after(last), last["group_id"] or self.group_id
        if self.events:
            first = self.events[0]
            status = first["previous_status"] or Student.Status.ACTIVE
            if first["event_type"] == StudentStatusEvent.EventType.TRANSFERRED:
                return status, first["from_group_id"]
            return status, first["group_id"] or self.group_id
        return self.status, self.group_id


class RosterHistory:
    """The status/group history of the candidate students, loaded once (four
    queries), so the roster of any number of days costs no further queries
    — e.g. one roster per lesson date in the Control module."""

    def __init__(self, group_ids: Iterable[int] | None = None):
        self.group_ids = set(group_ids) if group_ids is not None else None
        self._students = self._load()

    def _load(self) -> list[_StudentHistory]:
        wanted = self.group_ids
        students_qs = Student.objects.order_by()
        events_qs = StudentStatusEvent.objects.all()
        attendance_qs = Attendance.objects.order_by()
        homework_qs = HomeworkResult.objects.order_by()
        if wanted is not None:
            if not wanted:
                return []
            # Candidates only: students in those groups today, or ever moved
            # in/out of one of them (their events name the group).
            moved = StudentStatusEvent.objects.filter(
                Q(group_id__in=wanted) | Q(from_group_id__in=wanted)
            ).values("student_id")
            candidates = Student.objects.filter(Q(group_id__in=wanted) | Q(id__in=moved))
            students_qs = students_qs.filter(id__in=candidates.values("id"))
            events_qs = events_qs.filter(student__in=candidates.values("id"))
            attendance_qs = attendance_qs.filter(student__in=candidates.values("id"))
            homework_qs = homework_qs.filter(student__in=candidates.values("id"))

        students = list(students_qs.values("id", "group_id", "status", "is_active", "enrollment_date", "created_at"))
        if not students:
            return []

        first_lesson = dict(
            attendance_qs.values("student_id").annotate(first=Min("lesson__date")).values_list("student_id", "first")
        )
        for student_id, first in (
            homework_qs.values("student_id").annotate(first=Min("homework__lesson__date"))
            .values_list("student_id", "first")
        ):
            if first and (student_id not in first_lesson or first < first_lesson[student_id]):
                first_lesson[student_id] = first

        events_by_student: dict[int, list[dict]] = defaultdict(list)
        for event in (
            events_qs.order_by("student_id", "event_date", "created_at", "id")
            .values("student_id", "event_type", "event_date", "previous_status", "group_id", "from_group_id")
        ):
            events_by_student[event["student_id"]].append(event)

        history = []
        today = timezone.localdate()
        for row in students:
            created_on = timezone.localdate(row["created_at"]) if row["created_at"] else today
            joined = [created_on]
            if row["enrollment_date"]:
                joined.append(row["enrollment_date"])
            if first_lesson.get(row["id"]):
                joined.append(first_lesson[row["id"]])
            status = row["status"]
            if status == Student.Status.ACTIVE and not row["is_active"]:
                # `is_active` is derived from `status`; a row where the two
                # disagree (legacy/direct edits) is not counted as active.
                status = Student.Status.WITHDRAWN
            history.append(
                _StudentHistory(
                    row["id"], min(joined), created_on, status, row["group_id"],
                    events_by_student.get(row["id"], []),
                )
            )
        return history

    def on(self, day: dt.date) -> dict[int, RosterEntry]:
        """``{student_id: RosterEntry}`` of every student enrolled on ``day``
        (any status), with the group and status they had *on that day*,
        narrowed to the history's groups (as of ``day``, not today)."""
        roster: dict[int, RosterEntry] = {}
        for student in self._students:
            state = student.on(day)
            if state is None:
                continue  # not a student of the academy yet on that day
            status, group_id = state
            if self.group_ids is not None and group_id not in self.group_ids:
                continue
            roster[student.student_id] = RosterEntry(student.student_id, group_id, status, student.created_on)
        return roster


def roster_on(as_of: dt.date, *, group_ids: Iterable[int] | None = None) -> dict[int, RosterEntry]:
    """``{student_id: RosterEntry}`` of every student enrolled on ``as_of``
    (any status), with the group and status they had *on that day*.

    ``group_ids`` narrows the result to students who were in one of those
    groups on ``as_of`` (not the groups they are in today)."""
    return RosterHistory(group_ids).on(as_of)


def counts_by_group(roster: dict[int, RosterEntry], start: dt.date, end: dt.date) -> dict[int | None, dict]:
    """Per group: total/active/paused students on the roster day, plus
    ``new`` — records created inside ``start..end`` (the same «new student»
    definition every report uses)."""
    counts: dict[int | None, dict] = defaultdict(lambda: {"total": 0, "active": 0, "paused": 0, "new": 0})
    for entry in roster.values():
        row = counts[entry.group_id]
        row["total"] += 1
        row["active"] += entry.status == Student.Status.ACTIVE
        row["paused"] += entry.status == Student.Status.PAUSED
        row["new"] += start <= entry.created_on <= end
    return dict(counts)


def totals(roster: dict[int, RosterEntry], start: dt.date, end: dt.date) -> dict:
    """The same four figures as ``counts_by_group``, academy-wide."""
    result = {"total": 0, "active": 0, "paused": 0, "new": 0}
    for row in counts_by_group(roster, start, end).values():
        for key in result:
            result[key] += row[key]
    return result
