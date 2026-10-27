"""Кадровые показатели: главная HR, ежедневный и ежемесячный отчёты.

Всё считается по записям в базе: кандидаты (дата добавления, текущий этап),
собеседования (время, статус) и журнал HRActivity (переходы этапов, переносы,
отмены). Показатель, который нельзя достоверно посчитать, не выводится.
"""
from __future__ import annotations

import csv
import io
from collections import Counter, defaultdict
from datetime import date, datetime, time, timedelta

from django.db.models import Count, Q, QuerySet
from django.utils import timezone

from apps.staff_attendance.services.export import safe_cell
from apps.users.models import User

from ..models import Candidate, HRActivity, Interview, Vacancy

S = Candidate.Status
K = HRActivity.Kind

# Воронка: «дошёл до этапа» — достиг его или любого следующего.
FUNNEL = [S.NEW, S.CONTACTED, S.INTERVIEW_SCHEDULED, S.INTERVIEW_DONE, S.OFFER, S.HIRED]
RANK = {S.NEW: 0, S.CONTACTED: 1, S.INTERVIEW_SCHEDULED: 2, S.INTERVIEW_DONE: 3, S.AWAITING_DECISION: 3,
        S.OFFER: 4, S.HIRED: 5}
WAITING = (S.INTERVIEW_DONE, S.AWAITING_DECISION)
DECISIONS = (S.OFFER, S.HIRED, S.REJECTED, S.WITHDRAWN)


def day_bounds(day: date) -> tuple[datetime, datetime]:
    start = timezone.make_aware(datetime.combine(day, time.min))
    return start, start + timedelta(days=1)


def month_bounds(year: int, month: int) -> tuple[date, date]:
    first = date(year, month, 1)
    last = (date(year + (month == 12), month % 12 + 1, 1)) - timedelta(days=1)
    return first, last


# ---------------------------------------------------------------------------
# Фильтры (должность, вакансия, источник, ответственный)
# ---------------------------------------------------------------------------

def candidate_filter(filters: dict, prefix: str = "") -> Q:
    q = Q()
    if filters.get("vacancy"):
        q &= Q(**{f"{prefix}vacancy_id": filters["vacancy"]})
    if filters.get("source"):
        q &= Q(**{f"{prefix}source": filters["source"]})
    if filters.get("responsible"):
        q &= Q(**{f"{prefix}responsible_id": filters["responsible"]})
    if filters.get("position"):
        text = filters["position"]
        q &= (Q(**{f"{prefix}position__icontains": text}) | Q(**{f"{prefix}vacancy__title__icontains": text})
              | Q(**{f"{prefix}vacancy__department__icontains": text}))
    return q


def _candidates(filters: dict) -> QuerySet:
    return Candidate.objects.filter(candidate_filter(filters))


def _interviews(filters: dict) -> QuerySet:
    return Interview.objects.select_related("candidate", "interviewer", "vacancy").filter(
        candidate_filter(filters, "candidate__"))


def _events(filters: dict) -> QuerySet:
    return HRActivity.objects.filter(candidate__isnull=False).filter(candidate_filter(filters, "candidate__"))


def _local(value: datetime) -> str:
    return timezone.localtime(value).isoformat()


def interview_brief(interview: Interview) -> dict:
    return {
        "id": interview.pk,
        "scheduled_at": _local(interview.scheduled_at),
        "duration_minutes": interview.duration_minutes,
        "status": interview.status,
        "status_label": interview.get_status_display(),
        "format_label": interview.get_format_display(),
        "candidate": {"id": interview.candidate_id, "full_name": interview.candidate.full_name},
        "interviewer": interview.interviewer.get_full_name() or interview.interviewer.username,
        "position": interview.vacancy.title if interview.vacancy_id else interview.candidate.position,
    }


def candidate_brief(candidate: Candidate) -> dict:
    return {
        "id": candidate.pk,
        "full_name": candidate.full_name,
        "status": candidate.status,
        "status_label": candidate.get_status_display(),
        "position": candidate.position_label,
        "source_label": candidate.get_source_display(),
        "added_on": candidate.added_on.isoformat(),
    }


def activity_brief(entry: HRActivity) -> dict:
    return {
        "id": entry.pk,
        "kind": entry.kind,
        "kind_label": entry.get_kind_display(),
        "message": entry.message,
        "created_at": _local(entry.created_at),
        "actor": (entry.actor.get_full_name() or entry.actor.username) if entry.actor_id else None,
        "candidate": {"id": entry.candidate_id, "full_name": entry.candidate.full_name} if entry.candidate_id else None,
        "employee": ({"id": entry.employee_id, "full_name": entry.employee.get_full_name() or entry.employee.username}
                     if entry.employee_id else None),
        "from_status": entry.from_status,
        "to_status": entry.to_status,
    }


def visible_activity(qs: QuerySet) -> QuerySet:
    """Лента без служебной записи «вход в этап «Новый»» — её дублирует
    «Добавлен кандидат»; в журнале она остаётся для расчёта времени этапов."""
    return qs.exclude(kind=K.CANDIDATE_STATUS, from_status="")


def _status_counts(qs: QuerySet) -> dict[str, int]:
    counts = dict(qs.order_by().values("status").annotate(n=Count("id")).values_list("status", "n"))
    return {value: counts.get(value, 0) for value, _ in S.choices}


# ---------------------------------------------------------------------------
# Главная
# ---------------------------------------------------------------------------

def dashboard(date_from: date, date_to: date) -> dict:
    now = timezone.now()
    today_start, today_end = day_bounds(timezone.localdate())
    staff = User.objects.filter(role__in=User.HR_MANAGEABLE_ROLES, is_superuser=False, is_staff=False)
    period_start, _ = day_bounds(date_from)
    _, period_end = day_bounds(date_to)
    statuses = _status_counts(Candidate.objects.all())
    scheduled = Interview.objects.filter(status=Interview.Status.SCHEDULED)
    upcoming = (Interview.objects.select_related("candidate", "interviewer", "vacancy")
                .filter(status=Interview.Status.SCHEDULED, scheduled_at__gte=now - timedelta(hours=1))
                .order_by("scheduled_at")[:8])
    recent = visible_activity(HRActivity.objects.select_related("actor", "candidate", "employee"))[:12]
    return {
        "period": {"date_from": date_from.isoformat(), "date_to": date_to.isoformat()},
        "employees_active": staff.filter(is_active=True).count(),
        "employees_new": staff.filter(created_at__gte=period_start, created_at__lt=period_end).count(),
        "candidates_total": sum(statuses.values()),
        "candidates_in_progress": sum(n for s, n in statuses.items() if s not in (S.HIRED, S.REJECTED, S.WITHDRAWN)),
        "candidates_by_status": statuses,
        "interviews_scheduled": scheduled.filter(scheduled_at__gte=now).count(),
        "interviews_today": Interview.objects.exclude(status=Interview.Status.CANCELLED).filter(
            scheduled_at__gte=today_start, scheduled_at__lt=today_end).count(),
        "awaiting_decision": statuses[S.INTERVIEW_DONE] + statuses[S.AWAITING_DECISION],
        "interview_passed": statuses[S.INTERVIEW_DONE],
        "offers": statuses[S.OFFER],
        "hired": statuses[S.HIRED],
        "rejected": statuses[S.REJECTED],
        "withdrawn": statuses[S.WITHDRAWN],
        "vacancies_open": Vacancy.objects.filter(status=Vacancy.Status.OPEN).count(),
        "upcoming_interviews": [interview_brief(i) for i in upcoming],
        "recent_activity": [activity_brief(a) for a in recent],
    }


# ---------------------------------------------------------------------------
# Ежедневный отчёт
# ---------------------------------------------------------------------------

def daily(day: date, filters: dict) -> dict:
    start, end = day_bounds(day)
    new = _candidates(filters).select_related("vacancy").filter(added_on=day).order_by("last_name", "first_name")
    planned = _interviews(filters).filter(scheduled_at__gte=start, scheduled_at__lt=end).exclude(
        status=Interview.Status.CANCELLED).order_by("scheduled_at")
    events = _events(filters).filter(created_at__gte=start, created_at__lt=end)
    transitions = Counter(events.filter(kind=K.CANDIDATE_STATUS, to_status__in=DECISIONS)
                          .values_list("to_status", flat=True))
    waiting = _candidates(filters).filter(status__in=WAITING)
    return {
        "date": day.isoformat(),
        "new_candidates": len(new),
        "new_candidates_list": [candidate_brief(c) for c in new],
        "interviews_planned": len(planned),
        "interviews_list": [interview_brief(i) for i in planned],
        "interviews_conducted": sum(1 for i in planned if i.status == Interview.Status.COMPLETED),
        "interviews_rescheduled": events.filter(kind=K.INTERVIEW_RESCHEDULED).values("interview").distinct().count(),
        "interviews_cancelled": events.filter(kind=K.INTERVIEW_CANCELLED).values("interview").distinct().count(),
        "awaiting_decision_now": waiting.count(),
        "decisions": sum(transitions.values()),
        "offers": transitions[S.OFFER],
        "hired": transitions[S.HIRED],
        "rejected": transitions[S.REJECTED],
        "withdrawn": transitions[S.WITHDRAWN],
    }


# ---------------------------------------------------------------------------
# Ежемесячный отчёт
# ---------------------------------------------------------------------------

def _reached(cohort_ids: list[int]) -> dict[int, int]:
    """Наибольший ранг воронки, которого достиг каждый кандидат (по журналу)."""
    best = {cid: 0 for cid in cohort_ids}
    rows = HRActivity.objects.filter(candidate_id__in=cohort_ids, kind=K.CANDIDATE_STATUS).values_list(
        "candidate_id", "to_status")
    for cid, status in rows:
        rank = RANK.get(status)
        if rank is not None and rank > best[cid]:
            best[cid] = rank
    return best


def _stage_durations(filters: dict, start: datetime, end: datetime) -> list[dict]:
    """Среднее время на этапе по переходам, завершившимся в периоде. Учитываются
    только этапы, время входа в которые есть в журнале."""
    leaving = list(_events(filters).filter(kind=K.CANDIDATE_STATUS, created_at__gte=start, created_at__lt=end)
                   .exclude(from_status="").values_list("candidate_id", "from_status", "created_at"))
    if not leaving:
        return []
    candidates = {c for c, _, _ in leaving}
    history = defaultdict(list)
    for cid, to_status, at in (HRActivity.objects.filter(candidate_id__in=candidates, kind=K.CANDIDATE_STATUS)
                               .order_by("created_at", "id").values_list("candidate_id", "to_status", "created_at")):
        history[cid].append((to_status, at))
    totals: dict[str, list[float]] = defaultdict(list)
    for cid, stage, left_at in leaving:
        entered = [at for status, at in history[cid] if status == stage and at <= left_at]
        if entered:
            totals[stage].append((left_at - entered[-1]).total_seconds() / 3600)
    labels = dict(S.choices)
    return [
        {"status": stage, "status_label": labels[stage], "transitions": len(hours),
         "average_hours": round(sum(hours) / len(hours), 1)}
        for stage, hours in sorted(totals.items(), key=lambda item: RANK.get(item[0], 9))
    ]


def monthly(year: int, month: int, filters: dict) -> dict:
    first, last = month_bounds(year, month)
    start, _ = day_bounds(first)
    _, end = day_bounds(last)
    cohort = _candidates(filters).select_related("vacancy").filter(added_on__range=(first, last))
    cohort_list = list(cohort)
    events = _events(filters).filter(created_at__gte=start, created_at__lt=end)
    transitions = Counter(events.filter(kind=K.CANDIDATE_STATUS).values_list("to_status", flat=True))

    reached = _reached([c.pk for c in cohort_list])
    funnel = []
    for index, stage in enumerate(FUNNEL):
        count = sum(1 for rank in reached.values() if rank >= index)
        previous = funnel[-1]["count"] if funnel else None
        funnel.append({
            "status": stage, "status_label": S(stage).label, "count": count,
            "conversion_percent": round(count * 100 / previous, 1) if previous else None,
        })

    hire_days = []
    hired_events = events.filter(kind=K.CANDIDATE_STATUS, to_status=S.HIRED).select_related("candidate")
    for entry in hired_events:
        hire_days.append((timezone.localtime(entry.created_at).date() - entry.candidate.added_on).days)

    by_vacancy = Counter(c.vacancy.title if c.vacancy_id else (c.position or "Без вакансии") for c in cohort_list)
    by_source = Counter(c.get_source_display() for c in cohort_list)
    by_stage = Counter(c.status for c in cohort_list)
    return {
        "month": f"{year:04d}-{month:02d}",
        "new_candidates": len(cohort_list),
        "interviews_conducted": _interviews(filters).filter(
            status=Interview.Status.COMPLETED, scheduled_at__gte=start, scheduled_at__lt=end).count(),
        "interviews_cancelled": events.filter(kind=K.INTERVIEW_CANCELLED).values("interview").distinct().count(),
        "interviews_rescheduled": events.filter(kind=K.INTERVIEW_RESCHEDULED).count(),
        "hired": transitions[S.HIRED],
        "rejected": transitions[S.REJECTED],
        "withdrawn": transitions[S.WITHDRAWN],
        "offers": transitions[S.OFFER],
        "by_stage": [{"status": value, "status_label": label, "count": by_stage.get(value, 0)}
                     for value, label in S.choices],
        "funnel": funnel,
        "by_vacancy": [{"label": label, "count": n} for label, n in by_vacancy.most_common()],
        "by_source": [{"label": label, "count": n} for label, n in by_source.most_common()],
        "stage_durations": _stage_durations(filters, start, end),
        "average_days_to_hire": round(sum(hire_days) / len(hire_days), 1) if hire_days else None,
    }


# ---------------------------------------------------------------------------
# CSV
# ---------------------------------------------------------------------------

def _csv(rows: list[list]) -> str:
    buffer = io.StringIO()
    buffer.write("﻿")  # Excel открывает UTF-8 с BOM без «кракозябр»
    writer = csv.writer(buffer, delimiter=";")
    for row in rows:
        writer.writerow([safe_cell(cell) for cell in row])
    return buffer.getvalue()


def daily_csv(report: dict) -> str:
    rows = [["Ежедневный HR-отчёт", report["date"]], [], ["Показатель", "Значение"]]
    for key, label in (
        ("new_candidates", "Новые кандидаты"), ("interviews_planned", "Запланированные собеседования"),
        ("interviews_conducted", "Проведённые собеседования"), ("interviews_rescheduled", "Перенесённые встречи"),
        ("interviews_cancelled", "Отменённые встречи"), ("awaiting_decision_now", "Ожидают решения (сейчас)"),
        ("decisions", "Принятые решения"), ("offers", "Предложения о работе"), ("hired", "Приняты на работу"),
        ("rejected", "Отказы"), ("withdrawn", "Кандидат отказался"),
    ):
        rows.append([label, report[key]])
    rows += [[], ["Собеседования"], ["Время", "Кандидат", "Должность", "Интервьюер", "Статус"]]
    for item in report["interviews_list"]:
        rows.append([item["scheduled_at"][11:16], item["candidate"]["full_name"], item["position"],
                     item["interviewer"], item["status_label"]])
    rows += [[], ["Новые кандидаты"], ["Кандидат", "Должность", "Источник", "Этап"]]
    for item in report["new_candidates_list"]:
        rows.append([item["full_name"], item["position"], item["source_label"], item["status_label"]])
    return _csv(rows)


def monthly_csv(report: dict) -> str:
    rows = [["Ежемесячный HR-отчёт", report["month"]], [], ["Показатель", "Значение"]]
    for key, label in (
        ("new_candidates", "Новые кандидаты"), ("interviews_conducted", "Проведённые собеседования"),
        ("interviews_cancelled", "Отменённые встречи"), ("interviews_rescheduled", "Переносы встреч"),
        ("offers", "Предложения о работе"), ("hired", "Приняты на работу"), ("rejected", "Отказы"),
        ("withdrawn", "Кандидат отказался"), ("average_days_to_hire", "Среднее время до найма, дней"),
    ):
        rows.append([label, "" if report[key] is None else report[key]])
    rows += [[], ["Кандидаты месяца по этапам"], ["Этап", "Кандидатов"]]
    rows += [[item["status_label"], item["count"]] for item in report["by_stage"]]
    rows += [[], ["Воронка"], ["Этап", "Дошли", "Конверсия от предыдущего, %"]]
    rows += [[item["status_label"], item["count"], "" if item["conversion_percent"] is None
              else item["conversion_percent"]] for item in report["funnel"]]
    rows += [[], ["По вакансиям"], ["Вакансия", "Кандидатов"]]
    rows += [[item["label"], item["count"]] for item in report["by_vacancy"]]
    rows += [[], ["По источникам"], ["Источник", "Кандидатов"]]
    rows += [[item["label"], item["count"]] for item in report["by_source"]]
    if report["stage_durations"]:
        rows += [[], ["Среднее время на этапе"], ["Этап", "Переходов", "Среднее, ч"]]
        rows += [[item["status_label"], item["transitions"], item["average_hours"]] for item in report["stage_durations"]]
    return _csv(rows)
