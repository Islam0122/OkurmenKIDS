"""Кадровые показатели: главная HR, ежедневный и периодический (месячный) отчёты.

Всё считается по записям в базе — откликам (дата создания, текущий этап),
собеседованиям (время, статус), вакансиям (даты публикации и закрытия) и
журналу HRActivity (переходы этапов, назначения, переносы, отмены, неявки).
Что именно считается событием периода, перечислено в `DEFINITIONS` и
возвращается вместе с отчётом. Показатель, который нельзя достоверно
посчитать, не выводится (None или пустой список).
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

from ..models import AccountRequest, Application, HRActivity, Interview, Vacancy

S = Application.Status
K = HRActivity.Kind
I = Interview.Status  # noqa: E741

# Воронка: «дошёл до этапа» — достиг его или любого следующего.
FUNNEL = [S.NEW, S.SCREENING, S.SHORTLISTED, S.INTERVIEW_SCHEDULED, S.INTERVIEW_DONE, S.OFFER, S.HIRED]
RANK = {S.NEW: 0, S.SCREENING: 1, S.SHORTLISTED: 2, S.INTERVIEW_SCHEDULED: 3, S.INTERVIEW_DONE: 4,
        S.AWAITING_DECISION: 4, S.NEXT_STAGE: 4, S.OFFER: 5, S.HIRED: 6}
WAITING = (S.INTERVIEW_DONE, S.AWAITING_DECISION, S.NEXT_STAGE)
DECISIONS = (S.OFFER, S.HIRED, S.REJECTED, S.WITHDRAWN)
EARLY = (S.NEW, S.SCREENING)
TERMINAL = (S.HIRED, S.REJECTED, S.WITHDRAWN)
# Эффективность источника показывается, когда из него пришло хотя бы столько откликов.
MIN_SOURCE_SAMPLE = 10
MAX_PERIOD_DAYS = 366

DEFINITIONS = {
    "new_applications": "Новые отклики — по дате создания отклика (с сайта или добавленные HR).",
    "passed_screening": "Прошли первичный отбор — переход из «Нового отклика» или «Первичного просмотра» "
                        "на любой следующий этап (кроме отказа) в этот период.",
    "interviews_scheduled": "Назначено собеседований — по дате, когда встречу назначили.",
    "interviews_conducted": "Проведено собеседований — встречи с зафиксированным результатом, по дате и "
                            "времени самой встречи.",
    "interviews_rescheduled": "Перенесено, отменено, неявка — по дате, когда это зафиксировали.",
    "decisions": "Решения — переходы в «Предложение о работе», «Принят», «Отказ компании» или «Кандидат "
                 "отказался» по дате перехода.",
    "offers": "Предложения о работе — переходы в этап «Предложение о работе» по дате перехода.",
    "hired": "Приняты — переходы в «Принят на работу» (учётная запись создана) по дате перехода.",
    "funnel": "Воронка — отклики, созданные в периоде: сколько из них дошли до этапа или дальше; "
              "конверсия — доля от предыдущего этапа.",
    "average_days_to_hire": "Среднее время до найма — от даты отклика до перехода в «Принят» для принятых в периоде.",
    "vacancy_days_to_close": "Среднее время закрытия вакансии — от публикации до закрытия для вакансий, "
                             "закрытых в периоде (только с обеими датами).",
    "source_efficiency": f"Эффективность источника — доля откликов периода, дошедших до собеседования и до найма; "
                         f"показывается при {MIN_SOURCE_SAMPLE} и более откликах из источника.",
}


def day_bounds(day: date) -> tuple[datetime, datetime]:
    start = timezone.make_aware(datetime.combine(day, time.min))
    return start, start + timedelta(days=1)


def period_bounds(first: date, last: date) -> tuple[datetime, datetime]:
    return day_bounds(first)[0], day_bounds(last)[1]


def month_bounds(year: int, month: int) -> tuple[date, date]:
    first = date(year, month, 1)
    last = (date(year + (month == 12), month % 12 + 1, 1)) - timedelta(days=1)
    return first, last


# ---------------------------------------------------------------------------
# Фильтры (должность, вакансия, источник, ответственный HR)
# ---------------------------------------------------------------------------

def application_filter(filters: dict, prefix: str = "") -> Q:
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


def _applications(filters: dict) -> QuerySet:
    return Application.objects.filter(application_filter(filters))


def _interviews(filters: dict) -> QuerySet:
    return Interview.objects.select_related("application__candidate", "interviewer", "vacancy").filter(
        application_filter(filters, "application__"))


def _events(filters: dict) -> QuerySet:
    return HRActivity.objects.filter(application__isnull=False).filter(application_filter(filters, "application__"))


def _local(value: datetime) -> str:
    return timezone.localtime(value).isoformat()


def interview_brief(interview: Interview) -> dict:
    app = interview.application
    return {
        "id": interview.pk,
        "scheduled_at": _local(interview.scheduled_at),
        "duration_minutes": interview.duration_minutes,
        "status": interview.status,
        "status_label": interview.get_status_display(),
        "format_label": interview.get_format_display(),
        "candidate": {"id": app.candidate_id, "full_name": app.candidate.full_name},
        "application": app.pk,
        "interviewer": interview.interviewer.get_full_name() or interview.interviewer.username,
        "position": interview.vacancy.title if interview.vacancy_id else app.position,
    }


def application_brief(application: Application) -> dict:
    return {
        "id": application.pk,
        "number": application.number,
        "candidate": {"id": application.candidate_id, "full_name": application.candidate.full_name},
        "status": application.status,
        "status_label": application.get_status_display(),
        "position": application.position_label,
        "source_label": application.get_source_display(),
        "channel": application.channel,
        "applied_on": application.applied_on.isoformat(),
        "created_at": _local(application.created_at),
        "needs_duplicate_review": application.needs_duplicate_review,
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
        "application": entry.application_id,
        "employee": ({"id": entry.employee_id, "full_name": entry.employee.get_full_name() or entry.employee.username}
                     if entry.employee_id else None),
        "from_status": entry.from_status,
        "to_status": entry.to_status,
    }


def visible_activity(qs: QuerySet) -> QuerySet:
    """Лента без служебной записи «вход в первый этап» — её дублирует «Получен
    отклик» / «Добавлен кандидат»; в журнале она остаётся для времени этапов."""
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
    period_start, period_end = period_bounds(date_from, date_to)
    staff = User.objects.filter(role__in=User.HR_MANAGEABLE_ROLES, is_superuser=False, is_staff=False)
    statuses = _status_counts(Application.objects.all())
    vacancies = dict(Vacancy.objects.order_by().values("status").annotate(n=Count("id")).values_list("status", "n"))
    upcoming = (Interview.objects.select_related("application__candidate", "interviewer", "vacancy")
                .filter(status=I.SCHEDULED, scheduled_at__gte=now - timedelta(hours=1))
                .order_by("scheduled_at")[:8])
    recent_apps = Application.objects.select_related("candidate", "vacancy").order_by("-created_at", "-id")[:8]
    recent = visible_activity(HRActivity.objects.select_related("actor", "candidate", "employee"))[:12]
    hired_events = HRActivity.objects.filter(kind=K.CANDIDATE_STATUS, to_status=S.HIRED)
    return {
        "period": {"date_from": date_from.isoformat(), "date_to": date_to.isoformat()},
        "employees_active": staff.filter(is_active=True).count(),
        "employees_new": staff.filter(created_at__gte=period_start, created_at__lt=period_end).count(),
        "vacancies_open": vacancies.get(Vacancy.Status.PUBLISHED, 0),
        "vacancies_paused": vacancies.get(Vacancy.Status.PAUSED, 0),
        "vacancies_draft": vacancies.get(Vacancy.Status.DRAFT, 0),
        "vacancies_closed": vacancies.get(Vacancy.Status.CLOSED, 0),
        "applications_total": sum(statuses.values()),
        "applications_in_progress": sum(n for s, n in statuses.items() if s not in TERMINAL),
        "applications_today": Application.objects.filter(created_at__gte=today_start, created_at__lt=today_end).count(),
        "applications_new": statuses[S.NEW],
        "screening": statuses[S.SCREENING],
        "shortlisted": statuses[S.SHORTLISTED],
        "applications_by_status": statuses,
        "interviews_today": Interview.objects.filter(status__in=(I.SCHEDULED, I.COMPLETED, I.NO_SHOW),
                                                     scheduled_at__gte=today_start, scheduled_at__lt=today_end).count(),
        "interviews_upcoming": Interview.objects.filter(status=I.SCHEDULED, scheduled_at__gte=now).count(),
        "awaiting_decision": sum(statuses[s] for s in WAITING),
        "offers": statuses[S.OFFER],
        "hired": statuses[S.HIRED],
        "hired_in_period": hired_events.filter(created_at__gte=period_start, created_at__lt=period_end).count(),
        "rejected": statuses[S.REJECTED],
        "withdrawn": statuses[S.WITHDRAWN],
        "duplicates_to_review": Application.objects.filter(needs_duplicate_review=True).count(),
        "account_requests_pending": AccountRequest.objects.filter(status=AccountRequest.Status.PENDING).count(),
        "recent_applications": [application_brief(a) for a in recent_apps],
        "upcoming_interviews": [interview_brief(i) for i in upcoming],
        "recent_activity": [activity_brief(a) for a in recent],
    }


# ---------------------------------------------------------------------------
# Ежедневный отчёт
# ---------------------------------------------------------------------------

def _passed_screening(events: QuerySet) -> int:
    return (events.filter(kind=K.CANDIDATE_STATUS, from_status__in=EARLY)
            .exclude(to_status__in=(*EARLY, S.REJECTED, S.WITHDRAWN))
            .values("application").distinct().count())


def _distinct(events: QuerySet, kind: str) -> int:
    return events.filter(kind=kind).values("interview").distinct().count()


def daily(day: date, filters: dict) -> dict:
    start, end = day_bounds(day)
    new = list(_applications(filters).select_related("candidate", "vacancy")
               .filter(created_at__gte=start, created_at__lt=end).order_by("created_at", "id"))
    planned = list(_interviews(filters).filter(scheduled_at__gte=start, scheduled_at__lt=end)
                   .exclude(status__in=(I.CANCELLED, I.RESCHEDULED)).order_by("scheduled_at"))
    events = _events(filters).filter(created_at__gte=start, created_at__lt=end)
    transitions = Counter(events.filter(kind=K.CANDIDATE_STATUS, to_status__in=DECISIONS)
                          .values_list("to_status", flat=True))
    by_vacancy = Counter(a.position_label or "Без вакансии" for a in new)
    return {
        "date": day.isoformat(),
        "new_applications": len(new),
        "new_by_vacancy": [{"label": label, "count": n} for label, n in by_vacancy.most_common()],
        "new_applications_list": [application_brief(a) for a in new],
        "passed_screening": _passed_screening(events),
        "interviews_scheduled": _distinct(events, K.INTERVIEW_SCHEDULED),
        "interviews_planned": len(planned),
        "interviews_list": [interview_brief(i) for i in planned],
        "interviews_conducted": sum(1 for i in planned if i.status == I.COMPLETED),
        "interviews_rescheduled": _distinct(events, K.INTERVIEW_RESCHEDULED),
        "interviews_cancelled": _distinct(events, K.INTERVIEW_CANCELLED),
        "interviews_no_show": _distinct(events, K.INTERVIEW_NO_SHOW),
        "awaiting_decision_now": _applications(filters).filter(status__in=WAITING).count(),
        "decisions": sum(transitions.values()),
        "offers": transitions[S.OFFER],
        "hired": transitions[S.HIRED],
        "rejected": transitions[S.REJECTED],
        "withdrawn": transitions[S.WITHDRAWN],
        "definitions": DEFINITIONS,
    }


# ---------------------------------------------------------------------------
# Отчёт за период (по умолчанию — месяц)
# ---------------------------------------------------------------------------

def _reached(ids: list[int]) -> dict[int, int]:
    """Наибольший ранг воронки, которого достиг каждый отклик (по журналу)."""
    best = {pk: 0 for pk in ids}
    rows = HRActivity.objects.filter(application_id__in=ids, kind=K.CANDIDATE_STATUS).values_list(
        "application_id", "to_status")
    for pk, status in rows:
        rank = RANK.get(status)
        if rank is not None and rank > best[pk]:
            best[pk] = rank
    return best


def _stage_durations(filters: dict, start: datetime, end: datetime) -> list[dict]:
    """Среднее время на этапе по переходам, завершившимся в периоде. Учитываются
    только этапы, время входа в которые есть в журнале."""
    leaving = list(_events(filters).filter(kind=K.CANDIDATE_STATUS, created_at__gte=start, created_at__lt=end)
                   .exclude(from_status="").values_list("application_id", "from_status", "created_at"))
    if not leaving:
        return []
    history = defaultdict(list)
    for pk, to_status, at in (HRActivity.objects.filter(application_id__in={a for a, _, _ in leaving},
                                                        kind=K.CANDIDATE_STATUS)
                              .order_by("created_at", "id").values_list("application_id", "to_status", "created_at")):
        history[pk].append((to_status, at))
    totals: dict[str, list[float]] = defaultdict(list)
    for pk, stage, left_at in leaving:
        entered = [at for status, at in history[pk] if status == stage and at <= left_at]
        if entered:
            totals[stage].append((left_at - entered[-1]).total_seconds() / 3600)
    labels = dict(S.choices)
    return [
        {"status": stage, "status_label": labels.get(stage, stage), "transitions": len(hours),
         "average_hours": round(sum(hours) / len(hours), 1)}
        for stage, hours in sorted(totals.items(), key=lambda item: RANK.get(item[0], 9))
    ]


def _vacancy_close_times(filters: dict, start: datetime, end: datetime) -> dict:
    qs = Vacancy.objects.filter(closed_at__gte=start, closed_at__lt=end, published_at__isnull=False)
    if filters.get("vacancy"):
        qs = qs.filter(pk=filters["vacancy"])
    if filters.get("responsible"):
        qs = qs.filter(responsible_id=filters["responsible"])
    if filters.get("position"):
        qs = qs.filter(Q(title__icontains=filters["position"]) | Q(department__icontains=filters["position"]))
    days = [(v.closed_at - v.published_at).total_seconds() / 86400 for v in qs if v.closed_at >= v.published_at]
    return {"count": len(days), "average_days": round(sum(days) / len(days), 1) if days else None}


def period_report(first: date, last: date, filters: dict, label: str) -> dict:
    start, end = period_bounds(first, last)
    cohort = list(_applications(filters).select_related("vacancy").filter(created_at__gte=start, created_at__lt=end))
    events = _events(filters).filter(created_at__gte=start, created_at__lt=end)
    transitions = Counter(events.filter(kind=K.CANDIDATE_STATUS).values_list("to_status", flat=True))
    conducted = _interviews(filters).filter(status=I.COMPLETED, scheduled_at__gte=start, scheduled_at__lt=end)

    reached = _reached([a.pk for a in cohort])
    funnel = []
    for index, stage in enumerate(FUNNEL):
        count = sum(1 for rank in reached.values() if rank >= index)
        previous = funnel[-1]["count"] if funnel else None
        funnel.append({
            "status": stage, "status_label": S(stage).label, "count": count,
            "conversion_percent": round(count * 100 / previous, 1) if previous else None,
        })

    hire_days = [(timezone.localtime(entry.created_at).date() - entry.application.applied_on).days
                 for entry in events.filter(kind=K.CANDIDATE_STATUS, to_status=S.HIRED).select_related("application")]

    # По вакансиям: отклики периода, проведённые встречи, предложения, найм и отказы периода.
    vacancy_rows: dict[str, Counter] = defaultdict(Counter)
    for a in cohort:
        vacancy_rows[a.position_label or "Без вакансии"]["applications"] += 1
    for i in conducted:
        vacancy_rows[i.vacancy.title if i.vacancy_id else (i.application.position or "Без вакансии")]["interviews"] += 1
    for entry in events.filter(kind=K.CANDIDATE_STATUS, to_status__in=(S.OFFER, S.HIRED, S.REJECTED)) \
            .select_related("application__vacancy"):
        vacancy_rows[entry.application.position_label or "Без вакансии"][entry.to_status] += 1
    by_vacancy = sorted(
        ({"label": label, "applications": c["applications"], "interviews": c["interviews"], "offers": c[S.OFFER],
          "hired": c[S.HIRED], "rejected": c[S.REJECTED]} for label, c in vacancy_rows.items()),
        key=lambda row: (-row["applications"], row["label"]),
    )

    sources: dict[str, Counter] = defaultdict(Counter)
    labels = dict(Application.Source.choices)
    for a in cohort:
        row = sources[a.source]
        row["applications"] += 1
        if reached.get(a.pk, 0) >= RANK[S.INTERVIEW_SCHEDULED]:
            row["interview"] += 1
        if a.status == S.HIRED:
            row["hired"] += 1
    by_source = []
    for source, c in sorted(sources.items(), key=lambda item: -item[1]["applications"]):
        enough = c["applications"] >= MIN_SOURCE_SAMPLE
        by_source.append({
            "source": source, "label": labels.get(source, source), "count": c["applications"],
            "enough_data": enough,
            "interview_percent": round(c["interview"] * 100 / c["applications"], 1) if enough else None,
            "hired_percent": round(c["hired"] * 100 / c["applications"], 1) if enough else None,
        })

    by_stage = Counter(a.status for a in cohort)
    close_times = _vacancy_close_times(filters, start, end)
    return {
        "month": label,
        "date_from": first.isoformat(),
        "date_to": last.isoformat(),
        "new_applications": len(cohort),
        "interviews_conducted": conducted.count(),
        "interviews_scheduled": _distinct(events, K.INTERVIEW_SCHEDULED),
        "interviews_cancelled": _distinct(events, K.INTERVIEW_CANCELLED),
        "interviews_rescheduled": _distinct(events, K.INTERVIEW_RESCHEDULED),
        "interviews_no_show": _distinct(events, K.INTERVIEW_NO_SHOW),
        "passed_screening": _passed_screening(events),
        "hired": transitions[S.HIRED],
        "rejected": transitions[S.REJECTED],
        "withdrawn": transitions[S.WITHDRAWN],
        "offers": transitions[S.OFFER],
        "by_stage": [{"status": value, "status_label": text, "count": by_stage.get(value, 0)}
                     for value, text in S.choices],
        "funnel": funnel,
        "by_vacancy": by_vacancy,
        "by_source": by_source,
        "stage_durations": _stage_durations(filters, start, end),
        "average_days_to_hire": round(sum(hire_days) / len(hire_days), 1) if hire_days else None,
        "vacancies_closed": close_times["count"],
        "vacancy_days_to_close": close_times["average_days"],
        "definitions": DEFINITIONS,
    }


def monthly(year: int, month: int, filters: dict) -> dict:
    first, last = month_bounds(year, month)
    return period_report(first, last, filters, f"{year:04d}-{month:02d}")


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


def _definitions(report: dict) -> list[list]:
    return [[], ["Как считаются показатели"], *[[text] for text in report["definitions"].values()]]


def daily_csv(report: dict) -> str:
    rows = [["Ежедневный HR-отчёт", report["date"]], [], ["Показатель", "Значение"]]
    for key, label in (
        ("new_applications", "Новые отклики"), ("passed_screening", "Прошли первичный отбор"),
        ("interviews_scheduled", "Назначено собеседований"), ("interviews_conducted", "Проведено собеседований"),
        ("interviews_rescheduled", "Перенесено встреч"), ("interviews_cancelled", "Отменено встреч"),
        ("interviews_no_show", "Кандидат не пришёл"), ("awaiting_decision_now", "Ожидают решения (сейчас)"),
        ("decisions", "Принятые решения"), ("offers", "Предложения о работе"), ("hired", "Приняты на работу"),
        ("rejected", "Отказ компании"), ("withdrawn", "Кандидат отказался"),
    ):
        rows.append([label, report[key]])
    rows += [[], ["Отклики по вакансиям"], ["Вакансия", "Откликов"]]
    rows += [[item["label"], item["count"]] for item in report["new_by_vacancy"]]
    rows += [[], ["Собеседования дня"], ["Время", "Кандидат", "Должность", "Интервьюер", "Статус"]]
    for item in report["interviews_list"]:
        rows.append([item["scheduled_at"][11:16], item["candidate"]["full_name"], item["position"],
                     item["interviewer"], item["status_label"]])
    rows += [[], ["Новые отклики"], ["Номер", "Кандидат", "Вакансия", "Источник", "Этап"]]
    for item in report["new_applications_list"]:
        rows.append([item["number"], item["candidate"]["full_name"], item["position"], item["source_label"],
                     item["status_label"]])
    return _csv(rows + _definitions(report))


def monthly_csv(report: dict) -> str:
    rows = [["HR-отчёт за период", report["date_from"], report["date_to"]], [], ["Показатель", "Значение"]]
    for key, label in (
        ("new_applications", "Новые отклики"), ("passed_screening", "Прошли первичный отбор"),
        ("interviews_scheduled", "Назначено собеседований"), ("interviews_conducted", "Проведено собеседований"),
        ("interviews_cancelled", "Отменено встреч"), ("interviews_rescheduled", "Переносы встреч"),
        ("interviews_no_show", "Кандидат не пришёл"), ("offers", "Предложения о работе"),
        ("hired", "Приняты на работу"), ("rejected", "Отказ компании"), ("withdrawn", "Кандидат отказался"),
        ("average_days_to_hire", "Среднее время до найма, дней"), ("vacancies_closed", "Закрыто вакансий"),
        ("vacancy_days_to_close", "Среднее время закрытия вакансии, дней"),
    ):
        rows.append([label, "" if report[key] is None else report[key]])
    rows += [[], ["Отклики периода по этапам"], ["Этап", "Откликов"]]
    rows += [[item["status_label"], item["count"]] for item in report["by_stage"]]
    rows += [[], ["Воронка"], ["Этап", "Дошли", "Конверсия от предыдущего, %"]]
    rows += [[item["status_label"], item["count"], "" if item["conversion_percent"] is None
              else item["conversion_percent"]] for item in report["funnel"]]
    rows += [[], ["По вакансиям"], ["Вакансия", "Откликов", "Собеседований", "Предложений", "Принято", "Отказов"]]
    rows += [[r["label"], r["applications"], r["interviews"], r["offers"], r["hired"], r["rejected"]]
             for r in report["by_vacancy"]]
    rows += [[], ["По источникам"], ["Источник", "Откликов", "Дошли до собеседования, %", "Приняты, %"]]
    rows += [[r["label"], r["count"], "" if r["interview_percent"] is None else r["interview_percent"],
              "" if r["hired_percent"] is None else r["hired_percent"]] for r in report["by_source"]]
    if report["stage_durations"]:
        rows += [[], ["Среднее время на этапе"], ["Этап", "Переходов", "Среднее, ч"]]
        rows += [[item["status_label"], item["transitions"], item["average_hours"]] for item in report["stage_durations"]]
    return _csv(rows + _definitions(report))
