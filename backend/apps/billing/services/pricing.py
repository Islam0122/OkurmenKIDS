"""Тарифы и расчёт стоимости пакета.

Стоимость пакета = (индивидуальная цена или цена версии тарифа на дату)
− скидка (процент или фиксированная сумма). Результат — снимок, который
пакет и начисление хранят у себя: изменение тарифа или условий студента
не меняет уже созданных пакетов и начислений."""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.db.models import Q

from apps.accounting.services import audit
from apps.accounting.services.money import money

from ..models import BillingPlan, BillingPlanVersion, DiscountType
from . import BillingError

ZERO = Decimal("0.00")
PLAN_SETTINGS = (
    "name", "subject", "course", "payment_due_days", "warn_before_end_lessons", "early_invoice_enabled",
    "early_invoice_after_lessons", "absence_policy", "is_active",
)


def _decimal(value, field: str) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except Exception:  # noqa: BLE001
        raise BillingError(f"Некорректное число: {field}.", code="invalid_amount")


def discount_for(price: Decimal, discount_type: str, discount_value) -> Decimal:
    value = Decimal(discount_value or 0)
    if discount_type == DiscountType.PERCENT:
        return money(Decimal(price) * value / 100)
    if discount_type == DiscountType.FIXED:
        return money(value)
    return ZERO


def validate_terms(*, custom_price, discount_type: str, discount_value, base_price=None) -> tuple:
    """Проверить цену и скидку; вернуть нормализованные (custom_price,
    discount_type, discount_value). Отрицательные суммы, скидка > 100 % и
    скидка больше цены запрещены."""
    custom = _decimal(custom_price, "индивидуальная цена")
    discount_type = discount_type or DiscountType.NONE
    if discount_type not in DiscountType.values:
        raise BillingError("Неизвестный тип скидки.", code="invalid_discount")
    value = _decimal(discount_value, "скидка") or ZERO
    if custom is not None and custom <= 0:
        raise BillingError("Индивидуальная цена должна быть больше нуля.", code="invalid_amount")
    if value < 0:
        raise BillingError("Скидка не может быть отрицательной.", code="invalid_discount")
    if discount_type == DiscountType.NONE:
        value = ZERO
    elif value == 0:
        raise BillingError("Укажите размер скидки.", code="invalid_discount")
    if discount_type == DiscountType.PERCENT and value > 100:
        raise BillingError("Скидка не может быть больше 100 %.", code="invalid_discount")
    price = custom if custom is not None else (Decimal(base_price) if base_price is not None else None)
    if discount_type == DiscountType.FIXED and price is not None and value > price:
        raise BillingError("Скидка больше стоимости пакета.", code="invalid_discount")
    return custom, discount_type, money(value)


# ---------------------------------------------------------------------------
# Версии тарифа
# ---------------------------------------------------------------------------

def plan_version_on(plan: BillingPlan, day: dt.date) -> BillingPlanVersion:
    versions = BillingPlanVersion.objects.filter(plan=plan)
    version = versions.filter(effective_from__lte=day).filter(
        Q(effective_to__isnull=True) | Q(effective_to__gte=day)
    ).order_by("-effective_from").first()
    # До первой версии действует первая (тариф заведён позже начала учёта).
    version = version or versions.order_by("effective_from").first()
    if version is None:
        raise BillingError(f"У тарифа «{plan}» не задана цена.", code="no_price")
    return version


@dataclass(frozen=True)
class PriceQuote:
    version: BillingPlanVersion
    lessons: int
    base_price: Decimal
    custom_price: Decimal | None
    discount_type: str
    discount_value: Decimal
    discount_amount: Decimal
    final_price: Decimal

    def snapshot(self) -> dict:
        return {
            "plan": self.version.plan.name, "plan_id": self.version.plan_id, "plan_version": self.version.pk,
            "lessons": self.lessons, "base_price": str(self.base_price),
            "custom_price": None if self.custom_price is None else str(self.custom_price),
            "discount_type": self.discount_type, "discount_value": str(self.discount_value),
            "discount_amount": str(self.discount_amount), "final_price": str(self.final_price),
        }


def calculate_package_price(*, plan: BillingPlan, on_date: dt.date, custom_price=None,
                            discount_type: str = DiscountType.NONE, discount_value=ZERO) -> PriceQuote:
    version = plan_version_on(plan, on_date)
    base = version.package_price
    custom, discount_type, value = validate_terms(
        custom_price=custom_price, discount_type=discount_type, discount_value=discount_value, base_price=base,
    )
    price = custom if custom is not None else base
    discount = min(discount_for(price, discount_type, value), price)
    return PriceQuote(
        version=version, lessons=version.lessons_per_package, base_price=base, custom_price=custom,
        discount_type=discount_type, discount_value=value, discount_amount=discount, final_price=money(price - discount),
    )


def quote_for_profile(profile, on_date: dt.date) -> PriceQuote:
    return calculate_package_price(
        plan=profile.plan, on_date=on_date, custom_price=profile.custom_price,
        discount_type=profile.discount_type, discount_value=profile.discount_value,
    )


# ---------------------------------------------------------------------------
# Управление тарифами (администратор оплаты)
# ---------------------------------------------------------------------------

def _validate_plan_settings(data: dict, lessons: int | None = None):
    if data.get("early_invoice_enabled") and not data.get("early_invoice_after_lessons"):
        raise BillingError("Укажите, после какого урока выставлять начисление заранее.", code="invalid_plan")
    after = data.get("early_invoice_after_lessons")
    if after and lessons and after >= lessons:
        raise BillingError("Начисление заранее — раньше последнего урока пакета.", code="invalid_plan")


def create_plan(*, actor, name: str, lessons_per_package: int, package_price, effective_from: dt.date,
                reason: str = "Новый тариф", **settings) -> BillingPlan:
    from ..permissions import authorize

    authorize(actor, "manage_plans")
    _validate_plan_settings(settings, lessons_per_package)
    with transaction.atomic():
        try:
            with transaction.atomic():
                plan = BillingPlan.objects.create(name=name.strip(), created_by=actor, **settings)
        except IntegrityError:
            raise BillingError("Тариф с таким названием уже есть.", code="duplicate")
        add_plan_version(plan, actor=actor, lessons_per_package=lessons_per_package, package_price=package_price,
                         effective_from=effective_from, reason=reason)
        audit.log(actor, plan, "billing_plan_create", new={k: getattr(plan, k + "_id", None) if k in ("subject", "course")
                                                            else getattr(plan, k) for k in PLAN_SETTINGS})
    return plan


def update_plan_settings(plan: BillingPlan, *, actor, **changes) -> BillingPlan:
    from ..permissions import authorize

    authorize(actor, "manage_plans")
    with transaction.atomic():
        plan = BillingPlan.objects.select_for_update().get(pk=plan.pk)
        merged = {k: getattr(plan, k) for k in PLAN_SETTINGS} | changes
        _validate_plan_settings(merged, plan_version_on(plan, dt.date.today()).lessons_per_package)
        old = {k: getattr(plan, k) for k in changes}
        for key, value in changes.items():
            setattr(plan, key, value)
        plan.save()
        audit.log(actor, plan, "billing_plan_update", old=old, new=changes)
    return plan


def add_plan_version(plan: BillingPlan, *, actor, lessons_per_package: int, package_price, effective_from: dt.date,
                     reason: str) -> BillingPlanVersion:
    """Новая цена / размер пакета с даты. Прежняя версия закрывается днём
    раньше; уже созданные пакеты и начисления не меняются (у них снимок)."""
    from ..permissions import authorize

    authorize(actor, "manage_plans")
    reason = (reason or "").strip()
    if not reason:
        raise BillingError("Укажите основание изменения тарифа.", code="reason_required")
    price = _decimal(package_price, "стоимость пакета")
    if price is None or price <= 0:
        raise BillingError("Стоимость пакета должна быть больше нуля.", code="invalid_amount")
    if not lessons_per_package or int(lessons_per_package) <= 0:
        raise BillingError("Число уроков в пакете должно быть больше нуля.", code="invalid_lessons")
    with transaction.atomic():
        plan = BillingPlan.objects.select_for_update().get(pk=plan.pk)
        after = plan.early_invoice_after_lessons
        if plan.early_invoice_enabled and after and after >= int(lessons_per_package):
            raise BillingError("Порог раннего начисления должен быть меньше уроков в пакете.", code="invalid_plan")
        latest = BillingPlanVersion.objects.filter(plan=plan).order_by("-effective_from").first()
        if latest is not None and effective_from <= latest.effective_from:
            raise BillingError(
                f"Новая версия должна начинаться позже действующей (с {latest.effective_from:%d.%m.%Y}).",
                code="bad_date",
            )
        if latest is not None:
            BillingPlanVersion.objects.filter(pk=latest.pk).update(effective_to=effective_from - dt.timedelta(days=1))
        version = BillingPlanVersion.objects.create(
            plan=plan, lessons_per_package=int(lessons_per_package), package_price=money(price),
            effective_from=effective_from, reason=reason, previous_version=latest,
            created_by=actor if getattr(actor, "is_authenticated", False) else None,
        )
        audit.log(actor, version, "billing_plan_price", old={
            "package_price": latest.package_price if latest else None,
            "lessons_per_package": latest.lessons_per_package if latest else None,
        }, new={"plan": plan.pk, "package_price": version.package_price, "lessons_per_package": version.lessons_per_package,
                "effective_from": effective_from}, reason=reason)
    return version
