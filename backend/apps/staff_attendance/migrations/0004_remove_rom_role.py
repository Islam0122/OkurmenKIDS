"""Роль РОМ упразднена (users.0007): её убирают из списка отслеживаемых ролей
в настройках учёта, иначе запись не пройдёт проверку «Неизвестная роль».
Бывшие РОМ стали маркетингом, поэтому если РОМ отслеживался, маркетинг
добавляется в список — отметка прихода и ухода у этих сотрудников сохраняется.
Остальные роли списка не меняются. Повторный запуск ничего не меняет."""
from django.db import migrations


def forwards(apps, schema_editor):
    Settings = apps.get_model("staff_attendance", "AttendanceSettings")
    for config in Settings.objects.all():
        tracked = list(config.tracked_roles or [])
        if "rom" not in tracked:
            continue
        cleaned = [role for role in tracked if role != "rom"]
        if "marketing" not in cleaned:
            cleaned.append("marketing")
        config.tracked_roles = cleaned
        config.save(update_fields=["tracked_roles"])


class Migration(migrations.Migration):
    dependencies = [
        ("staff_attendance", "0003_track_staff_only_roles"),
        ("users", "0007_remove_rom_role"),
    ]

    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]
