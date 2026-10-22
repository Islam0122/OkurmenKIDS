"""Удалить ТОЛЬКО демо-набор оплаты (`seed_billing_demo`).

    python manage.py reset_billing_demo --confirm [--dry-run]

Удаляются лишь записи из реестра набора `billing_demo` (и всё, что принадлежит
демо-студентам и демо-группам, — например, платежи, добавленные вручную при
проверке). Если удаление задело бы хоть одну запись вне набора, команда
останавливается и ничего не удаляет. Не запускается при DJANGO_ENV=production.
"""
from django.core.management.base import BaseCommand, CommandError

from apps.billing.services import demo


class Command(BaseCommand):
    help = "Удалить только демо-данные оплаты обучения (требует --confirm; не в production)."

    def add_arguments(self, parser):
        parser.add_argument("--confirm", action="store_true", help="Обязательно: подтверждение удаления демо-набора.")
        parser.add_argument("--dry-run", action="store_true", help="Показать, что будет удалено, и откатить.")

    def handle(self, *args, **opts):
        if not opts["confirm"] and not opts["dry_run"]:
            raise CommandError("Команда удаляет демо-набор оплаты. Повторите с --confirm (или --dry-run для проверки).")
        if not demo.exists():
            self.stdout.write("Демо-набора нет — удалять нечего.")
            return
        try:
            deleted = demo.reset(dry_run=opts["dry_run"])
        except demo.DemoError as exc:
            raise CommandError(exc.message)
        title = "Будет удалено (dry-run, ничего не изменено)" if opts["dry_run"] else "Удалено"
        self.stdout.write(self.style.WARNING(f"{title}: {sum(deleted.values())} записей"))
        for label, n in deleted.items():
            self.stdout.write(f"  {label}: {n}")
