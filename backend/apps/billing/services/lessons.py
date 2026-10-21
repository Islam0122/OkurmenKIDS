"""Учёт проведённых уроков: списание в пакет студента.

Урок списывается только когда занятие в LMS «Проведён» — не при создании
расписания. Со студента — если в день урока он по истории LMS
(`accounting.services.activity`) был активен именно в этой группе, его
профиль действовал (начало ≤ дата < остановка), направление профиля
совпадает с предметом урока, а правило тарифа об отсутствии позволяет
(`AbsencePolicy`). Отменённые и перенесённые занятия: отменённое не
списывается, его перенос списывается, когда будет проведён
(`Lesson.rescheduled_from` — обычный урок со своим статусом).

Договор по программе: учебный месяц определяется только приоритетным
предметом (направление профиля — обычно IT). Уроки English, Soft Skills и
других предметов не списываются и не задерживают переход к следующему
месяцу. После каждого зачтённого урока пересчитывается стадия оплаты
начислений месяца: урок № `deadline_lessons` — последний срок, следующий —
просрочка. На последнем уроке последнего месяца договор — «Курс завершён».

`sync_lesson` идемпотентна: приводит списания урока к тому, что должно
быть, — недостающие создаёт, лишние (урок отменён, удалён, отсутствие
стало уважительным) сторнирует. Повторный вызов ничего не дублирует;
частичный уникальный индекс не даёт списать урок дважды даже при гонке.

Пакет: урок идёт в самый ранний пакет со свободным местом (у
использованного пакета место освобождает сторно ошибочного списания),
иначе в текущий. Предупреждение за `warn_before_end_lessons` уроков до
конца, раннее начисление по настройке тарифа, на последнем уроке —
`complete_package` и следующий платёжный цикл.
"""
from __future__ import annotations

import datetime as dt
import logging

from django.db import IntegrityError, transaction
from django.db.models import F, Q
from django.utils import timezone

from apps.academy.models import Attendance, Lesson
from apps.accounting.services import audit
from apps.accounting.services.activity import active_student_days

from ..models import AbsencePolicy, BillingEvent, BillingNotification, LessonConsumption, LessonPackage, StudentBillingProfile
from . import BillingError
from .invoices import (
    activate_package,
    course_finished,
    create_next_package_invoice,
    is_continuing,
    lock_profile,
    next_planned_package,
)
from .notifications import notify

logger = logging.getLogger(__name__)
PackageStatus = LessonPackage.Status
ATTENDED = (Attendance.Status.PRESENT, Attendance.Status.LATE)


# ---------------------------------------------------------------------------
# Кого списывать
# ---------------------------------------------------------------------------

def chargeable_profiles(lesson: Lesson | None) -> dict[int, StudentBillingProfile]:
    """{profile_id: профиль} — с кого списывается этот урок."""
    if lesson is None or lesson.status != Lesson.Status.COMPLETED:
        return {}
    gid = lesson.group_id
    candidates = StudentBillingProfile.objects.filter(
        Q(student__group_id=gid) | Q(student__status_events__group_id=gid)
        | Q(student__status_events__from_group_id=gid),
    )
    if not candidates.exists():
        return {}  # в группе нет студентов с профилем оплаты — история не нужна
    days = active_student_days(lesson.date, lesson.date, group_ids=[lesson.group_id])
    student_ids = [sid for sid, by_day in days.items() if by_day.get(lesson.date) == lesson.group_id]
    if not student_ids:
        return {}
    profiles = (
        StudentBillingProfile.objects.filter(student_id__in=student_ids, start_date__lte=lesson.date)
        .exclude(status=StudentBillingProfile.Status.COMPLETED)
        .filter(Q(stopped_on__isnull=True) | Q(stopped_on__gt=lesson.date))
        .filter(Q(subject__isnull=True) | Q(subject_id=lesson.subject_id))
        .select_related("plan")
    )
    attendance = dict(Attendance.objects.filter(lesson=lesson).values_list("student_id", "status"))
    course_id = lesson.group.course_id
    result = {}
    for profile in profiles:
        plan = profile.plan
        if plan.course_id and plan.course_id != course_id:
            continue
        mark = attendance.get(profile.student_id)
        if plan.absence_policy == AbsencePolicy.EXCEPT_EXCUSED and mark == Attendance.Status.EXCUSED:
            continue
        if plan.absence_policy == AbsencePolicy.ATTENDED_ONLY and mark not in ATTENDED:
            continue
        result[profile.pk] = profile
    return result


def sync_lesson(lesson_id: int, *, actor=None) -> dict:
    """Привести списания урока в соответствие с LMS. Возвращает сводку."""
    lesson = Lesson.objects.select_related("group").filter(pk=lesson_id).first()
    target = chargeable_profiles(lesson)
    existing = {
        c.profile_id: c for c in LessonConsumption.objects.filter(
            lesson_ref=lesson_id, kind=LessonConsumption.Kind.CONSUME, status=LessonConsumption.Status.ACTIVE,
        )
    }
    consumed, reversed_ = [], []
    for profile_id, profile in target.items():
        if profile_id not in existing:
            consumption, created = consume_lesson(profile, lesson, actor=actor)
            if created:
                consumed.append(consumption.pk)
    for profile_id, consumption in existing.items():
        if profile_id not in target:
            reason = "Урок удалён из LMS" if lesson is None else (
                "Урок больше не «Проведён»" if lesson.status != Lesson.Status.COMPLETED else "Урок не подлежит списанию"
            )
            reverse_consumption(consumption, actor=None, reason=reason, system=True)
            reversed_.append(consumption.pk)
    return {"lesson": lesson_id, "consumed": consumed, "reversed": reversed_}


def sync_lesson_safely(lesson_id: int) -> None:
    """Вызов из сигнала после коммита урока: ошибка учёта оплаты не должна
    ломать работу тренера — она пишется в журнал событий, а фоновая задача
    `process_completed_lessons` повторит обработку."""
    key = f"lesson:{lesson_id}"
    try:
        result = sync_lesson(lesson_id)
    except Exception as exc:  # noqa: BLE001
        logger.exception("billing: lesson %s sync failed", lesson_id)
        event, _ = BillingEvent.objects.get_or_create(key=key, defaults={"kind": "lesson_sync"})
        BillingEvent.objects.filter(pk=event.pk).update(
            status=BillingEvent.Status.FAILED, attempts=F("attempts") + 1, error=str(exc)[:2000], updated_at=timezone.now(),
        )
        return
    if result["consumed"] or result["reversed"]:
        BillingEvent.objects.update_or_create(key=key, defaults={
            "kind": "lesson_sync", "status": BillingEvent.Status.DONE, "result": result, "error": "",
            "processed_at": timezone.now(),
        })
    else:
        BillingEvent.objects.filter(key=key, status=BillingEvent.Status.FAILED).update(
            status=BillingEvent.Status.DONE, error="", processed_at=timezone.now(),
        )


# ---------------------------------------------------------------------------
# Списание и сторно
# ---------------------------------------------------------------------------

def _package_for_consumption(profile: StudentBillingProfile, on_date: dt.date, actor) -> LessonPackage:
    package = (
        LessonPackage.objects.select_for_update()
        .filter(profile=profile, status__in=(PackageStatus.ACTIVE, PackageStatus.COMPLETED),
                lessons_used__lt=F("lessons_total"))
        .order_by("number").first()
    )
    if package is not None:
        return package
    planned = next_planned_package(profile)
    if planned is not None:
        return activate_package(planned)
    # Пакета нет (студент вернулся после паузы, предыдущий пакет закончился,
    # пока он не учился) — новый платёжный цикл.
    package, _invoice, _created = create_next_package_invoice(
        profile, actor=None, on_date=on_date, activate=True, for_held_lesson=True,
    )
    return package


def consume_lesson(profile: StudentBillingProfile, lesson: Lesson, *, actor=None):
    """Списать проведённый урок со студента. Возвращает (списание, создано)."""
    from ..permissions import authorize

    authorize(None, "consume")
    if lesson.status != Lesson.Status.COMPLETED:
        raise BillingError("Списать можно только проведённый урок.", code="lesson_not_completed")
    with transaction.atomic():
        profile = lock_profile(profile)
        existing = LessonConsumption.objects.filter(
            profile=profile, lesson_ref=lesson.pk, kind=LessonConsumption.Kind.CONSUME,
            status=LessonConsumption.Status.ACTIVE,
        ).first()
        if existing is not None:
            return existing, False
        package = _package_for_consumption(profile, lesson.date, actor)
        try:
            with transaction.atomic():
                consumption = LessonConsumption.objects.create(
                    package=package, profile=profile, student_id=profile.student_id, lesson=lesson,
                    lesson_ref=lesson.pk, lesson_date=lesson.date, group_id=lesson.group_id,
                    created_by=actor if getattr(actor, "is_authenticated", False) else None,
                )
        except IntegrityError:
            return LessonConsumption.objects.get(
                profile=profile, lesson_ref=lesson.pk, kind=LessonConsumption.Kind.CONSUME,
                status=LessonConsumption.Status.ACTIVE,
            ), False
        LessonPackage.objects.filter(pk=package.pk).update(lessons_used=F("lessons_used") + 1, updated_at=timezone.now())
        package.refresh_from_db()
        if package.started_on is None:
            package.started_on = lesson.date
            package.save(update_fields=["started_on", "updated_at"])
        _after_consumption(profile, package, lesson.date, actor)
    return consumption, True


def _after_consumption(profile: StudentBillingProfile, package: LessonPackage, on_date: dt.date, actor) -> None:
    _refresh_deadlines(profile, package, on_date)
    if package.status != PackageStatus.ACTIVE:
        return
    plan = profile.plan
    remaining = package.lessons_remaining
    if plan.warn_before_end_lessons and 0 < remaining <= plan.warn_before_end_lessons and package.ending_notified_at is None:
        package.ending_notified_at = timezone.now()
        package.save(update_fields=["ending_notified_at", "updated_at"])
        notify(
            BillingNotification.Kind.PACKAGE_ENDING, f"ending:{package.pk}",
            f"Пакет скоро закончится: {profile.student}",
            f"Пакет №{package.number}: использовано {package.lessons_used} из {package.lessons_total}, осталось {remaining}.",
            recipient=profile.responsible_accountant, profile=profile,
        )
    if (plan.early_invoice_enabled and plan.early_invoice_after_lessons and remaining > 0
            and package.lessons_used >= plan.early_invoice_after_lessons and is_continuing(profile)
            and next_planned_package(profile) is None and not course_finished(profile)):
        create_next_package_invoice(profile, actor=None, on_date=on_date, activate=False)
    if remaining == 0:
        complete_package(package, on_date=on_date, actor=actor)


def _refresh_deadlines(profile, package: LessonPackage, on_date: dt.date) -> None:
    """Стадия оплаты начислений месяца после урока: срок наступил /
    просрочка. Даты фиксируются в начислении один раз (история)."""
    from ..models import Invoice
    from .invoices import refresh_invoice

    # Срок наступил — фиксируется и у оплаченного начисления (аналитика «ожидалось»).
    package.invoices.filter(
        status=Invoice.Status.PAID, due_lesson__isnull=False, due_reached_on__isnull=True,
        due_lesson__lte=package.lessons_used,
    ).update(due_reached_on=on_date)
    for invoice in package.invoices.filter(status__in=Invoice.UNPAID_STATUSES, due_lesson__isnull=False):
        invoice = refresh_invoice(invoice, on=on_date)
        if invoice.status != Invoice.Status.OVERDUE and package.lessons_used == invoice.due_lesson:
            notify(
                BillingNotification.Kind.PAYMENT_DEADLINE, f"deadline:{invoice.pk}",
                f"Последний срок оплаты: {profile.student}",
                f"{invoice.number}: проведён {invoice.due_lesson}-й урок месяца, остаток {invoice.balance} сом.",
                recipient=profile.responsible_accountant, profile=profile, invoice=invoice,
            )


def complete_package(package: LessonPackage, *, on_date: dt.date, actor=None) -> LessonPackage | None:
    """Зафиксировать использование пакета и начать следующий платёжный
    цикл: следующий пакет уже есть (оплачен вперёд / выставлен заранее) —
    он становится текущим без нового начисления; иначе, если студент
    продолжает обучение, — новый пакет с начислением. Возвращает следующий
    пакет или None (обучение не продолжается — начисления остановлены)."""
    with transaction.atomic():
        profile = lock_profile(package.profile_id)
        package = LessonPackage.objects.select_for_update().get(pk=package.pk)
        if package.status != PackageStatus.ACTIVE or package.lessons_used < package.lessons_total:
            return None
        package.status = PackageStatus.COMPLETED
        package.completed_on = on_date
        package.save(update_fields=["status", "completed_on", "updated_at"])
        audit.log(actor, package, "billing_package_complete", new={
            "profile": profile.pk, "number": package.number, "lessons": package.lessons_total, "completed_on": on_date,
        })
        notify(
            BillingNotification.Kind.PACKAGE_COMPLETED, f"completed:{package.pk}",
            f"Пакет использован: {profile.student}", f"Пакет №{package.number}, {package.lessons_total} уроков.",
            recipient=profile.responsible_accountant, profile=profile,
        )
        planned = next_planned_package(profile)
        if planned is not None:
            return activate_package(planned)
        if profile.is_course and course_finished(profile):
            _finish_course(profile, on_date=on_date, actor=actor)
            return None
        if not is_continuing(profile):
            return None
        next_package, _invoice, _created = create_next_package_invoice(
            profile, actor=None, on_date=on_date, activate=True,
        )
        return next_package


def _finish_course(profile: StudentBillingProfile, *, on_date: dt.date, actor) -> None:
    """Пройден последний учебный месяц — договор «Курс завершён». Долги и
    аванс остаются; уроки после завершения не списываются."""
    old = {"status": profile.status}
    profile.status = StudentBillingProfile.Status.COMPLETED
    profile.stopped_on, profile.stop_reason = on_date, "Курс завершён: пройдены все учебные месяцы"
    profile.save(update_fields=["status", "stopped_on", "stop_reason", "updated_at"])
    audit.log(actor, profile, "billing_contract_complete", old=old, new={"status": profile.status, "on": on_date})


def reverse_consumption(consumption: LessonConsumption, *, actor, reason: str, system: bool = False) -> LessonConsumption:
    """Сторно ошибочного списания: исходная запись помечается REVERSED,
    создаётся запись REVERSAL, урок возвращается в пакет. Если пакет уже
    использован, в нём освобождается место — следующий проведённый урок
    займёт его, повторного начисления нет."""
    from ..permissions import authorize

    if not system:
        authorize(actor, "reverse_consumption")
    reason = (reason or "").strip()
    if not reason:
        raise BillingError("Укажите причину сторно.", code="reason_required")
    with transaction.atomic():
        lock_profile(consumption.profile_id)
        consumption = LessonConsumption.objects.select_for_update().get(pk=consumption.pk)
        if consumption.kind != LessonConsumption.Kind.CONSUME or consumption.status != LessonConsumption.Status.ACTIVE:
            raise BillingError("Списание уже сторнировано.", code="bad_status")
        consumption.status = LessonConsumption.Status.REVERSED
        consumption.save(update_fields=["status"])
        reversal = LessonConsumption.objects.create(
            package=consumption.package, profile=consumption.profile, student=consumption.student,
            lesson=consumption.lesson, lesson_ref=consumption.lesson_ref, lesson_date=consumption.lesson_date,
            group=consumption.group, kind=LessonConsumption.Kind.REVERSAL, reversal_of=consumption, reason=reason,
            created_by=actor if getattr(actor, "is_authenticated", False) else None,
        )
        LessonPackage.objects.filter(pk=consumption.package_id).update(
            lessons_used=F("lessons_used") - 1, updated_at=timezone.now(),
        )
        audit.log(actor, consumption, "billing_consumption_reverse", new={
            "lesson": consumption.lesson_ref, "package": consumption.package_id,
        }, reason=reason)
    return reversal


def sync_recent_lessons(*, days: int = 14, on: dt.date | None = None) -> dict:
    """Подстраховка сигналов: пересинхронизировать уроки последних `days`
    дней (проведённые и уже списанные). Идемпотентно."""
    on = on or timezone.localdate()
    since = on - dt.timedelta(days=days)
    completed = set(Lesson.objects.filter(status=Lesson.Status.COMPLETED, date__gte=since, date__lte=on)
                    .values_list("pk", flat=True))
    consumed = set(LessonConsumption.objects.filter(
        kind=LessonConsumption.Kind.CONSUME, status=LessonConsumption.Status.ACTIVE, lesson_date__gte=since,
    ).values_list("lesson_ref", flat=True))
    totals = {"lessons": 0, "consumed": 0, "reversed": 0, "failed": 0}
    for lesson_id in sorted(completed | consumed):
        totals["lessons"] += 1
        try:
            result = sync_lesson(lesson_id)
        except Exception:  # noqa: BLE001 — один урок не останавливает обработку остальных
            logger.exception("billing: lesson %s sync failed", lesson_id)
            totals["failed"] += 1
            continue
        totals["consumed"] += len(result["consumed"])
        totals["reversed"] += len(result["reversed"])
    return totals
