"""Удаление ошибочно созданного платёжного профиля из бухгалтерии
(Django Admin → «Платёжные профили студентов» → «Удалить профиль из
бухгалтерии»). Только суперпользователь Django.

Удаляется ровно то, что принадлежит этому профилю: сам профиль и записи
`billing` / `accounting`, которые ссылаются на него (цены месяцев, история
условий, учебные месяцы и списания уроков в них, начисления и корректировки,
распределения, журнал аванса, брони, платежи профиля и их возвраты, чеки,
связи «платёж взамен», задачи, контакты, уведомления), — найдено по внешним
ключам, а не по имени студента. Студент, группа, расписание, уроки,
посещаемость, оценки и другие данные обучения не удаляются: ни одна модель
вне бухгалтерии не ссылается на эти записи (`maintenance.external_references`),
а количество записей всех таблиц вне бухгалтерии сверяется до и после.

Удаление останавливается (ничего не меняется), если:
* у профиля есть проведённый платёж или возврат — реальные деньги не должны
  исчезнуть из учёта: сначала сторно («Неправильные данные»), возврат или
  перенос на новый профиль платежом «взамен»;
* запись профиля связана с записью другого профиля (распределение на чужое
  начисление, перенесённая бронь, «взамен» платежа другого договора).

Перед удалением все строки целиком сохраняются в журнал аудита
(`billing_profile_purge`, `PayrollAuditLog` — он не удаляется): из этой копии
запись можно восстановить. Всё — в одной транзакции; после удаления
проверяется, что записей профиля не осталось, а другие таблицы не изменились,
иначе — откат.
"""
from __future__ import annotations

import hashlib
import json
from collections import defaultdict

from django.apps import apps as django_apps
from django.contrib.contenttypes.models import ContentType
from django.core import serializers
from django.db import connection, transaction

from apps.accounting.models import (
    DemoSeedRecord,
    PayrollAuditLog,
    StudentPayment,
    maintenance_delete,
)

from ..models import (
    BillingPlan,
    BillingPlanVersion,
    BillingSettings,
    StudentBillingProfile,
)
from . import BillingError

ACTION = "billing_profile_purge"
WARNING = ("Будет удалён бухгалтерский профиль ученика и связанные с ним бухгалтерские данные. Учебный профиль, "
           "зачисление, посещаемость, расписание, уроки и результаты обучения останутся без изменений. Действие "
           "повлияет на финансовую историю и отчёты")
# Общие для многих профилей / служебные — не принадлежат профилю.
_SHARED = (BillingPlan, BillingPlanVersion, BillingSettings, PayrollAuditLog, DemoSeedRecord)
_OWNER_FIELDS = ("profile", "billing_profile")


def is_allowed(user) -> bool:
    """Только активный суперпользователь Django — никакое разрешение или роль
    (бухгалтер, директор, staff) этого не заменяет."""
    return bool(user is not None and getattr(user, "is_active", False) and getattr(user, "is_superuser", False))


def _guard(actor) -> None:
    if not is_allowed(actor):
        raise BillingError("Удалить профиль из бухгалтерии может только суперпользователь.", code="forbidden")


def _models() -> list:
    return [m for app in ("billing", "accounting") for m in django_apps.get_app_config(app).get_models()
            if not m._meta.proxy and m not in _SHARED]


def _fks(model) -> list:
    return [f for f in model._meta.concrete_fields if f.is_relation and (f.many_to_one or f.one_to_one)]


def _owner(model, row) -> int | None:
    for name in _OWNER_FIELDS:
        field = next((f for f in model._meta.concrete_fields if f.name == name), None)
        if field is not None and field.related_model is StudentBillingProfile:
            return getattr(row, field.attname)
    return None


def _label(model, row) -> str:
    owner = _owner(model, row)
    who = f", профиль #{owner}" if owner else ""
    return f"{model._meta.verbose_name} #{row.pk}{who}"


def _collect(profile: StudentBillingProfile) -> tuple[dict, list[str]]:
    """{модель: {pk}} записей профиля и список связей с чужими записями.
    Запись входит в профиль, если ссылается на уже найденную запись и
    принадлежит этому профилю (или не принадлежит никакому — корректировка
    начисления, связь «взамен»); ссылка из записи другого профиля — конфликт."""
    models = _models()
    collected: dict = defaultdict(set)
    collected[StudentBillingProfile].add(profile.pk)
    foreign: list[str] = []
    changed = True
    while changed:
        changed = False
        for model in models:
            for field in _fks(model):
                target = field.related_model
                if target not in collected:
                    continue
                for row in model._base_manager.filter(**{f"{field.attname}__in": collected[target]}):
                    if row.pk in collected[model]:
                        continue
                    owner = _owner(model, row)
                    if owner not in (None, profile.pk):
                        foreign.append(f"{_label(model, row)} ссылается на {target._meta.verbose_name} профиля")
                        continue
                    collected[model].add(row.pk)
                    changed = True
    # Ссылки из записей профиля наружу — на записи бухгалтерии других профилей.
    scoped = set(models)
    for model, pks in list(collected.items()):
        for row in model._base_manager.filter(pk__in=pks):
            for field in _fks(model):
                value = getattr(row, field.attname)
                if value is not None and field.related_model in scoped and value not in collected[field.related_model]:
                    foreign.append(f"{_label(model, row)} → {field.related_model._meta.verbose_name} #{value} "
                                   "другого профиля")
    return {m: pks for m, pks in collected.items() if pks}, sorted(set(foreign))


def _real_money(collected: dict) -> list[dict]:
    rows = StudentPayment.objects.filter(pk__in=collected.get(StudentPayment, ()),
                                         status=StudentPayment.Status.CONFIRMED).select_related("receipt")
    out = []
    for p in rows.order_by("received_date", "pk"):
        receipt = getattr(p, "receipt", None)
        out.append({
            "id": p.pk, "kind": p.get_kind_display(), "amount": str(p.amount), "received_date": p.received_date,
            "receipt": receipt.number if receipt else None,
            "advice": ("Возврат проведён: если деньги действительно вернули — оставьте; ошибочный — отмените "
                       "возврат в «Неправильные данные»." if p.kind == StudentPayment.Kind.REFUND else
                       "Деньги не поступали — сторно в «Неправильные данные». Деньги получены — оформите "
                       "возврат, либо после создания нового профиля внесите их там платежом «взамен» этого "
                       "(сначала сторно здесь)."),
        })
    return out


def _fingerprint(collected: dict, payments: list[dict]) -> str:
    raw = json.dumps({m._meta.label: sorted(pks) for m, pks in collected.items()} | {"money": payments},
                     sort_keys=True, default=str)
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def preview(profile: StudentBillingProfile, *, actor) -> dict:
    """Что будет удалено и что мешает. Ничего не меняет."""
    _guard(actor)
    collected, foreign = _collect(profile)
    payments = _real_money(collected)
    external = _external_references()
    rows = [{"model": m._meta.verbose_name_plural, "label": m._meta.label, "count": len(pks)}
            for m, pks in sorted(collected.items(), key=lambda i: i[0]._meta.label)]
    payment_rows = [{
        "id": p.pk, "kind": p.get_kind_display(), "status": p.get_status_display(), "amount": p.amount,
        "received_date": p.received_date, "receipt": getattr(getattr(p, "receipt", None), "number", None),
    } for p in StudentPayment.objects.filter(pk__in=collected.get(StudentPayment, ())).select_related("receipt")
        .order_by("received_date", "pk")]
    return {
        "profile": profile, "student": profile.student, "warning": WARNING, "rows": rows,
        "total": sum(r["count"] for r in rows), "payments": payment_rows, "real_money": payments,
        "foreign": foreign, "external_references": external,
        "can_delete": not payments and not foreign and not external,
        "fingerprint": _fingerprint(collected, payments),
    }


def _external_references() -> list[str]:
    from apps.accounting.services.maintenance import external_references

    return external_references()


def _other_counts() -> dict:
    from apps.accounting.services.maintenance import other_app_counts

    return other_app_counts()


def _delete_leaves_first(collected: dict) -> None:
    """Удалить записи так, чтобы ни одна оставшаяся запись не ссылалась на
    удаляемую (PROTECT срабатывает только на ошибку порядка — откат)."""
    remaining = {m: set(pks) for m, pks in collected.items()}
    while any(remaining.values()):
        referenced: dict = defaultdict(set)
        for model, pks in remaining.items():
            if not pks:
                continue
            for field in _fks(model):
                if field.related_model in remaining:
                    for value in model._base_manager.filter(pk__in=pks).values_list(field.attname, flat=True):
                        if value is not None:
                            referenced[field.related_model].add(value)
        progress = False
        for model, pks in remaining.items():
            leaves = pks - referenced[model]
            if leaves:
                model._default_manager.filter(pk__in=leaves).delete()
                pks -= leaves
                progress = True
        if not progress:
            raise BillingError("Циклическая ссылка между записями профиля — удаление отменено.", code="cycle")


def purge(profile: StudentBillingProfile, *, actor, reason: str, fingerprint: str | None = None) -> dict:
    """Удалить профиль и его бухгалтерские записи. Возвращает {модель: удалено}."""
    _guard(actor)
    reason = (reason or "").strip()
    if not reason:
        raise BillingError("Укажите причину удаления.", code="reason_required")
    with transaction.atomic():
        profile = StudentBillingProfile.objects.select_for_update().select_related("student").get(pk=profile.pk)
        collected, foreign = _collect(profile)
        payments = _real_money(collected)
        if fingerprint is not None and fingerprint != _fingerprint(collected, payments):
            raise BillingError("Данные профиля изменились с момента просмотра — проверьте отчёт ещё раз.",
                               code="stale")
        if payments:
            raise BillingError("По профилю есть проведённые платежи или возвраты: "
                               + ", ".join(f"№{p['id']} {p['amount']} сом" for p in payments), code="real_money")
        if foreign:
            raise BillingError("Записи профиля связаны с другими профилями: " + "; ".join(foreign), code="foreign")
        if _external_references():
            raise BillingError("На бухгалтерию ссылаются модели других модулей — удаление остановлено.",
                               code="external")
        student_id, profile_id = profile.student_id, profile.pk
        snapshot = {m._meta.label: json.loads(serializers.serialize("json", m._base_manager.filter(pk__in=pks)))
                    for m, pks in collected.items()}
        counts = {m._meta.label: len(pks) for m, pks in collected.items()}
        scoped_before = {m._meta.label: m._base_manager.count() for m in _models()}
        others_before = _other_counts()
        demo = DemoSeedRecord.objects.none()
        for model, pks in collected.items():
            ct = ContentType.objects.get_for_model(model, for_concrete_model=False)
            demo = demo | DemoSeedRecord.objects.filter(content_type=ct, object_id__in=pks)
        with maintenance_delete():
            demo_deleted = demo.delete()[0]
            _delete_leaves_first(collected)
        left = {m._meta.label: n for m, pks in collected.items() if (n := m._base_manager.filter(pk__in=pks).count())}
        if left:
            raise BillingError(f"Удаление не завершено, остались записи: {left}. Изменения отменены.")
        expected = {label: n - counts.get(label, 0) for label, n in scoped_before.items()}
        if {m._meta.label: m._base_manager.count() for m in _models()} != expected:
            raise BillingError("Удаление затронуло записи других профилей. Изменения отменены.")
        changed = sorted(k for k, v in _other_counts().items() if others_before.get(k) != v)
        if changed:
            raise BillingError(f"Удаление изменило данные обучения или других модулей ({changed}). Изменения отменены.")
        if connection.vendor == "sqlite":
            connection.check_constraints()  # PostgreSQL проверяет внешние ключи сам
        PayrollAuditLog.objects.create(
            actor=actor, entity_type=StudentBillingProfile._meta.model_name, entity_id=profile_id, action=ACTION,
            old_values={"rows": snapshot}, reason=reason,
            new_values={"student": student_id, "student_name": str(profile.student), "deleted": counts,
                        "demo_records": demo_deleted},
        )
    return counts


__all__ = ["ACTION", "WARNING", "is_allowed", "preview", "purge"]
