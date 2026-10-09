"""Who was where on a given day — rebuilt from the StudentStatusEvent ledger,
so a September report opened in October still describes September.

`Student.status` / `Student.group` are only today's state. The ledger keeps
every change with its `event_date`: deactivation / pause / completion (the
group they left from), reactivation / return from pause / transfer (the
group they went to; a transfer also keeps `from_group`). Replaying the
events up to a day gives each student's status and group on that day. A
student with no event before the day was active there since enrolling; a
student with no events at all keeps today's status (nothing else is known).
Two queries, no per-student lookups.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from django.db.models import Q

from apps.academy.models import Group, Student, StudentStatusEvent

E = StudentStatusEvent.EventType
STATUS_AFTER = {
    E.DEACTIVATED: Student.Status.WITHDRAWN,
    E.PAUSED: Student.Status.PAUSED,
    E.COMPLETED: Student.Status.COMPLETED,
    E.REACTIVATED: Student.Status.ACTIVE,
    E.CONTINUED: Student.Status.ACTIVE,
}
# Events whose `group` is the one the student moved into (the rest: the group left from).
JOINS_GROUP = (E.REACTIVATED, E.CONTINUED, E.TRANSFERRED)


@dataclass
class StudentOn:
    student: Student
    status: str
    group_id: int | None


def enrolled_by(day: dt.date) -> Q:
    return Q(enrollment_date__lte=day) | Q(enrollment_date__isnull=True, created_at__date__lte=day)


def roster_on(day: dt.date) -> list[StudentOn]:
    """Every student enrolled by `day`, with their status and group on it."""
    students = list(Student.objects.filter(enrolled_by(day)).select_related("group"))
    events: dict[int, list[dict]] = {}
    for event in (
        StudentStatusEvent.objects.filter(student__in=students)
        .order_by("student_id", "event_date", "created_at", "pk")
        .values("student_id", "event_type", "event_date", "group_id", "from_group_id")
    ):
        events.setdefault(event["student_id"], []).append(event)

    roster = []
    for student in students:
        history = events.get(student.pk, [])
        before = [e for e in history if e["event_date"] <= day]
        after = [e for e in history if e["event_date"] > day]
        # No ledger at all (a status set before the ledger existed, or by an
        # import): today's status is all that is known.
        status = Student.Status.ACTIVE if history else student.status
        for event in before:
            status = STATUS_AFTER.get(event["event_type"], status)
        if before:
            # Every event names the group of that moment: the one joined, or the one left.
            group_id = before[-1]["group_id"]
        elif after and after[0]["event_type"] == E.TRANSFERRED:
            group_id = after[0]["from_group_id"]  # still in the group they later moved out of
        elif after and after[0]["event_type"] not in JOINS_GROUP:
            group_id = after[0]["group_id"]  # the group they later left from
        else:
            group_id = student.group_id
        roster.append(StudentOn(student=student, status=status, group_id=group_id))
    return roster


def groups_by_id(roster: list[StudentOn]) -> dict[int, Group]:
    ids = {r.group_id for r in roster if r.group_id}
    return {g.pk: g for g in Group.objects.filter(pk__in=ids)}


def started_by(group: Group, day: dt.date, month_start: dt.date) -> bool:
    """A group that had started by `day` and had not finished before the month began."""
    begun = group.start_date <= day if group.start_date else group.created_at.date() <= day
    return begun and not (group.end_date and group.end_date < month_start)
