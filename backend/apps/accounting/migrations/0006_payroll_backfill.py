"""Перенос данных для 0005 — отдельной миграцией, чтобы данные и схема
менялись в разных транзакциях (иначе откат на PostgreSQL падает с «pending
trigger events»). Повторяемо, без дублей; откат удаляет только перенесённое
и сохраняет причины спорных начислений в `note`."""
import datetime as dt

from django.db import migrations

MIGRATED_REASON = "Перенесено из настроек курса при введении истории тарифов (дата начала неизвестна)."


def backfill_prices(apps, schema_editor):
    Settings = apps.get_model("accounting", "CoursePayrollSettings")
    Version = apps.get_model("accounting", "CoursePriceVersion")
    for settings in Settings.objects.all():
        if Version.objects.filter(course_id=settings.course_id).exists():
            continue
        Version.objects.create(
            course_id=settings.course_id, price_per_student=settings.price_per_student, currency="KGS",
            effective_from=dt.date(2000, 1, 1), reason=MIGRATED_REASON, is_migrated=True,
        )


def remove_prices(apps, schema_editor):
    apps.get_model("accounting", "CoursePriceVersion").objects.filter(is_migrated=True, previous_version=None,
                                                                       next_version=None).delete()


def backfill_cycle_lessons(apps, schema_editor):
    Cycle = apps.get_model("accounting", "CourseCycle")
    Settings = apps.get_model("accounting", "CoursePayrollSettings")
    Link = apps.get_model("accounting", "CycleLesson")
    Lesson = apps.get_model("academy", "Lesson")
    starts = {s.course_id: s.count_lessons_from for s in Settings.objects.all()}
    for cycle in Cycle.objects.filter(status="COMPLETED").order_by("group_id", "course_id", "number"):
        if Link.objects.filter(cycle_id=cycle.pk).exists():
            continue
        lessons = Lesson.objects.filter(group_id=cycle.group_id, status="completed")
        if starts.get(cycle.course_id):
            lessons = lessons.filter(date__gte=starts[cycle.course_id])
        rows = list(lessons.order_by("date", "start_time", "id").values(
            "id", "date", "teacher_id", "group_teacher__teacher_id",
        ))
        chunk = rows[cycle.lessons_total - cycle.required_lessons:cycle.lessons_total]
        if len(chunk) != cycle.required_lessons or chunk[-1]["id"] != cycle.last_lesson_id:
            continue  # неоднозначно — в отчёт сверки, без угадывания
        if Link.objects.filter(is_live=True, lesson_ref__in=[r["id"] for r in chunk]).exists():
            continue
        Link.objects.bulk_create([
            Link(cycle_id=cycle.pk, lesson_id=r["id"], lesson_ref=r["id"], lesson_date=r["date"], position=i,
                 teacher_id=r["teacher_id"] or r["group_teacher__teacher_id"], is_live=True, backfilled=True)
            for i, r in enumerate(chunk, start=1)
        ])


def remove_cycle_lessons(apps, schema_editor):
    apps.get_model("accounting", "CycleLesson").objects.filter(backfilled=True).delete()


REVIEW_PREFIX = "Требует проверки: "


def preserve_review_reasons(apps, schema_editor):
    """Откат: поле причин удаляется, поэтому причины спорных начислений
    переносятся в `note` (оно есть и в прежней схеме). Статус
    REVIEW_REQUIRED прежний код не включает в расчёт — их нужно разобрать."""
    Accrual = apps.get_model("accounting", "CycleAccrual")
    for accrual in Accrual.objects.filter(status="REVIEW_REQUIRED").exclude(review_reasons=[]):
        accrual.note = (REVIEW_PREFIX + " ".join(accrual.review_reasons) + (f" {accrual.note}" if accrual.note else ""))
        accrual.save(update_fields=["note"])


def restore_review_reasons(apps, schema_editor):
    Accrual = apps.get_model("accounting", "CycleAccrual")
    for accrual in Accrual.objects.filter(status="REVIEW_REQUIRED", review_reasons=[], note__startswith=REVIEW_PREFIX):
        accrual.review_reasons = [accrual.note[len(REVIEW_PREFIX):]]
        accrual.save(update_fields=["review_reasons"])


class Migration(migrations.Migration):
    dependencies = [("accounting", "0005_payroll_estimates_pricing_analytics")]

    operations = [
        migrations.RunPython(backfill_prices, remove_prices),
        migrations.RunPython(backfill_cycle_lessons, remove_cycle_lessons),
        migrations.RunPython(restore_review_reasons, preserve_review_reasons),
    ]
