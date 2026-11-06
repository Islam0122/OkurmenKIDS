"""API — /api/v1/academic-progress/. Every number is computed on the server
(progress.py); writes are checked by access.py."""
from __future__ import annotations

from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.academy.models import Group
from apps.users.models import Subject

from . import access, progress
from .models import CurriculumMonth, GroupProgressAdjustment, ProgramCurriculum


class CanView(BasePermission):
    message = "Настройки учебных программ вам недоступны."

    def has_permission(self, request, view) -> bool:
        return access.can_view(request.user)


class _View(APIView):
    permission_classes = [IsAuthenticated, CanView]


def _ref(obj):
    return {"id": obj.pk, "name": obj.name} if obj is not None else None


def settings_payload(course, curriculum: ProgramCurriculum | None, user) -> dict:
    data = {
        "course": {"id": course.pk, "name": course.name, "count_lesson": course.count_lesson,
                   "subjects": [_ref(s) for s in course.subjects.all().order_by("name")]},
        "configured": curriculum is not None,
        "can_edit": access.can_edit(user, course),
        "settings": None,
    }
    if curriculum is not None:
        data["settings"] = {
            "lessons_per_month": curriculum.lessons_per_month,
            "duration_months": curriculum.duration_months,
            "main_subject": _ref(curriculum.main_subject),
            "extra_subjects": [_ref(s) for s in curriculum.extra_subjects.all().order_by("name")],
            "count_mode": curriculum.count_mode,
            "months": [
                {"number": m.number, "subject": _ref(m.subject), "planned_lessons": m.planned_lessons}
                for m in curriculum.months.all().order_by("number")
            ],
            "blocks": [{"number": b.number, "subject": _ref(b.subject), "planned": b.planned} for b in progress.blocks(curriculum)],
            "total_lessons": sum(b.planned for b in progress.blocks(curriculum)),
            "updated_at": curriculum.updated_at,
            "updated_by": (curriculum.updated_by.get_full_name() or curriculum.updated_by.username) if curriculum.updated_by_id else None,
        }
    return data


class MetaView(_View):
    def get(self, request):
        return Response({
            "subjects": [_ref(s) for s in Subject.objects.filter(is_active=True).order_by("name")],
            "can_edit": access.can_edit(request.user),
            "presets": [12, 20],
        })


class ProgramsView(_View):
    """Every program the user may see, with its study-month summary and how
    many of its groups need setting up."""

    def get(self, request):
        courses = list(access.visible_courses(request.user).order_by("name"))
        curricula = progress.load_curricula(c.pk for c in courses)
        groups = list(Group.objects.filter(course__in=courses).exclude(status=Group.Status.CANCELLED))
        prog = progress.progress_for(groups)
        by_course: dict[int, list] = {}
        for g in groups:
            by_course.setdefault(g.course_id, []).append(prog[g.pk])
        rows = []
        for c in courses:
            cur = curricula.get(c.pk)
            items = by_course.get(c.pk, [])
            rows.append({
                "id": c.pk, "name": c.name, "configured": cur is not None,
                "lessons_per_month": cur.lessons_per_month if cur else None,
                "duration_months": cur.duration_months if cur else None,
                "main_subject": _ref(cur.main_subject) if cur else None,
                "extra_subjects": [_ref(s) for s in cur.extra_subjects.all()] if cur else [],
                "total_lessons": sum(b.planned for b in progress.blocks(cur)) if cur else None,
                "groups": len(items),
                "groups_need_setup": sum(1 for p in items if p["status"] == progress.NEEDS_SETUP),
                "can_edit": access.can_edit(request.user, c),
            })
        return Response({"results": rows})


def _int(value, field, errors, lo=1, hi=200, required=True):
    if value in (None, ""):
        if required:
            errors[field] = "Обязательное поле."
        return None
    try:
        number = int(value)
    except (TypeError, ValueError):
        errors[field] = "Введите число."
        return None
    if not lo <= number <= hi:
        errors[field] = f"От {lo} до {hi}."
        return None
    return number


def _subject(value, field, errors):
    if value in (None, ""):
        return None
    subject = Subject.objects.filter(pk=value).first() if str(value).isdigit() else None
    if subject is None:
        errors[field] = "Предмет не найден."
    return subject


class ProgramView(_View):
    def _course(self, request, pk):
        return get_object_or_404(access.visible_courses(request.user), pk=pk)

    def get(self, request, pk):
        course = self._course(request, pk)
        return Response(settings_payload(course, ProgramCurriculum.objects.filter(course=course).first(), request.user))

    def put(self, request, pk):
        course = self._course(request, pk)
        if not access.can_edit(request.user, course):
            return Response({"detail": "Изменять настройки этой программы вы не можете."}, status=403)
        d, errors = request.data, {}
        per_month = _int(d.get("lessons_per_month"), "lessons_per_month", errors)
        duration = _int(d.get("duration_months"), "duration_months", errors, hi=60)
        main = _subject(d.get("main_subject"), "main_subject", errors)
        extra = [_subject(v, "extra_subjects", errors) for v in (d.get("extra_subjects") or [])]
        mode = d.get("count_mode") or ProgramCurriculum.CountMode.MAIN
        if mode not in ProgramCurriculum.CountMode.values:
            errors["count_mode"] = "Неверное значение."
        if main is not None and main in extra:
            errors["extra_subjects"] = "Основной предмет не может быть дополнительным."
        months, month_errors = [], {}
        for i, row in enumerate(d.get("months") or []):
            row_errors: dict = {}
            number = _int(row.get("number"), "number", row_errors, hi=60)
            if number and duration and number > duration:
                row_errors["number"] = "Больше продолжительности программы."
            planned = _int(row.get("planned_lessons"), "planned_lessons", row_errors, required=False)
            subject = _subject(row.get("subject"), "subject", row_errors)
            if row_errors:
                month_errors[i] = row_errors
            elif planned is not None or subject is not None:
                months.append((number, subject, planned))
        if len({m[0] for m in months}) != len(months):
            errors["months"] = "Учебный месяц указан дважды."
        if month_errors:
            errors["months"] = month_errors
        if errors:
            return Response(errors, status=400)
        with transaction.atomic():
            curriculum, _ = ProgramCurriculum.objects.get_or_create(course=course)
            curriculum.lessons_per_month, curriculum.duration_months = per_month, duration
            curriculum.main_subject, curriculum.count_mode, curriculum.updated_by = main, mode, request.user
            curriculum.save()
            curriculum.extra_subjects.set([s for s in extra if s])
            curriculum.months.all().delete()  # settings rows only — lessons and progress are untouched
            CurriculumMonth.objects.bulk_create(
                [CurriculumMonth(curriculum=curriculum, number=n, subject=s, planned_lessons=p) for n, s, p in months]
            )
        curriculum = ProgramCurriculum.objects.get(pk=curriculum.pk)
        return Response(settings_payload(course, curriculum, request.user))


class GroupProgressView(_View):
    def _group(self, request, pk):
        return get_object_or_404(Group.objects.filter(course__in=access.visible_courses(request.user)), pk=pk)

    def get(self, request, pk):
        group = self._group(request, pk)
        data = progress.group_progress(group)
        return Response({
            "group": {"id": group.pk, "name": group.name, "course": {"id": group.course_id, "name": group.course.name},
                      "start_date": group.start_date},
            "progress": data,
            "students": progress.student_progress(group, data),
            "can_edit": access.can_edit(request.user, group.course),
        })


class GroupHistoryView(GroupProgressView):
    """Confirm a group's history: lessons held before the LMS (0 is a valid answer)."""

    def put(self, request, pk):
        group = self._group(request, pk)
        if not access.can_edit(request.user, group.course):
            return Response({"detail": "Изменять настройки этой группы вы не можете."}, status=403)
        errors: dict = {}
        before = _int(request.data.get("lessons_before_lms"), "lessons_before_lms", errors, lo=0, hi=2000)
        if errors:
            return Response(errors, status=400)
        GroupProgressAdjustment.objects.update_or_create(
            group=group, defaults={"lessons_before_lms": before, "comment": str(request.data.get("comment") or "")[:255],
                                   "updated_by": request.user},
        )
        return self.get(request, pk)
