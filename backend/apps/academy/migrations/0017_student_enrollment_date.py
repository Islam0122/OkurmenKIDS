import django.utils.timezone
from django.db import migrations, models
from django.db.models import Min


def backfill_enrollment_date(apps, schema_editor):
    """Existing students get the earliest date the data actually supports:
    the day their record was created, or their first marked lesson if that
    is earlier (records typed in after the fact). An Admin can correct any
    date by hand afterwards."""
    Student = apps.get_model("academy", "Student")
    Attendance = apps.get_model("academy", "Attendance")
    tz = django.utils.timezone.get_current_timezone()

    first_lesson = dict(
        Attendance.objects.values("student_id").annotate(first=Min("lesson__date")).values_list("student_id", "first")
    )
    for student in Student.objects.filter(enrollment_date__isnull=True).only("id", "created_at"):
        candidates = [student.created_at.astimezone(tz).date()]
        if first_lesson.get(student.id):
            candidates.append(first_lesson[student.id])
        student.enrollment_date = min(candidates)
        student.save(update_fields=["enrollment_date"])


class Migration(migrations.Migration):

    dependencies = [
        ("academy", "0016_lesson_reschedule"),
    ]

    operations = [
        # Added without a default first so existing rows are not all stamped
        # with the migration date; backfilled from real data, then the
        # default for new students is switched on.
        migrations.AddField(
            model_name="student",
            name="enrollment_date",
            field=models.DateField(
                blank=True,
                null=True,
                help_text="Фактическая дата начала обучения. Используется для расчёта права на стипендию.",
                verbose_name="Дата начала обучения",
            ),
        ),
        migrations.RunPython(backfill_enrollment_date, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="student",
            name="enrollment_date",
            field=models.DateField(
                blank=True,
                default=django.utils.timezone.localdate,
                help_text="Фактическая дата начала обучения. Используется для расчёта права на стипендию.",
                null=True,
                verbose_name="Дата начала обучения",
            ),
        ),
    ]
