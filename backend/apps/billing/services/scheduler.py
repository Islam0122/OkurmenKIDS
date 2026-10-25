"""Периодические задачи LMS одним запуском — для Railway Cron
(`manage.py run_scheduled_tasks`) и для Celery Beat (`billing.run_daily`).

Что запускается (по порядку, сбой одной задачи не останавливает остальные):

* оплата обучения — `tasks.DAILY`: списание проведённых уроков (подстраховка
  сигналов), следующие учебные месяцы и ранние начисления, напоминания о
  конце пакета, распределение аванса на наступившие начисления, просрочки,
  повторные контакты, доставка уведомлений;
* снимок финансового отчёта и сверка — один раз в сутки (по дате проекта,
  Asia/Bishkek), повторные запуски в тот же день его не перестраивают;
* посещаемость сотрудников — закрыть открытые сессии прошлых дней.

Защита от повторной обработки:

* **один запуск за раз** — аренда в базе (`BillingEvent` с ключом
  `scheduler:lock`): запись захватывается одним атомарным UPDATE; второй
  запуск, пока первый работает, ничего не делает и завершается с кодом 0;
  аренда, не снятая из-за падения процесса, истекает через `LEASE`;
* **повтор в тот же день безопасен** — у каждой задачи свои блокировки и
  уникальные ключи (пакет, начисление, уведомление, задача), см. `tasks.py`;
* **миграции не применены** (деплой ещё идёт) — запуск пропускается;
  в базе нет ни одной миграции (не та база: например, не задан
  `DJANGO_ENV=production` и подключилась пустая SQLite) — ошибка, код 1;
* **аренда продлевается** перед каждой задачей, поэтому долгий запуск не
  теряет её, а аренда упавшего процесса истекает через `LEASE` после
  последнего продления.
"""
from __future__ import annotations

import datetime as dt
import logging
import uuid

from django.db import DEFAULT_DB_ALIAS, connections
from django.db.migrations.executor import MigrationExecutor
from django.db.migrations.recorder import MigrationRecorder
from django.utils import timezone

from ..models import BillingEvent

logger = logging.getLogger(__name__)

LOCK_KEY = "scheduler:lock"
LEASE = dt.timedelta(minutes=25)  # дольше одного запуска, короче интервала cron (30 мин)


def pending_migrations() -> list[str]:
    connection = connections[DEFAULT_DB_ALIAS]
    executor = MigrationExecutor(connection)
    plan = executor.migration_plan(executor.loader.graph.leaf_nodes())
    return [f"{migration.app_label}.{migration.name}" for migration, _backwards in plan]


def schema_missing() -> bool:
    """В базе нет таблицы миграций — значит, это не рабочая база проекта."""
    return not MigrationRecorder(connections[DEFAULT_DB_ALIAS]).has_table()


def acquire(run_id: uuid.UUID, *, now: dt.datetime | None = None) -> bool:
    """Захватить аренду: свободна, снята или истекла — атомарный UPDATE."""
    now = now or timezone.now()
    BillingEvent.objects.get_or_create(key=LOCK_KEY, defaults={"kind": "scheduler", "status": BillingEvent.Status.DONE})
    taken = (BillingEvent.objects.filter(key=LOCK_KEY)
             .exclude(status=BillingEvent.Status.PROCESSING, updated_at__gt=now - LEASE)
             .update(status=BillingEvent.Status.PROCESSING, run_id=run_id, updated_at=now, error=""))
    return taken == 1


def renew(run_id: uuid.UUID) -> None:
    BillingEvent.objects.filter(key=LOCK_KEY, run_id=run_id, status=BillingEvent.Status.PROCESSING).update(
        updated_at=timezone.now())


def release(run_id: uuid.UUID, *, result: dict, failed: bool) -> None:
    BillingEvent.objects.filter(key=LOCK_KEY, run_id=run_id).update(
        status=BillingEvent.Status.FAILED if failed else BillingEvent.Status.DONE,
        result=result, processed_at=timezone.now(), updated_at=timezone.now(),
        error="; ".join(k for k, v in result.get("tasks", {}).items() if isinstance(v, dict) and "error" in v)[:2000],
    )


def _report_done_today(on: dt.date) -> bool:
    return BillingEvent.objects.filter(key=f"task:build_financial_report:{on.isoformat()}",
                                       status=BillingEvent.Status.DONE).exists()


def run_all(*, on: dt.date | None = None, report: bool = True, staff_attendance: bool = True) -> dict:
    """Один запуск всех периодических задач (см. модуль). Возвращает
    {"status": done | skipped_locked | skipped_migrations | no_schema,
    "tasks": {...}, "failed": bool}."""
    from .. import tasks

    if schema_missing():
        logger.error("scheduler: database has no migrations table — wrong database or DJANGO_ENV")
        return {"status": "no_schema", "tasks": {}, "failed": True}
    pending = pending_migrations()
    if pending:
        logger.warning("scheduler: migrations pending, skip: %s", pending)
        return {"status": "skipped_migrations", "pending": pending, "tasks": {}, "failed": False}
    run_id = uuid.uuid4()
    if not acquire(run_id):
        logger.warning("scheduler: previous run still in progress, skip")
        return {"status": "skipped_locked", "tasks": {}, "failed": False}
    on = on or timezone.localdate()
    results: dict = {}
    try:
        results.update(tasks.run_daily_tasks(on=on, before_each=lambda: renew(run_id)))
        renew(run_id)
        if report and not _report_done_today(on):
            results["build_financial_report"] = _safe(
                lambda: {"problems": len(tasks.build_financial_report(on=on)["reconcile_problems"])}, "report")
        if staff_attendance:
            renew(run_id)
            from apps.staff_attendance.services.marking import close_stale_sessions

            results["staff_attendance_close_stale"] = _safe(lambda: {"closed": close_stale_sessions()}, "staff")
        renew(run_id)
        # Регулярные расходы компании: один неоплаченный расход на шаблон и
        # месяц (уникальный индекс) — повтор в тот же день ничего не создаёт.
        from apps.accounting.services.expenses import generate_recurring

        results["recurring_expenses"] = _safe(
            lambda: {"created": len(generate_recurring(on.year, on.month)["created"])}, "recurring_expenses")
    finally:
        failed = any(isinstance(v, dict) and "error" in v for v in results.values())
        summary = {"status": "done", "on": on.isoformat(), "run_id": str(run_id), "tasks": results, "failed": failed}
        release(run_id, result=summary, failed=failed)
    return summary


def _safe(func, name: str) -> dict:
    try:
        return func()
    except Exception as exc:
        logger.exception("scheduler task %s failed", name)
        return {"error": str(exc)}


__all__ = ["LEASE", "LOCK_KEY", "acquire", "pending_migrations", "release", "renew", "run_all", "schema_missing"]
