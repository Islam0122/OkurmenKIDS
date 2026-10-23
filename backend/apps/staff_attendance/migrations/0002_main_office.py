"""Начальная конфигурация: главный офис OkurmenKIDS (центр геозоны и радиус
100 м) и запись общих настроек. Это настройки, а не отметки — ни одной
сессии или события миграция не создаёт. Повторный запуск ничего не меняет;
если офисы уже есть, новый не добавляется."""
import secrets

from django.db import migrations

MAIN_OFFICE = {
    "name": "OkurmenKIDS — главный офис",
    "latitude": 42.88543338574097,
    "longitude": 74.60303549712579,
    "radius_m": 100,
}


def forwards(apps, schema_editor):
    Location = apps.get_model("staff_attendance", "AttendanceLocation")
    Settings = apps.get_model("staff_attendance", "AttendanceSettings")
    if not Location.objects.exists():
        Location.objects.create(code=secrets.token_urlsafe(12), is_active=True, **MAIN_OFFICE)
    Settings.objects.get_or_create(pk=1)


class Migration(migrations.Migration):
    dependencies = [("staff_attendance", "0001_initial")]

    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]
