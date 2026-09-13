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

from django import forms
from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Avg, Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.users.models import Subject, Teacher, User

from .constants import WEEKDAY_CODES, WEEKDAY_LABELS_FULL, WEEKDAY_LABELS_SHORT
from .models import (
    Attendance,
    Course,
    Group,
    GroupSchedule,
    GroupTeacher,
    Homework,
    HomeworkResult,
    Lesson,
    Room,
    Student,
)
from .services.analytics import get_dashboard
from .services.lesson_generator import (
    LessonGenerationError,
    generate_lessons_for_group,
    generate_lessons_for_group_with_report,
)

WEEKDAY_NAMES = [WEEKDAY_LABELS_FULL[code] for code in WEEKDAY_CODES]
WEEKDAY_SHORT_LABELS = {code: WEEKDAY_LABELS_SHORT[code] for code in WEEKDAY_CODES}


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

    by_teacher: dict[tuple[int | None, dt.date], list[Lesson]] = defaultdict(list)
    by_room: dict[tuple[int, dt.date], list[Lesson]] = defaultdict(list)
    for lesson in active:
        # Keyed on the lesson's *actual* teacher (Lesson.effective_teacher —
        # its own `teacher` when the generator set one, i.e. a specific
        # GroupTeacher slot, else that GroupTeacher's own teacher; never the
        # legacy `Group.teacher` field): a group with several teachers (see
        # models.GroupTeacher) must not treat two different teachers'
        # simultaneous lessons in the same group as a conflict with
        # themselves, nor miss a real conflict between one teacher's lesson
        # here and their own lesson in another group.
        effective_teacher = lesson.effective_teacher
        by_teacher[(effective_teacher.id if effective_teacher else None, lesson.date)].append(lesson)
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

    teacher_conflicts = _pairwise_conflicts(by_teacher, lambda l: str(l.effective_teacher))
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
        .select_related(
            "group", "group_teacher__teacher", "group_teacher__teacher__user", "group__course",
            "teacher", "teacher__user", "room", "subject", "plan",
        )
        .order_by("date", "start_time")
    )
    if teacher_id:
        # A lesson's actual teacher is Lesson.teacher when the generator set
        # one (a specific GroupTeacher slot), else that GroupTeacher's own
        # teacher — see Lesson.effective_teacher. A group with several
        # teachers (models.GroupTeacher) must only match lessons this
        # specific teacher actually gives, not every lesson of the group.
        lessons_qs = lessons_qs.filter(
            Q(teacher_id=teacher_id) | Q(teacher__isnull=True, group_teacher__teacher_id=teacher_id)
        )
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
        "groups": Group.objects.order_by("name"),
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


# ---------------------------------------------------------------------------
# "Аналитика" — a custom admin page (no model of its own), rendering
# AnalyticsService.get_dashboard() for a date range + optional Teacher/Group
# filter. Nothing is stored: every number is recomputed on this request.
# ---------------------------------------------------------------------------

def _quick_periods(today: dt.date) -> list[dict]:
    """Preset date ranges for the Analytics Dashboard's quick filter buttons."""
    week_start = _week_start(today)
    month_start = today.replace(day=1)
    last_month_end = month_start - dt.timedelta(days=1)
    last_month_start = last_month_end.replace(day=1)
    year_start = today.replace(month=1, day=1)

    return [
        {"key": "today", "label": "Сегодня", "date_from": today, "date_to": today},
        {
            "key": "this_week",
            "label": "Эта неделя",
            "date_from": week_start,
            "date_to": week_start + dt.timedelta(days=6),
        },
        {"key": "this_month", "label": "Этот месяц", "date_from": month_start, "date_to": today},
        {"key": "last_month", "label": "Прошлый месяц", "date_from": last_month_start, "date_to": last_month_end},
        {"key": "this_year", "label": "Этот год", "date_from": year_start, "date_to": today},
    ]


def analytics_view(request):
    if not _is_admin_user(request.user):
        raise PermissionDenied("Раздел «Аналитика» доступен только администратору.")

    today = timezone.localdate()
    month_start = today.replace(day=1)

    date_from = _parse_date(request.GET.get("date_from"), month_start)
    date_to = _parse_date(request.GET.get("date_to"), today)
    if date_to < date_from:
        date_from, date_to = date_to, date_from

    teacher_param = request.GET.get("teacher") or ""
    group_param = request.GET.get("group") or ""
    compare_param = request.GET.get("compare") or ""

    dashboard = get_dashboard(
        period="custom",
        start_date=date_from,
        end_date=date_to,
        compare="previous_period" if compare_param else None,
        teacher_id=int(teacher_param) if teacher_param else None,
        group_id=int(group_param) if group_param else None,
        today=today,
    )

    quick_periods = _quick_periods(today)
    active_period_key = next(
        (period["key"] for period in quick_periods if period["date_from"] == date_from and period["date_to"] == date_to),
        "custom",
    )

    filter_params = {"teacher": teacher_param, "group": group_param, "compare": compare_param}
    filter_qs = "&".join(f"{key}={value}" for key, value in filter_params.items() if value)

    def _period_url(period: dict) -> str:
        qs = f"date_from={period['date_from'].isoformat()}&date_to={period['date_to'].isoformat()}"
        if filter_qs:
            qs = f"{qs}&{filter_qs}"
        return f"{reverse('admin:academy_analytics')}?{qs}"

    context = {
        **admin.site.each_context(request),
        "title": "Аналитика",
        "dashboard": dashboard,
        "date_from": date_from,
        "date_to": date_to,
        "teachers": Teacher.objects.filter(is_active=True).select_related("user").order_by("user__first_name"),
        "groups": Group.objects.order_by("name"),
        "selected": {"teacher": teacher_param, "group": group_param, "compare": compare_param},
        "quick_periods": [{**period, "url": _period_url(period)} for period in quick_periods],
        "active_period_key": active_period_key,
        "reset_url": reverse("admin:academy_analytics"),
    }
    return render(request, "admin/academy/analytics.html", context)


# ---------------------------------------------------------------------------
# Program Workspace — one GroupTeacher's (Teaching Program's) complete
# picture in one place: overview, schedule, lesson plan, lessons, attendance,
# homework, homework results, materials, analytics. Every number here is
# scoped strictly to this one GroupTeacher (`lesson__group_teacher=`, never
# just `lesson__group=`), so a Group with several independent programs never
# bleeds one program's figures into another's — the same isolation the
# REST API and Django admin queryset scoping already enforce everywhere
# else (see apps.academy.permissions, models.LessonQuerySet.for_teacher).
#
# Deliberately doesn't call services.analytics.get_dashboard(): that
# service's AnalyticsScope only disambiguates by teacher+group+subject, not
# by GroupTeacher identity, which isn't precise enough for a teacher running
# two differently-subjected programs in the same group. Every figure below
# is instead a direct, exactly-scoped aggregate over this GroupTeacher's own
# Lessons/Attendance/Homework/HomeworkResult — simpler and strictly more
# correct for this one-program-at-a-time view than reusing that service.
# ---------------------------------------------------------------------------

def group_teacher_workspace_view(request, group_teacher_id: int):
    if not _is_admin_user(request.user):
        raise PermissionDenied("Раздел «Рабочее пространство программы» доступен только администратору.")

    group_teacher = get_object_or_404(
        GroupTeacher.objects.select_related("group__course", "teacher__user", "subject"),
        pk=group_teacher_id,
    )
    group = group_teacher.group
    today = timezone.localdate()

    schedules = list(group_teacher.schedules.select_related("room").order_by("day_of_week", "start_time"))
    lesson_plans = list(group_teacher.lesson_plans.order_by("lesson_number"))

    lessons_qs = (
        Lesson.objects.filter(group_teacher=group_teacher)
        .select_related("room", "subject", "plan", "individual_plan")
        .order_by("date", "start_time")
    )
    lessons = list(lessons_qs)
    lesson_stats = {
        "generated": len(lessons),
        "planned_total": len(lesson_plans) or group.course.count_lesson,
        "completed": sum(1 for lesson in lessons if lesson.status == Lesson.Status.COMPLETED),
        "cancelled": sum(1 for lesson in lessons if lesson.status == Lesson.Status.CANCELLED),
        "upcoming": sum(
            1 for lesson in lessons if lesson.status == Lesson.Status.PLANNED and lesson.date >= today
        ),
    }
    upcoming_lessons = [
        lesson for lesson in lessons if lesson.status == Lesson.Status.PLANNED and lesson.date >= today
    ][:10]
    past_lessons = sorted(
        (lesson for lesson in lessons if lesson.date < today or lesson.status != Lesson.Status.PLANNED),
        key=lambda lesson: (lesson.date, lesson.start_time),
        reverse=True,
    )[:10]

    attendance_qs = Attendance.objects.filter(lesson__group_teacher=group_teacher)
    attendance_total = attendance_qs.count()
    attendance_present = attendance_qs.filter(status=Attendance.Status.PRESENT).count()
    attendance_stats = {
        "total": attendance_total,
        "present": attendance_present,
        "absent": attendance_qs.filter(status=Attendance.Status.ABSENT).count(),
        "late": attendance_qs.filter(status=Attendance.Status.LATE).count(),
        "excused": attendance_qs.filter(status=Attendance.Status.EXCUSED).count(),
        "rate": round(100 * attendance_present / attendance_total, 1) if attendance_total else None,
    }

    homework_qs = Homework.objects.filter(lesson__group_teacher=group_teacher).select_related("lesson")
    results_qs = HomeworkResult.objects.filter(homework__lesson__group_teacher=group_teacher)
    avg_score = results_qs.exclude(score__isnull=True).aggregate(avg=Avg("score"))["avg"]
    homework_stats = {
        "assignments": homework_qs.count(),
        "results_total": results_qs.count(),
        "checked": results_qs.filter(status=HomeworkResult.Status.CHECKED).count(),
        "submitted": results_qs.filter(status=HomeworkResult.Status.SUBMITTED).count(),
        "not_submitted": results_qs.filter(status=HomeworkResult.Status.NOT_SUBMITTED).count(),
        "avg_score": round(avg_score, 1) if avg_score is not None else None,
    }

    students = list(group.students.filter(is_active=True).order_by("last_name", "first_name"))

    materials = []
    for plan in lesson_plans:
        if plan.youtube_url or plan.presentation_urls:
            materials.append(
                {
                    "source": f"План занятия №{plan.lesson_number}",
                    "topic": plan.topic,
                    "youtube_url": plan.youtube_url,
                    "presentation_urls": plan.presentation_urls,
                }
            )
    for lesson in lessons:
        if lesson.youtube_url or lesson.presentation_urls:
            materials.append(
                {
                    "source": f"Занятие №{lesson.lesson_number} ({lesson.date:%d.%m.%Y})",
                    "topic": lesson.topic,
                    "youtube_url": lesson.youtube_url,
                    "presentation_urls": lesson.presentation_urls,
                }
            )

    context = {
        **admin.site.each_context(request),
        "title": f"Рабочее пространство — {group_teacher}",
        "group_teacher": group_teacher,
        "group": group,
        "teacher": group_teacher.teacher,
        "subject": group_teacher.subject,
        "students": students,
        "schedules": schedules,
        "lesson_plans": lesson_plans,
        "upcoming_lessons": upcoming_lessons,
        "past_lessons": past_lessons,
        "lesson_stats": lesson_stats,
        "attendance_stats": attendance_stats,
        "homework_stats": homework_stats,
        "materials": materials,
        "group_url": reverse("admin:academy_group_change", args=[group.pk]),
        "group_teacher_url": reverse("admin:academy_groupteacher_change", args=[group_teacher.pk]),
        "lessons_url": f"{reverse('admin:academy_lesson_changelist')}?group_teacher__id__exact={group_teacher.pk}",
        "attendance_url": (
            f"{reverse('admin:academy_attendance_changelist')}?lesson__group_teacher__id__exact={group_teacher.pk}"
        ),
        "homework_url": (
            f"{reverse('admin:academy_homework_changelist')}?lesson__group_teacher__id__exact={group_teacher.pk}"
        ),
        "homework_results_url": (
            f"{reverse('admin:academy_homeworkresult_changelist')}"
            f"?homework__lesson__group_teacher__id__exact={group_teacher.pk}"
        ),
    }
    return render(request, "admin/academy/group_teacher_workspace.html", context)


# ---------------------------------------------------------------------------
# Group Workspace — a Group's own complete control center: Overview,
# Students, Teaching Programs, Schedule, Lessons, Attendance, Homework,
# Analytics. Each tab is a real Django view/URL (not an anchor-scrolled
# section) so Students/Lessons can have real search/filters/pagination and
# Programs/Schedule can have real add/remove forms — GroupAdmin.get_urls()
# wires every path below under /admin/academy/group/<id>/workspace/...,
# following the exact same admin_site.admin_view()/named-URL pattern the
# GroupTeacher workspace and the "Расписание"/"Аналитика" pages above
# already use. Every view is admin-only (spec §18), matching those.
# ---------------------------------------------------------------------------

def _workspace_tabs(group: Group) -> list[dict]:
    # Attendance/Homework kept as their own URLs/views (still reachable, still
    # tested) but folded out of the primary tab bar — this spec's tab list is
    # exactly Overview/Students/Teachers/Programs/Weekly Schedule/Lessons/
    # Analytics; their numbers already surface on Analytics.
    return [
        {"key": "overview", "label": "Обзор", "icon": "bi-clipboard-data",
         "url": reverse("admin:academy_group_workspace", args=[group.pk])},
        {"key": "students", "label": "Студенты", "icon": "bi-people",
         "url": reverse("admin:academy_group_workspace_students", args=[group.pk])},
        {"key": "teachers", "label": "Преподаватели", "icon": "bi-person-badge",
         "url": reverse("admin:academy_group_workspace_teachers", args=[group.pk])},
        {"key": "programs", "label": "Программы", "icon": "bi-kanban",
         "url": reverse("admin:academy_group_workspace_programs", args=[group.pk])},
        {"key": "schedule", "label": "Расписание", "icon": "bi-calendar-week",
         "url": reverse("admin:academy_group_workspace_schedule", args=[group.pk])},
        {"key": "lessons", "label": "Занятия", "icon": "bi-calendar-check",
         "url": reverse("admin:academy_group_workspace_lessons", args=[group.pk])},
        {"key": "analytics", "label": "Аналитика", "icon": "bi-graph-up-arrow",
         "url": reverse("admin:academy_group_workspace_analytics", args=[group.pk])},
    ]


def _workspace_context(request, group: Group, active_tab: str) -> dict:
    return {
        **admin.site.each_context(request),
        "group": group,
        "active_tab": active_tab,
        "tabs": _workspace_tabs(group),
        "change_url": reverse("admin:academy_group_change", args=[group.pk]),
        "changelist_url": reverse("admin:academy_group_changelist"),
        "add_student_url": reverse("admin:academy_group_workspace_students_add", args=[group.pk]),
        "add_existing_students_url": reverse(
            "admin:academy_group_workspace_students_add_existing", args=[group.pk]
        ),
        "add_teacher_url": reverse("admin:academy_group_workspace_teachers_add", args=[group.pk]),
        "add_program_url": reverse("admin:academy_group_workspace_programs_add", args=[group.pk]),
        "add_schedule_url": reverse("admin:academy_group_workspace_schedule_add", args=[group.pk]),
        "generate_lessons_url": reverse("admin:academy_group_workspace_generate_lessons", args=[group.pk]),
    }


def _require_admin(request) -> None:
    if not _is_admin_user(request.user):
        raise PermissionDenied("Рабочее пространство группы доступно только администратору.")


# -- Overview -----------------------------------------------------------

def group_workspace_overview_view(request, group_id):
    _require_admin(request)
    group = get_object_or_404(Group.objects.select_related("course"), pk=group_id)
    today = timezone.localdate()

    lessons_qs = Lesson.objects.filter(group=group)
    completed_count = lessons_qs.filter(status=Lesson.Status.COMPLETED).count()
    upcoming_count = lessons_qs.filter(status=Lesson.Status.PLANNED, date__gte=today).count()

    attendance_qs = Attendance.objects.filter(lesson__group=group)
    attendance_total = attendance_qs.count()
    attendance_present = attendance_qs.filter(
        status__in=[Attendance.Status.PRESENT, Attendance.Status.LATE]
    ).count()
    attendance_rate = round(100 * attendance_present / attendance_total, 1) if attendance_total else None

    programs = list(
        group.teachers.filter(is_active=True)
        .select_related("teacher__user", "subject")
        .prefetch_related("schedules__room")
    )
    program_rows = []
    for gt in programs:
        next_slot = min(
            (s for s in gt.schedules.all() if s.is_active),
            key=lambda s: (WEEKDAY_CODES.index(s.day_of_week), s.start_time),
            default=None,
        )
        program_rows.append(
            {
                "teacher": gt.teacher,
                "subject": gt.subject,
                "next_slot": next_slot,
                "day_label": WEEKDAY_SHORT_LABELS.get(next_slot.day_of_week) if next_slot else None,
                "workspace_url": reverse("admin:academy_groupteacher_workspace", args=[gt.pk]),
            }
        )

    if group.end_date:
        period_label = f"{group.start_date:%d.%m.%Y} – {group.end_date:%d.%m.%Y}"
    else:
        period_label = f"{group.start_date:%d.%m.%Y} – …"

    context = _workspace_context(request, group, "overview")
    context.update(
        {
            "title": group.name,
            "kpi": {
                "students": group.students_count,
                "teachers": len({gt.teacher_id for gt in programs}),
                "programs": len(programs),
                "upcoming_lessons": upcoming_count,
                "completed_lessons": completed_count,
                "attendance_rate": attendance_rate,
            },
            "period_label": period_label,
            "program_rows": program_rows,
        }
    )
    return render(request, "admin/academy/group/workspace/overview.html", context)


# -- Students -------------------------------------------------------------

def group_workspace_students_view(request, group_id):
    _require_admin(request)
    group = get_object_or_404(Group, pk=group_id)

    search = (request.GET.get("q") or "").strip()
    status_filter = request.GET.get("status") or ""

    students_qs = Student.objects.filter(group=group).order_by("last_name", "first_name")
    if search:
        students_qs = students_qs.filter(
            Q(first_name__icontains=search) | Q(last_name__icontains=search) | Q(phone__icontains=search)
        )
    if status_filter == "active":
        students_qs = students_qs.filter(is_active=True)
    elif status_filter == "inactive":
        students_qs = students_qs.filter(is_active=False)

    paginator = Paginator(students_qs, 25)
    page_obj = paginator.get_page(request.GET.get("page"))

    # Candidates for the "Добавить существующих" modal — every other active
    # student, rendered server-side with a client-side search/select-all
    # filter (see ui.js) rather than a second page/endpoint.
    candidate_students = (
        Student.objects.filter(is_active=True)
        .exclude(group=group)
        .select_related("group")
        .order_by("last_name", "first_name")
    )

    context = _workspace_context(request, group, "students")
    context.update(
        {
            "title": f"{group.name} — Студенты",
            "students": page_obj,
            "search": search,
            "status_filter": status_filter,
            "candidate_students": candidate_students,
            "export_url": f"{reverse('admin:academy_student_export')}?group__id__exact={group.pk}",
            "bulk_add_url": reverse("admin:academy_student_bulk_add"),
            "import_url": reverse("admin:academy_student_import"),
        }
    )
    return render(request, "admin/academy/group/workspace/students.html", context)


class GroupCreateStudentForm(forms.ModelForm):
    class Meta:
        model = Student
        fields = ["first_name", "last_name", "phone", "parent_phone", "is_active"]
        widgets = {
            "first_name": forms.TextInput(attrs={"class": "ok-input"}),
            "last_name": forms.TextInput(attrs={"class": "ok-input"}),
            "phone": forms.TextInput(attrs={"class": "ok-input"}),
            "parent_phone": forms.TextInput(attrs={"class": "ok-input"}),
        }


def group_workspace_add_student_view(request, group_id):
    """The compact "+ Добавить студента" quick-create form (spec §6) — a
    single new Student, auto-attached to this group, admin stays in the
    Workspace afterwards. Picking from *existing* students is a separate,
    modal-based bulk flow on the Students tab itself (see
    group_workspace_add_existing_students_view)."""
    _require_admin(request)
    group = get_object_or_404(Group, pk=group_id)

    if request.method == "POST":
        create_form = GroupCreateStudentForm(request.POST)
        if create_form.is_valid():
            student = create_form.save(commit=False)
            student.group = group
            student.save()
            messages.success(request, f"Студент «{student}» создан и добавлен в группу «{group.name}».")
            return redirect(reverse("admin:academy_group_workspace_students", args=[group.pk]))
    else:
        create_form = GroupCreateStudentForm(initial={"is_active": True})

    context = _workspace_context(request, group, "students")
    context.update({"title": f"{group.name} — Добавить студента", "create_form": create_form})
    return render(request, "admin/academy/group/workspace/add_student.html", context)


def group_workspace_add_existing_students_view(request, group_id):
    """POST target of the Students tab's "Добавить существующих" modal
    (spec §5): checkbox multi-select + search + select-all, all rendered
    server-side on students.html — this view only ever receives the final
    submit. Moving an already-grouped student here re-assigns them (Student.
    group is a single FK — see models.Student), matching how the rest of
    the app already treats "add to a group"."""
    _require_admin(request)
    if request.method != "POST":
        raise PermissionDenied
    group = get_object_or_404(Group, pk=group_id)

    student_ids = [pk for pk in request.POST.getlist("students") if pk.isdigit()]
    if not student_ids:
        messages.warning(request, "Не выбрано ни одного студента.")
    else:
        updated = Student.objects.filter(pk__in=student_ids).update(group=group)
        messages.success(request, f"Добавлено студентов в группу «{group.name}»: {updated}.")

    return redirect(reverse("admin:academy_group_workspace_students", args=[group.pk]))


def group_workspace_remove_student_view(request, group_id, student_id):
    _require_admin(request)
    if request.method != "POST":
        raise PermissionDenied
    group = get_object_or_404(Group, pk=group_id)
    student = get_object_or_404(Student, pk=student_id, group=group)
    student.group = None
    student.save(update_fields=["group", "updated_at"])
    messages.success(
        request,
        f"«{student}» удалён(а) из группы «{group.name}». Студент не удалён — история сохранена.",
    )
    return redirect(reverse("admin:academy_group_workspace_students", args=[group.pk]))


# -- Teaching Programs ------------------------------------------------------

def group_workspace_programs_view(request, group_id):
    _require_admin(request)
    group = get_object_or_404(Group.objects.select_related("course"), pk=group_id)

    context = _workspace_context(request, group, "programs")
    context.update({"title": f"{group.name} — Программы", "cards": _teaching_program_cards(group)})
    return render(request, "admin/academy/group/workspace/programs.html", context)


def _teaching_program_cards(group: Group) -> list[dict]:
    """One dict per GroupTeacher (Teaching Program) of `group` — shared by
    both the Teachers tab (roster: add/remove the assignment) and the
    Programs tab (business view: schedule/lesson-plan progress/generate),
    so the same query runs once and both tabs render the same real numbers.
    """
    today = timezone.localdate()
    programs = list(
        group.teachers.select_related("teacher__user", "subject")
        .prefetch_related("schedules__room")
        .annotate(_plan_count=Count("lesson_plans", distinct=True))
    )

    cards = []
    for gt in programs:
        active_slots = sorted(
            (s for s in gt.schedules.all() if s.is_active),
            key=lambda s: (WEEKDAY_CODES.index(s.day_of_week), s.start_time),
        )
        lessons = Lesson.objects.filter(group_teacher=gt)
        has_individual_plan = gt._plan_count > 0
        plan_filled = gt._plan_count if has_individual_plan else group.course.lesson_plans.count()
        cards.append(
            {
                "obj": gt,
                "slots": [
                    {
                        "day_label": WEEKDAY_SHORT_LABELS.get(s.day_of_week, s.day_of_week),
                        "time_label": f"{s.start_time:%H:%M}–{s.end_time:%H:%M}",
                        "room": s.room.name if s.room_id else "без кабинета",
                    }
                    for s in active_slots
                ],
                "lesson_count": lessons.count(),
                "completed_count": lessons.filter(status=Lesson.Status.COMPLETED).count(),
                "upcoming_count": lessons.filter(status=Lesson.Status.PLANNED, date__gte=today).count(),
                "plan_count": gt._plan_count,
                "has_individual_plan": has_individual_plan,
                "plan_filled": plan_filled,
                "plan_total": group.course.count_lesson,
                "workspace_url": reverse("admin:academy_groupteacher_workspace", args=[gt.pk]),
                "edit_url": reverse("admin:academy_groupteacher_change", args=[gt.pk]),
                "lesson_plan_url": (
                    reverse("admin:academy_groupteacher_change", args=[gt.pk])
                    if has_individual_plan
                    else f"{reverse('admin:academy_courselessonplan_changelist')}?course__id__exact={group.course_id}"
                ),
                "schedule_url": reverse("admin:academy_group_workspace_schedule", args=[group.pk]),
                "remove_url": reverse("admin:academy_group_workspace_teachers_remove", args=[group.pk, gt.pk]),
            }
        )
    return cards


# -- Teachers ---------------------------------------------------------------

def group_workspace_teachers_view(request, group_id):
    _require_admin(request)
    group = get_object_or_404(Group.objects.select_related("course"), pk=group_id)

    context = _workspace_context(request, group, "teachers")
    context.update({"title": f"{group.name} — Преподаватели", "cards": _teaching_program_cards(group)})
    return render(request, "admin/academy/group/workspace/teachers.html", context)


class AddTeacherAssignmentForm(forms.Form):
    teacher = forms.ModelChoiceField(
        queryset=Teacher.objects.filter(is_active=True).select_related("user"),
        label="Тренер",
        widget=forms.Select(attrs={"class": "ok-input"}),
    )
    subject = forms.ModelChoiceField(
        queryset=Subject.objects.none(), label="Предмет", widget=forms.Select(attrs={"class": "ok-input"})
    )

    def __init__(self, *args, group=None, **kwargs):
        super().__init__(*args, **kwargs)
        if group is not None:
            self.fields["subject"].queryset = group.course.subjects.filter(is_active=True)


def group_workspace_add_teacher_view(request, group_id):
    """Lightweight assignment (spec §7): just Teacher + Subject, no schedule
    required up front — creates a bare GroupTeacher directly (the same
    model GroupSchedule.save() would derive one into, just without a slot
    yet). The admin adds a weekly schedule for it afterwards, from the
    Teachers or Weekly Schedule tab."""
    _require_admin(request)
    group = get_object_or_404(Group.objects.select_related("course"), pk=group_id)

    if request.method == "POST":
        form = AddTeacherAssignmentForm(request.POST, group=group)
        if form.is_valid():
            teacher = form.cleaned_data["teacher"]
            subject = form.cleaned_data["subject"]
            group_teacher, created = GroupTeacher.objects.get_or_create(
                group=group, teacher=teacher, subject=subject
            )
            if created:
                messages.success(
                    request,
                    f"Преподаватель «{teacher}» добавлен ({subject.name}). "
                    "Теперь добавьте для него расписание.",
                )
            else:
                messages.warning(request, f"«{teacher}» уже преподаёт «{subject.name}» в этой группе.")
            return redirect(reverse("admin:academy_group_workspace_teachers", args=[group.pk]))
    else:
        form = AddTeacherAssignmentForm(group=group)

    context = _workspace_context(request, group, "teachers")
    context.update({"title": f"{group.name} — Добавить преподавателя", "form": form})
    return render(request, "admin/academy/group/workspace/add_teacher.html", context)


def group_workspace_remove_teacher_view(request, group_id, group_teacher_id):
    """Removes the assignment itself (spec §7 "Удалить назначение"), not a
    student — GroupSchedule rows of this GroupTeacher cascade-delete with
    it (models.GroupSchedule.group_teacher, on_delete=CASCADE); Lessons/
    Attendance/Homework already generated keep their history and just lose
    the program link (models.Lesson.group_teacher, on_delete=SET_NULL)."""
    _require_admin(request)
    if request.method != "POST":
        raise PermissionDenied
    group = get_object_or_404(Group, pk=group_id)
    group_teacher = get_object_or_404(GroupTeacher, pk=group_teacher_id, group=group)
    label = f"{group_teacher.teacher} — {group_teacher.subject.name if group_teacher.subject_id else 'без предмета'}"
    group_teacher.delete()
    messages.success(request, f"Назначение «{label}» удалено.")
    return redirect(reverse("admin:academy_group_workspace_teachers", args=[group.pk]))


class AddTeachingProgramForm(forms.Form):
    teacher = forms.ModelChoiceField(
        queryset=Teacher.objects.filter(is_active=True).select_related("user"),
        label="Тренер",
        widget=forms.Select(attrs={"class": "ok-input"}),
    )
    subject = forms.ModelChoiceField(
        queryset=Subject.objects.none(), label="Предмет", widget=forms.Select(attrs={"class": "ok-input"})
    )
    day_of_week = forms.MultipleChoiceField(
        choices=GroupSchedule.DAY_CHOICES,
        label="Дни недели",
        widget=forms.CheckboxSelectMultiple,
    )
    start_time = forms.TimeField(
        label="Время начала", widget=forms.TimeInput(attrs={"class": "ok-input", "type": "time"})
    )
    end_time = forms.TimeField(
        label="Время окончания", widget=forms.TimeInput(attrs={"class": "ok-input", "type": "time"})
    )
    room = forms.ModelChoiceField(
        queryset=Room.objects.filter(is_active=True), required=False, label="Кабинет",
        widget=forms.Select(attrs={"class": "ok-input"}),
    )
    lesson_plan_source = forms.ChoiceField(
        choices=[("course", "Общий план курса"), ("individual", "Индивидуальный план программы")],
        initial="course",
        label="План занятий",
        widget=forms.RadioSelect,
    )

    def __init__(self, *args, group=None, **kwargs):
        super().__init__(*args, **kwargs)
        if group is not None:
            self.fields["subject"].queryset = group.course.subjects.filter(is_active=True)

    def clean(self):
        cleaned = super().clean()
        start, end = cleaned.get("start_time"), cleaned.get("end_time")
        if start and end and end <= start:
            self.add_error("end_time", "Время окончания должно быть позже времени начала.")
        return cleaned


def group_workspace_add_program_view(request, group_id):
    _require_admin(request)
    group = get_object_or_404(Group.objects.select_related("course"), pk=group_id)

    if request.method == "POST":
        form = AddTeachingProgramForm(request.POST, group=group)
        if form.is_valid():
            teacher = form.cleaned_data["teacher"]
            subject = form.cleaned_data["subject"]
            days = form.cleaned_data["day_of_week"]
            start_time = form.cleaned_data["start_time"]
            end_time = form.cleaned_data["end_time"]
            room = form.cleaned_data.get("room")
            wants_individual_plan = form.cleaned_data["lesson_plan_source"] == "individual"
            day_labels = dict(GroupSchedule.DAY_CHOICES)

            new_slots = []
            has_errors = False
            for day in days:
                slot = GroupSchedule(
                    group=group, teacher=teacher, subject=subject,
                    day_of_week=day, start_time=start_time, end_time=end_time, room=room,
                )
                try:
                    slot.full_clean()
                except DjangoValidationError as exc:
                    has_errors = True
                    for message in (exc.messages if hasattr(exc, "messages") else [str(exc)]):
                        messages.error(request, f"{day_labels.get(day, day)}: {message}")
                else:
                    new_slots.append(slot)

            if not has_errors:
                with transaction.atomic():
                    for slot in new_slots:
                        slot.save()
                messages.success(
                    request,
                    f"Учебная программа добавлена: {teacher} — {subject.name} "
                    f"({len(new_slots)} слот(ов) расписания).",
                )
                if wants_individual_plan:
                    # Reuses the existing GroupTeacherLessonPlanInline on
                    # GroupTeacherAdmin's own change page — no new
                    # lesson-plan editor built here.
                    group_teacher = new_slots[0].group_teacher
                    messages.info(request, "Заполните индивидуальный план занятий для этой программы ниже.")
                    return redirect(reverse("admin:academy_groupteacher_change", args=[group_teacher.pk]))
                return redirect(reverse("admin:academy_group_workspace_programs", args=[group.pk]))
    else:
        form = AddTeachingProgramForm(group=group)

    context = _workspace_context(request, group, "programs")
    context.update({"title": f"{group.name} — Добавить учебную программу", "form": form})
    return render(request, "admin/academy/group/workspace/add_program.html", context)


# -- Schedule ---------------------------------------------------------------

def group_workspace_schedule_view(request, group_id):
    """Weekly Schedule tab (spec §9): day-grouped blocks — Monday through
    Sunday, each holding every slot that falls on it, sorted by start
    time — rather than one flat, hard-to-scan table."""
    _require_admin(request)
    group = get_object_or_404(Group, pk=group_id)

    slots = list(
        GroupSchedule.objects.filter(group=group)
        .select_related("teacher__user", "group_teacher__subject", "room")
    )

    def _row(slot: GroupSchedule) -> dict:
        return {
            "obj": slot,
            "program_label": (
                slot.group_teacher.subject.name
                if slot.group_teacher_id and slot.group_teacher.subject_id
                else "Без предмета"
            ),
            "teacher": slot.teacher,
            "time_label": f"{slot.start_time:%H:%M}–{slot.end_time:%H:%M}",
            "room": slot.room.name if slot.room_id else "—",
            "is_active": slot.is_active,
            "remove_url": reverse(
                "admin:academy_group_workspace_schedule_remove", args=[group.pk, slot.pk]
            ),
        }

    days = [
        {
            "code": code,
            "label": WEEKDAY_LABELS_FULL[code],
            "slots": sorted(
                (_row(s) for s in slots if s.day_of_week == code), key=lambda r: r["obj"].start_time
            ),
        }
        for code in WEEKDAY_CODES
    ]

    context = _workspace_context(request, group, "schedule")
    context.update({"title": f"{group.name} — Расписание", "days": days, "has_any_slot": bool(slots)})
    return render(request, "admin/academy/group/workspace/schedule.html", context)


class AddScheduleSlotForm(forms.Form):
    group_teacher = forms.ModelChoiceField(
        queryset=GroupTeacher.objects.none(),
        label="Учебная программа",
        widget=forms.Select(attrs={"class": "ok-input"}),
    )
    day_of_week = forms.ChoiceField(
        choices=GroupSchedule.DAY_CHOICES, label="День недели", widget=forms.Select(attrs={"class": "ok-input"})
    )
    start_time = forms.TimeField(
        label="Время начала", widget=forms.TimeInput(attrs={"class": "ok-input", "type": "time"})
    )
    end_time = forms.TimeField(
        label="Время окончания", widget=forms.TimeInput(attrs={"class": "ok-input", "type": "time"})
    )
    room = forms.ModelChoiceField(
        queryset=Room.objects.filter(is_active=True), required=False, label="Кабинет",
        widget=forms.Select(attrs={"class": "ok-input"}),
    )

    def __init__(self, *args, group=None, **kwargs):
        super().__init__(*args, **kwargs)
        if group is not None:
            self.fields["group_teacher"].queryset = (
                group.teachers.filter(is_active=True).select_related("teacher__user", "subject")
            )

    def clean(self):
        cleaned = super().clean()
        start, end = cleaned.get("start_time"), cleaned.get("end_time")
        if start and end and end <= start:
            self.add_error("end_time", "Время окончания должно быть позже времени начала.")
        return cleaned


def group_workspace_add_schedule_view(request, group_id):
    _require_admin(request)
    group = get_object_or_404(Group, pk=group_id)

    if not group.teachers.filter(is_active=True).exists():
        messages.warning(request, "Сначала добавьте хотя бы одну учебную программу.")
        return redirect(reverse("admin:academy_group_workspace_programs", args=[group.pk]))

    if request.method == "POST":
        form = AddScheduleSlotForm(request.POST, group=group)
        if form.is_valid():
            group_teacher = form.cleaned_data["group_teacher"]
            slot = GroupSchedule(
                group=group, teacher=group_teacher.teacher, subject=group_teacher.subject,
                day_of_week=form.cleaned_data["day_of_week"], start_time=form.cleaned_data["start_time"],
                end_time=form.cleaned_data["end_time"], room=form.cleaned_data.get("room"),
            )
            try:
                slot.full_clean()
            except DjangoValidationError as exc:
                for message in (exc.messages if hasattr(exc, "messages") else [str(exc)]):
                    messages.error(request, message)
            else:
                slot.save()
                messages.success(request, "Слот расписания добавлен.")
                return redirect(reverse("admin:academy_group_workspace_schedule", args=[group.pk]))
    else:
        initial = {}
        program_id = request.GET.get("program")
        if program_id and program_id.isdigit():
            initial["group_teacher"] = program_id
        form = AddScheduleSlotForm(group=group, initial=initial)

    context = _workspace_context(request, group, "schedule")
    context.update({"title": f"{group.name} — Добавить расписание", "form": form})
    return render(request, "admin/academy/group/workspace/add_schedule.html", context)


def group_workspace_remove_schedule_view(request, group_id, schedule_id):
    _require_admin(request)
    if request.method != "POST":
        raise PermissionDenied
    group = get_object_or_404(Group, pk=group_id)
    slot = get_object_or_404(GroupSchedule, pk=schedule_id, group=group)
    slot.delete()
    messages.success(request, "Слот расписания удалён.")
    return redirect(reverse("admin:academy_group_workspace_schedule", args=[group.pk]))


# -- Lessons ------------------------------------------------------------

def group_workspace_lessons_view(request, group_id):
    _require_admin(request)
    group = get_object_or_404(Group, pk=group_id)

    lessons_qs = (
        Lesson.objects.filter(group=group)
        .select_related("group_teacher__teacher__user", "group_teacher__subject", "teacher__user", "subject", "room")
        .annotate(
            attendance_count=Count("attendance_records", distinct=True),
            homework_count=Count("homeworks", distinct=True),
        )
        .order_by("-date", "-start_time")
    )

    program_id = request.GET.get("program") or ""
    teacher_id = request.GET.get("teacher") or ""
    subject_id = request.GET.get("subject") or ""
    status = request.GET.get("status") or ""
    date_from = request.GET.get("date_from") or ""
    date_to = request.GET.get("date_to") or ""

    if program_id:
        lessons_qs = lessons_qs.filter(group_teacher_id=program_id)
    if teacher_id:
        lessons_qs = lessons_qs.filter(
            Q(teacher_id=teacher_id) | Q(teacher__isnull=True, group_teacher__teacher_id=teacher_id)
        )
    if subject_id:
        lessons_qs = lessons_qs.filter(subject_id=subject_id)
    if status:
        lessons_qs = lessons_qs.filter(status=status)
    if date_from:
        parsed = _parse_date(date_from, None)
        if parsed:
            lessons_qs = lessons_qs.filter(date__gte=parsed)
    if date_to:
        parsed = _parse_date(date_to, None)
        if parsed:
            lessons_qs = lessons_qs.filter(date__lte=parsed)

    paginator = Paginator(lessons_qs, 25)
    page_obj = paginator.get_page(request.GET.get("page"))

    context = _workspace_context(request, group, "lessons")
    context.update(
        {
            "title": f"{group.name} — Занятия",
            "lessons": page_obj,
            "programs": group.teachers.filter(is_active=True).select_related("teacher__user", "subject"),
            "teachers": Teacher.objects.filter(group_assignments__group=group).distinct(),
            "subjects": Subject.objects.filter(group_assignments__group=group).distinct(),
            "status_choices": Lesson.Status.choices,
            "selected": {
                "program": program_id, "teacher": teacher_id, "subject": subject_id, "status": status,
                "date_from": date_from, "date_to": date_to,
            },
        }
    )
    return render(request, "admin/academy/group/workspace/lessons.html", context)


# -- Attendance ---------------------------------------------------------

def group_workspace_attendance_view(request, group_id):
    _require_admin(request)
    group = get_object_or_404(Group, pk=group_id)

    attendance_qs = (
        Attendance.objects.filter(lesson__group=group)
        .select_related("student", "lesson")
        .order_by("-lesson__date")
    )
    status_filter = request.GET.get("status") or ""
    all_qs = attendance_qs
    if status_filter:
        attendance_qs = attendance_qs.filter(status=status_filter)

    total = all_qs.count()
    present = all_qs.filter(status=Attendance.Status.PRESENT).count()
    rate = (
        round(100 * all_qs.filter(status__in=[Attendance.Status.PRESENT, Attendance.Status.LATE]).count() / total, 1)
        if total
        else None
    )

    paginator = Paginator(attendance_qs, 30)
    page_obj = paginator.get_page(request.GET.get("page"))

    context = _workspace_context(request, group, "attendance")
    context.update(
        {
            "title": f"{group.name} — Посещаемость",
            "records": page_obj,
            "stats": {
                "total": total,
                "present": present,
                "absent": all_qs.filter(status=Attendance.Status.ABSENT).count(),
                "late": all_qs.filter(status=Attendance.Status.LATE).count(),
                "excused": all_qs.filter(status=Attendance.Status.EXCUSED).count(),
                "rate": rate,
            },
            "status_choices": Attendance.Status.choices,
            "selected_status": status_filter,
        }
    )
    return render(request, "admin/academy/group/workspace/attendance.html", context)


# -- Homework -------------------------------------------------------------

def group_workspace_homework_view(request, group_id):
    _require_admin(request)
    group = get_object_or_404(Group, pk=group_id)

    homework_qs = (
        Homework.objects.filter(lesson__group=group)
        .select_related("lesson")
        .annotate(results_count=Count("results", distinct=True))
        .order_by("-created_at")
    )
    results_qs = HomeworkResult.objects.filter(homework__lesson__group=group)

    paginator = Paginator(homework_qs, 25)
    page_obj = paginator.get_page(request.GET.get("page"))

    context = _workspace_context(request, group, "homework")
    context.update(
        {
            "title": f"{group.name} — Домашние задания",
            "homeworks": page_obj,
            "stats": {
                "assignments": homework_qs.count(),
                "results_total": results_qs.count(),
                "checked": results_qs.filter(status=HomeworkResult.Status.CHECKED).count(),
                "submitted": results_qs.filter(
                    status__in=[
                        HomeworkResult.Status.SUBMITTED,
                        HomeworkResult.Status.LATE,
                        HomeworkResult.Status.CHECKED,
                    ]
                ).count(),
            },
        }
    )
    return render(request, "admin/academy/group/workspace/homework.html", context)


# -- Analytics ------------------------------------------------------------

def group_workspace_analytics_view(request, group_id):
    _require_admin(request)
    group = get_object_or_404(Group, pk=group_id)
    today = timezone.localdate()

    lessons_qs = Lesson.objects.filter(group=group)
    attendance_qs = Attendance.objects.filter(lesson__group=group)
    attendance_total = attendance_qs.count()
    attendance_present = attendance_qs.filter(
        status__in=[Attendance.Status.PRESENT, Attendance.Status.LATE]
    ).count()

    results_qs = HomeworkResult.objects.filter(homework__lesson__group=group)
    results_total = results_qs.count()
    results_checked = results_qs.filter(status=HomeworkResult.Status.CHECKED).count()

    context = _workspace_context(request, group, "analytics")
    context.update(
        {
            "title": f"{group.name} — Аналитика",
            "stats": {
                "students_count": group.students_count,
                "programs_count": group.teachers.filter(is_active=True).count(),
                "completed_lessons": lessons_qs.filter(status=Lesson.Status.COMPLETED).count(),
                "upcoming_lessons": lessons_qs.filter(
                    status=Lesson.Status.PLANNED, date__gte=today
                ).count(),
                "attendance_rate": (
                    round(100 * attendance_present / attendance_total, 1) if attendance_total else None
                ),
                "homework_completion_rate": (
                    round(100 * results_checked / results_total, 1) if results_total else None
                ),
            },
        }
    )
    return render(request, "admin/academy/group/workspace/analytics.html", context)


# -- Generate lessons -----------------------------------------------------

@require_POST
def group_workspace_generate_lessons_view(request, group_id):
    _require_admin(request)
    group = get_object_or_404(Group, pk=group_id)
    report = generate_lessons_for_group_with_report(group)

    summary_parts = [f"Создано: {report.created}", f"Уже существовало: {report.already_existed}"]
    if report.conflicts_skipped:
        summary_parts.append(f"Конфликтов пропущено: {report.conflicts_skipped}")
    summary_parts.append(f"Ошибок: {len(report.errors)}")

    level = messages.SUCCESS if report.created or not report.errors else messages.WARNING
    messages.add_message(request, level, " · ".join(summary_parts))
    for error in report.errors:
        messages.error(request, error)

    next_url = request.POST.get("next") or reverse("admin:academy_group_workspace", args=[group.pk])
    return redirect(next_url)
