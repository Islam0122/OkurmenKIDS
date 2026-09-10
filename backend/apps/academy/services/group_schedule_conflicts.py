"""Teacher/Room double-booking checks for GroupSchedule and for a Group's own
primary slot.

Two slots conflict when they'd put the same Teacher (or the same Room) in
two places at once: same weekday, overlapping time range, in an
active/non-cancelled group. Adjacent slots never conflict — 08:00-09:00 and
09:00-10:00 share a boundary, not a room/teacher, hence the strict `<`/`>`
comparison (same convention as `services.room_conflicts`, which this module
complements rather than replaces: that one checks a Group's own recurring
fields against other Groups', these check GroupSchedule rows against each
other, plus a Group-vs-Group teacher check mirroring the existing
Group-vs-Group room check).
"""
from __future__ import annotations

import datetime as dt

from .. import constants


def find_group_teacher_conflict(
    *,
    teacher,
    days_of_week,
    start_time,
    end_time,
    start_date,
    end_date=None,
    exclude_group_id=None,
):
    """Return the first other Group whose weekly schedule clashes on `teacher`, or None.

    Mirrors `services.room_conflicts.find_room_schedule_conflict` exactly,
    keyed on Teacher instead of Room — used by `Group.clean()` /
    `GroupSerializer` to reject a Group whose own primary slot would
    double-book a teacher already teaching another Group at that time.
    """
    if not teacher or not days_of_week or not start_time or not end_time or not start_date:
        return None

    from ..models import Group  # local import: services -> models only, never the reverse at module load

    days = {day for day in days_of_week if day in constants.WEEKDAY_CODES}
    if not days:
        return None

    candidates = Group.objects.filter(teacher=teacher).exclude(status=Group.Status.CANCELLED)
    if exclude_group_id is not None:
        candidates = candidates.exclude(pk=exclude_group_id)

    this_end = end_date or dt.date.max

    for other in candidates:
        other_days = {day for day in (other.days_of_week or []) if day in constants.WEEKDAY_CODES}
        if not days & other_days:
            continue
        if not (start_time < other.end_time and other.start_time < end_time):
            continue
        other_end = other.end_date or dt.date.max
        if start_date <= other_end and other.start_date <= this_end:
            return other

    return None


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
