"""Тестовые данные бухгалтерии за август–октябрь 2026.

    python manage.py seed_accounting_demo [--seed 42] [--month all|2026-08|2026-09|2026-10]
                                          [--dry-run] [--clear] [--today 2026-10-10]
                                          [--demo-password ...]

* По умолчанию ничего не удаляет; повторный запуск не создаёт дублей.
* `--month 2026-09` — данные по конец сентября (включая август: циклы
  переходят через границы месяцев); `all` — все три месяца (по текущую дату).
* `--clear` — удалить ТОЛЬКО записи из реестра генератора; если удаление
  задело бы что-то ещё, команда останавливается с ошибкой.
* `--dry-run` — выполнить в транзакции и откатить: показать, что будет создано
  (или удалено с `--clear`).
* `--demo-password` — пароль DEMO-пользователей для проверки интерфейса
  (по умолчанию вход им закрыт).
* Не запускается при DJANGO_ENV=production.

Подробно о сценариях — apps/accounting/services/demo_seed.py.
"""
import datetime as dt
import os

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.accounting.services import demo_seed


class Command(BaseCommand):
    help = "Тестовые данные бухгалтерии (август–октябрь 2026), с безопасной очисткой по реестру генератора."

    def add_arguments(self, parser):
        parser.add_argument("--seed", type=int, default=42)
        parser.add_argument("--month", default="all", help="all, 2026-08, 2026-09 или 2026-10")
        parser.add_argument("--clear", action="store_true", help="Удалить только данные генератора.")
        parser.add_argument("--dry-run", action="store_true", help="Показать результат без записи в БД.")
        parser.add_argument("--today", type=dt.date.fromisoformat, default=None,
                            help="Дата генерации (по умолчанию сегодня, Asia/Bishkek).")
        parser.add_argument("--demo-password", default=None)

    def handle(self, *args, **opts):
        if os.environ.get("DJANGO_ENV") == "production":
            raise CommandError("Генератор тестовых данных не запускается в production (DJANGO_ENV=production).")
        try:
            if opts["clear"]:
                self._clear(opts["dry_run"])
            else:
                self._generate(opts)
        except demo_seed.SeedError as exc:
            raise CommandError(exc.message)

    def _clear(self, dry_run):
        if not demo_seed.exists():
            self.stdout.write("Тестового набора нет — удалять нечего.")
            return
        deleted = demo_seed.clear(dry_run=dry_run)
        title = "Будет удалено (dry-run, ничего не изменено)" if dry_run else "Удалено записей набора"
        self.stdout.write(self.style.WARNING(f"{title}: {sum(deleted.values())}"))
        for label, n in sorted(deleted.items()):
            self.stdout.write(f"  {label}: {n}")

    def _generate(self, opts):
        month = opts["month"]
        if month == "all":
            months = list(demo_seed.MONTHS)
        elif month in demo_seed.MONTHS:
            months = [month]
        else:
            raise CommandError("--month: all, 2026-08, 2026-09 или 2026-10.")
        today = opts["today"] or timezone.localdate()
        result = demo_seed.generate(seed=opts["seed"], months=months, today=today,
                                    demo_password=opts["demo_password"], dry_run=opts["dry_run"])
        s = result["summary"]
        head = "DRY-RUN — ничего не записано" if opts["dry_run"] else "Тестовые данные готовы"
        self.stdout.write(self.style.SUCCESS(f"{head}: месяцы {', '.join(result['months'])}, данные по "
                                             f"{result['cutoff']:%d.%m.%Y} (сегодня {today:%d.%m.%Y})"))
        created = result["created"]
        self.stdout.write(f"Создано записей: {sum(created.values())}" + (" (повторный запуск — без изменений)" if not created else ""))
        for name, n in sorted(created.items()):
            self.stdout.write(f"  {name}: {n}")
        self.stdout.write(
            f"Сотрудников (тестовых): {s['employees']} · пользователей набора: {s['staff_users']} · правил оплаты: "
            f"{s['salary_rules']} · уроков: {s['lessons']}\n"
            f"Предметных циклов: {s['subject_cycles']} (завершено {s['completed_blocks']}, идёт {s['open_blocks']}) · "
            f"предварительных расчётов: {s['estimates']} · начислений на проверке: {s['review_required']}"
        )
        self.stdout.write(f"{'Месяц':<9}{'Начислено':>12}{'Выплачено':>12}{'Остаток':>12}{'Ждёт утв.':>12}"
                          f"{'Переводы':>12}{'С ошибкой':>11}")
        for m, row in s["months"].items():
            self.stdout.write(f"{m:<9}{row['accrued']:>12}{row['paid']:>12}{row['outstanding']:>12}"
                              f"{row['awaiting_approval']:>12}{row['cash_paid_in_month']:>12}{row['with_errors']:>11}")
        self.stdout.write(f"Остаток задолженности по набору: {s['total_outstanding']} сом")
        self.stdout.write(f"Проверки целостности: пройдены · отпечаток набора: {result['fingerprint']}")
