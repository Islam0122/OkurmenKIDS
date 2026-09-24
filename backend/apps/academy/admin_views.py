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
from django.db.models import Avg, Count, Min, Prefetch, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.formats import number_format
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from apps.users.models import Subject, Teacher, User

from .constants import WEEKDAY_CODES, WEEKDAY_LABELS_FULL, WEEKDAY_LABELS_SHORT
from .models import (
    AcademyMonthlyReport,
    Attendance,
    Course,
    Group,
    GroupSchedule,
    GroupTeacher,
    Homework,
    HomeworkResult,
    Lesson,
    MonthlyTeacherReport,
    Room,
    Student,
    StudentStatusEvent,
)
from .services.academy_monthly_report import compute_academy_monthly_stats
from .services.analytics import get_dashboard
from .services.chart_geometry import nice_domain, nice_ticks, ratio_in_domain
from .services.group_schedule_conflicts import overlapping_groups
from .services.lesson_status import attention_q, lesson_status_counts
from .services.monthly_report import compute_monthly_stats
from .services.monthly_report_pdf import MONTH_NAMES_RU
from .services.group_analytics import PERIOD_CHOICES, GroupAnalyticsFilters, get_group_analytics
from .services.lesson_generator import (
    LessonGenerationReport,
    generate_lessons_for_group_with_report,
    planned_lessons_by_program,
    preview_generation,
)
from .services.program_editing import build_schedule_slots, future_lessons, update_teaching_program
from .services.subject_assignments import STATUS_UNASSIGNED, subject_assignment_overview

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


def _lesson_status_kpi(lessons_qs, today: dt.date) -> dict:
    """The one, shared definition of "how many lessons are total/today/
    upcoming/completed/cancelled/requiring attention/this week" for a given
    (already filtered) Lesson queryset — used by both the Group Workspace
    overview and the Lessons monitoring page, so the same underlying data
    never reports two different numbers in two different places (spec: no
    duplicate source of truth for lesson statistics). The actual per-status
    counting lives in services.lesson_status.lesson_status_counts — the same
    function the Analytics dashboard uses — so this is the Admin-dashboard
    shaping of it, not a second implementation.

    Status-based, not date-based: "completed"/"cancelled" reflect the real
    `Lesson.status` value only — a lesson is never inferred as completed
    just because its date has passed, since status requires an explicit
    transition (start/complete/cancel — see services.lesson_lifecycle).
    "Upcoming" is still-scheduled and not yet in the past; "attention" is
    the opposite failure mode — still scheduled/in_progress but *already* in
    the past, i.e. a lesson a teacher forgot to start/finish.
    """
    week_start = _week_start(today)
    week_end = week_start + dt.timedelta(days=6)
    counts = lesson_status_counts(lessons_qs, today=today)
    return {
        "total": counts["total"],
        "today": lessons_qs.filter(date=today).count(),
        "upcoming": counts["upcoming"],
        "completed": counts["completed"],
        "cancelled": counts["cancelled"],
        "attention": counts["attention"],
        "this_week": lessons_qs.filter(date__gte=week_start, date__lte=week_end).count(),
    }


def _detect_conflicts(lessons: Iterable[Lesson]) -> tuple[list[dict], list[dict], list[dict], set[int]]:
    """Group-overlap check within the lessons currently on screen.

    Cancelled lessons never conflict with anything — a room/teacher/group
    slot freed up by a cancellation isn't a clash. Returns (teacher_conflicts,
    room_conflicts, group_conflicts, conflicting_lesson_ids) so the template
    can both list the conflicts and flag the individual cards. Each of the
    three lists holds *one* entry per genuinely conflicting cluster (see
    services.group_schedule_conflicts.overlapping_groups) — never one entry
    per pair.
    """
    active = [lesson for lesson in lessons if lesson.status != Lesson.Status.CANCELLED]

    by_teacher: dict[tuple[int | None, dt.date], list[Lesson]] = defaultdict(list)
    by_room: dict[tuple[int, dt.date], list[Lesson]] = defaultdict(list)
    by_group: dict[tuple[int, dt.date], list[Lesson]] = defaultdict(list)
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
        # A Group cannot physically attend two programs at once — checked
        # even when teacher and room both differ (see
        # services.group_schedule_conflicts.find_schedule_group_conflict).
        by_group[(lesson.group_id, lesson.date)].append(lesson)

    conflicting_ids: set[int] = set()

    def _grouped_conflicts(buckets, label_fn):
        found = []
        for key, bucket in buckets.items():
            for group in overlapping_groups(bucket):
                for lesson in group:
                    conflicting_ids.add(lesson.id)
                found.append({"label": label_fn(group[0]), "date": key[1], "lessons": group})
        return found

    teacher_conflicts = _grouped_conflicts(by_teacher, lambda l: str(l.effective_teacher))
    room_conflicts = _grouped_conflicts(by_room, lambda l: str(l.room))
    group_conflicts = _grouped_conflicts(by_group, lambda l: str(l.group))

    return teacher_conflicts, room_conflicts, group_conflicts, conflicting_ids


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
    teacher_conflicts, room_conflicts, group_conflicts, conflicting_ids = _detect_conflicts(lessons)

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
        "group_conflicts": group_conflicts,
        "conflicting_ids": conflicting_ids,
        "prev_week_url": _nav_url(week_start - dt.timedelta(days=7)),
        "next_week_url": _nav_url(week_start + dt.timedelta(days=7)),
        "today_url": _nav_url(today),
        "selected_group": Group.objects.filter(pk=group_id).first() if group_id else None,
    }
    return render(request, "admin/academy/schedule.html", context)


def add_generation_messages(request, report: LessonGenerationReport, *, prefix: str = "") -> None:
    """One place that turns a generation report into admin flash messages —
    shared by the Schedule page's quick action, the Group Workspace button
    and the Group changelist action, so all three tell the admin the same
    thing, including which lessons were *not* created and why."""
    summary_parts = [f"Создано: {report.created}", f"Уже существовало: {report.already_existed}"]
    if report.orphans_deleted:
        summary_parts.append(f"Удалено занятий без программы: {len(report.orphans_deleted)}")
    if report.expected:
        summary_parts.append(f"По плану: {report.expected}")
    if report.missing:
        summary_parts.append(f"Не создано: {report.missing}")
    if report.skipped:
        summary_parts.append(f"Пропущено: {report.skipped}")
    if report.conflicts:
        summary_parts.append(f"Конфликтов: {report.conflicts}")
    summary_parts.append(f"Ошибок: {len(report.errors)}")

    if report.errors and not report.created:
        level = messages.ERROR
    elif report.warnings or report.errors:
        level = messages.WARNING
    elif report.created:
        level = messages.SUCCESS
    else:
        level = messages.INFO
    messages.add_message(request, level, prefix + " · ".join(summary_parts))
    if report.orphans_deleted:
        messages.info(
            request,
            prefix + "Удалены занятия без программы (не проведённые, без посещаемости и оценок; созданы "
            "заново в своих программах, если предмет ведётся): " + "; ".join(report.orphans_deleted),
        )
    for warning in report.warnings:
        messages.warning(request, prefix + warning)
    for error in report.errors:
        messages.error(request, prefix + error)


@require_POST
def generate_lessons_for_group_view(request, group_id: int):
    if not _is_admin_user(request.user):
        raise PermissionDenied("Действие доступно только администратору.")

    group = get_object_or_404(Group, pk=group_id)
    report = generate_lessons_for_group_with_report(group)
    add_generation_messages(request, report, prefix=f"«{group.name}»: ")

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
        # This program's own share of the plan (its individual plan, or its
        # subject's rows of the shared course plan — e.g. 48 of 144), never
        # the whole course plan.
        "planned_total": planned_lessons_by_program(group).get(group_teacher.pk, 0),
        "completed": sum(1 for lesson in lessons if lesson.status == Lesson.Status.COMPLETED),
        "cancelled": sum(1 for lesson in lessons if lesson.status == Lesson.Status.CANCELLED),
        "upcoming": sum(
            1 for lesson in lessons if lesson.status == Lesson.Status.SCHEDULED and lesson.date >= today
        ),
    }
    upcoming_lessons = [
        lesson for lesson in lessons if lesson.status == Lesson.Status.SCHEDULED and lesson.date >= today
    ][:10]
    past_lessons = sorted(
        (lesson for lesson in lessons if lesson.date < today or lesson.status != Lesson.Status.SCHEDULED),
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
        "lessons_url": f"{reverse('admin:academy_lesson_changelist')}?group_teacher={group_teacher.pk}",
        "attendance_url": f"{reverse('admin:academy_attendance_changelist')}?group_teacher={group_teacher.pk}",
        "homework_url": f"{reverse('admin:academy_homework_changelist')}?group_teacher={group_teacher.pk}",
        "homework_results_url": (
            f"{reverse('admin:academy_homeworkresult_changelist')}?group_teacher={group_teacher.pk}"
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
    """The canonical Group Workspace sections, in order."""
    tabs = [
        ("overview", "Обзор", "bi-clipboard-data", "academy_group_workspace"),
        ("students", "Студенты", "bi-people", "academy_group_workspace_students"),
        ("teachers", "Преподаватели", "bi-person-badge", "academy_group_workspace_teachers"),
        ("programs", "Программы", "bi-kanban", "academy_group_workspace_programs"),
        ("schedule", "Расписание", "bi-calendar-week", "academy_group_workspace_schedule"),
        ("lessons", "Занятия", "bi-calendar-check", "academy_group_workspace_lessons"),
        ("attendance", "Посещаемость", "bi-person-check", "academy_group_workspace_attendance"),
        ("homework", "Домашние задания", "bi-journal-text", "academy_group_workspace_homework"),
        ("analytics", "Аналитика", "bi-graph-up-arrow", "academy_group_workspace_analytics"),
    ]
    return [
        {"key": key, "label": label, "icon": icon, "url": reverse(f"admin:{name}", args=[group.pk])}
        for key, label, icon, name in tabs
    ]


def _safe_next(request, default: str) -> str:
    """`next` from the POST/GET data if it points back into this site,
    else `default` — never an open redirect to another host."""
    candidate = request.POST.get("next") or request.GET.get("next")
    if candidate and url_has_allowed_host_and_scheme(
        candidate, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return candidate
    return default


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
        "generate_preview_url": reverse("admin:academy_group_workspace_generate_preview", args=[group.pk]),
        "programs_url": reverse("admin:academy_group_workspace_programs", args=[group.pk]),
    }


def _require_admin(request) -> None:
    if not _is_admin_user(request.user):
        raise PermissionDenied("Рабочее пространство группы доступно только администратору.")


# -- Overview -----------------------------------------------------------

def group_workspace_overview_view(request, group_id):
    _require_admin(request)
    group = get_object_or_404(Group.objects.select_related("course"), pk=group_id)
    today = timezone.localdate()

    lesson_kpi = _lesson_status_kpi(Lesson.objects.filter(group=group), today)

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
                "upcoming_lessons": lesson_kpi["upcoming"],
                "completed_lessons": lesson_kpi["completed"],
                "cancelled_lessons": lesson_kpi["cancelled"],
                "attention_lessons": lesson_kpi["attention"],
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
#
# The Programs tab is the group's control panel: one row per Teaching
# Program (GroupTeacher) — subject, trainer, plan vs. created lessons,
# progress, next lesson, status — plus one row per course subject nobody
# teaches yet. Everyday edits (trainer, subject, status, weekly slots)
# happen in a right-side drawer on the same page
# (group_workspace_program_edit_view), and "Сгенерировать занятия" always
# goes through a preview first (group_workspace_generate_preview_view) —
# no detour through the generic GroupTeacher admin form for simple changes.

def _program_status(card: dict) -> tuple[str, str]:
    """(badge css class, label) — the one status a program row shows."""
    if not card["obj"].is_active:
        return "ok-badge-muted", "Приостановлена"
    if not card["slots"]:
        return "ok-badge-danger", "Нет расписания"
    live_lessons = card["lesson_count"] - card["cancelled_count"]
    if card["plan_total"] and card["completed_count"] >= card["plan_total"]:
        return "ok-badge-info", "Программа пройдена"
    if card["plan_total"] and live_lessons < card["plan_total"]:
        return "ok-badge-warning", "Не все занятия созданы"
    return "ok-badge-success", "Идёт по расписанию"


def _teaching_program_cards(group: Group) -> list[dict]:
    """One dict per GroupTeacher (Teaching Program) of `group` — shared by
    the Programs tab (table), the Teachers tab (roster grouped by trainer)
    and the edit drawer. Lesson counters come from one grouped query for
    the whole group, not several queries per program."""
    today = timezone.localdate()
    programs = list(
        group.teachers.select_related("teacher__user", "subject")
        .prefetch_related("schedules__room")
        .annotate(_plan_count=Count("lesson_plans", distinct=True))
        .order_by("-is_active", "subject__name", "id")
    )
    lesson_counts = {
        row["group_teacher_id"]: row
        for row in Lesson.objects.filter(group=group, group_teacher__isnull=False)
        .values("group_teacher_id")
        .annotate(
            total=Count("id"),
            completed=Count("id", filter=Q(status=Lesson.Status.COMPLETED)),
            cancelled=Count("id", filter=Q(status=Lesson.Status.CANCELLED)),
            upcoming=Count("id", filter=Q(status=Lesson.Status.SCHEDULED, date__gte=today)),
            next_date=Min("date", filter=Q(status=Lesson.Status.SCHEDULED, date__gte=today)),
        )
    }

    planned = planned_lessons_by_program(group)
    course_plan_url = f"{reverse('admin:academy_courselessonplan_changelist')}?course__id__exact={group.course_id}"
    cards = []
    for gt in programs:
        active_slots = sorted(
            (s for s in gt.schedules.all() if s.is_active),
            key=lambda s: (WEEKDAY_CODES.index(s.day_of_week), s.start_time),
        )
        counts = lesson_counts.get(gt.pk, {})
        lesson_count = counts.get("total", 0)
        completed = counts.get("completed", 0)
        plan_total = planned.get(gt.pk, 0)
        has_individual_plan = gt._plan_count > 0
        admin_edit_url = reverse("admin:academy_groupteacher_change", args=[gt.pk])
        card = {
            "obj": gt,
            "slots": [
                {
                    "obj": s,
                    "day_label": WEEKDAY_SHORT_LABELS.get(s.day_of_week, s.day_of_week),
                    "time_label": f"{s.start_time:%H:%M}–{s.end_time:%H:%M}",
                    "room": s.room.name if s.room_id else "без кабинета",
                }
                for s in active_slots
            ],
            "lesson_count": lesson_count,
            "completed_count": completed,
            "cancelled_count": counts.get("cancelled", 0),
            "upcoming_count": counts.get("upcoming", 0),
            "next_lesson_date": counts.get("next_date"),
            "plan_count": gt._plan_count,
            "has_individual_plan": has_individual_plan,
            # "Lessons created / lessons this program is responsible
            # for": its subject's share of the shared course plan (e.g.
            # 48 of 144) or its own individual plan — see
            # services.lesson_generator.planned_lessons_by_program.
            "plan_filled": lesson_count,
            "plan_total": plan_total,
            "progress": min(round(100 * completed / plan_total), 100) if plan_total else None,
            "workspace_url": reverse("admin:academy_groupteacher_workspace", args=[gt.pk]),
            "edit_url": reverse("admin:academy_group_workspace_programs_edit", args=[group.pk, gt.pk]),
            "admin_edit_url": admin_edit_url,
            "lesson_plan_url": admin_edit_url if has_individual_plan else course_plan_url,
            "lessons_url": f"{reverse('admin:academy_group_workspace_lessons', args=[group.pk])}?program={gt.pk}",
            "analytics_url": f"{reverse('admin:academy_group_workspace_analytics', args=[group.pk])}?program={gt.pk}",
            "schedule_url": reverse("admin:academy_group_workspace_programs_edit", args=[group.pk, gt.pk]) + "#schedule",
            "generate_url": (
                f"{reverse('admin:academy_group_workspace_generate_preview', args=[group.pk])}?program={gt.pk}"
            ),
            "remove_url": reverse("admin:academy_group_workspace_teachers_remove", args=[group.pk, gt.pk]),
        }
        card["status_class"], card["status_label"] = _program_status(card)
        cards.append(card)
    return cards


def _unassigned_subject_rows(group: Group) -> list[dict]:
    """Course subjects whose plan rows no program will teach — shown as
    rows of their own so the gap is visible before generating."""
    add_program_url = reverse("admin:academy_group_workspace_programs_add", args=[group.pk])
    return [
        {"row": row, "assign_url": f"{add_program_url}?subject={row.subject_id}"}
        for row in subject_assignment_overview(group)
        if row.status == STATUS_UNASSIGNED
    ]


class EditProgramForm(forms.Form):
    """The drawer's form: trainer, subject and status of one program."""

    STATUS_CHOICES = [("active", "Активна"), ("inactive", "Приостановлена")]

    teacher = forms.ModelChoiceField(
        queryset=Teacher.objects.none(), label="Преподаватель", widget=forms.Select(attrs={"class": "ok-input"}),
    )
    subject = forms.ModelChoiceField(
        queryset=Subject.objects.none(), required=False, label="Предмет",
        widget=forms.Select(attrs={"class": "ok-input"}),
    )
    status = forms.ChoiceField(
        choices=STATUS_CHOICES, label="Статус программы", widget=forms.Select(attrs={"class": "ok-input"}),
    )
    reassign_future_lessons = forms.BooleanField(
        required=False, initial=True, label="Передать новому преподавателю будущие запланированные занятия",
    )

    def __init__(self, *args, group_teacher: GroupTeacher, has_lessons: bool, **kwargs):
        kwargs.setdefault(
            "initial",
            {
                "teacher": group_teacher.teacher_id,
                "subject": group_teacher.subject_id,
                "status": "active" if group_teacher.is_active else "inactive",
                "reassign_future_lessons": True,
            },
        )
        super().__init__(*args, **kwargs)
        self.group_teacher = group_teacher
        # The current trainer stays selectable even if deactivated since —
        # validation then explains why it can't be kept.
        self.fields["teacher"].queryset = Teacher.objects.filter(
            Q(is_active=True) | Q(pk=group_teacher.teacher_id)
        ).select_related("user")
        self.fields["subject"].queryset = group_teacher.group.course.subjects.filter(
            Q(is_active=True) | Q(pk=group_teacher.subject_id)
        )
        if has_lessons:
            # A lesson's subject is copied from its plan row — see
            # services.program_editing. Disabled fields keep their initial
            # value whatever the POST says.
            self.fields["subject"].disabled = True
            self.fields["subject"].help_text = "У программы уже есть занятия — предмет изменить нельзя."

    def clean_subject(self):
        subject = self.cleaned_data.get("subject")
        if subject is None and self.group_teacher.subject_id is not None:
            raise forms.ValidationError("Выберите предмет.")
        return subject


class ProgramScheduleForm(forms.Form):
    """Add weekly slots to one program from its drawer — several weekdays
    at the same time in one go."""

    day_of_week = forms.MultipleChoiceField(
        choices=GroupSchedule.DAY_CHOICES, label="Дни недели", widget=forms.CheckboxSelectMultiple,
    )
    start_time = forms.TimeField(
        label="Начало", widget=forms.TimeInput(attrs={"class": "ok-input", "type": "time"})
    )
    end_time = forms.TimeField(
        label="Окончание", widget=forms.TimeInput(attrs={"class": "ok-input", "type": "time"})
    )
    room = forms.ModelChoiceField(
        queryset=Room.objects.filter(is_active=True), required=False, label="Кабинет",
        widget=forms.Select(attrs={"class": "ok-input"}),
    )

    def clean(self):
        cleaned = super().clean()
        start, end = cleaned.get("start_time"), cleaned.get("end_time")
        if start and end and end <= start:
            self.add_error("end_time", "Время окончания должно быть позже времени начала.")
        return cleaned


def _add_validation_errors(form: forms.Form, exc: DjangoValidationError) -> None:
    if hasattr(exc, "error_dict"):
        for field_name, errors in exc.message_dict.items():
            target = field_name if field_name in form.fields else None
            for message in errors:
                form.add_error(target, message)
    else:
        for message in exc.messages:
            form.add_error(None, message)


def _render_programs(request, group: Group, *, drawer: dict | None = None, preview: dict | None = None,
                     status: int = 200):
    context = _workspace_context(request, group, "programs")
    cards = _teaching_program_cards(group)
    context.update(
        {
            "title": f"{group.name} — Программы",
            "cards": cards,
            "unassigned_subjects": _unassigned_subject_rows(group),
            "active_programs_count": sum(1 for card in cards if card["obj"].is_active),
            "drawer": drawer,
            "preview": preview,
        }
    )
    return render(request, "admin/academy/group/workspace/programs.html", context, status=status)


def group_workspace_programs_view(request, group_id):
    _require_admin(request)
    group = get_object_or_404(Group.objects.select_related("course"), pk=group_id)
    return _render_programs(request, group)


def _drawer_context(group: Group, group_teacher: GroupTeacher, *, form=None, schedule_form=None) -> dict:
    has_lessons = Lesson.objects.filter(group_teacher=group_teacher).exists()
    card = next(c for c in _teaching_program_cards(group) if c["obj"].pk == group_teacher.pk)
    return {
        "program": group_teacher,
        "card": card,
        "form": form or EditProgramForm(group_teacher=group_teacher, has_lessons=has_lessons),
        "schedule_form": schedule_form or ProgramScheduleForm(),
        "future_lessons_count": future_lessons(group_teacher).count(),
        "action_url": reverse("admin:academy_group_workspace_programs_edit", args=[group.pk, group_teacher.pk]),
        "schedule_add_url": reverse(
            "admin:academy_group_workspace_programs_schedule_add", args=[group.pk, group_teacher.pk]
        ),
        "slots": [
            {
                "obj": slot,
                "label": f"{WEEKDAY_SHORT_LABELS.get(slot.day_of_week, slot.day_of_week)} "
                         f"{slot.start_time:%H:%M}–{slot.end_time:%H:%M}",
                "room": slot.room.name if slot.room_id else "без кабинета",
                "remove_url": reverse("admin:academy_group_workspace_schedule_remove", args=[group.pk, slot.pk]),
            }
            for slot in sorted(
                group_teacher.schedules.select_related("room"),
                key=lambda s: (WEEKDAY_CODES.index(s.day_of_week), s.start_time),
            )
        ],
        "open_schedule": schedule_form is not None and schedule_form.is_bound,
    }


def group_workspace_program_edit_view(request, group_id, group_teacher_id):
    """Right-side drawer over the Programs tab: GET opens it for one
    program, POST saves trainer/subject/status through
    services.program_editing (slots and future lessons follow the trainer),
    re-rendering the drawer with field errors on failure."""
    _require_admin(request)
    group = get_object_or_404(Group.objects.select_related("course"), pk=group_id)
    group_teacher = get_object_or_404(
        GroupTeacher.objects.select_related("teacher__user", "subject", "group__course"), pk=group_teacher_id,
        group=group,
    )

    if request.method == "POST":
        has_lessons = Lesson.objects.filter(group_teacher=group_teacher).exists()
        form = EditProgramForm(request.POST, group_teacher=group_teacher, has_lessons=has_lessons)
        if form.is_valid():
            try:
                change = update_teaching_program(
                    group_teacher,
                    teacher=form.cleaned_data["teacher"],
                    subject=form.cleaned_data["subject"],
                    is_active=form.cleaned_data["status"] == "active",
                    reassign_future_lessons=form.cleaned_data["reassign_future_lessons"],
                )
            except DjangoValidationError as exc:
                _add_validation_errors(form, exc)
            else:
                if not change.changed:
                    messages.info(request, "Изменений нет — программа осталась прежней.")
                else:
                    parts = []
                    if change.teacher_changed:
                        parts.append(f"преподаватель — {form.cleaned_data['teacher']}")
                        if change.lessons_reassigned:
                            parts.append(f"передано будущих занятий: {change.lessons_reassigned}")
                    if change.subject_changed:
                        subject = form.cleaned_data["subject"]
                        parts.append(f"предмет — {subject.name if subject else 'без предмета'}")
                    if change.status_changed:
                        parts.append("статус — " + dict(EditProgramForm.STATUS_CHOICES)[form.cleaned_data["status"]])
                    messages.success(request, "Программа сохранена: " + "; ".join(parts) + ".")
                return redirect(_safe_next(request, reverse("admin:academy_group_workspace_programs", args=[group.pk])))
        group_teacher.refresh_from_db()
        drawer = _drawer_context(group, group_teacher, form=form)
        return _render_programs(request, group, drawer=drawer)

    return _render_programs(request, group, drawer=_drawer_context(group, group_teacher))


@require_POST
def group_workspace_program_schedule_add_view(request, group_id, group_teacher_id):
    """Add weekly slots (one per selected weekday) to a program from its
    drawer; every day is validated (teacher/room/group conflicts) before
    any is saved."""
    _require_admin(request)
    group = get_object_or_404(Group.objects.select_related("course"), pk=group_id)
    group_teacher = get_object_or_404(
        GroupTeacher.objects.select_related("teacher__user", "subject"), pk=group_teacher_id, group=group,
    )
    form = ProgramScheduleForm(request.POST)
    if form.is_valid():
        try:
            slots = build_schedule_slots(
                group=group, teacher=group_teacher.teacher, subject=group_teacher.subject,
                days=form.cleaned_data["day_of_week"], start_time=form.cleaned_data["start_time"],
                end_time=form.cleaned_data["end_time"], room=form.cleaned_data.get("room"),
            )
        except DjangoValidationError as exc:
            _add_validation_errors(form, exc)
        else:
            with transaction.atomic():
                for slot in slots:
                    slot.save()
            messages.success(
                request,
                f"Добавлено слотов расписания: {len(slots)}. Когда расписание будет готово, "
                "нажмите «Сгенерировать занятия».",
            )
            return redirect(
                reverse("admin:academy_group_workspace_programs_edit", args=[group.pk, group_teacher.pk]) + "#schedule"
            )
    drawer = _drawer_context(group, group_teacher, schedule_form=form)
    return _render_programs(request, group, drawer=drawer)


# -- Teachers ---------------------------------------------------------------

def group_workspace_teachers_view(request, group_id):
    """People view of the same programs: one card per trainer with every
    subject they teach in this group, so "who teaches what, how much" is
    answered at a glance. Editing still opens the program's drawer on the
    Programs tab."""
    _require_admin(request)
    group = get_object_or_404(Group.objects.select_related("course"), pk=group_id)

    cards = _teaching_program_cards(group)
    by_teacher: dict[int, dict] = {}
    for card in cards:
        teacher = card["obj"].teacher
        entry = by_teacher.setdefault(
            teacher.pk,
            {"teacher": teacher, "programs": [], "weekly_slots": 0, "upcoming": 0, "completed": 0},
        )
        entry["programs"].append(card)
        if card["obj"].is_active:
            entry["weekly_slots"] += len(card["slots"])
        entry["upcoming"] += card["upcoming_count"]
        entry["completed"] += card["completed_count"]

    context = _workspace_context(request, group, "teachers")
    context.update(
        {
            "title": f"{group.name} — Преподаватели",
            "cards": cards,
            "teachers": sorted(by_teacher.values(), key=lambda entry: str(entry["teacher"])),
            "unassigned_subjects": _unassigned_subject_rows(group),
        }
    )
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
            existing = GroupTeacher.objects.filter(group=group, teacher=teacher, subject=subject).first()
            if existing is not None:
                messages.warning(request, f"«{teacher}» уже преподаёт «{subject.name}» в этой группе.")
                return redirect(reverse("admin:academy_group_workspace_teachers", args=[group.pk]))
            group_teacher = GroupTeacher(group=group, teacher=teacher, subject=subject)
            try:
                group_teacher.full_clean()
            except DjangoValidationError as exc:
                for message in (exc.messages if hasattr(exc, "messages") else [str(exc)]):
                    form.add_error(None, message)
            else:
                group_teacher.save()
                messages.success(
                    request,
                    f"«{teacher}» назначен на предмет «{subject.name}». Чтобы по предмету создавались "
                    "занятия, добавьте этой программе расписание, затем нажмите «Сгенерировать занятия».",
                )
                return redirect(reverse("admin:academy_group_workspace_teachers", args=[group.pk]))
    else:
        initial = {}
        subject_id = request.GET.get("subject")
        if subject_id and subject_id.isdigit():
            initial["subject"] = subject_id
        form = AddTeacherAssignmentForm(group=group, initial=initial)

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
    return redirect(_safe_next(request, reverse("admin:academy_group_workspace_teachers", args=[group.pk])))


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
            try:
                new_slots = build_schedule_slots(
                    group=group, teacher=teacher, subject=subject, days=days,
                    start_time=start_time, end_time=end_time, room=room,
                )
            except DjangoValidationError as exc:
                for message in exc.messages:
                    messages.error(request, message)
            else:
                with transaction.atomic():
                    for slot in new_slots:
                        slot.save()
                messages.success(
                    request,
                    f"Учебная программа добавлена: {teacher} — {subject.name} "
                    f"({len(new_slots)} слот(ов) расписания). Когда расписание группы будет "
                    "полностью настроено, нажмите «Сгенерировать занятия».",
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
        initial = {}
        subject_id = request.GET.get("subject")
        if subject_id and subject_id.isdigit():
            initial["subject"] = subject_id
        form = AddTeachingProgramForm(group=group, initial=initial)

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
            "edit_program_url": (
                reverse("admin:academy_groupteacher_change", args=[slot.group_teacher_id])
                if slot.group_teacher_id
                else None
            ),
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
                messages.success(
                    request,
                    "Слот расписания добавлен. Когда расписание группы будет полностью настроено, "
                    "нажмите «Сгенерировать занятия».",
                )
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
    messages.success(request, "Слот расписания удалён. Уже созданные занятия не изменились.")
    return redirect(_safe_next(request, reverse("admin:academy_group_workspace_schedule", args=[group.pk])))


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

def _bar(value: float | None) -> dict:
    """Width/label for a server-rendered horizontal bar (0–100%). `width`
    is a pre-formatted CSS number: a float rendered by the template would
    be localized ("82,1") and silently break the style."""
    if value is None:
        return {"width": "0", "label": "—", "empty": True}
    width = max(0.0, min(float(value), 100.0))
    return {"width": f"{width:.1f}", "label": f"{number_format(value)}%", "empty": False}


def group_workspace_analytics_view(request, group_id):
    """Group Analytics: every Teaching Program of the group side by side
    plus a group-wide summary, filtered by program/teacher/subject/period/
    lesson status — see services.group_analytics for every definition."""
    _require_admin(request)
    group = get_object_or_404(Group.objects.select_related("course"), pk=group_id)
    filters = GroupAnalyticsFilters.from_query(request.GET)
    analytics = get_group_analytics(group, filters)
    summary = analytics.summary

    rows = []
    for row in analytics.rows:
        rows.append(
            {
                "row": row,
                "attendance_bar": _bar(row.attendance_rate),
                "homework_bar": _bar(row.homework_rate),
                "progress_bar": _bar(row.progress),
                # Planned vs conducted: the track is the planned lessons,
                # the fill the conducted share of them.
                "completed_width": f"{100 * row.completed / row.lessons:.1f}" if row.lessons else "0",
                "lessons_url": (
                    f"{reverse('admin:academy_group_workspace_lessons', args=[group.pk])}?program={row.group_teacher_id}"
                    if row.group_teacher_id else None
                ),
                "edit_url": (
                    reverse("admin:academy_group_workspace_programs_edit", args=[group.pk, row.group_teacher_id])
                    if row.group_teacher_id else None
                ),
            }
        )

    programs = list(group.teachers.select_related("teacher__user", "subject").order_by("subject__name", "id"))
    context = _workspace_context(request, group, "analytics")
    context.update(
        {
            "title": f"{group.name} — Аналитика",
            "analytics": analytics,
            "summary": summary,
            "rows": rows,
            "has_filters": bool(filters.as_query()),
            "summary_bars": {
                "attendance": _bar(summary["attendance_rate"]),
                "homework": _bar(summary["homework_rate"]),
                "progress": _bar(summary["progress"]),
            },
            "filter_options": {
                "programs": programs,
                "teachers": sorted({gt.teacher for gt in programs}, key=str),
                "subjects": sorted({gt.subject for gt in programs if gt.subject_id}, key=lambda s: s.name),
                "periods": PERIOD_CHOICES,
                "statuses": Lesson.Status.choices,
            },
            "selected": filters,
            # Kept for the tab's long-standing context contract.
            "stats": {
                "students_count": summary["students"],
                "programs_count": group.teachers.filter(is_active=True).count(),
                "completed_lessons": summary["completed"],
                "cancelled_lessons": summary["cancelled"],
                "upcoming_lessons": summary["upcoming"],
                "attendance_rate": summary["attendance_rate"],
                "homework_completion_rate": summary["homework_rate"],
            },
        }
    )
    return render(request, "admin/academy/group/workspace/analytics.html", context)


# -- Generate lessons -----------------------------------------------------

def group_workspace_generate_preview_view(request, group_id):
    """Step 1 of «Сгенерировать занятия»: exactly what the generator would
    do right now (per program: plan, existing, to be created and when;
    what is skipped and why; which orphan lessons would be deleted) — by
    running it in a rolled-back transaction, see
    services.lesson_generator.preview_generation. Nothing is written; the
    confirmation form posts to group_workspace_generate_lessons_view."""
    _require_admin(request)
    group = get_object_or_404(Group.objects.select_related("course"), pk=group_id)
    preview = preview_generation(group)
    focus = request.GET.get("program")
    return _render_programs(
        request, group,
        preview={
            "data": preview,
            "focus_program_id": int(focus) if focus and focus.isdigit() else None,
            "next_url": reverse("admin:academy_group_workspace_programs", args=[group.pk]),
        },
    )


@require_POST
def group_workspace_generate_lessons_view(request, group_id):
    """Step 2: generate. Idempotent — only missing lessons are created,
    existing ones are never modified. Untouched orphan lessons (see
    find_orphan_lessons) are deleted and recreated only when the admin
    ticked the confirmation in the preview (`confirm_cleanup`); otherwise
    they are kept and reported."""
    _require_admin(request)
    group = get_object_or_404(Group, pk=group_id)
    report = generate_lessons_for_group_with_report(group, cleanup_orphans=bool(request.POST.get("confirm_cleanup")))
    add_generation_messages(request, report)

    return redirect(_safe_next(request, reverse("admin:academy_group_workspace", args=[group.pk])))


# ---------------------------------------------------------------------------
# Read-only monitoring center — Посещаемость / Домашние задания / Результаты
# ДЗ. Admin only ever *watches* this data here (search/filter/drill down/
# jump to the related Group/Student/Lesson/Teacher); a Teacher is the one
# who actually records it, through their own lesson/homework-checking
# screens (services.attendance_service.bulk_mark_attendance,
# services.homework_service.bulk_upsert_homework_results) — never through
# Django admin. AttendanceAdmin/HomeworkAdmin/HomeworkResultAdmin (see
# admin.py) replace both their changelist_view and change_view with the six
# views below and lock has_add/change/delete_permission to False, so the
# read-only behaviour holds at the permission layer, not just in the UI.
# ---------------------------------------------------------------------------

def _effective_teacher_q(prefix: str, teacher_id) -> "Q":
    """Q matching the Lesson `teacher_id` actually gives, reached through
    `prefix` (e.g. "lesson", "homework__lesson", or "" for a queryset of
    Lesson itself) — the same effective-teacher rule as
    Lesson.effective_teacher / LessonQuerySet.for_teacher: the lesson's own
    explicit teacher when the generator set one, else its GroupTeacher's
    own teacher.
    """
    def field(name: str) -> str:
        return f"{prefix}__{name}" if prefix else name

    return Q(**{field("teacher_id"): teacher_id}) | Q(
        **{field("teacher__isnull"): True, field("group_teacher__teacher_id"): teacher_id}
    )


def attendance_monitor_view(request):
    _require_admin(request)

    search = (request.GET.get("q") or "").strip()
    group_id = request.GET.get("group") or ""
    student_id = request.GET.get("student") or ""
    teacher_id = request.GET.get("teacher") or ""
    subject_id = request.GET.get("subject") or ""
    course_id = request.GET.get("course") or ""
    status_filter = request.GET.get("status") or ""
    date_from = request.GET.get("date_from") or ""
    date_to = request.GET.get("date_to") or ""
    group_teacher_id = request.GET.get("group_teacher") or ""
    lesson_id = request.GET.get("lesson") or ""

    records_qs = Attendance.objects.select_related(
        "student",
        "lesson",
        "lesson__group",
        "lesson__group__course",
        "lesson__subject",
        "lesson__room",
        "lesson__teacher__user",
        "lesson__group_teacher__teacher__user",
        "lesson__group_teacher__subject",
    )

    if search:
        records_qs = records_qs.filter(
            Q(student__first_name__icontains=search)
            | Q(student__last_name__icontains=search)
            | Q(lesson__group__name__icontains=search)
            | Q(lesson__teacher__user__first_name__icontains=search)
            | Q(lesson__teacher__user__last_name__icontains=search)
            | Q(lesson__group_teacher__teacher__user__first_name__icontains=search)
            | Q(lesson__group_teacher__teacher__user__last_name__icontains=search)
        )
    if group_id:
        records_qs = records_qs.filter(lesson__group_id=group_id)
    if student_id:
        records_qs = records_qs.filter(student_id=student_id)
    if teacher_id:
        records_qs = records_qs.filter(_effective_teacher_q("lesson", teacher_id))
    if subject_id:
        records_qs = records_qs.filter(lesson__subject_id=subject_id)
    if course_id:
        records_qs = records_qs.filter(lesson__group__course_id=course_id)
    if status_filter:
        records_qs = records_qs.filter(status=status_filter)
    if group_teacher_id:
        records_qs = records_qs.filter(lesson__group_teacher_id=group_teacher_id)
    if lesson_id:
        records_qs = records_qs.filter(lesson_id=lesson_id)
    parsed = _parse_date(date_from, None)
    if parsed:
        records_qs = records_qs.filter(lesson__date__gte=parsed)
    parsed = _parse_date(date_to, None)
    if parsed:
        records_qs = records_qs.filter(lesson__date__lte=parsed)

    records_qs = records_qs.order_by("-lesson__date", "-lesson__start_time")

    total = records_qs.count()
    present = records_qs.filter(status=Attendance.Status.PRESENT).count()
    absent = records_qs.filter(status=Attendance.Status.ABSENT).count()
    late = records_qs.filter(status=Attendance.Status.LATE).count()
    excused = records_qs.filter(status=Attendance.Status.EXCUSED).count()
    rate = round(100 * (present + late) / total, 1) if total else None

    paginator = Paginator(records_qs, 25)
    page_obj = paginator.get_page(request.GET.get("page"))

    context = {
        **admin.site.each_context(request),
        "title": "Посещаемость",
        "subtitle": "Просмотр посещаемости студентов по группам, занятиям и преподавателям.",
        "records": page_obj,
        "kpi": {"total": total, "present": present, "absent": absent, "late": late, "excused": excused, "rate": rate},
        "groups": Group.objects.order_by("name"),
        "students": Student.objects.filter(is_active=True).select_related("group").order_by("last_name", "first_name"),
        "teachers": Teacher.objects.filter(is_active=True).select_related("user").order_by("user__first_name"),
        "subjects": Subject.objects.filter(is_active=True).order_by("name"),
        "courses": Course.objects.order_by("name"),
        "status_choices": Attendance.Status.choices,
        "selected": {
            "q": search, "group": group_id, "student": student_id, "teacher": teacher_id,
            "subject": subject_id, "course": course_id, "status": status_filter,
            "date_from": date_from, "date_to": date_to,
        },
        "reset_url": reverse("admin:academy_attendance_changelist"),
    }
    return render(request, "admin/academy/attendance/change_list.html", context)


def attendance_detail_view(request, object_id):
    _require_admin(request)
    record = get_object_or_404(
        Attendance.objects.select_related(
            "student",
            "student__group",
            "lesson",
            "lesson__group",
            "lesson__group__course",
            "lesson__subject",
            "lesson__room",
            "lesson__teacher__user",
            "lesson__group_teacher__teacher__user",
            "lesson__group_teacher__subject",
        ),
        pk=object_id,
    )
    lesson = record.lesson
    group = lesson.group
    subject = lesson.subject or (lesson.group_teacher.subject if lesson.group_teacher_id else None)
    teacher = lesson.effective_teacher

    context = {
        **admin.site.each_context(request),
        "title": "Посещаемость",
        "record": record,
        "student": record.student,
        "lesson": lesson,
        "group": group,
        "subject": subject,
        "teacher": teacher,
        "changelist_url": reverse("admin:academy_attendance_changelist"),
        "student_url": reverse("admin:academy_student_detail", args=[record.student_id]),
        "group_url": reverse("admin:academy_group_workspace", args=[group.pk]),
        "lesson_url": reverse("admin:academy_lesson_change", args=[lesson.pk]),
        "teacher_url": reverse("admin:users_teacher_change", args=[teacher.pk]) if teacher else None,
    }
    return render(request, "admin/academy/attendance/detail.html", context)


def homework_monitor_view(request):
    _require_admin(request)
    today = timezone.localdate()

    search = (request.GET.get("q") or "").strip()
    group_id = request.GET.get("group") or ""
    subject_id = request.GET.get("subject") or ""
    teacher_id = request.GET.get("teacher") or ""
    course_id = request.GET.get("course") or ""
    date_from = request.GET.get("date_from") or ""
    date_to = request.GET.get("date_to") or ""
    deadline_from = request.GET.get("deadline_from") or ""
    deadline_to = request.GET.get("deadline_to") or ""
    group_teacher_id = request.GET.get("group_teacher") or ""

    homeworks_qs = (
        Homework.objects.select_related(
            "lesson",
            "lesson__group",
            "lesson__group__course",
            "lesson__subject",
            "lesson__teacher__user",
            "lesson__group_teacher__teacher__user",
            "lesson__group_teacher__subject",
        )
        .annotate(
            results_total=Count("results", distinct=True),
            results_checked=Count(
                "results", filter=Q(results__status=HomeworkResult.Status.CHECKED), distinct=True
            ),
            results_submitted=Count(
                "results",
                filter=Q(
                    results__status__in=[
                        HomeworkResult.Status.SUBMITTED,
                        HomeworkResult.Status.LATE,
                        HomeworkResult.Status.CHECKED,
                    ]
                ),
                distinct=True,
            ),
            students_total=Count(
                "lesson__group__students",
                filter=Q(lesson__group__students__is_active=True),
                distinct=True,
            ),
        )
    )

    if search:
        homeworks_qs = homeworks_qs.filter(
            Q(title__icontains=search)
            | Q(description__icontains=search)
            | Q(lesson__group__name__icontains=search)
            | Q(lesson__subject__name__icontains=search)
            | Q(lesson__teacher__user__first_name__icontains=search)
            | Q(lesson__teacher__user__last_name__icontains=search)
            | Q(lesson__group_teacher__teacher__user__first_name__icontains=search)
            | Q(lesson__group_teacher__teacher__user__last_name__icontains=search)
        )
    if group_id:
        homeworks_qs = homeworks_qs.filter(lesson__group_id=group_id)
    if subject_id:
        homeworks_qs = homeworks_qs.filter(lesson__subject_id=subject_id)
    if teacher_id:
        homeworks_qs = homeworks_qs.filter(_effective_teacher_q("lesson", teacher_id))
    if course_id:
        homeworks_qs = homeworks_qs.filter(lesson__group__course_id=course_id)
    if group_teacher_id:
        homeworks_qs = homeworks_qs.filter(lesson__group_teacher_id=group_teacher_id)
    parsed = _parse_date(date_from, None)
    if parsed:
        homeworks_qs = homeworks_qs.filter(lesson__date__gte=parsed)
    parsed = _parse_date(date_to, None)
    if parsed:
        homeworks_qs = homeworks_qs.filter(lesson__date__lte=parsed)
    parsed = _parse_date(deadline_from, None)
    if parsed:
        homeworks_qs = homeworks_qs.filter(deadline__gte=parsed)
    parsed = _parse_date(deadline_to, None)
    if parsed:
        homeworks_qs = homeworks_qs.filter(deadline__lte=parsed)

    homeworks = list(homeworks_qs.order_by("-created_at"))

    def _status_of(hw) -> dict:
        if hw.results_total and hw.results_checked == hw.results_total:
            return {"label": "Проверено", "css": "ok-badge-success"}
        if hw.deadline and hw.deadline < today:
            return {"label": "Просрочено", "css": "ok-badge-danger"}
        if hw.deadline == today:
            return {"label": "Дедлайн сегодня", "css": "ok-badge-warning"}
        if hw.results_submitted:
            return {"label": "В процессе", "css": "ok-badge-warning"}
        return {"label": "Новое", "css": "ok-badge-muted"}

    rows = []
    for hw in homeworks:
        status_info = _status_of(hw)
        rows.append(
            {
                "obj": hw,
                "group": hw.lesson.group,
                "subject": hw.lesson.subject,
                "teacher": hw.lesson.effective_teacher,
                "students_total": hw.students_total,
                "submitted": hw.results_submitted,
                "checked": hw.results_checked,
                "status_label": status_info["label"],
                "status_css": status_info["css"],
                "detail_url": reverse("admin:academy_homework_change", args=[hw.pk]),
            }
        )

    total = len(homeworks)
    active_deadlines = sum(1 for hw in homeworks if hw.deadline and hw.deadline >= today)
    overdue = sum(1 for hw in homeworks if hw.deadline and hw.deadline < today)
    checked_complete = sum(1 for hw in homeworks if hw.results_total and hw.results_checked == hw.results_total)
    completion_rates = [100 * hw.results_checked / hw.results_total for hw in homeworks if hw.results_total]
    avg_completion = round(sum(completion_rates) / len(completion_rates), 1) if completion_rates else None
    students_count = (
        HomeworkResult.objects.filter(homework_id__in=[hw.pk for hw in homeworks]).values("student_id").distinct().count()
        if homeworks
        else 0
    )

    paginator = Paginator(rows, 20)
    page_obj = paginator.get_page(request.GET.get("page"))

    context = {
        **admin.site.each_context(request),
        "title": "Домашние задания",
        "subtitle": "Просмотр домашних заданий, связанных с занятиями и учебными программами.",
        "rows": page_obj,
        "kpi": {
            "total": total,
            "active_deadlines": active_deadlines,
            "overdue": overdue,
            "checked_complete": checked_complete,
            "avg_completion": avg_completion,
            "students_count": students_count,
        },
        "groups": Group.objects.order_by("name"),
        "subjects": Subject.objects.filter(is_active=True).order_by("name"),
        "teachers": Teacher.objects.filter(is_active=True).select_related("user").order_by("user__first_name"),
        "courses": Course.objects.order_by("name"),
        "selected": {
            "q": search, "group": group_id, "subject": subject_id, "teacher": teacher_id, "course": course_id,
            "date_from": date_from, "date_to": date_to, "deadline_from": deadline_from, "deadline_to": deadline_to,
        },
        "reset_url": reverse("admin:academy_homework_changelist"),
    }
    return render(request, "admin/academy/homework/change_list.html", context)


def homework_detail_view(request, object_id):
    _require_admin(request)
    homework = get_object_or_404(
        Homework.objects.select_related(
            "lesson",
            "lesson__group",
            "lesson__group__course",
            "lesson__subject",
            "lesson__teacher__user",
            "lesson__group_teacher__teacher__user",
            "lesson__group_teacher__subject",
        ),
        pk=object_id,
    )
    lesson = homework.lesson
    group = lesson.group
    subject = lesson.subject or (lesson.group_teacher.subject if lesson.group_teacher_id else None)
    teacher = lesson.effective_teacher
    today = timezone.localdate()

    students = list(group.students.filter(is_active=True).order_by("last_name", "first_name"))
    results_by_student = {
        r.student_id: r for r in HomeworkResult.objects.filter(homework=homework).select_related("student")
    }

    submission_rows = []
    submitted_count = 0
    checked_count = 0
    scores = []
    for student in students:
        result = results_by_student.get(student.id)
        status_value = result.status if result else HomeworkResult.Status.NOT_SUBMITTED
        if status_value in (
            HomeworkResult.Status.SUBMITTED,
            HomeworkResult.Status.LATE,
            HomeworkResult.Status.CHECKED,
        ):
            submitted_count += 1
        if status_value == HomeworkResult.Status.CHECKED:
            checked_count += 1
        if result and result.score is not None:
            scores.append(result.score)
        submission_rows.append(
            {
                "student": student,
                "student_url": reverse("admin:academy_student_detail", args=[student.pk]),
                "status_display": result.get_status_display() if result else HomeworkResult.Status.NOT_SUBMITTED.label,
                "status_value": status_value,
                "score": result.score if result else None,
                "comment": result.comment if result else "",
                "submitted_at": result.submitted_at if result else None,
                "checked_at": result.checked_at if result else None,
            }
        )

    total_students = len(students)
    not_submitted = max(total_students - submitted_count, 0)
    avg_score = round(sum(scores) / len(scores), 1) if scores else None

    if homework.deadline and homework.deadline < today:
        deadline_badge = {"label": f"Просрочено ({homework.deadline:%d.%m.%Y})", "css": "ok-badge-danger"}
    elif homework.deadline == today:
        deadline_badge = {"label": "Дедлайн сегодня", "css": "ok-badge-warning"}
    elif homework.deadline:
        deadline_badge = {"label": f"До {homework.deadline:%d.%m.%Y}", "css": "ok-badge-muted"}
    else:
        deadline_badge = {"label": "Без срока", "css": "ok-badge-muted"}

    context = {
        **admin.site.each_context(request),
        "title": "Домашние задания",
        "homework": homework,
        "lesson": lesson,
        "group": group,
        "subject": subject,
        "teacher": teacher,
        "deadline_badge": deadline_badge,
        "kpi": {
            "total_students": total_students,
            "submitted": submitted_count,
            "not_submitted": not_submitted,
            "checked": checked_count,
            "avg_score": avg_score,
        },
        "submission_rows": submission_rows,
        "changelist_url": reverse("admin:academy_homework_changelist"),
        "group_url": reverse("admin:academy_group_workspace", args=[group.pk]),
        "lesson_url": reverse("admin:academy_lesson_change", args=[lesson.pk]),
        "teacher_url": reverse("admin:users_teacher_change", args=[teacher.pk]) if teacher else None,
    }
    return render(request, "admin/academy/homework/detail.html", context)


def homeworkresult_monitor_view(request):
    _require_admin(request)

    search = (request.GET.get("q") or "").strip()
    group_id = request.GET.get("group") or ""
    student_id = request.GET.get("student") or ""
    teacher_id = request.GET.get("teacher") or ""
    subject_id = request.GET.get("subject") or ""
    homework_id = request.GET.get("homework") or ""
    status_filter = request.GET.get("status") or ""
    score_min = request.GET.get("score_min") or ""
    score_max = request.GET.get("score_max") or ""
    date_from = request.GET.get("date_from") or ""
    date_to = request.GET.get("date_to") or ""
    group_teacher_id = request.GET.get("group_teacher") or ""

    results_qs = HomeworkResult.objects.select_related(
        "student",
        "homework",
        "homework__lesson",
        "homework__lesson__group",
        "homework__lesson__group__course",
        "homework__lesson__subject",
        "homework__lesson__teacher__user",
        "homework__lesson__group_teacher__teacher__user",
        "homework__lesson__group_teacher__subject",
    )

    if search:
        results_qs = results_qs.filter(
            Q(student__first_name__icontains=search)
            | Q(student__last_name__icontains=search)
            | Q(homework__title__icontains=search)
            | Q(homework__lesson__group__name__icontains=search)
        )
    if group_id:
        results_qs = results_qs.filter(homework__lesson__group_id=group_id)
    if student_id:
        results_qs = results_qs.filter(student_id=student_id)
    if teacher_id:
        results_qs = results_qs.filter(_effective_teacher_q("homework__lesson", teacher_id))
    if subject_id:
        results_qs = results_qs.filter(homework__lesson__subject_id=subject_id)
    if homework_id:
        results_qs = results_qs.filter(homework_id=homework_id)
    if status_filter:
        results_qs = results_qs.filter(status=status_filter)
    if group_teacher_id:
        results_qs = results_qs.filter(homework__lesson__group_teacher_id=group_teacher_id)
    if score_min:
        results_qs = results_qs.filter(score__gte=score_min)
    if score_max:
        results_qs = results_qs.filter(score__lte=score_max)
    parsed = _parse_date(date_from, None)
    if parsed:
        results_qs = results_qs.filter(homework__lesson__date__gte=parsed)
    parsed = _parse_date(date_to, None)
    if parsed:
        results_qs = results_qs.filter(homework__lesson__date__lte=parsed)

    results_qs = results_qs.order_by("-created_at")

    total = results_qs.count()
    checked = results_qs.filter(status=HomeworkResult.Status.CHECKED).count()
    not_checked = total - checked
    submitted = results_qs.filter(
        status__in=[HomeworkResult.Status.SUBMITTED, HomeworkResult.Status.LATE, HomeworkResult.Status.CHECKED]
    ).count()
    not_submitted = results_qs.filter(status=HomeworkResult.Status.NOT_SUBMITTED).count()
    avg_score = results_qs.exclude(score__isnull=True).aggregate(avg=Avg("score"))["avg"]

    paginator = Paginator(results_qs, 25)
    page_obj = paginator.get_page(request.GET.get("page"))

    context = {
        **admin.site.each_context(request),
        "title": "Результаты домашних заданий",
        "subtitle": "Контроль выполнения и результатов домашних заданий студентов.",
        "records": page_obj,
        "kpi": {
            "total": total,
            "checked": checked,
            "not_checked": not_checked,
            "submitted": submitted,
            "not_submitted": not_submitted,
            "avg_score": round(avg_score, 1) if avg_score is not None else None,
        },
        "groups": Group.objects.order_by("name"),
        "students": Student.objects.filter(is_active=True).select_related("group").order_by("last_name", "first_name"),
        "teachers": Teacher.objects.filter(is_active=True).select_related("user").order_by("user__first_name"),
        "subjects": Subject.objects.filter(is_active=True).order_by("name"),
        "homeworks": Homework.objects.select_related("lesson__group").order_by("-created_at")[:200],
        "status_choices": HomeworkResult.Status.choices,
        "selected": {
            "q": search, "group": group_id, "student": student_id, "teacher": teacher_id, "subject": subject_id,
            "homework": homework_id, "status": status_filter, "score_min": score_min, "score_max": score_max,
            "date_from": date_from, "date_to": date_to,
        },
        "reset_url": reverse("admin:academy_homeworkresult_changelist"),
    }
    return render(request, "admin/academy/homeworkresult/change_list.html", context)


def homeworkresult_detail_view(request, object_id):
    _require_admin(request)
    result = get_object_or_404(
        HomeworkResult.objects.select_related(
            "student",
            "student__group",
            "homework",
            "homework__lesson",
            "homework__lesson__group",
            "homework__lesson__group__course",
            "homework__lesson__subject",
            "homework__lesson__teacher__user",
            "homework__lesson__group_teacher__teacher__user",
            "homework__lesson__group_teacher__subject",
        ),
        pk=object_id,
    )
    homework = result.homework
    lesson = homework.lesson
    group = lesson.group
    subject = lesson.subject or (lesson.group_teacher.subject if lesson.group_teacher_id else None)
    teacher = lesson.effective_teacher

    context = {
        **admin.site.each_context(request),
        "title": "Результаты домашних заданий",
        "result": result,
        "student": result.student,
        "homework": homework,
        "lesson": lesson,
        "group": group,
        "subject": subject,
        "teacher": teacher,
        "changelist_url": reverse("admin:academy_homeworkresult_changelist"),
        "student_url": reverse("admin:academy_student_detail", args=[result.student_id]),
        "group_url": reverse("admin:academy_group_workspace", args=[group.pk]),
        "homework_url": reverse("admin:academy_homework_change", args=[homework.pk]),
        "lesson_url": reverse("admin:academy_lesson_change", args=[lesson.pk]),
        "teacher_url": reverse("admin:users_teacher_change", args=[teacher.pk]) if teacher else None,
    }
    return render(request, "admin/academy/homeworkresult/detail.html", context)


def lesson_monitor_view(request):
    _require_admin(request)
    today = timezone.localdate()

    search = (request.GET.get("q") or "").strip()
    group_id = request.GET.get("group") or ""
    subject_id = request.GET.get("subject") or ""
    teacher_id = request.GET.get("teacher") or ""
    room_id = request.GET.get("room") or ""
    status_filter = request.GET.get("status") or ""
    date_from = request.GET.get("date_from") or ""
    date_to = request.GET.get("date_to") or ""
    group_teacher_id = request.GET.get("group_teacher") or ""
    attention_only = request.GET.get("attention") or ""

    lessons_qs = Lesson.objects.select_related(
        "group",
        "group__course",
        "room",
        "subject",
        "teacher__user",
        "group_teacher__teacher__user",
        "group_teacher__subject",
    )

    if search:
        lessons_qs = lessons_qs.filter(
            Q(group__name__icontains=search)
            | Q(topic__icontains=search)
            | Q(subject__name__icontains=search)
            | Q(teacher__user__first_name__icontains=search)
            | Q(teacher__user__last_name__icontains=search)
            | Q(group_teacher__teacher__user__first_name__icontains=search)
            | Q(group_teacher__teacher__user__last_name__icontains=search)
        )
    if group_id:
        lessons_qs = lessons_qs.filter(group_id=group_id)
    if subject_id:
        lessons_qs = lessons_qs.filter(subject_id=subject_id)
    if teacher_id:
        lessons_qs = lessons_qs.filter(_effective_teacher_q("", teacher_id))
    if room_id:
        lessons_qs = lessons_qs.filter(room_id=room_id)
    if status_filter:
        lessons_qs = lessons_qs.filter(status=status_filter)
    if group_teacher_id:
        lessons_qs = lessons_qs.filter(group_teacher_id=group_teacher_id)
    parsed = _parse_date(date_from, None)
    if parsed:
        lessons_qs = lessons_qs.filter(date__gte=parsed)
    parsed = _parse_date(date_to, None)
    if parsed:
        lessons_qs = lessons_qs.filter(date__lte=parsed)

    kpi = _lesson_status_kpi(lessons_qs, today)

    if attention_only:
        lessons_qs = lessons_qs.filter(attention_q(today, timezone.localtime().time()))

    lessons_qs = lessons_qs.order_by("-date", "-start_time")

    paginator = Paginator(lessons_qs, 25)
    page_obj = paginator.get_page(request.GET.get("page"))

    selected = {
        "q": search, "group": group_id, "subject": subject_id, "teacher": teacher_id, "room": room_id,
        "status": status_filter, "date_from": date_from, "date_to": date_to, "attention": attention_only,
    }

    def _quick_url(params: dict) -> str:
        qs = "&".join(f"{key}={value}" for key, value in params.items() if value)
        return f"{reverse('admin:academy_lesson_changelist')}{'?' + qs if qs else ''}"

    quick_presets = [
        {"label": "Все", "params": {}},
        {"label": "Сегодня", "params": {"date_from": today.isoformat(), "date_to": today.isoformat()}},
        {"label": "Предстоящие", "params": {"status": Lesson.Status.SCHEDULED, "date_from": today.isoformat()}},
        {"label": "Требуют внимания", "params": {"attention": "1"}},
        {"label": "Завершённые", "params": {"status": Lesson.Status.COMPLETED}},
        {"label": "Отменённые", "params": {"status": Lesson.Status.CANCELLED}},
    ]
    quick_filters = [
        {
            "label": preset["label"],
            "url": _quick_url(preset["params"]),
            "active": (
                selected["status"] == preset["params"].get("status", "")
                and selected["date_from"] == preset["params"].get("date_from", "")
                and selected["date_to"] == preset["params"].get("date_to", "")
                and selected["attention"] == preset["params"].get("attention", "")
            ),
        }
        for preset in quick_presets
    ]

    context = {
        **admin.site.each_context(request),
        "title": "Занятия",
        "subtitle": "Просмотр и контроль учебных занятий академии.",
        "lessons": page_obj,
        "kpi": kpi,
        "quick_filters": quick_filters,
        "groups": Group.objects.order_by("name"),
        "subjects": Subject.objects.filter(is_active=True).order_by("name"),
        "teachers": Teacher.objects.filter(is_active=True).select_related("user").order_by("user__first_name"),
        "rooms": Room.objects.filter(is_active=True).order_by("name"),
        "status_choices": Lesson.Status.choices,
        "selected": selected,
        "reset_url": reverse("admin:academy_lesson_changelist"),
        "schedule_url": reverse("admin:academy_schedule"),
    }
    return render(request, "admin/academy/lesson/change_list.html", context)


def lesson_detail_view(request, object_id):
    _require_admin(request)
    lesson = get_object_or_404(
        Lesson.objects.select_related(
            "group",
            "group__course",
            "room",
            "subject",
            "plan",
            "individual_plan",
            "teacher__user",
            "group_teacher__teacher__user",
            "group_teacher__subject",
            "rescheduled_from",
            "rescheduled_to",
        ),
        pk=object_id,
    )
    group = lesson.group
    subject = lesson.subject or (lesson.group_teacher.subject if lesson.group_teacher_id else None)
    teacher = lesson.effective_teacher

    students_count = group.students_count
    attendance_qs = Attendance.objects.filter(lesson=lesson).select_related("student")
    present_count = attendance_qs.filter(status=Attendance.Status.PRESENT).count()
    absent_count = attendance_qs.filter(status=Attendance.Status.ABSENT).count()

    homeworks = list(
        Homework.objects.filter(lesson=lesson).annotate(
            results_total=Count("results", distinct=True),
            results_checked=Count(
                "results", filter=Q(results__status=HomeworkResult.Status.CHECKED), distinct=True
            ),
            results_submitted=Count(
                "results",
                filter=Q(
                    results__status__in=[
                        HomeworkResult.Status.SUBMITTED,
                        HomeworkResult.Status.LATE,
                        HomeworkResult.Status.CHECKED,
                    ]
                ),
                distinct=True,
            ),
        )
    )
    homework_rows = []
    for hw in homeworks:
        avg_score = (
            HomeworkResult.objects.filter(homework=hw).exclude(score__isnull=True).aggregate(avg=Avg("score"))["avg"]
        )
        homework_rows.append(
            {
                "obj": hw,
                "students_total": students_count,
                "submitted": hw.results_submitted,
                "checked": hw.results_checked,
                "avg_score": round(avg_score, 1) if avg_score is not None else None,
                "detail_url": reverse("admin:academy_homework_change", args=[hw.pk]),
            }
        )
    checked_results_total = sum(hw.results_checked for hw in homeworks) if homeworks else None

    context = {
        **admin.site.each_context(request),
        "title": "Занятия",
        "lesson": lesson,
        "group": group,
        "subject": subject,
        "teacher": teacher,
        "kpi": {
            "students_count": students_count,
            "present_count": present_count,
            "absent_count": absent_count,
            "homework_count": len(homeworks),
            "checked_results_total": checked_results_total,
        },
        "attendance_records": list(
            attendance_qs.order_by("student__last_name", "student__first_name")
        ),
        "homework_rows": homework_rows,
        "changelist_url": reverse("admin:academy_lesson_changelist"),
        "group_url": reverse("admin:academy_group_workspace", args=[group.pk]),
        "program_url": (
            reverse("admin:academy_groupteacher_workspace", args=[lesson.group_teacher_id])
            if lesson.group_teacher_id
            else None
        ),
        "schedule_tab_url": reverse("admin:academy_group_workspace_schedule", args=[group.pk]),
        "teacher_url": reverse("admin:users_teacher_change", args=[teacher.pk]) if teacher else None,
        "attendance_url": f"{reverse('admin:academy_attendance_changelist')}?lesson={lesson.pk}",
        "course_lesson_plan_url": (
            reverse("admin:academy_courselessonplan_change", args=[lesson.plan_id]) if lesson.plan_id else None
        ),
        "individual_plan_program_url": (
            reverse("admin:academy_groupteacher_change", args=[lesson.individual_plan.group_teacher_id])
            if lesson.individual_plan_id
            else None
        ),
    }
    return render(request, "admin/academy/lesson/detail.html", context)


# ---------------------------------------------------------------------------
# Monthly Teacher Reports — Admin's read-only view onto what a Teacher has
# submitted. Admin never creates or edits a report (spec §14): both screens
# below are pure display, built on the very same `compute_monthly_stats`
# the Teacher-facing API/PDF use, so a number here can never drift from what
# the Teacher themself sees.
# ---------------------------------------------------------------------------

def monthly_report_monitor_view(request):
    _require_admin(request)

    teacher_id = request.GET.get("teacher") or ""
    year = request.GET.get("year") or ""
    month = request.GET.get("month") or ""

    reports_qs = MonthlyTeacherReport.objects.select_related("teacher__user")
    if teacher_id:
        reports_qs = reports_qs.filter(teacher_id=teacher_id)
    if year:
        reports_qs = reports_qs.filter(year=year)
    if month:
        reports_qs = reports_qs.filter(month=month)
    reports_qs = reports_qs.order_by("-year", "-month", "teacher__user__last_name")

    paginator = Paginator(reports_qs, 25)
    page_obj = paginator.get_page(request.GET.get("page"))

    rows = []
    for report in page_obj:
        stats = compute_monthly_stats(report.teacher, report.year, report.month)
        rows.append({"report": report, "stats": stats, "month_label": f"{MONTH_NAMES_RU[report.month]} {report.year}"})

    years = sorted(MonthlyTeacherReport.objects.values_list("year", flat=True).distinct(), reverse=True)

    context = {
        **admin.site.each_context(request),
        "title": "Отчёты преподавателей",
        "subtitle": "Ежемесячные отчёты о работе преподавателей — статистика считается автоматически.",
        "rows": rows,
        "page_obj": page_obj,
        "teachers": Teacher.objects.filter(is_active=True).select_related("user").order_by("user__first_name"),
        "years": years,
        "months": list(enumerate(MONTH_NAMES_RU))[1:],
        "selected": {"teacher": teacher_id, "year": year, "month": month},
        "reset_url": reverse("admin:academy_monthlyteacherreport_changelist"),
    }
    return render(request, "admin/academy/monthlyteacherreport/change_list.html", context)


def _num(value: float) -> str:
    """Plain `"34.0"`-style string for an SVG coordinate — never a raw
    float. `{{ }}` on a raw float renders through Django's active-locale
    number formatting (LANGUAGE_CODE="ru-ru" here), which turns "34.0"
    into "34,0" — invalid inside an SVG/CSS numeric attribute, so browsers
    silently drop or mis-parse it. Pre-stringifying in Python sidesteps
    that entirely, the same way `path` below already had to."""
    return f"{value:.1f}"


def _weekly_dynamics_chart(weeks: list[dict]) -> dict:
    """Geometry for an inline `<svg viewBox="0 0 {W} {H}">` line chart —
    same auto-scaled-domain approach as the PDF's chart (see
    services.chart_geometry), so a strong, stable month still reads as a
    real line instead of four points glued to the top of a 0-100% scale."""
    if len(weeks) < 2:
        return {"has_data": False}

    width, height = 600, 180
    plot_x0, plot_x1 = 34, width - 10
    plot_y0, plot_y1 = 22, height - 24

    values = [w["percent"] for w in weeks]
    domain_lo, domain_hi = nice_domain(values)

    def x_for(index: int) -> float:
        if len(weeks) == 1:
            return (plot_x0 + plot_x1) / 2
        return plot_x0 + (index / (len(weeks) - 1)) * (plot_x1 - plot_x0)

    def y_for(value: float) -> float:
        ratio = ratio_in_domain(value, domain_lo, domain_hi)
        return plot_y1 - ratio * (plot_y1 - plot_y0)

    # Every coordinate the template needs is pre-computed and pre-formatted
    # here — including offsets (value label above a point, axis label next
    # to a gridline) — so the template never has to run arithmetic on a
    # value that might be a string (Django's `add` filter silently returns
    # "" when it can't coerce both sides to int, which a "58.6"-style
    # string can't be).
    points = [
        {
            "x": _num(x_for(i)),
            "y": _num(y_for(w["percent"])),
            "value_label_y": _num(y_for(w["percent"]) - 10),
            "label": w["label"],
            "value": w["percent"],
        }
        for i, w in enumerate(weeks)
    ]
    path = " ".join(f"{'M' if i == 0 else 'L'}{p['x']},{p['y']}" for i, p in enumerate(points))
    ticks = [
        {"value": int(t), "y": _num(y_for(t)), "label_y": _num(y_for(t) + 3)}
        for t in nice_ticks(domain_lo, domain_hi)
    ]

    return {
        "has_data": True,
        "width": width,
        "height": height,
        "plot_x0": plot_x0,
        "plot_x1": plot_x1,
        "axis_label_x": plot_x0 - 6,
        "week_label_y": height - 6,
        "points": points,
        "path": path,
        "ticks": ticks,
    }


def monthly_report_detail_view(request, object_id):
    _require_admin(request)
    report = get_object_or_404(MonthlyTeacherReport.objects.select_related("teacher__user"), pk=object_id)
    stats = compute_monthly_stats(report.teacher, report.year, report.month)

    context = {
        **admin.site.each_context(request),
        "title": "Отчёт преподавателя",
        "report": report,
        "teacher": report.teacher,
        "stats": stats,
        "chart": _weekly_dynamics_chart(stats["weekly_dynamics"]),
        "month_label": f"{MONTH_NAMES_RU[report.month]} {report.year}",
        "changelist_url": reverse("admin:academy_monthlyteacherreport_changelist"),
        "teacher_url": reverse("admin:users_teacher_change", args=[report.teacher_id]),
        "pdf_url": reverse("monthly-report-pdf", args=[report.pk]),
    }
    return render(request, "admin/academy/monthlyteacherreport/detail.html", context)


# ---------------------------------------------------------------------------
# "Отчёт академии" — the whole-academy counterpart of the Monthly Teacher
# Report monitor/detail views above. Every figure is computed on demand by
# services.academy_monthly_report.compute_academy_monthly_stats from the
# existing Lesson/Attendance/Homework/HomeworkResult/Group/Student/Teacher
# data — nothing here duplicates that calculation, this module only ever
# renders it. Admin-only, enforced by `_require_admin` (backend check, not
# just a hidden Sidebar entry — see AcademyReportSidebarTests).
# ---------------------------------------------------------------------------

def academy_report_monitor_view(request):
    _require_admin(request)

    year = request.GET.get("year") or ""
    month = request.GET.get("month") or ""

    reports_qs = AcademyMonthlyReport.objects.all()
    if year:
        reports_qs = reports_qs.filter(year=year)
    if month:
        reports_qs = reports_qs.filter(month=month)
    reports_qs = reports_qs.order_by("-year", "-month")

    paginator = Paginator(reports_qs, 25)
    page_obj = paginator.get_page(request.GET.get("page"))

    rows = []
    for report in page_obj:
        stats = compute_academy_monthly_stats(report.year, report.month)
        rows.append({"report": report, "stats": stats, "month_label": f"{MONTH_NAMES_RU[report.month]} {report.year}"})

    years = sorted(AcademyMonthlyReport.objects.values_list("year", flat=True).distinct(), reverse=True)
    today = timezone.localdate()

    context = {
        **admin.site.each_context(request),
        "title": "Отчёт академии",
        "subtitle": "Ежемесячная статистика и результаты академии — считается автоматически.",
        "rows": rows,
        "page_obj": page_obj,
        "years": years,
        "months": list(enumerate(MONTH_NAMES_RU))[1:],
        "selected": {"year": year, "month": month},
        "current_year": today.year,
        "current_month": today.month,
        "reset_url": reverse("admin:academy_report_monitor"),
        "open_url": reverse("admin:academy_report_open"),
    }
    return render(request, "admin/academy/academymonthlyreport/change_list.html", context)


@require_POST
def academy_report_open_view(request):
    _require_admin(request)

    try:
        year = int(request.POST.get("year", ""))
        month = int(request.POST.get("month", ""))
    except (TypeError, ValueError):
        messages.error(request, "Укажите год и месяц.")
        return redirect(reverse("admin:academy_report_monitor"))

    if not (2000 <= year <= 2100 and 1 <= month <= 12):
        messages.error(request, "Некорректный год или месяц.")
        return redirect(reverse("admin:academy_report_monitor"))

    report, _created = AcademyMonthlyReport.objects.get_or_create(year=year, month=month)
    return redirect(reverse("admin:academy_report_detail", args=[report.pk]))


def academy_report_detail_view(request, object_id):
    _require_admin(request)
    report = get_object_or_404(AcademyMonthlyReport, pk=object_id)
    stats = compute_academy_monthly_stats(report.year, report.month)

    context = {
        **admin.site.each_context(request),
        "title": "Отчёт академии",
        "report": report,
        "stats": stats,
        "chart": _weekly_dynamics_chart(stats["weekly_dynamics"]),
        "month_label": f"{MONTH_NAMES_RU[report.month]} {report.year}",
        "monitor_url": reverse("admin:academy_report_monitor"),
        "pdf_url": reverse("academy-report-pdf", args=[report.pk]),
    }
    return render(request, "admin/academy/academymonthlyreport/detail.html", context)


# ---------------------------------------------------------------------------
# "Неактивные студенты" / "История ухода студентов" — read the audit trail
# `services.student_status` writes (see StudentStatusEvent). Both screens
# only ever read; nothing here mutates a Student or writes a new event.
# ---------------------------------------------------------------------------

def _reason_label(reason: str) -> str:
    return dict(StudentStatusEvent.Reason.choices).get(reason, reason or "—")


def _student_search_q(query: str) -> Q:
    q = Q(first_name__icontains=query) | Q(last_name__icontains=query) | Q(group__name__icontains=query)
    if query.isdigit():
        q |= Q(id=int(query))
    return q


def _int_or_none(value: str) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def inactive_students_view(request):
    """Only students who *left the academy entirely* — a reactivated
    student's `status` flips back to `active` (see services.student_status),
    so they drop off this list on their own without any extra bookkeeping
    here. Filtered by `status=WITHDRAWN` rather than `is_active=False`: a
    paused or completed student is also `is_active=False`, but pausing or
    completing studies is a different business process from departing and
    must never show up on this "who left" page (spec: "Не смешивай её с
    обычной повторной активацией после деактивации, если это разные
    бизнес-процессы")."""
    _require_admin(request)

    year = _int_or_none(request.GET.get("year"))
    month = _int_or_none(request.GET.get("month"))
    reason = request.GET.get("reason") or ""
    group_id = request.GET.get("group") or ""
    date_from = request.GET.get("date_from") or ""
    date_to = request.GET.get("date_to") or ""
    query = request.GET.get("q") or ""

    students_qs = Student.objects.filter(status=Student.Status.WITHDRAWN).select_related("group")
    if group_id:
        students_qs = students_qs.filter(group_id=group_id)
    if query:
        students_qs = students_qs.filter(_student_search_q(query))

    last_deactivation_qs = StudentStatusEvent.objects.filter(
        event_type=StudentStatusEvent.EventType.DEACTIVATED
    ).select_related("group").order_by("-created_at")
    students_qs = students_qs.prefetch_related(
        Prefetch("status_events", queryset=last_deactivation_qs, to_attr="_deactivations")
    )

    rows = []
    for student in students_qs:
        last_event = student._deactivations[0] if student._deactivations else None

        if year is not None and (last_event is None or last_event.event_date.year != year):
            continue
        if month is not None and (last_event is None or last_event.event_date.month != month):
            continue
        if reason and (last_event is None or last_event.reason != reason):
            continue
        if date_from and (last_event is None or last_event.event_date < dt.date.fromisoformat(date_from)):
            continue
        if date_to and (last_event is None or last_event.event_date > dt.date.fromisoformat(date_to)):
            continue

        rows.append({"student": student, "last_event": last_event})

    paginator = Paginator(rows, 25)
    page_obj = paginator.get_page(request.GET.get("page"))

    context = {
        **admin.site.each_context(request),
        "title": "Неактивные студенты",
        "subtitle": "Студенты, которые сейчас не активны — вернувшиеся автоматически исчезают из списка.",
        "page_obj": page_obj,
        "rows": page_obj.object_list,
        "groups": Group.objects.order_by("name"),
        "reasons": StudentStatusEvent.Reason.choices,
        "years": sorted(
            {
                d.year
                for d in StudentStatusEvent.objects.filter(
                    event_type=StudentStatusEvent.EventType.DEACTIVATED
                ).dates("event_date", "year")
            },
            reverse=True,
        ),
        "months": list(enumerate(MONTH_NAMES_RU))[1:],
        "selected": {
            "year": request.GET.get("year") or "",
            "month": request.GET.get("month") or "",
            "reason": reason,
            "group": group_id,
            "date_from": date_from,
            "date_to": date_to,
            "q": query,
        },
        "reset_url": reverse("admin:academy_inactive_students"),
        "history_url": reverse("admin:academy_student_departure_history"),
    }
    return render(request, "admin/academy/student/inactive_list.html", context)


def student_departure_history_view(request):
    """Every deactivation ever recorded — including students who have since
    returned (spec: "включая студентов, которые уже вернулись")."""
    _require_admin(request)

    year = request.GET.get("year") or ""
    month = request.GET.get("month") or ""
    reason = request.GET.get("reason") or ""
    group_id = request.GET.get("group") or ""
    date_from = request.GET.get("date_from") or ""
    date_to = request.GET.get("date_to") or ""
    query = request.GET.get("q") or ""

    events_qs = (
        StudentStatusEvent.objects.filter(event_type=StudentStatusEvent.EventType.DEACTIVATED)
        .select_related("student", "group", "performed_by")
        .order_by("-event_date", "-created_at")
    )
    if year:
        events_qs = events_qs.filter(event_date__year=year)
    if month:
        events_qs = events_qs.filter(event_date__month=month)
    if reason:
        events_qs = events_qs.filter(reason=reason)
    if group_id:
        events_qs = events_qs.filter(group_id=group_id)
    if date_from:
        events_qs = events_qs.filter(event_date__gte=date_from)
    if date_to:
        events_qs = events_qs.filter(event_date__lte=date_to)
    if query:
        q = Q(student__first_name__icontains=query) | Q(student__last_name__icontains=query) | Q(group__name__icontains=query)
        if query.isdigit():
            q |= Q(student_id=int(query))
        events_qs = events_qs.filter(q)

    paginator = Paginator(events_qs, 25)
    page_obj = paginator.get_page(request.GET.get("page"))

    context = {
        **admin.site.each_context(request),
        "title": "История ухода студентов",
        "subtitle": "Все деактивации, включая студентов, которые уже вернулись.",
        "page_obj": page_obj,
        "rows": page_obj.object_list,
        "groups": Group.objects.order_by("name"),
        "reasons": StudentStatusEvent.Reason.choices,
        "years": sorted({d.year for d in events_qs.dates("event_date", "year")}, reverse=True),
        "months": list(enumerate(MONTH_NAMES_RU))[1:],
        "selected": {
            "year": year, "month": month, "reason": reason, "group": group_id,
            "date_from": date_from, "date_to": date_to, "q": query,
        },
        "reset_url": reverse("admin:academy_student_departure_history"),
        "inactive_students_url": reverse("admin:academy_inactive_students"),
    }
    return render(request, "admin/academy/student/departure_history.html", context)
