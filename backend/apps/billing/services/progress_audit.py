"""Сверка учебного прогресса академии и бухгалтерии (только чтение).

Для каждого договора по программе — три независимых показателя
(`services.progress`) и деньги:

* **учебный месяц группы** — проведённые IT-занятия текущей группы, месяц
  по тарифу программы курса (одинаков у всех учеников группы); если
  программа или тариф неоднозначны — предупреждение;
* **посещаемость ученика** — посещённые им проведённые занятия группы;
* **финансовый пакет** — пакет договора и засчитанные ученику уроки
  (действующие списания `LessonConsumption`), с причинами незасчитанных;
* **деньги** — стадия, «К оплате сейчас» по срокам, аванс, начисления
  (период, дата создания, срок, оплачено, остаток), платежи с
  распределениями — чтобы аванс не принимался за оплату начисления.

Расхождение месяца группы и финансового пакета — справочно (ученик пришёл
позже, пропуски по правилу тарифа): начисления идут по договору.
Каждое расхождение получает код и объяснение (`FINDINGS`). Ничего не
меняет: ни уроки, ни посещаемость, ни начисления, ни платежи."""
from __future__ import annotations

from collections import Counter
from decimal import Decimal

from django.db.models import Q

from apps.academy.models import Lesson
from apps.accounting.models import StudentPayment

from ..models import Invoice, LessonConsumption, StudentBillingProfile
from . import progress as study
from .contracts import money_summary
from .lessons import _student_group_ids, lesson_breakdown

FINDINGS = {
    "group_month_unavailable": "Учебный месяц группы не определён — см. предупреждение (программа / тариф / группа).",
    "package_differs_from_group": "Финансовый пакет договора не совпадает с учебным месяцем группы (ученик пришёл "
                                  "позже, пропуски по правилу тарифа и т. п.) — справочно: начисления идут по договору.",
    "count_mismatch": "Проведённых уроков предмета в группах ученика с начала договора больше / меньше, чем засчитано "
                      "по договору — причины по урокам в `excluded`.",
    "not_processed": "Урок подлежит списанию, но не засчитан (сигнал / фоновая задача не обработали) — "
                     "исправляет billing_resync_lessons / sync_profile_history.",
    "before_contract": "Проведённые уроки до даты начала договора не засчитываются — проверьте дату начала.",
    "package_mismatch": "Уроки в пакетах (lessons_used) не совпадают с действующими списаниями — счётчики "
                        "пакетов расходятся с журналом списаний, нужна ручная проверка.",
    "credit_unapplied": "Аванс лежит рядом с неоплаченным начислением: «К оплате сейчас» его учитывает, "
                        "но начисление не оплачено (статус не «Оплачено»).",
    "overdue_before_deadline": "Начисление «Просрочено», хотя в его месяце засчитано не больше уроков, чем "
                               "срок оплаты, — проверьте начисление.",
    "possible_duplicate_payment": "Два проведённых платежа на одну сумму с одной датой — сверьте с кассой, не "
                                  "внесены ли одни деньги дважды (автоматически не исправляется).",
}


def _held_since_contract(profile) -> int:
    """Проведённые уроки предмета договора в группах ученика (текущая и из
    истории) с даты начала договора — для сверки с засчитанными."""
    held = Lesson.objects.filter(group_id__in=_student_group_ids(profile.student_id), status=Lesson.Status.COMPLETED,
                                 date__gte=profile.start_date)
    if profile.subject_id:
        held = held.filter(subject_id=profile.subject_id)
    if profile.stopped_on:
        held = held.filter(date__lt=profile.stopped_on)
    return held.count()


def profile_progress(profile: StudentBillingProfile) -> dict:
    from .queues import base_queryset, contract_row

    profile = base_queryset().get(pk=profile.pk)
    current_group = profile.student.group if profile.student.group_id else None
    counted = LessonConsumption.objects.filter(profile=profile, kind=LessonConsumption.Kind.CONSUME,
                                               status=LessonConsumption.Status.ACTIVE).count()
    distinct = (LessonConsumption.objects.filter(profile=profile, kind=LessonConsumption.Kind.CONSUME,
                                                 status=LessonConsumption.Status.ACTIVE)
                .values("lesson_ref").order_by().distinct().count())
    breakdown = lesson_breakdown(profile)
    excluded = Counter(r["reason"] for r in breakdown["lessons"]
                       if r["reason"] != "counted" and r["lesson_status"] == Lesson.Status.COMPLETED
                       and (not profile.subject_id or r["subject"] == profile.subject.name))
    row = contract_row(profile)
    group = row["group_progress"] or {}
    package = study.financial_package(profile)
    visits = study.attendance(profile, current_group)
    held_since = _held_since_contract(profile)
    s = money_summary(profile)
    invoices = []
    for inv in (Invoice.objects.filter(profile=profile).exclude(status=Invoice.Status.VOID)
                .select_related("package").order_by("package__number", "pk")):
        invoices.append({
            "number": inv.number, "kind": inv.kind, "month": inv.package.month_number, "amount": str(inv.amount),
            "paid": str(inv.amount_paid + inv.amount_adjusted), "balance": str(inv.balance), "status": inv.status,
            "due_lesson": inv.due_lesson, "month_lessons_used": inv.package.lessons_used,
            "due_date": None if inv.due_lesson else inv.due_date.isoformat(),
            "period_date": inv.period_date.isoformat(), "issue_date": inv.issue_date.isoformat(),
            "created_at": inv.created_at.isoformat(),
        })
    payments = []
    for p in (StudentPayment.objects.filter(billing_profile=profile).select_related("receipt")
              .prefetch_related("billing_allocations__invoice").order_by("received_date", "pk")):
        receipt = getattr(p, "receipt", None)
        allocations = [{"invoice": a.invoice.number, "amount": str(a.amount), "status": a.status}
                       for a in p.billing_allocations.all()]
        active = sum((a.amount for a in p.billing_allocations.all() if a.status == "ACTIVE"), Decimal(0))
        payments.append({
            "id": p.pk, "kind": p.kind, "status": p.status, "purpose": p.purpose, "amount": str(p.amount),
            "received_date": p.received_date.isoformat(), "created_at": p.created_at.isoformat(),
            "receipt": receipt.number if receipt else None, "allocations": allocations,
            "unallocated": str(p.amount - active) if p.kind == StudentPayment.Kind.PAYMENT
            and p.status == StudentPayment.Status.CONFIRMED else None,
        })
    same_day = Counter((p["amount"], p["received_date"]) for p in payments
                       if p["status"] == StudentPayment.Status.CONFIRMED and p["kind"] == StudentPayment.Kind.PAYMENT)
    findings = []
    if group.get("status") != "ok":
        findings.append("group_month_unavailable")
    elif package and (package["number"], package["lessons_used"]) != (group["month"], group["in_month"]):
        findings.append("package_differs_from_group")
    if package and package["counted"] != counted:
        findings.append("package_mismatch")
    if held_since != counted:
        findings.append("count_mismatch")
    if excluded.get("not_processed"):
        findings.append("not_processed")
    if excluded.get("before_contract"):
        findings.append("before_contract")
    if s["credit_unapplied"] > 0:
        findings.append("credit_unapplied")
    if any(i["status"] == Invoice.Status.OVERDUE and i["due_lesson"] and i["month_lessons_used"] <= i["due_lesson"]
           for i in invoices):
        findings.append("overdue_before_deadline")
    if any(n > 1 for n in same_day.values()):
        findings.append("possible_duplicate_payment")
    return {
        "profile": profile.pk, "student": str(profile.student), "plan": profile.plan.name,
        "group": profile.student.group.name if profile.student.group_id else None,
        "subject": profile.subject.name if profile.subject_id else None,
        "contract_start": profile.start_date.isoformat(), "absence_policy": profile.plan.absence_policy,
        "group_month": {k: group.get(k) for k in ("status", "warning", "group_name", "held", "month", "months",
                                                  "in_month", "per_month", "total")},
        "shown": (f"Месяц группы {group['month']} из {group['months']} · IT {group['in_month']}/{group['per_month']}"
                  if group.get("status") == "ok" else group.get("warning")),
        "attendance": visits,
        "package": {**(package or {}), "shown": (f"финансовый пакет №{package['number']}: "
                                                   f"{package['lessons_used']}/{package['lessons_total']}" if package else None)},
        "billing": {"counted": counted, "counted_distinct_lessons": distinct, "held_since_contract": held_since,
                    "excluded": dict(excluded)},
        "money": {"stage": row["stage"], "due_now": str(s["due_now"]), "overdue": str(s["overdue"]),
                  "credit": str(s["credit"]), "credit_unapplied": str(s["credit_unapplied"]),
                  "outstanding": str(s["outstanding"]), "received": str(s["net_received"]),
                  "allocated": str(s["allocated"]), "due_today": row["due_today_amount"],
                  "not_due": row["not_due_amount"], "invoices": invoices, "payments": payments},
        "findings": [{"code": c, "detail": FINDINGS[c]} for c in findings],
    }


def progress_audit(*, student: str | None = None, group: str | None = None, plan: str | None = None,
                   profile_id: int | None = None) -> dict:
    qs = StudentBillingProfile.objects.filter(duration_months__isnull=False).select_related("student", "plan")
    if profile_id:
        qs = qs.filter(pk=profile_id)
    for part in (student or "").split():
        qs = qs.filter(Q(student__first_name__icontains=part) | Q(student__last_name__icontains=part))
    if group:
        qs = qs.filter(student__group__name__icontains=group)
    if plan:
        qs = qs.filter(plan__name__icontains=plan)
    rows = [profile_progress(p) for p in qs.order_by("student__last_name", "student__first_name", "pk")]
    return {"total": len(rows), "with_findings": sum(1 for r in rows if r["findings"]),
            "by_finding": dict(Counter(f["code"] for r in rows for f in r["findings"])), "rows": rows}


__all__ = ["FINDINGS", "profile_progress", "progress_audit"]
