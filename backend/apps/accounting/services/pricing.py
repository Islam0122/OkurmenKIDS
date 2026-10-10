"""История тарифов курса: стоимость обучения одного студента за месяц.

Новая цена — новая версия `CoursePriceVersion` с датой начала и причиной;
предыдущая закрывается днём раньше, ничего не перезаписывается. Цикл берёт
цену, действовавшую на дату своего завершения, и хранит её снимок, поэтому
новый тариф не меняет уже созданных начислений.

Правила:
* Первый тариф курса действует и на более раннюю историю (до введения
  истории тарифов у курса была одна цена — так же считались и старые циклы).
* Ввести тариф задним числом на дату, когда у курса уже есть завершённый
  цикл, нельзя: история тарифов разошлась бы со снимками начислений.
  Исправление уже начисленного — корректировкой расчёта.
* Пока у курса нет ни одной версии (данные до миграции), действует
  `CoursePayrollSettings.price_per_student`.
"""
from __future__ import annotations

import datetime as dt
from decimal import Decimal

from django.db import transaction
from django.db.models import Max, Q
from django.utils import timezone

from ..models import CourseCycle, CoursePayrollSettings, CoursePriceVersion
from . import AccountingError, audit

VERSION_FIELDS = ("price_per_student", "effective_from", "effective_to", "reason")


def price_version_on(course_id: int, day: dt.date) -> CoursePriceVersion | None:
    versions = CoursePriceVersion.objects.filter(course_id=course_id)
    covering = versions.filter(effective_from__lte=day).filter(
        Q(effective_to__isnull=True) | Q(effective_to__gte=day)
    ).order_by("-effective_from").first()
    if covering is not None:
        return covering
    return versions.order_by("effective_from").first()


def price_on(settings: CoursePayrollSettings, day: dt.date) -> Decimal:
    version = price_version_on(settings.course_id, day)
    return version.price_per_student if version is not None else settings.price_per_student


def set_price(*, course, price_per_student: Decimal, effective_from: dt.date, reason: str, actor,
              is_migrated: bool = False) -> CoursePriceVersion:
    reason = (reason or "").strip()
    if not reason:
        raise AccountingError("Укажите причину изменения стоимости.", code="reason_required")
    price = Decimal(price_per_student)
    if price <= 0:
        raise AccountingError("Стоимость должна быть больше нуля.", code="invalid_amount")
    with transaction.atomic():
        settings = CoursePayrollSettings.objects.select_for_update().filter(course=course).first()
        if settings is None:
            raise AccountingError("Сначала задайте настройки курса (уроков в цикле).", code="no_settings")
        latest = CoursePriceVersion.objects.select_for_update().filter(course=course).order_by("-effective_from").first()
        if latest is not None and effective_from <= latest.effective_from:
            raise AccountingError(
                f"Новый тариф должен начинаться позже действующего (с {latest.effective_from:%d.%m.%Y}).",
                code="bad_date",
            )
        last_completed = CourseCycle.objects.filter(
            course=course, status=CourseCycle.Status.COMPLETED,
        ).aggregate(d=Max("completed_on"))["d"]
        if latest is not None and last_completed and effective_from <= last_completed:
            raise AccountingError(
                f"Нельзя ввести тариф задним числом: цикл курса уже завершён {last_completed:%d.%m.%Y} по прежней "
                "цене. Укажите дату позже или исправьте начисление корректировкой.",
                code="retroactive",
            )
        if latest is not None:
            old = {"effective_to": latest.effective_to}
            latest.effective_to = effective_from - dt.timedelta(days=1)
            latest.save(update_fields=["effective_to"])
            audit.log(actor, latest, "close_version", old=old, new={"effective_to": latest.effective_to})
        version = CoursePriceVersion.objects.create(
            course=course, price_per_student=price, effective_from=effective_from, reason=reason,
            previous_version=latest, is_migrated=is_migrated,
            created_by=actor if getattr(actor, "is_authenticated", False) else None,
        )
        audit.log(actor, version, "price_change", old={
            "price_per_student": latest.price_per_student if latest else None,
            "effective_from": latest.effective_from if latest else None,
        }, new={"course": course.pk, **audit.snapshot(version, VERSION_FIELDS)}, reason=reason)
        # Зеркало в настройках — цена, действующая сегодня (для старых
        # клиентов); расчёт всегда берёт цену из истории на дату цикла.
        current = price_on(settings, timezone.localdate())
        if settings.price_per_student != current:
            CoursePayrollSettings.objects.filter(pk=settings.pk).update(price_per_student=current)
    return version
