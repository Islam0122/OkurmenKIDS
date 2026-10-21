"""Глобальные настройки оплаты (`BillingSettings`): меняет бухгалтер,
каждое изменение — в журнале аудита."""
from __future__ import annotations

from django.db import transaction

from apps.accounting.services import audit

from ..models import BillingSettings

FIELDS = ("manager_max_discount_percent", "due_soon_lessons", "default_deadline_lessons", "accountant_refund_limit",
          "academy_name", "academy_details", "receipt_footer")


def update_settings(*, actor, **changes) -> BillingSettings:
    from ..permissions import authorize
    from . import BillingError

    authorize(actor, "manage_settings")
    unknown = set(changes) - set(FIELDS)
    if unknown:
        raise BillingError(f"Неизвестные настройки: {', '.join(sorted(unknown))}.", code="invalid")
    with transaction.atomic():
        BillingSettings.load()
        obj = BillingSettings.objects.select_for_update().get(pk=1)
        old = {k: getattr(obj, k) for k in changes}
        for key, value in changes.items():
            setattr(obj, key, value)
        obj.updated_by = actor
        obj.full_clean()
        obj.save()
        audit.log(actor, obj, "billing_settings_update", old=old, new=changes)
    return obj
