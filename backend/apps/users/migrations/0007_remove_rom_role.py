"""Роль РОМ упразднена. Пользователи с этой ролью переводятся на роль
«Маркетинг» — тот же отдел и тот же базовый уровень доступа (вход и отметка
прихода и ухода). Аккаунты и связанные данные не удаляются и не меняются.
Обратная миграция возвращает только список вариантов роли: кто был РОМ, после
перевода не отличить от маркетинга, поэтому роли пользователей не трогаются."""
from django.db import migrations, models


def move_rom_users(apps, schema_editor):
    User = apps.get_model("users", "User")
    User.objects.filter(role="rom").update(role="marketing")


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0006_staff_only_roles"),
    ]

    operations = [
        migrations.RunPython(move_rom_users, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="user",
            name="role",
            field=models.CharField(
                choices=[
                    ("admin", "Администратор"),
                    ("teacher", "Тренер"),
                    ("team_lead", "Team Lead"),
                    ("assistant", "Ассистент"),
                    ("accountant", "Бухгалтер"),
                    ("director", "Директор"),
                    ("dop", "ДОП"),
                    ("rop", "РОП"),
                    ("operations_director", "Операционный директор"),
                    ("hr_manager", "HR-менеджер"),
                    ("sales_manager", "Менеджер по продажам"),
                    ("marketing", "Маркетинг"),
                ],
                db_index=True,
                default="teacher",
                help_text="Определяет права доступа пользователя в системе.",
                max_length=20,
                verbose_name="Роль",
            ),
        ),
    ]
