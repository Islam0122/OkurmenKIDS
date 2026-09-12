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
from django.db.models import Avg, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.users.import_export.formats import UnsupportedFileFormat
from apps.users.import_export.teachers import (
    TeacherImportValidationError,
    import_teachers,
    preview_teachers_import,
)
from apps.users.models import Subject, Teacher, User

from .constants import WEEKDAY_CODES, WEEKDAY_LABELS_FULL
from .models import Attendance, Course, Group, GroupSchedule, GroupTeacher, Homework, HomeworkResult, Lesson, Room
from .services.analytics import get_dashboard
from .services.excel_template_service import UnknownTemplateType, build_template
from .services.group_import_export import (
    GroupImportValidationError,
    export_groups,
    import_groups,
    preview_groups_import,
)
from .services.import_export import (
    StudentImportValidationError,
    import_students,
    preview_students_import,
)
from .services.lesson_generator import LessonGenerationError, generate_lessons_for_group
from .services.schedule_export import export_schedules

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
# "Импорт данных" — one dashboard page for template download / import /
# export across the entities that already have a reliable, well-scoped
# import path: Students and Teachers (both pre-existing, reused as-is here)
# plus Groups (new — upsert by its own unique `name`, see
# services.group_import_export). Group schedules are export-only from this
# page (see services.schedule_export's module docstring for why an importer
# isn't built for it) and Courses are out of scope — a course only has a
# name/count_lesson/subjects, nothing an admin fills in bulk from a
# spreadsheet in practice, so adding it here would be exactly the kind of
# unsupported-entity over-engineering the spec warns against.
#
# Deliberately its own page rather than three separate ModelAdmin import
# screens: the spec asks for one place with three cards (import/template/
# export), and Student/Teacher already have their own dedicated import
# screens (see StudentAdmin/TeacherAdmin.import_view) that this page reuses
# by calling straight into the same service functions — no logic is
# duplicated, only the presentation is unified.
# ---------------------------------------------------------------------------

_IMPORT_ENTITIES = {
    "student": {
        "label": "Студенты",
        "preview": preview_students_import,
        "import": import_students,
        "error_cls": StudentImportValidationError,
    },
    "teacher": {
        "label": "Тренеры",
        "preview": preview_teachers_import,
        "import": import_teachers,
        "error_cls": TeacherImportValidationError,
    },
    "group": {
        "label": "Группы",
        "preview": preview_groups_import,
        "import": import_groups,
        "error_cls": GroupImportValidationError,
    },
}

_ENTITY_CHOICES = [(key, meta["label"]) for key, meta in _IMPORT_ENTITIES.items()]


class ImportDataForm(forms.Form):
    entity = forms.ChoiceField(
        label="Тип данных",
        choices=_ENTITY_CHOICES,
        widget=forms.Select(attrs={"class": "ok-input"}),
    )
    file = forms.FileField(
        label="Файл (XLSX или CSV)",
        widget=forms.ClearableFileInput(attrs={"class": "ok-input", "accept": ".xlsx,.xls,.csv"}),
    )

    def clean_file(self):
        uploaded = self.cleaned_data["file"]
        name = (uploaded.name or "").lower()
        if not name.endswith((".xlsx", ".xls", ".csv")):
            raise forms.ValidationError(
                "Неподдерживаемый формат файла. Загрузите файл с расширением .xlsx или .csv."
            )
        return uploaded


def import_data_view(request):
    """GET renders the "Импорт данных" dashboard; POST handles one entity's
    upload (preview or confirm), routed to the matching existing import
    service — see _IMPORT_ENTITIES above."""
    if not _is_admin_user(request.user):
        raise PermissionDenied("Раздел «Импорт данных» доступен только администратору.")

    preview = None
    failed = False
    selected_entity = request.POST.get("entity") or "student"
    if selected_entity not in _IMPORT_ENTITIES:
        selected_entity = "student"

    if request.method == "POST":
        form = ImportDataForm(request.POST, request.FILES)
        if form.is_valid():
            selected_entity = form.cleaned_data["entity"]
            entity_meta = _IMPORT_ENTITIES[selected_entity]
            uploaded_file = form.cleaned_data["file"]

            if "preview" in request.POST:
                try:
                    preview = entity_meta["preview"](uploaded_file)
                except UnsupportedFileFormat as exc:
                    messages.error(request, str(exc))
            else:
                try:
                    result = entity_meta["import"](uploaded_file)
                except UnsupportedFileFormat as exc:
                    messages.error(request, str(exc))
                except entity_meta["error_cls"] as exc:
                    preview = exc.preview
                    failed = True
                else:
                    messages.success(
                        request,
                        f"Импорт «{entity_meta['label']}» завершён: создано {result.created}, "
                        f"обновлено {result.updated} из {result.total}.",
                    )
                    return redirect(reverse("admin:academy_import_data"))
    else:
        form = ImportDataForm(initial={"entity": selected_entity})

    context = {
        **admin.site.each_context(request),
        "title": "Импорт данных",
        "form": form,
        "preview": preview,
        "failed": failed,
        "selected_entity": selected_entity,
        "entity_choices": _ENTITY_CHOICES,
        "template_url": reverse("admin:academy_import_template"),
        "export_students_url": f"{reverse('admin:academy_student_export')}?format=xlsx",
        "export_groups_url": f"{reverse('admin:academy_group_export')}?format=xlsx",
        "export_schedule_url": f"{reverse('admin:academy_groupschedule_export')}?format=xlsx",
    }
    return render(request, "admin/academy/import_data.html", context)


def download_template_view(request):
    if not _is_admin_user(request.user):
        raise PermissionDenied("Раздел «Импорт данных» доступен только администратору.")

    entity = request.GET.get("type", "student")
    try:
        return build_template(entity)
    except UnknownTemplateType as exc:
        messages.error(request, str(exc))
        return redirect(reverse("admin:academy_import_data"))


def export_groups_view(request):
    if not _is_admin_user(request.user):
        raise PermissionDenied("Раздел «Импорт данных» доступен только администратору.")

    fmt = request.GET.get("format", "xlsx")
    try:
        return export_groups(Group.objects.select_related("course"), fmt)
    except UnsupportedFileFormat as exc:
        messages.error(request, str(exc))
        return redirect(reverse("admin:academy_import_data"))


def export_schedule_view(request):
    if not _is_admin_user(request.user):
        raise PermissionDenied("Раздел «Импорт данных» доступен только администратору.")

    fmt = request.GET.get("format", "xlsx")
    try:
        return export_schedules(GroupSchedule.objects.all(), fmt)
    except UnsupportedFileFormat as exc:
        messages.error(request, str(exc))
        return redirect(reverse("admin:academy_import_data"))
