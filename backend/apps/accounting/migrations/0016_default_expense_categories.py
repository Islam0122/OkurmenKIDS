"""Начальный справочник категорий расходов. Повторный запуск ничего не
дублирует (по коду); откат удаляет только категории, к которым не привязан
ни один расход."""
from django.db import migrations

CATEGORIES = [
    ("rent", "Аренда офиса и учебных помещений"),
    ("utilities", "Коммунальные услуги"),
    ("internet", "Интернет и связь"),
    ("stationery", "Канцелярия"),
    ("materials", "Учебные материалы"),
    ("equipment", "Компьютеры и оборудование"),
    ("repair", "Ремонт и обслуживание"),
    ("marketing", "Реклама и маркетинг"),
    ("transport", "Транспорт"),
    ("household", "Хозяйственные расходы"),
    ("other", "Прочие расходы"),
]


def create(apps, schema_editor):
    ExpenseCategory = apps.get_model("accounting", "ExpenseCategory")
    for order, (code, name) in enumerate(CATEGORIES, start=1):
        ExpenseCategory.objects.get_or_create(code=code, defaults={"name": name, "sort_order": order * 10})


def remove(apps, schema_editor):
    ExpenseCategory = apps.get_model("accounting", "ExpenseCategory")
    for category in ExpenseCategory.objects.filter(code__in=[c for c, _ in CATEGORIES], expenses__isnull=True,
                                                   recurring__isnull=True):
        # QuerySet.delete() финансовых моделей запрещён — удаляем строку напрямую.
        schema_editor.execute(f"DELETE FROM {ExpenseCategory._meta.db_table} WHERE id = %s", [category.pk])


class Migration(migrations.Migration):

    dependencies = [("accounting", "0015_company_expenses")]

    operations = [migrations.RunPython(create, remove)]
