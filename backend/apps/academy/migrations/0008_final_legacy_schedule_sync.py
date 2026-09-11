"""Data migration: one last mirror of every Group's legacy teacher/room/
start_time/end_time/days_of_week fields into GroupSchedule/GroupTeacher,
run once as this deploy permanently retires the live auto-sync that used to
do this on every Group save (see services.group_schedule_sync — as of this
change it is no longer called automatically; Group's own
teacher/room/start_time/end_time/days_of_week are inert historical data
from here on, see their help_text).

Without this, any Group saved between the previous deploy (where the live
sync last ran) and this one — in a window where the app was still running
old code with a newer version of manage.py, a management command, a
fixture load, or any write that bypassed the signal — could have legacy
fields the sync never got to mirror yet, and would otherwise permanently
lose that data's schedule once the auto-sync is gone. Idempotent
(get_or_create throughout) and additive only: it never touches an existing
GroupSchedule row an admin already edited by hand (`subject` set), only the
auto-mirrored kind (`subject` NULL) — same rule the old live sync always
followed.
"""
from django.db import migrations

WEEKDAY_CODES = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


def final_sync(apps, schema_editor):
    Group = apps.get_model("academy", "Group")
    GroupTeacher = apps.get_model("academy", "GroupTeacher")
    GroupSchedule = apps.get_model("academy", "GroupSchedule")

    for group in Group.objects.all():
        if not (group.teacher_id and group.start_time and group.end_time and group.days_of_week):
            continue

        days = [day for day in group.days_of_week if day in WEEKDAY_CODES]
        is_active = group.status != "cancelled"

        group_teacher, _ = GroupTeacher.objects.get_or_create(
            group_id=group.id,
            teacher_id=group.teacher_id,
            subject_id=None,
            defaults={"is_legacy_primary": True},
        )

        for day in days:
            slot, created = GroupSchedule.objects.get_or_create(
                group_id=group.id,
                subject_id=None,
                day_of_week=day,
                defaults={
                    "teacher_id": group.teacher_id,
                    "start_time": group.start_time,
                    "end_time": group.end_time,
                    "room_id": group.room_id,
                    "is_active": is_active,
                    "group_teacher_id": group_teacher.id,
                },
            )
            if not created and slot.group_teacher_id != group_teacher.id:
                GroupSchedule.objects.filter(pk=slot.pk).update(group_teacher_id=group_teacher.id)


def noop_reverse(apps, schema_editor):
    # Same reasoning as 0004/0006: reversing would need to tell an
    # auto-mirrored row apart from one since edited by hand, and no
    # Group/GroupSchedule/GroupTeacher field this migration didn't itself
    # add is ever touched — nothing is lost by leaving the data in place.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("academy", "0007_group_legacy_fields_optional"),
    ]

    operations = [
        migrations.RunPython(final_sync, noop_reverse),
    ]
