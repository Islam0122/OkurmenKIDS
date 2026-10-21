"""Журнал контактов бухгалтера с родителями и задачи по долгам.

Каждый контакт — новая запись (история не перезаписывается). Контакт
обновляет состояние задачи по начислению: дату следующего контакта,
обещанную дату оплаты, «спор по начислению». Закрывает задачу только
фактическая оплата (`invoices.refresh_invoice`) или аннулирование
начисления — запись «оплата получена» без денег задачу не закрывает.
"""
from __future__ import annotations

import datetime as dt

from django.db import transaction
from django.utils import timezone

from apps.accounting.services import audit

from ..models import BillingContactLog, BillingNotification, BillingTask, Invoice, StudentBillingProfile
from . import BillingError
from .invoices import lock_profile
from .notifications import notify

Result = BillingContactLog.Result


def register_billing_contact(*, profile: StudentBillingProfile, actor, channel: str, result: str, comment: str = "",
                             invoice: Invoice | None = None, contacted_at=None,
                             promised_payment_date: dt.date | None = None,
                             next_contact_date: dt.date | None = None) -> BillingContactLog:
    from ..permissions import authorize

    authorize(actor, "contact")
    if channel not in BillingContactLog.Channel.values:
        raise BillingError("Неизвестный тип контакта.", code="invalid")
    if result not in Result.values:
        raise BillingError("Неизвестный результат контакта.", code="invalid")
    if result == Result.PROMISED and promised_payment_date is None:
        raise BillingError("Укажите обещанную дату оплаты.", code="promise_date_required")
    contacted_at = contacted_at or timezone.now()
    if contacted_at > timezone.now() + dt.timedelta(minutes=5):
        raise BillingError("Время контакта не может быть в будущем.", code="bad_date")
    if result == Result.FOLLOW_UP and next_contact_date is None:
        raise BillingError("Укажите дату следующего контакта.", code="next_contact_required")
    with transaction.atomic():
        profile = lock_profile(profile)
        if invoice is not None and invoice.profile_id != profile.pk:
            raise BillingError("Начисление другого студента.", code="wrong_profile")
        tasks = BillingTask.objects.select_for_update().filter(profile=profile, status__in=BillingTask.LIVE_STATUSES)
        task = (tasks.filter(invoice=invoice) if invoice is not None else tasks.order_by("invoice__due_date")).first()
        if invoice is None and task is not None:
            invoice = task.invoice
        log = BillingContactLog.objects.create(
            profile=profile, student_id=profile.student_id, invoice=invoice, task=task, staff=actor,
            contacted_at=contacted_at, channel=channel, result=result, comment=comment or "",
            promised_payment_date=promised_payment_date, next_contact_date=next_contact_date,
        )
        if task is not None:
            task.last_contact_at = contacted_at
            if next_contact_date:
                task.next_contact_date = next_contact_date
            if result == Result.PROMISED:
                task.status, task.promised_date = BillingTask.Status.PROMISED, promised_payment_date
                task.next_contact_date = next_contact_date or promised_payment_date + dt.timedelta(days=1)
            elif result == Result.DISPUTE:
                task.status = BillingTask.Status.DISPUTE
            if task.assignee_id is None:
                task.assignee = actor
            task.save()
        audit.log(actor, log, "billing_contact", new={
            "profile": profile.pk, "invoice": getattr(invoice, "pk", None), "channel": channel, "result": result,
            "promised_payment_date": promised_payment_date, "next_contact_date": next_contact_date,
        })
    return log


def follow_up_due(on: dt.date | None = None) -> list[int]:
    """Задачи, по которым пора связаться повторно: наступила дата
    следующего контакта или прошла обещанная дата без оплаты.
    Уведомление — одно на задачу и день (повторный запуск не дублирует)."""
    on = on or timezone.localdate()
    due = BillingTask.objects.filter(status__in=BillingTask.LIVE_STATUSES, next_contact_date__lte=on).select_related(
        "profile__student", "invoice",
    )
    ids = []
    for task in due:
        broken = task.status == BillingTask.Status.PROMISED and task.promised_date and task.promised_date < on
        notify(
            BillingNotification.Kind.FOLLOW_UP, f"followup:{task.pk}:{on.isoformat()}",
            f"{'Обещание не выполнено' if broken else 'Повторный контакт'}: {task.profile.student}",
            f"Начисление {task.invoice.number}, остаток {task.invoice.balance} сом.",
            recipient=task.assignee, profile=task.profile, invoice=task.invoice,
        )
        ids.append(task.pk)
    return ids
