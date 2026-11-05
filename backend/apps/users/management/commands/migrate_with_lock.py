"""`migrate` под блокировкой базы — для старта нескольких реплик на Railway:

    python manage.py migrate_with_lock --noinput

На PostgreSQL берётся advisory lock (`pg_advisory_lock`): одна реплика
применяет миграции, остальные ждут и затем видят «No migrations to apply».
На других базах (SQLite в разработке) — обычный `migrate`. Все аргументы
передаются `migrate` как есть.
"""
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import connection

LOCK_ID = 727_431_001  # постоянный номер блокировки миграций OkurmenKIDS


class Command(BaseCommand):
    help = "migrate под advisory lock PostgreSQL (без одновременных миграций с нескольких реплик)."

    def add_arguments(self, parser):
        parser.add_argument("args", nargs="*")
        parser.add_argument("--noinput", "--no-input", action="store_false", dest="interactive")

    def handle(self, *args, **options):
        if connection.vendor != "postgresql":
            call_command("migrate", *args, interactive=options["interactive"])
            return
        with connection.cursor() as cursor:
            self.stdout.write("Ожидание блокировки миграций…")
            cursor.execute("SELECT pg_advisory_lock(%s)", [LOCK_ID])
            try:
                call_command("migrate", *args, interactive=options["interactive"])
            finally:
                cursor.execute("SELECT pg_advisory_unlock(%s)", [LOCK_ID])
