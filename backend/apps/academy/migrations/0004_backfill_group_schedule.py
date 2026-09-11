"""Data migration: backfill GroupSchedule from every existing Group's own
teacher/room/start_time/end_time/days_of_week — one row per weekday, marked
as a "legacy" slot (subject=None). No Group data is read destructively and
nothing on Group itself is changed; this only adds GroupSchedule rows so the
new schedule table is a complete, correct source of truth for every Group
that already existed before GroupSchedule was introduced (see
services.group_schedule_sync, which keeps doing the same thing going
forward on every Group save).
"""
from django.db import migrations

WEEKDAY_CODES = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


def backfill_group_schedule(apps, schema_editor):
    Group = apps.get_model("academy", "Group")
    GroupSchedule = apps.get_model("academy", "GroupSchedule")

    for group in Group.objects.all():
        if not (group.teacher_id and group.start_time and group.end_time and group.days_of_week):
            continue

        days = [day for day in group.days_of_week if day in WEEKDAY_CODES]
        is_active = group.status != "cancelled"

        for day in days:
            GroupSchedule.objects.get_or_create(
                group=group,
                subject=None,
                day_of_week=day,
                defaults={
                    "teacher_id": group.teacher_id,
                    "start_time": group.start_time,
                    "end_time": group.end_time,
                    "room_id": group.room_id,
                    "is_active": is_active,
                },
            )


def noop_reverse(apps, schema_editor):
    # Reversing would need to tell an auto-mirrored row apart from one an
    # admin has since edited by hand — safer to leave GroupSchedule data in
    # place than guess. Group's own fields (the real data) are never
    # touched by this migration either way, so nothing is lost by not
    # reversing it.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("academy", "0003_group_schedule"),
    ]

    operations = [
        migrations.RunPython(backfill_group_schedule, noop_reverse),
    ]
