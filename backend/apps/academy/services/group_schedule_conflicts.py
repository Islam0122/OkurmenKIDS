"""Teacher/Room double-booking checks for GroupSchedule — the only source of
truth for a Group's schedule.

Two slots conflict when they'd put the same Teacher (or the same Room) in
two places at once: same weekday, overlapping time range, in an
active/non-cancelled group. Adjacent slots never conflict — 08:00-09:00 and
09:00-10:00 share a boundary, not a room/teacher, hence the strict `<`/`>`
comparison.
"""
from __future__ import annotations


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
