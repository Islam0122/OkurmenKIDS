from django.core.management.base import BaseCommand

from apps.staff_attendance.services.marking import close_stale_sessions


class Command(BaseCommand):
    help = "Закрыть открытые рабочие сессии прошлых дней как «Нет ухода» (время ухода не выдумывается)."

    def handle(self, *args, **options):
        closed = close_stale_sessions()
        self.stdout.write(self.style.SUCCESS(f"Закрыто сессий без ухода: {closed}"))
