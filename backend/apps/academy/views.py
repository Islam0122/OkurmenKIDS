from __future__ import annotations

from django.db.models import Count, Q
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import viewsets
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend

from apps.users.models import User

from .filters import KPIFilter, ScheduleFilter
from .models import KPI, Attendance, Group, Homework, Room, Schedule, Student
from .permissions import IsAdminOrOwningTeacher, IsAdminOrReadOnly
from .serializers import (
    AttendanceSerializer,
    GroupSerializer,
    HomeworkSerializer,
    KPISerializer,
    RoomSerializer,
    ScheduleSerializer,
    StudentSerializer,
)


def _teacher_profile(request):
    return getattr(request.user, "teacher_profile", None)


def _is_admin(user) -> bool:
    return bool(user.is_superuser or user.role == User.Role.ADMIN)


@extend_schema_view(
    list=extend_schema(tags=["Rooms"]),
    retrieve=extend_schema(tags=["Rooms"]),
    create=extend_schema(tags=["Rooms"]),
    update=extend_schema(tags=["Rooms"]),
    partial_update=extend_schema(tags=["Rooms"]),
    destroy=extend_schema(tags=["Rooms"]),
)
class RoomViewSet(viewsets.ModelViewSet):
    """Classrooms. Admin manages them; everyone authenticated can read."""

    queryset = Room.objects.all()
    serializer_class = RoomSerializer
    permission_classes = [IsAdminOrReadOnly]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ["is_active"]
    search_fields = ["name", "description"]
    ordering_fields = ["name", "capacity"]
    ordering = ["name"]


@extend_schema_view(
    list=extend_schema(tags=["Students"]),
    retrieve=extend_schema(tags=["Students"]),
    create=extend_schema(tags=["Students"]),
    update=extend_schema(tags=["Students"]),
    partial_update=extend_schema(tags=["Students"]),
    destroy=extend_schema(tags=["Students"]),
)
class StudentViewSet(viewsets.ModelViewSet):
    """Students. Admin sees/manages all; a Teacher only sees their own groups' students."""

    serializer_class = StudentSerializer
    permission_classes = [IsAdminOrReadOnly]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ["group", "is_active"]
    search_fields = ["first_name", "last_name"]
    ordering_fields = ["last_name", "first_name", "created_at"]
    ordering = ["last_name", "first_name"]

    def get_queryset(self):
        qs = Student.objects.select_related("group")
        user = self.request.user
        if _is_admin(user):
            return qs
        teacher = _teacher_profile(self.request)
        if teacher is None:
            return qs.none()
        return qs.filter(group__teacher=teacher)


@extend_schema_view(
    list=extend_schema(tags=["Groups"]),
    retrieve=extend_schema(tags=["Groups"]),
    create=extend_schema(tags=["Groups"]),
    update=extend_schema(tags=["Groups"]),
    partial_update=extend_schema(tags=["Groups"]),
    destroy=extend_schema(tags=["Groups"]),
)
class GroupViewSet(viewsets.ModelViewSet):
    """Groups. Admin manages all groups; a Teacher only reads their own."""

    serializer_class = GroupSerializer
    permission_classes = [IsAdminOrReadOnly]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ["teacher", "room", "status"]
    search_fields = ["name", "teacher__user__first_name", "teacher__user__last_name"]
    ordering_fields = ["name", "start_date", "created_at"]
    ordering = ["-start_date", "name"]

    def get_queryset(self):
        qs = (
            Group.objects.select_related("teacher__user", "room")
            .annotate(
                active_students_count=Count(
                    "students", filter=Q(students__is_active=True), distinct=True
                )
            )
        )
        user = self.request.user
        if _is_admin(user):
            return qs
        teacher = _teacher_profile(self.request)
        if teacher is None:
            return qs.none()
        return qs.filter(teacher=teacher)


@extend_schema_view(
    list=extend_schema(tags=["Schedules"]),
    retrieve=extend_schema(tags=["Schedules"]),
    create=extend_schema(tags=["Schedules"]),
    update=extend_schema(tags=["Schedules"]),
    partial_update=extend_schema(tags=["Schedules"]),
    destroy=extend_schema(tags=["Schedules"]),
)
class ScheduleViewSet(viewsets.ModelViewSet):
    """Lesson schedule. Admin manages it; a Teacher only reads their groups' lessons."""

    serializer_class = ScheduleSerializer
    permission_classes = [IsAdminOrReadOnly]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class = ScheduleFilter
    ordering_fields = ["date", "start_time"]
    ordering = ["date", "start_time"]

    def get_queryset(self):
        qs = Schedule.objects.select_related("group__teacher__user", "room")
        user = self.request.user
        if _is_admin(user):
            return qs
        teacher = _teacher_profile(self.request)
        if teacher is None:
            return qs.none()
        return qs.filter(group__teacher=teacher)


@extend_schema_view(
    list=extend_schema(tags=["Attendance"]),
    retrieve=extend_schema(tags=["Attendance"]),
    create=extend_schema(tags=["Attendance"]),
    update=extend_schema(tags=["Attendance"]),
    partial_update=extend_schema(tags=["Attendance"]),
    destroy=extend_schema(tags=["Attendance"]),
)
class AttendanceViewSet(viewsets.ModelViewSet):
    """Attendance records.

    ``GET /api/v1/academy/attendance/?group=1&date=2026-09-12`` returns the
    whole group's attendance for that day, ready for a table.
    """

    serializer_class = AttendanceSerializer
    permission_classes = [IsAuthenticated, IsAdminOrOwningTeacher]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ["group", "student", "date", "status"]
    search_fields = ["student__first_name", "student__last_name", "group__name"]
    ordering_fields = ["date", "created_at"]
    ordering = ["-date"]

    def get_queryset(self):
        qs = Attendance.objects.select_related("student", "group")
        user = self.request.user
        if _is_admin(user):
            return qs
        teacher = _teacher_profile(self.request)
        if teacher is None:
            return qs.none()
        return qs.filter(group__teacher=teacher)


@extend_schema_view(
    list=extend_schema(tags=["Homework"]),
    retrieve=extend_schema(tags=["Homework"]),
    create=extend_schema(tags=["Homework"]),
    update=extend_schema(tags=["Homework"]),
    partial_update=extend_schema(tags=["Homework"]),
    destroy=extend_schema(tags=["Homework"]),
)
class HomeworkViewSet(viewsets.ModelViewSet):
    """Homework results (score 0-10 per student per day) — not the assignment itself."""

    serializer_class = HomeworkSerializer
    permission_classes = [IsAuthenticated, IsAdminOrOwningTeacher]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ["group", "student", "date"]
    search_fields = ["student__first_name", "student__last_name", "group__name"]
    ordering_fields = ["date", "score", "created_at"]
    ordering = ["-date"]

    def get_queryset(self):
        qs = Homework.objects.select_related("student", "group")
        user = self.request.user
        if _is_admin(user):
            return qs
        teacher = _teacher_profile(self.request)
        if teacher is None:
            return qs.none()
        return qs.filter(group__teacher=teacher)


@extend_schema_view(
    list=extend_schema(tags=["KPI"]),
    retrieve=extend_schema(tags=["KPI"]),
)
class KPIViewSet(viewsets.ReadOnlyModelViewSet):
    """Read-only student analytics for a period — computed from Attendance and Homework."""

    serializer_class = KPISerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class = KPIFilter
    search_fields = ["student__first_name", "student__last_name", "group__name"]
    ordering_fields = ["date_from", "date_to"]
    ordering = ["-date_to"]

    def get_queryset(self):
        qs = KPI.objects.select_related("student", "group")
        user = self.request.user
        if _is_admin(user):
            return qs
        teacher = _teacher_profile(self.request)
        if teacher is None:
            return qs.none()
        return qs.filter(group__teacher=teacher)
