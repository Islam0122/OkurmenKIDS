"""Платёжный профиль студента: регистрация, условия оплаты, остановка.

Менеджер при регистрации указывает тариф, цену, скидку, бронь и особые
условия — профиль создаётся с первым пакетом и начислением автоматически,
вручную ничего не начисляется. Скидка в пределах полномочий менеджера
(`BILLING_MANAGER_MAX_DISCOUNT_PERCENT`) действует сразу; сверх них —
ждёт согласования администратора оплаты, а начисления профиля до решения
остаются черновиками (DRAFT) и не требуют оплаты.

Изменение условий действует на пакеты, созданные после изменения: уже
выставленные начисления и оплаченные пакеты хранят свой снимок.

Остановка начислений (деактивация, завершение обучения) не удаляет
историю: старые начисления и долги остаются, не начатые будущие пакеты
отменяются, оплата за них возвращается в аванс.
"""
from __future__ import annotations

import datetime as dt

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.academy.models import Student, StudentStatusEvent
from apps.accounting.services import audit

from ..models import (
    BillingNotification,
    BillingPlan,
    BillingTermsChange,
    DiscountType,
    Invoice,
    LessonPackage,
    StudentBillingProfile,
)
from . import BillingError
from .invoices import create_first_package, issue_drafts, lock_profile, void_invoice
from .notifications import notify
from .pricing import plan_version_on, validate_terms

Status = StudentBillingProfile.Status
TERMS_FIELDS = ("custom_price", "discount_type", "discount_value", "discount_reason")


def _terms(profile) -> dict:
    return {
        "custom_price": None if profile.custom_price is None else str(profile.custom_price),
        "discount_type": profile.discount_type, "discount_value": str(profile.discount_value),
        "discount_reason": profile.discount_reason,
    }


def _is_standard(custom_price, discount_type) -> bool:
    return custom_price is None and discount_type == DiscountType.NONE


def _apply_terms(profile, change: BillingTermsChange, *, assigned_by, approved_by) -> None:
    profile.custom_price = change.custom_price
    profile.discount_type, profile.discount_value = change.discount_type, change.discount_value
    profile.discount_reason = change.reason
    profile.discount_assigned_by, profile.discount_approved_by = assigned_by, approved_by
    profile.save()


def _submit_terms(profile, *, actor, custom_price, discount_type, discount_value, reason: str) -> BillingTermsChange:
    """Записать изменение условий: в пределах полномочий — применить сразу,
    иначе — на согласование. Вызывается под блокировкой профиля."""
    from ..permissions import check_manager_discount, is_billing_admin

    base = plan_version_on(profile.plan, timezone.localdate()).package_price
    custom, discount_type, value = validate_terms(
        custom_price=custom_price, discount_type=discount_type, discount_value=discount_value, base_price=base,
    )
    if not _is_standard(custom, discount_type) and not (reason or "").strip():
        raise BillingError("Укажите основание скидки или индивидуальной цены.", code="reason_required")
    if BillingTermsChange.objects.filter(profile=profile, status=BillingTermsChange.Status.PENDING).exists():
        raise BillingError("Предыдущее изменение условий ещё ждёт согласования.", code="pending_terms")
    within = check_manager_discount(actor, base_price=base, custom_price=custom, discount_type=discount_type,
                                    discount_value=value)
    change = BillingTermsChange.objects.create(
        profile=profile, custom_price=custom, discount_type=discount_type, discount_value=value,
        reason=(reason or "").strip() or "Стандартные условия", previous_terms=_terms(profile),
        status=BillingTermsChange.Status.APPROVED if within else BillingTermsChange.Status.PENDING,
        requested_by=actor, decided_by=actor if within else None, decided_at=timezone.now() if within else None,
    )
    if within:
        _apply_terms(profile, change, assigned_by=actor, approved_by=actor if is_billing_admin(actor) else None)
        audit.log(actor, profile, "billing_terms_apply", old=change.previous_terms, new=_terms(profile),
                  reason=change.reason)
    else:
        audit.log(actor, change, "billing_terms_request", new={
            "profile": profile.pk, "custom_price": custom, "discount_type": discount_type, "discount_value": value,
        }, reason=change.reason)
        notify(
            BillingNotification.Kind.DISCOUNT_APPROVAL, f"terms:{change.pk}",
            f"Скидка ждёт согласования: {profile.student}",
            f"{change.get_discount_type_display()} {value}, цена {custom or base}. Основание: {change.reason}",
            profile=profile,
        )
    return change


def create_student_billing_profile(*, student: Student, plan: BillingPlan, actor, start_date: dt.date | None = None,
                                   subject=None, parent_name: str = "", parent_phone: str = "",
                                   custom_price=None, discount_type: str = DiscountType.NONE, discount_value=0,
                                   discount_reason: str = "", special_terms: str = "", responsible_accountant=None,
                                   reservation_amount=None, reserved_until: dt.date | None = None,
                                   reservation_comment: str = "") -> StudentBillingProfile:
    """Регистрация студента в оплате: профиль, условия, первый пакет с
    начислением и (если указана) бронь."""
    from ..permissions import authorize
    from .reservations import create_reservation

    authorize(actor, "create_profile")
    if not plan.is_active:
        raise BillingError("Тариф отключён.", code="plan_inactive")
    if student.status != Student.Status.ACTIVE:
        raise BillingError("Студент не активен — профиль оплаты не создаётся.", code="student_inactive")
    if plan.course_id and student.group_id and student.group.course_id != plan.course_id:
        raise BillingError("Тариф относится к другой программе.", code="wrong_course")
    subject = subject or plan.subject
    if responsible_accountant is not None and getattr(responsible_accountant, "role", None) != "accountant":
        raise BillingError("Ответственным может быть только бухгалтер.", code="bad_accountant")
    start_date = start_date or student.enrollment_date or timezone.localdate()
    plan_version_on(plan, start_date)  # тариф с ценой — иначе понятная ошибка
    with transaction.atomic():
        Student.objects.select_for_update().get(pk=student.pk)
        try:
            with transaction.atomic():
                profile = StudentBillingProfile.objects.create(
                    student=student, subject=subject, plan=plan, start_date=start_date,
                    parent_name=(parent_name or "").strip(),
                    parent_phone=(parent_phone or student.parent_phone or "").strip(),
                    special_terms=special_terms or "", responsible_accountant=responsible_accountant, created_by=actor,
                )
        except IntegrityError:
            raise BillingError("У студента уже есть действующий профиль оплаты по этому направлению.", code="duplicate")
        audit.log(actor, profile, "billing_profile_create", new={
            "student": student.pk, "plan": plan.pk, "subject": getattr(subject, "pk", None), "start_date": start_date,
        })
        profile = lock_profile(profile)
        if custom_price not in (None, "") or (discount_type or DiscountType.NONE) != DiscountType.NONE:
            _submit_terms(profile, actor=actor, custom_price=custom_price, discount_type=discount_type,
                          discount_value=discount_value, reason=discount_reason)
        # Срок оплаты первого пакета — от даты начала обучения, если она впереди.
        create_first_package(profile, actor=actor, on_date=timezone.localdate())
        if reservation_amount not in (None, "", 0):
            create_reservation(profile, actor=actor, expected_amount=reservation_amount,
                               reserved_until=reserved_until, comment=reservation_comment, group=student.group)
    profile.refresh_from_db()
    return profile


def register_students(*, actor, plan: BillingPlan, students, start_date: dt.date | None = None,
                      responsible_accountant=None, prepaid_first_package: bool = False,
                      prepaid_reason: str = "") -> dict:
    """Массовое подключение уже учащихся студентов к оплате по тарифу.

    Каждый студент — отдельная операция (ошибка одного не откатывает
    остальных). Уже подключённые к этому направлению, неактивные и из
    другой программы пропускаются с причиной. Дата начала по умолчанию —
    сегодня: прошлые уроки не списываются.

    `prepaid_first_package` — первый пакет уже оплачен до внедрения учёта:
    начисление закрывается корректировкой с основанием (сумма начисления не
    меняется, фиктивного платежа нет). Только администратор оплаты."""
    from ..permissions import authorize
    from .invoices import adjust_invoice

    authorize(actor, "create_profile")
    if prepaid_first_package:
        authorize(actor, "adjust_invoice")
        if not (prepaid_reason or "").strip():
            raise BillingError("Укажите основание: где и когда оплачен первый пакет.", code="reason_required")
    start_date = start_date or timezone.localdate()
    subject = plan.subject
    result = {"created": [], "skipped": []}
    for student in students:
        def skip(reason):
            result["skipped"].append({"student": student.pk, "student_name": str(student), "reason": reason})

        if student.status != Student.Status.ACTIVE:
            skip("Студент не активен")
            continue
        live = StudentBillingProfile.objects.filter(student=student).exclude(status=Status.INACTIVE)
        if live.filter(subject=subject).exists() if subject else live.filter(subject__isnull=True).exists():
            skip("Уже подключён к оплате по этому направлению")
            continue
        try:
            profile = create_student_billing_profile(
                student=student, plan=plan, actor=actor, start_date=start_date,
                responsible_accountant=responsible_accountant,
            )
            if prepaid_first_package:
                invoice = profile.invoices.exclude(status="VOID").get()
                if invoice.amount > 0:
                    adjust_invoice(invoice, actor=actor, amount=invoice.amount,
                                   reason=f"Оплачено до подключения учёта: {prepaid_reason.strip()}")
        except BillingError as exc:
            skip(exc.message)
            continue
        result["created"].append(profile.pk)
    return result


def request_terms_change(profile: StudentBillingProfile, *, actor, custom_price=None,
                         discount_type: str = DiscountType.NONE, discount_value=0, reason: str = "") -> BillingTermsChange:
    from ..permissions import authorize

    authorize(actor, "change_terms")
    with transaction.atomic():
        profile = lock_profile(profile)
        if profile.status == Status.INACTIVE:
            raise BillingError("Начисления по профилю остановлены.", code="profile_inactive")
        return _submit_terms(profile, actor=actor, custom_price=custom_price, discount_type=discount_type,
                             discount_value=discount_value, reason=reason)


def decide_terms_change(change: BillingTermsChange, *, actor, approve: bool, comment: str = "") -> BillingTermsChange:
    """Решение администратора оплаты по скидке сверх полномочий менеджера.
    Черновые начисления профиля после решения выставляются (по новым
    условиям — если согласовано, по прежним — если отклонено)."""
    from ..permissions import authorize

    authorize(actor, "approve_terms")
    with transaction.atomic():
        profile = lock_profile(change.profile_id)
        change = BillingTermsChange.objects.select_for_update().get(pk=change.pk)
        if change.status != BillingTermsChange.Status.PENDING:
            raise BillingError("Решение по этому изменению уже принято.", code="bad_status")
        change.status = BillingTermsChange.Status.APPROVED if approve else BillingTermsChange.Status.REJECTED
        change.decided_by, change.decided_at, change.decision_comment = actor, timezone.now(), (comment or "").strip()
        change.save()
        if approve:
            old = _terms(profile)
            _apply_terms(profile, change, assigned_by=change.requested_by, approved_by=actor)
            audit.log(actor, profile, "billing_terms_apply", old=old, new=_terms(profile), reason=change.reason)
        audit.log(actor, change, "billing_terms_decide", new={"status": change.status}, reason=change.decision_comment)
        issue_drafts(profile, actor=actor)
    return change


def update_profile(profile: StudentBillingProfile, *, actor, **fields) -> StudentBillingProfile:
    """Контактные данные, особые условия, ответственный бухгалтер."""
    from ..permissions import authorize

    allowed = {"parent_name", "parent_phone", "special_terms", "responsible_accountant"}
    if set(fields) - allowed:
        raise BillingError("Эти поля меняются отдельными операциями.", code="invalid")
    authorize(actor, "assign" if set(fields) == {"responsible_accountant"} else "change_terms")
    accountant = fields.get("responsible_accountant")
    if accountant is not None and getattr(accountant, "role", None) != "accountant":
        raise BillingError("Ответственным может быть только бухгалтер.", code="bad_accountant")
    with transaction.atomic():
        profile = lock_profile(profile)
        old = {k: getattr(profile, k + "_id" if k == "responsible_accountant" else k) for k in fields}
        for key, value in fields.items():
            setattr(profile, key, value)
        profile.save()
        if "responsible_accountant" in fields:
            profile.tasks.filter(status__in=("OPEN", "PROMISED", "DISPUTE")).update(assignee=accountant)
        audit.log(actor, profile, "billing_profile_update", old=old, new={
            k: getattr(profile, k + "_id" if k == "responsible_accountant" else k) for k in fields
        })
    return profile


# ---------------------------------------------------------------------------
# Остановка и возобновление начислений
# ---------------------------------------------------------------------------

def deactivate_billing_profile(profile: StudentBillingProfile, *, actor, on_date: dt.date | None = None,
                               reason: str = "", source: str = StudentBillingProfile.StopSource.MANUAL,
                               system: bool = False) -> StudentBillingProfile:
    """Остановить будущие начисления. Старые начисления и долги остаются;
    уроки после даты остановки не списываются; не начатые будущие пакеты
    отменяются (оплата за них — в аванс, решение о возврате — за бухгалтером)."""
    from ..permissions import authorize

    if not system:
        authorize(actor, "stop_profile")
    reason = (reason or "").strip()
    if not reason:
        raise BillingError("Укажите причину остановки начислений.", code="reason_required")
    on_date = on_date or timezone.localdate()
    with transaction.atomic():
        profile = lock_profile(profile)
        if profile.status == Status.INACTIVE:
            return profile
        old = {"status": profile.status}
        profile.status = Status.INACTIVE
        profile.stopped_on, profile.stop_reason, profile.stop_source = on_date, reason, source
        profile.save()
        # Будущие пакеты: следующие (PLANNED) и текущий, по которому ещё не
        # было ни одного урока (студент ушёл до начала). Начатые — остаются.
        not_started = profile.packages.filter(lessons_used=0, started_on__isnull=True).filter(
            status__in=(LessonPackage.Status.PLANNED, LessonPackage.Status.ACTIVE),
        )
        for package in not_started:
            invoice = package.invoices.exclude(status=Invoice.Status.VOID).first()
            if invoice is not None:
                void_invoice(invoice, actor=actor, reason=f"Остановка начислений: {reason}", system=True)
            else:
                package.status = LessonPackage.Status.CANCELLED
                package.save(update_fields=["status", "updated_at"])
        for reservation in profile.reservations.filter(status="PENDING"):
            reservation.status = "CANCELLED"
            reservation.cancel_reason, reservation.cancelled_at = f"Остановка начислений: {reason}", timezone.now()
            reservation.save()
        audit.log(actor, profile, "billing_profile_stop", old=old, new={
            "status": profile.status, "stopped_on": on_date, "source": source,
        }, reason=reason)
    return profile


def pause_billing_profile(profile, *, actor, reason: str = "", system: bool = False) -> StudentBillingProfile:
    from ..permissions import authorize

    if not system:
        authorize(actor, "stop_profile")
    with transaction.atomic():
        profile = lock_profile(profile)
        if profile.status != Status.ACTIVE:
            return profile
        profile.status = Status.PAUSED
        profile.save(update_fields=["status", "updated_at"])
        audit.log(actor, profile, "billing_profile_pause", new={"status": profile.status}, reason=reason)
    return profile


def resume_billing_profile(profile, *, actor, reason: str = "", system: bool = False) -> StudentBillingProfile:
    """Возобновить начисления. Остановленный по статусу студента профиль
    возобновляется при его возвращении (с даты возврата)."""
    from ..permissions import authorize

    if not system:
        authorize(actor, "stop_profile")
    with transaction.atomic():
        profile = lock_profile(profile)
        if profile.status == Status.ACTIVE:
            return profile
        if profile.status == Status.INACTIVE:
            clash = StudentBillingProfile.objects.filter(
                student_id=profile.student_id, subject_id=profile.subject_id,
            ).exclude(pk=profile.pk).exclude(status=Status.INACTIVE).exists()
            if clash:
                raise BillingError("У студента уже есть другой действующий профиль.", code="duplicate")
        old = {"status": profile.status, "stopped_on": profile.stopped_on}
        profile.status = Status.ACTIVE
        profile.stopped_on, profile.stop_source = None, ""
        profile.save()
        audit.log(actor, profile, "billing_profile_resume", old=old, new={"status": profile.status}, reason=reason)
    return profile


STOP_EVENTS = {StudentStatusEvent.EventType.DEACTIVATED, StudentStatusEvent.EventType.COMPLETED}
RETURN_EVENTS = {StudentStatusEvent.EventType.REACTIVATED, StudentStatusEvent.EventType.CONTINUED}


def on_student_status_event(event_id: int) -> None:
    """Реакция на событие статуса студента в LMS (вызывается после коммита):

    * деактивация / завершение обучения — начисления останавливаются с
      даты события (как и в LMS, день ухода уже не учебный);
    * пауза — профиль приостановлен: новые пакеты не выставляются;
    * возврат / продолжение — профиль снова активен;
    * перевод в другую группу — ничего не меняется: пакет и долг остаются,
      уроки новой группы списываются в тот же пакет с даты перевода.
    """
    event = StudentStatusEvent.objects.filter(pk=event_id).select_related("student").first()
    if event is None:
        return
    profiles = StudentBillingProfile.objects.filter(student_id=event.student_id)
    reason = f"{event.get_event_type_display()} ({event.event_date:%d.%m.%Y})"
    if event.event_type in STOP_EVENTS:
        for profile in profiles.exclude(status=Status.INACTIVE):
            deactivate_billing_profile(profile, actor=event.performed_by, on_date=event.event_date, reason=reason,
                                       source=StudentBillingProfile.StopSource.STUDENT_STATUS, system=True)
    elif event.event_type == StudentStatusEvent.EventType.PAUSED:
        for profile in profiles.filter(status=Status.ACTIVE):
            pause_billing_profile(profile, actor=event.performed_by, reason=reason, system=True)
    elif event.event_type in RETURN_EVENTS:
        for profile in profiles.filter(status=Status.PAUSED):
            resume_billing_profile(profile, actor=event.performed_by, reason=reason, system=True)
        stopped = profiles.filter(status=Status.INACTIVE, stop_source=StudentBillingProfile.StopSource.STUDENT_STATUS)
        for profile in stopped.order_by("-stopped_on", "-pk"):
            try:
                resume_billing_profile(profile, actor=event.performed_by, reason=reason, system=True)
            except BillingError:
                continue
