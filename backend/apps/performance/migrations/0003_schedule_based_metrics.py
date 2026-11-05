"""«Общая статистика»: переход снимков на показатели по расписанию дня.

Почему отдельная миграция. На проде уже применены 0001_initial (первая версия
снимка: active_groups, active_students, attendance_marked, attendance_attended)
и 0002_dashboardaccesskey. Затем 0001 была по ошибке переписана на месте под
новую схему, а 0002 удалена; Django считал 0001 применённой и не менял
таблицу — отсюда «column …scheduled_groups does not exist». Файлы 0001/0002
восстановлены точно в том виде, в каком применены на проде, а переход на
новую схему — здесь.

Данные не удаляются:

* старые колонки переименовываются в legacy_* (RENAME COLUMN — без копирования
  и без потери значений), прежние проценты копируются в legacy_*_percent;
* новые колонки добавляются (NULL или 0 по умолчанию — без перезаписи таблицы);
* ручные корректировки переносятся: active_groups → scheduled_groups,
  active_students → scheduled_students (значение и отметка «вручную»);
* снимки без новых показателей помечаются «предварительными», чтобы
  планировщик посчитал их по расписанию дня из записей LMS (состав групп — на
  ту дату); вручную скорректированные значения при этом не трогаются.
"""
from django.db import migrations, models

FIELD_MAP = {"active_groups": "scheduled_groups", "active_students": "scheduled_students"}


def forwards(apps, schema_editor):
    Snapshot = apps.get_model("performance", "DailyPerformanceSnapshot")
    for snapshot in Snapshot.objects.all().iterator():
        snapshot.legacy_attendance_percent = snapshot.attendance_percent
        snapshot.legacy_homework_percent = snapshot.homework_percent
        manual = []
        for field in snapshot.manual_fields or []:
            new = FIELD_MAP.get(field)
            if new:
                setattr(snapshot, new, getattr(snapshot, f"legacy_{field}"))
                field = new
            if field not in manual:
                manual.append(field)
        snapshot.manual_fields = manual
        # Пересчитать по расписанию дня при следующем запуске планировщика.
        snapshot.status = "provisional"
        snapshot.save(update_fields=[
            "legacy_attendance_percent", "legacy_homework_percent", "manual_fields", "status",
            "scheduled_groups", "scheduled_students",
        ])


def backwards(apps, schema_editor):
    Snapshot = apps.get_model("performance", "DailyPerformanceSnapshot")
    reverse_map = {new: old for old, new in FIELD_MAP.items()}
    for snapshot in Snapshot.objects.all().iterator():
        snapshot.manual_fields = [reverse_map.get(field, field) for field in snapshot.manual_fields or []]
        snapshot.save(update_fields=["manual_fields"])


class Migration(migrations.Migration):

    dependencies = [
        ("performance", "0002_dashboardaccesskey"),
    ]

    operations = [
        # 1. Старые колонки — сохранить под именами legacy_*.
        migrations.RenameField("dailyperformancesnapshot", "active_groups", "legacy_active_groups"),
        migrations.RenameField("dailyperformancesnapshot", "active_students", "legacy_active_students"),
        migrations.RenameField("dailyperformancesnapshot", "attendance_marked", "legacy_attendance_marked"),
        migrations.RenameField("dailyperformancesnapshot", "attendance_attended", "legacy_attendance_attended"),
        migrations.AlterField(
            model_name="dailyperformancesnapshot",
            name="legacy_active_groups",
            field=models.PositiveIntegerField(blank=True, editable=False, null=True, verbose_name="Активных групп (первая версия)"),
        ),
        migrations.AlterField(
            model_name="dailyperformancesnapshot",
            name="legacy_active_students",
            field=models.PositiveIntegerField(blank=True, editable=False, null=True, verbose_name="Активных студентов (первая версия)"),
        ),
        migrations.AlterField(
            model_name="dailyperformancesnapshot",
            name="legacy_attendance_marked",
            field=models.PositiveIntegerField(default=0, editable=False, verbose_name="Отметок посещаемости (первая версия)"),
        ),
        migrations.AlterField(
            model_name="dailyperformancesnapshot",
            name="legacy_attendance_attended",
            field=models.PositiveIntegerField(default=0, editable=False, verbose_name="Присутствовали (первая версия)"),
        ),
        migrations.AddField(
            model_name="dailyperformancesnapshot",
            name="legacy_attendance_percent",
            field=models.DecimalField(blank=True, decimal_places=1, editable=False, max_digits=5, null=True, verbose_name="Посещаемость, % (первая версия)"),
        ),
        migrations.AddField(
            model_name="dailyperformancesnapshot",
            name="legacy_homework_percent",
            field=models.DecimalField(blank=True, decimal_places=1, editable=False, max_digits=5, null=True, verbose_name="Домашние задания, % (первая версия)"),
        ),
        # 2. Новые показатели по расписанию дня.
        migrations.AddField(
            model_name="dailyperformancesnapshot",
            name="scheduled_groups",
            field=models.PositiveIntegerField(blank=True, help_text="Группы с неотменёнными занятиями в этот день.", null=True, verbose_name="Групп по расписанию"),
        ),
        migrations.AddField(
            model_name="dailyperformancesnapshot",
            name="held_groups",
            field=models.PositiveIntegerField(blank=True, null=True, verbose_name="Групп с проведёнными занятиями"),
        ),
        migrations.AddField(
            model_name="dailyperformancesnapshot",
            name="scheduled_students",
            field=models.PositiveIntegerField(blank=True, help_text="Уникальные активные студенты групп с занятиями в этот день (состав на эту дату).", null=True, verbose_name="Студентов по расписанию"),
        ),
        migrations.AddField(
            model_name="dailyperformancesnapshot",
            name="attended_students",
            field=models.PositiveIntegerField(blank=True, help_text="Уникальные студенты с отметкой «Присутствовал» или «Опоздал».", null=True, verbose_name="Посетили занятия"),
        ),
        migrations.AddField(
            model_name="dailyperformancesnapshot",
            name="expected_students",
            field=models.PositiveIntegerField(default=0, help_text="Студенты занятий, которые должны были состояться (знаменатель посещаемости).", verbose_name="Ожидались на занятиях"),
        ),
        migrations.AddField(
            model_name="dailyperformancesnapshot",
            name="held_lessons_count",
            field=models.PositiveIntegerField(default=0, verbose_name="Проведено занятий"),
        ),
        # 3. Новые подписи существующих колонок (тип не меняется).
        migrations.AlterField(
            model_name="dailyperformancesnapshot",
            name="attendance_percent",
            field=models.DecimalField(blank=True, decimal_places=1, help_text="Посетили / ожидались. Пусто — в этот день не было занятий.", max_digits=5, null=True, verbose_name="Посещаемость, %"),
        ),
        migrations.AlterField(
            model_name="dailyperformancesnapshot",
            name="homework_percent",
            field=models.DecimalField(blank=True, decimal_places=1, help_text="Сдано (в срок, с опозданием, проверено) от всех результатов ДЗ, заданного в этот день.", max_digits=5, null=True, verbose_name="Домашние задания, %"),
        ),
        migrations.AlterField(
            model_name="dailyperformancesnapshot",
            name="lessons_count",
            field=models.PositiveIntegerField(default=0, verbose_name="Занятий по расписанию"),
        ),
        # 4. Данные: прежние проценты и ручные корректировки — сохранить и перенести.
        migrations.RunPython(forwards, backwards),
    ]
