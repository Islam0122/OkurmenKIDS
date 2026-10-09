"""«Расписание» API — /api/v1/schedule/. One API for the Team Lead's and the
Assistant's schedule pages over services.schedule_board, so both roles see
the same lessons, conflicts and free rooms from the same code.

Reading is open to Admin, Team Lead and Assistant (CanViewSchedule); a
Trainer keeps the lessons API scoped to their own groups. The board itself
never writes: lessons are moved / cancelled and weekly slots saved through
the Assistant Workspace endpoints (Admin + Assistant), and `can_edit` in the
board payload tells the page whether to offer those actions — a Team Lead
stays read-only, exactly as everywhere else (users.permissions).
"""
from __future__ import annotations

import datetime as dt

from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.users.models import Teacher
from apps.users.permissions import can_run_operations, can_view_academy, is_assistant

from .models import Group, Lesson, Room
from .services import schedule_board as service

TAGS = ["Schedule"]


class CanViewSchedule(BasePermission):
    """Admin, Team Lead or Assistant — the academy-wide schedule."""

    message = "Расписание академии доступно администратору, руководителю тренеров и ассистенту."

    def has_permission(self, request, view) -> bool:
        return can_view_academy(request.user) or is_assistant(request.user)


class ScheduleView(APIView):
    """Read only, enforced by the server: any method but GET / HEAD /
    OPTIONS is a 405 here, whatever the client (the LMS pages or the
    separate «OkurmenKIDS Schedule» site) sends."""

    permission_classes = [IsAuthenticated, CanViewSchedule]
    http_method_names = ["get", "head", "options"]


def _date(value, default: dt.date, name: str = "date") -> dt.date:
    if not value:
        return default
    try:
        return dt.date.fromisoformat(value)
    except ValueError:
        raise ValidationError({name: "Неверный формат даты (ожидается ГГГГ-ММ-ДД)."})


def _window(params) -> tuple[int, int]:
    start = service.parse_hm(params.get("start"))
    end = service.parse_hm(params.get("end"))
    if start is None or end is None:
        raise ValidationError({"start": "Укажите время начала и окончания в формате ЧЧ:ММ."})
    if end <= start:
        raise ValidationError({"end": "Время окончания должно быть позже времени начала."})
    return start, end


@extend_schema(tags=TAGS, responses={200: dict})
class ScheduleOptionsView(ScheduleView):
    """GET — trainers (with their colors), rooms, open groups, statuses."""

    def get(self, request):
        return Response(service.options())


@extend_schema(tags=TAGS, responses={200: dict})
class ScheduleBoardView(ScheduleView):
    """GET ?start=&end= (inclusive, at most 31 days; default: today) and the
    filters ?teacher= ?room=1,2 ?group= ?status= — lessons with trainer
    colors and conflicts, the legend, the counters."""

    def get(self, request):
        today = timezone.localdate()
        start = _date(request.query_params.get("start"), today, "start")
        end = _date(request.query_params.get("end"), start, "end")
        if end < start or (end - start).days >= service.MAX_RANGE_DAYS:
            raise ValidationError({"end": f"Период — от 1 до {service.MAX_RANGE_DAYS} дней."})
        filters = service.ScheduleFilters.from_params(request.query_params)
        return Response(service.board(start, end, filters, can_edit=can_run_operations(request.user)))


@extend_schema(tags=TAGS, responses={200: dict})
class FreeRoomsView(ScheduleView):
    """GET ?date=&start=HH:MM&end=HH:MM [&room=1,2] — every active room: free
    or busy for that window, when it frees up, the next free interval."""

    def get(self, request):
        day = _date(request.query_params.get("date"), timezone.localdate())
        start, end = _window(request.query_params)
        rooms = service.ScheduleFilters.from_params(request.query_params).rooms
        return Response(service.room_availability(day, start, end, rooms or None))


@extend_schema(tags=TAGS, responses={200: dict})
class ConflictCheckView(ScheduleView):
    """GET ?date=&start=&end= and ?lesson= (an existing lesson at a new time)
    or ?teacher=&room=&group= — the clashes it would cause, with the other
    lesson's data. The same check the move itself enforces."""

    def get(self, request):
        params = request.query_params
        day = _date(params.get("date"), timezone.localdate())
        start, end = _window(params)
        start_time, end_time = service.as_time(start), service.as_time(end)
        lesson_id = params.get("lesson")
        if lesson_id and str(lesson_id).isdigit():
            lesson = get_object_or_404(
                Lesson.objects.select_related("group", "room", "teacher__user", "group_teacher__teacher__user"),
                pk=lesson_id,
            )
            conflicts = service.lesson_conflicts(lesson, date=day, start_time=start_time, end_time=end_time)
        else:
            def pick(model, key, related=()):
                value = params.get(key)
                if not (value and str(value).isdigit()):
                    return None
                return get_object_or_404(model.objects.select_related(*related), pk=value)

            teacher = pick(Teacher, "teacher", ("user",))
            room = pick(Room, "room")
            group = pick(Group, "group")
            conflicts = service.find_conflicts(
                date=day, start_time=start_time, end_time=end_time,
                teacher_id=teacher.pk if teacher else None, room_id=room.pk if room else None,
                group_id=group.pk if group else None,
                teacher_name=str(teacher) if teacher else "", room_name=room.name if room else "",
                group_name=group.name if group else "",
            )
        return Response({"date": day, "start": service.hm(start), "end": service.hm(end),
                         "ok": not conflicts, "conflicts": conflicts})
