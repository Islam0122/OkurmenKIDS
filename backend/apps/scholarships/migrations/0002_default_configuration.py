from decimal import Decimal

from django.db import migrations


def create_default_configuration(apps, schema_editor):
    Configuration = apps.get_model("scholarships", "ScholarshipConfiguration")
    if Configuration.objects.exists():
        return
    Configuration.objects.create(
        name="Стипендия OkurmenKIDS",
        is_active=True,
        award_mode="monthly",
        max_recipients=20,
        attendance_weight=Decimal("0.40"),
        homework_weight=Decimal("0.30"),
        feedback_weight=Decimal("0.30"),
        subject_aggregation="equal",
        late_homework_credit=Decimal("0.50"),
        min_overall_score=Decimal("0"),
        min_marked_lessons=1,
        require_complete_feedback=True,
        auto_approve=False,
    )


class Migration(migrations.Migration):

    dependencies = [
        ("scholarships", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(create_default_configuration, migrations.RunPython.noop),
    ]
