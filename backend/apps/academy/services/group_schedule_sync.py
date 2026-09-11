"""One-off helper: turns a Group's legacy teacher/room/start_time/end_time/
days_of_week fields into ordinary GroupSchedule rows (and, via
GroupSchedule.save(), an ordinary GroupTeacher) — ordinary in the sense that
once created, such a row is in every way equal to one an admin added by
hand: same inline, same fields, no "this one is special" flag anywhere.

Not called automatically anymore (there is deliberately no signal/save()
hook wired to this — Group's own teacher/room/schedule fields are inert
legacy data now, kept only for historical continuity, and no longer drive
GroupSchedule/lesson generation at all; see their help_text on Group). Used
only by the one-off data migration that captured every pre-existing Group's
legacy fields into GroupTeacher/GroupSchedule the moment this model was
introduced (apps.academy.migrations.0004_backfill_group_schedule and
0008_final_legacy_schedule_sync) and by tests that need the same "recreate
what the old auto-mirror used to do" setup.

Only ever touches the rows it created before (`subject__isnull=True`, the
marker `sync_legacy_group_schedule` itself uses) — never an admin's own
explicitly-added GroupSchedule rows (`subject` set).

Every row this function creates/updates/deletes is tagged
``_defer_schedule_sync = True`` first, so GroupSchedule's own post_save/
post_delete signals (see signals.py) don't each trigger their own
`generate_lessons_for_group` call mid-loop, against a still-partially-synced
schedule — the caller generates once, after the whole sync is done.
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
