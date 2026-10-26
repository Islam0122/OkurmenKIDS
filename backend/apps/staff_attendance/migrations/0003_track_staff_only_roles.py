"""Новые роли (ДОП, РОП, РОМ, операционный директор, HR-менеджер, менеджер
по продажам, маркетинг) отмечают приход и уход. Запись настроек хранит
список отслеживаемых ролей в базе, поэтому в уже существующую запись роли
добавляются явно; остальные роли списка не меняются. Повторный запуск ничего
не меняет."""
from django.db import migrations

NEW_ROLES = ["dop", "rop", "rom", "operations_director", "hr_manager", "sales_manager", "marketing"]


def forwards(apps, schema_editor):
    Settings = apps.get_model("staff_attendance", "AttendanceSettings")
    for config in Settings.objects.all():
        tracked = list(config.tracked_roles or [])
        missing = [role for role in NEW_ROLES if role not in tracked]
        if missing:
            config.tracked_roles = tracked + missing
            config.save(update_fields=["tracked_roles"])


def backwards(apps, schema_editor):
    Settings = apps.get_model("staff_attendance", "AttendanceSettings")
    for config in Settings.objects.all():
        tracked = [role for role in (config.tracked_roles or []) if role not in NEW_ROLES]
        if tracked != config.tracked_roles:
            config.tracked_roles = tracked
            config.save(update_fields=["tracked_roles"])


class Migration(migrations.Migration):
    dependencies = [
        ("staff_attendance", "0002_main_office"),
        ("users", "0006_staff_only_roles"),
    ]

    operations = [migrations.RunPython(forwards, backwards)]
