"""Step 1 of 2: check the data, add the snapshot / journal fields.

Nothing existing is changed or deleted. If any award breaks the money rules
that 0007 turns into database constraints, the migration stops and lists
those awards (see services/integrity.py and
`python manage.py scholarship_integrity`) — a person decides how to fix
them, the migration never does.
"""
from django.db import migrations, models


def check_awards(apps, schema_editor):
    from apps.scholarships.services.integrity import describe, find_conflicts

    conflicts = find_conflicts(apps.get_model("scholarships", "ScholarshipAward"))
    if conflicts:
        raise RuntimeError(
            f"Миграция остановлена: {len(conflicts)} стипендий нарушают правила сумм и выплат. "
            "Данные не изменены.\n" + describe(conflicts) + "\n"
            "Проверка: python manage.py scholarship_integrity\n"
            "Стипендии без суммы (NULL), ещё не выданные, можно перевести в сумму 0 "
            "(«стипендия без денежной суммы»): python manage.py scholarship_integrity --fix-unpaid-null-amounts\n"
            "Остальное нужно исправить вручную."
        )


def snapshot_payer_names(apps, schema_editor):
    """paid_by_name for payments recorded before this migration."""
    Award = apps.get_model("scholarships", "ScholarshipAward")
    for award in Award.objects.filter(payment_status="paid", paid_by__isnull=False).select_related("paid_by"):
        user = award.paid_by
        name = f"{user.first_name} {user.last_name}".strip() or user.username
        Award.objects.filter(pk=award.pk).update(paid_by_name=name[:150])


class Migration(migrations.Migration):

    dependencies = [
        ("scholarships", "0005_award_payment"),
    ]

    operations = [
        migrations.RunPython(check_awards, migrations.RunPython.noop),
        migrations.AddField(
            model_name="scholarshipaward",
            name="paid_by_name",
            field=models.CharField(blank=True, max_length=150, verbose_name="Выдал (имя на момент выплаты)"),
        ),
        migrations.AddField(
            model_name="scholarshiprunlog",
            name="details",
            field=models.JSONField(blank=True, default=dict, verbose_name="Подробности"),
        ),
        migrations.RunPython(snapshot_payer_names, migrations.RunPython.noop),
    ]
