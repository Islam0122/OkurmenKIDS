"""Демо-данные финансового модуля: 15 студентов-сценариев (A–O).

    python manage.py seed_billing_demo [--today 2026-10-22]

* Данные создаются настоящими сервисами оплаты и отображаются в /finance.
* Повторный запуск ничего не дублирует (реестр `DemoSeedRecord`, набор
  `billing_demo`); недостающие сценарии досоздаются.
* Не запускается при DJANGO_ENV=production. Вход демо-пользователям закрыт,
  пока пароли не задаст `python manage.py billing_demo_passwords`.

Сценарии и ручные проверки — docs/BILLING_DEMO.md.
"""
import datetime as dt

from django.core.management.base import BaseCommand, CommandError

from apps.billing.services import demo


class Command(BaseCommand):
    help = "Создать демо-набор оплаты обучения (идемпотентно, только вне production)."

    def add_arguments(self, parser):
        parser.add_argument("--today", type=dt.date.fromisoformat, default=None,
                            help="Дата генерации (по умолчанию сегодня).")

    def handle(self, *args, **opts):
        try:
            result = demo.seed(today=opts["today"])
        except demo.DemoError as exc:
            raise CommandError(exc.message)
        created = ", ".join(result["created"]) or "ничего — набор уже создан"
        self.stdout.write(self.style.SUCCESS(f"Созданы сценарии: {created}. Начало обучения: {result['start']}. "
                                             f"Записей в реестре набора: {result['records']}."))
        self.stdout.write("")
        self.stdout.write(f"{'':2}{'Студент':28}{'Месяц':16}{'К оплате':>10}{'Просроч.':>10}{'Аванс':>10}{'Остаток':>10}")
        for r in demo.scenario_rows():
            self.stdout.write(f"{r['key']:2}{r['student'][:27]:28}{r['month']:16}{r['due_now']:>10}{r['overdue']:>10}"
                              f"{r['credit']:>10}{r['outstanding']:>10}")
        self.stdout.write("")
        self.stdout.write("Вход: python manage.py billing_demo_passwords — задаст пароли demo_accountant, "
                          "demo_manager, demo_director. Интерфейс: /finance.")
