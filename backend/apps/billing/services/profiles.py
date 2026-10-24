"""Платёжный профиль (договор) студента: регистрация, условия, остановка.

Договор по программе (`plan.duration_months`): при оформлении фиксируется
снимок условий программы (цена месяца, уроков в месяце, месяцев, срок
оплаты) и итоговая стоимость курса — скидка задаётся не процентом, а
итоговой суммой (`contracts.course_terms`). Способ оплаты — помесячно или
предоплата за весь курс; бронь — в первый месяц или в общую стоимость.

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
    LessonConsumption,
    LessonPackage,
    PaymentMode,
    ReservationAllocation,
    StudentBillingProfile,
)
from . import BillingError
from .contracts import course_quote, course_terms, invoiced_total
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
        "discount_enabled": profile.discount_enabled,
        "final_course_price": None if profile.final_course_price is None else str(profile.final_course_price),
        "discount_amount": str(profile.discount_amount),
    }


def _is_standard(custom_price, discount_type) -> bool:
    return custom_price is None and discount_type == DiscountType.NONE


def _apply_terms(profile, change: BillingTermsChange, *, assigned_by, approved_by) -> None:
    if profile.is_course:
        profile.discount_enabled = change.discount_enabled
        profile.final_course_price, profile.discount_amount = change.final_course_price, change.discount_amount
        profile.discount_reason = change.reason if change.discount_enabled else ""
        profile.discount_assigned_by, profile.discount_approved_by = assigned_by, approved_by
        profile.save()
        return
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


def _submit_course_terms(profile, *, actor, discount_enabled: bool, final_course_price, reason: str,
                         initial: bool = False) -> BillingTermsChange | None:
    """Итоговая стоимость курса: в пределах полномочий — сразу, иначе — на
    согласование бухгалтеру (начисления до решения — черновики). Уже
    выставленные начисления не меняются: новая цена — на будущие месяцы,
    поэтому итоговая не может быть меньше уже начисленного."""
    from ..permissions import check_course_discount, is_billing_admin

    final, discount = course_terms(standard_price=profile.standard_course_price, discount_enabled=discount_enabled,
                                   final_price=final_course_price, reason=reason)
    if initial and not discount_enabled:
        return None
    if not initial and final < invoiced_total(profile):
        raise BillingError(
            f"Итоговая стоимость меньше уже начисленного ({invoiced_total(profile)} сом) — оформите корректировку.",
            code="below_invoiced",
        )
    if BillingTermsChange.objects.filter(profile=profile, status=BillingTermsChange.Status.PENDING).exists():
        raise BillingError("Предыдущее изменение условий ещё ждёт согласования.", code="pending_terms")
    within = check_course_discount(actor, standard_price=profile.standard_course_price, final_price=final)
    change = BillingTermsChange.objects.create(
        profile=profile, discount_enabled=bool(discount_enabled), final_course_price=final, discount_amount=discount,
        reason=(reason or "").strip() or "Стандартная стоимость", previous_terms=_terms(profile),
        status=BillingTermsChange.Status.APPROVED if within else BillingTermsChange.Status.PENDING,
        requested_by=actor, decided_by=actor if within else None, decided_at=timezone.now() if within else None,
    )
    if within:
        _apply_terms(profile, change, assigned_by=actor, approved_by=actor if is_billing_admin(actor) else None)
        audit.log(actor, profile, "billing_terms_apply", old=change.previous_terms, new=_terms(profile),
                  reason=change.reason)
    else:
        audit.log(actor, change, "billing_terms_request", new={
            "profile": profile.pk, "final_course_price": final, "discount_amount": discount,
        }, reason=change.reason)
        notify(
            BillingNotification.Kind.DISCOUNT_APPROVAL, f"terms:{change.pk}",
            f"Скидка ждёт согласования: {profile.student}",
            f"Итоговая стоимость курса {final} сом вместо {profile.standard_course_price} (скидка {discount}). "
            f"Основание: {change.reason}", profile=profile,
        )
    return change


def create_student_billing_profile(*, student: Student, plan: BillingPlan, actor, start_date: dt.date | None = None,
                                   subject=None, parent_name: str = "", parent_phone: str = "",
                                   custom_price=None, discount_type: str = DiscountType.NONE, discount_value=0,
                                   discount_reason: str = "", special_terms: str = "", responsible_accountant=None,
                                   reservation_amount=None, reserved_until: dt.date | None = None,
                                   reservation_comment: str = "", payment_mode: str = PaymentMode.MONTHLY,
                                   reservation_allocation: str = ReservationAllocation.FIRST_MONTH,
                                   discount_enabled: bool = False, final_course_price=None) -> StudentBillingProfile:
    """Регистрация студента в оплате: договор, условия, первый учебный месяц
    (пакет) с начислением и (если указана) бронь."""
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
    course = {}
    if plan.is_course:
        if payment_mode not in PaymentMode.values or reservation_allocation not in ReservationAllocation.values:
            raise BillingError("Неизвестный способ оплаты или учёта брони.", code="invalid")
        if payment_mode == PaymentMode.MONTHLY and not plan.allow_monthly:
            raise BillingError("Программа не допускает помесячную оплату.", code="invalid_mode")
        if payment_mode == PaymentMode.FULL_PREPAY and not plan.allow_full_prepay:
            raise BillingError("Программа не допускает предоплату за весь курс.", code="invalid_mode")
        if custom_price not in (None, "") or (discount_type or DiscountType.NONE) != DiscountType.NONE:
            raise BillingError("Для программы скидка задаётся итоговой стоимостью курса.", code="invalid_discount")
        quote = course_quote(plan, start_date)
        # Проверка до создания: ошибка ввода не оставляет полузаписанный договор.
        course_terms(standard_price=quote.standard_course_price, discount_enabled=discount_enabled,
                     final_price=final_course_price, reason=discount_reason)
        course = {
            "payment_mode": payment_mode, "reservation_allocation": reservation_allocation,
            "duration_months": quote.duration_months, "lessons_per_month": quote.lessons_per_month,
            "deadline_lessons": quote.deadline_lessons, "month_price": quote.month_price,
            "standard_course_price": quote.standard_course_price, "final_course_price": quote.standard_course_price,
        }
    with transaction.atomic():
        Student.objects.select_for_update().get(pk=student.pk)
        try:
            with transaction.atomic():
                profile = StudentBillingProfile.objects.create(
                    student=student, subject=subject, plan=plan, start_date=start_date,
                    parent_name=(parent_name or "").strip(),
                    parent_phone=(parent_phone or student.parent_phone or "").strip(),
                    special_terms=special_terms or "", responsible_accountant=responsible_accountant, created_by=actor,
                    **course,
                )
        except IntegrityError:
            raise BillingError("У студента уже есть действующий профиль оплаты по этому направлению.", code="duplicate")
        audit.log(actor, profile, "billing_profile_create", new={
            "student": student.pk, "plan": plan.pk, "subject": getattr(subject, "pk", None), "start_date": start_date,
            **course,
        })
        profile = lock_profile(profile)
        if profile.is_course:
            _submit_course_terms(profile, actor=actor, discount_enabled=discount_enabled,
                                 final_course_price=final_course_price, reason=discount_reason, initial=True)
        elif custom_price not in (None, "") or (discount_type or DiscountType.NONE) != DiscountType.NONE:
            _submit_terms(profile, actor=actor, custom_price=custom_price, discount_type=discount_type,
                          discount_value=discount_value, reason=discount_reason)
        # Дата выставления — сегодня (срок оплаты первого пакета — от даты
        # начала, если она впереди); период начисления — начало договора, а не
        # день оформления: договор с 1 сентября, внесённый в октябре, — сентябрь.
        create_first_package(profile, actor=actor, on_date=timezone.localdate(), period_date=start_date)
        if reservation_amount not in (None, "", 0):
            create_reservation(profile, actor=actor, expected_amount=reservation_amount,
                               reserved_until=reserved_until, comment=reservation_comment, group=student.group)
    # Уроки, проведённые с даты начала договора до его оформления, — в учебный
    # месяц (сигналы урока сработали, когда договора ещё не было).
    from .lessons import sync_profile_history

    sync_profile_history(profile)
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
        live = StudentBillingProfile.objects.filter(student=student).exclude(status__in=StudentBillingProfile.CLOSED_STATUSES)
        if live.filter(subject=subject).exists() if subject else live.filter(subject__isnull=True).exists():
            skip("Уже подключён к оплате по этому направлению")
            continue
        try:
            profile = create_student_billing_profile(
                student=student, plan=plan, actor=actor, start_date=start_date,
                responsible_accountant=responsible_accountant,
            )
            if prepaid_first_package:
                invoice = profile.invoices.exclude(status="VOID").order_by("package__number", "pk").first()
                if invoice is not None and invoice.amount > 0:
                    # Оплачено до подключения — долг закрыт с периода начисления, не с сегодняшнего дня.
                    adjust_invoice(invoice, actor=actor, amount=invoice.amount,
                                   effective_date=min(invoice.period_date, timezone.localdate()),
                                   reason=f"Оплачено до подключения учёта: {prepaid_reason.strip()}")
        except BillingError as exc:
            skip(exc.message)
            continue
        result["created"].append(profile.pk)
    return result


def request_course_terms_change(profile: StudentBillingProfile, *, actor, discount_enabled: bool,
                                final_course_price=None, reason: str = "") -> BillingTermsChange:
    """Новая итоговая стоимость курса (действует на будущие месяцы)."""
    from ..permissions import authorize

    authorize(actor, "change_terms")
    with transaction.atomic():
        profile = lock_profile(profile)
        if not profile.is_course:
            raise BillingError("Договор без программы — меняется цена пакета.", code="not_course")
        if profile.status in StudentBillingProfile.CLOSED_STATUSES:
            raise BillingError("Договор закрыт.", code="profile_inactive")
        return _submit_course_terms(profile, actor=actor, discount_enabled=discount_enabled,
                                    final_course_price=final_course_price, reason=reason)


def change_payment_mode(profile: StudentBillingProfile, *, actor, payment_mode: str, reason: str = "") -> StudentBillingProfile:
    """Сменить способ оплаты курса — только до начала обучения (ни одного
    зачтённого урока, ни одной оплаты на начислениях): начисление месяца 1
    аннулируется и выставляется заново по новому способу. После начала —
    помесячно с оплатой вперёд (аванс закрывает будущие месяцы)."""
    from ..permissions import authorize
    from ..models import PaymentAllocation
    from .invoices import _after_invoice_created, _create_invoice
    from .contracts import month_charge

    authorize(actor, "change_terms")
    if payment_mode not in PaymentMode.values:
        raise BillingError("Неизвестный способ оплаты.", code="invalid")
    with transaction.atomic():
        profile = lock_profile(profile)
        if not profile.is_course:
            raise BillingError("Способ оплаты задаётся только для программы.", code="not_course")
        if profile.payment_mode == payment_mode:
            return profile
        allowed = profile.plan.allow_monthly if payment_mode == PaymentMode.MONTHLY else profile.plan.allow_full_prepay
        if not allowed:
            raise BillingError("Программа не допускает этот способ оплаты.", code="invalid_mode")
        packages = list(profile.packages.exclude(status=LessonPackage.Status.CANCELLED))
        if any(p.lessons_used for p in packages) or len(packages) > 1:
            raise BillingError("Обучение уже началось — способ оплаты не меняется.", code="already_started")
        if PaymentAllocation.objects.filter(profile=profile, status=PaymentAllocation.Status.ACTIVE).exists():
            raise BillingError("По начислению уже есть оплата — сначала сторнируйте распределение.", code="has_payments")
        old = {"payment_mode": profile.payment_mode}
        reason = (reason or "").strip() or "Смена способа оплаты до начала обучения"
        # Перевыставленное начисление остаётся в том же учебном периоде.
        period = (profile.invoices.exclude(status=Invoice.Status.VOID).values_list("period_date", flat=True).first()
                  or profile.start_date)
        for invoice in profile.invoices.exclude(status=Invoice.Status.VOID):
            void_invoice(invoice, actor=actor, reason=reason, system=True, cancel_package=False)
        profile.payment_mode = payment_mode
        profile.save(update_fields=["payment_mode", "updated_at"])
        if packages:
            package = packages[0]
            amount, kind = month_charge(profile, package.month_number)
            package.final_price = amount
            package.pricing_snapshot = {**package.pricing_snapshot, "payment_mode": payment_mode, "charge": str(amount)}
            package.save(update_fields=["final_price", "pricing_snapshot", "updated_at"])
            if amount > 0:
                created = _create_invoice(profile, package, amount=amount, kind=kind, on_date=timezone.localdate(),
                                          actor=actor, period_date=period,
                                          snapshot={**package.pricing_snapshot, "package_number": package.number})
                _after_invoice_created(profile, created, actor=actor)
        audit.log(actor, profile, "billing_payment_mode", old=old, new={"payment_mode": payment_mode}, reason=reason)
    return profile


def request_terms_change(profile: StudentBillingProfile, *, actor, custom_price=None,
                         discount_type: str = DiscountType.NONE, discount_value=0, reason: str = "") -> BillingTermsChange:
    from ..permissions import authorize

    authorize(actor, "change_terms")
    with transaction.atomic():
        profile = lock_profile(profile)
        if profile.status in StudentBillingProfile.CLOSED_STATUSES:
            raise BillingError("Начисления по профилю остановлены.", code="profile_inactive")
        if profile.is_course:
            raise BillingError("Для программы скидка задаётся итоговой стоимостью курса.", code="invalid_discount")
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


def change_start_date(profile: StudentBillingProfile, *, actor, start_date: dt.date, reason: str) -> dict:
    """Контролируемое исправление даты начала договора (например, договор
    оформлен 24.10 с датой «сегодня», а студент учится с сентября и уже
    оплатил курс). Только администратор оплаты, с основанием и аудитом.

    * раньше — уроки приоритетного предмета с новой даты засчитываются в
      учебные месяцы по обычным правилам (`sync_profile_history`): другие
      предметы, отменённые уроки и дни вне группы по-прежнему не идут;
    * позже — только если до новой даты ничего не засчитано (засчитанные
      уроки исправляются сторно отдельно, а не сменой даты);
    * период первого начисления, если он был равен старой дате начала,
      переносится на новую (`correct_invoice_period`, тоже в аудите).
    Посещаемость, платежи и суммы начислений не меняются."""
    from ..permissions import authorize
    from .invoices import correct_invoice_period
    from .lessons import sync_profile_history

    authorize(actor, "adjust_invoice")
    reason = (reason or "").strip()
    if not reason:
        raise BillingError("Укажите основание исправления даты начала.", code="reason_required")
    if start_date > timezone.localdate():
        raise BillingError("Дата начала не может быть в будущем при исправлении.", code="bad_date")
    with transaction.atomic():
        profile = lock_profile(profile)
        if profile.status in StudentBillingProfile.CLOSED_STATUSES:
            raise BillingError("Договор закрыт — дата начала не меняется.", code="profile_inactive")
        old = profile.start_date
        if start_date == old:
            return {"profile": profile.pk, "start_date": old.isoformat(), "consumed": 0, "changed": False}
        if start_date > old and LessonConsumption.objects.filter(
            profile=profile, kind=LessonConsumption.Kind.CONSUME, status=LessonConsumption.Status.ACTIVE,
            lesson_date__lt=start_date,
        ).exists():
            raise BillingError("До новой даты уже засчитаны уроки — сначала сторнируйте их.", code="has_consumptions")
        if profile.stopped_on and start_date >= profile.stopped_on:
            raise BillingError("Дата начала позже даты остановки начислений.", code="bad_date")
        profile.start_date = start_date
        profile.save(update_fields=["start_date", "updated_at"])
        audit.log(actor, profile, "billing_profile_start_date", old={"start_date": old},
                  new={"start_date": start_date}, reason=reason)
        first = (profile.invoices.exclude(status=Invoice.Status.VOID).select_related("package")
                 .order_by("package__number", "pk").first())
        if first is not None and first.period_date == old:
            correct_invoice_period(first, actor=actor, period_date=start_date, system=True,
                                   reason=f"Исправлена дата начала договора: {reason}")
    result = sync_profile_history(StudentBillingProfile.objects.get(pk=profile.pk))
    return {"profile": profile.pk, "start_date": start_date.isoformat(), "consumed": result["consumed"],
            "changed": True}


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
        if profile.status in StudentBillingProfile.CLOSED_STATUSES:
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
        if profile.status in (Status.ACTIVE, Status.COMPLETED):
            return profile  # завершённый курс не возобновляется — новый договор
        if profile.status == Status.INACTIVE:
            clash = StudentBillingProfile.objects.filter(
                student_id=profile.student_id, subject_id=profile.subject_id,
            ).exclude(pk=profile.pk).exclude(status__in=StudentBillingProfile.CLOSED_STATUSES).exists()
            if clash:
                raise BillingError("У студента уже есть другой действующий профиль.", code="duplicate")
        old = {"status": profile.status, "stopped_on": profile.stopped_on}
        profile.status = Status.ACTIVE
        profile.stopped_on, profile.stop_source = None, ""
        profile.save()
        audit.log(actor, profile, "billing_profile_resume", old=old, new={"status": profile.status}, reason=reason)
    from .lessons import sync_profile_history

    sync_profile_history(profile)  # уроки, проведённые, пока договор был приостановлен
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
        for profile in profiles.exclude(status__in=StudentBillingProfile.CLOSED_STATUSES):
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
