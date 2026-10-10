"""Ежедневная автоматизация зарплат (Celery в проекте нет — запускается по
cron / планировщику хостинга, например раз в день в 06:00 Asia/Bishkek):

    python manage.py payroll_autorun [--calculate] [--date YYYY-MM-DD]

1. Обновляет прогресс циклов и фиксирует завершённые (начисления за них
   создаются сразу, идемпотентно; спорные — в статусе «Требует проверки»).
2. С `--calculate` создаёт периоды текущего месяца и рассчитывает (только
   черновые и рассчитанные, не утверждённые) расчёты: оклады — в периоде
   «Весь месяц», процент — в текущей половине месяца. Утверждение остаётся
   за директором.
3. Печатает ближайшие и просроченные плановые выплаты.

Повторный запуск ничего не дублирует: уникальность циклов, начислений,
периодов и расчётов гарантируют ограничения БД, а не планировщик.
"""
import datetime as dt

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.accounting.models import PayrollPeriod
from apps.accounting.services import analytics
from apps.accounting.services.cycles import sync_all
from apps.accounting.services.payroll_calculator import calculate_period
from apps.accounting.services.periods import get_or_create_period


class Command(BaseCommand):
    help = "Идемпотентная автоматизация зарплат: циклы, (опционально) расчёт текущих периодов, плановые выплаты."

    def add_arguments(self, parser):
        parser.add_argument("--calculate", action="store_true", help="Рассчитать текущие периоды (без утверждения).")
        parser.add_argument("--date", type=dt.date.fromisoformat, default=None, help="Дата запуска (по умолчанию сегодня).")

    def handle(self, *args, calculate=False, date=None, **options):
        today = date or timezone.localdate()
        self.stdout.write(f"Новых завершённых циклов: {sync_all()}")
        if calculate:
            half = PayrollPeriod.PeriodType.FIRST_HALF if today.day <= 15 else PayrollPeriod.PeriodType.SECOND_HALF
            for period_type in (PayrollPeriod.PeriodType.MONTH, half):
                period, _ = get_or_create_period(today.year, today.month, period_type, None)
                if period.status == PayrollPeriod.Status.CLOSED:
                    continue
                result = calculate_period(period, None)
                self.stdout.write(
                    f"{period}: рассчитано {len(result['calculated'])}, пропущено {len(result['skipped'])}, "
                    f"ошибок {len(result['failed'])}"
                )
        for row in analytics.upcoming_payments(today=today, limit=50):
            mark = "ПРОСРОЧЕНО " if row["is_overdue"] else ""
            planned = row["planned_payment_date"]
            self.stdout.write(
                f"{mark}{planned:%d.%m.%Y} · {row['employee_name']} · {row['period_label']} · остаток {row['due']} сом"
                if planned else f"дата не настроена · {row['employee_name']} · остаток {row['due']} сом"
            )
