"""Ключ доступа «только чтение» к сайту «Общая статистика»:

    python manage.py create_dashboard_key "Телевизор в офисе" [--days 365]

Ключ печатается один раз — сохраните его (в базе только хеш). Откройте на
телевизоре: <адрес сайта>/monthly-performance?key=<ключ> — ключ запомнится
в браузере и исчезнет из адресной строки. Отключить — Django admin.
"""
import datetime as dt

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.performance.services.access_keys import issue_key


class Command(BaseCommand):
    help = "Создать ключ доступа к сайту «Общая статистика» (только просмотр)."

    def add_arguments(self, parser):
        parser.add_argument("name", help="Название ключа, например «Телевизор в офисе».")
        parser.add_argument("--days", type=int, default=None, help="Срок действия в днях (по умолчанию бессрочно).")

    def handle(self, *args, **options):
        expires = timezone.now() + dt.timedelta(days=options["days"]) if options["days"] else None
        key, raw = issue_key(options["name"], expires_at=expires)
        self.stdout.write(f"Ключ «{key.name}» создан. Сохраните его — он больше не будет показан:\n{raw}")
