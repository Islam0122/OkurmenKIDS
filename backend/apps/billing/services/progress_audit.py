"""Сверка учебного прогресса академии и бухгалтерии (только чтение).

Для каждого договора по программе сравниваются:

* **академия** — проведённые (`completed`) уроки приоритетного предмета
  договора в группах ученика (текущая и из истории переводов), как их
  считает вкладка «Программы» группы: всего и с даты начала договора;
* **бухгалтерия** — засчитанные уроки (действующие списания `LessonConsumption`)
  и то, что показывает строка «Все студенты» (`queues.contract_row`): номер
  текущего пакета и уроки в нём;
* **правило** «12 засчитанных уроков на месяц»: уроки 1–12 → месяц 1,
  13–24 → месяц 2… — месяц и прогресс месяца по числу засчитанных уроков;
* **деньги** — стадия, «К оплате сейчас», просрочка, аванс, начисления по
  месяцам (сумма, статус, остаток, срок) — чтобы аванс не принимался за
  оплату конкретного начисления.

Каждое расхождение получает код и объяснение (`FINDINGS`). Ничего не
меняет: ни уроки, ни посещаемость, ни начисления, ни платежи."""
from __future__ import annotations

from collections import Counter

from django.db.models import Q

from apps.academy.models import Lesson

from ..models import Invoice, LessonConsumption, StudentBillingProfile
from .contracts import money_summary
from .lessons import _student_group_ids, lesson_breakdown

FINDINGS = {
    "boundary_month": "Месяц завершён ровно на границе (12, 24, … уроков): бухгалтерия уже показывает следующий "
                      "месяц с 0 уроков, по правилу «1–12 → месяц 1» это ещё последний урок прошлого месяца.",
    "count_mismatch": "Проведённых уроков предмета в группе с начала договора больше / меньше, чем засчитано "
                      "в бухгалтерии — причины по урокам в `excluded`.",
    "not_processed": "Урок подлежит списанию, но не засчитан (сигнал / фоновая задача не обработали) — "
                     "исправляет billing_resync_lessons / sync_profile_history.",
    "before_contract": "Проведённые уроки до даты начала договора не засчитываются — проверьте дату начала.",
    "package_mismatch": "Номер пакета или уроки в нём не совпадают с правилом по числу засчитанных уроков "
                        "(не на границе) — нужна ручная проверка пакетов.",
    "credit_unapplied": "Аванс лежит рядом с неоплаченным начислением: «К оплате сейчас» его учитывает, "
                        "но начисление не оплачено (статус не «Оплачено»).",
    "overdue_before_deadline": "Начисление «Просрочено», хотя в его месяце засчитано не больше уроков, чем "
                               "срок оплаты, — проверьте начисление.",
}


def _rule(counted: int, per_month: int, duration: int | None) -> dict:
    """Месяц по правилу: уроки 1..per_month → 1, следующие per_month → 2…"""
    if not per_month:
        return {"month": None, "in_month": None}
    if counted <= 0:
        return {"month": 1, "in_month": 0}
    month = (counted - 1) // per_month + 1
    if duration:
        month = min(month, duration)
    return {"month": month, "in_month": counted - (month - 1) * per_month}


def profile_progress(profile: StudentBillingProfile) -> dict:
    from .queues import base_queryset, contract_row

    profile = base_queryset().get(pk=profile.pk)
    groups = _student_group_ids(profile.student_id)
    held = Lesson.objects.filter(group_id__in=groups, status=Lesson.Status.COMPLETED)
    if profile.subject_id:
        held = held.filter(subject_id=profile.subject_id)
    held_since = held.filter(date__gte=profile.start_date)
    if profile.stopped_on:
        held_since = held_since.filter(date__lt=profile.stopped_on)
    counted = LessonConsumption.objects.filter(profile=profile, kind=LessonConsumption.Kind.CONSUME,
                                               status=LessonConsumption.Status.ACTIVE).count()
    duplicates = (LessonConsumption.objects.filter(profile=profile, kind=LessonConsumption.Kind.CONSUME,
                                                   status=LessonConsumption.Status.ACTIVE)
                  .values("lesson_ref").order_by().distinct().count())
    breakdown = lesson_breakdown(profile)
    excluded = Counter(r["reason"] for r in breakdown["lessons"]
                       if r["reason"] != "counted" and r["lesson_status"] == Lesson.Status.COMPLETED
                       and (not profile.subject_id or r["subject"] == profile.subject.name))
    row = contract_row(profile)
    per_month = profile.lessons_per_month or (row["lessons_total"] or 0)
    rule = _rule(counted, per_month, profile.duration_months)
    s = money_summary(profile)
    invoices = []
    for inv in (Invoice.objects.filter(profile=profile).exclude(status=Invoice.Status.VOID)
                .select_related("package").order_by("package__number", "pk")):
        invoices.append({
            "number": inv.number, "kind": inv.kind, "month": inv.package.month_number, "amount": str(inv.amount),
            "paid": str(inv.amount_paid + inv.amount_adjusted), "balance": str(inv.balance), "status": inv.status,
            "due_lesson": inv.due_lesson, "month_lessons_used": inv.package.lessons_used,
            "issue_date": inv.issue_date.isoformat(),
        })
    findings = []
    shown_month, shown_used = row["month_number"], row["lessons_used"]
    if counted and per_month and counted % per_month == 0 and shown_used == 0 and shown_month == rule["month"] + 1:
        findings.append("boundary_month")
    elif rule["month"] and (shown_month, shown_used) != (rule["month"], rule["in_month"]):
        findings.append("package_mismatch")
    if held_since.count() != counted:
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
    return {
        "profile": profile.pk, "student": str(profile.student), "plan": profile.plan.name,
        "group": profile.student.group.name if profile.student.group_id else None,
        "subject": profile.subject.name if profile.subject_id else None,
        "contract_start": profile.start_date.isoformat(), "absence_policy": profile.plan.absence_policy,
        "academy": {"held_all_time": held.count(), "held_since_contract": held_since.count(),
                    "course_plan": (profile.duration_months or 0) * per_month or None},
        "billing": {"counted": counted, "counted_distinct_lessons": duplicates,
                    "shown": f"месяц {shown_month} из {row['duration_months']}, IT {shown_used}/{row['lessons_total']}",
                    "excluded": dict(excluded)},
        "rule": {"month": rule["month"], "month_progress": rule["in_month"], "per_month": per_month,
                 "shown": (f"месяц {rule['month']} из {profile.duration_months}, {rule['in_month']} из {per_month}"
                           if rule["month"] else None),
                 "course_progress": f"{counted} из {(profile.duration_months or 0) * per_month}"},
        "money": {"stage": row["stage"], "due_now": str(s["due_now"]), "overdue": str(s["overdue"]),
                  "credit": str(s["credit"]), "credit_unapplied": str(s["credit_unapplied"]),
                  "outstanding": str(s["outstanding"]), "invoices": invoices},
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
