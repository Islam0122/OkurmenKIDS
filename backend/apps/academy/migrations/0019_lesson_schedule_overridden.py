from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("academy", "0018_lesson_manually_edited"),
    ]

    operations = [
        migrations.AddField(
            model_name="lesson",
            name="schedule_overridden",
            field=models.BooleanField(
                default=False,
                help_text="Дату или время именно этого занятия изменили вручную. Такое занятие больше не следует за своим слотом расписания: ни сохранение слота, ни «Сгенерировать занятия» не переносят его (см. services.schedule_lesson_sync).",
                verbose_name="Перенесено вручную",
            ),
        ),
    ]
