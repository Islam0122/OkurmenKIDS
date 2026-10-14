# Additive only: every existing student stays listed (default True), nothing
# else changes. Used by the public leaderboard (apps.leaderboard).

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("academy", "0024_group_subject_start"),
    ]

    operations = [
        migrations.AddField(
            model_name="student",
            name="show_in_leaderboard",
            field=models.BooleanField(
                default=True,
                help_text="Если выключено, имя студента не показывается на публичном сайте рейтинга "
                "(баллы группы при этом учитываются).",
                verbose_name="Показывать в публичном рейтинге",
            ),
        ),
    ]
