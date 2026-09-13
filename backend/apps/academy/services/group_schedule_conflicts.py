"""Teacher/Room/Group double-booking checks for GroupSchedule — the only
source of truth for a Group's schedule.

Two slots conflict when they'd put the same Teacher, the same Room, or the
same Group in two places at once: same weekday, overlapping time range, in
an active/non-cancelled group. Adjacent slots never conflict —
08:00-09:00 and 09:00-10:00 share a boundary, not a room/teacher/group,
hence the strict `<`/`>` comparison.

Also home to the shared overlap/grouping primitives (`time_ranges_overlap`,
`overlapping_groups`) used both by the Schedule admin page's live conflict
report (admin_views.py) and by the read-only `audit_schedule_conflicts`
management command — one definition of "what counts as an overlap" and "how
overlapping items are grouped", never duplicated.
"""
from __future__ import annotations

from typing import Protocol


class _TimeRanged(Protocol):
    start_time: object
    end_time: object


def time_ranges_overlap(a: _TimeRanged, b: _TimeRanged) -> bool:
    return a.start_time < b.end_time and b.start_time < a.end_time


def overlapping_groups(items: list) -> list[list]:
    """Partition `items` (already known to share one resource + date/day)
    into connected components of mutually-or-transitively overlapping
    items, sorted by `start_time`.

    Three items all at 08:00-09:00 produce *one* group of 3, never the
    three pairwise combinations a naive nested loop would emit. A chain (A
    overlaps B, B overlaps C, A does not directly overlap C) is still one
    group: the shared resource genuinely can't do any two of the three at
    once, so all three belong to the same reported problem. Singletons
    (nothing overlaps them) are omitted — only genuine conflicts are
    returned.
    """
    items = sorted(items, key=lambda item: item.start_time)
    n = len(items)
    visited = [False] * n
    groups: list[list] = []

    for i in range(n):
        if visited[i]:
            continue
        visited[i] = True
        stack = [i]
        component = []
        while stack:
            idx = stack.pop()
            component.append(items[idx])
            for j in range(n):
                if not visited[j] and time_ranges_overlap(items[idx], items[j]):
                    visited[j] = True
                    stack.append(j)
        if len(component) >= 2:
            groups.append(component)

    return groups


def _find_slot_conflict(*, field: str, value, day_of_week, start_time, end_time, exclude_schedule_id=None):
    from ..models import Group, GroupSchedule

    if not value or not day_of_week or not start_time or not end_time:
        return None

    candidates = (
        GroupSchedule.objects.filter(**{field: value}, day_of_week=day_of_week, is_active=True)
        .exclude(group__status=Group.Status.CANCELLED)
        .select_related("group")
    )
    if exclude_schedule_id is not None:
        candidates = candidates.exclude(pk=exclude_schedule_id)

    for other in candidates:
        if start_time < other.end_time and other.start_time < end_time:
            return other
    return None


def find_schedule_teacher_conflict(*, teacher, day_of_week, start_time, end_time, exclude_schedule_id=None):
    """Return the first other active GroupSchedule slot clashing on `teacher`, or None."""
    return _find_slot_conflict(
        field="teacher",
        value=teacher,
        day_of_week=day_of_week,
        start_time=start_time,
        end_time=end_time,
        exclude_schedule_id=exclude_schedule_id,
    )


def find_schedule_room_conflict(*, room, day_of_week, start_time, end_time, exclude_schedule_id=None):
    """Return the first other active GroupSchedule slot clashing on `room`, or None."""
    return _find_slot_conflict(
        field="room",
        value=room,
        day_of_week=day_of_week,
        start_time=start_time,
        end_time=end_time,
        exclude_schedule_id=exclude_schedule_id,
    )


def find_schedule_group_conflict(*, group, day_of_week, start_time, end_time, exclude_schedule_id=None):
    """Return the first other active GroupSchedule slot clashing on `group`, or None.

    A Group cannot physically attend two different programs' lessons at the
    same time — even when the teacher and room are both different (e.g.
    CyberSecurity and English both scheduled Monday 08:00-09:00 for the same
    group). This is a distinct, mandatory check alongside teacher/room
    conflicts, never a substitute for them.
    """
    return _find_slot_conflict(
        field="group",
        value=group,
        day_of_week=day_of_week,
        start_time=start_time,
        end_time=end_time,
        exclude_schedule_id=exclude_schedule_id,
    )
