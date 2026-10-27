"""Напоминания HR-панели. Ничего не отправляется наружу (почта и мессенджеры
не настроены) — список строится из данных при каждом запросе:

* собеседования в ближайшие 24 часа;
* прошедшие собеседования без результата или отметки о неявке;
* новые отклики, которые ждут просмотра дольше двух дней;
* наступившая дата следующего этапа после собеседования;
* вакансии, у которых через три дня (или раньше) заканчивается приём откликов;
* отклики, которые нужно проверить на дубль, и запросы учётных записей.

`mine=True` — только то, где пользователь интервьюер или ответственный.
"""
from __future__ import annotations

from datetime import timedelta

from django.db.models import Q
from django.utils import timezone

from ..models import AccountRequest, Application, Interview, Vacancy

S = Application.Status
NEW_WAIT = timedelta(days=2)
SOON = timedelta(hours=24)
CLOSING_DAYS = 3
LIMIT = 30


def _name(interview: Interview) -> str:
    return interview.application.candidate.full_name


def _when(value) -> str:
    return timezone.localtime(value).isoformat()


def reminders(user, mine: bool = False) -> list[dict]:
    now = timezone.now()
    today = timezone.localdate()
    items: list[dict] = []
    interviews = Interview.objects.select_related("application__candidate").filter(status=Interview.Status.SCHEDULED)
    applications = Application.objects.select_related("candidate", "vacancy")
    if mine:
        interviews = interviews.filter(Q(interviewer=user) | Q(application__responsible=user))
        applications = applications.filter(responsible=user)

    for i in interviews.filter(scheduled_at__gte=now, scheduled_at__lt=now + SOON).order_by("scheduled_at"):
        items.append({"kind": "interview_soon", "level": "info", "at": _when(i.scheduled_at),
                      "title": f"Собеседование: {_name(i)}", "candidate": i.application.candidate_id,
                      "application": i.application_id, "interview": i.pk})
    for i in interviews.filter(scheduled_at__lt=now).order_by("scheduled_at"):
        items.append({"kind": "interview_result", "level": "warning", "at": _when(i.scheduled_at),
                      "title": f"Зафиксируйте итог собеседования: {_name(i)}", "candidate": i.application.candidate_id,
                      "application": i.application_id, "interview": i.pk})
    done = Interview.objects.select_related("application__candidate").filter(
        status=Interview.Status.COMPLETED, next_step_date__lte=today,
        application__status__in=(S.INTERVIEW_DONE, S.AWAITING_DECISION, S.NEXT_STAGE))
    if mine:
        done = done.filter(Q(interviewer=user) | Q(application__responsible=user))
    for i in done.order_by("next_step_date"):
        # Только последняя встреча отклика: после неё могла быть назначена новая.
        if i.application.interviews.filter(scheduled_at__gt=i.scheduled_at).exists():
            continue
        items.append({"kind": "next_step_due", "level": "warning", "at": i.next_step_date.isoformat(),
                      "title": f"Следующий шаг ({i.get_next_step_display().lower()}): {_name(i)}",
                      "candidate": i.application.candidate_id, "application": i.application_id, "interview": i.pk})
    for a in applications.filter(status=S.NEW, created_at__lt=now - NEW_WAIT).order_by("created_at")[:LIMIT]:
        items.append({"kind": "new_waiting", "level": "info", "at": _when(a.created_at),
                      "title": f"Отклик ждёт просмотра: {a.candidate.full_name} — {a.position_label or '—'}",
                      "candidate": a.candidate_id, "application": a.pk})
    for a in applications.filter(needs_duplicate_review=True).order_by("created_at")[:LIMIT]:
        items.append({"kind": "duplicate", "level": "warning", "at": _when(a.created_at),
                      "title": f"Проверьте возможный дубль: {a.candidate.full_name}",
                      "candidate": a.candidate_id, "application": a.pk})
    vacancies = Vacancy.objects.filter(status=Vacancy.Status.PUBLISHED, closes_on__gte=today,
                                       closes_on__lte=today + timedelta(days=CLOSING_DAYS))
    if mine:
        vacancies = vacancies.filter(responsible=user)
    for v in vacancies.order_by("closes_on"):
        items.append({"kind": "vacancy_closing", "level": "info", "at": v.closes_on.isoformat(),
                      "title": f"Приём откликов на «{v.title}» заканчивается", "vacancy": v.pk})
    expired = Vacancy.objects.filter(status=Vacancy.Status.PUBLISHED, closes_on__lt=today)
    if mine:
        expired = expired.filter(responsible=user)
    for v in expired.order_by("closes_on"):
        items.append({"kind": "vacancy_expired", "level": "warning", "at": v.closes_on.isoformat(),
                      "title": f"Срок приёма откликов на «{v.title}» истёк — закройте или продлите вакансию",
                      "vacancy": v.pk})
    requests = AccountRequest.objects.select_related("application__candidate").filter(
        status=AccountRequest.Status.PENDING)
    if mine:
        requests = requests.filter(requested_by=user)
    for r in requests:
        items.append({"kind": "account_request", "level": "info", "at": _when(r.created_at),
                      "title": f"Учётная запись «{r.username}» ждёт администратора",
                      "candidate": r.application.candidate_id, "application": r.application_id})
    return items[: LIMIT * 3]
