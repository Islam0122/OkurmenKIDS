"""The "Расписание" admin screen — a weekly calendar built on top of Lesson.

Deliberately not a Model/ModelAdmin: the spec is explicit that schedule data
already lives on Group + Lesson, so this is a plain admin-wrapped view that
queries Lesson and renders it as a week grid, with a couple of small
mutating endpoints (generate lessons) alongside it.
"""
from __future__ import annotations

import datetime as dt
from collections import defaultdict
from typing import Iterable

from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.users.models import Subject, Teacher, User

from .models import Course, Group, Lesson, Room
from .services.lesson_generator import LessonGenerationError, generate_lessons_for_group

WEEKDAY_NAMES = [
    "Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье",
]


def _is_admin_user(user) -> bool:
    return bool(
        user
        and user.is_authenticated
        and (user.is_superuser or getattr(user, "role", None) == User.Role.ADMIN)
    )


def _parse_date(value: str | None, default: dt.date) -> dt.date:
    if not value:
        return default
    try:
        return dt.date.fromisoformat(value)
    except ValueError:
        return default


def _week_start(day: dt.date) -> dt.date:
    return day - dt.timedelta(days=day.weekday())


def _time_ranges_overlap(a: Lesson, b: Lesson) -> bool:
    return a.start_time < b.end_time and b.start_time < a.end_time


def _detect_conflicts(lessons: Iterable[Lesson]) -> tuple[list[dict], list[dict], set[int]]:
    """Pairwise-overlap check within the lessons currently on screen.

    Cancelled lessons never conflict with anything — a room/teacher freed up
    by a cancellation isn't a clash. Returns (teacher_conflicts,
    room_conflicts, conflicting_lesson_ids) so the template can both list
    the conflicts and flag the individual cards.
    """
    active = [lesson for lesson in lessons if lesson.status != Lesson.Status.CANCELLED]

    by_teacher: dict[tuple[int, dt.date], list[Lesson]] = defaultdict(list)
    by_room: dict[tuple[int, dt.date], list[Lesson]] = defaultdict(list)
    for lesson in active:
        by_teacher[(lesson.group.teacher_id, lesson.date)].append(lesson)
        if lesson.room_id:
            by_room[(lesson.room_id, lesson.date)].append(lesson)

    conflicting_ids: set[int] = set()

    def _pairwise_conflicts(buckets, label_fn):
        found = []
        for key, bucket in buckets.items():
            if len(bucket) < 2:
                continue
            bucket = sorted(bucket, key=lambda l: l.start_time)
            for i in range(len(bucket)):
                for j in range(i + 1, len(bucket)):
                    if _time_ranges_overlap(bucket[i], bucket[j]):
                        conflicting_ids.add(bucket[i].id)
                        conflicting_ids.add(bucket[j].id)
                        found.append(
                            {
                                "label": label_fn(bucket[i]),
                                "date": key[1],
                                "lessons": [bucket[i], bucket[j]],
                            }
                        )
        return found

    teacher_conflicts = _pairwise_conflicts(by_teacher, lambda l: str(l.group.teacher))
    room_conflicts = _pairwise_conflicts(by_room, lambda l: str(l.room))

    return teacher_conflicts, room_conflicts, conflicting_ids


def schedule_view(request):
    if not _is_admin_user(request.user):
        raise PermissionDenied("Раздел «Расписание» доступен только администратору.")

    today = timezone.localdate()

    week_anchor = _parse_date(request.GET.get("week"), today)
    week_start = _week_start(week_anchor)
    week_end = week_start + dt.timedelta(days=6)

    date_from_param = request.GET.get("date_from")
    date_to_param = request.GET.get("date_to")
    if date_from_param or date_to_param:
        date_from = _parse_date(date_from_param, week_start)
        date_to = _parse_date(date_to_param, week_end)
    else:
        date_from, date_to = week_start, week_end
    if date_to < date_from:
        date_from, date_to = date_to, date_from

    teacher_id = request.GET.get("teacher") or ""
    group_id = request.GET.get("group") or ""
    course_id = request.GET.get("course") or ""
    subject_id = request.GET.get("subject") or ""
    room_id = request.GET.get("room") or ""
    status = request.GET.get("status") or ""

    lessons_qs = (
        Lesson.objects.filter(date__gte=date_from, date__lte=date_to)
        .select_related("group", "group__teacher", "group__teacher__user", "group__course", "room", "subject", "plan")
        .order_by("date", "start_time")
    )
    if teacher_id:
        lessons_qs = lessons_qs.filter(group__teacher_id=teacher_id)
    if group_id:
        lessons_qs = lessons_qs.filter(group_id=group_id)
    if course_id:
        lessons_qs = lessons_qs.filter(group__course_id=course_id)
    if subject_id:
        lessons_qs = lessons_qs.filter(subject_id=subject_id)
    if room_id:
        lessons_qs = lessons_qs.filter(room_id=room_id)
    if status:
        lessons_qs = lessons_qs.filter(status=status)

    lessons = list(lessons_qs)
    teacher_conflicts, room_conflicts, conflicting_ids = _detect_conflicts(lessons)

    days = []
    cursor = date_from
    while cursor <= date_to:
        day_lessons = [lesson for lesson in lessons if lesson.date == cursor]
        days.append(
            {
                "date": cursor,
                "weekday_label": WEEKDAY_NAMES[cursor.weekday()],
                "is_today": cursor == today,
                "lessons": day_lessons,
            }
        )
        cursor += dt.timedelta(days=1)

    # Query params preserved across week navigation (filters survive the jump).
    filter_params = {
        "teacher": teacher_id, "group": group_id, "course": course_id,
        "subject": subject_id, "room": room_id, "status": status,
    }
    filter_qs = "&".join(f"{key}={value}" for key, value in filter_params.items() if value)

    def _nav_url(week_date: dt.date) -> str:
        qs = f"week={week_date.isoformat()}"
        if filter_qs:
            qs = f"{qs}&{filter_qs}"
        return f"{reverse('admin:academy_schedule')}?{qs}"

    context = {
        **admin.site.each_context(request),
        "title": "Расписание",
        "days": days,
        "week_start": week_start,
        "week_end": week_end,
        "date_from": date_from,
        "date_to": date_to,
        "today": today,
        "is_custom_range": bool(date_from_param or date_to_param),
        "teachers": Teacher.objects.filter(is_active=True).select_related("user").order_by("user__first_name"),
        "groups": Group.objects.select_related("teacher__user").order_by("name"),
        "courses": Course.objects.order_by("name"),
        "subjects": Subject.objects.filter(is_active=True).order_by("name"),
        "rooms": Room.objects.filter(is_active=True).order_by("name"),
        "status_choices": Lesson.Status.choices,
        "selected": {
            "teacher": teacher_id, "group": group_id, "course": course_id,
            "subject": subject_id, "room": room_id, "status": status,
            "date_from": date_from_param or "", "date_to": date_to_param or "",
        },
        "teacher_conflicts": teacher_conflicts,
        "room_conflicts": room_conflicts,
        "conflicting_ids": conflicting_ids,
        "prev_week_url": _nav_url(week_start - dt.timedelta(days=7)),
        "next_week_url": _nav_url(week_start + dt.timedelta(days=7)),
        "today_url": _nav_url(today),
        "selected_group": Group.objects.filter(pk=group_id).first() if group_id else None,
    }
    return render(request, "admin/academy/schedule.html", context)


@require_POST
def generate_lessons_for_group_view(request, group_id: int):
    if not _is_admin_user(request.user):
        raise PermissionDenied("Действие доступно только администратору.")

    group = get_object_or_404(Group, pk=group_id)
    try:
        created = generate_lessons_for_group(group)
    except LessonGenerationError as exc:
        messages.error(request, f"«{group.name}»: {exc}")
    else:
        if created:
            messages.success(request, f"«{group.name}»: создано занятий — {len(created)}.")
        else:
            messages.warning(request, f"«{group.name}»: новых занятий не создано (уже сгенерированы).")

    return redirect(f"{reverse('admin:academy_schedule')}?group={group_id}")
