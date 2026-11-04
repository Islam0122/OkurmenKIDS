"""«Архив студентов» бухгалтерии — только чтение поверх единых данных.

Отдельной сущности «архивный студент» нет: архив — это `academy.Student`
со статусом WITHDRAWN («Деактивирован»), его последнее событие
`StudentStatusEvent(DEACTIVATED)` (дата, причина, комментарий, кто
оформил) и его договоры `StudentBillingProfile`. Ассистент деактивирует
студента в LMS → сигнал после коммита останавливает начисления
(`profiles.on_student_status_event`) → студент сразу виден здесь; при
восстановлении (статус снова ACTIVE) он так же сразу уходит из архива.

Деньги считаются только `contracts.money_summary` по каждому договору —
той же функцией, что карточка договора, очереди и отчёты. Здесь они лишь
суммируются по договорам студента:

* стоимость договора — итоговая стоимость курса (со скидкой);
* начислено — выставленные начисления (без аннулированных);
* оплачено — получено минус возвраты (подтверждённые платежи);
* скидка — скидка договора; корректировки/списания — отдельно;
* долг — «к оплате» по договору (`outstanding`; у остановленного договора —
  только наступившие начисления минус применимый аванс, будущие месяцы не
  долг); `due_now` — выставленные неоплаченные начисления на сегодня;
* переплата — свободный аванс, не покрывающий долг и будущие месяцы.

Модуль ничего не пишет: восстановление выполняет `academy.services.
student_status.reactivate_student` (тот же сервис, что у ассистента).
"""
from __future__ import annotations

import datetime as dt
from decimal import Decimal

from django.db.models import Count, Max, OuterRef, Prefetch, Q, Subquery

from apps.academy.models import Attendance, Group, Lesson, Student, StudentStatusEvent
from apps.accounting.models import StudentPayment

from ..models import Invoice, InvoiceAdjustment, LessonPackage, Receipt, StudentBillingProfile
from . import contracts

ZERO = Decimal("0.00")
DEACTIVATED = StudentStatusEvent.EventType.DEACTIVATED
REACTIVATED = StudentStatusEvent.EventType.REACTIVATED
TOTAL_KEYS = ("contract_price", "invoiced", "paid", "discount", "adjusted", "debt", "due_now", "overpayment")


def _s(value) -> str | None:
    return None if value is None else str(value)


def _user(user) -> dict | None:
    if user is None:
        return None
    return {"id": user.pk, "name": user.get_full_name() or user.get_username()}


def _ref(obj) -> dict | None:
    return None if obj is None else {"id": obj.pk, "name": str(obj)}


# ---------------------------------------------------------------------------
# Деньги студента (сумма по договорам; формула — contracts.money_summary)
# ---------------------------------------------------------------------------

def profile_totals(profile: StudentBillingProfile, summary: dict | None = None) -> dict:
    summary = summary or contracts.money_summary(profile)
    return {
        "contract_price": summary["final_course_price"],
        "invoiced": summary["invoiced"],
        "paid": summary["net_received"],
        "discount": summary["discount_amount"],
        "adjusted": summary["adjusted"],
        "debt": summary["outstanding"],
        "due_now": summary["due_now"],
        "overpayment": summary["credit_unreserved"],
    }


def student_finance(student: Student, profiles: list[StudentBillingProfile] | None = None) -> dict:
    """Итоги по всем договорам студента. `contract_price` — None, если ни у
    одного договора нет итоговой стоимости курса (тариф пакетов). Платежи
    вне оплаты обучения (без договора) в итоги не входят — как и в
    `money_summary`; они видны в истории платежей карточки."""
    if profiles is None:
        profiles = list(StudentBillingProfile.objects.filter(student=student).select_related("subject", "plan"))
    totals = {key: ZERO for key in TOTAL_KEYS}
    has_price = False
    for profile in profiles:
        for key, value in profile_totals(profile).items():
            if key == "contract_price":
                if value is None:
                    continue
                has_price = True
            totals[key] += value or ZERO
    if not has_price:
        totals["contract_price"] = None
    result = {key: _s(value) for key, value in totals.items()}
    result.update({"contracts_count": len(profiles), "has_debt": totals["debt"] > 0})
    return result


def stop_preview(student: Student) -> dict:
    """Что изменится в деньгах при остановке начислений (для окна деактивации):
    не начатые месяцы аннулируются (`profiles.deactivate_billing_profile`),
    поэтому их сумма не станет долгом; уже наступившие начисления останутся."""
    voided = ZERO
    live = StudentBillingProfile.objects.filter(student=student).exclude(
        status__in=StudentBillingProfile.CLOSED_STATUSES)
    for profile in live:
        not_started = profile.packages.filter(lessons_used=0, started_on__isnull=True, status__in=(
            LessonPackage.Status.PLANNED, LessonPackage.Status.ACTIVE))
        for invoice in Invoice.objects.filter(package__in=not_started).exclude(status=Invoice.Status.VOID):
            voided += invoice.amount
    return {"live_contracts": live.count(), "voided_on_stop": str(voided)}


# ---------------------------------------------------------------------------
# Список архива
# ---------------------------------------------------------------------------

def _last_event(event_type: str):
    return StudentStatusEvent.objects.filter(student=OuterRef("pk"), event_type=event_type).order_by(
        "-event_date", "-created_at", "-pk")


def archive_queryset():
    """Деактивированные студенты с их последней деактивацией (одна выборка)."""
    last = _last_event(DEACTIVATED)
    return (
        Student.objects.filter(status=Student.Status.WITHDRAWN)
        .annotate(
            deactivation_id=Subquery(last.values("pk")[:1]),
            deactivated_on=Subquery(last.values("event_date")[:1]),
            deactivation_reason=Subquery(last.values("reason")[:1]),
            last_group_id=Subquery(last.values("group_id")[:1]),
        )
        .select_related("group__course")
        .prefetch_related(Prefetch(
            "billing_profiles",
            queryset=StudentBillingProfile.objects.select_related("subject", "plan").order_by("-start_date", "-pk"),
            to_attr="archive_profiles",
        ))
        .order_by("-deactivated_on", "last_name", "first_name", "pk")
    )


def _date(value, name):
    if not value:
        return None
    try:
        return dt.date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{name}: неверная дата (ожидается ГГГГ-ММ-ДД)") from exc


def filter_archive(qs, params) -> tuple:
    """Фильтры в БД; фильтр по долгу (`debt=yes|no`) — после расчёта денег
    (`rows`), потому что долг — результат `money_summary`, а не поле."""
    for part in (params.get("search") or "").split():
        qs = qs.filter(Q(first_name__icontains=part) | Q(last_name__icontains=part)
                       | Q(phone__icontains=part) | Q(parent_phone__icontains=part))
    contract = (params.get("contract") or "").strip().lstrip("№#")
    if contract:
        # «31» — договор №31; «INV-2026-000031», «R-…» — номер начисления / чека.
        if contract.isdigit():
            match = Q(billing_profiles__pk=int(contract))
        else:
            match = Q(billing_profiles__invoices__number__icontains=contract) | Q(
                billing_profiles__receipts__number__icontains=contract)
        qs = qs.filter(match).distinct()
    if params.get("group"):
        gid = int(params["group"])
        qs = qs.filter(Q(last_group_id=gid) | Q(last_group_id__isnull=True, group_id=gid))
    if params.get("subject"):
        sid = int(params["subject"])
        qs = qs.filter(Q(billing_profiles__subject_id=sid) | Q(group__course__subjects__id=sid)).distinct()
    if params.get("reason"):
        qs = qs.filter(deactivation_reason=params["reason"])
    date_from, date_to = _date(params.get("date_from"), "date_from"), _date(params.get("date_to"), "date_to")
    if date_from:
        qs = qs.filter(deactivated_on__gte=date_from)
    if date_to:
        qs = qs.filter(deactivated_on__lte=date_to)
    return qs, (params.get("debt") or "").lower()


def subjects_of(student: Student, profiles) -> list[str]:
    names = [p.subject.name for p in profiles if p.subject_id]
    if not names and student.group_id:
        names = [s.name for s in student.group.course.subjects.all()]
    return list(dict.fromkeys(names))


def archive_row(student: Student, groups: dict[int, Group]) -> dict:
    profiles = list(getattr(student, "archive_profiles", None) or
                    StudentBillingProfile.objects.filter(student=student).select_related("subject", "plan"))
    group = groups.get(student.last_group_id) if getattr(student, "last_group_id", None) else student.group
    reason = getattr(student, "deactivation_reason", "") or ""
    return {
        "id": student.pk,
        "name": str(student),
        "group": _ref(group),
        "subjects": subjects_of(student, profiles),
        "contracts": [{"id": p.pk, "number": p.pk, "status": p.status, "status_display": p.get_status_display(),
                       "subject": p.subject.name if p.subject_id else None, "plan": p.plan.name} for p in profiles],
        "finance": student_finance(student, profiles),
        "deactivated_on": _s(getattr(student, "deactivated_on", None)),
        "reason": reason,
        "reason_display": StudentStatusEvent.Reason(reason).label if reason in StudentStatusEvent.Reason.values
        else StudentStatusEvent.UNKNOWN_REASON_LABEL,
        "status": student.status,
        "status_display": "Неактивен",
    }


def archive_rows(params) -> list[dict]:
    qs, debt = filter_archive(archive_queryset(), params)
    students = list(qs)
    group_ids = {s.last_group_id for s in students if s.last_group_id}
    groups = {g.pk: g for g in Group.objects.filter(pk__in=group_ids)}
    rows = [archive_row(s, groups) for s in students]
    if debt in ("yes", "1", "true"):
        rows = [r for r in rows if r["finance"]["has_debt"]]
    elif debt in ("no", "0", "false"):
        rows = [r for r in rows if not r["finance"]["has_debt"]]
    return rows


def statistics(rows: list[dict]) -> dict:
    """KPI архива по тем же строкам, что и таблица (тот же фильтр)."""
    debt = sum((Decimal(r["finance"]["debt"]) for r in rows), ZERO)
    paid = sum((Decimal(r["finance"]["paid"]) for r in rows), ZERO)
    overpayment = sum((Decimal(r["finance"]["overpayment"]) for r in rows), ZERO)
    with_debt = sum(1 for r in rows if r["finance"]["has_debt"])
    return {
        "total": len(rows), "debt_total": str(debt), "with_debt": with_debt, "without_debt": len(rows) - with_debt,
        "paid_total": str(paid), "overpayment_total": str(overpayment),
    }


# ---------------------------------------------------------------------------
# Карточка архивного студента
# ---------------------------------------------------------------------------

def _event_row(event: StudentStatusEvent) -> dict:
    return {
        "id": event.pk, "type": event.event_type, "type_display": event.get_event_type_display(),
        "date": _s(event.event_date), "reason": event.reason,
        "reason_display": event.get_reason_display() if event.reason else "",
        "comment": event.comment, "group": _ref(event.group), "from_group": _ref(event.from_group),
        "performed_by": _user(event.performed_by), "created_at": event.created_at.isoformat(),
        "last_activity_date": _s(event.last_activity_date), "study_days": event.study_days,
    }


def _payment_row(p: StudentPayment) -> dict:
    receipt = getattr(p, "receipt", None)
    return {
        "id": p.pk, "date": _s(p.received_date), "amount": str(p.amount), "kind": p.kind,
        "kind_display": p.get_kind_display(), "method": p.method, "method_display": p.get_method_display(),
        "status": p.status, "status_display": p.get_status_display(), "accepted_by": _user(p.created_by),
        "comment": p.comment, "reference": p.reference, "transaction": f"№{p.pk}",
        "receipt": None if receipt is None else {"id": receipt.pk, "number": receipt.number},
        "contract": p.billing_profile_id, "created_at": p.created_at.isoformat(),
    }


def _invoice_row(i: Invoice) -> dict:
    package = i.package
    label = i.get_kind_display()
    if i.kind == Invoice.Kind.MONTH and package.month_number:
        label = f"Учебный месяц №{package.month_number}"
    elif i.kind == Invoice.Kind.PACKAGE:
        label = f"Пакет уроков №{package.number}"
    return {
        "id": i.pk, "number": i.number, "date": _s(i.issue_date), "period_date": _s(i.period_date),
        "reason": label, "lessons_total": package.lessons_total, "lessons_used": package.lessons_used,
        "amount": str(i.amount), "paid": str(i.amount_paid), "adjusted": str(i.amount_adjusted),
        "balance": str(i.balance), "status": i.status, "status_display": i.get_status_display(),
        "void_reason": i.void_reason, "contract": i.profile_id,
    }


def _contract_row(profile: StudentBillingProfile) -> dict:
    summary = contracts.money_summary(profile)
    return {
        "id": profile.pk, "number": profile.pk, "status": profile.status, "status_display": profile.get_status_display(),
        "subject": profile.subject.name if profile.subject_id else None, "plan": profile.plan.name,
        "payment_mode_display": profile.get_payment_mode_display(), "start_date": _s(profile.start_date),
        "stopped_on": _s(profile.stopped_on), "stop_reason": profile.stop_reason,
        "stop_source_display": profile.get_stop_source_display() if profile.stop_source else "",
        "standard_course_price": _s(profile.standard_course_price), "final_course_price": _s(profile.final_course_price),
        "discount_amount": str(profile.discount_amount), "discount_reason": profile.discount_reason,
        "parent_name": profile.parent_name, "parent_phone": profile.parent_phone,
        "responsible_accountant": _user(profile.responsible_accountant),
        "totals": {k: _s(v) for k, v in profile_totals(profile, summary).items()},
        "terms_history": [
            {"id": c.pk, "status": c.status, "status_display": c.get_status_display(), "reason": c.reason,
             "final_course_price": _s(c.final_course_price), "discount_amount": str(c.discount_amount),
             "requested_by": _user(c.requested_by), "requested_at": c.requested_at.isoformat(),
             "decided_by": _user(c.decided_by), "decision_comment": c.decision_comment}
            for c in profile.terms_changes.select_related("requested_by", "decided_by").order_by("-requested_at")
        ],
        "adjustments": [
            {"id": a.pk, "invoice": a.invoice.number, "amount": str(a.amount), "reason": a.reason,
             "status": a.status, "status_display": a.get_status_display(), "date": _s(a.effective_date),
             "created_by": _user(a.created_by)}
            for a in InvoiceAdjustment.objects.filter(invoice__profile=profile).select_related(
                "invoice", "created_by").order_by("-effective_date", "-pk")
        ],
        "documents": [
            {"id": r.pk, "number": r.number, "kind_display": r.get_kind_display(),
             "status_display": r.get_status_display(), "issued_at": r.issued_at.isoformat()}
            for r in Receipt.objects.filter(profile=profile).order_by("-issued_at", "-pk")
        ],
    }


def _study_history(student: Student, events: list[StudentStatusEvent]) -> dict:
    attended = Attendance.objects.filter(
        student=student, status__in=(Attendance.Status.PRESENT, Attendance.Status.LATE),
    ).exclude(lesson__status=Lesson.Status.CANCELLED).aggregate(n=Count("pk"), last=Max("lesson__date"))
    groups: list[dict] = []
    for event in sorted(events, key=lambda e: (e.event_date, e.created_at)):
        target = event.group
        if target is not None and (not groups or groups[-1]["id"] != target.pk):
            groups.append({"id": target.pk, "name": target.name, "since": _s(event.event_date)})
    if student.group_id and (not groups or groups[-1]["id"] != student.group_id):
        groups.append({"id": student.group_id, "name": student.group.name, "since": _s(student.enrollment_date)})
    return {
        "groups": groups,
        "transfers": [_event_row(e) for e in events if e.event_type == StudentStatusEvent.EventType.TRANSFERRED],
        "attended_lessons": attended["n"], "last_attendance": _s(attended["last"]),
    }


def archive_detail(student: Student) -> dict:
    events = list(StudentStatusEvent.objects.filter(student=student).select_related(
        "group", "from_group", "performed_by").order_by("-event_date", "-created_at", "-pk"))
    deactivation = next((e for e in events if e.event_type == DEACTIVATED), None)
    profiles = list(StudentBillingProfile.objects.filter(student=student).select_related(
        "subject", "plan", "responsible_accountant").order_by("-start_date", "-pk"))
    payments = (StudentPayment.objects.filter(student=student).select_related("created_by", "receipt")
                .order_by("-received_date", "-pk"))
    invoices = (Invoice.objects.filter(profile__student=student).select_related("package")
                .order_by("-issue_date", "-pk"))
    last_group = deactivation.group if deactivation and deactivation.group_id else student.group
    return {
        "student": {
            "id": student.pk, "name": str(student), "first_name": student.first_name, "last_name": student.last_name,
            "phone": student.phone, "parent_phone": student.parent_phone,
            "parent_name": next((p.parent_name for p in profiles if p.parent_name), ""),
            "last_group": _ref(last_group), "subjects": subjects_of(student, profiles),
            "enrollment_date": _s(student.enrollment_date), "status": student.status,
            "status_display": student.get_status_display(), "is_archived": student.status == Student.Status.WITHDRAWN,
        },
        "deactivation": None if deactivation is None else _event_row(deactivation),
        "finance": student_finance(student, profiles),
        "contracts": [_contract_row(p) for p in profiles],
        "payments": [_payment_row(p) for p in payments],
        "invoices": [_invoice_row(i) for i in invoices],
        "status_history": [_event_row(e) for e in events if e.event_type in (DEACTIVATED, REACTIVATED)],
        "study": _study_history(student, events),
    }


# ---------------------------------------------------------------------------
# Восстановление: проверки до действия
# ---------------------------------------------------------------------------

def restore_check(student: Student) -> dict:
    """Можно ли восстановить и что произойдёт с договорами. Ничего не меняет.

    * группа — нужна открытая (активная или приостановленная);
    * договор, остановленный деактивацией, возобновится автоматически с даты
      возврата (`profiles.on_student_status_event`), если у студента нет
      другого действующего договора по тому же направлению; старые
      начисления и платежи не повторяются (уникальный бизнес-ключ начисления
      и списания урока), уроки периода отсутствия не списываются;
    * договор, закрытый вручную или завершённый, не возобновляется —
      предлагается оформить новый договор после восстановления.
    """
    groups = [
        {"id": g.pk, "name": g.name, "course": g.course.name, "status": g.status,
         "students_count": g.active_count, "max_students": g.max_students}
        for g in Group.objects.filter(status__in=(Group.Status.ACTIVE, Group.Status.PAUSED)).select_related("course")
        .annotate(active_count=Count("students", filter=Q(students__status=Student.Status.ACTIVE)))
        .order_by("name")
    ]
    profiles = list(StudentBillingProfile.objects.filter(student=student).select_related("subject", "plan"))
    resumable, closed = [], []
    for p in profiles:
        row = {"id": p.pk, "subject": p.subject.name if p.subject_id else None, "plan": p.plan.name,
               "status_display": p.get_status_display()}
        stopped_by_status = (p.status == StudentBillingProfile.Status.INACTIVE
                             and p.stop_source == StudentBillingProfile.StopSource.STUDENT_STATUS)
        (resumable if stopped_by_status else closed).append(row)
    warnings = []
    if student.status != Student.Status.WITHDRAWN:
        warnings.append("Студент не в архиве — восстанавливать нечего.")
    if not groups:
        warnings.append("Нет открытых групп — сначала откройте группу.")
    if not resumable:
        warnings.append("Действующего договора не будет — после восстановления оформите новый договор.")
    return {
        "can_restore": student.status == Student.Status.WITHDRAWN and bool(groups),
        "groups": groups, "resumable_contracts": resumable, "closed_contracts": closed,
        "needs_new_contract": not resumable, "warnings": warnings,
        "finance": student_finance(student, profiles),
    }
