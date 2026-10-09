from django.core.validators import RegexValidator
from django.db import migrations, models

PALETTE = (
    "#2563EB", "#D97706", "#7C3AED", "#DB2777", "#0891B2", "#16A34A", "#DC2626", "#4F46E5",
    "#C2410C", "#0D9488", "#9333EA", "#65A30D", "#BE123C", "#0369A1", "#A16207", "#475569",
)


def assign_colors(apps, schema_editor):
    """Give every existing trainer a stable color, oldest first (the same
    palette as users.models.TRAINER_PALETTE, frozen here)."""
    Teacher = apps.get_model("users", "Teacher")
    for index, teacher in enumerate(Teacher.objects.filter(color="").order_by("created_at", "pk")):
        teacher.color = PALETTE[index % len(PALETTE)]
        teacher.save(update_fields=["color"])


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0003_assistant_role"),
    ]

    operations = [
        migrations.AddField(
            model_name="teacher",
            name="color",
            field=models.CharField(
                blank=True,
                help_text="Постоянный цвет тренера в расписании (#RRGGBB). Пусто — назначается автоматически из палитры при сохранении.",
                max_length=7,
                validators=[RegexValidator("^#[0-9a-fA-F]{6}$", "Цвет в формате #RRGGBB.")],
                verbose_name="Цвет в расписании",
            ),
        ),
        migrations.RunPython(assign_colors, migrations.RunPython.noop),
    ]
