from django.core.management.base import BaseCommand

from apps.accounting.services.cycles import sync_all


class Command(BaseCommand):
    help = "Зафиксировать завершённые циклы курсов по проведённым урокам групп (идемпотентно)."

    def handle(self, *args, **options):
        self.stdout.write(f"Новых завершённых циклов: {sync_all()}")
