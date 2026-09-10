"""Keeps a Group's own primary slot (teacher/room/start_time/end_time/
days_of_week) mirrored into GroupSchedule, so GroupSchedule stays the single
complete source of truth for lesson generation and conflict-checking — a
Group created (or edited) the old, simple way never needs a second,
separate code path.

Called from `signals.py` on every Group save. Only ever touches the rows it
owns (`subject__isnull=True`, the marker for an auto-mirrored slot) — an
admin's own explicitly-added GroupSchedule rows (`subject` set) are never
read or written here.

Every row this function creates/updates/deletes is tagged
``_defer_schedule_sync = True`` first, so GroupSchedule's own post_save/
post_delete signals (see signals.py) don't each trigger their own
`generate_lessons_for_group` call mid-loop, against a still-partially-synced
schedule — the caller (signals.py) generates once, after the whole sync is
done.
"""
from __future__ import annotations

from .. import constants


def sync_legacy_group_schedule(group) -> None:
    from ..models import Group, GroupSchedule

    if group.teacher_id and group.start_time and group.end_time and group.days_of_week:
        managed_days = {day for day in group.days_of_week if day in constants.WEEKDAY_CODES}
    else:
        managed_days = set()

    existing = {slot.day_of_week: slot for slot in GroupSchedule.objects.filter(group=group, subject__isnull=True)}

    for day, slot in existing.items():
        if day not in managed_days:
            slot._defer_schedule_sync = True
            slot.delete()

    is_active = group.status != Group.Status.CANCELLED
    for day in managed_days:
        slot = existing.get(day)
        if slot is None:
            slot = GroupSchedule(
                group=group,
                teacher=group.teacher,
                subject=None,
                day_of_week=day,
                start_time=group.start_time,
                end_time=group.end_time,
                room=group.room,
                is_active=is_active,
            )
            slot._defer_schedule_sync = True
            slot.save()
            continue

        changed_fields = {
            "teacher_id": group.teacher_id,
            "start_time": group.start_time,
            "end_time": group.end_time,
            "room_id": group.room_id,
            "is_active": is_active,
        }
        dirty = [field for field, value in changed_fields.items() if getattr(slot, field) != value]
        if dirty:
            for field, value in changed_fields.items():
                setattr(slot, field, value)
            slot._defer_schedule_sync = True
            slot.save(update_fields=[*changed_fields.keys(), "updated_at"])
