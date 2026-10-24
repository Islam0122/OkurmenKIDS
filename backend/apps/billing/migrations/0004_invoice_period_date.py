"""Период начисления (`Invoice.period_date`) и дата корректировки
(`InvoiceAdjustment.effective_date`) — отдельно от даты создания записи.

Существующие записи заполняются без изменения смысла: период начисления =
дата начисления (`issue_date`), дата корректировки = день её создания.
Ни одна дата, сумма или статус старых записей не меняется. Начисления,
период которых по данным уроков и договора, вероятно, другой (договор
оформлен задним числом), не исправляются автоматически — их список и
контролируемое исправление с аудитом: `manage.py billing_period_review`."""
import django.utils.timezone
from django.db import migrations, models


def backfill(apps, schema_editor):
    Invoice = apps.get_model("billing", "Invoice")
    InvoiceAdjustment = apps.get_model("billing", "InvoiceAdjustment")
    Invoice.objects.filter(period_date__isnull=True).update(period_date=models.F("issue_date"))
    for adjustment in InvoiceAdjustment.objects.filter(effective_date__isnull=True).only("pk", "created_at").iterator():
        InvoiceAdjustment.objects.filter(pk=adjustment.pk).update(
            effective_date=django.utils.timezone.localdate(adjustment.created_at),
        )


class Migration(migrations.Migration):
    dependencies = [("billing", "0003_backfill_receipts")]

    operations = [
        migrations.AddField(
            model_name="invoice", name="period_date",
            field=models.DateField(null=True, verbose_name="Период начисления"),
        ),
        migrations.AddField(
            model_name="invoiceadjustment", name="effective_date",
            field=models.DateField(null=True, verbose_name="Дата корректировки"),
        ),
        migrations.RunPython(backfill, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="invoice", name="period_date",
            field=models.DateField(db_index=True, verbose_name="Период начисления"),
        ),
        migrations.AlterField(
            model_name="invoiceadjustment", name="effective_date",
            field=models.DateField(db_index=True, verbose_name="Дата корректировки"),
        ),
        # Только список вариантов (ранее не отражён в миграциях) — данные не меняются.
        migrations.AlterField(
            model_name="billingnotification", name="kind",
            field=models.CharField(choices=[
                ("PACKAGE_ENDING", "Пакет скоро закончится"), ("PACKAGE_COMPLETED", "Пакет использован"),
                ("INVOICE_CREATED", "Новое начисление"), ("INVOICE_PAID", "Начисление оплачено"),
                ("OVERDUE", "Просрочка"), ("PAYMENT_DEADLINE", "Последний срок оплаты"),
                ("FOLLOW_UP", "Повторный контакт"), ("DISCOUNT_APPROVAL", "Скидка ждёт согласования"),
                ("REPORT", "Финансовый отчёт"),
            ], db_index=True, max_length=20),
        ),
    ]
