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
from django.db.models import Avg, Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.users.models import Subject, Teacher, User

from .constants import WEEKDAY_CODES, WEEKDAY_LABELS_FULL
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
from .services.lesson_generator import LessonGenerationError, generate_lessons_for_group

WEEKDAY_NAMES = [WEEKDAY_LABELS_FULL[code] for code in WEEKDAY_CODES]


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
# Group Dashboard — "Открыть" on the Groups changelist lands here instead of
# the raw Django change form (the change form is still reachable, only via
# the dashboard's own "Изменить группу" button). Unlike the GroupTeacher
# Workspace above, this is scoped to the *whole* Group — every one of its
# Teaching Programs (models.GroupTeacher), every student, every Lesson
# regardless of which program generated it. Every figure is a direct,
# freshly-computed aggregate; nothing is stored.
# ---------------------------------------------------------------------------

_ATTENDED_STATUSES = (Attendance.Status.PRESENT, Attendance.Status.LATE)
_SUBMITTED_HOMEWORK_STATUSES = (
    HomeworkResult.Status.SUBMITTED,
    HomeworkResult.Status.CHECKED,
    HomeworkResult.Status.LATE,
)
_GROUP_STATUS_CSS = {
    Group.Status.ACTIVE: "ok-badge-success",
    Group.Status.PAUSED: "ok-badge-warning",
    Group.Status.COMPLETED: "ok-badge-muted",
    Group.Status.CANCELLED: "ok-badge-danger",
}


def group_dashboard_view(request, group_id: int):
    if not _is_admin_user(request.user):
        raise PermissionDenied("Раздел «Информация о группе» доступен только администратору.")

    group = get_object_or_404(Group.objects.select_related("course"), pk=group_id)
    today = timezone.localdate()

    programs = list(
        group.teachers.select_related("teacher__user", "subject")
        .prefetch_related("schedules__room")
        .order_by("-is_active", "id")
    )
    active_programs = [p for p in programs if p.is_active]
    active_teacher_ids = {p.teacher_id for p in active_programs}

    lessons_all_qs = Lesson.objects.filter(group=group)
    lesson_totals = lessons_all_qs.aggregate(
        total=Count("id"),
        completed=Count("id", filter=Q(status=Lesson.Status.COMPLETED)),
        upcoming=Count("id", filter=Q(status=Lesson.Status.PLANNED, date__gte=today)),
    )

    # --- Students: one query each for attendance/homework, not one per
    # student — then zipped onto each Student in Python. ---
    students_qs = group.students.order_by("last_name", "first_name")
    attendance_by_student = {
        row["student_id"]: row
        for row in (
            Attendance.objects.filter(lesson__group=group)
            .values("student_id")
            .annotate(total=Count("id"), attended=Count("id", filter=Q(status__in=_ATTENDED_STATUSES)))
        )
    }
    homework_by_student = {
        row["student_id"]: row
        for row in (
            HomeworkResult.objects.filter(homework__lesson__group=group)
            .values("student_id")
            .annotate(total=Count("id"), done=Count("id", filter=Q(status__in=_SUBMITTED_HOMEWORK_STATUSES)))
        )
    }
    students = []
    for student in students_qs:
        attendance_row = attendance_by_student.get(student.id)
        homework_row = homework_by_student.get(student.id)
        students.append(
            {
                "obj": student,
                "attendance_rate": (
                    round(attendance_row["attended"] / attendance_row["total"] * 100, 1)
                    if attendance_row and attendance_row["total"]
                    else None
                ),
                "homework_rate": (
                    round(homework_row["done"] / homework_row["total"] * 100, 1)
                    if homework_row and homework_row["total"]
                    else None
                ),
            }
        )
    students_total = len(students)
    students_active = sum(1 for row in students if row["obj"].is_active)

    # --- Programs tab: same shape as GroupAdmin.teaching_programs_summary,
    # but as plain data for a template instead of an HTML string. ---
    program_cards = []
    for program in programs:
        program_lessons = Lesson.objects.filter(group_teacher=program)
        active_slots = sorted(
            (slot for slot in program.schedules.all() if slot.is_active),
            key=lambda slot: (WEEKDAY_CODES.index(slot.day_of_week), slot.start_time),
        )
        program_cards.append(
            {
                "obj": program,
                "schedule": active_slots,
                "lesson_count": program_lessons.count(),
                "completed": program_lessons.filter(status=Lesson.Status.COMPLETED).count(),
                "upcoming": program_lessons.filter(status=Lesson.Status.PLANNED, date__gte=today).count(),
                "plan_count": program.lesson_plans.count(),
                "workspace_url": reverse("admin:academy_groupteacher_workspace", args=[program.pk]),
                "change_url": reverse("admin:academy_groupteacher_change", args=[program.pk]),
                "lessons_url": (
                    f"{reverse('admin:academy_lesson_changelist')}?group_teacher__id__exact={program.pk}"
                ),
            }
        )

    # --- Teachers tab: every distinct teacher across this group's programs. ---
    teachers_by_id: dict[int, dict] = {}
    for program in programs:
        entry = teachers_by_id.setdefault(program.teacher_id, {"teacher": program.teacher, "programs": []})
        entry["programs"].append(program)
    teachers_summary = list(teachers_by_id.values())

    # --- Schedule tab: this group's own weekly slots, grouped by day. ---
    schedule_slots = list(
        GroupSchedule.objects.filter(group=group, is_active=True)
        .select_related("teacher__user", "subject", "room")
        .order_by("day_of_week", "start_time")
    )
    schedule_by_day: dict[str, list] = defaultdict(list)
    for slot in schedule_slots:
        schedule_by_day[slot.day_of_week].append(slot)
    weekly_schedule = [
        {"code": code, "label": WEEKDAY_LABELS_FULL[code], "slots": schedule_by_day.get(code, [])}
        for code in WEEKDAY_CODES
    ]

    # --- Lessons tab: this group's own Lessons only, with optional filters. ---
    lessons_qs = lessons_all_qs.select_related(
        "subject", "room", "group_teacher__teacher__user"
    ).order_by("-date", "-start_time")
    lesson_filters = {
        "subject": request.GET.get("lesson_subject") or "",
        "teacher": request.GET.get("lesson_teacher") or "",
        "status": request.GET.get("lesson_status") or "",
        "date": request.GET.get("lesson_date") or "",
    }
    if lesson_filters["subject"]:
        lessons_qs = lessons_qs.filter(subject_id=lesson_filters["subject"])
    if lesson_filters["teacher"]:
        teacher_id = lesson_filters["teacher"]
        lessons_qs = lessons_qs.filter(
            Q(teacher_id=teacher_id) | Q(teacher__isnull=True, group_teacher__teacher_id=teacher_id)
        )
    if lesson_filters["status"]:
        lessons_qs = lessons_qs.filter(status=lesson_filters["status"])
    if lesson_filters["date"]:
        filter_date = _parse_date(lesson_filters["date"], None)
        if filter_date:
            lessons_qs = lessons_qs.filter(date=filter_date)
    lessons = list(lessons_qs[:300])

    upcoming_preview = list(
        lessons_all_qs.select_related("subject", "room", "group_teacher__teacher__user")
        .filter(status=Lesson.Status.PLANNED, date__gte=today)
        .order_by("date", "start_time")[:8]
    )

    # --- Analytics tab + the attendance/homework KPI cards: the existing,
    # already-tested analytics service, scoped to just this group over its
    # whole lifetime (never a fabricated/mock figure). ---
    end_boundary = max(today, group.end_date) if group.end_date else today
    dashboard = get_dashboard(
        period="custom", start_date=group.start_date, end_date=end_boundary, group_id=group.pk, today=today
    )

    kpis = [
        {"icon": "bi-mortarboard", "label": "Всего студентов", "value": students_total},
        {"icon": "bi-person-check", "label": "Активных студентов", "value": students_active},
        {"icon": "bi-person-badge", "label": "Преподавателей", "value": len(active_teacher_ids)},
        {"icon": "bi-collection-play", "label": "Учебных программ", "value": len(active_programs)},
        {"icon": "bi-calendar3", "label": "Всего занятий", "value": lesson_totals["total"] or 0},
        {"icon": "bi-check2-circle", "label": "Завершённых занятий", "value": lesson_totals["completed"] or 0},
        {"icon": "bi-calendar-event", "label": "Предстоящих занятий", "value": lesson_totals["upcoming"] or 0},
        {
            "icon": "bi-clipboard-check",
            "label": "Attendance Rate",
            "value": f"{dashboard['attendance']['attendance_rate']['value']}%",
        },
        {
            "icon": "bi-journal-check",
            "label": "Homework Completion",
            "value": f"{dashboard['homework']['submission_rate']['value']}%",
        },
    ]

    capacity_label = f"{students_active} / {group.max_students}" if group.max_students else f"{students_active} / ∞"
    period_label = (
        f"{group.start_date:%d.%m.%Y} – {group.end_date:%d.%m.%Y}"
        if group.end_date
        else f"{group.start_date:%d.%m.%Y} – …"
    )

    context = {
        **admin.site.each_context(request),
        "title": group.name,
        "group": group,
        "status_css": _GROUP_STATUS_CSS.get(group.status, "ok-badge-muted"),
        "capacity_label": capacity_label,
        "period_label": period_label,
        "kpis": kpis,
        "students": students,
        "students_total": students_total,
        "students_active": students_active,
        "students_inactive": students_total - students_active,
        "programs": program_cards,
        "active_programs_count": len(active_programs),
        "teachers_summary": teachers_summary,
        "weekly_schedule": weekly_schedule,
        "lessons": lessons,
        "lesson_filters": lesson_filters,
        "lesson_statuses": Lesson.Status.choices,
        "filter_subjects": Subject.objects.filter(is_active=True).order_by("name"),
        "filter_teachers": Teacher.objects.filter(id__in=active_teacher_ids).select_related("user"),
        "upcoming_preview": upcoming_preview,
        "dashboard": dashboard,
        "active_tab": request.GET.get("tab") or "overview",
        "change_url": reverse("admin:academy_group_change", args=[group.pk]),
        "changelist_url": reverse("admin:academy_group_changelist"),
        "add_student_url": f"{reverse('admin:academy_student_add')}?group={group.pk}",
        "add_existing_students_url": reverse("admin:academy_group_add_students", args=[group.pk]),
        "import_students_url": reverse("admin:academy_student_import"),
        "dashboard_url": reverse("admin:academy_group_dashboard", args=[group.pk]),
    }
    return render(request, "admin/academy/group_dashboard.html", context)


@require_POST
def group_student_action_view(request, group_id: int, student_id: int):
    """Removing a Student from a Group only ever nulls Student.group — the
    Student row (and every Attendance/HomeworkResult it's tied to) is never
    deleted. "Деактивировать" is the same is_active flip StudentAdmin's own
    bulk action does; it's not a delete either.
    """
    if not _is_admin_user(request.user):
        raise PermissionDenied("Действие доступно только администратору.")

    group = get_object_or_404(Group, pk=group_id)
    student = get_object_or_404(Student, pk=student_id, group=group)
    action = request.POST.get("action")

    if action == "remove":
        student.group = None
        student.save()
        messages.success(request, f"«{student}» убран(а) из группы «{group.name}». Студент не удалён из системы.")
    elif action == "deactivate":
        student.is_active = False
        student.save()
        messages.success(request, f"«{student}» деактивирован(а). История посещаемости и ДЗ сохранена.")
    elif action == "activate":
        student.is_active = True
        student.save()
        messages.success(request, f"«{student}» снова активен(а).")
    else:
        messages.error(request, "Неизвестное действие.")

    return redirect(f"{reverse('admin:academy_group_dashboard', args=[group_id])}?tab=students")


def group_add_students_view(request, group_id: int):
    """The "Добавить существующих" / "Массовое добавление" flow: pick any
    number of existing Students (not already in this group) and assign them
    all at once. Never creates a Student — that's the separate "+ Добавить
    студента" button, which opens the ordinary Student add form pre-filled
    with this group.
    """
    if not _is_admin_user(request.user):
        raise PermissionDenied("Действие доступно только администратору.")

    group = get_object_or_404(Group, pk=group_id)

    if request.method == "POST":
        selected_ids = request.POST.getlist("student_ids")
        if selected_ids:
            updated = Student.objects.filter(id__in=selected_ids).update(group=group, updated_at=timezone.now())
            messages.success(request, f"Добавлено студентов в «{group.name}»: {updated}.")
        else:
            messages.warning(request, "Не выбрано ни одного студента.")
        return redirect(f"{reverse('admin:academy_group_dashboard', args=[group_id])}?tab=students")

    query = (request.GET.get("q") or "").strip()
    candidates_qs = Student.objects.filter(is_active=True).exclude(group=group).order_by("last_name", "first_name")
    if query:
        candidates_qs = candidates_qs.filter(
            Q(first_name__icontains=query) | Q(last_name__icontains=query) | Q(phone__icontains=query)
        )

    context = {
        **admin.site.each_context(request),
        "title": f"Добавить студентов — {group.name}",
        "group": group,
        "candidates": candidates_qs[:200],
        "query": query,
        "dashboard_url": reverse("admin:academy_group_dashboard", args=[group_id]),
    }
    return render(request, "admin/academy/group_add_students.html", context)
