"""Пароли демо-пользователей оплаты — только для локальной тестовой среды.

    python manage.py billing_demo_passwords            # случайный пароль каждому (показывается один раз)
    python manage.py billing_demo_passwords --password 'свой-пароль'

Генератор создаёт demo_accountant / demo_manager / demo_director без пароля
(вход закрыт). Не запускается при DJANGO_ENV=production.
"""
from django.core.management.base import BaseCommand, CommandError

from apps.billing.services import demo


class Command(BaseCommand):
    help = "Задать пароли демо-пользователям оплаты (локально)."

    def add_arguments(self, parser):
        parser.add_argument("--password", default=None, help="Пароль для всех демо-пользователей (иначе — случайные).")

    def handle(self, *args, **opts):
        try:
            result = demo.set_passwords(opts["password"])
        except demo.DemoError as exc:
            raise CommandError(exc.message)
        for username, password in result.items():
            self.stdout.write(f"{username:24} {password}")
        self.stdout.write(self.style.WARNING("Сохраните пароли — повторно они не показываются."))
