"""«Параллельные занятия» API — /api/v1/parallel-lessons/.

Several groups, one room, one shared trainer, one lesson (see
services.parallel_sessions). Roles are the existing ones (users.permissions):

* Admin and Assistant — the academy's schedule operators (the same pair that
  moves/cancels lessons in the Assistant Workspace) — create, edit, cancel
  sessions and add/remove groups;
* Team Lead — reads every session, never writes (as everywhere else);
* Trainer — reads the sessions they give, marks attendance per group, adds
  homework, starts and completes their own sessions;
* Admin may also mark attendance and complete any session; the Assistant
  stays read-only on attendance/homework (IsAdminOrOwningTeacher's rule).

Every other role (accountant, director, HR, marketing, …) has no access —
payroll keeps reading the groups' lessons as before (apps.accounting).
"""
from __future__ import annotations

import datetime as dt

from django.core.exceptions import ValidationError as DjangoValidationError
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.response import Response

from apps.users.permissions import can_run_operations, can_view_academy, is_admin_user, is_assistant

from .models import Group, Lesson, ParallelSession, ParallelSessionGroup
from .parallel_session_serializers import (
    AddGroupSerializer,
    ParallelSessionCancelSerializer,
    ConflictCheckSerializer,
    ParallelSessionSerializer,
    ParallelSessionUpdateSerializer,
    ParallelSessionWriteSerializer,
    RemoveGroupSerializer,
    SessionAttendanceSerializer,
    SharedHomeworkSerializer,
)
from .serializers import HomeworkSerializer
from .services import lesson_lifecycle
from .services import parallel_sessions as service
from .services.attendance_service import bulk_mark_attendance

TAGS = ["Parallel lessons"]


def _teacher(user):
    return getattr(user, "teacher_profile", None)


def sees_all(user) -> bool:
    """Admin, Team Lead, Assistant — every session."""
    return can_view_academy(user) or is_assistant(user)


def gives(user, session: ParallelSession) -> bool:
    teacher = _teacher(user)
    return teacher is not None and teacher.pk == session.teacher_id


def capabilities(user, session: ParallelSession) -> dict:
    manage = can_run_operations(user)
    teach = is_admin_user(user) or gives(user, session)
    open_ = session.is_open
    return {
        "can_edit": manage and open_,
        "can_change_schedule": manage and session.status == ParallelSession.Status.SCHEDULED,
        "can_manage_groups": manage and session.status == ParallelSession.Status.SCHEDULED,
        "can_cancel": manage and open_,
        "can_start": teach and session.status == ParallelSession.Status.SCHEDULED,
        "can_complete": teach and open_,
        "can_mark_attendance": teach and session.status != ParallelSession.Status.CANCELLED,
        "can_add_homework": teach and session.status != ParallelSession.Status.CANCELLED,
    }


class CanUseParallelSessions(BasePermission):
    """Admin, Team Lead, Assistant or a trainer. Writes are checked per
    action (_require_manage / _require_teach)."""

    message = "Параллельные занятия доступны администратору, руководителю тренеров, ассистенту и тренерам."

    def has_permission(self, request, view) -> bool:
        return sees_all(request.user) or _teacher(request.user) is not None


def _require_manage(request) -> None:
    if not can_run_operations(request.user):
        raise PermissionDenied("Создавать и изменять параллельные занятия может администратор или ассистент.")


def _require_teach(request, session: ParallelSession) -> None:
    if not (is_admin_user(request.user) or gives(request.user, session)):
        raise PermissionDenied("Это может сделать тренер занятия или администратор.")


def _drf(exc: DjangoValidationError) -> DRFValidationError:
    if hasattr(exc, "message_dict"):
        return DRFValidationError(exc.message_dict)
    return DRFValidationError(exc.messages)


def _date_param(params, name):
    value = params.get(name)
    if not value:
        return None
    try:
        return dt.date.fromisoformat(value)
    except ValueError:
        raise DRFValidationError({name: "Неверный формат даты (ожидается ГГГГ-ММ-ДД)."})


def _int_param(params, name):
    value = params.get(name)
    return int(value) if value and str(value).isdigit() else None


@extend_schema(tags=TAGS)
class ParallelSessionViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    serializer_class = ParallelSessionSerializer
    permission_classes = [IsAuthenticated, CanUseParallelSessions]

    def get_queryset(self):
        qs = ParallelSession.objects.select_related(
            "teacher__user", "room", "subject", "created_by", "completed_by",
        )
        user = self.request.user
        if not sees_all(user):
            teacher = _teacher(user)
            if teacher is None:
                return qs.none()
            qs = qs.filter(teacher=teacher)
        if self.action != "list":
            return qs
        params = self.request.query_params
        day = _date_param(params, "date")
        if day:
            qs = qs.filter(date=day)
        date_from, date_to = _date_param(params, "date_from"), _date_param(params, "date_to")
        if date_from:
            qs = qs.filter(date__gte=date_from)
        if date_to:
            qs = qs.filter(date__lte=date_to)
        for name, field in (("teacher", "teacher_id"), ("room", "room_id")):
            value = _int_param(params, name)
            if value:
                qs = qs.filter(**{field: value})
        group = _int_param(params, "group")
        if group:
            qs = qs.filter(participants__group_id=group).distinct()
        state = params.get("status")
        if state in ParallelSession.Status.values:
            qs = qs.filter(status=state)
        return qs.order_by("-date", "-start_time", "-pk")

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["student_counts"] = None
        return context

    def _out(self, session, code=status.HTTP_200_OK):
        session = self.get_queryset().get(pk=session.pk)
        return Response(ParallelSessionSerializer(session, context=self.get_serializer_context()).data, status=code)

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        items = list(page if page is not None else queryset)
        group_ids = set(ParallelSessionGroup.objects.filter(session__in=items).values_list("group_id", flat=True))
        context = self.get_serializer_context()
        context["student_counts"] = service._active_students_by_group(group_ids)
        data = ParallelSessionSerializer(items, many=True, context=context).data
        return self.get_paginated_response(data) if page is not None else Response(data)

    # -- create / edit ------------------------------------------------------

    @extend_schema(request=ParallelSessionWriteSerializer, responses={201: ParallelSessionSerializer})
    def create(self, request):
        _require_manage(request)
        body = ParallelSessionWriteSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        data = body.validated_data
        try:
            session = service.create_session(service.SessionInput(
                teacher=data["teacher"], room=data["room"], subject=data.get("subject"), date=data["date"],
                start_time=data["start_time"], end_time=data["end_time"], groups=data["groups"],
                topic=data["topic"], description=data["description"], notes=data["notes"],
                youtube_url=data["youtube_url"], presentation_urls=data["presentation_urls"],
                programs=data.get("programs"),
            ), request.user)
        except DjangoValidationError as exc:
            raise _drf(exc)
        return self._out(session, status.HTTP_201_CREATED)

    @extend_schema(request=ParallelSessionUpdateSerializer, responses=ParallelSessionSerializer)
    def partial_update(self, request, pk=None):
        session = self.get_object()
        _require_manage(request)
        body = ParallelSessionUpdateSerializer(data=request.data, partial=True)
        body.is_valid(raise_exception=True)
        try:
            session = service.update_session(session, dict(body.validated_data), request.user)
        except DjangoValidationError as exc:
            raise _drf(exc)
        return self._out(session)

    def update(self, request, pk=None):
        return self.partial_update(request, pk)

    @extend_schema(request=ConflictCheckSerializer, responses={200: dict},
                   description="Conflicts a session with these trainer/room/groups/time would cause. Read only.")
    @action(detail=False, methods=["post"], url_path="check")
    def check(self, request):
        _require_manage(request)
        body = ConflictCheckSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        data = body.validated_data
        if data["end_time"] <= data["start_time"]:
            raise DRFValidationError({"end_time": "Время окончания должно быть позже времени начала."})
        groups = list(Group.objects.filter(pk__in=data["groups"]))
        conflicts = service.find_session_conflicts(
            date=data["date"], start_time=data["start_time"], end_time=data["end_time"],
            teacher=data.get("teacher"), room=data.get("room"), groups=groups,
            exclude_session_id=data.get("session"),
        )
        return Response({"ok": not conflicts, "conflicts": conflicts})

    # -- lifecycle ----------------------------------------------------------

    @extend_schema(request=ParallelSessionCancelSerializer, responses=ParallelSessionSerializer)
    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        session = self.get_object()
        _require_manage(request)
        body = ParallelSessionCancelSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        try:
            session = service.cancel_session(session, request.user, body.validated_data["reason"])
        except DjangoValidationError as exc:
            raise _drf(exc)
        return self._out(session)

    @extend_schema(request=None, responses=ParallelSessionSerializer)
    @action(detail=True, methods=["post"])
    def start(self, request, pk=None):
        session = self.get_object()
        _require_teach(request, session)
        try:
            session = service.start_session(session, request.user)
        except DjangoValidationError as exc:
            raise _drf(exc)
        return self._out(session)

    @extend_schema(request=None, responses=ParallelSessionSerializer,
                   description="Completes the session and every group's lesson (regular completion rules per group).")
    @action(detail=True, methods=["post"])
    def complete(self, request, pk=None):
        session = self.get_object()
        _require_teach(request, session)
        try:
            session = service.complete_session(session, request.user)
        except DjangoValidationError as exc:
            raise _drf(exc)
        return self._out(session)

    # -- groups -------------------------------------------------------------

    @extend_schema(request=AddGroupSerializer, responses=ParallelSessionSerializer)
    @action(detail=True, methods=["get", "post"])
    def groups(self, request, pk=None):
        session = self.get_object()
        if request.method == "GET":
            return Response(ParallelSessionSerializer(session, context=self.get_serializer_context()).data["groups"])
        _require_manage(request)
        body = AddGroupSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        try:
            service.add_group(session, body.validated_data["group"], request.user, body.validated_data.get("program"))
        except DjangoValidationError as exc:
            raise _drf(exc)
        return self._out(session, status.HTTP_201_CREATED)

    @extend_schema(request=RemoveGroupSerializer, responses=ParallelSessionSerializer)
    @action(detail=True, methods=["delete"], url_path=r"groups/(?P<group_id>\d+)")
    def remove_group(self, request, pk=None, group_id=None):
        session = self.get_object()
        _require_manage(request)
        body = RemoveGroupSerializer(data=request.data if isinstance(request.data, dict) else {})
        body.is_valid(raise_exception=True)
        group = get_object_or_404(Group, pk=group_id)
        try:
            service.remove_group(session, group, request.user, body.validated_data["reason"])
        except DjangoValidationError as exc:
            raise _drf(exc)
        return self._out(session)

    # -- attendance / homework / stats ---------------------------------------

    @extend_schema(request=SessionAttendanceSerializer, responses={200: dict},
                   description="GET — students grouped by group with their marks. POST — mark one group "
                               "({group, entries}); every group's attendance stays on its own lesson.")
    @action(detail=True, methods=["get", "post"])
    def attendance(self, request, pk=None):
        session = self.get_object()
        if request.method == "GET":
            return Response(service.roster(session))
        _require_teach(request, session)
        body = SessionAttendanceSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        lesson = (Lesson.objects.filter(parallel_session=session, group_id=body.validated_data["group"])
                  .exclude(status=Lesson.Status.CANCELLED).select_related("group").first())
        if lesson is None:
            raise DRFValidationError({"group": "Группа не участвует в этом занятии."})
        if not is_admin_user(request.user) and lesson_lifecycle.attendance_editing_locked(lesson):
            raise PermissionDenied("Занятие отменено — посещаемость нельзя изменять.")
        try:
            records = bulk_mark_attendance(lesson, body.validated_data["entries"])
        except DjangoValidationError as exc:
            raise _drf(exc)
        return Response({"group": lesson.group_id, "lesson": lesson.pk, "marked": len(records),
                         "roster": service.roster(session)})

    @extend_schema(request=SharedHomeworkSerializer, responses={200: dict},
                   description="GET — homework of every group's lesson. POST — the same homework for all groups "
                               "(or only `groups`), created as regular Homework of each group's lesson.")
    @action(detail=True, methods=["get", "post"])
    def homework(self, request, pk=None):
        from .models import Homework

        session = self.get_object()
        if request.method == "POST":
            _require_teach(request, session)
            body = SharedHomeworkSerializer(data=request.data)
            body.is_valid(raise_exception=True)
            data = body.validated_data
            try:
                service.add_shared_homework(session, title=data["title"], description=data["description"],
                                            deadline=data.get("deadline"), group_ids=data["groups"] or None)
            except DjangoValidationError as exc:
                raise _drf(exc)
        items = (Homework.objects.filter(lesson__parallel_session=session)
                 .exclude(lesson__status=Lesson.Status.CANCELLED)
                 .select_related("lesson__group").order_by("lesson__group__name", "created_at"))
        payload = HomeworkSerializer(items, many=True, context=self.get_serializer_context()).data
        return Response(payload, status=status.HTTP_201_CREATED if request.method == "POST" else status.HTTP_200_OK)

    @extend_schema(responses={200: dict})
    @action(detail=True, methods=["get"])
    def statistics(self, request, pk=None):
        return Response(service.statistics(self.get_object()))

    @extend_schema(responses={200: dict})
    @action(detail=True, methods=["get"])
    def history(self, request, pk=None):
        return Response(service.history(self.get_object()))

    @extend_schema(
        responses={200: dict},
        parameters=[OpenApiParameter("start", str), OpenApiParameter("end", str), OpenApiParameter("teacher", int)],
        description="Period report: totals, trainer workload (one session = one lesson), attendance by group.",
    )
    @action(detail=False, methods=["get"])
    def analytics(self, request):
        params = request.query_params
        today = timezone.localdate()
        start = _date_param(params, "start") or today.replace(day=1)
        end = _date_param(params, "end") or today
        if end < start:
            raise DRFValidationError({"end": "Конец периода раньше начала."})
        teacher_id = _int_param(params, "teacher")
        if not sees_all(request.user):
            teacher_id = _teacher(request.user).pk  # a trainer sees their own figures only
        return Response(service.analytics(start=start, end=end, teacher_id=teacher_id))

    @extend_schema(responses={200: dict}, description="Choices for the create form: trainers, rooms, open groups.")
    @action(detail=False, methods=["get"])
    def options(self, request):
        from .services.schedule_board import options

        data = options()
        counts = service._active_students_by_group([g["id"] for g in data["groups"]])
        for group in data["groups"]:
            group["students_count"] = counts.get(group["id"], 0)
        data["statuses"] = [{"value": v, "label": l} for v, l in ParallelSession.Status.choices]
        from apps.users.models import Subject

        data["subjects"] = [{"id": s.pk, "name": s.name} for s in Subject.objects.filter(is_active=True).order_by("name")]
        return Response(data)
