"""Data migration: populate GroupTeacher from every existing GroupSchedule
row, and point every existing GroupSchedule/Lesson at the right one.

Without this, a GroupSchedule row created before GroupTeacher existed would
keep `group_teacher = NULL` forever (it's only ever (re)computed in
`GroupSchedule.save()` — see 0005) until someone happens to edit and resave
it by hand, which would silently break lesson generation for every group
that already existed (the generator groups work by GroupTeacher — see
services.lesson_generator). This migration is what makes GroupTeacher a
complete, correct source of truth for data that predates it, the same role
0004_backfill_group_schedule played for GroupSchedule itself.

One GroupTeacher per distinct (group, teacher, subject) combination already
present in GroupSchedule — mirroring exactly what `GroupSchedule.save()`
would produce if every existing row were resaved today. Existing Lessons are
then pointed at their schedule slot's GroupTeacher, or — for older Lessons
generated before GroupSchedule/teacher existed at all (`schedule` and/or
`teacher` left NULL) — at the group's own primary GroupTeacher (subject
NULL), matching `Lesson.effective_teacher`'s own fallback to `group.teacher`.

Purely additive: no Group/GroupSchedule/Lesson field other than the new
`group_teacher` FK (and Lesson's `individual_plan`, untouched here — no
GroupTeacherLessonPlan exists yet at this point for any pre-existing data)
is read destructively or changed.
"""
from django.db import migrations


def backfill_group_teacher(apps, schema_editor):
    Group = apps.get_model("academy", "Group")
    GroupTeacher = apps.get_model("academy", "GroupTeacher")
    GroupSchedule = apps.get_model("academy", "GroupSchedule")
    Lesson = apps.get_model("academy", "Lesson")

    cache: dict[tuple[int, int, int | None], int] = {}

    def group_teacher_id_for(group_id: int, teacher_id: int, subject_id: int | None) -> int:
        key = (group_id, teacher_id, subject_id)
        if key in cache:
            return cache[key]
        group_teacher, _ = GroupTeacher.objects.get_or_create(
            group_id=group_id,
            teacher_id=teacher_id,
            subject_id=subject_id,
            defaults={"is_legacy_primary": subject_id is None},
        )
        cache[key] = group_teacher.id
        return group_teacher.id

    schedule_group_teacher_id: dict[int, int] = {}
    for schedule in GroupSchedule.objects.all():
        gt_id = group_teacher_id_for(schedule.group_id, schedule.teacher_id, schedule.subject_id)
        schedule_group_teacher_id[schedule.id] = gt_id
        if schedule.group_teacher_id != gt_id:
            GroupSchedule.objects.filter(pk=schedule.pk).update(group_teacher_id=gt_id)

    group_teacher_ids = dict(Group.objects.values_list("id", "teacher_id"))

    for lesson in Lesson.objects.filter(group_teacher__isnull=True):
        if lesson.schedule_id and lesson.schedule_id in schedule_group_teacher_id:
            gt_id = schedule_group_teacher_id[lesson.schedule_id]
        else:
            teacher_id = lesson.teacher_id or group_teacher_ids.get(lesson.group_id)
            if teacher_id is None:
                # A Lesson whose group's own teacher was later removed
                # (PROTECT normally prevents this, but historical/edge data
                # can still be inconsistent) — nothing sensible to backfill.
                continue
            gt_id = group_teacher_id_for(lesson.group_id, teacher_id, None)
        Lesson.objects.filter(pk=lesson.pk).update(group_teacher_id=gt_id)


def noop_reverse(apps, schema_editor):
    # Reversing would need to tell an auto-derived GroupTeacher apart from
    # one lesson generation has since built real plans/lessons on top of —
    # safer to leave the data in place. No Group/GroupSchedule/Lesson field
    # other than the new group_teacher FK is touched either way.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("academy", "0005_groupteacher"),
    ]

    operations = [
        migrations.RunPython(backfill_group_teacher, noop_reverse),
    ]
