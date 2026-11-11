"""Profile URLs are unique. Separate from 0003 (which fills the slugs): on
PostgreSQL a table cannot be altered in the same transaction that updated its
rows while deferred foreign-key checks are pending."""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("website", "0003_team_member_profile"),
    ]

    operations = [
        migrations.AlterField(
            model_name="teammember",
            name="slug",
            field=models.SlugField(
                blank=True,
                help_text="/team/<slug>. Пусто — из имени.",
                max_length=220,
                unique=True,
                verbose_name="Адрес профиля (slug)",
            ),
        ),
    ]
