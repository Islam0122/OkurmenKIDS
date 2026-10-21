"""Чеки для платежей, зарегистрированных до появления чеков.

Только данные чека: новые платежи, начисления или распределения не
создаются, суммы не меняются. Повторный запуск ничего не дублирует (у
платежа не больше одного чека). Отменённый платёж — чек «Аннулирован»."""
from django.db import migrations


def backfill(apps, schema_editor):
    StudentPayment = apps.get_model("accounting", "StudentPayment")
    Receipt = apps.get_model("billing", "Receipt")
    done = set(Receipt.objects.values_list("payment_id", flat=True))
    payments = (
        StudentPayment.objects.filter(billing_profile__isnull=False).exclude(pk__in=done)
        .select_related("student", "group", "course", "created_by").order_by("pk")
    )
    for p in payments.iterator():
        receipt = Receipt.objects.create(
            payment_id=p.pk, profile_id=p.billing_profile_id,
            kind="REFUND" if p.kind == "refund" else "PAYMENT",
            status="CANCELLED" if p.status == "void" else "ISSUED",
            issued_by_id=p.created_by_id,
            cancelled_at=p.voided_at, cancel_reason=p.void_reason or "",
            snapshot={
                "backfilled": True, "student": f"{p.student.last_name} {p.student.first_name}".strip(),
                "group": p.group.name, "program": p.course.name, "amount": str(p.amount),
                "method": p.method, "purpose": p.purpose, "received_date": p.received_date.isoformat(),
                "reference": p.reference,
            },
        )
        Receipt.objects.filter(pk=receipt.pk).update(
            number=f"OK-{p.created_at:%Y}-{receipt.pk:06d}", issued_at=p.created_at,
        )


class Migration(migrations.Migration):
    dependencies = [("billing", "0002_course_contracts")]

    operations = [migrations.RunPython(backfill, migrations.RunPython.noop)]
