"""Сводка кабинета маркетинга и отчёты за неделю или месяц.

Все показатели считаются из контент-плана и задач в базе — без
демонстрационных и расчётных «прогнозов». Заявок и рекламных кампаний в
системе нет, поэтому и показателей по ним нет.

Публикации относятся к периоду по дате выхода (`publish_date`): так
«выполнение контент-плана» — доля опубликованных среди тех, чья дата уже
прошла (сегодняшние — только уже вышедшие). Задачи — по моменту выполнения (`completed_at`) и сроку.
"""
from __future__ import annotations

import calendar
from datetime import date, timedelta

from django.db.models import Count, F, Q
from django.utils import timezone

from .models import Channel, ContentItem, MarketingTask
from .serializers import person, team_queryset

UPCOMING_LIMIT = 6


def week_bounds(anchor: date) -> tuple[date, date]:
    start = anchor - timedelta(days=anchor.weekday())
    return start, start + timedelta(days=6)


def month_bounds(anchor: date) -> tuple[date, date]:
    last = calendar.monthrange(anchor.year, anchor.month)[1]
    return anchor.replace(day=1), anchor.replace(day=last)


def _open_tasks():
    return MarketingTask.objects.filter(status__in=MarketingTask.OPEN_STATUSES)


def _planned(date_from: date, date_to: date):
    """Публикации плана на период: с датой выхода в периоде, кроме идей."""
    return ContentItem.objects.filter(publish_date__range=(date_from, date_to)).exclude(status=ContentItem.Status.IDEA)


def dashboard(user, today: date, date_from: date, date_to: date) -> dict:
    """Главная: открытые задачи, состояние плана и ближайшие дела. Ближайшие
    задачи и публикации — queryset'ы, их сериализует представление."""
    open_tasks = _open_tasks()
    content = ContentItem.objects.all()
    planned = _planned(date_from, date_to)
    upcoming_tasks = open_tasks.select_related("responsible", "created_by").order_by(
        F("due_date").asc(nulls_last=True), "-created_at")[:UPCOMING_LIMIT]
    upcoming_content = content.exclude(status=ContentItem.Status.PUBLISHED).filter(
        publish_date__gte=today).select_related("responsible", "created_by")[:UPCOMING_LIMIT]
    return {
        "today": today.isoformat(),
        "period": {"date_from": date_from.isoformat(), "date_to": date_to.isoformat()},
        "tasks": {
            "open": open_tasks.count(),
            "in_progress": open_tasks.filter(status=MarketingTask.Status.IN_PROGRESS).count(),
            "overdue": open_tasks.filter(due_date__lt=today).count(),
            "due_today": open_tasks.filter(due_date=today).count(),
            "mine_open": open_tasks.filter(responsible=user).count(),
            "done_in_period": MarketingTask.objects.filter(
                status=MarketingTask.Status.DONE, completed_at__date__range=(date_from, date_to)).count(),
        },
        "content": {
            "ideas": content.filter(status=ContentItem.Status.IDEA).count(),
            "in_work": content.filter(status__in=(ContentItem.Status.PREPARING, ContentItem.Status.REVIEW)).count(),
            "scheduled": content.filter(status=ContentItem.Status.SCHEDULED).count(),
            "planned_in_period": planned.count(),
            "published_in_period": planned.filter(status=ContentItem.Status.PUBLISHED).count(),
        },
        "upcoming_tasks": upcoming_tasks,
        "upcoming_content": upcoming_content,
    }


def _buckets(date_from: date, date_to: date) -> list[tuple[date, date]]:
    """До двух недель — по дням, дольше — отрезками по 7 дней."""
    step = 1 if (date_to - date_from).days < 14 else 7
    buckets, start = [], date_from
    while start <= date_to:
        end = min(start + timedelta(days=step - 1), date_to)
        buckets.append((start, end))
        start = end + timedelta(days=1)
    return buckets


def _percent(part: int, whole: int) -> int | None:
    return round(100 * part / whole) if whole else None


def report(kind: str, date_from: date, date_to: date, today: date) -> dict:
    planned = _planned(date_from, date_to)
    published = planned.filter(status=ContentItem.Status.PUBLISHED)
    # Срок наступил: дата прошла, а сегодняшняя — только если уже вышла
    # (вечерний пост не считается невыполненным с утра).
    due = planned.filter(Q(publish_date__lt=today) | Q(publish_date=today, status=ContentItem.Status.PUBLISHED))
    due_count = due.count()
    due_done = due.filter(status=ContentItem.Status.PUBLISHED).count()

    completed = MarketingTask.objects.filter(status=MarketingTask.Status.DONE,
                                             completed_at__date__range=(date_from, date_to))
    on_time = sum(1 for task in completed.only("due_date", "completed_at")
                  if task.due_date is None or timezone.localtime(task.completed_at).date() <= task.due_date)
    completed_count = completed.count()

    series = []
    for start, end in _buckets(date_from, date_to):
        series.append({
            "date_from": start.isoformat(),
            "date_to": end.isoformat(),
            "published": published.filter(publish_date__range=(start, end)).count(),
            "planned": planned.filter(publish_date__range=(start, end)).count(),
            "tasks_completed": completed.filter(completed_at__date__range=(start, end)).count(),
        })

    channel_rows = {row["channel"]: row for row in planned.values("channel").annotate(
        planned=Count("id"), published=Count("id", filter=Q(status=ContentItem.Status.PUBLISHED)))}
    labels = dict(Channel.choices)
    by_channel = [{"channel": value, "label": labels[value], "planned": row["planned"], "published": row["published"]}
                  for value, row in sorted(channel_rows.items(), key=lambda item: -item[1]["planned"])]

    by_person = []
    for member in team_queryset():
        row = {
            **person(member),
            "tasks_completed": completed.filter(responsible=member).count(),
            "tasks_open": _open_tasks().filter(responsible=member).count(),
            "content_planned": planned.filter(responsible=member).count(),
            "content_published": published.filter(responsible=member).count(),
        }
        if any(row[key] for key in ("tasks_completed", "tasks_open", "content_planned", "content_published")):
            by_person.append(row)

    return {
        "period": {"kind": kind, "date_from": date_from.isoformat(), "date_to": date_to.isoformat()},
        "today": today.isoformat(),
        "tasks": {
            "created": MarketingTask.objects.filter(created_at__date__range=(date_from, date_to)).count(),
            "completed": completed_count,
            "completed_on_time": on_time,
            "completed_late": completed_count - on_time,
            "overdue_now": _open_tasks().filter(due_date__lt=today).count(),
            "open_due_in_period": _open_tasks().filter(due_date__range=(date_from, date_to)).count(),
        },
        "content": {
            "planned": planned.count(),
            "prepared": planned.filter(status__in=ContentItem.READY_STATUSES).count(),
            "published": published.count(),
            "plan_due": due_count,
            "plan_done": due_done,
            "plan_completion": _percent(due_done, due_count),
        },
        "series": series,
        "by_channel": by_channel,
        "by_person": by_person,
    }

