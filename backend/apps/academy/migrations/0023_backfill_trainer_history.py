"""Backfill the trainer assignment history (TrainerAssignment) and the
stored trainer of legacy lessons — only from what the data can confirm.

Before this migration a Teaching Program (GroupTeacher) only knew its
*current* trainer. For every program this creates one assignment for that
trainer, starting from the earliest date the data confirms they were the
program's trainer:

* evidence of an earlier trainer change — a LogEntry of the program
  recording a replaced trainer (services.trainer_assignment: «Заменил
  тренера …», the admin form changing «Тренер», a «Учебная конфигурация»
  save whose «Было» names another trainer), or a lesson of the program that
  stores another trainer — moves the start to the day after the latest such
  evidence;
* without any, the current trainer covers the program from its first day
  (group start / first lesson / creation, whichever is earliest).

An inactive program gets a closed assignment ending on its last update.

Lessons that never stored their trainer (Lesson.teacher is NULL — legacy
data) get the program's trainer only when the assignment covers their date;
older ones stay NULL and count for no trainer (they still count for their
group, subject and the academy). `manage.py audit_trainer_history` lists
them so an admin can set the trainer by hand. Nothing is deleted; lessons
that already store a trainer are never touched.
"""
import datetime as dt
import json

from django.db import migrations
from django.utils import timezone

CHANGE = 2


def _local_date(moment):
    return timezone.localtime(moment).date() if timezone.is_aware(moment) else moment.date()


def _change_evidence(entry, current_name: str) -> bool:
    message = entry.change_message or ""
    if "Заменил тренера" in message:
        return True
    if "Учебная конфигурация" in message and "Было:" in message:
        before = message.split("Было:", 1)[1].split("Стало:", 1)[0]
        return bool(current_name) and current_name not in before and before.strip(" .") != "—"
    if message.startswith("["):
        try:
            for item in json.loads(message):
                fields = (item.get("changed") or {}).get("fields") or []
                if any(str(f).lower() in ("тренер", "teacher") for f in fields):
                    return True
        except (ValueError, AttributeError, TypeError):
            return False
    return False


def backfill(apps, schema_editor):
    GroupTeacher = apps.get_model("academy", "GroupTeacher")
    Lesson = apps.get_model("academy", "Lesson")
    TrainerAssignment = apps.get_model("academy", "TrainerAssignment")
    ContentType = apps.get_model("contenttypes", "ContentType")
    LogEntry = apps.get_model("admin", "LogEntry")

    content_type = ContentType.objects.filter(app_label="academy", model="groupteacher").first()
    today = timezone.localdate()

    for program in GroupTeacher.objects.select_related("group", "teacher__user").iterator():
        if TrainerAssignment.objects.filter(program_id=program.pk).exists():
            continue
        user = program.teacher.user
        current_name = f"{user.first_name} {user.last_name}".strip() or user.username

        floors = []
        if content_type is not None:
            for entry in LogEntry.objects.filter(
                content_type_id=content_type.pk, object_id=str(program.pk), action_flag=CHANGE,
            ):
                if _change_evidence(entry, current_name):
                    floors.append(_local_date(entry.action_time))
        last_other = (
            Lesson.objects.filter(group_teacher_id=program.pk, teacher__isnull=False)
            .exclude(teacher_id=program.teacher_id).order_by("-date").values_list("date", flat=True).first()
        )
        if last_other is not None:
            floors.append(last_other + dt.timedelta(days=1))

        if floors:
            start = max(floors)
        else:
            first_lesson = (
                Lesson.objects.filter(group_teacher_id=program.pk).order_by("date").values_list("date", flat=True).first()
            )
            candidates = [d for d in (program.group.start_date, first_lesson, _local_date(program.created_at)) if d]
            start = min(candidates) if candidates else today

        end = None
        if not program.is_active:
            end = max(_local_date(program.updated_at), start)
        TrainerAssignment.objects.create(
            program_id=program.pk, group_id=program.group_id, teacher_id=program.teacher_id,
            subject_id=program.subject_id, start_date=start, end_date=end, source="migration",
            closed_at=program.updated_at if end else None,
        )

        # Legacy lessons without a stored trainer: only those the confirmed
        # assignment covers.
        covered = Lesson.objects.filter(group_teacher_id=program.pk, teacher__isnull=True, date__gte=start)
        if end is not None:
            covered = covered.filter(date__lt=end) if end > start else covered.none()
        covered.update(teacher_id=program.teacher_id)


class Migration(migrations.Migration):

    dependencies = [
        ("academy", "0022_trainer_assignment_history"),
        ("admin", "0003_logentry_add_action_flag_choices"),
        ("contenttypes", "0002_remove_content_type_name"),
    ]

    operations = [
        migrations.RunPython(backfill, migrations.RunPython.noop),
    ]
