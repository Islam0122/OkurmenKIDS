"""Фоновые задачи оплаты обучения (Celery).

Задачи только инициируют проверку и обработку — всю работу делают
сервисы, а защиту от дублей дают блокировки профиля и уникальные
бизнес-ключи (пакет `profile+number`, одно начисление на пакет, `dedup_key`
уведомлений). Поэтому повторный запуск, ретрай после сбоя или два
параллельных воркера Beat не создают повторных начислений, списаний и
уведомлений.

Каждый запуск пишется в журнал обработки событий (`BillingEvent`): ключ
задачи и дня, попытки, результат или ошибка.

Celery в проекте необязателен: без брокера (`CELERY_BROKER_URL` пуст)
задачи выполняются синхронно (`CELERY_TASK_ALWAYS_EAGER`), а для cron
хостинга есть `python manage.py billing_autorun` — тот же набор задач.
"""
from __future__ import annotations

import datetime as dt
import functools
import logging

from django.conf import settings
from django.db import transaction
from django.db.models import F, Q
from django.utils import timezone

from .models import BillingEvent, Invoice, LessonPackage, StudentBillingProfile
from .services import BillingError

logger = logging.getLogger(__name__)

try:  # pragma: no cover — зависит от окружения
    from celery import shared_task
except ImportError:  # pragma: no cover
    def shared_task(*dargs, **dkwargs):
        def wrap(func):
            func.delay = func
            func.apply_async = lambda args=(), kwargs=None, **_: func(*args, **(kwargs or {}))
            return func
        return wrap(dargs[0]) if dargs and callable(dargs[0]) else wrap


def tracked(kind: str):
    """Записать запуск в `BillingEvent` (ключ — задача и день)."""
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            on = kwargs.get("on") or timezone.localdate()
            key = f"task:{kind}:{on.isoformat()}"
            event, _ = BillingEvent.objects.get_or_create(key=key, defaults={"kind": kind})
            BillingEvent.objects.filter(pk=event.pk).update(
                status=BillingEvent.Status.PROCESSING, attempts=F("attempts") + 1, updated_at=timezone.now(),
            )
            try:
                result = func(*args, **kwargs)
            except Exception as exc:
                BillingEvent.objects.filter(pk=event.pk).update(
                    status=BillingEvent.Status.FAILED, error=str(exc)[:2000], updated_at=timezone.now(),
                )
                raise
            BillingEvent.objects.filter(pk=event.pk).update(
                status=BillingEvent.Status.DONE, result=result if isinstance(result, dict) else {"result": result},
                error="", processed_at=timezone.now(), updated_at=timezone.now(),
            )
            return result
        return wrapper
    return decorator


def _date(value) -> dt.date:
    if value is None:
        return timezone.localdate()
    return value if isinstance(value, dt.date) else dt.date.fromisoformat(str(value))


RETRY = {"autoretry_for": (Exception,), "retry_backoff": True, "retry_kwargs": {"max_retries": 3}}


@shared_task(name="billing.process_completed_lessons", **RETRY)
def process_completed_lessons(on=None, days: int | None = None) -> dict:
    """Подстраховка сигналов: списать проведённые и сторнировать отменённые
    уроки за последние дни."""
    from .services.lessons import sync_recent_lessons

    on = _date(on)
    days = days if days is not None else int(getattr(settings, "BILLING_SYNC_LOOKBACK_DAYS", 14))
    return tracked("process_completed_lessons")(lambda on: sync_recent_lessons(days=days, on=on))(on=on)


@shared_task(name="billing.check_packages_ending", **RETRY)
def check_packages_ending(on=None) -> dict:
    """Уведомить о пакетах, которые скоро закончатся (если уведомление ещё
    не отправлено при списании урока)."""
    from .models import BillingNotification
    from .services.notifications import notify

    def run(on):
        sent = 0
        packages = LessonPackage.objects.filter(status=LessonPackage.Status.ACTIVE, ending_notified_at__isnull=True)
        packages = packages.select_related("profile__plan", "profile__student")
        for package in packages:
            warn = package.profile.plan.warn_before_end_lessons
            if not warn or not (0 < package.lessons_remaining <= warn):
                continue
            with transaction.atomic():
                locked = LessonPackage.objects.select_for_update().get(pk=package.pk)
                if locked.ending_notified_at is not None:
                    continue
                locked.ending_notified_at = timezone.now()
                locked.save(update_fields=["ending_notified_at", "updated_at"])
                profile = package.profile
                notify(
                    BillingNotification.Kind.PACKAGE_ENDING, f"ending:{package.pk}",
                    f"Пакет скоро закончится: {profile.student}",
                    f"Пакет №{package.number}: осталось {locked.lessons_remaining} из {locked.lessons_total}.",
                    recipient=profile.responsible_accountant, profile=profile,
                )
                sent += 1
        return {"notified": sent}

    return tracked("check_packages_ending")(run)(on=_date(on))


@shared_task(name="billing.process_completed_packages", **RETRY)
def process_completed_packages(on=None) -> dict:
    """Завершённые пакеты без следующего пакета у продолжающих студентов —
    создать следующий платёжный цикл (например, после паузы сигнал не
    сработал). Повтор ничего не дублирует: сервис проверяет следующий пакет
    под блокировкой профиля."""
    from .services.invoices import create_next_package_invoice

    def run(on):
        created = 0
        live = Q(packages__status__in=(LessonPackage.Status.ACTIVE, LessonPackage.Status.PLANNED))
        profiles = StudentBillingProfile.objects.filter(
            status=StudentBillingProfile.Status.ACTIVE, student__status="active",
            packages__status=LessonPackage.Status.COMPLETED,
        ).exclude(live).distinct()
        for profile in profiles:
            try:
                _package, _invoice, was_created = create_next_package_invoice(profile, on_date=on, activate=True)
            except BillingError as exc:
                logger.warning("billing: next package for profile %s: %s", profile.pk, exc.message)
                continue
            created += int(was_created)
        return {"created": created}

    return tracked("process_completed_packages")(run)(on=_date(on))


@shared_task(name="billing.create_early_invoices", **RETRY)
def create_early_invoices(on=None) -> dict:
    """Раннее начисление по настройке тарифа (например, после 9-го из 12
    уроков) — для пакетов, где порог пройден, а следующего пакета нет."""
    from .services.invoices import create_next_package_invoice, is_continuing, next_planned_package

    def run(on):
        created = 0
        packages = LessonPackage.objects.filter(
            status=LessonPackage.Status.ACTIVE, profile__plan__early_invoice_enabled=True,
            profile__status=StudentBillingProfile.Status.ACTIVE,
            lessons_used__gte=F("profile__plan__early_invoice_after_lessons"),
        ).select_related("profile__plan", "profile__student")
        for package in packages:
            profile = package.profile
            if not is_continuing(profile) or next_planned_package(profile) is not None:
                continue
            _package, _invoice, was_created = create_next_package_invoice(profile, on_date=on, activate=False)
            created += int(was_created)
        return {"created": created}

    return tracked("create_early_invoices")(run)(on=_date(on))


@shared_task(name="billing.apply_credit_to_due_invoices", **RETRY)
def apply_credit_to_due_invoices(on=None) -> dict:
    """Платёжное событие «наступил срок оплаты»: доступный аванс (например,
    оплаченная бронь) покрывает начисления, срок которых наступил."""
    from .services.ledger import credit_balance
    from .services.payments import apply_available_credit

    def run(on):
        applied = 0
        profile_ids = set(Invoice.objects.filter(status__in=Invoice.UNPAID_STATUSES, due_date__lte=on)
                          .values_list("profile_id", flat=True))
        for profile_id in sorted(profile_ids):
            if credit_balance(profile_id) <= 0:
                continue
            applied += len(apply_available_credit(StudentBillingProfile(pk=profile_id), system=True))
        return {"allocations": applied}

    return tracked("apply_credit_to_due_invoices")(run)(on=_date(on))


@shared_task(name="billing.mark_overdue_invoices", **RETRY)
def mark_overdue_invoices(on=None) -> dict:
    from .services.invoices import mark_overdue_invoices as mark

    return tracked("mark_overdue_invoices")(lambda on: {"overdue": mark(on)})(on=_date(on))


@shared_task(name="billing.follow_up_contacts", **RETRY)
def follow_up_contacts(on=None) -> dict:
    from .services.contacts import follow_up_due

    return tracked("follow_up_contacts")(lambda on: {"tasks": follow_up_due(on)})(on=_date(on))


@shared_task(name="billing.notify_accountants", **RETRY)
def notify_accountants(on=None) -> dict:
    from .services.notifications import dispatch_pending

    return tracked("notify_accountants")(lambda on: {"sent": dispatch_pending()})(on=_date(on))


@shared_task(name="billing.build_financial_report", **RETRY)
def build_financial_report(on=None) -> dict:
    """Ежедневный снимок отчёта (месяц по `on`) — в журнале событий под
    ключом задачи и дня; повтор в тот же день перезаписывает снимок."""
    from .services.reports import financial_report, reconcile

    def run(on):
        report = financial_report({}, date_from=on.replace(day=1), date_to=on)
        report["reconcile_problems"] = reconcile()
        return report

    return tracked("build_financial_report")(run)(on=_date(on))


DAILY = (
    process_completed_lessons, process_completed_packages, create_early_invoices, check_packages_ending,
    apply_credit_to_due_invoices, mark_overdue_invoices, follow_up_contacts, notify_accountants,
)


@shared_task(name="billing.run_daily")
def run_daily(on=None, report: bool = True) -> dict:
    """Все проверки дня по порядку (Celery Beat или `billing_autorun`)."""
    on = _date(on)
    results = {}
    for task in DAILY:
        try:
            results[task.__name__] = task(on=on)
        except Exception as exc:  # noqa: BLE001 — сбой одной проверки не останавливает остальные
            logger.exception("billing task %s failed", task.__name__)
            results[task.__name__] = {"error": str(exc)}
    if report:
        results["build_financial_report"] = {"problems": len(build_financial_report(on=on)["reconcile_problems"])}
    return results
