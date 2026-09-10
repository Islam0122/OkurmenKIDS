"""Room double-booking checks for a Group's recurring weekly schedule.

Two Groups conflict when they'd use the same Room on the same weekday, with
overlapping time ranges, during an overlapping stretch of the calendar (a
Group with no `end_date` is treated as open-ended). This runs at Group
save-time — see `models.Group.clean` and `serializers.GroupSerializer.validate`
— so a schedule that would double-book a Room is rejected outright, before
any Lesson is ever generated from it. A cancelled Group never blocks a room:
its slot is free again.
"""
from __future__ import annotations

import datetime as dt

from ..constants import WEEKDAY_CODES


def find_room_schedule_conflict(
    *,
    room,
    days_of_week,
    start_time,
    end_time,
    start_date,
    end_date=None,
    exclude_group_id=None,
):
    """Return the first other Group whose weekly schedule clashes on `room`, or None.

    All of `room`/`days_of_week`/`start_time`/`end_time`/`start_date` must be
    present to check anything — a Group missing one of these can't have
    lessons generated yet either, so there's nothing to conflict over.
    """
    if not room or not days_of_week or not start_time or not end_time or not start_date:
        return None

    from ..models import Group  # local import: services -> models only, never the reverse at module load

    days = {day for day in days_of_week if day in WEEKDAY_CODES}
    if not days:
        return None

    candidates = Group.objects.filter(room=room).exclude(status=Group.Status.CANCELLED)
    if exclude_group_id is not None:
        candidates = candidates.exclude(pk=exclude_group_id)

    this_end = end_date or dt.date.max

    for other in candidates:
        other_days = {day for day in (other.days_of_week or []) if day in WEEKDAY_CODES}
        if not days & other_days:
            continue
        if not (start_time < other.end_time and other.start_time < end_time):
            continue
        other_end = other.end_date or dt.date.max
        if start_date <= other_end and other.start_date <= this_end:
            return other

    return None
