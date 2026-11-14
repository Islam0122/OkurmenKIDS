"""Public team category: «Руководство академии» vs «Наши преподаватели».

Until now the site had only the department (`group`), and the homepage block
«Наши преподаватели» took the first profiles of *any* department — so the
director and the operational director (stored as «Администрация») were shown
as teachers. The new `category` is filled from the department:

* «Руководство», «Администрация» → management (on the site so far these are
  only the academy's directors);
* IT / English / Soft Skills trainers and profiles without a department → teacher.

Nothing is deleted; `group` is kept as it was. Editors can re-assign a
profile (e.g. to «Сотрудники академии») in the CMS at any time.
"""
from django.db import migrations, models

MANAGEMENT_GROUPS = ("management", "administration")


def forwards(apps, schema_editor):
    TeamMember = apps.get_model("website", "TeamMember")
    TeamMember.objects.filter(group__in=MANAGEMENT_GROUPS).update(category="management")
    TeamMember.objects.exclude(group__in=MANAGEMENT_GROUPS).update(category="teacher")


class Migration(migrations.Migration):

    dependencies = [
        ("website", "0007_course_schedule_translations"),
    ]

    operations = [
        migrations.AddField(
            model_name="teammember",
            name="category",
            field=models.CharField(
                choices=[
                    ("management", "Руководство академии"),
                    ("teacher", "Преподаватели"),
                    ("staff", "Сотрудники академии"),
                ],
                db_index=True,
                default="teacher",
                help_text="Руководство академии, преподаватели или сотрудники. "
                          "Директора и управляющие — «Руководство академии».",
                max_length=16,
                verbose_name="Раздел на сайте",
            ),
        ),
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
