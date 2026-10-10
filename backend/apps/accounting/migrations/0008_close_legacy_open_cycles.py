"""Закрыть открытые общие циклы групп (денег в них нет — это только прогресс):
дальше прогресс ведут циклы по предметам. Завершённые общие циклы и их
начисления не меняются. Повторяемо; откат возвращает закрытые этой
миграцией циклы в «Идёт» и возможен, только пока ни один предметный цикл
не завершён (иначе — понятная ошибка, данные не трогаются)."""
from django.db import migrations

REASON = "Учёт переведён на циклы по предметам."


def close_legacy(apps, schema_editor):
    Cycle = apps.get_model("accounting", "CourseCycle")
    Cycle.objects.filter(per_subject=False, status="IN_PROGRESS").update(status="INVALIDATED", invalidated_reason=REASON)


def reopen_legacy(apps, schema_editor):
    Cycle = apps.get_model("accounting", "CourseCycle")
    if Cycle.objects.filter(per_subject=True).exclude(status="IN_PROGRESS").exists():
        raise RuntimeError(
            "Откат невозможен: уже есть завершённые или отменённые циклы по предметам (с начислениями). "
            "Прежняя схема (один общий цикл группы) не может их хранить — откатывайте код, не миграции."
        )
    # Открытые предметные циклы — только прогресс, денег в них нет.
    Cycle.objects.filter(per_subject=True, status="IN_PROGRESS").delete()
    for cycle in Cycle.objects.filter(per_subject=False, status="INVALIDATED", invalidated_reason=REASON):
        if not Cycle.objects.filter(group_id=cycle.group_id, course_id=cycle.course_id, per_subject=False,
                                    status="IN_PROGRESS").exists():
            cycle.status, cycle.invalidated_reason = "IN_PROGRESS", ""
            cycle.save(update_fields=["status", "invalidated_reason"])


class Migration(migrations.Migration):
    dependencies = [("accounting", "0007_subject_cycles")]

    operations = [migrations.RunPython(close_legacy, reopen_legacy)]
